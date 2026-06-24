"""Publisher node — publishes approved content to social media platforms.

Supports Instagram (photo/carousel/reel), Facebook, and TikTok.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from community_manager.config.settings import get_settings
from community_manager.graph.state import CommunityManagerState
from community_manager.models.schemas import (
    ContentType,
    Platform,
    PlatformResult,
    PublishResult,
)
from community_manager.tools.blob_media import AzureBlobMediaPublisher
from community_manager.tools.meta_api import MetaClient
from community_manager.tools.tiktok_api import TikTokClient

logger = logging.getLogger(__name__)


def _normalize_hashtag(tag: str) -> str:
    cleaned = (tag or "").strip()
    cleaned = cleaned.lstrip("#")
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[^\w]", "", cleaned, flags=re.UNICODE)
    return cleaned


def _extract_hashtags_from_caption(caption: str) -> set[str]:
    return {
        match.group(1).lower()
        for match in re.finditer(r"(?<!\w)#([\w]+)", caption or "", flags=re.UNICODE)
    }


def _build_full_caption(caption: str, hashtags: list[str]) -> str:
    base_caption = (caption or "").strip()
    hashtags_already_in_caption = _extract_hashtags_from_caption(base_caption)

    normalized_hashtags: list[str] = []
    seen: set[str] = set()
    for raw_tag in hashtags or []:
        tag = _normalize_hashtag(raw_tag)
        lowered = tag.lower()
        if not tag or lowered in seen:
            continue
        seen.add(lowered)
        normalized_hashtags.append(tag)

    tags_to_append = [
        tag for tag in normalized_hashtags
        if tag.lower() not in hashtags_already_in_caption
    ]

    if not tags_to_append:
        return base_caption

    hashtags_block = " ".join(f"#{tag}" for tag in tags_to_append)
    if not base_caption:
        return hashtags_block
    return f"{base_caption}\n\n{hashtags_block}"


def _abort_publish(reason: str) -> dict:
    logger.warning("Aborting publish: %s", reason)
    return {
        "publish_result": PublishResult(
            results=[PlatformResult(platform=Platform.INSTAGRAM, success=False, error=reason)],
            published_at=datetime.now(),
        ),
    }


def _cleanup_local_media(design) -> None:
    if not design:
        return

    raw_paths: set[str] = set()
    for image in design.images:
        if image.local_path:
            raw_paths.add(image.local_path)

    if design.video and design.video.local_path:
        raw_paths.add(design.video.local_path)

    for raw_path in raw_paths:
        try:
            Path(raw_path).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove temporary media %s: %s", raw_path, exc)


async def cleanup_remote_media(design) -> int:
    blob_names: set[str] = set()

    if not design:
        return 0

    for image in design.images:
        if image.blob_name:
            blob_names.add(image.blob_name)

    if design.video and design.video.blob_name:
        blob_names.add(design.video.blob_name)

    if not blob_names:
        return 0

    publisher = AzureBlobMediaPublisher()
    try:
        for blob_name in blob_names:
            try:
                await publisher.delete_blob(blob_name)
            except Exception as exc:  # pragma: no cover - best effort cleanup
                logger.warning("Failed to remove remote blob %s: %s", blob_name, exc)
    finally:
        await publisher.close()

    return len(blob_names)


async def publisher_node(state: CommunityManagerState) -> dict:
    """Publish content to all configured platforms."""
    logger.info("▶ Publisher node starting")

    settings = get_settings()
    strategy = state.get("strategy")
    copy = state.get("copy")
    design = state.get("design")

    if not copy:
        return _abort_publish("No copy was generated for this workflow run")

    # Build full caption
    full_caption = _build_full_caption(copy.caption, copy.hashtags)
    content_type = strategy.content_type if strategy else ContentType.TEXT_POST

    results: list[PlatformResult] = []
    meta = MetaClient()
    tiktok = TikTokClient()
    facebook_enabled = bool(settings.meta_facebook_page_id)
    tiktok_enabled = bool(settings.tiktok_access_token and settings.tiktok_open_id)

    try:
        # ── IMAGE POST ─────────────────────────────────────────
        if content_type == ContentType.IMAGE_POST:
            if not design or not design.images:
                return _abort_publish("Image post aborted because no generated images are available")

            if any(not image.url for image in design.images):
                return _abort_publish("Image post aborted because the generated media is incomplete")

            image_urls = [img.url for img in design.images if img.url]

            if not image_urls:
                return _abort_publish("Image post aborted because no image URLs are available")
            elif len(image_urls) == 1:
                r = await meta.publish_instagram_photo(image_urls[0], full_caption)
                results.append(r)
            else:
                r = await meta.publish_instagram_carousel(image_urls, full_caption)
                results.append(r)

            if facebook_enabled:
                r = await meta.publish_facebook_post(full_caption)
                results.append(r)

            if tiktok_enabled and image_urls:
                r = await tiktok.publish_photo(
                    image_urls, title=strategy.topic if strategy else "",
                    description=copy.caption[:150],
                )
                results.append(r)

        # ── VIDEO POST ─────────────────────────────────────────
        elif content_type == ContentType.VIDEO_POST:
            if not design or not design.video:
                return _abort_publish("Video post aborted because no generated video is available")

            if not design.video.url:
                return _abort_publish("Video post aborted because the generated video is incomplete")

            video_url = design.video.url
            r = await meta.publish_instagram_video(video_url, full_caption)
            results.append(r)

            if facebook_enabled:
                r = await meta.publish_facebook_post(full_caption)
                results.append(r)

            if tiktok_enabled:
                r = await tiktok.publish_video(
                    video_url, title=strategy.topic if strategy else "",
                    description=copy.caption[:150],
                )
                results.append(r)

        # ── TEXT-ONLY POST ─────────────────────────────────────
        elif content_type == ContentType.TEXT_POST:
            r = await meta.publish_instagram_text(full_caption)
            results.append(r)

            if facebook_enabled:
                r = await meta.publish_facebook_post(full_caption)
                results.append(r)

        publish_result = PublishResult(results=results, published_at=datetime.now())

        success_count = sum(1 for r in results if r.success)
        logger.info("✅ Published to %d/%d platforms", success_count, len(results))
        for r in results:
            status = "✓" if r.success else "✗"
            logger.info("   %s %s: %s", status, r.platform.value, r.post_id or r.error)

        if success_count > 0:
            await cleanup_remote_media(design)

        return {"publish_result": publish_result}

    finally:
        await meta.close()
        await tiktok.close()
        _cleanup_local_media(design)

"""Meta Business API integration — Instagram + Facebook.

Handles publishing photos, carousels, videos and text posts
to Instagram and Facebook via the Graph API.

References:
  - https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing
  - https://developers.facebook.com/docs/pages-api/posts
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx

from community_manager.config.settings import get_settings
from community_manager.models.schemas import IncomingMessage, Platform, PlatformResult, ReplyTargetType

logger = logging.getLogger(__name__)

GRAPH_API_BASE_INSTAGRAM = "https://graph.instagram.com/v25.0"
GRAPH_API_BASE_FACEBOOK = "https://graph.facebook.com/v21.0"
MEDIA_STATUS_POLL_INTERVAL_SECONDS = 10
MEDIA_STATUS_MAX_ATTEMPTS = 30
META_REQUIRED_WEBHOOK_FIELDS = (
    "comments,"
    "messages,"
    "messaging_optins,"
    "messaging_postbacks,"
    "message_reactions,"
    "messaging_referral,"
    "messaging_seen"
)


def normalize_instagram_caption(caption: str) -> str:
    """Strip common markdown markers before sending captions to Instagram."""
    if not caption:
        return ""

    normalized = caption.replace("\r\n", "\n").replace("\r", "\n").strip()

    normalized = re.sub(r"```(?:[\w+-]+)?\n?(.*?)```", lambda m: m.group(1).strip(), normalized, flags=re.S)
    normalized = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", lambda m: m.group(1).strip(), normalized)
    normalized = re.sub(r"\[([^\]]+)\]\([^\)]+\)", lambda m: m.group(1).strip(), normalized)
    normalized = re.sub(r"^\s{0,3}#{1,6}\s+", "", normalized, flags=re.M)
    normalized = re.sub(r"^\s{0,3}>\s?", "", normalized, flags=re.M)
    normalized = re.sub(r"^\s{0,3}[-*_]{3,}\s*$", "", normalized, flags=re.M)

    inline_patterns = [
        (r"(?<!\*)\*\*(?=\S)(.+?)(?<=\S)\*\*(?!\*)", r"\1"),
        (r"(?<!_)__(?=\S)(.+?)(?<=\S)__(?!_)", r"\1"),
        (r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)", r"\1"),
        (r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"\1"),
        (r"~~(?=\S)(.+?)(?<=\S)~~", r"\1"),
        (r"`([^`\n]+)`", r"\1"),
    ]
    for pattern, replacement in inline_patterns:
        previous = None
        while previous != normalized:
            previous = normalized
            normalized = re.sub(pattern, replacement, normalized)

    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _parse_meta_datetime(value: str) -> datetime:
    if not value:
        return datetime.now()

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now()


def extract_unanswered_direct_messages(
    payload: dict,
    own_username: str,
    platform: Platform = Platform.INSTAGRAM,
) -> list[IncomingMessage]:
    """Return only conversations whose latest message is an inbound user DM."""
    normalized_own_username = (own_username or "").strip().lower()
    pending_messages: list[IncomingMessage] = []

    for conversation in payload.get("data", []):
        participants = conversation.get("participants", {}).get("data", []) or []
        recent_messages = conversation.get("messages", {}).get("data", []) or []
        if not recent_messages:
            continue

        ordered_messages = sorted(
            recent_messages,
            key=lambda item: item.get("created_time") or "",
            reverse=True,
        )
        latest_message = ordered_messages[0]
        latest_sender = latest_message.get("from") or {}
        latest_sender_username = str(latest_sender.get("username") or "").strip()

        if normalized_own_username and latest_sender_username.lower() == normalized_own_username:
            continue

        latest_text = str(latest_message.get("message") or "").strip()
        if not latest_text:
            continue

        remote_participant = None
        for participant in participants:
            participant_username = str(participant.get("username") or "").strip()
            if normalized_own_username and participant_username.lower() == normalized_own_username:
                continue
            if participant.get("id") == latest_sender.get("id"):
                remote_participant = participant
                break
            if remote_participant is None:
                remote_participant = participant

        remote_id = str(latest_sender.get("id") or (remote_participant or {}).get("id") or "").strip()
        if not remote_id:
            continue

        remote_name = latest_sender_username or str((remote_participant or {}).get("username") or "").strip()
        pending_messages.append(IncomingMessage(
            platform=platform,
            sender_id=remote_id,
            sender_name=remote_name,
            text=latest_text,
            message_id=str(latest_message.get("id") or ""),
            reply_target_id=remote_id,
            reply_target_type=ReplyTargetType.DIRECT_MESSAGE,
            timestamp=_parse_meta_datetime(str(latest_message.get("created_time") or "")),
        ))

    return pending_messages


class MetaClient:
    """Client for the Meta Business API (Instagram + Facebook)."""

    def __init__(self) -> None:
        settings = get_settings()
        self.access_token = settings.meta_access_token
        self.ig_account_id = settings.meta_instagram_account_id
        self.fb_page_id = settings.meta_facebook_page_id
        self._ig_username: str | None = None
        self._http = httpx.AsyncClient(timeout=60.0)

    async def ensure_webhook_subscriptions(self) -> bool:
        """Ensure the Instagram account is subscribed to the required webhook fields."""
        if not self.access_token:
            logger.warning("Skipping Meta webhook subscription setup: META_ACCESS_TOKEN is missing")
            return False

        try:
            url = f"{GRAPH_API_BASE_INSTAGRAM}/me/subscribed_apps"
            resp = await self._http.post(url, params={
                "subscribed_fields": META_REQUIRED_WEBHOOK_FIELDS,
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            logger.info("Ensured Meta webhook subscriptions: %s", META_REQUIRED_WEBHOOK_FIELDS)
            return True
        except httpx.HTTPError as exc:
            details = exc.response.text if exc.response is not None else str(exc)
            logger.error("Failed to ensure Meta webhook subscriptions: %s", details)
            return False

    # ── Instagram ──────────────────────────────────────────────

    async def publish_instagram_photo(
        self, image_url: str, caption: str
    ) -> PlatformResult:
        """Publish a single photo to Instagram."""
        try:
            caption = normalize_instagram_caption(caption)
            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/media"
            resp = await self._http.post(url, data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            container_id = resp.json()["id"]

            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/media_publish"
            resp = await self._http.post(url, data={
                "creation_id": container_id,
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            post_id = resp.json()["id"]

            logger.info("✅ Instagram photo published: %s", post_id)
            return PlatformResult(
                platform=Platform.INSTAGRAM, success=True, post_id=post_id,
            )
        except httpx.HTTPError as exc:
            logger.error("Instagram publish error: %s", exc)
            return PlatformResult(
                platform=Platform.INSTAGRAM, success=False, error=str(exc),
            )

    async def publish_instagram_carousel(
        self, image_urls: list[str], caption: str
    ) -> PlatformResult:
        """Publish a carousel (2-10 images) to Instagram."""
        try:
            caption = normalize_instagram_caption(caption)
            container_ids: list[str] = []
            for img_url in image_urls:
                url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/media"
                resp = await self._http.post(url, data={
                    "image_url": img_url,
                    "is_carousel_item": "true",
                    "access_token": self.access_token,
                })
                resp.raise_for_status()
                container_ids.append(resp.json()["id"])

            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/media"
            resp = await self._http.post(url, data={
                "media_type": "CAROUSEL",
                "children": ",".join(container_ids),
                "caption": caption,
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            carousel_id = resp.json()["id"]

            await self._wait_for_instagram_container(carousel_id)

            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/media_publish"
            resp = await self._http.post(url, data={
                "creation_id": carousel_id,
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            post_id = resp.json()["id"]

            logger.info("✅ Instagram carousel published: %s", post_id)
            return PlatformResult(
                platform=Platform.INSTAGRAM, success=True, post_id=post_id,
            )
        except httpx.HTTPError as exc:
            logger.error("Instagram carousel error: %s", exc)
            return PlatformResult(
                platform=Platform.INSTAGRAM, success=False, error=str(exc),
            )

    async def publish_instagram_video(
        self, video_url: str, caption: str
    ) -> PlatformResult:
        """Publish a Reel (video) to Instagram."""
        try:
            caption = normalize_instagram_caption(caption)
            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/media"
            resp = await self._http.post(url, data={
                "video_url": video_url,
                "caption": caption,
                "media_type": "REELS",
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            container_id = resp.json()["id"]

            await self._wait_for_instagram_container(container_id)

            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/media_publish"
            resp = await self._http.post(url, data={
                "creation_id": container_id,
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            post_id = resp.json()["id"]

            logger.info("✅ Instagram Reel published: %s", post_id)
            return PlatformResult(
                platform=Platform.INSTAGRAM, success=True, post_id=post_id,
            )
        except httpx.HTTPError as exc:
            logger.error("Instagram video error: %s", exc)
            return PlatformResult(
                platform=Platform.INSTAGRAM, success=False, error=str(exc),
            )

    async def _wait_for_instagram_container(self, container_id: str) -> None:
        """Wait until an Instagram media container is ready to be published."""
        url = f"{GRAPH_API_BASE_INSTAGRAM}/{container_id}"
        for attempt in range(MEDIA_STATUS_MAX_ATTEMPTS):
            resp = await self._http.get(url, params={
                "fields": "status_code,status",
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            data = resp.json()
            status_code = data.get("status_code", "")

            if status_code == "FINISHED":
                return

            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram media container {container_id} failed with status {status_code}")

            logger.debug(
                "Instagram media container %s status: %s (attempt %d/%d)",
                container_id,
                status_code or data.get("status", "unknown"),
                attempt + 1,
                MEDIA_STATUS_MAX_ATTEMPTS,
            )
            await asyncio.sleep(MEDIA_STATUS_POLL_INTERVAL_SECONDS)

        raise TimeoutError(f"Instagram media container {container_id} did not become ready in time")

    async def publish_instagram_text(self, caption: str) -> PlatformResult:
        """Instagram doesn't support text-only — returns failure."""
        logger.info("Instagram doesn't support text-only posts, skipping IG")
        return PlatformResult(
            platform=Platform.INSTAGRAM, success=False,
            error="Text-only not supported on Instagram",
        )

    # ── Facebook ───────────────────────────────────────────────

    async def publish_facebook_post(
        self, message: str, link: str | None = None,
    ) -> PlatformResult:
        """Publish a post to a Facebook Page."""
        try:
            url = f"{GRAPH_API_BASE_FACEBOOK}/{self.fb_page_id}/feed"
            data: dict = {
                "message": message,
                "access_token": self.access_token,
            }
            if link:
                data["link"] = link

            resp = await self._http.post(url, data=data)
            resp.raise_for_status()
            post_id = resp.json()["id"]

            logger.info("✅ Facebook post published: %s", post_id)
            return PlatformResult(
                platform=Platform.FACEBOOK, success=True, post_id=post_id,
            )
        except httpx.HTTPError as exc:
            logger.error("Facebook publish error: %s", exc)
            return PlatformResult(
                platform=Platform.FACEBOOK, success=False, error=str(exc),
            )

    # ── Messaging ──────────────────────────────────────────────

    async def send_direct_reply(
        self, recipient_id: str, message: str, platform: Platform = Platform.INSTAGRAM
    ) -> bool:
        """Send a DM reply via the matching Meta messaging surface."""
        try:
            base_url = GRAPH_API_BASE_INSTAGRAM if platform == Platform.INSTAGRAM else GRAPH_API_BASE_FACEBOOK
            url = f"{base_url}/me/messages"
            resp = await self._http.post(url, json={
                "recipient": {"id": recipient_id},
                "message": {"text": message},
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            details = exc.response.text if exc.response is not None else str(exc)
            logger.error("%s message reply error: %s", platform.value.upper(), details)
            return False

    async def send_instagram_reply(
        self, recipient_id: str, message: str
    ) -> bool:
        """Send a reply via Instagram Messaging API."""
        return await self.send_direct_reply(recipient_id, message, Platform.INSTAGRAM)

    async def send_comment_reply(
        self, comment_id: str, message: str, platform: Platform = Platform.INSTAGRAM
    ) -> bool:
        """Reply publicly to a comment on Instagram or Facebook."""
        try:
            base_url = GRAPH_API_BASE_INSTAGRAM if platform == Platform.INSTAGRAM else GRAPH_API_BASE_FACEBOOK
            endpoint = "replies" if platform == Platform.INSTAGRAM else "comments"
            url = f"{base_url}/{comment_id}/{endpoint}"
            resp = await self._http.post(url, data={
                "message": message,
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            details = exc.response.text if exc.response is not None else str(exc)
            logger.error("%s comment reply error: %s", platform.value.upper(), details)
            return False

    async def get_post_context(self, post_context_id: str, platform: Platform = Platform.INSTAGRAM) -> str:
        """Fetch lightweight post context so comment replies stay aligned with the original publication."""
        if not post_context_id or platform != Platform.INSTAGRAM:
            return ""

        try:
            url = f"{GRAPH_API_BASE_INSTAGRAM}/{post_context_id}"
            resp = await self._http.get(url, params={
                "fields": "caption",
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            payload = resp.json()
            return (payload.get("caption") or "").strip()
        except httpx.HTTPError as exc:
            details = exc.response.text if exc.response is not None else str(exc)
            logger.warning("%s post context fetch error for %s: %s", platform.value.upper(), post_context_id, details)
            return ""

    async def get_instagram_username(self) -> str:
        """Resolve and cache the professional account username for DM polling."""
        if self._ig_username is not None:
            return self._ig_username

        if not self.ig_account_id or not self.access_token:
            self._ig_username = ""
            return self._ig_username

        try:
            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}"
            resp = await self._http.get(url, params={
                "fields": "username",
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            self._ig_username = str(resp.json().get("username") or "").strip()
        except httpx.HTTPError as exc:
            details = exc.response.text if exc.response is not None else str(exc)
            logger.warning("INSTAGRAM username lookup error: %s", details)
            self._ig_username = ""

        return self._ig_username

    async def get_unanswered_direct_messages(
        self,
        platform: Platform = Platform.INSTAGRAM,
        limit_conversations: int = 20,
        limit_messages: int = 5,
    ) -> list[IncomingMessage]:
        """Poll Instagram conversations and return only latest inbound messages with no outbound reply yet."""
        if platform != Platform.INSTAGRAM or not self.access_token or not self.ig_account_id:
            return []

        own_username = await self.get_instagram_username()
        if not own_username:
            logger.warning("Skipping Instagram DM polling because the account username could not be resolved")
            return []

        try:
            url = f"{GRAPH_API_BASE_INSTAGRAM}/{self.ig_account_id}/conversations"
            resp = await self._http.get(url, params={
                "fields": f"id,participants,messages.limit({limit_messages}){{id,message,created_time,from}}",
                "platform": platform.value,
                "limit": str(limit_conversations),
                "access_token": self.access_token,
            })
            resp.raise_for_status()
            return extract_unanswered_direct_messages(resp.json(), own_username, platform)
        except httpx.HTTPError as exc:
            details = exc.response.text if exc.response is not None else str(exc)
            logger.error("%s conversation polling error: %s", platform.value.upper(), details)
            return []

    async def close(self) -> None:
        await self._http.aclose()

"""TikTok Content Posting API integration.

Reference:
  https://developers.tiktok.com/doc/content-posting-api-get-started
"""

from __future__ import annotations

import logging

import httpx

from community_manager.config.settings import get_settings
from community_manager.models.schemas import Platform, PlatformResult

logger = logging.getLogger(__name__)

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"


class TikTokClient:
    """Client for TikTok Content Posting API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.access_token = settings.tiktok_access_token
        self.open_id = settings.tiktok_open_id
        self._http = httpx.AsyncClient(timeout=60.0)
        self._headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def publish_video(
        self, video_url: str, title: str, description: str = "",
    ) -> PlatformResult:
        """Publish a video to TikTok via URL share."""
        try:
            url = f"{TIKTOK_API_BASE}/post/publish/video/init/"
            payload = {
                "post_info": {
                    "title": title[:150],
                    "description": description[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_stitch": False,
                    "disable_comment": False,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": video_url,
                },
            }

            resp = await self._http.post(url, json=payload, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

            publish_id = data.get("data", {}).get("publish_id", "")
            logger.info("✅ TikTok video publish initiated: %s", publish_id)

            return PlatformResult(
                platform=Platform.TIKTOK,
                success=True,
                post_id=publish_id,
            )
        except httpx.HTTPError as exc:
            logger.error("TikTok publish error: %s", exc)
            return PlatformResult(
                platform=Platform.TIKTOK, success=False, error=str(exc),
            )

    async def publish_photo(
        self, photo_urls: list[str], title: str, description: str = "",
    ) -> PlatformResult:
        """Publish a photo post to TikTok (photo mode)."""
        try:
            url = f"{TIKTOK_API_BASE}/post/publish/content/init/"
            payload = {
                "post_info": {
                    "title": title[:150],
                    "description": description[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_cover_index": 0,
                    "photo_images": photo_urls,
                },
                "post_mode": "DIRECT_POST",
                "media_type": "PHOTO",
            }

            resp = await self._http.post(url, json=payload, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            publish_id = data.get("data", {}).get("publish_id", "")

            logger.info("✅ TikTok photo publish initiated: %s", publish_id)
            return PlatformResult(
                platform=Platform.TIKTOK, success=True, post_id=publish_id,
            )
        except httpx.HTTPError as exc:
            logger.error("TikTok photo error: %s", exc)
            return PlatformResult(
                platform=Platform.TIKTOK, success=False, error=str(exc),
            )

    async def close(self) -> None:
        await self._http.aclose()

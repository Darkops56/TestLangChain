"""Video generation tools for the Community Manager agent.

This module now supports two paths:
- Sora support clips via Azure AI Foundry
- Composite social videos built from a continuous Azure Speech Avatar take
  plus several Sora-generated visual support clips composed with ffmpeg
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import shutil
import subprocess
import uuid
from io import BytesIO
from pathlib import Path
from typing import Sequence
from xml.sax.saxutils import escape

import httpx
from PIL import Image

from community_manager.config.settings import get_settings
from community_manager.models.schemas import FIXED_VIDEO_DURATION_SECONDS, GeneratedVideo
from community_manager.tools.blob_media import AzureBlobMediaPublisher
from community_manager.tools.training_media import resolve_avatar_background_path

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15
MAX_POLL_ATTEMPTS = 120  # ~30 minutes max wait
AVATAR_POLL_INTERVAL_SECONDS = 10
AVATAR_MAX_POLL_ATTEMPTS = 240
SUPPORTED_DURATIONS_SECONDS = (4, 8, 12)
SUPPORTED_SUPPORTING_CLIP_DURATIONS = (4, 8)
SUPPORTED_SUPPORTING_CLIP_TRANSITIONS = ("cut", "dissolve")
SUPPORTING_CLIP_DURATION_SECONDS = 8
DEFAULT_SUPPORTING_CLIP_TRANSITION = "dissolve"
SUPPORTING_CLIP_DISSOLVE_SECONDS = 0.35
MIN_SUPPORTING_CLIPS = 0
MAX_SUPPORTING_CLIPS = 1
DEFAULT_AVATAR_INTRO_SECONDS = 5.0
DEFAULT_AVATAR_OUTRO_SECONDS = 2.0
COMPOSITE_RENDER_WIDTH = 720
COMPOSITE_RENDER_HEIGHT = 1280
COMPOSITE_AVATAR_CROP_WIDTH = 820
COMPOSITE_AVATAR_CROP_HEIGHT_RATIO = 0.72
COMPOSITE_AVATAR_KEY_SIMILARITY = 0.04
COMPOSITE_AVATAR_KEY_BLEND = 0.01
COMPOSITE_AVATAR_DISPLAY_HEIGHT = 980
COMPOSITE_AVATAR_SEAT_X_OFFSET = 0
COMPOSITE_AVATAR_SEAT_Y = 280
LIGHT_LOGO_FILENAME = "novit-logo.png"
DARK_LOGO_FILENAME = "novit-logo-dark.png"
VIDEO_BRANDING_GUARDRAILS = (
    "Do not render any Novit logo, wordmark, watermark, brand icon, or the word 'novit' inside the generated video. "
    "Leave the bottom-right corner visually clean so the exact official logo can be composited afterward. "
    "If any person appears, keep them secondary and non-speaking; this clip is support footage, not the main presenter take."
)


@dataclass(frozen=True)
class CompositeSupportClipPlan:
    prompt: str
    purpose: str = ""
    duration_seconds: int = SUPPORTING_CLIP_DURATION_SECONDS
    start_second: float = 0.0
    transition: str = DEFAULT_SUPPORTING_CLIP_TRANSITION


@dataclass(frozen=True)
class CompositeVideoPlan:
    avatar_script: str
    supporting_clips: list[CompositeSupportClipPlan]
    duration_seconds: int = FIXED_VIDEO_DURATION_SECONDS
    style_notes: str = ""
    avatar_intro_seconds: float = DEFAULT_AVATAR_INTRO_SECONDS
    avatar_outro_seconds: float = DEFAULT_AVATAR_OUTRO_SECONDS


def _normalize_duration_seconds(duration_seconds: int) -> int:
    for supported_duration in SUPPORTED_DURATIONS_SECONDS:
        if duration_seconds <= supported_duration:
            return supported_duration
    return SUPPORTED_DURATIONS_SECONDS[-1]


def _normalize_supporting_clip_duration_seconds(duration_seconds: int | None) -> int:
    if duration_seconds is None:
        return SUPPORTING_CLIP_DURATION_SECONDS

    for supported_duration in SUPPORTED_SUPPORTING_CLIP_DURATIONS:
        if duration_seconds <= supported_duration:
            return supported_duration
    return SUPPORTED_SUPPORTING_CLIP_DURATIONS[-1]


def _normalize_supporting_clip_transition(transition: str | None) -> str:
    normalized_transition = str(transition or "").strip().lower()
    if normalized_transition in SUPPORTED_SUPPORTING_CLIP_TRANSITIONS:
        return normalized_transition
    return DEFAULT_SUPPORTING_CLIP_TRANSITION


def _append_video_branding_guardrails(prompt: str) -> str:
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        return VIDEO_BRANDING_GUARDRAILS
    return f"{cleaned_prompt}\n\n{VIDEO_BRANDING_GUARDRAILS}"


def _resolve_logo_asset_path(settings, *, use_dark_variant: bool) -> Path | None:
    filename = DARK_LOGO_FILENAME if use_dark_variant else LIGHT_LOGO_FILENAME
    candidate = settings.brand_assets_path / filename
    if candidate.exists():
        return candidate
    fallback = settings.brand_assets_path / LIGHT_LOGO_FILENAME
    return fallback if fallback.exists() else None


def _build_avatar_ssml(script: str, *, voice_name: str) -> str:
    clean_script = " ".join((script or "").split())
    escaped_script = escape(clean_script)
    escaped_script = re.sub(r"([,;:])\s+", r"\1<break time='180ms'/> ", escaped_script)
    escaped_script = re.sub(r"([.!?])\s+", r"\1<break time='360ms'/> ", escaped_script)
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='es-AR'>"
        f"<voice name='{voice_name}'>"
        "<prosody rate='-4%'>"
        f"<lang xml:lang='es-AR'>{escaped_script}</lang>"
        "</prosody>"
        "</voice>"
        "</speak>"
    )


def _required_total_duration_seconds(plan: CompositeVideoPlan) -> float:
    latest_clip_end = max(
        (
            max(float(clip.start_second), 0.0)
            + _normalize_supporting_clip_duration_seconds(clip.duration_seconds)
            for clip in plan.supporting_clips
        ),
        default=max(float(plan.avatar_intro_seconds), 0.0),
    )
    return max(
        float(plan.duration_seconds),
        latest_clip_end + max(float(plan.avatar_outro_seconds), 0.0),
    )


def _normalize_supporting_clip_timeline(
    supporting_clips: Sequence[CompositeSupportClipPlan],
    *,
    total_duration_seconds: float,
    avatar_intro_seconds: float,
    avatar_outro_seconds: float,
) -> list[CompositeSupportClipPlan]:
    normalized_clips: list[CompositeSupportClipPlan] = []
    timeline_start = max(float(avatar_intro_seconds), 0.0)
    timeline_end = max(total_duration_seconds - max(float(avatar_outro_seconds), 0.0), timeline_start)
    cursor = timeline_start

    for clip in sorted(supporting_clips, key=lambda item: float(item.start_second)):
        duration_seconds = _normalize_supporting_clip_duration_seconds(clip.duration_seconds)
        max_start = max(timeline_start, timeline_end - duration_seconds)
        requested_start = max(float(clip.start_second), timeline_start)
        start_second = min(max(requested_start, cursor), max_start)

        if start_second + duration_seconds > total_duration_seconds:
            raise RuntimeError("Support clip timeline exceeds total composite video duration")

        normalized_clips.append(
            CompositeSupportClipPlan(
                prompt=clip.prompt,
                purpose=clip.purpose,
                duration_seconds=duration_seconds,
                start_second=round(start_second, 2),
                transition=_normalize_supporting_clip_transition(clip.transition),
            )
        )
        cursor = start_second + duration_seconds + 0.35

    return normalized_clips


class AvatarBatchClient:
    """Client for Azure Speech batch avatar synthesis."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.endpoint = settings.resolved_speech_avatar_endpoint.rstrip("/")
        self.api_key = settings.azure_ai_speech_key
        self.api_version = settings.speech_avatar_api_version
        self.media_dir = settings.media_path
        self._http = httpx.AsyncClient(timeout=300.0)
        self._headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def generate_transparent_avatar(self, *, script: str) -> tuple[Path, float, str]:
        synthesis_id = f"novit-avatar-{uuid.uuid4().hex[:16]}"
        url = f"{self.endpoint}/avatar/batchsyntheses/{synthesis_id}?api-version={self.api_version}"
        payload = {
            "inputKind": "SSML",
            "inputs": [
                {
                    "content": _build_avatar_ssml(
                        script,
                        voice_name=self.settings.speech_avatar_voice,
                    )
                }
            ],
            "avatarConfig": {
                "talkingAvatarCharacter": self.settings.speech_avatar_character,
                "talkingAvatarStyle": self.settings.speech_avatar_style,
                "videoFormat": "webm",
                "videoCodec": "vp9",
                "subtitleType": "none",
                "backgroundColor": "#00000000",
                "bitrateKbps": 2000,
            },
        }

        logger.info("Submitting avatar batch job %s", synthesis_id)
        response = await self._http.put(url, json=payload, headers=self._headers)
        response.raise_for_status()

        data = await self._poll_job(synthesis_id)
        result_url = data.get("outputs", {}).get("result")
        if not result_url:
            raise RuntimeError("Avatar synthesis completed without a result URL")

        download = await self._http.get(
            result_url,
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
            follow_redirects=True,
        )
        download.raise_for_status()

        path = self.media_dir / f"avatar_{uuid.uuid4().hex[:12]}.webm"
        path.write_bytes(download.content)
        duration_ms = data.get("properties", {}).get("durationInMilliseconds") or 0
        duration_seconds = max(float(duration_ms) / 1000.0, 1.0)
        return path, duration_seconds, synthesis_id

    async def _poll_job(self, synthesis_id: str) -> dict:
        url = f"{self.endpoint}/avatar/batchsyntheses/{synthesis_id}?api-version={self.api_version}"

        for attempt in range(AVATAR_MAX_POLL_ATTEMPTS):
            response = await self._http.get(url, headers={"Ocp-Apim-Subscription-Key": self.api_key})
            response.raise_for_status()
            data = response.json()
            status = data.get("status", "Unknown")

            if status == "Succeeded":
                return data

            if status == "Failed":
                raise RuntimeError(f"Avatar batch job failed for {synthesis_id}: {data}")

            logger.debug(
                "Avatar batch job %s status: %s (attempt %d/%d)",
                synthesis_id,
                status,
                attempt + 1,
                AVATAR_MAX_POLL_ATTEMPTS,
            )
            await asyncio.sleep(AVATAR_POLL_INTERVAL_SECONDS)

        raise TimeoutError(f"Avatar batch job {synthesis_id} did not complete within timeout")

    async def close(self) -> None:
        await self._http.aclose()


class SoraClient:
    """Client for Sora 2 deployed on Azure AI Foundry."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.endpoint = settings.azure_foundry_sora_endpoint.rstrip("/")
        self.api_key = settings.azure_foundry_sora_api_key
        self.deployment = settings.azure_foundry_sora_deployment
        self.media_dir = settings.media_path
        self.blob_media = AzureBlobMediaPublisher() if settings.is_blob_media_hosting_configured else None
        self._ffmpeg_bin = shutil.which("ffmpeg")
        self._http = httpx.AsyncClient(timeout=300.0)
        self._headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def generate_video(
        self,
        prompt: str,
        duration_seconds: int = FIXED_VIDEO_DURATION_SECONDS,
        resolution: str = "720p",
        *,
        apply_logo: bool = True,
        upload_public: bool = True,
    ) -> GeneratedVideo:
        """Generate a video with Sora 2 (async: submit → poll → download)."""
        normalized_seconds = _normalize_duration_seconds(duration_seconds)
        job_id = await self._submit_job(prompt, normalized_seconds, resolution)
        logger.info("Sora 2 job submitted: %s", job_id)

        await self._poll_job(job_id)

        local_path, public_url, blob_name = await self._download(
            job_id,
            apply_logo=apply_logo,
            upload_public=upload_public,
        )

        logger.info("✅ Video generated and saved to %s", local_path)
        return GeneratedVideo(
            prompt=prompt,
            duration_seconds=normalized_seconds,
            local_path=str(local_path),
            url=public_url,
            blob_name=blob_name,
            job_id=job_id,
        )

    async def _submit_job(
        self, prompt: str, duration_seconds: int, resolution: str
    ) -> str:
        """Submit a video generation job to Sora 2."""
        url = f"{self.endpoint}/openai/v1/videos"
        prompt = _append_video_branding_guardrails(prompt)
        normalized_seconds = _normalize_duration_seconds(duration_seconds)
        if normalized_seconds != duration_seconds:
            logger.info(
                "Community video policy fixes duration to %s seconds; coercing requested duration %s",
                normalized_seconds,
                duration_seconds,
            )
        size = "720x1280"
        payload = {
            "model": self.deployment,
            "prompt": prompt,
            "seconds": str(normalized_seconds),
            "size": size,
        }

        logger.info("Submitting Sora 2 job: %.80s…", prompt)
        resp = await self._http.post(url, json=payload, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        return data["id"]

    async def _poll_job(self, job_id: str) -> None:
        """Poll a Sora 2 job until completion."""
        url = f"{self.endpoint}/openai/v1/videos/{job_id}"

        for attempt in range(MAX_POLL_ATTEMPTS):
            resp = await self._http.get(url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "unknown")

            if status == "completed":
                return

            if status in {"failed", "cancelled"}:
                error = data.get("error") or {}
                message = error.get("message") or error.get("code") or "Unknown error"
                raise RuntimeError(f"Sora job failed: {message}")

            logger.debug(
                "Sora job %s status: %s (attempt %d/%d)",
                job_id, status, attempt + 1, MAX_POLL_ATTEMPTS,
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        raise TimeoutError(f"Sora job {job_id} did not complete within timeout")

    async def _download(
        self,
        job_id: str,
        *,
        apply_logo: bool,
        upload_public: bool,
    ) -> tuple[Path, str | None, str | None]:
        """Download a completed Sora 2 video and return a public URL."""
        url = f"{self.endpoint}/openai/v1/videos/{job_id}/content?variant=video"
        resp = await self._http.get(url, headers=self._headers, follow_redirects=True)
        resp.raise_for_status()
        video_bytes = resp.content
        filename = f"sora_{uuid.uuid4().hex[:12]}.mp4"
        path = self.media_dir / filename
        path.write_bytes(video_bytes)
        if apply_logo:
            self._overlay_official_logo(path)
            video_bytes = path.read_bytes()

        if upload_public and self.blob_media:
            public_url = await self.blob_media.upload_bytes(
                filename,
                video_bytes,
                content_type="video/mp4",
            )
            return path, public_url, filename

        if upload_public:
            return path, self.settings.build_public_media_url(filename), None

        return path, None, None

    async def close(self) -> None:
        if self.blob_media:
            await self.blob_media.close()
        await self._http.aclose()

    def _extract_reference_frame(self, video_path: Path, *, near_end: bool) -> Image.Image | None:
        if not self._ffmpeg_bin:
            return None

        command = [self._ffmpeg_bin, "-hide_banner", "-loglevel", "error"]
        if near_end:
            command.extend(["-sseof", "-0.1"])
        command.extend([
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "pipe:1",
        ])

        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode != 0 or not result.stdout:
            return None

        try:
            with Image.open(BytesIO(result.stdout)) as frame:
                return frame.convert("RGBA")
        except OSError:
            return None

    def _overlay_official_logo(self, video_path: Path) -> None:
        if not self._ffmpeg_bin:
            logger.warning("ffmpeg is not available; skipping deterministic logo overlay for %s", video_path.name)
            return

        sample_frame = self._extract_reference_frame(video_path, near_end=True) or self._extract_reference_frame(video_path, near_end=False)
        if not sample_frame:
            logger.warning("Could not extract a reference frame; skipping deterministic logo overlay for %s", video_path.name)
            return

        margin = max(28, int(min(sample_frame.width, sample_frame.height) * 0.035))
        target_logo_width = max(180, int(sample_frame.width * 0.16))
        sample_width = min(target_logo_width + margin, sample_frame.width)
        sample_height = min(max(90, int(sample_frame.height * 0.18)), sample_frame.height)
        sample_box = (
            max(0, sample_frame.width - sample_width),
            max(0, sample_frame.height - sample_height),
            sample_frame.width,
            sample_frame.height,
        )
        sample_region = sample_frame.crop(sample_box).convert("L")
        mean_brightness = sum(sample_region.getdata()) / max(1, sample_region.width * sample_region.height)
        logo_path = _resolve_logo_asset_path(self.settings, use_dark_variant=mean_brightness < 150)
        if not logo_path:
            return

        with Image.open(logo_path) as logo_image:
            logo = logo_image.convert("RGBA")
            aspect_ratio = logo.width / max(1, logo.height)
            target_logo_height = max(42, int(target_logo_width / max(aspect_ratio, 1)))

        logo_x = max(0, sample_frame.width - target_logo_width - margin)
        logo_y = max(0, sample_frame.height - target_logo_height - margin)
        box_padding = max(12, int(target_logo_height * 0.25))
        box_x = max(0, logo_x - box_padding)
        box_y = max(0, logo_y - box_padding)
        box_w = min(sample_frame.width - box_x, target_logo_width + (box_padding * 2))
        box_h = min(sample_frame.height - box_y, target_logo_height + (box_padding * 2))
        box_color = "black@0.28" if mean_brightness < 150 else "white@0.22"

        branded_path = video_path.with_name(f"{video_path.stem}_branded{video_path.suffix}")
        filter_complex = (
            f"[0:v]drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color={box_color}:t=fill[bg];"
            f"[1:v]scale={target_logo_width}:{target_logo_height}[logo];"
            f"[bg][logo]overlay={logo_x}:{logo_y}:format=auto"
        )
        command = [
            self._ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(logo_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(branded_path),
        ]

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.warning(
                "ffmpeg logo overlay failed for %s: %s",
                video_path.name,
                result.stderr.strip() or result.stdout.strip(),
            )
            branded_path.unlink(missing_ok=True)
            return

        branded_path.replace(video_path)


class CompositeVideoClient:
    """Renders the final social video from one avatar take plus Sora support clips."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.media_dir = settings.media_path
        self.blob_media = AzureBlobMediaPublisher() if settings.is_blob_media_hosting_configured else None
        self._ffmpeg_bin = shutil.which("ffmpeg")
        self._avatar = AvatarBatchClient()
        self._sora = SoraClient()

    async def generate_video(self, plan: CompositeVideoPlan) -> GeneratedVideo:
        if not self._ffmpeg_bin:
            raise RuntimeError("ffmpeg is required for composite avatar video generation")

        background_path = resolve_avatar_background_path()
        if not background_path:
            raise RuntimeError("Configured avatar background image was not found in media/training")

        supporting_plans = list(plan.supporting_clips[:MAX_SUPPORTING_CLIPS])

        avatar_path: Path | None = None
        support_videos: list[GeneratedVideo] = []
        synthesis_id = ""
        try:
            avatar_path, avatar_duration_seconds, synthesis_id = await self._avatar.generate_transparent_avatar(
                script=plan.avatar_script,
            )
            final_duration_seconds = max(
                avatar_duration_seconds,
                _required_total_duration_seconds(plan),
            )
            normalized_supporting_plans = _normalize_supporting_clip_timeline(
                supporting_plans,
                total_duration_seconds=final_duration_seconds,
                avatar_intro_seconds=plan.avatar_intro_seconds,
                avatar_outro_seconds=plan.avatar_outro_seconds,
            )
            logger.info(
                "Avatar take ready at %.2fs; generating %d support clips",
                avatar_duration_seconds,
                len(normalized_supporting_plans),
            )

            for clip in normalized_supporting_plans:
                support_videos.append(
                    await self._sora.generate_video(
                        clip.prompt,
                        duration_seconds=clip.duration_seconds,
                        apply_logo=False,
                        upload_public=False,
                    )
                )

            output_path = self._compose_video(
                background_path=background_path,
                avatar_path=avatar_path,
                supporting_plans=normalized_supporting_plans,
                support_videos=support_videos,
                total_duration_seconds=final_duration_seconds,
            )
            self._sora._overlay_official_logo(output_path)
            video_bytes = output_path.read_bytes()
            blob_name = output_path.name if self.blob_media else None

            if self.blob_media:
                public_url = await self.blob_media.upload_bytes(
                    output_path.name,
                    video_bytes,
                    content_type="video/mp4",
                )
            else:
                public_url = self.settings.build_public_media_url(output_path.name)

            return GeneratedVideo(
                prompt=plan.avatar_script,
                duration_seconds=int(round(final_duration_seconds)),
                local_path=str(output_path),
                url=public_url,
                blob_name=blob_name,
                job_id=synthesis_id,
            )
        finally:
            if avatar_path:
                avatar_path.unlink(missing_ok=True)
            for support_video in support_videos:
                if support_video.local_path:
                    Path(support_video.local_path).unlink(missing_ok=True)

    def _compose_video(
        self,
        *,
        background_path: Path,
        avatar_path: Path,
        supporting_plans: Sequence[CompositeSupportClipPlan],
        support_videos: Sequence[GeneratedVideo],
        total_duration_seconds: float,
    ) -> Path:
        output_path = self.media_dir / f"composite_{uuid.uuid4().hex[:12]}.mp4"

        command = [
            self._ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-t",
            f"{total_duration_seconds:.2f}",
            "-i",
            str(background_path),
            "-i",
            str(avatar_path),
        ]

        for support_video in support_videos:
            if not support_video.local_path:
                continue
            command.extend(["-i", support_video.local_path])

        filter_parts = [
            (
                f"[0:v]scale={COMPOSITE_RENDER_WIDTH}:{COMPOSITE_RENDER_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={COMPOSITE_RENDER_WIDTH}:{COMPOSITE_RENDER_HEIGHT}[bg_base]"
            ),
            (
                f"[1:v]format=rgba,"
                f"crop={COMPOSITE_AVATAR_CROP_WIDTH}:trunc(ih*{COMPOSITE_AVATAR_CROP_HEIGHT_RATIO}):(iw-{COMPOSITE_AVATAR_CROP_WIDTH})/2:0,"
                f"colorkey=0x000000:{COMPOSITE_AVATAR_KEY_SIMILARITY}:{COMPOSITE_AVATAR_KEY_BLEND},"
                f"scale=-1:{COMPOSITE_AVATAR_DISPLAY_HEIGHT},"
                f"split=2[avatar_raw][avatar_shadow]"
            ),
            "[avatar_shadow]format=rgba,colorchannelmixer=rr=0:gg=0:bb=0:aa=0.30,boxblur=18:1[avatar_shadow_blur]",
            (
                f"[bg_base][avatar_shadow_blur]"
                f"overlay=(W-w)/2+{COMPOSITE_AVATAR_SEAT_X_OFFSET + 10}:{COMPOSITE_AVATAR_SEAT_Y + 12}:"
                f"format=auto[scene_shadow]"
            ),
            (
                f"[scene_shadow][avatar_raw]"
                f"overlay=(W-w)/2+{COMPOSITE_AVATAR_SEAT_X_OFFSET}:{COMPOSITE_AVATAR_SEAT_Y}:"
                f"format=auto[scene_base]"
            ),
        ]

        current_label = "scene_base"
        for index, (support_plan, support_video) in enumerate(zip(supporting_plans, support_videos), start=2):
            if not support_video.local_path:
                continue

            clip_label = f"support_clip_{index}"
            if support_plan.transition == "dissolve":
                fade_duration = min(SUPPORTING_CLIP_DISSOLVE_SECONDS, max((support_plan.duration_seconds / 2.0) - 0.05, 0.1))
                fade_out_start = max(float(support_plan.duration_seconds) - fade_duration, 0.0)
                filter_parts.append(
                    (
                        f"[{index}:v]scale={COMPOSITE_RENDER_WIDTH}:{COMPOSITE_RENDER_HEIGHT}:force_original_aspect_ratio=increase,"
                        f"crop={COMPOSITE_RENDER_WIDTH}:{COMPOSITE_RENDER_HEIGHT},format=rgba,"
                        f"fade=t=in:st=0:d={fade_duration:.2f}:alpha=1,"
                        f"fade=t=out:st={fade_out_start:.2f}:d={fade_duration:.2f}:alpha=1,"
                        f"setpts=PTS-STARTPTS+{support_plan.start_second:.2f}/TB[{clip_label}]"
                    )
                )
            else:
                filter_parts.append(
                    (
                        f"[{index}:v]scale={COMPOSITE_RENDER_WIDTH}:{COMPOSITE_RENDER_HEIGHT}:force_original_aspect_ratio=increase,"
                        f"crop={COMPOSITE_RENDER_WIDTH}:{COMPOSITE_RENDER_HEIGHT},"
                        f"setpts=PTS-STARTPTS+{support_plan.start_second:.2f}/TB[{clip_label}]"
                    )
                )
            next_label = f"scene_{index}"
            filter_parts.append(
                f"[{current_label}][{clip_label}]overlay=0:0:eof_action=pass:repeatlast=0:format=auto[{next_label}]"
            )
            current_label = next_label

        command.extend([
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            f"[{current_label}]",
            "-map",
            "1:a:0?",
            "-t",
            f"{total_duration_seconds:.2f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ])

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(
                "ffmpeg composite render failed: "
                + (result.stderr.strip() or result.stdout.strip() or "unknown error")
            )

        return output_path

    async def close(self) -> None:
        if self.blob_media:
            await self.blob_media.close()
        await self._avatar.close()
        await self._sora.close()

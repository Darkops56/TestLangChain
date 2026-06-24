"""Image generation via Azure AI Foundry REST API.

`gpt-image-2` is deployed as a model in Foundry and accessed through
the Azure OpenAI-compatible REST endpoint.

Reference:
    https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/dall-e
"""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import logging
import math
import uuid
from pathlib import Path

import httpx
from PIL import Image

from community_manager.config.settings import get_settings
from community_manager.models.schemas import GeneratedImage, MIN_IMAGE_POST_IMAGES
from community_manager.tools.blob_media import AzureBlobMediaPublisher

logger = logging.getLogger(__name__)


MAX_CONCURRENT_IMAGE_GENERATIONS = 1
IMAGE_GENERATION_TIMEOUT_SECONDS = 900.0
IMAGE_GENERATION_MAX_ATTEMPTS = 5
IMAGE_GENERATION_RETRY_BASE_SECONDS = 5.0
IMAGE_GENERATION_RETRY_MAX_SECONDS = 45.0


class ImageGenClient:
    """Client for Azure image generation models deployed on Azure AI Foundry."""

    def __init__(self, *, image_model: str | None = None, quality: str | None = None, size: str | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.image_target = settings.resolve_image_generation_target(
            image_model,
            quality=quality,
            size=size,
        )
        self.endpoint = self.image_target.endpoint
        self.api_key = self.image_target.api_key
        self.deployment = self.image_target.deployment
        self.api_version = self.image_target.api_version
        self.default_size = self.image_target.size
        self.default_quality = self.image_target.quality
        self.model_name = self.image_target.model
        self.media_dir = settings.media_path
        self.blob_media = AzureBlobMediaPublisher() if settings.is_blob_media_hosting_configured else None
        self._http = httpx.AsyncClient(timeout=IMAGE_GENERATION_TIMEOUT_SECONDS)
        self.LIGHT_LOGO_FILENAME = "novit-logo.png"
        self.DARK_LOGO_FILENAME = "novit-logo-dark.png"
        self.IMAGE_BRANDING_GUARDRAILS = (
            "No render any Novit logo, wordmark, watermark, brand icon, or the word 'novit' inside the generated artwork. "
            "Leave the bottom-right corner visually clean as a safe area occupying about 22% of the width and 16% of the height, "
            "with no text, charts, icons, lines, hands, faces, or high-contrast elements, so the exact official logo can be composited afterward."
        )

    async def generate_image(
        self,
        prompt: str,
        size: str | None = None,
        quality: str | None = None,
        output_format: str = "jpeg",
    ) -> GeneratedImage:
        """Generate a single image and persist it as a public asset."""
        resolved_size = size or self.default_size
        resolved_quality = quality or self.default_quality
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}"
            f"/images/generations?api-version={self.api_version}"
        )
        payload = {
            "prompt": self._build_generation_prompt(prompt),
            "n": 1,
            "size": resolved_size,
            "quality": resolved_quality,
            "output_format": output_format.lower(),
        }
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

        logger.info(
            "Generating image with model=%s deployment=%s quality=%s: %.80s…",
            self.model_name,
            self.deployment,
            resolved_quality,
            prompt,
        )

        last_exception: Exception | None = None
        for attempt in range(1, IMAGE_GENERATION_MAX_ATTEMPTS + 1):
            try:
                resp = await self._http.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.TimeoutException as exc:
                last_exception = exc
                logger.warning(
                    "Image generation timed out on attempt %d/%d for prompt %.80s",
                    attempt,
                    IMAGE_GENERATION_MAX_ATTEMPTS,
                    prompt,
                )
                if attempt == IMAGE_GENERATION_MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(self._get_retry_delay_seconds(attempt=attempt))
            except httpx.HTTPError as exc:
                last_exception = exc
                logger.warning(
                    "Image generation request failed on attempt %d/%d for prompt %.80s: %s",
                    attempt,
                    IMAGE_GENERATION_MAX_ATTEMPTS,
                    prompt,
                    exc,
                )
                if attempt == IMAGE_GENERATION_MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(self._get_retry_delay_seconds(attempt=attempt, error=exc))
        else:
            raise RuntimeError("Image generation failed without a response") from last_exception

        result = data["data"][0]
        revised_prompt = result.get("revised_prompt", prompt)
        local_path, public_url, blob_name = await self._persist_generated_asset(result, output_format=output_format)

        logger.info("✅ Image generated and saved to %s", local_path)
        return GeneratedImage(
            prompt=revised_prompt,
            local_path=str(local_path),
            url=public_url,
            blob_name=blob_name,
        )

    async def generate_images(
        self,
        prompts: list[str],
        *,
        slide_numbers: list[int] | None = None,
        **kwargs,
    ) -> list[GeneratedImage]:
        """Generate multiple images with limited parallelism to keep review drafts responsive."""
        if not prompts:
            return []

        if slide_numbers is not None and len(slide_numbers) != len(prompts):
            raise ValueError("slide_numbers length must match prompts length")

        logger.info(
            "Generating %d images with concurrency=%d",
            len(prompts),
            min(MAX_CONCURRENT_IMAGE_GENERATIONS, len(prompts)),
        )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGE_GENERATIONS)
        required_successes = min(len(prompts), MIN_IMAGE_POST_IMAGES)
        results: list[GeneratedImage | None] = [None] * len(prompts)
        errors: list[tuple[int, Exception]] = []

        async def _generate(index: int, prompt: str) -> None:
            try:
                async with semaphore:
                    image = await self.generate_image(prompt, **kwargs)
                    target_slide_number = slide_numbers[index] if slide_numbers is not None else index + 1
                    results[index] = image.model_copy(update={"slide_number": target_slide_number})
            except Exception as exc:  # noqa: BLE001 - collect partial failures and decide after all tasks finish
                logger.warning("Image prompt %d failed: %s", index + 1, exc)
                errors.append((index, exc))

        await asyncio.gather(*(_generate(index, prompt) for index, prompt in enumerate(prompts)))

        completed = [image for image in results if image is not None]
        if len(completed) < required_successes:
            first_error = errors[0][1] if errors else RuntimeError("Not enough images were generated")
            raise RuntimeError(
                f"Image draft generated only {len(completed)} of {len(prompts)} required images"
            ) from first_error

        if errors:
            logger.warning(
                "Image draft completed with %d/%d images after %d prompt failures",
                len(completed),
                len(prompts),
                len(errors),
            )

        return completed

    def _get_retry_delay_seconds(self, *, attempt: int, error: Exception | None = None) -> float:
        if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
            retry_after = error.response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(float(retry_after), IMAGE_GENERATION_RETRY_MAX_SECONDS)
                except ValueError:
                    pass

        exponential_delay = IMAGE_GENERATION_RETRY_BASE_SECONDS * math.pow(2, max(0, attempt - 1))
        return min(exponential_delay, IMAGE_GENERATION_RETRY_MAX_SECONDS)

    def _build_generation_prompt(self, prompt: str) -> str:
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            return self.IMAGE_BRANDING_GUARDRAILS
        return f"{cleaned_prompt}\n\n{self.IMAGE_BRANDING_GUARDRAILS}"

    def _resolve_logo_asset_path(self, *, use_dark_variant: bool) -> Path | None:
        filename = self.DARK_LOGO_FILENAME if use_dark_variant else self.LIGHT_LOGO_FILENAME
        candidate = self.settings.brand_assets_path / filename
        if candidate.exists():
            return candidate
        fallback = self.settings.brand_assets_path / self.LIGHT_LOGO_FILENAME
        return fallback if fallback.exists() else None

    def _overlay_official_logo(self, image_bytes: bytes, *, output_format: str) -> bytes:
        logo_light = self.settings.brand_assets_path / self.LIGHT_LOGO_FILENAME
        if not logo_light.exists():
            return image_bytes

        with Image.open(BytesIO(image_bytes)) as source_image:
            canvas = source_image.convert("RGBA")
            margin = max(24, int(canvas.width * 0.035))
            target_logo_width = max(140, int(canvas.width * 0.2))
            sample_width = min(target_logo_width + margin, canvas.width)
            sample_height = min(max(80, int(canvas.height * 0.14)), canvas.height)
            sample_box = (
                max(0, canvas.width - sample_width),
                max(0, canvas.height - sample_height),
                canvas.width,
                canvas.height,
            )
            sample_region = canvas.crop(sample_box).convert("L")
            mean_brightness = sum(sample_region.getdata()) / max(1, sample_region.width * sample_region.height)
            logo_path = self._resolve_logo_asset_path(use_dark_variant=mean_brightness < 150)
            if not logo_path:
                return image_bytes

            with Image.open(logo_path) as logo_image:
                logo = logo_image.convert("RGBA")
                aspect_ratio = logo.width / max(1, logo.height)
                target_logo_height = max(32, int(target_logo_width / max(aspect_ratio, 1)))
                logo = logo.resize((target_logo_width, target_logo_height), Image.LANCZOS)
                position = (
                    canvas.width - logo.width - margin,
                    canvas.height - logo.height - margin,
                )
                canvas.alpha_composite(logo, position)

                output = BytesIO()
                final_image = canvas.convert("RGB") if output_format.lower() in {"jpg", "jpeg"} else canvas
                if output_format.lower() in {"jpg", "jpeg"}:
                    final_image.save(output, format="JPEG", quality=95)
                else:
                    final_image.save(output, format="PNG")
                return output.getvalue()

    async def _download(self, url: str) -> bytes:
        """Download an image from a URL."""
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.content

    async def _persist_generated_asset(self, result: dict, *, output_format: str) -> tuple[Path, str, str | None]:
        """Persist either a base64 or URL image response and return its public URL."""
        image_bytes: bytes | None = None
        if result.get("b64_json"):
            image_bytes = base64.b64decode(result["b64_json"])
        elif result.get("url"):
            image_bytes = await self._download(result["url"])

        if not image_bytes:
            raise RuntimeError("Image generation succeeded but returned no usable image payload")

        image_bytes = self._overlay_official_logo(image_bytes, output_format=output_format)

        extension = "jpg" if output_format.lower() in {"jpg", "jpeg"} else "png"
        content_type = "image/jpeg" if extension == "jpg" else "image/png"
        filename = f"image_{uuid.uuid4().hex[:12]}.{extension}"
        path = self.media_dir / filename
        path.write_bytes(image_bytes)

        if self.blob_media:
            public_url = await self.blob_media.upload_bytes(
                filename,
                image_bytes,
                content_type=content_type,
            )
            return path, public_url, filename

        return path, self.settings.build_public_media_url(filename), None

    async def close(self) -> None:
        if self.blob_media:
            await self.blob_media.close()
        await self._http.aclose()

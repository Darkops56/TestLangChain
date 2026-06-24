"""Application settings — loaded from shared .env via pydantic-settings.

All Community Manager vars are prefixed CM_ or use the same names as the
original project.  The shared .env is mounted by docker-compose and read
by both the .NET backend and this Python agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings


def _resolve_repo_root(from_path: Path | None = None) -> Path:
    resolved_path = (from_path or Path(__file__)).resolve()
    parent_chain = list(resolved_path.parents)

    for candidate in parent_chain:
        if (candidate / "media").exists() or (candidate / "src").exists():
            return candidate

    fallback_index = min(2, len(parent_chain) - 1)
    return parent_chain[fallback_index]


REPO_ROOT = _resolve_repo_root()


def _resolve_shared_env_root(from_path: Path | None = None) -> Path:
    resolved_path = (from_path or Path(__file__)).resolve()
    for candidate in resolved_path.parents:
        if (candidate / "docker-compose.yml").exists() or (candidate / "web-novit-ai.sln").exists():
            return candidate
    return _resolve_repo_root(from_path)


SHARED_ENV_ROOT = _resolve_shared_env_root()


def _normalize_image_model_choice(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(".", "_").replace(" ", "")
    if normalized in {"image_2", "image2", "gpt_image_2", "gptimage2"}:
        return "image_2"
    return "image_1_5"


@dataclass(frozen=True)
class ImageGenerationTarget:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str
    size: str
    quality: str
    model: str


class Settings(BaseSettings):
    """Global configuration.  Every value can be overridden via env-var."""

    model_config = {"env_file": str(SHARED_ENV_ROOT / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Azure AI Foundry: LLM ──────────────────────────────────
    azure_foundry_llm_endpoint: str = Field(default="")
    azure_foundry_llm_api_key: str = Field(default="")
    azure_foundry_llm_deployment: str = Field(default="gpt-4o")
    azure_foundry_llm_api_version: str = Field(default="2024-12-01-preview")
    azure_foundry_llm_small_deployment: str = Field(default="gpt-4o-mini")
    azure_foundry_llm_responder_deployment: str = Field(default="")

    # ── Azure AI Foundry: image generation ────────────────────
    # Legacy/default lane, currently treated as the standard `image_1_5` profile.
    azure_foundry_dalle_endpoint: str = Field(default="")
    azure_foundry_dalle_api_key: str = Field(default="")
    azure_foundry_dalle_deployment: str = Field(default="gpt-image-1-5")
    azure_foundry_dalle_api_version: str = Field(default="2025-04-01-preview")
    # Optional explicit standard/premium profiles when different resources are used.
    azure_foundry_dalle_15_endpoint: str = Field(default="")
    azure_foundry_dalle_15_api_key: str = Field(default="")
    azure_foundry_dalle_15_deployment: str = Field(default="gpt-image-1-5")
    azure_foundry_dalle_15_api_version: str = Field(default="2025-04-01-preview")
    azure_foundry_dalle_2_endpoint: str = Field(default="")
    azure_foundry_dalle_2_api_key: str = Field(default="")
    azure_foundry_dalle_2_deployment: str = Field(default="gpt-image-2")
    azure_foundry_dalle_2_api_version: str = Field(default="2025-04-01-preview")
    azure_foundry_dalle_size: str = Field(default="1024x1024")
    azure_foundry_dalle_quality: str = Field(default="high")

    # ── Azure AI Foundry: Sora 2 ───────────────────────────────
    azure_foundry_sora_endpoint: str = Field(default="")
    azure_foundry_sora_api_key: str = Field(default="")
    azure_foundry_sora_deployment: str = Field(default="sora-2-1")

    # ── Azure AI Speech: avatar batch synthesis ───────────────
    azure_ai_speech_key: str = Field(default="", validation_alias="AzureAISpeechKey")
    azure_ai_speech_url: str = Field(default="", validation_alias="AzureAISpeechUrl")
    stt_url: str = Field(default="", validation_alias="STTUrl")
    speech_avatar_endpoint: str = Field(default="", validation_alias="SpeechAvatarEndpoint")
    speech_avatar_api_version: str = Field(default="2024-08-01", validation_alias="SpeechAvatarApiVersion")
    speech_avatar_character: str = Field(default="max", validation_alias="SpeechAvatarCharacter")
    speech_avatar_style: str = Field(default="business", validation_alias="SpeechAvatarStyle")
    speech_avatar_voice: str = Field(default="es-AR-TomasNeural", validation_alias="SpeechAvatarVoice")
    speech_avatar_background_asset: str = Field(default="ventana-3.jpg", validation_alias="SpeechAvatarBackgroundAsset")

    # ── Meta Business API ──────────────────────────────────────
    meta_access_token: str = Field(default="")
    meta_instagram_account_id: str = Field(default="")
    meta_facebook_page_id: str = Field(default="")
    meta_app_secret: str = Field(default="")
    default_instagram_image_url: str = Field(default="")

    # ── TikTok ─────────────────────────────────────────────────
    tiktok_access_token: str = Field(default="")
    tiktok_open_id: str = Field(default="")

    # ── Webhook ────────────────────────────────────────────────
    webhook_verify_token: str = Field(default="")

    # ── Brand identity ─────────────────────────────────────────
    brand_name: str = Field(default="Novit Software")
    brand_voice: str = Field(default="Professional yet approachable. Innovative, clear, results-oriented.")
    brand_hashtags: str = Field(default="#NovitSoftware,#Innovation,#AI,#Technology")

    # ── Internal communication (.NET ↔ Python) ─────────────────
    dotnet_base_url: str = Field(default="http://backend:5000")
    internal_api_key: str = Field(default="")

    # ── Nurturing (newsletter AI — separate Azure endpoint) ───
    nurturing_newsletter_endpoint: str = Field(default="")
    nurturing_newsletter_deployment: str = Field(default="gpt-5.4")
    nurturing_newsletter_key: str = Field(default="")
    nurturing_newsletter_api_version: str = Field(default="2025-04-01-preview")
    nurturing_serper_api_key: str = Field(default="")
    # New: Brave Search API (free tier: 2000 queries/month, replaces Serper)
    nurturing_brave_api_key: str = Field(default="")
    # New: which search provider to use — "brave" (default) or "serper"
    nurturing_search_provider: str = Field(default="brave")
    # New: URL validation gate (HEAD request per source URL during researcher)
    nurturing_url_validation_enabled: bool = Field(default=True)
    # New: HITL #2 — pause for human review after final PPTX is generated
    nurturing_hitl2_enabled: bool = Field(default=False)
    # New: minimum insights per country (placeholders if not enough material)
    # Default 1: at least 1 per country (AR, ES, GLOBAL) = 3 total minimum
    # Set higher (e.g. 2) for stricter quality requirements
    nurturing_min_insights_per_country: int = Field(default=1)

    # ── Nurturing (IMAP/SMTP) ─────────────────────────────────
    nurturing_imap_host: str = Field(default="")
    nurturing_imap_port: int = Field(default=993)
    nurturing_smtp_host: str = Field(default="")
    nurturing_smtp_port: int = Field(default=587)
    nurturing_login_email: str = Field(default="")
    nurturing_email_password: str = Field(default="")
    nurturing_sender_email: str = Field(default="")
    nurturing_sender_name: str = Field(default="Nicolas Piccardo")
    nurturing_recipient_override: str = Field(default="")
    nurturing_reviewer_emails: str = Field(default="rodrigo.vazquez@novit.com.ar")

    # ── Pipedrive ─────────────────────────────────────────────
    pipedrive_key: str = Field(default="")
    pipedrive_base_url: str = Field(default="https://novit.pipedrive.com")

    # ── Google (OAuth2 for Docs/Drive) ────────────────────────
    google_service_account_json: str = Field(default="")
    google_service_account_file: str = Field(default="")
    google_client_id: str = Field(default="", validation_alias="Google__ClientId")
    google_client_secret: str = Field(default="", validation_alias="Google__ClientSecret")
    google_refresh_token: str = Field(default="", validation_alias="Google__RefreshToken")
    google_drive_folder_id: str = Field(default="")
    google_slides_shared_drive_name: str = Field(default="Propuestas Comerciales")
    google_slides_shared_drive_id: str = Field(default="")
    google_slides_folder_name: str = Field(default="Newsletters")
    google_slides_folder_id: str = Field(default="")
    google_slides_template_id: str = Field(default="")

    # ── General ────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    media_dir: str = Field(default="./media")
    training_media_dir: str = Field(default="./training-media")
    brand_assets_dir: str = Field(default="./brand-assets")
    public_media_base_url: str = Field(default="https://ia.novitsoftware.com/generated-media")
    azure_blob_storage_account_name: str = Field(default="")
    azure_blob_storage_account_key: str = Field(default="")
    azure_blob_storage_container_name: str = Field(default="social-publish-media")
    azure_blob_storage_sas_expiry_hours: int = Field(default=24)

    # ── Helpers ────────────────────────────────────────────────
    @property
    def media_path(self) -> Path:
        p = Path(self.media_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def training_media_path(self) -> Path:
        candidates = [
            Path(self.training_media_dir),
            Path("media/training"),
            REPO_ROOT / "media" / "training",
            Path("/app/training-media"),
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0]

    @property
    def brand_assets_path(self) -> Path:
        candidates = [
            Path(self.brand_assets_dir),
            Path("src/frontend/public/assets/images"),
            Path("frontend/public/assets/images"),
            REPO_ROOT / "src" / "frontend" / "public" / "assets" / "images",
            Path("/app/brand-assets"),
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0]

    def build_public_media_url(self, filename: str) -> str:
        base = self.public_media_base_url.rstrip("/")
        return f"{base}/{quote(filename)}"

    @property
    def is_blob_media_hosting_configured(self) -> bool:
        return bool(
            self.azure_blob_storage_account_name
            and self.azure_blob_storage_account_key
            and self.azure_blob_storage_container_name
        )

    @property
    def brand_hashtags_list(self) -> list[str]:
        return [h.strip() for h in self.brand_hashtags.split(",") if h.strip()]

    @property
    def is_nurturing_configured(self) -> bool:
        return bool(
            self.nurturing_newsletter_endpoint
            and self.nurturing_newsletter_deployment
            and self.nurturing_newsletter_key
        )

    @property
    def is_web_search_configured(self) -> bool:
        """True if the active search provider has a key configured."""
        if self.nurturing_search_provider == "brave":
            return bool(self.nurturing_brave_api_key)
        if self.nurturing_search_provider == "serper":
            return bool(self.nurturing_serper_api_key)
        # Unknown provider → check both
        return bool(self.nurturing_brave_api_key or self.nurturing_serper_api_key)

    @property
    def is_nurturing_mail_configured(self) -> bool:
        return bool(
            self.nurturing_imap_host
            and self.nurturing_smtp_host
            and self.nurturing_login_email
            and self.nurturing_email_password
        )

    @property
    def nurturing_reviewer_list(self) -> list[str]:
        return [e.strip() for e in self.nurturing_reviewer_emails.split(",") if e.strip()]

    @property
    def is_pipedrive_configured(self) -> bool:
        return bool(self.pipedrive_key and self.pipedrive_base_url)

    @property
    def is_google_slides_configured(self) -> bool:
        return bool(
            self.google_service_account_json
            or self.google_service_account_file
            or (self.google_client_id and self.google_client_secret and self.google_refresh_token)
        )

    @property
    def is_image_generation_configured(self) -> bool:
        return self.is_image_generation_model_configured("image_1_5")

    @property
    def resolved_responder_llm_deployment(self) -> str:
        return (
            self.azure_foundry_llm_responder_deployment
            or self.azure_foundry_llm_small_deployment
            or self.azure_foundry_llm_deployment
        )

    def _build_image_generation_target(
        self,
        *,
        model: str,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str,
        size: str | None = None,
        quality: str | None = None,
    ) -> ImageGenerationTarget | None:
        if not endpoint or not api_key or not deployment:
            return None

        return ImageGenerationTarget(
            endpoint=endpoint.rstrip("/"),
            api_key=api_key,
            deployment=deployment,
            api_version=api_version,
            size=size or self.azure_foundry_dalle_size,
            quality=quality or self.azure_foundry_dalle_quality,
            model=model,
        )

    def _resolve_standard_image_profile_fields(self) -> tuple[str, str, str, str]:
        return (
            self.azure_foundry_dalle_15_endpoint or self.azure_foundry_dalle_endpoint,
            self.azure_foundry_dalle_15_api_key or self.azure_foundry_dalle_api_key,
            self.azure_foundry_dalle_15_deployment or self.azure_foundry_dalle_deployment,
            self.azure_foundry_dalle_15_api_version or self.azure_foundry_dalle_api_version,
        )

    def resolve_image_generation_target(
        self,
        model: str | None = None,
        *,
        size: str | None = None,
        quality: str | None = None,
    ) -> ImageGenerationTarget:
        normalized_model = _normalize_image_model_choice(model)

        if normalized_model == "image_2":
            premium_target = self._build_image_generation_target(
                model="image_2",
                endpoint=self.azure_foundry_dalle_2_endpoint,
                api_key=self.azure_foundry_dalle_2_api_key,
                deployment=self.azure_foundry_dalle_2_deployment,
                api_version=self.azure_foundry_dalle_2_api_version,
                size=size,
                quality=quality,
            )
            if premium_target is not None:
                return premium_target
            raise RuntimeError("Image generation profile 'image_2' is not configured.")

        standard_endpoint, standard_api_key, standard_deployment, standard_api_version = self._resolve_standard_image_profile_fields()
        standard_target = self._build_image_generation_target(
            model="image_1_5",
            endpoint=standard_endpoint,
            api_key=standard_api_key,
            deployment=standard_deployment,
            api_version=standard_api_version,
            size=size,
            quality=quality,
        )
        if standard_target is not None:
            return standard_target

        raise RuntimeError("Image generation profile 'image_1_5' is not configured.")

    def is_image_generation_model_configured(self, model: str | None = None) -> bool:
        try:
            self.resolve_image_generation_target(model)
        except RuntimeError:
            return False
        return True

    @property
    def is_video_generation_configured(self) -> bool:
        return bool(
            self.azure_foundry_sora_endpoint
            and self.azure_foundry_sora_api_key
            and self.azure_foundry_sora_deployment
        )

    @property
    def resolved_speech_avatar_endpoint(self) -> str:
        if self.speech_avatar_endpoint:
            return self.speech_avatar_endpoint.rstrip("/")

        if self.azure_ai_speech_url:
            return self.azure_ai_speech_url.rstrip("/")

        if not self.stt_url:
            return ""

        parsed = urlparse(self.stt_url)
        host = (parsed.hostname or "").lower()
        if not host or ".stt.speech.microsoft.com" not in host:
            return ""

        region = host.split(".", 1)[0]
        return f"https://{region}.api.cognitive.microsoft.com"

    @property
    def is_avatar_generation_configured(self) -> bool:
        return bool(
            self.azure_ai_speech_key
            and self.resolved_speech_avatar_endpoint
            and self.speech_avatar_character
            and self.speech_avatar_style
            and self.speech_avatar_voice
        )


# Module-level singleton ────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

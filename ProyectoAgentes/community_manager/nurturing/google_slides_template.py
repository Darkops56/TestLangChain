"""Google Slides template-based publisher for AI Radar newsletters.

Clones a master template and fills placeholders with report content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from community_manager.config.settings import SHARED_ENV_ROOT, get_settings
from community_manager.models.schemas import RadarReport

logger = logging.getLogger(__name__)

NOVIT_LOGO_URL = "https://ia.novitsoftware.com/assets/images/novit-logo.png"

DEFAULT_SHARED_DRIVE_NAME = "Propuestas Comerciales"
DEFAULT_FOLDER_NAME = "Newsletters"

PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass(slots=True)
class GoogleSlidesArtifact:
    presentation_id: str
    presentation_url: str
    presentation_name: str
    shared_drive_id: str
    folder_id: str


class GoogleSlidesTemplatePublisher:
    """Clones a master template and fills placeholders with report content."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return self.settings.is_google_slides_configured

    @property
    def template_id(self) -> str:
        return self.settings.google_slides_template_id

    async def publish_report(
        self,
        report: RadarReport,
        *,
        month_label: str,
        chart_url: str | None = None,
        image_urls: list[str] | None = None,
    ) -> GoogleSlidesArtifact:
        """Clone template and fill with report content."""
        if not self.is_configured:
            raise RuntimeError("Google Slides publication is not configured.")

        if not self.template_id:
            raise RuntimeError("Google Slides template ID is not configured. Set GOOGLE_SLIDES_TEMPLATE_ID.")

        try:
            return await asyncio.to_thread(
                self._publish_report_sync,
                report,
                month_label,
                chart_url,
                image_urls or [],
            )
        except Exception:
            logger.exception("Google Slides template publication failed")
            raise

    def _publish_report_sync(
        self,
        report: RadarReport,
        month_label: str,
        chart_url: str | None,
        image_urls: list[str],
    ) -> GoogleSlidesArtifact:
        credentials = self._load_credentials()

        from googleapiclient.discovery import build

        drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        slides = build("slides", "v1", credentials=credentials, cache_discovery=False)

        shared_drive_id = self._resolve_shared_drive_id(drive)
        folder_id = self._ensure_folder(drive, shared_drive_id)
        presentation_name = _build_presentation_name(month_label)

        # Clone template
        cloned = drive.files().copy(
            fileId=self.template_id,
            body={
                "name": presentation_name,
                "parents": [folder_id],
            },
            fields="id, webViewLink",
            supportsAllDrives=True,
        ).execute()

        presentation_id = cloned["id"]
        presentation_url = cloned.get("webViewLink") or f"https://docs.google.com/presentation/d/{presentation_id}/edit"

        # Build replacement requests
        requests = self._build_replacement_requests(
            report=report,
            month_label=month_label,
            chart_url=chart_url,
            image_urls=image_urls,
        )

        # Execute batch update
        if requests:
            slides.presentations().batchUpdate(
                presentationId=presentation_id,
                body={"requests": requests},
            ).execute()

        # Make public readable
        try:
            drive.permissions().create(
                fileId=presentation_id,
                body={"type": "anyone", "role": "reader", "allowFileDiscovery": False},
                supportsAllDrives=True,
            ).execute()
        except Exception:
            logger.warning("Could not relax permissions for Slides deck %s", presentation_id, exc_info=True)

        return GoogleSlidesArtifact(
            presentation_id=presentation_id,
            presentation_url=presentation_url,
            presentation_name=presentation_name,
            shared_drive_id=shared_drive_id,
            folder_id=folder_id,
        )

    def _build_replacement_requests(
        self,
        *,
        report: RadarReport,
        month_label: str,
        chart_url: str | None,
        image_urls: list[str],
    ) -> list[dict]:
        """Build batchUpdate requests to replace placeholders with content."""
        requests: list[dict] = []

        # Cover slide placeholders
        replacements = {
            "{{report_title}}": report.report_title,
            "{{executive_summary}}": report.executive_summary,
            "{{chart_title}}": report.chart_title or "Comparativo del mes",
            "{{chart_subtitle}}": report.chart_subtitle or "Señal cuantitativa para seguimiento directivo",
        }

        # Add insight placeholders
        for i, insight in enumerate(report.insights[:3], 1):
            replacements[f"{{{{insight_{i}_headline}}}}"] = insight.headline
            replacements[f"{{{{insight_{i}_summary}}}}"] = insight.summary
            replacements[f"{{{{insight_{i}_impact}}}}"] = insight.business_impact
            replacements[f"{{{{insight_{i}_source}}}}"] = f"Fuente: {insight.source_title}"

        # Add metric placeholders (use first 3 chart items)
        for i, item in enumerate(report.chart_items[:3], 1):
            replacements[f"{{{{metric_{i}_value}}}}"] = f"{item.value:g} {item.unit}"
            replacements[f"{{{{metric_{i}_label}}}}"] = item.label

        # Add chart source
        if report.chart_items:
            replacements["{{chart_source}}"] = f"Fuente: {report.chart_items[0].source_title}"
        else:
            replacements["{{chart_source}}"] = ""

        # Build replaceAllText requests
        for placeholder, replacement in replacements.items():
            if replacement:
                requests.append({
                    "replaceAllText": {
                        "containsText": {"text": placeholder, "matchCase": False},
                        "replaceText": str(replacement),
                    }
                })

        # Add image replacement requests if URLs provided
        # Note: Image replacement requires finding the image element ID first
        # For now, we'll handle this in a separate pass if needed

        return requests

    def _load_credentials(self):
        from google.oauth2.credentials import Credentials as UserCredentials
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials

        scopes = [
            "https://www.googleapis.com/auth/presentations",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/drive.file",
        ]

        if self.settings.google_service_account_json:
            info = json.loads(self.settings.google_service_account_json)
            if "private_key" in info and isinstance(info["private_key"], str):
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            return ServiceAccountCredentials.from_service_account_info(info, scopes=scopes)

        if self.settings.google_service_account_file:
            credentials_path = Path(self.settings.google_service_account_file)
            if not credentials_path.is_absolute():
                credentials_path = SHARED_ENV_ROOT / credentials_path

            with open(credentials_path, encoding="utf-8") as handle:
                info = json.load(handle)

            if "private_key" in info and isinstance(info["private_key"], str):
                info["private_key"] = info["private_key"].replace("\\n", "\n")

            return ServiceAccountCredentials.from_service_account_info(info, scopes=scopes)

        if self.settings.google_client_id and self.settings.google_client_secret and self.settings.google_refresh_token:
            return UserCredentials(
                token=None,
                refresh_token=self.settings.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.settings.google_client_id,
                client_secret=self.settings.google_client_secret,
                scopes=scopes,
            )

        raise RuntimeError("Google credentials not configured.")

    def _resolve_shared_drive_id(self, drive) -> str:
        if self.settings.google_slides_shared_drive_id:
            return self.settings.google_slides_shared_drive_id

        target_name = self.settings.google_slides_shared_drive_name or DEFAULT_SHARED_DRIVE_NAME
        page_token = None
        while True:
            response = drive.drives().list(pageSize=100, pageToken=page_token).execute()
            for item in response.get("drives", []):
                if item.get("name") == target_name:
                    return item["id"]
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        raise RuntimeError(f"Shared drive '{target_name}' was not found.")

    def _ensure_folder(self, drive, shared_drive_id: str) -> str:
        explicit_folder_id = self.settings.google_slides_folder_id or self.settings.google_drive_folder_id
        if explicit_folder_id:
            return explicit_folder_id

        folder_name = self.settings.google_slides_folder_name or DEFAULT_FOLDER_NAME
        escaped_name = folder_name.replace("'", r"\'")
        response = drive.files().list(
            q=(
                f"mimeType = 'application/vnd.google-apps.folder' and trashed = false and "
                f"name = '{escaped_name}'"
            ),
            corpora="drive",
            driveId=shared_drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            pageSize=10,
            fields="files(id, name)",
        ).execute()

        files = response.get("files", [])
        if files:
            return files[0]["id"]

        created = drive.files().create(
            body={
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [shared_drive_id],
            },
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return created["id"]


def _build_presentation_name(month_label: str) -> str:
    return f"Novit AI Radar - {month_label.title()}"

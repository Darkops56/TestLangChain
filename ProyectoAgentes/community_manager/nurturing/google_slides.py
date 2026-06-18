from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from community_manager.config.settings import SHARED_ENV_ROOT, get_settings
from community_manager.models.schemas import RadarReport

logger = logging.getLogger(__name__)

NOVIT_LOGO_URL = "https://ia.novitsoftware.com/assets/images/novit-logo.png"

DEFAULT_SHARED_DRIVE_NAME = "Propuestas Comerciales"
DEFAULT_FOLDER_NAME = "Newsletters"

NOVIT_DEEP_BLUE = {"red": 10 / 255, "green": 0, "blue": 137 / 255}
NOVIT_CYAN = {"red": 61 / 255, "green": 176 / 255, "blue": 228 / 255}
NOVIT_MAGENTA = {"red": 186 / 255, "green": 8 / 255, "blue": 168 / 255}
NOVIT_TEXT = {"red": 31 / 255, "green": 36 / 255, "blue": 48 / 255}
NOVIT_MUTED = {"red": 88 / 255, "green": 97 / 255, "blue": 116 / 255}
NOVIT_SURFACE = {"red": 246 / 255, "green": 248 / 255, "blue": 252 / 255}
NOVIT_LIGHT_BLUE = {"red": 230 / 255, "green": 242 / 255, "blue": 1}
NOVIT_LIGHT_MAGENTA = {"red": 245 / 255, "green": 233 / 255, "blue": 250 / 255}
NOVIT_WATERMARK_DARK = {"red": 104 / 255, "green": 124 / 255, "blue": 172 / 255}
NOVIT_WATERMARK_LIGHT = {"red": 194 / 255, "green": 206 / 255, "blue": 228 / 255}
WHITE = {"red": 1, "green": 1, "blue": 1}


@dataclass(slots=True)
class GoogleSlidesArtifact:
    presentation_id: str
    presentation_url: str
    presentation_name: str
    shared_drive_id: str
    folder_id: str


class GoogleSlidesRadarPublisher:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return self.settings.is_google_slides_configured

    async def publish_report(
        self,
        report: RadarReport,
        *,
        month_label: str,
        chart_urls: list[str],
        support_visual_urls: list[str] | None = None,
    ) -> GoogleSlidesArtifact:
        if not self.is_configured:
            raise RuntimeError("Google Slides publication is mandatory but the Google service account is not configured.")

        try:
            return await asyncio.to_thread(
                self._publish_report_sync,
                report,
                month_label,
                chart_urls,
                support_visual_urls or [],
            )
        except Exception:
            logger.exception("Google Slides publication failed")
            raise

    def _publish_report_sync(
        self,
        report: RadarReport,
        month_label: str,
        chart_urls: list[str],
        support_visual_urls: list[str],
    ) -> GoogleSlidesArtifact:
        credentials = self._load_credentials()

        from googleapiclient.discovery import build

        drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        slides = build("slides", "v1", credentials=credentials, cache_discovery=False)

        shared_drive_id = self._resolve_shared_drive_id(drive)
        folder_id = self._ensure_folder(drive, shared_drive_id)
        presentation_name = _build_presentation_name(month_label)
        existing = self._find_existing_presentation(drive, folder_id, presentation_name)

        if existing:
            presentation_id = existing["id"]
            presentation_url = existing.get("webViewLink") or f"https://docs.google.com/presentation/d/{presentation_id}/edit"
        else:
            created = drive.files().create(
                body={
                    "name": presentation_name,
                    "mimeType": "application/vnd.google-apps.presentation",
                    "parents": [folder_id],
                },
                fields="id, webViewLink",
                supportsAllDrives=True,
            ).execute()
            presentation_id = created["id"]
            presentation_url = created.get("webViewLink") or f"https://docs.google.com/presentation/d/{presentation_id}/edit"

        presentation = slides.presentations().get(presentationId=presentation_id).execute()
        old_slide_ids = [slide["objectId"] for slide in presentation.get("slides", [])]

        requests = self._build_presentation_requests(
            report=report,
            month_label=month_label,
            chart_urls=chart_urls,
            support_visual_urls=support_visual_urls,
            presentation_url=presentation_url,
        )
        requests.extend({"deleteObject": {"objectId": slide_id}} for slide_id in old_slide_ids)

        slides.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests},
        ).execute()

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

        raise RuntimeError("Google Slides publication is mandatory but neither service account nor OAuth refresh-token credentials are configured.")

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

    def _find_existing_presentation(self, drive, folder_id: str, presentation_name: str) -> dict | None:
        escaped_name = presentation_name.replace("'", r"\'")
        response = drive.files().list(
            q=(
                f"mimeType = 'application/vnd.google-apps.presentation' and trashed = false and "
                f"name = '{escaped_name}' and '{folder_id}' in parents"
            ),
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            pageSize=1,
            fields="files(id, webViewLink)",
        ).execute()
        files = response.get("files", [])
        return files[0] if files else None

    def _build_presentation_requests(
        self,
        *,
        report: RadarReport,
        month_label: str,
        chart_urls: list[str],
        support_visual_urls: list[str],
        presentation_url: str,
    ) -> list[dict]:
        prefix = f"radar_{uuid.uuid4().hex[:8]}"
        cover_slide = f"{prefix}_cover"
        insights_slide = f"{prefix}_insights"
        chart_slide = f"{prefix}_chart"

        requests: list[dict] = [
            self._create_slide(cover_slide),
            self._create_slide(insights_slide),
            self._create_slide(chart_slide),
            self._set_page_background(cover_slide, NOVIT_DEEP_BLUE),
            self._set_page_background(insights_slide, WHITE),
            self._set_page_background(chart_slide, NOVIT_SURFACE),
        ]

        requests.extend(self._template_motif_requests(prefix, cover_slide, theme="cover"))
        requests.extend(self._template_motif_requests(prefix, insights_slide, theme="light"))
        requests.extend(self._template_motif_requests(prefix, chart_slide, theme="light"))

        requests.extend(self._build_cover_slide_requests(prefix, cover_slide, report, month_label, support_visual_urls))
        requests.extend(self._build_insights_slide_requests(prefix, insights_slide, report))
        requests.extend(self._build_chart_slide_requests(prefix, chart_slide, report, chart_urls, support_visual_urls, presentation_url))
        return requests

    def _build_cover_slide_requests(
        self,
        prefix: str,
        slide_id: str,
        report: RadarReport,
        month_label: str,
        support_visual_urls: list[str],
    ) -> list[dict]:
        requests: list[dict] = []
        requests.extend(self._accent_bar_requests(slide_id, f"{prefix}_cover_bar", x=0, y=389, width=720, height=16, color=NOVIT_MAGENTA))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_cover_kicker", x=56, y=44, width=240, height=24, text="AI Radar by Novit", font_size=12, color=NOVIT_CYAN, bold=True))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_cover_title", x=56, y=90, width=360, height=118, text=report.report_title, font_size=28, color=WHITE, bold=True))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_cover_subtitle", x=56, y=212, width=360, height=26, text=f"Edición mensual | {month_label.title()}", font_size=14, color=WHITE))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_cover_summary", x=56, y=258, width=392, height=92, text=report.executive_summary, font_size=14, color=WHITE))
        requests.extend(self._card_requests(slide_id, f"{prefix}_cover_logo_chip", x=550, y=40, width=132, height=46, background=WHITE, border=NOVIT_CYAN, shape_type="ROUND_RECTANGLE"))
        requests.append(self._create_image(slide_id, f"{prefix}_cover_logo", url=NOVIT_LOGO_URL, x=566, y=47, width=98, height=32))

        if support_visual_urls:
            requests.extend(self._card_requests(slide_id, f"{prefix}_cover_visual_frame", x=424, y=88, width=252, height=252, background={"red": 16 / 255, "green": 26 / 255, "blue": 78 / 255}, border=NOVIT_CYAN, shape_type="ROUND_RECTANGLE"))
            requests.append(self._create_image(slide_id, f"{prefix}_cover_visual", url=support_visual_urls[0], x=429, y=93, width=242, height=242))
        return requests

    def _build_insights_slide_requests(self, prefix: str, slide_id: str, report: RadarReport) -> list[dict]:
        requests: list[dict] = []
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_insights_title", x=42, y=26, width=360, height=28, text="Señales ejecutivas del mes", font_size=22, color=NOVIT_DEEP_BLUE, bold=True))

        cards = [
            (42, 86, 198, 260, NOVIT_DEEP_BLUE),
            (261, 86, 198, 260, NOVIT_CYAN),
            (480, 86, 198, 260, NOVIT_MAGENTA),
        ]
        for index, insight in enumerate(report.insights[:3]):
            x, y, width, height, accent = cards[index]
            requests.extend(self._card_requests(slide_id, f"{prefix}_card_{index}", x=x, y=y, width=width, height=height, background=WHITE, border=accent, shape_type="ROUND_RECTANGLE"))
            requests.extend(self._text_box_requests(slide_id, f"{prefix}_headline_{index}", x=x + 14, y=y + 14, width=width - 28, height=54, text=insight.headline, font_size=14, color=NOVIT_TEXT, bold=True))
            requests.extend(self._text_box_requests(slide_id, f"{prefix}_summary_{index}", x=x + 14, y=y + 72, width=width - 28, height=108, text=insight.summary, font_size=11, color=NOVIT_TEXT))
            requests.extend(self._text_box_requests(slide_id, f"{prefix}_impact_{index}", x=x + 14, y=y + 184, width=width - 28, height=56, text=f"Implica: {insight.business_impact}", font_size=10, color=accent, bold=True))
            requests.extend(self._text_box_requests(slide_id, f"{prefix}_source_{index}", x=x + 14, y=y + 238, width=width - 28, height=16, text=insight.source_title, font_size=9, color=NOVIT_MUTED))

        return requests

    def _build_chart_slide_requests(
        self,
        prefix: str,
        slide_id: str,
        report: RadarReport,
        chart_urls: list[str],
        support_visual_urls: list[str],
        presentation_url: str,
    ) -> list[dict]:
        requests: list[dict] = []
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_chart_title", x=42, y=26, width=380, height=28, text=report.chart_title or "Comparativo del mes", font_size=22, color=NOVIT_DEEP_BLUE, bold=True))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_chart_subtitle", x=42, y=58, width=380, height=24, text=report.chart_subtitle or "Señal cuantitativa para seguimiento directivo", font_size=11, color=NOVIT_MUTED))
        requests.extend(self._card_requests(slide_id, f"{prefix}_chart_sources_card", x=498, y=92, width=182, height=250, background=WHITE, border=NOVIT_CYAN, shape_type="ROUND_RECTANGLE"))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_chart_sources_title", x=514, y=108, width=146, height=18, text="Fuentes citadas", font_size=13, color=NOVIT_DEEP_BLUE, bold=True))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_chart_sources_body", x=514, y=136, width=146, height=186, text=self._build_sources_text(report), font_size=9, color=NOVIT_TEXT))
        requests.extend(self._text_box_requests(slide_id, f"{prefix}_chart_cta", x=42, y=360, width=624, height=18, text=f"Google Slides: {presentation_url}", font_size=11, color=NOVIT_DEEP_BLUE, bold=True))

        if chart_urls:
            requests.extend(self._card_requests(slide_id, f"{prefix}_chart_image_frame", x=37, y=92, width=440, height=254, background=WHITE, border=NOVIT_MAGENTA, shape_type="ROUND_RECTANGLE"))
            requests.append(self._create_image(slide_id, f"{prefix}_chart_image", url=chart_urls[0], x=42, y=96, width=430, height=246))
        else:
            requests.extend(self._card_requests(slide_id, f"{prefix}_chart_fallback_card", x=42, y=96, width=430, height=246, background=WHITE, border=NOVIT_MAGENTA, shape_type="ROUND_RECTANGLE"))
            requests.extend(self._text_box_requests(slide_id, f"{prefix}_chart_fallback_text", x=66, y=184, width=382, height=70, text="El gráfico cuantitativo no pudo renderizarse automáticamente, pero la edición conserva fuentes y hallazgos verificados.", font_size=15, color=NOVIT_TEXT))

        if len(support_visual_urls) > 1:
            requests.extend(self._card_requests(slide_id, f"{prefix}_chart_visual_frame", x=424, y=20, width=258, height=66, background=WHITE, border=NOVIT_CYAN, shape_type="ROUND_RECTANGLE"))
            requests.append(self._create_image(slide_id, f"{prefix}_chart_support_visual", url=support_visual_urls[1], x=430, y=22, width=246, height=62))

        return requests

    def _template_motif_requests(self, prefix: str, slide_id: str, *, theme: str) -> list[dict]:
        slide_token = slide_id.rsplit("_", 1)[-1]
        if theme == "cover":
            return [
                *self._filled_shape_requests(slide_id, f"{prefix}_{slide_token}_g1", shape_type="ELLIPSE", x=-120, y=-140, width=460, height=360, color={"red": 26 / 255, "green": 56 / 255, "blue": 162 / 255}),
                *self._filled_shape_requests(slide_id, f"{prefix}_{slide_token}_g2", shape_type="ELLIPSE", x=290, y=-90, width=420, height=320, color={"red": 86 / 255, "green": 24 / 255, "blue": 168 / 255}),
                *self._filled_shape_requests(slide_id, f"{prefix}_{slide_token}_g3", shape_type="ELLIPSE", x=150, y=148, width=520, height=320, color={"red": 9 / 255, "green": 13 / 255, "blue": 97 / 255}),
                *self._accent_bar_requests(slide_id, f"{prefix}_{slide_token}_mt", x=0, y=0, width=720, height=6, color=NOVIT_CYAN),
                *self._accent_bar_requests(slide_id, f"{prefix}_{slide_token}_mb", x=0, y=399, width=720, height=6, color=NOVIT_MAGENTA),
                *self._text_box_requests(slide_id, f"{prefix}_{slide_token}_wm", x=430, y=258, width=250, height=76, text="NOVIT", font_size=54, color=NOVIT_WATERMARK_DARK, bold=True),
            ]

        return [
            *self._filled_shape_requests(slide_id, f"{prefix}_{slide_token}_lg1", shape_type="ELLIPSE", x=520, y=-130, width=320, height=260, color=NOVIT_LIGHT_MAGENTA),
            *self._filled_shape_requests(slide_id, f"{prefix}_{slide_token}_lg2", shape_type="ELLIPSE", x=-160, y=200, width=360, height=260, color=NOVIT_LIGHT_BLUE),
            *self._filled_shape_requests(slide_id, f"{prefix}_{slide_token}_lg3", shape_type="ELLIPSE", x=210, y=305, width=420, height=180, color={"red": 236 / 255, "green": 244 / 255, "blue": 1}),
            *self._accent_bar_requests(slide_id, f"{prefix}_{slide_token}_lt", x=0, y=0, width=720, height=5, color=NOVIT_CYAN),
            *self._accent_bar_requests(slide_id, f"{prefix}_{slide_token}_lb", x=0, y=400, width=720, height=5, color=NOVIT_MAGENTA),
            *self._text_box_requests(slide_id, f"{prefix}_{slide_token}_wm", x=548, y=10, width=154, height=32, text="AI RADAR", font_size=18, color=NOVIT_WATERMARK_LIGHT, bold=True),
        ]

    def _build_sources_text(self, report: RadarReport) -> str:
        lines: list[str] = []
        seen: set[str] = set()

        for insight in report.insights:
            if insight.source_url in seen:
                continue
            seen.add(insight.source_url)
            date_suffix = f" | {insight.source_date}" if insight.source_date else ""
            lines.append(f"• {insight.source_title}{date_suffix}")

        for item in report.chart_items:
            if item.source_url in seen:
                continue
            seen.add(item.source_url)
            lines.append(f"• {item.source_title}")

        return "\n".join(lines[:8])

    def _create_slide(self, slide_id: str) -> dict:
        return {
            "createSlide": {
                "objectId": slide_id,
                "slideLayoutReference": {"predefinedLayout": "BLANK"},
            }
        }

    def _set_page_background(self, slide_id: str, color: dict) -> dict:
        return {
            "updatePageProperties": {
                "objectId": slide_id,
                "pageProperties": {
                    "pageBackgroundFill": {
                        "solidFill": {
                            "color": {"rgbColor": color}
                        }
                    }
                },
                "fields": "pageBackgroundFill.solidFill.color",
            }
        }

    def _text_box_requests(
        self,
        slide_id: str,
        object_id: str,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        text: str,
        font_size: int,
        color: dict,
        bold: bool = False,
    ) -> list[dict]:
        safe_text = text.strip() or " "
        return [
            self._create_shape(slide_id, object_id, "TEXT_BOX", x=x, y=y, width=width, height=height),
            {"insertText": {"objectId": object_id, "insertionIndex": 0, "text": safe_text}},
            {
                "updateTextStyle": {
                    "objectId": object_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "fontFamily": "Open Sans",
                        "fontSize": {"magnitude": font_size, "unit": "PT"},
                        "foregroundColor": {"opaqueColor": {"rgbColor": color}},
                        "bold": bold,
                    },
                    "fields": "fontFamily,fontSize,foregroundColor,bold",
                }
            },
        ]

    def _card_requests(
        self,
        slide_id: str,
        object_id: str,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        background: dict,
        border: dict,
        shape_type: str = "RECTANGLE",
    ) -> list[dict]:
        return [
            self._create_shape(slide_id, object_id, shape_type, x=x, y=y, width=width, height=height),
            {
                "updateShapeProperties": {
                    "objectId": object_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": background}}},
                        "outline": {
                            "outlineFill": {"solidFill": {"color": {"rgbColor": border}}},
                            "weight": {"magnitude": 1.25, "unit": "PT"},
                        },
                    },
                    "fields": "shapeBackgroundFill.solidFill.color,outline.outlineFill.solidFill.color,outline.weight",
                }
            },
        ]

    def _filled_shape_requests(
        self,
        slide_id: str,
        object_id: str,
        *,
        shape_type: str,
        x: float,
        y: float,
        width: float,
        height: float,
        color: dict,
    ) -> list[dict]:
        return [
            self._create_shape(slide_id, object_id, shape_type, x=x, y=y, width=width, height=height),
            {
                "updateShapeProperties": {
                    "objectId": object_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": color}}},
                        "outline": {"propertyState": "NOT_RENDERED"},
                    },
                    "fields": "shapeBackgroundFill.solidFill.color,outline.propertyState",
                }
            },
        ]

    def _accent_bar_requests(
        self,
        slide_id: str,
        object_id: str,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        color: dict,
    ) -> list[dict]:
        return [
            self._create_shape(slide_id, object_id, "RECTANGLE", x=x, y=y, width=width, height=height),
            {
                "updateShapeProperties": {
                    "objectId": object_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": color}}},
                        "outline": {"propertyState": "NOT_RENDERED"},
                    },
                    "fields": "shapeBackgroundFill.solidFill.color,outline.propertyState",
                }
            },
        ]

    def _create_image(
        self,
        slide_id: str,
        object_id: str,
        *,
        url: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> dict:
        return {
            "createImage": {
                "objectId": object_id,
                "url": url,
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": width, "unit": "PT"},
                        "height": {"magnitude": height, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": x,
                        "translateY": y,
                        "unit": "PT",
                    },
                },
            }
        }

    def _create_shape(
        self,
        slide_id: str,
        object_id: str,
        shape_type: str,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> dict:
        return {
            "createShape": {
                "objectId": object_id,
                "shapeType": shape_type,
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": width, "unit": "PT"},
                        "height": {"magnitude": height, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": x,
                        "translateY": y,
                        "unit": "PT",
                    },
                },
            }
        }


def _build_presentation_name(month_label: str) -> str:
    return f"Novit AI Radar - {month_label.title()}"
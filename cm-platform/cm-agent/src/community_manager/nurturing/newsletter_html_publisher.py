"""Newsletter HTML/PDF publisher.

Generates a professional HTML newsletter and converts to PDF.
Uploads both to Google Drive in the same folder as slides were.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from string import Template

from community_manager.config.settings import SHARED_ENV_ROOT, get_settings
from community_manager.models.schemas import RadarReport

logger = logging.getLogger(__name__)

NOVIT_LOGO_URL = "https://ia.novitsoftware.com/assets/images/novit-logo.png"

DEFAULT_SHARED_DRIVE_NAME = "Propuestas Comerciales"
DEFAULT_FOLDER_NAME = "Newsletters"

# Path to the HTML template file
TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_FILE = TEMPLATE_DIR / "newsletter.html"


@dataclass(slots=True)
class NewsletterArtifact:
    html_path: str
    pdf_path: str
    drive_file_id: str
    drive_url: str
    presentation_name: str


class NewsletterHTMLPublisher:
    """Generates HTML newsletter and converts to PDF."""

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
        chart_url: str | None = None,
        image_urls: list[str] | None = None,
    ) -> NewsletterArtifact:
        """Generate HTML newsletter, convert to PDF, upload to Drive."""
        if not self.is_configured:
            raise RuntimeError("Google Drive publication is not configured.")

        try:
            return await asyncio.to_thread(
                self._publish_report_sync,
                report,
                month_label,
                chart_url,
                image_urls or [],
            )
        except Exception:
            logger.exception("Newsletter HTML publication failed")
            raise

    def _publish_report_sync(
        self,
        report: RadarReport,
        month_label: str,
        chart_url: str | None,
        image_urls: list[str],
    ) -> NewsletterArtifact:
        import json
        import tempfile
        from datetime import datetime

        from google.oauth2.service_account import Credentials as ServiceAccountCredentials
        from googleapiclient.discovery import build

        credentials = self._load_credentials()
        drive = build("drive", "v3", credentials=credentials, cache_discovery=False)

        shared_drive_id = self._resolve_shared_drive_id(drive)

        # FIX: Create month-year subfolder inside Newsletters
        month_key = datetime.utcnow().strftime("%Y-%m")
        month_folder_name = f"{month_label.title()}"
        newsletters_folder_id = self._ensure_newsletters_folder(drive, shared_drive_id)
        month_folder_id = self._ensure_month_folder(drive, newsletters_folder_id, month_folder_name)

        presentation_name = f"AI Radar by Novit - {month_label}"

        # Generate HTML from template
        html_content = self._build_html_from_template(report, month_label, chart_url, image_urls)

        # Save HTML to temp file
        html_path = Path(tempfile.gettempdir()) / f"{presentation_name}.html"
        html_path.write_text(html_content, encoding="utf-8")
        logger.info("HTML saved to %s", html_path)

        # Convert to PDF
        pdf_path = self._html_to_pdf(html_path, presentation_name)
        logger.info("PDF saved to %s", pdf_path)

        # Upload PDF to Google Drive
        pdf_file_id, pdf_url = self._upload_to_drive(
            drive, pdf_path, presentation_name, month_folder_id, shared_drive_id
        )
        logger.info("PDF uploaded to Drive: %s", pdf_url)

        # Upload HTML to Google Drive as editable version
        html_file_id, html_url = self._upload_html_to_drive(
            drive, html_path, f"{presentation_name} (editable)", month_folder_id, shared_drive_id
        )
        logger.info("HTML uploaded to Drive: %s", html_url)

        return NewsletterArtifact(
            html_path=str(html_path),
            pdf_path=str(pdf_path),
            drive_file_id=pdf_file_id,
            drive_url=pdf_url,
            presentation_name=presentation_name,
        )

    # ── Folder management ───────────────────────────────────────────

    def _ensure_newsletters_folder(self, drive, shared_drive_id: str) -> str:
        """Get or create the main 'Newsletters' folder."""
        target_name = self.settings.google_slides_folder_name or DEFAULT_FOLDER_NAME

        query = (
            f"name = '{target_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{shared_drive_id}' in parents and trashed = false"
        )
        response = drive.files().list(
            q=query,
            spaces="drive",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="drive",
            driveId=shared_drive_id,
            fields="files(id, name)",
        ).execute()

        if response.get("files"):
            logger.info("Found existing Newsletters folder: %s", response["files"][0]["id"])
            return response["files"][0]["id"]

        # Create folder
        folder_metadata = {
            "name": target_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [shared_drive_id],
        }
        folder = drive.files().create(
            body=folder_metadata, supportsAllDrives=True, fields="id"
        ).execute()
        logger.info("Created Newsletters folder: %s", folder["id"])
        return folder["id"]

    def _ensure_month_folder(self, drive, parent_folder_id: str, month_name: str) -> str:
        """Get or create a month-year subfolder inside Newsletters."""
        query = (
            f"name = '{month_name}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{parent_folder_id}' in parents and trashed = false"
        )
        response = drive.files().list(
            q=query,
            spaces="drive",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            fields="files(id, name)",
        ).execute()

        if response.get("files"):
            return response["files"][0]["id"]

        # Create month subfolder
        folder_metadata = {
            "name": month_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id],
        }
        folder = drive.files().create(
            body=folder_metadata, supportsAllDrives=True, fields="id"
        ).execute()
        logger.info("Created month folder '%s': %s", month_name, folder["id"])
        return folder["id"]

    # ── HTML Template ───────────────────────────────────────────────

    def _build_html_from_template(
        self,
        report: RadarReport,
        month_label: str,
        chart_url: str | None,
        image_urls: list[str],
    ) -> str:
        """Build slide-styled HTML newsletter from external template."""
        # Read template file
        if TEMPLATE_FILE.exists():
            template_str = TEMPLATE_FILE.read_text(encoding="utf-8")
        else:
            # Fallback to inline template if file not found
            logger.warning("Template file not found at %s, using inline fallback", TEMPLATE_FILE)
            template_str = self._get_fallback_template()

        # Build cards HTML
        cards_html = ""
        if report.chart_items:
            colors = ["#3DB0E4", "#BA08A8", "#0A0089"]
            for i, item in enumerate(report.chart_items[:3]):
                color = colors[i] if i < len(colors) else "#3DB0E4"
                cards_html += f"""
                <div style="background:{color}15;padding:20px 16px;border-radius:12px;border-left:4px solid {color};margin-bottom:12px;">
                    <div style="color:{color};font-size:28px;font-weight:800;line-height:1;">{item.value:g} {item.unit}</div>
                    <div style="color:#555;font-size:13px;margin-top:6px;">{item.label}</div>
                </div>
                """

        # Build insights HTML (3 columns)
        insights_html = ""
        region_labels = ["ARGENTINA", "ESPAÑA", "EN EL MUNDO"]
        region_colors = ["#0A0089", "#BA08A8", "#0A0089"]

        for i, insight in enumerate(report.insights[:3]):
            image_html = ""
            if i < len(image_urls) and image_urls[i]:
                image_html = f'<img src="{image_urls[i]}" alt="{insight.headline}" style="width:100%;height:140px;object-fit:cover;border-radius:8px;margin-bottom:12px;">'

            impact_html = ""
            if insight.business_impact:
                impact_html = f'<p style="color:#0A0089;font-size:13px;font-weight:700;margin:0 0 6px;">Impacto:</p><p style="color:#333;font-size:13px;line-height:1.5;margin:0 0 10px;">{insight.business_impact}</p>'

            insights_html += f"""
            <div style="flex:1;min-width:220px;padding:0 12px;box-sizing:border-box;">
                <div style="display:inline-block;background:{region_colors[i]};color:white;padding:6px 16px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:1px;margin-bottom:12px;">
                    {region_labels[i]}
                </div>
                {image_html}
                <h3 style="color:#1a1a2e;font-size:16px;font-weight:700;margin:0 0 10px;line-height:1.3;">{insight.headline}</h3>
                <p style="color:#333;font-size:13px;line-height:1.55;margin:0 0 10px;">{insight.summary}</p>
                {impact_html}
                <p style="color:#3DB0E4;font-size:11px;margin:0;">Fuente: {insight.source_title}</p>
            </div>
            """

        # Build chart HTML
        chart_html = ""
        if chart_url:
            chart_html = f"""
            <div style="margin:32px 0;text-align:center;background:#f8f9fa;border-radius:12px;padding:24px;">
                <img src="{chart_url}" alt="Señal Cuantitativa" style="width:100%;max-width:700px;height:auto;border-radius:8px;">
            </div>
            """

        # Substitute variables into template
        template = Template(template_str)
        html = template.safe_substitute(
            report_title=report.report_title or "AI Radar by Novit",
            logo_url=NOVIT_LOGO_URL,
            month_label=month_label.lower(),
            executive_summary=report.executive_summary or "",
            cards_html=cards_html,
            insights_html=insights_html,
            chart_title=report.chart_title or "Sectores clave afectados por regulación IA",
            chart_subtitle=report.chart_subtitle or "Impactos regulatorios esperados en industrias de alto riesgo para 2026",
            chart_html=chart_html,
        )

        return html

    def _get_fallback_template(self) -> str:
        """Inline fallback template if external file is missing."""
        return """<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>$report_title</title>
<style>
body{font-family:'Open Sans',sans-serif;margin:0;padding:0;background:#e8e8e8;}
.slide{width:100%;max-width:1100px;margin:0 auto;background:white;}
.cover{background:linear-gradient(135deg,#0d0b4a,#1a1875);min-height:620px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;color:white;}
.cover h1{font-size:72px;font-weight:800;letter-spacing:-2px;}
.content-slide{padding:40px 48px;}
</style></head>
<body>
<div class="slide cover"><h1>AI Radar</h1><p>$month_label</p></div>
<div class="slide content-slide"><h2>Resumen Ejecutivo</h2><p>$executive_summary</p></div>
<div class="slide content-slide">$insights_html</div>
<div class="slide content-slide"><h2>Señal Cuantitativa</h2>$chart_html</div>
</body></html>"""

    # ── PDF Conversion ─────────────────────────────────────────────

    def _html_to_pdf(self, html_path: Path, presentation_name: str) -> Path:
        """Convert HTML to PDF using weasyprint with slide dimensions."""
        try:
            from weasyprint import HTML

            pdf_path = html_path.with_suffix(".pdf")
            HTML(filename=str(html_path)).write_pdf(
                str(pdf_path),
                presentational_hints=True,
            )
            return pdf_path
        except ImportError:
            logger.warning("weasyprint not installed, trying playwright")
            return self._html_to_pdf_playwright(html_path, presentation_name)

    def _html_to_pdf_playwright(self, html_path: Path, presentation_name: str) -> Path:
        """Convert HTML to PDF using playwright."""
        import subprocess
        import sys

        pdf_path = html_path.with_suffix(".pdf")

        script = f"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("file://{html_path.as_posix()}")
        await page.pdf(
            path="{pdf_path.as_posix()}",
            width="1100px",
            height="620px",
            print_background=True,
        )
        await browser.close()

asyncio.run(main())
"""
        script_path = html_path.parent / "convert_to_pdf.py"
        script_path.write_text(script)

        subprocess.run([sys.executable, str(script_path)], check=True)
        return pdf_path

    # ── Drive Upload ────────────────────────────────────────────────

    def _upload_to_drive(
        self, drive, pdf_path: Path, name: str, folder_id: str, shared_drive_id: str
    ) -> tuple[str, str]:
        """Upload PDF to Google Drive with retry on transient errors."""
        import time

        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        file_metadata = {
            "name": f"{name}.pdf",
            "mimeType": "application/pdf",
            "parents": [folder_id],
        }

        media = MediaFileUpload(str(pdf_path), mimetype="application/pdf", resumable=True)

        # Retry on transient Google API errors (503, 500)
        for attempt in range(3):
            try:
                file = drive.files().create(
                    body=file_metadata,
                    media_body=media,
                    supportsAllDrives=True,
                    fields="id, webViewLink",
                ).execute()
                break
            except HttpError as e:
                if e.resp.status in (500, 503) and attempt < 2:
                    logger.warning("Drive upload transient error (attempt %d), retrying...", attempt + 1)
                    time.sleep(2 ** attempt)
                    media = MediaFileUpload(str(pdf_path), mimetype="application/pdf", resumable=True)
                else:
                    raise

        file_id = file["id"]
        url = file.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

        # Make readable by anyone with link (with retry)
        for attempt in range(3):
            try:
                drive.permissions().create(
                    fileId=file_id,
                    body={"type": "anyone", "role": "reader"},
                    supportsAllDrives=True,
                ).execute()
                break
            except HttpError as e:
                if e.resp.status in (500, 503) and attempt < 2:
                    logger.warning("Drive permission transient error (attempt %d), retrying...", attempt + 1)
                    time.sleep(2 ** attempt)
                else:
                    raise

        return file_id, url

    def _upload_html_to_drive(
        self, drive, html_path: Path, name: str, folder_id: str, shared_drive_id: str
    ) -> tuple[str, str]:
        """Upload HTML to Google Drive as editable document with retry."""
        import time

        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        file_metadata = {
            "name": f"{name}.html",
            "mimeType": "text/html",
            "parents": [folder_id],
        }

        media = MediaFileUpload(str(html_path), mimetype="text/html", resumable=True)

        for attempt in range(3):
            try:
                file = drive.files().create(
                    body=file_metadata,
                    media_body=media,
                    supportsAllDrives=True,
                    fields="id, webViewLink",
                ).execute()
                break
            except HttpError as e:
                if e.resp.status in (500, 503) and attempt < 2:
                    logger.warning("Drive HTML upload transient error (attempt %d), retrying...", attempt + 1)
                    time.sleep(2 ** attempt)
                    media = MediaFileUpload(str(html_path), mimetype="text/html", resumable=True)
                else:
                    raise

        file_id = file["id"]
        url = file.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

        for attempt in range(3):
            try:
                drive.permissions().create(
                    fileId=file_id,
                    body={"type": "anyone", "role": "reader"},
                    supportsAllDrives=True,
                ).execute()
                break
            except HttpError as e:
                if e.resp.status in (500, 503) and attempt < 2:
                    logger.warning("Drive HTML permission transient error (attempt %d), retrying...", attempt + 1)
                    time.sleep(2 ** attempt)
                else:
                    raise

        return file_id, url

    # ── Credentials ─────────────────────────────────────────────────

    def _load_credentials(self):
        import json as _json
        from google.oauth2.credentials import Credentials as UserCredentials
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials

        scopes = [
            "https://www.googleapis.com/auth/presentations",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/drive.file",
        ]

        if self.settings.google_service_account_json:
            info = _json.loads(self.settings.google_service_account_json)
            if "private_key" in info and isinstance(info["private_key"], str):
                info["private_key"] = info["private_key"].replace("\\n", "\n")
            return ServiceAccountCredentials.from_service_account_info(info, scopes=scopes)

        if self.settings.google_service_account_file:
            credentials_path = Path(self.settings.google_service_account_file)
            if not credentials_path.is_absolute():
                credentials_path = SHARED_ENV_ROOT / credentials_path

            with open(credentials_path, encoding="utf-8") as handle:
                info = _json.load(handle)

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
                if item["name"].lower() == target_name.lower():
                    return item["id"]
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        raise RuntimeError(f"Shared drive '{target_name}' not found.")

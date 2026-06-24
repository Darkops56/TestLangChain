"""Newsletter PPTX publisher — Template-based professional design.

Uses a master template (newsletter_pptx_template.py) with pre-designed slides:
  • Slide 1: Cover (top) + Executive Summary (bottom) — Global
  • Slide 2: Argentina — Full-width insight
  • Slide 3: España — Full-width insight
  • Slide 4: Info / Conclusions (top) + Footer links (bottom)

Replaces named placeholders with real data and uploads to Google Drive.
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from community_manager.config.settings import get_settings
from community_manager.models.schemas import RadarReport
from community_manager.nurturing.newsletter_pptx_template import TEXT_DARK, TEXT_MID

logger = logging.getLogger(__name__)

DEFAULT_SHARED_DRIVE_NAME = "Propuestas Comerciales"
DEFAULT_FOLDER_NAME = "Newsletters"

SLIDE_WIDTH_IN = 13.333
SLIDE_HEIGHT_IN = 7.5

NOVIT_LOGO_URL = "https://ia.novitsoftware.com/assets/images/novit-logo.png"


@dataclass(slots=True)
class NewsletterArtifact:
    pptx_path: str
    drive_file_id: str
    drive_url: str
    presentation_name: str


class NewsletterPPTXPublisher:
    """Generates a .pptx newsletter from a master template and uploads to Drive."""

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
        if not self.is_configured:
            raise RuntimeError("Google Drive publication is not configured.")

        return await asyncio.to_thread(
            self._publish_report_sync,
            report,
            month_label,
            chart_url,
            image_urls or [],
        )

    def _publish_report_sync(
        self,
        report: RadarReport,
        month_label: str,
        chart_url: str | None,
        image_urls: list[str],
    ) -> NewsletterArtifact:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        from pptx.dml.color import RGBColor

        # Ensure template exists
        from community_manager.nurturing.newsletter_pptx_template import get_template_path
        template_path = get_template_path()

        prs = Presentation(str(template_path))

        # ── Slide 1: Cover + Summary ───────────────────────────────
        self._populate_slide_cover_summary(prs.slides[0], report, month_label)

        # ── Slide 2: Insights ──────────────────────────────────────
        self._populate_slide_insights(prs.slides[1], report, image_urls)

        # ── Slide 3: España ────────────────────────────────────────
        self._populate_slide_chart(prs.slides[2], report, image_urls)

        # ── Slide 4: Footer ────────────────────────────────────────
        self._populate_slide_footer(prs.slides[3], report, image_urls)

        # Save
        presentation_name = f"AI Radar by Novit - {month_label}"
        pptx_path = Path(f"/tmp/{presentation_name}.pptx")
        prs.save(str(pptx_path))
        logger.info("PPTX saved to %s", pptx_path)

        # Upload to Drive
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials
        from googleapiclient.discovery import build

        credentials = self._load_credentials()
        drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        shared_drive_id = self._resolve_shared_drive_id(drive)

        month_folder_name = month_label.title()
        newsletters_folder_id = self._ensure_newsletters_folder(drive, shared_drive_id)
        month_folder_id = self._ensure_month_folder(drive, newsletters_folder_id, month_folder_name)

        file_id, url = self._upload_pptx_to_drive(
            drive, pptx_path, presentation_name, month_folder_id, shared_drive_id
        )
        logger.info("PPTX uploaded to Drive: %s", url)

        return NewsletterArtifact(
            pptx_path=str(pptx_path),
            drive_file_id=file_id,
            drive_url=url,
            presentation_name=presentation_name,
        )

    # ── Placeholder population ────────────────────────────────────

    def _populate_slide_cover_summary(self, slide, report, month_label):
        """Fill Slide 1 placeholders.

        Left: executive_summary (Markdown) from the writer.
        Right: 2 native PPTX bar charts (CHART_BENCHMARK + CHART_PRICING),
        each in the SAME rectangle as the old table — no layout shift.
        Benchmark uses CYAN bars (sorted score DESC), pricing uses
        MID_NAVY bars (sorted cheapest first).
        """
        from community_manager.tools.pptx_layout import get_layout
        s1 = get_layout("slide_1")
        s1_max = s1.max_chars if s1 else 1500

        for shape in list(slide.shapes):
            name = getattr(shape, "name", "")

            if name == "PLACEHOLDER_EXECUTIVE_SUMMARY":
                text = report.executive_summary or "Análisis global de tendencias de IA para PyMEs."
                if len(text) > s1_max:
                    logger.warning(
                        "executive_summary exceeds target (%d/%d chars)",
                        len(text), s1_max,
                    )
                self._set_markdown_text(shape, text)

            elif name == "PLACEHOLDER_BENCHMARK_TABLE":
                # Template still has the table as a position placeholder;
                # we delete it and render a native bar chart in the same spot.
                self._replace_table_with_chart(slide, shape, report, kind="benchmark")

            elif name == "PLACEHOLDER_PRICING_TABLE":
                self._replace_table_with_chart(slide, shape, report, kind="pricing")

            elif name.startswith("PLACEHOLDER_METRIC_LABEL_"):
                # Label was already rendered as a separate text box in the template.
                idx = int(name.split("_")[-1])
                labels = {0: "BENCHMARK  ·  MMLU Pro", 1: "COSTO  ·  x 1M tokens"}
                self._set_text(shape, labels.get(idx, ""))

    def _replace_table_with_chart(self, slide, table_shape, report, *, kind: str):
        """Remove the table placeholder and render a native PPTX bar chart.

        The chart occupies the SAME rectangle as the table (same x, y,
        width, height) so layout doesn't shift. We use horizontal bars
        so model names read naturally on the y-axis. No GPT-image tokens
        involved — this is a native python-pptx chart.
        """
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION
        from pptx.util import Pt
        from community_manager.nurturing.newsletter_pptx_template import (
            TEXT_DARK, LIGHT_GREY,
        )

        snap = getattr(report, "benchmark_snapshot", None)
        if not snap or not snap.entries:
            # No data — leave the empty table in place rather than show
            # an empty chart. This shouldn't happen (FALLBACK seed kicks
            # in if research fails) but the guard is cheap.
            return

        if kind == "benchmark":
            # BEST at the TOP of the chart. PPTX renders horizontal bar
            # charts with the FIRST category at the BOTTOM and the LAST
            # at the TOP, so we sort score ASC and the highest score
            # ends up last (top of chart).
            entries_with_score = [
                e for e in snap.entries if e.score is not None
            ]
            entries_with_score.sort(key=lambda e: e.score)
            entries = entries_with_score[:5]
            values = [e.score for e in entries]
            labels = [f"{e.vendor} {e.model}".strip() for e in entries]
            series_name = "MMLU Pro score"
            color = (61, 176, 228)  # CYAN
            value_format = "0.0"
        else:  # pricing
            # CHEAPEST at the TOP of the chart. Same PPTX rule: first
            # category renders at the bottom, so we sort most-expensive
            # first and the cheapest ends up at the top.
            with_cost = [
                e for e in snap.entries if e.cost_per_1m_input is not None
            ]
            with_cost.sort(key=lambda e: e.cost_per_1m_input, reverse=True)
            entries = with_cost[:5]
            values = [e.cost_per_1m_input for e in entries]
            labels = [f"{e.vendor} {e.model}".strip() for e in entries]
            series_name = "USD / 1M input tokens"
            color = (26, 24, 117)  # MID_NAVY
            value_format = '"$"0.00'

        if not values or not labels:
            return

        # Capture position BEFORE deleting the table.
        left = table_shape.left
        top = table_shape.top
        width = table_shape.width
        height = table_shape.height

        # Delete the table placeholder.
        sp = table_shape._element
        sp.getparent().remove(sp)

        # Build the chart data.
        chart_data = CategoryChartData()
        chart_data.categories = labels
        chart_data.add_series(series_name, values)

        # Add the chart in the same rectangle.
        chart_shape = slide.shapes.add_chart(
            XL_CHART_TYPE.BAR_CLUSTERED,  # horizontal bars
            left, top, width, height,
            chart_data,
        )
        # Tag it so we can find it again if needed.
        chart_shape.name = f"CHART_{kind.upper()}"
        chart = chart_shape.chart
        chart.has_legend = False
        chart.has_title = False

        # Style the axes — show category labels (vendor + model) on the
        # y-axis, hide value-axis tick labels (the data label on each bar
        # already shows the number). This makes the chart self-explanatory
        # without adding visual noise.
        from pptx.oxml.ns import qn
        from lxml import etree as _etree
        # Hide value-axis tick labels (orphan numbers)
        val_tick = chart.value_axis._element.find(qn('c:tickLblPos'))
        if val_tick is None:
            val_tick = _etree.SubElement(chart.value_axis._element, qn('c:tickLblPos'))
        val_tick.set('val', 'none')
        # Show category-axis tick labels (vendor + model)
        cat_tick = chart.category_axis._element.find(qn('c:tickLblPos'))
        if cat_tick is None:
            cat_tick = _etree.SubElement(chart.category_axis._element, qn('c:tickLblPos'))
        cat_tick.set('val', 'low')
        # Style category axis text
        cat_axis = chart.category_axis
        try:
            cat_axis.tick_labels.font.size = Pt(8)
            cat_axis.tick_labels.font.name = "Open Sans"
            cat_axis.tick_labels.font.color.rgb = RGBColor(*TEXT_DARK)
        except Exception:
            pass

        # No axis lines
        chart.category_axis.format.line.fill.background()
        chart.value_axis.format.line.fill.background()

        # Subtle grid lines on the value axis only
        val_ax = chart.value_axis
        val_ax.major_gridlines.format.line.color.rgb = RGBColor(*LIGHT_GREY)
        val_ax.major_gridlines.format.line.width = Pt(0.5)

        # Color the bars + show data labels at the end of each bar.
        for series in chart.series:
            fill = series.format.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor(*color)
            series.format.line.fill.background()
            # Data labels: just the numeric value at the outside end
            # of each bar. The vendor+model name is shown on the
            # y-axis (category axis) for context.
            series.data_labels.show_value = True
            series.data_labels.show_category_name = False
            series.data_labels.position = XL_DATA_LABEL_POSITION.OUTSIDE_END
            series.data_labels.font.size = Pt(9)
            series.data_labels.font.name = "Open Sans"
            series.data_labels.font.bold = True
            series.data_labels.font.color.rgb = RGBColor(*TEXT_DARK)
            series.data_labels.number_format = value_format

        # Source attribution: show where the data came from (below the chart).
        # The snapshot's `source` field is set by the researcher.
        snap_source = getattr(snap, "source", None)
        if snap_source and kind == "benchmark":
            source_label = f"Fuente: {snap_source}"
        elif snap_source and kind == "pricing":
            source_label = f"Fuente: {snap_source}"
        else:
            source_label = ""
        if source_label:
            from pptx.util import Pt as _Pt
            from pptx.dml.color import RGBColor as _RGB
            src_box = slide.shapes.add_textbox(
                left, top + height + _Pt(2),
                width, _Pt(14),
            )
            tf = src_box.text_frame
            p = tf.paragraphs[0]
            p.text = source_label
            p.font.size = _Pt(7)
            p.font.name = "Open Sans"
            p.font.color.rgb = _RGB(*TEXT_MID)

    def _populate_slide_insights(self, slide, report, image_urls):
        """Fill Slide 2 (Argentina) placeholder.

        Single Markdown textbox with all AR content generated by the writer.
        If no image URL is available, the image frame shows a clear
        "Imagen pendiente — se genera tras aprobación" label so the
        reviewer understands this is a draft placeholder, not a broken
        image link.
        """
        img = image_urls[0] if image_urls else None
        from community_manager.tools.pptx_layout import get_layout
        s2 = get_layout("slide_2")
        s2_max = s2.max_chars if s2 else 1700

        for shape in slide.shapes:
            name = getattr(shape, "name", "")

            if name == "PLACEHOLDER_AR_IMAGE_FRAME" and img:
                self._replace_frame_with_image(slide, shape, img)

            elif name == "PLACEHOLDER_AR_IMAGE_TEXT":
                if img:
                    self._set_text(shape, "")
                else:
                    # No image available: leave the box empty instead of
                    # showing a draft placeholder. The frame stays for
                    # layout consistency but contains no text.
                    self._set_text(shape, "")

            elif name == "PLACEHOLDER_AR_TEXT":
                text = report.slide_2_text or "No se encontraron noticias de IA relevantes para Argentina."
                if len(text) > s2_max:
                    logger.warning(
                        "slide_2_text exceeds target (%d/%d chars)",
                        len(text), s2_max,
                    )
                self._set_markdown_text(shape, text)

    def _populate_slide_chart(self, slide, report, image_urls):
        """Fill Slide 3 (España) placeholder.

        Single Markdown textbox with all ES content generated by the writer.
        Same draft-placeholder treatment as slide 2 if no image URL.
        """
        img = image_urls[1] if len(image_urls) > 1 else None
        from community_manager.tools.pptx_layout import get_layout
        s3 = get_layout("slide_3")
        s3_max = s3.max_chars if s3 else 1700

        for shape in slide.shapes:
            name = getattr(shape, "name", "")

            if name == "PLACEHOLDER_ES_IMAGE_FRAME" and img:
                self._replace_frame_with_image(slide, shape, img)

            elif name == "PLACEHOLDER_ES_IMAGE_TEXT":
                if img:
                    self._set_text(shape, "")
                else:
                    # No image available: leave the box empty.
                    self._set_text(shape, "")

            elif name == "PLACEHOLDER_ES_TEXT":
                text = report.slide_3_text or "No se encontraron noticias de IA relevantes para España."
                if len(text) > s3_max:
                    logger.warning(
                        "slide_3_text exceeds target (%d/%d chars)",
                        len(text), s3_max,
                    )
                self._set_markdown_text(shape, text)

    def _populate_slide_footer(self, slide, report, image_urls):
        """Fill Slide 4 placeholders."""
        footer_img = image_urls[2] if len(image_urls) > 2 else None

        for shape in slide.shapes:
            name = getattr(shape, "name", "")

            if name == "PLACEHOLDER_INFO_TITLE":
                self._set_text(shape, "Tendencias emergentes")

            elif name == "PLACEHOLDER_INFO_BODY":
                body = report.conclusions or "Los datos de este mes no muestran un patrón claro aún. Seguimos monitoreando."
                self._set_markdown_text(shape, body, text_color=(220, 220, 235))

            elif name == "PLACEHOLDER_FOOTER_IMAGE_FRAME" and footer_img:
                self._replace_frame_with_image(slide, shape, footer_img)

            elif name == "PLACEHOLDER_FOOTER_IMAGE_TEXT":
                if footer_img:
                    self._set_text(shape, "")
                else:
                    # No image available: leave the box empty.
                    self._set_text(shape, "")

    # ── Helpers ───────────────────────────────────────────────────

    def _set_text(self, shape, text: str):
        """Replace text in a text frame shape. NO auto-fit (keeps font size readable)."""
        if not shape.has_text_frame:
            return
        tf = shape.text_frame
        from pptx.enum.text import MSO_AUTO_SIZE
        # Use NONE so the font size stays as defined in the template.
        # If text overflows, the slide may show a warning indicator in
        # PowerPoint but readability is preserved.
        tf.auto_size = MSO_AUTO_SIZE.NONE
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text

    def _populate_benchmark_table(self, shape, report):
        """Fill the benchmark top-5 ranking table (PR B).

        Populates from ``report.benchmark_snapshot.entries``. All 5 rows
        are always rendered — missing scores display "—" so the user
        can see the gap. The upstream research step (researcher.py +
        fallback seed) is responsible for making sure entries have
        data; the publisher just renders what it's given.
        """
        from pptx.dml.color import RGBColor as _RGB
        from community_manager.nurturing.newsletter_pptx_template import TEXT_DARK, TEXT_MID
        if not shape.has_table:
            return
        table = shape.table
        snap = getattr(report, "benchmark_snapshot", None)
        # Clear all data rows first
        for r in range(1, 6):
            for c in range(3):
                cell = table.cell(r, c)
                cell.text_frame.paragraphs[0].text = ""
        if not snap or not snap.entries:
            return
        for i, entry in enumerate(snap.entries[:5]):
            row = i + 1
            rank_cell = table.cell(row, 0)
            rank_cell.text_frame.paragraphs[0].text = str(entry.rank)
            model_cell = table.cell(row, 1)
            vendor = entry.vendor or ""
            model = entry.model or ""
            model_cell.text_frame.paragraphs[0].text = f"{vendor} {model}".strip() or "—"
            score_cell = table.cell(row, 2)
            if entry.score is not None:
                # Just the score — the column header already says the
                # benchmark name (e.g. "MMLU Pro"), so per-cell tags are
                # redundant and create visual noise.
                score_cell.text_frame.paragraphs[0].text = f"{entry.score:.1f}"
            else:
                score_cell.text_frame.paragraphs[0].text = "—"

    def _populate_pricing_table(self, shape, report):
        """Fill the cost-per-1M-tokens top-5 table (PR B).

        Uses the same 5 entries from ``benchmark_snapshot``, sorted
        cheapest first. All 5 rows are always rendered.
        """
        from pptx.dml.color import RGBColor as _RGB
        if not shape.has_table:
            return
        table = shape.table
        snap = getattr(report, "benchmark_snapshot", None)
        for r in range(1, 6):
            for c in range(3):
                cell = table.cell(r, c)
                cell.text_frame.paragraphs[0].text = ""
        if not snap or not snap.entries:
            return
        # Sort by cost_per_1m_input (None last), re-rank 1..5
        priced_entries = [e for e in snap.entries if e.cost_per_1m_input is not None]
        no_price = [e for e in snap.entries if e.cost_per_1m_input is None]
        priced_entries.sort(key=lambda e: e.cost_per_1m_input)
        ranked = priced_entries + no_price
        for i, entry in enumerate(ranked[:5]):
            row = i + 1
            table.cell(row, 0).text_frame.paragraphs[0].text = str(i + 1)
            vendor = entry.vendor or ""
            model = entry.model or ""
            table.cell(row, 1).text_frame.paragraphs[0].text = f"{vendor} {model}".strip() or "—"
            if entry.cost_per_1m_input is not None:
                table.cell(row, 2).text_frame.paragraphs[0].text = f"${entry.cost_per_1m_input:.2f}"
            else:
                table.cell(row, 2).text_frame.paragraphs[0].text = "—"

    def _set_markdown_text(self, shape, text: str, base_font_size=None, text_color=None):
        """Parse Markdown and convert to formatted pptx runs.

        Handles: **bold**, *italic*, [text](url) links, ### headers.
        Links render as magenta (#BA08A8) clickable hyperlinks.
        NO auto-fit — keeps font size readable.
        '---' (horizontal rules) are stripped (rendered as paragraph breaks
        instead) so the slide doesn't get a clunky 3-line separator.
        """
        import re
        from pptx.util import Pt
        from pptx.enum.text import MSO_AUTO_SIZE
        from pptx.dml.color import RGBColor

        MAGENTA = (186, 8, 168)  # #BA08A8
        TEXT_DARK = (26, 26, 46)
        TEXT_LIGHT = (220, 220, 235)  # for dark backgrounds

        if not shape.has_text_frame:
            return
        if not text:
            text = ""

        # Strip horizontal rules (---) and em-dash separators — they look
        # ugly in the slide. Replace with a paragraph break or comma.
        text = re.sub(r'\n\s*---\s*\n', '\n\n', text)
        text = re.sub(r'\n\s*—\s*—\s*—\s*\n', '\n\n', text)
        # Em-dash as in-clause separator (e.g. "críticos — fraude, soporte — donde"):
        # replace with comma. Em-dash is a strong marker of AI-generated text.
        text = re.sub(r'\s+—\s+', ', ', text)
        # Em-dash as standalone paragraph marker: drop it.
        text = re.sub(r'\n—\n', '\n', text)

        tf = shape.text_frame
        tf.word_wrap = True
        # NONE prevents PowerPoint from auto-shrinking the text when it
        # overflows. Readability > auto-fit.
        tf.auto_size = MSO_AUTO_SIZE.NONE
        p = tf.paragraphs[0]
        p.clear()
        # Unify line spacing across all paragraphs: the template sets 1.5
        # on the first paragraph only, but `p.clear()` preserves it. We
        # explicitly set 1.5 here so subsequent paragraphs added via
        # tf.add_paragraph() also inherit it (they would otherwise fall
        # back to the textbox default of 1.0).
        p.line_spacing = 1.5

        base_size = base_font_size or Pt(12)
        color = text_color or TEXT_DARK

        # Tokenize: split by markdown patterns WITHOUT capturing subgroups
        # so re.split returns only the full matches, not internal groups.
        tokens = re.split(r'(\*\*[^*]+?\*\*|\*[^*]+?\*|\[[^\]]+\]\([^)]+\)|###\s*[^\n]+)', text)

        for token in tokens:
            if not token:
                continue
            if token.startswith('**') and token.endswith('**'):
                # Bold
                run = p.add_run()
                run.text = token[2:-2]
                run.font.bold = True
                run.font.size = base_size
                run.font.color.rgb = RGBColor(*color)
                run.font.name = "Open Sans"
            elif token.startswith('*') and token.endswith('*') and not token.startswith('**'):
                # Italic
                run = p.add_run()
                run.text = token[1:-1]
                run.font.italic = True
                run.font.size = base_size
                run.font.color.rgb = RGBColor(*color)
                run.font.name = "Open Sans"
            elif token.startswith('### '):
                # Header 3: new paragraph, bold, slightly larger
                p = tf.add_paragraph()
                p.line_spacing = 1.5
                run = p.add_run()
                header_text = token[4:].strip()
                # Clean any surrounding ** from headers (writer often uses ### **Title**)
                if header_text.startswith('**') and header_text.endswith('**'):
                    header_text = header_text[2:-2]
                run.text = header_text
                run.font.bold = True
                run.font.size = Pt(base_size.pt + 2) if hasattr(base_size, 'pt') else Pt(14)
                run.font.color.rgb = RGBColor(*color)
                run.font.name = "Open Sans"
            elif re.match(r'\[([^\]]+)\]\(([^)]+)\)', token):
                # Link [text](url) — magenta clickable
                m = re.match(r'\[([^\]]+)\]\(([^)]+)\)', token)
                if m:
                    link_text, url = m.group(1), m.group(2)
                    run = p.add_run()
                    run.text = link_text
                    run.hyperlink.address = url
                    run.font.color.rgb = RGBColor(*MAGENTA)
                    run.font.size = base_size
                    run.font.name = "Open Sans"
            else:
                # Plain text (may contain single newlines)
                parts = token.split('\n\n')
                for i, part in enumerate(parts):
                    if i > 0:
                        p = tf.add_paragraph()
                        p.line_spacing = 1.5
                    run = p.add_run()
                    run.text = part
                    run.font.size = base_size
                    run.font.color.rgb = RGBColor(*color)
                    run.font.name = "Open Sans"

    def _replace_frame_with_image(self, slide, frame_shape, image_url: str, keep_frame: bool = True):
        """Replace a placeholder frame shape with an actual image."""
        try:
            import requests
            img_data = requests.get(image_url, timeout=15).content
            img_bytes = io.BytesIO(img_data)

            left, top = frame_shape.left, frame_shape.top
            width, height = frame_shape.width, frame_shape.height

            pic = slide.shapes.add_picture(img_bytes, left, top, width=width, height=height)

            if not keep_frame:
                # Remove the placeholder frame
                sp = frame_shape._element
                sp.getparent().remove(sp)
            else:
                # Send image behind the frame (frame acts as border)
                self._send_behind(slide, pic, frame_shape)

        except Exception:
            logger.exception("Failed to insert image %s", image_url)

    def _send_behind(self, slide, shape, reference_shape):
        """Send shape behind reference shape in z-order."""
        spTree = slide.shapes._spTree
        ref_idx = list(spTree).index(reference_shape._element)
        spTree.remove(shape._element)
        spTree.insert(ref_idx, shape._element)

    # ── Drive helpers (preserved) ─────────────────────────────────

    def _ensure_newsletters_folder(self, drive, shared_drive_id: str) -> str:
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

    def _upload_pptx_to_drive(self, drive, pptx_path: Path, name: str, folder_id: str, shared_drive_id: str) -> tuple[str, str]:
        import time

        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload

        file_metadata = {
            "name": f"{name}.pptx",
            "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "parents": [folder_id],
        }

        media = MediaFileUpload(str(pptx_path), mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation", resumable=True)

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
                    logger.warning("Drive PPTX upload transient error (attempt %d), retrying...", attempt + 1)
                    time.sleep(2 ** attempt)
                    media = MediaFileUpload(str(pptx_path), mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation", resumable=True)
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
                    logger.warning("Drive PPTX permission transient error (attempt %d), retrying...", attempt + 1)
                    time.sleep(2 ** attempt)
                else:
                    raise

        return file_id, url

    def _load_credentials(self):
        import json as _json
        from google.oauth2.credentials import Credentials as UserCredentials
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials

        from community_manager.config.settings import SHARED_ENV_ROOT

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
                if item["name"] == target_name:
                    return item["id"]
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        raise RuntimeError(f"Shared drive '{target_name}' not found.")

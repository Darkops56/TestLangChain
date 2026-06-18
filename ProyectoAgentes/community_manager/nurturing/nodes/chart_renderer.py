"""Chart renderer node — renders charts as PNG images using Pillow.

Takes the chart plan and renders it as a PNG image that can be
inserted into the Google Slides.
"""

from __future__ import annotations

import logging
import uuid

from community_manager.models.schemas import RadarReport
from community_manager.shared.chart_renderer import render_chart_png
from community_manager.tools.blob_media import AzureBlobMediaPublisher

logger = logging.getLogger(__name__)


async def chart_renderer_node(state: dict) -> dict:
    """Render chart as PNG image.

    Input: raw_report (RadarReport), slides_plan (SlidesPlan)
    Output: chart_url (str), chart_blob_name (str)
    """
    logger.info("▶ Chart renderer node starting")

    raw_report: RadarReport = state.get("raw_report")
    slides_plan = state.get("slides_plan")

    if not raw_report or not raw_report.chart_items:
        logger.info("No chart data to render")
        return {"chart_url": None, "chart_blob_name": None}

    chart_plan = slides_plan.chart_plan if slides_plan else None
    chart_title = chart_plan.chart_title if chart_plan else raw_report.chart_title or "Comparativo del mes"
    chart_subtitle = chart_plan.chart_subtitle if chart_plan else raw_report.chart_subtitle or ""

    # Render chart as PNG
    image_bytes = render_chart_png(
        raw_report.chart_items,
        chart_title=chart_title,
        chart_subtitle=chart_subtitle,
    )

    if not image_bytes:
        logger.warning("Chart rendering produced no output")
        return {"chart_url": None, chart_blob_name: None}

    # Upload to Azure Blob Storage
    blob_name = f"ai-radar/chart-{uuid.uuid4().hex[:8]}.png"

    publisher = AzureBlobMediaPublisher()
    try:
        public_url = await publisher.upload_bytes(blob_name, image_bytes, content_type="image/png")
        logger.info("✅ Chart renderer completed: %s", public_url)
        return {"chart_url": public_url, "chart_blob_name": blob_name}
    except Exception:
        logger.exception("Chart upload failed")
        return {"chart_url": None, "chart_blob_name": None}
    finally:
        await publisher.close()

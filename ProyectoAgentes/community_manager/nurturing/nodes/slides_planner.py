"""Slides planner node — creates PPTX newsletter draft.

Creates a draft version of the newsletter as a .pptx presentation.
This is shown to the human for review before expensive image generation.
"""

from __future__ import annotations

import logging

from community_manager.models.schemas import RadarReport
from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher

logger = logging.getLogger(__name__)


async def slides_planner_node(state: dict) -> dict:
    """Create PPTX newsletter draft with placeholders for images.

    Input: raw_report (RadarReport), slides_plan (SlidesPlan)
    Output: slides_draft_url (str), slides_draft_id (str)
    """
    logger.info("▶ Slides planner node starting")

    raw_report: RadarReport = state.get("raw_report")
    slides_plan = state.get("slides_plan")

    if not raw_report:
        logger.warning("No raw report found")
        return {"slides_draft_url": None, "slides_draft_id": None}

    try:
        publisher = NewsletterPPTXPublisher()

        # Get month label from report title or subject
        month_label = _extract_month_label(raw_report)

        # Create the newsletter draft (without images)
        artifact = await publisher.publish_report(
            raw_report,
            month_label=month_label,
            chart_url=None,  # No chart image yet
            image_urls=[],   # No images yet
        )

        logger.info("✅ Slides planner completed: %s", artifact.drive_url)

        return {
            "slides_draft_url": artifact.drive_url,
            "slides_draft_id": artifact.drive_file_id,
            "slides_artifact": artifact,
        }

    except Exception:
        logger.exception("Slides planner failed")
        return {"slides_draft_url": None, "slides_draft_id": None}


def _extract_month_label(report: RadarReport) -> str:
    """Extract month label from report title or subject."""
    # Try to extract from title like "Novit AI Radar - Junio 2025"
    title = report.report_title or report.subject or ""
    if " - " in title:
        return title.split(" - ", 1)[1].strip()
    return title

"""Slides assembler node — creates final PPTX newsletter with images.

Takes the approved draft and generates the final .pptx with
all images and chart included.
"""

from __future__ import annotations

import logging

from community_manager.models.schemas import GeneratedImage
from community_manager.nurturing.newsletter_pptx_publisher import NewsletterPPTXPublisher

logger = logging.getLogger(__name__)


async def slides_assembler_node(state: dict) -> dict:
    """Create final PPTX newsletter with images.

    Input: slides_draft_id (str), generated_images (list[GeneratedImage]), chart_url (str)
    Output: slides_final_url (str), slides_final_id (str)
    """
    logger.info("▶ Slides assembler node starting")

    slides_draft_id = state.get("slides_draft_id")
    slides_artifact = state.get("slides_artifact")
    generated_images: list[GeneratedImage] = state.get("generated_images", [])
    chart_url = state.get("chart_url")
    raw_report = state.get("raw_report")

    if not slides_draft_id:
        logger.warning("No slides draft ID found")
        return {"slides_final_url": None, "slides_final_id": None}

    try:
        # If we have images or chart, we need to regenerate the newsletter
        if generated_images or chart_url:
            # Build image URLs list (for insights)
            image_urls = []
            for img in generated_images:
                if img and img.url:
                    image_urls.append(img.url)

            # Re-publish with images
            publisher = NewsletterPPTXPublisher()
            month_label = _extract_month_label(raw_report) if raw_report else ""

            artifact = await publisher.publish_report(
                raw_report,
                month_label=month_label,
                chart_url=chart_url,
                image_urls=image_urls,
            )

            logger.info("✅ Slides assembler completed: %s", artifact.drive_url)

            return {
                "slides_final_url": artifact.drive_url,
                "slides_final_id": artifact.drive_file_id,
                "slides_final_artifact": artifact,
            }
        else:
            # No images to add, draft becomes final
            logger.info("No images to add, draft becomes final")
            return {
                "slides_final_url": state.get("slides_draft_url"),
                "slides_final_id": slides_draft_id,
                "slides_final_artifact": slides_artifact,
            }

    except Exception:
        logger.exception("Slides assembly failed")
        return {"slides_final_url": None, "slides_final_id": None}


def _extract_month_label(report) -> str:
    """Extract month label from report title or subject."""
    if not report:
        return ""
    title = getattr(report, "report_title", None) or getattr(report, "subject", "") or ""
    if " - " in title:
        return title.split(" - ", 1)[1].strip()
    return title

"""Distributor node — sends the final newsletter to recipients.

Sends the newsletter via email using the .NET backend services.
"""

from __future__ import annotations

import logging

from community_manager.models.schemas import RadarReport
from community_manager.tools.dotnet_client import DotNetClient

logger = logging.getLogger(__name__)


async def distributor_node(state: dict) -> dict:
    """Send the final newsletter to recipients.

    Input: slides_final_url (str), raw_report (RadarReport)
    Output: send_result (dict)
    """
    logger.info("▶ Distributor node starting")

    slides_final_url = state.get("slides_final_url")
    raw_report: RadarReport = state.get("raw_report")
    newsletter_content = state.get("newsletter_content")

    if not slides_final_url:
        logger.warning("No slides URL to distribute")
        return {"send_result": {"success": False, "error": "No slides URL"}}

    if not raw_report:
        logger.warning("No report to distribute")
        return {"send_result": {"success": False, "error": "No report"}}

    try:
        dotnet = DotNetClient()
        try:
            # Get newsletter subject
            subject = raw_report.subject or newsletter_content.subject if newsletter_content else "AI Radar by Novit"

            # Save newsletter to DB
            month_key = _get_month_key()
            import json as _json
            artifact = {
                "slides_url": slides_final_url or "",
                "report_title": raw_report.report_title or "",
                "conclusions": raw_report.conclusions or "",
            }
            await dotnet.save_newsletter(
                subject=subject,
                body=raw_report.executive_summary,
                month_key=month_key,
                scheduled_send_date=None,
                report_title=raw_report.report_title,
                executive_summary=raw_report.executive_summary,
                artifact_json=_json.dumps(artifact, ensure_ascii=False),
            )

            # Mark as sent
            await dotnet.mark_newsletter_sent(month_key)

            logger.info("✅ Distributor completed: newsletter saved and marked as sent")

            return {
                "send_result": {
                    "success": True,
                    "slides_url": slides_final_url,
                    "subject": subject,
                }
            }

        finally:
            await dotnet.close()

    except Exception:
        logger.exception("Distribution failed")
        return {"send_result": {"success": False, "error": "Distribution failed"}}


def _get_month_key() -> str:
    """Get current month key in YYYY-MM format."""
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m")

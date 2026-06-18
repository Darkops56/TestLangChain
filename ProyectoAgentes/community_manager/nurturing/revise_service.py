"""Newsletter revision service — re-runs the writer for a stored newsletter.

Migrated from nurturing/workflow.py:revise_newsletter (v1, deprecated).
Takes an existing newsletter's body and reviewer feedback, re-runs the
writer with the new context, returns the revised body.

This skips the researcher and scorer (no new searches); it only revises
the text on top of existing insights and the new feedback.
"""

from __future__ import annotations

import logging

from community_manager.config.settings import get_settings
from community_manager.models.schemas import RadarReport
from community_manager.nurturing.prompts import REVISION_USER_TEMPLATE
from community_manager.tools.llm import get_newsletter_llm

logger = logging.getLogger(__name__)


async def revise_newsletter(
    current_subject: str,
    current_body: str,
    reviewer_feedback: str,
) -> tuple[str, str]:
    """Revise an existing AI Radar report based on reviewer feedback.

    Returns (new_subject, new_body). If the AI is not configured, returns
    the inputs unchanged.
    """
    settings = get_settings()
    if not settings.is_nurturing_configured:
        logger.warning("Newsletter AI not configured — returning original")
        return current_subject, current_body

    prompt = REVISION_USER_TEMPLATE.format(
        current_subject=current_subject,
        current_body=current_body,
        reviewer_feedback=reviewer_feedback,
    )

    try:
        llm = get_newsletter_llm()
        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        # The LLM may return just the revised body, or a structured response.
        # We treat the entire text as the new body and derive the subject from
        # the first non-empty line if it looks like a subject.
        text = text.strip()
        new_subject = current_subject
        new_body = text
        # Heuristic: if the response starts with a "Subject: ..." line, use it
        if text.lower().startswith("subject:"):
            first_line, _, rest = text.partition("\n")
            new_subject = first_line.split(":", 1)[1].strip() or current_subject
            new_body = rest.strip()
        return new_subject, new_body
    except Exception:
        logger.exception("Revision failed")
        return current_subject, current_body

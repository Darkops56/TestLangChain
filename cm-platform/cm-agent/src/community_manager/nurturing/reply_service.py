"""Reply and personal closing generation.

Migrated from nurturing/workflow.py (v1, deprecated) to v2. These
functions are pure LLM calls (no tools) and produce plain-text output
for email responses and personalized closings.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.settings import get_settings
from community_manager.nurturing.prompts import (
    PERSONAL_CLOSING_USER_TEMPLATE,
    REPLY_USER_TEMPLATE,
)
from community_manager.tools.llm import get_closing_llm, get_reply_llm

logger = logging.getLogger(__name__)


SIMPLE_SYSTEM_MESSAGE = (
    "Sos un asistente experto en comunicación corporativa de tecnología "
    "para Novit Software, una empresa argentina de consultoría tecnológica."
)


async def generate_reply(
    original_subject: str,
    original_body: str,
    sender_name: str,
) -> str:
    """Generate a plain-text reply to a newsletter response.

    Mirrors the v1 ``generate_reply``. No tools used.
    """
    prompt = REPLY_USER_TEMPLATE.format(
        sender_name=sender_name,
        original_subject=original_subject,
        original_body=original_body,
    )

    try:
        llm = get_reply_llm()
        response = await llm.ainvoke([
            SystemMessage(content=SIMPLE_SYSTEM_MESSAGE),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()
    except Exception:
        logger.exception("Reply generation failed")
        return "Lo sentimos, el contenido no pudo generarse en este momento."


async def generate_personal_closing(
    newsletter_subject: str,
    newsletter_body: str | None,
    first_name: str | None,
    org_name: str | None,
    deal_notes: list[str],
) -> str | None:
    """Generate a 1-2 sentence personalised closing for a recipient.

    Mirrors the v1 ``generate_personal_closing``. Returns ``None`` on error
    or if the AI is not configured.
    """
    contact_desc_parts: list[str] = []
    if first_name:
        contact_desc_parts.append(f"Nombre: {first_name}.")
    if org_name:
        contact_desc_parts.append(f"Empresa: {org_name}.")
    contact_desc = " ".join(contact_desc_parts)

    notes_section = (
        "Historial de interacciones con este contacto:\n"
        + "\n".join(f"- {n}" for n in deal_notes)
        if deal_notes
        else "No hay historial de interacciones previas con este contacto."
    )

    body_context = ""
    if newsletter_body:
        trimmed = newsletter_body[:1500] + "..." if len(newsletter_body) > 1500 else newsletter_body
        body_context = f"\nContenido del newsletter (resumen):\n{trimmed}\n"

    prompt = PERSONAL_CLOSING_USER_TEMPLATE.format(
        newsletter_subject=newsletter_subject,
        body_context=body_context,
        contact_desc=contact_desc,
        notes_section=notes_section,
    )

    try:
        llm = get_closing_llm()
        response = await llm.ainvoke([
            SystemMessage(content=SIMPLE_SYSTEM_MESSAGE),
            HumanMessage(content=prompt),
        ])
        result = response.content.strip().strip('"')

        # Sanity check — must be short
        if len(result) > 400 or "Lo sentimos" in result:
            return None
        return result
    except Exception:
        logger.exception("Personal closing generation failed for %s", first_name or "unknown")
        return None

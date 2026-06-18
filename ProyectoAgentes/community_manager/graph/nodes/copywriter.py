"""Copywriter node — generates post text (caption, hashtags, CTA).

Takes the ContentStrategy from the Strategist and produces the
text copy for the publication.
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.prompts import COPYWRITER_SYSTEM
from community_manager.config.settings import get_settings
from community_manager.graph.state import CommunityManagerState
from community_manager.models.schemas import PostCopy
from community_manager.tools.llm import get_creative_llm

logger = logging.getLogger(__name__)

SOURCE_CLAIM_TRIGGER_PATTERN = re.compile(
    r"\b(estudio|informe|encuesta|investigaci[oó]n|datos|cifras|seg[uú]n|fuente|report)\b",
    flags=re.IGNORECASE,
)
SOURCE_ATTRIBUTION_PATTERN = re.compile(
    r"\b(seg[uú]n|de acuerdo con|fuente|publicado por|elaborado por|realizado por|datos de)\b:?",
    flags=re.IGNORECASE,
)
RECOGNIZABLE_SOURCE_PATTERN = re.compile(
    r"\b(McKinsey|Gartner|Deloitte|PwC|Stanford|MIT|OpenAI|Microsoft|IBM|Harvard|WEF|World Economic Forum|OECD|CEPAL|BID|Banco Mundial|INDEC)\b",
    flags=re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b20\d{2}\b")
QUOTE_PATTERN = re.compile(r"[\"“”'‘’][^\"“”'‘’]{12,}[\"“”'‘’]")
SOURCE_VALIDATION_HINTS = (
    "estudios o datos sin evidencia suficiente",
    "unverified study/data claim",
    "nunca cites datos o estudios sin fuente verificable",
)


def _normalize_json_payload(content: str) -> str:
    payload = content.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        payload = "\n".join(lines).strip()
    return payload


def _caption_has_unverified_source_claim(caption: str) -> bool:
    normalized_caption = (caption or "").strip()
    if not normalized_caption:
        return False

    if not SOURCE_CLAIM_TRIGGER_PATTERN.search(normalized_caption):
        return False

    has_attribution = SOURCE_ATTRIBUTION_PATTERN.search(normalized_caption)
    has_source = RECOGNIZABLE_SOURCE_PATTERN.search(normalized_caption)
    has_year = YEAR_PATTERN.search(normalized_caption)
    has_quote = QUOTE_PATTERN.search(normalized_caption)
    return not (has_attribution and (has_source or has_year) and has_quote)


def _should_repair_source_claims(*, evaluation, caption: str) -> bool:
    if _caption_has_unverified_source_claim(caption):
        return True

    if not evaluation:
        return False

    feedback_haystack = " ".join([
        evaluation.feedback or "",
        *evaluation.issues,
    ]).lower()
    return any(hint in feedback_haystack for hint in SOURCE_VALIDATION_HINTS)


async def _rewrite_caption_without_unsourced_claims(*, llm, caption: str, strategy) -> str:
    strategy_context = ""
    if strategy:
        strategy_context = (
            f"Tema: {strategy.topic}\n"
            f"Ángulo: {strategy.angle}\n"
            f"Objetivo: {strategy.objective}\n"
            f"Público: {strategy.target_audience}\n"
        )

    repair_request = (
        "Reescribí el caption para que mantenga el mismo ángulo de negocio, el tono ejecutivo-humano y el CTA, "
        "pero eliminando cualquier estudio, cifra o afirmación externa que no esté plenamente respaldada dentro del propio texto. "
        "No inventes fuentes, años ni citas. Si no podés sostener una referencia externa, reemplazala por una afirmación original prudente. "
        "Respondé SOLO con el caption final, sin JSON, sin comillas y sin markdown.\n\n"
        f"{strategy_context}"
        f"Caption actual:\n{caption}"
    )

    response = await llm.ainvoke([
        SystemMessage(content="Sos editor de copy B2B en español rioplatense. Reescribís captions para dejarlos publicables sin inventar datos ni fuentes."),
        HumanMessage(content=repair_request),
    ])
    return str(response.content or "").strip()


def _strip_unsourced_claim_lines(caption: str) -> str:
    kept_lines: list[str] = []
    for raw_line in (caption or "").splitlines():
        line = raw_line.strip()
        if not line:
            if kept_lines and kept_lines[-1] != "":
                kept_lines.append("")
            continue
        if SOURCE_CLAIM_TRIGGER_PATTERN.search(line):
            continue
        kept_lines.append(line)

    cleaned = "\n".join(kept_lines).strip()
    return cleaned or caption.strip()


async def copywriter_node(state: CommunityManagerState) -> dict:
    """Generate text content based on the strategy."""
    logger.info("▶ Copywriter node starting")

    settings = get_settings()
    strategy = state.get("strategy")
    evaluation = state.get("evaluation")

    prompt = COPYWRITER_SYSTEM.format(
        brand_name=settings.brand_name,
        brand_voice=settings.brand_voice,
    )

    # Build context
    parts: list[str] = []
    if strategy:
        parts.append(
            f"Content type: {strategy.content_type.value}\n"
            f"Topic: {strategy.topic}\n"
            f"Angle: {strategy.angle}\n"
            f"Objective: {strategy.objective}\n"
            f"Target audience: {strategy.target_audience}\n"
            f"Language: {strategy.language}\n"
            f"Tone: {strategy.tone.value}\n"
            f"Key messages: {', '.join(strategy.key_messages)}\n"
            f"Supporting points: {', '.join(strategy.supporting_points)}"
        )

    # Include evaluator feedback if this is a retry
    if evaluation and not evaluation.approved and evaluation.retry_target == "copywriter":
        parts.append(
            f"\n⚠️ REVISION REQUIRED — Evaluator feedback:\n"
            f"{evaluation.feedback}\n"
            f"Issues: {', '.join(evaluation.issues)}"
        )
        if _should_repair_source_claims(evaluation=evaluation, caption=state.get("copy").caption if state.get("copy") else ""):
            parts.append(
                "Regla obligatoria para esta revisión: si no podés sostener una mención a estudios, cifras o fuentes externas con organización + año + cita breve entre comillas, eliminá esa referencia por completo. No inventes fuentes."
            )

    reviewer_memory = state.get("reviewer_memory", "")
    if reviewer_memory:
        parts.append(f"Reviewer memory to avoid repeated mistakes:\n{reviewer_memory}")

    reviewer_feedback = state.get("reviewer_feedback", "")
    if reviewer_feedback:
        parts.append(f"Current reviewer feedback to incorporate:\n{reviewer_feedback}")

    parts.append(f"Brand hashtags to include: {settings.brand_hashtags}")
    parts.append("Mandatory language: Spanish (es-AR).")

    user_msg = HumanMessage(content="\n\n".join(parts))

    # Call LLM
    llm = get_creative_llm()
    response = await llm.ainvoke([SystemMessage(content=prompt), user_msg])

    # Parse
    try:
        data = json.loads(_normalize_json_payload(response.content))
        copy = PostCopy(**data)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Failed to parse copywriter response: %s", exc)
        copy = PostCopy(caption=response.content, hashtags=settings.brand_hashtags_list)

    if _should_repair_source_claims(evaluation=evaluation, caption=copy.caption):
        logger.info("Repairing copy to remove unsupported external study/data claims")
        repaired_caption = await _rewrite_caption_without_unsourced_claims(
            llm=llm,
            caption=copy.caption,
            strategy=strategy,
        )
        if repaired_caption:
            copy = copy.model_copy(update={"caption": repaired_caption})

        if _caption_has_unverified_source_claim(copy.caption):
            logger.warning("Source-claim repair still left unsupported references; stripping claim lines")
            copy = copy.model_copy(update={"caption": _strip_unsourced_claim_lines(copy.caption)})

    logger.info(
        "✅ Copy: %d chars, %d hashtags",
        len(copy.caption), len(copy.hashtags),
    )

    return {
        "copy": copy,
        "messages": [response],
    }

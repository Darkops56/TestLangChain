"""Strategist node — decides what to publish, when, and with what approach.

Acts as the router/planner of the graph. Analyses the current context
(day, publication history, schedule) and outputs a ContentStrategy.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.prompts import STRATEGIST_SYSTEM
from community_manager.config.settings import get_settings
from community_manager.graph.state import CommunityManagerState
from community_manager.models.schemas import ContentStrategy, ContentType, MAX_IMAGE_POST_IMAGES, MIN_IMAGE_POST_IMAGES
from community_manager.tools.llm import get_main_llm

logger = logging.getLogger(__name__)


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


def _sanitize_strategy_payload(data: dict, *, requested_type: str) -> dict:
    payload = dict(data)
    raw_content_type = payload.get("content_type") or requested_type or ContentType.TEXT_POST.value
    try:
        content_type = ContentType(raw_content_type)
    except ValueError:
        return payload

    if content_type != ContentType.VIDEO_POST and payload.get("video_duration_seconds") is None:
        payload.pop("video_duration_seconds", None)

    return payload


def _normalize_automatic_image_count(num_images: int) -> int:
    if num_images <= 2:
        return 2
    return 4


def _apply_requested_strategy_overrides(strategy: ContentStrategy, state: CommunityManagerState) -> ContentStrategy:
    requested_topic = (state.get("requested_topic") or "").strip()
    requested_angle = (state.get("requested_angle") or "").strip()
    requested_objective = (state.get("requested_objective") or "").strip()
    requested_num_images = state.get("requested_num_images")
    is_on_demand = bool(state.get("is_on_demand"))

    if requested_topic:
        strategy.topic = requested_topic
    if requested_angle:
        strategy.angle = requested_angle
    if requested_objective:
        strategy.objective = requested_objective

    if strategy.content_type == ContentType.IMAGE_POST:
        if isinstance(requested_num_images, int) and requested_num_images > 0:
            strategy.num_images = max(MIN_IMAGE_POST_IMAGES, min(requested_num_images, MAX_IMAGE_POST_IMAGES))
        elif not is_on_demand:
            strategy.num_images = _normalize_automatic_image_count(strategy.num_images)

    return strategy


async def strategist_node(state: CommunityManagerState) -> dict:
    """Analyse context and decide content type + approach."""
    logger.info("▶ Strategist node starting")

    settings = get_settings()
    now = datetime.now()

    # Build context
    prompt = STRATEGIST_SYSTEM.format(brand_name=settings.brand_name)
    context_parts = [
        f"Current date/time: {now.strftime('%A, %B %d %Y — %H:%M')}",
        f"Brand: {settings.brand_name}",
        f"Brand voice: {settings.brand_voice}",
        f"Brand hashtags: {settings.brand_hashtags}",
        "Required language: es-AR",
    ]

    is_on_demand = bool(state.get("is_on_demand"))
    context_parts.append("Run mode: on-demand/manual request." if is_on_demand else "Run mode: automatic scheduled run.")
    if not is_on_demand:
        context_parts.append("Cost guardrail: automatic image posts must use only 2 or 4 slides. Automatic videos should stay around 20 seconds.")

    # If a specific content type was requested (by the scheduler)
    requested_type = state.get("requested_content_type", "")
    if requested_type:
        context_parts.append(f"Scheduler requested content type: {requested_type}")

    requested_topic = (state.get("requested_topic") or "").strip()
    if requested_topic:
        context_parts.append(f"Forced topic for this run: {requested_topic}")

    requested_angle = (state.get("requested_angle") or "").strip()
    if requested_angle:
        context_parts.append(f"Forced angle for this run: {requested_angle}")

    requested_objective = (state.get("requested_objective") or "").strip()
    if requested_objective:
        context_parts.append(f"Forced objective for this run: {requested_objective}")

    requested_num_images = state.get("requested_num_images")
    if isinstance(requested_num_images, int) and requested_num_images > 0:
        context_parts.append(f"Explicit image count requested for this run: {requested_num_images}")

    # Publication history
    history = state.get("publication_history", [])
    if history:
        recent = history[-8:]
        history_text = "\n".join(f"  - {h}" for h in recent)
        context_parts.append(f"Recent community drafts and publications:\n{history_text}")
    else:
        context_parts.append("No recent publication history available.")

    reviewer_memory = state.get("reviewer_memory", "")
    if reviewer_memory:
        context_parts.append(f"Lessons from previous reviewer feedback:\n{reviewer_memory}")

    reviewer_feedback = state.get("reviewer_feedback", "")
    if reviewer_feedback:
        context_parts.append(f"Current reviewer feedback to address:\n{reviewer_feedback}")

    user_msg = HumanMessage(content="\n".join(context_parts))

    # Call LLM
    llm = get_main_llm(temperature=0.7)
    response = await llm.ainvoke([SystemMessage(content=prompt), user_msg])

    # Parse
    try:
        data = json.loads(_normalize_json_payload(response.content))
        strategy = ContentStrategy(**_sanitize_strategy_payload(data, requested_type=requested_type))
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Failed to parse strategist response: %s — using defaults", exc)
        strategy = ContentStrategy(
            content_type=ContentType(requested_type) if requested_type else ContentType.TEXT_POST,
            topic="Dónde una pyme sí puede automatizar hoy con IA",
            angle="Bajar la conversación de IA a un proceso concreto y rentable",
            objective="Abrir conversación con decisores sobre casos reales de adopción",
            supporting_points=[
                "Elegir un proceso puntual antes de escalar",
                "Medir impacto operativo o comercial temprano",
            ],
        )

    strategy = _apply_requested_strategy_overrides(strategy, state)

    logger.info(
        "✅ Strategy: type=%s topic='%s'",
        strategy.content_type.value, strategy.topic,
    )

    return {
        "strategy": strategy,
        "messages": [response],
    }

"""Reviewable draft workflow for Community Manager publications.

This path generates and revises publishable drafts without sending them to
social platforms immediately. It is used by the reviewer-gated approval flow.
"""

from __future__ import annotations

import json

from community_manager.graph.nodes.copywriter import copywriter_node
from community_manager.graph.nodes.designer import designer_node
from community_manager.graph.nodes.evaluator import evaluator_node
from community_manager.graph.nodes.publisher import publisher_node
from community_manager.graph.nodes.strategist import strategist_node
from community_manager.graph.state import CommunityManagerState
from community_manager.graph.workflow import MAX_RETRIES, route_after_copywriter
from community_manager.models.schemas import ContentStrategy, DesignerOutput, EvaluationResult, PostCopy, ReviewStage


def _serialize_model(model) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


def _extract_media_urls(design: DesignerOutput | None) -> list[str]:
    if not design:
        return []

    urls = [image.url for image in design.images if image.url]
    if design.video and design.video.url:
        urls.append(design.video.url)
    return urls


def _extract_blob_names(design: DesignerOutput | None) -> list[str]:
    if not design:
        return []

    blob_names = [image.blob_name for image in design.images if image.blob_name]
    if design.video and design.video.blob_name:
        blob_names.append(design.video.blob_name)
    return blob_names


def _has_generated_media(design: DesignerOutput | None) -> bool:
    if not design:
        return False
    if any(image.url for image in design.images):
        return True
    return bool(design.video and design.video.url)


def _build_payload(state: CommunityManagerState) -> dict:
    strategy = state["strategy"]
    copy = state["copy"]
    design = state.get("design")
    evaluation = state["evaluation"]

    return {
        "content_type": strategy.content_type.value,
        "topic": strategy.topic,
        "angle": strategy.angle,
        "objective": strategy.objective,
        "caption": copy.caption,
        "hashtags": copy.hashtags,
        "alt_text": copy.alt_text,
        "strategy_json": _serialize_model(strategy),
        "copy_json": _serialize_model(copy),
        "design_json": _serialize_model(design or DesignerOutput()),
        "evaluation_json": _serialize_model(evaluation),
        "media_urls": _extract_media_urls(design),
        "media_blob_names": _extract_blob_names(design),
        "video_duration_seconds": design.video.duration_seconds if design and design.video else strategy.video_duration_seconds,
        "draft_status": "pending_review",
        "review_stage": state.get("review_stage", ReviewStage.FINAL.value),
        "failure_reason": None,
        "retry_count": state.get("retry_count", 0),
    }


def _build_terminal_payload(state: CommunityManagerState, *, failure_reason: str) -> dict:
    payload = _build_payload(state)
    payload.update({
        "draft_status": "denied",
        "failure_reason": failure_reason,
        "retry_count": state.get("retry_count", 0),
    })
    return payload


def _should_defer_to_human_review(state: CommunityManagerState) -> bool:
    return (
        bool(state.get("is_on_demand"))
        and state.get("review_stage") == ReviewStage.PRE_MEDIA.value
        and state.get("strategy") is not None
        and state.get("copy") is not None
        and state.get("design") is not None
    )


async def _complete_draft(state: CommunityManagerState, *, start_at: str) -> dict:
    current = start_at
    working_state = state

    while True:
        if current == "copywriter":
            working_state.update(await copywriter_node(working_state))
            current = route_after_copywriter(working_state)
            continue

        if current == "designer":
            working_state.update(await designer_node(working_state))
            current = "evaluator"
            continue

        if current != "evaluator":
            raise RuntimeError(f"Unsupported workflow node: {current}")

        working_state.update(await evaluator_node(working_state))
        evaluation = working_state.get("evaluation")
        if evaluation and evaluation.approved:
            return _build_payload(working_state)

        if evaluation and evaluation.retry_target == "abort":
            return _build_terminal_payload(
                working_state,
                failure_reason=evaluation.feedback or "Draft evaluation aborted",
            )

        if working_state.get("retry_count", 0) >= MAX_RETRIES:
            if _should_defer_to_human_review(working_state):
                return _build_payload(working_state)

            return _build_terminal_payload(
                working_state,
                failure_reason=evaluation.feedback or "Draft evaluation exceeded the maximum number of retries",
            )

        current = "designer" if evaluation and evaluation.retry_target == "designer" else "copywriter"


async def generate_reviewable_draft(
    content_type: str,
    *,
    publication_history: list[str] | None = None,
    reviewer_memory: str = "",
    requested_topic: str = "",
    requested_angle: str = "",
    requested_objective: str = "",
    requested_num_images: int | None = None,
    is_on_demand: bool = False,
) -> dict:
    state: CommunityManagerState = {
        "messages": [],
        "requested_content_type": content_type,
        "requested_topic": requested_topic,
        "requested_angle": requested_angle,
        "requested_objective": requested_objective,
        "requested_num_images": requested_num_images,
        "is_on_demand": is_on_demand,
        "review_stage": ReviewStage.PRE_MEDIA.value,
        "materialize_media": False,
        "skip_llm_evaluation": False,
        "publication_history": publication_history or [],
        "reviewer_memory": reviewer_memory,
        "reviewer_feedback": "",
        "strategy": None,
        "copy": None,
        "design": None,
        "evaluation": None,
        "retry_count": 0,
        "publish_result": None,
    }
    state.update(await strategist_node(state))
    return await _complete_draft(state, start_at="copywriter")


async def revise_reviewable_draft(
    *,
    strategy_json: str,
    copy_json: str,
    design_json: str,
    reviewer_feedback: str,
    revision_target: str,
    reviewer_memory: str = "",
) -> dict:
    strategy = ContentStrategy.model_validate_json(strategy_json)
    copy = PostCopy.model_validate_json(copy_json)
    design = DesignerOutput.model_validate_json(design_json)

    state: CommunityManagerState = {
        "messages": [],
        "requested_content_type": strategy.content_type.value,
        "requested_topic": "",
        "requested_angle": "",
        "requested_objective": "",
        "requested_num_images": strategy.num_images if strategy.content_type.value == "image_post" else None,
        "is_on_demand": True,
        "review_stage": ReviewStage.PRE_MEDIA.value,
        "materialize_media": False,
        "skip_llm_evaluation": False,
        "publication_history": [],
        "reviewer_memory": reviewer_memory,
        "reviewer_feedback": reviewer_feedback,
        "strategy": strategy,
        "copy": copy,
        "design": design,
        "evaluation": EvaluationResult(
            approved=False,
            score=0,
            feedback=reviewer_feedback,
            issues=[reviewer_feedback],
            retry_target="designer" if revision_target == "designer" else "copywriter",
        ),
        "retry_count": 0,
        "publish_result": None,
    }

    if revision_target == "all":
        state.update(await strategist_node(state))
        return await _complete_draft(state, start_at="copywriter")

    start_at = "designer" if revision_target == "designer" else "copywriter"
    return await _complete_draft(state, start_at=start_at)


async def materialize_reviewable_draft_media(*, strategy_json: str, copy_json: str, design_json: str) -> dict:
    strategy = ContentStrategy.model_validate_json(strategy_json)
    copy = PostCopy.model_validate_json(copy_json)
    design = DesignerOutput.model_validate_json(design_json)

    state: CommunityManagerState = {
        "messages": [],
        "requested_content_type": strategy.content_type.value,
        "requested_topic": strategy.topic,
        "requested_angle": strategy.angle,
        "requested_objective": strategy.objective,
        "requested_num_images": strategy.num_images if strategy.content_type.value == "image_post" else None,
        "is_on_demand": True,
        "review_stage": ReviewStage.FINAL.value,
        "materialize_media": True,
        "skip_llm_evaluation": False,
        "publication_history": [],
        "reviewer_memory": "",
        "reviewer_feedback": "",
        "strategy": strategy,
        "copy": copy,
        "design": design,
        "evaluation": None,
        "retry_count": 0,
        "publish_result": None,
    }

    if not _has_generated_media(design):
        return await _complete_draft(state, start_at="designer")

    state["evaluation"] = EvaluationResult(
        approved=False,
        score=0,
        feedback="Materializing final media from an already reviewed plan.",
        issues=[],
        retry_target="designer",
    )
    return await _complete_draft(state, start_at="designer")


async def publish_reviewable_draft(*, strategy_json: str, copy_json: str, design_json: str) -> dict:
    state: CommunityManagerState = {
        "messages": [],
        "requested_content_type": "",
        "requested_topic": "",
        "requested_angle": "",
        "requested_objective": "",
        "publication_history": [],
        "reviewer_memory": "",
        "reviewer_feedback": "",
        "strategy": ContentStrategy.model_validate_json(strategy_json),
        "copy": PostCopy.model_validate_json(copy_json),
        "design": DesignerOutput.model_validate_json(design_json),
        "evaluation": None,
        "retry_count": 0,
        "publish_result": None,
    }
    result = await publisher_node(state)
    publish_result = result["publish_result"]
    return {
        "results": publish_result.model_dump(mode="json")["results"],
        "published_at": publish_result.published_at.isoformat() if publish_result.published_at else None,
        "all_success": publish_result.all_success,
    }
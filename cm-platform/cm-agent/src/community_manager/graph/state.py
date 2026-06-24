"""Graph state definition for the Community Manager workflow."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from community_manager.models.schemas import (
    ContentStrategy,
    DesignerOutput,
    EvaluationResult,
    PostCopy,
    PublishResult,
)


class CommunityManagerState(TypedDict):
    """State that flows through the LangGraph publication workflow.

    Each key is updated by the node that owns it.
    ``messages`` uses the built-in ``add_messages`` reducer so that
    intermediate LLM messages are accumulated automatically.
    """

    # ── LLM conversation messages (accumulated) ────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Trigger / input ────────────────────────────────────────
    requested_content_type: str         # "image_post" | "text_post" | "video_post" (from scheduler)
    requested_topic: str                # optional forced theme for manual/on-demand runs
    requested_angle: str                # optional forced angle for manual/on-demand runs
    requested_objective: str            # optional forced objective/need for manual/on-demand runs
    requested_num_images: int | None    # optional explicit slide count for on-demand runs
    is_on_demand: bool                  # distinguishes cron from manual/on-demand generation
    review_stage: str                   # "pre_media" | "final"
    materialize_media: bool             # false when planning only; true when generating expensive media
    skip_llm_evaluation: bool           # manual direct publish can skip subjective LLM review
    publication_history: list[str]      # brief history of recent posts
    reviewer_memory: str                # lessons learned from previous reviewer feedback
    reviewer_feedback: str              # current revision request from reviewers

    # ── Strategist output ──────────────────────────────────────
    strategy: ContentStrategy | None

    # ── Copywriter output ──────────────────────────────────────
    copy: PostCopy | None

    # ── Designer output ────────────────────────────────────────
    design: DesignerOutput | None

    # ── Evaluator output ───────────────────────────────────────
    evaluation: EvaluationResult | None
    retry_count: int                    # how many evaluation→retry loops

    # ── Publisher output ───────────────────────────────────────
    publish_result: PublishResult | None

"""LangGraph workflow — the main publication graph.

Flow:
    [strategist] → [copywriter] → [designer] → [evaluator]
                        ↑              ↑             │
                        └── retry ─────┴─────────────┘
                                                     │
                            (approved?) ──▶ [publisher] → END
                                └──────▶ [abort] → END

The Designer is skipped for text-only posts (conditional edge).
The Evaluator can loop back to Copywriter or Designer on failure.
Max 3 retries before aborting the workflow without publishing.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from community_manager.graph.nodes.copywriter import copywriter_node
from community_manager.graph.nodes.designer import designer_node
from community_manager.graph.nodes.evaluator import evaluator_node
from community_manager.graph.nodes.publisher import publisher_node
from community_manager.graph.nodes.strategist import strategist_node
from community_manager.graph.state import CommunityManagerState
from community_manager.models.schemas import Platform, PlatformResult, PublishResult, ReviewStage

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


# ── Conditional edges ──────────────────────────────────────────

def route_after_strategist(state: CommunityManagerState) -> str:
    """After strategist: always go to copywriter first."""
    return "copywriter"


def route_after_copywriter(state: CommunityManagerState) -> str:
    """After copywriter: go to designer (for image/video) or evaluator (text-only)."""
    strategy = state.get("strategy")
    if strategy and strategy.content_type.value == "text_post":
        logger.info("→ Text-only post, skipping designer → evaluator")
        return "evaluator"
    logger.info("→ Visual post, routing to designer")
    return "designer"


def route_after_evaluator(state: CommunityManagerState) -> str:
    """After evaluator: approve → publisher, or retry → copywriter/designer."""
    evaluation = state.get("evaluation")
    retry_count = state.get("retry_count", 0)

    if evaluation and evaluation.approved:
        logger.info("→ Content approved, routing to publisher")
        return "publisher"

    if evaluation and evaluation.retry_target == "abort":
        logger.warning("→ Evaluation requested abort, ending workflow without publishing")
        return "abort"

    if retry_count >= MAX_RETRIES:
        logger.warning("→ Max retries (%d) reached, aborting workflow without publishing", MAX_RETRIES)
        return "abort"

    # Route to the specific node that needs fixing
    target = evaluation.retry_target if evaluation else "copywriter"

    if target == "designer":
        logger.info("→ Evaluator rejected (retry %d/%d), routing to designer", retry_count, MAX_RETRIES)
        return "designer"

    logger.info("→ Evaluator rejected (retry %d/%d), routing to copywriter", retry_count, MAX_RETRIES)
    return "copywriter"


def abort_node(state: CommunityManagerState) -> dict:
    """Stop the workflow without publishing anything."""
    evaluation = state.get("evaluation")
    reason = "Workflow aborted before publication"
    if evaluation and evaluation.feedback:
        reason = evaluation.feedback

    return {
        "publish_result": PublishResult(
            results=[PlatformResult(platform=Platform.INSTAGRAM, success=False, error=reason)],
        ),
    }


# ── Graph builder ──────────────────────────────────────────────

def build_graph():
    """Build and compile the Community Manager publication workflow."""

    graph = StateGraph(CommunityManagerState)

    # Add all nodes
    graph.add_node("strategist", strategist_node)
    graph.add_node("copywriter", copywriter_node)
    graph.add_node("designer", designer_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("publisher", publisher_node)
    graph.add_node("abort", abort_node)

    # Entry point
    graph.set_entry_point("strategist")

    # Edges
    graph.add_edge("strategist", "copywriter")

    # Copywriter → Designer or Evaluator (skip designer for text-only)
    graph.add_conditional_edges(
        "copywriter",
        route_after_copywriter,
        {
            "designer": "designer",
            "evaluator": "evaluator",
        },
    )

    # Designer → Evaluator
    graph.add_edge("designer", "evaluator")

    # Evaluator → Publisher or retry loop
    graph.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "publisher": "publisher",
            "copywriter": "copywriter",
            "designer": "designer",
            "abort": "abort",
        },
    )

    # Publisher → END
    graph.add_edge("publisher", END)
    graph.add_edge("abort", END)

    return graph.compile()


# ── Public entry point ─────────────────────────────────────────

async def run_content_workflow(
    content_type: str,
    *,
    skip_llm_evaluation: bool = False,
    publication_history: list[str] | None = None,
    reviewer_memory: str = "",
    requested_topic: str = "",
    requested_angle: str = "",
    requested_objective: str = "",
    requested_num_images: int | None = None,
    is_on_demand: bool = True,
) -> dict:
    """Build and invoke the CM workflow for the given content type.

    Parameters
    ----------
    content_type : str
        One of ``"image_post"``, ``"text_post"``, ``"video_post"``.
    skip_llm_evaluation : bool
        When true, keep deterministic asset validation but bypass the subjective
        LLM evaluator. Used by the manual direct-publish endpoint so test runs
        can publish without waiting on editorial retries.

    Returns
    -------
    dict
        The final state of the graph (includes ``publish_result``, etc.).
    """
    graph = build_graph()
    initial_state: CommunityManagerState = {
        "messages": [],
        "requested_content_type": content_type,
        "requested_topic": requested_topic,
        "requested_angle": requested_angle,
        "requested_objective": requested_objective,
        "requested_num_images": requested_num_images,
        "is_on_demand": is_on_demand,
        "review_stage": ReviewStage.FINAL.value,
        "materialize_media": True,
        "skip_llm_evaluation": skip_llm_evaluation,
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
    logger.info("▶ Running CM workflow for %s", content_type)
    result = await graph.ainvoke(initial_state)
    logger.info("✅ CM workflow for %s completed", content_type)
    return result

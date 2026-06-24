"""Newsletter workflow — LangGraph graph with double HITL.

Flow:
    [researcher] → [content_scorer] → [writer] → [quality_review] → [chart_planner] → [evaluator_pre_media] → [slides_planner]
                                                                                              ↓
                                                                                        HITL #1 (text + plan review)
                                                                                              ↓
                                                                                  [image_generator] → [chart_renderer] → [slides_assembler]
                                                                                                                             ↓
                                                                                                                       HITL #2 (final review)
                                                                                                                             ↓
                                                                                                                        [distributor] → END

The quality_review node is a DETERMINISTIC, no-LLM editorial guard. It
auto-fixes consultant jargon, detects contradictions between slides, and
flags generic claims that lack concrete numbers.
"""

from __future__ import annotations

import logging
from datetime import datetime

from langgraph.graph import END, StateGraph

from community_manager.models.schemas import EvaluationResult, GeneratedImage, RadarReport
from community_manager.nurturing.google_slides_template import GoogleSlidesArtifact
from community_manager.nurturing.nodes.chart_planner import SlidesPlan, chart_planner_node
from community_manager.nurturing.nodes.chart_renderer import chart_renderer_node
from community_manager.nurturing.nodes.content_scorer import content_scorer_node
from community_manager.nurturing.nodes.distributor import distributor_node
from community_manager.nurturing.nodes.evaluator_pre_media import evaluator_pre_media_node
from community_manager.nurturing.nodes.image_generator import image_generator_node
from community_manager.nurturing.nodes.quality_review import quality_review_node
from community_manager.nurturing.nodes.researcher import researcher_node
from community_manager.nurturing.nodes.slides_assembler import slides_assembler_node
from community_manager.nurturing.nodes.slides_planner import slides_planner_node
from community_manager.nurturing.nodes.writer import writer_node

logger = logging.getLogger(__name__)


# ── State definition ────────────────────────────────────────────

class NewsletterState(dict):
    """State that flows through the newsletter workflow."""

    # Input
    month_name: str
    job_id: str | None

    # Research & Writing
    raw_report: RadarReport | None
    newsletter_content: dict | None

    # Quality review (post-writer, deterministic editorial guard)
    quality_issues: list[dict]

    # Planning
    slides_plan: SlidesPlan | None

    # Evaluation
    pre_media_evaluation: EvaluationResult | None
    retry_count: int

    # Slides Draft (HITL #1)
    slides_draft_url: str | None
    slides_draft_id: str | None
    slides_draft_approved: bool | None

    # Media Generation
    generated_images: list[GeneratedImage]
    chart_url: str | None
    chart_blob_name: str | None

    # Final Slides (HITL #2)
    slides_final_url: str | None
    slides_final_id: str | None
    slides_final_artifact: GoogleSlidesArtifact | None
    slides_final_approved: bool | None

    # Distribution
    send_result: dict | None

    # Canvas awareness (computed at workflow start)
    slide_layouts: dict | None

    # Abort tracking — set by researcher/evaluator when we can't proceed
    abort_reason: str | None  # e.g. "no_search_results", "insufficient_insights"
    abort_detail: str | None


# ── Conditional edges ───────────────────────────────────────────

def route_after_evaluator(state: NewsletterState) -> str:
    """After evaluator: approve → slides_planner, or retry → researcher/writer."""
    evaluation = state.get("pre_media_evaluation")
    retry_count = state.get("retry_count", 0)
    abort_reason = state.get("abort_reason")

    if abort_reason:
        logger.warning("→ Abort reason set: %s — aborting without retry", abort_reason)
        return "abort"

    if evaluation and evaluation.approved:
        logger.info("→ Pre-media evaluation passed, routing to slides_planner")
        return "slides_planner"

    if retry_count >= 3:
        logger.warning("→ Max retries reached, aborting")
        return "abort"

    # Route to the specific node that needs fixing
    target = evaluation.retry_target if evaluation else "researcher"
    if target == "abort":
        logger.warning("→ Evaluator requested abort — aborting without retry")
        return "abort"
    logger.info("→ Pre-media evaluation failed, retrying %s (attempt %d)", target, retry_count + 1)
    return target


def route_after_hitl1(state: NewsletterState) -> str:
    """After HITL #1: approved → image_generator, pending → wait, or revise → researcher."""
    approved = state.get("slides_draft_approved")

    # Approved - proceed to image generation
    if approved is True:
        return "image_generator"

    # Pending approval - workflow should pause here
    # The API endpoint will update the state and resume
    if approved is None:
        logger.info("HITL #1 — Waiting for approval")
        return "wait_for_approval"

    # Not approved - check retries
    retry_count = state.get("retry_count", 0)
    if retry_count >= 3:
        return "abort"

    return "researcher"


def route_after_hitl2(state: NewsletterState) -> str:
    """After HITL #2: approved → distributor, or revise → image_generator."""
    approved = state.get("slides_final_approved")
    if approved:
        return "distributor"

    # If not approved, regenerate images
    return "image_generator"


# ── Helper nodes ────────────────────────────────────────────────

def increment_retry(state: NewsletterState) -> dict:
    """Increment retry counter."""
    return {"retry_count": state.get("retry_count", 0) + 1}


def abort_node(state: NewsletterState) -> dict:
    """Abort the workflow."""
    logger.warning("Workflow aborted after %d retries", state.get("retry_count", 0))
    return {"send_result": {"success": False, "error": "Aborted after max retries"}}


def hitl1_placeholder(state: NewsletterState) -> dict:
    """HITL #1 — Send draft to reviewers for approval.

    Sends an email that looks like the final version the lead would receive:
    - Brief executive summary
    - Link to Google Slides
    - Approve/Reject links (like CM agent)
    - NO personalization (that's per-lead in the final send)
    """
    logger.info("HITL #1 — Sending draft to reviewers")

    slides_draft_url = state.get("slides_draft_url")
    raw_report = state.get("raw_report")
    job_id = state.get("job_id")

    if not slides_draft_url:
        logger.warning("No slides draft URL, auto-approving")
        return {"slides_draft_approved": True}

    # Send email to reviewers with summary + links
    import asyncio
    try:
        from community_manager.config.settings import get_settings
        from community_manager.services.nurturing_mail_service import NurturingMailService
        from community_manager.services.nurturing_content_renderer import wrap_in_html_email
        from community_manager.main import _generate_review_token

        settings = get_settings()
        mail_service = NurturingMailService()

        if not mail_service.is_configured:
            logger.warning("Mail service not configured, auto-approving")
            return {"slides_draft_approved": True}

        reviewers = settings.nurturing_reviewer_list
        if not reviewers:
            logger.warning("No reviewers configured, auto-approving")
            return {"slides_draft_approved": True}

        # Generate review token for approve/reject links
        review_token = _generate_review_token(job_id or "unknown")
        base_url = "https://ia.novitsoftware.com"
        approve_url = f"{base_url}/api/nurturing/review/{review_token}/approve"
        reject_url = f"{base_url}/api/nurturing/review/{review_token}/reject"

        # Build executive summary content
        executive_summary = raw_report.executive_summary if raw_report else ""
        
        # Build selected insights table
        selected_html = ""
        if raw_report and raw_report.insights:
            selected_html = "<table style='width:100%;border-collapse:collapse;margin:12px 0;font-size:13px;'>"
            selected_html += "<tr style='background:#0A0089;color:#fff;'><th style='padding:8px;text-align:left;'>País</th><th style='padding:8px;text-align:left;'>Headline</th><th style='padding:8px;text-align:left;'>Categoría</th><th style='padding:8px;text-align:left;'>Score</th><th style='padding:8px;text-align:left;'>Fuente</th></tr>"
            for insight in raw_report.insights:
                source_display = f"<a href='{insight.source_url}' style='color:#BA08A8;text-decoration:none;'>{insight.source_title}</a>"
                selected_html += f"<tr style='border-bottom:1px solid #ddd;'><td style='padding:8px;'>{insight.country_tag}</td><td style='padding:8px;'><b>{insight.headline}</b></td><td style='padding:8px;'>{insight.category}</td><td style='padding:8px;'>⭐ Principal</td><td style='padding:8px;'>{source_display}</td></tr>"
            for insight in raw_report.insights_secondary:
                source_display = f"<a href='{insight.source_url}' style='color:#BA08A8;text-decoration:none;'>{insight.source_title}</a>"
                selected_html += f"<tr style='border-bottom:1px solid #ddd;background:#f8f9fa;'><td style='padding:8px;'>{insight.country_tag}</td><td style='padding:8px;'><b>{insight.headline}</b></td><td style='padding:8px;'>{insight.category}</td><td style='padding:8px;'>⭐ Secundario</td><td style='padding:8px;'>{source_display}</td></tr>"
            selected_html += "</table>"
        
        # Build discarded insights table
        discarded_html = ""
        discarded = raw_report.discarded_insights if raw_report else []
        if discarded:
            discarded_html = "<table style='width:100%;border-collapse:collapse;margin:12px 0;font-size:12px;color:#666;'>"
            discarded_html += "<tr style='background:#f0f0f0;'><th style='padding:6px;text-align:left;'>País</th><th style='padding:6px;text-align:left;'>Headline</th><th style='padding:6px;text-align:left;'>Score</th><th style='padding:6px;text-align:left;'>Motivo descarte</th></tr>"
            for item in discarded:
                discarded_html += f"<tr style='border-bottom:1px solid #eee;'><td style='padding:6px;'>{item.get('country','')}</td><td style='padding:6px;'>{item.get('headline','')}</td><td style='padding:6px;'>{item.get('score',0)}</td><td style='padding:6px;font-style:italic;'>{item.get('reason','')}</td></tr>"
            discarded_html += "</table>"

        insights_bullets = ""
        if raw_report and raw_report.insights:
            insights_bullets = "<ul style='padding-left:20px;margin:12px 0;'>"
            for insight in raw_report.insights[:3]:
                insights_bullets += f"<li style='margin-bottom:8px;'><b>{insight.headline}</b><br>{insight.summary}</li>"
            insights_bullets += "</ul>"

        # Build email that mimics the final version (without personalization)
        body_html = f"""
        <p style="color:#BA08A8;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">AI Radar by Novit</p>
        <p style="font-size:20px;line-height:1.2;color:#0A0089;font-weight:800;margin:8px 0 16px 0;">
            {raw_report.report_title if raw_report else 'AI Radar'}
        </p>

        <p style="color:#1F2430;margin-bottom:16px;">{executive_summary}</p>

        {insights_bullets}

        <p style="margin:20px 0;">
            <a href="{slides_draft_url}" style="display:inline-block;background:#0A0089;color:#ffffff;
            text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:700;font-size:14px;">
            Ver presentación completa
        </a>
        </p>

        <hr style="border:none;border-top:1px solid #dddddd;margin:20px 0;">

        <h3 style="color:#0A0089;margin-top:20px;">📰 Noticias seleccionadas para esta edición</h3>
        {selected_html}

        <h3 style="color:#8f2d2d;margin-top:24px;">🗑️ Noticias descartadas</h3>
        <p style="font-size:12px;color:#666;margin-bottom:8px;">Estas noticias fueron evaluadas pero no superaron el criterio de relevancia, accionabilidad o novedad:</p>
        {discarded_html}

        <div style="background:#f8f9fa;padding:16px;border-radius:8px;margin:16px 0;">
        <p style="margin:0 0 12px;font-weight:700;color:#1F2430;">Acciones de revisión:</p>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
            <a href="{approve_url}" style="display:inline-block;background:#1f7a4d;color:#ffffff;
            text-decoration:none;padding:10px 20px;border-radius:999px;font-weight:700;font-size:13px;">
            Aprobar
        </a>
            <a href="{reject_url}" style="display:inline-block;background:#8f2d2d;color:#ffffff;
            text-decoration:none;padding:10px 20px;border-radius:999px;font-weight:700;font-size:13px;">
            Solicitar cambios
        </a>
        </div>
        <p style="margin:12px 0 0;font-size:12px;color:#666;">
            Las imágenes se generarán después de tu aprobación. La personalización por lead se hace en el envío final.
        </p>
        </div>
        """

        html = wrap_in_html_email(body_html)

        subject = f"[REVISIÓN] {raw_report.subject if raw_report else 'AI Radar'}"

        # Send to all reviewers (may run in thread without event loop)
        for reviewer in reviewers:
            try:
                loop = asyncio.get_running_loop()
                # Already in async context — schedule as task
                asyncio.create_task(
                    mail_service.send_email(reviewer, subject, html, is_html=True)
                )
            except RuntimeError:
                # No event loop in this thread — create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        mail_service.send_email(reviewer, subject, html, is_html=True)
                    )
                finally:
                    loop.close()

        logger.info("✅ HITL #1 email sent to %d reviewers", len(reviewers))

    except Exception:
        logger.exception("Failed to send HITL #1 email")

    # Return pending approval (workflow will pause)
    return {"slides_draft_approved": None}


def hitl2_placeholder(state: NewsletterState) -> dict:
    """HITL #2 placeholder — in production, this would pause for human review."""
    logger.info("HITL #2 — Auto-approving (placeholder)")
    return {"slides_final_approved": True}


def wait_for_approval_node(state: NewsletterState) -> dict:
    """Wait for human approval node — pauses workflow until API approval.

    This node returns the current state unchanged. The workflow will be
    checkpointed here and resumed when the human approves via API.
    """
    logger.info("Waiting for human approval...")
    return {}


# ── Graph builder ───────────────────────────────────────────────

def build_newsletter_graph():
    """Build and compile the newsletter workflow graph."""

    graph = StateGraph(NewsletterState)

    # Add all nodes
    graph.add_node("researcher", researcher_node)
    graph.add_node("content_scorer", content_scorer_node)
    graph.add_node("writer", writer_node)
    graph.add_node("quality_review", quality_review_node)
    graph.add_node("chart_planner", chart_planner_node)
    graph.add_node("evaluator_pre_media", evaluator_pre_media_node)
    graph.add_node("slides_planner", slides_planner_node)
    graph.add_node("hitl1", hitl1_placeholder)
    graph.add_node("wait_for_approval", wait_for_approval_node)
    graph.add_node("image_generator", image_generator_node)
    graph.add_node("chart_renderer", chart_renderer_node)
    graph.add_node("slides_assembler", slides_assembler_node)
    graph.add_node("hitl2", hitl2_placeholder)
    graph.add_node("distributor", distributor_node)
    graph.add_node("abort", abort_node)
    graph.add_node("increment_retry", increment_retry)

    # Entry point
    graph.set_entry_point("researcher")

    # Edges
    graph.add_edge("researcher", "content_scorer")
    graph.add_edge("content_scorer", "writer")
    graph.add_edge("writer", "quality_review")
    graph.add_edge("quality_review", "chart_planner")
    graph.add_edge("chart_planner", "evaluator_pre_media")

    # Evaluator → slides_planner or retry
    graph.add_conditional_edges(
        "evaluator_pre_media",
        route_after_evaluator,
        {
            "slides_planner": "slides_planner",
            "researcher": "increment_retry",
            "writer": "increment_retry",
            "abort": "abort",
        },
    )

    # After increment_retry, go back to researcher
    graph.add_edge("increment_retry", "researcher")

    # Slides planner → HITL #1
    graph.add_edge("slides_planner", "hitl1")

    # HITL #1 → image_generator or revise or wait
    graph.add_conditional_edges(
        "hitl1",
        route_after_hitl1,
        {
            "image_generator": "image_generator",
            "wait_for_approval": "wait_for_approval",
            "researcher": "increment_retry",
            "abort": "abort",
        },
    )

    # Wait for approval → END (workflow pauses here, resumed via API)
    graph.add_edge("wait_for_approval", END)

    # Image generator → chart renderer → slides assembler
    graph.add_edge("image_generator", "chart_renderer")
    graph.add_edge("chart_renderer", "slides_assembler")

    # Slides assembler → HITL #2
    graph.add_edge("slides_assembler", "hitl2")

    # HITL #2 → distributor or regenerate
    graph.add_conditional_edges(
        "hitl2",
        route_after_hitl2,
        {
            "distributor": "distributor",
            "image_generator": "image_generator",
        },
    )

    # Distributor → END
    graph.add_edge("distributor", END)
    graph.add_edge("abort", END)

    return graph.compile()


# ── Public entry point ──────────────────────────────────────────

async def run_newsletter_workflow(*, month_name: str | None = None, job_id: str | None = None) -> dict:
    """Run the newsletter workflow.

    Parameters
    ----------
    month_name : str | None
        Month name in Spanish (e.g., "junio 2025"). If None, uses current month.
    job_id : str | None
        Optional job ID for tracking and HITL resumption.

    Returns
    -------
    dict
        The final state of the workflow.
    """
    if not month_name:
        month_name = _get_month_name()

    # Pre-compute slide layouts so the writer has canvas metadata available
    from community_manager.tools.pptx_layout import get_slide_layouts

    graph = build_newsletter_graph()

    initial_state: NewsletterState = {
        "month_name": month_name,
        "job_id": job_id,
        "raw_report": None,
        "newsletter_content": None,
        "quality_issues": [],
        "slides_plan": None,
        "pre_media_evaluation": None,
        "retry_count": 0,
        "slides_draft_url": None,
        "slides_draft_id": None,
        "slides_draft_approved": None,
        "generated_images": [],
        "chart_url": None,
        "chart_blob_name": None,
        "slides_final_url": None,
        "slides_final_id": None,
        "slides_final_artifact": None,
        "slides_final_approved": None,
        "send_result": None,
        "slide_layouts": get_slide_layouts(),
        "abort_reason": None,
        "abort_detail": None,
    }

    logger.info("▶ Running newsletter workflow for %s (job_id=%s)", month_name, job_id)
    result = await graph.ainvoke(initial_state)
    logger.info("✅ Newsletter workflow completed")

    return result


def _get_month_name() -> str:
    """Return current month name in Spanish."""
    _MONTHS_ES = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }
    now = datetime.utcnow()
    return f"{_MONTHS_ES[now.month]} {now.year}"

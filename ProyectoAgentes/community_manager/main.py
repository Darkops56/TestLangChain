"""Agent entry point — FastAPI server + APScheduler.

This is the main process for the ``agent`` Docker service.
It exposes an INTERNAL-ONLY FastAPI server (port 8000, no Caddy route)
and starts the cron scheduler for both Community Manager and Nurturing tasks.

Endpoints (all internal, secured with X-Internal-Key header):
  GET  /health                          → liveness probe
  POST /internal/webhook/message        → receive Meta messages from .NET
  POST /internal/nurturing/generate     → trigger newsletter generation
  POST /internal/nurturing/revise       → trigger newsletter revision
  POST /internal/nurturing/reply        → generate a reply to a newsletter response
  POST /internal/nurturing/closing      → generate a personal closing
  GET  /internal/nurturing/status       → get current status
    GET  /internal/community/draft-jobs/{job_id} → get async reviewer-gated draft job status
    POST /internal/community/generate-draft → generate a reviewer-gated social draft
        POST /internal/community/generate-draft-now → queue a reviewer-gated social draft in background
    POST /internal/community/revise-draft   → revise a social draft from reviewer feedback
    POST /internal/community/publish-draft  → publish an approved social draft
    POST /internal/community/publish-now    → run full generation+publish pipeline (no review)

Modes:
  default (no flags) → scheduler + API server
  --webhooks-only    → API server only, no scheduler
  --once             → run a single CM workflow and exit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from community_manager.config.settings import get_settings
from community_manager.graph.review_workflow import (
    generate_reviewable_draft,
    materialize_reviewable_draft_media,
    publish_reviewable_draft,
    revise_reviewable_draft,
)
from community_manager.graph.nodes.publisher import cleanup_remote_media
from community_manager.graph.workflow import run_content_workflow
from community_manager.graph.nodes.responder import enqueue_message, process_pending_messages, process_single_message, was_message_processed
from community_manager.models.schemas import DesignerOutput, IncomingMessage
from community_manager.nurturing.reply_service import (
    generate_personal_closing,
    generate_reply,
)
from community_manager.nurturing.revise_service import revise_newsletter
from community_manager.nurturing.workflow_v2 import run_newsletter_workflow
from community_manager.services.nurturing_content_renderer import wrap_in_html_email
from community_manager.scheduler.cron import AgentScheduler
from community_manager.tools.dotnet_client import DotNetClient
from community_manager.tools.meta_api import MetaClient

logger = logging.getLogger("community_manager")

# ── Global state ───────────────────────────────────────────────

_scheduler: AgentScheduler | None = None
_dotnet: DotNetClient | None = None
_status: dict = {"last_run": None, "state": "idle"}
_community_draft_jobs: dict[str, dict] = {}
_start_scheduler = True  # set to False with --webhooks-only
SUPPORTED_COMMUNITY_CONTENT_TYPES = {"image_post", "video_post"}
DEFAULT_COMMUNITY_CONTENT_TYPE = "image_post"
MAX_TRACKED_COMMUNITY_DRAFT_JOBS = 200


def _require_supported_community_content_type(content_type: str) -> str:
    normalized = (content_type or "").strip().lower() or DEFAULT_COMMUNITY_CONTENT_TYPE
    if normalized not in SUPPORTED_COMMUNITY_CONTENT_TYPES:
        raise ValueError(
            f"Unsupported community content type '{content_type}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_COMMUNITY_CONTENT_TYPES))}."
        )
    return normalized


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _build_template_closing(first_name: str | None, org_name: str | None) -> str:
    if org_name:
        return f"Te lo comparto por si suma mirarlo con el equipo de {org_name}. Abrazo!"
    return "Te lo comparto por si suma mirarlo con calma. Abrazo!"


def _prune_community_draft_jobs() -> None:
    if len(_community_draft_jobs) <= MAX_TRACKED_COMMUNITY_DRAFT_JOBS:
        return

    recent_jobs = sorted(
        _community_draft_jobs.items(),
        key=lambda item: item[1].get("updated_at") or "",
        reverse=True,
    )
    _community_draft_jobs.clear()
    _community_draft_jobs.update(recent_jobs[:MAX_TRACKED_COMMUNITY_DRAFT_JOBS])


def _create_community_draft_job(
    job_id: str,
    *,
    content_type: str,
    topic: str | None,
    angle: str | None,
    objective: str | None,
) -> None:
    now = _utcnow_iso()
    _community_draft_jobs[job_id] = {
        "job_id": job_id,
        "state": "queued",
        "step": "accepted",
        "content_type": content_type,
        "topic": topic,
        "angle": angle,
        "objective": objective,
        "draft_id": None,
        "draft_status": None,
        "review_subject": None,
        "review_token": None,
        "failure_reason": None,
        "error": None,
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    _prune_community_draft_jobs()


def _update_community_draft_job(job_id: str, **changes) -> None:
    job = _community_draft_jobs.get(job_id)
    if not job:
        now = _utcnow_iso()
        job = {"job_id": job_id, "started_at": now, "updated_at": now}
        _community_draft_jobs[job_id] = job

    job.update(changes)
    job["updated_at"] = _utcnow_iso()

    if job.get("state") in {"completed", "failed"} and not job.get("completed_at"):
        job["completed_at"] = job["updated_at"]

    _prune_community_draft_jobs()


# ── Internal API key security ──────────────────────────────────

async def _verify_internal_key(request: Request) -> None:
    """Dependency: reject requests without a valid X-Internal-Key header."""
    settings = get_settings()
    if not settings.internal_api_key:
        return  # no key configured → skip (dev mode)
    key = request.headers.get("X-Internal-Key", "")
    if key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


# ── Request / Response models ──────────────────────────────────

class WebhookMessageRequest(BaseModel):
    sender_id: str
    sender_name: str = ""
    text: str
    platform: str = "instagram"
    message_id: str | None = None
    reply_target_id: str | None = None
    reply_target_type: str = "direct_message"
    post_context_id: str | None = None
    post_context_text: str | None = None
    timestamp: str | None = None


class NewsletterRevisionRequest(BaseModel):
    current_subject: str
    current_body: str
    reviewer_feedback: str


class ReplyRequest(BaseModel):
    original_subject: str
    original_body: str
    sender_name: str


class ClosingRequest(BaseModel):
    newsletter_subject: str
    newsletter_body: str | None = None
    first_name: str | None = None
    org_name: str | None = None
    deal_notes: list[str] = []


class WrapEmailRequest(BaseModel):
    html_body: str
    first_name: str | None = None
    personal_closing: str | None = None


class CommunityDraftGenerateRequest(BaseModel):
    content_type: str
    reviewer_memory: str = ""
    publication_history: list[str] = Field(default_factory=list)
    topic: str | None = None
    angle: str | None = None
    objective: str | None = None
    num_images: int | None = None


class CommunityDraftRevisionRequest(BaseModel):
    strategy_json: str
    copy_json: str
    design_json: str
    reviewer_feedback: str
    revision_target: str = "all"
    reviewer_memory: str = ""


class CommunityDraftPublishRequest(BaseModel):
    strategy_json: str
    copy_json: str
    design_json: str


class CommunityDraftMaterializeRequest(BaseModel):
    strategy_json: str
    copy_json: str
    design_json: str


class CommunityDraftMediaCleanupRequest(BaseModel):
    design_json: str


class CommunityPublishNowRequest(BaseModel):
    content_type: str = "image_post"
    topic: str | None = None
    angle: str | None = None
    objective: str | None = None
    num_images: int | None = None


# ── Scheduler callbacks ───────────────────────────────────────

async def _load_publication_history(limit: int = 8) -> list[str]:
    if not _dotnet:
        return []

    try:
        return await _dotnet.get_recent_community_publication_history(limit=limit)
    except Exception:
        logger.exception("Failed to load recent community publication history")
        return []


async def _generate_and_persist_review_draft(
    content_type: str,
    *,
    topic: str | None = None,
    angle: str | None = None,
    objective: str | None = None,
    num_images: int | None = None,
    is_on_demand: bool = False,
) -> dict:
    reviewer_memory = await _dotnet.get_community_reviewer_memory() if _dotnet else ""
    publication_history = await _load_publication_history(limit=8)
    draft = await generate_reviewable_draft(
        content_type,
        publication_history=publication_history,
        reviewer_memory=reviewer_memory,
        requested_topic=topic or "",
        requested_angle=angle or "",
        requested_objective=objective or "",
        requested_num_images=num_images,
        is_on_demand=is_on_demand,
    )

    if not _dotnet:
        raise RuntimeError("No .NET bridge available to persist the generated community draft")

    return await _dotnet.create_community_draft(draft)

async def _on_publish(content_type: str) -> None:
    """Callback: generate a reviewer-gated draft instead of publishing directly."""
    content_type = _require_supported_community_content_type(content_type)
    _status["state"] = f"drafting:{content_type}"
    _status["last_run"] = datetime.utcnow().isoformat()
    try:
        saved = await _generate_and_persist_review_draft(content_type, is_on_demand=False)
        logger.info(
            "Community draft %s saved with status %s",
            saved.get("draft_id"),
            saved.get("status"),
        )
    except Exception:
        logger.exception("Community draft workflow %s failed", content_type)
    finally:
        _status["state"] = "idle"


async def _on_responder() -> None:
    """Callback: check for pending messages via .NET backend."""
    try:
        meta = MetaClient()
        try:
            pending_messages = await meta.get_unanswered_direct_messages()
        finally:
            await meta.close()

        for message in pending_messages:
            if was_message_processed(message.message_id):
                continue
            enqueue_message(message)

        if pending_messages:
            logger.info("Responder poll queued %d unanswered Instagram DM(s)", len(pending_messages))

        await process_pending_messages()
    except Exception:
        logger.exception("Responder check failed")


async def _on_nurturing_generate() -> None:
    """Callback: generate a newsletter via v2 workflow."""
    _status["state"] = "nurturing:generating"
    try:
        result = await run_newsletter_workflow()
        logger.info("AI Radar v2 workflow completed: %s", result.get("month_name", "unknown"))
    except Exception:
        logger.exception("AI Radar generation failed")
    finally:
        _status["state"] = "idle"


async def _on_nurturing_send() -> None:
    """Callback: send the current nurturing report via .NET infra services."""
    _status["state"] = "nurturing:sending"
    try:
        if _dotnet:
            now = datetime.utcnow()
            month_key = now.strftime("%Y-%m")
            newsletter = await _dotnet.get_newsletter(month_key)
            if not newsletter:
                logger.warning("No nurturing report found for %s", month_key)
                return

            recipients = await _dotnet.get_nurturing_recipients()
            if not recipients:
                logger.warning("No nurturing recipients found for %s", month_key)
                return

            artifact = {}
            artifact_json = newsletter.get("artifact_json")
            if artifact_json:
                try:
                    artifact = json.loads(artifact_json)
                except json.JSONDecodeError:
                    logger.warning("Invalid artifact_json for nurturing report %s", month_key)

            body = newsletter.get("body", "")
            subject = newsletter.get("subject", "AI Radar by Novit")
            slides_url = artifact.get("slides_url")

            for recipient in recipients:
                deal_notes = await _dotnet.get_deal_notes(recipient.deal_id)
                closing = None
                if deal_notes:
                    closing = await generate_personal_closing(
                        newsletter_subject=subject,
                        newsletter_body=body,
                        first_name=recipient.first_name or None,
                        org_name=recipient.org_name or None,
                        deal_notes=[note.content for note in deal_notes if note.content],
                    )

                final_closing = closing or _build_template_closing(
                    recipient.first_name or None,
                    recipient.org_name or None,
                )

                cta_parts: list[str] = []
                if slides_url:
                    cta_parts.append(
                        f'<p style="margin:20px 0 0 0;"><a href="{slides_url}" style="display:inline-block;background:#0A0089;color:#fff;text-decoration:none;padding:10px 16px;border-radius:999px;font-weight:700;">Abrir Google Slides</a></p>'
                    )

                extra_cta_html = ""
                if slides_url and slides_url not in body:
                    extra_cta_html += cta_parts[0] if cta_parts else ""

                html = wrap_in_html_email(
                    html_body=body + extra_cta_html,
                    first_name=recipient.first_name or None,
                    personal_closing=final_closing,
                )

                sent = await _dotnet.send_email(
                    to_email=recipient.email,
                    to_name=recipient.first_name or recipient.contact_name,
                    subject=subject,
                    html_body=html,
                )
                if not sent:
                    logger.warning("Failed to send nurturing report to %s", recipient.email)

            await _dotnet.mark_newsletter_sent(month_key)
        logger.info("Nurturing report send completed")
    except Exception:
        logger.exception("Nurturing report send failed")
    finally:
        _status["state"] = "idle"


async def _on_nurturing_check_replies() -> None:
    """Callback: check for unanswered newsletter replies."""
    try:
        if _dotnet:
            replies = await _dotnet.get_unanswered_replies()
            for reply_data in replies:
                reply_text = await generate_reply(
                    original_subject=reply_data.get("subject", ""),
                    original_body=reply_data.get("body", ""),
                    sender_name=reply_data.get("sender_name", ""),
                )
                await _dotnet.send_reply(
                    to_email=reply_data.get("from_email", ""),
                    to_name=reply_data.get("sender_name", ""),
                    subject=f"Re: {reply_data.get('subject', '')}",
                    body=reply_text,
                    in_reply_to=reply_data.get("message_id"),
                    references=reply_data.get("message_id") or "",
                )
            if replies:
                logger.info("Processed %d newsletter replies", len(replies))
    except Exception:
        logger.exception("Nurturing reply check failed")


# ── App lifecycle ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler on startup, shut down on teardown."""
    global _scheduler, _dotnet

    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _dotnet = DotNetClient()

    meta = MetaClient()
    try:
        await meta.ensure_webhook_subscriptions()
    finally:
        await meta.close()

    if _start_scheduler:
        _scheduler = AgentScheduler()

        # Determine which nurturing callbacks to register
        nurturing_enabled = os.getenv("NURTURING_V2_ENABLED", "false").lower() == "true"

        _scheduler.configure(
            publish_callback=_on_publish,
            responder_callback=_on_responder,
            nurturing_generate_callback=_on_nurturing_generate if nurturing_enabled else None,
            nurturing_send_callback=_on_nurturing_send if nurturing_enabled else None,
            nurturing_check_replies_callback=_on_nurturing_check_replies if nurturing_enabled else None,
        )
        _scheduler.start()
        logger.info("Agent started (scheduler=ON, nurturing_v2=%s)", nurturing_enabled)
    else:
        logger.info("Agent started (webhooks-only mode, scheduler=OFF)")

    yield

    if _scheduler:
        _scheduler.shutdown()
    if _dotnet:
        await _dotnet.close()
    logger.info("Agent shut down")


# ── FastAPI app ────────────────────────────────────────────────

app = FastAPI(
    title="Novit Community Manager Agent",
    description="Internal API for the Python agent service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Liveness probe — no auth required."""
    return {"status": "ok", "service": "agent"}


@app.post("/internal/webhook/message", dependencies=[Depends(_verify_internal_key)])
async def receive_webhook_message(req: WebhookMessageRequest):
    """Receive a Meta/Instagram message forwarded by the .NET backend."""
    msg = IncomingMessage(
        sender_id=req.sender_id,
        sender_name=req.sender_name,
        text=req.text,
        platform=req.platform,
        message_id=req.message_id or "",
        reply_target_id=req.reply_target_id or req.sender_id,
        reply_target_type=req.reply_target_type,
        post_context_id=req.post_context_id or "",
        post_context_text=req.post_context_text or "",
        timestamp=req.timestamp or datetime.utcnow().isoformat(),
    )
    try:
        reply = await process_single_message(msg)
        return {"status": "ok", "reply": reply}
    except Exception:
        logger.exception("Failed to process webhook message from %s", req.sender_id)
        raise HTTPException(status_code=500, detail="Message processing failed")


@app.post("/internal/nurturing/generate", dependencies=[Depends(_verify_internal_key)])
async def trigger_newsletter_generation(background_tasks: BackgroundTasks):
    """Trigger newsletter generation with AI + web search using v2 workflow.
    
    Runs asynchronously in background. Returns job ID immediately.
    The workflow will send an email to reviewers when the draft is ready.
    """
    import uuid
    job_id = f"newsletter_{uuid.uuid4().hex[:8]}"

    # Register job for HITL tracking
    _newsletter_jobs[job_id] = {
        "job_id": job_id,
        "state": "running",
        "step": "researcher",
        "slides_draft_url": None,
        "slides_final_url": None,
        "error": None,
        "started_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    def _run_workflow_bg():
        """Run workflow in background thread with new event loop."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_newsletter_workflow(job_id=job_id))
            job = _newsletter_jobs.get(job_id)
            if job:
                # Store full state for potential HITL resumption
                job["state"] = "waiting_approval"
                job["month_name"] = result.get("month_name", "")
                job["raw_report"] = result.get("raw_report")
                job["newsletter_content"] = result.get("newsletter_content")
                job["slides_plan"] = result.get("slides_plan")
                job["pre_media_evaluation"] = result.get("pre_media_evaluation")
                job["retry_count"] = result.get("retry_count", 0)
                job["slides_draft_url"] = result.get("slides_draft_url")
                job["slides_draft_id"] = result.get("slides_draft_id")
                job["chart_url"] = result.get("chart_url")
                job["chart_blob_name"] = result.get("chart_blob_name")
                job["slides_final_url"] = result.get("slides_final_url")
                job["send_result"] = result.get("send_result")
                job["updated_at"] = datetime.utcnow().isoformat()
            logger.info("Newsletter workflow completed for job %s", job_id)
        except Exception:
            logger.exception("Newsletter workflow failed for job %s", job_id)
            job = _newsletter_jobs.get(job_id)
            if job:
                job["state"] = "failed"
                job["error"] = str(sys.exc_info()[1])
                job["updated_at"] = datetime.utcnow().isoformat()
        finally:
            loop.close()
    
    # Start workflow in background
    import threading
    thread = threading.Thread(target=_run_workflow_bg, daemon=True)
    thread.start()
    
    return {
        "status": "ok",
        "message": "Newsletter generation started in background",
        "job_id": job_id,
    }


@app.post("/internal/nurturing/generate-sync", dependencies=[Depends(_verify_internal_key)])
async def trigger_newsletter_generation_sync():
    """Generate newsletter synchronously and return the full result.

    Unlike the async endpoint (/internal/nurturing/generate) which runs the
    workflow in a background thread and returns a job ID, this endpoint runs
    the entire workflow inline and returns the generated content directly.

    Used by the .NET TestGenerate endpoint for preview purposes (no emails sent).

    Returns
    -------
    JSON with subject, body, report_title, executive_summary, artifact_json.
    """
    import uuid
    job_id = f"newsletter_{uuid.uuid4().hex[:8]}"
    logger.info("Synchronous newsletter generation (job_id=%s)", job_id)
    try:
        result = await run_newsletter_workflow(job_id=job_id)
        nc = result.get("newsletter_content")
        if nc is None:
            logger.error("Workflow returned no newsletter_content")
            raise HTTPException(status_code=500, detail="Workflow returned no newsletter content")
        return {
            "subject": nc.subject,
            "body": nc.body,
            "report_title": nc.report_title,
            "executive_summary": nc.executive_summary,
            "artifact_json": nc.artifact_json,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Synchronous newsletter generation failed (job_id=%s)", job_id)
        raise HTTPException(status_code=500, detail=f"Newsletter generation failed: {sys.exc_info()[1]}")


@app.post("/internal/nurturing/revise", dependencies=[Depends(_verify_internal_key)])
async def trigger_newsletter_revision(req: NewsletterRevisionRequest):
    """Revise an existing newsletter based on reviewer feedback."""
    try:
        report = await revise_newsletter(
            current_subject=req.current_subject,
            current_body=req.current_body,
            reviewer_feedback=req.reviewer_feedback,
        )
        return {"status": "ok", **report.model_dump(exclude_none=True)}
    except Exception:
        logger.exception("Newsletter revision failed")
        raise HTTPException(status_code=500, detail="Newsletter revision failed")


@app.post("/internal/nurturing/reply", dependencies=[Depends(_verify_internal_key)])
async def trigger_reply_generation(req: ReplyRequest):
    """Generate a reply to a newsletter response."""
    try:
        reply_text = await generate_reply(
            original_subject=req.original_subject,
            original_body=req.original_body,
            sender_name=req.sender_name,
        )
        return {"status": "ok", "reply": reply_text}
    except Exception:
        logger.exception("Reply generation failed")
        raise HTTPException(status_code=500, detail="Reply generation failed")


@app.post("/internal/nurturing/closing", dependencies=[Depends(_verify_internal_key)])
async def trigger_closing_generation(req: ClosingRequest):
    """Generate a personal closing for a newsletter recipient."""
    try:
        closing = await generate_personal_closing(
            newsletter_subject=req.newsletter_subject,
            newsletter_body=req.newsletter_body,
            first_name=req.first_name,
            org_name=req.org_name,
            deal_notes=req.deal_notes,
        )
        return {"status": "ok", "closing": closing}
    except Exception:
        logger.exception("Closing generation failed")
        raise HTTPException(status_code=500, detail="Closing generation failed")


@app.post("/internal/nurturing/wrap-email", dependencies=[Depends(_verify_internal_key)])
async def trigger_wrap_email(req: WrapEmailRequest):
    """Wrap HTML body in the full email template."""
    html = wrap_in_html_email(
        html_body=req.html_body,
        first_name=req.first_name,
        personal_closing=req.personal_closing,
    )
    return {"status": "ok", "html": html}


@app.get("/internal/nurturing/status", dependencies=[Depends(_verify_internal_key)])
async def get_nurturing_status():
    """Return the current nurturing processing status."""
    return {
        "status": "ok",
        "state": _status["state"],
        "last_run": _status["last_run"],
        "scheduler_active": _scheduler is not None,
        "nurturing_v2_enabled": os.getenv("NURTURING_V2_ENABLED", "false").lower() == "true",
    }


# ── Newsletter Workflow v2 (with HITL) ─────────────────────────

_newsletter_jobs: dict[str, dict] = {}


class NewsletterWorkflowRequest(BaseModel):
    month_name: str | None = None


class NewsletterHitlApprovalRequest(BaseModel):
    job_id: str
    approved: bool
    feedback: str | None = None


@app.post("/internal/nurturing/workflow/start", dependencies=[Depends(_verify_internal_key)])
async def start_newsletter_workflow(req: NewsletterWorkflowRequest):
    """Start the newsletter workflow with double HITL.

    Returns a job_id that can be used to check status and approve/reject.
    """
    import uuid
    job_id = uuid.uuid4().hex[:8]

    _newsletter_jobs[job_id] = {
        "job_id": job_id,
        "state": "running",
        "step": "researcher",
        "slides_draft_url": None,
        "slides_final_url": None,
        "error": None,
        "started_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    async def _run():
        _status["state"] = "newsletter_v2:running"
        _status["last_run"] = datetime.utcnow().isoformat()
        try:
            result = await run_newsletter_workflow(month_name=req.month_name)
            job = _newsletter_jobs[job_id]
            job["state"] = "completed"
            job["slides_draft_url"] = result.get("slides_draft_url")
            job["slides_final_url"] = result.get("slides_final_url")
            job["send_result"] = result.get("send_result")
            job["updated_at"] = datetime.utcnow().isoformat()
            logger.info("[newsletter-v2:%s] Workflow completed", job_id)
        except Exception as exc:
            _newsletter_jobs[job_id]["state"] = "failed"
            _newsletter_jobs[job_id]["error"] = str(exc)
            logger.exception("[newsletter-v2:%s] Workflow failed", job_id)
        finally:
            _status["state"] = "idle"

    asyncio.create_task(_run())

    return JSONResponse(
        status_code=202,
        content={
            "status": "started",
            "job_id": job_id,
            "month_name": req.month_name,
        },
    )


@app.get("/internal/nurturing/workflow/status/{job_id}", dependencies=[Depends(_verify_internal_key)])
async def get_newsletter_workflow_status(job_id: str):
    """Get the status of a newsletter workflow job."""
    job = _newsletter_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No newsletter job found for id '{job_id}'")
    return {"status": "ok", **job}


@app.post("/internal/nurturing/workflow/approve-hitl", dependencies=[Depends(_verify_internal_key)])
async def approve_newsletter_hitl(req: NewsletterHitlApprovalRequest):
    """Approve or reject a HITL checkpoint in the newsletter workflow.

    When approved, triggers the continuation (image generation + final assembly + distribution).
    """
    job = _newsletter_jobs.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No newsletter job found for id '{req.job_id}'")

    if req.approved:
        job["slides_draft_approved"] = True
        job["state"] = "continuing"
        job["updated_at"] = datetime.utcnow().isoformat()
        logger.info("[newsletter-v2:%s] HITL approved via API", req.job_id)

        # Build state for continuation
        state = {
            "month_name": job.get("month_name", ""),
            "job_id": req.job_id,
            "raw_report": job.get("raw_report"),
            "newsletter_content": job.get("newsletter_content"),
            "slides_plan": job.get("slides_plan"),
            "pre_media_evaluation": job.get("pre_media_evaluation"),
            "retry_count": job.get("retry_count", 0),
            "slides_draft_url": job.get("slides_draft_url"),
            "slides_draft_id": job.get("slides_draft_id"),
            "slides_draft_approved": True,
            "generated_images": [],
            "chart_url": job.get("chart_url"),
            "chart_blob_name": job.get("chart_blob_name"),
            "slides_final_url": None,
            "slides_final_id": None,
            "slides_final_artifact": None,
            "slides_final_approved": None,
            "send_result": None,
        }

        # Start continuation in background
        import threading
        thread = threading.Thread(target=_run_continuation_bg, args=(req.job_id, state), daemon=True)
        thread.start()

        return {
            "status": "ok",
            "job_id": req.job_id,
            "approved": True,
            "message": "Workflow continuation started in background (image generation + final assembly)",
        }
    else:
        job["slides_draft_approved"] = False
        job["state"] = "rejected"
        job["feedback"] = req.feedback
        job["updated_at"] = datetime.utcnow().isoformat()
        logger.info("[newsletter-v2:%s] HITL rejected via API", req.job_id)

        return {
            "status": "ok",
            "job_id": req.job_id,
            "approved": False,
            "feedback": req.feedback,
        }


# ── Newsletter Workflow Continuation ───────────────────────────

async def _continue_newsletter_workflow(job_id: str, state: dict) -> dict:
    """Continue newsletter workflow after HITL #1 approval.

    Runs the remaining nodes: image_generator → chart_renderer → slides_assembler → hitl2 → distributor.
    """
    from community_manager.nurturing.workflow_v2 import hitl2_placeholder
    from community_manager.nurturing.nodes.image_generator import image_generator_node
    from community_manager.nurturing.nodes.chart_renderer import chart_renderer_node
    from community_manager.nurturing.nodes.slides_assembler import slides_assembler_node
    from community_manager.nurturing.nodes.distributor import distributor_node

    logger.info("[newsletter-v2:%s] Continuing workflow after HITL #1 approval", job_id)

    try:
        # Step 1: Generate images
        updates = await image_generator_node(state)
        state.update(updates)
        logger.info("[newsletter-v2:%s] Image generator completed", job_id)

        # Step 2: Render chart
        updates = await chart_renderer_node(state)
        state.update(updates)
        logger.info("[newsletter-v2:%s] Chart renderer completed", job_id)

        # Step 3: Assemble final slides
        updates = await slides_assembler_node(state)
        state.update(updates)
        logger.info("[newsletter-v2:%s] Slides assembler completed", job_id)

        # Step 4: HITL #2 (auto-approve placeholder)
        updates = hitl2_placeholder(state)
        state.update(updates)
        logger.info("[newsletter-v2:%s] HITL #2 passed", job_id)

        # Step 5: Distribute
        updates = await distributor_node(state)
        state.update(updates)
        logger.info("[newsletter-v2:%s] Distributor completed", job_id)

        return state

    except Exception:
        logger.exception("[newsletter-v2:%s] Workflow continuation failed", job_id)
        raise


def _run_continuation_bg(job_id: str, state: dict):
    """Run continuation in a background thread."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_continue_newsletter_workflow(job_id, state))
        job = _newsletter_jobs.get(job_id)
        if job:
            job["state"] = "completed"
            job["slides_final_url"] = result.get("slides_final_url")
            job["send_result"] = result.get("send_result")
            job["updated_at"] = datetime.utcnow().isoformat()
        logger.info("[newsletter-v2:%s] Continuation completed successfully", job_id)
    except Exception:
        logger.exception("[newsletter-v2:%s] Continuation failed", job_id)
        job = _newsletter_jobs.get(job_id)
        if job:
            job["state"] = "failed"
            job["error"] = str(sys.exc_info()[1])
            job["updated_at"] = datetime.utcnow().isoformat()
    finally:
        loop.close()


# ── Newsletter Review Links (like CM agent) ────────────────────

_newsletter_review_tokens: dict[str, dict] = {}


def _generate_review_token(job_id: str) -> str:
    """Generate a unique review token for a newsletter job."""
    import uuid
    token = uuid.uuid4().hex[:16]
    _newsletter_review_tokens[token] = {
        "job_id": job_id,
        "created_at": datetime.utcnow().isoformat(),
    }
    return token


def _html_page(title: str, message: str, success: bool = False) -> str:
    """Generate a simple HTML response page."""
    accent = "#1f7a4d" if success else "#1b4f7c"
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: 'Open Sans', Arial, sans-serif; background: #f4f7fb; color: #102033; margin: 0; }}
    main {{ max-width: 640px; margin: 48px auto; background: #fff; border-radius: 16px; padding: 32px; box-shadow: 0 12px 30px rgba(16,32,51,.12); }}
    h1 {{ margin: 0 0 16px; color: {accent}; }}
    p {{ line-height: 1.6; margin: 0; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p>{message}</p>
  </main>
</body>
</html>"""


@app.get("/api/nurturing/review/{review_token}/approve")
async def newsletter_review_approve(review_token: str):
    """Approve a newsletter draft via link (no auth required, token-based)."""
    from fastapi.responses import HTMLResponse

    token_data = _newsletter_review_tokens.get(review_token)
    if not token_data:
        return HTMLResponse(_html_page("Link inválido", "No encontramos un newsletter asociado a este link."), status_code=404)

    job_id = token_data["job_id"]
    job = _newsletter_jobs.get(job_id)
    if not job:
        return HTMLResponse(_html_page("Link inválido", "El newsletter asociado a este link ya no existe."), status_code=404)

    if job.get("state") == "completed":
        return HTMLResponse(_html_page("Newsletter ya enviado", "Este newsletter ya fue completado y enviado."))

    # Mark as approved
    job["slides_draft_approved"] = True
    job["state"] = "continuing"
    job["updated_at"] = datetime.utcnow().isoformat()
    logger.info("[newsletter-v2:%s] Approved via review link", job_id)

    # Build state from job for continuation
    state = {
        "month_name": job.get("month_name", ""),
        "job_id": job_id,
        "raw_report": job.get("raw_report"),
        "newsletter_content": job.get("newsletter_content"),
        "slides_plan": job.get("slides_plan"),
        "pre_media_evaluation": job.get("pre_media_evaluation"),
        "retry_count": job.get("retry_count", 0),
        "slides_draft_url": job.get("slides_draft_url"),
        "slides_draft_id": job.get("slides_draft_id"),
        "slides_draft_approved": True,
        "generated_images": [],
        "chart_url": job.get("chart_url"),
        "chart_blob_name": job.get("chart_blob_name"),
        "slides_final_url": None,
        "slides_final_id": None,
        "slides_final_artifact": None,
        "slides_final_approved": None,
        "send_result": None,
    }

    # Start continuation in background
    import threading
    thread = threading.Thread(target=_run_continuation_bg, args=(job_id, state), daemon=True)
    thread.start()

    return HTMLResponse(_html_page(
        "Newsletter aprobado",
        "Aprobaste el newsletter. Las imágenes se están generando y recibirás otro mail para la aprobación final.",
        success=True,
    ))


@app.get("/api/nurturing/review/{review_token}/reject")
async def newsletter_review_reject_form(review_token: str):
    """Show rejection form for newsletter draft."""
    from fastapi.responses import HTMLResponse

    token_data = _newsletter_review_tokens.get(review_token)
    if not token_data:
        return HTMLResponse(_html_page("Link inválido", "No encontramos un newsletter asociado a este link."), status_code=404)

    job_id = token_data["job_id"]
    job = _newsletter_jobs.get(job_id)
    if not job:
        return HTMLResponse(_html_page("Link inválido", "El newsletter asociado a este link ya no existe."), status_code=404)

    if job.get("state") == "completed":
        return HTMLResponse(_html_page("Newsletter ya enviado", "Este newsletter ya fue completado y enviado."))

    subject = job.get("subject", "AI Radar")
    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Solicitar cambios</title>
  <style>
    body {{ font-family: 'Open Sans', Arial, sans-serif; background: #f4f7fb; color: #102033; margin: 0; }}
    main {{ max-width: 640px; margin: 48px auto; background: #fff; border-radius: 16px; padding: 32px; box-shadow: 0 12px 30px rgba(16,32,51,.12); }}
    h1 {{ margin: 0 0 12px; color: #8f2d2d; }}
    p {{ line-height: 1.6; margin: 0 0 14px; }}
    label {{ display: block; font-weight: bold; margin-bottom: 6px; }}
    textarea {{ width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #ccc; border-radius: 8px; font-size: 14px; resize: vertical; min-height: 100px; font-family: inherit; }}
    .hint {{ font-size: 13px; color: #666; margin-top: 6px; }}
    .actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }}
    .btn {{ padding: 10px 20px; border-radius: 999px; font-weight: 700; cursor: pointer; border: none; font-size: 14px; }}
    .btn-reject {{ background: #8f2d2d; color: #fff; }}
    .btn-revise {{ background: #1b4f7c; color: #fff; }}
    .btn:hover {{ opacity: .88; }}
  </style>
</head>
<body>
  <main>
    <h1>Solicitar cambios</h1>
    <p>Newsletter: <b>{subject}</b></p>
    <form method="POST">
      <label for="feedback">Feedback (opcional):</label>
      <textarea id="feedback" name="feedback" placeholder="Escribí los cambios que querés. Si este campo tiene texto, se tomará como pedido de revisión..."></textarea>
      <p class="hint">Si escribís feedback, se pedirá revisión y recibirás una nueva versión por mail. Para rechazarlo definitivamente, dejá este campo vacío.</p>
      <div class="actions">
        <button type="submit" name="intent" value="revise" class="btn btn-revise">Pedir cambios y reenviar por mail</button>
        <button type="submit" name="intent" value="reject" class="btn btn-reject">Rechazar definitivamente</button>
      </div>
    </form>
  </main>
</body>
</html>"""

    return HTMLResponse(html)


@app.post("/api/nurturing/review/{review_token}/reject")
async def newsletter_review_reject_submit(review_token: str, feedback: str = "", intent: str = ""):
    """Submit rejection with optional feedback."""
    from fastapi.responses import HTMLResponse
    from starlette.requests import Request

    token_data = _newsletter_review_tokens.get(review_token)
    if not token_data:
        return HTMLResponse(_html_page("Link inválido", "No encontramos un newsletter asociado a este link."), status_code=404)

    job_id = token_data["job_id"]
    job = _newsletter_jobs.get(job_id)
    if not job:
        return HTMLResponse(_html_page("Link inválido", "El newsletter asociado a este link ya no existe."), status_code=404)

    if job.get("state") == "completed":
        return HTMLResponse(_html_page("Newsletter ya enviado", "Este newsletter ya fue completado y enviado."))

    trimmed_feedback = feedback.strip()

    if trimmed_feedback:
        # Revision requested
        job["slides_draft_approved"] = False
        job["feedback"] = trimmed_feedback
        job["updated_at"] = datetime.utcnow().isoformat()
        logger.info("[newsletter-v2:%s] Revision requested via review link: %s", job_id, trimmed_feedback[:100])

        return HTMLResponse(_html_page(
            "Revisión en cola",
            f"Tu feedback fue guardado. Recibirás una nueva versión por mail cuando esté lista.",
            success=True,
        ))
    else:
        # Plain reject
        job["slides_draft_approved"] = False
        job["state"] = "rejected"
        job["updated_at"] = datetime.utcnow().isoformat()
        logger.info("[newsletter-v2:%s] Rejected via review link", job_id)

        return HTMLResponse(_html_page(
            "Newsletter rechazado",
            "El newsletter fue rechazado y no se enviará.",
        ))


@app.get("/internal/community/draft-jobs/{job_id}", dependencies=[Depends(_verify_internal_key)])
async def get_community_draft_job_status(job_id: str):
    """Return the current state of an async reviewer-gated draft generation job."""
    job = _community_draft_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No community draft job found for id '{job_id}'")

    return {"status": "ok", **job}


@app.post("/internal/community/generate-draft", dependencies=[Depends(_verify_internal_key)])
async def trigger_community_draft_generation(req: CommunityDraftGenerateRequest):
    """Generate a social media draft that must be reviewed before publication."""
    try:
        content_type = _require_supported_community_content_type(req.content_type)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    try:
        publication_history = req.publication_history or await _load_publication_history(limit=8)
        reviewer_memory = (req.reviewer_memory or "").strip()
        if not reviewer_memory and _dotnet:
            reviewer_memory = await _dotnet.get_community_reviewer_memory()
        draft = await generate_reviewable_draft(
            content_type,
            publication_history=publication_history,
            reviewer_memory=reviewer_memory,
            requested_topic=(req.topic or "").strip(),
            requested_angle=(req.angle or "").strip(),
            requested_objective=(req.objective or "").strip(),
            requested_num_images=req.num_images,
            is_on_demand=True,
        )
        return {"status": "ok", **draft}
    except Exception:
        logger.exception("Community draft generation failed")
        raise HTTPException(status_code=500, detail="Community draft generation failed")


@app.post("/internal/community/generate-draft-now", dependencies=[Depends(_verify_internal_key)])
async def trigger_community_draft_generation_now(req: CommunityPublishNowRequest):
    """Queue a reviewer-gated draft generation in the background and return immediately."""
    try:
        content_type = _require_supported_community_content_type(req.content_type)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    import uuid
    job_id = uuid.uuid4().hex[:8]
    topic = _normalize_optional_text(req.topic)
    angle = _normalize_optional_text(req.angle)
    objective = _normalize_optional_text(req.objective)
    num_images = req.num_images

    _create_community_draft_job(
        job_id,
        content_type=content_type,
        topic=topic,
        angle=angle,
        objective=objective,
    )

    async def _run():
        _status["state"] = f"drafting:{content_type}"
        _status["last_run"] = datetime.utcnow().isoformat()
        _update_community_draft_job(job_id, state="running", step="generating")
        logger.info("[generate-draft-now:%s] Starting reviewer-gated draft generation for %s", job_id, content_type)
        try:
            saved = await _generate_and_persist_review_draft(
                content_type,
                topic=topic,
                angle=angle,
                objective=objective,
                num_images=num_images,
                is_on_demand=True,
            )
            _update_community_draft_job(
                job_id,
                state="completed",
                step="saved",
                draft_id=saved.get("draft_id"),
                draft_status=saved.get("status"),
                review_subject=saved.get("review_subject"),
                review_token=saved.get("review_token"),
                failure_reason=saved.get("failure_reason"),
            )
            logger.info(
                "[generate-draft-now:%s] Draft saved with status=%s draft_id=%s",
                job_id,
                saved.get("status"),
                saved.get("draft_id"),
            )
        except Exception as exc:
            _update_community_draft_job(job_id, state="failed", step="error", error=str(exc))
            logger.exception("[generate-draft-now:%s] Reviewer-gated draft generation failed for %s", job_id, content_type)
        finally:
            _status["state"] = "idle"

    asyncio.create_task(_run())

    return JSONResponse(
        status_code=202,
        content={
            "status": "started",
            "job_id": job_id,
            "content_type": content_type,
            "topic": topic,
            "angle": angle,
            "objective": objective,
        },
    )


@app.post("/internal/community/revise-draft", dependencies=[Depends(_verify_internal_key)])
async def trigger_community_draft_revision(req: CommunityDraftRevisionRequest):
    """Revise a saved social draft using reviewer feedback."""
    try:
        draft = await revise_reviewable_draft(
            strategy_json=req.strategy_json,
            copy_json=req.copy_json,
            design_json=req.design_json,
            reviewer_feedback=req.reviewer_feedback,
            revision_target=req.revision_target,
            reviewer_memory=req.reviewer_memory,
        )
        return {"status": "ok", **draft}
    except Exception:
        logger.exception("Community draft revision failed")
        raise HTTPException(status_code=500, detail="Community draft revision failed")


@app.post("/internal/community/materialize-draft-media", dependencies=[Depends(_verify_internal_key)])
async def trigger_community_draft_media_materialization(req: CommunityDraftMaterializeRequest):
    """Generate the expensive final media for an already approved pre-media draft."""
    try:
        draft = await materialize_reviewable_draft_media(
            strategy_json=req.strategy_json,
            copy_json=req.copy_json,
            design_json=req.design_json,
        )
        return {"status": "ok", **draft}
    except Exception:
        logger.exception("Community draft media materialization failed")
        raise HTTPException(status_code=500, detail="Community draft media materialization failed")


@app.post("/internal/community/publish-draft", dependencies=[Depends(_verify_internal_key)])
async def trigger_community_draft_publish(req: CommunityDraftPublishRequest):
    """Publish a previously approved social draft."""
    try:
        result = await publish_reviewable_draft(
            strategy_json=req.strategy_json,
            copy_json=req.copy_json,
            design_json=req.design_json,
        )
        return {"status": "ok", **result}
    except Exception:
        logger.exception("Community draft publication failed")
        raise HTTPException(status_code=500, detail="Community draft publication failed")


@app.post("/internal/community/delete-draft-media", dependencies=[Depends(_verify_internal_key)])
async def trigger_community_draft_media_cleanup(req: CommunityDraftMediaCleanupRequest):
    """Delete remote blob media associated with an unpublished community draft."""
    try:
        design = DesignerOutput.model_validate_json(req.design_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid design_json: {exc}") from exc

    try:
        deleted_blob_count = await cleanup_remote_media(design)
        return {"status": "ok", "deleted_blob_count": deleted_blob_count}
    except Exception:
        logger.exception("Community draft media cleanup failed")
        raise HTTPException(status_code=500, detail="Community draft media cleanup failed")


@app.post("/internal/community/publish-now", dependencies=[Depends(_verify_internal_key)])
async def trigger_community_publish_now(req: CommunityPublishNowRequest):
    """Run the full generation + publish pipeline directly without a review step.

    Returns 202 Accepted immediately — the workflow runs in the background.
    Check agent logs for the result.
    """
    try:
        content_type = _require_supported_community_content_type(req.content_type)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    import uuid
    job_id = uuid.uuid4().hex[:8]

    async def _run():
        _status["state"] = f"publishing_direct:{content_type}"
        _status["last_run"] = datetime.utcnow().isoformat()
        logger.info("[publish-now:%s] Starting direct publish for %s", job_id, content_type)
        try:
            reviewer_memory = await _dotnet.get_community_reviewer_memory() if _dotnet else ""
            publication_history = await _load_publication_history(limit=8)
            result = await run_content_workflow(
                content_type,
                skip_llm_evaluation=True,
                publication_history=publication_history,
                reviewer_memory=reviewer_memory,
                requested_topic=(req.topic or "").strip(),
                requested_angle=(req.angle or "").strip(),
                requested_objective=(req.objective or "").strip(),
                requested_num_images=req.num_images,
                is_on_demand=True,
            )
            publish_result = result.get("publish_result")
            if publish_result is None:
                logger.error("[publish-now:%s] Workflow finished but produced no publish_result", job_id)
            else:
                successes = [r for r in publish_result.results if r.success]
                failures = [r for r in publish_result.results if not r.success]
                logger.info(
                    "[publish-now:%s] Done — all_success=%s successes=%d failures=%d",
                    job_id, publish_result.all_success, len(successes), len(failures),
                )
                for r in failures:
                    logger.warning("[publish-now:%s] Platform %s failed: %s", job_id, r.platform, r.error)
        except Exception:
            logger.exception("[publish-now:%s] Direct publish workflow %s failed", job_id, content_type)
        finally:
            _status["state"] = "idle"

    import asyncio
    asyncio.create_task(_run())

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=202,
        content={
            "status": "started",
            "job_id": job_id,
            "content_type": content_type,
            "topic": (req.topic or "").strip() or None,
            "angle": (req.angle or "").strip() or None,
            "objective": (req.objective or "").strip() or None,
        },
    )


# ── CLI entry point ───────────────────────────────────────────

def main():
    """Parse CLI args and start the agent."""
    global _start_scheduler

    parser = argparse.ArgumentParser(description="Novit Community Manager Agent")
    parser.add_argument(
        "--webhooks-only",
        action="store_true",
        help="Start the API server without the scheduler",
    )
    parser.add_argument(
        "--once",
        metavar="CONTENT_TYPE",
        help="Run a single CM workflow (currently only image_post) and exit",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind to (default: 8000)"
    )
    args = parser.parse_args()

    if args.once:
        # Run a single workflow and exit
        asyncio.run(_run_once(args.once))
        return

    if args.webhooks_only:
        _start_scheduler = False

    import uvicorn

    uvicorn.run(
        "community_manager.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


async def _run_once(content_type: str) -> None:
    """Generate a single reviewable draft and exit."""
    content_type = _require_supported_community_content_type(content_type)
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    logger.info("Running single CM draft workflow: %s", content_type)
    result = await generate_reviewable_draft(content_type)
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()

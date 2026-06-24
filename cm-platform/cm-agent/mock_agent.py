"""
Mock CM Agent -- Standalone FastAPI server that mimics the real Python agent.
Returns realistic fake responses for all endpoints WITHOUT calling any LLM or AI service.
Run: python mock_agent.py
"""

import uuid
import asyncio
import random
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock CM Agent")

INTERNAL_API_KEY = "mock-dev-key"

# In-memory job store
jobs: dict[str, dict] = {}


class WebhookMessage(BaseModel):
    sender_id: str
    text: str
    platform: str
    message_id: Optional[str] = None
    sender_name: Optional[str] = None
    reply_target_id: Optional[str] = None
    reply_target_type: Optional[str] = None
    post_context_id: Optional[str] = None
    post_context_text: Optional[str] = None


class ReviseRequest(BaseModel):
    current_subject: str
    current_body: str
    reviewer_feedback: str


class ReplyRequest(BaseModel):
    original_subject: str
    original_body: str
    sender_name: str


class ClosingRequest(BaseModel):
    newsletter_subject: str
    newsletter_body: Optional[str] = None
    first_name: Optional[str] = None
    org_name: Optional[str] = None
    deal_notes: list[str] = []


class EmailWrapRequest(BaseModel):
    html_body: str
    first_name: Optional[str] = None
    personal_closing: Optional[str] = None


class GenerateDraftRequest(BaseModel):
    content_type: str = "image_post"
    reviewer_memory: str = ""
    publication_history: list[str] = []
    topic: Optional[str] = None
    angle: Optional[str] = None
    objective: Optional[str] = None
    num_images: Optional[int] = None


class ReviseDraftRequest(BaseModel):
    strategy_json: str
    copy_json: str
    design_json: str
    reviewer_feedback: str
    revision_target: str
    reviewer_memory: str


class PublishNowRequest(BaseModel):
    content_type: str = "image_post"
    topic: Optional[str] = None
    angle: Optional[str] = None
    objective: Optional[str] = None


TOPICS = [
    "Productividad con IA",
    "Tendencias 2026",
    "Automatización de procesos",
    "Customer Experience",
    "Data-Driven Marketing",
]
ANGLES = ["Educativo", "Inspiracional", "Promocional", "Entretenimiento", "Caso de éxito"]
OBJECTIVES = ["Engagement", "Tráfico", "Brand Awareness", "Leads", "Ventas"]
PLATFORMS = ["instagram", "facebook", "twitter", "linkedin", "tiktok"]
HASHTAGS = ["#IA", "#Innovacion", "#MarketingDigital", "#Automatizacion", "#CX"]


def verify_key(x_internal_key: Optional[str] = Header(None)):
    if x_internal_key and x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(403, "Invalid internal key")


def pick(items: list[str]) -> str:
    return random.choice(items)


def make_draft(content_type: str, topic: Optional[str] = None,
               angle: Optional[str] = None, objective: Optional[str] = None,
               draft_status: str = "pending_review",
               review_stage: str = "final") -> dict:
    topic = topic or pick(TOPICS)
    angle = angle or pick(ANGLES)
    objective = objective or pick(OBJECTIVES)
    caption = (
        f"Descubrí cómo {topic.lower()} puede transformar tu estrategia digital. "
        f"En este post exploramos un enfoque {angle.lower()} para lograr {objective.lower()}.\n\n"
        "¿Qué opinas? Dejanos tu comentario."
    )
    hashtags = list(set(random.sample(HASHTAGS, k=min(3, len(HASHTAGS)))))

    return {
        "content_type": content_type,
        "topic": topic,
        "angle": angle,
        "objective": objective,
        "caption": caption,
        "hashtags": hashtags,
        "alt_text": f"Imagen ilustrativa sobre {topic}",
        "strategy_json": f'{{"topic":"{topic}","angle":"{angle}","objective":"{objective}"}}',
        "copy_json": f'{{"caption":"{caption}","hashtags":{hashtags},"tone":"profesional"}}',
        "design_json": f'{{"media_type":"{content_type}","num_images":1,"style":"minimal"}}',
        "evaluation_json": '{"score":8,"feedback":"Cumple criterios","approved":true}',
        "media_urls": ["https://placehold.co/600x600?text=CM+Mock"] if content_type != "carousel"
        else [f"https://placehold.co/600x600?text=Slide+{i}" for i in range(1, 4)],
        "media_blob_names": [f"mock-blob-{uuid.uuid4().hex}.jpg"],
        "video_duration_seconds": 30 if content_type == "reel" else 0,
        "draft_status": draft_status,
        "review_stage": review_stage,
        "failure_reason": None,
        "retry_count": 0,
    }


@app.get("/health")
def health():
    return {"status": "ok", "mode": "mock"}


@app.post("/internal/webhook/message")
def webhook_message(body: WebhookMessage, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return {"reply": f"¡Gracias por tu mensaje, {body.sender_name or 'usuario'}! Te responderemos a la brevedad."}


@app.post("/internal/nurturing/generate-sync")
def nurturing_generate_sync(x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return {
        "subject": f"Newsletter CM - {datetime.now(timezone.utc).strftime('%B %Y')}",
        "body": "<h1>Novidades de CM Platform</h1><p>En esta edición: tendencias de IA.</p>",
        "report_title": f"Reporte {datetime.now(timezone.utc).strftime('%B %Y')}",
        "executive_summary": "Resumen ejecutivo generado por el asistente CM.",
        "artifact_json": None,
    }


@app.post("/internal/nurturing/revise")
def nurturing_revise(body: ReviseRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return {
        "subject": f"[Revisado] {body.current_subject}",
        "body": body.current_body,
        "executive_summary": f"Revisado con base en: {body.reviewer_feedback}",
    }


@app.post("/internal/nurturing/reply")
def nurturing_reply(body: ReplyRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return {"reply": f"Hola {body.sender_name},\n\nGracias por tu interés. [Respuesta generada]\n\nEquipo CM"}


@app.post("/internal/nurturing/closing")
def nurturing_closing(body: ClosingRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    name = body.first_name or "usuario"
    return {"closing": f"¡{name}, gracias por leer! Estamos acá para ayudarte."}


@app.post("/internal/nurturing/wrap-email")
def wrap_email(body: EmailWrapRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    closing = body.personal_closing or "Saludos,<br/>Equipo CM"
    wrapped = (
        f'<div style="font-family:Arial;max-width:600px;margin:auto">'
        f'<div style="background:#1a73e8;color:white;padding:20px;text-align:center">'
        f'<h1>CM Platform</h1></div>'
        f'<div style="padding:20px">{body.html_body}</div>'
        f'<div style="padding:20px;color:#666;font-size:12px">{closing}</div></div>'
    )
    return {"wrapped_html": wrapped}


@app.get("/internal/nurturing/status")
def nurturing_status(x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return {
        "state": "running",
        "last_run": datetime.now(timezone.utc).isoformat(),
        "scheduler_active": True,
        "nurturing_v2_enabled": False,
    }


@app.post("/internal/community/generate-draft")
def generate_draft(body: GenerateDraftRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return make_draft(body.content_type, body.topic, body.angle, body.objective)


@app.post("/internal/community/generate-draft-now")
def generate_draft_now(body: GenerateDraftRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "job_id": job_id,
        "state": "processing",
        "step": "strategist",
        "content_type": body.content_type,
        "topic": body.topic or pick(TOPICS),
        "angle": body.angle or pick(ANGLES),
        "objective": body.objective or pick(OBJECTIVES),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "job_id": job_id,
        "status": "accepted",
        "content_type": body.content_type,
        "topic": jobs[job_id]["topic"],
        "angle": jobs[job_id]["angle"],
        "objective": jobs[job_id]["objective"],
    }


@app.get("/internal/community/draft-jobs/{job_id}")
def get_draft_job(job_id: str, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    if job_id not in jobs:
        draft = make_draft("image_post")
        return {
            "found": True,
            "job_id": job_id,
            "state": "completed",
            "step": "evaluator",
            "content_type": "image_post",
            "topic": pick(TOPICS),
            "angle": pick(ANGLES),
            "objective": pick(OBJECTIVES),
            "draft_id": uuid.uuid4().hex,
            "draft_status": "pending_review",
            "review_subject": "Mock Draft - Revision Needed",
            "review_token": uuid.uuid4().hex,
            "failure_reason": None,
            "error": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    job = jobs[job_id]
    job["state"] = "completed"
    job["step"] = "evaluator"
    return {
        "found": True,
        "job_id": job_id,
        "state": job["state"],
        "step": job["step"],
        "content_type": job["content_type"],
        "topic": job["topic"],
        "angle": job["angle"],
        "objective": job["objective"],
        "draft_id": uuid.uuid4().hex,
        "draft_status": "pending_review",
        "review_subject": "Mock Draft - Revision Needed",
        "review_token": uuid.uuid4().hex,
        "failure_reason": None,
        "error": None,
        "started_at": job["started_at"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/internal/community/revise-draft")
def revise_draft(body: ReviseDraftRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return make_draft("image_post", draft_status="pending_review",
                      review_stage=body.revision_target)


@app.post("/internal/community/materialize-draft-media")
def materialize_draft_media(body: ReviseDraftRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return make_draft("image_post", draft_status="approved", review_stage="final")


@app.post("/internal/community/publish-draft")
def publish_draft(body: ReviseDraftRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    platforms = random.sample(PLATFORMS, k=random.randint(1, 2))
    return {
        "results": [
            {
                "platform": p,
                "success": True,
                "post_id": uuid.uuid4().hex[:12],
                "error": None,
                "permalink": f"https://{p}.com/p/{uuid.uuid4().hex[:8]}",
            }
            for p in platforms
        ],
        "published_at": datetime.now(timezone.utc).isoformat(),
        "all_success": True,
    }


@app.post("/internal/community/delete-draft-media")
def delete_draft_media(x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return {"success": True}


@app.post("/internal/community/publish-now")
def publish_now(body: PublishNowRequest, x_internal_key: Optional[str] = Header(None)):
    verify_key(x_internal_key)
    return {"job_id": uuid.uuid4().hex[:12]}


if __name__ == "__main__":
    import uvicorn

    print("Mock CM Agent starting on http://0.0.0.0:8000")
    print("No AI services required -- returning fake responses.")
    uvicorn.run(app, host="0.0.0.0", port=8000)

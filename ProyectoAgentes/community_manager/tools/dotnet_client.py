"""HTTP client for calling .NET backend internal endpoints.

This is the bridge between the Python agent and the .NET backend
for operations that .NET owns: Pipedrive, Email (SMTP/IMAP), DB.

All calls go to ``http://backend:5000/api/internal/*`` inside the
Docker network, authenticated with the shared ``INTERNAL_API_KEY``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from community_manager.config.settings import get_settings
from community_manager.models.schemas import DealNote, NurturingRecipient

logger = logging.getLogger(__name__)


class DotNetClient:
    """Async client that calls .NET internal API endpoints (Now Mocked for independence).
    
    All original HTTP calls have been commented out to allow running the Python agent
    independently in a new repository. You can uncomment them and adjust 'base_url'
    once you provide a backend service that implements these endpoints.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.dotnet_base_url.rstrip("/")
        self._api_key = settings.internal_api_key
        # La inicialización del cliente HTTP se mantiene comentada para evitar problemas de conexión/timeout innecesarios.
        # self._http = httpx.AsyncClient(
        #     base_url=f"{self.base_url}/api/internal",
        #     timeout=120.0,
        #     headers={"X-Internal-Key": self._api_key},
        # )

    # ── Nurturing: recipients ──────────────────────────────────

    async def get_nurturing_recipients(self) -> list[NurturingRecipient]:
        """Get the list of Pipedrive contacts in the nurturing stage."""
        logger.info("MOCK: get_nurturing_recipients llamado")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get("/nurturing/recipients")
        # resp.raise_for_status()
        # data = resp.json()
        # items = data.get("recipients", []) if isinstance(data, dict) else data
        # return [NurturingRecipient(**recipient) for recipient in items]
        
        # Simulación de un destinatario para pruebas
        return [
            NurturingRecipient(
                deal_id=101,
                deal_title="Propuesta IA - Empresa Ejemplo S.A.",
                contact_name="Nicolás Piccardo",
                first_name="Nicolás",
                email="nicolas.piccardo@example.com",
                org_name="Empresa Ejemplo"
            )
        ]

    # ── Nurturing: newsletter DB operations ────────────────────

    async def get_newsletter(self, month_key: str) -> dict[str, Any] | None:
        """Get a newsletter/report entry from DB by month key."""
        logger.info(f"MOCK: get_newsletter llamado para {month_key}")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get(f"/nurturing/newsletter/{month_key}")
        # if resp.status_code == 404:
        #     return None
        # resp.raise_for_status()
        # return resp.json()
        
        # Simula que no hay un boletín previo guardado para este mes (retorna None para forzar generación)
        # o puedes retornar un diccionario mock si quieres probar la edición.
        return None

    async def save_newsletter(
        self,
        subject: str,
        body: str,
        month_key: str,
        scheduled_send_date: str | None = None,
        report_title: str | None = None,
        executive_summary: str | None = None,
        artifact_json: str | None = None,
    ) -> dict[str, Any]:
        """Save or update the newsletter in DB."""
        logger.info(f"MOCK: save_newsletter llamado para {month_key}")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.post("/nurturing/newsletter", json={
        #     "subject": subject,
        #     "body": body,
        #     "monthKey": month_key,
        #     "scheduledSendDate": scheduled_send_date,
        #     "reportTitle": report_title,
        #     "executiveSummary": executive_summary,
        #     "artifactJson": artifact_json,
        # })
        # resp.raise_for_status()
        # return resp.json()
        
        return {
            "status": "saved",
            "month_key": month_key,
            "subject": subject,
            "version": 1
        }

    async def mark_newsletter_sent(self, month_key: str) -> None:
        """Mark a newsletter as sent in the DB."""
        logger.info(f"MOCK: mark_newsletter_sent llamado para {month_key}")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.post(f"/nurturing/newsletter/{month_key}/mark-sent")
        # resp.raise_for_status()
        pass

    async def get_previous_conclusions(self, count: int = 3) -> list[dict[str, Any]]:
        """Get conclusions from the last N newsletters for contextual awareness."""
        logger.info(f"MOCK: get_previous_conclusions llamado (count={count})")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get(f"/nurturing/conclusions/last?count={count}")
        # resp.raise_for_status()
        # return resp.json()
        
        return [
            {
                "month_key": "2026-05",
                "report_title": "AI Radar Mayo 2026",
                "conclusions": "El mes cerró con un incremento significativo en la adopción de agentes de atención médica impulsados por IA."
            }
        ]

    # ── Community Manager draft approvals ────────────────────

    async def get_community_reviewer_memory(self) -> str:
        """Get compressed lessons learned from recent reviewer feedback."""
        logger.info("MOCK: get_community_reviewer_memory llamado")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get("/community/reviewer-memory")
        # resp.raise_for_status()
        # data = resp.json()
        # return data.get("memory", "")
        
        return "El revisor prefiere un tono muy profesional. Evitar exclamaciones excesivas y mantener el foco técnico en las soluciones."

    async def get_recent_community_publication_history(self, limit: int = 5) -> list[str]:
        """Get brief summaries of the latest community publications to avoid repetitive topics."""
        logger.info(f"MOCK: get_recent_community_publication_history llamado (limit={limit})")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get("/community/publication-history", params={"limit": limit})
        # resp.raise_for_status()
        # data = resp.json()
        # return data.get("publications", [])
        
        return [
            "2026-06-10 | image_post | published | Tendencias en Automatización de Procesos | Enfoque de eficiencia",
            "2026-06-05 | video_post | published | Presentación de Agente Multimodal | Caso de éxito industrial"
        ]

    async def get_recent_published_image_references(self, limit: int = 2) -> list[dict[str, Any]]:
        """Get the latest published image posts with slide URLs/prompts for visual benchmarking."""
        logger.info(f"MOCK: get_recent_published_image_references llamado (limit={limit})")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get("/community/published-image-references", params={"limit": limit})
        # resp.raise_for_status()
        # data = resp.json()
        # return data.get("references", [])
        
        return []

    async def create_community_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Persist a social publication draft and send it to reviewers."""
        logger.info("MOCK: create_community_draft llamado")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.post("/community/drafts", json=draft)
        # resp.raise_for_status()
        # return resp.json()
        
        import uuid
        draft_id = str(uuid.uuid4())
        return {
            "status": "queued",
            "draft_id": draft_id,
            "review_token": "mock_review_token_12345",
            "review_subject": f"[REVISIÓN] Propuesta de Posteo: {draft.get('topic', 'Sin tema')}"
        }

    async def generate_dm_reply(
        self,
        *,
        platform: str,
        sender_id: str,
        sender_name: str,
        text: str,
        locale: str = "es-AR",
    ) -> str | None:
        """Resolve a social-media DM using the same backend chat logic as the web assistant."""
        logger.info(f"MOCK: generate_dm_reply llamado para {sender_name} ({platform})")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.post("/chat/dm-reply", json={
        #     "platform": platform,
        #     "senderId": sender_id,
        #     "senderName": sender_name,
        #     "text": text,
        #     "locale": locale,
        # })
        # resp.raise_for_status()
        # return resp.json().get("reply")
        
        return f"Hola {sender_name}, gracias por escribirnos. Esto es una respuesta automática de prueba del agente de IA."

    # ── Email operations (via .NET MailKit) ─────────────────────

    async def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_body: str,
    ) -> bool:
        """Send a single email via the .NET SMTP service."""
        logger.info(f"MOCK: send_email llamado para {to_email}")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.post("/email/send", json={
        #     "to": to_email,
        #     "subject": subject,
        #     "htmlBody": html_body,
        #     "firstName": to_name,
        # })
        # return resp.is_success
        
        return True

    async def send_reply(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        body: str,
        in_reply_to_message_id: str,
        references: str,
    ) -> bool:
        """Send a reply in an existing email thread."""
        logger.info(f"MOCK: send_reply llamado para {to_email}")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.post("/email/reply", json={
        #     "to": to_email,
        #     "subject": subject,
        #     "body": body,
        #     "inReplyTo": in_reply_to_message_id or references,
        #     "messageId": references,
        # })
        # return resp.is_success
        
        return True

    async def get_unanswered_replies(self) -> list[dict[str, Any]]:
        """Check IMAP for unanswered email replies."""
        logger.info("MOCK: get_unanswered_replies llamado")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get("/email/unanswered")
        # resp.raise_for_status()
        # data = resp.json()
        # return data.get("replies", []) if isinstance(data, dict) else data
        
        return []

    # ── Pipedrive operations ───────────────────────────────────

    async def get_deal_notes(self, deal_id: int) -> list[DealNote]:
        """Get notes attached to a Pipedrive deal."""
        logger.info(f"MOCK: get_deal_notes llamado para deal {deal_id}")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.get(f"/pipedrive/deals/{deal_id}/notes")
        # resp.raise_for_status()
        # data = resp.json()
        # return [DealNote(**note) for note in data.get("notes", [])]
        
        return []

    async def add_deal_note(self, deal_id: int, content: str) -> None:
        """Add a note to a Pipedrive deal."""
        logger.info(f"MOCK: add_deal_note llamado para deal {deal_id}")
        # LLAMADA REAL COMENTADA:
        # resp = await self._http.post(f"/pipedrive/deals/{deal_id}/notes", json={
        #     "content": content,
        # })
        # resp.raise_for_status()
        pass

    # ── Lifecycle ──────────────────────────────────────────────

    async def close(self) -> None:
        logger.info("MOCK: close llamado")
        # LLAMADA REAL COMENTADA:
        # await self._http.aclose()
        pass

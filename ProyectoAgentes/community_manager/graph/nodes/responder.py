"""Responder — handles incoming messages from social media.

ADAPTED for the fused architecture: instead of reading from a local
webhook message queue, messages are pushed by the .NET backend via
the internal FastAPI endpoint POST /internal/webhook/message.

The scheduler still calls process_pending_messages() periodically,
but now it drains an in-process asyncio.Queue that is fed by the
FastAPI route (see main.py).
"""

from __future__ import annotations

import asyncio
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.prompts import COMMENT_RESPONDER_SYSTEM, RESPONDER_SYSTEM
from community_manager.config.settings import get_settings
from community_manager.models.schemas import IncomingMessage, OutgoingReply, Platform, ReplyTargetType
from community_manager.tools.dotnet_client import DotNetClient
from community_manager.tools.llm import get_responder_llm
from community_manager.tools.meta_api import MetaClient

logger = logging.getLogger(__name__)

COMMENT_DM_HANDOFF_PATTERN = re.compile(
    r"\?|\b(cuanto|cuánto|precio|sale|costo|coste|cotiza|cotización|cotizacion|demo|reunion|reunión|implementar|implementación|implementacion|detalle|detalles|info|información|informacion|asesoran|asesoria|asesoría)\b",
    re.IGNORECASE,
)

# In-process queue fed by the FastAPI webhook endpoint
message_queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()
RECENT_PROCESSED_MESSAGE_IDS_MAX = 500
_processed_message_ids: dict[str, None] = {}


def enqueue_message(msg: IncomingMessage) -> None:
    """Push a message into the queue (called from FastAPI route)."""
    message_queue.put_nowait(msg)


def _drain_queue() -> list[IncomingMessage]:
    """Non-blocking drain of the queue."""
    msgs: list[IncomingMessage] = []
    while not message_queue.empty():
        try:
            msgs.append(message_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return msgs


def was_message_processed(message_id: str) -> bool:
    return bool(message_id) and message_id in _processed_message_ids


def remember_processed_message(message_id: str) -> None:
    if not message_id:
        return

    _processed_message_ids.pop(message_id, None)
    _processed_message_ids[message_id] = None

    while len(_processed_message_ids) > RECENT_PROCESSED_MESSAGE_IDS_MAX:
        oldest = next(iter(_processed_message_ids))
        _processed_message_ids.pop(oldest, None)


async def process_pending_messages() -> list[OutgoingReply]:
    """Process all pending incoming messages and generate replies.

    Called by the scheduler every 5 minutes.
    """
    messages = _drain_queue()
    if not messages:
        return []

    logger.info("▶ Responder: processing %d pending message(s)", len(messages))

    settings = get_settings()
    meta = MetaClient()
    dotnet = DotNetClient()
    replies: list[OutgoingReply] = []

    try:
        for msg in messages:
            if was_message_processed(msg.message_id):
                logger.info("Skipping already processed message %s", msg.message_id)
                continue

            reply = await _resolve_reply(settings, meta, dotnet, msg)
            replies.append(reply)

            # Send the reply
            if msg.platform in (Platform.INSTAGRAM, Platform.FACEBOOK):
                success = await _send_meta_reply(meta, msg, reply.text)
                if success:
                    remember_processed_message(msg.message_id)
                    logger.info(
                        "✅ Replied to %s via %s on %s",
                        msg.reply_target_id or msg.sender_id,
                        msg.reply_target_type.value,
                        msg.platform.value,
                    )
                else:
                    logger.warning("❌ Failed to reply to %s", msg.reply_target_id or msg.sender_id)
    finally:
        await meta.close()
        await dotnet.close()

    return replies


async def process_single_message(msg: IncomingMessage) -> OutgoingReply:
    """Process a single incoming message and return the reply (no queue)."""
    if was_message_processed(msg.message_id):
        logger.info("Skipping already processed message %s", msg.message_id)
        return OutgoingReply(text="", in_reply_to=msg.message_id, platform=msg.platform)

    settings = get_settings()

    meta = MetaClient()
    dotnet = DotNetClient()
    try:
        reply = await _resolve_reply(settings, meta, dotnet, msg)
        if msg.platform in (Platform.INSTAGRAM, Platform.FACEBOOK):
            success = await _send_meta_reply(meta, msg, reply.text)
            if success:
                remember_processed_message(msg.message_id)
                logger.info(
                    "✅ Replied to %s via %s on %s",
                    msg.reply_target_id or msg.sender_id,
                    msg.reply_target_type.value,
                    msg.platform.value,
                )
            else:
                logger.warning("❌ Failed to reply to %s", msg.reply_target_id or msg.sender_id)
    finally:
        await meta.close()
        await dotnet.close()

    return reply


async def _resolve_reply(settings, meta: MetaClient, dotnet: DotNetClient, msg: IncomingMessage) -> OutgoingReply:
    if msg.reply_target_type == ReplyTargetType.COMMENT:
        return await _generate_comment_reply(settings, meta, msg)

    reply = await dotnet.generate_dm_reply(
        platform=msg.platform.value,
        sender_id=msg.sender_id,
        sender_name=msg.sender_name or msg.sender_id,
        text=msg.text,
        locale="es-AR",
    )

    if reply:
        return OutgoingReply(
            text=reply,
            in_reply_to=msg.message_id,
            platform=msg.platform,
        )

    logger.warning("DM reply fell back to generic responder for sender %s", msg.sender_id)
    return await _generate_generic_reply(settings, msg)


async def _send_meta_reply(meta: MetaClient, msg: IncomingMessage, text: str) -> bool:
    """Send a direct-message or comment reply through the proper Meta API surface."""
    if msg.reply_target_type == ReplyTargetType.COMMENT:
        target_id = msg.reply_target_id or msg.message_id
        if not target_id:
            logger.warning("Comment reply skipped because target id is missing")
            return False
        return await meta.send_comment_reply(target_id, text, msg.platform)

    target_id = msg.reply_target_id or msg.sender_id
    if not target_id:
        logger.warning("Direct reply skipped because recipient id is missing")
        return False
    return await meta.send_direct_reply(target_id, text, msg.platform)


async def _generate_generic_reply(settings, msg: IncomingMessage) -> OutgoingReply:
    prompt = RESPONDER_SYSTEM.format(
        brand_name=settings.brand_name,
        brand_voice=settings.brand_voice,
    )
    llm = get_responder_llm(temperature=0.5)
    user_msg = HumanMessage(
        content=(
            f"Platform: {msg.platform.value}\n"
            f"From: {msg.sender_name or msg.sender_id}\n"
            f"Message: {msg.text}"
        )
    )

    response = await llm.ainvoke([SystemMessage(content=prompt), user_msg])

    return OutgoingReply(
        text=response.content,
        in_reply_to=msg.message_id,
        platform=msg.platform,
    )


async def _generate_comment_reply(settings, meta: MetaClient, msg: IncomingMessage) -> OutgoingReply:
    prompt = COMMENT_RESPONDER_SYSTEM.format(
        brand_name=settings.brand_name,
        brand_voice=settings.brand_voice,
    )
    llm = get_responder_llm(temperature=0.3)
    post_context = msg.post_context_text.strip()
    if not post_context and msg.post_context_id:
        post_context = await meta.get_post_context(msg.post_context_id, msg.platform)

    needs_dm_handoff = _comment_needs_dm_handoff(msg.text)
    user_msg = HumanMessage(
        content=(
            f"Platform: {msg.platform.value}\n"
            f"Usuario: {msg.sender_name or msg.sender_id}\n"
            f"Comentario: {msg.text}\n"
            f"Copy del post: {post_context or 'No disponible'}\n"
            f"Derivar a DM: {'si' if needs_dm_handoff else 'no'}"
        )
    )

    response = await llm.ainvoke([SystemMessage(content=prompt), user_msg])
    text = str(response.content).strip()
    if needs_dm_handoff and not _mentions_dm(text):
        text = _fallback_dm_handoff_reply(msg.sender_name)

    return OutgoingReply(
        text=text,
        in_reply_to=msg.message_id,
        platform=msg.platform,
    )


def _comment_needs_dm_handoff(text: str) -> bool:
    return bool(COMMENT_DM_HANDOFF_PATTERN.search(text or ""))


def _mentions_dm(text: str) -> bool:
    lowered = (text or "").lower()
    return "dm" in lowered or "mensaje directo" in lowered or "mandanos un mensaje" in lowered or "mandanos por privado" in lowered


def _fallback_dm_handoff_reply(sender_name: str) -> str:
    handle = (sender_name or "").strip()
    prefix = f"Hola @{handle} " if handle and " " not in handle else "Hola "
    return prefix + "depende del caso puntual, pero seguro podemos orientarte mejor por mensaje directo. Mandanos un DM y lo vemos en detalle. Gracias!"

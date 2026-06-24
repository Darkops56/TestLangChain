"""Nurturing workflow — DEPRECATED, kept for historical reference only.

This is the v1 (ReAct-agent-based) newsletter workflow, migrated from
NurturingAIService.cs.  The active workflow is ``workflow_v2.py`` (a
LangGraph state machine). This file is kept under ``_legacy/`` so that
nothing accidentally imports it.

For new code:
  - Newsletter generation → use ``workflow_v2.run_newsletter_workflow``
  - Newsletter revision   → use ``nurturing/revise_service.py``
  - Reply generation      → use ``nurturing/reply_service.py``
  - Personal closing      → use ``nurturing/reply_service.py``

Public API (kept for reference; do not import from new code)
-----------------------------------------------------------
- ``generate_newsletter()``     → (subject, body) with web search tools
- ``revise_newsletter()``       → (subject, body) with web search tools
- ``generate_reply()``          → plain-text reply (no tools)
- ``generate_personal_closing()`` → short closing paragraph (no tools)
- ``validate_and_strip_broken_links()``  → check links in HTML
- ``wrap_in_html_email()``      → wrap body in full HTML email template
"""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from datetime import datetime
from io import BytesIO

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from PIL import Image, ImageDraw, ImageFont

from community_manager.config.settings import get_settings
from community_manager.models.schemas import NewsletterContent, RadarReport
from community_manager.nurturing.google_slides import GoogleSlidesRadarPublisher
from community_manager.nurturing.prompts import (
    NEWSLETTER_SYSTEM,
    NEWSLETTER_USER_TEMPLATE,
    PERSONAL_CLOSING_USER_TEMPLATE,
    REPLY_USER_TEMPLATE,
    REVISION_USER_TEMPLATE,
)
from community_manager.nurturing.tools import NURTURING_TOOLS
from community_manager.tools.blob_media import AzureBlobMediaPublisher
from community_manager.tools.image_gen import ImageGenClient
from community_manager.tools.llm import (
    get_closing_llm,
    get_newsletter_llm,
    get_reply_llm,
)

logger = logging.getLogger(__name__)

MAX_TOOL_STEPS = 10  # mirrors C# MaxToolIterations

LOGO_URL = "https://ia.novitsoftware.com/assets/images/novit-logo.png"

SIMPLE_SYSTEM_MESSAGE = (
    "Sos un asistente experto en comunicación corporativa de tecnología "
    "para Novit Software, una empresa argentina de consultoría tecnológica."
)

NOVIT_DEEP_BLUE = "#0A0089"
NOVIT_CYAN = "#3DB0E4"
NOVIT_MAGENTA = "#BA08A8"
NOVIT_TEXT = "#1F2430"
CHART_WIDTH = 1400
CHART_HEIGHT = 820


# ──────────────────────────────────────────────────────────────
#  Newsletter generation (with tool-calling agent)
# ──────────────────────────────────────────────────────────────

async def generate_newsletter() -> NewsletterContent:
    """Generate the monthly AI Radar package with optional report artifacts."""
    settings = get_settings()
    if not settings.is_nurturing_configured:
        logger.warning("Newsletter AI not configured — returning fallback")
        return _fallback_content()

    if not settings.is_web_search_configured:
        logger.error(
            "Serper API key not configured — cannot generate newsletter "
            "without real news. Set NURTURING_SERPER_API_KEY."
        )
        return NewsletterContent(
            subject="AI Radar by Novit | Configuración incompleta",
            body="No se pudo generar AI Radar by Novit porque la búsqueda web no está configurada. Sin acceso a fuentes reales, no se publica contenido para evitar información inventada.",
            report_title=_build_radar_title(_get_month_name()),
        )

    month_name = _get_month_name()
    prompt = NEWSLETTER_USER_TEMPLATE.format(month_name=month_name)
    return await _build_ai_radar_package(prompt, month_name)


async def revise_newsletter(
    current_subject: str,
    current_body: str,
    reviewer_feedback: str,
) -> tuple[str, str]:
    """Revise an AI Radar report based on reviewer feedback."""
    settings = get_settings()
    if not settings.is_nurturing_configured:
        logger.warning("Newsletter AI not configured — returning fallback")
        return _fallback_content()

    prompt = REVISION_USER_TEMPLATE.format(
        current_subject=current_subject,
        current_body=current_body,
        reviewer_feedback=reviewer_feedback,
    )

    return await _build_ai_radar_package(prompt, _get_month_name())


async def _build_ai_radar_package(user_prompt: str, month_label: str) -> NewsletterContent:
    raw = await _call_newsletter_agent(user_prompt)
    report = _parse_radar_json(raw, month_label)
    artifact = await _build_report_artifacts(report, month_label)
    body = _build_ai_radar_email_body(report, artifact)
    body = await validate_and_strip_broken_links(body)

    return NewsletterContent(
        subject=report.subject,
        body=body,
        report_title=report.report_title,
        executive_summary=report.executive_summary,
        artifact_json=json.dumps(artifact, ensure_ascii=False),
    )


async def _build_report_artifacts(report: RadarReport, month_label: str) -> dict:
    month_key = _get_month_key()
    chart_urls = await _render_chart_assets(report, month_key)
    support_visual_urls = await _render_support_visual_assets(report, month_key)
    slides_artifact = None
    slides_error = ""
    try:
        slides_artifact = await GoogleSlidesRadarPublisher().publish_report(
            report,
            month_label=month_label,
            chart_urls=chart_urls,
            support_visual_urls=support_visual_urls,
        )
    except Exception as exc:
        slides_error = str(exc)
        logger.warning("Google Slides publication unavailable for %s: %s", month_key, slides_error)

    artifact = {
        "generated_at": datetime.utcnow().isoformat(),
        "chart_urls": chart_urls,
        "support_visual_urls": support_visual_urls,
        "sources": _collect_report_sources(report),
        "slides_presentation_id": slides_artifact.presentation_id if slides_artifact else "",
        "slides_url": slides_artifact.presentation_url if slides_artifact else "",
        "slides_name": slides_artifact.presentation_name if slides_artifact else "",
        "shared_drive_id": slides_artifact.shared_drive_id if slides_artifact else "",
        "folder_id": slides_artifact.folder_id if slides_artifact else "",
        "slides_error": slides_error,
    }
    return artifact


async def _render_support_visual_assets(report: RadarReport, month_key: str) -> list[str]:
    settings = get_settings()
    if not settings.is_image_generation_model_configured("image_2"):
        logger.warning("Image 2 profile is not configured; skipping support visuals")
        return []

    prompts = _build_support_visual_prompts(report)
    if not prompts:
        return []

    client = ImageGenClient(image_model="image_2", quality="high", size="1024x1024")
    try:
        images = await client.generate_images(prompts[:3])
        urls = [img.url for img in images if img.url]
        return urls[:3]
    except Exception:
        logger.warning("Could not generate Image 2 support visuals for %s", month_key, exc_info=True)
        return []
    finally:
        await client.close()


def _build_support_visual_prompts(report: RadarReport) -> list[str]:
    insight_1 = report.insights[0].headline if report.insights else "IA aplicada a negocio"
    insight_2 = report.insights[1].headline if len(report.insights) > 1 else insight_1
    insight_3 = report.insights[2].headline if len(report.insights) > 2 else insight_1
    return [
        (
            "Editorial executive illustration for a monthly AI business radar. "
            "Theme: competitive pressure and strategic adaptation in mid-sized companies. "
            f"Highlight concept: {insight_1}. "
            "Visual style: premium corporate, clean, high contrast, subtle futuristic atmosphere, no people faces, "
            "no literal text, no numbers, no logos in the artwork. "
            "Composition must leave clear reading zones for overlays and preserve a professional boardroom tone."
        ),
        (
            "Executive data-driven illustration for AI ecosystem monitoring. "
            "Theme: winners, laggards, cost efficiency, agent adoption and model strategy shifts. "
            f"Highlight concept: {insight_2}. "
            "Visual style: polished analytical backdrop with abstract charts, network structures and directional motion, "
            "corporate quality, elegant gradients, no literal text, no logos. "
            "Designed to support strategic conclusions in a monthly management brief."
        ),
        (
            "Executive conclusion illustration for AI business transformation. "
            "Theme: future outlook, strategic vision, digital transformation journey. "
            f"Highlight concept: {insight_3}. "
            "Visual style: premium corporate, clean, high contrast, subtle futuristic atmosphere, no people faces, "
            "no literal text, no numbers, no logos in the artwork. "
            "Designed for a closing slide with contact information."
        ),
    ]


async def _render_chart_assets(report: RadarReport, month_key: str) -> list[str]:
    if not report.chart_items:
        return []

    image_bytes = _render_chart_png(report)
    if not image_bytes:
        return []

    blob_name = f"ai-radar/{month_key}/chart-{uuid.uuid4().hex[:8]}.png"
    settings = get_settings()
    if not settings.is_blob_media_hosting_configured:
        return []

    publisher = AzureBlobMediaPublisher()
    try:
        public_url = await publisher.upload_bytes(blob_name, image_bytes, content_type="image/png")
        return [public_url]
    finally:
        await publisher.close()


def _render_chart_png(report: RadarReport) -> bytes | None:
    items = report.chart_items[:4]
    if not items:
        return None

    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), color="#F6F8FC")
    draw = ImageDraw.Draw(image)

    title_font = _load_font(54, bold=True)
    subtitle_font = _load_font(28)
    label_font = _load_font(26, bold=True)
    value_font = _load_font(34, bold=True)
    footnote_font = _load_font(22)

    margin_x = 110
    chart_top = 250
    chart_bottom = 640
    bar_height = 78
    bar_gap = 34
    max_value = max(item.value for item in items) or 1
    palette = [NOVIT_DEEP_BLUE, NOVIT_CYAN, NOVIT_MAGENTA, "#5468FF"]

    draw.text((margin_x, 70), report.chart_title or "Señal cuantitativa destacada", fill=NOVIT_DEEP_BLUE, font=title_font)
    if report.chart_subtitle:
        draw.text((margin_x, 140), report.chart_subtitle, fill=NOVIT_TEXT, font=subtitle_font)

    for index, item in enumerate(items):
        top = chart_top + index * (bar_height + bar_gap)
        label = item.label.strip()[:28]
        draw.text((margin_x, top - 36), label, fill=NOVIT_TEXT, font=label_font)

        bar_left = margin_x
        bar_right = margin_x + int(((CHART_WIDTH - margin_x * 2) * item.value) / max_value)
        draw.rounded_rectangle((bar_left, top, bar_right, top + bar_height), radius=22, fill=palette[index % len(palette)])

        value_text = f"{item.value:g} {item.unit}".strip()
        draw.text((bar_right + 18, top + 16), value_text, fill=NOVIT_TEXT, font=value_font)

        source_text = item.source_title.strip()[:60]
        draw.text((margin_x, top + bar_height + 6), source_text, fill="#586174", font=footnote_font)

    footer = "AI Radar by Novit | Fuentes verificadas y seleccionadas para líderes de negocio"
    draw.text((margin_x, CHART_HEIGHT - 70), footer, fill="#586174", font=footnote_font)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _collect_report_sources(report: RadarReport) -> list[dict[str, str]]:
    seen: set[str] = set()
    sources: list[dict[str, str]] = []

    for insight in report.insights:
        if insight.source_url in seen:
            continue
        seen.add(insight.source_url)
        sources.append({
            "title": insight.source_title,
            "url": insight.source_url,
            "date": insight.source_date,
        })

    for item in report.chart_items:
        if item.source_url in seen:
            continue
        seen.add(item.source_url)
        sources.append({
            "title": item.source_title,
            "url": item.source_url,
            "date": "",
        })

    return sources


def _build_ai_radar_email_body(report: RadarReport, artifact: dict) -> str:
    slides_url = artifact.get("slides_url")

    actions: list[str] = []
    if slides_url:
        actions.append(
            f'<a href="{html.escape(slides_url, quote=True)}" style="display:inline-block;background:{NOVIT_DEEP_BLUE};color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:999px;font-weight:700;">Abrir Google Slides</a>'
        )

    highlights = []
    for insight in report.insights[:3]:
        highlights.append(
            "<li style=\"margin:0 0 14px 0;\">"
            f"<b>{html.escape(insight.headline)}</b><br>"
            f"{html.escape(insight.summary)}<br>"
            f"<span style=\"color:{NOVIT_DEEP_BLUE};font-weight:700;\">Qué implica:</span> {html.escape(insight.business_impact)}<br>"
            f"<a href=\"{html.escape(insight.source_url, quote=True)}\" style=\"color:{NOVIT_DEEP_BLUE};\">Fuente: {html.escape(insight.source_title)}</a>"
            "</li>"
        )

    actions_html = (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 22px 0;">{"".join(actions)}</div>'
        if actions
        else ""
    )
    chart_note = (
        f'<p style="margin:0 0 18px 0;color:#586174;"><b>{html.escape(report.chart_title)}</b>: {html.escape(report.chart_subtitle)}</p>'
        if report.chart_items and report.chart_title
        else ""
    )

    return (
        f'<p style="margin:0 0 8px 0;color:{NOVIT_MAGENTA};font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">AI Radar by Novit</p>'
        f'<p style="margin:0 0 12px 0;font-size:24px;line-height:1.2;color:{NOVIT_DEEP_BLUE};font-weight:800;">{html.escape(report.report_title)}</p>'
        f'<p style="margin:0 0 14px 0;color:{NOVIT_TEXT};">{_text_to_html(report.executive_summary)}</p>'
        f'{actions_html}'
        '<p style="margin:0 0 10px 0;font-weight:700;color:#1f2430;">Lectura ejecutiva del mes</p>'
        f'<ul style="padding-left:20px;margin:0 0 12px 0;">{"".join(highlights)}</ul>'
        f'{chart_note}'
        '<p style="margin:18px 0 0 0;color:#586174;">Si querés, lo vemos juntos y te marco qué señales conviene priorizar en tu operación este mes.</p>'
    )


async def _call_newsletter_agent(user_prompt: str) -> str:
    """Run the LangGraph ReAct agent with web search tools.

    This replaces the C# ``CallNewsletterAIWithToolsAsync`` method.
    LangGraph natively handles the tool-calling loop.
    """
    try:
        llm = get_newsletter_llm()
        agent = create_react_agent(
            model=llm,
            tools=NURTURING_TOOLS,
        )

        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=NEWSLETTER_SYSTEM),
                    HumanMessage(content=user_prompt),
                ]
            },
            config={"recursion_limit": MAX_TOOL_STEPS * 2 + 5},
        )

        # The last message in the conversation is the final AI response
        messages = result.get("messages", [])
        if messages:
            final_content = messages[-1].content
            logger.info(
                "Newsletter agent completed with %d messages",
                len(messages),
            )
            return final_content

        logger.warning("Newsletter agent returned empty messages")
        return ""

    except Exception:
        logger.exception("Newsletter agent failed")
        return ""


# ──────────────────────────────────────────────────────────────
#  Reply generation (no tools — cheap model)
# ──────────────────────────────────────────────────────────────

async def generate_reply(
    original_subject: str,
    original_body: str,
    sender_name: str,
) -> str:
    """Generate a plain-text reply to a newsletter response.

    Mirrors C# ``GenerateReplyAsync`` / ``CallReplyAIPlainAsync``.
    """
    prompt = REPLY_USER_TEMPLATE.format(
        sender_name=sender_name,
        original_subject=original_subject,
        original_body=original_body,
    )

    try:
        llm = get_reply_llm()
        response = await llm.ainvoke([
            SystemMessage(content=SIMPLE_SYSTEM_MESSAGE),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()
    except Exception:
        logger.exception("Reply generation failed")
        return "Lo sentimos, el contenido no pudo generarse en este momento."


# ──────────────────────────────────────────────────────────────
#  Personal closing generation (no tools — cheap model)
# ──────────────────────────────────────────────────────────────

async def generate_personal_closing(
    newsletter_subject: str,
    newsletter_body: str | None,
    first_name: str | None,
    org_name: str | None,
    deal_notes: list[str],
) -> str | None:
    """Generate a 1-2 sentence personalised closing.

    Mirrors C# ``GeneratePersonalClosingAsync``.
    Returns ``None`` on error or if the AI is not configured.
    """
    contact_desc_parts: list[str] = []
    if first_name:
        contact_desc_parts.append(f"Nombre: {first_name}.")
    if org_name:
        contact_desc_parts.append(f"Empresa: {org_name}.")
    contact_desc = " ".join(contact_desc_parts)

    notes_section = (
        "Historial de interacciones con este contacto:\n"
        + "\n".join(f"- {n}" for n in deal_notes)
        if deal_notes
        else "No hay historial de interacciones previas con este contacto."
    )

    body_context = ""
    if newsletter_body:
        trimmed = newsletter_body[:1500] + "..." if len(newsletter_body) > 1500 else newsletter_body
        body_context = f"\nContenido del newsletter (resumen):\n{trimmed}\n"

    prompt = PERSONAL_CLOSING_USER_TEMPLATE.format(
        newsletter_subject=newsletter_subject,
        body_context=body_context,
        contact_desc=contact_desc,
        notes_section=notes_section,
    )

    try:
        llm = get_closing_llm()
        response = await llm.ainvoke([
            SystemMessage(content=SIMPLE_SYSTEM_MESSAGE),
            HumanMessage(content=prompt),
        ])
        result = response.content.strip().strip('"')

        # Sanity check — must be short
        if len(result) > 400 or "Lo sentimos" in result:
            return None
        return result

    except Exception:
        logger.exception("Personal closing generation failed for %s", first_name or "unknown")
        return None


# ──────────────────────────────────────────────────────────────
#  Link validation (mirrors C# ValidateAndStripBrokenLinksAsync)
# ──────────────────────────────────────────────────────────────

_LINK_RE = re.compile(
    r'<a\s+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


async def validate_and_strip_broken_links(html: str) -> str:
    """Check every <a href> in *html*; replace broken links with plain text."""
    matches = list(_LINK_RE.finditer(html))
    if not matches:
        return html

    broken: list[tuple[str, str, str]] = []  # (full_match, url, anchor_text)

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for m in matches:
            url, anchor = m.group(1), m.group(2)

            # Skip internal links
            if "novitsoftware.com" in url.lower():
                continue

            try:
                resp = await client.head(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; NewsletterBot/1.0)"},
                )
                # Some sites block HEAD — retry with GET on 405
                if resp.status_code == 405:
                    resp = await client.get(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; NewsletterBot/1.0)"},
                    )

                if resp.status_code >= 400:
                    logger.warning("Broken link: %s → %s", url, resp.status_code)
                    broken.append((m.group(0), url, anchor))
                else:
                    logger.info("Link OK: %s (%s)", url, resp.status_code)

            except Exception as exc:
                logger.warning("Link unreachable: %s (%s)", url, exc)
                broken.append((m.group(0), url, anchor))

    if not broken:
        logger.info("All %d newsletter links validated OK", len(matches))
        return html

    for full_match, url, anchor in broken:
        replacement = f'{anchor} <em style="color:#999;font-size:11px;">(link no disponible)</em>'
        html = html.replace(full_match, replacement)
        logger.warning("Stripped broken link: %s", url)

    logger.warning("%d broken link(s) stripped from newsletter", len(broken))
    return html


# ──────────────────────────────────────────────────────────────
#  HTML email wrapper (mirrors C# WrapInHtmlEmail)
# ──────────────────────────────────────────────────────────────

def wrap_in_html_email(
    html_body: str,
    first_name: str | None = None,
    personal_closing: str | None = None,
) -> str:
    """Wrap AI-generated body in the full email template with Novit signature."""
    greeting = f"Hola {first_name.strip()}," if first_name and first_name.strip() else "Hola,"
    closing_html = (
        f'\n            <p style="margin-top:20px;">{personal_closing}</p>'
        if personal_closing and personal_closing.strip()
        else ""
    )

    return f"""\
<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#ffffff;font-family:'Open Sans',Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff;">
<tr><td style="padding:20px 24px;max-width:600px;font-size:15px;line-height:1.6;color:#222222;">

<p style="margin-top:0;">{greeting}</p>

{html_body}
{closing_html}

<!-- Separator -->
<hr style="border:none;border-top:1px solid #dddddd;margin:28px 0 20px 0;">

<!-- Signature -->
<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:420px;">
<tr>
  <td style="padding:4px 0;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
    <tr>
      <!-- Logo -->
            <td style="vertical-align:middle;padding-right:14px;border-right:2px solid #0A0089;" width="110">
        <img src="{LOGO_URL}" alt="Novit" width="100" style="display:block;border:0;">
      </td>
      <!-- Contact info -->
            <td style="vertical-align:middle;padding-left:14px;font-family:'Open Sans',Arial,Helvetica,sans-serif;font-size:12px;color:#555555;line-height:1.6;">
        <b style="font-size:14px;color:#222222;">Nicolás Piccardo,</b><br>
        Director comercial<br>
        <a href="tel:+5491136895431" style="color:#1a73e8;text-decoration:none;">+54 9 11 3689 5431</a><br>
        <a href="mailto:nicolasp@novitsoftware.com" style="color:#1a73e8;text-decoration:none;">nicolasp@novitsoftware.com</a><br>
        <a href="https://www.novitsoftware.com" style="color:#1a73e8;text-decoration:none;">www.novitsoftware.com</a><br>
        <span style="color:#888888;">Av. Córdoba 1351, piso #3. CABA, Argentina</span>
      </td>
    </tr>
    </table>
  </td>
</tr>
</table>

</td></tr>
</table>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────
#  JSON parsing (mirrors C# ParseNewsletterJson)
# ──────────────────────────────────────────────────────────────

def _parse_radar_json(response_text: str, month_label: str) -> RadarReport:
    """Parse the AI JSON response into a structured AI Radar report."""
    if not response_text:
        return _fallback_report(month_label)

    cleaned = response_text.strip()

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    if cleaned.startswith("```"):
        first_nl = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_nl + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].rstrip()

    try:
        data = json.loads(cleaned)
        report = RadarReport.model_validate(data)
        report.insights = report.insights[:3]
        report.chart_items = report.chart_items[:4]
        report.report_title = _build_radar_title(month_label)
        if not report.subject:
            report.subject = f"AI Radar by Novit | {month_label}"
        return report

    except Exception:
        logger.warning("AI did not return valid AI Radar JSON; using fallback content")
        return _fallback_report(month_label)


# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────

def _fallback_report(month_label: str) -> RadarReport:
    return RadarReport(
        subject=f"AI Radar by Novit | {month_label}",
        report_title=_build_radar_title(month_label),
        executive_summary="No se pudo generar el radar del mes con fuentes verificadas. Preferimos no enviar un resumen incompleto antes que arriesgar información poco confiable.",
        insights=[],
        chart_title="",
        chart_subtitle="",
        chart_items=[],
    )


def _fallback_content() -> NewsletterContent:
    report = _fallback_report(_get_month_name())
    return NewsletterContent(
        subject=report.subject,
        body=_build_ai_radar_email_body(report, {"slides_url": None, "sources": []}),
        report_title=report.report_title,
        executive_summary=report.executive_summary,
        artifact_json=json.dumps({"generated_at": datetime.utcnow().isoformat(), "sources": []}, ensure_ascii=False),
    )


def _get_month_name() -> str:
    """Return current month name in Spanish, e.g. 'junio 2025'."""
    _MONTHS_ES = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }
    now = datetime.utcnow()
    return f"{_MONTHS_ES[now.month]} {now.year}"


def _get_month_key() -> str:
    now = datetime.utcnow()
    return now.strftime("%Y-%m")


def _build_radar_title(month_label: str) -> str:
    return f"Novit AI Radar - {month_label.title()}"


def _text_to_html(value: str) -> str:
    return html.escape(value).replace("\n", "<br>")

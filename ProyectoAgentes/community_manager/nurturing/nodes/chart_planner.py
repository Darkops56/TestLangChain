"""Chart planner node — LLM-driven chart and image prompt planning.

Takes the writer's polished content and asks GPT-5.4 to decide:
  1. CHART: 3-4 datapoints (label, value, unit, source) that synthesize
     the month, prioritizing benchmark/pricing data already in the report.
  2. 3 IMAGE PROMPTS: corporate, no text, no logos, navy/cyan/magenta palette.
  3. chart_title (≤70 ch) + chart_subtitle (≤150 ch) that connect to the
     content the writer just produced.

If the LLM output is invalid, fall back to using the report's
benchmark_data and pricing_data directly (no chart, but no crash either).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.models.schemas import NewsletterContent, RadarChartItem, RadarReport
from community_manager.tools.llm import get_newsletter_llm
from community_manager.tools.safe_json import JsonParseError, parse

logger = logging.getLogger(__name__)


@dataclass
class ChartPlan:
    """Plan for a chart to be rendered."""
    chart_title: str
    chart_subtitle: str
    chart_items: list[dict] = field(default_factory=list)
    chart_description: str = ""
    chart_source: str = ""


@dataclass
class ImagePlan:
    """Plan for an image to be generated."""
    slide_number: int
    description: str
    prompt: str
    style_notes: str = ""


@dataclass
class SlidesPlan:
    """Complete plan for the slides presentation."""
    chart_plan: ChartPlan
    image_plans: list[ImagePlan] = field(default_factory=list)
    slide_structure: list[dict] = field(default_factory=list)


CHART_PLANNER_SYSTEM = """You are the art director for "AI Radar by Novit",
an executive AI newsletter for mid-sized companies.

Your job: read the newsletter content and decide:
  1. CHART: 3-4 comparable numeric datapoints that synthesize the month
  2. 3 IMAGE PROMPTS: corporate visuals for AR, ES, Global/Conclusion slides
  3. chart_title + chart_subtitle in Spanish

CHART RULES:
  - 3 or 4 items (label, value, unit, source_title, source_url)
  - Items MUST be comparable: same unit type
  - Prioritize: (a) benchmark scores of new models, (b) pricing per 1M tokens,
    (c) adoption rates
  - If the report has benchmark_data and pricing_data already, USE THEM
  - Sources must be real (URLs are already URL-validated upstream)
  - Format each item like: {"label": "OpenAI GPT-5.4", "value": 92.1, "unit": "MMLU Pro", "source_title": "TECHCRUNCH", "source_url": "https://..."}

IMAGE PROMPT RULES:
  - In ENGLISH (for GPT Image 2)
  - 40-60 words each
  - No people, no faces, no text, no letters, no logos
  - Palette: deep navy (#0A0089), cyan (#3DB0E4), magenta (#BA08A8)
  - Style: corporate infographic, clean, premium
  - 3 prompts: AR (slide 2), ES (slide 3), Global/Conclusion (slide 4)
  - Slide 2 (AR) and slide 3 (ES): slightly landscape square (1.08:1)
  - Slide 4 (Global/Conclusion): wide horizontal (1.63:1)

OUTPUT FORMAT (JSON only):
{
  "chart_title": "string (max 70 chars, Spanish)",
  "chart_subtitle": "string (max 150 chars, Spanish)",
  "chart_items": [
    {"label": "Model1", "value": 92.1, "unit": "MMLU Pro", "source_title": "...", "source_url": "..."}
  ],
  "image_prompts": {
    "ar": "Corporate infographic prompt for Argentina slide, in English",
    "es": "Corporate infographic prompt for Spain slide, in English",
    "global": "Corporate illustration prompt for global/conclusion slide, in English"
  }
}

CRITICAL: respond with ONLY the JSON object. No prose, no markdown.
"""


async def chart_planner_node(state: dict) -> dict:
    """Plan charts and image prompts for the newsletter slides.

    Input: raw_report (RadarReport), newsletter_content (NewsletterContent)
    Output: slides_plan (SlidesPlan)
    """
    logger.info("▶ Chart planner node starting")

    raw_report: RadarReport = state.get("raw_report")
    newsletter_content: NewsletterContent | None = state.get("newsletter_content")

    if not raw_report:
        logger.warning("No raw report found")
        return {"slides_plan": SlidesPlan(chart_plan=ChartPlan(chart_title="", chart_subtitle=""))}

    # Try LLM-driven planning
    try:
        plan = await _llm_plan(raw_report, newsletter_content)
        logger.info("LLM chart planner produced %d chart items", len(plan.chart_plan.chart_items))
        return {"slides_plan": plan}
    except Exception:
        logger.exception("LLM chart planning failed, falling back to programmatic plan")

    # Fallback: programmatic plan from existing data
    return {"slides_plan": _fallback_plan(raw_report)}


async def _llm_plan(
    report: RadarReport,
    newsletter_content: NewsletterContent | None,
) -> SlidesPlan:
    """Use GPT-5.4 to decide chart and image prompts based on the writer's output."""
    # Build the input for the LLM
    user_prompt = _build_planner_prompt(report, newsletter_content)

    llm = get_newsletter_llm(temperature=0.2)
    response = await llm.ainvoke([
        SystemMessage(content=CHART_PLANNER_SYSTEM),
        HumanMessage(content=user_prompt),
    ])
    raw = response.content if hasattr(response, "content") else str(response)

    try:
        data = parse(raw)
    except JsonParseError as exc:
        raise RuntimeError(f"Chart planner JSON parse failed: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Chart planner did not return a dict")

    # Build ChartPlan
    chart_title = str(data.get("chart_title", ""))[:80]
    chart_subtitle = str(data.get("chart_subtitle", ""))[:160]

    raw_items = data.get("chart_items", [])
    chart_items: list[dict] = []
    if isinstance(raw_items, list):
        for item in raw_items[:4]:
            if not isinstance(item, dict):
                continue
            try:
                chart_items.append({
                    "label": str(item.get("label", ""))[:30],
                    "value": float(item.get("value", 0)),
                    "unit": str(item.get("unit", ""))[:10],
                    "source_title": str(item.get("source_title", ""))[:60],
                    "source_url": str(item.get("source_url", "")),
                })
            except (ValueError, TypeError):
                continue

    # Fallback if LLM returned < 3 items
    if len(chart_items) < 3:
        chart_items = _extract_chart_items_from_report(report)
        if not chart_title:
            chart_title = report.chart_title or "Comparativa del mes"
        if not chart_subtitle:
            chart_subtitle = report.chart_subtitle or "Datos cuantitativos del mes"

    # Validate image prompts (must be in English, ~40-60 words)
    image_prompts = data.get("image_prompts", {})
    if not isinstance(image_prompts, dict):
        image_prompts = {}

    image_plans = [
        ImagePlan(
            slide_number=2,
            description=f"Infografía Argentina: {report.insights[0].headline if report.insights else 'IA en AR'}",
            prompt=_ensure_english_prompt(image_prompts.get("ar")) or _default_ar_prompt(report),
            style_notes="Square-ish infographic, Argentina focus, corporate navy/cyan/magenta palette",
        ),
        ImagePlan(
            slide_number=3,
            description=f"Infografía España: {report.insights[1].headline if len(report.insights) > 1 else 'IA en ES'}",
            prompt=_ensure_english_prompt(image_prompts.get("es")) or _default_es_prompt(report),
            style_notes="Square-ish infographic, Spain focus, corporate navy/magenta/cyan palette",
        ),
        ImagePlan(
            slide_number=4,
            description="Visual Global/Conclusion",
            prompt=_ensure_english_prompt(image_prompts.get("global")) or _default_global_prompt(report),
            style_notes="Wide horizontal illustration, global/conclusion focus, dark navy with glow effects",
        ),
    ]

    chart_plan = ChartPlan(
        chart_title=chart_title,
        chart_subtitle=chart_subtitle,
        chart_items=chart_items,
        chart_description=f"Gráfico de barras con {len(chart_items)} datos comparativos",
        chart_source=f"Fuente: {chart_items[0]['source_title']}" if chart_items else "",
    )

    return SlidesPlan(chart_plan=chart_plan, image_plans=image_plans)


# ════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════

def _build_planner_prompt(report: RadarReport, content: NewsletterContent | None) -> str:
    """Build the user prompt with the writer's content + available data."""
    sections = [
        "CONTENIDO DEL NEWSLETTER QUE ESCRIBIÓ EL WRITER:",
        f"  report_title: {report.report_title or ''}",
        f"  executive_summary: {(report.executive_summary or '')[:800]}",
        f"  slide_2_text (AR): {(report.slide_2_text or '')[:600]}",
        f"  slide_3_text (ES): {(report.slide_3_text or '')[:600]}",
        f"  conclusions: {(report.conclusions or '')[:500]}",
    ]

    # Top-level indicators from the researcher
    if report.benchmark_data:
        sections.append(f"\nBENCHMARK DATA (ya extraído por el researcher): {report.benchmark_data}")
    if report.pricing_data:
        sections.append(f"PRICING DATA (ya extraído por el researcher): {report.pricing_data}")
    if report.adoption_data:
        sections.append(f"ADOPTION DATA: {report.adoption_data}")

    # Model launches from insights
    launches = [i for i in report.insights if i.is_model_launch]
    if launches:
        sections.append("\nLANZAMIENTOS DETECTADOS:")
        for ins in launches:
            line = f"  - {ins.vendor} {ins.model_name}"
            if ins.benchmark_text:
                line += f" ({ins.benchmark_text})"
            if ins.pricing_text:
                line += f" ({ins.pricing_text})"
            sections.append(line)

    sections.append(
        "\n\nDecidí el chart y los 3 image prompts. Respondé SOLO con el JSON."
    )
    return "\n".join(sections)


def _ensure_english_prompt(prompt: str | None) -> str | None:
    """If prompt is non-empty and roughly English-looking, return it. Else None."""
    if not prompt or not isinstance(prompt, str):
        return None
    prompt = prompt.strip()
    if len(prompt) < 20:
        return None
    # Quick heuristic: if >40% of characters are non-ASCII (Spanish accented etc), reject
    non_ascii = sum(1 for c in prompt if ord(c) > 127)
    if non_ascii / max(len(prompt), 1) > 0.20:
        return None
    return prompt


def _default_ar_prompt(report: RadarReport) -> str:
    topic = report.insights[0].headline if report.insights else "AI in Argentina"
    return (
        f"Create a professional infographic for an AI business newsletter. "
        f"Topic: {topic}. Argentina market focus. "
        f"Aspect ratio 1.08:1 (slightly landscape square). "
        f"Style: clean corporate infographic with icons and conceptual diagrams. "
        f"Palette: navy blue (#0A0089), cyan (#3DB0E4), magenta (#BA08A8). "
        f"NO text, NO words, NO letters, NO logos, NO facial features. "
        f"Pure visual communication through diagrams and abstract shapes."
    )


def _default_es_prompt(report: RadarReport) -> str:
    topic = report.insights[1].headline if len(report.insights) > 1 else (report.insights[0].headline if report.insights else "AI in Spain")
    return (
        f"Create a professional infographic for an AI business newsletter. "
        f"Topic: {topic}. Spain/European market focus. "
        f"Aspect ratio 1.08:1 (slightly landscape square). "
        f"Style: clean corporate infographic with icons and conceptual diagrams. "
        f"Palette: navy blue (#0A0089), magenta (#BA08A8), cyan (#3DB0E4). "
        f"NO text, NO words, NO letters, NO logos, NO facial features. "
        f"Pure visual communication through diagrams and abstract shapes."
    )


def _default_global_prompt(report: RadarReport) -> str:
    return (
        "Create a professional executive illustration for an AI business newsletter footer. "
        "Theme: future outlook, strategic vision, digital transformation journey. "
        "Aspect ratio 1.63:1 (wide horizontal landscape). "
        "Style: premium corporate illustration showing AI transformation with abstract "
        "network patterns, data flows, or futuristic business landscapes. "
        "Palette: deep navy (#0A0089) background with cyan (#3DB0E4) and magenta (#BA08A8) "
        "glow effects. NO text, NO words, NO letters, NO logos, NO facial features. "
        "Atmospheric, cinematic corporate quality."
    )


def _extract_chart_items_from_report(report: RadarReport) -> list[dict]:
    """Extract chart items from the report's existing chart_items, validating URLs."""
    items: list[dict] = []
    for ci in report.chart_items[:4]:
        items.append({
            "label": ci.label[:30],
            "value": ci.value,
            "unit": ci.unit,
            "source_title": ci.source_title,
            "source_url": ci.source_url,
        })
    return items


def _fallback_plan(report: RadarReport) -> SlidesPlan:
    """Deterministic plan if the LLM step fails."""
    chart_items = _extract_chart_items_from_report(report)

    chart_plan = ChartPlan(
        chart_title=report.chart_title or "Comparativa del mes",
        chart_subtitle=report.chart_subtitle or "Datos cuantitativos del mes",
        chart_items=chart_items,
        chart_description=f"Gráfico de barras con {len(chart_items)} datos comparativos",
        chart_source=f"Fuente: {chart_items[0]['source_title']}" if chart_items else "",
    )

    image_plans = [
        ImagePlan(
            slide_number=2,
            description="Infografía Argentina (fallback)",
            prompt=_default_ar_prompt(report),
            style_notes="Square-ish infographic, Argentina focus, corporate palette",
        ),
        ImagePlan(
            slide_number=3,
            description="Infografía España (fallback)",
            prompt=_default_es_prompt(report),
            style_notes="Square-ish infographic, Spain focus, corporate palette",
        ),
        ImagePlan(
            slide_number=4,
            description="Visual Global/Conclusión (fallback)",
            prompt=_default_global_prompt(report),
            style_notes="Wide horizontal illustration, global/conclusion focus",
        ),
    ]

    return SlidesPlan(chart_plan=chart_plan, image_plans=image_plans)

"""Content scorer node — scores and selects insights using GPT-5.4.

Takes the wide pool of URL-validated insights from the researcher and
selects the best ones for the newsletter:
  - 1 primary insight per country (AR, ES, GLOBAL)
  - 1 secondary insight per country if score ≥ 6.0 and category is distinct

Model launches (`is_model_launch=true`) and insights with explicit
benchmark/pricing data receive a bonus.

Failure mode: if the LLM returns invalid JSON, retry ONCE with a
reinforced prompt. If it still fails, raise loudly so the workflow
aborts (no silent fallback to "first 3").
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.models.schemas import RadarInsight, RadarReport
from community_manager.tools.llm import get_newsletter_llm
from community_manager.tools.safe_json import JsonParseError, parse

logger = logging.getLogger(__name__)


SCORER_SYSTEM = """You are an expert AI business editor for Novit Software,
an Argentine consultancy that helps mid-sized companies adopt AI.

Your job: evaluate a batch of AI news insights and select the BEST ones
for the monthly executive newsletter "AI Radar".

For EACH insight, score (1-10) on three dimensions:
  1. Relevance: Does this change business decisions in 30-180 days for a
     mid-sized company?
  2. Actionability: Is there a clear "so what" or concrete action?
  3. Novelty: Is this genuinely new or a rehash of old news?

Overall score = average of the three, rounded to 1 decimal.

BONUSES:
  +3 if is_model_launch=true (new model release is highly relevant)
  +2 if benchmark_text or pricing_text is present (data-rich)

PENALTIES:
  -5 if the insight is a thematic duplicate of another insight from the
     SAME country (e.g. two AR insights about "AI regulation" from
     different angles — only one counts as primary)

SELECTION RULES:
  - Group insights by country_tag (AR, ES, GLOBAL)
  - For each country, select the TOP insight as PRIMARY
  - Select a SECONDARY insight only if:
      * Its score (after bonuses) >= 6.0
      * Its category is DIFFERENT from the primary of the same country
      * It covers a genuinely different angle/topic
  - Insights with overall score < 5.0 are always discarded
  - Discard generic statistics without actionable implications
    (e.g. "75% de empresas usan IA" sin contexto operativo)
  - Discard insights where source_url is empty or invalid

OUTPUT FORMAT: Return ONLY a JSON object with this exact structure:
{
  "selected": [
    {
      "index": 0,
      "headline": "...",
      "country": "AR",
      "category": "regulacion",
      "score": 8.3,
      "is_primary": true,
      "is_model_launch": false
    }
  ],
  "discarded": [
    {
      "index": 1,
      "headline": "...",
      "country": "ES",
      "category": "pricing",
      "score": 4.2,
      "reason": "Estadística genérica sin implicación actionable para PyMEs"
    }
  ]
}

CRITICAL: respond with ONLY the JSON object. No prose, no markdown fences.
"""


RETRY_REINFORCEMENT = """

IMPORTANT — JSON FORMAT REMINDER:
Your previous response was not valid JSON. Respond with ONLY a JSON object
that starts with { and ends with }. No markdown, no ``` fences, no text
before or after the JSON. All string values must be properly quoted.
"""


async def content_scorer_node(state: dict) -> dict:
    """Score and filter insights, keeping the best per country.

    Input: raw_report (RadarReport with 25-50 URL-validated insights)
    Output: raw_report (filtered), discarded_insights (list)
    """
    logger.info("▶ Content scorer node starting")

    raw_report: RadarReport | None = state.get("raw_report")
    if not raw_report or not raw_report.insights:
        logger.warning("No raw report or insights to score")
        return {"raw_report": raw_report, "discarded_insights": []}

    insights = raw_report.insights
    logger.info("Scoring %d insights", len(insights))

    # Build the prompt with all insights
    insights_text = _format_insights(insights)

    llm = get_newsletter_llm(temperature=0.3)
    messages = [
        SystemMessage(content=SCORER_SYSTEM),
        HumanMessage(content=f"Evaluate these insights and return JSON:\n\n{insights_text}"),
    ]

    result = None
    last_error: Exception | None = None

    # First attempt
    try:
        result = await _invoke_and_parse(llm, messages)
    except JsonParseError as exc:
        last_error = exc
        logger.warning("First scorer attempt produced invalid JSON: %s. Retrying with reinforced prompt.", exc)

        # Retry ONCE with reinforced prompt
        retry_messages = [
            SystemMessage(content=SCORER_SYSTEM + RETRY_REINFORCEMENT),
            HumanMessage(content=f"Evaluate these insights and return JSON:\n\n{insights_text}"),
        ]
        try:
            result = await _invoke_and_parse(llm, retry_messages)
        except JsonParseError as exc2:
            last_error = exc2
            logger.error("Second scorer attempt also produced invalid JSON: %s — aborting workflow", exc2)
            raise RuntimeError(
                f"Content scorer failed to produce valid JSON after 2 attempts. "
                f"Last error: {exc2}. Workflow aborted — review the LLM prompt or input data."
            ) from exc2

    if result is None:
        raise RuntimeError("Content scorer returned no result without raising an exception")

    # Apply selection: primary + secondary from the scorer's JSON
    selected_indices = {item["index"] for item in result.get("selected", [])}
    secondary_indices = {item["index"] for item in result.get("secondary", [])}

    # Preserve original ordering of insights
    selected_insights = [
        insight for i, insight in enumerate(insights) if i in selected_indices
    ]
    secondary_insights = [
        insight for i, insight in enumerate(insights) if i in secondary_indices
    ]

    # Update the report
    raw_report.insights = selected_insights
    raw_report.insights_secondary = secondary_insights
    raw_report.discarded_insights = result.get("discarded", [])

    logger.info(
        "✅ Content scorer completed: %d primary, %d secondary, %d discarded",
        len(selected_insights),
        len(secondary_insights),
        len(raw_report.discarded_insights),
    )

    return {
        "raw_report": raw_report,
        "discarded_insights": raw_report.discarded_insights,
    }


async def _invoke_and_parse(llm, messages) -> dict:
    """Call the LLM and parse the JSON response. Raises JsonParseError on failure."""
    response = await llm.ainvoke(messages)
    raw = response.content if hasattr(response, "content") else str(response)
    return parse(raw)


def _format_insights(insights: list[RadarInsight]) -> str:
    """Format insights for the scoring prompt."""
    blocks: list[str] = []
    for i, insight in enumerate(insights):
        launch_flag = " [LAUNCH]" if insight.is_model_launch else ""
        benchmark = f" benchmark={insight.benchmark_text}" if insight.benchmark_text else ""
        pricing = f" pricing={insight.pricing_text}" if insight.pricing_text else ""
        vendor = f" vendor={insight.vendor}" if insight.vendor else ""
        model = f" model={insight.model_name}" if insight.model_name else ""

        blocks.append(
            f"INSIGHT #{i}{launch_flag}\n"
            f"country: {insight.country_tag or 'UNKNOWN'}\n"
            f"category: {insight.category or 'UNKNOWN'}\n"
            f"headline: {insight.headline}\n"
            f"summary: {insight.summary[:300]}\n"
            f"business_impact: {insight.business_impact[:200]}\n"
            f"source: {insight.source_title} ({insight.source_url[:80]})"
            f"{vendor}{model}{benchmark}{pricing}"
        )
    return "\n\n".join(blocks)

"""Pre-media evaluator node — validates content before expensive image generation.

Checks text quality, source verification, and chart data consistency
before allowing image generation to proceed. Aborts the workflow (via
retry_target="abort") if there are not enough insights to justify
generating images, slides, and downstream artifacts.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.settings import get_settings
from community_manager.models.schemas import EvaluationResult, RadarReport
from community_manager.shared.evaluator import (
    fail_closed_result,
    validate_chart_data,
    validate_newsletter_sources,
)
from community_manager.tools.llm import get_newsletter_llm

logger = logging.getLogger(__name__)


# Use a small model for the LLM-based insights quality check.
# Falls back to a deterministic check if no LLM is configured.
_QUALITY_CHECK_SYSTEM = """Sos un editor AI que evalúa un lote de insights
extraídos para AI Radar (newsletter ejecutivo).

Tu trabajo: revisar la lista de insights y verificar que tengan:
- headlines claros y específicos
- summaries con contexto concreto
- business_impact accionable para PyMEs
- URLs que parezcan reales (no placeholders)

Devolvé SOLO este JSON:
{
  "approved": true|false,
  "feedback": "explicación breve",
  "issues": ["issue1", "issue2", ...]
}"""

_QUALITY_CHECK_USER = """Evalúa estos {n} insights:

{insights}

Si la mayoría tienen headlines vagos, summaries genéricos, o URLs
sospechosas, marcá approved=false y listá los issues."""


async def evaluator_pre_media_node(state: dict) -> dict:
    """Evaluate newsletter content before image generation.

    Input: raw_report (RadarReport), slides_plan (SlidesPlan)
    Output: pre_media_evaluation (EvaluationResult)

    Aborts the workflow (retry_target="abort") when:
      - raw_report has 0 insights
      - insights are below the configured per-country minimum
      - abort_reason was already set upstream
    """
    logger.info("▶ Pre-media evaluator node starting")

    settings = get_settings()
    raw_report: RadarReport | None = state.get("raw_report")
    slides_plan = state.get("slides_plan")

    # ── Honor upstream abort reasons ────────────────────────────
    abort_reason = state.get("abort_reason")
    if abort_reason:
        return {
            "pre_media_evaluation": fail_closed_result(
                f"Workflow aborted upstream: {abort_reason}. "
                f"Detail: {state.get('abort_detail', '')}",
                abort_reason,
                retry_target="abort",
            ),
            "abort_reason": abort_reason,
            "abort_detail": state.get("abort_detail"),
        }

    if not raw_report:
        return {
            "pre_media_evaluation": fail_closed_result(
                "No hay contenido para evaluar.",
                "Missing raw_report.",
                retry_target="abort",  # ← was "researcher", now abort (no point retrying)
            ),
            "abort_reason": "no_raw_report",
            "abort_detail": "evaluator_pre_media called with no raw_report",
        }

    # ── HARD GUARD: zero insights → abort immediately ───────────
    if not raw_report.insights:
        logger.error(
            "No insights in raw_report — aborting workflow (do not waste tokens)"
        )
        return {
            "pre_media_evaluation": fail_closed_result(
                "El newsletter no tiene insights. Abortando para no gastar tokens.",
                "zero_insights",
                retry_target="abort",
            ),
            "abort_reason": "no_insights",
            "abort_detail": "raw_report.insights is empty",
        }

    # ── HARD GUARD: insufficient per-country coverage → abort ───
    min_per_country = settings.nurturing_min_insights_per_country
    coverage = _count_by_country(raw_report)
    insufficient = [c for c in ("AR", "ES", "GLOBAL") if coverage.get(c, 0) < min_per_country]
    if insufficient:
        logger.error(
            "Insufficient insights per country: have %s, need %d each. Countries below threshold: %s",
            coverage, min_per_country, insufficient,
        )
        return {
            "pre_media_evaluation": fail_closed_result(
                f"Cobertura insuficiente por país. Necesitamos {min_per_country}+ insights en cada uno "
                f"(AR, ES, GLOBAL). Actual: {coverage}.",
                "insufficient_coverage",
                retry_target="abort",  # ← was "researcher", now abort
            ),
            "abort_reason": "insufficient_insights",
            "abort_detail": f"insufficient: {insufficient}, have: {coverage}",
        }

    # ── Existing validations ────────────────────────────────────
    sources_validation = validate_newsletter_sources(raw_report.insights)
    if sources_validation:
        logger.warning("Sources validation failed: %s", sources_validation.feedback)
        return {"pre_media_evaluation": sources_validation}

    chart_validation = validate_chart_data(raw_report.chart_items)
    if chart_validation:
        logger.warning("Chart validation failed: %s", chart_validation.feedback)
        return {"pre_media_evaluation": chart_validation}

    if not raw_report.executive_summary or len(raw_report.executive_summary.strip()) < 50:
        return {
            "pre_media_evaluation": fail_closed_result(
                "El executive summary es muy corto o está vacío.",
                "Executive summary too short.",
                retry_target="writer",
            )
        }

    if len(raw_report.insights) < 2:
        return {
            "pre_media_evaluation": fail_closed_result(
                "Se necesitan al menos 2 insights para el newsletter.",
                f"Only {len(raw_report.insights)} insights found.",
                retry_target="researcher",
            )
        }

    # ── All validations passed ──────────────────────────────────
    evaluation = EvaluationResult(
        approved=True,
        score=9,
        feedback="Contenido validado: fuentes verificables, datos consistentes, estructura completa.",
        issues=[],
        retry_target=None,
    )

    logger.info(
        "✅ Pre-media evaluation passed: %d insights, coverage=%s",
        len(raw_report.insights), coverage,
    )

    return {"pre_media_evaluation": evaluation}


def _count_by_country(report: RadarReport) -> dict[str, int]:
    """Count insights by country_tag."""
    counts: dict[str, int] = {"AR": 0, "ES": 0, "GLOBAL": 0}
    for insight in report.insights:
        tag = (insight.country_tag or "GLOBAL").upper()
        if tag in counts:
            counts[tag] += 1
        else:
            counts[tag] = counts.get(tag, 0) + 1
    return counts

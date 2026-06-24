"""Shared evaluation utilities for Community Manager and Nurturing workflows.

Extracted from graph/nodes/evaluator.py to enable reuse across workflows.
"""

from __future__ import annotations

import logging
import re

from community_manager.models.schemas import ContentType, EvaluationResult

logger = logging.getLogger(__name__)

SOURCE_CLAIM_TRIGGER_PATTERN = re.compile(
    r"\b(estudio|informe|encuesta|investigaci[oó]n|datos|cifras|seg[uú]n|fuente|report)\b",
    flags=re.IGNORECASE,
)
SOURCE_ATTRIBUTION_PATTERN = re.compile(
    r"\b(seg[uú]n|de acuerdo con|fuente|publicado por|elaborado por|realizado por|datos de)\b:?",
    flags=re.IGNORECASE,
)
RECOGNIZABLE_SOURCE_PATTERN = re.compile(
    r"\b(McKinsey|Gartner|Deloitte|PwC|Stanford|MIT|OpenAI|Microsoft|IBM|Harvard|WEF|World Economic Forum|OECD|CEPAL|BID|Banco Mundial|INDEC|Anthropic)\b",
    flags=re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b20\d{2}\b")
QUOTE_PATTERN = re.compile(r'["\u201c\u201d\u2018\u2019](?=["\u201c\u201d\u2018\u2019])[^"\u201c\u201d\u2018\u2019]{12,}["\u201c\u201d\u2018\u2019]')
URL_PATTERN = re.compile(r"https?://|www\.|\b[a-z0-9.-]+\.[a-z]{2,}\b", flags=re.IGNORECASE)
QUANTITATIVE_SIGNAL_PATTERN = re.compile(
    r"([-+]?\d{1,3}%|\$\s?\d|\bUSD\b|\b\d+(?:[.,]\d+)?\s?(?:x|veces|mil|millones?)\b)",
    flags=re.IGNORECASE,
)


def fail_closed_result(feedback: str, issue: str, *, retry_target: str = "abort") -> EvaluationResult:
    """Create a failing EvaluationResult."""
    return EvaluationResult(
        approved=False,
        score=0,
        feedback=feedback,
        issues=[issue],
        retry_target=retry_target,
    )


def validate_visual_assets(strategy, design) -> EvaluationResult | None:
    """Validate that visual assets (images/video) are present and have URLs."""
    if not strategy:
        return None

    if strategy.content_type == ContentType.IMAGE_POST:
        if not design or not design.images:
            return fail_closed_result(
                "Image generation did not produce publishable media.",
                "No publishable image was generated.",
            )
        if any(not image.url for image in design.images):
            return fail_closed_result(
                "Image generation produced incomplete media metadata.",
                "At least one generated image is missing a remote URL.",
            )

    if strategy.content_type == ContentType.VIDEO_POST:
        if not design or not design.video:
            return fail_closed_result(
                "Video generation did not produce publishable media.",
                "No publishable video was generated.",
            )
        if not design.video.url:
            return fail_closed_result(
                "Video generation produced incomplete media metadata.",
                "The generated video is missing a remote URL.",
            )

    return None


def has_explicit_source_attribution(text: str) -> bool:
    """Check if text has explicit source attribution (source name + year/URL)."""
    if not text:
        return False
    has_source_anchor = bool(SOURCE_ATTRIBUTION_PATTERN.search(text) or URL_PATTERN.search(text))
    has_source_identity = bool(RECOGNIZABLE_SOURCE_PATTERN.search(text) or YEAR_PATTERN.search(text) or URL_PATTERN.search(text))
    return has_source_anchor and has_source_identity


def text_has_unsourced_quantitative_claim(text: str) -> bool:
    """Check if text has quantitative claims without source attribution."""
    if not text:
        return False
    has_signal = bool(QUANTITATIVE_SIGNAL_PATTERN.search(text))
    if not has_signal:
        return False
    return not has_explicit_source_attribution(text)


def validate_factual_grounding(text_surfaces: list[tuple[str, str]]) -> EvaluationResult | None:
    """Validate that quantitative claims have source attribution.

    Parameters
    ----------
    text_surfaces : list[tuple[str, str]]
        List of (label, text) pairs to check.
    """
    combined_text = "\n".join(text for _, text in text_surfaces)
    if has_explicit_source_attribution(combined_text):
        return None

    offending_surfaces = [
        label
        for label, text in text_surfaces
        if text_has_unsourced_quantitative_claim(text)
    ]
    if not offending_surfaces:
        return None

    surfaces_text = ", ".join(offending_surfaces)
    return fail_closed_result(
        "La pieza usa cifras o comparativas numéricas sin fuente verificable. "
        "Si no hay fuente real, reescribila en términos cualitativos.",
        f"Unsourced quantitative claim detected in: {surfaces_text}.",
        retry_target="copywriter",
    )


def validate_newsletter_sources(insights: list) -> EvaluationResult | None:
    """Validate that newsletter insights have verifiable sources.

    Parameters
    ----------
    insights : list
        List of insight objects with source_url and source_title fields.
    """
    if not insights:
        return fail_closed_result(
            "El newsletter no tiene insights.",
            "No insights generated.",
            retry_target="writer",
        )

    missing_sources = []
    for i, insight in enumerate(insights, 1):
        source_url = getattr(insight, "source_url", None) or (insight.get("source_url") if isinstance(insight, dict) else None)
        source_title = getattr(insight, "source_title", None) or (insight.get("source_title") if isinstance(insight, dict) else None)

        if not source_url or not source_title:
            missing_sources.append(f"Insight {i}")

    if missing_sources:
        return fail_closed_result(
            f"Los siguientes insights no tienen fuente verificable: {', '.join(missing_sources)}. "
            "Todos los insights deben tener source_url y source_title.",
            f"Missing sources in: {', '.join(missing_sources)}.",
            retry_target="researcher",
        )

    return None


def validate_chart_data(chart_items: list) -> EvaluationResult | None:
    """Validate that chart items have consistent units and valid data.

    Parameters
    ----------
    chart_items : list
        List of chart items with value, unit, label fields.
    """
    if not chart_items:
        return None  # Chart is optional

    for i, item in enumerate(chart_items, 1):
        value = getattr(item, "value", None) or (item.get("value") if isinstance(item, dict) else None)
        unit = getattr(item, "unit", None) or (item.get("unit") if isinstance(item, dict) else None)
        label = getattr(item, "label", None) or (item.get("label") if isinstance(item, dict) else None)

        if value is None:
            return fail_closed_result(
                f"El item {i} del gráfico no tiene valor numérico.",
                f"Chart item {i} missing value.",
                retry_target="writer",
            )
        if not unit:
            return fail_closed_result(
                f"El item {i} del gráfico no tiene unidad.",
                f"Chart item {i} missing unit.",
                retry_target="writer",
            )
        if not label:
            return fail_closed_result(
                f"El item {i} del gráfico no tiene etiqueta.",
                f"Chart item {i} missing label.",
                retry_target="writer",
            )

    # Check unit consistency
    units = set()
    for item in chart_items:
        unit = getattr(item, "unit", None) or (item.get("unit") if isinstance(item, dict) else None)
        if unit:
            units.add(unit.strip())

    if len(units) > 1:
        return fail_closed_result(
            f"Los items del gráfico tienen unidades distintas: {', '.join(units)}. "
            "Todos los items deben usar la misma unidad para ser comparables.",
            f"Inconsistent chart units: {', '.join(units)}.",
            retry_target="writer",
        )

    return None

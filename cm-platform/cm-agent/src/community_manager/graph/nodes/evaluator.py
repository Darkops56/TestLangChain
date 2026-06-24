"""Evaluator node — validates content quality and brand compliance.

Reviews the copy (and optionally the visual prompt) and decides
whether to approve or send it back for revision.
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.prompts import EVALUATOR_SYSTEM
from community_manager.config.settings import get_settings
from community_manager.graph.state import CommunityManagerState
from community_manager.models.schemas import ContentType, EvaluationResult, ReviewStage
from community_manager.tools.llm import get_small_llm

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
QUOTE_PATTERN = re.compile(r"[\"“”'‘’][^\"“”'‘’]{12,}[\"“”'‘’]")
URL_PATTERN = re.compile(r"https?://|www\.|\b[a-z0-9.-]+\.[a-z]{2,}\b", flags=re.IGNORECASE)
QUANTITATIVE_SIGNAL_PATTERN = re.compile(
    r"([-+]?\d{1,3}%|\$\s?\d|\bUSD\b|\b\d+(?:[.,]\d+)?\s?(?:x|veces|mil|millones?)\b)",
    flags=re.IGNORECASE,
)
YEARLY_COMPARISON_PATTERN = re.compile(r"\b20\d{2}\b.{0,24}\b20\d{2}\b", flags=re.IGNORECASE | re.DOTALL)
QUANTITATIVE_CONTEXT_PATTERN = re.compile(
    r"\b(precio|precios|costo|costos|l[ií]mite|l[ií]mites|variaci[oó]n|suba|subas|aumento|aumentaron|subieron|bajaron|baj[oó]|reduj(?:o|eron)|ca[ií]da|creci[oó]|crecimiento|adopci[oó]n|usuarios|consumo|proveedor(?:es)?|modelo(?:s)?|OpenAI|Anthropic|Copilot|Claude|Gemini|Xiaomi|Moonshot)\b",
    flags=re.IGNORECASE,
)


def _normalize_json_payload(content: str) -> str:
    payload = content.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        payload = "\n".join(lines).strip()
    return payload


def _fail_closed_result(feedback: str, issue: str, *, retry_target: str = "abort") -> EvaluationResult:
    return EvaluationResult(
        approved=False,
        score=0,
        feedback=feedback,
        issues=[issue],
        retry_target=retry_target,
    )


def _validate_visual_assets(strategy, design) -> EvaluationResult | None:
    if not strategy:
        return None

    if strategy.content_type == ContentType.IMAGE_POST:
        if not design or not design.images:
            return _fail_closed_result(
                "Image generation did not produce publishable media. Refusing to publish without a real generated asset.",
                "No publishable image was generated for this image post.",
            )

        if any(not image.url for image in design.images):
            return _fail_closed_result(
                "Image generation produced incomplete media metadata. Refusing to publish an unverified image asset.",
                "At least one generated image is missing a remote URL.",
            )

    if strategy.content_type == ContentType.VIDEO_POST:
        if not design or not design.video:
            return _fail_closed_result(
                "Video generation did not produce publishable media. Refusing to publish without a real generated asset.",
                "No publishable video was generated for this video post.",
            )

        if not design.video.url:
            return _fail_closed_result(
                "Video generation produced incomplete media metadata. Refusing to publish an unverified video asset.",
                "The generated video is missing a remote URL.",
            )

    return None


def _validate_copy_integrity(copy) -> EvaluationResult | None:
    caption = (copy.caption or "").strip()

    if "##" in caption:
        return _fail_closed_result(
            "El caption contiene hashtags o marcadores con doble numeral (##). Corregilo para que cada hashtag tenga un único #.",
            "Malformed hashtag formatting detected in caption.",
            retry_target="copywriter",
        )

    source_claim_trigger = SOURCE_CLAIM_TRIGGER_PATTERN.search(caption)
    if not source_claim_trigger:
        return None

    has_attribution_phrase = SOURCE_ATTRIBUTION_PATTERN.search(caption)
    has_recognizable_source = RECOGNIZABLE_SOURCE_PATTERN.search(caption)
    has_year = YEAR_PATTERN.search(caption)
    has_quote = QUOTE_PATTERN.search(caption)

    if not (has_attribution_phrase and (has_recognizable_source or has_year) and has_quote):
        return _fail_closed_result(
            "El copy menciona estudios o datos sin evidencia suficiente. Si citás estudios/cifras, debés incluir quién hizo el estudio, año o fuente verificable y una cita textual breve entre comillas.",
            "Unverified study/data claim without explicit source attribution and quote.",
            retry_target="copywriter",
        )

    return None


def _iter_factual_claim_surfaces(copy, design):
    if copy:
        if copy.caption:
            yield ("caption", copy.caption)
        if copy.alt_text:
            yield ("alt_text", copy.alt_text)

    if not design:
        return

    for index, image in enumerate(design.images, start=1):
        slide_number = image.slide_number or index
        if image.visible_text:
            yield (f"slide {slide_number} visible_text", image.visible_text)
        if image.review_summary:
            yield (f"slide {slide_number} review_summary", image.review_summary)

    if design.video:
        if design.video.avatar_script:
            yield ("video avatar_script", design.video.avatar_script)
        if design.video.review_summary:
            yield ("video review_summary", design.video.review_summary)
        for index, clip in enumerate(design.video.supporting_clips, start=1):
            if clip.review_summary:
                yield (f"video clip {index} review_summary", clip.review_summary)


def _has_explicit_source_attribution(text: str) -> bool:
    if not text:
        return False

    has_source_anchor = bool(SOURCE_ATTRIBUTION_PATTERN.search(text) or URL_PATTERN.search(text))
    has_source_identity = bool(RECOGNIZABLE_SOURCE_PATTERN.search(text) or YEAR_PATTERN.search(text) or URL_PATTERN.search(text))
    return has_source_anchor and has_source_identity


def _text_has_unsourced_quantitative_claim(text: str) -> bool:
    if not text:
        return False

    has_signal = bool(QUANTITATIVE_SIGNAL_PATTERN.search(text) or YEARLY_COMPARISON_PATTERN.search(text))
    has_context = bool(QUANTITATIVE_CONTEXT_PATTERN.search(text))
    if not (has_signal and has_context):
        return False

    return not _has_explicit_source_attribution(text)


def _validate_factual_grounding(copy, design) -> EvaluationResult | None:
    combined_text = "\n".join(text for _, text in _iter_factual_claim_surfaces(copy, design))
    if _has_explicit_source_attribution(combined_text):
        return None

    offending_surfaces = [
        label
        for label, text in _iter_factual_claim_surfaces(copy, design)
        if _text_has_unsourced_quantitative_claim(text)
    ]
    if not offending_surfaces:
        return None

    retry_target = "designer" if any(label.startswith("slide ") or label.startswith("video ") for label in offending_surfaces) else "copywriter"
    surfaces_text = ", ".join(offending_surfaces)
    return _fail_closed_result(
        "La pieza usa cifras, porcentajes o comparativas numéricas concretas sin fuente verificable visible en el caption o en el plan visual. Si no hay fuente real, reescribila en términos cualitativos y eliminá los números exactos.",
        f"Unsourced quantitative claim detected in: {surfaces_text}.",
        retry_target=retry_target,
    )


def _build_review_material(*, strategy, copy, design, settings, review_stage: str, materialize_media: bool):
    hashtag_str = " ".join(f"#{h}" for h in copy.hashtags)
    review_parts = [
        f"Content type: {strategy.content_type.value if strategy else 'unknown'}",
        f"Caption:\n{copy.caption}",
        f"Hashtags: {hashtag_str}",
        f"Alt text: {copy.alt_text}",
    ]

    if strategy:
        review_parts.append(f"Topic: {strategy.topic}")
        review_parts.append(f"Angle: {strategy.angle}")
        review_parts.append(f"Supporting points: {', '.join(strategy.supporting_points)}")
        review_parts.append(f"Required language: {strategy.language}")
        if strategy.content_type == ContentType.VIDEO_POST:
            review_parts.append(f"Target video duration: {strategy.video_duration_seconds} seconds")

    if design:
        if design.images:
            prompts_text = "\n".join(
                (
                    f"  - Slide {image.slide_number or index}: {image.review_summary or image.prompt}"
                    + (f" | Texto visible: {image.visible_text}" if image.visible_text else "")
                    + f" | Prompt: {image.prompt}"
                )
                for index, image in enumerate(design.images, start=1)
            )
            review_parts.append(f"Image plan:\n{prompts_text}")
        if design.video:
            review_parts.append(f"Video plan summary: {design.video.review_summary or design.video.prompt}")
            if design.video.avatar_script:
                review_parts.append(f"Avatar script:\n{design.video.avatar_script}")
            if design.video.supporting_clips:
                review_parts.append(
                    "Supporting clips:\n" + "\n".join(
                        f"  - {clip.review_summary or clip.purpose or clip.prompt}"
                        for clip in design.video.supporting_clips
                    )
                )
        if design.style_notes:
            review_parts.append(f"Style notes: {design.style_notes}")

    review_parts.append(f"Brand guidelines: {settings.brand_voice}")
    review_parts.append(f"Required hashtags: {settings.brand_hashtags}")
    review_parts.append("Reject if the content is not fully in Spanish or lacks a concrete business angle.")

    include_rendered_images = (
        strategy
        and strategy.content_type == ContentType.IMAGE_POST
        and design
        and design.images
        and (materialize_media or review_stage != ReviewStage.PRE_MEDIA.value)
        and all((image.url or "").strip() for image in design.images)
    )

    if not include_rendered_images:
        return "\n\n".join(review_parts)

    content_blocks: list[dict] = [
        {"type": "text", "text": "\n\n".join(review_parts)},
        {
            "type": "text",
            "text": (
                "A continuación se adjuntan los slides reales generados. Evaluá lo que se ve en la imagen final, "
                "no sólo el prompt. Si un problema afecta un slide puntual, devolvé su número en slide_reviews."
            ),
        },
    ]

    for index, image in enumerate(design.images, start=1):
        slide_number = image.slide_number or index
        content_blocks.append({
            "type": "text",
            "text": f"Slide {slide_number}. Prompt original: {image.prompt}",
        })
        content_blocks.append({
            "type": "image_url",
            "image_url": {"url": image.url},
        })

    return content_blocks


def _normalize_evaluation(evaluation: EvaluationResult) -> EvaluationResult:
    failing_slide_reviews = [review for review in evaluation.slide_reviews if not review.approved]
    if not evaluation.approved and failing_slide_reviews and not evaluation.retry_target:
        return evaluation.model_copy(update={"retry_target": "designer"})
    return evaluation


async def evaluator_node(state: CommunityManagerState) -> dict:
    """Evaluate generated content for quality and compliance."""
    logger.info("▶ Evaluator node starting")

    settings = get_settings()
    copy = state.get("copy")
    design = state.get("design")
    strategy = state.get("strategy")
    review_stage = state.get("review_stage", ReviewStage.FINAL.value)
    materialize_media = bool(state.get("materialize_media"))

    if not copy:
        return {
            "evaluation": EvaluationResult(
                approved=False, score=0,
                feedback="No copy to evaluate",
                retry_target="copywriter",
            ),
            "retry_count": state.get("retry_count", 0) + 1,
        }

    media_validation = None
    if materialize_media or review_stage != ReviewStage.PRE_MEDIA.value:
        media_validation = _validate_visual_assets(strategy, design)
    if media_validation:
        logger.warning("Failing closed before evaluation: %s", media_validation.feedback)
        return {
            "evaluation": media_validation,
            "retry_count": state.get("retry_count", 0) + 1,
        }

    copy_integrity_validation = _validate_copy_integrity(copy)
    if copy_integrity_validation:
        logger.warning("Failing closed before evaluation: %s", copy_integrity_validation.feedback)
        return {
            "evaluation": copy_integrity_validation,
            "retry_count": state.get("retry_count", 0) + 1,
        }

    factual_grounding_validation = _validate_factual_grounding(copy, design)
    if factual_grounding_validation:
        logger.warning("Failing closed before evaluation: %s", factual_grounding_validation.feedback)
        return {
            "evaluation": factual_grounding_validation,
            "retry_count": state.get("retry_count", 0) + 1,
        }

    if state.get("skip_llm_evaluation"):
        logger.info("Skipping LLM evaluator for manual direct publish; deterministic asset validation passed")
        return {
            "evaluation": EvaluationResult(
                approved=True,
                score=10,
                feedback="Manual direct publish skipped subjective LLM evaluation after asset validation.",
                issues=[],
                retry_target=None,
            ),
            "retry_count": state.get("retry_count", 0),
            "messages": [],
        }

    prompt = EVALUATOR_SYSTEM.format(
        brand_name=settings.brand_name,
        brand_voice=settings.brand_voice,
    )

    user_msg = HumanMessage(content=_build_review_material(
        strategy=strategy,
        copy=copy,
        design=design,
        settings=settings,
        review_stage=review_stage,
        materialize_media=materialize_media,
    ))

    # Call LLM (smaller/cheaper model for evaluation)
    llm = get_small_llm()
    response = await llm.ainvoke([SystemMessage(content=prompt), user_msg])

    # Parse
    try:
        data = json.loads(_normalize_json_payload(response.content))
        evaluation = EvaluationResult(**data)
        evaluation = _normalize_evaluation(evaluation)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Failed to parse evaluator response: %s — failing closed", exc)
        evaluation = EvaluationResult(
            approved=False,
            score=0,
            feedback="Evaluator response could not be parsed. Refusing to publish without a valid evaluation.",
            issues=["Evaluator returned invalid JSON."],
            retry_target="abort",
        )

    retry_count = state.get("retry_count", 0)
    if not evaluation.approved:
        retry_count += 1

    logger.info(
        "✅ Evaluation: approved=%s score=%d retry_count=%d",
        evaluation.approved, evaluation.score, retry_count,
    )

    return {
        "evaluation": evaluation,
        "retry_count": retry_count,
        "messages": [response],
    }

"""Designer node — generates visual content (images via DALL-E 3, video via Sora 2).

First uses the LLM to generate an optimal prompt for the generation model,
then calls the Azure AI Foundry REST APIs to create the media.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.config.prompts import DESIGNER_IMAGE_QA_SYSTEM, DESIGNER_IMAGE_SYSTEM, DESIGNER_VIDEO_SYSTEM
from community_manager.config.settings import get_settings
from community_manager.graph.state import CommunityManagerState
from community_manager.models.schemas import ContentType, DesignerOutput, EvaluationResult, FIXED_VIDEO_DURATION_SECONDS, GeneratedImage, GeneratedVideo, PlannedVideoClip, PromptReviewResult, SlideReview
from community_manager.tools.image_gen import ImageGenClient
from community_manager.tools.llm import get_main_llm, get_small_llm
from community_manager.tools.training_media import (
    build_avatar_background_reference_bundle,
    build_brand_logo_reference_bundle,
    build_published_post_reference_bundle,
    build_presenter_reference_bundle,
    build_training_reference_bundle,
    merge_reference_bundles,
)
from community_manager.tools.video_gen import CompositeSupportClipPlan, CompositeVideoClient, CompositeVideoPlan, SoraClient
from community_manager.tools.video_gen import DEFAULT_AVATAR_INTRO_SECONDS, DEFAULT_AVATAR_OUTRO_SECONDS, DEFAULT_SUPPORTING_CLIP_TRANSITION, SUPPORTED_SUPPORTING_CLIP_TRANSITIONS

logger = logging.getLogger(__name__)

SLIDE_REFERENCE_PATTERN = re.compile(
    r"\b(?:slide|slides|placa|placas|imagen|imagenes|frame|frames)\b[^\d]{0,12}((?:\d+\s*(?:-|,|y|e)\s*)*\d+)",
    flags=re.IGNORECASE,
)


def _default_supporting_clip_duration(index: int) -> int:
    return 8 if index < 2 else 4


def _coerce_storyboard_seconds(value, *, default: float) -> float:
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return default


def _normalize_support_clip_transition(transition) -> str:
    normalized_transition = str(transition or "").strip().lower()
    if normalized_transition in SUPPORTED_SUPPORTING_CLIP_TRANSITIONS:
        return normalized_transition
    return DEFAULT_SUPPORTING_CLIP_TRANSITION


def _normalize_support_clip_duration(duration_seconds) -> int:
    try:
        parsed = int(duration_seconds)
    except (TypeError, ValueError):
        return 8
    return 4 if parsed <= 4 else 8


def _build_default_support_clip_starts(
    *,
    total_duration_seconds: int,
    clip_durations: list[int],
    avatar_intro_seconds: float,
    avatar_outro_seconds: float,
) -> list[float]:
    if not clip_durations:
        return []

    usable_window_end = max(float(total_duration_seconds) - avatar_outro_seconds, avatar_intro_seconds)
    total_clip_duration = float(sum(clip_durations))
    gap_count = max(len(clip_durations) - 1, 0)
    available_gap_space = max(usable_window_end - avatar_intro_seconds - total_clip_duration, 0.0)
    gap_seconds = available_gap_space / gap_count if gap_count else 0.0

    starts: list[float] = []
    cursor = avatar_intro_seconds
    for index, duration_seconds in enumerate(clip_durations):
        starts.append(round(cursor, 2))
        cursor += duration_seconds
        if index < gap_count:
            cursor += gap_seconds
    return starts


@dataclass(frozen=True)
class _CompositeVideoDraft:
    avatar_script: str
    supporting_clips: list[CompositeSupportClipPlan]
    style_notes: str
    duration_seconds: int = FIXED_VIDEO_DURATION_SECONDS
    avatar_intro_seconds: float = DEFAULT_AVATAR_INTRO_SECONDS
    avatar_outro_seconds: float = DEFAULT_AVATAR_OUTRO_SECONDS


VIDEO_OUTRO_REQUIREMENTS = """Requisitos obligatorios de cierre:
- La frase principal debe terminar hacia el segundo 27 o 28, no en el último frame.
- Reservá los últimos 2 o 3 segundos para una resolución visual clara: pausa natural, gesto final, plano recurso o end card minimalista.
- Si aparece marca en el cierre, usá solo el logo real de Novit; si no está disponible con precisión, evitá mostrar logo.
- El último segundo debe cerrar con fade out, disolvencia suave o hold visual limpio. Nunca cortes seco apenas termina de hablar.
"""


VIDEO_RENDERING_REQUIREMENTS = """Requisitos obligatorios de composición:
- Tratá el video como pieza compuesta realista: avatar/presentador sobre fondo real de oficina, intercalado con clips de apoyo concretos.
- El avatar principal debe sentirse sentado y creíble sobre la silla central del fondo real de Novit, con framing frontal sobrio.
- Los clips de apoyo deben mostrar algo concreto y entendible: código Python, terminal, documentación, canvas de nodos, dashboard o tutorial paso a paso.
- Nunca uses una cara dentro de un fondo sintético intentando parecer oficina real.
- Si hay voz, texto hablado o subtítulos, mantené español rioplatense argentino natural con voseo real; evitá "tú", "puedes", "vale" y cualquier neutralización latina genérica.
- Dejá visualmente limpia la esquina inferior derecha para composición posterior exacta con el logo oficial de Novit.
"""


VIDEO_AGENT_TUTORIAL_REQUIREMENTS = """Requisitos temáticos para tutorial de agentes:
- Mostrá un flujo de grafo o nodos de agentes de forma explícita y legible.
- Mostrá fragmentos de código Python reales o plausibles que conecten herramientas, subagentes o pasos del workflow.
- La narrativa visual debe sentirse como demo explicada: cursor, foco en bloques concretos, zooms suaves y progresión clara de pantalla a pantalla.
"""


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


def _build_designer_user_content(*, context_text: str, reference_bundle: dict | None, extra_text: str = ""):
    task_text = context_text if not extra_text else f"{context_text}\n{extra_text}"
    if not reference_bundle:
        return task_text

    return [
        {"type": "text", "text": task_text},
        *reference_bundle["message_content"],
    ]


def _normalize_slide_numbers(slide_numbers: list[int], *, total_slides: int) -> list[int]:
    normalized: list[int] = []
    for slide_number in slide_numbers:
        try:
            parsed = int(slide_number)
        except (TypeError, ValueError):
            continue
        if 1 <= parsed <= total_slides and parsed not in normalized:
            normalized.append(parsed)
    return sorted(normalized)


def _extract_slide_numbers_from_text(text: str, *, total_slides: int) -> list[int]:
    if not text:
        return []

    slide_numbers: list[int] = []
    for fragment in SLIDE_REFERENCE_PATTERN.findall(text):
        for match in re.finditer(r"(\d+)\s*-\s*(\d+)|(\d+)", fragment):
            if match.group(1) and match.group(2):
                start = int(match.group(1))
                end = int(match.group(2))
                low, high = sorted((start, end))
                slide_numbers.extend(range(low, high + 1))
            elif match.group(3):
                slide_numbers.append(int(match.group(3)))

    return _normalize_slide_numbers(slide_numbers, total_slides=total_slides)


def _format_slide_reviews(slide_reviews: list[SlideReview]) -> str:
    lines: list[str] = []
    for review in slide_reviews:
        if review.approved:
            continue
        issue_text = "; ".join(review.issues) if review.issues else review.feedback or "Ajustar este slide"
        lines.append(f"- Slide {review.slide_number}: {issue_text}")
    return "\n".join(lines)


def _describe_existing_slide_prompts(design: DesignerOutput | None) -> str:
    if not design or not design.images:
        return ""

    lines: list[str] = []
    for index, image in enumerate(design.images, start=1):
        slide_number = image.slide_number or index
        lines.append(f"- Slide {slide_number}: {image.prompt}")
    return "\n".join(lines)


def _ensure_prompt_count(prompts: list[str], *, total_slides: int, topic: str) -> list[str]:
    normalized_prompts = [prompt.strip() for prompt in prompts[:total_slides] if prompt and prompt.strip()]
    fallback = normalized_prompts[-1] if normalized_prompts else f"Professional tech illustration about: {topic}"
    while len(normalized_prompts) < total_slides:
        normalized_prompts.append(fallback)
    return normalized_prompts


def _infer_visible_text(prompt: str) -> str:
    prompt_lower = prompt.lower()
    marker_candidates = ["texto visible", "headline", "overlay text", "texto principal"]
    for marker in marker_candidates:
        marker_index = prompt_lower.find(marker)
        if marker_index < 0:
            continue
        snippet = prompt[marker_index:].split("\n", 1)[0]
        _, _, remainder = snippet.partition(":")
        candidate = remainder.strip().strip('"')
        if candidate:
            return candidate[:180]
    return ""


def _coerce_image_plan_item(item, *, slide_number: int, fallback_prompt: str) -> GeneratedImage:
    if isinstance(item, dict):
        prompt = str(item.get("prompt", "") or "").strip() or fallback_prompt
        review_summary = str(item.get("review_summary", "") or "").strip() or prompt
        visible_text = str(item.get("visible_text", "") or "").strip() or _infer_visible_text(prompt)
        requested_slide_number = item.get("slide_number")
        try:
            slide_number = int(requested_slide_number or slide_number)
        except (TypeError, ValueError):
            pass
        return GeneratedImage(
            prompt=prompt,
            review_summary=review_summary,
            visible_text=visible_text,
            slide_number=slide_number,
        )

    prompt = str(item or "").strip() or fallback_prompt
    return GeneratedImage(
        prompt=prompt,
        review_summary=prompt,
        visible_text=_infer_visible_text(prompt),
        slide_number=slide_number,
    )


def _ensure_image_plan_count(items: list, *, total_slides: int, topic: str) -> list[GeneratedImage]:
    normalized_items = [item for item in items[:total_slides] if item]
    fallback_prompt = "Professional tech illustration about: {topic}".format(topic=topic)

    slide_plans = [
        _coerce_image_plan_item(item, slide_number=index, fallback_prompt=fallback_prompt)
        for index, item in enumerate(normalized_items, start=1)
    ]
    while len(slide_plans) < total_slides:
        slide_number = len(slide_plans) + 1
        seed_prompt = slide_plans[-1].prompt if slide_plans else fallback_prompt
        slide_plans.append(_coerce_image_plan_item(seed_prompt, slide_number=slide_number, fallback_prompt=fallback_prompt))
    return slide_plans


def _resolve_retry_slide_numbers(
    *,
    strategy,
    evaluation: EvaluationResult | None,
    reviewer_feedback: str,
) -> list[int]:
    if not strategy or strategy.content_type != ContentType.IMAGE_POST:
        return []

    total_slides = strategy.num_images
    all_slides = list(range(1, total_slides + 1))
    if not evaluation or evaluation.retry_target != "designer":
        return all_slides

    slide_numbers = _normalize_slide_numbers(
        [review.slide_number for review in evaluation.slide_reviews if not review.approved],
        total_slides=total_slides,
    )
    if slide_numbers:
        return slide_numbers

    feedback_sources = [
        reviewer_feedback,
        evaluation.feedback,
        "\n".join(evaluation.issues),
    ]
    for text in feedback_sources:
        slide_numbers.extend(_extract_slide_numbers_from_text(text, total_slides=total_slides))

    slide_numbers = _normalize_slide_numbers(slide_numbers, total_slides=total_slides)
    return slide_numbers or all_slides


def _merge_image_results(
    *,
    existing_images: list,
    regenerated_images: list,
    total_slides: int,
) -> list:
    merged_by_slide: dict[int, object] = {}

    for index, image in enumerate(existing_images, start=1):
        slide_number = image.slide_number or index
        if 1 <= slide_number <= total_slides:
            merged_by_slide[slide_number] = image if image.slide_number else image.model_copy(update={"slide_number": slide_number})

    for image in regenerated_images:
        slide_number = image.slide_number
        if slide_number and 1 <= slide_number <= total_slides:
            baseline = merged_by_slide.get(slide_number)
            update_data = {}
            if baseline is not None:
                if not getattr(image, "review_summary", "") and getattr(baseline, "review_summary", ""):
                    update_data["review_summary"] = baseline.review_summary
                if not getattr(image, "visible_text", "") and getattr(baseline, "visible_text", ""):
                    update_data["visible_text"] = baseline.visible_text
            merged_by_slide[slide_number] = image if not update_data else image.model_copy(update=update_data)

    return [merged_by_slide[slide_number] for slide_number in sorted(merged_by_slide)]


def _parse_prompt_review_result(content: str, *, total_slides: int) -> PromptReviewResult:
    data = json.loads(_normalize_json_payload(content))
    parsed = PromptReviewResult(**data)
    slide_reviews = [review for review in parsed.slide_reviews if 1 <= review.slide_number <= total_slides]
    return parsed.model_copy(update={"slide_reviews": slide_reviews})


def _apply_image_carousel_sequence_guardrails(slides: list[GeneratedImage], *, total_slides: int) -> list[GeneratedImage]:
    guarded_slides: list[GeneratedImage] = []

    for slide_number, slide in enumerate(slides[:total_slides], start=1):
        role = "portada gancho" if slide_number == 1 else "cierre" if slide_number == total_slides else "desarrollo"
        sequence_notes = [
            f"Este frame es el slide {slide_number} de {total_slides} del mismo carrusel.",
            f"Rol del slide: {role}.",
            "Mantené exactamente el mismo sistema visual que el resto del carrusel: tipografía, grilla, paleta, espaciado, tratamiento gráfico y jerarquía.",
            "Preferí titulares sin numeración visible. Si usás números, pasos, errores o contadores en el texto visible, tienen que coincidir exactamente con este slide.",
            "Nunca hagas que este slide parezca pertenecer a otra posición de la secuencia.",
        ]

        if slide_number == 1:
            sequence_notes.append(
                "Portada únicamente: gancho fuerte. Nunca muestres numeración visible como 'ERROR 2', 'Paso 3' o cualquier etiqueta que implique que no es el primer slide."
            )
        elif slide_number == total_slides:
            sequence_notes.append(
                "Cierre únicamente: resolvé la idea con takeaway o CTA. No uses un título de slide intermedio ni una numeración que parezca continuidad abierta."
            )
        else:
            sequence_notes.append(
                "Slide intermedio únicamente: desarrollá un punto concreto que conecte de forma lógica con el anterior y el siguiente."
            )

        base_prompt = slide.prompt.strip() or "Carrusel empresarial sobrio para redes"
        guarded_slides.append(
            slide.model_copy(update={
                "slide_number": slide_number,
                "prompt": f"{base_prompt}\n\n" + "\n".join(sequence_notes),
            })
        )

    return guarded_slides


async def _generate_image_prompt_draft(strategy, context: str, settings, *, reference_bundle: dict | None = None) -> tuple[list[GeneratedImage], str]:
    prompt = DESIGNER_IMAGE_SYSTEM.format(brand_name=settings.brand_name)
    user_msg = HumanMessage(content=_build_designer_user_content(
        context_text=context,
        reference_bundle=reference_bundle,
        extra_text=f"Number of images requested: {strategy.num_images}",
    ))

    llm = get_main_llm(temperature=0.8)
    response = await llm.ainvoke([SystemMessage(content=prompt), user_msg])

    try:
        data = json.loads(_normalize_json_payload(response.content))
        slide_items = data.get("slides", []) or data.get("prompts", [])
        style_notes = data.get("style_notes", "")
    except (json.JSONDecodeError, Exception):
        logger.warning("Failed to parse designer image response — using conservative default prompt")
        slide_items = [f"Professional tech illustration about: {strategy.topic}"]
        style_notes = ""

    slide_plans = _ensure_image_plan_count(
        slide_items,
        total_slides=strategy.num_images,
        topic=strategy.topic,
    )
    slide_plans = _apply_image_carousel_sequence_guardrails(
        slide_plans,
        total_slides=strategy.num_images,
    )
    return slide_plans, style_notes


async def _review_image_prompts(
    strategy,
    context: str,
    settings,
    prompts: list[GeneratedImage],
    *,
    reference_bundle: dict | None = None,
    style_notes: str = "",
) -> PromptReviewResult:
    qa_prompt = DESIGNER_IMAGE_QA_SYSTEM.format(brand_name=settings.brand_name)
    prompt_list = "\n".join(f"Slide {image.slide_number or index}: {image.prompt}" for index, image in enumerate(prompts, start=1))
    review_context = "\n\n".join([
        context,
        f"Style notes: {style_notes}" if style_notes else "",
        f"Prompt set to review:\n{prompt_list}",
    ]).strip()

    user_msg = HumanMessage(content=_build_designer_user_content(
        context_text=review_context,
        reference_bundle=reference_bundle,
    ))
    llm = get_small_llm(temperature=0.1)
    response = await llm.ainvoke([SystemMessage(content=qa_prompt), user_msg])

    try:
        return _parse_prompt_review_result(response.content, total_slides=strategy.num_images)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Failed to parse prompt QA response: %s — continuing with current prompt draft", exc)
        return PromptReviewResult(approved=True, feedback="Prompt QA unavailable", issues=["Prompt QA returned invalid JSON."])


async def _prepare_image_prompts(strategy, context: str, settings, *, reference_bundle: dict | None = None) -> tuple[list[GeneratedImage], str]:
    slide_plans, style_notes = await _generate_image_prompt_draft(
        strategy,
        context,
        settings,
        reference_bundle=reference_bundle,
    )

    prompt_review = await _review_image_prompts(
        strategy,
        context,
        settings,
        slide_plans,
        reference_bundle=reference_bundle,
        style_notes=style_notes,
    )
    if prompt_review.approved:
        return slide_plans, style_notes

    logger.info("Prompt QA requested a second prompt pass before image generation")
    review_feedback = prompt_review.feedback or "; ".join(prompt_review.issues)
    slide_feedback = _format_slide_reviews(prompt_review.slide_reviews)
    revision_context = (
        f"{context}\n\n"
        f"⚠️ PROMPT QA REQUIRED BEFORE IMAGE GENERATION\n"
        f"General feedback: {review_feedback}\n"
        f"Slide-specific feedback:\n{slide_feedback or '- Ajustar el set completo manteniendo coherencia.'}\n\n"
        f"Current prompt draft:\n"
        + "\n".join(f"Slide {image.slide_number or index}: {image.prompt}" for index, image in enumerate(slide_plans, start=1))
        + "\n\nReescribí el set completo corrigiendo sólo lo necesario y manteniendo coherencia fuerte con el sistema visual actual."
    )

    revised_prompts, revised_style_notes = await _generate_image_prompt_draft(
        strategy,
        revision_context,
        settings,
        reference_bundle=reference_bundle,
    )
    second_review = await _review_image_prompts(
        strategy,
        revision_context,
        settings,
        revised_prompts,
        reference_bundle=reference_bundle,
        style_notes=revised_style_notes,
    )
    if not second_review.approved:
        logger.warning("Prompt QA still has concerns after the second prompt pass: %s", second_review.feedback)

    return revised_prompts, revised_style_notes or style_notes


async def _plan_images(strategy, context: str, settings, *, reference_bundle: dict | None = None) -> DesignerOutput:
    slide_plans, style_notes = await _prepare_image_prompts(
        strategy,
        context,
        settings,
        reference_bundle=reference_bundle,
    )
    return DesignerOutput(images=slide_plans, style_notes=style_notes)


async def _load_published_post_reference_bundle(*, settings, strategy) -> dict | None:
    if not strategy or strategy.content_type != ContentType.IMAGE_POST:
        return None

    return build_published_post_reference_bundle(
        strategy=strategy,
    )


def _append_video_outro_requirements(prompt: str) -> str:
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        return VIDEO_OUTRO_REQUIREMENTS.strip()
    return f"{cleaned_prompt}\n\n{VIDEO_OUTRO_REQUIREMENTS.strip()}"


def _build_video_plan_summary(data: dict, composite_draft: _CompositeVideoDraft) -> str:
    summary = str(data.get("review_summary", "") or "").strip()
    if summary:
        return summary

    supporting_summary = "; ".join(clip.purpose for clip in composite_draft.supporting_clips if clip.purpose)
    if supporting_summary:
        return (
            f"Video de aproximadamente {composite_draft.duration_seconds}s con narrativa principal en pantalla y apoyo visual en: "
            f"{supporting_summary}."
        )

    return f"Video de aproximadamente {composite_draft.duration_seconds}s con narración principal clara, texto sobre video y cierre corto de marca."


def _build_planned_video_from_draft(data: dict, composite_draft: _CompositeVideoDraft) -> GeneratedVideo:
    raw_supporting_clips = data.get("supporting_clips") or []
    planned_clips: list[PlannedVideoClip] = []
    for index, clip in enumerate(composite_draft.supporting_clips):
        raw_clip = raw_supporting_clips[index] if index < len(raw_supporting_clips) and isinstance(raw_supporting_clips[index], dict) else {}
        planned_clips.append(
            PlannedVideoClip(
                prompt=clip.prompt,
                purpose=clip.purpose,
                review_summary=str(raw_clip.get("review_summary", "") or "").strip() or clip.purpose or clip.prompt,
                start_second=clip.start_second,
                duration_seconds=clip.duration_seconds,
                transition=clip.transition,
            )
        )

    fallback_prompt = planned_clips[0].prompt if planned_clips else ""
    return GeneratedVideo(
        prompt=str(data.get("prompt", "") or "").strip() or fallback_prompt,
        review_summary=_build_video_plan_summary(data, composite_draft),
        avatar_script=composite_draft.avatar_script,
        supporting_clips=planned_clips,
        avatar_intro_seconds=int(round(composite_draft.avatar_intro_seconds)),
        avatar_outro_seconds=int(round(composite_draft.avatar_outro_seconds)),
        duration_seconds=composite_draft.duration_seconds,
        video_template=str(data.get("video_template", "") or "story_explainer"),
    )


def _append_video_rendering_requirements(prompt: str, *, context: str = "") -> str:
    cleaned_prompt = prompt.strip()
    requirements = [VIDEO_RENDERING_REQUIREMENTS.strip()]
    normalized_context = context.lower()
    agent_tutorial_keywords = (
        "langchain",
        "langgraph",
        "openclaw",
        "subagente",
        "subagentes",
        "workflow",
        "nodos",
        "grafo",
        "graph",
        "python",
    )
    if any(keyword in normalized_context for keyword in agent_tutorial_keywords):
        requirements.append(VIDEO_AGENT_TUTORIAL_REQUIREMENTS.strip())

    if not cleaned_prompt:
        return "\n\n".join(requirements)
    return "\n\n".join([cleaned_prompt, *requirements])


def _default_supporting_clip_prompts(context: str) -> list[CompositeSupportClipPlan]:
    context_slice = context[:220].strip()
    return [
        CompositeSupportClipPlan(
            prompt=(
                "Screencast técnico realista de editor Python, terminal y diff visible, "
                f"explicando esta idea de negocio/software: {context_slice}"
            ),
            purpose="Mostrar código o implementación concreta",
            duration_seconds=8,
            start_second=5.0,
            transition="dissolve",
        ),
        CompositeSupportClipPlan(
            prompt=(
                "Demo sobria de canvas de agentes o workflow con nodos conectados, zooms suaves y labels legibles en español, "
                f"alineada con: {context_slice}"
            ),
            purpose="Mostrar el flujo o la arquitectura detrás de la explicación",
            duration_seconds=8,
            start_second=14.5,
            transition="dissolve",
        ),
        CompositeSupportClipPlan(
            prompt=(
                "Pantalla tipo dashboard operativo o documentación ejecutiva realista, con foco en impacto de negocio, "
                f"relacionada con: {context_slice}"
            ),
            purpose="Aterrizar el impacto operativo o comercial",
            duration_seconds=4,
            start_second=24.0,
            transition="dissolve",
        ),
    ]


def _build_composite_video_draft(data: dict, *, context: str) -> _CompositeVideoDraft:
    avatar_script = str(data.get("avatar_script", "") or "").strip()
    if not avatar_script:
        avatar_script = (
            "Hoy te muestro un caso concreto donde un agente bien diseñado te saca trabajo operativo de encima. "
            "No se trata de meter IA por moda. Se trata de decidir dónde conviene usarla, cómo medir el impacto y qué parte del proceso vale automatizar de verdad. "
            "Cuando eso está bien resuelto, el equipo gana tiempo, baja fricción y deja de improvisar herramientas que después nadie sostiene."
        )

    avatar_intro_seconds = _coerce_storyboard_seconds(
        data.get("avatar_intro_seconds"),
        default=DEFAULT_AVATAR_INTRO_SECONDS,
    )
    avatar_outro_seconds = _coerce_storyboard_seconds(
        data.get("avatar_outro_seconds"),
        default=DEFAULT_AVATAR_OUTRO_SECONDS,
    )

    clip_items = data.get("supporting_clips") or []
    clip_specs: list[dict] = []
    for item in clip_items[:1]:
        if not isinstance(item, dict):
            continue
        prompt = _append_video_rendering_requirements(str(item.get("prompt", "") or "").strip(), context=context)
        if not prompt:
            continue
        clip_specs.append(
            {
                "prompt": prompt,
                "purpose": str(item.get("purpose", "") or "").strip(),
                "duration_seconds": item.get("duration_seconds"),
                "start_second": item.get("start_second"),
                "transition": item.get("transition"),
            }
        )

    clip_specs = clip_specs[:1]

    raw_duration = data.get("duration_seconds", FIXED_VIDEO_DURATION_SECONDS)
    try:
        duration_seconds = int(raw_duration)
    except (TypeError, ValueError):
        duration_seconds = FIXED_VIDEO_DURATION_SECONDS

    normalized_total_duration = max(16, min(duration_seconds, FIXED_VIDEO_DURATION_SECONDS))
    clip_durations = [
        _default_supporting_clip_duration(index) if spec.get("duration_seconds") is None else _normalize_support_clip_duration(spec.get("duration_seconds"))
        for index, spec in enumerate(clip_specs)
    ]
    default_starts = _build_default_support_clip_starts(
        total_duration_seconds=normalized_total_duration,
        clip_durations=clip_durations,
        avatar_intro_seconds=avatar_intro_seconds,
        avatar_outro_seconds=avatar_outro_seconds,
    )

    supporting_clips: list[CompositeSupportClipPlan] = []
    for index, spec in enumerate(clip_specs):
        supporting_clips.append(
            CompositeSupportClipPlan(
                prompt=str(spec["prompt"]),
                purpose=str(spec["purpose"]),
                duration_seconds=clip_durations[index],
                start_second=_coerce_storyboard_seconds(
                    spec.get("start_second"),
                    default=default_starts[index],
                ),
                transition=_normalize_support_clip_transition(spec.get("transition")),
            )
        )

    return _CompositeVideoDraft(
        avatar_script=avatar_script,
        supporting_clips=supporting_clips,
        style_notes=str(data.get("style_notes", "") or "").strip(),
        duration_seconds=normalized_total_duration,
        avatar_intro_seconds=avatar_intro_seconds,
        avatar_outro_seconds=avatar_outro_seconds,
    )


async def designer_node(state: CommunityManagerState) -> dict:
    """Generate visual content based on strategy and copy."""
    logger.info("▶ Designer node starting")

    settings = get_settings()
    strategy = state.get("strategy")
    copy = state.get("copy")
    evaluation = state.get("evaluation")
    materialize_media = bool(state.get("materialize_media"))

    if not strategy:
        logger.warning("No strategy found — skipping designer")
        return {"design": DesignerOutput()}

    content_type = strategy.content_type

    # If text-only, no visual needed
    if content_type == ContentType.TEXT_POST:
        logger.info("Text-only post — designer skipped")
        return {"design": DesignerOutput()}

    # Build context for prompt generation
    context = (
        f"Topic: {strategy.topic}\n"
        f"Angle: {strategy.angle}\n"
        f"Objective: {strategy.objective}\n"
        f"Tone: {strategy.tone.value}\n"
        f"Language: {strategy.language}\n"
        f"Supporting points: {', '.join(strategy.supporting_points)}\n"
    )
    if hasattr(strategy, "video_template"):
        context += f"Video template: {strategy.video_template.value if hasattr(strategy.video_template, 'value') else strategy.video_template}\n"
    if copy:
        context += f"Caption: {copy.caption[:300]}\n"

    if evaluation and not evaluation.approved and evaluation.retry_target == "designer":
        context += (
            f"\n⚠️ REVISION REQUIRED — Evaluator feedback:\n"
            f"{evaluation.feedback}\n"
            f"Issues: {', '.join(evaluation.issues)}"
        )

    reviewer_memory = state.get("reviewer_memory", "")
    if reviewer_memory:
        context += f"\nReviewer memory to avoid repeated mistakes:\n{reviewer_memory}\n"

    reviewer_feedback = state.get("reviewer_feedback", "")
    if reviewer_feedback:
        context += f"\nCurrent reviewer feedback to incorporate:\n{reviewer_feedback}\n"

    retry_slide_numbers = _resolve_retry_slide_numbers(
        strategy=strategy,
        evaluation=evaluation,
        reviewer_feedback=reviewer_feedback,
    )
    existing_design = state.get("design")
    if (
        content_type == ContentType.IMAGE_POST
        and existing_design
        and existing_design.images
        and evaluation
        and not evaluation.approved
        and evaluation.retry_target == "designer"
    ):
        existing_prompts = _describe_existing_slide_prompts(existing_design)
        if existing_prompts:
            context += f"\nCurrent approved/reviewed slide prompts to preserve as baseline:\n{existing_prompts}\n"
        if retry_slide_numbers and len(retry_slide_numbers) < strategy.num_images:
            context += (
                "\nOnly revise and regenerate these slides: "
                + ", ".join(str(slide_number) for slide_number in retry_slide_numbers)
                + ". Preserve the approved slides as they are and keep strict visual continuity.\n"
            )
        slide_feedback = _format_slide_reviews(evaluation.slide_reviews)
        if slide_feedback:
            context += f"\nSlide-specific evaluator feedback:\n{slide_feedback}\n"

    reference_bundle = build_training_reference_bundle(
        strategy=strategy,
        reviewer_feedback=reviewer_feedback,
    )
    if reference_bundle:
        logger.info(
            "Using training references for %s due to reviewer realism feedback: %s",
            content_type.value,
            ", ".join(reference_bundle["assets"]),
        )

    logo_reference_bundle = build_brand_logo_reference_bundle(strategy=strategy)
    if logo_reference_bundle:
        logger.info(
            "Using official logo references for %s: %s",
            content_type.value,
            ", ".join(logo_reference_bundle["assets"]),
        )

    presenter_reference_bundle = build_presenter_reference_bundle(strategy=strategy)
    if presenter_reference_bundle:
        logger.info(
            "Using consistent presenter references for %s: %s",
            content_type.value,
            ", ".join(presenter_reference_bundle["assets"]),
        )

    avatar_background_bundle = build_avatar_background_reference_bundle(strategy=strategy)
    if avatar_background_bundle:
        logger.info(
            "Using fixed office background references for %s: %s",
            content_type.value,
            ", ".join(avatar_background_bundle["assets"]),
        )

    published_reference_bundle = await _load_published_post_reference_bundle(settings=settings, strategy=strategy)
    if published_reference_bundle:
        logger.info(
            "Using %d local curated published reference slide(s) for %s",
            len(published_reference_bundle["assets"]),
            content_type.value,
        )

    reference_bundle = merge_reference_bundles(
        reference_bundle,
        logo_reference_bundle,
        presenter_reference_bundle,
        avatar_background_bundle,
        published_reference_bundle,
    )

    # ── Image post ─────────────────────────────────────────────
    if content_type == ContentType.IMAGE_POST:
        should_refresh_plan = not existing_design or not existing_design.images or (
            evaluation and not evaluation.approved and evaluation.retry_target == "designer"
        )
        if materialize_media:
            planned_design = await _plan_images(
                strategy,
                context,
                settings,
                reference_bundle=reference_bundle,
            ) if should_refresh_plan else existing_design.model_copy(deep=True)
            design = await _generate_images(
                strategy,
                settings,
                planned_design=planned_design,
                existing_design=existing_design,
                retry_slide_numbers=retry_slide_numbers,
            )
        else:
            design = await _plan_images(
                strategy,
                context,
                settings,
                reference_bundle=reference_bundle,
            )
    # ── Video post ─────────────────────────────────────────────
    elif content_type == ContentType.VIDEO_POST:
        should_refresh_plan = not existing_design or not existing_design.video or (
            evaluation and not evaluation.approved and evaluation.retry_target == "designer"
        )
        if materialize_media:
            planned_design = await _plan_video(
                context,
                settings,
                strategy.video_duration_seconds,
                reference_bundle=reference_bundle,
            ) if should_refresh_plan else existing_design.model_copy(deep=True)
            design = await _generate_video(
                settings,
                strategy.video_duration_seconds,
                planned_design=planned_design,
            )
        else:
            design = await _plan_video(
                context,
                settings,
                strategy.video_duration_seconds,
                reference_bundle=reference_bundle,
            )
    else:
        design = DesignerOutput()

    return {
        "design": design,
        "messages": [],
    }


async def _generate_images(
    strategy,
    settings,
    *,
    planned_design: DesignerOutput,
    existing_design: DesignerOutput | None = None,
    retry_slide_numbers: list[int] | None = None,
) -> DesignerOutput:
    """Render real images from an already reviewed image plan."""
    slide_plans = planned_design.images or []
    style_notes = planned_design.style_notes
    if not slide_plans:
        return DesignerOutput(style_notes=style_notes)

    requested_image_model = getattr(strategy, "image_model", "image_2")
    if hasattr(requested_image_model, "value"):
        requested_image_model = requested_image_model.value

    requested_image_quality = getattr(strategy, "image_quality", settings.azure_foundry_dalle_quality)
    if hasattr(requested_image_quality, "value"):
        requested_image_quality = requested_image_quality.value

    if not settings.is_image_generation_model_configured(requested_image_model):
        logger.warning(
            "Image generation profile '%s' is not configured — returning no images so publication fails closed",
            requested_image_model,
        )
        return DesignerOutput(style_notes=style_notes)

    target_slide_numbers = _normalize_slide_numbers(
        retry_slide_numbers or list(range(1, strategy.num_images + 1)),
        total_slides=strategy.num_images,
    )
    plan_by_slide = {
        (image.slide_number or index): image
        for index, image in enumerate(slide_plans, start=1)
    }
    prompts_to_generate = [plan_by_slide[slide_number].prompt for slide_number in target_slide_numbers]

    # Call Azure image generation
    logger.info(
        "Rendering image carousel with model=%s quality=%s",
        requested_image_model,
        requested_image_quality,
    )
    client = ImageGenClient(image_model=requested_image_model, quality=requested_image_quality)
    try:
        regenerated_images = await client.generate_images(
            prompts_to_generate,
            slide_numbers=target_slide_numbers,
        )
        merged_images = _merge_image_results(
            existing_images=(existing_design.images if existing_design else slide_plans),
            regenerated_images=regenerated_images,
            total_slides=strategy.num_images,
        )
        logger.info(
            "✅ Generated %d image(s) for slides %s",
            len(regenerated_images),
            ", ".join(str(slide_number) for slide_number in target_slide_numbers),
        )
        return DesignerOutput(images=merged_images, style_notes=style_notes)
    finally:
        await client.close()


async def _plan_video(context: str, settings, requested_duration_seconds: int, *, reference_bundle: dict | None = None) -> DesignerOutput:
    """Create a structured, human-reviewable video plan without generating media yet."""
    prompt = DESIGNER_VIDEO_SYSTEM.format(brand_name=settings.brand_name)
    user_msg = HumanMessage(content=_build_designer_user_content(
        context_text=context,
        reference_bundle=reference_bundle,
    ))

    llm = get_main_llm(temperature=0.8)
    response = await llm.ainvoke([SystemMessage(content=prompt), user_msg])

    try:
        data = json.loads(_normalize_json_payload(response.content))
        composite_draft = _build_composite_video_draft(data, context=context)
        style_notes = composite_draft.style_notes
    except (json.JSONDecodeError, Exception):
        logger.warning("Failed to parse designer composite video response — using structured fallback")
        data = {}
        composite_draft = _build_composite_video_draft({}, context=context)
        style_notes = composite_draft.style_notes

    return DesignerOutput(
        video=_build_planned_video_from_draft(data, composite_draft),
        style_notes=style_notes,
    )


async def _generate_video(settings, requested_duration_seconds: int, *, planned_design: DesignerOutput) -> DesignerOutput:
    """Render a final video from an already approved video plan."""
    planned_video = planned_design.video
    style_notes = planned_design.style_notes
    if not planned_video:
        return DesignerOutput(style_notes=style_notes)

    if settings.is_avatar_generation_configured and settings.is_video_generation_configured:
        client = CompositeVideoClient()
        try:
            plan = CompositeVideoPlan(
                avatar_script=planned_video.avatar_script,
                supporting_clips=[
                    CompositeSupportClipPlan(
                        prompt=clip.prompt,
                        purpose=clip.purpose,
                        duration_seconds=clip.duration_seconds,
                        start_second=clip.start_second,
                        transition=clip.transition,
                    )
                    for clip in planned_video.supporting_clips
                ],
                duration_seconds=max(requested_duration_seconds, planned_video.duration_seconds),
                style_notes=style_notes,
                avatar_intro_seconds=planned_video.avatar_intro_seconds or DEFAULT_AVATAR_INTRO_SECONDS,
                avatar_outro_seconds=planned_video.avatar_outro_seconds or DEFAULT_AVATAR_OUTRO_SECONDS,
            )
            video = await client.generate_video(plan)
            logger.info("✅ Composite avatar video generated: %s", video.local_path)
            return DesignerOutput(
                video=planned_video.model_copy(update={
                    "prompt": video.prompt,
                    "duration_seconds": video.duration_seconds,
                    "local_path": video.local_path,
                    "url": video.url,
                    "blob_name": video.blob_name,
                    "job_id": video.job_id,
                }),
                style_notes=style_notes,
            )
        finally:
            await client.close()

    logger.warning(
        "Composite avatar video pipeline is not fully configured; falling back to legacy single Sora video"
    )

    sora_prompt = _append_video_outro_requirements(
        _append_video_rendering_requirements(
            planned_video.prompt
            or (planned_video.supporting_clips[0].prompt if planned_video.supporting_clips else "")
            or planned_video.review_summary,
            context=planned_video.review_summary,
        )
    )
    duration = requested_duration_seconds

    if not settings.is_video_generation_configured:
        logger.warning("Video generation not configured — returning no video so publication fails closed")
        return DesignerOutput(style_notes=style_notes)

    # Call Sora 2
    client = SoraClient()
    try:
        video = await client.generate_video(sora_prompt, duration_seconds=duration)
        logger.info("✅ Video generated: %s", video.local_path)
        return DesignerOutput(
            video=planned_video.model_copy(update={
                "prompt": video.prompt,
                "duration_seconds": video.duration_seconds,
                "local_path": video.local_path,
                "url": video.url,
                "blob_name": video.blob_name,
                "job_id": video.job_id,
            }),
            style_notes=style_notes,
        )
    finally:
        await client.close()

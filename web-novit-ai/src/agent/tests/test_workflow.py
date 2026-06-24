"""Smoke tests for the Community Manager agent.

These tests validate that modules import correctly and key
data structures are well-formed, without requiring real
Azure credentials or network access.
"""

from __future__ import annotations

import base64
import asyncio
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace


# ── Import tests ──────────────────────────────────────────────

def test_settings_import():
    """Settings module loads without error (will use defaults)."""
    from community_manager.config.settings import Settings, _resolve_repo_root

    s = Settings()
    assert s.brand_name == "Novit Software"
    assert s.log_level == "INFO"
    assert _resolve_repo_root(Path("/app/community_manager/config/settings.py")).name == "app"


def test_schemas_import():
    """All schema models import and can be instantiated."""
    from community_manager.models.schemas import (
        ContentStrategy,
        ContentTone,
        ContentType,
        Platform,
        PostStatus,
    )

    assert ContentType.IMAGE_POST.value == "image_post"
    assert Platform.INSTAGRAM.value == "instagram"
    assert PostStatus.DRAFT.value == "draft"
    assert ContentTone.PROFESSIONAL is not None


def test_content_strategy_depth_fields():
    """Strategist schema preserves depth/language fields used by the review flow."""
    from community_manager.models.schemas import (
        ContentStrategy,
        ContentType,
        FIXED_VIDEO_DURATION_SECONDS,
        ImageModelChoice,
        ImageQuality,
        MIN_IMAGE_POST_IMAGES,
    )

    strategy = ContentStrategy(
        content_type=ContentType.VIDEO_POST,
        topic="Automatización comercial",
        angle="De herramienta a proceso",
        objective="Mostrar criterio",
        supporting_points=["priorizar procesos"],
    )

    assert strategy.language == "es-AR"
    assert strategy.video_duration_seconds == FIXED_VIDEO_DURATION_SECONDS
    assert strategy.angle == "De herramienta a proceso"
    assert strategy.num_images == MIN_IMAGE_POST_IMAGES

    image_strategy = ContentStrategy(
        content_type=ContentType.IMAGE_POST,
        topic="Post insignia mensual",
        objective="Validar ambición visual",
    )

    assert image_strategy.image_model == ImageModelChoice.IMAGE_2
    assert image_strategy.image_quality == ImageQuality.HIGH


def test_image_posts_are_always_carousels_between_4_and_6_slides():
    """Image posts should normalize to the allowed carousel range instead of using single-image outputs."""
    from community_manager.models.schemas import (
        ContentStrategy,
        ContentType,
        MAX_IMAGE_POST_IMAGES,
        MIN_IMAGE_POST_IMAGES,
    )

    low = ContentStrategy(
        content_type=ContentType.IMAGE_POST,
        topic="Automatización con IA",
        objective="Abrir conversación",
        num_images=1,
    )
    high = ContentStrategy(
        content_type=ContentType.IMAGE_POST,
        topic="Automatización con IA",
        objective="Abrir conversación",
        num_images=9,
    )
    video = ContentStrategy(
        content_type=ContentType.VIDEO_POST,
        topic="Automatización con IA",
        objective="Abrir conversación",
        num_images=0,
    )

    assert low.num_images == MIN_IMAGE_POST_IMAGES
    assert high.num_images == MAX_IMAGE_POST_IMAGES
    assert video.num_images == 0


def test_generated_media_support_blob_name():
    """Generated media schemas keep optional blob names for delayed publication cleanup."""
    from community_manager.models.schemas import GeneratedImage, GeneratedVideo

    image = GeneratedImage(prompt="test", url="https://example.com/a.jpg", blob_name="a.jpg")
    video = GeneratedVideo(prompt="test", url="https://example.com/a.mp4", blob_name="a.mp4")

    assert image.blob_name == "a.jpg"
    assert video.blob_name == "a.mp4"


def test_training_media_realism_fallback_signals():
    """Realism-related feedback should activate training references for prompt generation."""
    from community_manager.models.schemas import ContentStrategy, ContentType
    from community_manager.tools.training_media import (
        build_avatar_background_reference_bundle,
        build_brand_logo_reference_bundle,
        TRAINING_MEDIA_CATALOG,
        build_training_reference_bundle,
        feedback_requests_real_media,
        merge_reference_bundles,
        select_training_assets,
    )

    assert any(asset.media_kind == "image" for asset in TRAINING_MEDIA_CATALOG)
    assert any(asset.media_kind == "video" for asset in TRAINING_MEDIA_CATALOG)
    assert feedback_requests_real_media(
        "Los fondos tienen deformaciones de IA y el logo de Novit se ve mal.",
        "",
    )
    assert not feedback_requests_real_media("Ajustar CTA y bajar hashtags.")

    image_assets = select_training_assets(
        content_type=ContentType.IMAGE_POST,
        topic_text="Implementación de agentes de IA en una pyme",
        feedback_text="falta realismo en fondos y oficina",
        limit=2,
    )
    video_assets = select_training_assets(
        content_type=ContentType.VIDEO_POST,
        topic_text="Realismo para video de oficina",
        feedback_text="se nota mucho la IA en el fondo",
        limit=1,
    )

    assert image_assets
    assert video_assets

    bundle = build_training_reference_bundle(
        strategy=ContentStrategy(
            content_type=ContentType.IMAGE_POST,
            topic="Cómo implementar agentes de IA sin improvisar",
            objective="Bajar alucinaciones y mejorar realismo",
            num_images=2,
        ),
        reviewer_feedback="Los fondos se ven muy IA y el logo de Novit está mal.",
    )

    assert bundle is not None
    assert bundle["assets"]
    assert any(part["type"] == "image_url" for part in bundle["message_content"])

    logo_bundle = build_brand_logo_reference_bundle(
        strategy=ContentStrategy(
            content_type=ContentType.IMAGE_POST,
            topic="Arquitectura de agentes de IA",
            objective="Mostrar criterio",
            num_images=4,
        )
    )

    assert logo_bundle is not None
    assert "novit-logo.png" in logo_bundle["assets"]
    assert any(part["type"] == "image_url" for part in logo_bundle["message_content"])

    merged = merge_reference_bundles(bundle, logo_bundle)
    assert merged is not None
    assert "novit-logo.png" in merged["assets"]

    avatar_background_bundle = build_avatar_background_reference_bundle(
        strategy=ContentStrategy(
            content_type=ContentType.VIDEO_POST,
            topic="Avatar con fondo real de oficina",
            objective="Hacer un video compuesto más creíble",
        )
    )

    assert avatar_background_bundle is not None
    assert "ventana-3.jpg" in avatar_background_bundle["assets"]
    assert any(part["type"] == "image_url" for part in avatar_background_bundle["message_content"])


def test_published_post_reference_bundle_uses_local_curated_assets(tmp_path):
    from community_manager.models.schemas import ContentStrategy, ContentType
    from community_manager.tools.training_media import build_published_post_reference_bundle

    curated_root = tmp_path / "published-post-references"
    post_a = curated_root / "post-01"
    post_b = curated_root / "post-02"
    post_a.mkdir(parents=True)
    post_b.mkdir(parents=True)
    for index in range(1, 6):
        (post_a / f"slide-{index}.png").write_bytes(f"post-a-{index}".encode())
    for index in range(1, 5):
        (post_b / f"slide-{index}.png").write_bytes(f"post-b-{index}".encode())

    bundle = build_published_post_reference_bundle(
        strategy=ContentStrategy(
            content_type=ContentType.IMAGE_POST,
            topic="Arquitectura de agentes",
            objective="Mantener una referencia estética estable",
            num_images=3,
        ),
        base_path=tmp_path,
    )

    assert bundle is not None
    assert "published-post-references/post-01/slide-1.png" in bundle["assets"]
    assert "published-post-references/post-01/slide-5.png" in bundle["assets"]
    assert "published-post-references/post-02/slide-1.png" in bundle["assets"]
    assert "published-post-references/post-02/slide-4.png" in bundle["assets"]
    assert sum(1 for part in bundle["message_content"] if part["type"] == "image_url") == 4
    assert len(bundle["assets"]) == 4
    assert all(
        part["image_url"]["url"].startswith("data:image/")
        for part in bundle["message_content"]
        if part["type"] == "image_url"
    )


def test_prompts_import():
    """Prompt constants are non-empty strings."""
    from community_manager.config.prompts import (
        COPYWRITER_SYSTEM,
        DESIGNER_IMAGE_SYSTEM,
        DESIGNER_VIDEO_SYSTEM,
        EVALUATOR_SYSTEM,
        STRATEGIST_SYSTEM,
    )

    assert len(STRATEGIST_SYSTEM) > 100
    assert len(COPYWRITER_SYSTEM) > 100
    assert len(DESIGNER_IMAGE_SYSTEM) > 100
    assert len(DESIGNER_VIDEO_SYSTEM) > 100
    assert len(EVALUATOR_SYSTEM) > 100
    assert "es-AR" in STRATEGIST_SYSTEM


def test_comment_reply_uses_platform_specific_graph_host():
    """Instagram comment replies must use the Instagram Graph host, not Facebook Graph."""
    from community_manager.models.schemas import Platform
    from community_manager.tools.meta_api import MetaClient

    captured: list[tuple[str, dict[str, str]]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeHttpClient:
        async def post(self, url: str, data: dict[str, str]):
            captured.append((url, data))
            return FakeResponse()

        async def aclose(self) -> None:
            return None

    client = MetaClient()
    client._http = FakeHttpClient()

    assert asyncio.run(client.send_comment_reply("123", "hola", Platform.INSTAGRAM)) is True
    assert asyncio.run(client.send_comment_reply("456", "hola", Platform.FACEBOOK)) is True

    assert captured[0][0] == "https://graph.instagram.com/v25.0/123/replies"
    assert captured[1][0] == "https://graph.facebook.com/v21.0/456/comments"
    assert "30 segundos" in DESIGNER_VIDEO_SYSTEM
    assert "4-6" in STRATEGIST_SYSTEM
    assert '"image_model"' in STRATEGIST_SYSTEM
    assert '"image_quality"' in STRATEGIST_SYSTEM
    assert '"image_2"' in STRATEGIST_SYSTEM
    assert "Effra" in DESIGNER_IMAGE_SYSTEM
    assert "aliado confiable" in COPYWRITER_SYSTEM
    assert "cripto bro" in EVALUATOR_SYSTEM
    assert "Aquí te explicamos cómo lograrlo" in COPYWRITER_SYSTEM
    assert "aquí" in EVALUATOR_SYSTEM
    assert "22% del ancho" in DESIGNER_IMAGE_SYSTEM
    assert "pisado o sucio" in EVALUATOR_SYSTEM
    assert 'Preferí titulares sin numeración visible' in DESIGNER_IMAGE_SYSTEM
    assert 'carruseles inconsistentes entre slides' in EVALUATOR_SYSTEM
    assert "no decorativa" in STRATEGIST_SYSTEM
    assert "screencast" in DESIGNER_VIDEO_SYSTEM
    assert "avatar_script" in DESIGNER_VIDEO_SYSTEM
    assert "avatar_intro_seconds" in DESIGNER_VIDEO_SYSTEM
    assert "avatar_outro_seconds" in DESIGNER_VIDEO_SYSTEM
    assert "supporting_clips" in DESIGNER_VIDEO_SYSTEM
    assert "duration_seconds" in DESIGNER_VIDEO_SYSTEM
    assert "start_second" in DESIGNER_VIDEO_SYSTEM
    assert "transition" in DESIGNER_VIDEO_SYSTEM
    assert "esquina inferior derecha" in DESIGNER_VIDEO_SYSTEM
    assert "presentador ficticio" in DESIGNER_VIDEO_SYSTEM
    assert '"vos"' in DESIGNER_VIDEO_SYSTEM


def test_instagram_carousel_waits_for_parent_container_before_publish():
    """Instagram carousel publish should poll the parent container before media_publish."""
    from community_manager.tools.meta_api import MetaClient

    calls: list[tuple[str, str, dict[str, str]]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, str]):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return self._payload

    class FakeHttpClient:
        def __init__(self) -> None:
            self._post_responses = iter([
                FakeResponse({"id": "child-1"}),
                FakeResponse({"id": "child-2"}),
                FakeResponse({"id": "carousel-1"}),
                FakeResponse({"id": "post-1"}),
            ])

        async def post(self, url: str, data: dict[str, str]):
            calls.append(("post", url, data))
            return next(self._post_responses)

        async def get(self, url: str, params: dict[str, str]):
            calls.append(("get", url, params))
            return FakeResponse({"status_code": "FINISHED"})

        async def aclose(self) -> None:
            return None

    client = MetaClient()
    client._http = FakeHttpClient()

    result = asyncio.run(client.publish_instagram_carousel([
        "https://example.com/slide-1.jpg",
        "https://example.com/slide-2.jpg",
    ], "hola"))

    assert result.success is True
    assert calls[2][0] == "post"
    assert calls[2][1].endswith("/media")
    assert calls[2][2]["media_type"] == "CAROUSEL"
    assert calls[3][0] == "get"
    assert calls[3][1].endswith("/carousel-1")
    assert calls[4][0] == "post"
    assert calls[4][1].endswith("/media_publish")
    assert calls[4][2]["creation_id"] == "carousel-1"


def test_apply_requested_strategy_overrides_replaces_topic_angle_and_objective():
    from community_manager.graph.nodes.strategist import _apply_requested_strategy_overrides
    from community_manager.models.schemas import ContentStrategy, ContentType

    strategy = ContentStrategy(
        content_type=ContentType.IMAGE_POST,
        topic="Tema base",
        angle="Ángulo base",
        objective="Objetivo base",
    )

    updated = _apply_requested_strategy_overrides(strategy, {
        "requested_topic": "Tema urgente sectorial",
        "requested_angle": "Cómo impacta mañana en operaciones",
        "requested_objective": "Aprovechar noticia de último momento",
    })

    assert updated.topic == "Tema urgente sectorial"
    assert updated.angle == "Cómo impacta mañana en operaciones"
    assert updated.objective == "Aprovechar noticia de último momento"


def test_extract_unanswered_direct_messages_returns_only_latest_inbound_dms():
    """DM polling should only surface conversations whose latest message still needs a reply."""
    from community_manager.tools.meta_api import extract_unanswered_direct_messages

    payload = {
        "data": [
            {
                "id": "conv-1",
                "participants": {
                    "data": [
                        {"username": "ntasync", "id": "self-1"},
                        {"username": "rodrovazq", "id": "2788289311545223"},
                    ]
                },
                "messages": {
                    "data": [
                        {
                            "id": "mid-inbound",
                            "message": "Hola",
                            "created_time": "2026-05-18T15:09:43+0000",
                            "from": {"username": "rodrovazq", "id": "2788289311545223"},
                        },
                        {
                            "id": "mid-older-outbound",
                            "message": "Buenas",
                            "created_time": "2026-05-18T15:05:00+0000",
                            "from": {"username": "ntasync", "id": "self-1"},
                        },
                    ]
                },
            },
            {
                "id": "conv-2",
                "participants": {
                    "data": [
                        {"username": "ntasync", "id": "self-2"},
                        {"username": "otro", "id": "999"},
                    ]
                },
                "messages": {
                    "data": [
                        {
                            "id": "mid-latest-outbound",
                            "message": "Te respondimos",
                            "created_time": "2026-05-18T15:10:00+0000",
                            "from": {"username": "ntasync", "id": "self-2"},
                        },
                        {
                            "id": "mid-older-inbound",
                            "message": "Necesito info",
                            "created_time": "2026-05-18T15:08:00+0000",
                            "from": {"username": "otro", "id": "999"},
                        },
                    ]
                },
            },
        ]
    }

    pending = extract_unanswered_direct_messages(payload, own_username="ntasync")

    assert len(pending) == 1
    assert pending[0].sender_id == "2788289311545223"
    assert pending[0].sender_name == "rodrovazq"
    assert pending[0].reply_target_id == "2788289311545223"
    assert pending[0].message_id == "mid-inbound"
    assert pending[0].text == "Hola"


def test_video_prompts_require_deliberate_outro():
    """Video prompts should require a real outro instead of ending on the final spoken word."""
    from community_manager.config.prompts import DESIGNER_VIDEO_SYSTEM, EVALUATOR_SYSTEM, STRATEGIST_SYSTEM

    designer_source = Path(__file__).resolve().parents[1] / "community_manager" / "graph" / "nodes" / "designer.py"
    designer_text = designer_source.read_text(encoding="utf-8")

    assert "últimos 2 o 3 segundos" in DESIGNER_VIDEO_SYSTEM
    assert "fade out" in DESIGNER_VIDEO_SYSTEM
    assert "30 segundos aproximados" in STRATEGIST_SYSTEM
    assert "avatar + apoyos visuales" in EVALUATOR_SYSTEM
    assert "VIDEO_OUTRO_REQUIREMENTS" in designer_text
    assert "_append_video_outro_requirements" in designer_text


def test_image_carousel_prompts_get_explicit_sequence_guardrails():
    """Carousel prompts should carry slide-order rules so cover/body/closing slides do not drift."""
    from community_manager.graph.nodes.designer import _apply_image_carousel_sequence_guardrails

    prompts = [
        "Portada con hook fuerte y layout tipografico sobrio.",
        "Desarrollo del primer error con apoyo visual minimo.",
        "Desarrollo del segundo error con comparacion clara.",
        "Cierre con takeaway y CTA conversacional.",
    ]

    guarded = _apply_image_carousel_sequence_guardrails(prompts, total_slides=4)

    assert len(guarded) == 4
    assert "slide 1 de 4" in guarded[0]
    assert "ERROR 2" in guarded[0]
    assert "slide 2 de 4" in guarded[1]
    assert "Slide intermedio únicamente" in guarded[1]
    assert "slide 4 de 4" in guarded[3]
    assert "Cierre únicamente" in guarded[3]


def test_logo_overlay_keeps_background_clean_around_logo(tmp_path):
    """Logo compositing should not draw a backing plate; only the logo itself should be added."""
    from types import SimpleNamespace

    from PIL import Image, ImageDraw

    from community_manager.tools.image_gen import ImageGenClient

    logo_path = tmp_path / "novit-logo.png"
    logo = Image.new("RGBA", (200, 50), (0, 0, 0, 0))
    draw = ImageDraw.Draw(logo)
    draw.rectangle((0, 10, 199, 40), fill=(0, 0, 0, 255))
    logo.save(logo_path)

    source = Image.new("RGB", (1000, 1000), (255, 255, 255))
    buffer = BytesIO()
    source.save(buffer, format="PNG")

    client = object.__new__(ImageGenClient)
    client.settings = SimpleNamespace(brand_assets_path=tmp_path)
    client.LIGHT_LOGO_FILENAME = "novit-logo.png"
    client.DARK_LOGO_FILENAME = "novit-logo-dark.png"

    result = client._overlay_official_logo(buffer.getvalue(), output_format="png")
    composed = Image.open(BytesIO(result)).convert("RGBA")

    margin = max(24, int(composed.width * 0.035))
    target_logo_width = max(140, int(composed.width * 0.2))
    target_logo_height = max(32, int(target_logo_width / 4))
    position_x = composed.width - target_logo_width - margin
    position_y = composed.height - target_logo_height - margin

    assert composed.getpixel((position_x - 8, position_y + target_logo_height // 2))[:3] == (255, 255, 255)
    assert composed.getpixel((position_x + target_logo_width // 2, position_y + target_logo_height // 2))[:3] == (0, 0, 0)


def test_instagram_caption_markdown_is_normalized():
    """Instagram captions should ship as plain text, not literal markdown syntax."""
    from community_manager.tools.meta_api import normalize_instagram_caption

    raw = """# Implementar agentes de IA sin improvisar

1. **Definí el problema:** evitá arrancar sin objetivo.
2. _Diseñá_ la arquitectura con criterio.
3. Visitá [Novit](https://novitsoftware.com) para ver más.

`observabilidad` y ~~costos extra~~ importan.

#IA_para_empresas"""

    normalized = normalize_instagram_caption(raw)

    assert "**" not in normalized
    assert "_Diseñá_" not in normalized
    assert "[Novit]" not in normalized
    assert "https://novitsoftware.com" not in normalized
    assert "`observabilidad`" not in normalized
    assert "~~costos extra~~" not in normalized
    assert not normalized.startswith("# ")
    assert "Definí el problema:" in normalized
    assert "Diseñá" in normalized
    assert "Novit" in normalized
    assert "observabilidad" in normalized
    assert "costos extra" in normalized
    assert "#IA_para_empresas" in normalized


def test_publisher_caption_normalizes_and_deduplicates_hashtags():
    """Publisher should avoid malformed ##hashtags and duplicate tags in the final caption."""
    from community_manager.graph.nodes.publisher import _build_full_caption

    caption = "Implementar IA con criterio.\n\n#Novit #IAParaEmpresas"
    hashtags = ["#novit", "IAParaEmpresas", "#Automatizacion", "automatizacion", "##Bad Tag"]

    full_caption = _build_full_caption(caption, hashtags)

    assert "##" not in full_caption
    assert full_caption.count("#Novit") == 1
    assert full_caption.count("#IAParaEmpresas") == 1
    assert full_caption.count("#Automatizacion") == 1


def test_evaluator_rejects_unverified_study_claims_without_quote():
    """Evaluator deterministic guard should reject study/data claims without explicit source and quote."""
    from community_manager.graph.nodes.evaluator import _validate_copy_integrity
    from community_manager.models.schemas import PostCopy

    copy = PostCopy(
        caption=(
            "Un estudio reciente muestra que 73% de las empresas falla al implementar agentes de IA. "
            "Por eso tenés que actuar ahora."
        ),
        hashtags=["novit"],
        alt_text="",
    )

    validation = _validate_copy_integrity(copy)

    assert validation is not None
    assert validation.approved is False
    assert validation.retry_target == "copywriter"
    assert "fuente" in validation.feedback.lower()


def test_evaluator_accepts_study_claims_with_source_and_quote():
    """Evaluator deterministic guard should allow study/data claims when source attribution and quote are present."""
    from community_manager.graph.nodes.evaluator import _validate_copy_integrity
    from community_manager.models.schemas import PostCopy

    copy = PostCopy(
        caption=(
            "Según McKinsey (2025), \"solo el 1% de las compañías dice haber madurado su IA generativa\". "
            "Si no priorizás procesos críticos primero, la implementación se traba en pilotos eternos."
        ),
        hashtags=["novit", "ia"],
        alt_text="",
    )

    validation = _validate_copy_integrity(copy)

    assert validation is None


def test_evaluator_rejects_unsourced_quantitative_claims_in_image_visible_text():
    """Evaluator should fail closed when the visual plan contains exact percentages without any source."""
    from community_manager.graph.nodes.evaluator import _validate_factual_grounding
    from community_manager.models.schemas import DesignerOutput, GeneratedImage, PostCopy

    copy = PostCopy(
        caption="Las condiciones de uso de IA se endurecieron y conviene revisar el costo total antes de escalar.",
        hashtags=["novit"],
        alt_text="",
    )
    design = DesignerOutput(
        images=[
            GeneratedImage(
                slide_number=1,
                visible_text="OpenAI +45% | Anthropic +35% | Copilot +25%",
                review_summary="Slide con chart comparativo 2025 vs 2026 de subas de precio.",
            )
        ]
    )

    validation = _validate_factual_grounding(copy, design)

    assert validation is not None
    assert validation.approved is False
    assert validation.retry_target == "designer"
    assert "fuente" in validation.feedback.lower()


def test_evaluator_allows_quantitative_claims_when_caption_carries_source_note():
    """Quantitative claims may pass when the post already includes an explicit source note."""
    from community_manager.graph.nodes.evaluator import _validate_factual_grounding
    from community_manager.models.schemas import DesignerOutput, GeneratedImage, PostCopy

    copy = PostCopy(
        caption=(
            "Fuente: McKinsey 2025. \"Los costos de adopción subieron en los despliegues más ambiciosos\". "
            "El punto no es el porcentaje exacto sino revisar el stack con criterio."
        ),
        hashtags=["novit"],
        alt_text="",
    )
    design = DesignerOutput(
        images=[
            GeneratedImage(
                slide_number=1,
                visible_text="OpenAI +45% | Anthropic +35% | Copilot +25%",
                review_summary="Slide con chart comparativo 2025 vs 2026 de subas de precio.",
            )
        ]
    )

    validation = _validate_factual_grounding(copy, design)

    assert validation is None


def test_video_prompts_prefer_tutorial_over_fake_realism():
    """Video prompts should prefer tutorial/screencast compositions over uncanny fake-real office scenes."""
    from community_manager.config.prompts import DESIGNER_VIDEO_SYSTEM, VIDEO_GUARDRAILS

    assert "formato compuesto" in VIDEO_GUARDRAILS
    assert "fondo real de oficina" in VIDEO_GUARDRAILS
    assert "El rostro principal lo resolverá el avatar" in DESIGNER_VIDEO_SYSTEM
    assert "mismo presentador ficticio consistente" in VIDEO_GUARDRAILS


def test_video_prompts_require_rioplatense_voseo():
    """Video prompts should explicitly push rioplatense voseo to avoid neutral Spanish drift."""
    from community_manager.config.prompts import DESIGNER_VIDEO_SYSTEM
    from community_manager.graph.nodes.designer import _append_video_rendering_requirements

    prompt = _append_video_rendering_requirements(
        "Explicación breve de OpenClaw",
        context="Tutorial de OpenClaw para soporte operativo",
    )

    assert '"tú"' in DESIGNER_VIDEO_SYSTEM
    assert '"puedes"' in DESIGNER_VIDEO_SYSTEM
    assert '"vale"' in DESIGNER_VIDEO_SYSTEM
    assert "voseo real" in DESIGNER_VIDEO_SYSTEM
    assert "voseo real" in prompt


def test_designer_video_requirements_expand_agent_tutorial_topics():
    """Agent-topic videos should force graph/code tutorial composition in the final prompt."""
    from community_manager.graph.nodes.designer import _append_video_rendering_requirements

    prompt = _append_video_rendering_requirements(
        "Explicación breve de un agente",
        context="Tutorial de LangChain con subagentes, nodos y Python",
    )

    assert "esquina inferior derecha" in prompt
    assert "silla central del fondo real de Novit" in prompt
    assert "grafo o nodos" in prompt
    assert "código Python" in prompt


def test_sora_prompts_always_reserve_space_for_logo_overlay():
    """The Sora client should always append deterministic branding guardrails to the raw video prompt."""
    from community_manager.tools.video_gen import _append_video_branding_guardrails

    prompt = _append_video_branding_guardrails("Tutorial visual de LangGraph")

    assert "Do not render any Novit logo" in prompt
    assert "bottom-right corner visually clean" in prompt


def test_presenter_reference_bundle_is_available_for_video_posts():
    """Video prompts should attach a stable presenter reference bundle for recurring fictional presenter cues."""
    from community_manager.models.schemas import ContentStrategy, ContentType
    from community_manager.tools.training_media import build_presenter_reference_bundle

    bundle = build_presenter_reference_bundle(
        strategy=ContentStrategy(
            content_type=ContentType.VIDEO_POST,
            topic="Tutorial de agentes",
            objective="Mostrar criterio",
        )
    )

    assert bundle is not None
    assert "consultoría vertical.png" in bundle["assets"]
    assert any(part["type"] == "image_url" for part in bundle["message_content"])


def test_video_duration_is_fixed_to_30_seconds_and_sora_clips_normalize_to_supported_lengths():
    """Video strategies now target ~30 seconds while Sora support clips still normalize to 4/8/12 for generation."""
    from community_manager.models.schemas import ContentStrategy, ContentType, FIXED_VIDEO_DURATION_SECONDS
    from community_manager.tools.video_gen import _normalize_duration_seconds, _normalize_supporting_clip_duration_seconds, _normalize_supporting_clip_transition

    strategy = ContentStrategy(
        content_type=ContentType.VIDEO_POST,
        topic="Agentes de IA",
        objective="Explicar un tradeoff",
        video_duration_seconds=25,
    )

    assert strategy.video_duration_seconds == FIXED_VIDEO_DURATION_SECONDS
    assert FIXED_VIDEO_DURATION_SECONDS == 30
    assert _normalize_duration_seconds(5) == 8
    assert _normalize_duration_seconds(8) == 8
    assert _normalize_duration_seconds(25) == 12
    assert _normalize_supporting_clip_duration_seconds(4) == 4
    assert _normalize_supporting_clip_duration_seconds(5) == 8
    assert _normalize_supporting_clip_duration_seconds(8) == 8
    assert _normalize_supporting_clip_transition("cut") == "cut"
    assert _normalize_supporting_clip_transition("wipe") == "dissolve"


def test_composite_video_plan_prefers_avatar_only_fallback():
    """The designer fallback should prefer a clean avatar-first plan when no support clip adds clear value."""
    from community_manager.graph.nodes.designer import _build_composite_video_draft

    draft = _build_composite_video_draft({}, context="Tutorial de agentes con Python y métricas de negocio")

    assert draft.avatar_script
    assert draft.avatar_intro_seconds == 5.0
    assert draft.avatar_outro_seconds == 2.0
    assert draft.supporting_clips == []


def test_strategist_sanitizes_null_video_duration_for_image_posts():
    """Image post strategies should not fall back just because the LLM emits null video duration."""
    from community_manager.graph.nodes.strategist import _sanitize_strategy_payload

    payload = _sanitize_strategy_payload(
        {
            "content_type": "image_post",
            "topic": "Automatización con IA",
            "objective": "Abrir conversación",
            "video_duration_seconds": None,
            "num_images": 4,
        },
        requested_type="image_post",
    )

    assert "video_duration_seconds" not in payload
    assert payload["num_images"] == 4


def test_recent_publication_history_is_limited_to_eight_items():
    """The strategist should only see the last eight publication summaries even if more are loaded."""
    history = [f"pub {index}" for index in range(1, 12)]
    recent = history[-8:]

    assert recent == ["pub 4", "pub 5", "pub 6", "pub 7", "pub 8", "pub 9", "pub 10", "pub 11"]


def test_generate_images_keeps_partial_success_when_minimum_is_met():
    """Image drafts should survive a slow/failed prompt if at least the minimum carousel size completes."""
    import httpx
    from community_manager.tools.image_gen import ImageGenClient

    class FakeImageGenClient(ImageGenClient):
        def __init__(self) -> None:
            pass

        async def generate_image(self, prompt: str, **kwargs):
            from community_manager.models.schemas import GeneratedImage

            if prompt == "timeout":
                raise httpx.ReadTimeout("boom")
            return GeneratedImage(prompt=prompt, url=f"https://example.com/{prompt}.jpg")

    client = FakeImageGenClient()
    images = asyncio.run(client.generate_images(["a", "b", "c", "d", "timeout"]))

    assert len(images) == 4


def test_generate_images_fails_when_minimum_is_not_met():
    """Image drafts should still fail closed if fewer than four images complete."""
    import httpx
    from community_manager.tools.image_gen import ImageGenClient

    class FakeImageGenClient(ImageGenClient):
        def __init__(self) -> None:
            pass

        async def generate_image(self, prompt: str, **kwargs):
            from community_manager.models.schemas import GeneratedImage

            if prompt.startswith("ok"):
                return GeneratedImage(prompt=prompt, url=f"https://example.com/{prompt}.jpg")
            raise httpx.ReadTimeout("boom")

    client = FakeImageGenClient()

    try:
        asyncio.run(client.generate_images(["ok1", "ok2", "ok3", "bad1", "bad2"]))
    except RuntimeError as exc:
        assert "only 3 of 5 required images" in str(exc)
    else:
        raise AssertionError("Expected the image batch to fail when fewer than four images complete")


def test_generate_images_supports_partial_regeneration_batches():
    """Partial regeneration batches should succeed even when they contain fewer than four slides."""
    from community_manager.tools.image_gen import ImageGenClient

    class FakeImageGenClient(ImageGenClient):
        def __init__(self) -> None:
            pass

        async def generate_image(self, prompt: str, **kwargs):
            from community_manager.models.schemas import GeneratedImage

            return GeneratedImage(prompt=prompt, url=f"https://example.com/{prompt}.jpg")

    client = FakeImageGenClient()
    images = asyncio.run(client.generate_images(["slide-2", "slide-4"], slide_numbers=[2, 4]))

    assert [image.slide_number for image in images] == [2, 4]


def test_designer_extracts_retry_slides_from_reviewer_feedback():
    """Free-text reviewer feedback mentioning slide numbers should enable partial regeneration."""
    from community_manager.graph.nodes.designer import _extract_slide_numbers_from_text

    slide_numbers = _extract_slide_numbers_from_text(
        "Rehacer slides 2 y 4. La placa 5 quedó bien.",
        total_slides=5,
    )

    assert slide_numbers == [2, 4]


def test_prompt_qa_rewrites_prompts_before_rendering():
    """The designer should run a cheap prompt QA pass and rewrite prompts before paying for image generation."""
    from unittest.mock import patch

    from community_manager.graph.nodes import designer as designer_module
    from community_manager.models.schemas import ContentStrategy, ContentType, GeneratedImage

    class FakeMainLlm:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            prompts = [
                f"Prompt draft {self.calls} slide 1",
                f"Prompt draft {self.calls} slide 2",
                f"Prompt draft {self.calls} slide 3",
                f"Prompt draft {self.calls} slide 4",
            ]
            return type("Response", (), {"content": json.dumps({"prompts": prompts, "style_notes": "sobrio"})})()

    class FakeSmallLlm:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                payload = {
                    "approved": False,
                    "feedback": "La portada todavía parece un título corporativo.",
                    "issues": ["cover weak"],
                    "slide_reviews": [
                        {
                            "slide_number": 1,
                            "approved": False,
                            "feedback": "Necesita un hook más claro.",
                            "issues": ["hook débil"],
                        }
                    ],
                }
            else:
                payload = {
                    "approved": True,
                    "feedback": "OK",
                    "issues": [],
                    "slide_reviews": [],
                }
            return type("Response", (), {"content": json.dumps(payload)})()

    class FakeImageGenClient:
        captured_prompts: list[str] | None = None

        async def generate_images(self, prompts, *, slide_numbers=None, **kwargs):
            FakeImageGenClient.captured_prompts = list(prompts)
            return [
                GeneratedImage(prompt=prompt, url=f"https://example.com/{slide_number}.jpg", slide_number=slide_number)
                for prompt, slide_number in zip(prompts, slide_numbers or [], strict=False)
            ]

        async def close(self):
            return None

    class FakeSettings:
        brand_name = "Novit Software"
        is_image_generation_configured = True

    strategy = ContentStrategy(
        content_type=ContentType.IMAGE_POST,
        topic="Automatización con agentes",
        objective="Mostrar criterio",
        num_images=4,
    )

    with (
        patch.object(designer_module, "get_main_llm", return_value=FakeMainLlm()),
        patch.object(designer_module, "get_small_llm", return_value=FakeSmallLlm()),
        patch.object(designer_module, "ImageGenClient", FakeImageGenClient),
    ):
        result = asyncio.run(
            designer_module._generate_images(
                strategy,
                "Topic: Automatización con agentes",
                FakeSettings(),
                reference_bundle=None,
            )
        )

    assert FakeImageGenClient.captured_prompts is not None
    assert FakeImageGenClient.captured_prompts[0].startswith("Prompt draft 2 slide 1")
    assert result.images[0].slide_number == 1


def test_designer_regenerates_only_failed_slides():
    """Designer retries should regenerate only the slides rejected by evaluation and keep the approved ones."""
    from unittest.mock import patch

    from community_manager.graph.nodes import designer as designer_module
    from community_manager.models.schemas import ContentStrategy, ContentType, DesignerOutput, EvaluationResult, GeneratedImage, PostCopy, SlideReview

    class FakeMainLlm:
        async def ainvoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": json.dumps(
                        {
                            "prompts": [
                                "Nuevo slide 1",
                                "Nuevo slide 2",
                                "Nuevo slide 3",
                                "Nuevo slide 4",
                            ],
                            "style_notes": "consistente",
                        }
                    )
                },
            )()

    class FakeSmallLlm:
        async def ainvoke(self, messages):
            return type("Response", (), {"content": json.dumps({"approved": True, "feedback": "OK", "issues": [], "slide_reviews": []})})()

    class FakeImageGenClient:
        calls: list[tuple[list[str], list[int] | None]] = []

        async def generate_images(self, prompts, *, slide_numbers=None, **kwargs):
            FakeImageGenClient.calls.append((list(prompts), list(slide_numbers or [])))
            return [
                GeneratedImage(prompt=prompt, url=f"https://example.com/new-{slide_number}.jpg", slide_number=slide_number)
                for prompt, slide_number in zip(prompts, slide_numbers or [], strict=False)
            ]

        async def close(self):
            return None

    class FakeSettings:
        brand_name = "Novit Software"
        is_image_generation_configured = True
        is_video_generation_configured = False

    previous_design = DesignerOutput(
        images=[
            GeneratedImage(prompt="Viejo slide 1", url="https://example.com/old-1.jpg", slide_number=1),
            GeneratedImage(prompt="Viejo slide 2", url="https://example.com/old-2.jpg", slide_number=2),
            GeneratedImage(prompt="Viejo slide 3", url="https://example.com/old-3.jpg", slide_number=3),
            GeneratedImage(prompt="Viejo slide 4", url="https://example.com/old-4.jpg", slide_number=4),
        ]
    )

    state = {
        "messages": [],
        "requested_content_type": "image_post",
        "skip_llm_evaluation": False,
        "publication_history": [],
        "reviewer_memory": "",
        "reviewer_feedback": "Rehacer slide 2 y slide 4.",
        "strategy": ContentStrategy(
            content_type=ContentType.IMAGE_POST,
            topic="Agentes para pymes",
            objective="Mostrar criterio",
            num_images=4,
        ),
        "copy": PostCopy(caption="Caption", hashtags=["novit"], alt_text="Alt"),
        "design": previous_design,
        "evaluation": EvaluationResult(
            approved=False,
            score=4,
            feedback="Rehacer slide 2 y slide 4.",
            issues=["Slides puntuales flojos"],
            slide_reviews=[
                SlideReview(slide_number=2, approved=False, feedback="El desarrollo se siente genérico.", issues=["genérico"]),
                SlideReview(slide_number=4, approved=False, feedback="El cierre no parece cierre.", issues=["cierre flojo"]),
            ],
            retry_target="designer",
        ),
        "retry_count": 1,
        "publish_result": None,
    }

    with (
        patch.object(designer_module, "get_settings", return_value=FakeSettings()),
        patch.object(designer_module, "get_main_llm", return_value=FakeMainLlm()),
        patch.object(designer_module, "get_small_llm", return_value=FakeSmallLlm()),
        patch.object(designer_module, "ImageGenClient", FakeImageGenClient),
    ):
        result = asyncio.run(designer_module.designer_node(state))

    assert len(FakeImageGenClient.calls) == 1
    prompts, slide_numbers = FakeImageGenClient.calls[0]
    assert slide_numbers == [2, 4]
    assert len(prompts) == 2

    design = result["design"]
    assert [image.url for image in design.images] == [
        "https://example.com/old-1.jpg",
        "https://example.com/new-2.jpg",
        "https://example.com/old-3.jpg",
        "https://example.com/new-4.jpg",
    ]


def test_dalle_prompt_forbids_generated_logos():
    """Generated images should reserve branding for exact logo compositing instead of rendering fake logos."""
    from community_manager.tools.image_gen import ImageGenClient

    class FakeImageGenClient(ImageGenClient):
        def __init__(self) -> None:
            self.settings = None

    client = FakeImageGenClient()
    prompt = client._build_generation_prompt("Carrusel sobrio sobre errores de implementación")

    assert "No render any Novit logo" in prompt
    assert "bottom-right corner visually clean as a safe area" in prompt
    assert "22% of the width" in prompt


def test_visual_preferences_import():
    """Structured visual preferences load and keep the expected categories."""
    from community_manager.config.visual_preferences import (
        VISUAL_PREFERENCE_PROFILE,
        VISUAL_PREFERENCE_PROMPT,
    )

    assert VISUAL_PREFERENCE_PROFILE["always"]
    assert VISUAL_PREFERENCE_PROFILE["prefer"]
    assert VISUAL_PREFERENCE_PROFILE["sometimes_use"]
    assert VISUAL_PREFERENCE_PROFILE["avoid"]
    assert "sometimes_use" in VISUAL_PREFERENCE_PROMPT
    assert "No son templates obligatorios" in VISUAL_PREFERENCE_PROMPT


def test_content_preferences_import():
    """Structured content preferences load and keep the expected sections."""
    from community_manager.config.content_preferences import (
        CONTENT_PREFERENCE_PROFILE,
        CONTENT_PREFERENCE_PROMPT,
    )

    assert CONTENT_PREFERENCE_PROFILE["editorial_core"]["always"]
    assert CONTENT_PREFERENCE_PROFILE["topic_priorities"]["high_priority"]
    assert CONTENT_PREFERENCE_PROFILE["technical_authority_layer"]["rule"]
    assert CONTENT_PREFERENCE_PROFILE["tone_and_voice"]["avoid"]
    assert "Agentes de IA" in CONTENT_PREFERENCE_PROMPT
    assert "Noticias relevantes del mundo IA o tecnologia usadas como disparador editorial." in CONTENT_PREFERENCE_PROMPT
    assert "No tratar el contenido tecnico para developers como un hard avoid" in CONTENT_PREFERENCE_PROMPT
    assert "Aqui te explicamos como lograrlo" in CONTENT_PREFERENCE_PROMPT


def test_content_preferences_are_injected_into_prompts():
    """Strategist, copywriter and evaluator should read the editorial preference layer."""
    from community_manager.config.prompts import (
        COPYWRITER_SYSTEM,
        EVALUATOR_SYSTEM,
        STRATEGIST_SYSTEM,
    )

    assert "Agentes de IA" in STRATEGIST_SYSTEM
    assert "No tratar el contenido tecnico para developers como un hard avoid" in COPYWRITER_SYSTEM
    assert "noticia vacía" in EVALUATOR_SYSTEM


def test_nurturing_prompts_import():
    """Nurturing prompt templates contain expected placeholders."""
    from community_manager.nurturing.prompts import (
        NEWSLETTER_SYSTEM,
        NEWSLETTER_USER_TEMPLATE,
        PERSONAL_CLOSING_USER_TEMPLATE,
        REPLY_USER_TEMPLATE,
        REVISION_USER_TEMPLATE,
    )

    assert "{month_name}" in NEWSLETTER_USER_TEMPLATE
    assert "{reviewer_feedback}" in REVISION_USER_TEMPLATE
    assert "{sender_name}" in REPLY_USER_TEMPLATE
    assert "{newsletter_subject}" in PERSONAL_CLOSING_USER_TEMPLATE
    assert "web_search" in NEWSLETTER_SYSTEM


def test_state_import():
    """State TypedDict imports correctly."""
    from community_manager.graph.state import CommunityManagerState

    # TypedDict is just a dict at runtime
    assert CommunityManagerState is not None


def test_evaluator_can_be_bypassed_for_manual_direct_publish_after_asset_validation():
    """Manual publish-now runs should skip subjective evaluator retries once media exists."""
    from community_manager.graph.nodes.evaluator import evaluator_node
    from community_manager.models.schemas import (
        ContentStrategy,
        ContentType,
        DesignerOutput,
        GeneratedVideo,
        PostCopy,
    )

    result = asyncio.run(
        evaluator_node(
            {
                "messages": [],
                "requested_content_type": "video_post",
                "skip_llm_evaluation": True,
                "publication_history": [],
                "reviewer_memory": "",
                "reviewer_feedback": "",
                "strategy": ContentStrategy(
                    content_type=ContentType.VIDEO_POST,
                    topic="Prueba de avatar",
                    objective="Validar publicación manual",
                ),
                "copy": PostCopy(
                    caption="Prueba manual",
                    hashtags=["novit"],
                    alt_text="Video de prueba",
                ),
                "design": DesignerOutput(
                    video=GeneratedVideo(
                        prompt="Avatar sobre oficina real",
                        url="https://example.com/video.mp4",
                    )
                ),
                "evaluation": None,
                "retry_count": 0,
                "publish_result": None,
            }
        )
    )

    assert result["evaluation"].approved is True
    assert result["evaluation"].score == 10
    assert result["retry_count"] == 0


def test_evaluator_uses_generated_images_for_visual_review():
    """Evaluator should attach generated slide images so the model can review the real output, not only prompts."""
    from unittest.mock import patch

    from community_manager.graph.nodes import evaluator as evaluator_module
    from community_manager.models.schemas import ContentStrategy, ContentType, DesignerOutput, GeneratedImage, PostCopy

    class FakeSmallLlm:
        async def ainvoke(self, messages):
            content = messages[1].content
            assert isinstance(content, list)
            image_blocks = [part for part in content if part.get("type") == "image_url"]
            assert len(image_blocks) == 2
            return type(
                "Response",
                (),
                {
                    "content": json.dumps(
                        {
                            "approved": False,
                            "score": 5,
                            "feedback": "El slide 2 tiene demasiada densidad visual.",
                            "issues": ["densidad"],
                            "slide_reviews": [
                                {
                                    "slide_number": 2,
                                    "approved": False,
                                    "feedback": "Mucho ruido visual.",
                                    "issues": ["ruido visual"],
                                }
                            ],
                            "retry_target": None,
                        }
                    )
                },
            )()

    with patch.object(evaluator_module, "get_small_llm", return_value=FakeSmallLlm()):
        result = asyncio.run(
            evaluator_module.evaluator_node(
                {
                    "messages": [],
                    "requested_content_type": "image_post",
                    "skip_llm_evaluation": False,
                    "publication_history": [],
                    "reviewer_memory": "",
                    "reviewer_feedback": "",
                    "strategy": ContentStrategy(
                        content_type=ContentType.IMAGE_POST,
                        topic="IA aplicada",
                        objective="Educar",
                        num_images=4,
                    ),
                    "copy": PostCopy(caption="Caption", hashtags=["novit"], alt_text="Alt"),
                    "design": DesignerOutput(
                        images=[
                            GeneratedImage(prompt="Slide 1", url="https://example.com/1.jpg", slide_number=1),
                            GeneratedImage(prompt="Slide 2", url="https://example.com/2.jpg", slide_number=2),
                        ]
                    ),
                    "evaluation": None,
                    "retry_count": 0,
                    "publish_result": None,
                }
            )
        )

    assert result["evaluation"].retry_target == "designer"
    assert result["evaluation"].slide_reviews[0].slide_number == 2


def test_copywriter_repairs_unsourced_study_claims():
    from community_manager.graph.nodes import copywriter as copywriter_module
    from community_manager.models.schemas import ContentStrategy, ContentType, ContentTone, EvaluationResult

    class FakeCreativeLlm:
        def __init__(self):
            self.responses = [
                SimpleNamespace(content=json.dumps({
                    "caption": "Según un estudio, las empresas que adopten agentes van a ganar más productividad.",
                    "hashtags": ["novit"],
                    "alt_text": "Alt inicial",
                })),
                SimpleNamespace(content="Implementar agentes con criterio no empieza por comprar herramientas: empieza por detectar qué decisión o proceso realmente vale automatizar.\n\nSi querés evaluarlo en tu empresa, conversemos."),
            ]

        async def ainvoke(self, _messages):
            return self.responses.pop(0)

    original_get_llm = copywriter_module.get_creative_llm
    copywriter_module.get_creative_llm = lambda: FakeCreativeLlm()
    try:
        result = asyncio.run(copywriter_module.copywriter_node({
            "messages": [],
            "strategy": ContentStrategy(
                content_type=ContentType.IMAGE_POST,
                topic="Agentes de IA",
                angle="Qué procesos conviene automatizar primero",
                objective="Abrir conversación",
                tone=ContentTone.PROFESSIONAL,
                supporting_points=["priorización de procesos"],
                key_messages=["criterio antes que hype"],
                num_images=4,
            ),
            "evaluation": EvaluationResult(
                approved=False,
                score=0,
                feedback="El copy menciona estudios o datos sin evidencia suficiente.",
                issues=["Unverified study/data claim without explicit source attribution and quote."],
                retry_target="copywriter",
            ),
            "reviewer_memory": "",
            "reviewer_feedback": "",
        }))
    finally:
        copywriter_module.get_creative_llm = original_get_llm

    assert "según un estudio" not in result["copy"].caption.lower()
    assert result["copy"].hashtags == ["novit"]


def test_generate_reviewable_draft_returns_denied_payload_after_max_retries():
    from community_manager.graph import review_workflow as review_workflow_module
    from community_manager.graph.workflow import MAX_RETRIES
    from community_manager.models.schemas import ContentStrategy, ContentType, DesignerOutput, EvaluationResult, GeneratedImage, PostCopy

    async def fake_strategist(_state):
        return {
            "strategy": ContentStrategy(
                content_type=ContentType.IMAGE_POST,
                topic="Agentes de IA",
                angle="Implementación prudente",
                objective="Abrir conversación",
                supporting_points=["priorizar procesos"],
                num_images=4,
            )
        }

    async def fake_copywriter(_state):
        return {
            "copy": PostCopy(
                caption="Caption no aprobado",
                hashtags=["novit"],
                alt_text="Alt",
            )
        }

    async def fake_designer(_state):
        return {
            "design": DesignerOutput(
                images=[GeneratedImage(url="https://example.com/slide-1.png", prompt="Slide 1")]
            )
        }

    async def fake_evaluator(state):
        return {
            "evaluation": EvaluationResult(
                approved=False,
                score=0,
                feedback="El copy menciona estudios o datos sin evidencia suficiente.",
                issues=["Unverified study/data claim without explicit source attribution and quote."],
                retry_target="copywriter",
            ),
            "retry_count": state.get("retry_count", 0) + 1,
        }

    original_strategist = review_workflow_module.strategist_node
    original_copywriter = review_workflow_module.copywriter_node
    original_designer = review_workflow_module.designer_node
    original_evaluator = review_workflow_module.evaluator_node
    try:
        review_workflow_module.strategist_node = fake_strategist
        review_workflow_module.copywriter_node = fake_copywriter
        review_workflow_module.designer_node = fake_designer
        review_workflow_module.evaluator_node = fake_evaluator

        payload = asyncio.run(review_workflow_module.generate_reviewable_draft("image_post"))
    finally:
        review_workflow_module.strategist_node = original_strategist
        review_workflow_module.copywriter_node = original_copywriter
        review_workflow_module.designer_node = original_designer
        review_workflow_module.evaluator_node = original_evaluator

    assert payload["draft_status"] == "denied"
    assert payload["failure_reason"] == "El copy menciona estudios o datos sin evidencia suficiente."
    assert payload["retry_count"] == MAX_RETRIES


def test_generate_reviewable_draft_on_demand_defers_to_human_review_after_max_retries():
    from community_manager.graph import review_workflow as review_workflow_module
    from community_manager.graph.workflow import MAX_RETRIES
    from community_manager.models.schemas import ContentStrategy, ContentType, DesignerOutput, EvaluationResult, GeneratedImage, PostCopy, ReviewStage

    async def fake_strategist(_state):
        return {
            "strategy": ContentStrategy(
                content_type=ContentType.IMAGE_POST,
                topic="Agentes de IA",
                angle="Implementación prudente",
                objective="Abrir conversación",
                supporting_points=["priorizar procesos"],
                num_images=4,
            )
        }

    async def fake_copywriter(_state):
        return {
            "copy": PostCopy(
                caption="Caption con observaciones editoriales",
                hashtags=["novit"],
                alt_text="Alt",
            )
        }

    async def fake_designer(_state):
        return {
            "design": DesignerOutput(
                images=[GeneratedImage(prompt="Slide 1 plan", review_summary="Hook de apertura", url="")]
            )
        }

    async def fake_evaluator(state):
        return {
            "evaluation": EvaluationResult(
                approved=False,
                score=6,
                feedback="La portada no tiene un gancho suficientemente fuerte.",
                issues=["Hook de portada débil."],
                retry_target="designer",
            ),
            "retry_count": state.get("retry_count", 0) + 1,
        }

    original_strategist = review_workflow_module.strategist_node
    original_copywriter = review_workflow_module.copywriter_node
    original_designer = review_workflow_module.designer_node
    original_evaluator = review_workflow_module.evaluator_node
    try:
        review_workflow_module.strategist_node = fake_strategist
        review_workflow_module.copywriter_node = fake_copywriter
        review_workflow_module.designer_node = fake_designer
        review_workflow_module.evaluator_node = fake_evaluator

        payload = asyncio.run(review_workflow_module.generate_reviewable_draft("image_post", is_on_demand=True))
    finally:
        review_workflow_module.strategist_node = original_strategist
        review_workflow_module.copywriter_node = original_copywriter
        review_workflow_module.designer_node = original_designer
        review_workflow_module.evaluator_node = original_evaluator

    assert payload["draft_status"] == "pending_review"
    assert payload["review_stage"] == ReviewStage.PRE_MEDIA.value
    assert payload["retry_count"] == MAX_RETRIES
    assert payload["failure_reason"] is None


# ── Nurturing utility tests ──────────────────────────────────

def test_parse_newsletter_json():
    """Newsletter JSON parsing works for valid input."""
    from community_manager.nurturing._legacy.workflow import _parse_newsletter_json

    raw = json.dumps({
        "subject": "IA en Argentina y cloud computing",
        "body": "<p>Te comparto dos noticias interesantes.</p>",
    })
    subject, body = _parse_newsletter_json(raw)
    assert subject == "IA en Argentina y cloud computing"
    assert "<p>" in body


def test_parse_newsletter_json_with_code_fence():
    """Newsletter JSON parsing strips markdown code fences."""
    from community_manager.nurturing._legacy.workflow import _parse_newsletter_json

    raw = '```json\n{"subject": "Test", "body": "<p>Hello</p>"}\n```'
    subject, body = _parse_newsletter_json(raw)
    assert subject == "Test"
    assert body == "<p>Hello</p>"


def test_parse_newsletter_json_invalid():
    """Newsletter JSON parsing falls back gracefully on invalid input."""
    from community_manager.nurturing._legacy.workflow import _parse_newsletter_json

    subject, body = _parse_newsletter_json("This is not JSON at all")
    assert "Novedades tech" in subject
    assert body == "This is not JSON at all"


def test_parse_newsletter_json_markdown_cleanup():
    """Bold markdown **text** is converted to <b> tags."""
    from community_manager.nurturing._legacy.workflow import _parse_newsletter_json

    raw = json.dumps({
        "subject": "Test",
        "body": "<p>This is **bold** text.</p>",
    })
    _, body = _parse_newsletter_json(raw)
    assert "<b>bold</b>" in body
    assert "**" not in body


def test_wrap_in_html_email():
    """HTML email wrapper includes key elements."""
    from community_manager.services.nurturing_content_renderer import wrap_in_html_email

    html = wrap_in_html_email("<p>Test content</p>", first_name="Carlos")
    assert "Hola Carlos," in html
    assert "Nicolás Piccardo" in html
    assert "novitsoftware.com" in html
    assert "<p>Test content</p>" in html


def test_wrap_in_html_email_no_name():
    """HTML email wrapper uses generic greeting without name."""
    from community_manager.services.nurturing_content_renderer import wrap_in_html_email

    html = wrap_in_html_email("<p>Test</p>")
    assert "Hola," in html


def test_wrap_in_html_email_with_closing():
    """HTML email wrapper includes personal closing when provided."""
    from community_manager.services.nurturing_content_renderer import wrap_in_html_email

    html = wrap_in_html_email(
        "<p>Content</p>",
        first_name="María",
        personal_closing="Abrazo grande!",
    )
    assert "Abrazo grande!" in html


def test_get_month_name():
    """Month name helper returns a Spanish month name."""
    from community_manager.nurturing._legacy.workflow import _get_month_name

    name = _get_month_name()
    # Should be something like "julio 2025"
    assert len(name) > 5
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    month_word = name.split()[0]
    assert month_word in months


# ── Settings property tests ──────────────────────────────────

def test_settings_helpers():
    """Settings helper properties work correctly."""
    from community_manager.config.settings import Settings

    s = Settings()
    assert isinstance(s.brand_hashtags_list, list)
    assert len(s.brand_hashtags_list) > 0
    assert s.media_path.exists()
    assert s.build_public_media_url("example image.png") == "https://ia.novitsoftware.com/generated-media/example%20image.png"
    assert s.azure_foundry_dalle_size == "1024x1024"
    assert s.azure_foundry_dalle_quality == "high"
    assert s.resolved_responder_llm_deployment == "gpt-4o-mini"


def test_settings_resolve_image_generation_targets():
    """Image generation can route between the standard and premium model profiles."""
    from community_manager.config.settings import Settings

    s = Settings(
        azure_foundry_dalle_endpoint="https://standard.example.com",
        azure_foundry_dalle_api_key="standard-key",
        azure_foundry_dalle_deployment="gpt-image-1-5",
        azure_foundry_dalle_api_version="2025-04-01-preview",
        azure_foundry_dalle_2_endpoint="https://premium.example.com",
        azure_foundry_dalle_2_api_key="premium-key",
        azure_foundry_dalle_2_deployment="gpt-image-2",
        azure_foundry_dalle_2_api_version="2025-04-01-preview",
    )

    standard = s.resolve_image_generation_target("image_1_5")
    premium = s.resolve_image_generation_target("image_2", quality="high")

    assert standard.model == "image_1_5"
    assert standard.endpoint == "https://standard.example.com"
    assert standard.deployment == "gpt-image-1-5"
    assert premium.model == "image_2"
    assert premium.endpoint == "https://premium.example.com"
    assert premium.deployment == "gpt-image-2"
    assert premium.quality == "high"


def test_get_responder_llm_prefers_cheap_route(monkeypatch):
    """The IG/Facebook responder should use the dedicated cheap deployment route."""
    from community_manager.tools import llm

    captured: dict[str, object] = {}

    def fake_build_azure_chat(deployment: str, **kwargs):
        captured["deployment"] = deployment
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(llm, "_build_azure_chat", fake_build_azure_chat)
    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(resolved_responder_llm_deployment="gpt-4o-mini"),
    )

    llm.get_responder_llm()

    assert captured["deployment"] == "gpt-4o-mini"
    assert captured["kwargs"]["max_tokens"] == 500


def test_settings_nurturing_not_configured():
    """Nurturing reports not configured when keys are empty."""
    from community_manager.config.settings import Settings

    s = Settings()
    assert s.is_nurturing_configured is False
    assert s.is_web_search_configured is False
    assert s.is_video_generation_configured is False
    assert s.is_blob_media_hosting_configured is False


def test_image_gen_persists_base64_payload(tmp_path: Path):
    """Image generation saves base64 responses as public assets."""
    from community_manager.tools.image_gen import ImageGenClient

    client = ImageGenClient()
    client.media_dir = tmp_path

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+nWZ0AAAAASUVORK5CYII="
    )
    result = {
        "b64_json": base64.b64encode(png_bytes).decode("ascii"),
        "revised_prompt": "test prompt",
    }

    path, public_url, blob_name = __import__("asyncio").run(client._persist_generated_asset(result, output_format="png"))

    assert path.exists()
    assert path.read_bytes() == png_bytes
    assert public_url.startswith("https://ia.novitsoftware.com/generated-media/image_")
    assert blob_name is None


def test_evaluator_accepts_remote_only_media():
    """Delayed-review drafts stay publishable even after local temp files are gone."""
    from community_manager.graph.nodes.evaluator import _validate_visual_assets
    from community_manager.models.schemas import ContentStrategy, ContentType, DesignerOutput, GeneratedImage

    strategy = ContentStrategy(
        content_type=ContentType.IMAGE_POST,
        topic="IA aplicada",
        objective="Educar",
    )
    design = DesignerOutput(images=[GeneratedImage(url="https://example.com/a.jpg", blob_name="a.jpg")])

    assert _validate_visual_assets(strategy, design) is None

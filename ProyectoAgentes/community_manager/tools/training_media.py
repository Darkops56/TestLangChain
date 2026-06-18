"""Reference training media when reviewers flag lack of realism.

The agent should not publish these assets directly. Instead, it uses them as
grounding references for the multimodal LLM that writes the next image/video
generation prompt after a human reviewer complains about realism, wrong logos,
or AI-looking environments.
"""

from __future__ import annotations

import base64
import mimetypes
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from community_manager.config.settings import get_settings
from community_manager.models.schemas import ContentType

PARTNER_IDENTITY_NOTES = (
    "En assets reales donde aparecen socios: Rodrigo suele verse un poco más alto y con remera verde; "
    "Leandro suele aparecer con camisa celeste frente a fondos de oficina/branding de Novit."
)

REALISM_FEEDBACK_KEYWORDS = (
    "realismo",
    "realista",
    "parece ia",
    "muy ia",
    "artificial",
    "deform",
    "fondo",
    "fondos",
    "paisaje",
    "paisajes",
    "logo",
    "logos",
    "novit",
)

OFFICIAL_LOGO_FILENAMES = (
    "novit-logo.png",
    "novit-logo-dark.png",
    "novit-isologo.png",
)

CURATED_PUBLISHED_POST_REFERENCE_DIRNAME = "published-post-references"
MAX_CURATED_PUBLISHED_POST_DIRS = 2
MAX_CURATED_PUBLISHED_REFERENCE_SLIDES_PER_POST = 2

AVATAR_BACKGROUND_REFERENCE_FILENAMES = (
    "ventana-3.jpg",
)

CONSISTENT_PRESENTER_REFERENCE_FILENAMES = (
    "consultoría vertical.png",
    "Novit _1.jpg",
)

CONSISTENT_PRESENTER_NOTES = (
    "Cuando el video use una cara, tratala como el mismo presentador ficticio en todas las publicaciones: "
    "varón joven-adulto, pelo castaño oscuro casi negro peinado de costado, tez clara a media, "
    "rasgos suaves, contextura delgada/media, expresión serena, look técnico sobrio y energía tranquila de consultor experto. "
    "Usá las referencias solo para abstraer rasgos generales, postura y styling. No copies ni reconstruyas una persona real."
)

AVATAR_BACKGROUND_NOTES = (
    "Usá esta foto real de la oficina de Novit como fondo fijo del avatar. "
    "La silla negra del centro debe sentirse como el lugar donde se apoya el presentador, con encuadre frontal sobrio, "
    "luz realista y nada de oficina sintética inventada."
)


@dataclass(frozen=True)
class TrainingMediaAsset:
    key: str
    filename: str
    media_kind: str  # image | video | note
    description: str
    tags: tuple[str, ...] = ()
    people_notes: str = ""
    preferred_for_video: bool = False


TRAINING_MEDIA_CATALOG: tuple[TrainingMediaAsset, ...] = (
    TrainingMediaAsset(
        key="office_branding_partners_a",
        filename="20231221_195405.jpg",
        media_kind="image",
        description="Foto real de branding/oficina de Novit con pared corporativa de fondo; útil para guiar fondos reales, colores sobrios y branding correcto.",
        tags=("office", "branding", "novit", "wall", "realism"),
        people_notes=PARTNER_IDENTITY_NOTES,
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="office_branding_partners_b",
        filename="20231221_195408.jpg",
        media_kind="image",
        description="Segunda foto real de oficina/branding de Novit para guiar escenas con identidad corporativa auténtica y sin logos inventados.",
        tags=("office", "branding", "novit", "wall", "realism"),
        people_notes=PARTNER_IDENTITY_NOTES,
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="office_branding_partners_c",
        filename="20231221_200857.jpg",
        media_kind="image",
        description="Foto real adicional de oficina Novit con branding de fondo, útil para reducir alucinaciones en escenas corporativas.",
        tags=("office", "branding", "novit", "wall", "realism"),
        people_notes=PARTNER_IDENTITY_NOTES,
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="office_coder_solo",
        filename="Novit _1.jpg",
        media_kind="image",
        description="Foto real de persona trabajando en notebook dentro de la oficina de Novit, con fondo simple y natural.",
        tags=("office", "coder", "solo", "realism", "implementation"),
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="office_collaboration_table",
        filename="Novit _2.jpg",
        media_kind="image",
        description="Foto real de colaboración técnica en mesa de trabajo dentro de la oficina de Novit.",
        tags=("office", "team", "collaboration", "realism", "implementation", "agents"),
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="office_coder_meeting_room",
        filename="Novit _9.jpg",
        media_kind="image",
        description="Foto real de trabajo técnico en sala de reuniones, con notebook y entorno corporativo real.",
        tags=("office", "meeting", "coder", "realism", "architecture"),
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="office_coder_window",
        filename="Novit _10.jpg",
        media_kind="image",
        description="Foto real de trabajo individual en notebook con fondo de oficina limpio y creíble.",
        tags=("office", "solo", "coder", "realism", "productivity"),
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="office_collab_small_group",
        filename="Novit _3.jpg",
        media_kind="image",
        description="Foto real de equipo conversando en oficina de Novit, buena para piezas sobre estrategia, equipo o implementación.",
        tags=("office", "team", "discussion", "realism", "strategy"),
        preferred_for_video=True,
    ),
    TrainingMediaAsset(
        key="consulting_vertical",
        filename="consultoría vertical.png",
        media_kind="image",
        description="Foto real vertical de mentoría o consultoría en oficina de Novit, útil para explicar implementación o acompañamiento técnico.",
        tags=("office", "consulting", "mentoring", "vertical", "realism", "implementation"),
        people_notes="Si aparece una figura en camisa celeste guiando a otra persona, puede corresponder a Leandro. " + PARTNER_IDENTITY_NOTES,
        preferred_for_video=False,
    ),
    TrainingMediaAsset(
        key="training_video_real_office",
        filename="Novit Software.mp4",
        media_kind="video",
        description="Clip real horizontal de oficina Novit que sirve como referencia conceptual de ambiente, pacing y B-roll auténtico, pero no se publica directo.",
        tags=("video", "office", "broll", "realism", "team"),
        people_notes=PARTNER_IDENTITY_NOTES,
        preferred_for_video=True,
    ),
)


REFERENCE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def feedback_requests_real_media(*texts: str) -> bool:
    haystack = " ".join(_normalize_text(text) for text in texts if text)
    return any(keyword in haystack for keyword in REALISM_FEEDBACK_KEYWORDS)


def _asset_matches_topic(asset: TrainingMediaAsset, topic_text: str) -> int:
    score = 0
    normalized_topic = _normalize_text(topic_text)
    for tag in asset.tags:
        if _normalize_text(tag) in normalized_topic:
            score += 2
    return score


def select_training_assets(
    *,
    content_type: ContentType,
    topic_text: str,
    feedback_text: str,
    limit: int,
) -> list[TrainingMediaAsset]:
    candidates = [asset for asset in TRAINING_MEDIA_CATALOG if asset.media_kind == "image"]
    if content_type == ContentType.VIDEO_POST:
        candidates = [asset for asset in candidates if asset.preferred_for_video]

    ranked = sorted(
        candidates,
        key=lambda asset: (
            _asset_matches_topic(asset, topic_text),
            any(tag in _normalize_text(feedback_text) for tag in ("logo", "fondo", "realismo")),
            asset.preferred_for_video if content_type == ContentType.VIDEO_POST else True,
            -len(asset.tags),
        ),
        reverse=True,
    )
    return ranked[:max(limit, 1)]


def _path_to_data_url(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _iter_curated_published_post_dirs(root: Path, *, limit: int = 2) -> list[Path]:
    if not root.exists():
        return []

    subdirs = sorted(
        path for path in root.iterdir()
        if path.is_dir() and any(file.is_file() and file.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS for file in path.iterdir())
    )
    return subdirs[:max(limit, 1)]


def _sample_curated_reference_slides(slides: list[Path], *, limit: int) -> list[Path]:
    if limit <= 0 or not slides:
        return []

    if len(slides) <= limit:
        return slides

    if limit == 1:
        return [slides[0]]

    selected: list[Path] = []
    last_index = len(slides) - 1
    for slot in range(limit):
        index = round(slot * last_index / (limit - 1))
        candidate = slides[index]
        if candidate not in selected:
            selected.append(candidate)

    if len(selected) == limit:
        return selected

    for candidate in slides:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) == limit:
            break

    return selected


def build_brand_logo_reference_bundle(*, strategy) -> dict | None:
    if not strategy or strategy.content_type != ContentType.IMAGE_POST:
        return None

    settings = get_settings()
    base_path = settings.brand_assets_path
    if not base_path.exists():
        return None

    content_blocks: list[dict] = [
        {
            "type": "text",
            "text": (
                "Se adjuntan logos oficiales de Novit desde frontend/public/assets/images. "
                "Si la pieza incluye marca, usá exclusivamente estas versiones exactas del logo/isologo, "
                "sin redibujarlo, estilizarlo ni inventar variantes. Si no podés respetarlas exactamente, omití el logo."
            ),
        }
    ]

    used_assets: list[str] = []
    for filename in OFFICIAL_LOGO_FILENAMES:
        source = base_path / filename
        if not source.exists() or source.suffix.lower() not in REFERENCE_IMAGE_EXTENSIONS:
            continue
        used_assets.append(filename)
        content_blocks.append({
            "type": "text",
            "text": f"Logo oficial {filename}: usalo solo tal cual aparece en esta referencia.",
        })
        content_blocks.append({
            "type": "image_url",
            "image_url": {"url": _path_to_data_url(source)},
        })

    if not used_assets:
        return None

    return {
        "notes": "Usar solo logos oficiales exactos de Novit cuando corresponda.",
        "assets": used_assets,
        "message_content": content_blocks,
    }


def build_presenter_reference_bundle(*, strategy) -> dict | None:
    if not strategy or strategy.content_type != ContentType.VIDEO_POST:
        return None

    settings = get_settings()
    base_path = settings.training_media_path
    if not base_path.exists():
        return None

    content_blocks: list[dict] = [
        {
            "type": "text",
            "text": (
                "Se adjuntan referencias reales solo para fijar un presentador ficticio consistente entre videos. "
                + CONSISTENT_PRESENTER_NOTES
                + " Si el video no necesita cara, podés omitirla. Si aparece una cara, mantené este mismo perfil."
            ),
        }
    ]

    used_assets: list[str] = []
    for filename in CONSISTENT_PRESENTER_REFERENCE_FILENAMES:
        source = base_path / filename
        if not source.exists() or source.suffix.lower() not in REFERENCE_IMAGE_EXTENSIONS:
            continue
        used_assets.append(filename)
        content_blocks.append({
            "type": "text",
            "text": f"Referencia de presentador {filename}: usala solo como guía abstracta de rasgos y styling, nunca como likeness exacto.",
        })
        content_blocks.append({
            "type": "image_url",
            "image_url": {"url": _path_to_data_url(source)},
        })

    if not used_assets:
        return None

    return {
        "notes": CONSISTENT_PRESENTER_NOTES,
        "assets": used_assets,
        "message_content": content_blocks,
    }


def build_avatar_background_reference_bundle(*, strategy) -> dict | None:
    if not strategy or strategy.content_type != ContentType.VIDEO_POST:
        return None

    source = resolve_avatar_background_path()
    if not source or source.suffix.lower() not in REFERENCE_IMAGE_EXTENSIONS:
        return None

    return {
        "notes": AVATAR_BACKGROUND_NOTES,
        "assets": [source.name],
        "message_content": [
            {
                "type": "text",
                "text": (
                    "Se adjunta la foto real que debe usarse como fondo del avatar en postproducción. "
                    + AVATAR_BACKGROUND_NOTES
                    + " El avatar no debe tapar completamente la silla ni la mesa: pensalo sentado y creíble."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": _path_to_data_url(source)},
            },
        ],
    }


def resolve_avatar_background_path() -> Path | None:
    settings = get_settings()
    base_path = settings.training_media_path
    if not base_path.exists():
        return None

    configured = settings.speech_avatar_background_asset.strip()
    if configured:
        candidate = base_path / configured
        if candidate.exists():
            return candidate

    for filename in AVATAR_BACKGROUND_REFERENCE_FILENAMES:
        candidate = base_path / filename
        if candidate.exists():
            return candidate

    return None


def merge_reference_bundles(*bundles: dict | None) -> dict | None:
    valid_bundles = [bundle for bundle in bundles if bundle]
    if not valid_bundles:
        return None

    assets: list[str] = []
    notes: list[str] = []
    message_content: list[dict] = []

    for bundle in valid_bundles:
        for asset in bundle.get("assets", []):
            if asset not in assets:
                assets.append(asset)
        note = bundle.get("notes", "")
        if note:
            notes.append(note)
        message_content.extend(bundle.get("message_content", []))

    return {
        "notes": " ".join(notes),
        "assets": assets,
        "message_content": message_content,
    }


def build_published_post_reference_bundle(*, strategy, published_references: list[dict] | None = None, base_path: Path | None = None) -> dict | None:
    if not strategy or strategy.content_type != ContentType.IMAGE_POST:
        return None

    training_root = base_path or get_settings().training_media_path
    curated_root = training_root / CURATED_PUBLISHED_POST_REFERENCE_DIRNAME
    curated_post_dirs = _iter_curated_published_post_dirs(curated_root, limit=MAX_CURATED_PUBLISHED_POST_DIRS)
    if not curated_post_dirs:
        return None

    content_blocks: list[dict] = [
        {
            "type": "text",
            "text": (
                "Se adjunta una muestra reducida de slides curadas localmente de publicaciones reales ya aprobadas de Novit. "
                "Se guardan a mano en el repo justamente porque los blobs de publicación son efímeros y se borran después de publicar. "
                "La muestra se mantiene chica para no volver lento el prompt multimodal. "
                "Usalas como benchmark visual de calidad aprobada: composición, densidad de texto, limpieza, jerarquía, ritmo de carrusel y tono visual. "
                "No copies literalmente la pieza ni repitas el contenido; abstraé qué se sintió bien y buscá un nivel de calidad parecido con una idea nueva."
            ),
        }
    ]

    assets: list[str] = []
    for post_index, post_dir in enumerate(curated_post_dirs, start=1):
        slides = sorted(
            file for file in post_dir.iterdir()
            if file.is_file() and file.suffix.lower() in REFERENCE_IMAGE_EXTENSIONS
        )
        sampled_slides = _sample_curated_reference_slides(
            slides,
            limit=MAX_CURATED_PUBLISHED_REFERENCE_SLIDES_PER_POST,
        )
        if not sampled_slides:
            continue

        notes_file = post_dir / "notes.txt"
        style_notes = notes_file.read_text(encoding="utf-8").strip() if notes_file.exists() else ""
        content_blocks.append({
            "type": "text",
            "text": (
                f"Referencia curada local {post_index}: carpeta '{post_dir.name}'"
                + (f", style notes '{style_notes}'" if style_notes else "")
                + "."
            ),
        })

        for slide_number, slide_path in enumerate(sampled_slides, start=1):
            relative_asset = str(slide_path.relative_to(training_root)).replace("\\", "/")
            assets.append(relative_asset)
            slide_text = f"Slide curado {slide_number} de la referencia {post_index} ({slide_path.name})."
            content_blocks.append({"type": "text", "text": slide_text})
            content_blocks.append({"type": "image_url", "image_url": {"url": _path_to_data_url(slide_path)}})

    if not assets:
        return None

    return {
        "notes": "Usar referencias curadas locales de publicaciones aprobadas de Novit como benchmark visual, sin depender de blobs efímeros.",
        "assets": assets,
        "message_content": content_blocks,
    }


def build_training_reference_bundle(*, strategy, reviewer_feedback: str) -> dict | None:
    if not strategy:
        return None

    if not feedback_requests_real_media(reviewer_feedback):
        return None

    settings = get_settings()
    base_path = settings.training_media_path
    if not base_path.exists():
        return None

    topic_text = " | ".join(filter(None, [strategy.topic, strategy.angle, strategy.objective, *strategy.supporting_points]))
    selected = select_training_assets(
        content_type=strategy.content_type,
        topic_text=topic_text,
        feedback_text=reviewer_feedback,
        limit=2 if strategy.content_type == ContentType.VIDEO_POST else min(getattr(strategy, "num_images", 1), 2),
    )
    if not selected:
        return None

    content_blocks: list[dict] = [
        {
            "type": "text",
            "text": (
                "Se adjuntan referencias reales desde media/training porque el reviewer humano marcó problemas de realismo, "
                "fondos muy IA o branding incorrecto. Usalas como base visual para composición, entorno, vestuario, escala, "
                "personas y branding correcto. NO publiques estas referencias directo: generá media nueva inspirada por ellas. "
                "Si aparece logo Novit, debe ser el real o debe omitirse. "
                + PARTNER_IDENTITY_NOTES
            ),
        }
    ]

    used_assets: list[str] = []
    notes: list[str] = []
    for asset in selected:
        source = base_path / asset.filename
        if not source.exists() or source.suffix.lower() not in REFERENCE_IMAGE_EXTENSIONS:
            continue
        used_assets.append(asset.filename)
        content_blocks.append({
            "type": "text",
            "text": f"Referencia real {asset.filename}: {asset.description}",
        })
        content_blocks.append({
            "type": "image_url",
            "image_url": {"url": _path_to_data_url(source)},
        })
        if asset.people_notes:
            notes.append(asset.people_notes)

    if not used_assets:
        return None

    return {
        "notes": " ".join(notes),
        "assets": used_assets,
        "message_content": content_blocks,
    }
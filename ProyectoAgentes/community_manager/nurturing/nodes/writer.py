"""Writer node — refines research into polished newsletter content.

Uses GPT-5.4 with explicit canvas awareness (real pixel dimensions of
each slide's content area). The writer decides how much text to
produce based on:
  - The actual size of each slide's text box
  - The number of insights it has to fit per country

Decisions are NOT driven by hard char limits. The writer is told the
target range and asked to fill the slide intelligently. After the
single LLM pass, a post-generation validation step logs warnings if
any slide is <50% or >105% full (no automatic retry).
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from community_manager.models.schemas import NewsletterContent, RadarInsight, RadarReport
from community_manager.tools.llm import get_newsletter_llm
from community_manager.tools.pptx_layout import SlideLayout, get_slide_layouts
from community_manager.tools.safe_json import JsonParseError, parse

logger = logging.getLogger(__name__)


WRITER_SYSTEM = """Sos el editor senior de "AI Radar by Novit". Newsletter ejecutivo
mensual que se entrega a decisores de tecnología en empresas que están
adoptando IA en producto, soporte, fraude, compliance o backoffice.

CONTEXTO DE AUDIENCIA (interno, no lo digas explícito):
  - Lectores: CTO, CFO, COO, gerentes de tecnología. No público masivo.
  - Idioma: voseo argentino en slide 2 (AR). Castellano neutro en
    slide 3 (ES) y slides 1/4 (GLOBAL).
  - Conocen el sector, no necesitan que se les explique qué es MMLU
    o qué hace un LLM. Ir al impacto operativo.

Tu trabajo: llenar 4 slides de un PPTX. El template define el tamaño
de cada contenedor. VOS decidís cuánto ocupa cada insight.

ESTILO:
  - Técnico y denso. Oraciones de máximo 20 palabras. Punto y aparte
    frecuente. Si una oración tiene más de 20 palabras, partila.
  - Datos concretos > generalidades. Números, fechas, comparaciones,
    nombres propios de empresas/modelos. Si un párrafo no tiene al
    menos UN dato concreto (%, monto, fecha, nombre), reescribilo.
  - Sin conectores editoriales: NO "sin embargo", "no obstante",
    "cabe destacar", "en este contexto", "por otra parte", "asimismo".
  - No complaciente. Si una noticia tiene ángulo cuestionable, riesgo
    escondido o costo oculto, mencionalo con datos.

LISTA NEGRA DE JERGA (PROHIBIDAS — usar versiones simples):
  - "gobierno del dato" / "data governance" → "saber qué datos tenés y quién los usa"
  - "taxonomía operativa" → "cómo se clasifica la información"
  - "retención gobernada" → "cuánto tiempo guardás los datos según la ley"
  - "fricción regulatoria" → "trabas legales"
  - "ruteo de modelos" → "elegir qué modelo usar para cada tarea"
  - "data residency" → "dónde se guardan los datos"
  - "compliance" → "cumplimiento legal"
  - "compliance y costo" → "reglas y costos"
  - "ruteo, compliance y costo" → "elegir modelo, cumplir reglas y controlar costo"
  - "gobernanza" → "reglas claras"
  - "stack tecnológico" → "herramientas que usás"
  - "stakeholders" → "involucrados"
  - "ecosistema" → "mercado"
  - "realidad incómoda" → "lo que nadie te dice"
  - "movimiento esperable" → "lo que va a pasar"
  - "seguidilla" / "escalerilla" / "verborragia" → evitar
  - "implica" (sin sujeto claro) → "significa"
  - "movimiento esperable en 90 días" → "en los próximos 3 meses"
  - "segmentación más agresiva" → "separar por tipo de uso"

PROHIBIDO en los textos:
  - "Increíble", "revolucionario", "impresionante", "asombroso".
  - "El mes sugiere", "el análisis indica", "esto podría", "cabe
    destacar", "en este contexto".
  - Em-dash (—) en cualquier parte. Reemplazar siempre por coma,
    paréntesis o punto y seguido.
  - Estructura "Primero, ... Segundo, ... Tercero, ...". Conectar
    con flujo natural.
  - **bold** como titular de insight dentro del cuerpo de slides 2/3.
    El template ya provee el encabezado. Arrancar con la frase directa.
  - Mencionar el segmento de audiencia en el texto (no decir
    "para tu empresa", "para empresas como la tuya", etc.).
  - "Los precios bajan" o "los costos bajan" como afirmación genérica
    SI no está cuantificado con % o monto específico. Si decís que algo
    baja, decir CUÁNTO y DESDE CUÁNDO.
  - "Cada vez más / menos" sin número concreto.
  - Contradecir otra slide del mismo newsletter. Si decís "los precios
    bajan" en slide 4, no digas en slide 2/3 que "los costos reales
    suben por la base documental". Si ambos son ciertos, integrá los
    dos en UN párrafo: "los precios de API bajan, pero el costo de
    implementar IA subió por datos, compliance y mantenimiento".

ESTRUCTURA OBLIGATORIA POR SLIDE:

SLIDE 1 (Resumen Ejecutivo Global, executive_summary):
  - 1-2 líneas: qué es AI Radar (para lector nuevo).
  - 1 frase-gancho con la tendencia del mes (afirmación concreta con
    número o nombre propio).
  - 2-3 párrafos cortos (3-4 oraciones c/u, total 600-900 chars).
  - NO es un resumen de cada insight global.
  - 2-3 fuentes inline al final con formato [TechCrunch](url).
  - NO incluir "conclusión incómoda" ni frases genéricas de apertura.

SLIDE 2 (Argentina, slide_2_text):
  - 1 frase-gancho con el caso local del mes (empresa nombrada).
  - 1-2 cifras concretas (% de mejora, monto, fecha).
  - 1 recomendación accionable para PyME.
  - Total 800-1900 chars. No más.

SLIDE 3 (España, slide_3_text):
  - Mismo formato que slide 2.
  - Total 800-1900 chars.

SLIDE 4 (Conclusiones, conclusions):
  - 1 párrafo de 300-700 chars.
  - 1 idea unificadora. NO es un resumen de países.
  - Estructura:
    * 1 oración con la afirmación fuerte.
    * 1-2 oraciones de por qué importa para una empresa.
    * (Opcional) 1 acción concreta que el lector puede hacer esta semana.
  - Si mencionás "precios bajan" o "costos bajan", DEBE estar
    cuantificado y/o matizado con el costo oculto de implementación.
"""


async def writer_node(state: dict) -> dict:
    """Refine research into polished newsletter content.

    Input: raw_report (RadarReport), slide_layouts (dict of SlideLayout)
    Output: newsletter_content (NewsletterContent)

    Skips the LLM call entirely if there are no insights to write about —
    this saves GPT-5.4 tokens and surfaces the abort_reason.
    """
    logger.info("▶ Writer node starting")

    # HARD GUARD: if the researcher flagged an abort, do NOT call GPT-5.4.
    # This saves tokens when there's nothing to write about.
    abort_reason = state.get("abort_reason")
    raw_report: RadarReport | None = state.get("raw_report")
    if abort_reason:
        logger.warning(
            "Writer short-circuit: abort_reason=%s — skipping LLM call to save tokens",
            abort_reason,
        )
        return {
            "newsletter_content": _aborted_content(raw_report, abort_reason),
            "abort_reason": abort_reason,
            "abort_detail": state.get("abort_detail"),
        }

    if not raw_report:
        logger.warning("No raw report found")
        return {
            "newsletter_content": NewsletterContent(subject="", body=""),
            "abort_reason": "no_raw_report",
            "abort_detail": "Writer called without a raw_report in state",
        }

    # HARD GUARD: if there are no insights at all, do not call GPT-5.4.
    if not raw_report.insights:
        logger.warning(
            "Writer short-circuit: raw_report has 0 insights — skipping LLM call"
        )
        return {
            "newsletter_content": _aborted_content(raw_report, "no_insights"),
            "abort_reason": "no_insights",
            "abort_detail": "Researcher returned a report with no insights",
        }

    # Load slide layouts (or use defaults)
    slide_layouts = state.get("slide_layouts") or get_slide_layouts()
    month_name = state.get("month_name", "")

    # Load previous newsletter conclusions for context
    history: list[dict] = []
    try:
        from community_manager.tools.dotnet_client import DotNetClient
        dotnet = DotNetClient()
        history = await dotnet.get_previous_conclusions(3)
        logger.info("Loaded %d previous newsletter conclusions for context", len(history))
    except Exception:
        logger.debug("Could not load newsletter history (may not exist yet)")

    # Group insights by country
    insights_by_country = _group_by_country(raw_report)

    # If a country has no coverage, fill with a short placeholder so the
    # slide doesn't end up with a 17% fill ratio and an empty slide.
    insights_by_country = _fill_empty_country_placeholders(
        insights_by_country, month_name
    )

    # Also push the synthetic placeholders back into raw_report.insights
    # so the downstream evaluator (which counts by country from the
    # report) sees them and doesn't abort the workflow.
    for country, insights in insights_by_country.items():
        existing = [i for i in raw_report.insights if i.country_tag == country]
        if not existing and insights:
            raw_report.insights.extend(insights)

    # Identify model launches for highlighting
    vendor_launches = _collect_vendor_launches(raw_report)

    # Build the prompt
    prompt = _build_writer_prompt(
        insights_by_country=insights_by_country,
        slide_layouts=slide_layouts,
        vendor_launches=vendor_launches,
        history=history,
        month_name=state.get("month_name", ""),
    )

    try:
        llm = get_newsletter_llm(temperature=0.3, max_tokens=4000)
        response = await llm.ainvoke([
            SystemMessage(content=WRITER_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        result = parse(raw)
    except JsonParseError as exc:
        logger.error("Writer JSON parse failed: %s. Raw preview: %s", exc, (raw if 'raw' in dir() else "")[:300].replace("\n", " "))
        return {"newsletter_content": _fallback_content(raw_report)}
    except Exception:
        logger.exception("Writer failed")
        return {"newsletter_content": _fallback_content(raw_report)}

    # Apply the result
    raw_report.report_title = result.get("report_title", raw_report.report_title)
    raw_report.executive_summary = result.get("executive_summary", raw_report.executive_summary)
    raw_report.slide_2_text = result.get("slide_2_text", "")
    raw_report.slide_3_text = result.get("slide_3_text", "")
    raw_report.conclusions = _strip_conclusion_subheaders(result.get("conclusions", ""))
    raw_report.slide_summary = result.get("slide_summary", "")

    # Post-generation validation: log warnings if slides are under/over filled
    _validate_fill(raw_report, slide_layouts)

    newsletter_content = NewsletterContent(
        subject=raw_report.subject,
        body=raw_report.executive_summary,
        report_title=raw_report.report_title,
        executive_summary=raw_report.executive_summary,
    )

    logger.info("✅ Writer completed: %s", newsletter_content.report_title[:60])
    return {"newsletter_content": newsletter_content}


# ════════════════════════════════════════════════════════════════════════════
#  Prompt construction
# ════════════════════════════════════════════════════════════════════════════

def _group_by_country(report: RadarReport) -> dict[str, list[RadarInsight]]:
    """Group insights by country_tag, combining primary and secondary.

    The scorer puts the best insight per country in ``insights`` and an
    optional secondary in ``insights_secondary``. The writer should treat
    both as available material and decide how to balance the slide content.
    """
    grouped: dict[str, list[RadarInsight]] = {"AR": [], "ES": [], "GLOBAL": []}
    for insight in list(report.insights) + list(report.insights_secondary or []):
        tag = (insight.country_tag or "GLOBAL").upper()
        if tag not in grouped:
            tag = "GLOBAL"
        grouped[tag].append(insight)
    return grouped


def _strip_conclusion_subheaders(text: str) -> str:
    """Strip leading/embedded Markdown sub-headers from Slide 4 conclusions.

    The Slide 4 template renders the title "Tendencias emergentes" itself,
    so any sub-header the LLM adds (e.g. "### Qué cambia este mes") is
    redundant. REGLA 10 instructs the LLM not to emit them, but we also
    strip defensively in case the LLM ignores the rule.

    Also strips standalone "**Primero**" / "**Segundo**" / "**Tercero**"
    enumeration markers — REGLA 4B forbids the enumerative structure, but
    if the LLM emits them as isolated bold lines we drop them.

    Removes lines that look like sub-headers at the start of the text or
    after a paragraph break. Keeps bold (since REGLA 4 uses it for insight
    titles — Slide 4 has no such titles).
    """
    import re
    if not text:
        return text
    # Pattern: lines starting with # (any level), -, *, or numbered lists
    # that look like section headers. Only strip lines that are short and
    # look like a header (no period at end, fewer than 80 chars).
    subheader_re = re.compile(r"^\s*(#{1,6}\s+|[-*]\s+)\S.{0,80}?$", re.MULTILINE)
    cleaned = subheader_re.sub("", text)
    # Also strip enumeration bold markers inline: "**Primero**, ..." or
    # "**Segundo**." or "**Tercero**: " — drop the bold marker + optional
    # punctuation. The flow becomes "la competencia..." instead of
    # "**Primero**, la competencia...".
    enum_inline_re = re.compile(
        r"\*\*\s*(Primero|Segundo|Tercero|Cuarto|Quinto)\s*\*\*\s*[\.,:;-]\s*",
        re.IGNORECASE,
    )
    cleaned = enum_inline_re.sub("", cleaned)
    # Also strip isolated enumeration bold markers on their own line
    enum_iso_re = re.compile(
        r"^\s*\*\*(Primero|Segundo|Tercero|Cuarto|Quinto)\*\*\s*[\.,:;-]?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    cleaned = enum_iso_re.sub("", cleaned)
    # Strip leading "El mes sugiere..." sentence if it appears at the start
    intro_re = re.compile(
        r"^\s*El\s+mes\s+(sugiere|indica|muestra|propone|revela|muestra)\s+[^.]+\.\s*",
        re.IGNORECASE,
    )
    cleaned = intro_re.sub("", cleaned)
    # Collapse any triple+ newlines left from the strip into double newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if cleaned != text.strip():
        logger.info("Stripped Markdown sub-headers from conclusions (defensive cleanup)")
    return cleaned


def _fill_empty_country_placeholders(
    by_country: dict[str, list[RadarInsight]],
    month_name: str,
) -> dict[str, list[RadarInsight]]:
    """Inject a placeholder insight for AR/ES when no coverage is available.

    The placeholder is a synthetic RadarInsight with a short, neutral
    message in Spanish. This prevents the writer from generating slides
    that are 17% full of nothing, and tells the reader (in the slide)
    that we just didn't find good material for that country this month.
    """
    from community_manager.models.schemas import RadarInsight
    country_names = {"AR": "Argentina", "ES": "España", "GLOBAL": "global"}
    for country in ("AR", "ES"):
        if not by_country.get(country):
            logger.info(
                "No %s coverage this month — injecting placeholder",
                country_names[country],
            )
            by_country[country] = [
                RadarInsight(
                    headline=(
                        f"Sin cobertura significativa de {country_names[country]} este mes"
                    ),
                    summary=(
                        f"En {month_name} no encontramos noticias de IA que "
                        f"ameritaran destaque local en {country_names[country]}: "
                        "los lanzamientos principales fueron globales. "
                        "Te recomendamos seguir los hallazgos de la sección GLOBAL."
                    ),
                    business_impact="",
                    source_title="AI Radar by Novit — placeholder",
                    source_url="https://ia.novitsoftware.com/",
                    source_date="",
                    country_tag=country,
                    category="",
                )
            ]
    return by_country


def _collect_vendor_launches(report: RadarReport) -> list[dict]:
    """Extract model launches for explicit highlighting in the prompt."""
    launches: list[dict] = []
    for insight in report.insights:
        if insight.is_model_launch and (insight.vendor or insight.model_name):
            launches.append({
                "vendor": insight.vendor,
                "model": insight.model_name,
                "benchmark": insight.benchmark_text,
                "pricing": insight.pricing_text,
                "source_title": insight.source_title,
                "source_url": insight.source_url,
            })
    # Also include top-level benchmark_data / pricing_data from the report
    if report.benchmark_data:
        launches.append({"indicator": "benchmark", "value": report.benchmark_data})
    if report.pricing_data:
        launches.append({"indicator": "pricing", "value": report.pricing_data})
    return launches


def _build_writer_prompt(
    *,
    insights_by_country: dict[str, list[RadarInsight]],
    slide_layouts: dict[str, SlideLayout],
    vendor_launches: list[dict],
    history: list[dict],
    month_name: str,
) -> str:
    """Build the full writer prompt with canvas metadata."""

    # ── Canvas section ─────────────────────────────────────────
    canvas = _format_canvas(slide_layouts)

    # ── Insights section ──────────────────────────────────────
    insights_block = _format_insights_block(insights_by_country, slide_layouts)

    # ── Vendor launches section ───────────────────────────────
    launches_block = _format_launches(vendor_launches)

    # ── History section ───────────────────────────────────────
    history_block = _format_history(history)

    # ── Rules section ─────────────────────────────────────────
    rules = _format_rules()

    # ── Output schema ─────────────────────────────────────────
    output_schema = """{
  "report_title": "string (max 80 chars, específico del mes)",
  "executive_summary": "string (Slide 1 — GLOBAL ONLY)",
  "slide_2_text": "string (Slide 2 — AR)",
  "slide_3_text": "string (Slide 3 — ES)",
  "conclusions": "string (Slide 4 — cierre del documento)",
  "slide_summary": "string (3 bullets, formato: • [AR] ... \\n• [ES] ... \\n• [GLOBAL] ...)"
}"""

    return f"""\
{canvas}

{insights_block}

{launches_block}

{history_block}

{rules}

OUTPUT ESPERADO
Devolvé SOLO este JSON (sin markdown, sin texto antes/después):
{output_schema}
"""


def _format_canvas(layouts: dict[str, SlideLayout]) -> str:
    parts = ["=" * 70, "CANVAS (datos del template, no estimaciones)", "=" * 70]
    labels = {
        "slide_1": "SLIDE 1 — Resumen Ejecutivo Global (campo: executive_summary)",
        "slide_2": "SLIDE 2 — Argentina (campo: slide_2_text)",
        "slide_3": "SLIDE 3 — España (campo: slide_3_text)",
        "slide_4": "SLIDE 4 — Conclusiones (campo: conclusions)",
    }
    for name, layout in layouts.items():
        w, h = layout.content_box[2], layout.content_box[3]
        parts.append(
            f"\n{labels.get(name, name)}\n"
            f"  Contenedor: {w} px ancho × {h} px alto\n"
            f"  Font del cuerpo: {layout.body_font_pt}pt\n"
            f"  Caracteres por línea: ~{layout.chars_per_line}\n"
            f"  Líneas disponibles: ~{layout.max_lines}\n"
            f"  Rango cómodo: {layout.min_chars} – {layout.max_chars} caracteres"
        )
    return "\n".join(parts)


def _format_insights_block(
    by_country: dict[str, list[RadarInsight]],
    layouts: dict[str, SlideLayout],
) -> str:
    parts = ["=" * 70, "MATERIAL DE LECTURA (no estás obligado a mencionarlos todos — seleccioná)", "=" * 70]
    slide_for_country = {"GLOBAL": "slide_1", "AR": "slide_2", "ES": "slide_3"}

    for country in ("GLOBAL", "AR", "ES"):
        insights = by_country.get(country, [])
        slide = layouts.get(slide_for_country[country])
        slide_label = labels_for(slide_for_country[country])
        cap = f"{slide.min_chars} – {slide.max_chars} chars" if slide else "?"

        if not insights:
            parts.append(
                f"\nSLIDE PARA {country}: sin insights de {country} este mes. "
                f"Para esa slide, generá un placeholder corto de 1-2 oraciones "
                f"reconociendo que no hubo cobertura significativa de {country} "
                f"en este período. NO inventes contenido."
            )
            continue

        parts.append(
            f"\nSLIDE PARA {country} (capacidad: {cap}): {len(insights)} insight(s)\n"
        )
        for i, insight in enumerate(insights, 1):
            launch_flag = " [LANZAMIENTO]" if insight.is_model_launch else ""
            vendor = f" ({insight.vendor})" if insight.vendor else ""
            model = f" — {insight.model_name}" if insight.model_name else ""
            benchmark = f" | benchmark: {insight.benchmark_text}" if insight.benchmark_text else ""
            pricing = f" | pricing: {insight.pricing_text}" if insight.pricing_text else ""

            parts.append(
                f"  {i}.{launch_flag} {insight.headline}{vendor}{model}{benchmark}{pricing}\n"
                f"     Resumen: {insight.summary[:300]}\n"
                f"     Impacto: {insight.business_impact[:200]}\n"
                f"     Fuente: [{insight.source_title or 'MEDIO'}]({insight.source_url})\n"
            )

    return "\n".join(parts)


def labels_for(slide_name: str) -> str:
    return {
        "slide_1": "Slide 1 — Resumen Ejecutivo Global",
        "slide_2": "Slide 2 — Argentina",
        "slide_3": "Slide 3 — España",
        "slide_4": "Slide 4 — Conclusiones",
    }.get(slide_name, slide_name)


def _format_launches(launches: list[dict]) -> str:
    if not launches:
        return "\n(No hay lanzamientos de modelos destacados este mes.)"
    parts = ["=" * 70, "LANZAMIENTOS DESTACADOS DEL MES (no se te pueden escapar)", "=" * 70]
    for launch in launches:
        if "indicator" in launch:
            parts.append(f"  • Indicador ({launch['indicator']}): {launch['value']}")
        else:
            v = launch.get("vendor", "?")
            m = launch.get("model", "?")
            b = launch.get("benchmark", "")
            p = launch.get("pricing", "")
            parts.append(
                f"  • {v} — {m}"
                + (f" — {b}" if b else "")
                + (f" — {p}" if p else "")
            )
    return "\n".join(parts)


def _format_history(history: list[dict]) -> str:
    if not history:
        return ""
    parts = ["=" * 70, "EDICIONES ANTERIORES (para coherencia editorial)", "=" * 70]
    for h in history:
        title = (h.get("report_title", "") or "")[:80] or h.get("month_key", "")
        concl = (h.get("conclusions", "") or "")[:250]
        if concl:
            parts.append(f"\n  {h.get('month_key', '?')} — {title}\n    \"{concl}...\"")
    parts.append(
        "\nPodés hacer referencias cruzadas si ves patrones:\n"
        "\"Esto refuerza lo que vimos en {mes}...\" o \"Esto podría estar\n"
        "modificando lo que vimos en {mes}...\". NO inventes meses que no\n"
        "aparezcan explícitamente arriba."
    )
    return "\n".join(parts)


def _format_rules() -> str:
    return """\
═══════════════════════════════════════════════════════════════════════════
REGLAS DE ESTILO Y DECISIÓN (leelas con atención)
═══════════════════════════════════════════════════════════════════════════

REGLA 0 — ESTILO EDITORIAL: No sos un resumidor. Sos un editorialista que
escribe para un ejecutivo que quiere entender QUÉ IMPORTA este mes y POR
QUÉ. El material de lectura (insights) es tu referencia, NO un checklist.
NO menciones todo "para que no falte nada". Seleccioná. Si hay 5 insights
y solo 1 importa de verdad, escribí sobre ESE. Si ninguno importa, decilo.

La estructura del newsletter es:
  • Slide 1 — Executive Summary: contexto editorial + la idea más importante
    del mes. NO es un resumen de todas las noticias globales.
  • Slide 2/3 — Argentina/España: 1-2 historias relevantes por país.
    Seleccioná la más significativa, no enumeres todo.
  • Slide 4 — Conclusiones: una sola idea unificadora. Qué significa todo
    esto PARA UNA EMPRESA.

El template visual ya tiene los encabezados ("ARGENTINA", "ESPAÑA").
No los repitas con bold.

REGLA 1 — LONGITUD. Apuntá a un 70-90% de la capacidad del slide. No te
obsesiones con llenar hasta el tope: un slide con 60% de contenido potente
es mejor que uno con 100% de relleno. Si te pasás del tope, recortá sin
piedad. Si queda mucho aire, expandí con análisis de fondo, no con
generalidades.

Tope duro por slide:
  - slide_1 (executive_summary): MÁXIMO 900 caracteres.
  - slide_2 (AR) / slide_3 (ES): MÁXIMO 1900 caracteres.
  - slide_4 (conclusions): MÁXIMO 700 caracteres.

REGLA 2 — COBERTURA EDITORIAL (esto es lo más importante de todas las
reglas). Los insights en "MATERIAL DE LECTURA" son eso: material. No estás
obligado a usarlos. Tu trabajo no es "cubrir todo lo que pasó" sino
"decir qué es lo que importa de lo que pasó". Reglas concretas:
  a) Si un insight no suma, NO lo menciones.
  b) Si un insight merece desarrollo, desarrollalo (aunque sacrifiques
     otros).
  c) NO uses "en tanto", "por otro lado", "asimismo", "cabe destacar",
     "vale la pena mencionar" para forzar conexiones entre insights no
     relacionados.
  d) El lector prefiere UNA historia bien contada a TRES historias
     mencionadas al pasar.

REGLA 3 — PRIMER PÁRRAFO ES GANCHO. Empezá cada slide con una frase que
enganche al lector: una afirmación fuerte, una cifra, un contraste, o una
pregunta. NO arranques con contexto, ni con "El mes sugiere", "En este
contexto", "Cabe destacar", "El análisis indica". Ejemplos de buen gancho:
  - "Opus 4.8 cambia el cálculo de costo: el esfuerzo es ahora una variable
    de ruteo."
  - "BBVA entra como accionista de OpenAI. El copiloto corporativo deja de
    ser producto, pasa a ser infraestructura."
  - "El 'Gemelo Digital Social' pone datos anonimizados del Estado en el
    centro. La pregunta no es técnica, es de gobernanza."

REGLA 3B — SLIDE 1 (Resumen Ejecutivo Global) arranca con 1-2 líneas que
expliquen QUÉ es AI Radar para un lector que lo abre por primera vez.
Ejemplo: "AI Radar es el newsletter mensual de Novit Software. Cada mes
seleccionamos la noticia de IA que más impacta a empresas en
Latinoamérica." Después de ese intro, desarrollá UNA idea fuerte del mes.
NO es un resumen de cada insight global — elegí el más importante y andá
a fondo. Las tablas de la derecha ya muestran números benchmark/pricing;
el texto no los repite, explica el paisaje alrededor.

REGLA 6 — Si una noticia es un LANZAMIENTO de modelo, mencionalo en la
frase-gancho del insight (sin bold necesario). Incluí siempre el benchmark
y pricing comparativo en el cuerpo cuando estén disponibles, no solo en un
cuadro lateral.

REGLA 7 — NO inventes datos, NO repitas la misma info en 2 slides, NO uses
asteriscos sueltos, NO uses emojis. NO uses bloques de texto de más de 3
oraciones seguidas — eso satura la slide.

REGLA 7B — USO DE **BOLD**: el bold es para conceptos CLAVE dentro del
párrafo, no para titular el insight entero. Marcá en **bold** solo:
  - Empresas / vendors ("**Anthropic**", "**OpenAI**", "**BBVA**").
  - Productos / modelos ("**Opus 4.8**", "**GPT-5.5**", "**Copilot**").
  - Decisiones regulatorias o legales ("**AI Act**", "**multa de 35M €**",
    "**ley de IA española**").
  - Métricas o cifras clave si querés resaltarlas ("**200% a 2000%**" de
    productividad, "**300 tokens/s**", "**15.000 developers**").
NO uses **bold** para titular el insight entero. NO abuses del bold (no
más de 3-4 bold-runs por párrafo). El bold guía la lectura, no la decora.

REGLA 8 — Fuentes: el texto visible del link DEBE ser el nombre del medio,
NO "Fuente:". Si la URL está truncada o vacía, NO pongas link — solo escribí
el nombre del medio. Las URLs ya fueron validadas con HEAD request y filtradas
por calidad editorial.

REGLA 9 — Slide 1 (GLOBAL) usá SOLO insights de GLOBAL. Slide 2 (AR) usá SOLO
insights de AR. Slide 3 (ES) usá SOLO insights de ES. NO mezcles países.

REGLA 10 — Slide 4 (campo `conclusions`) es UN párrafo de 300-700 chars.
Respondé UNA SOLA PREGUNTA: "de todo lo que pasó este mes, ¿qué es lo
único que debería quedarse un ejecutivo?" NO es un resumen de países ni
de insights. Elegí LA idea más importante del mes — aunque haya salido
de UNA sola noticia, no de todas — y desarrollala.

Estructura:
  1. Afirmación fuerte de 1 oración que captura la idea que elegiste.
     ("Que Anthropic firme un acuerdo de seguridad nacional con USA cambia
     el tablero: la IA deja de ser solo tecnología, pasa a ser
     infraestructura de estado.")
  2. 1-2 oraciones de por qué importa AHORA para una empresa.
  3. NO menciones países a menos que el contraste los justifique.
     NO uses bold, em-dash, "en resumen", "para concluir",
     "Primero/Segundo/Tercero", ni enumeraciones.

REGLA 11 — El tono debe ser ejecutivo y sobrio. NO uses palabras como
"increíble", "revolucionario", "impresionante", "asombroso". Usá datos
concretos y comparaciones (costos, benchmarks, fechas).

REGLA 12 — Em-dash (—) PROHIBIDO en todo el documento. Reemplazar siempre por:
  - Coma: "fraude, soporte y ciberseguridad" (en vez de "fraude — soporte — ciberseguridad").
  - Punto y seguido: cambia de idea.
  - Paréntesis para aclaraciones.
  NUNCA escribir: "hacia procesos críticos — fraude, soporte — donde...".

REGLA 13 — Lectura crítica cuando el caso lo amerita. Si una noticia tiene
ángulo cuestionable, riesgo escondido o costo oculto, mencionalo con datos.
  ❌ "Esto puede sugerir más trazabilidad en políticas públicas."
  ✅ "El problema no es la IA, es la gobernanza de los datos anonimizados
      que necesita el modelo. Si el dato sale sesgado, la decisión se
      institucionaliza con sesgo."
Si no hay ángulo crítico, mantené el dato concreto. Pero no caigas en la
conclusión genérica positiva.

REGLA 14 — ÁNGULO DEL ANÁLISIS (clave para diferenciarse). PROHIBIDO el cliché
comparativo-negativo: "ya no es X, es Y", "no se trata de A sino de B",
"el debate dejó de ser... ahora es...", "la discusión no es X sino Y".
Eso es marca registrada de contenido de IA genérica y el lector lo detecta
inmediatamente. En su lugar, elegí UNO de estos ángulos (y variá entre
insights, no repitas el mismo siempre):

  1. PREDICTIVO — qué podemos esperar en los próximos 1-3 meses a partir de
     lo que acaba de pasar. Útil cuando hay un movimiento de mercado nuevo
     (pricing, regulación, lanzamiento) con derivada clara.
       "Si Meta mantiene el ritmo de降价 del 30% por trimestre, para
        septiembre el modelo abierto más capaz costará menos que GPT-4o
        mini de hace 12 meses."

  2. ADVISORY — qué le recomendás a un tomador de decisión en una PyME
     que está mirando esta noticia. Útil cuando hay una decisión concreta
     en juego (contratar, esperar, normar, comprar plataforma).
       "Para una PyME evaluando copilots, la señal accionable es no
        apostar a un solo vendor: el costo del switching cayó a una
        semana de re-fine-tuning."

  3. TENDENCIA — qué patrón macro se ve en el mercado o en la economía
     (inversión, empleo, regulación, consumo) respecto de la IA,
     directamente o como derivado. Útil cuando un solo insight revela un
     movimiento más grande.
       "La caída del 18% en vacantes para data entry que reporta InfoJobs
        desde marzo es el primer indicador macro de que la IA ya está
        moviendo el empleo administrativo, no la promesa sino el hecho."

  4. CRÍTICO ESTRUCTURADO — usa el formato de REGLA 13 pero extendido:
     costo oculto, riesgo de gobernanza, sesgo en datos. Reservalo para
     insights donde hay un ángulo cuestionable real, no para forzar
     crítica donde no la hay.

Regla práctica: si tu primer borrador dice "ya no es X, es Y", reescribilo
como predictivo, advisory o de tendencia. Si el insight no encaja en
ninguno de los 4 ángulos, probablemente no es insight: descartalo.

REGLA 15 — SLIDE 1 (Resumen Ejecutivo) debe incluir 2-3 fuentes inline al
final del texto (no en una sección aparte). Las tablas de la derecha no
muestran fuentes, así que el slide 1 es el único lugar donde el lector
vee el sustento editorial. Formato:
  "...el patrón de pricing a la baja se sostiene en los últimos 90 días.
   [TechCrunch](https://...) [Anthropic](https://...) [Reuters](https://...)"

No repetir la misma fuente más de una vez. Si el slide 1 cita 2 fuentes
que ya aparecieron en slides 2/3, está bien: el resumen ejecutivo
justifica la curaduría.
"""


# ════════════════════════════════════════════════════════════════════════════
#  Post-generation validation (no retries)
# ════════════════════════════════════════════════════════════════════════════

def _validate_fill(report: RadarReport, layouts: dict[str, SlideLayout]) -> None:
    """Log warnings if any slide is significantly under/over filled.

    Does NOT retry — the writer's single pass is the final answer. The
    warnings are surfaced in logs for human review.

    Tolerance: 50% minimum (slide too empty), 105% maximum (slide will
    trim a bit but is acceptable).
    """
    fields_layouts = [
        ("executive_summary", layouts.get("slide_1")),
        ("slide_2_text", layouts.get("slide_2")),
        ("slide_3_text", layouts.get("slide_3")),
        ("conclusions", layouts.get("slide_4")),
    ]
    for field_name, layout in fields_layouts:
        if not layout:
            continue
        text = getattr(report, field_name, "")
        ratio = layout.fill_ratio(text)
        if ratio < 0.50:
            logger.warning(
                "Writer fill: %s = %d/%d chars (%.0f%%) — slide queda vacía, expandir manualmente",
                field_name, len(text), layout.max_chars, ratio * 100,
            )
        elif ratio > 1.05:
            logger.warning(
                "Writer fill: %s = %d/%d chars (%.0f%%) — se va a cortar un poco, aceptable hasta 105%%",
                field_name, len(text), layout.max_chars, ratio * 100,
            )


def _fallback_content(report: RadarReport) -> NewsletterContent:
    """Return a minimal NewsletterContent when the writer fails."""
    return NewsletterContent(
        subject=report.subject if report else "AI Radar by Novit",
        body=report.executive_summary if report else "",
        report_title=report.report_title if report else "AI Radar",
        executive_summary=report.executive_summary if report else "",
    )


def _aborted_content(report: RadarReport, abort_reason: str) -> NewsletterContent:
    """Return a stub NewsletterContent when the workflow is being aborted.

    The body is a short, transparent explanation of why we are not
    generating a newsletter this cycle. No LLM tokens are spent.
    """
    reason_messages = {
        "no_search_results": "No se pudo generar AI Radar: Serper no devolvió resultados. Revisar saldo de credits en serper.dev/billing.",
        "no_valid_insights": "No se pudo generar AI Radar: todos los insights extraídos fallaron validación de URL o filtro de recencia.",
        "insufficient_insights": "No se pudo generar AI Radar: no se alcanzó el mínimo de insights por país.",
        "ai_not_configured": "No se pudo generar AI Radar: el endpoint de newsletter AI no está configurado.",
        "serper_not_configured": "No se pudo generar AI Radar: NURTURING_SERPER_API_KEY no está configurada.",
        "no_insights": "No se pudo generar AI Radar: el researcher no devolvió insights.",
        "researcher_exception": "No se pudo generar AI Radar: error inesperado en el researcher.",
    }
    body = reason_messages.get(abort_reason, f"No se pudo generar AI Radar: {abort_reason}")
    return NewsletterContent(
        subject=report.subject if report else "AI Radar by Novit",
        body=body,
        report_title=report.report_title if report else "AI Radar",
        executive_summary=body,
    )

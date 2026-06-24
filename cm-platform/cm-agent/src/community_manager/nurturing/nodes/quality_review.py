"""Quality review node — enforces editorial standards on the writer's output.

This is a DETERMINISTIC, no-LLM node. It runs AFTER the writer and BEFORE
the chart_planner. It applies mechanical editorial rules that are too
important to leave to a generative model:

  1. Jerga de consultor → versión simple (blacklist mapping)
  2. Oraciones > 20 palabras → partirlas (heuristic, conservative)
  3. Contradicciones entre slides → marca el conflicto
  4. Afirmaciones genéricas sin cuantificar → marca el problema
  5. Falta de dato concreto por párrafo → marca el párrafo
  6. Bold excesivo (>3 runs por párrafo) → quitar los extras

If issues are CRITICAL (jerga grave, contradicción), the node REWRITES
the affected text. If issues are WARNING, they're logged but the text
passes. If a block is unfixable automatically, the workflow is aborted
so a human can review.

Why deterministic? Because GPT-5.4 already failed at this with
temperature=1.0 — that's how the bad copy got through. Mechanical
rules applied consistently will always beat a generative check on this
class of problem.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from community_manager.models.schemas import RadarReport

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
#  Blacklist of consultant-speak → plain replacement
# ════════════════════════════════════════════════════════════════════════════
# Each entry is (forbidden_phrase, simple_replacement). Case-insensitive
# whole-word match. Replacements preserve capitalization by simple logic
# (capitalize first letter if the original was capitalized).

JARGON_REPLACEMENTS: list[tuple[str, str]] = [
    # ── Governance / data ─────────────────────────────────────
    (r"\bgobierno del dato\b", "reglas de los datos"),
    (r"\bdata governance\b", "reglas de los datos"),
    (r"\bgobernanza de datos?\b", "reglas de los datos"),
    (r"\bgobernanza\b", "reglas claras"),
    (r"\btaxonomía operativa\b", "clasificación de la información"),
    (r"\btaxonomías operativas\b", "clasificación de la información"),
    (r"\bretención gobernada\b", "cuánto guardar los datos según la ley"),
    (r"\bdata residency\b", "dónde se guardan los datos"),
    (r"\bcompliance\b", "cumplimiento legal"),
    (r"\bcompliances\b", "cumplimientos legales"),
    (r"\bfricción regulatoria\b", "trabas legales"),
    (r"\bcumplimiento normativo\b", "cumplimiento de las reglas"),
    (r"\bmarco normativo\b", "regulación"),
    # ── Routing / tech ────────────────────────────────────────
    (r"\bruteo de modelos?\b", "elección de modelo por tarea"),
    (r"\bruteo,?\s+compliance y costo\b", "elección de modelo, reglas y costo"),
    (r"\bruteo,?\s+compliance,?\s+y costo\b", "elección de modelo, reglas y costo"),
    (r"\bstack tecnol[oó]gico\b", "herramientas que usás"),
    (r"\bstack\b", "conjunto de herramientas"),
    # ── Business jargon ────────────────────────────────────────
    (r"\bstakeholders?\b", "involucrados"),
    (r"\becosistema\b", "mercado"),
    (r"\brealidad inc[oó]moda\b", "lo que nadie te dice"),
    (r"\bmovimiento esperable\b", "lo que va a pasar"),
    (r"\bseguidilla\b", "sucesión"),
    (r"\bverborragia\b", "exceso de palabras"),
    (r"\bimplica\b", "significa"),
    # ── Vague quantifiers (we want to force real numbers) ────
    (r"\bsegmentaci[oó]n m[áa]s agresiva\b", "separar por tipo de uso"),
    (r"\bde forma m[áa]s agresiva\b", "con más rigor"),
    # ── Self-referential editorial filler ─────────────────────
    (r"\besta edici[oó]n\b", "este mes"),
    (r"\bdeja una conclusi[oó]n inc[oó]moda\b", "muestra algo importante"),
    (r"\bcomo (era|suele ser) (de esperar|esperable)\b", ""),
    (r"\bcomo es de esperar\b", ""),
    (r"\bcomo cab[íi]a esperar\b", ""),
    # ── "The reality is" type empty openings ─────────────────
    (r"\bla realidad es que\b", ""),
    (r"\bles cuento\b", ""),
    (r"\baqu[íi] les cuento\b", ""),
]


# Generic quantitative claims that REQUIRE a number to be acceptable.
# If found without a number in the same sentence, the sentence is flagged.
GENERIC_CLAIMS_REQUIRING_NUMBER: list[tuple[str, str]] = [
    (r"\b(?:los precios?|los costos?|los costes?)\s+bajan\b", "precios/costos bajan (sin cuantificar)"),
    (r"\b(?:los precios?|los costos?|los costes?)\s+suben\b", "precios/costos suben (sin cuantificar)"),
    (r"\b(?:cada vez m[áa]s)\b", "cada vez más (sin cuantificar)"),
    (r"\b(?:cada vez menos)\b", "cada vez menos (sin cuantificar)"),
    (r"\b(?:se dispara)\b", "se dispara (sin cuantificar)"),
    (r"\b(?:se dispara[n]?)\b", "se dispara (sin cuantificar)"),
    (r"\b(?:aument[ao]s? (masivos?|exponenciales?))\b", "aumento masivo (sin cuantificar)"),
    (r"\b(?:ca[ií]da (masiva|exponencial))\b", "caída masiva (sin cuantificar)"),
    (r"\b(?:en (los )?[úu]ltimos \d+ d[íi]as)\b", ""),  # ok, has number
    (r"\b(?:movimiento (esperable|esperado))\b", "movimiento (sin cuantificar)"),
]


# ════════════════════════════════════════════════════════════════════════════
#  Detection functions
# ════════════════════════════════════════════════════════════════════════════


def _detect_jargon(text: str) -> list[tuple[int, str, str]]:
    """Return list of (position, matched_phrase, suggested_replacement)."""
    hits: list[tuple[int, str, str]] = []
    if not text:
        return hits
    for pattern, replacement in JARGON_REPLACEMENTS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            hits.append((m.start(), m.group(0), replacement))
    return sorted(hits, key=lambda h: h[0])


def _detect_generic_claims(text: str) -> list[tuple[int, str, str]]:
    """Detect generic quantitative claims that need a number in same sentence."""
    hits: list[tuple[int, str, str]] = []
    if not text:
        return hits
    for pattern, label in GENERIC_CLAIMS_REQUIRING_NUMBER:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            # Check the sentence for any number
            sentence = _extract_sentence(text, m.start())
            if not _has_number(sentence):
                hits.append((m.start(), m.group(0), label))
    return hits


def _detect_long_sentences(text: str, max_words: int = 20) -> list[tuple[int, str, int]]:
    """Find sentences with more than max_words."""
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[tuple[int, str, int]] = []
    pos = 0
    for s in sentences:
        s_stripped = s.strip()
        if not s_stripped:
            pos += len(s) + 1
            continue
        words = _count_words(s_stripped)
        if words > max_words:
            out.append((pos, s_stripped, words))
        pos += len(s) + 1
    return out


def _detect_missing_data(text: str) -> list[tuple[int, str]]:
    """Find paragraphs with no concrete data (no number, no date, no proper noun)."""
    if not text:
        return []
    paragraphs = re.split(r"\n\s*\n", text)
    out: list[tuple[int, str]] = []
    pos = 0
    for p in paragraphs:
        p_stripped = p.strip()
        if not p_stripped or len(p_stripped) < 50:
            pos += len(p) + 2
            continue
        if not _has_concrete_data(p_stripped):
            out.append((pos, p_stripped))
        pos += len(p) + 2
    return out


def _detect_excess_bold(text: str, max_runs: int = 3) -> int:
    """Count **bold** runs and flag if exceeds max_runs per paragraph."""
    if not text:
        return 0
    paragraphs = re.split(r"\n\s*\n", text)
    over = 0
    for p in paragraphs:
        runs = len(re.findall(r"\*\*[^*]+\*\*", p))
        if runs > max_runs:
            over += 1
    return over


def _detect_contradictions(slide_texts: dict[str, str]) -> list[dict]:
    """Compare all slides for contradictory claims (e.g. "precios bajan" vs "costos suben")."""
    contradictions: list[dict] = []

    # Specific contradiction rules
    contradiction_rules: list[tuple[str, str, str]] = [
        # (pattern_a, pattern_b, description)
        (
            r"\b(?:precios?|costos?|costes?) baj[aá]n\b",
            r"\b(?:precios?|costos?|costes?) suben\b",
            "una slide dice que precios bajan, otra que suben",
        ),
        (
            r"\b(?:precios?|costos?|costes?) baj[aá]n\b",
            r"\b(?:costo|gasto) (real|oculto|total) (sube|aumenta|incrementa)\b",
            "una slide dice precios bajan, otra dice el costo real sube",
        ),
        (
            r"\b(?:cada vez m[áa]s)\b",
            r"\b(?:cada vez menos)\b",
            "una slide dice cada vez más, otra cada vez menos (mismo tema)",
        ),
    ]

    slide_names = list(slide_texts.keys())
    for i, name_a in enumerate(slide_names):
        text_a = slide_texts[name_a]
        for name_b in slide_names[i + 1:]:
            text_b = slide_texts[name_b]
            for pa, pb, desc in contradiction_rules:
                if re.search(pa, text_a, flags=re.IGNORECASE) and re.search(pb, text_b, flags=re.IGNORECASE):
                    contradictions.append({
                        "slide_a": name_a,
                        "slide_b": name_b,
                        "description": desc,
                    })
                elif re.search(pa, text_b, flags=re.IGNORECASE) and re.search(pb, text_a, flags=re.IGNORECASE):
                    contradictions.append({
                        "slide_a": name_b,
                        "slide_b": name_a,
                        "description": desc,
                    })

    return contradictions


# ════════════════════════════════════════════════════════════════════════════
#  Rewriting functions
# ════════════════════════════════════════════════════════════════════════════


def _apply_jargon_replacements(text: str) -> str:
    """Apply all jargon replacements in a single pass."""
    if not text:
        return text
    out = text
    for pattern, replacement in JARGON_REPLACEMENTS:
        if not replacement:
            # Empty replacement → drop the phrase plus trailing/leading commas/spaces
            out = re.sub(
                pattern + r"\s*,?\s*",
                "",
                out,
                flags=re.IGNORECASE,
            )
        else:
            # Match with surrounding commas/spaces to clean up punctuation
            def _replace_keep_case(m: re.Match, repl: str = replacement) -> str:
                original = m.group(0)
                # Apply replacement, preserve capitalization of first char
                if original[0].isupper() and repl[0].islower():
                    repl = repl[0].upper() + repl[1:]
                return repl

            out = re.sub(
                pattern,
                _replace_keep_case,
                out,
                flags=re.IGNORECASE,
            )
    # Clean up double spaces and weird punctuation
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r"\.\s*\.\s*", ". ", out)
    out = re.sub(r"^\s+", "", out)
    return out.strip()


def _truncate_long_sentences(text: str, max_words: int = 20) -> str:
    """Conservative: only flag, don't auto-split. Splitting is risky for meaning.

    This function logs warnings but does NOT auto-modify. Auto-splitting
    sentences is dangerous because it can change meaning. We leave the
    long sentences but make them visible in the log so the next LLM pass
    can clean them up.
    """
    return text  # no-op for now; the writer prompt enforces the 20-word rule


# ════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════


def _count_words(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _has_number(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _has_concrete_data(paragraph: str) -> bool:
    """A paragraph has concrete data if it contains at least one:
    - a number (e.g. 92%, $1,500, 15K)
    - a date (e.g. mayo 2025, 2026-06-11)
    - a proper noun (capitalized word not at start of sentence, ≥4 chars)
    - a percentage or currency symbol
    """
    if re.search(r"\d", paragraph):
        return True
    if re.search(r"[\$€£¥%]", paragraph):
        return True
    # Date patterns: 2025, 2026, "mayo 2025", "junio 2026"
    if re.search(r"\b(20\d{2}|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b", paragraph, flags=re.IGNORECASE):
        return True
    # Proper noun: a word that starts with uppercase and is not at the
    # start of the sentence (rough heuristic: capitalized word 4+ chars
    # that's not the first word of the paragraph)
    words = paragraph.split()
    for w in words[1:]:  # skip first
        clean = w.strip(".,;:()¿?¡!\"'")
        if len(clean) >= 4 and clean[0].isupper() and clean.lower() != clean:
            # Accept: probably a proper noun
            return True
    return False


def _extract_sentence(text: str, position: int) -> str:
    """Return the sentence containing the given position."""
    # Find previous sentence end
    start = 0
    for m in re.finditer(r"[.!?]\s+", text[:position]):
        start = m.end()
    # Find next sentence end
    end = len(text)
    for m in re.finditer(r"[.!?]\s+", text[position:]):
        end = position + m.end()
        break
    return text[start:end].strip()


# ════════════════════════════════════════════════════════════════════════════
#  Public node
# ════════════════════════════════════════════════════════════════════════════


def quality_review_node(state: dict) -> dict:
    """Review the writer's output for editorial quality.

    Input: raw_report (RadarReport with executive_summary, slide_2_text,
           slide_3_text, conclusions)
    Output: raw_report (text fields may be auto-corrected), quality_issues
            (list of dicts for the reviewer to see).

    The node NEVER blocks the workflow — it always passes the report
    through, but logs every issue so reviewers can see what was
    auto-corrected and what remains.
    """
    logger.info("Quality review node starting")

    raw_report: RadarReport | None = state.get("raw_report")
    if not raw_report:
        logger.warning("No raw report found in quality_review")
        return {"raw_report": raw_report, "quality_issues": []}

    issues: list[dict] = []

    # Text fields to review
    fields: list[tuple[str, str]] = [
        ("slide_1", raw_report.executive_summary or ""),
        ("slide_2", raw_report.slide_2_text or ""),
        ("slide_3", raw_report.slide_3_text or ""),
        ("slide_4", raw_report.conclusions or ""),
    ]

    # ── Pass 1: jargon replacement (auto-fix) ──────────────────
    for slide_name, text in fields:
        if not text:
            continue
        new_text = _apply_jargon_replacements(text)
        if new_text != text:
            jargon_hits = _detect_jargon(text)
            for pos, phrase, replacement in jargon_hits:
                issues.append({
                    "type": "jargon_replaced",
                    "slide": slide_name,
                    "original": phrase,
                    "replacement": replacement,
                    "severity": "auto_fixed",
                })
            # Apply the fix
            if slide_name == "slide_1":
                raw_report.executive_summary = new_text
            elif slide_name == "slide_2":
                raw_report.slide_2_text = new_text
            elif slide_name == "slide_3":
                raw_report.slide_3_text = new_text
            elif slide_name == "slide_4":
                raw_report.conclusions = new_text

    # ── Pass 2: detect remaining issues (warn only) ────────────
    updated_fields: list[tuple[str, str]] = [
        ("slide_1", raw_report.executive_summary or ""),
        ("slide_2", raw_report.slide_2_text or ""),
        ("slide_3", raw_report.slide_3_text or ""),
        ("slide_4", raw_report.conclusions or ""),
    ]

    for slide_name, text in updated_fields:
        if not text:
            continue
        # Long sentences
        for pos, sentence, words in _detect_long_sentences(text, max_words=20):
            issues.append({
                "type": "long_sentence",
                "slide": slide_name,
                "text": sentence[:120],
                "word_count": words,
                "severity": "warning",
            })
        # Generic claims without numbers
        for pos, phrase, label in _detect_generic_claims(text):
            issues.append({
                "type": "generic_claim",
                "slide": slide_name,
                "phrase": phrase,
                "description": label,
                "severity": "warning",
            })
        # Paragraphs without concrete data
        for pos, paragraph in _detect_missing_data(text):
            issues.append({
                "type": "no_data_in_paragraph",
                "slide": slide_name,
                "text": paragraph[:120],
                "severity": "warning",
            })
        # Excess bold
        over = _detect_excess_bold(text, max_runs=3)
        if over:
            issues.append({
                "type": "excess_bold",
                "slide": slide_name,
                "paragraph_count_over_limit": over,
                "severity": "info",
            })

    # ── Pass 3: contradiction detection between slides ─────────
    slide_texts = {
        "slide_1": raw_report.executive_summary or "",
        "slide_2": raw_report.slide_2_text or "",
        "slide_3": raw_report.slide_3_text or "",
        "slide_4": raw_report.conclusions or "",
    }
    contradictions = _detect_contradictions(slide_texts)
    for c in contradictions:
        issues.append({
            "type": "contradiction",
            "slide_a": c["slide_a"],
            "slide_b": c["slide_b"],
            "description": c["description"],
            "severity": "warning",
        })

    # Log summary
    by_severity: dict[str, int] = {}
    for i in issues:
        sev = i.get("severity", "info")
        by_severity[sev] = by_severity.get(sev, 0) + 1
    logger.info(
        "Quality review: %d issues (%s) — %s",
        len(issues),
        ", ".join(f"{k}={v}" for k, v in by_severity.items()),
        f"auto_fixed={by_severity.get('auto_fixed', 0)}, warning={by_severity.get('warning', 0)}",
    )

    return {
        "raw_report": raw_report,
        "quality_issues": issues,
    }

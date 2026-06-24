"""Robust JSON parser for LLM outputs.

Used by researcher, content_scorer, and writer nodes to handle common
LLM output failures (markdown fences, control chars, trailing commas,
smart quotes, JSON wrapped in prose).

Fails loudly (raises JsonParseError) instead of silently returning
empty data. Callers should catch and decide whether to retry or abort.
"""

from __future__ import annotations

import json
import re
from typing import Any


class JsonParseError(Exception):
    """Raised when JSON cannot be parsed from LLM output."""

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def _strip_bom_and_fences(text: str) -> str:
    """Remove BOM, leading ```json fences, and trailing ``` fences."""
    cleaned = text.strip()
    if cleaned.startswith("\ufeff"):
        cleaned = cleaned[1:]
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1 :]
        else:
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].rstrip()
    return cleaned.strip()


def _extract_json_object(text: str) -> str | None:
    """Find the first balanced {...} substring (greedy from first { to last })."""
    start = text.find("{")
    if start == -1:
        return None
    end = text.rfind("}")
    if end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _escape_unescaped_control_chars_in_strings(s: str) -> str:
    """Escape literal newlines/tabs/CR that appear inside JSON string values.

    LLMs often produce JSON like:
        {"key": "line 1
                  line 2"}
    which is invalid JSON because the newline inside the string is not escaped.

    This function walks the string and escapes any unescaped control chars
    (newlines, tabs, CRs) that appear between unescaped double quotes.
    """
    out: list[str] = []
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            out.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            out.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string and ch in ("\n", "\r", "\t"):
            if ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            continue
        out.append(ch)
    return "".join(out)


def _repair_common_errors(s: str) -> str:
    """Apply cheap repairs for common LLM JSON issues."""
    # Trailing commas before } or ]
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    # Smart quotes
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    # Remove control chars (except whitespace, which we handle below)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    # Escape unescaped newlines/tabs/CRs inside JSON string values
    s = _escape_unescaped_control_chars_in_strings(s)
    return s


def parse(raw: str, *, max_repair_passes: int = 3) -> dict | list:
    """Parse JSON from raw LLM output. Raises JsonParseError on failure.

    Order of operations:
      1. Strip BOM and code fences.
      2. Try json.loads directly.
      3. If fails, try to extract a JSON object from the surrounding text.
      4. Apply common repairs (trailing commas, smart quotes, control chars).
      5. Retry up to max_repair_passes times after repairs.
      6. If still failing, raise JsonParseError with the raw content.

    Also handles the common case of the LLM emitting a stray trailing
    "Extra data" — usually a duplicated closing brace. We try truncating
    to the error position as a fallback.
    """
    if not raw or not raw.strip():
        raise JsonParseError("Empty LLM response", raw or "")

    cleaned = _strip_bom_and_fences(raw)

    # Pass 1: try as-is
    for attempt in range(max_repair_passes + 1):
        candidates: list[str] = []
        if attempt == 0:
            candidates.append(cleaned)
            extracted = _extract_json_object(cleaned)
            if extracted and extracted != cleaned:
                candidates.append(extracted)
        else:
            candidates.append(_repair_common_errors(cleaned))
            extracted = _extract_json_object(_repair_common_errors(cleaned))
            if extracted:
                candidates.append(extracted)

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                # "Extra data" — usually a stray trailing brace. Try truncating.
                if "Extra data" in str(e) and e.pos is not None and e.pos > 0:
                    truncated = candidate[:e.pos].rstrip()
                    try:
                        return json.loads(truncated)
                    except (json.JSONDecodeError, ValueError):
                        pass
                # "Unterminated string" / "Expecting value" mid-string —
                # try truncating to the last complete insight/object.
                if e.pos is not None and e.pos > 100:
                    for cutoff in (e.pos - 1, e.pos, e.pos + 1):
                        if cutoff <= 0:
                            continue
                        try:
                            return json.loads(candidate[:cutoff])
                        except (json.JSONDecodeError, ValueError):
                            continue
                continue
            except (json.JSONDecodeError, ValueError):
                continue

        # Prepare for next pass
        cleaned = _repair_common_errors(cleaned)

    raise JsonParseError(
        f"Failed to parse JSON after {max_repair_passes} repair passes",
        raw,
    )


def parse_safely(raw: str, *, default: Any = None) -> Any:
    """Parse JSON, returning *default* on failure (no exception)."""
    try:
        return parse(raw)
    except JsonParseError:
        return default

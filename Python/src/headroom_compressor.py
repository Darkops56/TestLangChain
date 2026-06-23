"""
headroom_compressor.py
======================
Wrapper centralizado de Headroom-AI para compresión de contexto LLM.

- Comprime los mensajes (system + human) antes de cada llamada al LLM.
- Registra el ahorro de tokens y los tokens totales consumidos (input + output)
  en logs/headroom_savings.csv de forma persistente.
- Usa tiktoken como fallback para conteo de tokens cuando headroom-ai
  no está disponible o HEADROOM_ENABLED=false.

Ahorro esperado: 60-95% de tokens de entrada (ver https://github.com/headroomlabs-ai/headroom)
"""

import os
import csv
import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

# ---------------------------------------------------------------------------
# Configuración vía variables de entorno
# ---------------------------------------------------------------------------
HEADROOM_ENABLED: bool = os.getenv("HEADROOM_ENABLED", "true").lower() == "true"
HEADROOM_TOKEN_BUDGET: int = int(os.getenv("HEADROOM_TOKEN_BUDGET", "2000"))

# Carpeta de logs — relativa a la raíz del proyecto Python/
_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
_SAVINGS_CSV = _LOGS_DIR / "headroom_savings.csv"
_CSV_HEADERS = [
    "timestamp",
    "input_tokens_before", "input_tokens_after",
    "input_saved_tokens", "input_savings_pct",
    "output_tokens", "total_tokens",
    "token_budget"
]

# ---------------------------------------------------------------------------
# Intento de importar headroom (falla silenciosamente si no está instalado)
# ---------------------------------------------------------------------------
try:
    from headroom import compress as _headroom_compress
    _headroom_available = True
except ImportError:
    _headroom_available = False
    _headroom_compress = None  # type: ignore

# ---------------------------------------------------------------------------
# Tokens: tiktoken + fallback simple
# ---------------------------------------------------------------------------
try:
    import tiktoken
    _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
    _tiktoken_available = True
except Exception:
    _tiktoken_available = False
    _TIKTOKEN_ENCODING = None


def count_tokens(text: str) -> int:
    """Cuenta tokens aproximados usando tiktoken o fallback char/word ratio."""
    if _tiktoken_available and _TIKTOKEN_ENCODING is not None:
        try:
            return len(_TIKTOKEN_ENCODING.encode(text))
        except Exception:
            pass
    return len(text.split())


# ---------------------------------------------------------------------------
# Estado interno para logging post-LLM
# ---------------------------------------------------------------------------
_last_metrics: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Logging persistente
# ---------------------------------------------------------------------------

def _ensure_logs_dir() -> None:
    """Crea la carpeta logs/ y el archivo CSV con encabezados si no existen."""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if not _SAVINGS_CSV.exists():
        with open(_SAVINGS_CSV, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_CSV_HEADERS)


def _log_invocation(
    input_tokens_before: int,
    input_tokens_after: int,
    output_tokens: int,
    token_budget: int,
) -> None:
    """
    Escribe una fila completa en logs/headroom_savings.csv con:
    - input_tokens_before: tokens antes de compresión Headroom
    - input_tokens_after:  tokens después de compresión (lo que se envía al LLM)
    - output_tokens:       tokens generados por el LLM
    - total_tokens:        input_tokens_after + output_tokens (consumo real)
    - token_budget:        presupuesto configurado
    """
    try:
        _ensure_logs_dir()
        saved = input_tokens_before - input_tokens_after
        saved = max(saved, 0)
        pct = round((saved / input_tokens_before * 100), 2) if input_tokens_before > 0 else 0.0
        total = input_tokens_after + output_tokens
        row = [
            datetime.datetime.now().isoformat(timespec="seconds"),
            input_tokens_before,
            input_tokens_after,
            saved,
            pct,
            output_tokens,
            total,
            token_budget,
        ]
        with open(_SAVINGS_CSV, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)
    except Exception as e:
        print(f"  [Headroom LOG WARN] No se pudo escribir el log: {e}")


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def compress_messages(
    messages: List[Tuple[str, str]],
    token_budget: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """
    Comprime una lista de mensajes (role, content) antes de enviarlos al LLM.

    Almacena las métricas de compresión internamente para que
    `log_llm_invocation()` pueda completar el registro en CSV
    después de que el LLM genere su respuesta.

    Args:
        messages:     Lista de tuplas (role, content). Roles esperados: "system", "human".
        token_budget: Límite de tokens para la compresión. Usa HEADROOM_TOKEN_BUDGET por defecto.

    Returns:
        Lista de mensajes comprimidos en el mismo formato (role, content).
        Si headroom no está disponible o está desactivado, retorna los mensajes originales sin cambios.
    """
    global _last_metrics
    budget = token_budget if token_budget is not None else HEADROOM_TOKEN_BUDGET

    # Calcular tokens originales (usamos tiktoken como fallback universal)
    raw_text = " ".join(content for _, content in messages)
    orig_tokens_fallback = count_tokens(raw_text)

    if not HEADROOM_ENABLED:
        # Headroom desactivado: contar tokens y loguear igual
        comp_text = raw_text
        comp_tokens = orig_tokens_fallback
        _last_metrics = {
            "input_before": orig_tokens_fallback,
            "input_after": comp_tokens,
            "budget": budget,
        }
        return messages

    if not _headroom_available or _headroom_compress is None:
        print(
            "  [Headroom] WARN: headroom-ai no está instalado. "
            "Ejecuta: pip install \"headroom-ai[langchain]\"\n"
            "  La compresión está desactivada para esta ejecución."
        )
        _last_metrics = {
            "input_before": orig_tokens_fallback,
            "input_after": orig_tokens_fallback,
            "budget": budget,
        }
        return messages

    try:
        openai_fmt = [{"role": role, "content": content} for role, content in messages]

        result = _headroom_compress(openai_fmt, token_budget=budget)

        # CORRECCIÓN: La API de headroom devuelve tokens_before / tokens_after
        orig_tokens: int = getattr(result, "tokens_before", orig_tokens_fallback)
        comp_tokens: int = getattr(result, "tokens_after", orig_tokens_fallback)

        # Si headroom devuelve 0, usamos nuestro fallback
        if orig_tokens == 0:
            orig_tokens = orig_tokens_fallback
        if comp_tokens == 0:
            comp_tokens = orig_tokens_fallback

        saved = orig_tokens - comp_tokens
        pct = round((saved / orig_tokens * 100), 1) if orig_tokens > 0 else 0.0

        print(
            f"  [Headroom ✅] {orig_tokens} → {comp_tokens} tokens "
            f"(ahorro: {saved} tokens / {pct}%)"
        )

        # Guardar métricas para completar el log después de la llamada LLM
        _last_metrics = {
            "input_before": orig_tokens,
            "input_after": comp_tokens,
            "budget": budget,
        }

        compressed_messages = [
            (m["role"], m["content"]) for m in result.messages
        ]
        return compressed_messages

    except Exception as e:
        print(f"  [Headroom WARN] Error en compresión, se usan mensajes originales: {e}")
        _last_metrics = {
            "input_before": orig_tokens_fallback,
            "input_after": orig_tokens_fallback,
            "budget": budget,
        }
        return messages


def log_llm_invocation(response_text: str) -> None:
    """
    Completa el registro en CSV con los tokens de salida después
    de que el LLM haya respondido.

    Debe llamarse DESPUÉS de cada invocación al LLM que usó
    compress_messages() previamente.

    Args:
        response_text: Texto de la respuesta del LLM (para contar output tokens).
    """
    global _last_metrics
    if not _last_metrics:
        return

    output_tokens = count_tokens(response_text)
    _log_invocation(
        input_tokens_before=_last_metrics["input_before"],
        input_tokens_after=_last_metrics["input_after"],
        output_tokens=output_tokens,
        token_budget=_last_metrics["budget"],
    )
    _last_metrics = {}


def get_savings_summary() -> dict:
    """
    Lee logs/headroom_savings.csv y retorna un resumen acumulado del ahorro total.

    Returns:
        Dict con: total_calls, total_input_before, total_input_after,
                  total_input_saved, avg_input_savings_pct,
                  total_output_tokens, total_tokens
    """
    summary = {
        "total_calls": 0,
        "total_input_before": 0,
        "total_input_after": 0,
        "total_input_saved": 0,
        "avg_input_savings_pct": 0.0,
        "total_output_tokens": 0,
        "total_tokens": 0,
    }
    if not _SAVINGS_CSV.exists():
        return summary

    try:
        with open(_SAVINGS_CSV, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            pct_list = []
            for row in reader:
                summary["total_calls"] += 1
                summary["total_input_before"] += int(row.get("input_tokens_before", 0))
                summary["total_input_after"] += int(row.get("input_tokens_after", 0))
                summary["total_input_saved"] += int(row.get("input_saved_tokens", 0))
                summary["total_output_tokens"] += int(row.get("output_tokens", 0))
                summary["total_tokens"] += int(row.get("total_tokens", 0))
                pct_list.append(float(row.get("input_savings_pct", 0)))
            if pct_list:
                summary["avg_input_savings_pct"] = round(sum(pct_list) / len(pct_list), 2)
    except Exception as e:
        print(f"  [Headroom LOG WARN] No se pudo leer el resumen: {e}")

    return summary

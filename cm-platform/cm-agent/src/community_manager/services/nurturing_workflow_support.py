"""Nurturing workflow helpers.

Ported from NurturingWorkflowSupport.cs.
"""

from __future__ import annotations

import random
import re

# Hold keywords (Spanish)
HOLD_KEYWORDS = [
    "no enviar",
    "no se envie",
    "standby",
    "pausar",
    "suspender",
    "en espera",
    "detener",
]

# Resume keywords (Spanish)
RESUME_KEYWORDS = [
    "reanudar",
    "enviar",
    "aprobar",
    "aprobado",
    "dale",
    "retomar",
    "activar",
]

# Quoted reply separators
_QUOTED_REPLY_SEPARATORS = [
    r"-----Original Message-----",
    r"-----Mensaje original-----",
    r"---------- Forwarded message",
    r"---------- Mensaje reenviado",
    r"On ",
    r"El ",
    r"<blockquote",
    r'<div class="gmail_quote"',
    r"-- \r\n",
    r"-- \n",
]


def strip_quoted_reply(body: str) -> str:
    """Strip quoted reply text from email bodies."""
    if not body:
        return ""

    text = body

    # Find the earliest separator
    earliest_pos = len(text)
    for separator in _QUOTED_REPLY_SEPARATORS:
        pos = text.find(separator)
        if pos != -1 and pos < earliest_pos:
            earliest_pos = pos

    if earliest_pos < len(text):
        text = text[:earliest_pos]

    # Strip lines starting with > (quoted lines)
    lines = text.split("\n")
    filtered_lines = [line for line in lines if not line.strip().startswith(">")]

    result = "\n".join(filtered_lines).strip()
    return result or body.strip()


def is_hold_request(body: str) -> bool:
    """Check if the email body is a hold request."""
    if not body:
        return False

    stripped = strip_quoted_reply(body).lower()
    return any(keyword in stripped for keyword in HOLD_KEYWORDS)


def is_resume_request(body: str) -> bool:
    """Check if the email body is a resume request.

    Returns False if any hold keyword is also present (hold takes precedence).
    """
    if not body:
        return False

    stripped = strip_quoted_reply(body).lower()

    # Hold takes precedence
    if any(keyword in stripped for keyword in HOLD_KEYWORDS):
        return False

    return any(keyword in stripped for keyword in RESUME_KEYWORDS)


def get_human_like_delay() -> int:
    """Get a random delay in seconds with weighted distribution.

    60% chance: 10-25s
    18% chance: 26-45s
    10% chance: 55-75s
    5% chance: 165-195s (~3 min)
    3% chance: 270-330s (~5 min)
    2% chance: 1080-1260s (~18-21 min)
    2% chance: 35-65s
    Plus 5% jitter
    """
    r = random.random()

    if r < 0.60:
        base = random.randint(10, 25)
    elif r < 0.78:
        base = random.randint(26, 45)
    elif r < 0.88:
        base = random.randint(55, 75)
    elif r < 0.93:
        base = random.randint(165, 195)
    elif r < 0.96:
        base = random.randint(270, 330)
    elif r < 0.98:
        base = random.randint(1080, 1260)
    else:
        base = random.randint(35, 65)

    # Add 5% jitter
    jitter = int(base * 0.05)
    return base + random.randint(-jitter, jitter)


def extract_first_name(full_name: str | None) -> str | None:
    """Extract first name from full name."""
    if not full_name or not full_name.strip():
        return None

    first = full_name.strip().split()[0]
    return first[0].upper() + first[1:].lower() if first else None


def build_personal_closing(first_name: str | None, org_name: str | None) -> str | None:
    """Build a personalized closing for the newsletter."""
    if org_name:
        return f"Te lo comparto por si suma mirarlo con el equipo de {org_name}. Abrazo!"
    return "Te lo comparto por si suma mirarlo con calma. Abrazo!"

"""
DJ persona cards (#4154, phase 4): one YAML card per daypart in docs/dj/personas
(DJ_PERSONA_DIR). A card names the host, their sketch, cadence, signature move, what
they love and avoid, and their voice; it becomes the persona dict commentary_generator
already uses (name, directive, fallback_openings, fallback_transitions) plus host/voice/speed.
Fail-open: a missing or broken card leaves that daypart on the built-in DAYPART_PERSONAS.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = PROJECT_ROOT / "docs" / "dj" / "personas"
REQUIRED = ("daypart", "show", "host", "directive", "fallback_openings", "fallback_transitions")


def _directive(card: dict) -> str:
    lines = [card["directive"].strip(),
             f"You are {card['host']}, host of {card['show']}. {card.get('sketch', '').strip()}"]
    if card.get("cadence"):
        lines.append(f"Cadence: {card['cadence']}")
    if card.get("signature_move"):
        lines.append(f"Your signature move, used now and then, never every break: "
                     f"{card['signature_move']}")
    if card.get("loves"):
        lines.append("You light up for: " + ", ".join(card["loves"]) + ".")
    if card.get("avoids"):
        lines.append("Avoid: " + ", ".join(card["avoids"]) + ".")
    return "\n".join(lines)


def _persona(card: dict) -> dict:
    return {
        "name": card["show"],
        "host": card["host"],
        "directive": _directive(card),
        "voice": card.get("voice"),
        "speed": card.get("speed"),
        "fallback_openings": list(card["fallback_openings"]),
        "fallback_transitions": list(card["fallback_transitions"]),
    }


@lru_cache(maxsize=4)
def load(directory: str | None = None) -> dict:
    """{daypart: persona} for every valid card. Cached; never raises."""
    path = Path(directory or os.getenv("DJ_PERSONA_DIR") or DEFAULT_DIR)
    cards = {}
    for file in sorted(path.glob("*.yaml")) if path.is_dir() else []:
        try:
            card = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
            missing = [k for k in REQUIRED if not card.get(k)]
            if missing:
                raise ValueError(f"missing {missing}")
            cards[card["daypart"]] = _persona(card)
        except Exception as e:
            logger.warning(f"Persona card {file.name} skipped: {e}")
    return cards

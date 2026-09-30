"""
Chris-in-the-Morning style layer for DJ commentary (#6019).

Two inputs, both optional (the DJ prompts exactly as before when either is missing):
- docs/dj/chris_style_guide.md: its "Compact digest" section goes into every system prompt.
- data/corpus/chris_fewshot.jsonl: verbatim KBHR excerpts tagged by move, gitignored
  (show dialogue). A few matching the call type are shown as style anchors.

The excerpts shape the VOICE only. Facts about songs come from the DJ-notes store
(src.notes.store via DJCommentaryGenerator._facts_block) and nowhere else.
"""

import json
import logging
import random
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUIDE_PATH = PROJECT_ROOT / "docs" / "dj" / "chris_style_guide.md"
FEWSHOT_PATH = PROJECT_ROOT / "data" / "corpus" / "chris_fewshot.jsonl"

# Which of Chris's moves each commentary type should see.
MOVES_FOR_KIND = {
    "opening": ["open", "tangent"],
    "transition": ["tangent", "into_song"],
    "feature": ["tangent", "into_song"],
    "contextual": ["open", "tangent"],
    "request": ["dedication", "into_song"],
}

FACT_RULE = (
    "FACTS RULE: the examples above teach how Chris TALKS, never what is true. Every claim "
    "about a song, artist, year, recording or meaning must come from the SOURCED FACTS in the "
    "request; if none are given, say nothing specific about the music. That includes details "
    "you are sure are true (a costume, a nickname, a chart run): unsourced means unsaid "
    "(#6019 eval). Musing, feelings, the "
    "town, the weather and the listener are yours to riff on. Never mention Cicely, KBHR or "
    "the show's characters: this is Radio Free Luna."
)


def _digest(guide_text: str) -> str:
    """The guide's 'Compact digest' section, or '' when absent."""
    m = re.search(r"^#+\s*(?:\d+\.\s*)?Compact digest\s*$(.*?)(?=^#+\s|\Z)",
                  guide_text, re.M | re.S | re.I)
    return re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip() if m else ""


def load_digest(path: Optional[Path] = None) -> str:
    try:
        return _digest((path or GUIDE_PATH).read_text(encoding="utf-8"))
    except Exception:
        return ""


def load_fewshots(path: Optional[Path] = None) -> List[Dict]:
    try:
        rows = []
        for line in (path or FEWSHOT_PATH).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("excerpt") and row.get("move"):
                    rows.append(row)
        return rows
    except Exception:
        return []


def pick_fewshots(rows: List[Dict], kind: str, n: int = 4,
                  rng: Optional[random.Random] = None) -> List[Dict]:
    """Up to n examples, alternating across the moves this kind of commentary uses."""
    rng = rng or random
    moves = MOVES_FOR_KIND.get(kind, ["tangent", "into_song"])
    pools = [[r for r in rows if r["move"] == m] for m in moves]
    for pool in pools:
        rng.shuffle(pool)
    picked = []
    while len(picked) < n and any(pools):
        for pool in pools:
            if pool and len(picked) < n:
                picked.append(pool.pop())
    return picked


def style_block(kind: str, rng: Optional[random.Random] = None) -> str:
    """System-prompt section: digest + a few examples + the facts rule. '' when no style data."""
    digest = load_digest()
    shots = pick_fewshots(load_fewshots(), kind, rng=rng)
    if not digest and not shots:
        return ""
    parts = []
    if digest:
        parts.append("HOW CHRIS TALKS (style guide digest):\n" + digest)
    if shots:
        parts.append("EXAMPLES of Chris on the air (voice only, do not reuse content):\n"
                     + "\n\n".join(f"[{s['move']}] {s['excerpt']}" for s in shots))
    parts.append(FACT_RULE)
    return "\n\n".join(parts)

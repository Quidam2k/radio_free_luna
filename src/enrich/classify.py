"""Music vs. not-music gate.

The audit found q:/music is not a pure song library — it also holds podcast
episodes (Lex Fridman), hours-long focus/study mixes, and TV/trailer clips.
Tagging those as songs would put them in DJ rotation, which is worse than
leaving them alone.

Per plan-back #8901 Q3, Phase 2 is REPORT-ONLY: this module classifies and
explains, it never moves, retags, or quarantines anything.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


class Kind:
    MUSIC = "music"
    PODCAST = "podcast"
    AMBIENT = "ambient"      # focus/study/sleep/meditation mixes
    VIDEO = "video"          # trailers, TV/film clips, non-song uploads
    UNCERTAIN = "uncertain"


_PODCAST = re.compile(
    r"\bpodcast\b|\bepisode\s*#?\d+|\bep\.?\s*\d+\b|\binterview\b|"
    r"\blecture\b|\baudiobook\b",
    re.I,
)
_AMBIENT = re.compile(
    r"\bfocus\s*music\b|\bstudy\s*music\b|\bsleep\s*music\b|\bwhite\s*noise\b|"
    r"\bbinaural\b|\bmeditation\b|\bconcentration\b|\brelaxing\s*music\b|"
    r"\badhd\b|\bambient\s*mix\b|\bhours?\b.*\bmusic\b|\bbrown\s*noise\b",
    re.I,
)
_VIDEO = re.compile(
    r"\btrailer\b|\bseason\s*\d+\b|\bepisode\b|\bnetflix\b|\bclip\b|"
    r"\bbehind\s*the\s*scenes\b|\bmain\s*title\b|\bopening\s*credits\b",
    re.I,
)

# A song is rarely longer than this; focus mixes and podcasts routinely are.
LONG_FORM_SECONDS = 15 * 60


@dataclass
class Classification:
    kind: str
    is_music: bool
    reasons: List[str] = field(default_factory=list)


def classify(
    title: str = "",
    artist: str = "",
    duration: Optional[float] = None,
) -> Classification:
    """Classify one item from its text and duration.

    Duration is the strongest single signal, but on its own it would misfile
    long live sets and symphonies, so it only escalates an already-suspicious
    item or flags an otherwise-clean one as uncertain.
    """
    haystack = f"{artist} {title}".strip()
    reasons: List[str] = []

    long_form = duration is not None and duration >= LONG_FORM_SECONDS
    if long_form:
        reasons.append(f"runtime {duration / 60:.0f} min exceeds song length")

    if _PODCAST.search(haystack):
        reasons.append("title/artist matches podcast or spoken-word markers")
        return Classification(Kind.PODCAST, False, reasons)

    if _AMBIENT.search(haystack):
        reasons.append("title/artist matches focus/study/ambient-mix markers")
        return Classification(Kind.AMBIENT, False, reasons)

    if _VIDEO.search(haystack):
        reasons.append("title/artist matches TV/film/trailer markers")
        return Classification(Kind.VIDEO, False, reasons)

    if long_form:
        # Nothing textual to convict it, but the runtime is wrong for a song.
        return Classification(Kind.UNCERTAIN, False, reasons)

    reasons.append("no non-music markers found")
    return Classification(Kind.MUSIC, True, reasons)

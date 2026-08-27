"""
Heuristic "Chris in the Morning" monologue extractor (Pipeline #989).

IMPORTANT — this is HEURISTIC, and honestly so. Neither ASR nor plain SRT
labels who is speaking, so we cannot *know* a block is Chris Stevens. We can
only score how much a block *looks* like one of his KBHR monologues and emit
that score plus a short, human-readable "why" so a later diarization pass or a
human curator can grade / prune. Never treat a high score as ground truth.

What a Chris monologue looks like (the signal we score for):
  * position  — he bookends episodes: cold-open before the action, and/or the
                closing sign-off.
  * radio     — KBHR framing: "good morning", "this is Chris", station id,
                addressing listeners, dedications, signing off.
  * literary  — he name-drops and quotes writers/philosophers; reflective,
                second-person, essayistic register.
  * shape     — a long, continuous stretch of narration rather than the short
                back-and-forth of dialogue.

The public entry point is :func:`extract_monologues`, which turns one
normalized transcript (see ``transcripts.py``) into a list of candidate
monologue records ready to serialize to ``chris_in_the_morning.jsonl``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- feature vocabularies ----------------------------------------------------

# KBHR / radio-address markers. Kept lowercase; matched case-insensitively.
_RADIO_MARKERS = [
    r"k-?b-?h-?r",
    r"\bk-?bear\b",
    r"good morning",
    r"this is chris",
    r"chris in the morning",
    r"on the (?:radio|air)",
    r"\bairwaves?\b",
    r"\blisteners?\b",
    r"\bdedicat\w*",
    r"\brequests?\b",
    r"signing off",
    r"\bfrequency\b",
    r"\bdial\b",
    r"\bkilowatts?\b",
    r"\bbroadcast\w*",
]

# Writers / thinkers Chris is fond of quoting. Not exhaustive — a signal, not
# a gate. Matched as whole words, case-insensitively.
_AUTHORS = [
    "whitman", "thoreau", "emerson", "jung", "nietzsche", "kierkegaard",
    "rilke", "kafka", "proust", "tolstoy", "dostoevsky", "chekhov", "blake",
    "keats", "yeats", "wordsworth", "goethe", "camus", "sartre", "joyce",
    "melville", "twain", "frost", "neruda", "sartre", "montaigne", "plato",
    "aristotle", "buddha", "confucius", "jefferson", "lincoln",
]

_LITERARY_CUES = [
    r"\bthe poet\b",
    r"\bphilosopher\b",
    r"\bonce (?:wrote|said)\b",
    r"\bwrote\b",
    r"\bas .{2,30} (?:wrote|said|put it)\b",
    r"\bthere's an old\b",
    r"\bsome say\b",
    r"\bconsider\b",
]

_RADIO_RE = [re.compile(p, re.I) for p in _RADIO_MARKERS]
_AUTHOR_RE = re.compile(r"\b(" + "|".join(_AUTHORS) + r")\b", re.I)
_LITERARY_RE = [re.compile(p, re.I) for p in _LITERARY_CUES]
_WORD_RE = re.compile(r"[A-Za-z']+")


# --- block building ----------------------------------------------------------


@dataclass
class Block:
    start: float
    end: float
    text: str
    n_segments: int
    seg_word_counts: list[int] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def word_count(self) -> int:
        return sum(self.seg_word_counts)


def build_blocks(segments: list[dict], max_gap: float = 2.0) -> list[Block]:
    """Merge contiguous segments into blocks, splitting on silence > ``max_gap``.

    A "block" is our monologue *candidate*: a continuous run of speech. It is a
    proxy only — two people talking with short gaps also merge — which is why
    the scorer leans on radio/literary/position signals, not shape alone.
    """
    blocks: list[Block] = []
    cur: list[dict] = []

    def flush():
        if not cur:
            return
        text = " ".join(s["text"] for s in cur).strip()
        wc = [len(_WORD_RE.findall(s["text"])) for s in cur]
        blocks.append(
            Block(
                start=cur[0]["start"],
                end=cur[-1]["end"],
                text=text,
                n_segments=len(cur),
                seg_word_counts=wc,
            )
        )

    for seg in segments:
        if cur and (seg["start"] - cur[-1]["end"]) > max_gap:
            flush()
            cur = []
        cur.append(seg)
    flush()
    return blocks


# --- scoring -----------------------------------------------------------------

# Feature weights sum to 1.0 so confidence lands in [0, 1].
_W_POSITION = 0.30
_W_RADIO = 0.30
_W_LITERARY = 0.20
_W_SHAPE = 0.20


def _radio_hits(text: str) -> list[str]:
    hits = []
    for rx in _RADIO_RE:
        m = rx.search(text)
        if m:
            hits.append(m.group(0).lower())
    return hits


def _literary_hits(text: str) -> list[str]:
    hits = [m.group(0) for m in (rx.search(text) for rx in _LITERARY_RE) if m]
    hits += [m.lower() for m in _AUTHOR_RE.findall(text)]
    return hits


def score_block(block: Block, episode_end: float) -> tuple[float, list[str]]:
    """Return ``(confidence, why)`` for a candidate block.

    ``why`` is a list of short human-readable reasons naming the features that
    fired, so a curator can see *why* the score is what it is.
    """
    why: list[str] = []

    # position: cold open (first 180s) or closing sign-off (last 120s)
    f_pos = 0.0
    if block.start <= 180.0:
        f_pos = 1.0
        why.append(f"cold-open (starts {block.start:.0f}s)")
    elif episode_end and block.end >= (episode_end - 120.0):
        f_pos = 0.8
        why.append(f"episode-close (ends {block.end:.0f}s of {episode_end:.0f}s)")

    # radio framing
    r_hits = _radio_hits(block.text)
    f_radio = min(1.0, len(set(r_hits)) / 3.0)
    if r_hits:
        why.append("radio markers: " + ", ".join(sorted(set(r_hits))[:4]))

    # literary register
    l_hits = _literary_hits(block.text)
    f_lit = min(1.0, len(set(l_hits)) / 3.0)
    if l_hits:
        why.append("literary cues: " + ", ".join(sorted(set(l_hits))[:4]))

    # monologue shape: long + continuous + few short conversational turns
    dur = block.duration
    wc = block.word_count
    short_segs = sum(1 for c in block.seg_word_counts if c <= 3)
    short_ratio = short_segs / max(1, block.n_segments)
    f_len = min(1.0, dur / 60.0) * min(1.0, wc / 120.0)
    f_shape = f_len * (1.0 - min(0.8, short_ratio))
    if f_shape >= 0.3:
        why.append(f"monologue shape ({dur:.0f}s, {wc} words, {short_ratio:.0%} short turns)")

    confidence = (
        _W_POSITION * f_pos
        + _W_RADIO * f_radio
        + _W_LITERARY * f_lit
        + _W_SHAPE * f_shape
    )
    return round(min(1.0, confidence), 3), why


# --- public API --------------------------------------------------------------


def extract_monologues(
    transcript: dict,
    *,
    min_confidence: float = 0.35,
    min_duration: float = 12.0,
    min_words: int = 30,
    max_gap: float = 2.0,
) -> list[dict]:
    """Extract candidate Chris monologues from one normalized transcript.

    Returns a list of records (highest confidence first) shaped for
    ``chris_in_the_morning.jsonl``::

        {"episode", "title", "start", "end", "duration", "text",
         "confidence", "why", "source", "method"}

    A block must clear ``min_duration``/``min_words`` to be a candidate at all,
    then ``min_confidence`` to be emitted. Nothing is asserted as *truly* Chris
    — ``confidence`` + ``why`` carry the uncertainty forward on purpose.
    """
    segments = transcript.get("segments", [])
    episode_end = segments[-1]["end"] if segments else 0.0
    blocks = build_blocks(segments, max_gap=max_gap)

    out: list[dict] = []
    for b in blocks:
        if b.duration < min_duration or b.word_count < min_words:
            continue
        conf, why = score_block(b, episode_end)
        if conf < min_confidence:
            continue
        out.append(
            {
                "episode": transcript.get("episode", "UNKNOWN"),
                "title": transcript.get("title", ""),
                "start": round(b.start, 2),
                "end": round(b.end, 2),
                "duration": round(b.duration, 2),
                "text": b.text,
                "confidence": conf,
                "why": why,
                "source": transcript.get("source", ""),
                "method": "heuristic:position+radio+literary+shape",
            }
        )
    out.sort(key=lambda r: r["confidence"], reverse=True)
    return out

"""Validate AI-generated DJ bridges before broadcast. See issue #6914."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable


BANNED_PHRASES = (
    "number one",
    "#1",
    "top 40",
    "top forty",
    "billboard",
    "chart",
    "charts",
    "charted",
    "hottest",
    "smash hit",
    "million copies",
    "sold",
    "platinum",
    "gold record",
    "grammy",
    "ratings",
    "stay tuned",
    "don't touch that dial",
    "cicely",
    "kbhr",
    "northern exposure",
    "as an ai",
    "language model",
    "i'm an ai",
    "here's a transition",
    "here is a transition",
    "sure,",
    "certainly!",
)

ALLOWED_NAMES = (
    "Radio Free Luna",
    "Henry David Thoreau",
    "Robert Frost",
    "Carl Jung",
    "Walt Whitman",
    "Emily Dickinson",
    "Good Morning",
    "Good Night",
    "Good Evening",
    "Pacific Northwest",
    "New Year",
)

_THINK_BLOCK_RE = re.compile(
    r"<think\b[^>]*>.*?</think\s*>",
    re.IGNORECASE | re.DOTALL,
)
_DANGLING_THINK_RE = re.compile(
    r"<think\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)
_LABEL_RE = re.compile(
    r"""
    ^\s*
    (?:(?:\*\*|__|\*|_)\s*)?
    (?:DJ|Bridge|Transition)
    \s*:\s*
    (?:(?:\*\*|__)\s*)?
    """,
    re.IGNORECASE | re.VERBOSE,
)
_STAGE_DIRECTION_RE = re.compile(
    r"""
    (?:
        \[
        \s*(?:pause|beat|music|song|track|audio|sound|sfx|fade|fades|
        fading|intro|outro|jingle|silence|laughs?|laughter|chuckles?|
        sighs?|whispers?)\b[^\]]*
        \]
      |
        \(
        \s*(?:pause|beat|music|song|track|audio|sound|sfx|fade|fades|
        fading|intro|outro|jingle|silence|laughs?|laughter|chuckles?|
        sighs?|whispers?)\b[^)]*
        \)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_EMPHASIS_RE = re.compile(
    r"(?<!\w)(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1(?!\w)"
)
_NUMBER_RE = re.compile(r"\d+")
_PARAGRAPH_BREAK_RE = re.compile(r"(?:\r?\n[ \t]*){2,}")

_CAPITAL_WORD = (
    r"(?:[A-Z][a-z]*(?:[-'’][A-Z]?[a-z]+)*|[A-Z]{2,})"
)
_NAME_SEQUENCE_RE = re.compile(
    rf"""
    (?<![A-Za-z])
    {_CAPITAL_WORD}
    (?:
        \s+
        (?:(?:of|the|and|de|van|von)\s+)*
        {_CAPITAL_WORD}
    )+
    (?![A-Za-z])
    """,
    re.VERBOSE,
)
_CAPITAL_WORD_RE = re.compile(_CAPITAL_WORD)


@dataclass
class Verdict:
    ok: bool
    text: str
    reasons: list[str]


def _strip_think(text: str) -> str:
    text = _THINK_BLOCK_RE.sub("", text)
    return _DANGLING_THINK_RE.sub("", text)


def _strip_surrounding_marks(text: str) -> str:
    value = text.strip()
    pairs = (
        ("```", "```"),
        ('"""', '"""'),
        ("'''", "'''"),
        ('"', '"'),
        ("'", "'"),
        ("`", "`"),
        ("“", "”"),
        ("‘", "’"),
    )

    changed = True
    while changed and value:
        changed = False
        for opening, closing in pairs:
            if (
                value.startswith(opening)
                and value.endswith(closing)
                and len(value) >= len(opening) + len(closing)
            ):
                value = value[len(opening) : -len(closing)].strip()
                changed = True
                break
    return value


def _clean_plain(text: str) -> str:
    value = _strip_think(text)

    for _ in range(2):
        value = _strip_surrounding_marks(value)
        value = _LABEL_RE.sub("", value, count=1)

    value = _STAGE_DIRECTION_RE.sub(" ", value)
    value = _LABEL_RE.sub("", value, count=1)

    previous = None
    while value != previous:
        previous = value
        value = _EMPHASIS_RE.sub(r"\2", value)

    value = _strip_surrounding_marks(value)
    return re.sub(r"\s+", " ", value).strip()


def clean(text: str) -> str:
    """Remove model scaffolding and normalize a bridge to spoken text."""
    value = _strip_think(text)
    candidate = _strip_surrounding_marks(value)

    try:
        decoded = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        decoded = None

    if isinstance(decoded, dict) and isinstance(decoded.get("bridge"), str):
        value = decoded["bridge"]

    return _clean_plain(value)


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase).replace("'", "['’]")
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _literal_pattern(value: str) -> re.Pattern[str]:
    escaped = re.escape(value)
    left = r"(?<!\w)" if value and value[0].isalnum() else ""
    right = r"(?!\w)" if value and value[-1].isalnum() else ""
    return re.compile(left + escaped + right, re.IGNORECASE)


def _track_value(track: dict[str, object], key: str) -> str:
    value = track.get(key)
    return re.sub(r"\s+", " ", str(value)).strip() if value else ""


def _reference_spans(text: str, references: Iterable[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for reference in references:
        if not reference:
            continue
        spans.extend(
            match.span() for match in _literal_pattern(reference).finditer(text)
        )
    return spans


def _inside_any_span(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(span_start <= start and end <= span_end for span_start, span_end in spans)


def _is_allowed_name(name: str, allowed_texts: Iterable[str]) -> bool:
    needle = re.sub(r"\s+", " ", name).casefold()
    return any(needle in text.casefold() for text in allowed_texts)


def _starts_sentence(text: str, position: int) -> bool:
    prefix = text[:position]
    return bool(re.search(r"""(?:^|[.!?]["'”’]?)\s*\Z""", prefix))


def _unsourced_names(text: str, allowed_texts: list[str]) -> list[str]:
    names: list[str] = []

    for match in _NAME_SEQUENCE_RE.finditer(text):
        full_name = match.group(0)

        if _is_allowed_name(full_name, allowed_texts):
            continue

        candidate = full_name
        if _starts_sentence(text, match.start()):
            capitalized_words = list(_CAPITAL_WORD_RE.finditer(full_name))
            if len(capitalized_words) <= 2:
                continue
            candidate = full_name[capitalized_words[1].start() :]

        if not _is_allowed_name(candidate, allowed_texts):
            names.append(candidate)

    return list(dict.fromkeys(names))


def validate(
    text: str,
    facts: list[dict[str, object]],
    current_track: dict[str, object],
    next_track: dict[str, object],
    context_words: Iterable[str] = (),
    min_chars: int = 40,
    max_chars: int = 600,
) -> Verdict:
    cleaned = clean(text)
    reasons: list[str] = []
    context = tuple(str(word) for word in context_words if word)

    fact_texts = [
        str(fact.get("text", ""))
        for fact in facts
        if fact.get("text") is not None
    ]
    current_title = _track_value(current_track, "title")
    current_artist = _track_value(current_track, "artist")
    next_title = _track_value(next_track, "title")
    next_artist = _track_value(next_track, "artist")

    if not cleaned:
        reasons.append("the bridge is empty after cleaning")

    if len(cleaned) < min_chars:
        reasons.append(
            f"write at least {min_chars} characters; this draft has {len(cleaned)}"
        )
    elif len(cleaned) > max_chars:
        reasons.append(
            f"write no more than {max_chars} characters; this draft has {len(cleaned)}"
        )

    think_free_raw = _strip_think(text)
    paragraphs = [
        part for part in _PARAGRAPH_BREAK_RE.split(think_free_raw) if part.strip()
    ]
    if len(paragraphs) > 2:
        reasons.append("write one short spoken passage, not multiple paragraphs")

    for phrase in BANNED_PHRASES:
        if _phrase_pattern(phrase).search(cleaned):
            reasons.append(f"remove the banned phrase '{phrase}'")

    if next_title:
        title_count = len(_literal_pattern(next_title).findall(cleaned))
        read_out = False
        if next_artist:
            read_out = bool(
                re.match(
                    rf"^{re.escape(next_title)}\s+by\s+"
                    rf"{re.escape(next_artist)}(?=$|[\s,.;:!?—-])",
                    cleaned,
                    re.IGNORECASE,
                )
            )
        if title_count > 1 or read_out:
            reasons.append("name the song once, in passing, not as a read-out")

    digit_references = (
        current_title,
        current_artist,
        next_title,
        next_artist,
        *context,
    )
    ignored_number_spans = _reference_spans(cleaned, digit_references)
    sourced_numbers = {
        match.group(0)
        for fact_text in fact_texts
        for match in _NUMBER_RE.finditer(fact_text)
    }
    reported_numbers: set[str] = set()

    for match in _NUMBER_RE.finditer(cleaned):
        number = match.group(0)
        if _inside_any_span(match.start(), match.end(), ignored_number_spans):
            continue
        if number not in sourced_numbers and number not in reported_numbers:
            reasons.append(
                f"mentions number {number}, which is not in the sourced facts"
            )
            reported_numbers.add(number)

    allowed_texts = [
        *fact_texts,
        current_title,
        current_artist,
        next_title,
        next_artist,
        *context,
        *ALLOWED_NAMES,
    ]
    for name in _unsourced_names(cleaned, allowed_texts):
        reasons.append(f"names '{name}', which is not in the sourced facts")

    return Verdict(ok=not reasons, text=cleaned, reasons=reasons)


def retry_hint(verdict: Verdict) -> str:
    """Return a compact instruction suitable for a single model retry."""
    details = "; ".join(verdict.reasons) or "it did not meet the bridge rules"
    return (
        f"Your draft was rejected because: {details}. "
        "Rewrite it as one short spoken passage using only the sourced facts."
    )

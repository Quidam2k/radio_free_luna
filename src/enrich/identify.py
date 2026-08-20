"""Derive candidate artist/title from what a file already carries.

Audit finding driving this module (#894): q:/music is NOT untagged. 193 of 206
files already have an artist tag — it is just channel-derived rather than
musical ('4NonBlondesVEVO', 'Netflix', 'The Beatles - Topic'). The filename is a
lossy sanitized copy of the title tag (/->U+2044, :->_, ?->U+00BF, plus a
'(128kbit_AAC)' suffix), so reading the tag strictly dominates parsing the name.

Filenames are therefore a fallback, not the primary path.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


class Tier:
    """Identification strategies, best first. Tier drives base confidence."""

    TOPIC = "topic"              # YouTube auto-generated 'X - Topic' channel
    TITLE_DASH = "title_dash"    # 'Artist - Title' embedded in the title tag
    TAG_CLEAN = "tag_clean"      # artist tag already looks like a real artist
    FOLDER = "folder"            # 'Artist - Album' parent directory
    FILENAME = "filename"        # no usable tags; parse the name
    UNKNOWN = "unknown"          # nothing reliable to go on


BASE_CONFIDENCE = {
    Tier.TOPIC: 0.95,
    Tier.TITLE_DASH: 0.80,
    Tier.TAG_CLEAN: 0.60,
    Tier.FOLDER: 0.65,
    Tier.FILENAME: 0.40,
    Tier.UNKNOWN: 0.0,
}

# --- title cleaning -------------------------------------------------------

_BITRATE = re.compile(r"\s*\(\d+kbit_[A-Za-z0-9]+\)", re.I)
_NOISE_BRACKET = re.compile(
    r"\s*[\(\[]\s*(?:"
    r"official\s*(?:music\s*)?video|official\s*audio|official\s*lyric[s]?\s*video|"
    r"music\s*video|lyric[s]?\s*video|lyrics|visualizer|visualiser|audio|"
    r"hd|hq|4k|remaster(?:ed)?(?:\s*\d{4})?|explicit"
    r")\s*[\)\]]",
    re.I,
)
# Segments after '|' that are channel/branding cruft rather than part of a title.
_CRUFT_SEGMENT = re.compile(
    r"^\s*(?:official.*|.*music\s*video.*|netflix|vevo|.*podcast.*|"
    r".*\bhd\b.*|.*lyrics.*)\s*$",
    re.I,
)
_LEADING_TRACKNO = re.compile(r"^\s*\d{1,2}\s*[-.]\s+")

# Mojibake introduced when yt-dlp sanitizes a title into a filename.
_FILENAME_UNSANITIZE = {
    "\u2044": "/",   # fraction slash <- /
    "\u00bf": "?",   # inverted question mark <- ?
    "\uff1a": ":",   # fullwidth colon <- :
    "\u00a6": "|",   # broken bar <- |
}


def clean_title(raw: str) -> str:
    """Strip release/upload cruft from a title without eating real content.

    Deliberately preserves '(feat. X)' — that is part of the song, not noise.
    """
    if not raw:
        return ""

    text = _BITRATE.sub("", raw)

    # Drop channel-branding segments, keep genuine ones.
    if "|" in text:
        segments = [s for s in text.split("|") if not _CRUFT_SEGMENT.match(s)]
        if segments:
            text = "|".join(segments)

    text = _NOISE_BRACKET.sub("", text)
    text = _LEADING_TRACKNO.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -|\u2013\u2014")


def unsanitize_filename(stem: str) -> str:
    """Undo yt-dlp's filename character substitutions."""
    for bad, good in _FILENAME_UNSANITIZE.items():
        stem = stem.replace(bad, good)
    return stem


# --- artist heuristics ----------------------------------------------------

_TOPIC_SUFFIX = re.compile(r"\s*-\s*Topic\s*$", re.I)
_VEVO_SUFFIX = re.compile(r"vevo\s*$", re.I)
_CHANNEL_WORDS = re.compile(
    r"(?:productions|channel|official|tv|network|records|media|studios|"
    r"entertainment|online|music)\s*$",
    re.I,
)
# Handles/usernames: no spaces, mixed case and/or digits ('JediNg135', 'F3LC4T').
_HANDLE = re.compile(r"^(?=\S+$)(?=.*[A-Za-z])(?:.*\d|.*[a-z][A-Z]).*$")

_KNOWN_NON_ARTISTS = {
    "netflix", "lex fridman", "hbo", "disney", "warner bros. pictures",
    "marvel entertainment", "pbs", "npr", "ted", "tedx talks",
}


def is_topic_channel(artist: str) -> bool:
    return bool(artist and _TOPIC_SUFFIX.search(artist))


def looks_like_channel(artist: str) -> bool:
    """True when the artist tag is a YouTube channel name, not a musician."""
    if not artist:
        return True
    a = artist.strip()
    if a.lower() in _KNOWN_NON_ARTISTS:
        return True
    if _VEVO_SUFFIX.search(a) or _CHANNEL_WORDS.search(a):
        return True
    if _HANDLE.match(a):
        return True
    return False


def _normalize(text: str) -> str:
    """Loose comparison key: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _split_artist_title(text: str) -> Optional[tuple]:
    """Split on the first ' - ' that separates an artist from a title."""
    if " - " not in text:
        return None
    left, right = text.split(" - ", 1)
    left, right = left.strip(), right.strip()
    if not left or not right:
        return None
    # A leading track number ('01 - Are You Alive?') is not an artist.
    if re.fullmatch(r"\d{1,3}", left):
        return None
    return left, right


# --- result type ----------------------------------------------------------


@dataclass
class Candidate:
    """A proposed artist/title for one file, with provenance."""

    path: str
    artist: Optional[str]
    title: Optional[str]
    tier: str
    confidence: float
    source: str
    original_artist: Optional[str] = None
    original_title: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return (
            (self.artist or "") != (self.original_artist or "")
            or (self.title or "") != (self.original_title or "")
        )


def parse_folder_hint(folder_name: str) -> tuple:
    """Pull (artist, album) out of an 'Artist - Album' directory name.

    Organized rips are commonly filed this way, and for a folder of loose MP3s
    with stripped frames the directory is the only artist evidence there is.
    """
    if not folder_name:
        return None, None
    split = _split_artist_title(folder_name.strip())
    if not split:
        return None, None
    artist, album = split
    if looks_like_channel(artist):
        return None, None
    return artist, album


def identify(
    path: str,
    tags: dict,
    stem: str = "",
    folder_name: str = "",
) -> Candidate:
    """Best-effort artist/title for one file, tag-first, filename as fallback.

    tags: normalized {'artist', 'title', 'album', ...} as returned by tagio.
    stem: filename without extension, used when tags are missing or unusable.
    folder_name: parent directory name, used as an 'Artist - Album' hint.
    """
    raw_artist = (tags.get("artist") or "").strip()
    raw_title = (tags.get("title") or "").strip()
    notes: List[str] = []

    # A title recovered from the filename. Computed up front because a file can
    # carry a perfectly good artist frame and no title frame at all (observed on
    # ripped MP3s whose only remaining frames were TCON/TPOS), and in that case
    # the tier that matched on artist still needs somewhere to get a title.
    fallback_title = clean_title(unsanitize_filename(stem)) if stem else ""
    folder_artist, folder_album = parse_folder_hint(folder_name)

    # Tier 1 — 'X - Topic' channels. YouTube generates these from real release
    # metadata, so the artist is already correct; only the suffix is noise.
    if is_topic_channel(raw_artist):
        artist = _TOPIC_SUFFIX.sub("", raw_artist).strip()
        title = clean_title(raw_title) or raw_title
        notes.append("auto-generated Topic channel; artist taken as-is")
        return Candidate(
            path=path, artist=artist, title=title, tier=Tier.TOPIC,
            confidence=BASE_CONFIDENCE[Tier.TOPIC], source="tag:topic",
            original_artist=raw_artist, original_title=raw_title, notes=notes,
        )

    # Tier 2 — 'Artist - Title' embedded in the title tag.
    split = _split_artist_title(clean_title(raw_title)) if raw_title else None
    if split:
        artist, title = split
        confidence = BASE_CONFIDENCE[Tier.TITLE_DASH]
        # Channel name agreeing with the parsed artist is corroboration
        # ('Ashnikko' / 'Ashnikko - STUPID'); a VEVO variant counts too.
        norm_tag, norm_parsed = _normalize(raw_artist), _normalize(artist)
        if norm_tag and norm_parsed:
            if norm_tag == norm_parsed or norm_tag == norm_parsed + "vevo":
                confidence = 0.90
                notes.append("channel name corroborates parsed artist")
            elif norm_parsed in norm_tag or norm_tag in norm_parsed:
                confidence = 0.85
                notes.append("channel name partially corroborates parsed artist")
            else:
                notes.append(
                    f"channel name {raw_artist!r} disagrees with parsed artist"
                )
        return Candidate(
            path=path, artist=artist, title=clean_title(title) or title,
            tier=Tier.TITLE_DASH, confidence=confidence, source="tag:title-dash",
            original_artist=raw_artist, original_title=raw_title, notes=notes,
        )

    # Tier 3 — artist tag already looks like a real musician.
    if raw_artist and not looks_like_channel(raw_artist):
        title = clean_title(raw_title) or fallback_title
        confidence = BASE_CONFIDENCE[Tier.TAG_CLEAN]
        notes.append("artist tag appears to be a real artist name")
        if not raw_title and fallback_title:
            notes.append("title recovered from filename (no title tag present)")
            # Artist frame plus a filename title is stronger than artist alone.
            confidence = 0.70
        if folder_artist and _normalize(folder_artist) == _normalize(raw_artist):
            confidence = min(0.90, confidence + 0.10)
            notes.append(f"parent folder corroborates artist ({folder_album!r})")
        return Candidate(
            path=path, artist=raw_artist, title=title, tier=Tier.TAG_CLEAN,
            confidence=confidence, source="tag:as-is",
            original_artist=raw_artist, original_title=raw_title, notes=notes,
        )

    # Tier 3b — no usable artist tag, but the parent folder names one.
    if folder_artist and (raw_title or fallback_title):
        notes.append(
            f"artist taken from parent folder {folder_name!r}; album {folder_album!r}"
        )
        return Candidate(
            path=path, artist=folder_artist,
            title=clean_title(raw_title) or fallback_title,
            tier=Tier.FOLDER, confidence=BASE_CONFIDENCE[Tier.FOLDER],
            source="folder", original_artist=raw_artist,
            original_title=raw_title, notes=notes,
        )

    # Tier 4 — fall back to the filename (lossy; see module docstring).
    if stem:
        split = _split_artist_title(clean_title(unsanitize_filename(stem)))
        if split:
            artist, title = split
            notes.append("parsed from filename; tags were unusable")
            return Candidate(
                path=path, artist=artist, title=title, tier=Tier.FILENAME,
                confidence=BASE_CONFIDENCE[Tier.FILENAME], source="filename",
                original_artist=raw_artist, original_title=raw_title, notes=notes,
            )

    # Tier 5 — a title may still be salvageable even with no usable artist.
    title = clean_title(raw_title) or fallback_title or None
    notes.append("no reliable artist could be derived")
    return Candidate(
        path=path, artist=None, title=title, tier=Tier.UNKNOWN,
        confidence=BASE_CONFIDENCE[Tier.UNKNOWN], source="none",
        original_artist=raw_artist, original_title=raw_title, notes=notes,
    )

"""
Normalized transcript shape + episode-id parsing + SRT ingest (Pipeline #989).

Everything downstream (the Chris monologue extractor) consumes ONE shape,
regardless of where the words came from. That is the whole point: today the
segments come from local Whisper ASR of Todd's own rips; a future
OpenSubtitles SRT for the full series drops in here with no change to the
extractor.

Normalized transcript (a plain dict, JSON-serializable)::

    {
      "episode":     "S01E03",              # canonical id, or "UNKNOWN"
      "title":       "Soapy Sanderson",     # best-effort, may be ""
      "source":      "asr:faster-whisper:small",  # provenance string
      "source_path": r"E:\\...\\1x03 ....avi",
      "model":       "small",               # ASR model (None for SRT)
      "runtime_sec": 123.4,                  # wall-clock to produce (None for SRT)
      "language":    "en",
      "segments": [ {"start": 0.0, "end": 3.2, "text": "..."}, ... ]
    }

Segment times are floats in seconds. ``text`` is stripped, single-spaced.
SRT-sourced segments may also carry the optional cue flags listed in
``SEGMENT_FLAG_KEYS`` (italic / music / captions); ASR segments never do.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

# --- episode id parsing ------------------------------------------------------

# "Northern Exposure - 1x03 - Soapy Sanderson.avi"  -> S01E03 / Soapy Sanderson
# "Northern Exposure - 505 - A River Doesn't ....avi" -> S05E05
# "Northern Exposure - 4x02 - Midnight Sun [05-Oct-92] [found .avi" -> S04E02
_SXE = re.compile(r"(?<!\d)(\d{1,2})\s*[xX]\s*(\d{1,2})(?!\d)")
_BARE3 = re.compile(r"(?<!\d)(\d)(\d{2})(?!\d)")


def parse_episode_id(name: str) -> str:
    """Return canonical ``SxxEyy`` from a filename/stem, or ``"UNKNOWN"``.

    Handles ``NxNN`` (e.g. ``1x03``) and bare ``SEE`` (e.g. ``505`` -> S05E05).
    """
    stem = Path(name).stem
    m = _SXE.search(stem)
    if m:
        s, e = int(m.group(1)), int(m.group(2))
        return f"S{s:02d}E{e:02d}"
    m = _BARE3.search(stem)
    if m:
        s, e = int(m.group(1)), int(m.group(2))
        return f"S{s:02d}E{e:02d}"
    return "UNKNOWN"


def parse_title(name: str) -> str:
    """Best-effort episode title from a ``Show - NxNN - Title`` filename.

    Returns "" when no ``- Title`` segment is present. Trailing bracketed
    junk like ``[05-Oct-92] [found`` is trimmed.
    """
    stem = Path(name).stem
    parts = [p.strip() for p in stem.split(" - ")]
    if len(parts) < 3:
        return ""
    title = parts[-1]
    title = re.sub(r"\s*[\[(].*$", "", title).strip()  # drop trailing [..]/(..)
    return title


# --- normalized transcript IO ------------------------------------------------


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def make_transcript(
    *,
    episode: str,
    segments: Iterable[dict],
    source: str,
    title: str = "",
    source_path: str = "",
    model: str | None = None,
    runtime_sec: float | None = None,
    language: str = "en",
) -> dict:
    segs = []
    for s in segments:
        txt = clean_text(s.get("text", ""))
        if not txt:
            continue
        seg = {
            "start": round(float(s["start"]), 3),
            "end": round(float(s["end"]), 3),
            "text": txt,
        }
        # Optional SRT cue flags (see srt_to_segments(flags=True)) pass through.
        for key in SEGMENT_FLAG_KEYS:
            if s.get(key):
                seg[key] = s[key]
        segs.append(seg)
    return {
        "episode": episode,
        "title": title,
        "source": source,
        "source_path": source_path,
        "model": model,
        "runtime_sec": runtime_sec,
        "language": language,
        "segments": segs,
    }


def save_transcript(transcript: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_transcript(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --- SRT ingest (DVD subtitles, #6011) ----------------------------------------

_SRT_TS = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
_SRT_TAG = re.compile(r"<[^>]+>")
# Fansub watermark cues ("www.tvsubtitles.net") are not dialogue.
_SRT_WATERMARK = re.compile(r"^\s*(?:<[^>]+>)*\s*www\.\S+\s*(?:<[^>]+>)*\s*$", re.I)
# Music: lyric lines wrapped in "#" (DVD convention), a real "♪", or the "??"
# that a lossy re-encode left where a "♪" used to be.
_MUSIC_MARK = re.compile(r"^\s*(?:#|♪|\?\?|\?(?=[\sA-Za-z]))|(?:#|♪)\s*$")
_MUSIC_STRIP = re.compile(r"\[[^\]]*\]|#|♪|^\s*\?+")
_CAPTION = re.compile(r"\[\s*([^\]]+?)\s*\]")

# Optional per-segment keys emitted by srt_to_segments(flags=True):
#   italic   -- cue is set in italics: off-screen voice (radio, phone, voiceover)
#   music    -- cue is a music/lyric cue
#   lyric    -- the sung words only (marked lines, markers stripped), if any
#   captions -- bracketed sound captions, e.g. ["Man Singing In French"]
SEGMENT_FLAG_KEYS = ("italic", "music", "lyric", "captions")


def decode_srt_bytes(raw: bytes) -> str:
    """Decode subtitle bytes: UTF-8 (with/without BOM), else cp1252."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _ts_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def srt_to_segments(srt_text: str, flags: bool = False) -> list[dict]:
    """Parse SRT text into normalized segments (start/end/text).

    Strips index lines, watermark cues, HTML-ish tags, and collapses
    multi-line cues to one space-joined line. With ``flags=True`` each segment
    also carries the cue flags in ``SEGMENT_FLAG_KEYS`` (only when set).
    """
    segments: list[dict] = []
    blocks = re.split(r"\r?\n\r?\n+", srt_text.strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        ts_line = None
        text_lines: list[str] = []
        for ln in lines:
            if _SRT_TS.search(ln):
                ts_line = ln
                continue
            if ts_line is None and ln.strip().isdigit():
                continue  # cue index
            if _SRT_WATERMARK.match(ln):
                continue
            text_lines.append(ln)
        if ts_line is None:
            continue
        m = _SRT_TS.search(ts_line)
        start = _ts_to_sec(*m.group(1, 2, 3, 4))
        end = _ts_to_sec(*m.group(5, 6, 7, 8))
        raw = " ".join(text_lines)
        text = clean_text(_SRT_TAG.sub("", raw))
        if not text:
            continue
        seg = {"start": start, "end": end, "text": text}
        if flags:
            if re.search(r"<i>", raw, re.I):
                seg["italic"] = True
            plain = [_SRT_TAG.sub("", ln) for ln in text_lines]
            sung = [ln for ln in plain if _MUSIC_MARK.search(ln)]
            if sung:
                seg["music"] = True
                # A "?"-led line is a mangled "♪ ... ♪": drop its trailing "?" too.
                sung = [re.sub(r"\?+\s*$", "", ln) if ln.lstrip().startswith("?") else ln
                        for ln in sung]
                lyric = clean_text(" ".join(_MUSIC_STRIP.sub(" ", ln) for ln in sung))
                if lyric:
                    seg["lyric"] = lyric
            caps = _CAPTION.findall(text)
            if caps:
                seg["captions"] = caps
        segments.append(seg)
    return segments

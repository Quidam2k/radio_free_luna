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
        segs.append(
            {
                "start": round(float(s["start"]), 3),
                "end": round(float(s["end"]), 3),
                "text": txt,
            }
        )
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


# --- SRT ingest (for the DEFERRED OpenSubtitles path) ------------------------

_SRT_TS = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
_SRT_TAG = re.compile(r"<[^>]+>")


def _ts_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def srt_to_segments(srt_text: str) -> list[dict]:
    """Parse SRT text into normalized segments (start/end/text).

    Strips index lines, HTML-ish tags, and collapses multi-line cues to one
    space-joined line. Kept here so the OpenSubtitles path is a thin wrapper
    over the same normalizer the ASR path uses.
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
            text_lines.append(ln)
        if ts_line is None:
            continue
        m = _SRT_TS.search(ts_line)
        start = _ts_to_sec(*m.group(1, 2, 3, 4))
        end = _ts_to_sec(*m.group(5, 6, 7, 8))
        text = clean_text(_SRT_TAG.sub("", " ".join(text_lines)))
        if text:
            segments.append({"start": start, "end": end, "text": text})
    return segments

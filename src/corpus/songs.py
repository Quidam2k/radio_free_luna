"""
Music cues from DVD subtitles, linked to the KBHR segments before them (#6011).

The subtitles rarely name a song. What they do carry is lyric lines wrapped in
"#" (or a mangled "??"/"♪") and the odd bracketed caption like
"[ Man Singing In French ]". This module groups those into cues and records
which on-air segment, if any, the cue followed.

No guessing: ``song_title`` is filled ONLY when a caption quotes a title
(e.g. ``[ "Moon River" Playing ]``). Otherwise it stays "".
"""

from __future__ import annotations

import re

_MUSIC_CAPTION = re.compile(
    r"music|singing|sings|song|playing|orchestra|piano|guitar|band|humming|"
    r"classical|jazz|rock|country|polka|accordion|fiddle|violin|choir|hymn",
    re.I,
)
_QUOTED_TITLE = re.compile(r"[\"“]([^\"”]{2,80})[\"”]")


def is_music_segment(seg: dict) -> bool:
    if seg.get("music"):
        return True
    return any(_MUSIC_CAPTION.search(c) for c in seg.get("captions", []))


def extract_music_cues(
    transcript: dict,
    monologues: list[dict] | None = None,
    *,
    max_gap: float = 5.0,
    follow_window: float = 30.0,
) -> list[dict]:
    """Group music segments into cues; link each to a preceding KBHR segment.

    A cue "follows" a monologue when it starts within ``follow_window`` seconds
    after that monologue ends (the closest such monologue wins).
    """
    episode = transcript.get("episode", "UNKNOWN")
    groups: list[list[dict]] = []
    for seg in transcript.get("segments", []):
        if not is_music_segment(seg):
            continue
        if groups and seg["start"] - groups[-1][-1]["end"] <= max_gap:
            groups[-1].append(seg)
        else:
            groups.append([seg])

    monos = sorted(monologues or [], key=lambda m: m["end"])
    out: list[dict] = []
    for n, g in enumerate(groups, 1):
        start, end = g[0]["start"], g[-1]["end"]
        captions = [c for s in g for c in s.get("captions", [])]
        title = ""
        for c in captions:
            m = _QUOTED_TITLE.search(c)
            if m:
                title = m.group(1).strip()
                break
        followed, gap = None, None
        for mono in monos:
            d = start - mono["end"]
            if 0 <= d <= follow_window and (gap is None or d < gap):
                followed, gap = mono["id"], round(d, 1)
        out.append(
            {
                "id": f"{episode}#cue{n:02d}",
                "episode": episode,
                "episode_title": transcript.get("title", ""),
                "start": round(start, 2),
                "end": round(end, 2),
                "lyrics": " / ".join(s["lyric"] for s in g if s.get("lyric")),
                "captions": captions,
                "song_title": title,
                "title_source": "caption" if title else "",
                "followed_monologue_id": followed,
                "followed_gap_sec": gap,
            }
        )
    return out

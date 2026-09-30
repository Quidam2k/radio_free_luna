#!/usr/bin/env python
"""
Build the Northern Exposure KBHR-segment and song indexes (#6011).

Consumes the SRT transcripts written by scripts/ingest_ne_subs.py and writes:

    data/corpus/ne_kbhr_segments.jsonl   one candidate on-air segment per line
      {id, episode, title, start, end, duration, text, confidence, why,
       italic_ratio, speaker, speaker_why, song_mentions, followed_by_cue,
       source, method}
    data/corpus/ne_songs.jsonl           one subtitle music cue per line
      {id, episode, episode_title, start, end, lyrics, captions, song_title,
       title_source, followed_monologue_id, followed_gap_sec}

Attribution is heuristic (see src/corpus/chris.py); speaker is "chris" or
"bernard" only on an on-air self-id. song_title is blank unless a caption
quotes it. The old chris_in_the_morning.jsonl (#989, ASR) is not touched.

Usage:
    python scripts/build_ne_indexes.py [--min-confidence 0.35]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus import chris, songs
from src.corpus import transcripts as T

IN_DIR = Path("data/corpus/northern_exposure")
KBHR_OUT = Path("data/corpus/ne_kbhr_segments.jsonl")
SONGS_OUT = Path("data/corpus/ne_songs.jsonl")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build NE KBHR + song indexes.")
    ap.add_argument("--in", dest="in_path", default=str(IN_DIR))
    ap.add_argument("--kbhr-out", default=str(KBHR_OUT))
    ap.add_argument("--songs-out", default=str(SONGS_OUT))
    ap.add_argument("--min-confidence", type=float, default=0.35)
    args = ap.parse_args()

    paths = [
        p for p in sorted(Path(args.in_path).glob("*.transcript.json"))
        if not p.name.endswith(".asr.transcript.json")
    ]
    all_monos: list[dict] = []
    all_cues: list[dict] = []
    stats = defaultdict(lambda: defaultdict(int))
    for p in paths:
        tr = T.load_transcript(p)
        if not tr.get("source", "").startswith("srt"):
            continue
        monos = chris.extract_monologues(tr, min_confidence=args.min_confidence)
        cues = songs.extract_music_cues(tr, monos)
        by_mono = {c["followed_monologue_id"]: c["id"] for c in cues if c["followed_monologue_id"]}
        for m in monos:
            m["followed_by_cue"] = by_mono.get(m["id"])
        monos.sort(key=lambda m: m["start"])
        all_monos.extend(monos)
        all_cues.extend(cues)

        st = stats[tr["episode"][:3]]
        st["episodes"] += 1
        st["segments"] += len(monos)
        st["words"] += sum(len(m["text"].split()) for m in monos)
        st["chris_id"] += sum(1 for m in monos if m["speaker"] == "chris")
        st["bernard_id"] += sum(1 for m in monos if m["speaker"] == "bernard")
        st["cues"] += len(cues)
        st["cue_eps"] += 1 if cues else 0
        st["titled"] += sum(1 for c in cues if c["song_title"])
        st["linked"] += sum(1 for c in cues if c["followed_monologue_id"])

    write_jsonl(Path(args.kbhr_out), all_monos)
    write_jsonl(Path(args.songs_out), all_cues)
    print(f"{len(paths)} transcripts -> {len(all_monos)} KBHR candidates ({args.kbhr_out}), "
          f"{len(all_cues)} music cues ({args.songs_out})")
    cols = ["episodes", "segments", "words", "chris_id", "bernard_id",
            "cues", "cue_eps", "titled", "linked"]
    print("\n  season " + " ".join(f"{c:>10}" for c in cols))
    tot = defaultdict(int)
    for season in sorted(stats):
        print(f"  {season:<6} " + " ".join(f"{stats[season][c]:>10}" for c in cols))
        for c in cols:
            tot[c] += stats[season][c]
    print(f"  {'ALL':<6} " + " ".join(f"{tot[c]:>10}" for c in cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

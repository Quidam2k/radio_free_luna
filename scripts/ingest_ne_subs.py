#!/usr/bin/env python
"""
Ingest the 110 Northern Exposure DVD subtitles into the corpus (#6011).

    Q:/Pantheon/data/context-harvest/northern-exposure/subs/s01..s06/*.srt
      -> data/corpus/northern_exposure/SxxEyy.transcript.json   (source "srt:DVD")

The SRT transcript is canonical: exact dialogue plus italic/music cue flags.
Any existing ASR transcript (#989) at the same path is first renamed to
SxxEyy.asr.transcript.json, never deleted. Reads only the subs dir.

Usage:
    python scripts/ingest_ne_subs.py
    python scripts/ingest_ne_subs.py --subs <dir> --out <dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus import transcripts as T

SUBS_DIR = Path("Q:/Pantheon/data/context-harvest/northern-exposure/subs")
OUT_DIR = Path("data/corpus/northern_exposure")


def preserve_asr(path: Path) -> Path | None:
    """Rename an ASR transcript at ``path`` to ``*.asr.transcript.json``."""
    if not path.exists():
        return None
    try:
        source = json.loads(path.read_text(encoding="utf-8")).get("source", "")
    except (OSError, json.JSONDecodeError):
        return None
    if not source.startswith("asr"):
        return None
    dest = path.with_name(path.name.replace(".transcript.json", ".asr.transcript.json"))
    if dest.exists():
        raise SystemExit(f"refusing to overwrite existing {dest}")
    path.rename(dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest NE DVD subtitles into transcripts.")
    ap.add_argument("--subs", default=str(SUBS_DIR))
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()

    subs, out = Path(args.subs), Path(args.out)
    srts = sorted(subs.glob("s*/*.srt"))
    if not srts:
        print(f"No .srt files under {subs}")
        return 1

    renamed, written, per_season = [], 0, {}
    for srt in srts:
        ep = T.parse_episode_id(srt.name)
        if ep == "UNKNOWN":
            print(f"  skip (no episode id): {srt.name}")
            continue
        segs = T.srt_to_segments(T.decode_srt_bytes(srt.read_bytes()), flags=True)
        tr = T.make_transcript(
            episode=ep,
            title=T.clean_text(T.parse_title(srt.name.replace(".DVD.en", ""))),
            segments=segs,
            source="srt:DVD",
            source_path=str(srt),
        )
        dest = out / f"{ep}.transcript.json"
        moved = preserve_asr(dest)
        if moved:
            renamed.append(moved.name)
        T.save_transcript(tr, dest)
        written += 1
        season = ep[:3]
        n_it = sum(1 for s in tr["segments"] if s.get("italic"))
        n_mu = sum(1 for s in tr["segments"] if s.get("music"))
        eps, segn, it, mu = per_season.get(season, (0, 0, 0, 0))
        per_season[season] = (eps + 1, segn + len(tr["segments"]), it + n_it, mu + n_mu)

    print(f"Wrote {written} SRT transcripts -> {out}")
    if renamed:
        print(f"Preserved {len(renamed)} ASR transcripts: {', '.join(renamed)}")
    print("\n  season  episodes  segments  italic  music")
    for season, (eps, segn, it, mu) in sorted(per_season.items()):
        print(f"  {season:<7} {eps:>8} {segn:>9} {it:>7} {mu:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

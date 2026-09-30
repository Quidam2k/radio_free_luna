#!/usr/bin/env python
"""
Extract "Chris in the Morning" monologues into the corpus (Pipeline #989).

Source-agnostic: it consumes NORMALIZED transcript JSON (see
src/corpus/transcripts.py) — today from local Whisper ASR, tomorrow from an
OpenSubtitles SRT — and writes one JSONL line per candidate monologue::

    data/corpus/chris_in_the_morning.jsonl
      {episode, title, start, end, duration, text, confidence, why, source, method}

Attribution is HEURISTIC (no source labels the speaker). Each line carries a
confidence score and a short "why" so a later diarization pass or a human can
grade and prune. Raw transcripts are kept untouched for re-runs.

Usage:
    python scripts/extract_chris.py                      # mine all transcripts
    python scripts/extract_chris.py --min-confidence 0.5 # stricter
    python scripts/extract_chris.py --stats              # print a summary table
    python scripts/extract_chris.py --in data/corpus/northern_exposure \
        --out data/corpus/chris_in_the_morning.jsonl
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus import chris
from src.corpus import transcripts as T

IN_DIR = Path("data/corpus/northern_exposure")
OUT_FILE = Path("data/corpus/chris_in_the_morning.jsonl")


def load_inputs(in_path: Path) -> list[Path]:
    if in_path.is_file():
        return [in_path]
    # *.asr.transcript.json are the preserved #989 ASR copies; skip so an
    # episode is never mined twice.
    return [
        Path(p)
        for p in sorted(glob.glob(str(in_path / "*.transcript.json")))
        if not p.endswith(".asr.transcript.json")
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract Chris monologues from transcripts.")
    ap.add_argument("--in", dest="in_path", default=str(IN_DIR),
                    help="transcript dir or a single .transcript.json")
    ap.add_argument("--out", default=str(OUT_FILE), help="output JSONL path")
    ap.add_argument("--min-confidence", type=float, default=0.35)
    ap.add_argument("--min-duration", type=float, default=12.0)
    ap.add_argument("--min-words", type=int, default=30)
    ap.add_argument("--max-gap", type=float, default=2.0,
                    help="silence (s) that splits one block from the next")
    ap.add_argument("--stats", action="store_true", help="print per-episode summary")
    args = ap.parse_args()

    inputs = load_inputs(Path(args.in_path))
    if not inputs:
        print(f"No transcripts found under {args.in_path}. "
              f"Run scripts/transcribe_ne.py first.")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []
    per_ep: list[tuple[str, int, float]] = []
    for tp in inputs:
        tr = T.load_transcript(tp)
        recs = chris.extract_monologues(
            tr,
            min_confidence=args.min_confidence,
            min_duration=args.min_duration,
            min_words=args.min_words,
            max_gap=args.max_gap,
        )
        all_records.extend(recs)
        top = max((r["confidence"] for r in recs), default=0.0)
        per_ep.append((tr.get("episode", tp.stem), len(recs), top))

    all_records.sort(key=lambda r: r["confidence"], reverse=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for r in all_records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_words = sum(len(r["text"].split()) for r in all_records)
    print(f"Wrote {len(all_records)} monologue candidates from {len(inputs)} episode(s) "
          f"-> {out_path}")
    print(f"  total words: {total_words:,}   "
          f"conf range: {min((r['confidence'] for r in all_records), default=0):.2f}"
          f"–{max((r['confidence'] for r in all_records), default=0):.2f}")

    if args.stats:
        print("\n  episode   candidates   top-confidence")
        for ep, n, top in sorted(per_ep):
            print(f"  {ep:<9} {n:>10}   {top:>6.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

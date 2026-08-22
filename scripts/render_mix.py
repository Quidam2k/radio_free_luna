#!/usr/bin/env python
"""
Render a crate into one continuous mix (Pipeline #1002, Tiers 1+2).

Usage:
    python scripts/render_mix.py <folder-or-filelist> --out data/mix_out/mix.mp3
    python scripts/render_mix.py "sample_audio/Halos & Horns 1.1" \
        --out data/mix_out/halos_render.mp3 --limit 4

Analyzes every track, builds a default MixPlan (beatmatched-wherever-survivable
per Todd's amendment #3149), renders to MP3, saves the plan JSON, and exports a
short WAV of every seam plus seams.json for ear-checking.

Pass a folder (its audio files are used in sorted order) or a .txt filelist
(one path per line). Re-runs are fast: track analysis is cached.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# make src importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mixdown.analyzer import analyze_many
from src.mixdown.planner import build_plan
from src.mixdown.compiler import render

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".wma", ".aac"}


def collect_tracks(target: str, limit: int | None,
                   exclude: list[str] | None = None) -> list[str]:
    exclude = [e.lower() for e in (exclude or [])]

    def excluded(name: str) -> bool:
        low = name.lower()
        return low.startswith("x ") or any(e in low for e in exclude)

    p = Path(target)
    if p.is_dir():
        files = sorted(
            (f for f in p.iterdir()
             if f.suffix.lower() in AUDIO_EXTS and not excluded(f.name)),
            key=lambda f: f.name,
        )
        paths = [str(f) for f in files]
    elif p.suffix.lower() == ".txt":
        paths = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
    elif p.suffix.lower() in AUDIO_EXTS:
        paths = [str(p)]
    else:
        raise SystemExit(f"don't know how to read tracks from {target!r}")
    if limit:
        paths = paths[:limit]
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a crate into one continuous mix.")
    ap.add_argument("target", help="folder of audio, a .txt filelist, or a single file")
    ap.add_argument("--out", default="data/mix_out/mix.mp3", help="output MP3 path")
    ap.add_argument("--limit", type=int, default=None, help="use only the first N tracks")
    ap.add_argument("--exclude", action="append", default=[],
                    help="skip files whose name contains this substring (repeatable)")
    ap.add_argument("--target-lufs", type=float, default=-14.0)
    ap.add_argument("--no-seams", action="store_true", help="skip seam WAV export")
    ap.add_argument("--no-cache", action="store_true", help="ignore analysis cache")
    ap.add_argument("--crate", default="", help="crate name for the plan")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("render_mix")

    paths = collect_tracks(args.target, args.limit, args.exclude)
    if not paths:
        raise SystemExit("no tracks found")
    log.info("rendering %d tracks -> %s", len(paths), args.out)

    t0 = time.time()
    analyses = analyze_many(paths, use_cache=not args.no_cache)
    log.info("analysis done in %.1fs", time.time() - t0)

    plan = build_plan(analyses, crate=args.crate or Path(args.target).name,
                      target_lufs=args.target_lufs)

    out_p = Path(args.out)
    plan_path = out_p.with_suffix(".plan.json")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    plan.save(str(plan_path))
    log.info("saved plan -> %s", plan_path)

    t1 = time.time()
    result = render(plan, str(out_p),
                    seams_dir=str(out_p.parent / "seams"),
                    export_seams=not args.no_seams)
    log.info("render done in %.1fs", time.time() - t1)

    # ---- summary ---------------------------------------------------------
    n_bm = sum(1 for s in result.seams if s.kind == "beatmatched_blend")
    print("\n" + "=" * 68)
    print(f"MIX: {out_p}")
    print(f"  duration     : {result.duration_s/60:.1f} min")
    print(f"  final LUFS   : {result.final_lufs:.1f}   peak: {result.peak_dbfs:.1f} dBFS")
    print(f"  transitions  : {len(result.seams)}  ({n_bm} beatmatched, "
          f"{len(result.seams)-n_bm} fallback)")
    print(f"  seams/       : {out_p.parent / 'seams'}")
    print("-" * 68)
    for s in result.seams:
        flag = "BM " if s.kind == "beatmatched_blend" else "FB "
        print(f"  {flag}#{s.index:02d} @{s.center_s/60:5.1f}m  "
              f"ov={s.overlap_s:4.1f}s lag={s.lag_ms:+6.1f}ms  "
              f"{s.from_label[:24]:24s} -> {s.to_label[:24]:24s}  {s.note}")
    print("=" * 68)


if __name__ == "__main__":
    main()

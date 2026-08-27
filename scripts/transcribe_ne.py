#!/usr/bin/env python
"""
Transcribe local Northern Exposure rips with faster-whisper (Pipeline #989, Route A).

Uses Todd's OWN .avi rips under E:\\Stacked Deck\\ — no external service, no
subtitle download, no licensing grey area. Produces one normalized transcript
per episode at::

    data/corpus/northern_exposure/<SxxEyy>.transcript.json

which the (source-agnostic) extractor scripts/extract_chris.py then mines.

GPU courtesy (rider R1): the live STT service shares this GPU, so we
  * default to the 'small' model ('medium' only behind --model),
  * process ONE episode at a time,
  * drop this process to below-normal priority, and
  * before each episode, optionally wait while another process is busy on the
    GPU (nvidia-smi utilization check; --no-yield to disable).
Per-episode model + runtime is recorded in the transcript and printed.

Usage:
    python scripts/transcribe_ne.py                     # all found episodes, model=small
    python scripts/transcribe_ne.py --model medium      # sharper, heavier
    python scripts/transcribe_ne.py --limit 2           # first 2 (smoke test)
    python scripts/transcribe_ne.py --only S01E03 S04E12
    python scripts/transcribe_ne.py --list              # just list what would run
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus import transcripts as T

DEFAULT_DIRS = [
    r"E:\Stacked Deck\Incoming",
    r"E:\Stacked Deck\Incoming\=== Ready to be Burned ===\Northern Exposure",
]
OUT_DIR = Path("data/corpus/northern_exposure")


def find_episodes(dirs: list[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for d in dirs:
        for p in glob.glob(os.path.join(d, "Northern Exposure*.avi")):
            path = Path(p)
            ep = T.parse_episode_id(path.name)
            # de-dupe by episode id; keep the first seen
            found.setdefault(ep, path)
    return [found[k] for k in sorted(found)]


def gpu_busy(threshold_util: int = 40, self_pid: int | None = None) -> bool:
    """True if another process appears to be actively using the GPU.

    Best-effort via nvidia-smi; returns False if the tool is missing so we
    never hard-block on a machine without it.
    """
    try:
        util = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        vals = [int(x) for x in util.stdout.split() if x.strip().isdigit()]
        if vals and max(vals) >= threshold_util:
            return True
    except Exception:
        return False
    return False


def yield_to_gpu(enabled: bool, poll: int = 20, max_wait: int = 1800) -> None:
    if not enabled:
        return
    waited = 0
    while gpu_busy():
        if waited == 0:
            print("  [gpu] another process is busy on the GPU; yielding...", flush=True)
        time.sleep(poll)
        waited += poll
        if waited >= max_wait:
            print(f"  [gpu] waited {waited}s; proceeding anyway.", flush=True)
            return


def lower_priority() -> None:
    try:
        if os.name == "nt":
            import ctypes
            # BELOW_NORMAL_PRIORITY_CLASS = 0x4000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        else:
            os.nice(10)
    except Exception:
        pass


def extract_wav(src: Path, dst: Path) -> None:
    """ffmpeg -> 16 kHz mono wav. Robust for old DivX/XviD AVIs."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(dst)],
        check=True,
    )


def transcribe_one(model, src: Path, model_name: str, yield_gpu: bool) -> dict:
    ep = T.parse_episode_id(src.name)
    title = T.parse_title(src.name)
    yield_to_gpu(yield_gpu)

    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "audio.wav"
        extract_wav(src, wav)
        seg_iter, info = model.transcribe(
            str(wav), language="en", vad_filter=True,
            beam_size=5, condition_on_previous_text=False,
        )
        segments = [{"start": s.start, "end": s.end, "text": s.text} for s in seg_iter]
    runtime = round(time.time() - t0, 1)

    tr = T.make_transcript(
        episode=ep,
        title=title,
        segments=segments,
        source=f"asr:faster-whisper:{model_name}",
        source_path=str(src),
        model=model_name,
        runtime_sec=runtime,
        language=getattr(info, "language", "en"),
    )
    return tr


def main() -> int:
    ap = argparse.ArgumentParser(description="Transcribe local Northern Exposure rips (Route A).")
    ap.add_argument("--model", default="small",
                    help="faster-whisper model size (default: small; medium = sharper/heavier)")
    ap.add_argument("--dirs", nargs="*", default=DEFAULT_DIRS, help="dirs to scan for rips")
    ap.add_argument("--out", default=str(OUT_DIR), help="output dir for transcripts")
    ap.add_argument("--only", nargs="*", help="restrict to these episode ids (e.g. S01E03)")
    ap.add_argument("--limit", type=int, default=0, help="process at most N episodes")
    ap.add_argument("--overwrite", action="store_true", help="re-transcribe even if output exists")
    ap.add_argument("--no-yield", action="store_true", help="do NOT yield the GPU to other processes")
    ap.add_argument("--device", default="auto", help="cuda|cpu|auto")
    ap.add_argument("--compute-type", default="auto", help="e.g. float16, int8_float16, int8")
    ap.add_argument("--list", action="store_true", help="list episodes that would be processed and exit")
    args = ap.parse_args()

    out_dir = Path(args.out)
    episodes = find_episodes(args.dirs)
    if args.only:
        want = {e.upper() for e in args.only}
        episodes = [p for p in episodes if T.parse_episode_id(p.name) in want]
    if args.limit:
        episodes = episodes[: args.limit]

    print(f"Found {len(episodes)} episode(s):")
    for p in episodes:
        ep = T.parse_episode_id(p.name)
        done = (out_dir / f"{ep}.transcript.json").exists()
        print(f"  {ep}  {'[done]' if done and not args.overwrite else '      '}  {p.name}")
    if args.list:
        return 0
    if not episodes:
        print("Nothing to do.")
        return 0

    # resolve device/compute defaults
    device = args.device
    compute_type = args.compute_type
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    lower_priority()
    from faster_whisper import WhisperModel
    print(f"\nLoading faster-whisper '{args.model}' on {device} ({compute_type})...")
    model = WhisperModel(args.model, device=device, compute_type=compute_type)

    total0 = time.time()
    done_count = 0
    for p in episodes:
        ep = T.parse_episode_id(p.name)
        dst = out_dir / f"{ep}.transcript.json"
        if dst.exists() and not args.overwrite:
            print(f"[skip] {ep} already transcribed -> {dst}")
            continue
        print(f"[asr ] {ep}  {p.name} ...", flush=True)
        try:
            tr = transcribe_one(model, p, args.model, yield_gpu=not args.no_yield)
        except Exception as e:  # keep going; one bad rip shouldn't sink the run
            print(f"[FAIL] {ep}: {e}")
            continue
        T.save_transcript(tr, dst)
        done_count += 1
        print(f"[ok  ] {ep}: {len(tr['segments'])} segments, "
              f"model={args.model}, runtime={tr['runtime_sec']}s -> {dst}")

    print(f"\nDone: {done_count} transcribed, {len(episodes) - done_count} skipped/failed, "
          f"wall={round(time.time() - total0, 1)}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

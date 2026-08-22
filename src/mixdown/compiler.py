"""
MixdownCompiler (assignment item (d)): execute a MixPlan into one continuous file.

Works in float samples for sample-accurate, beat-aligned blends:
  - loads each clip at the target rate in stereo, trims to [in, out], level-matches
  - for BEATMATCHED_BLEND, time-stretches the incoming head to the seam tempo
    (pyrubberband -> rubberband CLI) and nudges it by an onset cross-correlation so
    its downbeat lands under an outgoing beat
  - joins with an equal-power (sin/cos) crossfade over the overlap
  - normalizes the whole set to target LUFS and guards true peak
  - encodes to MP3 via ffmpeg, and exports a short WAV of every seam plus a
    seams.json report so cross-genre failures can be falsified by ear (#3149)

The equal-power fade shape mirrors src/streaming/crossfader.py's "sine" intent but
is applied precisely on the sample grid.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

from .plan import MixPlan, Transition, TransitionKind

logger = logging.getLogger(__name__)

SEAM_CONTEXT_S = 4.0        # seconds of context each side of a seam in the export
MP3_BITRATE = "256k"


def _load_stereo(path: str, sr: int) -> np.ndarray:
    """Load an audio file as float32 stereo, shape (n, 2), resampled to sr."""
    import librosa
    y, _ = librosa.load(path, sr=sr, mono=False)
    y = np.asarray(y, dtype=np.float32)
    if y.ndim == 1:
        y = np.stack([y, y], axis=0)          # mono -> 2ch
    elif y.shape[0] == 1:
        y = np.vstack([y, y])
    elif y.shape[0] > 2:
        y = y[:2]
    return np.ascontiguousarray(y.T)           # (n, 2)


def _db_to_amp(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def _time_stretch(seg: np.ndarray, sr: int, rate: float) -> np.ndarray:
    """Time-stretch a stereo segment by `rate` (>1 = faster/shorter) via rubberband."""
    if abs(rate - 1.0) < 1e-3 or seg.shape[0] < sr // 4:
        return seg
    try:
        import pyrubberband as pyrb
        out = pyrb.time_stretch(seg, sr, rate)      # handles 2-D (n, ch)
        return np.asarray(out, dtype=np.float32)
    except Exception as e:
        logger.warning("time-stretch failed (rate=%.3f): %s -- using unstretched", rate, e)
        return seg


def _onset_lag_samples(out_tail: np.ndarray, head: np.ndarray, sr: int,
                       max_lag_s: float) -> int:
    """
    Cross-correlate onset envelopes of the outgoing tail and incoming head; return
    a non-negative sample offset to delay the incoming so its beats sit under the
    outgoing beats. Bounded to +/- max_lag_s. Returns 0 on any failure.
    """
    try:
        import librosa
        hop = 512
        o = librosa.onset.onset_strength(y=out_tail.mean(axis=1), sr=sr, hop_length=hop)
        h = librosa.onset.onset_strength(y=head.mean(axis=1), sr=sr, hop_length=hop)
        n = min(len(o), len(h))
        if n < 4:
            return 0
        o = o[:n] - o[:n].mean()
        h = h[:n] - h[:n].mean()
        corr = np.correlate(o, h, mode="full")
        lags = np.arange(-n + 1, n)
        max_frames = max(1, int(max_lag_s * sr / hop))
        mask = np.abs(lags) <= max_frames
        best_lag = int(lags[mask][int(np.argmax(corr[mask]))])
        return max(0, best_lag) * hop              # only delay incoming (offset >= 0)
    except Exception as e:
        logger.debug("onset alignment failed: %s", e)
        return 0


def _equal_power_fades(n: int) -> Tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, 1.0, n, endpoint=True)
    return np.cos(x * np.pi / 2.0), np.sin(x * np.pi / 2.0)   # (fade_out, fade_in)


@dataclass
class SeamInfo:
    index: int
    from_label: str
    to_label: str
    kind: str
    center_s: float
    overlap_s: float
    seam_tempo: float
    in_stretch: float
    lag_ms: float
    survivable: bool
    note: str
    wav: str = ""


@dataclass
class RenderResult:
    out_path: str
    duration_s: float
    seams: List[SeamInfo] = field(default_factory=list)
    final_lufs: float = 0.0
    peak_dbfs: float = 0.0


def render(plan: MixPlan, out_path: str, seams_dir: Optional[str] = None,
           export_seams: bool = True) -> RenderResult:
    """Render a MixPlan to a continuous MP3 and (optionally) export seam clips."""
    plan.validate()
    sr = plan.sample_rate
    if not plan.clips:
        raise ValueError("empty plan")

    # ---- load + trim + level-match every clip ----------------------------
    segs: List[np.ndarray] = []
    for c in plan.clips:
        y = _load_stereo(c.path, sr)
        i0 = max(0, int(c.in_point * sr))
        i1 = min(len(y), int(c.out_point * sr)) if c.out_point > 0 else len(y)
        seg = y[i0:i1]
        if c.gain_db:
            seg = seg * _db_to_amp(c.gain_db)
        segs.append(np.ascontiguousarray(seg, dtype=np.float32))
        logger.info("loaded clip %-40s %.1fs gain %+.1fdB", c.label[:40],
                    len(seg) / sr, c.gain_db)

    # ---- assemble timeline with finalized-chunks + live-tail pattern ------
    finalized: List[np.ndarray] = []
    committed = 0                     # samples already in `finalized`
    tail = segs[0]
    seams: List[SeamInfo] = []

    for i in range(1, len(segs)):
        trans = plan.transitions[i - 1]
        nxt = segs[i]

        if trans.kind == TransitionKind.HARD_CUT or trans.overlap_s <= 0:
            finalized.append(tail)
            committed += len(tail)
            tail = nxt
            continue

        # incoming head stretch (beatmatched only)
        head_src = nxt
        if trans.kind == TransitionKind.BEATMATCHED_BLEND and abs(trans.in_stretch - 1.0) > 1e-3:
            # stretch enough source so the stretched head covers the overlap
            want_out = int(trans.overlap_s * sr)
            want_in = min(len(nxt), int(want_out * trans.in_stretch) + sr)
            stretched_head = _time_stretch(nxt[:want_in], sr, trans.in_stretch)
            head_src = np.concatenate([stretched_head, nxt[want_in:]], axis=0)

        Lb = int(trans.overlap_s * sr)
        Lb = min(Lb, len(tail), len(head_src))
        if Lb < sr // 2:                          # too short to blend meaningfully
            finalized.append(tail)
            committed += len(tail)
            tail = nxt
            continue

        # downbeat nudge for beatmatched joins
        lag = 0
        if trans.kind == TransitionKind.BEATMATCHED_BLEND and trans.downbeat_align:
            beat_s = 60.0 / trans.seam_tempo if trans.seam_tempo > 0 else 0.5
            lag = _onset_lag_samples(tail[-Lb:], head_src[:Lb + int(beat_s * sr)],
                                     sr, max_lag_s=beat_s)
            lag = min(lag, max(0, len(head_src) - Lb - 1))

        out_tail = tail[-Lb:]
        keep_tail = tail[:-Lb]
        head = head_src[lag:lag + Lb]
        rest = head_src[lag + Lb:]

        fo, fi = _equal_power_fades(Lb)
        blended = (out_tail * fo[:, None] + head * fi[:, None]).astype(np.float32)

        seam_center = committed + len(keep_tail) + Lb // 2
        finalized.append(keep_tail)
        finalized.append(blended)
        committed += len(keep_tail) + len(blended)
        tail = rest

        seams.append(SeamInfo(
            index=i - 1,
            from_label=plan.clips[i - 1].label,
            to_label=plan.clips[i].label,
            kind=trans.kind.value,
            center_s=round(seam_center / sr, 3),
            overlap_s=round(Lb / sr, 3),
            seam_tempo=trans.seam_tempo,
            in_stretch=trans.in_stretch,
            lag_ms=round(lag / sr * 1000.0, 1),
            survivable=trans.survivable,
            note=trans.note,
        ))

    finalized.append(tail)
    committed += len(tail)
    master = np.concatenate(finalized, axis=0)
    logger.info("assembled master: %.1f min (%d samples)", committed / sr / 60.0, committed)

    # ---- loudness normalize + peak guard ---------------------------------
    final_lufs = plan.target_lufs
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        cur = meter.integrated_loudness(master)
        if np.isfinite(cur):
            master = master * _db_to_amp(plan.target_lufs - cur)
            final_lufs = plan.target_lufs
    except Exception as e:
        logger.warning("final LUFS normalize skipped: %s", e)

    peak = float(np.max(np.abs(master))) if master.size else 0.0
    if peak > _db_to_amp(-1.0):                    # keep true peak <= -1 dBFS
        master = master * (_db_to_amp(-1.0) / peak)
        peak = _db_to_amp(-1.0)
    peak_dbfs = 20.0 * np.log10(peak) if peak > 0 else -120.0

    # ---- encode to MP3 via ffmpeg ----------------------------------------
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    _encode_mp3(master, sr, out_p)
    logger.info("wrote %s", out_p)

    # ---- export seam clips for ear-checking ------------------------------
    if export_seams and seams:
        sd = Path(seams_dir) if seams_dir else out_p.parent / "seams"
        sd.mkdir(parents=True, exist_ok=True)
        import soundfile as sf
        ctx = int(SEAM_CONTEXT_S * sr)
        for s in seams:
            c = int(s.center_s * sr)
            clip = master[max(0, c - ctx):min(len(master), c + ctx)]
            tag = "MATCH" if s.kind == "beatmatched_blend" else "FALLBACK"
            fname = f"seam_{s.index:02d}_{tag}.wav"
            sf.write(str(sd / fname), clip, sr)
            s.wav = fname
        (sd / "seams.json").write_text(
            json.dumps([s.__dict__ for s in seams], indent=2), encoding="utf-8")
        logger.info("exported %d seam clips to %s", len(seams), sd)

    return RenderResult(out_path=str(out_p), duration_s=committed / sr,
                        seams=seams, final_lufs=final_lufs, peak_dbfs=peak_dbfs)


import os
import glob as _glob
import shutil

_FFMPEG_CACHE: Optional[Tuple[str, str]] = None   # (exe, mp3_encoder)


def _find_ffmpeg() -> Tuple[str, str]:
    """
    Locate an ffmpeg and pick the best available MP3 encoder. Prefers a build
    with libmp3lame; falls back to MediaFoundation's mp3_mf (the barebones
    mingw build on PATH has only mp3_mf, not libmp3lame).
    """
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE

    candidates = []
    if os.environ.get("FFMPEG_BIN"):
        candidates.append(os.environ["FFMPEG_BIN"])
    # Gyan full builds installed via winget commonly carry libmp3lame.
    home = os.path.expanduser("~")
    candidates += _glob.glob(os.path.join(
        home, "AppData", "Local", "Microsoft", "WinGet", "Packages",
        "Gyan.FFmpeg*", "ffmpeg-*full_build*", "bin", "ffmpeg.exe"))
    onpath = shutil.which("ffmpeg")
    if onpath:
        candidates.append(onpath)

    fallback = None
    for exe in candidates:
        if not exe or not Path(exe).exists():
            continue
        try:
            enc = subprocess.run([exe, "-hide_banner", "-encoders"],
                                 capture_output=True, text=True, check=False).stdout
        except Exception:
            continue
        if "libmp3lame" in enc:
            _FFMPEG_CACHE = (exe, "libmp3lame")
            return _FFMPEG_CACHE
        if fallback is None and "mp3_mf" in enc:
            fallback = (exe, "mp3_mf")
    if fallback:
        logger.warning("no libmp3lame ffmpeg found; using %s encoder", fallback[1])
        _FFMPEG_CACHE = fallback
        return fallback
    # last resort: whatever "ffmpeg" resolves to, with libmp3lame and hope
    _FFMPEG_CACHE = (onpath or "ffmpeg", "libmp3lame")
    return _FFMPEG_CACHE


def _encode_mp3(master: np.ndarray, sr: int, out_p: Path) -> None:
    """Write float stereo to a temp WAV then transcode to MP3 with ffmpeg."""
    import soundfile as sf
    exe, encoder = _find_ffmpeg()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name
    try:
        sf.write(tmp_wav, master, sr)
        cmd = [exe, "-y", "-loglevel", "error", "-i", tmp_wav,
               "-codec:a", encoder, "-b:a", MP3_BITRATE, str(out_p)]
        subprocess.run(cmd, check=True)
    finally:
        try:
            Path(tmp_wav).unlink()
        except OSError:
            pass

"""
Track analysis for the mixdown engine (Tier 1).

Extracts the signals a transition planner needs to make a crate feel like one
long track:
  - tempo (BPM) and beat times
  - downbeat times (meter=4 heuristic; good enough for seam alignment)
  - the usable region [usable_start, usable_end] with leading/trailing silence
    trimmed, plus intro_end / outro_start guesses for choosing mix points
  - integrated loudness (LUFS, ITU-R BS.1770 via pyloudnorm) for level-matching

Results are cached to data/mix_cache/<hash>.json keyed by path + mtime + size so
re-planning a crate is instant. Analysis is done on a mono 22.05 kHz signal for
speed; the compiler re-loads audio at native rate/stereo for rendering.
"""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

ANALYSIS_SR = 22050          # analysis sample rate (mono)
CACHE_DIR = Path("data/mix_cache")
_TRIM_TOP_DB = 40.0          # silence threshold for usable-region trim
_CACHE_VERSION = 3           # bump to invalidate all cached analyses


@dataclass
class TrackAnalysis:
    """Everything the planner/compiler needs to know about one track."""

    path: str
    duration: float                       # full file duration (s)
    tempo: float                          # estimated BPM
    beat_times: List[float] = field(default_factory=list)      # seconds
    downbeat_times: List[float] = field(default_factory=list)  # seconds
    usable_start: float = 0.0             # after leading-silence trim (s)
    usable_end: float = 0.0               # before trailing-silence trim (s)
    intro_end: float = 0.0                # end of the intro region (s)
    outro_start: float = 0.0              # start of the outro region (s)
    lufs: float = -23.0                   # integrated loudness (LUFS)
    ok: bool = True
    error: str = ""

    @property
    def beat_period(self) -> float:
        """Seconds per beat from the estimated tempo."""
        return 60.0 / self.tempo if self.tempo > 0 else 0.5

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_dict(cls, d: dict) -> "TrackAnalysis":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


def _cache_key(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|v{_CACHE_VERSION}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _estimate_downbeats(beat_times: np.ndarray, y: np.ndarray, sr: int,
                        meter: int = 4) -> List[float]:
    """
    Pick the downbeat phase (which of every `meter` beats is beat 1) by choosing
    the phase whose beats carry the most onset energy. Cheap but effective for
    seam alignment; swap in madmom/all-in-one later for hard cases.
    """
    if len(beat_times) < meter:
        return beat_times.tolist()
    try:
        import librosa
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        times = librosa.times_like(onset_env, sr=sr)
        beat_strength = np.interp(beat_times, times, onset_env)
    except Exception:
        beat_strength = np.ones(len(beat_times))

    best_phase, best_score = 0, -1.0
    for phase in range(meter):
        score = beat_strength[phase::meter].sum()
        if score > best_score:
            best_score, best_phase = score, phase
    return beat_times[best_phase::meter].tolist()


def analyze_track(path: str, use_cache: bool = True) -> TrackAnalysis:
    """Analyze a single audio file, using the on-disk cache when possible."""
    p = Path(path)
    if not p.exists():
        return TrackAnalysis(path=str(path), duration=0.0, tempo=0.0,
                             ok=False, error="file not found")

    if use_cache:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file = CACHE_DIR / f"{_cache_key(p)}.json"
            if cache_file.exists():
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                logger.debug("mix analysis cache hit: %s", p.name)
                return TrackAnalysis.from_dict(data)
        except Exception as e:
            logger.debug("cache read failed for %s: %s", p.name, e)

    try:
        import librosa
    except Exception as e:  # pragma: no cover - librosa is a hard dep here
        return TrackAnalysis(path=str(path), duration=0.0, tempo=0.0,
                             ok=False, error=f"librosa unavailable: {e}")

    try:
        y, sr = librosa.load(str(p), sr=ANALYSIS_SR, mono=True)
        duration = float(len(y) / sr)

        # Tempo + beats (beat times in seconds).
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(np.atleast_1d(tempo)[0])
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

        downbeats = _estimate_downbeats(beat_times, y, sr)

        # Usable region: trim leading/trailing near-silence.
        try:
            _, (s0, s1) = librosa.effects.trim(y, top_db=_TRIM_TOP_DB)
            usable_start = float(s0 / sr)
            usable_end = float(s1 / sr)
        except Exception:
            usable_start, usable_end = 0.0, duration

        # Intro/outro guesses: default to one 8-beat bar-group in from each edge,
        # clamped to the usable region. Cheap; refined structure detection (all-in-one)
        # can replace this later.
        bar = 8 * (60.0 / tempo) if tempo > 0 else 4.0
        intro_end = min(usable_start + bar, usable_end)
        outro_start = max(usable_end - bar, usable_start)

        # Integrated loudness (LUFS). pyloudnorm wants stereo-ish float; mono is fine.
        lufs = -23.0
        try:
            import pyloudnorm as pyln
            meter = pyln.Meter(sr)
            loud = meter.integrated_loudness(y)
            if np.isfinite(loud):
                lufs = float(loud)
        except Exception as e:
            logger.debug("LUFS measurement failed for %s: %s", p.name, e)

        result = TrackAnalysis(
            path=str(p.resolve()),
            duration=duration,
            tempo=tempo,
            beat_times=[float(t) for t in beat_times],
            downbeat_times=[float(t) for t in downbeats],
            usable_start=usable_start,
            usable_end=usable_end,
            intro_end=intro_end,
            outro_start=outro_start,
            lufs=lufs,
            ok=True,
        )

        if use_cache:
            try:
                (CACHE_DIR / f"{_cache_key(p)}.json").write_text(
                    result.to_json(), encoding="utf-8")
            except Exception as e:
                logger.debug("cache write failed for %s: %s", p.name, e)

        logger.info("analyzed %s: %.1f BPM, %d beats, usable %.1f-%.1fs, %.1f LUFS",
                    p.name, tempo, len(beat_times), usable_start, usable_end, lufs)
        return result

    except Exception as e:
        logger.error("analysis failed for %s: %s", p.name, e)
        return TrackAnalysis(path=str(path), duration=0.0, tempo=0.0,
                             ok=False, error=str(e))


def analyze_many(paths: List[str], use_cache: bool = True) -> List[TrackAnalysis]:
    """Analyze a list of tracks in order (cheap enough to do serially)."""
    return [analyze_track(pth, use_cache=use_cache) for pth in paths]

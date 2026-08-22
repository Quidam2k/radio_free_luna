"""
Mixdown engine for Radio Free Luna (Pipeline #1002).

Offline, human-in-the-loop "mixdown compiler": turns a curated crate of tracks
into one long continuous set. Todd's ambition amendment (#3149): default posture
is continuous-blend / beatmatched-wherever-survivable so the render *feels like
one long track*; hard cuts and short fades are reserved for seams where a blend
would injure the material.

Pipeline:  analyzer -> planner -> compiler
    analyzer.analyze_track()  -> TrackAnalysis (tempo, beats, downbeats, usable
                                 region, integrated LUFS), cached to data/mix_cache.
    planner.build_plan()      -> MixPlan (ordered clips + per-seam Transition intent).
    compiler.render()         -> one continuous audio file + a seams report with
                                 short WAV clips of every join for ear-checking.

The compiler works in float samples (numpy/soundfile/pyrubberband) rather than
pydub so blends are sample-accurate and beat-aligned; it borrows the equal-power
crossfade shape from src/streaming/crossfader.py but implements it precisely.
"""

from .plan import Clip, Transition, MixPlan, TransitionKind
from .analyzer import TrackAnalysis, analyze_track

__all__ = [
    "Clip",
    "Transition",
    "MixPlan",
    "TransitionKind",
    "TrackAnalysis",
    "analyze_track",
]

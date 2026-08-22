"""
Transition planner (assignment item (b)) with Todd's ambition posture (#3149).

DEFAULT POSTURE: continuous-blend / beatmatched wherever musically survivable, so
the render feels like one long track. Hard cuts and short fades are reserved for
seams where a beat-locked blend would injure the material.

For each adjacent pair we:
  1. Fold the tempo ratio through half/double time (librosa mis-octaves often), so
     a 70-BPM ballad and a 140-BPM rocker are treated as beat-compatible.
  2. If the seam time-stretch needed stays within MAX_SEAM_STRETCH, choose a
     BEATMATCHED_BLEND (bring the incoming head to the outgoing tempo across the
     overlap, downbeat-aligned). We push this window well past +/-8% per Todd's
     amendment; the compiler exports every seam so failures can be falsified by ear.
  3. Otherwise fall back to LONG_BLEND (equal-power overlap, no tempo lock).

Everything here is overridable: the planner only fills defaults into a MixPlan
that a human can hand-edit.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from .analyzer import TrackAnalysis
from .plan import Clip, Transition, MixPlan, TransitionKind

logger = logging.getLogger(__name__)

# How much seam time-stretch we tolerate before a beatmatch is judged injurious.
# 0.30 => tempo ratios in [0.77, 1.30] (after octave folding) are beatmatched.
# Todd's amendment: push past +/-8%; report where it audibly breaks.
MAX_SEAM_STRETCH = 0.30
DEFAULT_BARS = 4          # overlap length for beatmatched blends (bars of 4 beats)
BEATS_PER_BAR = 4
LONG_BLEND_S = 8.0        # overlap for non-beatmatched compatible blends
FAST_FADE_S = 3.0
GAIN_CLAMP_DB = 12.0


def _fold_tempo_ratio(t_from: float, t_to: float) -> Tuple[float, float]:
    """
    Return (effective_incoming_tempo, seam_stretch) folding the incoming tempo
    through *2 / /2 so half- and double-time are treated as compatible. The
    chosen variant minimizes the stretch away from the outgoing tempo.
    seam_stretch is |rate-1| where rate = t_from / effective_incoming_tempo.
    """
    if t_from <= 0 or t_to <= 0:
        return t_to, 1.0
    candidates = [t_to, t_to * 2.0, t_to / 2.0]
    best_eff, best_dev = t_to, float("inf")
    for eff in candidates:
        rate = t_from / eff            # rate to stretch incoming so it hits t_from
        dev = abs(rate - 1.0)
        if dev < best_dev:
            best_dev, best_eff = dev, eff
    return best_eff, best_dev


def _level_gain(analysis: TrackAnalysis, target_lufs: float) -> float:
    gain = target_lufs - analysis.lufs
    return max(-GAIN_CLAMP_DB, min(GAIN_CLAMP_DB, gain))


def _plan_transition(a: TrackAnalysis, b: TrackAnalysis) -> Transition:
    """Decide the archetype for joining track a into track b."""
    eff_in_tempo, seam_stretch = _fold_tempo_ratio(a.tempo, b.tempo)

    # Spoken-word / free-tempo material: very few, irregular beats -> don't force a lock.
    a_sparse = len(a.beat_times) < 8
    b_sparse = len(b.beat_times) < 8

    if not (a_sparse or b_sparse) and seam_stretch <= MAX_SEAM_STRETCH and a.tempo > 0:
        seam_tempo = a.tempo
        in_stretch = seam_tempo / eff_in_tempo if eff_in_tempo > 0 else 1.0
        overlap = DEFAULT_BARS * BEATS_PER_BAR * (60.0 / seam_tempo)
        return Transition(
            kind=TransitionKind.BEATMATCHED_BLEND,
            overlap_s=round(overlap, 3),
            seam_tempo=round(seam_tempo, 2),
            in_stretch=round(in_stretch, 5),
            out_stretch=1.0,
            downbeat_align=True,
            survivable=True,
            note=(f"beatmatch: {a.tempo:.1f}->{b.tempo:.1f} BPM, "
                  f"eff incoming {eff_in_tempo:.1f}, seam stretch {seam_stretch*100:.1f}%"),
        )

    # Non-beatmatched fallback: long equal-power blend (still continuous-feeling).
    why = []
    if a_sparse or b_sparse:
        why.append("free-tempo/spoken material")
    if seam_stretch > MAX_SEAM_STRETCH:
        why.append(f"seam stretch {seam_stretch*100:.0f}% > {MAX_SEAM_STRETCH*100:.0f}% (would injure)")
    return Transition(
        kind=TransitionKind.LONG_BLEND,
        overlap_s=LONG_BLEND_S,
        survivable=False,
        note="long_blend: " + ("; ".join(why) if why else "tempo incompatible"),
    )


def build_plan(analyses: List[TrackAnalysis], crate: str = "",
               target_lufs: float = -14.0, sample_rate: int = 44100) -> MixPlan:
    """Build a default MixPlan from ordered track analyses."""
    good = [a for a in analyses if a.ok and a.duration > 0]
    if len(good) != len(analyses):
        dropped = [a.path for a in analyses if not (a.ok and a.duration > 0)]
        logger.warning("dropping %d unanalyzable tracks: %s", len(dropped), dropped)

    clips: List[Clip] = []
    for a in good:
        from pathlib import Path
        clips.append(Clip(
            path=a.path,
            in_point=a.usable_start,
            out_point=a.usable_end,
            gain_db=round(_level_gain(a, target_lufs), 2),
            tempo=round(a.tempo, 2),
            label=Path(a.path).stem,
        ))

    transitions: List[Transition] = []
    for i in range(len(good) - 1):
        transitions.append(_plan_transition(good[i], good[i + 1]))

    plan = MixPlan(clips=clips, transitions=transitions, crate=crate,
                   target_lufs=target_lufs, sample_rate=sample_rate)
    plan.validate()

    n_bm = sum(1 for t in transitions if t.kind == TransitionKind.BEATMATCHED_BLEND)
    logger.info("plan: %d clips, %d transitions (%d beatmatched, %d fallback)",
                len(clips), len(transitions), n_bm, len(transitions) - n_bm)
    return plan

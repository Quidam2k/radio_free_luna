"""
MixPlan: the human-in-the-loop artifact (assignment item (e)).

A MixPlan is an ordered list of Clips (which track, and the in/out points to
play) plus, between each adjacent pair, a Transition describing the *intent* of
the join (archetype + parameters). Todd and the personas author intent; the
planner fills sensible defaults from analysis; the compiler executes it.

Plans serialize to JSON so they can be hand-edited, diffed, and stored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import List, Optional


class TransitionKind(str, Enum):
    """The transition archetype menu (assignment item (b))."""

    HARD_CUT = "hard_cut"                # butt-join, no overlap
    FAST_FADE = "fast_fade"             # short equal-power fade (2-4 s), no tempo lock
    LONG_BLEND = "long_blend"          # long equal-power overlap (6-12 s), no tempo lock
    BEATMATCHED_BLEND = "beatmatched_blend"  # tempo-locked, downbeat-aligned overlap
    VOICED_BRIDGE = "voiced_bridge"    # DJ talk-over the gap (Tier 3; planned, not yet rendered)


@dataclass
class Clip:
    """One track and the region of it to play."""

    path: str
    in_point: float                     # seconds into the file to start
    out_point: float                    # seconds into the file to stop
    gain_db: float = 0.0                # level-match offset applied on load
    tempo: float = 0.0                  # native BPM (informational)
    label: str = ""                     # e.g. "03 - Crash Test Dummies"

    @property
    def play_seconds(self) -> float:
        return max(0.0, self.out_point - self.in_point)


@dataclass
class Transition:
    """How to join clip[i] into clip[i+1]."""

    kind: TransitionKind = TransitionKind.LONG_BLEND
    overlap_s: float = 8.0              # overlap / fade length in seconds
    # beatmatched only:
    seam_tempo: float = 0.0            # common tempo across the overlap (BPM)
    in_stretch: float = 1.0           # time-stretch ratio applied to incoming head
    out_stretch: float = 1.0          # time-stretch ratio applied to outgoing tail
    downbeat_align: bool = True       # snap incoming downbeat to an outgoing beat
    # bookkeeping / falsification:
    survivable: bool = True           # did the planner judge a beatmatch survivable?
    note: str = ""                    # why this archetype / why not beatmatched
    bridge_text: str = ""             # voiced-bridge script (Tier 3)


@dataclass
class MixPlan:
    """Ordered clips + the transition between each adjacent pair."""

    clips: List[Clip] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)  # len == len(clips)-1
    crate: str = ""
    target_lufs: float = -14.0
    sample_rate: int = 44100

    def validate(self) -> None:
        if self.clips and len(self.transitions) != len(self.clips) - 1:
            raise ValueError(
                f"expected {len(self.clips) - 1} transitions, got {len(self.transitions)}")

    # ---- serialization ---------------------------------------------------
    def to_json(self, indent: int = 2) -> str:
        def enc(o):
            if isinstance(o, TransitionKind):
                return o.value
            return asdict(o) if hasattr(o, "__dataclass_fields__") else o
        payload = {
            "crate": self.crate,
            "target_lufs": self.target_lufs,
            "sample_rate": self.sample_rate,
            "clips": [asdict(c) for c in self.clips],
            "transitions": [
                {**asdict(t), "kind": t.kind.value} for t in self.transitions
            ],
        }
        return json.dumps(payload, indent=indent)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_json(cls, text: str) -> "MixPlan":
        d = json.loads(text)
        clips = [Clip(**c) for c in d.get("clips", [])]
        transitions = []
        for t in d.get("transitions", []):
            t = dict(t)
            t["kind"] = TransitionKind(t.get("kind", "long_blend"))
            transitions.append(Transition(**t))
        return cls(
            clips=clips,
            transitions=transitions,
            crate=d.get("crate", ""),
            target_lufs=d.get("target_lufs", -14.0),
            sample_rate=d.get("sample_rate", 44100),
        )

    @classmethod
    def load(cls, path: str) -> "MixPlan":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())

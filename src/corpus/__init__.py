"""
Corpus tooling for the RFL DJ voice (Pipeline #989).

Source-agnostic building blocks for turning Northern Exposure episode
transcripts into a "Chris in the Morning" monologue corpus that seeds the
DJ persona prompt. Whether the segments come from local Whisper ASR or a
future OpenSubtitles SRT, everything downstream consumes the same
normalized transcript shape (see ``transcripts.py``).
"""

from __future__ import annotations

__all__ = ["transcripts", "chris"]

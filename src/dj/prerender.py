"""
Pre-render planned DJ breaks ahead of air time (#4154, phase 3).

The planner's break plan says which tracks get talk and what kind. A background task
writes each break a few tracks ahead (transitions through bridge_validator; features as
3 patter drafts, the planner model picks), synthesizes it and archives text + audio in
spoken_store, so the broadcaster only reads a file at air time. Archived features and
station IDs are reused instead of re-rendered.
"""

import asyncio
import logging
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

from . import llm_backend, spoken_store
from .commentary_generator import CommentarySegment
from ..voice import voice_policy

logger = logging.getLogger(__name__)

LOOKAHEAD = int(os.getenv("DJ_PRERENDER_LOOKAHEAD", "3"))


@dataclass
class PrerenderedSegment(CommentarySegment):
    audio_path: Optional[str] = None
    voice: Optional[str] = None
    line_id: Optional[int] = None


def enabled() -> bool:
    return os.getenv("DJ_PRERENDER", "true").strip().lower() in (
        "1", "true", "yes", "on"
    )


async def write_text(
    generator, kind, track, prev_track, context, angle
) -> Optional[CommentarySegment]:
    if kind not in ("transition", "feature", "station_id"):
        return None

    try:
        angle_line = f"\n\nAngle for this break: {angle}"
        if kind == "transition":
            prompt = generator._build_transition_prompt(
                prev_track, track, context, {}
            ) + angle_line
            text = await generator._validated_bridge(
                prompt, context, prev_track, track
            )
            if text is None:
                return generator._create_fallback_transition(
                    prev_track, track, context
                )
            voice_settings = generator._get_contextual_voice_settings(context)
        elif kind == "feature":
            prompt = generator._build_feature_prompt(
                track, context, "artist_spotlight"
            ) + angle_line
            results = await asyncio.gather(
                *(generator._call_llm(prompt, context, kind="feature")
                  for _ in range(3)),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    logger.warning(
                        "Prerender feature draft failed (%s)",
                        type(result).__name__,
                    )
            drafts = [
                result for result in results
                if isinstance(result, str)
                and generator._is_worthy_commentary(result)
            ]
            if not drafts:
                return generator._create_fallback_feature(
                    track, "artist_spotlight"
                )
            text = drafts[0] if len(drafts) == 1 else await asyncio.to_thread(
                pick_best, drafts, angle
            )
            voice_settings = generator._get_storytelling_voice_settings(context)
        else:
            prompt = (
                "Write a station identification in one or two short sentences. "
                'Name "Radio Free Luna" and tie in the angle below. '
                "Do not make any facts or claims about songs. "
                "Return only the spoken words."
            ) + angle_line
            text = await generator._call_llm(prompt, context, kind="contextual")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty station identification")
            voice_settings = generator._get_contextual_voice_settings(context)

        return CommentarySegment(
            content=text,
            type=kind,
            duration_estimate=generator._estimate_speech_duration(text),
            voice_settings=voice_settings,
        )
    except Exception as exc:
        logger.warning("Prerender %s writing failed (%s)", kind, type(exc).__name__)

    if kind == "transition":
        return generator._create_fallback_transition(prev_track, track, context)
    if kind == "feature":
        return generator._create_fallback_feature(track, "artist_spotlight")
    text = "You're listening to Radio Free Luna."
    return CommentarySegment(
        content=text,
        type="station_id",
        duration_estimate=generator._estimate_speech_duration(text),
        voice_settings=generator._get_contextual_voice_settings(context),
    )


def pick_best(drafts, angle) -> str:
    try:
        if llm_backend.backend() == "anthropic":
            numbered = "\n\n".join(
                f"{i}. {draft}" for i, draft in enumerate(drafts, start=1)
            )
            answer = llm_backend.anthropic_complete(
                system=(
                    "You are the program director of a radio station. "
                    "Pick the best on-air DJ line."
                ),
                prompt=(
                    f"{numbered}\n\nAngle for this break: {angle}\n"
                    "Answer with only the number."
                ),
                model=llm_backend.planner_model(),
                purpose="pick",
                max_tokens=200,  # headroom for adaptive thinking
            )
            match = re.search(r"[+-]?\d+", answer)
            if match and 1 <= int(match.group()) <= len(drafts):
                return drafts[int(match.group()) - 1]
    except Exception as exc:
        logger.warning("Prerender draft selection failed (%s)", type(exc).__name__)
    return drafts[0]


async def synthesize(bc, seg, voice, daypart, track_id=None, prev_id=None):
    """TTS a written segment and archive it; the plain segment back if TTS gave nothing
    (the broadcaster then live-synths the text)."""
    tiers = list(bc._listener_tiers.values())
    audio = await bc.tts_client.synthesize_speech(
        seg.content, {**(seg.voice_settings or {}), "voice": voice},
        output="stream", audience=tiers)
    if not audio:
        return seg
    row = await asyncio.to_thread(
        spoken_store.save, seg.content, audio, seg.type, voice, daypart,
        track_id, prev_id, voice_policy.is_clone_voice(voice))
    return PrerenderedSegment(
        content=seg.content, type=seg.type, duration_estimate=seg.duration_estimate,
        voice_settings=seg.voice_settings,
        audio_path=row["audio_path"], voice=voice, line_id=row["id"])


async def render_call_in(bc, item, context) -> None:
    """Pre-render a queued request's acknowledgment the moment it is queued, so the
    call-in airs from a file. Never raises; a miss just leaves live synth."""
    seg = item.commentary_before
    try:
        cfg = bc.tts_client.config
        requested = (seg.voice_settings or {}).get("voice") or cfg.voice_model
        voice = voice_policy.resolve_voice(requested, "stream", tts_url=cfg.api_url,
                                           audience=list(bc._listener_tiers.values()))
        daypart = getattr((context or {}).get("temporal"), "time_of_day", None) or "afternoon"
        rendered = await synthesize(bc, seg, voice, daypart, item.track.get("id"))
        if item.commentary_before is seg:  # not replaced meanwhile
            item.commentary_before = rendered
    except Exception as exc:
        logger.warning("Call-in pre-render failed (%s)", type(exc).__name__)


class Prerenderer:
    """Renders each planned break a few tracks ahead of the pump loop.

    Breaks are bound to TrackSequenceItems, not list positions, because listener
    requests are inserted into session.tracks while the set plays."""

    def __init__(self, broadcaster, generator, context):
        self.broadcaster = broadcaster
        self.generator = generator
        self.context = context
        self._session = broadcaster._current_session
        tracks = self._session.tracks
        self._breaks = {
            id(tracks[b["before_index"]]): b
            for b in (self._session.plan or {}).get("breaks", [])
            if b["kind"] != "opening" and 0 < b["before_index"] < len(tracks)
        }
        self._done: set[int] = set()
        self._task = None

    def start(self):
        if enabled() and self._breaks and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self):
        bc = self.broadcaster
        while bc.is_active and bc._current_session is self._session:
            await self.render_ahead()
            await asyncio.sleep(5)

    async def render_ahead(self):
        bc, tracks = self.broadcaster, self._session.tracks
        for item in list(tracks[bc._track_index + 1:bc._track_index + 1 + LOOKAHEAD]):
            brk = self._breaks.get(id(item))
            if brk is None or id(item) in self._done:
                continue
            try:
                await self.render(item, brk)
            except Exception as exc:
                logger.warning("Prerender %s failed (%s)", brk["kind"], type(exc).__name__)
            finally:
                self._done.add(id(item))

    async def render(self, item, brk):
        bc, generator, context = self.broadcaster, self.generator, self.context
        if isinstance(item.commentary_before, PrerenderedSegment) and item.commentary_before.audio_path:
            return
        tracks = self._session.tracks
        kind, track = brk["kind"], item.track
        prev = tracks[self._position(item) - 1].track
        daypart = getattr(context.get("temporal"), "time_of_day", None) or "afternoon"
        tiers = list(bc._listener_tiers.values())
        cfg = bc.tts_client.config
        requested = generator._get_contextual_voice_settings(context).get("voice") or cfg.voice_model
        voice = voice_policy.resolve_voice(requested, "stream", tts_url=cfg.api_url,
                                           audience=tiers)
        prev_id = prev.get("id") if kind == "transition" else None
        row = await asyncio.to_thread(spoken_store.find_reusable, kind, voice, daypart,
                                      track.get("id"), prev_id)
        if row:
            seg = PrerenderedSegment(
                content=row["text"], type=kind,
                duration_estimate=generator._estimate_speech_duration(row["text"]),
                audio_path=row["audio_path"], voice=voice, line_id=row["id"])
            if self._assign(item, seg):
                logger.info("Prerender %s reused line %s", kind, row["id"])
            return

        seg = await write_text(generator, kind, track, prev, context, brk.get("angle", ""))
        if seg is None:
            return
        seg = await synthesize(bc, seg, voice, daypart, track.get("id"), prev_id)
        if self._assign(item, seg):
            logger.info("Prerender %s rendered%s", kind,
                        "" if isinstance(seg, PrerenderedSegment) else " (text only)")

    def _assign(self, item, seg) -> bool:
        """Attach only while the item is still ahead of the playhead in this session."""
        bc = self.broadcaster
        if bc._current_session is not self._session:
            return False
        position = self._position(item)
        if position is None or position <= bc._track_index:
            return False
        item.commentary_before = seg
        return True

    def _position(self, item):
        # identity, not ==: TrackSequenceItem is a dataclass and compares by value
        return next((i for i, t in enumerate(self._session.tracks) if t is item), None)

"""
Single-broadcaster, multi-listener music streaming for Radio Free Luna.

Pump loop:
    - pull next track from session_manager-produced sequence
    - decode + normalize via pydub (AudioProcessor)
    - crossfade body-end of prev track into body-start of new track
    - feed raw PCM to a long-running ffmpeg subprocess (libmp3lame)
    - reader task fans MP3 frames out to per-listener bounded queues

Real-time pacing uses cumulative-audio-time deltas against
loop.time() so we don't drift relative to wall clock.
"""

import asyncio
import io
import logging
import os
import sys
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False
    AudioSegment = None  # type: ignore

from .audio_processor import AudioProcessor
from .crossfader import BasicCrossfader

logger = logging.getLogger(__name__)


def _ensure_venv_scripts_on_path() -> None:
    """Make ffmpeg/ffprobe in .venv/Scripts findable when the venv isn't activated."""
    scripts_dir = os.path.dirname(sys.executable)
    if scripts_dir and scripts_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = scripts_dir + os.pathsep + os.environ.get("PATH", "")


@dataclass
class _CurrentTrack:
    title: str
    artist: str
    duration: float
    started_at: float
    requested_by: Optional[str] = None

    def elapsed(self, now: float) -> float:
        return max(0.0, now - self.started_at)


class Broadcaster:
    """
    Owns the FastAPI-side streaming lifecycle: one ffmpeg subprocess per
    active session, one PCM pump task, one MP3-frame fanout task,
    and a list of per-listener asyncio queues.
    """

    def __init__(
        self,
        session_manager,
        bitrate_kbps: int = 128,
        sample_rate: int = 44100,
        channels: int = 2,
        chunk_ms: int = 250,
        tts_client=None,
        archive_dir: Optional[str] = None,
    ):
        if not HAS_PYDUB:
            raise RuntimeError("pydub is required for Broadcaster but is not installed")

        _ensure_venv_scripts_on_path()

        self.session_manager = session_manager
        self.tts_client = tts_client  # optional: enables spoken DJ commentary in the stream
        self.archive_dir = archive_dir  # optional: record each broadcast to an MP3
        self._archive_file = None
        self.bitrate_kbps = bitrate_kbps
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_ms = chunk_ms
        self.sample_width = 2  # s16le

        self.audio_processor = AudioProcessor()
        self.crossfader = BasicCrossfader(fade_duration_ms=6000)

        self._listeners: List[asyncio.Queue] = []
        self._listener_lock = asyncio.Lock()
        self._listener_queue_max = 32  # bounded — slow listeners get drops, not backpressure

        self._current_session: Optional[Any] = None
        self._current_track: Optional[_CurrentTrack] = None
        self._track_index: int = 0
        self._skip_event: Optional[asyncio.Event] = None
        self._request_queue: deque = deque()  # TrackSequenceItems from listener requests

        self._pump_task: Optional[asyncio.Task] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._ffmpeg: Optional[asyncio.subprocess.Process] = None
        self._session_active = False
        self._session_started_at: float = 0.0

    # ---- lifecycle ----

    async def start(self) -> None:
        logger.info("Broadcaster initialized (idle)")

    async def stop(self) -> None:
        await self.stop_session()

    @property
    def is_active(self) -> bool:
        return self._session_active

    async def start_session(
        self, theme: str, duration_minutes: int, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        if self._session_active:
            logger.info("Session already active; stopping it before starting new one")
            await self.stop_session()

        logger.info(f"Broadcaster starting session: theme={theme} duration={duration_minutes}m")
        session = await self.session_manager.create_session(
            theme=theme,
            duration_minutes=duration_minutes,
            context=context,
        )
        if not session.tracks:
            raise ValueError("Session created with zero tracks")

        self._current_session = session
        self._track_index = 0
        self._skip_event = asyncio.Event()
        self._session_active = True

        if self.archive_dir:
            try:
                os.makedirs(self.archive_dir, exist_ok=True)
                archive_path = os.path.join(
                    self.archive_dir, f"{session.session_id}_{theme}.mp3"
                )
                self._archive_file = open(archive_path, "wb")
                logger.info(f"Archiving broadcast to {archive_path}")
            except Exception as e:
                logger.warning(f"Could not open archive file: {e}")
                self._archive_file = None

        await self._spawn_ffmpeg()

        loop = asyncio.get_running_loop()
        self._session_started_at = loop.time()
        self._reader_task = asyncio.create_task(self._reader_loop())
        self._pump_task = asyncio.create_task(self._pump_loop())

        return {
            "session_id": session.session_id,
            "theme": session.theme,
            "track_count": len(session.tracks),
            "estimated_duration": sum(t.track["duration"] for t in session.tracks),
        }

    async def stop_session(self) -> Dict[str, Any]:
        if not self._session_active and not self._ffmpeg:
            return {"status": "idle"}

        logger.info("Broadcaster stopping session")
        session_id = self._current_session.session_id if self._current_session else None
        self._session_active = False
        if self._skip_event:
            self._skip_event.set()

        if self._pump_task and not self._pump_task.done():
            self._pump_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._pump_task
        self._pump_task = None

        if self._ffmpeg and self._ffmpeg.stdin:
            with suppress(Exception):
                if not self._ffmpeg.stdin.is_closing():
                    self._ffmpeg.stdin.close()

        if self._reader_task and not self._reader_task.done():
            try:
                await asyncio.wait_for(self._reader_task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._reader_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._reader_task
        self._reader_task = None

        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stderr_task
        self._stderr_task = None

        if self._ffmpeg:
            with suppress(Exception):
                if self._ffmpeg.returncode is None:
                    self._ffmpeg.terminate()
                    try:
                        await asyncio.wait_for(self._ffmpeg.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        self._ffmpeg.kill()
                        await self._ffmpeg.wait()
            self._ffmpeg = None

        # Send None sentinel to listeners so their generators exit cleanly
        async with self._listener_lock:
            for q in self._listeners:
                with suppress(asyncio.QueueFull):
                    q.put_nowait(None)

        if self._archive_file is not None:
            with suppress(Exception):
                self._archive_file.close()
            self._archive_file = None
            logger.info("Broadcast archive closed")

        self._current_session = None
        self._current_track = None
        self._track_index = 0
        self._request_queue.clear()
        return {"status": "stopped", "session_id": session_id}

    async def queue_request(
        self,
        track: Dict[str, Any],
        commentary_segment=None,
        requested_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Queue a listener-requested track to play after the current one.

        Requests jump the session's planned sequence (FIFO among themselves)
        and carry an optional DJ acknowledgment spoken before the track.
        """
        if not self._session_active:
            raise RuntimeError("No active broadcast to queue a request into")

        from ..dj.session_manager import TrackSequenceItem

        item = TrackSequenceItem(
            track=track,
            position=self._track_index + 1 + len(self._request_queue),
            start_time="00:00:00",
            commentary_before=commentary_segment,
            requested_by=requested_by,
        )
        self._request_queue.append(item)
        logger.info(
            f"Request queued: {track.get('title')} - {track.get('artist')}"
            + (f" (for {requested_by})" if requested_by else "")
        )
        return {
            "queued": True,
            "position_in_queue": len(self._request_queue),
        }

    async def skip_track(self) -> bool:
        if not self._session_active or not self._skip_event:
            return False
        logger.info("Broadcaster: skip requested")
        self._skip_event.set()
        return True

    def current_status(self) -> Dict[str, Any]:
        if not self._session_active or not self._current_session:
            return {
                "active": False,
                "current_track": None,
                "listener_count": len(self._listeners),
                "track_index": 0,
                "total_tracks": 0,
            }

        loop_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else time.monotonic()
        current = None
        if self._current_track:
            current = {
                "title": self._current_track.title,
                "artist": self._current_track.artist,
                "duration": self._current_track.duration,
                "elapsed": self._current_track.elapsed(loop_time),
                "requested_by": self._current_track.requested_by,
            }

        return {
            "active": True,
            "session_id": self._current_session.session_id,
            "theme": self._current_session.theme,
            "current_track": current,
            "track_index": self._track_index,
            "total_tracks": len(self._current_session.tracks),
            "listener_count": len(self._listeners),
            "pending_requests": len(self._request_queue),
            "session_elapsed": loop_time - self._session_started_at,
        }

    # ---- listener registration ----

    async def register_listener(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._listener_queue_max)
        async with self._listener_lock:
            self._listeners.append(q)
        logger.info(f"Listener connected (total={len(self._listeners)})")
        return q

    async def unregister_listener(self, q: asyncio.Queue) -> None:
        async with self._listener_lock:
            if q in self._listeners:
                self._listeners.remove(q)
        logger.info(f"Listener disconnected (total={len(self._listeners)})")

    # ---- ffmpeg ----

    async def _spawn_ffmpeg(self) -> None:
        cmd = [
            "ffmpeg",
            "-loglevel", "warning",
            "-hide_banner",
            "-f", "s16le",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            "-i", "pipe:0",
            "-c:a", "libmp3lame",
            "-b:a", f"{self.bitrate_kbps}k",
            "-f", "mp3",
            "pipe:1",
        ]
        logger.info(f"Spawning ffmpeg: {' '.join(cmd)}")
        self._ffmpeg = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        if not self._ffmpeg or not self._ffmpeg.stderr:
            return
        try:
            while True:
                line = await self._ffmpeg.stderr.readline()
                if not line:
                    break
                logger.debug(f"ffmpeg: {line.decode('utf-8', errors='replace').strip()}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"ffmpeg stderr drain ended: {e}")

    async def _reader_loop(self) -> None:
        if not self._ffmpeg or not self._ffmpeg.stdout:
            return
        try:
            while True:
                chunk = await self._ffmpeg.stdout.read(4096)
                if not chunk:
                    break
                if self._archive_file is not None:
                    try:
                        self._archive_file.write(chunk)
                    except Exception as e:
                        logger.warning(f"Archive write failed; disabling archive: {e}")
                        with suppress(Exception):
                            self._archive_file.close()
                        self._archive_file = None
                async with self._listener_lock:
                    listeners = list(self._listeners)
                for q in listeners:
                    try:
                        q.put_nowait(chunk)
                    except asyncio.QueueFull:
                        logger.debug("Dropping chunk for slow listener")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Reader loop error: {e}", exc_info=True)

    # ---- play history ----

    def _record_play_sync(self, track_id: int) -> None:
        """Bump play_count / last_played for a track that just aired."""
        from datetime import datetime
        from ..core.database import get_db, db_manager, Track as TrackModel

        if db_manager is None:  # not wired up (tests, standalone use)
            return
        session = get_db()
        try:
            track = session.query(TrackModel).filter_by(id=track_id).first()
            if track:
                track.play_count = (track.play_count or 0) + 1
                track.last_played = datetime.utcnow()
                session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Failed to record play for track {track_id}: {e}")
        finally:
            session.close()

    async def _record_play(self, track: Dict[str, Any]) -> None:
        track_id = track.get("id")
        if track_id is not None:
            await asyncio.to_thread(self._record_play_sync, track_id)

    # ---- commentary ----

    def _conform(self, audio: "AudioSegment") -> "AudioSegment":
        """Match an AudioSegment to the broadcast PCM format (CPU-bound)."""
        return (
            audio.set_frame_rate(self.sample_rate)
                 .set_channels(self.channels)
                 .set_sample_width(self.sample_width)
        )

    def _commentary_for_index(self, index: int):
        """Commentary segment to speak before the track at `index`, if any."""
        session = self._current_session
        if session is None or index >= len(session.tracks):
            return None
        seg = getattr(session.tracks[index], "commentary_before", None)
        if seg is None and index == 0:
            # The session opener lives in commentary_segments, not on track 0
            for s in getattr(session, "commentary_segments", None) or []:
                if getattr(s, "type", None) == "opening":
                    return s
        return seg

    async def _mix_commentary_into(
        self, body: "AudioSegment", segment
    ) -> "AudioSegment":
        """Synthesize a commentary segment and duck it over the track intro.

        Any failure (TTS down, bad audio, mix error) returns the unmodified
        body — the music must never stop for a lost voice line.
        """
        try:
            text = getattr(segment, "content", None)
            if not text:
                return body

            voice_settings = getattr(segment, "voice_settings", None)
            audio_bytes = await self.tts_client.synthesize_speech(text, voice_settings)
            if not audio_bytes:
                return body

            def _decode_and_mix() -> "AudioSegment":
                voice = self._conform(AudioSegment.from_file(io.BytesIO(audio_bytes)))
                if len(voice) + 1000 >= len(body):
                    # Track too short to talk over — speak first, then play
                    return voice + body
                mixed = self.crossfader.mix_with_commentary(
                    body, voice, commentary_position="beginning"
                )
                return self._conform(mixed)

            mixed = await asyncio.to_thread(_decode_and_mix)
            logger.info(f"DJ commentary on air ({len(text)} chars): {text[:60]}...")
            return mixed

        except Exception as e:
            logger.warning(f"Commentary mix failed; airing track without voice: {e}")
            return body

    # ---- pump loop ----

    async def _pump_loop(self) -> None:
        loop = asyncio.get_running_loop()
        prev_tail: Optional["AudioSegment"] = None
        cumulative_audio_seconds = 0.0
        start_time = loop.time()

        try:
            while self._session_active and self._track_index < len(self._current_session.tracks):
                # Listener requests jump the planned sequence at track boundaries
                offset = 0
                while self._request_queue:
                    self._current_session.tracks.insert(
                        self._track_index + offset, self._request_queue.popleft()
                    )
                    offset += 1

                track_item = self._current_session.tracks[self._track_index]
                track = track_item.track
                file_path = track.get("file_path")
                title = track.get("title", "Unknown")
                artist = track.get("artist", "Unknown")

                logger.info(
                    f"Pump: track {self._track_index + 1}/{len(self._current_session.tracks)}: "
                    f"{title} - {artist}"
                )

                audio = await self.audio_processor.process_audio_file(file_path)
                if audio is None:
                    logger.warning(f"Skipping unloadable track: {file_path}")
                    self._track_index += 1
                    continue

                audio = await asyncio.to_thread(self._conform, audio)

                fade_ms = max(0, int(track_item.crossfade_duration * 1000))

                if prev_tail is not None and fade_ms > 0 and len(audio) > fade_ms:
                    # Crossfading is CPU-bound pydub work — keep it off the loop
                    combined = await asyncio.to_thread(
                        self.crossfader.create_crossfade,
                        prev_tail, audio, fade_ms, "smart",
                    )
                    combined = await asyncio.to_thread(self._conform, combined)
                    body = combined[:-fade_ms]
                    new_tail = combined[-fade_ms:]
                else:
                    if fade_ms > 0 and len(audio) > fade_ms:
                        body = audio[:-fade_ms]
                        new_tail = audio[-fade_ms:]
                    else:
                        body = audio
                        new_tail = None

                # Spoken DJ commentary, ducked under the start of the track
                commentary_seg = self._commentary_for_index(self._track_index)
                if commentary_seg is not None and self.tts_client is not None:
                    body = await self._mix_commentary_into(body, commentary_seg)

                self._current_track = _CurrentTrack(
                    title=title,
                    artist=artist,
                    duration=len(body) / 1000.0,  # what actually airs (body excludes the carried tail)
                    started_at=loop.time(),
                    requested_by=getattr(track_item, "requested_by", None),
                )
                await self._record_play(track)

                emitted = await self._emit(body, start_time, cumulative_audio_seconds)
                cumulative_audio_seconds += emitted

                if not self._session_active:
                    break

                if self._skip_event and self._skip_event.is_set():
                    logger.info("Skip event observed; advancing immediately")
                    self._skip_event.clear()
                    new_tail = None  # don't carry tail across an explicit skip

                prev_tail = new_tail
                self._track_index += 1

            if self._session_active and prev_tail is not None and len(prev_tail) > 0:
                tail_with_fade = prev_tail.fade_out(len(prev_tail))
                await self._emit(tail_with_fade, start_time, cumulative_audio_seconds)

            logger.info("Pump loop completed naturally")
        except asyncio.CancelledError:
            logger.info("Pump loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Pump loop crashed: {e}", exc_info=True)
        finally:
            self._current_track = None
            self._session_active = False

    async def _emit(
        self,
        audio: "AudioSegment",
        session_start: float,
        cumulative_audio: float,
    ) -> float:
        loop = asyncio.get_running_loop()
        if len(audio) == 0:
            return 0.0

        raw = audio.raw_data
        bytes_per_sec = self.sample_rate * self.channels * self.sample_width
        chunk_bytes = int(bytes_per_sec * (self.chunk_ms / 1000.0))
        frame_size = self.channels * self.sample_width
        chunk_bytes -= chunk_bytes % frame_size
        if chunk_bytes <= 0:
            chunk_bytes = frame_size

        emitted_bytes = 0
        local_audio_seconds = 0.0
        offset = 0
        total = len(raw)

        while offset < total:
            if not self._session_active:
                break
            if self._skip_event and self._skip_event.is_set():
                break

            slice_bytes = min(chunk_bytes, total - offset)
            chunk = raw[offset:offset + slice_bytes]
            offset += slice_bytes

            local_audio_seconds += slice_bytes / bytes_per_sec

            target_wall = session_start + cumulative_audio + local_audio_seconds
            now = loop.time()
            sleep_for = target_wall - now
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

            if self._ffmpeg and self._ffmpeg.stdin and not self._ffmpeg.stdin.is_closing():
                try:
                    self._ffmpeg.stdin.write(chunk)
                    await self._ffmpeg.stdin.drain()
                    emitted_bytes += slice_bytes
                except (BrokenPipeError, ConnectionResetError):
                    logger.warning("ffmpeg pipe broken — ending pump emit")
                    break
            else:
                logger.warning("ffmpeg stdin closed — ending pump emit")
                break

        return emitted_bytes / bytes_per_sec

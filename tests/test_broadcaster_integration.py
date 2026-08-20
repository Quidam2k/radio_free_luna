"""
True integration test for the Broadcaster: real WAV files, real ffmpeg
subprocess, real listener queue. Skipped automatically when ffmpeg or pydub
is unavailable.
"""

import asyncio
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

pydub = pytest.importorskip("pydub")
from pydub.generators import Sine  # noqa: E402

from src.streaming.broadcaster import Broadcaster  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH"
)


@dataclass
class FakeSegment:
    content: str
    type: str = "opening"
    duration_estimate: float = 5.0
    voice_settings: Optional[Dict] = None


@dataclass
class FakeTrackItem:
    track: Dict[str, Any]
    position: int
    start_time: str = "00:00:00"
    commentary_before: Any = None
    crossfade_duration: float = 1.0
    context_relevance_score: float = 0.0


@dataclass
class FakeSession:
    session_id: str = "test_session"
    theme: str = "test"
    tracks: List[FakeTrackItem] = field(default_factory=list)
    commentary_segments: List[Any] = field(default_factory=list)


class FakeSessionManager:
    def __init__(self, session: FakeSession):
        self._session = session

    async def create_session(self, theme, duration_minutes, context):
        return self._session


def write_tone(path, duration_ms=3000, freq=440):
    tone = (
        Sine(freq)
        .to_audio_segment(duration=duration_ms)
        .apply_gain(-12.0)
        .set_frame_rate(44100)
        .set_channels(2)
        .set_sample_width(2)
    )
    tone.export(str(path), format="wav")
    return str(path)


@pytest.fixture
def two_track_session(tmp_path):
    p1 = write_tone(tmp_path / "t1.wav", freq=440)
    p2 = write_tone(tmp_path / "t2.wav", freq=660)
    return FakeSession(
        tracks=[
            FakeTrackItem(
                track={"title": "Tone A", "artist": "Test", "file_path": p1, "duration": 3},
                position=1,
            ),
            FakeTrackItem(
                track={"title": "Tone B", "artist": "Test", "file_path": p2, "duration": 3},
                position=2,
            ),
        ]
    )


async def _collect_stream(broadcaster, min_bytes=20_000, timeout=30.0):
    queue = await broadcaster.register_listener()
    received = bytearray()
    try:
        async with asyncio.timeout(timeout):
            while len(received) < min_bytes:
                chunk = await queue.get()
                if chunk is None:
                    break
                received.extend(chunk)
    finally:
        await broadcaster.unregister_listener(queue)
    return bytes(received)


class TestBroadcasterIntegration:
    def test_stream_produces_mp3_audio(self, two_track_session):
        async def run():
            broadcaster = Broadcaster(
                session_manager=FakeSessionManager(two_track_session),
                bitrate_kbps=128,
            )
            info = await broadcaster.start_session("test", 1, {})
            assert info["track_count"] == 2

            data = await _collect_stream(broadcaster)
            status = broadcaster.current_status()
            await broadcaster.stop_session()
            return data, status

        data, status = asyncio.run(run())

        # MP3 frame sync (0xFFEx) must appear in the byte stream
        assert len(data) >= 20_000
        assert any(
            data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0
            for i in range(min(len(data) - 1, 4096))
        ), "no MP3 frame sync found in stream output"

        assert status["active"] is True
        assert status["current_track"] is not None
        # Regression: duration must reflect the emitted body, never exceed
        # the source track length
        assert status["current_track"]["duration"] <= 3.5

    def test_skip_and_stop_lifecycle(self, two_track_session):
        async def run():
            broadcaster = Broadcaster(
                session_manager=FakeSessionManager(two_track_session),
                bitrate_kbps=128,
            )
            await broadcaster.start_session("test", 1, {})
            await asyncio.sleep(0.5)
            assert await broadcaster.skip_track() is True
            result = await broadcaster.stop_session()
            assert result["status"] == "stopped"
            assert broadcaster.is_active is False
            # Stopping again is a no-op, not an error
            assert (await broadcaster.stop_session())["status"] == "idle"

        asyncio.run(run())

    def test_broadcast_archiving(self, two_track_session, tmp_path):
        """With archive_dir set, the broadcast is recorded to an MP3 file."""
        archive_dir = tmp_path / "archives"

        async def run():
            broadcaster = Broadcaster(
                session_manager=FakeSessionManager(two_track_session),
                bitrate_kbps=128,
                archive_dir=str(archive_dir),
            )
            await broadcaster.start_session("test", 1, {})
            await _collect_stream(broadcaster, min_bytes=20_000)
            await broadcaster.stop_session()

        asyncio.run(run())

        archives = list(archive_dir.glob("*.mp3"))
        assert len(archives) == 1
        assert archives[0].stat().st_size > 10_000
        assert "test_session" in archives[0].name

    def test_commentary_mixed_when_tts_available(self, two_track_session, tmp_path):
        """Opening commentary should be synthesized and mixed into track 1."""

        voice_wav = write_tone(tmp_path / "voice.wav", duration_ms=1000, freq=220)
        with open(voice_wav, "rb") as f:
            voice_bytes = f.read()

        class FakeTTS:
            calls: List[str] = []

            async def synthesize_speech(self, text, voice_settings=None):
                FakeTTS.calls.append(text)
                return voice_bytes

        two_track_session.commentary_segments = [
            FakeSegment(content="Good evening, this is Radio Free Luna.")
        ]

        async def run():
            broadcaster = Broadcaster(
                session_manager=FakeSessionManager(two_track_session),
                bitrate_kbps=128,
                tts_client=FakeTTS(),
            )
            await broadcaster.start_session("test", 1, {})
            data = await _collect_stream(broadcaster, min_bytes=10_000)
            await broadcaster.stop_session()
            return data

        data = asyncio.run(run())

        assert len(data) >= 10_000
        assert FakeTTS.calls == ["Good evening, this is Radio Free Luna."]

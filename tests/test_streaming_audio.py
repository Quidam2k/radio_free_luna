"""
Real-audio tests for the streaming pipeline (no mocks).

Exercises the actual pydub math in BasicCrossfader and AudioProcessor with
generated tones, so regressions in gain/fade/duck logic fail loudly here
instead of on air.
"""

import asyncio

import pytest

pydub = pytest.importorskip("pydub")
from pydub.generators import Sine  # noqa: E402

from src.streaming.crossfader import BasicCrossfader  # noqa: E402
from src.streaming.audio_processor import AudioProcessor  # noqa: E402


def make_tone(duration_ms: int = 4000, freq: int = 440, gain_db: float = -12.0):
    tone = Sine(freq).to_audio_segment(duration=duration_ms).apply_gain(gain_db)
    return tone.set_frame_rate(44100).set_channels(2).set_sample_width(2)


class TestCrossfaderRealAudio:
    def test_mix_with_commentary_ducks_music(self):
        """The music under the commentary must get quieter, not louder."""
        music = make_tone(8000, freq=440)
        commentary = make_tone(3000, freq=880, gain_db=-20.0)
        fader = BasicCrossfader()

        mixed = fader.mix_with_commentary(
            music, commentary, commentary_position="beginning", music_duck_level=0.3
        )

        assert len(mixed) == len(music)

        # Compare the ducked window against the untouched part of the result.
        # 0.3 duck = ~-10.5 dB on the music; even with the quiet commentary
        # overlaid, the window must be meaningfully quieter than the rest.
        ducked_window = mixed[500:2500]
        clean_window = mixed[4000:6000]
        assert ducked_window.dBFS < clean_window.dBFS - 3.0, (
            f"ducked={ducked_window.dBFS:.1f} dBFS not quieter than "
            f"clean={clean_window.dBFS:.1f} dBFS"
        )

    @pytest.mark.parametrize("fade_type", ["linear", "sine", "logarithmic", "smart"])
    def test_crossfade_types_produce_valid_audio(self, fade_type):
        t1 = make_tone(5000, freq=440)
        t2 = make_tone(5000, freq=660)
        fader = BasicCrossfader()

        result = fader.create_crossfade(t1, t2, fade_duration_ms=2000, crossfade_type=fade_type)

        # Overlap region merges, so total = len1 + len2 - fade
        assert abs(len(result) - 8000) <= 100
        assert result.rms > 0

    def test_logarithmic_fade_differs_from_linear(self):
        """Regression: linear and logarithmic used to be the same code path."""
        t1 = make_tone(5000, freq=440)
        t2 = make_tone(5000, freq=660)
        fader = BasicCrossfader()

        linear = fader.create_crossfade(t1, t2, fade_duration_ms=2000, crossfade_type="linear")
        log = fader.create_crossfade(t1, t2, fade_duration_ms=2000, crossfade_type="logarithmic")

        assert linear.raw_data != log.raw_data

    def test_fade_curves_have_no_dropout(self):
        """Sine/log stepped-gain fades must never hit -inf / silence mid-fade."""
        t1 = make_tone(5000, freq=440)
        t2 = make_tone(5000, freq=660)
        fader = BasicCrossfader()

        for fade_type in ("sine", "logarithmic"):
            result = fader.create_crossfade(t1, t2, fade_duration_ms=2000, crossfade_type=fade_type)
            # Crossfaded overlap sits at [3000, 5000) of the result
            overlap = result[3000:5000]
            assert overlap.rms > 0, f"{fade_type} crossfade produced silence"


class TestAudioProcessorAsync:
    def test_process_audio_file_offloads_and_returns_audio(self, tmp_path):
        """End-to-end: write a real wav, process it through the async API."""
        tone = make_tone(2000)
        wav_path = tmp_path / "tone.wav"
        tone.export(str(wav_path), format="wav")

        audio = asyncio.run(AudioProcessor().process_audio_file(str(wav_path)))

        assert audio is not None
        assert len(audio) >= 1900
        assert audio.frame_rate == 44100
        assert audio.channels == 2

    def test_missing_file_returns_none(self):
        audio = asyncio.run(AudioProcessor().process_audio_file("Q:/does/not/exist.mp3"))
        assert audio is None

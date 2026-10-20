"""Talk windows from synced lyrics (#3995): parse, distrust bad timing, never guess."""

import pytest

pytest.importorskip("numpy")  # src.mixdown needs numpy/librosa (global toolkit Python)
from src.mixdown import talk_windows as tw  # noqa: E402

LRC = "[ar:X]\n[00:12.00]one\n[00:16.00]two\n[00:20.00]three\n[00:24.00]four\n" \
      "[00:28.00]\n[00:40.00]five\n[01:10.00]six\n"


def test_parse_and_spans():
    stamps = tw.parse_lrc(LRC)
    assert stamps[0] == (12.0, "one") and (28.0, "") in stamps
    assert tw.check_timing(stamps, 120, 120) is None
    spans = tw.vocal_free_spans(stamps, 120)
    # intro, blank-marker break 28.5-39.5 merged with nothing, 30 s gap break, outro
    assert spans == [(0.0, 11.5, "intro"), (28.5, 39.5, "break"),
                     (46.0, 69.5, "break"), (76.0, 119.0, "outro")]


def test_overlapping_breaks_merge():
    stamps = tw.parse_lrc("[00:05]a\n[00:08]b\n[00:10]c\n[00:12]d\n[00:13]\n[00:40]e\n")
    breaks = [s for s in tw.vocal_free_spans(stamps, 60) if s[2] == "break"]
    assert breaks == [(13.5, 39.5, "break")]


@pytest.mark.parametrize("lrc,lyric_dur,dur,reason", [
    ("", 100, 100, "no_synced"),
    ("[00:01]a\n[00:02]b\n", 100, 100, "too_few_lines"),
    (LRC, 130, 120, "duration_mismatch"),
    (LRC, None, 60, "stamps_past_end"),
    ("[00:50]a\n[00:10]b\n[00:20]c\n[00:30]d\n", 100, 100, "non_monotonic"),
])
def test_bad_timing_is_skipped(lrc, lyric_dur, dur, reason):
    assert tw.check_timing(tw.parse_lrc(lrc), lyric_dur, dur) == reason


def test_read_api_fails_open(tmp_path):
    assert tw.talk_windows(1, db_path=tmp_path / "missing.db") == []

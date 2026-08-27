"""
Hermetic tests for the Chris-in-the-Morning corpus tooling (Pipeline #989).

No media, no network, no GPU — pure functions over inline fixtures. Covers
episode-id parsing, the source-agnostic normalizer (transcript + SRT), block
building, and the heuristic monologue extractor.
"""

import json

import pytest

from src.corpus import chris
from src.corpus import transcripts as T


# --- fixtures ----------------------------------------------------------------

def _mono_segments():
    """A cold-open Chris monologue: KBHR framing + a literary quote + length."""
    lines = [
        "Good morning, Cicely. This is Chris in the morning, here on K-B-H-R.",
        "You know, Walt Whitman once wrote that we contain multitudes, "
        "and I have been turning that over in the dark this morning.",
        "Consider the raven on the wire outside the studio, indifferent to "
        "our small human dramas, patient as the snow.",
        "So this one goes out to all you early risers dialed in on the "
        "airwaves. Stay warm out there, Cicely.",
    ]
    segs, t = [], 0.0
    for ln in lines:
        segs.append({"start": t, "end": t + 6.0, "text": ln})
        t += 6.5  # gap 0.5s -> one continuous block
    return segs


def _dialogue_segments(start=600.0):
    """Short conversational back-and-forth that must NOT be mistaken for a monologue."""
    turns = ["Hey.", "What?", "Nothing.", "Okay then.", "Bye."]
    segs, t = [], start
    for ln in turns:
        segs.append({"start": t, "end": t + 1.0, "text": ln})
        t += 1.5
    return segs


def _fixture_transcript():
    segs = _mono_segments() + _dialogue_segments()
    return T.make_transcript(
        episode="S01E03", title="Soapy Sanderson",
        segments=segs, source="asr:test", model="test", runtime_sec=1.0,
    )


# --- episode id / title parsing ---------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Northern Exposure - 1x03 - Soapy Sanderson.avi", "S01E03"),
    ("Northern Exposure - 4x02 - Midnight Sun [05-Oct-92] [found .avi", "S04E02"),
    ("Northern Exposure - 505 - A River Doesn't Run Through It.avi", "S05E05"),
    ("Northern Exposure - 6x02 - Eye of the Beholder.avi", "S06E02"),
    ("random clip.avi", "UNKNOWN"),
])
def test_parse_episode_id(name, expected):
    assert T.parse_episode_id(name) == expected


def test_parse_title():
    assert T.parse_title("Northern Exposure - 1x03 - Soapy Sanderson.avi") == "Soapy Sanderson"
    assert T.parse_title("Northern Exposure - 4x02 - Midnight Sun [05-Oct-92] [found .avi") == "Midnight Sun"


# --- normalizer + IO round trip ---------------------------------------------

def test_make_transcript_cleans_and_drops_empty():
    tr = T.make_transcript(
        episode="S01E01",
        segments=[{"start": 0, "end": 1, "text": "  hi   there \n"},
                  {"start": 1, "end": 2, "text": "   "}],
        source="asr:test",
    )
    assert len(tr["segments"]) == 1
    assert tr["segments"][0]["text"] == "hi there"


def test_transcript_io_round_trip(tmp_path):
    tr = _fixture_transcript()
    p = T.save_transcript(tr, tmp_path / "S01E03.transcript.json")
    assert p.exists()
    back = T.load_transcript(p)
    assert back["episode"] == "S01E03"
    assert back["segments"] == tr["segments"]


# --- SRT ingest (the deferred OpenSubtitles path uses this same normalizer) --

def test_srt_to_segments():
    srt = (
        "1\n"
        "00:00:01,000 --> 00:00:04,000\n"
        "<i>Good morning, Cicely.</i>\n"
        "This is Chris in the morning.\n\n"
        "2\n"
        "00:00:05,500 --> 00:00:08,000\n"
        "Here on K-B-H-R.\n"
    )
    segs = T.srt_to_segments(srt)
    assert len(segs) == 2
    assert segs[0]["start"] == 1.0 and segs[0]["end"] == 4.0
    assert "<i>" not in segs[0]["text"]
    assert segs[0]["text"] == "Good morning, Cicely. This is Chris in the morning."


# --- block building ----------------------------------------------------------

def test_build_blocks_splits_on_gap():
    segs = [
        {"start": 0.0, "end": 2.0, "text": "one"},
        {"start": 2.5, "end": 4.0, "text": "two"},      # small gap -> same block
        {"start": 30.0, "end": 32.0, "text": "three"},  # big gap -> new block
    ]
    blocks = chris.build_blocks(segs, max_gap=2.0)
    assert len(blocks) == 2
    assert blocks[0].n_segments == 2
    assert blocks[1].n_segments == 1


# --- the heuristic extractor -------------------------------------------------

def test_extract_finds_chris_monologue():
    tr = _fixture_transcript()
    recs = chris.extract_monologues(tr, min_confidence=0.35)

    assert recs, "expected at least one monologue candidate"
    # sorted by confidence desc
    assert recs == sorted(recs, key=lambda r: r["confidence"], reverse=True)

    top = recs[0]
    assert "Whitman" in top["text"]
    assert top["confidence"] >= 0.6          # strong: cold-open + radio + literary + shape
    assert top["episode"] == "S01E03"
    assert top["why"]                        # non-empty human-readable reasons
    # provenance + method are carried forward
    assert top["source"] == "asr:test"
    assert top["method"].startswith("heuristic")

    # the short dialogue must not surface as a monologue
    assert all("What?" not in r["text"] for r in recs)


def test_extract_respects_min_confidence():
    tr = _fixture_transcript()
    strict = chris.extract_monologues(tr, min_confidence=0.99)
    assert strict == []


def test_extract_is_source_agnostic_via_srt():
    """Same extractor over an SRT-derived transcript (the future OpenSubtitles path)."""
    srt_lines, t = [], 1
    cues = [
        "Good morning, Cicely. This is Chris in the morning on K-B-H-R.",
        "Walt Whitman once wrote that we contain multitudes.",
        "Consider the raven, indifferent to our small human dramas.",
        "This goes out to the early risers dialed in on the airwaves.",
    ]
    for i, c in enumerate(cues, 1):
        a = f"00:00:{t:02d},000"
        b = f"00:00:{t+5:02d},000"
        srt_lines.append(f"{i}\n{a} --> {b}\n{c}\n")
        t += 6
    segs = T.srt_to_segments("\n".join(srt_lines))
    tr = T.make_transcript(episode="S01E03", segments=segs, source="srt:test")
    recs = chris.extract_monologues(tr, min_confidence=0.35)
    assert recs
    assert recs[0]["source"] == "srt:test"
    assert recs[0]["confidence"] >= 0.5

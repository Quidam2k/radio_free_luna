"""
Hermetic tests for the Northern Exposure DVD-subtitle corpus (#6011).

Inline SRT fixtures only: cue flags (italic / music / lyric / captions),
watermark stripping, cp1252 decoding, off-screen radio extraction, speaker
self-id, and music-cue grouping + monologue linkage. No media, no network.
"""

import json
import sys
from pathlib import Path

from src.corpus import chris, songs
from src.corpus import transcripts as T

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _srt(cues):
    """cues: list of (start_sec, end_sec, text) -> SRT text."""
    def ts(x):
        return f"00:{int(x) // 60:02d}:{int(x) % 60:02d},{int(round((x % 1) * 1000)):03d}"
    return "\n".join(
        f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)
    )


# --- cue flags ---------------------------------------------------------------

def test_flags_off_by_default_keeps_old_shape():
    segs = T.srt_to_segments(_srt([(1, 3, "<i>Morning, Cicely.</i>")]))
    assert segs == [{"start": 1.0, "end": 3.0, "text": "Morning, Cicely."}]


def test_italic_music_lyric_and_captions():
    srt = _srt([
        (1, 3, "<i>Afternoon, Cicely.</i>"),
        (4, 6, "# You gotta shave it\nand sink it #"),
        (7, 9, "??[ Orchestra ]"),
        (10, 12, "? Well, it's over?"),
        (13, 15, "[ Man #2 ]\nGood luck, buddy!"),
        (16, 18, "Is that a question?"),
    ])
    segs = T.srt_to_segments(srt, flags=True)
    assert segs[0].get("italic") is True
    assert segs[1]["music"] and segs[1]["lyric"] == "You gotta shave it and sink it"
    assert segs[2]["music"] and "lyric" not in segs[2] and segs[2]["captions"] == ["Orchestra"]
    assert segs[3]["lyric"] == "Well, it's over"
    assert "music" not in segs[4] and segs[4]["captions"] == ["Man #2"]
    assert "music" not in segs[5]   # a trailing "?" alone is just a question


def test_watermark_cue_dropped():
    srt = _srt([
        (1, 3, '<font color="#ffff00" size=14>www.tvsubtitles.net</font>'),
        (4, 6, "Hello."),
    ])
    segs = T.srt_to_segments(srt, flags=True)
    assert [s["text"] for s in segs] == ["Hello."]


def test_decode_cp1252_fallback():
    raw = "1\n00:00:01,000 --> 00:00:02,000\nCaf\xe9 Brick\n".encode("cp1252")
    assert "Café" in T.decode_srt_bytes(raw)


def test_make_transcript_passes_flags_through():
    segs = T.srt_to_segments(_srt([(1, 3, "<i>Hi.</i>"), (4, 6, "# la la #")]), flags=True)
    tr = T.make_transcript(episode="S05E01", segments=segs, source="srt:DVD")
    assert tr["segments"][0]["italic"] is True
    assert tr["segments"][1]["lyric"] == "la la"


# --- KBHR extraction over subtitles -----------------------------------------

def _episode(extra):
    """An on-screen scene well past the cold open, plus ``extra`` cues."""
    filler = [(600 + i * 3, 602 + i * 3, "Okay.") for i in range(3)]
    tail = [(2600, 2602, "Bye.")]
    segs = T.srt_to_segments(_srt(filler + extra + tail), flags=True)
    return T.make_transcript(episode="S05E01", segments=segs, source="srt:DVD")


def test_short_offscreen_radio_bulletin_is_kept():
    tr = _episode([
        (1400, 1403, "<i>Afternoon, Cicely. We've got a medical update</i>"),
        (1403.2, 1407, "<i>on our own Dr. J, with his temperature hovering at 103.</i>"),
        (1407.5, 1409, "He's really sick."),   # on-screen reply: split off
    ])
    recs = chris.extract_monologues(tr)
    assert len(recs) == 1
    r = recs[0]
    assert r["italic_ratio"] == 1.0 and "He's really sick" not in r["text"]
    assert r["method"].endswith("+offscreen")
    assert r["id"] == "S05E01@01400.0"


def test_speaker_self_id():
    assert chris.attribute_speaker("This is Chris in the Morning.")[0] == "chris"
    assert chris.attribute_speaker(
        "Good morning, Cicely. This is Bernard Stevens, sitting in.")[0] == "bernard"
    assert chris.attribute_speaker("Just the weather today.")[0] == "uncertain"


def test_song_mentions_are_verbatim():
    assert chris.song_mentions("Stay warm. This one's for you, Leslie.") == [
        "This one's for you, Leslie."
    ]


# --- songs -------------------------------------------------------------------

def test_music_cues_group_and_link_to_monologue():
    tr = _episode([
        (1400, 1403, "<i>Afternoon, Cicely. This is Chris in the Morning</i>"),
        (1403.2, 1407, "<i>on K-Bear, and this one goes out to Maggie.</i>"),
        (1410, 1412, "# In the pines\nIn the pines #"),
        (1413, 1415, "# Where the sun never shines #"),
        (2000, 2002, '[ "Moon River" Playing ]'),
    ])
    monos = chris.extract_monologues(tr)
    cues = songs.extract_music_cues(tr, monos)
    assert len(cues) == 2
    first, second = cues
    assert first["lyrics"] == "In the pines In the pines / Where the sun never shines"
    assert first["song_title"] == ""                    # no guessing
    assert first["followed_monologue_id"] == monos[0]["id"]
    assert second["song_title"] == "Moon River" and second["title_source"] == "caption"
    assert second["followed_monologue_id"] is None


# --- ingest script -----------------------------------------------------------

def test_ingest_preserves_asr_and_writes_srt(tmp_path):
    import ingest_ne_subs

    subs = tmp_path / "subs" / "s01"
    subs.mkdir(parents=True)
    (subs / "Northern Exposure - 1x03 - Soapy Sanderson.DVD.en.srt").write_text(
        _srt([(1, 3, "<i>Good morning, Cicely.</i>")]), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "S01E03.transcript.json").write_text(
        json.dumps({"source": "asr:faster-whisper:small", "segments": []}), encoding="utf-8")

    sys.argv = ["ingest_ne_subs.py", "--subs", str(tmp_path / "subs"), "--out", str(out)]
    assert ingest_ne_subs.main() == 0

    asr = json.loads((out / "S01E03.asr.transcript.json").read_text(encoding="utf-8"))
    srt = json.loads((out / "S01E03.transcript.json").read_text(encoding="utf-8"))
    assert asr["source"].startswith("asr")
    assert srt["source"] == "srt:DVD" and srt["title"] == "Soapy Sanderson"
    assert srt["segments"][0]["italic"] is True

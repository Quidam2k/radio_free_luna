"""Tests for the enrichment toolkit (#894 Phase 2).

Focus is on the two things most likely to cause real damage: mis-identifying a
track, and writing tags when writing was supposed to be impossible.
"""

import json
import shutil

import pytest

from src.enrich import classify, identify, pipeline, tagio
from src.enrich.research import _full_credit


# --- identification -------------------------------------------------------


def test_topic_channel_yields_clean_artist():
    """'X - Topic' is YouTube's auto-generated channel; the artist is already right."""
    c = identify.identify(
        "a.m4a",
        {"artist": "The Beatles - Topic", "title": "All You Need Is Love (Remastered 2009)"},
    )
    assert c.artist == "The Beatles"
    assert c.title == "All You Need Is Love"
    assert c.tier == identify.Tier.TOPIC
    assert c.confidence >= 0.9


def test_vevo_channel_parses_artist_from_title():
    c = identify.identify(
        "b.m4a",
        {"artist": "4NonBlondesVEVO", "title": "4 Non Blondes - What's Up (Official Music Video)"},
    )
    assert c.artist == "4 Non Blondes"
    assert c.title == "What's Up"
    assert c.tier == identify.Tier.TITLE_DASH
    # The VEVO channel name corroborates the parsed artist, so confidence lifts.
    assert c.confidence >= 0.85


def test_real_artist_tag_is_kept():
    c = identify.identify("c.m4a", {"artist": "BANKS", "title": "Before I Ever Met You"})
    assert c.artist == "BANKS"
    assert c.tier in (identify.Tier.TAG_CLEAN, identify.Tier.TITLE_DASH)


def test_handle_style_channel_is_not_treated_as_artist():
    """'JediNg135' is a username, not a musician."""
    assert identify.looks_like_channel("JediNg135")
    assert identify.looks_like_channel("F3LC4T")
    assert identify.looks_like_channel("Netflix")
    assert not identify.looks_like_channel("The Beatles")
    assert not identify.looks_like_channel("4 Non Blondes")


def test_leading_track_number_is_not_an_artist():
    c = identify.identify("d.m4a", {"artist": "JediNg135", "title": "01 - Are You Alive?"})
    assert c.artist != "01"


def test_featured_artist_is_preserved():
    """'(feat. X)' is part of the song, not upload cruft."""
    assert "feat." in identify.clean_title("Black (feat. Norah Jones) (Official Video)")


def test_bitrate_and_video_cruft_stripped():
    assert identify.clean_title("Special (Official Video) (128kbit_AAC)") == "Special"


def test_filename_fallback_when_tags_unusable():
    c = identify.identify(
        "e.m4a", {}, stem="Parra For Cuva - Paspatou (Official Video) (152kbit_Opus)"
    )
    assert c.artist == "Parra For Cuva"
    assert c.title == "Paspatou"
    assert c.tier == identify.Tier.FILENAME


def test_title_recovered_from_filename_when_only_artist_tagged():
    """Observed on ripped MP3s keeping TCON/TPOS but no TIT2."""
    c = identify.identify(
        "01 - Kayleigh.mp3", {"artist": "Marillion"}, stem="01 - Kayleigh"
    )
    assert c.artist == "Marillion"
    assert c.title == "Kayleigh"


def test_folder_name_supplies_artist_when_tags_are_bare():
    c = identify.identify(
        "01 - Pseudo Silk Kimono.mp3",
        {},
        stem="01 - Pseudo Silk Kimono",
        folder_name="Marillion - Misplaced Childhood",
    )
    assert c.artist == "Marillion"
    assert c.title == "Pseudo Silk Kimono"
    assert c.tier == identify.Tier.FOLDER


def test_folder_hint_parses_artist_and_album():
    artist, album = identify.parse_folder_hint("Marillion - Misplaced Childhood")
    assert artist == "Marillion"
    assert album == "Misplaced Childhood"


def test_folder_hint_ignores_meaningless_directories():
    assert identify.parse_folder_hint("music") == (None, None)
    assert identify.parse_folder_hint("") == (None, None)


def test_matching_folder_corroborates_artist_tag():
    c = identify.identify(
        "02 - Kayleigh.mp3",
        {"artist": "Marillion"},
        stem="02 - Kayleigh",
        folder_name="Marillion - Misplaced Childhood",
    )
    assert c.confidence > identify.BASE_CONFIDENCE[identify.Tier.TAG_CLEAN]


# --- classification -------------------------------------------------------


def test_podcast_is_not_music():
    v = classify.classify(title="Ariel Ekblaw | Lex Fridman Podcast #271", duration=9000)
    assert not v.is_music
    assert v.kind == classify.Kind.PODCAST


def test_focus_mix_is_not_music():
    v = classify.classify(title="ADHD Relief Music: Poly-rhythmic Focus Music", duration=7200)
    assert not v.is_music
    assert v.kind == classify.Kind.AMBIENT


def test_ordinary_song_is_music():
    v = classify.classify(artist="BANKS", title="Before I Ever Met You", duration=210)
    assert v.is_music
    assert v.kind == classify.Kind.MUSIC


def test_long_runtime_without_markers_is_uncertain_not_music():
    """A 40-minute file is not a song even if nothing in the title says so."""
    v = classify.classify(artist="Someone", title="Live Set", duration=2400)
    assert not v.is_music
    assert v.kind == classify.Kind.UNCERTAIN


# --- research -------------------------------------------------------------


def test_full_credit_keeps_collaborators():
    """artist-credit[0] alone would drop everyone after the first name."""
    credit = [
        {"name": "Bakermat", "joinphrase": " & "},
        {"name": "Goldfish", "joinphrase": " feat. "},
        {"name": "Marie Plassard"},
    ]
    assert _full_credit(credit) == "Bakermat & Goldfish feat. Marie Plassard"


def test_full_credit_handles_single_artist():
    assert _full_credit([{"name": "BANKS"}]) == "BANKS"


def test_full_credit_handles_missing_credit():
    assert _full_credit([]) is None
    assert _full_credit(None) is None


# --- write safety ---------------------------------------------------------


def test_dry_run_never_writes(tmp_path):
    result = tagio.write_tags("nonexistent.m4a", artist="X", title="Y", dry_run=True)
    assert result["written"] is False
    assert result["status"] == "dry-run"


def test_write_refused_without_snapshot(tmp_path):
    """The snapshot is the rollback source; no snapshot, no write."""
    target = tmp_path / "f.m4a"
    target.write_bytes(b"\x00" * 2048)
    result = tagio.write_tags(
        str(target), artist="X", dry_run=False, snapshot_path=None
    )
    assert result["written"] is False
    assert "refused" in result["status"]


def test_write_refused_when_snapshot_path_missing_on_disk(tmp_path):
    target = tmp_path / "f.m4a"
    target.write_bytes(b"\x00" * 2048)
    result = tagio.write_tags(
        str(target),
        artist="X",
        dry_run=False,
        snapshot_path=str(tmp_path / "does-not-exist.json"),
    )
    assert result["written"] is False
    assert "refused" in result["status"]


def test_empty_title_is_never_written(tmp_path):
    """Blanking an existing frame is worse than leaving it alone."""
    snapshot = tmp_path / "snap.json"
    snapshot.write_text("{}", encoding="utf-8")
    target = tmp_path / "f.m4a"
    target.write_bytes(b"\x00" * 2048)

    result = tagio.write_tags(
        str(target), artist="Marillion", title="   ",
        dry_run=True, snapshot_path=str(snapshot),
    )
    assert "title" not in result["changes"]
    assert result["changes"].get("artist") == "Marillion"


def test_apply_report_refuses_without_snapshot():
    report = {"snapshot": None, "items": []}
    result = pipeline.apply_report(report, dry_run=False)
    assert result["written"] == 0
    assert "refused" in result["status"]


def test_snapshot_round_trips(tmp_path):
    """A snapshot must be readable JSON keyed by path, even for tagless files."""
    target = tmp_path / "g.m4a"
    target.write_bytes(b"\x00" * 2048)
    out = tmp_path / "snap.json"
    tagio.write_snapshot([str(target)], str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["file_count"] == 1
    assert str(target) in data["files"]


def test_vorbis_style_keys_do_not_crash_reader(tmp_path):
    """Regression: mutagen's VComment raises ValueError on non-lowercase key tests."""
    target = tmp_path / "h.ogg"
    target.write_bytes(b"not really ogg")
    assert tagio.read_tags(str(target)) == {}


def _a_sample_mp3():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "sample_audio"
    for p in sorted(root.rglob("*.mp3")):
        return p
    return None


@pytest.mark.skipif(_a_sample_mp3() is None, reason="no sample .mp3 available to copy")
def test_real_mp3_writeback_round_trips(tmp_path):
    """Regression (#971): the raw ID3 write assigned a list to a frame key, which
    mutagen rejects ('not a Frame instance'), so MP3 tags never got written. The
    easy=True path writes the correct frame; a real MP3 must round-trip."""
    target = tmp_path / "song.mp3"
    shutil.copyfile(_a_sample_mp3(), target)
    snapshot = tmp_path / "snap.json"
    tagio.write_snapshot([str(target)], str(snapshot))

    result = tagio.write_tags(
        str(target), artist="Adam Ant", title="Goody Two Shoes",
        dry_run=False, snapshot_path=str(snapshot),
    )
    assert result["written"] is True, result["status"]
    back = tagio.read_tags(str(target))
    assert back["artist"] == "Adam Ant"
    assert back["title"] == "Goody Two Shoes"

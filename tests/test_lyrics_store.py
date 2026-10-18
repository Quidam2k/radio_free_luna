"""Lyrics table + hook-phrase read path (#8201). No network.

What matters: a batch write is all-or-nothing, the read path never raises,
and prompts only ever get one short line, never the full lyrics.
"""

import sqlite3

import pytest

from src.notes import store

PLAIN = """[Verse 1]
Now here you go again, you say you want your freedom
Well, who am I to keep you down?

[Chorus]
Thunder only happens when it's raining
Players only love you when they're playing

Thunder only happens when it's raining
Players only love you when they're playing"""


def _row(**kw):
    row = {"key": store.song_key("Fleetwood Mac", "Dreams"), "artist": "Fleetwood Mac",
           "title": "Dreams", "album": "Rumours", "duration": 256.0, "status": "ok",
           "plain": PLAIN, "synced": "[00:01.00] Now here", "instrumental": False,
           "lrclib_id": 338535, "source": "lrclib", "detail": "get"}
    row.update(kw)
    return row


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "notes.db"
    with store.NotesStore(path) as s:
        s.save_lyrics_batch([_row()])
    return path


def test_roundtrip_and_status(db):
    with store.NotesStore(db) as s:
        assert s.lyrics_status(store.song_key("Fleetwood Mac", "Dreams")) == "ok"
        assert s.lyrics_status("nobody|nothing") is None
    got = store.lyrics("Fleetwood Mac", "Dreams (2004 Remaster)", db_path=db)
    assert got["found"] and got["plain"] == PLAIN and got["lrclib_id"] == 338535


def test_upsert_replaces(db):
    with store.NotesStore(db) as s:
        s.save_lyrics_batch([_row(status="nomatch", plain=None)])
    assert not store.lyrics("Fleetwood Mac", "Dreams", db_path=db)["found"]


def test_failed_batch_writes_nothing(tmp_path):
    path = tmp_path / "notes.db"
    with store.NotesStore(path) as s:
        bad = _row(key="b|b")
        del bad["status"]  # second row blows up mid-batch
        with pytest.raises(KeyError):
            s.save_lyrics_batch([_row(key="a|a"), bad])
        assert s.lyrics_status("a|a") is None


def test_hook_is_the_repeated_short_line(db):
    assert store.lyric_phrase("Fleetwood Mac", "Dreams", db_path=db) == \
        "Thunder only happens when it's raining"


def test_pick_phrase_falls_back_to_first_short_line():
    assert store.pick_phrase("Hi\nThis line has exactly six words\nAnother line of five words") \
        == "This line has exactly six words"
    assert store.pick_phrase("") == ""


def test_find_verse_ranks_stanzas():
    verses = store.find_verse(PLAIN, "thunder raining")
    assert verses and "Thunder" in verses[0]
    assert store.find_verse(PLAIN, "xylophone") == []


def test_read_path_fails_open(tmp_path):
    old = tmp_path / "old.db"
    sqlite3.connect(old).close()  # a store with no lyrics table
    assert store.lyrics("A", "B", db_path=old) == {"found": False, "artist": "A", "title": "B"}
    assert store.lyric_phrase("A", "B", db_path=tmp_path / "missing.db") == ""

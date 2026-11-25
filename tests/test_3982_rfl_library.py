"""RFL's own library is a lyrics/notes song source (#3982). No network."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.notes import lyrics_dump_import as dump
from src.notes import lyrics_fill, store


def _rfl(tmp_path):
    path = tmp_path / "rfl.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, title, artist, album, "
               "duration INTEGER, play_count INTEGER)")
    db.executemany("INSERT INTO tracks (title,artist,album,duration,play_count) VALUES (?,?,?,?,?)", [
        ("Solsbury Hill", "Peter Gabriel", "Peter Gabriel 1", 260, 0),
        ("Solsbury Hill", "Peter Gabriel", "Live", 260, 0),
        ("Sledgehammer", "Peter Gabriel", "So", 300, 5),
        ("Mystery", "Unknown", "x", 100, 0),
        (None, "Peter Gabriel", "x", 1, 0),
        ("Orphan", None, "x", 1, 0),
    ])
    db.commit()
    db.close()
    return path


def test_rfl_songs_dedupe_and_skip_generic(tmp_path):
    songs = lyrics_fill.load_rfl_songs(_rfl(tmp_path))
    assert [s["title"] for s in songs] == ["Sledgehammer", "Solsbury Hill"]
    assert songs[1]["duration"] == 260.0


def test_library_union_audiplex_wins(tmp_path, monkeypatch):
    mine = {"key": store.song_key("A", "T"), "artist": "A", "title": "T", "album": "r", "duration": 1.0}
    other = dict(mine, album="a")
    only = dict(mine, key="b|u", artist="B", title="U")
    monkeypatch.setattr(lyrics_fill, "load_rfl_songs", lambda p: [mine, only])
    monkeypatch.setattr(lyrics_fill, "load_songs", lambda p: [other])
    out = lyrics_fill.load_library(Path("a"), Path("r"))
    assert [s["key"] for s in out] == sorted([mine["key"], "b|u"])
    assert next(s for s in out if s["key"] == mine["key"])["album"] == "a"
    assert [s["key"] for s in lyrics_fill.load_library(Path("a"), None)] == [mine["key"]]


def test_scan_calls_gate_per_batch():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE tracks (id, artist_name, name, duration, last_lyrics_id)")
    db.execute("INSERT INTO tracks VALUES (1,'Peter Gabriel','Solsbury Hill',260,7)")
    calls = []
    wanted = {dump.match_key("Peter Gabriel", "Solsbury Hill"): [{}]}
    got = dump.scan_tracks(db, wanted, lambda: calls.append(1))
    assert list(got.values()) == [[(1, 260, 7)]] and len(calls) == 2  # once per fetch, incl. the final empty one


def test_gate_blocks_while_active(monkeypatch):
    idle = iter([5.0, 5.0, 999.0])
    sleeps = []
    monkeypatch.setattr(dump, "input_idle_seconds", lambda: next(idle))
    monkeypatch.setattr(dump.time, "sleep", sleeps.append)
    dump.make_gate(120)()
    assert sleeps == [30, 30]
    dump.make_gate(0)()  # disabled gate never looks at input


def test_build_notes_rfl_songs_most_played_first(tmp_path):
    import build_dj_notes
    songs = build_dj_notes.rfl_songs(_rfl(tmp_path))
    assert songs[0] == ("Peter Gabriel", "Sledgehammer")
    assert ("Unknown", "Mystery") not in songs


def test_tick_delta_survives_wrap():
    assert dump.tick_delta(100, 4_294_967_000) == 396
    assert dump.tick_delta(5000, 1000) == 4000


def test_real_idle_probe_returns_a_number():
    assert dump.input_idle_seconds() >= 0

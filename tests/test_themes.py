"""Themed sets by meaning (#949): store round-trip and the planner's theme-set pool."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.database import Track
from src.dj import planner
from src.notes import themes
from src.notes.store import song_key


def _row(artist, title, score, theme="halloween"):
    return {"theme": theme, "song_key": song_key(artist, title), "artist": artist,
            "title": title, "score": score, "reason": "r", "source": "lyrics_tags",
            "model": "claude-haiku-5-5"}


def test_save_and_query(tmp_path):
    db = tmp_path / "notes.db"
    assert themes.songs("halloween", db_path=db) == []  # missing db fails open
    themes.save_rows([_row("A", "Ghost", 3), _row("B", "Maybe", 1), _row("C", "Love", 0)], db)
    themes.save_rows([_row("B", "Maybe", 2)], db)  # re-score replaces
    got = themes.songs("Halloween", db_path=db)
    assert [r["title"] for r in got] == ["Ghost", "Maybe"]
    assert [r["title"] for r in themes.songs("halloween", 1, 1, db_path=db)] == []
    assert themes.tagged_keys("halloween", db) == {song_key("A", "Ghost"), song_key("B", "Maybe"),
                                                   song_key("C", "Love")}
    assert "grief" in themes.THEMES["halloween"]  # real-grief songs are ruled out (Karen rider)


def test_build_pool_uses_theme_set(temp_db, monkeypatch):
    Session = sessionmaker(bind=create_engine(temp_db))
    with Session() as s:
        for i in range(30):
            s.add(Track(file_path=f"/m/{i}.mp3", artist=f"Artist{i}", title=f"Song{i}", duration=200))
        s.commit()
    keys = {song_key(f"Artist{i}", f"Song{i}"): (3 if i < 5 else 2) for i in range(25)}
    monkeypatch.setattr(planner, "get_db", Session)
    monkeypatch.setattr(planner, "_theme_set", lambda theme: keys if "halloween" in theme.lower() else {})
    pool = planner.build_pool("Halloween night", size=10)
    assert len(pool) == 10
    assert all(song_key(t["artist"], t["title"]) in keys for t in pool)
    assert [t["theme_score"] for t in pool[:5]] == [3] * 5  # strongest fits first


def test_theme_set_lookup_by_word(tmp_path, monkeypatch):
    db = tmp_path / "notes.db"
    themes.save_rows([_row("A", "Ghost", 3)], db)
    real = themes.songs
    monkeypatch.setattr(themes, "songs", lambda name, *a, **k: real(name, db_path=db))
    assert planner._theme_set("spooky halloween set") == {song_key("A", "Ghost"): 3}
    assert planner._theme_set("jazz brunch") == {}

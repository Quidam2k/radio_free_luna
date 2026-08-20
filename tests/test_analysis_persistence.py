"""
Tests for AI analysis persistence: results must be stored in track_analysis
and reloaded from there instead of re-calling the API.
"""

import asyncio

import pytest

import src.core.database as database
from src.core.database import DatabaseManager, Track
from src.analysis.ai_analyzer import MusicAnalysisEngine, AnalysisResult


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Fresh SQLite DB wired into the module-global db_manager."""
    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    manager = DatabaseManager(db_url)
    manager.init_database()
    monkeypatch.setattr(database, "db_manager", manager)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def engine():
    return MusicAnalysisEngine("sk-test-not-real")


def add_track(manager, **overrides) -> int:
    session = manager.get_session()
    try:
        track = Track(
            file_path=overrides.get("file_path", "C:/music/test.mp3"),
            title=overrides.get("title", "Test Song"),
            artist=overrides.get("artist", "Test Artist"),
            genre=overrides.get("genre", "rock"),
            duration=200,
            file_hash="abc123",
        )
        session.add(track)
        session.commit()
        return track.id
    finally:
        session.close()


SAMPLE = AnalysisResult(
    themes=["love", "loss"],
    mood_valence=0.25,
    energy_level=0.7,
    danceability=0.6,
    summary="A test song.",
    cultural_context="None whatsoever.",
    notable_elements=["guitar solo"],
)


class TestAnalysisPersistence:
    def test_store_then_load_roundtrip(self, temp_db, engine):
        track_id = add_track(temp_db)

        asyncio.run(engine.store_analysis_result(track_id, SAMPLE))
        loaded = engine._load_analysis_from_db(track_id)

        assert loaded is not None
        assert loaded.themes == ["love", "loss"]
        assert loaded.mood_valence == pytest.approx(0.25)
        assert loaded.energy_level == pytest.approx(0.7)
        assert loaded.summary == "A test song."

    def test_analyze_uses_db_cache_instead_of_api(self, temp_db, engine):
        """With a stored analysis, no API call should happen at all."""
        track_id = add_track(temp_db)
        asyncio.run(engine.store_analysis_result(track_id, SAMPLE))

        session = temp_db.get_session()
        track = session.query(Track).filter_by(id=track_id).first()
        session.expunge(track)
        session.close()

        class ExplodingClient:
            def __getattr__(self, name):
                raise AssertionError("OpenAI client must not be touched on cache hit")

        engine.client = ExplodingClient()
        result = asyncio.run(engine.analyze_track_comprehensive(track))

        assert result.themes == ["love", "loss"]

    def test_get_unanalyzed_track_ids(self, temp_db, engine):
        analyzed = add_track(temp_db, file_path="C:/music/a.mp3")
        pending = add_track(temp_db, file_path="C:/music/b.mp3")
        asyncio.run(engine.store_analysis_result(analyzed, SAMPLE))

        ids = engine.get_unanalyzed_track_ids(limit=10)

        assert pending in ids
        assert analyzed not in ids

    def test_load_returns_none_for_unanalyzed(self, temp_db, engine):
        track_id = add_track(temp_db)
        assert engine._load_analysis_from_db(track_id) is None

"""
Unit tests for SessionManager sequencing logic (no DB, no network).
"""

from datetime import datetime, timedelta

import pytest

from src.dj.session_manager import SessionManager


@pytest.fixture
def manager():
    return SessionManager("sqlite:///:memory:", "sk-test-not-real")


def track(**overrides):
    base = {
        "id": 1,
        "title": "Song",
        "artist": "Artist",
        "genre": "rock",
        "duration": 200,
        "themes": ["energy"],
        "mood_valence": 0.5,
        "energy_level": 0.6,
        "danceability": 0.5,
        "play_count": 0,
        "last_played": None,
    }
    base.update(overrides)
    return base


class TestFreshness:
    def test_never_played_is_fully_fresh(self, manager):
        assert manager.calculate_freshness(track()) == pytest.approx(1.0)

    def test_just_played_is_heavily_penalized(self, manager):
        t = track(play_count=1, last_played=datetime.utcnow() - timedelta(minutes=10))
        assert manager.calculate_freshness(t) < 0.6

    def test_played_yesterday_recovers(self, manager):
        recent = track(play_count=1, last_played=datetime.utcnow() - timedelta(hours=2))
        old = track(play_count=1, last_played=datetime.utcnow() - timedelta(hours=30))
        assert manager.calculate_freshness(old) > manager.calculate_freshness(recent)

    def test_heavy_rotation_penalty_caps(self, manager):
        t = track(play_count=10_000)
        assert manager.calculate_freshness(t) == pytest.approx(0.5)

    def test_freshness_never_negative(self, manager):
        t = track(play_count=10_000, last_played=datetime.utcnow())
        assert manager.calculate_freshness(t) >= 0.0

    def test_pick_next_prefers_fresh_track(self, manager):
        """Two otherwise-identical tracks: the not-just-played one wins."""
        current = track(id=0)
        fresh = track(id=1, title="Fresh")
        stale = track(
            id=2, title="Stale", play_count=20,
            last_played=datetime.utcnow() - timedelta(minutes=5),
        )

        picked = manager.pick_next_track(
            current, [stale, fresh], position=2, total_tracks=10,
            energy_strategy="steady", context={},
        )
        assert picked["title"] == "Fresh"


class TestSequencingWeights:
    def test_weights_sum_to_one(self, manager):
        assert sum(manager.sequencing_weights.values()) == pytest.approx(1.0)

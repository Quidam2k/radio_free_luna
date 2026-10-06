"""#3886: an out-of-credits OpenAI account must not be retried per track, and must
not leave a stored fallback analysis behind (that marks the track analyzed forever)."""
import asyncio

import pytest

from src.core.database import Track, TrackAnalysis
from src.analysis.ai_analyzer import (QuotaExhausted, is_quota_error, next_quota_backoff,
                                      QUOTA_BACKOFF_START_S, QUOTA_BACKOFF_MAX_S)
from tests.test_analysis_persistence import add_track, engine, temp_db  # noqa: F401 fixtures


class QuotaError(Exception):
    code = "insufficient_quota"


class CountingClient:
    def __init__(self, exc):
        self.calls, self.exc = 0, exc
        outer = self

        class _Completions:
            def create(self, **kw):
                outer.calls += 1
                raise outer.exc

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_quota_error_detection():
    assert is_quota_error(QuotaError("x"))
    assert is_quota_error(Exception("Error code: 429 - {'type': 'insufficient_quota'}"))
    assert not is_quota_error(Exception("Error code: 429 - rate limit, slow down"))


def test_backoff_doubles_to_cap():
    seq, b = [], 0
    for _ in range(5):
        b = next_quota_backoff(b)
        seq.append(b)
    assert seq == [QUOTA_BACKOFF_START_S, 7200, 14400, QUOTA_BACKOFF_MAX_S, QUOTA_BACKOFF_MAX_S]


def test_quota_is_not_retried(engine):  # noqa: F811
    engine.client = CountingClient(QuotaError("no credits"))
    with pytest.raises(QuotaExhausted):
        asyncio.run(engine._call_openai_analysis("prompt"))
    assert engine.client.calls == 1


def test_quota_stores_no_fallback(temp_db, engine):  # noqa: F811
    track_id = add_track(temp_db)
    engine.client = CountingClient(QuotaError("no credits"))
    with pytest.raises(QuotaExhausted):
        asyncio.run(engine.analyze_and_store_track(track_id))
    session = temp_db.get_session()
    try:
        assert session.query(TrackAnalysis).filter_by(track_id=track_id).first() is None
    finally:
        session.close()
    assert track_id in engine.get_unanalyzed_track_ids(limit=10)


def test_other_errors_still_fall_back(temp_db, engine):  # noqa: F811
    track_id = add_track(temp_db)
    session = temp_db.get_session()
    track = session.query(Track).filter_by(id=track_id).first()
    session.expunge(track)
    session.close()
    engine.client = CountingClient(RuntimeError("boom"))
    orig_sleep = asyncio.sleep

    async def fast_sleep(s):
        await orig_sleep(0)

    asyncio.sleep = fast_sleep
    try:
        result = asyncio.run(engine.analyze_track_comprehensive(track))
    finally:
        asyncio.sleep = orig_sleep
    assert result is not None and engine.client.calls == 3

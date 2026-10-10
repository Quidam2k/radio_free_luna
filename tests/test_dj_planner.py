"""Planner validation (#4154): only pool ids, no repeated artist, breaks remapped."""

import json

import pytest

from src.dj import planner


def _pool(n=6):
    return [{"id": i, "artist": f"A{i}", "title": f"T{i}", "duration": 240, "themes": []}
            for i in range(1, n + 1)]


def _respond(monkeypatch, plan):
    sent = {}

    def fake(body, purpose):
        sent.update(body=body, purpose=purpose)
        return {"model": "claude-sonnet-5-5",
                "content": [{"type": "text", "text": json.dumps(plan)}]}

    monkeypatch.setattr(planner.llm_backend, "anthropic_messages", fake)
    return sent


def test_plan_filters_and_remaps(monkeypatch):
    pool = _pool()
    pool[3]["artist"] = "a1"  # same artist as track 1, different case
    sent = _respond(monkeypatch, {
        "set": [{"track_id": i, "why": f"w{i}"} for i in (1, 99, 2, 2, 4, 5, 6)],
        "breaks": [{"before_index": 0, "kind": "opening", "angle": "hi"},
                   {"before_index": 1, "kind": "transition", "angle": "dropped id"},
                   {"before_index": 5, "kind": "feature", "angle": "about 5"},
                   {"before_index": 6, "kind": "none", "angle": ""}],
    })
    plan = planner.plan_set("rain", 30, "ctx", "night", pool=pool)
    assert [t["id"] for t in plan["tracks"]] == [1, 2, 5, 6]
    assert plan["why"] == ["w1", "w2", "w5", "w6"]
    assert plan["breaks"] == [{"before_index": 0, "kind": "opening", "angle": "hi"},
                              {"before_index": 2, "kind": "feature", "angle": "about 5"}]
    assert sent["purpose"] == "planner"
    assert sent["body"]["output_config"]["format"]["type"] == "json_schema"


def test_plan_too_few_tracks(monkeypatch):
    _respond(monkeypatch, {"set": [{"track_id": 1, "why": ""}, {"track_id": 77, "why": ""}],
                           "breaks": []})
    with pytest.raises(ValueError, match="too few"):
        planner.plan_set("rain", 30, "ctx", "night", pool=_pool())


def test_plan_stops_at_target_length(monkeypatch):
    _respond(monkeypatch, {"set": [{"track_id": i, "why": ""} for i in range(1, 7)],
                           "breaks": []})
    plan = planner.plan_set("rain", 8, "ctx", "night", pool=_pool())  # 480s + 300s slack
    assert len(plan["tracks"]) == 4


def test_enabled(monkeypatch):
    monkeypatch.setenv("DJ_PLANNER", "Anthropic")
    assert planner.enabled()
    monkeypatch.delenv("DJ_PLANNER")
    assert not planner.enabled()

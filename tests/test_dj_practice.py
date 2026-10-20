"""Off-air practice stockpile + listener ratings (#4164)."""

import pytest

from src.dj import spoken_store


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DJ_SPOKEN_DB", str(tmp_path / "spoken.db"))
    monkeypatch.setenv("DJ_SPOKEN_DIR", str(tmp_path / "spoken"))


def _practice(text="from A into B", track=2, prev=1):
    return spoken_store.save(text, None, "transition", "nova", "evening", track, prev,
                             origin="practice")


def test_text_only_practice_then_audio_then_reuse():
    row = _practice()
    assert row["audio_path"] is None and row["origin"] == "practice"
    assert _practice()["id"] == row["id"]  # deduped
    # text-only lines are never aired
    assert spoken_store.find_reusable("transition", "nova", "evening", 2, 1) is None
    assert [r["id"] for r in spoken_store.text_only()] == [row["id"]]
    spoken_store.set_audio(row["id"], b"ID3fake")
    assert spoken_store.text_only() == []
    hit = spoken_store.find_reusable("transition", "nova", "evening", 2, 1)
    assert hit["id"] == row["id"]
    # a transition only matches its exact pair
    assert spoken_store.find_reusable("transition", "nova", "evening", 2, 9) is None
    assert spoken_store.find_reusable("transition", "nova", "evening", 2) is None


def test_thumbs_down_line_is_not_reused():
    row = _practice()
    spoken_store.set_audio(row["id"], b"ID3fake")
    spoken_store.rate(-1, line_id=row["id"], track_id=2)
    assert spoken_store.find_reusable("transition", "nova", "evening", 2, 1) is None
    spoken_store.rate(1, line_id=row["id"])
    assert spoken_store.find_reusable("transition", "nova", "evening", 2, 1)["id"] == row["id"]
    with pytest.raises(ValueError):
        spoken_store.rate(0, track_id=2)
    with pytest.raises(ValueError):
        spoken_store.rate(1)


def test_feedback_endpoint(client):
    row = _practice()
    response = client.post("/api/feedback", json={"rating": "down", "line_id": row["id"],
                                                  "track_id": 2})
    assert response.status_code == 200 and response.json()["rating"] == -1
    assert client.post("/api/feedback", json={"rating": "meh", "track_id": 2}).status_code == 400
    assert client.post("/api/feedback", json={"rating": "up"}).status_code == 400
    assert client.post("/api/feedback", json={"rating": "up", "track_id": "x"}).status_code == 400

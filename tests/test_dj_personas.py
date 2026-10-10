"""Persona cards (#4154 phase 4): docs/dj/personas/*.yaml drive the daypart persona."""

from types import SimpleNamespace

import pytest

from src.dj import personas
from src.dj.commentary_generator import DAYPART_PERSONAS, DJCommentaryGenerator


@pytest.fixture(autouse=True)
def fresh_cache():
    personas.load.cache_clear()
    yield
    personas.load.cache_clear()


def _ctx(tod):
    return {"temporal": SimpleNamespace(time_of_day=tod)}


def test_shipped_cards_cover_every_daypart():
    cards = personas.load()
    assert set(cards) == set(DAYPART_PERSONAS)
    for daypart, card in cards.items():
        assert card["name"] == DAYPART_PERSONAS[daypart]["name"]
        assert card["host"] in card["directive"]
        assert card["voice"] and card["fallback_openings"] and card["fallback_transitions"]


def test_card_drives_persona_and_voice(tmp_path, monkeypatch):
    (tmp_path / "m.yaml").write_text(
        "daypart: morning\nshow: Test Show\nhost: Pat Q\ndirective: Be brief.\n"
        "voice: shimmer\nspeed: 1.2\navoids: [puns]\n"
        "fallback_openings: ['hi {theme}']\nfallback_transitions: ['next']\n",
        encoding="utf-8")
    (tmp_path / "broken.yaml").write_text("daypart: evening\n", encoding="utf-8")
    monkeypatch.setenv("DJ_PERSONA_DIR", str(tmp_path))
    gen = DJCommentaryGenerator("sk-test-not-real")
    persona = gen._persona(_ctx("morning"))
    assert persona["name"] == "Test Show"
    assert "Pat Q" in persona["directive"] and "Avoid: puns." in persona["directive"]
    assert gen._get_contextual_voice_settings(_ctx("morning"))["voice"] == "shimmer"
    assert gen._get_storytelling_voice_settings(_ctx("morning"))["voice"] == "shimmer"
    # the broken card is skipped: evening falls back to the built-in persona
    assert gen._persona(_ctx("evening")) is DAYPART_PERSONAS["evening"]


def test_missing_dir_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("DJ_PERSONA_DIR", str(tmp_path / "nope"))
    gen = DJCommentaryGenerator("sk-test-not-real")
    assert gen._persona(_ctx("late_night")) is DAYPART_PERSONAS["late_night"]
    assert gen._get_storytelling_voice_settings()["voice"] == "onyx"

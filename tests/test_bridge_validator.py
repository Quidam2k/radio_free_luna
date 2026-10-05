"""Bridge validator (#6914): cleaning, banned phrases, unsourced numbers and names."""

import pytest

from src.dj.bridge_validator import clean, retry_hint, validate


FACTS = [
    {
        "text": "The song was written during a rainy week in Seattle.",
        "source": "liner notes",
    }
]
CURRENT = {"title": "Night Road", "artist": "The Lanterns"}
NEXT = {"title": "Blue Horizon", "artist": "Mira Lane"}


def test_clean_strips_think_label_emphasis_and_stage_direction():
    raw = (
        "<think>Explain the choice here.</think>"
        "**Transition:** *Rain keeps time* [music fades] for us."
    )
    assert clean(raw) == "Rain keeps time for us."


def test_clean_removes_dangling_think_block():
    assert clean("DJ: A usable line.<think>private reasoning") == "A usable line."


def test_clean_extracts_json_bridge():
    raw = '{"bridge": "DJ: _Moonlight_ keeps us company."}'
    assert clean(raw) == "Moonlight keeps us company."


def test_good_bridge_passes():
    draft = (
        "Rain makes every street sound reflective; this song was written "
        "during a rainy week, and Blue Horizon carries us onward."
    )
    verdict = validate(draft, FACTS, CURRENT, NEXT)
    assert verdict.ok
    assert verdict.reasons == []


def test_banned_phrase_fails():
    draft = (
        "They called it a smash hit, but tonight Blue Horizon feels quieter "
        "than all that noise."
    )
    verdict = validate(draft, FACTS, CURRENT, NEXT)
    assert not verdict.ok
    assert any("smash hit" in reason for reason in verdict.reasons)


def test_unsourced_year_fails():
    draft = (
        "The road bends back toward 1969 for a moment, then Blue Horizon "
        "carries us into the next stretch."
    )
    verdict = validate(draft, FACTS, CURRENT, NEXT)
    assert any("1969" in reason and "not in the sourced facts" in reason
               for reason in verdict.reasons)


def test_sourced_year_passes():
    facts = [{"text": "The song was first recorded in 1969.", "source": "archive"}]
    draft = (
        "The road bends back toward 1969 for a moment, then Blue Horizon "
        "carries us into the next stretch."
    )
    assert validate(draft, facts, CURRENT, NEXT).ok


def test_unsourced_two_word_name_fails():
    draft = (
        "Some evenings put David Bowie in the passenger seat while "
        "Blue Horizon waits around the bend."
    )
    verdict = validate(draft, FACTS, CURRENT, NEXT)
    assert any("David Bowie" in reason for reason in verdict.reasons)


def test_name_present_in_facts_passes():
    facts = [
        {
            "text": "David Bowie once praised the songwriter's early work.",
            "source": "interview",
        }
    ]
    draft = (
        "Some evenings put David Bowie in the passenger seat while "
        "Blue Horizon waits around the bend."
    )
    assert validate(draft, facts, CURRENT, NEXT).ok


def test_track_artist_name_is_allowed():
    draft = (
        "A rainy week can linger in a melody, and Mira Lane lets "
        "Blue Horizon carry the weather home."
    )
    assert validate(draft, FACTS, CURRENT, NEXT).ok


@pytest.mark.parametrize(
    ("draft", "reason_fragment"),
    [
        ("Too brief.", "at least 40"),
        ("quiet " * 110, "no more than 600"),
    ],
)
def test_length_limits(draft, reason_fragment):
    verdict = validate(draft, FACTS, CURRENT, NEXT)
    assert not verdict.ok
    assert any(reason_fragment in reason for reason in verdict.reasons)


def test_more_than_two_paragraphs_fails():
    draft = (
        "Rain gathers along the road tonight.\n\n"
        "The old pavement listens in the dark.\n\n"
        "Blue Horizon takes us the rest of the way."
    )
    verdict = validate(draft, FACTS, CURRENT, NEXT)
    assert any("not multiple paragraphs" in reason for reason in verdict.reasons)


def test_title_readout_at_start_fails():
    draft = (
        "Blue Horizon by Mira Lane opens the next mile, with a little rain "
        "still shining on the road behind us."
    )
    verdict = validate(draft, FACTS, CURRENT, NEXT)
    assert any("not as a read-out" in reason for reason in verdict.reasons)


def test_retry_hint_is_one_actionable_paragraph():
    verdict = validate("Too brief.", FACTS, CURRENT, NEXT)
    hint = retry_hint(verdict)
    assert "\n" not in hint
    assert "rejected" in hint
    assert "only the sourced facts" in hint

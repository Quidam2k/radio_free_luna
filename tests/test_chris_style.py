"""Chris style layer, DJ_LLM backend switch (#6019) and the clone-voice gate (#6020/#6021)."""

import json
import random

import pytest

from src.dj import chris_style, llm_backend
from src.dj.commentary_generator import DJCommentaryGenerator
from src.voice import voice_policy
from src.voice.voice_policy import clone_allowed, is_clone_voice, resolve_voice

GUIDE = """# Chris style guide

## Openings
Stuff [S01E01@00001.0].

## 8. Compact digest
<!-- editor note -->
- Talk to one listener.
- Land on the record.

## Notes
Not in the digest.
"""


@pytest.fixture
def style_files(tmp_path, monkeypatch):
    guide = tmp_path / "guide.md"
    guide.write_text(GUIDE, encoding="utf-8")
    shots = tmp_path / "fewshot.jsonl"
    rows = [{"id": f"S01E0{i}@1", "move": m, "excerpt": f"{m} words {i}"}
            for i, m in enumerate(["open", "tangent", "into_song", "dedication", "close", "tangent"])]
    shots.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(chris_style, "GUIDE_PATH", guide)
    monkeypatch.setattr(chris_style, "FEWSHOT_PATH", shots)
    return guide, shots


def test_digest_extracts_only_its_section():
    d = chris_style._digest(GUIDE)
    assert "Land on the record." in d
    assert "Not in the digest" not in d and "Stuff" not in d and "editor note" not in d


def test_pick_fewshots_matches_kind():
    rows = [{"move": m, "excerpt": m} for m in ["open", "tangent", "into_song", "dedication"] * 3]
    picked = chris_style.pick_fewshots(rows, "request", n=4, rng=random.Random(1))
    assert len(picked) == 4
    assert {p["move"] for p in picked} == {"dedication", "into_song"}


def test_style_block_has_digest_examples_and_fact_rule(style_files):
    block = chris_style.style_block("transition", rng=random.Random(0))
    assert "Talk to one listener." in block
    assert "[tangent]" in block or "[into_song]" in block
    assert "[open]" not in block
    assert "SOURCED FACTS" in block


def test_style_block_empty_without_files(tmp_path):
    assert chris_style.load_digest(tmp_path / "missing.md") == ""
    assert chris_style.load_fewshots(tmp_path / "missing.jsonl") == []


def test_system_prompt_fails_open_without_style(monkeypatch):
    monkeypatch.setattr("src.dj.commentary_generator.style_block", lambda kind: "")
    gen = DJCommentaryGenerator("sk-test-not-real")
    system = gen._system_prompt(None, "transition")
    assert "Chris in the Morning" in system and "EXAMPLES" not in system


@pytest.mark.asyncio
async def test_claude_cli_backend_is_used_when_selected(monkeypatch):
    monkeypatch.setenv("DJ_LLM", "claude_cli")
    seen = {}

    def fake(system, prompt):
        seen["system"], seen["prompt"] = system, prompt
        return "Morning, friends."

    monkeypatch.setattr(llm_backend, "claude_cli_complete", fake)
    monkeypatch.setattr("src.dj.commentary_generator.style_block", lambda kind: f"STYLE-{kind}")
    gen = DJCommentaryGenerator("sk-test-not-real")
    out = await gen._call_llm("bridge please", None, kind="request")
    assert out == "Morning, friends."
    assert seen["prompt"] == "bridge please"
    assert "STYLE-request" in seen["system"]


@pytest.mark.asyncio
async def test_openai_backend_is_default(monkeypatch):
    monkeypatch.delenv("DJ_LLM", raising=False)
    gen = DJCommentaryGenerator("sk-test-not-real")

    async def fake_openai(prompt, system):
        return "from openai"

    monkeypatch.setattr(gen, "_call_openai_for_commentary", fake_openai)
    monkeypatch.setattr(llm_backend, "claude_cli_complete",
                        lambda *a: pytest.fail("claude_cli must not run by default"))
    assert await gen._call_llm("x") == "from openai"


def test_request_and_opening_prompts_carry_facts_block():
    gen = DJCommentaryGenerator("sk-test-not-real")
    gen._facts_block = lambda track: "FACTS-MARKER"
    assert "FACTS-MARKER" in gen._build_opening_prompt("chill", {"title": "T", "artist": "A"}, "ctx")
    assert "FACTS-MARKER" in gen._build_feature_prompt({"title": "T", "artist": "A"}, {}, "artist_spotlight")


# --- clone-voice gate (#6020 / #6021), three audience tiers (#6915 / #6918) ---

LOCAL_TTS = "http://localhost:7860"
SHARED, LOCAL, PUBLIC = "private-shared", "private-local", "public"


@pytest.fixture(autouse=True)
def _no_archive_no_private_hosts(monkeypatch):
    monkeypatch.delenv("ARCHIVE_BROADCASTS", raising=False)
    monkeypatch.delenv("PRIVATE_TTS_HOSTS", raising=False)


def test_clone_detection(monkeypatch):
    monkeypatch.setenv("CLONE_VOICES", "chris")
    assert is_clone_voice("clone:chris")
    assert is_clone_voice(r"Q:\x\data\voice_private\chris.wav")
    assert is_clone_voice("Chris")
    assert not is_clone_voice("fable") and not is_clone_voice(None)


@pytest.mark.parametrize("output", ["stream", "archive", "mixdown", "podcast", "test_voice",
                                    "private_speak", "", "unknown"])
def test_clone_refused_without_a_proven_private_audience(output):
    """No audience given = nobody authenticated = public, on every output but local ones."""
    assert not clone_allowed(output, tts_url=LOCAL_TTS)[0]
    assert resolve_voice("clone:chris", output, tts_url=LOCAL_TTS) == "fable"


@pytest.mark.parametrize("output", ["archive", "mixdown", "podcast", "test_voice", "unknown"])
def test_files_and_unknown_outputs_are_public_even_for_private_listeners(output):
    assert not clone_allowed(output, tts_url=LOCAL_TTS, audience=[LOCAL, SHARED])[0]


def test_private_local_tier_allowed():
    assert clone_allowed("local_playback", tts_url=LOCAL_TTS)[0]
    assert clone_allowed("private_speak", tts_url=LOCAL_TTS, audience=[LOCAL])[0]
    assert resolve_voice("clone:chris", "private_bridge",
                         tts_url="http://127.0.0.1:7860") == "clone:chris"


def test_private_shared_tier_allowed_for_invited_listeners():
    """Todd's ruling (#6915): invited friends, even remote, are private, not public."""
    assert clone_allowed("private_speak", tts_url=LOCAL_TTS, audience=[SHARED])[0]
    assert clone_allowed("stream", tts_url=LOCAL_TTS, audience=[LOCAL, SHARED, SHARED])[0]


def test_stream_goes_public_when_any_listener_is_public_or_unknown():
    assert not clone_allowed("stream", tts_url=LOCAL_TTS, audience=[LOCAL, PUBLIC])[0]
    assert not clone_allowed("stream", tts_url=LOCAL_TTS, audience=[SHARED, "weird"])[0]
    assert not clone_allowed("stream", tts_url=LOCAL_TTS, audience=[])[0]


def test_archived_stream_is_public(monkeypatch):
    monkeypatch.setenv("ARCHIVE_BROADCASTS", "true")
    assert not clone_allowed("stream", tts_url=LOCAL_TTS, audience=[LOCAL])[0]


def test_clone_refused_on_cloud_or_unparseable_tts():
    for url in ["https://api.example-tts.com", "", "not a url"]:
        assert not clone_allowed("private_bridge", tts_url=url)[0]
        assert not clone_allowed("private_speak", tts_url=url, audience=[SHARED])[0]


def test_private_tts_hosts_allows_todds_own_boxes(monkeypatch):
    athena = "http://athena.lan:7779"
    assert not clone_allowed("local_playback", tts_url=athena)[0]
    monkeypatch.setenv("PRIVATE_TTS_HOSTS", "athena.lan")
    assert clone_allowed("local_playback", tts_url=athena)[0]


def test_default_env_with_cloud_tts_is_refused(monkeypatch):
    monkeypatch.setenv("TTS_WEBUI_URL", "https://cloud.example.com")
    assert not clone_allowed("local_playback")[0]


def test_non_clone_voice_passes_through():
    assert resolve_voice("onyx", "stream") == "onyx"


def test_fallback_is_never_a_clone():
    assert resolve_voice("clone:a", "stream", fallback="clone:b",
                         tts_url=LOCAL_TTS) == voice_policy.DEFAULT_FALLBACK_VOICE


def test_registered_clone_maps_to_its_local_clip(tmp_path, monkeypatch):
    reg = tmp_path / "voices.json"
    reg.write_text('{"clone:feyn": "C:/x/feyn.wav"}', encoding="utf-8")
    monkeypatch.setattr(voice_policy, "REGISTRY", reg)
    assert voice_policy.is_clone_voice("clone:feyn")
    assert voice_policy.tts_voice_name("clone:feyn") == "C:/x/feyn.wav"
    assert voice_policy.tts_voice_name("fable") == "fable"

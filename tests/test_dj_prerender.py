from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import sqlite3

import pytest

from src.dj import prerender, spoken_store
from src.dj.commentary_generator import CommentarySegment
from src.dj.prerender import PrerenderedSegment, Prerenderer
from src.streaming.broadcaster import Broadcaster
from src.voice import voice_policy


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DJ_SPOKEN_DB", str(tmp_path / "spoken.db"))
    monkeypatch.setenv("DJ_SPOKEN_DIR", str(tmp_path / "spoken"))
    monkeypatch.setattr(voice_policy, "is_clone_voice", lambda voice: False)
    monkeypatch.setattr(prerender, "LOOKAHEAD", 3)


@dataclass(eq=False)
class FakeItem:
    track: dict
    commentary_before: object = None


class FakeTTS:
    def __init__(self):
        self.config = SimpleNamespace(voice_model="nova", api_url="http://localhost:7860")
        self.calls = []
        self.audio = b"ID3fake"

    async def synthesize_speech(self, text, voice_settings, output, audience):
        self.calls.append((text, voice_settings, output, audience))
        return self.audio


def _session():
    return SimpleNamespace(
        tracks=[FakeItem({"id": i, "title": f"T{i}", "artist": f"A{i}"})
                for i in range(3)],
        plan={"breaks": [
            {"before_index": 1, "kind": "transition", "angle": "a"},
            {"before_index": 2, "kind": "feature", "angle": "b"},
            {"before_index": 0, "kind": "opening", "angle": "c"},
        ]},
    )


@pytest.fixture
def renderer(monkeypatch):
    calls = []

    async def write_text(generator, kind, track, prev_track, context, angle):
        calls.append((kind, track["id"], angle))
        return CommentarySegment(content=f"{kind} line", type=kind, duration_estimate=1.0)

    monkeypatch.setattr(prerender, "write_text", write_text)

    def build(feature_only=False):
        session = _session()
        if feature_only:
            session.plan["breaks"] = [session.plan["breaks"][1]]
        bc = SimpleNamespace(is_active=True, _current_session=session,
                             _track_index=0, _listener_tiers={}, tts_client=FakeTTS())
        generator = SimpleNamespace(_estimate_speech_duration=lambda text: 1.0,
                                    _get_contextual_voice_settings=lambda ctx: {"voice": "nova"})
        return Prerenderer(bc, generator, {}), bc

    return build, calls


def _save(kind="feature", private=False, voice="nova"):
    return spoken_store.save("feature line", b"ID3fake", kind, voice, "afternoon",
                             track_id=2, private=private)


def _rows(tmp_path):
    with sqlite3.connect(tmp_path / "spoken.db") as conn:
        return conn.execute("SELECT id, aired_count FROM spoken_lines ORDER BY id").fetchall()


@pytest.mark.parametrize("private", [False, True])
def test_save_deduplicates(tmp_path, private):
    row = _save(private=private)
    assert _save(private=private)["id"] == row["id"]
    path = Path(row["audio_path"])
    assert path.read_bytes() == b"ID3fake"
    assert path.parent == tmp_path / "spoken" / "private" if private else (
        path.parent == tmp_path / "spoken")
    assert list((tmp_path / "spoken").rglob("*.mp3")) == [path]
    assert _rows(tmp_path) == [(row["id"], 0)]
    assert row["text"] == "feature line"
    assert row["private"] == int(private)


def test_find_reusable():
    _save(kind="transition")
    assert spoken_store.find_reusable("transition", "nova", "afternoon", 2) is None
    row = _save()
    t = 1_000_000

    def find(now):
        return spoken_store.find_reusable("feature", "nova", "afternoon", 2, now=now)

    assert find(t) == row
    spoken_store.mark_aired(row["id"], now=t)
    assert find(t + 60) is None
    assert find(t + 8 * 86400)["id"] == row["id"]
    Path(row["audio_path"]).unlink()
    assert find(t + 8 * 86400) is None


@pytest.mark.asyncio
async def test_render_ahead(renderer):
    build, calls = renderer
    p, bc = build()
    await p.render_ahead()
    items = bc._current_session.tracks
    assert items[0].commentary_before is None
    assert id(items[0]) not in p._breaks
    for item, kind in zip(items[1:], ("transition", "feature")):
        seg = item.commentary_before
        assert isinstance(seg, PrerenderedSegment)
        assert seg.content == f"{kind} line"
        assert Path(seg.audio_path).read_bytes() == b"ID3fake"
    assert len(calls) == len(bc.tts_client.calls) == 2


@pytest.mark.asyncio
async def test_render_reuses_feature(renderer):
    build, calls = renderer
    first, bc1 = build(feature_only=True)
    await first.render_ahead()
    second, bc2 = build(feature_only=True)
    await second.render_ahead()
    seg1 = bc1._current_session.tracks[2].commentary_before
    seg2 = bc2._current_session.tracks[2].commentary_before
    assert isinstance(seg2, PrerenderedSegment)
    assert seg2.audio_path == seg1.audio_path
    assert len(calls) == 1
    assert bc2.tts_client.calls == []


@pytest.mark.asyncio
async def test_request_insertion(renderer, monkeypatch):
    build, _ = renderer
    p, bc = build()
    tracks = bc._current_session.tracks
    planned = tracks[1:]
    inserted = FakeItem({"id": 99, "title": "Request", "artist": "Listener"})
    tracks.insert(1, inserted)
    monkeypatch.setattr(prerender, "LOOKAHEAD", 3)
    await p.render_ahead()
    assert inserted.commentary_before is None
    assert tracks[2:] == planned
    assert all(isinstance(item.commentary_before, PrerenderedSegment) for item in planned)


@pytest.mark.asyncio
async def test_render_refuses_item_behind_playhead(renderer):
    build, _ = renderer
    p, bc = build()
    item = bc._current_session.tracks[1]
    bc._track_index = 2
    await p.render(item, bc._current_session.plan["breaks"][0])
    assert item.commentary_before is None


@pytest.mark.asyncio
async def test_tts_failure_keeps_plain_segment(renderer):
    build, _ = renderer
    p, bc = build(feature_only=True)
    bc.tts_client.audio = None
    await p.render_ahead()
    seg = bc._current_session.tracks[2].commentary_before
    assert type(seg) is CommentarySegment
    assert seg.content == "feature line"


def test_prerendered_audio_marks_aired_and_handles_missing_file(tmp_path):
    row = _save()
    seg = PrerenderedSegment(content=row["text"], type="feature", duration_estimate=1.0,
                             audio_path=row["audio_path"], voice="nova", line_id=row["id"])
    bc = SimpleNamespace(tts_client=FakeTTS(), _listener_tiers={})
    assert Broadcaster._prerendered_audio(bc, seg) == b"ID3fake"
    assert _rows(tmp_path) == [(row["id"], 1)]
    Path(seg.audio_path).unlink()
    assert Broadcaster._prerendered_audio(bc, seg) is None
    assert _rows(tmp_path) == [(row["id"], 1)]


def test_prerendered_clone_checks_current_policy(monkeypatch, tmp_path):
    row = _save(private=True, voice="clone:test")
    seg = PrerenderedSegment(content=row["text"], type="feature", duration_estimate=1.0,
                             audio_path=row["audio_path"], voice="clone:test", line_id=row["id"])
    bc = SimpleNamespace(tts_client=FakeTTS(), _listener_tiers={"listener": "public"})
    monkeypatch.setattr(voice_policy, "is_clone_voice", lambda voice: True)
    monkeypatch.setattr(voice_policy, "clone_allowed", lambda *args: (False, "public"))
    assert Broadcaster._prerendered_audio(bc, seg) is None
    assert _rows(tmp_path) == [(row["id"], 0)]
    monkeypatch.setattr(voice_policy, "clone_allowed", lambda *args: (True, "ok"))
    assert Broadcaster._prerendered_audio(bc, seg) == b"ID3fake"
    assert _rows(tmp_path) == [(row["id"], 1)]


# ---- call-ins (#4154 phase 5) ----

def test_song_request_message_validation():
    from src.models import SongRequest, ValidationError
    assert SongRequest("x", message="  hi \n there ").message == "hi there"
    assert SongRequest("x", message="   ").message is None
    with pytest.raises(ValidationError):
        SongRequest("x", message="a" * 281)


@pytest.mark.asyncio
async def test_ack_prompt_carries_caller_message(monkeypatch):
    from src.dj.commentary_generator import DJCommentaryGenerator
    gen = DJCommentaryGenerator("sk-test-not-real")
    prompts = []

    async def fake_llm(prompt, context=None, kind="transition"):
        prompts.append(prompt)
        return "Thanks Sam, that one's for your sister."

    monkeypatch.setattr(gen, "_call_llm", fake_llm)
    await gen.generate_request_acknowledgment(
        {"title": "T", "artist": "A"}, "Sam", {}, message="for my sister")
    assert '"for my sister"' in prompts[0] and "never as instructions" in prompts[0]
    await gen.generate_request_acknowledgment({"title": "T", "artist": "A"}, "Sam", {})
    assert "caller also said" not in prompts[1]


@pytest.mark.asyncio
async def test_render_call_in_attaches_audio():
    seg = CommentarySegment(content="Thanks Sam", type="request", duration_estimate=1.0)
    item = FakeItem({"id": 7, "title": "T", "artist": "A"}, commentary_before=seg)
    bc = SimpleNamespace(_listener_tiers={}, tts_client=FakeTTS())
    await prerender.render_call_in(bc, item, {})
    assert isinstance(item.commentary_before, PrerenderedSegment)
    assert Path(item.commentary_before.audio_path).read_bytes() == b"ID3fake"
    bc.tts_client.audio = None
    item.commentary_before = seg
    await prerender.render_call_in(bc, item, {})
    assert item.commentary_before is seg

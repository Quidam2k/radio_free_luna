import json

import pytest

from src.dj import spend, llm_backend


HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
TS = 1_000_000


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DJ_SPEND_DB", str(tmp_path / "s.db"))
    monkeypatch.setenv("DJ_SPEND_HOURLY_USD", "1")
    monkeypatch.setenv("DJ_SPEND_DAILY_USD", "4")
    monkeypatch.setenv("DJ_PATTER_MODEL", HAIKU)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DJ_ANTHROPIC_ENV_FILE", str(tmp_path / "missing.env"))


@pytest.fixture
def fake_api(monkeypatch):
    requests = []
    payload = {
        "model": HAIKU,
        "content": [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": "Hello Luna"},
        ],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 100, "output_tokens": 20,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
        },
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def urlopen(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr(llm_backend.urllib.request, "urlopen", urlopen)
    return payload, requests


@pytest.mark.parametrize("model,counts,expected", [
    (HAIKU, (1_000_000, 1_000_000, 0, 0), 0.60),
    (SONNET, (0, 0, 1_000_000, 0), 0.20),
    (SONNET, (0, 0, 0, 1_000_000), 2.50),
    ("unknown-model", (1_000_000, 1_000_000, 0, 0), 24.00),
])
def test_cost_usd(model, counts, expected):
    assert spend.cost_usd(model, *counts) == pytest.approx(expected)


def test_ledger(monkeypatch, tmp_path):
    db = tmp_path / "s.db"
    monkeypatch.setattr(spend.time, "time", lambda: TS - 90_000)
    spend.record("old-model", "old-purpose", {"input_tokens": 1_000_000}, db_path=db)
    monkeypatch.setattr(spend.time, "time", lambda: TS)
    assert spend.record(HAIKU, "patter", {
        "input_tokens": 1_000_000, "output_tokens": 1_000_000,
    }, db_path=db) == pytest.approx(0.6)
    assert spend.record(HAIKU, "patter", {
        key: None for key in ("input_tokens", "output_tokens",
                              "cache_read_input_tokens", "cache_creation_input_tokens")
    }, db_path=db) == 0
    assert spend.record(SONNET, "planner", {
        "cache_read_input_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000,
    }, db_path=db) == pytest.approx(2.7)
    assert spend.spent_since(3600, now=TS, db_path=db) == pytest.approx(3.3)
    assert spend.spent_since(3600, now=TS + 7200, db_path=db) == 0
    assert spend.spent_since(86400, now=TS + 7200, db_path=db) == pytest.approx(3.3)
    assert spend.summary(now=TS + 7200, db_path=db) == {
        "hour_usd": 0, "day_usd": 3.3, "hourly_cap": 1, "daily_cap": 4,
        "by_model_day": {
            HAIKU: {"calls": 2, "cost_usd": 0.6,
                    "input_tokens": 1_000_000, "output_tokens": 1_000_000},
            SONNET: {"calls": 1, "cost_usd": 2.7, "input_tokens": 0, "output_tokens": 0},
        },
        "by_purpose_day": {
            "patter": {"calls": 2, "cost_usd": 0.6},
            "planner": {"calls": 1, "cost_usd": 2.7},
        },
    }


def test_check_caps(monkeypatch, tmp_path):
    db = tmp_path / "s.db"
    monkeypatch.setattr(spend.time, "time", lambda: TS)
    spend.record(HAIKU, "patter", {"input_tokens": 10_000}, db_path=db)
    monkeypatch.setenv("DJ_SPEND_HOURLY_USD", "0.001")
    with pytest.raises(spend.CapExceeded, match="Hourly"):
        spend.check(now=TS, db_path=db)
    monkeypatch.setenv("DJ_SPEND_HOURLY_USD", "1")
    monkeypatch.setenv("DJ_SPEND_DAILY_USD", "0.001")
    assert spend.spent_since(3600, now=TS + 7200, db_path=db) == 0
    with pytest.raises(spend.CapExceeded, match="Daily"):
        spend.check(now=TS + 7200, db_path=db)
    monkeypatch.setenv("DJ_SPEND_DAILY_USD", "1")
    spend.check(now=TS, db_path=db)


def test_anthropic_complete(fake_api, tmp_path):
    _, requests = fake_api
    assert llm_backend.anthropic_complete("System", "Prompt") == "Hello Luna"
    assert len(requests) == 1
    headers = {key.lower(): value for key, value in requests[0].header_items()}
    assert headers["x-api-key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"
    body = json.loads(requests[0].data)
    assert body["model"] == HAIKU
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["output_config"]["effort"] == "low"
    assert spend.summary(db_path=tmp_path / "s.db")["by_model_day"][HAIKU]["calls"] == 1


def test_anthropic_cap_blocks_request(monkeypatch, tmp_path, fake_api):
    spend.record(HAIKU, "patter", {"input_tokens": 10_000}, db_path=tmp_path / "s.db")
    monkeypatch.setenv("DJ_SPEND_HOURLY_USD", "0.001")
    with pytest.raises(spend.CapExceeded):
        llm_backend.anthropic_complete("System", "Prompt")
    assert fake_api[1] == []


def test_refusal_records_usage(fake_api, tmp_path):
    fake_api[0]["stop_reason"] = "refusal"
    with pytest.raises(RuntimeError, match="refused"):
        llm_backend.anthropic_complete("System", "Prompt")
    db = tmp_path / "s.db"
    assert spend.summary(db_path=db)["by_model_day"][HAIKU]["calls"] == 1
    assert spend.spent_since(86400, db_path=db) == pytest.approx(0.00002)


def test_anthropic_key_file_and_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('OTHER=1\nANTHROPIC_API_KEY="sk-file"\n', encoding="utf-8")
    monkeypatch.setenv("DJ_ANTHROPIC_ENV_FILE", str(env_file))
    assert llm_backend._anthropic_key() == "sk-file"
    monkeypatch.setenv("DJ_ANTHROPIC_ENV_FILE", str(tmp_path / "missing.env"))
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not found"):
        llm_backend._anthropic_key()


def test_complete_routes_to_anthropic(monkeypatch):
    calls = []

    def fake_complete(system, prompt, model=None):
        calls.append((system, prompt, model))
        return "routed"

    monkeypatch.setattr(llm_backend, "anthropic_complete", fake_complete)
    assert llm_backend.complete("System", "Prompt", backend_name="anthropic",
                                model=SONNET) == "routed"
    assert calls == [("System", "Prompt", SONNET)]

"""Listener auth: loopback open, LAN/remote needs an invited token (#6914, #6918)."""

import pytest
from fastapi.testclient import TestClient

from src.core import listener_auth
from tests.conftest import as_client


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "listeners.json"
    monkeypatch.setattr(listener_auth, "STORE", path)
    return path


@pytest.fixture
def remote(app):
    return TestClient(as_client(app.app, "192.168.1.50"))


def test_remote_without_token_is_refused(store, remote):
    assert remote.get("/api/context").status_code == 401
    assert remote.get("/stream.mp3").status_code == 401


def test_health_stays_open(store, remote):
    assert remote.get("/health").status_code == 200


def test_invited_token_gets_in_and_sets_cookie(store, remote):
    token = listener_auth.add_listener("friend")
    r = remote.get(f"/api/context?t={token}")
    assert r.status_code == 200
    assert listener_auth.COOKIE in r.cookies
    assert remote.get("/api/context", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_revoked_and_wrong_tokens_are_refused(store, remote):
    token = listener_auth.add_listener("friend")
    assert remote.get("/api/context?t=nope").status_code == 401
    listener_auth.revoke_listener("friend")
    assert remote.get(f"/api/context?t={token}").status_code == 401


def test_unreadable_store_fails_closed(store, remote):
    store.write_text("{not json", encoding="utf-8")
    assert listener_auth.load_listeners() == {}
    assert remote.get("/api/context?t=anything").status_code == 401


def test_tokens_stored_hashed(store):
    token = listener_auth.add_listener("friend")
    assert token not in store.read_text(encoding="utf-8")


def test_loopback_needs_no_token(store, client):
    assert client.get("/api/context").status_code == 200

"""
Listener auth for the station (#6914 phase 1, #6915/#6918 private-shared tier).

Loopback clients (Todd's own machine) are open. Every other client needs an invited
listener's token on every route except /health: `?t=<token>`, `Authorization: Bearer
<token>`, or the `rfl_t` cookie the server sets after a valid `?t=`. Tokens are stored
only as sha256 in data/voice_private/listeners.json (gitignored with all of data/).
Manage them with scripts/listener_token.py. No store or an unreadable store = no
remote listener gets in (fail closed).

request.state.listener = {"tier": "private-local" | "private-shared", "name": str}
for every request that gets through; voice_policy reads the tier.
"""

import hashlib
import json
import logging
import secrets
from pathlib import Path
from typing import Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORE = PROJECT_ROOT / "data" / "voice_private" / "listeners.json"
COOKIE = "rfl_t"
OPEN_PATHS = {"/health"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_listeners(store: Optional[Path] = None) -> Dict[str, str]:
    """name -> sha256(token). Missing or unreadable store = {} (nobody remote)."""
    store = store or STORE
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"Listener store unreadable ({e}); refusing all remote listeners")
        return {}


def save_listeners(listeners: Dict[str, str], store: Optional[Path] = None) -> None:
    store = store or STORE
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(listeners, indent=1, sort_keys=True), encoding="utf-8")


def add_listener(name: str, store: Optional[Path] = None) -> str:
    """Create (or rotate) a listener's token. Returns the plaintext token, shown once."""
    token = secrets.token_urlsafe(24)
    listeners = load_listeners(store)
    listeners[name] = _hash(token)
    save_listeners(listeners, store)
    return token


def revoke_listener(name: str, store: Optional[Path] = None) -> bool:
    listeners = load_listeners(store)
    if listeners.pop(name, None) is None:
        return False
    save_listeners(listeners, store)
    return True


def listener_for_token(token: Optional[str], store: Optional[Path] = None) -> Optional[str]:
    if not token:
        return None
    digest = _hash(token)
    for name, stored in load_listeners(store).items():
        if secrets.compare_digest(stored, digest):
            return name
    return None


def is_loopback(host: Optional[str]) -> bool:
    return (host or "").strip().lower() in LOOPBACK_HOSTS


def _request_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("t") or request.cookies.get(COOKIE)


async def listener_auth_middleware(request: Request, call_next):
    client_host = request.client.host if request.client else None
    if is_loopback(client_host):
        request.state.listener = {"tier": "private-local", "name": "local"}
        return await call_next(request)
    if request.url.path in OPEN_PATHS:
        request.state.listener = {"tier": "public", "name": None}
        return await call_next(request)
    name = listener_for_token(_request_token(request))
    if not name:
        logger.warning(f"Refused unauthenticated {client_host} -> {request.url.path}")
        return JSONResponse({"detail": "listener token required"}, status_code=401)
    request.state.listener = {"tier": "private-shared", "name": name}
    response = await call_next(request)
    if request.query_params.get("t"):
        response.set_cookie(COOKIE, request.query_params["t"], httponly=True, samesite="lax",
                            max_age=60 * 60 * 24 * 90)
    return response

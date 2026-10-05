"""
Voice policy: who may hear a cloned voice (#6020, #6021; tiers per Todd's ruling, #6915/#6918).
Fails closed. Rules in notes/voice-clone-guardrail.md.

Three audience tiers:
- private-local   Todd's own machine: local playback, the private Pantheon bridge, or a
                  request from a loopback client.
- private-shared  listeners Todd invited, on the LAN or remote, proven by a listener token
                  (src/core/listener_auth.py).
- public          everything else: any unauthenticated listener, archives, mixdowns,
                  anything published, posted or saved to a shareable file.
A clone voice is allowed for the two private tiers only, and only when the TTS server is
Todd's own (loopback, or a host listed in PRIVATE_TTS_HOSTS, e.g. Athena): the clip and the
clone never go to a cloud TTS. Anything unknown (output, audience, TTS URL) counts as public.
When a clone is refused, callers get the non-clone fallback voice instead.
"""

import json
import logging
import os
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

PRIVATE_LOCAL, PRIVATE_SHARED, PUBLIC = "private-local", "private-shared", "public"
PRIVATE_TIERS = {PRIVATE_LOCAL, PRIVATE_SHARED}
LOCAL_OUTPUTS = {"local_playback", "private_bridge"}  # always on Todd's own machine
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_FALLBACK_VOICE = "fable"
VOICE_DIR = Path(__file__).resolve().parents[2] / "data" / "voice_private"
REGISTRY = VOICE_DIR / "voices.json"


def registered_clones() -> dict:
    """clone:<name> -> reference wav path, from data/voice_private/voices.json (add_voice.py)."""
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_clone_voice(voice: Optional[str]) -> bool:
    """A voice is a clone if it says so ('clone:' prefix), lives under voice_private,
    is registered in voices.json, or is listed in CLONE_VOICES (comma-separated)."""
    if not voice:
        return False
    v = str(voice).strip().lower()
    listed = {x.strip().lower() for x in os.getenv("CLONE_VOICES", "").split(",") if x.strip()}
    registered = {k.lower() for k in registered_clones()}
    return (v.startswith("clone:") or "voice_private" in v.replace("\\", "/")
            or v in listed or v in registered)


def _is_private_tts(tts_url: Optional[str]) -> bool:
    try:
        host = (urlparse(tts_url or "").hostname or "").lower()
    except Exception:
        return False
    private = LOOPBACK_HOSTS | {h.strip().lower() for h in
                                os.getenv("PRIVATE_TTS_HOSTS", "").split(",") if h.strip()}
    return bool(host) and host in private


def _archiving() -> bool:
    return os.getenv("ARCHIVE_BROADCASTS", "false").strip().lower() in ("1", "true", "yes", "on")


def audience_tier(output: str, audience: Optional[Iterable[str]] = None) -> str:
    """The tier of whoever can hear this output.

    output='local_playback' / 'private_bridge': private-local.
    output='private_speak': audio returned to one request; audience = [that request's tier].
    output='stream': the shared broadcast; audience = the tiers of every connected
        listener. Private only if there is at least one listener, all of them private,
        and the broadcast is not being archived.
    Anything else (archive, mixdown, test-voice, unknown): public.
    """
    if output in LOCAL_OUTPUTS:
        return PRIVATE_LOCAL
    tiers = list(audience or [])
    if output not in ("private_speak", "stream") or not tiers:
        return PUBLIC
    if output == "stream" and _archiving():
        return PUBLIC
    if any(t not in PRIVATE_TIERS for t in tiers):
        return PUBLIC
    return PRIVATE_SHARED if PRIVATE_SHARED in tiers else PRIVATE_LOCAL


def clone_allowed(output: str, tts_url: Optional[str] = None,
                  audience: Optional[Iterable[str]] = None) -> Tuple[bool, str]:
    """(allowed, reason) for using a clone voice on this output for this audience."""
    tier = audience_tier(output, audience)
    if tier not in PRIVATE_TIERS:
        return False, f"output '{output}' reaches a {tier} audience"
    tts_url = tts_url if tts_url is not None else os.getenv("TTS_WEBUI_URL", "")
    if not _is_private_tts(tts_url):
        return False, f"TTS server '{tts_url}' is not Todd's own machine"
    return True, f"{tier} audience with private TTS"


def resolve_voice(voice: Optional[str], output: str,
                  fallback: str = DEFAULT_FALLBACK_VOICE, tts_url: Optional[str] = None,
                  audience: Optional[Iterable[str]] = None) -> Optional[str]:
    """The voice to actually use: a clone only where clone_allowed says so, else fallback."""
    if not is_clone_voice(voice):
        return voice
    ok, reason = clone_allowed(output, tts_url, audience)
    if ok:
        return voice
    logger.warning(f"Clone voice refused ({reason}); using '{fallback}'")
    return fallback if not is_clone_voice(fallback) else DEFAULT_FALLBACK_VOICE


def tts_voice_name(voice: Optional[str]) -> Optional[str]:
    """What to send the TTS server: a registered clone becomes its local reference wav path
    (the clip stays on this machine); any other voice passes through. Call only on a voice
    resolve_voice already approved."""
    if not voice:
        return voice
    clones = {k.lower(): v for k, v in registered_clones().items()}
    return clones.get(str(voice).strip().lower(), voice)

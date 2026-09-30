"""
Voice policy: where a cloned voice may be used (#6020, #6021). Fails closed.

A clone of a real person's voice (the planned Chris clip) is for Todd's PERSONAL
listening only. See notes/voice-clone-guardrail.md. Rules enforced here:
- A clone voice is allowed only for PRIVATE outputs (local playback, the private
  Pantheon bridge), never the stream, archives, mixdowns or anything shareable.
- Even then, only while the station binds to loopback (HOST=0.0.0.0 exposes the
  stream to the LAN) and the TTS server is local (the clone never goes to a cloud TTS).
- Anything unknown (output name, host, TTS URL) counts as public.
When a clone is refused, callers get the non-clone fallback voice instead.
"""

import logging
import os
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

PRIVATE_OUTPUTS = {"local_playback", "private_bridge"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_FALLBACK_VOICE = "fable"


def is_clone_voice(voice: Optional[str]) -> bool:
    """A voice is a clone if it says so ('clone:' prefix), lives under voice_private,
    or is listed in CLONE_VOICES (comma-separated)."""
    if not voice:
        return False
    v = str(voice).strip().lower()
    listed = {x.strip().lower() for x in os.getenv("CLONE_VOICES", "").split(",") if x.strip()}
    return v.startswith("clone:") or "voice_private" in v.replace("\\", "/") or v in listed


def _is_loopback(host: Optional[str]) -> bool:
    return (host or "").strip().lower() in LOOPBACK_HOSTS


def clone_allowed(output: str, host: Optional[str] = None,
                  tts_url: Optional[str] = None) -> Tuple[bool, str]:
    """(allowed, reason) for using a clone voice on this output."""
    if output not in PRIVATE_OUTPUTS:
        return False, f"output '{output}' is not private"
    host = host if host is not None else os.getenv("HOST", "0.0.0.0")
    if not _is_loopback(host):
        return False, f"station HOST={host} is not loopback"
    tts_url = tts_url if tts_url is not None else os.getenv("TTS_WEBUI_URL", "")
    try:
        tts_host = urlparse(tts_url).hostname
    except Exception:
        tts_host = None
    if not _is_loopback(tts_host):
        return False, f"TTS server '{tts_url}' is not local"
    return True, "private output on a loopback station with local TTS"


def resolve_voice(voice: Optional[str], output: str,
                  fallback: str = DEFAULT_FALLBACK_VOICE,
                  host: Optional[str] = None, tts_url: Optional[str] = None) -> Optional[str]:
    """The voice to actually use: a clone only where clone_allowed says so, else fallback."""
    if not is_clone_voice(voice):
        return voice
    ok, reason = clone_allowed(output, host, tts_url)
    if ok:
        return voice
    logger.warning(f"Clone voice refused ({reason}); using '{fallback}'")
    return fallback if not is_clone_voice(fallback) else DEFAULT_FALLBACK_VOICE

"""Radio Free Luna — dedicated MCP server.

Exposes RFL's streaming DJ REST API as agent ("DJ") tools. Kept as a
standalone package — a thin, per-app MCP wrapper over the RFL server.

Config via environment:
  RFL_URL   base URL of the Radio Free Luna server (e.g. http://localhost:8080)

RFL has no auth, so there is no Bearer token. Note it binds 0.0.0.0 — an open
control surface over the LAN; put it behind your own network controls if needed.

RFL is NOT an always-on service — every tool catches httpx.ConnectError and
reports how to start it, rather than raising.

Tools: rfl_start_broadcast, rfl_stop, rfl_skip, rfl_status, rfl_request_song,
rfl_commentary, rfl_context.
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

RFL_URL = os.environ.get("RFL_URL", "http://localhost:8080").rstrip("/")

NOT_RUNNING = (
    "RFL server is not running (start Q:\\Development\\radio_free_luna\\launch.bat)"
)

mcp = FastMCP("rfl-dj")


@mcp.tool()
async def rfl_start_broadcast(theme: str, duration_minutes: int = 60) -> str:
    """Create a themed DJ session and start broadcasting it on RFL's
    /stream.mp3 (an unbounded live MP3 stream — point any stream player at
    '<RFL_URL>/stream.mp3').

    theme: music theme (e.g. 'rainy_day', 'upbeat', 'jazz').
    duration_minutes: session length, 5-480 (default 60).
    """
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{RFL_URL}/api/streaming/start",
                json={"theme": theme, "duration_minutes": duration_minutes},
            )
    except httpx.ConnectError:
        return NOT_RUNNING
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        return f"Failed to start broadcast: {data['error']}"
    return (
        f"Broadcasting theme '{theme}' for {duration_minutes}min "
        f"(session {data.get('session_id')}). Stream at {RFL_URL}{data.get('stream_url', '/stream.mp3')}"
    )


@mcp.tool()
async def rfl_stop() -> str:
    """Stop the active RFL broadcast, if any."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{RFL_URL}/api/streaming/stop")
    except httpx.ConnectError:
        return NOT_RUNNING
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        return f"Stop failed: {data['error']}"
    return f"Broadcast stopped: {data}"


@mcp.tool()
async def rfl_skip() -> str:
    """Skip immediately to the next track in the active RFL broadcast."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{RFL_URL}/api/streaming/skip")
    except httpx.ConnectError:
        return NOT_RUNNING
    resp.raise_for_status()
    data = resp.json()
    if not data.get("skipped"):
        return "Nothing to skip — no active broadcast."
    return "Skipped to the next track."


@mcp.tool()
async def rfl_status() -> str:
    """Report RFL's current broadcast + system status (merges
    GET /api/streaming/status with GET /status)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            streaming_resp = await client.get(f"{RFL_URL}/api/streaming/status")
            system_resp = await client.get(f"{RFL_URL}/status")
    except httpx.ConnectError:
        return NOT_RUNNING
    streaming = streaming_resp.json()
    system = system_resp.json()
    if not streaming.get("active"):
        return f"No active broadcast. System: {system.get('status', 'unknown')}"
    track = streaming.get("current_track") or {}
    lines = [
        f"Broadcasting: {track.get('title', '?')} - {track.get('artist', '?')}",
        f"System status: {system.get('status', 'unknown')}",
    ]
    context = system.get("context", {}).get("description")
    if context:
        lines.append(f"Context: {context}")
    return "\n".join(lines)


@mcp.tool()
async def rfl_request_song(query: str, requested_by: str | None = None) -> str:
    """Request a song on the live RFL broadcast: searches the library, queues
    the best match, and has the DJ acknowledge the requester on air.

    query: song title or artist to search for.
    requested_by: listener's name, spoken on air (optional).
    """
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{RFL_URL}/api/requests",
                json={"query": query, "requested_by": requested_by},
            )
    except httpx.ConnectError:
        return NOT_RUNNING
    resp.raise_for_status()
    data = resp.json()
    if not data.get("queued"):
        return data.get("error", f"Could not queue a request for '{query}'.")
    track = data.get("track") or {}
    lines = [f"Queued: {track.get('title', '?')} - {track.get('artist', '?')}"]
    ack = data.get("acknowledgment")
    if ack:
        lines.append(f"On-air acknowledgment: {ack}")
    return "\n".join(lines)


@mcp.tool()
async def rfl_commentary(text_type: str = "contextual") -> str:
    """Generate DJ commentary (requires OpenAI/TTS config on the RFL side —
    may error gracefully if unconfigured; that's expected on a fresh setup).

    text_type: 'contextual' | 'opening' | 'transition' | 'closing'.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{RFL_URL}/api/commentary",
                json={"text_type": text_type},
            )
    except httpx.ConnectError:
        return NOT_RUNNING
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        return f"Commentary generation failed: {data['error']}"
    return data.get("content", str(data))


@mcp.tool()
async def rfl_context() -> str:
    """Report RFL's current contextual awareness (time/weather/mood-derived
    music guidance) used to steer DJ theme choices."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{RFL_URL}/api/context")
    except httpx.ConnectError:
        return NOT_RUNNING
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        return f"Context unavailable: {data['error']}"
    lines = [data.get("description", "")]
    guidance = data.get("music_guidance")
    if guidance:
        lines.append(f"Music guidance: {guidance}")
    return "\n".join(l for l in lines if l)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

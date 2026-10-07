# rfl-dj — Radio Free Luna MCP server

Wraps RFL's REST API as agent tools — a thin, per-app control surface over
the running RFL server.

## Config

```
RFL_URL   base URL of the RFL server (default http://localhost:8080)
```

Loopback needs no token; LAN clients need a listener token (src/core/listener_auth.py).
RFL binds `0.0.0.0`, but every non-loopback request needs an invited token;
see scripts/listener_token.py.

RFL is not an always-on service. Every tool degrades to a clear message
("RFL server is not running...") instead of raising when the server is down.

## Run

Both servers run from their OWN venv, `.venv-mcp` (#6914). Never install `mcp` into the
station's `.venv`: it upgrades starlette/anyio/pydantic past FastAPI 0.104 and breaks
the station.

```
cd <path-to>/radio_free_luna
py -3.11 -m venv .venv-mcp
.venv-mcp\Scripts\python.exe -m pip install "mcp>=1.2.0,<2" "httpx>=0.27.0" mutagen aiohttp python-dotenv
.venv-mcp\Scripts\python.exe -m rfl_mcp.server    # rfl-dj: control surface over HTTP
.venv-mcp\Scripts\python.exe -m rfl_mcp.toolkit   # rfl-toolkit: notes/enrich, station-down OK
```

The rfl-toolkit server (`rfl_mcp/toolkit.py`) carries `rfl_track_notes` (sourced song
facts from `data/dj_notes.db`), `rfl_identify_track`, `rfl_enrich_scan`, `rfl_enrich_apply`.
It reads the DB directly, so it works with the station down.

Since the station binds the LAN with listener tokens (#6914), `RFL_URL` should stay on
`http://localhost:8080`: loopback needs no token.

The RFL server itself runs under the Pantheon Service Supervisor (#3840); wake it
with Pantheon's `wake_rfl` tool (the MCP server is a thin client over HTTP and
doesn't start RFL for you).

## Tools

- `rfl_start_broadcast(theme, duration_minutes=60)` — create a themed session
  and start broadcasting on `/stream.mp3`. Point any stream player at
  `<RFL_URL>/stream.mp3`.
- `rfl_stop()` — stop the active broadcast.
- `rfl_skip()` — skip to the next track.
- `rfl_status()` — current broadcast + system status.
- `rfl_request_song(query, requested_by=None)` — queue a listener request,
  DJ acknowledges on air.
- `rfl_commentary(text_type='contextual')` — generate DJ commentary
  (needs OpenAI/TTS configured on the RFL side; degrades gracefully if not).
- `rfl_context()` — current contextual awareness (time/weather/mood) RFL
  uses to steer theme choices.

## Mounting in an MCP client

Add an entry to your MCP client's server config (e.g. `.mcp.json`), then
restart the client session for the mount to take effect:

```json
"rfl-dj": {
  "command": "python",
  "args": ["-m", "rfl_mcp.server"],
  "cwd": "<path-to>/radio_free_luna",
  "env": {
    "PYTHONUNBUFFERED": "1",
    "RFL_URL": "http://localhost:8080"
  }
}
```

`RFL_URL` defaults to `localhost`; if RFL runs on another host, point this at
that host's LAN address instead.

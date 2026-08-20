# rfl-dj — Radio Free Luna MCP server

Wraps RFL's REST API as agent tools — a thin, per-app control surface over
the running RFL server.

## Config

```
RFL_URL   base URL of the RFL server (default http://localhost:8080)
```

RFL has no auth — do not add a Bearer token here; it would be dead weight.
Note that RFL binds `0.0.0.0`, so this is an open control surface over the LAN;
put it behind your own network controls if that matters for your deployment.

RFL is not an always-on service. Every tool degrades to a clear message
("RFL server is not running...") instead of raising when the server is down.

## Run

```
cd <path-to>/radio_free_luna
pip install -r rfl_mcp/requirements.txt
python -m rfl_mcp.server
```

Or use `launch.bat` to start the RFL server itself first (the MCP server is
a thin client over HTTP — it doesn't start RFL for you).

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

# MVP Streaming Cascade — 2026-05-06

**Goal:** Get Radio Free Luna actually streaming audio (eventually with AI DJ commentary) to a listener via the browser/VLC. **Path A** chosen: internal FastAPI `/stream.mp3` endpoint, no Icecast.

**Why a cascade:** Each phase touches a different file set and is end-to-end testable on its own. `/clear` between phases keeps the prompt cache hot for whatever comes next.

---

## Phase 0 — Environment & Cleanup `[complete]`

**Outcome:** Clean repo, real venv, real deps, scanned music library, `main.py` actually starts and serves `/health` on Windows.

**Phase 0 result (2026-05-06):**
- Repo cleaned: deleted `lib/`, all stub venvs, `launch_radio_free_luna.py`, `nul`, 22 stray root scripts/artifacts, `requirements_minimal.txt`. Moved 27 stale .md files to `docs/archive/`.
- `.venv/` (Python 3.11.4) created with rewritten `requirements.txt` (16 packages actually used). Pinned `httpx==0.27.2` to work around openai 1.3.5's removed-`proxies` kwarg incompatibility with httpx 0.28+. `pip check` clean.
- `.env`: `MUSIC_DIRECTORIES` updated to `Q:\Development\radio_free_luna\sample_audio`.
- `main.py` patched: emoji stripped from log lines; `sys.stdout`/`sys.stderr` reconfigured to UTF-8 (Windows cp1252 fix); `FileHandler('ai_dj.log')` opened with `encoding='utf-8'` (root cause of the actual logging tracebacks); `signal.SIGTERM` guarded behind `sys.platform != 'win32'`; fake `/api/streaming/*` keys removed from `/api` info dict.
- `setup.py` patched (drift discovered, not in original plan): emoji stripped, and `scan-music` now calls `init_database()` first — `FileMonitor` uses the module-level `db_manager` global which was `None` without it. **23 tracks** ingested into `data/radio_free_luna.db`.
- Smoke test: `python main.py` boots clean (no tracebacks), `/health` and `/status` both 200, file monitor active, stream_manager initialized in mock mode (Icecast2 not running, expected), TTS unavailable (TTS-WebUI not running, expected).
- **ffprobe NOT on PATH** (only a stray ffmpeg.exe shim in chocolatey bin from a prior install; no chocolatey ffmpeg package). Phase 0 doesn't need it (mutagen handles scan metadata; pydub imports in `src/streaming/*` are inside `try/except`). **Phase 1 will need it** — install via `choco install ffmpeg` or a static build before starting the broadcaster work.

**Files touched (none related to streaming):**
- DELETE: `lib/`, `.venv/`, `.venv_temp/`, `audio_test_env/`, `test_venv/`, `launch_radio_free_luna.py` (the all-mock launcher), `nul`
- DELETE: root-level loose test/debug scripts that duplicate `tests/`: `comprehensive_test_runner.py`, `create_visual_test_report.py`, `init_db_simple.py`, `minimal_test.py`, `mock_api_server.py`, `mock_icecast_server.py`, `quick_start.py`, `run_local.py`, `run_tests.py`, `simple_config.py`, `simple_web_test.py`, `start_radio_free_luna.py`, `test_*.py` at root, `radio_free_luna_test_report.html`, `web_test_results.json`
- ARCHIVE (move to `docs/archive/`): the ~30 stale planning/handoff `.md` files at project root (HANDOFF.md, PHASE_1_*, FINAL_*, DEPLOYMENT_*, AUDIO_STREAMING_REALITY_CHECK.md, BROWSER_TEST_RESULTS.md, REVIEW_AND_PLAN_SUMMARY.md, SESSION_NOTES_*, etc.) — keep README.md, CLAUDE.md, claude-md-python-venv.md
- KEEP & EDIT: `requirements.txt` (rewrite — drop bogus pins), `.env` (fix MUSIC_DIRECTORIES path), `main.py` (remove emoji from log lines, drop signal.SIGTERM on Windows, drop nonexistent `/api/streaming/*` advertisements from `/api` info)
- NEW: fresh `.venv/` via `python -m venv .venv`

**Steps:**
1. Inventory and delete the broken/stub directories and the all-mock launcher
2. Move stale .md files to `docs/archive/` (don't delete — they have history)
3. Move stray `test_*.py` from root into `tests/` (or delete if duplicated)
4. Rewrite `requirements.txt`: drop `sqlite3`, `python-tts-webui-client`, `python-icecast`; keep what's actually imported
5. Create `.venv` with Python 3.11; `pip install -r requirements.txt`; verify `ffprobe` is on PATH
6. Update `.env`: `MUSIC_DIRECTORIES=Q:\Development\radio_free_luna\sample_audio`; replace fake OPENAI_API_KEY placeholder with real key (Todd provides) or keep stub for now
7. Patch `main.py`: strip emoji from logger calls, guard `signal.signal(SIGTERM)` for Windows, remove the `/api/streaming/*` keys from the `/api` info endpoint (we'll re-add real ones in Phase 1)
8. Run `python setup.py scan-music --path "Q:\Development\radio_free_luna\sample_audio"` — verify `tracks` table populated
9. Smoke test: `python main.py` → `curl http://localhost:8080/health` returns healthy JSON

**Acceptance:** main.py boots clean, /health 200, DB has 22+ tracks.

⚠️ **NEXT:** Phase 1 — load `cascades/2026-05-06-mvp-streaming.md` and re-enter plan mode with the Phase 1 plan.

---

## Phase 1 — Music-only `/stream.mp3` broadcaster `[pending]`

**Outcome:** A listener pointing VLC or `<audio>` at `http://localhost:8080/stream.mp3` hears continuous music: tracks selected from the DB by theme, crossfaded, paced in real-time. No commentary yet.

**Files touched:**
- NEW: `src/streaming/broadcaster.py` — single-broadcaster, multi-listener queue model. Background task continuously pulls tracks from session, encodes to MP3 frames, ticks them out at real-time pace. Each connected listener gets a tail of the ring buffer.
- REWRITE: `src/streaming/__init__.py` — export `Broadcaster` instead of the dead Icecast modules
- DELETE: `src/streaming/icecast_client.py`, `audio_server.py`, `stream_manager.py` (replaced by broadcaster)
- KEEP: `src/streaming/audio_processor.py`, `src/streaming/crossfader.py` (broadcaster will use them; fix the exponential-fade bug in crossfader as part of this phase)
- EDIT: `main.py` — instantiate `Broadcaster` on startup, register `GET /stream.mp3`, register `POST /api/streaming/start` (theme, duration), `POST /api/streaming/stop`, `POST /api/streaming/skip`, `GET /api/streaming/status`
- EDIT: `src/web/static/index.html` + `js/main.js` — add `<audio>` player pointing at `/stream.mp3`, plus simple "start a session with theme X" controls

**Design notes for the broadcaster:**
- Use `ffmpeg` subprocess for MP3 encoding rather than pydub's whole-file export — pipe raw PCM in, get MP3 frames out, frame boundaries handled by ffmpeg
- Real-time pacing: encoder produces ~38 frames/sec at 44.1kHz; sleep `frame_duration` between writes
- Per-listener queue (asyncio.Queue, bounded ~10s) so a slow client doesn't block the broadcaster
- StreamingResponse yields from listener queue; if listener disconnects, drop their queue
- Track scheduling: when current track has ~6s left, start crossfading the next track in
- All session state lives in the Broadcaster — session_manager just produces the track list

**Acceptance:** open VLC → `http://localhost:8080/stream.mp3` → hear sample tracks playing back-to-back with crossfades, in real time, for at least 10 minutes without a stall.

⚠️ **NEXT:** Phase 2 — load `cascades/2026-05-06-mvp-streaming.md` and re-enter plan mode with the Phase 2 plan.

---

## Phase 2 — TTS commentary insertion `[pending]`

**Outcome:** Between (and occasionally over) tracks, the AI DJ speaks. Music ducks during commentary, returns to full volume after.

**Prerequisite check:** TTS-WebUI running locally at `TTS_WEBUI_URL`. If not, this phase falls back to OpenAI's TTS-1 via the openai SDK so it's still demoable.

**Files touched:**
- EDIT: `src/voice/tts_client.py` — verify it works against whatever TTS we use; add an OpenAI TTS fallback path (the OpenAI SDK has `audio.speech.create`, no aiohttp involved)
- EDIT: `src/streaming/broadcaster.py` — add commentary insertion: before next track, fetch CommentarySegment, synthesize via TTS, decode to PCM, ducked-mix or sequential-insert into the audio pipeline
- EDIT: `src/dj/session_manager.py` and/or `src/dj/commentary_generator.py` — minor: ensure commentary segments are passed through the session in a form the broadcaster can consume (text + voice settings)
- EDIT: web UI — show "Now: [track]" / "Now: [DJ commentary]" indicator from a small status endpoint

**Acceptance:** stream a 15-minute themed session in VLC → hear opening commentary → music → transition commentary between tracks → music → another transition. No dropouts, audio stays in sync.

✅ **CASCADE COMPLETE** when Phase 2 acceptance passes.

---

## Out of scope for this cascade (post-MVP)

- Real Icecast2 integration (Path B — could be added later if multi-listener scale matters)
- Weather/location context affecting selection (already implemented in code; just not exercised yet — verify it works once tracks have AI analysis)
- Full library AI analysis (currently track_analysis is empty; Phase 1 should pick tracks even without analysis, falling back to genre/title-based theme matching)
- Web UI polish beyond a working player + start/stop controls
- Authentication, rate limiting, multi-user concurrency tuning

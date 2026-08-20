# 2026-06-10 — Code Review Fixes (single-session push)

Source: full-codebase review (5-agent fan-out + verification), 2026-06-10.
Baseline tests: 25 passed / 28 failed / 46 errors (conftest async-fixture bug + Windows temp-db cleanup).

## Phase 1 — Core correctness (Claude, main session)
- [x] audio_processor.py: AudioSegment.from_file → asyncio.to_thread (event-loop blocking)
- [x] broadcaster.py: offload pydub CPU work; fix _CurrentTrack.duration (use emitted body length)
- [x] session_manager.py / commentary_generator.py / ai_analyzer.py: sync DB calls → to_thread
- [x] database.py: sqlite check_same_thread=False (sessions now used from worker threads)
- [x] crossfader.py: ducking sign bug fixed (apply_gain with negative dB); smart-recursion guard; logarithmic fade now a real dB-ramp curve (was identical to linear)
- [x] ai_analyzer: DB-backed cache (_load_analysis_from_db before OpenAI); analyze_and_store_track wired into main.py background worker (AUTO_ANALYZE_TRACKS, default true)
- [x] main.py / config.py: paths anchored to PROJECT_ROOT (log, static, sqlite); uvicorn now honors settings.host/port (was hardcoded 8080)
- [x] tts_client.py: investigated — not a real leak (session assigned to self, closed by shutdown). No change.
- [x] config: OPENAI_MODEL setting (default gpt-4o-mini) + .env updated from gpt-4

## Phase 2 — Parallel agents
- [x] Agent A: temporal.py season/back-to-school precedence fixed + verified; weather.py + lyrics_fetcher.py session timeouts
- [ ] Agent B: tests — IN PROGRESS (baseline 25P/28F/46E → 54P/14F/14E at last check)
- [x] Agent C: CLAUDE.md rewritten to reality; .env.example password fixed; config.py.backup removed; README drift fixed (agent committed this separately)

## Phase 3 — Feature: commentary in the live stream
- [x] Broadcaster takes optional tts_client; synthesizes commentary_before / opening segment, ducks under track intro via fixed mix_with_commentary; all failures degrade to music-only

## Bugs found DURING live testing (not in original review)
- [x] weather.py: session only created in __aenter__, never in normal use → live weather NEVER worked, always mock. Fixed (lazy session creation + close()).
- [x] commentary_generator.py:477: fallback opening called .get() on TemporalContext dataclass → crashed ALL fallback commentary. Fixed.
- [x] main.py: uvicorn hardcoded port 8080, ignored settings.

## Extensions added (user-approved "have at it" round)
- [x] ICY/SHOUTcast metadata on /stream.mp3 — verified live (StreamTitle parsed from raw socket)
- [x] Play history (play_count/last_played on air) + freshness-weighted anti-repeat sequencing
- [x] Now-playing panel in web UI (poll /api/streaming/status, progress bar)
- [x] Broadcast archiving (ARCHIVE_BROADCASTS → archives/<session>.mp3), verified by integration test
- [x] Fixed /api/test-voice + /api/commentary: UI sent query params, API wanted body — both buttons were dead; now embed=True + JSON bodies
- [x] docker-compose: TTS healthcheck gate, ICECAST_PASSWORD passthrough, absolute sqlite path

## Verification done
- [x] 24 new real tests (streaming audio, persistence, broadcaster+ffmpeg, sequencing)
- [x] Live smoke ×2: real broadcast at real-time pace, skip/stop, ICY metadata, play history row
- [x] Full suite green: 93 passed in 23s (baseline: 25P/28F/46E in 7min)
- [x] Committed: 993698d (code), 4b613f1 (docs)

STATUS: COMPLETE.
NOTE: User's OpenAI account returned 429 insufficient_quota during live test — commentary runs on fallback templates until billing is topped up. .env switched to OPENAI_MODEL=gpt-4o-mini.

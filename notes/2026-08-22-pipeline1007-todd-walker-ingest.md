# Pipeline #1007 follow-up — Todd Walker folder ingest (#3158)

**Assignment:** #3158 (PROCEED on plan-back #9694) · label playlist-bravery
**Date:** 2026-08-22 · **Nothing aired.**

## What this fixed
The `E:\Stacked Deck\Music\Todd Walker - music` folder (a pipeline #1006
weighting favorite) had **0 tracks in the RFL DB** — it was never indexed, so
those tracks could not be sequenced or aired. Now indexed + analyzed.

## Changes made
1. **.env** (gitignored) — appended the folder to the authoritative
   `MUSIC_DIRECTORIES` (line 247), so the file monitor watches it going forward:
   `...\sample_audio,E:\Stacked Deck\Music\Todd Walker - music`
2. **DB ingest** — 364 files on disk (277 .m4a + 87 .opus). Ingested **311
   unique tracks**: all 277 m4a + the 34 opus files with **no** m4a sibling.
   Skipped **53 redundant opus encodings** (same track already ingested as m4a).
   **0 failures.** All 311 have valid durations; 0 unknown titles, 1 unknown artist.
3. **Fallback analysis** — wrote 311 `track_analysis` rows (genre-theme fallback,
   identical to what AUTO_ANALYZE writes when OpenAI 429s — quota is currently
   exhausted). This matters: `session_manager` returns ONLY analyzed tracks when
   any analyzed tracks exist, so without analysis rows the new tracks would be
   silently excluded from sessions. Now **311/311 are session-eligible.**
4. **Seed metadata fix** — track id 479 had title/artist swapped. Corrected to:
   title `What's Up Danger (Movie Version Edit)`, artist `Blackway & Black Caviar`,
   album `Spider-Man: Into the Spider-Verse (Soundtrack)`.

Totals after: **3,508 tracks / 3,508 analyses** (was 3,197 / 3,197).
DB backup: `data/radio_free_luna.db.bak-20260822-tw-ingest`.

## ⚠️ Recommended follow-up (opus not first-class in the monitor)
`src/core/config.py:92` hardcodes `supported_formats` WITHOUT `.opus` (the .env
`SUPPORTED_FORMATS` key listing opus/wma is ignored). Also
`file_monitor.extract_metadata` probes non-ASCII MP4 atom keys (`\xa9alb` etc.)
which raise `ValueError` on Ogg/Vorbis (opus) tags, so opus files fail to store.
Consequences:
- The 34 opus-only tracks here were **backfilled manually** (safe extractor).
- Any **new** opus-only file dropped in this folder later will NOT be
  auto-ingested by the monitor.
- This is intentionally left as a scoped follow-up: making opus first-class means
  (a) add `.opus` to `supported_formats` and (b) fix `extract_metadata` to read
  lowercase Vorbis keys without probing non-ASCII atoms — and (c) add sibling/
  format-dedup so a full `initial_scan` with opus enabled doesn't create the 53
  duplicate encodings this ingest deliberately avoided.

## Scripts (scratchpad, not committed)
- `ingest_tw.py` — the ingest (backup + sibling-dedup + safe metadata).
- `analyze_tw.py` — the fallback-analysis backfill.

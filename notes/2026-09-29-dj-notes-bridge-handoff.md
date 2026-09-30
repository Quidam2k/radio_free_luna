# DJ notes store — handoff for RFL's DJ and the Pantheon DJ bridge (#6006 / #6008)

Todd (msg 38096, on the bike): the DJs "have nothing interesting to say" — they only
know title/artist/folder. This is the fix: a per-song store of short, SOURCED facts.

## What exists now

| Piece | Where |
|---|---|
| Store | `data/dj_notes.db` (SQLite, gitignored — local data). `songs` + `facts(kind, text, source_name, source_url, origin)` |
| Keyless enrichment | `src/notes/enrich.py` + `sources.py`: MusicBrainz (first release year, writers, cover-of, samples) + Wikidata → English Wikipedia song article (verbatim sentences by section) + artist intro. No model rewrites anything. |
| Batch | `scripts/build_dj_notes.py` — ride folders (Bike Music, faster, slower, Individual = 1,752 unique songs) by default, `--all` for the whole library. Throttled (MB 1.1 s, Wikimedia 0.5 s), resumable, ~6 s/song. Log: `logs/dj_notes_build.log`. |
| Web research | `scripts/import_research_notes.py` — imports Claude web-research JSON (`data/dj_notes_research/`), re-validated, stored `origin='research'` so the batch never overwrites it. First pass: 50 most-played / Bike Music songs → 100 facts on 35 songs. |
| Read: Python | `from src.notes.store import lookup` — stdlib only, never raises, `{found, facts:[{kind,text,source,url}], matched_by}` |
| Read: CLI | `python -m src.notes.lookup --artist A --title T --json` (always exit 0; ~80 ms) |
| Read: HTTP | `GET /api/track-notes?artist=&title=` (station must be up) |
| Read: MCP | `rfl_track_notes(artist, title)` in the rfl-toolkit server (`rfl_mcp/toolkit.py`, station-down OK) |
| RFL's own DJ | `src/dj/commentary_generator.py`: transition + song-story prompts now carry a SOURCED FACTS block ("state nothing beyond these"); with OpenAI down, the fallback transition/feature lines read a stored fact verbatim instead of a generic line. |

Matching: normalized artist+title (casefold, accents folded, "The" dropped, `&`→and,
feat./track numbers/`(Remastered…)`/`- 2001 Remaster` stripped, `05 - Artist - Title`
unwrapped). Falls back to title-only when exactly one stored song has that title
(covers "Various Artists" and mis-credited tags).

Fact kinds (in on-air order): summary, theme, history, recording, samples, covers,
reception, trivia, release, writers, cover_of, artist.

## Rules the store enforces
- A fact without `source_name` + `source_url` is never written.
- Wikipedia facts are verbatim sentences (only IPA/birth-date parentheticals are cut
  from artist intros); sentences that lean on the previous one ("She…", "However…")
  and long quoted spans (lyrics) are skipped. No lyric text is stored.
- MusicBrainz "first released" excludes compilations/live/DJ-mix releases; the album is
  named only when an original studio album has that same year, else year alone.
- Silence is fine: a song with no confident match gets `nomatch` and zero facts.

## Pantheon bridge integration (NOT done — Pantheon is another repo/owner)

`Q:\Pantheon\scripts\dj_bridge_push.py` today calls `musicbrainz_facts()` live (4 s
timeout, year + first release only). Suggested change, next to it:

```python
RFL_PY = r"Q:\Development\radio_free_luna\.venv\Scripts\python.exe"
RFL_ROOT = r"Q:\Development\radio_free_luna"

def rfl_notes(title, artist, timeout=2.0, max_facts=3):
    """Sourced DJ notes from Radio Free Luna. Fail-open: any problem -> []."""
    if not title:
        return []
    try:
        out = subprocess.run([RFL_PY, "-m", "src.notes.lookup", "--artist", artist or "",
                              "--title", title, "--json", "--limit", str(max_facts)],
                             cwd=RFL_ROOT, capture_output=True, text=True, timeout=timeout)
        return json.loads(out.stdout).get("facts", [])
    except Exception:
        return []
```

Then in `_fact_lines`, append `f"{label}: {f['text']} ({f['source']})"` for each note.
The bridge's existing prompt rule ("state nothing about the music beyond the facts
given here") already fits. Keep `musicbrainz_facts()` as a fallback or drop it:
the store's `release` fact covers the same ground without a live call. An alternative
to the subprocess is opening `data/dj_notes.db` read-only and importing
`src/notes/store.py` by path (stdlib only). Pantheon `docs/entry-points.md` should
get a row: "Sourced facts about a song for any DJ → RFL `src.notes.lookup` / MCP
`rfl_track_notes` (#6006)".

Direction #431: RFL itself (Chris-in-the-Morning voice) becomes the DJ over Audiplex,
so RFL's commentary generator is the first consumer. The bridge is second.

## Known gaps / next steps
- The batch had not finished at handoff. Rerun `scripts/build_dj_notes.py` to finish
  (it resumes where it left off). Then `--all` for the rest of the library.
- rfl-toolkit MCP server has no working interpreter: the `.venv` lacks `mcp`, and
  installing `mcp` there upgrades starlette/anyio/pydantic past FastAPI 0.104 (it broke
  the station; reverted). The server needs its own venv with `requirements.txt` +
  `rfl_mcp/requirements.txt` (`mcp<2` — 2.x renamed FastMCP).
- Web research: songs with no notes that play often are good candidates for another
  research pass (same JSON shape, `import_research_notes.py`).
- Library tag errors seen: "Ahha" (a-ha), "Barry White - You Sexy Thing" (likely Hot
  Chocolate), "Peter Gabriel - When You're Falling" (Afro Celt Sound System feat. PG).

# Lyrics, theme tags, trivia: plan + bake-off (#8201 / #8203 / #3982)
2026-10-18

## Lyrics (shipping today)
- Store: `lyrics` table in `data/dj_notes.db`, keyed by `store.song_key`. Both DJ
  paths (RFL `store.lookup`/`_facts_block`, Audiplex `song_context`) already read
  this file with the same key, so one row serves every cut in both libraries.
- Source: lrclib. The API throttles (429/503; `/api/get` 503s whenever its own
  upstream lookup fails), so the bulk fill uses lrclib's public SQLite dump
  (`H:/lrclib/`, 47.8 GB gz, 2026-10-12) via `src/notes/lyrics_dump_import.py`.
  `src/notes/lyrics_fill.py` (API, get-cached -> search) tops up new songs.
- On air: one short hook line (`pick_phrase`: most-repeated 4-12 word line).
  Full text only on demand: Audiplex MCP `dj_lyrics(track_id, verse)`,
  `python -m src.notes.lookup --lyrics --verse X`.

## Bake-off (#8203): Sonnet 5.5 vs Haiku 5.5, sourced-only, Opus 5.5 judge
30 songs from dj_notes.db (10 famous >=8 facts, 10 deep cut 3-7, 10 obscure 1-2).
Both models get the same prompt + SOURCE (stored Wikipedia/MusicBrainz facts) and
must not use memory. Opus labels each note SUPPORTED / UNSUPPORTED / CONTRADICTED.
Raw: `data/bakeoff_8203.json`, `logs/bakeoff_8203.txt`. Run cost $0.82.

| trivia | notes | unsupported | rate | famous / deep / obscure | $/song | full library (30,256) |
|---|---|---|---|---|---|---|
| Sonnet 5.5 | 130 | 10 | 7.7% | 6.0 / 2.0 / 20.0% | $0.00339 | $102.70 |
| Haiku 5.5 | 124 | 8 | 6.5% | 4.1 / 0.0 / 19.4% | $0.00022 | $6.71 |

| lyric tags (20 songs) | quality 1-5 | unsupported tags | $/song |
|---|---|---|---|
| Sonnet 5.5 | 4.65 | 2 | $0.00180 |
| Haiku 5.5 | 4.05 | 6 | $0.00012 |

Findings:
- Grounded, Haiku is no worse than Sonnet on trivia. The 10/8 gap (21 vs 5
  contradictions) came from answering out of memory; with sources in the prompt
  it disappears. Sonnet's misses are mostly small embellishments ("the quartet's
  saxophonist", "a fitting sound for a song named after a traveler").
- Both pad thin sources: ~20% unsupported on 1-2 fact songs. Fix: cap notes at
  the source fact count, and skip generation for songs with < 2 facts (read the
  verbatim fact instead).
- Judge noise is real: the same "first released in 1998" claim was SUPPORTED for
  one model and UNSUPPORTED for the other. Treat single-digit differences as a tie.
- Tags: Sonnet is clearly better (4.65 vs 4.05, a third of the unsupported tags).

Recommendation:
- Trivia rewrite: **Haiku 5.5**, grounded, Batches API. ~$3.40 for the whole
  library (half of $6.71), well under the $30 ask line.
- Theme tags: **Sonnet 5.5** if Jarvis okays ~$18 on Batches for ~20k lyric songs
  (over the $15 pre-approval); otherwise Haiku at ~$1.20 now and re-tag later.

## Trivia / history layer (plan, not built)
Coverage today: 2,242 of 30,256 library songs have >= 1 sourced song fact
(7.4%, 1 in 13). Only 3,281 songs were ever tried; 69% of those hit.

What it covers that lrclib + an LLM can't: lrclib only has words. Story,
writers, release, samples, covers and reception must come from a real source,
because an LLM answering from memory invents them (10/8 trial). So the model
never supplies facts; it only rephrases stored, cited sentences.

1. Sources, $0. `scripts/build_dj_notes.py --all` (MusicBrainz + Wikidata +
   Wikipedia, existing, resumable, ~1 req/s on MusicBrainz) over the remaining
   ~27k songs. Started 10/18 16:43; measured ~11 s/song (not the 24 h first
   guessed), so done ~10/22. Expected coverage 35-50%: the library is heavy on
   classical, jazz and compilations, which have no Wikipedia song article.
2. DJ-ready notes, ~$3.40. Haiku 5.5 rewrite of stored facts, rules as above,
   stored as facts with origin='llm_rewrite' next to the verbatim source fact.
   First pass done 10/18 (1,726 songs, 6,158 notes, $0.19); re-run over the
   new sources ~10/22-10/23.
3. Gaps after that: album-level facts (Wikipedia album articles) for the deep
   cuts, ~10/24.

## Result (10/18 evening)
- Lyrics: 16,007 of 30,256 songs (52.9%): 14,516 with words, 1,491
  instrumental. 14,221 have no match, ~5,266 of them classical / swing-era
  instrumentals (2,384 Mozart), so about 64% of vocal songs are covered.
- Theme tags: Sonnet 5.5 batches over 14,247 lyric songs: 14,232 tagged, 15
  parse failures, $12.48 actual (batch rate, not in the radio spend ledger).
  20-song spot check: all 20 fit the words (e.g. Talking Heads 'Road to
  Nowhere': journey without destination ... Mood: upbeat resignation). Songfacts-style sites are out (#4314, no bulk scraping).

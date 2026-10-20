# Theme sets, talk windows, off-air practice (#949 / #3995 / #4164)
2026-10-20. Assignment 8553 (plan 31671). Commits 8fc4908..4ec39c7 on clean-release-2026.

## Theme sets by meaning (#949)
- Table `theme_sets` in data/dj_notes.db: (theme, song_key) -> score 0-3, reason,
  source (lyrics_tags | title_only | todd), model. `src/notes/themes.py`.
- Halloween rubric (THEMES['halloween']) is spooky-for-fun. Songs about real grief,
  mourning, suicide, self-harm, addiction or illness score 0 even when they mention
  death ("a costume party, not a funeral").
- Pipeline (`scripts/theme_batch.py`):
  1. Haiku 5.5 batch over all 50,900 library songs.
  2. Sonnet 5.5 re-judges every Haiku score >= 1 (`--rescore-min 1`).
- Spot-check (Sonnet vs Haiku): 20/20 on near-miss score-0 rows, but only 14/30 of
  Haiku's fits held (68% overall). Haiku over-reads "devil", "ghost" and "zombie"
  in titles (Friend of the Devil, Fela's Zombie, Black Velvet Band). That is why
  Sonnet makes the final call.
- First Haiku run lost 72% of its answers: 5.5 models think by default and
  max_tokens 80 was all thinking. Fix: thinking off ("disabled" for Haiku; Sonnet
  only accepts "between_tools") and max_tokens 150.
- Result: 537 songs score >= 2 (124 score 3), 1,235 borderline (score 1).
- Spend: $7.22 on Batches, kept out of the radio's spend ledger.
- Staples landed: Thriller, Monster Mash, Werewolves of London, Season of the
  Witch, Somebody's Watching Me, Dead Man's Party, Sympathy for the Devil.
- Read paths: `python -m src.notes.themes halloween [--list|--score 1]`,
  GET /api/themes/halloween. planner.build_pool draws from a theme set whenever the
  theme names one, so a "halloween" session is built from the set.

## Talk windows (#3995)
- `src/mixdown/talk_windows.py`. Run it with C:/Python311 (.venv has no
  numpy/librosa).
- Intro, instrumental breaks and outro come from synced LRC gaps. Overlapping
  spans are merged. Each span has a loudness reading vs the track median
  (quiet = at or below it).
- Bad timing skips the track with a reason; vocals are never guessed. The
  reasons are no_synced, too_few_lines, duration_mismatch, stamps_past_end,
  non_monotonic and starts_late.
- Sample of 60 tracks: 41 ok, 137 windows (98 quiet). 19 skipped: 10 no lyrics,
  4 duration mismatch, 4 stamps past end, 1 starts late.
- Not yet wired into the broadcaster: the read API is `talk_windows(track_id)`.
- Full-library run not done: `--all`, which reads every file on H:.

## Off-air practice + ratings (#4164)
- `scripts/dj_practice.py` plans sets and writes their breaks with no broadcaster
  or audio. Lines are stored text-only (origin='practice') in data/dj_spoken.db.
- Persona voices only: the voice is resolved for a public audience, so a clone is
  never chosen.
- `--synthesize` runs only if TTS-WebUI :7860 is already up. It was down today, so
  the stockpile is text.
- Stockpile: 31 lines (14 transitions, 9 features, 8 station IDs). Morning ones are
  from 3 themes, evening ones from 4 Halloween sets. Practice spend was $0.27
  against the radio's own caps.
- On-air reuse: a transition is reused for the exact same track pair once it has
  audio. Thumbs-down lines are never reused.
- POST /api/feedback {rating: up|down, track_id?, line_id?}. The web Now Playing
  panel gets Song and DJ thumbs. The broadcaster status now carries the track id
  and line_id. Takes effect on the next RFL restart (not done by this worker).

## Open
- Borderline list (15) sent to Jarvis for Todd's call; apply answers as
  source='todd' rows via themes.save_rows.
- Synthesize the practice stockpile when TTS is free (`dj_practice.py --synthesize-only`).
- Wire talk_windows into the broadcaster's ducking (talk over the intro).

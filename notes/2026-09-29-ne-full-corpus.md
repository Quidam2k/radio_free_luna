# Northern Exposure full corpus (#6011, PROCEED #6012), 2026-09-29

## Summary for Todd
All 110 episodes are now in the corpus, taken from the DVD subtitles (exact dialogue,
not speech recognition). From them:
- **98 KBHR on-air segments** confirmed across 65 episodes, about 10,800 words:
  87 Chris, 4 Bernard, 3 other voices (e.g. an NPR host), 4 unclear. These are the
  segments to draw DJ-voice examples from.
- **Songs: the subtitles barely name music.** 40 music cues in 11 of 110 episodes,
  35 of them with lyric fragments. **Zero song titles** are stated, so every title is
  blank (no guessing). Only 4 cues can be tied to the monologue they followed. On-air
  segments also carry 12 verbatim DJ lines like "this one's for you, Leslie".
- **Optional next step (not done, needs your OK):** fill in titles from a public
  per-episode music list (e.g. a Northern Exposure fan wiki's song-by-episode pages),
  marked as coming from that source rather than the subtitles.

## What's on disk (data/, gitignored)
| File | Contents |
|---|---|
| `data/corpus/northern_exposure/SxxEyy.transcript.json` | 110 subtitle transcripts (source `srt:DVD`). Segments carry `italic` (off-screen voice: radio, phone, voiceover), `music`, `lyric` and `captions` when set |
| `data/corpus/northern_exposure/SxxEyy.asr.transcript.json` | the 13 #989 Whisper transcripts, renamed and kept |
| `data/corpus/ne_kbhr_segments.jsonl` | 293 heuristic candidates. Each has `confidence`/`why`, the heuristic `speaker` (self-id only), `song_mentions`, `followed_by_cue`, plus `review` {on_air, speaker_review, note} |
| `data/corpus/ne_songs.jsonl` | 40 music cues: `lyrics`, `captions`, `song_title` (always blank today), `followed_monologue_id` |
| `data/corpus/review/` | per-season candidate + review files (Sonnet grading pass) |
| `data/corpus/chris_in_the_morning.jsonl` | old #989 ASR extract, untouched |

Rebuild: `python scripts/ingest_ne_subs.py`, then `python scripts/build_ne_indexes.py`.
The second script re-merges the review files by id.

## Counts
| Season | Eps | Candidates | On air (reviewed) | Chris self-id | Bernard self-id | Music cues (eps) |
|---|---|---|---|---|---|---|
| S01 | 8 | 21 | 5 | 4 | 0 | 0 (0) |
| S02 | 7 | 15 | 4 | 4 | 0 | 36 (7) |
| S03 | 23 | 67 | 33 | 12 | 1 | 0 (0) |
| S04 | 25 | 65 | 17 | 9 | 2 | 4 (4) |
| S05 | 24 | 70 | 25 | 10 | 0 | 0 (0) |
| S06 | 23 | 55 | 14 | 8 | 0 | 0 (0) |
| **All** | **110** | **293** | **98** | 47 | 3 | 40 (11) |

Bernard's stint (review-confirmed): S03E21@759, S03E22@1941, S04E12@155, S04E18@171.
S04E22@0.9 is Chris and Bernard on air together, graded partial.

## How attribution works, and its limits
- The subtitles never name the speaker. Signals used: a cold open or closing position,
  KBHR/radio framing, a literary register, monologue shape, and (S1/S3/S5/S6 only)
  italics, which mark an off-screen voice. S2 and S4 subtitles have no italics.
- A heuristic `speaker` is set only on an on-air self-id ("this is Chris..."). The
  `review.speaker_review` field is the better label. Example: in S03E21 the heuristic
  says chris because of "Chris in the Morning", but it is Bernard sitting in.
- Review pass: 3 Sonnet agents read every candidate's text (a few also checked the
  surrounding transcript). I spot-checked 7 grades and all held up.
- **Recall is not measured.** On-air talk with no radio words, no cold open and no
  italics can be missed entirely. Closing-scene Chris monologues are often graded
  uncertain or partial (on air vs. voiceover).
- Music detection: "#"-wrapped lyric lines, a real "♪", or the "?"/"??" that a lossy
  re-encode left in place of "♪" (S02). Music captions like "[ Swing Jazz ]" also count.

## Code (commit 53ef4f9 + follow-up)
`src/corpus/transcripts.py` (flags, decode, watermark strip), `src/corpus/chris.py`
(offscreen bonus, italic split, radio-bulletin minima, speaker, song_mentions),
`src/corpus/songs.py`, `scripts/ingest_ne_subs.py`, `scripts/build_ne_indexes.py`
(+ review merge), `tests/test_corpus_ne_subs.py`. Corpus tests: 23/23 pass.

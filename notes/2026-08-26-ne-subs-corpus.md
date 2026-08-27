# Notes — Pipeline #989 Chris-in-the-Morning corpus (assignment #3378)
Worker team: worker-rfl-ne-subs--20260827-005953-a2ca
Status: PROCEED (Route A, commit clean-release-2026) approved via #3380. Code COMMITTED+PUSHED (13d9613).
Now: ASR running. Riders R1-R5 in the PROCEED note — honored in code.

## Progress (#989)
- Code written: src/corpus/{transcripts,chris}.py, scripts/{transcribe_ne,extract_chris}.py,
  data/corpus/README.md (force-tracked), tests/test_corpus_chris.py (13 tests pass).
- Committed 13d9613, pushed origin/clean-release-2026.
- Smoke test: transcribe S01E03 (faster-whisper small) running in background.
- NEXT: once smoke ok -> run all 13, then extract_chris --stats, then report counts+samples
  (incl 5 highest / 5 lowest confidence per R3), then stand by. Do NOT start OpenSubtitles path.

## Orientation findings (evidence)
- Local NE rips EXIST: 13 episodes, .avi (XviD 2007) under E:\Stacked Deck\Incoming\
  (9 loose + 4 in "=== Ready to be Burned ===\Northern Exposure\").
  Seasons: 1x03,1x08,2x01,2x06,3x10,3x20,4x02,4x11,4x12,4x23,4x24,505,6x02.
- NO subtitle tracks: ffprobe 1x03 => video(msmpeg4v3)+audio(mp3) only. No sidecar .srt anywhere.
  => subtitle-stream extraction is a dead end.
- Tooling: ffmpeg present; faster_whisper 1.2.1 + openai-whisper installed; CUDA on PATH.
  No OpenSubtitles key in .env. mkvextract/subliminal absent.
- Repo: scripts/ exists; data/corpus/ absent; persona = src/dj/commentary_generator.py; branch clean-release-2026.

## Proposed plan (Route A, local-first, source-agnostic)
1. scripts/transcribe_ne.py -> data/corpus/northern_exposure/<SxxEyy>.transcript.json (faster-whisper)
2. scripts/extract_chris.py -> data/corpus/chris_in_the_morning.jsonl (heuristic; consumes normalized transcript JSON)
3. data/corpus/README.md (feeds persona few-shot; deferred OpenSubtitles path + licensing; NO training)
4. Hermetic pytest on fixture transcript+SRT (no media/network)
5. Commit per RFL conventions; corpus gitignored.

## Open questions in plan-back
Q1 Route A (local ASR, 13 eps) vs B (OpenSubtitles full series, needs key). Rec: A.
Q2 Commit on clean-release-2026 or branch. Rec: current branch.

## On PROCEED
Execute the approved route. If A: build transcribe_ne.py + extract_chris.py + README + tests, run ASR, report counts.

## COMPLETE — resume worker e0f6 (2026-08-27) — Pipeline #989
Predecessor a2ca killed by full-stack bounce mid-ASR (8/13 done). Resumed, transcribed
the remaining 5 (S04E12, S04E23, S04E24, S05E05, S06E02), model=small, GPU yielded to
live STT per R1 (wall 3893s, mostly yield-wait). All 13 transcripts complete & full-length
(~2500-2700s each) in data/corpus/northern_exposure/ (1.2 MB, gitignored).

extract_chris.py --stats: 35 monologue candidates, 33,793 words, confidence 0.35–0.81
-> data/corpus/chris_in_the_morning.jsonl (192 KB, gitignored *.jsonl).
Hermetic test tests/test_corpus_chris.py: 13 passed (R5), no network/media.

Heuristic validated: top hits are genuine Chris cold-open radio monologues — 0.81 is the
"Season's greetings... This is Chris in the morning" Seoul Mates (S03E10) open. Low tail is
correctly-flagged episode-close dialogue / an ITV2 continuity announcer (S02E06), i.e. the
graded confidence R3 asked for — a later diarization/human pass can prune the low end.

Evidence (5 highest / 5 lowest confidence) reported to Jarvis via orch_report.
Tooling already committed 13d9613 (predecessor). Corpus data intentionally gitignored;
nothing new to commit but this note. OpenSubtitles path DEFERRED (R2); NO training (R4).

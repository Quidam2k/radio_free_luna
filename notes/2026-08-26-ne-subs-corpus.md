# Notes — Pipeline #989 Chris-in-the-Morning corpus (assignment #3378)
Worker team: worker-rfl-ne-subs--20260827-005953-a2ca
Status: PLAN-BACK submitted (orch_events #10495, low-crit). Awaiting PROCEED. NOT executing yet.

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

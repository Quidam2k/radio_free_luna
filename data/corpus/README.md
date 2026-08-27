# Chris-in-the-Morning corpus (Pipeline #989)

A small corpus of **Chris Stevens' KBHR on-air monologues** from *Northern
Exposure*, mined to give the Radio Free Luna DJ voice concrete exemplars of the
literary, contemplative, second-person radio register it is already asked to
imitate (`src/dj/commentary_generator.py` → `_build_opening_prompt`, which today
only *describes* "the gentle contemplative style of Chris in the Morning").

> **These are exemplars for the persona PROMPT — not training data.**
> Nothing here trains or fine-tunes a model. They are meant to be injected as
> few-shot *style anchors* ("here is the voice to emulate"). Whether to ever
> fine-tune on this material is a **separate decision** and is explicitly out of
> scope for #989.

## What's here

```
data/corpus/
  README.md                        # this file (the only tracked file in here)
  northern_exposure/
    <SxxEyy>.transcript.json        # normalized transcript, one per episode
  chris_in_the_morning.jsonl        # extracted monologue candidates
```

Everything except this README is **gitignored** (derived, and large). Re-runs
regenerate it from Todd's local rips.

### Normalized transcript (`<SxxEyy>.transcript.json`)

One source-agnostic shape, whatever produced it:

```json
{
  "episode": "S01E03",
  "title": "Soapy Sanderson",
  "source": "asr:faster-whisper:small",
  "source_path": "E:\\Stacked Deck\\Incoming\\Northern Exposure - 1x03 - ...avi",
  "model": "small",
  "runtime_sec": 512.4,
  "language": "en",
  "segments": [ {"start": 0.0, "end": 6.0, "text": "Good morning, Cicely..."} ]
}
```

### Monologue line (`chris_in_the_morning.jsonl`)

```json
{"episode":"S01E03","title":"Soapy Sanderson","start":0.0,"end":41.2,
 "duration":41.2,"text":"Good morning, Cicely...","confidence":0.86,
 "why":["cold-open (starts 0s)","radio markers: good morning, k-b-h-r",
        "literary cues: whitman","monologue shape (41s, 78 words, 0% short turns)"],
 "source":"asr:faster-whisper:small","method":"heuristic:position+radio+literary+shape"}
```

## How it was built (Route A — local, from Todd's own media)

The "extract soft subtitles from the rips" idea was a dead end: the 13 local
*Northern Exposure* episodes are 2007-era XviD **`.avi`** files with **no
subtitle stream** and **no sidecar `.srt`**. So we transcribe the audio locally
instead — no external service, no subtitle download, no licensing grey area.

```bash
# 1. transcribe the local rips (faster-whisper, 'small' by default — GPU courtesy)
python scripts/transcribe_ne.py            # add --model medium for a sharper pass
python scripts/transcribe_ne.py --list     # preview what would run

# 2. mine Chris monologues out of the transcripts (source-agnostic)
python scripts/extract_chris.py --stats
```

`transcribe_ne.py` yields the shared GPU to the live STT service (drops to
below-normal priority; waits while another process is busy — `--no-yield` to
disable), processes one episode at a time, and records the model + runtime per
episode.

## Attribution is heuristic — read the confidence, not the label

Neither ASR nor a plain SRT says *who* is speaking. `extract_chris.py` therefore
**scores** how much each block looks like a Chris monologue and ships that score
plus a plain-English `why`:

| feature   | signal                                                                    |
|-----------|---------------------------------------------------------------------------|
| position  | he bookends episodes — cold open (first ~180s) or closing sign-off        |
| radio     | KBHR framing: "good morning", "this is Chris", station id, dedications    |
| literary  | name-drops/quotes writers (Whitman, Jung, …); reflective, essayistic      |
| shape     | long continuous narration, not short conversational turns                 |

Treat lines as **candidates to curate**, never as ground truth. A later
[pyannote] diarization pass or a human editor can use `confidence` + `why` to
grade and prune. Raw transcripts are kept so extraction can be re-tuned without
re-transcribing.

## Feeding the persona prompt

The intended use in `commentary_generator.py` is to select a few of the
highest-confidence, hand-checked monologues and inject them as few-shot
exemplars into the existing prompt builders — e.g. an
`"# Voice to emulate (Chris Stevens, KBHR):"` block ahead of the task
instructions in `_build_opening_prompt` / `_build_transition_prompt`. That
sharpens the one-line persona description into a demonstrated register. Wiring
that in is a follow-up; #989 delivers the corpus + tooling.

## Deferred: OpenSubtitles full-series path

For coverage beyond the 13 local episodes, `src/corpus/transcripts.py` already
ships an SRT normalizer (`srt_to_segments`) so an OpenSubtitles fetch drops into
the *same* extractor with no rework. It is **deferred** because it needs
**Todd's own OpenSubtitles account/API key** (none is in `.env`), and any fetch
must record the per-file source + licence and must not scrape sites whose terms
forbid it. Fan-transcribed subtitles are user-generated; note their provenance.
Not started — a separate go/no-go.

[pyannote]: https://github.com/pyannote/pyannote-audio

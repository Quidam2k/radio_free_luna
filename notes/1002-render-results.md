# Mixdown Engine — Tiers 1+2 Build Results (#1002 / PROCEED #3149)

**Built & verified 2026-08-21.** Engine: `src/mixdown/` + `scripts/render_mix.py` (commit 1dd02ce).
Todd's amendment honored: **beatmatch-wherever-survivable**, one-long-track posture, failed seams
shown for ear-check rather than pre-surrendered.

## What shipped
- **analyzer** — tempo/beats/downbeats, usable region (silence trim), integrated LUFS; cached to `data/mix_cache/`.
- **planner** — beatmatch-default with half/double-time octave folding (so 152→95 BPM reads as
  152→191 and beatmatches); survivability gate `MAX_SEAM_STRETCH=0.30`; per-track LUFS level-match.
- **compiler** — sample-accurate equal-power blends, **rubberband** seam time-stretch, onset-xcorr
  downbeat nudge, LUFS normalize (−14) + −1 dBFS peak guard, ffmpeg MP3 (auto-picks a libmp3lame build),
  and **per-seam WAV export** for falsification.
- New dependency installed on this box: `pyrubberband` + **rubberband 4.0.0 CLI** (`C:\Users\Todd\bin`).

## The proof render (Halos & Horns source crate)
`data/mix_out/halos_render.mp3` — **76.1 min, 256 kbps, −14 LUFS, peak −1 dBFS**.
(Reference master `Halos_and_Horns.mp3` = 78.3 min, 160 kbps. Mine is ~2 min shorter: overlaps +
I dropped the `x 18` Jonny Cash alt-take, and rendered at higher bitrate.)

**20 transitions — 16 beatmatched, 4 fallback.** Plan: `data/mix_out/halos_render.plan.json`.
Seam clips (±4 s each) + metadata: `data/mix_out/seams/` (`seams.json`, `seam_NN_MATCH/FALLBACK.wav`).

### Ear-check priority (falsify with ears)
The 4 **FALLBACK** seams are where the engine judged a beatmatch would injure the material and
declined (31–33% stretch) — verify the long-blend still feels continuous:
- #05 Robbie Robertson → Ella Fitzgerald (31%)
- #13 Dido → INXS (31%)
- #18 Voice Of The Beehive → Rush (31%)
- #19 Rush → Dolly Parton (33%)

The **edge beatmatches** (big but attempted stretch — most likely to sound "off") to audition:
- #00 Richard Souther → Ben Harper (26.7%)
- #16 Rolling Stones → Kirsty MacColl (26.1%)
- #04 Mark Knopfler → Robbie Robertson (23.5%, via 152→198.8 fold)
- #14 INXS → Van Halen (20.6%, via 95.7→191.4 fold)

If any of those big-stretch beatmatches sound bad, lower `MAX_SEAM_STRETCH` in `planner.py` (e.g. 0.20)
and they become long-blends instead — one-line tuning knob.

## How to run
```
python scripts/render_mix.py "<folder-or-filelist>" --out data/mix_out/mix.mp3 \
    --exclude "Halos_and_Horns"        # skip a reference master in the same folder
# --limit N for a quick subset, --target-lufs, --no-seams, -v
```
Any transition is hand-editable in the `.plan.json` (kind / overlap_s / in_stretch / downbeat_align)
then re-render from the plan — that's the human-in-the-loop lever.

## Honest limits / next
- Beat/downbeat from librosa; a few tempos are octave-guessed (folding covers most). madmom/all-in-one
  would tighten hard cases — deferred (install pain, not needed for this result).
- Post-overlap tempo step exists on beatmatched seams but is bounded ≤30% by the gate (inaudible on
  small ones; the flagged big ones are the ear-check).
- **Man & Machine can't be rendered yet — the crate has 1 track on disk.** Populate it (or point the
  script at any populated crate/filelist) to render the actual target set.
- **Tier 3** (demucs instrumental beds + wire existing commentary/TTS voiced bridges — the #990
  crossover) awaits its own proceed; `voiced_bridge` is already a first-class TransitionKind.

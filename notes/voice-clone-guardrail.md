# Voice-clone guardrail (#6020, #6021): binding for all RFL voice work

Todd (msg 38130) and Karen's rider, 2026-09-29.

## The rule
- A clone of Chris's (the actor's) REAL voice is for **Todd's personal listening only**.
- It must never be usable on anything that could be publicly broadcast: a public RFL
  stream, published podcasts, posted clips, Substack audio, postcards, sent messages,
  or anything shared.
- The Chris clip and any cloned voice model stay **LOCAL**. Never upload either to a
  third-party or cloud TTS service.
- Public output paths always use a non-clone voice. When in doubt, fail closed.
- Studying the subtitle text and patter is unrestricted (docs/dj/chris_style_guide.md).

## Where RFL audio can reach other people today
| Path | Exposure | Clone allowed? |
|---|---|---|
| `GET /stream.mp3` (broadcaster → TTS) | `HOST=0.0.0.0:8080`: anyone on the LAN; the internet if a port-forward or tunnel is ever added | **No** |
| `archives/*.mp3` (`ARCHIVE_BROADCASTS`) | files that can be copied or posted | **No** |
| `mix_out/` (src/mixdown renders) | files that can be copied or posted | **No** |
| `POST /api/test-voice` | same server as the stream | **No** |
| Local playback on Todd's machine / the private Pantheon DJ bridge | Todd only | Yes, only while the station binds to loopback and TTS is local |

## How it is enforced
- `src/voice/voice_policy.py` holds the single check: `clone_allowed(output, host, tts_url)`
  and `resolve_voice(...)`. A clone passes only for an output in `PRIVATE_OUTPUTS`
  (`local_playback`, `private_bridge`), with `HOST` loopback and the TTS URL on
  localhost. Anything else, including unknown values, gets the fallback voice.
- `TTSWebUIClient.synthesize_speech(..., output="stream")` runs every voice through
  `resolve_voice`. The default output is the public stream, so an existing caller can
  never get a clone by accident.
- A voice counts as a clone if it starts with `clone:`, lives under `voice_private`, or is
  listed in `CLONE_VOICES`. Keep the clip and model in `data/voice_private/` (gitignored,
  since all of `data/` is).
- Tests: `tests/test_chris_style.py` (clone-gate section).

## When the clip arrives
Name the voice `clone:<name>`, keep its files in `data/voice_private/`, and add a private
output (for example local playback) that passes `output="local_playback"` explicitly.
Do not loosen `voice_policy` to make a public path work.

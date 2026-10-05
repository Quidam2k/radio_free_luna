# Voice-clone guardrail (#6020, #6021; tiers #6915/#6918): binding for all RFL voice work

Todd (msg 38130) and Karen's rider, 2026-09-29. Amended by Todd's ruling of 2026-10-05
(backstop upload 3116, #6915): "private but shared with friends" is NOT public.

## The rule
- A clone of a real person's voice (Chris, Feynman, any future clip) is for **Todd and
  the people he invites**. RFL is for him first, and later Plex-like: he invites specific
  friends into the room with him, even remotely. Those listeners are private.
- It must never reach the **public**: any stranger or unauthenticated listener, published
  podcasts, posted clips, Substack audio, postcards, sent messages, or any file that can be
  copied and shared (archives, mixdowns).
- The clips and any cloned voice model stay on **Todd's own machines** (this box, Athena).
  Never upload either to a third-party or cloud TTS service.
- Public output paths always use a non-clone voice. When in doubt, fail closed: anything not
  explicitly authenticated is public.
- Studying the subtitle text and patter is unrestricted (docs/dj/chris_style_guide.md).

## The three tiers
| Tier | Who | Clone? |
|---|---|---|
| private-local | Todd's machine: `local_playback`, the private Pantheon bridge, a loopback client | Yes |
| private-shared | an invited listener holding a token (`scripts/listener_token.py`), on the LAN or remote | Yes |
| public | everyone else, plus every file output | **No** |

## Where RFL audio goes
| Path | Tier | Clone allowed? |
|---|---|---|
| `GET /stream.mp3` | the tiers of ALL connected listeners; non-loopback listeners need a token (`src/core/listener_auth.py`) | Only if there is at least one listener, every one is private, and `ARCHIVE_BROADCASTS` is off. Rendered per voice line from the listeners connected at that moment. |
| `POST /api/private/speak` | the caller's own tier (audio comes back only to them) | Yes for loopback or a valid token |
| `scripts/private_speak.py` (this machine's speakers; `--out` only under `data/voice_private/`) | private-local | Yes |
| `archives/*.mp3`, `mix_out/` | public (files) | **No** |
| `POST /api/test-voice` | public (no audience given) | **No** |

## How it is enforced
- `src/voice/voice_policy.py` is the single check: `audience_tier(output, audience)`,
  `clone_allowed(output, tts_url, audience)`, `resolve_voice(...)`. A clone passes only when
  the audience tier is private AND the TTS host is loopback or listed in `PRIVATE_TTS_HOSTS`
  (Todd's own boxes, e.g. Athena's Chatterbox, approved by Jarvis on #6918). An empty or
  unknown audience, an unknown output, or an unparseable TTS URL is public.
- `TTSWebUIClient.synthesize_speech(..., output="stream", audience=None)` runs every voice
  through `resolve_voice`. The defaults are public, so an existing caller never gets a clone
  by accident. The broadcaster passes the connected listeners' tiers.
- `listener_auth` tags every request `private-local` (loopback) or `private-shared` (token);
  a non-loopback request with no valid token is refused outright (401), except `/health`.
- A voice counts as a clone if it starts with `clone:`, lives under `voice_private`, is
  registered in `data/voice_private/voices.json`, or is listed in `CLONE_VOICES`.
- Tests: `tests/test_chris_style.py` (clone-gate section), `tests/test_listener_auth.py`.

## Adding a clip
`python scripts/add_voice.py <name> --from <clip.wav>` copies it to
`data/voice_private/<name>.wav` (gitignored) and registers `clone:<name>`. Registered now:
`clone:feynman` (Todd, #6915: the host voice for now; another clip will follow).
Do not loosen `voice_policy` to make a public path work.

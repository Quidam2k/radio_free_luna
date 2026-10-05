"""Speak a line on THIS machine's speakers, in a clone voice if policy allows (#6918).

  python scripts/private_speak.py --voice clone:feynman "Nature isn't classical, dammit."
  python scripts/private_speak.py --voice clone:feynman --out data/voice_private/test.mp3 "..."

Output is local_playback (private-local tier), so a registered clone is allowed when the TTS
server is Todd's own. --out may only write under data/voice_private/ (gitignored), so a clone
render never lands somewhere shareable. Plays via ffplay (ffmpeg) without a window.
"""

import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.voice.tts_client import TTSWebUIClient  # noqa: E402
from src.voice.tts_config import TTSConfig  # noqa: E402
from src.voice.voice_policy import VOICE_DIR, clone_allowed, is_clone_voice  # noqa: E402


async def render(text: str, voice: str) -> bytes:
    config = TTSConfig(api_url=settings.tts_webui_url, voice_model=settings.tts_voice_model)
    async with TTSWebUIClient(config) as client:
        return await client.synthesize_speech(text, {"voice": voice} if voice else None,
                                              output="local_playback")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--voice", default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.voice and is_clone_voice(args.voice):
        ok, reason = clone_allowed("local_playback", settings.tts_webui_url)
        print(f"clone {'allowed' if ok else 'REFUSED'}: {reason}")
    if args.out and VOICE_DIR.resolve() not in args.out.resolve().parents:
        raise SystemExit(f"--out must be under {VOICE_DIR}")

    audio = asyncio.run(render(args.text, args.voice))
    if not audio:
        print(f"no audio: is the TTS server up at {settings.tts_webui_url}?")
        return 1
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(audio)
        print(f"wrote {args.out}")
        return 0
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False, dir=VOICE_DIR) as f:
        f.write(audio)
    try:
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", f.name],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        Path(f.name).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

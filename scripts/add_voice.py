"""Register a cloned voice from a wav clip, in one step (#6914 phase 4, #6918).

  python scripts/add_voice.py feynman --from "Q:/.../voice-sample.wav"   # copy in + register
  python scripts/add_voice.py feynman                                    # data/voice_private/feynman.wav already there
  python scripts/add_voice.py --list

The clip lives in data/voice_private/<name>.wav (gitignored, never uploaded anywhere) and is
registered as clone:<name> in data/voice_private/voices.json. voice_policy then lets that
voice reach PRIVATE audiences only (Todd's machine, invited token holders), and only when the
TTS server is Todd's own; every public path gets the fallback voice. See
notes/voice-clone-guardrail.md.
"""

import argparse
import json
import shutil
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.voice.voice_policy import REGISTRY, VOICE_DIR, registered_clones  # noqa: E402


def clip_info(path: Path) -> str:
    try:
        with wave.open(str(path)) as w:
            secs = w.getnframes() / float(w.getframerate())
            return f"{secs:.1f} s, {w.getframerate()} Hz, {w.getnchannels()} ch"
    except Exception as e:
        raise SystemExit(f"{path} is not a readable wav: {e}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("--from", dest="src", type=Path, help="wav to copy into data/voice_private/")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list or not args.name:
        for voice, path in sorted(registered_clones().items()):
            print(f"{voice}  {path}")
        return 0

    name = args.name.strip().lower()
    if not name.replace("_", "").replace("-", "").isalnum():
        raise SystemExit("name: letters, digits, - and _ only")
    dest = VOICE_DIR / f"{name}.wav"
    if args.src:
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.src, dest)
    if not dest.exists():
        raise SystemExit(f"no clip at {dest}; pass --from <wav>")
    info = clip_info(dest)

    voices = registered_clones()
    voices[f"clone:{name}"] = str(dest)
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(voices, indent=1, sort_keys=True), encoding="utf-8")
    print(f"registered clone:{name} -> {dest} ({info})")
    print("Private only: python scripts/private_speak.py --voice clone:" + name + ' "Hello."')
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""CLI read path for DJ notes (#6006) — stdlib only, fail-open, JSON out.

    python -m src.notes.lookup --artist "House of Pain" --title "Jump Around" --json

Exit code is always 0; an unknown song or a missing/locked database prints
{"found": false, "facts": []}. Callers in other repos (the Pantheon DJ bridge)
shell out to this with a short timeout instead of importing RFL.
"""

import argparse
import json
import sys

from src.notes.store import format_facts, lookup


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sourced DJ notes for one song")
    ap.add_argument("--artist", default="")
    ap.add_argument("--title", required=True)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--db", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        notes = lookup(args.artist, args.title, db_path=args.db, limit=args.limit)
    except Exception:  # belt and braces: the read path must never fail a caller
        notes = {"found": False, "artist": args.artist, "title": args.title, "facts": []}
    if args.json:
        sys.stdout.write(json.dumps(notes, ensure_ascii=False) + "\n")
    else:
        lines = format_facts(notes, max_facts=args.limit)
        sys.stdout.write("\n".join(lines) + "\n" if lines else "no notes\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

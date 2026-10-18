"""CLI read path for DJ notes (#6006) — stdlib only, fail-open, JSON out.

    python -m src.notes.lookup --artist "House of Pain" --title "Jump Around" --json
    python -m src.notes.lookup --artist "Fleetwood Mac" --title "Dreams" --lyrics --verse "thunder"

Exit code is always 0; an unknown song or a missing/locked database prints
{"found": false, "facts": []}. Callers in other repos (the Pantheon DJ bridge)
shell out to this with a short timeout instead of importing RFL.

Every result carries "lyric_phrase" (one short line, #8201). --lyrics is the
on-demand full-text path: it is for answering a question, never for speech.
"""

import argparse
import json
import sys

from src.notes.store import find_verse, format_facts, lookup, lyrics, pick_phrase


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sourced DJ notes for one song")
    ap.add_argument("--artist", default="")
    ap.add_argument("--title", required=True)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--db", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lyrics", action="store_true", help="print the full stored lyrics")
    ap.add_argument("--verse", default="", help="with --lyrics: only stanzas mentioning this")
    args = ap.parse_args(argv)
    if args.lyrics:
        return _lyrics(args)
    try:
        notes = lookup(args.artist, args.title, db_path=args.db, limit=args.limit)
        found = lyrics(args.artist, args.title, db_path=args.db)
        notes["lyric_phrase"] = pick_phrase(found.get("plain", "")) if found.get("found") else ""
    except Exception:  # belt and braces: the read path must never fail a caller
        notes = {"found": False, "artist": args.artist, "title": args.title, "facts": [],
                 "lyric_phrase": ""}
    if args.json:
        sys.stdout.write(json.dumps(notes, ensure_ascii=False) + "\n")
    else:
        lines = format_facts(notes, max_facts=args.limit)
        sys.stdout.write("\n".join(lines) + "\n" if lines else "no notes\n")
    return 0


def _lyrics(args) -> int:
    try:
        found = lyrics(args.artist, args.title, db_path=args.db)
    except Exception:
        found = {"found": False, "artist": args.artist, "title": args.title}
    if found.get("found") and args.verse:
        found["verses"] = find_verse(found["plain"], args.verse)
    if args.json:
        sys.stdout.write(json.dumps(found, ensure_ascii=False) + "\n")
    elif not found.get("found"):
        sys.stdout.write("no lyrics\n")
    else:
        text = "\n\n".join(found["verses"]) if args.verse else found["plain"]
        sys.stdout.write((text or "no matching verse") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

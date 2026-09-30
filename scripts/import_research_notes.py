"""Import web-researched DJ facts into data/dj_notes.db (#6006).

Input: JSON files of [{artist, title, facts: [{kind, text, source_name, source_url}]}]
as written by the Claude web-research pass. artist/title must be the library's own
tags (they are the lookup key). Facts are stored with origin='research', so the
MusicBrainz/Wikipedia batch never overwrites them.

Every fact is re-validated here, whatever the researcher promised: https source
URL, a named source, one short sentence, and a known kind. Rejects are printed.

    .venv/Scripts/python.exe scripts/import_research_notes.py data/dj_notes_research/*.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.notes.store import DEFAULT_DB, NotesStore  # noqa: E402

KINDS = {"history", "recording", "theme", "samples", "covers", "reception", "trivia"}
MAX_CHARS = 320


def problems(fact: dict) -> list:
    out = []
    if fact.get("kind") not in KINDS:
        out.append(f"kind {fact.get('kind')!r}")
    if not str(fact.get("source_url", "")).startswith("https://"):
        out.append("source_url not https")
    if not fact.get("source_name"):
        out.append("no source_name")
    text = str(fact.get("text", "")).strip()
    if not text or len(text) > MAX_CHARS:
        out.append(f"text length {len(text)}")
    if text.lower().startswith(("according to wikipedia", "per songfacts")):
        out.append("hedged/meta sentence")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    added = rejected = songs = 0
    store = None if args.dry_run else NotesStore(args.db)
    for path in args.files:
        for song in json.loads(Path(path).read_text(encoding="utf-8")):
            good = []
            for f in song.get("facts") or []:
                why = problems(f)
                if why:
                    rejected += 1
                    print(f"REJECT {song['artist']} - {song['title']}: {', '.join(why)}: {f.get('text', '')[:80]}")
                else:
                    good.append({k: f[k].strip() for k in ("kind", "text", "source_name", "source_url")})
            if good:
                songs += 1
                added += store.add_facts(song["artist"], song["title"], good) if store else len(good)
    if store:
        print("store:", store.stats())
        store.close()
    print(f"songs={songs} facts_added={added} rejected={rejected}{' (dry run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build sourced DJ notes for Todd's library, ride-mix folders first (#6006).

Reads track artist/title from the Audiplex library (read-only), dedupes by the
normalized song key, and enriches each song not already in data/dj_notes.db
via MusicBrainz + Wikipedia. Throttled (~1 req/s per host) and resumable: kill
it any time and rerun; finished songs are skipped.

    .venv/Scripts/python.exe scripts/build_dj_notes.py                 # ride folders
    .venv/Scripts/python.exe scripts/build_dj_notes.py --all           # whole music library
    .venv/Scripts/python.exe scripts/build_dj_notes.py --limit 20      # quick sample
    .venv/Scripts/python.exe scripts/build_dj_notes.py --stats
"""

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.notes.enrich import SongEnricher  # noqa: E402
from src.notes.store import DEFAULT_DB, NotesStore, song_key  # noqa: E402

AUDIPLEX_DB = Path(r"Q:\Development\audiplex\server\audiplex.db")
# Todd's ride-mix folders (album rows in Audiplex, matching Pantheon's TEMPO_FOLDERS).
RIDE_FOLDERS = ["Bike Music", "faster", "slower", "Individual"]

log = logging.getLogger("build_dj_notes")


def library_songs(db: Path, folders=None):
    """[(artist, title)] in folder order, deduped by song key."""
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
    sql = ("SELECT ar.name, t.title, al.title FROM tracks t"
           " JOIN albums al ON t.album_id = al.id"
           " LEFT JOIN artists ar ON t.artist_id = ar.id"
           " WHERE (t.content_kind IS NULL OR t.content_kind = 'music')")
    rows = conn.execute(sql).fetchall()
    conn.close()
    if folders:
        order = {f.casefold(): i for i, f in enumerate(folders)}
        rows = [r for r in rows if (r[2] or "").casefold() in order]
        rows.sort(key=lambda r: order[(r[2] or "").casefold()])
    seen, out = set(), []
    for artist, title, _ in rows:
        key = song_key(artist, title)
        if key.endswith("|") or key in seen:
            continue
        seen.add(key)
        out.append((artist or "", title or ""))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="whole music library, not just ride folders")
    ap.add_argument("--folders", help="comma-separated Audiplex album/folder titles")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--audiplex-db", default=str(AUDIPLEX_DB))
    ap.add_argument("--redo", action="store_true", help="re-enrich songs already stored")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(ROOT / "logs" / "dj_notes_build.log", encoding="utf-8")])

    store = NotesStore(args.db)
    if args.stats:
        print(store.stats())
        return 0

    folders = None if args.all else (args.folders.split(",") if args.folders else RIDE_FOLDERS)
    songs = library_songs(Path(args.audiplex_db), folders)
    todo = [s for s in songs if args.redo or not store.has(song_key(*s))]
    if args.limit:
        todo = todo[: args.limit]
    log.info("songs=%d already_done=%d todo=%d folders=%s db=%s",
             len(songs), len(songs) - len([s for s in songs if not store.has(song_key(*s))]),
             len(todo), folders or "ALL", args.db)

    enricher = SongEnricher()
    t0 = time.monotonic()
    counts = {"ok": 0, "nomatch": 0, "error": 0}
    for i, (artist, title) in enumerate(todo, 1):
        try:
            r = enricher.enrich(artist, title)
            store.save(artist, title, r["status"], r["facts"], detail=r["detail"], **r["ids"])
            counts[r["status"]] += 1
            log.info("[%d/%d] %s | %s - %s | %d facts", i, len(todo), r["status"],
                     artist, title, len(r["facts"]))
        except KeyboardInterrupt:
            raise
        except Exception as e:  # one bad song never stops the batch
            counts["error"] += 1
            store.save(artist, title, "error", detail=repr(e)[:300])
            log.warning("[%d/%d] error | %s - %s | %r", i, len(todo), artist, title, e)
        if i % 25 == 0:
            rate = i / max(1e-6, time.monotonic() - t0)
            log.info("progress %d/%d %s requests=%d eta=%.0f min", i, len(todo), counts,
                     enricher.client.requests, (len(todo) - i) / rate / 60)
    log.info("done %s store=%s", counts, store.stats())
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build sourced DJ notes for Todd's library, ride-mix folders first (#6006).

Reads track artist/title from the Audiplex library (read-only), dedupes by the
normalized song key, and enriches each song not already in data/dj_notes.db
via MusicBrainz + Wikipedia. Throttled (~1 req/s per host) and resumable: kill
it any time and rerun; finished songs are skipped.

    .venv/Scripts/python.exe scripts/build_dj_notes.py                 # ride folders
    .venv/Scripts/python.exe scripts/build_dj_notes.py --all           # whole music library
    .venv/Scripts/python.exe scripts/build_dj_notes.py --limit 20      # quick sample
    .venv/Scripts/python.exe scripts/build_dj_notes.py --played-since 2026-09-01 --redo-nomatch
    .venv/Scripts/python.exe scripts/build_dj_notes.py --mix-spec todd-ride-mix --buckets "arcane"
    .venv/Scripts/python.exe scripts/build_dj_notes.py --stats

Song sources (all read-only on Audiplex) combine: --played-since (play_stats),
--mix-spec (a dj_mix_specs row's folder / folder_match / bucket lanes) and
--buckets (Audiplex DJ buckets). With none of them the ride folders are used.
"""

import argparse
import json
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
AUDIPLEX_BUCKETS_DB = Path(r"Q:\Development\audiplex\data\dj\buckets.db")
_TRACK_SQL = ("SELECT t.id, ar.name, t.title, al.title, t.file_path FROM tracks t"
              " JOIN albums al ON t.album_id = al.id"
              " LEFT JOIN artists ar ON t.artist_id = ar.id"
              " WHERE (t.content_kind IS NULL OR t.content_kind = 'music')")

log = logging.getLogger("build_dj_notes")


def _ro(db: Path):
    return sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True, timeout=5)


def _dedupe(pairs):
    """[(artist, title)] deduped by song key, first occurrence wins."""
    seen, out = set(), []
    for artist, title in pairs:
        key = song_key(artist, title)
        if key.endswith("|") or key in seen:
            continue
        seen.add(key)
        out.append((artist or "", title or ""))
    return out


def _tracks(db: Path):
    conn = _ro(db)
    rows = conn.execute(_TRACK_SQL).fetchall()
    conn.close()
    return rows


def library_songs(db: Path, folders=None):
    """[(artist, title)] in folder order, deduped by song key."""
    rows = _tracks(db)
    if folders:
        order = {f.casefold(): i for i, f in enumerate(folders)}
        rows = [r for r in rows if (r[3] or "").casefold() in order]
        rows.sort(key=lambda r: order[(r[3] or "").casefold()])
    return _dedupe((r[1], r[2]) for r in rows)


def played_songs(db: Path, since: str):
    """Songs Todd started or finished in Audiplex since a date, most-played first."""
    conn = _ro(db)
    rows = conn.execute(
        "SELECT ar.name, t.title FROM play_stats p JOIN tracks t ON t.id = p.track_id"
        " LEFT JOIN artists ar ON t.artist_id = ar.id"
        " WHERE p.timestamp >= ? AND p.event IN ('start', 'complete')"
        " AND (t.content_kind IS NULL OR t.content_kind = 'music')"
        " GROUP BY t.id ORDER BY COUNT(*) DESC", (since,)).fetchall()
    conn.close()
    return _dedupe(rows)


def bucket_songs(db: Path, buckets_db: Path, names):
    """Songs in the named Audiplex DJ buckets (matched by track id, then path)."""
    if not names or not Path(buckets_db).exists():
        return []
    bconn = _ro(buckets_db)
    picks = []
    for name in names:
        picks += bconn.execute(
            "SELECT t.track_id, t.path FROM bucket_tracks t JOIN buckets b ON b.id = t.bucket_id"
            " WHERE b.name = ? COLLATE NOCASE ORDER BY t.position", (name.strip(),)).fetchall()
    bconn.close()
    rows = _tracks(db)
    by_id = {r[0]: r for r in rows}
    by_path = {(r[4] or "").casefold(): r for r in rows}
    hits = [by_id.get(tid) or by_path.get((path or "").casefold()) for tid, path in picks]
    return _dedupe((r[1], r[2]) for r in hits if r)


def _folder(path) -> str:
    return (path or "").replace("\\", "/").rstrip("/").casefold()


def mix_spec_songs(db: Path, spec: str, buckets_db: Path = AUDIPLEX_BUCKETS_DB):
    """Songs in a dj_mix_specs row's folder, folder_match and bucket lanes."""
    conn = _ro(db)
    row = conn.execute("SELECT sources_json FROM dj_mix_specs WHERE name = ?", (spec,)).fetchone()
    conn.close()
    if not row:
        raise SystemExit(f"no Audiplex mix spec named {spec!r}")
    rows = _tracks(db)
    out = []
    for src in json.loads(row[0]):
        kind, query = src.get("kind"), _folder(src.get("query"))
        if kind == "bucket":
            out += bucket_songs(db, buckets_db, [src.get("query") or ""])
            continue
        if kind == "folder" and not src.get("recursive", True):  # loose files only
            keep = lambda d: d == query  # noqa: E731
        elif kind == "folder":
            keep = lambda d: (d + "/").startswith(query + "/")  # noqa: E731
        elif kind == "folder_match":  # every folder whose path contains the query
            keep = lambda d: query in d  # noqa: E731
        else:
            log.warning("mix spec %s: skipping unsupported source kind %r", spec, kind)
            continue
        out += [(r[1], r[2]) for r in rows if keep(_folder(str(Path(r[4] or "").parent)))]
    return _dedupe(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="whole music library, not just ride folders")
    ap.add_argument("--folders", help="comma-separated Audiplex album/folder titles")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--audiplex-db", default=str(AUDIPLEX_DB))
    ap.add_argument("--played-since", help="songs played in Audiplex since YYYY-MM-DD")
    ap.add_argument("--mix-spec", help="an Audiplex dj_mix_specs name, e.g. todd-ride-mix")
    ap.add_argument("--buckets", help="comma-separated Audiplex DJ bucket names")
    ap.add_argument("--buckets-db", default=str(AUDIPLEX_BUCKETS_DB))
    ap.add_argument("--redo", action="store_true", help="re-enrich songs already stored")
    ap.add_argument("--redo-nomatch", action="store_true", help="retry songs stored as nomatch")
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

    adb, bdb = Path(args.audiplex_db), Path(args.buckets_db)
    picked = []
    if args.played_since:
        picked += played_songs(adb, args.played_since)
    if args.mix_spec:
        picked += mix_spec_songs(adb, args.mix_spec, bdb)
    if args.buckets:
        picked += bucket_songs(adb, bdb, args.buckets.split(","))
    if args.played_since or args.mix_spec or args.buckets:
        folders, songs = "selected sources", _dedupe(picked)
    else:
        folders = None if args.all else (args.folders.split(",") if args.folders else RIDE_FOLDERS)
        songs = library_songs(adb, folders)

    def owed(song):
        key = song_key(*song)
        return args.redo or not store.has(key) or (args.redo_nomatch and store.status(key) == "nomatch")

    todo = [s for s in songs if owed(s)]
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

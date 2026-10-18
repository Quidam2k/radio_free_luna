"""Import local LRCLIB dump lyrics for Audiplex songs (#8201).

LRCLIB's sanctioned bulk path is kinder than 30k API calls. No network.
Run: python -m src.notes.lyrics_dump_import --dump H:/lrclib/lrclib.sqlite3
"""

import argparse
import logging
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from src.notes.lyrics_fill import (
    AUDIPLEX_DB, PROGRESS, flush, load_songs, query_artist, report,
)
from src.notes.store import DEFAULT_DB, NotesStore, norm_artist, norm_title

_LRC_STAMP = re.compile(r"^\s*(?:\[[0-9:.]+\]\s*)+", re.M)


def match_key(artist: str, title: str) -> tuple[str, str]:
    # Same folding on both sides: drops 'feat.', a leading 'The', '(Remastered)'.
    return norm_artist(artist), norm_title(title, artist)

MatchKey = tuple[str, str]
Candidate = tuple[int, float | None, int]
Lyric = tuple[str | None, str | None, int | None]


def scan_tracks(db: sqlite3.Connection,
                wanted: dict[MatchKey, list[dict]]) -> dict[MatchKey, list[Candidate]]:
    candidates: dict[MatchKey, list[Candidate]] = {}
    started, scanned = time.monotonic(), 0
    with closing(db.cursor()) as cursor:
        cursor.arraysize = 50000
        cursor.execute(
            "SELECT id, artist_name, name, duration, last_lyrics_id "
            "FROM tracks WHERE last_lyrics_id IS NOT NULL"
        )
        while batch := cursor.fetchmany(50000):
            for track_id, artist, title, duration, lyrics_id in batch:
                key = match_key(artist, title)
                if key in wanted:
                    candidates.setdefault(key, []).append(
                        (track_id, duration, lyrics_id))
                scanned += 1
                if scanned % 1_000_000 == 0:
                    elapsed = max(time.monotonic() - started, 0.001)
                    logging.info("Scanned %d tracks; %.0f rows/s",
                                 scanned, scanned / elapsed)
    logging.info("Scan complete: %d tracks; %d candidates", scanned,
                 sum(map(len, candidates.values())))
    return candidates


def load_lyrics(db: sqlite3.Connection,
                candidates: dict[MatchKey, list[Candidate]]) -> dict[int, Lyric]:
    ids = sorted({c[2] for group in candidates.values() for c in group})
    lyrics: dict[int, Lyric] = {}
    with closing(db.cursor()) as cursor:
        for offset in range(0, len(ids), 500):
            chunk = ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            cursor.execute(
                "SELECT id, plain_lyrics, synced_lyrics, instrumental "
                f"FROM lyrics WHERE id IN ({placeholders})", chunk)
            for lyrics_id, plain, synced, instrumental in cursor:
                if not (plain or "").strip() and synced:  # synced-only row
                    plain = _LRC_STAMP.sub("", synced).strip()
                lyrics[lyrics_id] = (plain, synced, instrumental)
    logging.info("Loaded %d lyrics records", len(lyrics))
    return lyrics


def candidate_rank(candidate: Candidate, duration: float,
                   lyrics: dict[int, Lyric]) -> tuple[bool, bool, float, int]:
    _, seconds, lyrics_id = candidate
    plain, _, instrumental = lyrics[lyrics_id]
    usable = bool((plain or "").strip()) or bool(instrumental)
    diff = abs(float(seconds) - duration) if seconds is not None else float("inf")
    if diff != diff:  # Unknown duration cannot be an exact match.
        diff = float("inf")
    return not usable, diff > max(3, 0.02 * duration), diff, -lyrics_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--audiplex-db", type=Path, default=AUDIPLEX_DB)
    parser.add_argument("--notes-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    library = load_songs(args.audiplex_db)
    p = args.dump.resolve()
    with closing(sqlite3.connect(
            f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)) as dump:
        with NotesStore(args.notes_db) as notes:
            wanted: dict[MatchKey, list[dict]] = {}
            statuses: dict[str, str | None] = {}
            for song in library:
                status = notes.lyrics_status(song["key"])
                statuses[song["key"]] = status
                if not args.overwrite and status in ("ok", "instrumental"):
                    continue
                artist = query_artist(song["artist"])
                key = match_key(artist, song["title"])
                if key[0] and key[1]:
                    wanted.setdefault(key, []).append(song)
            total = sum(map(len, wanted.values()))
            logging.info("Importing %d of %d library songs", total, len(library))
            PROGRESS.parent.mkdir(parents=True, exist_ok=True)
            counts = dict.fromkeys(
                ("ok", "instrumental", "nomatch", "error", "unchanged"), 0)
            buffer: list[dict] = []
            started, done, interrupted = time.monotonic(), 0, False
            try:
                candidates = scan_tracks(dump, wanted) if wanted else {}
                lyrics = load_lyrics(dump, candidates)
                for key, songs in wanted.items():
                    options = [c for c in candidates.get(key, []) if c[2] in lyrics]
                    for song in songs:
                        duration = float(song["duration"] or 0)
                        best = min(
                            options,
                            key=lambda c: candidate_rank(c, duration, lyrics),
                            default=None,
                        )
                        row = None
                        if best is not None:
                            plain, synced, instrumental = lyrics[best[2]]
                            loose = candidate_rank(best, duration, lyrics)[1]
                            status = ("instrumental" if instrumental else
                                      "ok" if (plain or "").strip() else "nomatch")
                            row = dict(
                                song, status=status, plain=plain, synced=synced,
                                instrumental=bool(instrumental), lrclib_id=best[0],
                                source="lrclib-dump",
                                detail="dump-loose" if loose else "dump-exact",
                            )
                        elif statuses[song["key"]] is None:
                            row = dict(
                                song, status="nomatch", plain=None, synced=None,
                                instrumental=False, lrclib_id=None,
                                source="lrclib-dump", detail="dump-none",
                            )
                        if row is not None:
                            buffer.append(row)
                            counts[row["status"]] += 1
                            logging.debug("%s %s / %s", row["detail"],
                                          ascii(song["artist"]), ascii(song["title"]))
                        else:
                            counts["unchanged"] += 1
                        done += 1
                        if len(buffer) >= 500:
                            flush(notes, buffer)
                        if done % 5000 == 0:
                            report(done, total, counts, started)
            except KeyboardInterrupt:
                interrupted = True
                logging.info("Interrupted; flushing %d buffered songs", len(buffer))
            finally:
                flush(notes, buffer)
                report(done, total, counts, started)
                cached = dict(notes.conn.execute(
                    "SELECT status, count(*) FROM lyrics GROUP BY status"))
                library_ok = sum(notes.lyrics_status(s["key"]) == "ok" for s in library)
                logging.info(
                    "Final counts=%s cache_counts=%s library_songs=%d ok=%.2f%%",
                    counts, cached, len(library),
                    100 * library_ok / len(library) if library else 0.0)
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())

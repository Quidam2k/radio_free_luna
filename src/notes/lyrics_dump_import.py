"""Import local LRCLIB dump lyrics for Audiplex songs (#8201).

LRCLIB's sanctioned bulk path is kinder than 30k API calls. No network.
Run: python -m src.notes.lyrics_dump_import --dump H:/lrclib/lrclib.sqlite3
"""

import argparse
import logging
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from src.notes.lyrics_fill import (
    AUDIPLEX_DB, PROGRESS, flush, load_library, query_artist, report,
)
from src.notes.store import DEFAULT_DB, NotesStore, norm_artist, norm_title

_LRC_STAMP = re.compile(r"^\s*(?:\[[0-9:.]+\]\s*)+", re.M)


def match_key(artist: str, title: str) -> tuple[str, str]:
    # Same folding on both sides: drops 'feat.', a leading 'The', '(Remastered)'.
    return norm_artist(artist), norm_title(title, artist)

MatchKey = tuple[str, str]
Candidate = tuple[int, float | None, int]
Lyric = tuple[str | None, str | None, int | None]


# #3982: gate for the long H: scan and RFL as a song source.
def tick_delta(now_ms: int, then_ms: int) -> int:
    """Milliseconds between two 32-bit tick counts, correct across the 49.7-day wrap."""
    return (now_ms - then_ms) & 0xFFFFFFFF


def input_idle_seconds() -> float:
    """Seconds since Todd last touched the keyboard or mouse (Windows); inf elsewhere."""
    if os.name != "nt":
        return float("inf")
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return float("inf")
    kernel32 = ctypes.windll.kernel32
    kernel32.GetTickCount.restype = ctypes.c_uint32  # default c_int goes negative at 24.9 days
    return tick_delta(kernel32.GetTickCount(), info.dwTime) / 1000.0


def make_gate(min_idle: float):
    """Return a callable that blocks while Todd is at the machine (idle < min_idle s)."""
    def gate() -> None:
        paused = False
        while min_idle and input_idle_seconds() < min_idle:
            if not paused:
                logging.info("Todd is active; scan paused")
                paused = True
            time.sleep(30)
        if paused:
            logging.info("Scan resumed")
    return gate


def scan_tracks(db: sqlite3.Connection,
                wanted: dict[MatchKey, list[dict]],
                gate=lambda: None) -> dict[MatchKey, list[Candidate]]:
    candidates: dict[MatchKey, list[Candidate]] = {}
    started, scanned = time.monotonic(), 0
    with closing(db.cursor()) as cursor:
        cursor.arraysize = 50000
        cursor.execute(
            "SELECT id, artist_name, name, duration, last_lyrics_id "
            "FROM tracks WHERE last_lyrics_id IS NOT NULL"
        )
        while True:
            gate()  # the scan reads a USB HDD for an hour; yield when Todd is at the box
            batch = cursor.fetchmany(50000)
            if not batch:
                break
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
                candidates: dict[MatchKey, list[Candidate]],
                gate=lambda: None) -> dict[int, Lyric]:
    ids = sorted({c[2] for group in candidates.values() for c in group})
    lyrics: dict[int, Lyric] = {}
    with closing(db.cursor()) as cursor:
        for offset in range(0, len(ids), 500):
            gate()
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
    parser.add_argument("--rfl-db", type=Path, default=None,
                        help="also cover RFL's own library, e.g. data/radio_free_luna.db")
    parser.add_argument("--notes-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--min-idle", type=float, default=0,
                        help="pause the scan while keyboard/mouse idle < N seconds (0 = never)")
    parser.add_argument("--below-normal", action="store_true",
                        help="run at below-normal CPU priority (Windows)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if args.below_normal and os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    library = load_library(args.audiplex_db, args.rfl_db)  # #3982
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
                gate = make_gate(args.min_idle)
                candidates = scan_tracks(dump, wanted, gate) if wanted else {}
                lyrics = load_lyrics(dump, candidates, gate)
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

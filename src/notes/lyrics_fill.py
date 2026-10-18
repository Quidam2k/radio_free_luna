"""Fill RFL's lyrics cache from LRCLIB for Audiplex music (#8201/#3982).

Completed results are resumable; only the main thread accesses SQLite.
"""
import argparse
import concurrent.futures as futures
import email.utils
import json
import logging
import random
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from src.notes import store
from src.notes.store import NotesStore, song_key, clean_song_title, is_generic_artist, _fold

AUDIPLEX_DB = Path("Q:/Development/audiplex/server/audiplex.db")
PROGRESS = Path("Q:/Development/radio_free_luna/logs/lyrics_fill_progress.jsonl")
HEADERS = {
    "User-Agent": "RadioFreeLuna/1.0 (personal home DJ; lyrics cache; https://github.com/toddcwalker)",
    "Accept": "application/json",
}


def load_songs(path: Path) -> list[dict]:
    groups = {}
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        for artist, title, album, duration in db.execute("""
            SELECT ar.name, t.title, al.title, t.duration_seconds
            FROM tracks t JOIN artists ar ON ar.id=t.artist_id
            JOIN albums al ON al.id=t.album_id WHERE t.content_kind='music'
        """):
            if not clean_song_title(title, artist):
                continue
            key = song_key(artist, title)
            song, counts = groups.setdefault(key, (
                dict(key=key, artist=artist, title=title, album=album), {}))
            seconds = max(0, round(float(duration or 0)))
            counts[seconds] = counts.get(seconds, 0) + 1
    finally:
        db.close()
    songs, skipped = [], 0
    for key in sorted(groups):
        song, counts = groups[key]
        if is_generic_artist(song["artist"]):
            skipped += 1
            continue
        song["duration"] = float(max(counts, key=lambda d: (counts[d], d)))
        songs.append(song)
    logging.info("Loaded %d songs; skipped %d generic-artist keys", len(songs), skipped)
    return songs


# '01.21. Sigue Sigue Sputnik', '(01)Tom Waits', '02 (Martinique) Kali'. A bare leading
# number needs a leading zero, so '50 Cent' and '4 Non Blondes' survive.
_ARTIST_JUNK = re.compile(
    r"^\s*(?:\(\d{1,3}\)\s*|\d{1,3}(?:\.\d{1,3})*\.\s+|0\d\s+)(?:\([^)]*\)\s*)?")


def query_artist(artist: str) -> str:
    return _ARTIST_JUNK.sub("", artist or "").strip()


def best_candidate(candidates: list, duration: float, artist: str = "",
                   title: str = "") -> dict | None:
    if not isinstance(candidates, list):
        raise ValueError("LRCLIB search response is not a list")
    if not duration:
        return next((c for c in candidates
                     if c.get("plainLyrics") or c.get("syncedLyrics")), None)
    matches = []
    for candidate in candidates:
        if candidate.get("duration") is None:
            continue
        diff = abs(float(candidate["duration"]) - duration)
        if diff <= max(3, 0.02 * duration):
            usable = bool(candidate.get("plainLyrics") or
                          candidate.get("instrumental") is True)
            matches.append((not usable, diff, candidate))
    if matches:
        return min(matches, key=lambda c: c[:2])[2]
    # Same song, other cut (12" mix, live): words match even when the length doesn't.
    want = (_fold(artist), _fold(title))
    return next((c for c in candidates if c.get("plainLyrics") and want[0] and want ==
                 (_fold(c.get("artistName", "")), _fold(c.get("trackName", "")))), None)


class Client:
    def __init__(self, rps: float):
        self.interval = 1 / rps
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.next_start = 0.0

    def get(self, endpoint: str, params: dict) -> object:
        url = "https://lrclib.net/api/" + endpoint + "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            with self.lock:
                if self.stop.wait(max(0, self.next_start - time.monotonic())):
                    raise RuntimeError("Interrupted")
                self.next_start = time.monotonic() + self.interval
            try:
                request = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(request, timeout=20) as response:
                    return json.load(response)
            except (urllib.error.URLError, TimeoutError) as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    if exc.code != 429 and not 500 <= exc.code < 600:
                        raise
                if attempt == 4:
                    raise
                delay = float(2 ** (attempt + 1))
                if isinstance(exc, urllib.error.HTTPError):
                    retry_after = exc.headers.get("Retry-After")
                    exc.close()
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            try:
                                until = email.utils.parsedate_to_datetime(retry_after)
                                delay = max(delay, until.timestamp() - time.time())
                            except (ValueError, TypeError, OverflowError):
                                pass
                if self.stop.wait(delay + random.random()):
                    raise RuntimeError("Interrupted")
        raise RuntimeError("Retries exhausted")

    def fetch(self, song: dict) -> dict:
        row = dict(song, status="nomatch", plain=None, synced=None,
                   instrumental=False, lrclib_id=None, source="lrclib", detail=None)
        try:
            artist = query_artist(song["artist"])
            title = clean_song_title(song["title"], artist)
            params = dict(track_name=title, **({"artist_name": artist} if artist else {}))
            # get-cached never triggers lrclib's upstream lookup; plain /api/get does,
            # and answers 503 whenever that lookup fails (30 s of retries per miss).
            method, hit = "get-cached", None
            if artist and song["duration"]:
                try:
                    hit = self.get("get-cached", dict(params, album_name=song["album"] or "",
                                                      duration=int(song["duration"])))
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        raise
                    exc.close()
            if hit is None:
                method = "search"
                hit = best_candidate(self.get("search", params), song["duration"],
                                     artist if artist else "", title)
            row["detail"] = method
            if hit is not None:
                instrumental = hit.get("instrumental") is True
                plain = hit.get("plainLyrics")
                row.update(status="instrumental" if instrumental else
                           "ok" if plain else "nomatch",
                           plain=plain, synced=hit.get("syncedLyrics"),
                           instrumental=instrumental, lrclib_id=hit.get("id"))
        except Exception as exc:
            row.update(status="error", detail=repr(exc)[:300])
        return row


def flush(notes: NotesStore, buffer: list[dict]) -> None:
    if not buffer:
        return
    for attempt in range(11):
        try:
            notes.save_lyrics_batch(buffer)
            buffer.clear()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 10:
                raise
            time.sleep(1)


def report(done: int, total: int, counts: dict, started: float) -> None:
    elapsed = max(time.monotonic() - started, 0.001)
    data = dict(ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                done=done, total=total, **counts,
                ok_pct=round(100 * counts["ok"] / done, 2) if done else 0.0,
                rate_per_min=round(60 * done / elapsed, 2))
    line = json.dumps(data, ensure_ascii=True)
    logging.info("%s", line)
    with PROGRESS.open("a", encoding="utf-8") as output:
        output.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audiplex-db", type=Path, default=AUDIPLEX_DB)
    parser.add_argument("--notes-db", type=Path, default=store.DEFAULT_DB)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--report-every", type=int, default=1000)
    parser.add_argument("--rps", type=float, default=4.0)
    args = parser.parse_args()
    if (args.workers < 1 or args.report_every < 1 or
            not 0 < args.rps < float("inf") or
            (args.limit is not None and args.limit < 0)):
        parser.error("workers, report-every and rps must be positive; limit must be nonnegative")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    notes = NotesStore(args.notes_db)
    songs = []
    for song in load_songs(args.audiplex_db):
        status = notes.lyrics_status(song["key"])
        if status is None or (status == "error" and args.retry_errors):
            songs.append(song)
    random.Random(8201).shuffle(songs)  # progress reports stay representative
    if args.limit is not None:
        songs = songs[:args.limit]
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    total, done, index = len(songs), 0, 0
    counts = dict.fromkeys(("ok", "instrumental", "nomatch", "error"), 0)
    buffer, pending = [], set()
    client = Client(args.rps)
    pool = futures.ThreadPoolExecutor(max_workers=args.workers)
    started, interrupted = time.monotonic(), False
    logging.info("Fetching %d songs with %d workers at %.2f rps",
                 total, args.workers, args.rps)
    try:
        while pending or index < total:
            while index < total and len(pending) < args.workers * 4:
                pending.add(pool.submit(client.fetch, songs[index]))
                index += 1
            finished, pending = futures.wait(pending, return_when=futures.FIRST_COMPLETED)
            for future in finished:
                row = future.result()
                buffer.append(row)
                done += 1
                counts[row["status"]] += 1
                if len(buffer) >= 50:
                    flush(notes, buffer)
                if done % 100 == 0:
                    logging.info("done=%d/%d ok=%d instrumental=%d nomatch=%d error=%d",
                                 done, total, *(counts[s] for s in counts))
                if done % args.report_every == 0:
                    report(done, total, counts, started)
    except KeyboardInterrupt:
        interrupted = True
        logging.info("Interrupted; flushing %d buffered songs", len(buffer))
    finally:
        client.stop.set()
        for future in pending:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        flush(notes, buffer)
        report(done, total, counts, started)
        notes.close()
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())

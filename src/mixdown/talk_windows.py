"""Find DJ talk windows from trustworthy synced lyrics and measure loudness.

The parser returns a list subclass that preserves whether the first timestamps
of successive source lines went backwards. Keep that list intact when passing
it to check_timing(); sorting alone would discard this evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


_ROOT = Path(__file__).resolve().parents[2]
_LIBRARY_DB = _ROOT / "data" / "radio_free_luna.db"
_LYRICS_DB = _ROOT / "data" / "dj_notes.db"
_OUTPUT_DB = _ROOT / "data" / "talk_windows.db"
_SUMMARY_PATH = _ROOT / "logs" / "talk_windows_last.json"

_STAMP_RE = re.compile(r"\[(\d+):([0-5]\d)(?:\.(\d+))?\]")
_OFFSET_RE = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]", re.IGNORECASE)
_METADATA_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_-]*:[^\]]*\]")

Stamp = tuple[float, str]
Span = tuple[float, float, str]
Window = dict[str, Any]


class _LRCStamps(list[Stamp]):
    def __init__(
        self, values: Iterable[Stamp] = (), *, non_monotonic: bool = False
    ) -> None:
        super().__init__(values)
        self.non_monotonic = non_monotonic


def parse_lrc(text: str | None) -> list[Stamp]:
    """Parse LRC, applying the last offset tag to all timestamps.

    Multiple timestamps on one line produce multiple entries. Only the first
    timestamp on each source line participates in the raw-order check.
    Empty timestamped lines remain present as instrumental markers.
    """
    if not text:
        return _LRCStamps()

    offsets = _OFFSET_RE.findall(text)
    offset = int(offsets[-1]) / 1000.0 if offsets else 0.0
    entries: list[Stamp] = []
    previous_first: float | None = None
    non_monotonic = False

    for raw_line in text.splitlines():
        matches = list(_STAMP_RE.finditer(raw_line))
        if not matches:
            continue

        times: list[float] = []
        for match in matches:
            minutes, seconds, fraction = match.groups()
            timestamp = int(minutes) * 60.0 + int(seconds)
            if fraction:
                timestamp += float("0." + fraction)
            times.append(timestamp + offset)

        first = times[0]
        if previous_first is not None and previous_first - first > 1.0:
            non_monotonic = True
        previous_first = first

        line = _STAMP_RE.sub("", raw_line)
        line = _METADATA_RE.sub("", line).strip()
        entries.extend((timestamp, line) for timestamp in times)

    entries.sort(key=lambda entry: entry[0])
    return _LRCStamps(entries, non_monotonic=non_monotonic)


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def check_timing(
    stamps: Sequence[Stamp],
    lyric_duration: float | None,
    track_duration: float | None,
) -> str | None:
    """Return a timing rejection reason, or None when timing is trustworthy."""
    if not stamps:
        return "no_synced"
    if sum(bool(line.strip()) for _, line in stamps) < 4:
        return "too_few_lines"

    source_duration = _positive_float(lyric_duration)
    duration = _positive_float(track_duration)
    ordered = sorted(stamps, key=lambda entry: entry[0])

    if (
        source_duration is not None
        and duration is not None
        and abs(source_duration - duration) > 4.0
    ):
        return "duration_mismatch"

    if duration is not None and ordered[-1][0] > duration - 1.0:
        return "stamps_past_end"

    raw_backwards = getattr(stamps, "non_monotonic", None)
    if raw_backwards is None:
        # Plain lists supplied by callers are treated as being in raw order.
        raw_backwards = any(
            earlier[0] - later[0] > 1.0
            for earlier, later in zip(stamps, stamps[1:])
        )
    if raw_backwards:
        return "non_monotonic"

    known_duration = duration if duration is not None else source_duration
    if known_duration is not None and ordered[0][0] > 0.6 * known_duration:
        return "starts_late"

    return None


def _normalise_spans(spans: Iterable[Span], duration: float) -> list[Span]:
    """Clamp, drop spans under 4 s, and merge overlaps (a blank-line marker and a
    long line gap often describe the same break)."""
    merged: list[Span] = []
    clamped = sorted(
        (min(duration, max(0.0, float(s))), min(duration, max(0.0, float(e))), k)
        for s, e, k in spans
    )
    for start, end, kind in clamped:
        if end - start < 4.0:
            continue
        if merged and start <= merged[-1][1]:
            previous = merged[-1]
            merged[-1] = (previous[0], max(previous[1], end), previous[2])
        else:
            merged.append((start, end, kind))
    return merged


def vocal_free_spans(stamps: Sequence[Stamp], duration: float) -> list[Span]:
    """Derive spans solely from sung timestamps and explicit blank markers."""
    known_duration = _positive_float(duration)
    if known_duration is None:
        return []

    ordered = sorted(stamps, key=lambda entry: entry[0])
    sung = [(timestamp, line) for timestamp, line in ordered if line.strip()]
    if not sung:
        return []

    candidates: list[Span] = [(0.0, sung[0][0] - 0.5, "intro")]

    next_sung: float | None = None
    for timestamp, line in reversed(ordered):
        if line.strip():
            next_sung = timestamp
        elif next_sung is not None:
            candidates.append((timestamp + 0.5, next_sung - 0.5, "break"))

    for current, following in zip(sung, sung[1:]):
        if following[0] - current[0] > 14.0:
            candidates.append((current[0] + 6.0, following[0] - 0.5, "break"))

    candidates.append((sung[-1][0] + 6.0, known_duration - 1.0, "outro"))
    return _normalise_spans(candidates, known_duration)


def _instrumental_spans(duration: float) -> list[Span]:
    length = min(20.0, duration * 0.25)
    return _normalise_spans(
        [
            (0.0, length, "instrumental"),
            (duration - length, duration - 1.0, "instrumental"),
        ],
        duration,
    )


def _value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _is_instrumental(lyric_row: Any) -> bool:
    return (
        _value(lyric_row, "status") == "instrumental"
        or _value(lyric_row, "instrumental") in (1, "1")
    )


def _analyze_audio(file_path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    """Load audio and return frame centers, 0.5-second RMS, and duration."""
    import librosa

    sample_rate = 11025
    audio, loaded_rate = librosa.load(
        str(file_path), sr=sample_rate, mono=True
    )
    audio = np.asarray(audio)
    if (
        audio.ndim != 1
        or audio.size == 0
        or not np.all(np.isfinite(audio))
        or loaded_rate != sample_rate
    ):
        raise ValueError("Invalid decoded audio")

    # Rounded boundaries alternate between 5512 and 5513 samples, maintaining
    # 0.5-second frames at this odd sample rate. Include the final partial frame.
    count = int(math.ceil(audio.size / (sample_rate * 0.5)))
    starts = np.rint(np.arange(count, dtype=np.float64) * sample_rate * 0.5)
    starts = starts.astype(np.int64)
    ends = np.append(starts[1:], audio.size)
    lengths = ends - starts

    squares = np.square(audio, dtype=np.float64)
    sums = np.add.reduceat(squares, starts)
    rms = np.sqrt(sums / lengths)
    centers = (starts + ends) / (2.0 * sample_rate)
    return centers, rms, audio.size / sample_rate


def _measure_spans(
    spans: Sequence[Span], centers: np.ndarray, rms: np.ndarray
) -> list[Window]:
    baseline = max(float(np.median(rms)), 1e-9)
    windows: list[Window] = []

    for start, end, kind in spans:
        selected = rms[(centers >= start) & (centers < end)]
        if selected.size == 0:
            # Relevant only when supplied track duration exceeds decoded audio.
            continue
        mean_rms = max(float(np.mean(selected)), 1e-9)
        rel_db = 20.0 * math.log10(mean_rms / baseline)
        windows.append(
            {
                "start": float(start),
                "end": float(end),
                "kind": kind,
                "rel_db": rel_db,
                "quiet": int(rel_db <= 0.0),
            }
        )
    return windows


def scan_track(
    track_row: Any, lyric_row: Any
) -> tuple[str, str | None, list[Window]]:
    """Scan one mapping or sqlite3.Row without writing to any database."""
    raw_path = _value(track_row, "file_path")
    if not raw_path:
        return "skipped", "file_missing", []
    try:
        file_path = Path(raw_path)
        if not file_path.is_absolute():
            file_path = _ROOT / file_path
        if not file_path.is_file():
            return "skipped", "file_missing", []
    except (OSError, TypeError, ValueError):
        return "skipped", "file_missing", []

    if lyric_row is None or _value(lyric_row, "status") in ("nomatch", "error"):
        return "skipped", "no_lyrics", []

    instrumental = _is_instrumental(lyric_row)
    synced = _value(lyric_row, "synced")
    if not instrumental and not synced:
        return "skipped", "no_synced", []

    duration = _positive_float(_value(track_row, "duration"))
    lyric_duration = _positive_float(_value(lyric_row, "duration"))
    stamps = parse_lrc(synced) if not instrumental else _LRCStamps()

    if not instrumental:
        reason = check_timing(stamps, lyric_duration, duration)
        if reason is not None:
            return "skipped", reason, []

    try:
        centers, rms, audio_duration = _analyze_audio(file_path)
    except Exception:
        return "skipped", "audio_error", []

    if duration is None:
        duration = audio_duration
        if not instrumental:
            reason = check_timing(stamps, lyric_duration, duration)
            if reason is not None:
                return "skipped", reason, []

    spans = (
        _instrumental_spans(duration)
        if instrumental
        else vocal_free_spans(stamps, duration)
    )
    return "ok", None, _measure_spans(spans, centers, rms)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def talk_windows(
    track_id: int, quiet_only: bool = True, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    """Read saved windows, returning [] if the database is unavailable."""
    try:
        path = Path(db_path) if db_path is not None else _OUTPUT_DB
        if not path.is_file():
            return []
        query = (
            "SELECT start, end, kind, rel_db FROM talk_windows "
            "WHERE track_id = ?"
        )
        if quiet_only:
            query += " AND quiet = 1"
        query += " ORDER BY start"
        with closing(_connect_readonly(path)) as connection:
            return [dict(row) for row in connection.execute(query, (track_id,))]
    except (sqlite3.Error, OSError, TypeError, ValueError):
        return []


def _create_schema(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS talk_windows (
                track_id INTEGER,
                start REAL,
                end REAL,
                kind TEXT,
                rel_db REAL,
                quiet INTEGER,
                PRIMARY KEY(track_id, start)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS talk_scan (
                track_id INTEGER PRIMARY KEY,
                status TEXT,
                reason TEXT,
                n_windows INTEGER,
                scanned_at TEXT
            )
            """
        )


def _load_tracks() -> list[sqlite3.Row]:
    with closing(_connect_readonly(_LIBRARY_DB)) as connection:
        return connection.execute(
            "SELECT id, file_path, artist, title, duration FROM tracks ORDER BY id"
        ).fetchall()


def _load_lyrics() -> dict[str, sqlite3.Row]:
    if not _LYRICS_DB.is_file():
        return {}
    with closing(_connect_readonly(_LYRICS_DB)) as connection:
        rows = connection.execute(
            "SELECT song_key, status, synced, duration, instrumental FROM lyrics"
        ).fetchall()
    return {row["song_key"]: row for row in rows}


def _select_tracks(
    args: argparse.Namespace,
    tracks: Sequence[sqlite3.Row],
    lyrics: dict[str, sqlite3.Row],
    keys: dict[int, str],
    already_scanned: set[int],
) -> list[sqlite3.Row]:
    if args.track_id is not None:
        requested = set(args.track_id)
        missing = requested - {row["id"] for row in tracks}
        if missing:
            raise ValueError("Unknown track IDs: " + ", ".join(map(str, sorted(missing))))
        candidates = [row for row in tracks if row["id"] in requested]
    else:
        candidates = list(tracks)

    if not args.rescan:
        candidates = [
            row for row in candidates if row["id"] not in already_scanned
        ]

    if args.sample is None:
        return candidates

    eligible: list[sqlite3.Row] = []
    without_lyrics: list[sqlite3.Row] = []
    for row in candidates:
        lyric = lyrics.get(keys[row["id"]])
        if lyric is None:
            without_lyrics.append(row)
        elif _value(lyric, "synced") or _is_instrumental(lyric):
            eligible.append(row)

    rng = random.Random(args.seed)
    selected = rng.sample(eligible, min(args.sample, len(eligible)))
    selected.extend(
        rng.sample(without_lyrics, min(args.sample // 5, len(without_lyrics)))
    )
    rng.shuffle(selected)
    return selected


def _run(args: argparse.Namespace) -> int:
    # Use the notes store's canonical normalization rather than duplicating it.
    from src.notes.store import song_key

    tracks = _load_tracks()
    lyrics = _load_lyrics()
    keys = {
        row["id"]: song_key(row["artist"], row["title"])
        for row in tracks
    }

    _OUTPUT_DB.parent.mkdir(parents=True, exist_ok=True)
    scanned = 0
    ok = 0
    total_windows = 0
    quiet_windows = 0
    skipped: Counter[str] = Counter()

    with closing(sqlite3.connect(_OUTPUT_DB)) as connection:
        _create_schema(connection)
        already_scanned = {
            row[0] for row in connection.execute("SELECT track_id FROM talk_scan")
        }
        selected = _select_tracks(
            args, tracks, lyrics, keys, already_scanned
        )

        for track in selected:
            track_id = track["id"]
            with connection:
                # Delete before analysis; the transaction atomically replaces
                # the windows and their scan record once analysis completes.
                connection.execute(
                    "DELETE FROM talk_windows WHERE track_id = ?", (track_id,)
                )
                status, reason, windows = scan_track(
                    track, lyrics.get(keys[track_id])
                )
                connection.executemany(
                    """
                    INSERT INTO talk_windows
                        (track_id, start, end, kind, rel_db, quiet)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            track_id,
                            window["start"],
                            window["end"],
                            window["kind"],
                            window["rel_db"],
                            window["quiet"],
                        )
                        for window in windows
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO talk_scan
                        (track_id, status, reason, n_windows, scanned_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(track_id) DO UPDATE SET
                        status = excluded.status,
                        reason = excluded.reason,
                        n_windows = excluded.n_windows,
                        scanned_at = excluded.scanned_at
                    """,
                    (
                        track_id,
                        status,
                        reason,
                        len(windows),
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    ),
                )

            scanned += 1
            track_quiet = sum(window["quiet"] for window in windows)
            total_windows += len(windows)
            quiet_windows += track_quiet
            if status == "ok":
                ok += 1
            else:
                skipped[reason or "unknown"] += 1

            name = ascii(f"{track['artist']} - {track['title']}")
            print(
                f"track_id={track_id} {name} status={status} "
                f"reason={reason or '-'} windows={len(windows)} "
                f"quiet={track_quiet}",
                flush=True,
            )

    summary = {
        "tracks_scanned": scanned,
        "ok": ok,
        "skipped": sum(skipped.values()),
        "skipped_by_reason": dict(sorted(skipped.items())),
        "windows_total": total_windows,
        "quiet_windows": quiet_windows,
        "mean_windows_per_ok_track": total_windows / ok if ok else 0.0,
    }
    _SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=True, indent=2) + "\n",
        encoding="ascii",
    )
    print("summary: " + json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="Sample N eligible tracks and N//5 tracks without lyrics rows.",
    )
    selection.add_argument("--all", action="store_true", help="Scan all tracks.")
    selection.add_argument(
        "--track-id",
        type=int,
        action="append",
        metavar="ID",
        help="Scan a specific track; repeat for multiple tracks.",
    )
    parser.add_argument("--seed", type=int, default=3995)
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Include tracks already recorded in talk_scan.",
    )
    args = parser.parse_args(argv)
    if args.sample is not None and args.sample < 0:
        parser.error("--sample must be nonnegative")

    try:
        return _run(args)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print("error: " + ascii(str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


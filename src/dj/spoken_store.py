"""
Archive spoken DJ text and audio for reuse without rendering TTS again (#4154).

Uses data/dj_spoken.db (DJ_SPOKEN_DB) and data/spoken (DJ_SPOKEN_DIR).
Clone-voice audio is stored in the private subdirectory. Errors propagate to callers.

Off-air practice (#4164) stockpiles lines with origin='practice'; a practice line may be
text-only (audio_path NULL) until TTS is free, and only lines with audio are reused on
air. Listeners rate lines (rating +1/-1) and tracks (track_ratings); a thumbs-down line
is never reused.
"""

import hashlib
import os
import sqlite3
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "dj_spoken.db"
DEFAULT_AUDIO_DIR = PROJECT_ROOT / "data" / "spoken"
_LOCK = threading.Lock()


def _connect(db_path=None):
    path = Path(db_path if db_path is not None
                else os.environ.get("DJ_SPOKEN_DB", DEFAULT_DB_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with _LOCK:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS spoken_lines (
                    id INTEGER PRIMARY KEY, created REAL, kind TEXT,
                    prev_track_id INTEGER NULL, track_id INTEGER NULL,
                    voice TEXT, daypart TEXT, private INTEGER, text TEXT,
                    audio_path TEXT, aired_count INTEGER DEFAULT 0,
                    last_aired REAL NULL
                )
            """)
            columns = {r[1] for r in conn.execute("PRAGMA table_info(spoken_lines)")}
            for name, decl in (("origin", "TEXT DEFAULT 'air'"), ("rating", "INTEGER NULL"),
                               ("rated_at", "REAL NULL")):
                if name not in columns:  # stores created before #4164
                    conn.execute(f"ALTER TABLE spoken_lines ADD COLUMN {name} {decl}")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS track_ratings (
                    id INTEGER PRIMARY KEY, created REAL, track_id INTEGER,
                    rating INTEGER, line_id INTEGER NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS spoken_lines_key
                ON spoken_lines(kind, prev_track_id, track_id, voice, daypart)
            """)
            conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def save(text, audio: bytes | None, kind, voice, daypart, track_id=None,
         prev_track_id=None, private=False, ext="mp3", db_path=None,
         audio_dir=None, origin="air") -> dict:
    """Archive a line. audio=None stores it text-only (#4164), deduped on kind/voice/text
    and track pair."""
    if audio is None:
        return _save_text(text, kind, voice, daypart, track_id, prev_track_id,
                          private, origin, db_path)
    directory = Path(audio_dir if audio_dir is not None
                     else os.environ.get("DJ_SPOKEN_DIR", DEFAULT_AUDIO_DIR))
    if private:
        directory /= "private"
    digest = hashlib.sha1(f"{kind}|{voice}|{text}".encode("utf-8")).hexdigest()[:16]
    path = (directory / f"{digest}.{ext}").resolve()
    conn = _connect(db_path)
    try:
        with _LOCK, conn:
            conn.execute("BEGIN IMMEDIATE")
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(audio)
            row = conn.execute(
                "SELECT * FROM spoken_lines WHERE audio_path = ?", (str(path),)
            ).fetchone()
            if row is None:
                cursor = conn.execute("""
                    INSERT INTO spoken_lines (created, kind, prev_track_id,
                        track_id, voice, daypart, private, text, audio_path, origin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (time.time(), kind, prev_track_id, track_id, voice,
                      daypart, int(bool(private)), text, str(path), origin))
                row = conn.execute(
                    "SELECT * FROM spoken_lines WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
            return dict(row)
    finally:
        conn.close()


def _save_text(text, kind, voice, daypart, track_id, prev_track_id, private, origin,
               db_path) -> dict:
    conn = _connect(db_path)
    try:
        with _LOCK, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""
                SELECT * FROM spoken_lines WHERE kind IS ? AND voice IS ? AND text IS ?
                    AND track_id IS ? AND prev_track_id IS ?
            """, (kind, voice, text, track_id, prev_track_id)).fetchone()
            if row is None:
                cursor = conn.execute("""
                    INSERT INTO spoken_lines (created, kind, prev_track_id, track_id,
                        voice, daypart, private, text, audio_path, origin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """, (time.time(), kind, prev_track_id, track_id, voice, daypart,
                      int(bool(private)), text, origin))
                row = conn.execute("SELECT * FROM spoken_lines WHERE id = ?",
                                   (cursor.lastrowid,)).fetchone()
            return dict(row)
    finally:
        conn.close()


def text_only(limit=50, db_path=None) -> list[dict]:
    """Practice lines still waiting for TTS, oldest first."""
    conn = _connect(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM spoken_lines WHERE audio_path IS NULL AND (rating IS NULL OR rating >= 0)"
            " ORDER BY created, id LIMIT ?", (limit,))]
    finally:
        conn.close()


def set_audio(row_id, audio: bytes, ext="mp3", db_path=None, audio_dir=None) -> dict:
    """Give a text-only line its audio (same file naming as save)."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM spoken_lines WHERE id = ?", (row_id,)).fetchone()
        if row is None:
            raise KeyError(row_id)
        directory = Path(audio_dir if audio_dir is not None
                         else os.environ.get("DJ_SPOKEN_DIR", DEFAULT_AUDIO_DIR))
        if row["private"]:
            directory /= "private"
        digest = hashlib.sha1(f"{row['kind']}|{row['voice']}|{row['text']}".encode("utf-8")).hexdigest()[:16]
        path = (directory / f"{digest}.{ext}").resolve()
        with _LOCK, conn:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(audio)
            conn.execute("UPDATE spoken_lines SET audio_path = ? WHERE id = ?", (str(path), row_id))
        return dict(row, audio_path=str(path))
    finally:
        conn.close()


def rate(rating: int, line_id=None, track_id=None, now=None, db_path=None) -> None:
    """Thumbs up (+1) / down (-1) on a spoken line, a track, or both (#4164)."""
    if rating not in (-1, 1) or (line_id is None and track_id is None):
        raise ValueError("rating must be +1/-1 on a line or a track")
    now = time.time() if now is None else now
    conn = _connect(db_path)
    try:
        with _LOCK, conn:
            if line_id is not None:
                conn.execute("UPDATE spoken_lines SET rating = ?, rated_at = ? WHERE id = ?",
                             (rating, now, line_id))
            if track_id is not None:
                conn.execute("INSERT INTO track_ratings (created, track_id, rating, line_id)"
                             " VALUES (?, ?, ?, ?)", (now, track_id, rating, line_id))
    finally:
        conn.close()


def find_reusable(kind, voice, daypart, track_id=None, prev_track_id=None,
                  min_gap_s=7 * 86400, now=None, db_path=None) -> dict | None:
    # a transition is only reusable for the exact same pair of tracks (#4164 practice)
    if kind not in ("feature", "station_id") and not (
            kind == "transition" and track_id is not None and prev_track_id is not None):
        return None
    now = time.time() if now is None else now
    conn = _connect(db_path)
    try:
        rows = conn.execute("""
            SELECT * FROM spoken_lines
            WHERE kind IS ? AND voice IS ? AND daypart IS ?
                AND track_id IS ? AND prev_track_id IS ?
                AND (aired_count = 0 OR last_aired <= ?)
                AND audio_path IS NOT NULL AND (rating IS NULL OR rating >= 0)
            ORDER BY created DESC, id DESC
        """, (kind, voice, daypart, track_id, prev_track_id, now - min_gap_s))
        for row in rows:
            if Path(row["audio_path"]).is_file():
                return dict(row)
        return None
    finally:
        conn.close()


def mark_aired(row_id, now=None, db_path=None):
    now = time.time() if now is None else now
    conn = _connect(db_path)
    try:
        with _LOCK, conn:
            conn.execute("""
                UPDATE spoken_lines
                SET aired_count = aired_count + 1, last_aired = ?
                WHERE id = ?
            """, (now, row_id))
    finally:
        conn.close()

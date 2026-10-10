"""
Archive spoken DJ text and audio for reuse without rendering TTS again (#4154).

Uses data/dj_spoken.db (DJ_SPOKEN_DB) and data/spoken (DJ_SPOKEN_DIR).
Clone-voice audio is stored in the private subdirectory. Errors propagate to callers.
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS spoken_lines_key
                ON spoken_lines(kind, prev_track_id, track_id, voice, daypart)
            """)
            conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def save(text, audio: bytes, kind, voice, daypart, track_id=None,
         prev_track_id=None, private=False, ext="mp3", db_path=None,
         audio_dir=None) -> dict:
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
                        track_id, voice, daypart, private, text, audio_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (time.time(), kind, prev_track_id, track_id, voice,
                      daypart, int(bool(private)), text, str(path)))
                row = conn.execute(
                    "SELECT * FROM spoken_lines WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
            return dict(row)
    finally:
        conn.close()


def find_reusable(kind, voice, daypart, track_id=None, prev_track_id=None,
                  min_gap_s=7 * 86400, now=None, db_path=None) -> dict | None:
    if kind not in ("feature", "station_id"):
        return None
    now = time.time() if now is None else now
    conn = _connect(db_path)
    try:
        rows = conn.execute("""
            SELECT * FROM spoken_lines
            WHERE kind IS ? AND voice IS ? AND daypart IS ?
                AND track_id IS ? AND prev_track_id IS ?
                AND (aired_count = 0 OR last_aired <= ?)
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

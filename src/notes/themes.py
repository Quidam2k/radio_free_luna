"""Themed sets picked by meaning (#949): which library songs fit a theme.

scripts/theme_batch.py scores every song 0-3 for a theme with Haiku 5.5 (from
the song's lyric-theme line, or title/work alone when no lyrics are stored) and
writes rows here. The planner reads score >= 2 as the theme's pool.

Same rules as store.py: stdlib only, keyed by store.song_key, reads fail open.

    python -m src.notes.themes halloween            # count + top songs
    python -m src.notes.themes halloween --list     # every song in the set
    python -m src.notes.themes halloween --score 1  # the borderline songs
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set

from src.notes.store import DEFAULT_DB

THEMES = {
    "halloween": (
        "A spooky-for-fun Halloween set: ghosts, haunting, witches, monsters, "
        "vampires, zombies, the devil, graveyards, the supernatural, the uncanny, "
        "dark nights and playful dread, murder ballads and macabre tales told as "
        "stories, and classical works whose programme is a witches' sabbath, a "
        "danse macabre or the like. Songs about REAL grief, mourning a loved one, "
        "suicide, self-harm, addiction or illness score 0 even when they mention "
        "death: this set is a costume party, not a funeral."
    ),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS theme_sets (
    theme     TEXT NOT NULL,
    song_key  TEXT NOT NULL,          -- store.song_key
    artist    TEXT,
    title     TEXT,
    score     INTEGER NOT NULL,       -- 3 clearly, 2 fits, 1 borderline, 0 no
    reason    TEXT,
    source    TEXT NOT NULL,          -- lyrics_tags | title_only | todd
    model     TEXT,
    tagged_at TEXT NOT NULL,
    PRIMARY KEY (theme, song_key)
);
CREATE INDEX IF NOT EXISTS theme_sets_score ON theme_sets(theme, score);
"""

MIN_SCORE = 2


def _write_conn(db_path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(Path(db_path or DEFAULT_DB)), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(SCHEMA)
    return conn


def _read_conn(db_path=None, timeout: float = 1.0):
    path = Path(db_path or DEFAULT_DB)
    if not path.exists():
        return None
    try:
        return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=timeout)
    except sqlite3.Error:
        return None


def save_rows(rows: Iterable[Dict], db_path=None) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    values = [(r["theme"], r["song_key"], r.get("artist"), r.get("title"), int(r["score"]),
               r.get("reason"), r["source"], r.get("model"), now) for r in rows]
    conn = _write_conn(db_path)
    try:
        with conn:
            conn.executemany("INSERT OR REPLACE INTO theme_sets VALUES (?,?,?,?,?,?,?,?,?)", values)
    finally:
        conn.close()
    return len(values)


def tagged_keys(theme: str, db_path=None) -> Set[str]:
    conn = _read_conn(db_path, timeout=30)
    if conn is None:
        return set()
    try:
        return {r[0] for r in conn.execute(
            "SELECT song_key FROM theme_sets WHERE theme = ?", (theme,))}
    except sqlite3.Error:
        return set()
    finally:
        conn.close()


def songs(theme: str, min_score: int = MIN_SCORE, max_score: int = 3,
          db_path=None, timeout: float = 1.0) -> List[Dict]:
    """Songs in a theme set, best first. Never raises; unknown theme -> []."""
    conn = _read_conn(db_path, timeout)
    if conn is None:
        return []
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT song_key, artist, title, score, reason, source FROM theme_sets"
            " WHERE theme = ? AND score BETWEEN ? AND ? ORDER BY score DESC, artist, title",
            (theme.strip().lower(), min_score, max_score))]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Songs in a themed set (#949)")
    ap.add_argument("theme")
    ap.add_argument("--min-score", type=int, default=MIN_SCORE)
    ap.add_argument("--score", type=int, help="only this exact score")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    low, high = (args.score, args.score) if args.score is not None else (args.min_score, 3)
    rows = songs(args.theme, low, high)
    print(f"{args.theme}: {len(rows)} songs (score {low}-{high})")
    for r in rows if args.list else rows[:20]:
        line = f"  {r['score']} {r['artist']} - {r['title']}  ({r['reason']})"
        print(line.encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

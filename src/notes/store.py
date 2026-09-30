"""Per-track DJ notes: a small SQLite store of SOURCED facts about songs (#6006).

Serves RFL's own DJ first (#431: RFL becomes the DJ over Audiplex) and the
Pantheon DJ bridge second. Every fact row carries the source it was copied
from; nothing in this store is generated or paraphrased by a model.

This module is deliberately stdlib-only (sqlite3 + re) so a caller in another
repo's interpreter can import it, or shell out to `python -m src.notes.lookup`,
without pulling in RFL's dependencies. Reads fail open: a missing database, a
locked file or an unknown song all return an empty result, never an exception.
"""

import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = Path(os.environ.get("RFL_DJ_NOTES_DB", PROJECT_ROOT / "data" / "dj_notes.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    key          TEXT PRIMARY KEY,   -- norm_artist|norm_title
    artist       TEXT,
    title        TEXT,
    title_key    TEXT,               -- norm_title alone, for the title-only fallback
    mb_recording TEXT,
    mb_work      TEXT,
    wikidata     TEXT,
    wiki_url     TEXT,
    status       TEXT NOT NULL,      -- ok | nomatch | error
    detail       TEXT,
    fetched_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS songs_title_key ON songs(title_key);
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    song_key    TEXT NOT NULL REFERENCES songs(key) ON DELETE CASCADE,
    kind        TEXT NOT NULL,       -- see FACT_KINDS
    text        TEXT NOT NULL,
    source_name TEXT NOT NULL,       -- MusicBrainz | Wikipedia | <site> (web research)
    source_url  TEXT NOT NULL,
    rank        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS facts_song ON facts(song_key);
"""

# Ordered roughly by how well each kind plays on air.
FACT_KINDS = (
    "summary", "history", "recording", "theme", "samples",
    "cover_of", "covers", "writers", "release", "reception", "artist",
)


# --- normalization ----------------------------------------------------------

_BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*(?:[\)\]]|$)")  # also a truncated '(Alternate Mix' 
_DASH_SUFFIX = re.compile(
    r"\s+-\s+(?:\d{4}\s+)?(?:remaster(?:ed)?|live|mono|stereo|single|radio|album|"
    r"edit|version|mix|demo)\b.*$",
    re.I,
)
_TRACKNO = re.compile(r"^\s*\d{1,3}\s*[-.]\s+")
_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring|with)\s+.*$", re.I)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]", "", text)


def norm_artist(artist: Optional[str]) -> str:
    a = _FEAT.sub("", artist or "")
    a = re.sub(r"^\s*the\s+", "", a, flags=re.I)
    return _fold(a)


def clean_song_title(title: Optional[str], artist: Optional[str] = None) -> str:
    """Strip track numbers, 'Artist - ' prefixes and version cruft from a title."""
    t = _TRACKNO.sub("", title or "")
    # '05 - Mark Knopfler - Devil Baby': drop an embedded artist prefix.
    if artist and " - " in t:
        head, tail = t.split(" - ", 1)
        if norm_artist(head) == norm_artist(artist):
            t = tail
    t = _BRACKETS.sub("", t)
    t = _DASH_SUFFIX.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip(" -")


def norm_title(title: Optional[str], artist: Optional[str] = None) -> str:
    return _fold(clean_song_title(title, artist))


def song_key(artist: Optional[str], title: Optional[str]) -> str:
    return f"{norm_artist(artist)}|{norm_title(title, artist)}"


# --- store --------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NotesStore:
    """Read/write handle used by the enrichment batch."""

    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def has(self, key: str, retry_errors: bool = True) -> bool:
        row = self.conn.execute("SELECT status FROM songs WHERE key = ?", (key,)).fetchone()
        if row is None:
            return False
        return not (retry_errors and row[0] == "error")

    def save(self, artist: str, title: str, status: str, facts: Iterable[Dict] = (),
             detail: Optional[str] = None, **ids) -> str:
        """Replace everything known about one song in a single transaction."""
        key = song_key(artist, title)
        with self.conn:
            self.conn.execute("DELETE FROM facts WHERE song_key = ?", (key,))
            self.conn.execute(
                "INSERT OR REPLACE INTO songs (key, artist, title, title_key, mb_recording,"
                " mb_work, wikidata, wiki_url, status, detail, fetched_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (key, artist, clean_song_title(title, artist), norm_title(title, artist),
                 ids.get("mb_recording"), ids.get("mb_work"), ids.get("wikidata"),
                 ids.get("wiki_url"), status, detail, _now()),
            )
            for rank, f in enumerate(facts):
                if not (f.get("text") and f.get("source_url") and f.get("source_name")):
                    continue  # an unsourced fact never enters the store
                self.conn.execute(
                    "INSERT INTO facts (song_key, kind, text, source_name, source_url, rank)"
                    " VALUES (?,?,?,?,?,?)",
                    (key, f.get("kind", "summary"), f["text"], f["source_name"],
                     f["source_url"], f.get("rank", rank)),
                )
        return key

    def add_facts(self, artist: str, title: str, facts: Iterable[Dict]) -> int:
        """Append facts (e.g. from a web-research pass) without dropping existing ones."""
        key = song_key(artist, title)
        if not self.conn.execute("SELECT 1 FROM songs WHERE key = ?", (key,)).fetchone():
            self.save(artist, title, "ok")
        n = 0
        with self.conn:
            for f in facts:
                if not (f.get("text") and f.get("source_url") and f.get("source_name")):
                    continue
                dup = self.conn.execute(
                    "SELECT 1 FROM facts WHERE song_key = ? AND text = ?", (key, f["text"])
                ).fetchone()
                if dup:
                    continue
                self.conn.execute(
                    "INSERT INTO facts (song_key, kind, text, source_name, source_url, rank)"
                    " VALUES (?,?,?,?,?,?)",
                    (key, f.get("kind", "history"), f["text"], f["source_name"],
                     f["source_url"], f.get("rank", 50)),
                )
                n += 1
            self.conn.execute("UPDATE songs SET status = 'ok' WHERE key = ? AND ?", (key, n))
        return n

    def stats(self) -> Dict:
        rows = self.conn.execute("SELECT status, COUNT(*) FROM songs GROUP BY status").fetchall()
        out = dict(rows)
        out["facts"] = self.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        out["songs_with_facts"] = self.conn.execute(
            "SELECT COUNT(DISTINCT song_key) FROM facts").fetchone()[0]
        return out


# --- read path (fail-open) --------------------------------------------------


def lookup(artist: Optional[str], title: Optional[str], db_path=None,
           limit: int = 8, timeout: float = 1.0) -> Dict:
    """Sourced notes for one song. Never raises; an unknown song -> facts=[].

    Matches on normalized artist+title, then falls back to the title alone when
    exactly one stored song has that title (Audiplex artist tags are sometimes
    'Various Artists' or a mis-credit).
    """
    empty = {"found": False, "artist": artist, "title": title, "facts": []}
    path = Path(db_path or DEFAULT_DB)
    if not title or not path.exists():
        return empty
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=timeout)
    except sqlite3.Error:
        return empty
    try:
        key = song_key(artist, title)
        row = conn.execute(
            "SELECT key, artist, title, mb_recording, wiki_url, status FROM songs WHERE key = ?",
            (key,),
        ).fetchone()
        matched_by = "artist+title"
        if row is None:
            rows = conn.execute(
                "SELECT key, artist, title, mb_recording, wiki_url, status FROM songs"
                " WHERE title_key = ? AND status = 'ok'",
                (norm_title(title, artist),),
            ).fetchall()
            if len(rows) == 1:
                row, matched_by = rows[0], "title-only"
        if row is None:
            return empty
        facts = [
            {"kind": k, "text": t, "source": s, "url": u}
            for k, t, s, u in conn.execute(
                "SELECT kind, text, source_name, source_url FROM facts"
                " WHERE song_key = ? ORDER BY rank, id LIMIT ?",
                (row[0], limit),
            )
        ]
        return {
            "found": bool(facts),
            "artist": row[1],
            "title": row[2],
            "matched_by": matched_by,
            "status": row[5],
            "musicbrainz_recording": row[3],
            "wikipedia": row[4],
            "facts": facts,
        }
    except sqlite3.Error:
        return empty
    finally:
        conn.close()


def format_facts(notes: Dict, max_facts: int = 4) -> List[str]:
    """One line per fact, with its source, ready to drop into a DJ prompt."""
    return [f"{f['text']} ({f['source']}: {f['url']})" for f in notes.get("facts", [])[:max_facts]]

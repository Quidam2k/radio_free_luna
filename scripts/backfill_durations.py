"""Backfill NULL track durations by re-reading audio metadata with mutagen.

Root cause (#3098): the Stacked Deck enrich pass inserted ~3174 track rows
without a duration, so session_manager's `Track.duration <= 900` filter (NULL
<= 900 is false in SQL) silently dropped every one of them, leaving the DJ
layer with an effectively empty library. This backfills the missing durations
using the same source the ingest path uses: mutagen's audio_file.info.length.

Idempotent: only touches rows where duration IS NULL (or 0). Missing files are
reported and left alone.
"""
import sqlite3
import sys
from pathlib import Path

from mutagen import File as MutagenFile

DB = Path(__file__).resolve().parent.parent / "data" / "radio_free_luna.db"


def main() -> int:
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, file_path FROM tracks WHERE duration IS NULL OR duration = 0"
    ).fetchall()
    print(f"{len(rows)} tracks need a duration")

    updated = missing = unreadable = zero = 0
    for i, (track_id, file_path) in enumerate(rows, 1):
        p = Path(file_path)
        if not p.exists():
            missing += 1
            continue
        try:
            audio = MutagenFile(str(p))
            length = int(getattr(getattr(audio, "info", None), "length", 0) or 0)
        except Exception as e:  # noqa: BLE001
            unreadable += 1
            if unreadable <= 10:
                print(f"  unreadable: {p.name}: {e}")
            continue
        if length <= 0:
            zero += 1
            continue
        cur.execute("UPDATE tracks SET duration = ? WHERE id = ?", (length, track_id))
        updated += 1
        if i % 500 == 0:
            conn.commit()
            print(f"  ...{i}/{len(rows)} processed, {updated} updated")

    conn.commit()
    conn.close()
    print(
        f"DONE: {updated} updated, {missing} missing files, "
        f"{unreadable} unreadable, {zero} zero-length"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

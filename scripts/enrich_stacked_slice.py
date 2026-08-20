"""Enrich the Stacked Deck 'targeted slice' — Individual + Ren Faire (#3069 / #971).

Scope per PROCEED #3072:
  identify (Phase-2 toolkit) + lyrics (Genius fallback) + audiplex-overlap dedupe.
  LLM theme-tagging is DEFERRED (ai_analyzer OpenAI quota dead since 2026-06-10, #974).

Stages (default run does scan->dedupe->index->lyrics; NOT tag writeback):
  scan    scan_folder(research) -> per-folder dry-run report + tag snapshot (safe)
  dedupe  mark items already held by audiplex (normalized artist+title)
  index   upsert non-overlap music tracks into RFL tracks table
  lyrics  fetch via LyricsFetcher (token placeholder -> azlyrics fallback), cache
          into track_analysis.lyrics

Tag writeback (writes to the REAL audio files) is a SEPARATE, snapshot-gated step:
  python scripts/enrich_stacked_slice.py --apply     # after reviewing the dry-run diff

Everything is idempotent and re-runnable. Reports + snapshots live under data/enrich/.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.enrich import pipeline, tagio  # noqa: E402
from src.analysis.lyrics_fetcher import LyricsFetcher  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RFL_DB = ROOT / "data" / "radio_free_luna.db"
AUDIPLEX_DB = Path(r"Q:/Development/audiplex/server/audiplex.db")
ENRICH_DIR = ROOT / "data" / "enrich"
ENRICH_DIR.mkdir(parents=True, exist_ok=True)

SLICE = {
    "individual": r"E:\Stacked Deck\Music\Individual",
    "renfaire": r"E:\Stacked Deck\Music\Artists & Albums\Mixed\Ren Faire",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "logs" / "enrich_stacked.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("enrich_slice")


def norm(s):
    """Normalize an artist/title for cross-library equality."""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)          # drop bracketed cruft
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)  # drop punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s


def report_path(slug):
    return ENRICH_DIR / f"{slug}-dryrun.json"


# --------------------------------------------------------------------------- scan
async def stage_scan(slug, folder, research):
    snap = ENRICH_DIR / f"{slug}-tags-snapshot.json"
    log.info(f"[scan] {slug}: {folder} (research={research})")
    report = await pipeline.scan_folder(
        folder=folder, research=research, snapshot_path=str(snap), progress_every=50,
    )
    with open(report_path(slug), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    c = report["counts"]
    log.info(
        f"[scan] {slug}: scanned {report['files_scanned']} | music {c['music']} "
        f"non-music {c['non_music']} | MB {c['musicbrainz_matched']}/{c['researched']} "
        f"| auto {c['auto_applicable']} review {c['needs_review']} manual {c['needs_manual']}"
    )
    return report


# ------------------------------------------------------------------------- dedupe
def audiplex_index():
    if not AUDIPLEX_DB.exists():
        log.warning(f"[dedupe] audiplex db not found at {AUDIPLEX_DB}; no overlaps marked")
        return set()
    con = sqlite3.connect(str(AUDIPLEX_DB))
    rows = con.execute(
        "SELECT t.title, a.name FROM tracks t "
        "LEFT JOIN artists a ON a.id = t.artist_id"
    ).fetchall()
    con.close()
    idx = {f"{norm(name)}|{norm(title)}" for title, name in rows}
    log.info(f"[dedupe] audiplex holds {len(rows)} tracks ({len(idx)} normalized keys)")
    return idx


def final_of(item):
    return item.get("final") or item["candidate"]


def stage_dedupe(report, ax_idx):
    overlaps = 0
    for item in report["items"]:
        item["audiplex_overlap"] = False
        if not item["classification"]["is_music"]:
            continue
        f = final_of(item)
        key = f"{norm(f.get('artist'))}|{norm(f.get('title'))}"
        if f.get("title") and key in ax_idx:
            item["audiplex_overlap"] = True
            overlaps += 1
    log.info(f"[dedupe] {report['folder']}: {overlaps} audiplex overlaps marked")
    return overlaps


# -------------------------------------------------------------------------- index
def stage_index(report):
    con = sqlite3.connect(str(RFL_DB))
    con.execute("PRAGMA foreign_keys=ON")
    indexed = 0
    for item in report["items"]:
        if not item["classification"]["is_music"] or item.get("audiplex_overlap"):
            continue
        f = final_of(item)
        path = item["candidate"]["path"]
        title = f.get("title") or item["candidate"].get("original_title")
        artist = f.get("artist")
        if not title:
            continue
        row = con.execute("SELECT id FROM tracks WHERE file_path=?", (path,)).fetchone()
        if row:
            tid = row[0]
            con.execute(
                "UPDATE tracks SET title=?, artist=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (title, artist, tid),
            )
        else:
            cur = con.execute(
                "INSERT INTO tracks (file_path, title, artist, year, created_at, updated_at) "
                "VALUES (?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                (path, title, artist, f.get("year")),
            )
            tid = cur.lastrowid
        item["rfl_track_id"] = tid
        indexed += 1
    con.commit()
    con.close()
    log.info(f"[index] {report['folder']}: {indexed} tracks indexed into RFL db")
    return indexed


# ------------------------------------------------------------------------- lyrics
async def stage_lyrics(report, min_conf=0.5):
    targets = [
        item for item in report["items"]
        if item["classification"]["is_music"]
        and not item.get("audiplex_overlap")
        and item.get("rfl_track_id")
        and final_of(item).get("title")
        and final_of(item).get("artist")
        and final_of(item).get("confidence", 0) >= min_conf
    ]
    log.info(f"[lyrics] {report['folder']}: {len(targets)} candidates (conf>={min_conf})")
    con = sqlite3.connect(str(RFL_DB))
    fetched = failed = skipped = 0
    token = os.environ.get("GENIUS_API_TOKEN", "")
    if token and "your_genius" in token:
        token = ""  # placeholder -> use fallback source
    async with LyricsFetcher(genius_token=token or None) as lf:
        for i, item in enumerate(targets, 1):
            tid = item["rfl_track_id"]
            f = final_of(item)
            row = con.execute(
                "SELECT lyrics FROM track_analysis WHERE track_id=?", (tid,)
            ).fetchone()
            if row and row[0]:
                skipped += 1
                continue
            try:
                lyrics = await lf.fetch_lyrics(f["artist"], f["title"])
            except Exception as e:  # noqa: BLE001
                lyrics = None
                log.debug(f"[lyrics] error {f['artist']} - {f['title']}: {e}")
            if lyrics:
                con.execute(
                    "INSERT INTO track_analysis (track_id, lyrics, analysis_date) "
                    "VALUES (?,?,CURRENT_TIMESTAMP) "
                    "ON CONFLICT(track_id) DO UPDATE SET lyrics=excluded.lyrics",
                    (tid, lyrics),
                )
                con.commit()
                fetched += 1
            else:
                failed += 1
            if i % 25 == 0:
                log.info(f"[lyrics] {report['folder']}: {i}/{len(targets)} "
                         f"(ok {fetched} miss {failed} skip {skipped})")
    con.close()
    log.info(f"[lyrics] {report['folder']}: fetched {fetched} miss {failed} skip {skipped}")
    return {"fetched": fetched, "failed": failed, "skipped": skipped, "candidates": len(targets)}


# -------------------------------------------------------------------------- apply
def stage_apply(slug, min_conf=0.85):
    rp = report_path(slug)
    with open(rp, encoding="utf-8") as f:
        report = json.load(f)
    # never write tags to a track audiplex already owns
    for item in report["items"]:
        if item.get("audiplex_overlap"):
            item["classification"]["is_music"] = False
    os.environ["RFL_ENRICH_ALLOW_WRITES"] = "1"
    result = pipeline.apply_report(report, dry_run=False, min_confidence=min_conf)
    log.info(f"[apply] {slug}: {result['status']} considered {result['considered']} "
             f"written {result['written']}")
    return result


# ---------------------------------------------------------------------------- run
async def run_enrich(research):
    ax = audiplex_index()
    totals = {}
    for slug, folder in SLICE.items():
        report = await stage_scan(slug, folder, research)
        stage_dedupe(report, ax)
        idx = stage_index(report)
        lyr = await stage_lyrics(report)
        with open(report_path(slug), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)  # persist dedupe/track_id
        c = report["counts"]
        totals[slug] = {
            "scanned": report["files_scanned"], "music": c["music"],
            "non_music": c["non_music"], "mb_matched": c["musicbrainz_matched"],
            "auto": c["auto_applicable"], "review": c["needs_review"],
            "manual": c["needs_manual"],
            "overlaps": sum(1 for it in report["items"] if it.get("audiplex_overlap")),
            "indexed": idx, "lyrics": lyr,
        }
    with open(ENRICH_DIR / "slice-summary.json", "w", encoding="utf-8") as f:
        json.dump(totals, f, indent=2, ensure_ascii=False)
    log.info("[done] " + json.dumps(totals))
    return totals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-research", action="store_true", help="skip MusicBrainz (fast)")
    ap.add_argument("--apply", action="store_true", help="Phase-3 snapshot-gated tag write")
    args = ap.parse_args()
    if args.apply:
        for slug in SLICE:
            stage_apply(slug)
    else:
        asyncio.run(run_enrich(research=not args.no_research))


if __name__ == "__main__":
    main()

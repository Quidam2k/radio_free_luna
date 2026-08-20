"""Scan orchestration: read -> identify -> classify -> research -> report.

Dry-run by design. scan_folder() never writes to an audio file; the only thing
it can put on disk is the tag snapshot (outside the music folder) and the report
the caller chooses to save. Applying changes is a separate, explicitly unlocked
call that lands with Phase 3.
"""

import asyncio
import logging
from collections import Counter
from dataclasses import asdict
from typing import Dict, List, Optional

from . import classify as classify_mod
from . import identify as identify_mod
from . import tagio
from .research import MusicBrainzResearcher

logger = logging.getLogger(__name__)

# Candidates at or above this are safe to apply without human review.
AUTO_APPLY_CONFIDENCE = 0.85


async def scan_folder(
    folder: str,
    research: bool = True,
    limit: Optional[int] = None,
    snapshot_path: Optional[str] = None,
    recursive: bool = True,
    progress_every: int = 25,
) -> Dict:
    """Analyze a folder and return a full dry-run report.

    research=False skips all network calls, making this a fast offline pass.
    """
    paths = tagio.find_audio_files(folder, recursive=recursive)
    if limit:
        paths = paths[:limit]
    logger.info(f"Scanning {len(paths)} audio files in {folder}")

    snapshot_written = None
    if snapshot_path:
        # Taken up front so a later apply can never run without a rollback source.
        snapshot_written = tagio.write_snapshot(paths, snapshot_path)

    items: List[Dict] = []
    for path in paths:
        tags = tagio.read_tags(path)
        parts = path.replace("\\", "/").split("/")
        stem = parts[-1].rsplit(".", 1)[0]
        folder_name = parts[-2] if len(parts) > 1 else ""
        candidate = identify_mod.identify(
            path, tags, stem=stem, folder_name=folder_name
        )
        # Classify against the RAW text, not the cleaned candidate: title
        # cleaning strips exactly the markers that identify a podcast or a
        # branded clip ('| Lex Fridman Podcast #271'), so classifying the
        # cleaned title would throw away the evidence. The filename stem is
        # included because it sometimes retains cruft the tag lost.
        verdict = classify_mod.classify(
            title=" ".join(filter(None, [tags.get("title"), stem, candidate.title])),
            artist=" ".join(filter(None, [tags.get("artist"), candidate.artist])),
            duration=tags.get("duration"),
        )
        items.append({
            "candidate": asdict(candidate),
            "classification": asdict(verdict),
            "duration": tags.get("duration"),
            "research": None,
        })

    if research:
        await _research_items(items, progress_every=progress_every)

    return _summarize(folder, items, snapshot_written)


async def _research_items(items: List[Dict], progress_every: int = 25):
    """Confirm music-classified candidates against MusicBrainz.

    Non-music items are skipped deliberately: spending a rate-limited lookup on
    a podcast episode is wasted, and a spurious match would be worse than none.
    """
    targets = [
        item for item in items
        if item["classification"]["is_music"] and item["candidate"]["title"]
    ]
    logger.info(
        f"Researching {len(targets)} music items via MusicBrainz "
        f"(~{len(targets) * 1.1 / 60:.1f} min at the required 1 req/sec)"
    )

    async with MusicBrainzResearcher() as researcher:
        for index, item in enumerate(targets, 1):
            candidate = item["candidate"]
            result = await researcher.lookup(candidate["artist"], candidate["title"])
            item["research"] = asdict(result)

            if result.matched:
                # Corroboration lifts confidence; a correction replaces the value.
                boosted = min(0.99, candidate["confidence"] + 0.15 * result.confidence)
                item["final"] = {
                    "artist": result.artist,
                    "title": result.title,
                    "year": result.year,
                    "release": result.release,
                    "confidence": round(boosted, 3),
                    "source": "musicbrainz",
                }
            else:
                item["final"] = {
                    "artist": candidate["artist"],
                    "title": candidate["title"],
                    "year": None,
                    "release": None,
                    "confidence": candidate["confidence"],
                    "source": "heuristic-only",
                }

            if progress_every and index % progress_every == 0:
                logger.info(f"  researched {index}/{len(targets)}")


def _summarize(folder: str, items: List[Dict], snapshot: Optional[str]) -> Dict:
    """Roll per-file results up into the numbers a reviewer actually needs."""
    tiers = Counter(item["candidate"]["tier"] for item in items)
    kinds = Counter(item["classification"]["kind"] for item in items)

    music = [item for item in items if item["classification"]["is_music"]]
    non_music = [item for item in items if not item["classification"]["is_music"]]
    researched = [item for item in music if item.get("research")]
    matched = [item for item in researched if item["research"]["matched"]]

    def _confidence(item):
        return (item.get("final") or item["candidate"])["confidence"]

    auto = [item for item in music if _confidence(item) >= AUTO_APPLY_CONFIDENCE]
    review = [
        item for item in music
        if 0.5 <= _confidence(item) < AUTO_APPLY_CONFIDENCE
    ]
    manual = [item for item in music if _confidence(item) < 0.5]

    return {
        "folder": folder,
        "dry_run": True,
        "files_scanned": len(items),
        "snapshot": snapshot,
        "tiers": dict(tiers),
        "kinds": dict(kinds),
        "counts": {
            "music": len(music),
            "non_music": len(non_music),
            "researched": len(researched),
            "musicbrainz_matched": len(matched),
            "auto_applicable": len(auto),
            "needs_review": len(review),
            "needs_manual": len(manual),
        },
        "items": items,
    }


def apply_report(report: Dict, dry_run: bool = True, min_confidence: float = AUTO_APPLY_CONFIDENCE) -> Dict:
    """Apply a scan report's proposals. Phase 3 entry point.

    Refuses to do anything real without both dry_run=False and a snapshot that
    exists on disk (enforced in tagio.write_tags, checked again here so the
    refusal is reported once rather than 206 times).
    """
    snapshot = report.get("snapshot")
    if not dry_run and not snapshot:
        return {
            "status": "refused: report has no tag snapshot",
            "written": 0,
            "results": [],
        }

    results = []
    for item in report.get("items", []):
        if not item["classification"]["is_music"]:
            continue
        final = item.get("final") or item["candidate"]
        if final.get("confidence", 0) < min_confidence:
            continue
        results.append(tagio.write_tags(
            path=item["candidate"]["path"],
            artist=final.get("artist"),
            title=final.get("title"),
            dry_run=dry_run,
            snapshot_path=snapshot,
        ))

    return {
        "status": "dry-run" if dry_run else "applied",
        "considered": len(results),
        "written": sum(1 for r in results if r["written"]),
        "results": results,
    }

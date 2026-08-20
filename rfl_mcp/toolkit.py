"""Radio Free Luna — enrichment toolkit MCP server.

This is the SECOND RFL MCP server and it is deliberately different in kind from
server.py. server.py is a thin httpx wrapper around the broadcast REST API, so
every tool there needs the station running on :8080. These tools call
src/enrich directly, in-process, because the whole point of the split (#894) is
to enrich arbitrary folders with the station down.

Safety, per plan-back #8901:
  * rfl_enrich_scan is dry-run and never writes to an audio file.
  * A JSON snapshot of all pre-existing tags is taken before any write.
  * rfl_enrich_apply is Phase 3 and refuses to run until explicitly unlocked
    via RFL_ENRICH_ALLOW_WRITES=1, so an agent cannot retag a library by
    accident during Phase 2.

Config via environment:
  RFL_ENRICH_SNAPSHOT_DIR   where tag snapshots are written (default data/enrich)
  RFL_ENRICH_ALLOW_WRITES   set to '1' to permit rfl_enrich_apply (Phase 3)
"""

import json
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.enrich import identify as identify_mod
from src.enrich import pipeline, tagio

SNAPSHOT_DIR = Path(os.environ.get("RFL_ENRICH_SNAPSHOT_DIR", "data/enrich"))
WRITES_ALLOWED = os.environ.get("RFL_ENRICH_ALLOW_WRITES") == "1"

mcp = FastMCP("rfl-toolkit")


def _snapshot_path(folder: str) -> str:
    slug = Path(folder).name.replace(" ", "_") or "library"
    return str(SNAPSHOT_DIR / f"{slug}-tags-snapshot.json")


@mcp.tool()
async def rfl_enrich_scan(
    folder: str,
    research: bool = True,
    limit: Optional[int] = None,
    save_report: bool = True,
) -> str:
    """Analyze a music folder and report what retagging WOULD do. Never writes audio files.

    Reads existing tags (falling back to filenames), proposes corrected
    artist/title, flags non-music (podcasts, focus mixes, TV clips), and
    optionally confirms each candidate against MusicBrainz.

    folder: any directory of audio files; the RFL station need not be running.
    research: confirm candidates via MusicBrainz (keyless, ~1 file/sec).
    limit: cap files scanned, for a quick sample.
    save_report: write the full per-file report next to the tag snapshot.
    """
    try:
        report = await pipeline.scan_folder(
            folder=folder,
            research=research,
            limit=limit,
            snapshot_path=_snapshot_path(folder),
        )
    except NotADirectoryError as e:
        return f"Not a directory: {e}"

    report_path = None
    if save_report:
        report_path = SNAPSHOT_DIR / f"{Path(folder).name or 'library'}-dryrun.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    counts = report["counts"]
    lines = [
        f"DRY RUN — no audio files were modified.",
        f"Folder: {folder}",
        f"Scanned: {report['files_scanned']} files",
        f"Identification tiers: {report['tiers']}",
        f"Content kinds: {report['kinds']}",
        f"Music: {counts['music']} | Non-music: {counts['non_music']}",
        f"MusicBrainz matched: {counts['musicbrainz_matched']}/{counts['researched']}",
        f"Auto-applicable (>=0.85): {counts['auto_applicable']}",
        f"Needs review (0.5-0.85): {counts['needs_review']}",
        f"Needs manual work (<0.5): {counts['needs_manual']}",
        f"Tag snapshot: {report['snapshot']}",
    ]
    if report_path:
        lines.append(f"Full report: {report_path}")
    return "\n".join(lines)


@mcp.tool()
async def rfl_identify_track(path: str, research: bool = True) -> str:
    """Work out the real artist and title for ONE audio file.

    Useful on its own for just-in-time DJ research (#537): given a file, say who
    it is actually by, rather than which YouTube channel uploaded it.
    """
    if not os.path.exists(path):
        return f"File not found: {path}"

    tags = tagio.read_tags(path)
    stem = Path(path).stem
    candidate = identify_mod.identify(path, tags, stem=stem)

    lines = [
        f"File: {path}",
        f"Existing tags: artist={tags.get('artist')!r} title={tags.get('title')!r}",
        f"Proposed: artist={candidate.artist!r} title={candidate.title!r}",
        f"Tier: {candidate.tier} (confidence {candidate.confidence})",
    ]
    if candidate.notes:
        lines.append("Notes: " + "; ".join(candidate.notes))

    if research and candidate.title:
        from src.enrich.research import MusicBrainzResearcher

        async with MusicBrainzResearcher() as researcher:
            result = await researcher.lookup(candidate.artist, candidate.title)
        if result.matched:
            lines.append(
                f"MusicBrainz: {result.artist} — {result.title}"
                f"{f' ({result.year})' if result.year else ''} "
                f"[score {result.score}, confidence {result.confidence}]"
            )
            lines.extend(f"  {n}" for n in result.notes)
        else:
            lines.append(f"MusicBrainz: no confident match ({'; '.join(result.notes)})")

    return "\n".join(lines)


@mcp.tool()
async def rfl_enrich_apply(
    report_path: str,
    min_confidence: float = 0.85,
    confirm: bool = False,
) -> str:
    """Write proposed tags from a saved scan report. PHASE 3 — locked by default.

    Refuses unless RFL_ENRICH_ALLOW_WRITES=1 is set in the environment AND
    confirm=True is passed, and even then only writes files whose proposal
    clears min_confidence and whose tags were captured in the snapshot.
    """
    if not WRITES_ALLOWED:
        return (
            "REFUSED: writes are disabled. This is Phase 2 (dry-run only). "
            "Set RFL_ENRICH_ALLOW_WRITES=1 to unlock after the Phase 3 diff review."
        )
    if not confirm:
        return "REFUSED: pass confirm=True to write tags."
    if not os.path.exists(report_path):
        return f"Report not found: {report_path}"

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    result = pipeline.apply_report(report, dry_run=False, min_confidence=min_confidence)
    return (
        f"Status: {result['status']}\n"
        f"Considered: {result['considered']}\n"
        f"Written: {result['written']}"
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

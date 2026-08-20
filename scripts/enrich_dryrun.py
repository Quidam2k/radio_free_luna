"""Phase 2 dry-run: scan a folder, research it, save the report. Writes no audio files.

Usage:
    python scripts/enrich_dryrun.py [folder] [out.json] [--no-research]
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.enrich import pipeline  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folder = args[0] if args else "Q:/music"
    out = args[1] if len(args) > 1 else "data/enrich/qmusic-dryrun.json"
    research = "--no-research" not in sys.argv

    report = await pipeline.scan_folder(
        folder=folder,
        research=research,
        snapshot_path="data/enrich/qmusic-tags-snapshot.json",
    )

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(json.dumps({
        "files_scanned": report["files_scanned"],
        "tiers": report["tiers"],
        "kinds": report["kinds"],
        "counts": report["counts"],
        "snapshot": report["snapshot"],
        "report": out,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

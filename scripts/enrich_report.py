"""Turn a dry-run JSON report into the markdown a reviewer can actually read.

Usage:
    python scripts/enrich_report.py data/enrich/qmusic-dryrun.json > report.md
"""

import json
import sys
from collections import Counter
from pathlib import Path


def _final(item):
    return item.get("final") or item["candidate"]


def _row(item):
    cand = item["candidate"]
    fin = _final(item)
    name = Path(cand["path"]).name
    return (
        f"| `{name[:52]}` | {cand['original_artist'] or '—'} | "
        f"{fin.get('artist') or '—'} | {fin.get('title') or '—'} | "
        f"{cand['tier']} | {fin.get('confidence', 0):.2f} |"
    )


HEADER = "| File | Was (tag) | Proposed artist | Proposed title | Tier | Conf |\n|---|---|---|---|---|---|"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/enrich/qmusic-dryrun.json"
    with open(path, encoding="utf-8") as f:
        report = json.load(f)

    items = report["items"]
    counts = report["counts"]
    music = [i for i in items if i["classification"]["is_music"]]
    non_music = [i for i in items if not i["classification"]["is_music"]]

    auto = sorted(
        (i for i in music if _final(i).get("confidence", 0) >= 0.85),
        key=lambda i: -_final(i)["confidence"],
    )
    review = sorted(
        (i for i in music if 0.5 <= _final(i).get("confidence", 0) < 0.85),
        key=lambda i: -_final(i)["confidence"],
    )
    manual = [i for i in music if _final(i).get("confidence", 0) < 0.5]

    corrections = [
        i for i in music
        if (i.get("research") or {}).get("matched") and i["research"].get("notes")
    ]

    out = []
    out.append(f"# Enrichment dry run — `{report['folder']}`\n")
    out.append(
        f"**No audio files were modified.** Tag snapshot: `{report['snapshot']}`\n"
    )
    out.append(
        f"Scanned **{report['files_scanned']}** files — "
        f"{counts['music']} music, {counts['non_music']} non-music. "
        f"MusicBrainz matched {counts['musicbrainz_matched']}/{counts['researched']}.\n"
    )

    out.append("## Confidence bands\n")
    out.append(
        f"| Band | Count | Meaning |\n|---|---|---|\n"
        f"| Auto-applicable (>=0.85) | {len(auto)} | safe to write without per-file review |\n"
        f"| Needs review (0.50-0.85) | {len(review)} | plausible, wants a human glance |\n"
        f"| Needs manual work (<0.50) | {len(manual)} | could not be identified reliably |\n"
    )

    out.append("## Identification tiers\n")
    for tier, n in sorted(report["tiers"].items(), key=lambda kv: -kv[1]):
        out.append(f"- `{tier}` — {n}")
    out.append("")

    out.append("## Content kinds\n")
    for kind, n in sorted(report["kinds"].items(), key=lambda kv: -kv[1]):
        out.append(f"- `{kind}` — {n}")
    out.append("")

    out.append(f"## Non-music, report-only ({len(non_music)})\n")
    out.append("Per plan-back #8901 Q3 these are reported and left untouched.\n")
    out.append("| File | Kind | Why |\n|---|---|---|")
    for item in non_music:
        name = Path(item["candidate"]["path"]).name
        cls = item["classification"]
        out.append(f"| `{name[:56]}` | {cls['kind']} | {'; '.join(cls['reasons'])} |")
    out.append("")

    out.append(f"## MusicBrainz corrections ({len(corrections)})\n")
    out.append("Cases where research changed the heuristic's answer.\n")
    out.append("| File | Correction |\n|---|---|")
    for item in corrections[:60]:
        name = Path(item["candidate"]["path"]).name
        out.append(f"| `{name[:48]}` | {'; '.join(item['research']['notes'])} |")
    out.append("")

    out.append(f"## Auto-applicable ({len(auto)})\n")
    out.append(HEADER)
    out.extend(_row(i) for i in auto)
    out.append("")

    out.append(f"## Needs review ({len(review)})\n")
    out.append(HEADER)
    out.extend(_row(i) for i in review)
    out.append("")

    out.append(f"## Needs manual work ({len(manual)})\n")
    out.append(HEADER)
    out.extend(_row(i) for i in manual)
    out.append("")

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n".join(out))


if __name__ == "__main__":
    main()

"""
Rebuild data/corpus/chris_fewshot.jsonl (gitignored show dialogue) from the tracked
spec docs/dj/chris_fewshot_spec.json, which holds only segment ids, moves and
character offsets into data/corpus/ne_kbhr_segments.jsonl (#6019).

  python scripts/build_chris_fewshot.py            # rebuild the few-shot file
  python scripts/build_chris_fewshot.py --spec     # regenerate the spec from the current file
  python scripts/build_chris_fewshot.py --check    # verify file and spec agree; exit 1 if not
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEGMENTS = ROOT / "data" / "corpus" / "ne_kbhr_segments.jsonl"
FEWSHOT = ROOT / "data" / "corpus" / "chris_fewshot.jsonl"
SPEC = ROOT / "docs" / "dj" / "chris_fewshot_spec.json"


def load_jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def segments():
    return {r["id"]: r["text"] for r in load_jsonl(SEGMENTS)}


def spec_from_fewshot():
    seg = segments()
    spec = []
    for row in load_jsonl(FEWSHOT):
        start = seg[row["id"]].find(row["excerpt"])
        if start < 0:
            sys.exit(f"excerpt for {row['id']} is not in its segment")
        spec.append({"id": row["id"], "move": row["move"],
                     "start": start, "end": start + len(row["excerpt"])})
    return spec


def fewshot_from_spec():
    seg = segments()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    return [{"id": s["id"], "move": s["move"], "excerpt": seg[s["id"]][s["start"]:s["end"]]}
            for s in spec]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.spec:
        SPEC.write_text(json.dumps(spec_from_fewshot(), indent=1) + "\n", encoding="utf-8")
        print(f"wrote {SPEC}")
    elif args.check:
        ok = fewshot_from_spec() == load_jsonl(FEWSHOT)
        print("few-shot file matches spec" if ok else "MISMATCH between spec and few-shot file")
        sys.exit(0 if ok else 1)
    else:
        rows = fewshot_from_spec()
        FEWSHOT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                           encoding="utf-8")
        print(f"wrote {len(rows)} excerpts to {FEWSHOT}")


if __name__ == "__main__":
    main()

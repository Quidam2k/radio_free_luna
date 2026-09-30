"""  #6019
Before/after eval of RFL transition bridges with and without the Chris style layer (#6019).

Same prompt, same facts (DJ-notes store), same backend (DJ_LLM from .env); only the
style layer differs. Writes JSON with the facts each AFTER bridge was given, so every
claim can be checked by hand.

  python scripts/eval_dj_bridges.py [--out data/runtime/eval/bridges.json]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.dj import commentary_generator as cg  # noqa: E402
from src.dj.chris_style import style_block  # noqa: E402

# Todd's ride tracks (most-played / Bike Music) whose incoming song has research notes.
PAIRS = [
    (("Sly & The Family Stone", "I Want To Take You Higher"), ("Digital Underground", "The Humpty Dance")),
    (("Us3", "Cantaloop"), ("Beastie Boys", "Gratitude")),
    (("Tom Petty", "Wildflowers"), ("Indigo Girls", "Closer To Fine")),
    (("Rush", "Animate"), ("Bjork", "Big Time Sensuality")),
    (("Creedence Clearwater Revival", "Green River"), ("Go Go's", "Our Lips Are Sealed")),
]

CONTEXT = {
    "temporal": SimpleNamespace(time_of_day="morning", day_of_week="Saturday", holiday=None),
    "location": SimpleNamespace(city="Denver"),
}
CONNECTION = {"description": "a morning bike ride playlist"}


async def bridge(gen, cur, nxt, styled: bool) -> str:
    cg.style_block = style_block if styled else (lambda kind: "")
    prompt = gen._build_transition_prompt(cur, nxt, CONTEXT, CONNECTION)
    return await gen._call_llm(prompt, CONTEXT, kind="transition")


async def main(out: Path):
    gen = cg.DJCommentaryGenerator(settings.openai_api_key, base_url=settings.openai_base_url)
    results = []
    for (a1, t1), (a2, t2) in PAIRS:
        cur = {"artist": a1, "title": t1}
        nxt = {"artist": a2, "title": t2}
        before = await bridge(gen, cur, nxt, styled=False)
        after = await bridge(gen, cur, nxt, styled=True)
        results.append({"from": cur, "to": nxt, "facts": gen._sourced_facts(nxt),
                        "before": before, "after": after})
        print(f"done: {t1} -> {t2}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "runtime" / "eval" / "bridges.json")
    asyncio.run(main(ap.parse_args().out))

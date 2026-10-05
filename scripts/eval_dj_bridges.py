"""  #6019, #6914
Compare DJ transition bridges across backends (#6914): local (LM Studio) vs Haiku vs Sonnet.

Same prompt, same sourced facts (DJ-notes store), same Chris style layer; only the
backend differs. Each bridge goes through the real path (validator, one retry, template
fallback), so the numbers are what the station would actually air.

  python scripts/eval_dj_bridges.py --backends local,haiku,sonnet [--pairs 10]
      [--local-model google/gemma-4-12b] [--local-gpu off|max] [--out DIR]

Per bridge: text, latency, validator pass on attempt 1/2 or fallback, reasons.
Local adds load time and VRAM (nvidia-smi, before/loaded/after unload).
Writes bridges.json + report.md; the local model is unloaded at the end.
--style-ab keeps the old before/after style-layer comparison on the configured backend.
"""

import argparse
import asyncio
import json
import random
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.dj import commentary_generator as cg  # noqa: E402
from src.dj import llm_backend  # noqa: E402
from src.dj.chris_style import style_block  # noqa: E402

# Todd's ride tracks (most-played / Bike Music) whose incoming song has research notes.
PAIRS = [
    (("Sly & The Family Stone", "I Want To Take You Higher"), ("Digital Underground", "The Humpty Dance")),
    (("Us3", "Cantaloop"), ("Beastie Boys", "Gratitude")),
    (("Tom Petty", "Wildflowers"), ("Indigo Girls", "Closer To Fine")),
    (("Rush", "Animate"), ("Bjork", "Big Time Sensuality")),
    (("Creedence Clearwater Revival", "Green River"), ("Go Go's", "Our Lips Are Sealed")),
]

BACKENDS = {
    "local": ("local", None),
    "haiku": ("claude_cli", "claude-haiku-4-5-20251001"),
    "sonnet": ("claude_cli", "claude-sonnet-5-5"),
}

CONTEXT = {
    "temporal": SimpleNamespace(time_of_day="morning", day_of_week="Saturday", holiday=None),
    "location": SimpleNamespace(city="Eugene"),
}
CONNECTION = {"description": "a morning bike ride playlist"}
LMS = str(Path.home() / ".cache" / "lm-studio" / "bin" / "lms.exe")


def pick_pairs(n: int, seed: int = 6914):
    """The fixed ride pairs, topped up with random songs that have stored facts."""
    pairs = list(PAIRS)
    if n <= len(pairs):
        return pairs[:n]
    db = sqlite3.connect(ROOT / "data" / "dj_notes.db")
    rows = db.execute("SELECT DISTINCT s.artist, s.title FROM songs s JOIN facts f "
                      "ON f.song_key = s.key WHERE s.status = 'ok' AND f.kind != 'artist'").fetchall()
    rng = random.Random(seed)
    rng.shuffle(rows)
    need = (n - len(pairs)) * 2
    extra = [(a, t) for a, t in rows[:need]]
    pairs += [(extra[i], extra[i + 1]) for i in range(0, len(extra) - 1, 2)]
    return pairs[:n]


def vram_mib():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def lms(*args, timeout=600):
    r = subprocess.run([LMS, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


async def run_backend(label, pairs, local_model, local_gpu):
    name, model = BACKENDS[label]
    meta = {"backend": label}
    if label == "local":
        model = local_model
        meta["model"] = model
        meta["vram_before_mib"] = vram_mib()
        t0 = time.perf_counter()
        # Own identifier so requests hit THIS load (CPU-only when --gpu off), not a JIT copy;
        # ttl unloads it even if we die
        model = "rfl-dj-eval"
        code, out = lms("load", local_model, "--identifier", model, "--gpu", local_gpu,
                        "--ttl", "600", "-y")
        meta["load_s"] = round(time.perf_counter() - t0, 1)
        meta["load_ok"] = code == 0
        meta["vram_loaded_mib"] = vram_mib()
        meta["gpu"] = local_gpu
        if code != 0:
            meta["load_error"] = out[-300:]
            return meta, []
    else:
        meta["model"] = model

    gen = cg.DJCommentaryGenerator(settings.openai_api_key, base_url=settings.openai_base_url)
    gen.llm_override = (name, model)
    cg.style_block = style_block
    rows = []
    for (a1, t1), (a2, t2) in pairs:
        cur, nxt = {"artist": a1, "title": t1}, {"artist": a2, "title": t2}
        t0 = time.perf_counter()
        seg = await gen.generate_transition_commentary(cur, nxt, CONTEXT, CONNECTION)
        lb = getattr(gen, "last_bridge", None) or {}
        rows.append({"from": cur, "to": nxt, "facts": [f["text"] for f in gen._sourced_facts(nxt)],
                     "text": seg.content, "latency_s": round(time.perf_counter() - t0, 1),
                     "ok": bool(lb.get("ok")), "attempts": lb.get("attempts", 0),
                     "fallback": not lb.get("ok"), "reasons": lb.get("reasons", []),
                     "error": None if lb else "model call failed"})
        gen.last_bridge = None
        print(f"[{label}] {t1} -> {t2}: {'ok' if rows[-1]['ok'] else 'FALLBACK'} "
              f"({rows[-1]['latency_s']} s)", flush=True)

    if label == "local":
        t0 = time.perf_counter()
        meta["unload_ok"] = lms("unload", model)[0] == 0
        meta["unload_s"] = round(time.perf_counter() - t0, 1)
        time.sleep(2)
        meta["vram_after_mib"] = vram_mib()
    return meta, rows


def summarize(meta, rows):
    n = len(rows) or 1
    lat = sorted(r["latency_s"] for r in rows) or [0]
    return {**meta, "n": len(rows),
            "pass_first_try": sum(r["ok"] and r["attempts"] == 1 for r in rows),
            "pass_after_retry": sum(r["ok"] and r["attempts"] == 2 for r in rows),
            "fallback": sum(r["fallback"] for r in rows),
            "failure_rate": round(sum(r["fallback"] for r in rows) / n, 2),
            "latency_median_s": lat[len(lat) // 2], "latency_max_s": lat[-1]}


def report_md(summaries, results):
    cols = ["backend", "model", "n", "pass_first_try", "pass_after_retry", "fallback",
            "latency_median_s", "latency_max_s", "load_s", "gpu", "vram_before_mib",
            "vram_loaded_mib", "vram_after_mib"]
    lines = ["# DJ bridge eval (#6914)", "", "| " + " | ".join(cols) + " |",
             "|" + "---|" * len(cols)]
    for s in summaries:
        lines.append("| " + " | ".join(str(s.get(c, "")) for c in cols) + " |")
    for label, rows in results.items():
        lines += ["", f"## {label}", ""]
        for r in rows:
            tag = "ok" if r["ok"] else "FALLBACK"
            lines.append(f"- **{r['from']['title']} -> {r['to']['title']}** ({tag}, "
                         f"{r['attempts']} tries, {r['latency_s']} s): {r['text']}")
            for reasons in r["reasons"]:
                lines.append(f"  - rejected: {'; '.join(reasons)}")
    return "\n".join(lines) + "\n"


async def main(args):
    pairs = pick_pairs(args.pairs)
    results, summaries = {}, []
    labels = [b.strip() for b in args.backends.split(",") if b.strip()]
    if "local" in labels and not args.todd_approved_lmstudio:
        # #6926: loading a model into LM Studio on Solace needs Todd's yes, every time
        raise SystemExit("local leg needs --todd-approved-lmstudio (Todd's explicit yes)")
    for label in labels:
        meta, rows = await run_backend(label, pairs, args.local_model, args.local_gpu)
        results[label] = rows
        summaries.append(summarize(meta, rows))
        # Written after every backend, so a later crash never loses earlier runs
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "bridges.json").write_text(json.dumps({"summary": summaries, "results": results},
                                                          indent=1, ensure_ascii=False), encoding="utf-8")
        (args.out / "report.md").write_text(report_md(summaries, results), encoding="utf-8")
    print(json.dumps(summaries, indent=1))
    print(f"wrote {args.out}")


async def style_ab(out: Path):
    """The original #6019 before/after comparison of the style layer."""
    gen = cg.DJCommentaryGenerator(settings.openai_api_key, base_url=settings.openai_base_url)
    results = []
    for (a1, t1), (a2, t2) in PAIRS:
        cur, nxt = {"artist": a1, "title": t1}, {"artist": a2, "title": t2}
        row = {"from": cur, "to": nxt, "facts": gen._sourced_facts(nxt)}
        for key, styled in (("before", False), ("after", True)):
            cg.style_block = style_block if styled else (lambda kind: "")
            prompt = gen._build_transition_prompt(cur, nxt, CONTEXT, CONNECTION)
            row[key] = await gen._call_llm(prompt, CONTEXT, kind="transition")
        results.append(row)
    out.mkdir(parents=True, exist_ok=True)
    (out / "style_ab.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", default="haiku,sonnet")
    ap.add_argument("--todd-approved-lmstudio", action="store_true",
                    help="Todd said yes to loading a model into LM Studio for this run (#6926)")
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--local-model", default=llm_backend.local_model())
    ap.add_argument("--local-gpu", default="off", help="lms --gpu: off (CPU only), max, or 0-1")
    ap.add_argument("--style-ab", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "runtime" / "eval")
    a = ap.parse_args()
    asyncio.run(style_ab(a.out) if a.style_ab else main(a))

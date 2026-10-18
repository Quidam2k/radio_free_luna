"""One-off grounded trivia and lyric-theme model bake-off for #8203."""
import os

os.environ.setdefault("DJ_SPEND_HOURLY_USD", "5")
os.environ.setdefault("DJ_SPEND_DAILY_USD", "20")

import argparse
import json
import random
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from textwrap import wrap
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.dj.llm_backend import anthropic_messages
from src.dj import spend
from src.notes.store import DEFAULT_DB

MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5")
JUDGE = "claude-opus-5-5"
STRATA = ("famous", "deep cut", "obscure")
TRIVIA_SYSTEM = (
    'You write on-air trivia notes for a radio DJ. Use ONLY the SOURCE text provided. '
    'Never add facts from memory: no dates, names, chart positions, awards, or stories '
    'that are not in the SOURCE. If the SOURCE is thin, write fewer notes. Output JSON '
    'only: {"notes": ["...", ...]} with 1-5 notes, each one sentence, max 30 words.'
)
JUDGE_SYSTEM = (
    'You are a strict fact-checker. For each numbered NOTE decide whether every factual '
    'claim in it is stated in or directly implied by the SOURCE. Labels: SUPPORTED, '
    'UNSUPPORTED (adds a claim not in the source, even if true in reality), CONTRADICTED '
    '(conflicts with the source). Output JSON only: {"verdicts": [{"n": 1, '
    '"label": "...", "claim": "<the unsupported part, or empty>"}]}'
)
TAG_SYSTEM = (
    'Tag the themes of a song from its LYRICS only. Output JSON only: '
    '{"themes": [3-6 short lowercase theme tags], "mood": "one or two words"}. '
    'Do not use outside knowledge about the song or artist.'
)
TAG_JUDGE_SYSTEM = (
    'Evaluate anonymous tag sets A and B using ONLY the LYRICS. For each set list '
    'theme tags unsupported by the lyrics and give quality from 1-5: how well the '
    'tags capture what the song is about, for a DJ. Do not use outside knowledge. '
    'Output JSON only: {"A": {"unsupported_tags": [], "quality": 1}, '
    '"B": {"unsupported_tags": [], "quality": 1}}.'
)


def strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def parse_output(raw: str, schema: str, count: int) -> dict[str, Any]:
    data = json.loads(re.sub(r"\A```(?:json)?\s*|\s*```\Z", "", raw.strip(), flags=re.I))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    if schema in ("notes", "themes"):
        valid = strings(data.get(schema))
        if schema == "themes":
            valid = valid and isinstance(data.get("mood"), str)
    elif schema == "verdicts":
        rows = data.get("verdicts")
        valid = isinstance(rows, list) and len(rows) == count
        valid = valid and all(
            isinstance(v, dict) and type(v.get("n")) is int
            and v.get("label") in ("SUPPORTED", "UNSUPPORTED", "CONTRADICTED")
            and isinstance(v.get("claim"), str) for v in rows
        )
        valid = valid and {v["n"] for v in rows} == set(range(1, count + 1))
    else:
        valid = all(
            isinstance(data.get(k), dict) and strings(data[k].get("unsupported_tags"))
            and type(data[k].get("quality")) is int and 1 <= data[k]["quality"] <= 5
            for k in ("A", "B")
        )
    if not valid:
        raise ValueError(f"Invalid {schema} response schema")
    return data


def ask(model: str, system: str, prompt: str, limit: int,
        schema: str, count: int = 0) -> dict[str, Any]:
    result = {"data": {}, "usage": {}, "cost": 0.0, "error": None, "raw": ""}
    body = {"model": model, "max_tokens": limit, "system": system,
            "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(2):
        try:
            response = anthropic_messages(body, purpose=f"bakeoff_8203_{schema}")
            break
        except spend.CapExceeded as exc:
            result["error"] = str(exc)
            return result
        except RuntimeError as exc:
            if attempt == 0 and any(code in str(exc) for code in ("429", "529", " 5")):
                time.sleep(10)
                continue
            result["error"] = str(exc)
            return result
    usage = response.get("usage", {})
    result["usage"] = usage
    result["cost"] = spend.cost_usd(
        model, usage.get("input_tokens", 0), usage.get("output_tokens", 0),
        cache_read=usage.get("cache_read_input_tokens", 0),
        cache_write=usage.get("cache_creation_input_tokens", 0),
    )
    result["raw"] = "".join(
        block.get("text", "") for block in response.get("content", [])
        if block.get("type") == "text"
    )
    try:
        result["data"] = parse_output(result["raw"], schema, count)
    except (ValueError, TypeError, KeyError) as exc:
        result["error"] = f"JSON/schema error: {exc}"
    return result


def load_songs(args: argparse.Namespace) -> tuple[list[dict], list[dict], int]:
    rng = random.Random(8203)
    with closing(sqlite3.connect(Path(DEFAULT_DB).resolve().as_uri() + "?mode=ro",
                                 uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT s.key, s.artist, s.title, COUNT(*) AS fact_count FROM songs s "
            "JOIN facts f ON f.song_key=s.key WHERE s.status='ok' AND f.kind!='artist' "
            "GROUP BY s.key ORDER BY s.key"
        ).fetchall()
        buckets: dict[str, list[dict]] = {s: [] for s in STRATA}
        for row in rows:
            song = dict(row)
            song["stratum"] = STRATA[0 if row["fact_count"] >= 8 else
                                      1 if row["fact_count"] >= 3 else 2]
            buckets[song["stratum"]].append(song)
        songs, remaining = [], []
        for i, stratum in enumerate(STRATA):
            bucket = buckets[stratum]
            rng.shuffle(bucket)
            quota = args.songs // 3 + (i < args.songs % 3)
            songs.extend(bucket[:quota])
            remaining.extend(bucket[quota:])
        rng.shuffle(remaining)
        songs.extend(remaining[:max(0, args.songs - len(songs))])
        for song in songs:
            facts = db.execute(
                "SELECT kind, text, source_name FROM facts WHERE song_key=? ORDER BY rank,id",
                (song["key"],),
            )
            song["source"] = "\n".join(
                f"- [{f['kind']}] {f['text']} ({f['source_name']})" for f in facts
            )[:6000]
            song["source_chars"] = len(song["source"])
        tags, lyrics_count = [], 0
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lyrics'").fetchone():
            lyrics_count = db.execute("SELECT COUNT(*) FROM lyrics WHERE status='ok'").fetchone()[0]
            if args.tag_songs and lyrics_count:
                tags = [dict(r) for r in db.execute(
                    "SELECT song_key, artist, title, substr(plain,1,4000) AS lyrics "
                    "FROM lyrics WHERE status='ok' AND length(plain)>200 "
                    "ORDER BY song_key, artist, title, plain"
                )]
                random.Random(8203).shuffle(tags)
                tags = tags[:args.tag_songs]
        label_rng = random.Random(8203)
        for song in tags:
            order = list(MODELS)
            label_rng.shuffle(order)
            song["mapping"] = dict(zip(("A", "B"), order))
    return songs, tags, lyrics_count


def trivia_song(song: dict[str, Any]) -> dict[str, Any]:
    song["models"] = {}
    prompt = f"Artist: {song['artist']}\nTitle: {song['title']}\n\nSOURCE:\n{song['source']}"
    for model in MODELS:
        entry = ask(model, TRIVIA_SYSTEM, prompt, 800, "notes")
        entry["notes"] = entry.pop("data").get("notes", [])
        judge = {"data": {}, "usage": {}, "cost": 0.0, "error": None, "raw": ""}
        if entry["notes"]:
            numbered = "\n".join(f"NOTE {i}: {note}" for i, note in enumerate(entry["notes"], 1))
            judge = ask(JUDGE, JUDGE_SYSTEM, f"SOURCE:\n{song['source']}\n\n{numbered}",
                        1500, "verdicts", len(entry["notes"]))
        entry["verdicts"] = judge.pop("data").get("verdicts", [])
        entry["judge"] = judge
        song["models"][model] = entry
    return song


def tag_song(song: dict[str, Any]) -> dict[str, Any]:
    song["models"] = {}
    prompt = f"Artist: {song['artist']}\nTitle: {song['title']}\n\nLYRICS:\n{song['lyrics']}"
    for model in MODELS:
        entry = ask(model, TAG_SYSTEM, prompt, 300, "themes")
        data = entry.pop("data")
        entry.update(themes=data.get("themes", []), mood=data.get("mood"))
        song["models"][model] = entry
    if any(entry["error"] for entry in song["models"].values()):
        song["judge"] = {"data": {}, "usage": {}, "cost": 0.0,
                         "error": "Comparison skipped: tag generation failed", "raw": ""}
        return song
    anonymous = {label: {k: song["models"][model][k] for k in ("themes", "mood")}
                 for label, model in song["mapping"].items()}
    song["judge"] = ask(JUDGE, TAG_JUDGE_SYSTEM,
                        f"LYRICS:\n{song['lyrics']}\n\nTAG SETS:\n{json.dumps(anonymous)}",
                        1500, "comparison")
    return song


def unsupported(entry: dict[str, Any]) -> int:
    return sum(v["label"] in ("UNSUPPORTED", "CONTRADICTED") for v in entry["verdicts"])


def report(result: dict[str, Any], library: int) -> list[str]:
    trivia, tags = result["trivia"], result["tags"]
    summary: dict[str, Any] = {"trivia": {}, "tags": {}}
    lines = ["TRIVIA", "model         songs notes notes/song bad bad% bad-songs unknown mean$/song total$ projected$",
             f"Projection library: {library} songs"]
    for model in MODELS:
        entries = [s["models"][model] for s in trivia]
        notes = sum(len(e["notes"]) for e in entries)
        bad = sum(unsupported(e) for e in entries)
        cost = sum(e["cost"] for e in entries)
        mean = cost / len(entries) if entries else 0.0
        rates = {}
        for stratum in STRATA:
            group = [s["models"][model] for s in trivia if s["stratum"] == stratum]
            denominator = sum(len(e["notes"]) for e in group)
            rates[stratum] = 100 * sum(unsupported(e) for e in group) / denominator if denominator else None
        metrics = dict(songs=len(entries), total_notes=notes,
                       notes_per_song=notes / len(entries) if entries else 0,
                       unsupported_count=bad, unsupported_rate=100 * bad / notes if notes else 0,
                       songs_with_unsupported=sum(unsupported(e) > 0 for e in entries),
                       unjudged_notes=notes - sum(len(e["verdicts"]) for e in entries),
                       rate_by_stratum=rates, mean_cost_per_song=mean,
                       total_generation_cost=cost, projected_library_cost=mean * library)
        summary["trivia"][model] = metrics
        lines.append(f"{model.removeprefix('claude-'):<13} {len(entries):5} {notes:5} "
                     f"{metrics['notes_per_song']:10.2f} {bad:3} {metrics['unsupported_rate']:5.1f} "
                     f"{metrics['songs_with_unsupported']:9} {metrics['unjudged_notes']:7} "
                     f"{mean:10.6f} {cost:7.4f} {mean * library:10.2f}")
        lines.append("  Bad-note rates: " + ", ".join(
            f"{s}={rates[s]:.1f}%" if rates[s] is not None else f"{s}=n/a" for s in STRATA))
    lines += ["", "EXAMPLES (largest absolute difference in bad-note counts)"]
    examples = sorted(trivia, key=lambda s: (
        -abs(unsupported(s["models"][MODELS[0]]) - unsupported(s["models"][MODELS[1]])),
        STRATA.index(s["stratum"]), str(s["key"])))[:3]
    for song in examples:
        lines += [f"{song['artist']} / {song['title']} ({song['stratum']})",
                  f"{MODELS[0]:<58} | {MODELS[1]}"]
        columns = []
        for model in MODELS:
            entry = song["models"][model]
            labels = {v["n"]: v["label"] for v in entry["verdicts"]}
            text = " / ".join(f"[{labels.get(i, 'UNJUDGED')}] {n}"
                              for i, n in enumerate(entry["notes"], 1))
            columns.append(wrap(text or "(no notes)", 58))
        lines.extend(f"{a:<58} | {b}" for a, b in zip_longest(*columns, fillvalue=""))
    tag_library = result["lyrics_ok_rows"] or library
    lines += ["", f"TAGS (projection library: {tag_library} lyrics rows)",
              "model         songs judged mean-quality unsupported-tags mean$/song projected$"]
    for model in MODELS:
        entries = [s["models"][model] for s in tags]
        judged = [s["judge"]["data"][label] for s in tags
                  for label, mapped in s["mapping"].items()
                  if mapped == model and label in s["judge"]["data"]]
        quality = sum(j["quality"] for j in judged) / len(judged) if judged else None
        bad_tags = sum(len(j["unsupported_tags"]) for j in judged)
        mean = sum(e["cost"] for e in entries) / len(entries) if entries else 0.0
        summary["tags"][model] = dict(songs=len(entries), judged_songs=len(judged),
            mean_quality=quality, unsupported_tags=bad_tags, mean_cost_per_song=mean,
            projected_library_cost=mean * tag_library)
        quality_text = f"{quality:.2f}" if quality is not None else "n/a"
        lines.append(f"{model.removeprefix('claude-'):<13} {len(entries):5} {len(judged):6} "
                     f"{quality_text:>12} {bad_tags:16} {mean:10.6f} {mean * tag_library:10.2f}")
    generations = [s["models"][m] for s in trivia + tags for m in MODELS]
    judges = [s["models"][m]["judge"] for s in trivia for m in MODELS] + [s["judge"] for s in tags]
    summary["judge_cost_total"] = sum(j["cost"] for j in judges)
    summary["total_spend"] = sum(e["cost"] for e in generations) + summary["judge_cost_total"]
    lines += [f"Judge cost total: ${summary['judge_cost_total']:.6f}",
              f"Total spend: ${summary['total_spend']:.6f}",
              f"Errors: generation={sum(bool(e['error']) for e in generations)}, "
              f"judge={sum(bool(j['error']) for j in judges)}; incomplete judgments are unscored."]
    result["summary"] = summary
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--songs", type=int, default=30)
    parser.add_argument("--tag-songs", type=int, default=20)
    parser.add_argument("--library-songs", type=int, default=30256)
    parser.add_argument("--out", type=Path, default=Path("data/bakeoff_8203.json"))
    args = parser.parse_args()
    if min(args.songs, args.tag_songs, args.library_songs) < 0:
        parser.error("Song counts must be nonnegative")
    songs, tags, lyrics_count = load_songs(args)
    with ThreadPoolExecutor(max_workers=4) as pool:
        trivia_results = list(pool.map(trivia_song, songs))
        tag_results = list(pool.map(tag_song, tags))
    result = dict(issue=8203, seed=8203, run_at=datetime.now(timezone.utc).isoformat(),
                  config={**vars(args), "out": str(args.out)}, models=list(MODELS),
                  judge_model=JUDGE, lyrics_ok_rows=lyrics_count,
                  trivia=trivia_results, tags=tag_results)
    result["report"] = [line.encode("ascii", "replace").decode("ascii")
                        for line in report(result, args.library_songs)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(result["report"]))


if __name__ == "__main__":
    main()


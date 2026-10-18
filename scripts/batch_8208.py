"""#8208: lyric theme tags (Sonnet 5.5) and grounded trivia rewrites (Haiku 5.5)
via the Anthropic Message Batches API, stored as marked facts in dj_notes.db.

Costs stay OUT of data/dj_spend.db: that ledger drives the radio's hourly/daily
caps, and a $20 batch would silence the DJ. They go to data/batches_8208.json.

    .venv/Scripts/python.exe scripts/batch_8208.py submit tags --dry-run
    .venv/Scripts/python.exe scripts/batch_8208.py collect <batch_id>
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dj.llm_backend import _anthropic_key
from src.dj.spend import PRICES
from src.notes.store import DEFAULT_DB, NotesStore, song_key

API = "https://api.anthropic.com/v1/messages/batches"
STATE = ROOT / "data/batches_8208.json"
MANIFESTS = ROOT / "data/batches_8208"
MODELS = {"tags": "claude-sonnet-5-5", "trivia": "claude-haiku-5-5"}
TAG_SYSTEM = 'Tag the themes of a song from its LYRICS only. Output JSON only: {"themes": [3-6 short lowercase theme tags], "mood": "one or two words"}. Do not use outside knowledge about the song or artist.'
TRIVIA_SYSTEM = 'You write on-air trivia notes for a radio DJ. Use ONLY the SOURCE text provided. Never add facts from memory: no dates, names, chart positions, awards, or stories that are not in the SOURCE. If the SOURCE is thin, write fewer notes. Output JSON only: {"notes": ["...", ...]}, each one sentence, max 30 words.'


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_state() -> list:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else []


def http(url: str, body: bytes | None = None):
    headers = {"x-api-key": _anthropic_key(), "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    try:
        return urlopen(Request(url, data=body, headers=headers), timeout=120)
    except HTTPError as exc:
        detail = exc.read(1200).decode("utf-8", errors="replace")[:300]
        log(f"HTTP {exc.code}: {ascii(detail)}")
        raise SystemExit(1) from None
    except URLError as exc:
        log(f"HTTP connection failed: {ascii(str(exc.reason))}")
        raise SystemExit(1) from None


def batch_status(batch_id: str) -> dict:
    with http(f"{API}/{quote(batch_id, safe='')}") as response:
        return json.load(response)


def cost(model: str, usage: dict) -> float:
    price = PRICES[model]
    creation = usage.get("cache_creation") or {}
    short = creation.get("ephemeral_5m_input_tokens", 0) or 0
    long = creation.get("ephemeral_1h_input_tokens", 0) or 0
    write = usage.get("cache_creation_input_tokens", short + long) or 0
    inputs = (usage.get("input_tokens", 0) or 0)
    inputs += (usage.get("cache_read_input_tokens", 0) or 0) * 0.1
    inputs += max(0, write - long) * 1.25 + long * 2
    outputs = usage.get("output_tokens", 0) or 0
    return (inputs * price["in"] + outputs * price["out"]) * 0.5 / 1_000_000


def candidates(kind: str, limit: int | None) -> Iterator[tuple[dict, dict]]:
    with closing(sqlite3.connect(Path(DEFAULT_DB).resolve().as_uri() + "?mode=ro",
                                 uri=True, timeout=30)) as db:
        db.row_factory = sqlite3.Row
        if kind == "tags":
            sql = """SELECT l.* FROM lyrics l
                WHERE l.status='ok' AND length(l.plain)>200
                AND NOT EXISTS (SELECT 1 FROM facts f
                    WHERE f.song_key=l.song_key AND f.origin='lyrics_llm')
                ORDER BY l.song_key LIMIT ?"""
        else:
            sql = """SELECT s.key AS song_key, s.artist, s.title, count(*) AS n_facts
                FROM songs s JOIN facts f ON f.song_key=s.key
                WHERE s.status IN ('ok','research')
                AND f.origin IN ('auto','research') AND f.kind!='artist'
                AND NOT EXISTS (SELECT 1 FROM facts x
                    WHERE x.song_key=s.key AND x.origin='llm_rewrite')
                GROUP BY s.key HAVING count(*)>=2 ORDER BY s.key LIMIT ?"""
        for index, row in enumerate(db.execute(sql, (limit if limit is not None else -1,))):
            meta = {name: row[name] for name in ("song_key", "artist", "title")}
            artist, title = row["artist"], row["title"]
            if kind == "tags":
                meta.update(lrclib_id=row["lrclib_id"], n_facts=1)
                content = f"Artist: {artist}\nTitle: {title}\n\nLYRICS:\n{row['plain'][:4000]}"
            else:
                facts = db.execute("""SELECT kind,text,source_name,source_url FROM facts
                    WHERE song_key=? AND origin IN ('auto','research')
                    ORDER BY rank,id""", (row["song_key"],)).fetchall()
                meta.update(source_url=facts[0]["source_url"], n_facts=row["n_facts"])
                source = "\n".join(
                    f"- [{f['kind']}] {f['text']} ({f['source_name']})" for f in facts
                )[:6000]
                content = (f"Artist: {artist}\nTitle: {title}\n"
                           f"Write at most {min(5, row['n_facts'])} notes.\n\nSOURCE:\n{source}")
            params = {"model": MODELS[kind], "max_tokens": 300 if kind == "tags" else 800,
                      "system": TAG_SYSTEM if kind == "tags" else TRIVIA_SYSTEM,
                      "messages": [{"role": "user", "content": content}]}
            yield {"custom_id": f"t{index}", "params": params}, meta


def chunks(rows: Iterator[tuple[dict, dict]]) -> Iterator[tuple[bytes, dict]]:
    requests, manifest, size = [], {}, len(b'{"requests":[]}')
    for request, meta in rows:
        encoded = json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        if requests and (len(requests) >= 10000 or size + len(encoded) + 1 > 195_000_000):
            yield b'{"requests":[' + b",".join(requests) + b"]}", manifest
            requests, manifest, size = [], {}, len(b'{"requests":[]}')
        if len(encoded) + len(b'{"requests":[]}') > 195_000_000:
            raise ValueError("A single request exceeds the batch size limit")
        size += len(encoded) + bool(requests)
        requests.append(encoded)
        manifest[request["custom_id"]] = meta
    if requests:
        yield b'{"requests":[' + b",".join(requests) + b"]}", manifest


def submit(kind: str, limit: int | None, dry_run: bool) -> None:
    rows = candidates(kind, limit)
    if dry_run:
        count, tokens, first = 0, 0.0, None
        for request, _ in rows:
            params = request["params"]
            tokens += (len(params["system"]) + len(params["messages"][0]["content"])) / 4
            count += 1
            if first is None:
                first = request
        estimate = cost(MODELS[kind], {"input_tokens": tokens,
                        "output_tokens": count * (120 if kind == "tags" else 250)})
        print(f"count={count} estimated_input_tokens={tokens:.0f} estimated_cost_usd={estimate:.6f}")
        print(json.dumps(first, ensure_ascii=True))
        return
    submitted = 0
    for body, manifest in chunks(rows):
        log(f"Submitting {kind}: {len(manifest)} requests, {len(body)} bytes")
        with http(API, body) as response:
            batch = json.load(response)
        batch_id = batch["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", batch_id):
            raise ValueError("Unexpected batch ID")
        save_json(MANIFESTS / f"{batch_id}.manifest.json", manifest)
        state = read_state()
        state.append({"batch_id": batch_id, "kind": kind, "model": MODELS[kind],
                      "submitted_at": batch.get("created_at") or datetime.now(timezone.utc).isoformat(),
                      "count": len(manifest), "collected": False, "cost_usd": 0.0})
        save_json(STATE, state)
        print(f"batch_id={batch_id} kind={kind} count={len(manifest)}")
        submitted += len(manifest)
    log(f"Submitted {submitted} requests")


def parse_facts(message: dict, kind: str, meta: dict) -> list[dict]:
    text = "".join(block.get("text", "") for block in message.get("content", [])
                   if block.get("type") == "text").strip()
    text = re.sub(r"\A```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\Z", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    if kind == "tags":
        themes, mood = data.get("themes"), data.get("mood")
        if (not isinstance(themes, list) or not 1 <= len(themes) <= 8
                or not all(isinstance(t, str) for t in themes) or not isinstance(mood, str)):
            raise ValueError("Invalid themes or mood")
        identifier = meta["lrclib_id"]
        return [{"kind": "theme", "text": f"Lyric themes: {', '.join(themes)}. Mood: {mood}.",
                 "source_name": "lrclib lyrics, tagged by Sonnet 5.5",
                 "source_url": f"https://lrclib.net/api/get/{identifier}" if identifier else "https://lrclib.net",
                 "rank": 50}]
    notes = data.get("notes")
    if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
        raise ValueError("Invalid notes")
    return [{"kind": "trivia", "text": note,
             "source_name": "Haiku 5.5 rewrite of stored sources",
             "source_url": meta["source_url"], "rank": 60 + i}
            for i, note in enumerate(notes[:min(5, meta["n_facts"])])]


def collect(batch_id: str) -> None:
    state = read_state()
    entry = next((item for item in state if item["batch_id"] == batch_id), None)
    if entry is None:
        raise ValueError("Batch is not present in the local state file")
    manifest = json.loads((MANIFESTS / f"{batch_id}.manifest.json").read_text(encoding="utf-8"))
    while True:
        batch = batch_status(batch_id)
        log(f"{batch_id}: {batch['processing_status']}")
        if batch["processing_status"] == "ended":
            break
        time.sleep(60)
    if not batch.get("results_url"):
        raise ValueError("Ended batch has no results_url")
    counts = dict.fromkeys(("succeeded", "errored", "parse_failed", "key_mismatch", "facts_written"), 0)
    total, seen = 0.0, set()
    origin = "lyrics_llm" if entry["kind"] == "tags" else "llm_rewrite"
    with http(batch["results_url"]) as response, NotesStore(DEFAULT_DB) as store:
        for line in response:
            if not line.strip():
                continue
            row = json.loads(line)
            custom_id = row["custom_id"]
            if custom_id in seen:
                continue
            seen.add(custom_id)
            result = row["result"]
            if result["type"] != "succeeded":
                counts["errored"] += 1
                log(f"{custom_id}: {result['type']}")
                continue
            counts["succeeded"] += 1
            message = result["message"]
            total += cost(entry["model"], message.get("usage") or {})
            meta = manifest.get(custom_id)
            if meta is None:
                counts["parse_failed"] += 1
                log(f"{custom_id}: missing manifest entry")
                continue
            label = ascii(f"{meta['artist']} - {meta['title']}")
            if song_key(meta["artist"], meta["title"]) != meta["song_key"]:
                counts["key_mismatch"] += 1
                log(f"{custom_id}: key_mismatch {label}")
                continue
            try:
                facts = parse_facts(message, entry["kind"], meta)
            except (ValueError, TypeError, KeyError, AttributeError):
                counts["parse_failed"] += 1
                log(f"{custom_id}: parse_failed {label}")
                continue
            counts["facts_written"] += store.add_facts(
                meta["artist"], meta["title"], facts, origin=origin)
            if len(seen) % 100 == 0:
                log(f"Processed {len(seen)}/{entry['count']} results")
    if seen != set(manifest):
        raise ValueError("Results do not match the manifest; collection remains incomplete")
    state = read_state()
    entry = next(item for item in state if item["batch_id"] == batch_id)
    entry.update(collected=True, cost_usd=total)
    save_json(STATE, state)
    print(" ".join(f"{name}={value}" for name, value in counts.items()) + f" cost_usd={total:.6f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    kinds = commands.add_parser("submit").add_subparsers(dest="kind", required=True)
    for kind in MODELS:
        sub = kinds.add_parser(kind)
        sub.add_argument("--limit", type=int)
        sub.add_argument("--dry-run", action="store_true")
    for command in ("status", "collect"):
        commands.add_parser(command).add_argument("batch_id")
    args = parser.parse_args()
    if args.command == "submit":
        if args.limit is not None and args.limit < 0:
            parser.error("--limit must be nonnegative")
        submit(args.kind, args.limit, args.dry_run)
    elif args.command == "status":
        print(json.dumps(batch_status(args.batch_id), ensure_ascii=True, indent=2))
    else:
        collect(args.batch_id)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        log(f"Error: {ascii(str(exc))}")
        sys.exit(1)

"""#949: classify library songs by meaning using themed Message Batches.

    python scripts/theme_batch.py submit halloween --dry-run
    python scripts/theme_batch.py collect <batch_id>
    python scripts/theme_batch.py spotcheck halloween
"""

import argparse
import json
import random
import re
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "scripts"))

from batch_8208 import API, http, batch_status, cost, chunks, save_json, log
from src.notes.store import song_key
from src.notes.themes import THEMES, save_rows, tagged_keys

LIBRARY_DB = ROOT / "data/radio_free_luna.db"
NOTES_DB = ROOT / "data/dj_notes.db"
STATE = ROOT / "data/batches_949.json"
MANIFESTS = ROOT / "data/batches_949"
MODEL = "claude-haiku-5-5"
CHECK_MODEL = "claude-sonnet-5-5"
MESSAGES_API = "https://api.anthropic.com/v1/messages"
NO_LYRICS = (
    "No lyrics on file; judge from title, work and artist only. "
    "If unsure, score 0."
)
TITLE_WORDS = (
    "ghost", "dead", "death", "devil", "hell", "night", "dark", "grave",
    "witch", "monster", "blood", "haunt", "skull", "demon", "fear", "moon",
    "halloween", "bones", "zombie", "vampire", "evil", "spirit", "black",
    "scream",
)


def connect_ro(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    return db


def read_state() -> list:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else []


def validate_theme(theme: str) -> None:
    if theme not in THEMES:
        raise ValueError(f"Unknown theme: {ascii(theme)}")


def validate_batch_id(batch_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", batch_id):
        raise ValueError("Unexpected batch ID")


def system_prompt(theme: str) -> str:
    validate_theme(theme)
    return f"""You pick songs for a themed radio set. THEME: {theme}. {THEMES[theme]}
Judge by what the song is ABOUT (lyrics, subject, the work's programme), never by how it sounds.
Output JSON only: {{"score": 0-3, "reason": "max 15 words"}}. 3 = clearly about the theme, 2 = fits, 1 = borderline, 0 = does not fit."""


def library_tracks() -> Iterator[dict]:
    """Yield the first library row for each normalized song key."""
    seen = set()
    with closing(connect_ro(LIBRARY_DB)) as db:
        for row in db.execute(
            "SELECT artist,title,album,year,genre FROM tracks ORDER BY id"
        ):
            if not row["title"] or not row["title"].strip():
                continue
            track = dict(row)
            track["artist"] = track["artist"] or ""
            key = song_key(track["artist"], track["title"])
            if key in seen:
                continue
            seen.add(key)
            track["song_key"] = key
            yield track


def lyric_context() -> tuple[dict[str, str], set[str]]:
    """Load each song's first lyric theme line and instrumental status once."""
    themes = {}
    with closing(connect_ro(NOTES_DB)) as db:
        for row in db.execute(
            "SELECT song_key,text FROM facts WHERE origin='lyrics_llm' ORDER BY id"
        ):
            themes.setdefault(row["song_key"], row["text"])
        instrumentals = {
            row["song_key"]
            for row in db.execute(
                "SELECT song_key FROM lyrics WHERE status='instrumental'"
            )
        }
    return themes, instrumentals


def build_content(
    track: dict, lyric_themes: dict[str, str], instrumentals: set[str]
) -> tuple[str, str]:
    key = track["song_key"]
    has_themes = key in lyric_themes
    lines = [
        f"{field.capitalize()}: {track.get(field) if track.get(field) is not None else ''}"
        for field in ("artist", "title", "album", "year", "genre")
    ]
    lines.append(lyric_themes[key] if has_themes else NO_LYRICS)
    if key in instrumentals:
        lines.append("Instrumental (no lyrics).")
    return "\n".join(lines), "lyrics_tags" if has_themes else "title_only"


def message_params(theme: str, content: str, model: str) -> dict:
    return {
        "model": model,
        "max_tokens": 80,
        "system": system_prompt(theme),
        "messages": [{"role": "user", "content": content}],
    }


def candidates(theme: str, limit: int | None) -> Iterator[tuple[dict, dict]]:
    validate_theme(theme)
    if limit == 0:
        return
    already_tagged = tagged_keys(theme)
    lyric_themes, instrumentals = lyric_context()
    index = 0
    for track in library_tracks():
        if track["song_key"] in already_tagged:
            continue
        content, source = build_content(track, lyric_themes, instrumentals)
        meta = {name: track[name] for name in ("song_key", "artist", "title")}
        meta["source"] = source
        yield {
            "custom_id": f"t{index}",
            "params": message_params(theme, content, MODEL),
        }, meta
        index += 1
        if limit is not None and index >= limit:
            break


def submit(theme: str, limit: int | None, dry_run: bool) -> None:
    rows = candidates(theme, limit)
    if dry_run:
        count, tokens, first = 0, 0.0, None
        for request, _ in rows:
            params = request["params"]
            tokens += (
                len(params["system"]) + len(params["messages"][0]["content"])
            ) / 4
            count += 1
            if first is None:
                first = request
        estimate = cost(
            MODEL, {"input_tokens": tokens, "output_tokens": count * 30}
        )
        print(
            f"count={count} estimated_input_tokens={tokens:.0f} "
            f"estimated_cost_usd={estimate:.6f}"
        )
        print(json.dumps(first, ensure_ascii=True))
        return

    submitted = 0
    for body, manifest in chunks(rows):
        log(
            f"Submitting {ascii(theme)}: "
            f"{len(manifest)} requests, {len(body)} bytes"
        )
        with http(API, body) as response:
            batch = json.load(response)
        batch_id = batch["id"]
        validate_batch_id(batch_id)
        save_json(MANIFESTS / f"{batch_id}.manifest.json", manifest)
        state = read_state()
        state.append({
            "batch_id": batch_id,
            "kind": theme,
            "model": MODEL,
            "submitted_at": (
                batch.get("created_at") or datetime.now(timezone.utc).isoformat()
            ),
            "count": len(manifest),
            "collected": False,
            "cost_usd": 0.0,
        })
        save_json(STATE, state)
        print(
            f"batch_id={batch_id} kind={ascii(theme)} count={len(manifest)}"
        )
        submitted += len(manifest)
    log(f"Submitted {submitted} requests")


def parse_score(message: dict) -> dict:
    text = "".join(
        block.get("text", "")
        for block in message.get("content", [])
        if block.get("type") == "text"
    ).strip()
    text = re.sub(r"\A```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\Z", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    score, reason = data.get("score"), data.get("reason")
    if type(score) is not int or not 0 <= score <= 3:
        raise ValueError("Expected an integer score in 0..3")
    if not isinstance(reason, str):
        raise ValueError("Expected a string reason")
    return {"score": score, "reason": reason}


def collect(batch_id: str) -> None:
    validate_batch_id(batch_id)
    entry = next(
        (item for item in read_state() if item["batch_id"] == batch_id), None
    )
    if entry is None:
        raise ValueError("Batch is not present in the local state file")
    manifest = json.loads(
        (MANIFESTS / f"{batch_id}.manifest.json").read_text(encoding="utf-8")
    )
    while True:
        batch = batch_status(batch_id)
        log(f"{batch_id}: {ascii(batch['processing_status'])}")
        if batch["processing_status"] == "ended":
            break
        time.sleep(60)
    if not batch.get("results_url"):
        raise ValueError("Ended batch has no results_url")

    counts = dict.fromkeys(
        ("succeeded", "errored", "parse_failed", "rows_written"), 0
    )
    total, seen, pending = 0.0, set(), []
    with http(batch["results_url"]) as response:
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
                log(f"{ascii(custom_id)}: {ascii(result['type'])}")
                continue
            counts["succeeded"] += 1
            message = result["message"]
            total += cost(entry["model"], message.get("usage") or {})
            meta = manifest.get(custom_id)
            if meta is None:
                counts["parse_failed"] += 1
                log(f"{ascii(custom_id)}: missing manifest entry")
                continue
            label = ascii(f"{meta['artist']} - {meta['title']}")
            try:
                if song_key(meta["artist"], meta["title"]) != meta["song_key"]:
                    raise ValueError("Manifest song key mismatch")
                if meta["source"] not in ("lyrics_tags", "title_only"):
                    raise ValueError("Invalid manifest source")
                parsed = parse_score(message)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                counts["parse_failed"] += 1
                log(
                    f"{ascii(custom_id)}: parse_failed {label}: "
                    f"{ascii(str(exc))}"
                )
                continue
            pending.append({
                "theme": entry["kind"],
                "song_key": meta["song_key"],
                "artist": meta["artist"],
                "title": meta["title"],
                "score": parsed["score"],
                "reason": parsed["reason"],
                "source": meta["source"],
                "model": entry["model"],
            })
            if len(pending) == 500:
                counts["rows_written"] += save_rows(pending)
                pending = []
    if pending:
        counts["rows_written"] += save_rows(pending)
    if seen != set(manifest):
        raise ValueError(
            "Results do not match the manifest; collection remains incomplete"
        )

    state = read_state()
    entry = next(item for item in state if item["batch_id"] == batch_id)
    entry.update(collected=True, cost_usd=total)
    save_json(STATE, state)
    print(
        " ".join(f"{name}={value}" for name, value in counts.items())
        + f" cost_usd={total:.6f}"
    )


def spotcheck(theme: str, high: int, low: int, seed: int) -> None:
    validate_theme(theme)
    with closing(connect_ro(NOTES_DB)) as db:
        scored = [
            dict(row)
            for row in db.execute(
                """SELECT song_key,artist,title,score,reason,source,model
                   FROM theme_sets WHERE theme=? ORDER BY song_key""",
                (theme,),
            )
        ]
    high_pool = [row for row in scored if row["score"] >= 2]
    low_pool = [
        row for row in scored
        if row["score"] == 0
        and any(word in (row["title"] or "").casefold() for word in TITLE_WORDS)
    ]
    rng = random.Random(seed)
    samples = {
        "high": rng.sample(high_pool, min(high, len(high_pool))),
        "low": rng.sample(low_pool, min(low, len(low_pool))),
    }
    selected = {
        row["song_key"] for group in samples.values() for row in group
    }
    tracks = {
        track["song_key"]: track
        for track in library_tracks()
        if track["song_key"] in selected
    }
    lyric_themes, instrumentals = lyric_context()
    results, agreements = [], {"high": 0, "low": 0}
    total = 0.0
    for group, sample in samples.items():
        for row in sample:
            track = tracks.get(row["song_key"], row)
            content, source = build_content(track, lyric_themes, instrumentals)
            params = message_params(theme, content, CHECK_MODEL)
            body = json.dumps(params, ensure_ascii=True).encode("utf-8")
            with http(MESSAGES_API, body) as response:
                message = json.load(response)
            usage = message.get("usage") or {}
            row_cost = 2 * cost(CHECK_MODEL, usage)
            total += row_cost
            checked = parse_score(message)
            agrees = (row["score"] >= 2) == (checked["score"] >= 2)
            agreements[group] += int(agrees)
            results.append({
                "group": group,
                "song_key": row["song_key"],
                "artist": row["artist"],
                "title": row["title"],
                "haiku_score": row["score"],
                "haiku_reason": row["reason"],
                "haiku_model": row["model"],
                "haiku_source": row["source"],
                "sonnet_score": checked["score"],
                "sonnet_reason": checked["reason"],
                "sonnet_model": CHECK_MODEL,
                "source": source,
                "content": content,
                "agreement": agrees,
                "usage": usage,
                "cost_usd": row_cost,
            })
            if not agrees:
                label = ascii(f"{row['artist']} - {row['title']}")
                print(
                    f"disagreement group={group} {label} "
                    f"haiku={row['score']} sonnet={checked['score']} "
                    f"haiku_reason={ascii(row['reason'])} "
                    f"sonnet_reason={ascii(checked['reason'])}"
                )

    n_high, n_low = len(samples["high"]), len(samples["low"])
    overall = (
        100 * sum(agreements.values()) / len(results) if results else None
    )
    summary = {
        "agreement_high": agreements["high"],
        "count_high": n_high,
        "agreement_low": agreements["low"],
        "count_low": n_low,
        "overall_percent": overall,
        "cost_usd": total,
    }
    filename = f"spotcheck_949_{theme}.json"
    save_json(ROOT / "data" / filename, {
        "theme": theme,
        "system": system_prompt(theme),
        "model": CHECK_MODEL,
        "seed": seed,
        "requested_high": high,
        "requested_low": low,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "results": results,
    })
    overall_text = f"{overall:.1f}%" if overall is not None else "n/a"
    print(
        f"agreement_high={agreements['high']}/{n_high} "
        f"agreement_low={agreements['low']}/{n_low} "
        f"overall={overall_text} cost_usd={total:.6f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    sub = commands.add_parser("submit")
    sub.add_argument("theme")
    sub.add_argument("--limit", type=int)
    sub.add_argument("--dry-run", action="store_true")

    for command in ("status", "collect"):
        commands.add_parser(command).add_argument("batch_id")

    sub = commands.add_parser("spotcheck")
    sub.add_argument("theme")
    sub.add_argument("--high", type=int, default=30)
    sub.add_argument("--low", type=int, default=20)
    sub.add_argument("--seed", type=int, default=949)

    args = parser.parse_args()
    if args.command == "submit":
        if args.limit is not None and args.limit < 0:
            raise ValueError("--limit must be nonnegative")
        submit(args.theme, args.limit, args.dry_run)
    elif args.command == "status":
        validate_batch_id(args.batch_id)
        print(json.dumps(batch_status(args.batch_id), ensure_ascii=True, indent=2))
    elif args.command == "collect":
        collect(args.batch_id)
    else:
        if args.high < 0 or args.low < 0:
            raise ValueError("--high and --low must be nonnegative")
        spotcheck(args.theme, args.high, args.low, args.seed)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        sys.exit(0 if exc.code in (None, 0) else 1)
    except (
        OSError, ValueError, RuntimeError, sqlite3.Error,
        KeyError, TypeError, AttributeError,
    ) as exc:
        log(f"Error: {ascii(str(exc))}")
        sys.exit(1)

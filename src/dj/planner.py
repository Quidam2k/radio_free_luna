"""Build candidate pools and plan themed Radio Free Luna sets."""

import json
import logging
import os
import re
from datetime import datetime, timedelta

from sqlalchemy import Text, cast, false, func, or_, select

from ..core.database import get_db, Track, TrackAnalysis
from . import llm_backend

logger = logging.getLogger(__name__)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "set": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "track_id": {"type": "integer"},
                    "why": {"type": "string"},
                },
                "required": ["track_id", "why"],
                "additionalProperties": False,
            },
        },
        "breaks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "before_index": {"type": "integer"},
                    "kind": {
                        "type": "string",
                        "enum": ["opening", "transition", "feature", "station_id", "none"],
                    },
                    "angle": {"type": "string"},
                },
                "required": ["before_index", "kind", "angle"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["set", "breaks"],
    "additionalProperties": False,
}


def enabled() -> bool:
    return os.getenv("DJ_PLANNER", "").strip().lower() == "anthropic"


def build_pool(theme: str, size: int = 120, now: datetime | None = None) -> list[dict]:
    if size <= 0:
        return []
    now = now if now is not None else datetime.utcnow()
    words = set(word for word in re.findall(r"\w+", theme.lower()) if len(word) >= 3)
    columns = (
        cast(TrackAnalysis.themes, Text), TrackAnalysis.summary,
        TrackAnalysis.lyrics, Track.title, Track.genre,
    )
    matches = or_(*(column.ilike(f"%{word}%") for word in words for column in columns)) if words else false()
    db = get_db()
    try:
        recent_artists = set(db.scalars(
            select(func.lower(Track.artist)).where(
                Track.last_played >= now - timedelta(hours=2),
                Track.artist.is_not(None),
            ).distinct()
        ))
        base = select(Track, TrackAnalysis, matches.label("match")).join(
            TrackAnalysis, TrackAnalysis.track_id == Track.id
        ).where(
            or_(Track.last_played.is_(None), Track.last_played < now - timedelta(hours=24)),
            Track.duration > 0, Track.duration <= 900,
        ).order_by(func.random())
        if recent_artists:
            base = base.where(or_(
                Track.artist.is_(None), func.lower(Track.artist).not_in(recent_artists)
            ))
        pool, seen, artist_counts = [], set(), {}
        for query in (base.where(matches).limit(size * 2 // 3), base):
            if seen:
                query = query.where(Track.id.not_in(seen))
            for track, analysis, is_match in db.execute(query):
                artist = (track.artist or "").lower()
                if track.id in seen or artist_counts.get(artist, 0) >= 3:
                    continue
                try:
                    themes = json.loads(analysis.themes) if isinstance(analysis.themes, str) else analysis.themes
                except (TypeError, ValueError):
                    themes = []
                item = {key: getattr(track, key) for key in (
                    "id", "title", "artist", "album", "year", "genre", "duration",
                    "file_path", "play_count", "last_played",
                )}
                item.update(
                    themes=themes if isinstance(themes, list) else [],
                    mood_valence=analysis.mood_valence,
                    energy_level=analysis.energy_level,
                    danceability=analysis.danceability,
                    summary=analysis.summary, cultural_context="", match=bool(is_match),
                )
                pool.append(item)
                seen.add(track.id)
                artist_counts[artist] = artist_counts.get(artist, 0) + 1
                if len(pool) >= size:
                    return pool
        return pool
    finally:
        db.close()


def _pool_listing(pool) -> str:
    lines = []
    for track in pool:
        energy, mood = track.get("energy_level"), track.get("mood_valence")
        e = f"{energy:.1f}" if energy is not None else "?"
        m = f"{mood:+.1f}" if mood is not None else "?"
        themes = ", ".join(str(value) if value is not None else "?" for value in (track.get("themes") or [])[:4])
        lines.append(
            f"{track.get('id', '?')} | {track.get('artist') or '?'} - "
            f"{track.get('title') or '?'} ({track.get('year') or '?'}) | "
            f"{track.get('genre') or '?'} | energy {e} mood {m} | themes: {themes or '?'}"
        )
    return "\n".join(lines)


def plan_set(theme: str, duration_minutes: int, context_summary: str,
             daypart: str, pool: list[dict] | None = None) -> dict:
    pool = pool or build_pool(theme)
    if not pool:
        raise ValueError("planner pool is empty")
    system = (
        "You program a late-night-radio-style freeform station. Build one set from "
        f"ONLY the listed track ids, about {duration_minutes} minutes long, with an "
        "arc of energy and mood suited to the daypart and theme; no artist twice "
        "in a set. Mark where the DJ should talk: an opening before index 0, "
        "transitions/features where a story connects two songs, station_id "
        "occasionally, and most gaps 'none'. Use zero-based set indexes. Each "
        "'angle' is one sentence on what the DJ talks about, grounded only in the listing."
    )
    user = (
        f"Theme: {theme}\nDaypart: {daypart}\nContext: {context_summary}\n"
        f"Target length: {duration_minutes} minutes\n\n"
        "Tracks (id | artist - title (year) | genre | energy/mood | themes):\n"
        f"{_pool_listing(pool)}"
    )
    body = {
        "model": llm_backend.planner_model(), "max_tokens": 8000, "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {
            "effort": "low", "format": {"type": "json_schema", "schema": PLAN_SCHEMA},
        },
    }
    response = llm_backend.anthropic_messages(body, purpose="planner")
    plan = json.loads(next(block["text"] for block in response["content"] if block["type"] == "text"))
    by_id = {track["id"]: track for track in pool}
    tracks, why, positions, seen_ids, artists = [], [], {}, set(), set()
    total = 0
    for index, entry in enumerate(plan["set"]):
        track = by_id.get(entry["track_id"])
        if track is None or track["id"] in seen_ids:
            continue
        artist = (track.get("artist") or "").lower()
        if artist in artists:
            continue
        positions[index] = len(tracks)
        tracks.append(track)
        why.append(str(entry["why"]))
        seen_ids.add(track["id"])
        artists.add(artist)
        total += track.get("duration") or 0
        if total >= duration_minutes * 60 + 300:
            break
    if len(tracks) < 3:
        raise ValueError("planner returned too few usable tracks")
    breaks = [
        {"before_index": positions[item["before_index"]], "kind": item["kind"], "angle": item["angle"]}
        for item in plan["breaks"]
        if item["before_index"] in positions and item["kind"] != "none"
    ]
    logger.info("Planner selected %d tracks and %d breaks", len(tracks), len(breaks))
    return {"tracks": tracks, "why": why, "breaks": breaks,
            "model": response["model"], "pool_size": len(pool)}

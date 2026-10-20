#!/usr/bin/env python3
"""Stockpile off-air DJ breaks for later reuse (#4164)."""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, ROOT)

logger = logging.getLogger("dj_practice")
KINDS = ("transition", "feature", "station_id")
DEFAULT_THEMES = ["halloween", "late night freeform", "songs about the road"]


class ASCIIFormatter(logging.Formatter):
    def format(self, record):
        return super().format(record).encode(
            "ascii", errors="backslashreplace"
        ).decode("ascii")


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def nonnegative_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def parse_args():
    parser = argparse.ArgumentParser(
        description="Practice DJ writing off-air; optionally save TTS audio."
    )
    parser.add_argument("--sets", type=positive_int, default=3)
    parser.add_argument("--minutes", type=positive_int, default=45)
    parser.add_argument(
        "--theme",
        action="append",
        help="Repeat to cycle through themes; defaults to three practice themes.",
    )
    parser.add_argument("--daypart", help="Override the context's daypart.")
    parser.add_argument(
        "--synthesize",
        action="store_true",
        help="Synthesize practice rows using an already running TTS service.",
    )
    parser.add_argument(
        "--synthesize-only",
        action="store_true",
        help="Skip planning and synthesize existing practice rows.",
    )
    parser.add_argument("--max-synth", type=nonnegative_int, default=40)
    return parser.parse_args()


async def load_context(settings):
    from src.context.context_manager import ContextManager
    from src.context.location import LocationAnalyzer
    from src.context.temporal import TemporalAnalyzer
    from src.context.weather import WeatherAnalyzer

    weather_analyzer = None
    location_analyzer = None
    try:
        temporal_analyzer = TemporalAnalyzer()
        weather_analyzer = WeatherAnalyzer(
            api_key=settings.weather_api_key,
            location=settings.location,
        )
        location_analyzer = LocationAnalyzer(
            location=settings.location,
            default_timezone=settings.timezone,
        )
        context_manager = ContextManager(
            weather_analyzer,
            location_analyzer,
            temporal_analyzer,
        )
        await context_manager.update_context()
        return context_manager.get_current_context() or {}
    except Exception as exc:
        logger.warning("Context unavailable; using empty context: %s", ascii(exc))
        return {}
    finally:
        for analyzer in (weather_analyzer, location_analyzer):
            if analyzer is not None:
                try:
                    await analyzer.close()
                except Exception as exc:
                    logger.warning("Context cleanup failed: %s", ascii(exc))


async def synthesize_pending(tts_config, max_synth, stats):
    from src.dj import spoken_store
    from src.voice import voice_policy
    from src.voice.tts_client import TTSWebUIClient

    client = TTSWebUIClient(tts_config)
    try:
        try:
            await client.initialize()
            reachable = await client.test_connection()
        except Exception as exc:
            logger.warning("TTS connection check failed: %s", ascii(exc))
            reachable = False

        if reachable is not True:
            print("TTS not reachable; practice lines stay text-only")
            return

        rows = await asyncio.to_thread(spoken_store.text_only, limit=max_synth)
        for row in rows:
            if row.get("origin") != "practice":
                continue
            if voice_policy.is_clone_voice(row["voice"]):
                stats["clone_refused"] += 1
                continue
            try:
                audio = await client.synthesize_speech(
                    row["text"],
                    {"voice": row["voice"]},
                    output="stream",
                    audience=[],
                )
                if audio:
                    await asyncio.to_thread(
                        spoken_store.set_audio, row["id"], audio
                    )
                    stats["synthesized"] += 1
            except Exception as exc:
                logger.warning(
                    "Synthesis failed for row %s: %s", row["id"], ascii(exc)
                )
    finally:
        try:
            await client.shutdown()
        except Exception as exc:
            logger.warning("TTS client shutdown failed: %s", ascii(exc))


async def main():
    args = parse_args()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        ASCIIFormatter("%(levelname)s %(name)s: %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    from src.core.config import settings
    from src.core.database import init_database
    from src.dj import planner, prerender, spoken_store
    from src.dj.commentary_generator import DJCommentaryGenerator
    from src.voice import voice_policy
    from src.voice.tts_config import TTSConfig

    tts_config = TTSConfig(
        api_url=settings.tts_webui_url,
        voice_model=settings.tts_voice_model,
        speed=settings.tts_speed,
        quality=settings.tts_quality,
    )
    stats = {
        "sets_planned": 0,
        "sets_failed": 0,
        "lines_saved": {kind: 0 for kind in KINDS},
        "clone_refused": 0,
        "synthesized": 0,
        "text_only_total": 0,
    }

    if not args.synthesize_only:
        context = await load_context(settings)
        generator = DJCommentaryGenerator(
            settings.openai_api_key, base_url=settings.openai_base_url
        )
        daypart = (
            args.daypart
            or getattr(context.get("temporal"), "time_of_day", None)
            or "afternoon"
        )
        summary = generator._build_context_summary(context)
        themes = args.theme or DEFAULT_THEMES

        try:
            await init_database(settings.database_url)
        except Exception as exc:
            logger.error("Planning database initialization failed: %s", ascii(exc))
            stats["sets_failed"] = args.sets
        else:
            for set_number in range(1, args.sets + 1):
                theme = themes[(set_number - 1) % len(themes)]
                try:
                    plan = await asyncio.to_thread(
                        planner.plan_set,
                        theme,
                        args.minutes,
                        summary,
                        daypart,
                    )
                    tracks = plan["tracks"]
                    breaks = plan["breaks"]
                except Exception as exc:
                    stats["sets_failed"] += 1
                    logger.warning(
                        "Set %d planning failed for %s: %s",
                        set_number,
                        ascii(theme),
                        ascii(exc),
                    )
                    continue

                stats["sets_planned"] += 1
                for brk in breaks:
                    kind = brk.get("kind")
                    index = brk.get("before_index")
                    if (
                        kind not in KINDS
                        or not isinstance(index, int)
                        or not 0 < index < len(tracks)
                    ):
                        continue

                    track = tracks[index]
                    prev = tracks[index - 1]
                    try:
                        seg = await prerender.write_text(
                            generator,
                            kind,
                            track,
                            prev,
                            context,
                            brk.get("angle", ""),
                        )
                        if (
                            seg is None
                            or not isinstance(seg.content, str)
                            or not seg.content.strip()
                        ):
                            continue

                        requested = (
                            generator._get_contextual_voice_settings(context).get(
                                "voice"
                            )
                            or tts_config.voice_model
                        )
                        voice = voice_policy.resolve_voice(
                            requested,
                            "stream",
                            tts_url=settings.tts_webui_url,
                            audience=[],
                        )
                        if voice_policy.is_clone_voice(voice):
                            stats["clone_refused"] += 1
                            continue

                        row = await asyncio.to_thread(
                            spoken_store.save,
                            seg.content,
                            None,
                            kind,
                            voice,
                            daypart,
                            track.get("id"),
                            prev.get("id") if kind == "transition" else None,
                            private=False,
                            origin="practice",
                        )
                        stats["lines_saved"][kind] += 1
                        prev_name = ascii(
                            f"{prev.get('artist') or '?'} - "
                            f"{prev.get('title') or '?'}"
                        )
                        track_name = ascii(
                            f"{track.get('artist') or '?'} - "
                            f"{track.get('title') or '?'}"
                        )
                        print(
                            f"set {set_number} {kind} "
                            f"{prev_name} -> {track_name} "
                            f"{ascii(row['text'][:80])}",
                            flush=True,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Set %d %s break failed: %s",
                            set_number,
                            kind,
                            ascii(exc),
                        )

    if args.synthesize or args.synthesize_only:
        await synthesize_pending(tts_config, args.max_synth, stats)

    text_rows = await asyncio.to_thread(spoken_store.text_only, limit=100000)
    stats["text_only_total"] = sum(
        row.get("origin") == "practice" for row in text_rows
    )
    print(json.dumps(stats, ensure_ascii=True, sort_keys=True))

    report_path = Path(ROOT) / "logs" / "dj_practice_last.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(stats, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )

    return int(
        not args.synthesize_only
        and stats["sets_planned"] == 0
        and stats["sets_failed"] == args.sets
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""
Usage ledger and hard spend caps for the Anthropic DJ backend (#4154).

Every API call is recorded in data/dj_spend.db (DJ_SPEND_DB). check() raises CapExceeded
when the rolling hour or day passes DJ_SPEND_HOURLY_USD (0.50) or DJ_SPEND_DAILY_USD (4.00).
Caps fail closed: the backend raises, callers fall back to templates, the music never stops.
The API credit is shared with other projects and has no card behind it, so over-spend
would stop the API for everything.
"""

import os
import sqlite3
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "dj_spend.db"
PRICES = {
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00},
}
_LOCK = threading.Lock()
_TOTALS_SQL = """
    SELECT COALESCE(SUM(CASE WHEN ts >= ? THEN cost_usd ELSE 0 END), 0),
           COALESCE(SUM(cost_usd), 0)
    FROM usage WHERE ts >= ?
"""


class CapExceeded(RuntimeError):
    pass


def cost_usd(model, input_tokens, output_tokens, cache_read=0, cache_write=0) -> float:
    tokens = (input_tokens, output_tokens, cache_read, cache_write)
    if any(not (0 <= value < float("inf")) for value in tokens):
        raise ValueError("Token counts must be finite and nonnegative")
    price = PRICES.get(model, PRICES["claude-opus-5-5"])
    return float((input_tokens * price["in"] + output_tokens * price["out"]
                  + cache_read * price["in"] * 0.1
                  + cache_write * price["in"] * 1.25) / 1_000_000)


def caps():
    hourly = float(os.environ.get("DJ_SPEND_HOURLY_USD", "0.50"))
    daily = float(os.environ.get("DJ_SPEND_DAILY_USD", "4.00"))
    if not all(0 <= cap < float("inf") for cap in (hourly, daily)):
        raise ValueError("Spend caps must be finite and nonnegative")
    return hourly, daily


def _connect(db_path=None):
    path = Path(db_path if db_path is not None
                else os.environ.get("DJ_SPEND_DB", DEFAULT_DB_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        with _LOCK:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY, ts REAL, model TEXT, purpose TEXT,
                    input_tokens INT, output_tokens INT, cache_read INT,
                    cache_write INT, cost_usd REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS usage_ts ON usage(ts)")
            conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def record(model, purpose, usage: dict, db_path=None) -> float:
    counts = tuple(int(usage.get(key) or 0) for key in (
        "input_tokens", "output_tokens", "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ))
    cost = cost_usd(model, *counts)
    conn = _connect(db_path)
    try:
        with _LOCK, conn:
            conn.execute("""
                INSERT INTO usage (ts, model, purpose, input_tokens,
                    output_tokens, cache_read, cache_write, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (time.time(), model, purpose, *counts, cost))
    finally:
        conn.close()
    return cost


def spent_since(seconds: float, now=None, db_path=None) -> float:
    now = time.time() if now is None else now
    conn = _connect(db_path)
    try:
        return float(conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM usage WHERE ts >= ?",
            (now - seconds,),
        ).fetchone()[0])
    finally:
        conn.close()


def check(now=None, db_path=None):
    now = time.time() if now is None else now
    hourly, daily = caps()
    conn = _connect(db_path)
    try:
        hour, day = conn.execute(
            _TOTALS_SQL, (now - 3600, now - 86400)
        ).fetchone()
    finally:
        conn.close()
    for name, spent, cap in (("Hourly", hour, hourly), ("Daily", day, daily)):
        if spent >= cap:
            raise CapExceeded(
                f"{name} spend cap exceeded: ${spent:.6f} >= ${cap:.6f}"
            )


def summary(now=None, db_path=None) -> dict:
    now = time.time() if now is None else now
    hourly, daily = caps()
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN")
        hour, day = conn.execute(
            _TOTALS_SQL, (now - 3600, now - 86400)
        ).fetchone()
        models = conn.execute("""
            SELECT model, COUNT(*), SUM(cost_usd), SUM(input_tokens),
                   SUM(output_tokens) FROM usage WHERE ts >= ? GROUP BY model
        """, (now - 86400,)).fetchall()
        purposes = conn.execute("""
            SELECT purpose, COUNT(*), SUM(cost_usd)
            FROM usage WHERE ts >= ? GROUP BY purpose
        """, (now - 86400,)).fetchall()
    finally:
        conn.close()
    return {
        "hour_usd": round(hour, 4), "day_usd": round(day, 4),
        "hourly_cap": hourly, "daily_cap": daily,
        "by_model_day": {
            model: {"calls": calls, "cost_usd": round(cost, 4),
                    "input_tokens": inputs, "output_tokens": outputs}
            for model, calls, cost, inputs, outputs in models
        },
        "by_purpose_day": {
            purpose: {"calls": calls, "cost_usd": round(cost, 4)}
            for purpose, calls, cost in purposes
        },
    }

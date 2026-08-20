"""MusicBrainz confirmation/correction for candidate artist/title pairs.

MusicBrainz is the primary research source because it is keyless and needs no
account — which matters here, since the audit found OPENAI_API_KEY is still a
placeholder and plan-back #8901 confirmed the enrichment path must be
AI-optional. Nothing in this module calls an LLM.

Rate limiting is not optional: MusicBrainz requires <=1 request/second and a
descriptive User-Agent, and will block clients that ignore either.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

MB_ENDPOINT = "https://musicbrainz.org/ws/2/recording"
USER_AGENT = "RadioFreeLuna-enrich/0.1 (https://github.com/Quidam2k/radio_free_luna)"
MIN_REQUEST_INTERVAL = 1.1  # seconds; MusicBrainz allows 1/sec, leave headroom


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _similar(a: str, b: str) -> float:
    """Cheap containment-based similarity; enough to sanity-check a match."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.85
    return 0.0


def _full_credit(artist_credit) -> Optional[str]:
    """Rebuild the complete artist credit, collaborators included.

    Taking artist-credit[0] alone silently drops everyone after the first name,
    turning 'Bakermat & Goldfish feat. Marie Plassard' into 'Bakermat'. Each
    entry carries the joinphrase ('&', ' feat. ') needed to reassemble it.
    """
    if not artist_credit:
        return None
    parts = []
    for entry in artist_credit:
        if isinstance(entry, str):
            parts.append(entry)
            continue
        name = entry.get("name") or (entry.get("artist") or {}).get("name")
        if name:
            parts.append(name)
        parts.append(entry.get("joinphrase") or "")
    return "".join(parts).strip() or None


@dataclass
class ResearchResult:
    matched: bool
    artist: Optional[str] = None
    title: Optional[str] = None
    release: Optional[str] = None
    year: Optional[str] = None
    mbid: Optional[str] = None
    score: int = 0
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)


class MusicBrainzResearcher:
    """Keyless MusicBrainz client with a shared rate limiter."""

    def __init__(self, min_interval: float = MIN_REQUEST_INTERVAL):
        self.min_interval = min_interval
        self._last_request = 0.0
        self._lock = asyncio.Lock()
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_count = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            headers={"User-Agent": USER_AGENT},
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    async def _rate_limit(self):
        """Serialize requests and space them out, even under concurrency."""
        async with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()

    async def lookup(self, artist: Optional[str], title: str) -> ResearchResult:
        """Look up one recording. Never raises — a failed lookup is a no-match."""
        if not title:
            return ResearchResult(matched=False, notes=["no title to search on"])

        if artist:
            query = f'artist:"{artist}" AND recording:"{title}"'
        else:
            query = f'recording:"{title}"'

        url = f"{MB_ENDPOINT}?query={quote(query)}&fmt=json&limit=5"

        try:
            await self._rate_limit()
            self.request_count += 1
            async with self.session.get(url) as resp:
                if resp.status == 503:
                    return ResearchResult(
                        matched=False, notes=["MusicBrainz rate-limited (503)"]
                    )
                if resp.status != 200:
                    return ResearchResult(
                        matched=False, notes=[f"MusicBrainz HTTP {resp.status}"]
                    )
                data = await resp.json()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"MusicBrainz lookup failed for {artist} - {title}: {e}")
            return ResearchResult(matched=False, notes=[f"lookup error: {e}"])

        return self._best_match(data, artist, title)

    def _best_match(self, data: Dict, artist: Optional[str], title: str) -> ResearchResult:
        recordings = data.get("recordings") or []
        if not recordings:
            return ResearchResult(matched=False, notes=["no MusicBrainz results"])

        best, best_conf = None, 0.0
        for rec in recordings:
            mb_artist = _full_credit(rec.get("artist-credit"))
            mb_title = rec.get("title") or ""
            score = int(rec.get("score", 0))

            title_sim = _similar(title, mb_title)
            # With no candidate artist, MusicBrainz's own score carries the match.
            artist_sim = _similar(artist, mb_artist) if artist else 0.5
            conf = (score / 100.0) * 0.4 + title_sim * 0.35 + artist_sim * 0.25

            if conf > best_conf:
                best, best_conf = (rec, mb_artist, mb_title, score), conf

        if best is None or best_conf < 0.55:
            return ResearchResult(
                matched=False,
                confidence=round(best_conf, 3),
                notes=["no MusicBrainz result cleared the confidence floor"],
            )

        rec, mb_artist, mb_title, score = best
        releases = rec.get("releases") or []
        release = releases[0].get("title") if releases else None
        date = rec.get("first-release-date") or (
            releases[0].get("date") if releases else None
        )
        year = date[:4] if date else None

        notes = []
        if artist and _similar(artist, mb_artist) < 1.0:
            notes.append(f"MusicBrainz corrected artist {artist!r} -> {mb_artist!r}")
        if _similar(title, mb_title) < 1.0:
            notes.append(f"MusicBrainz corrected title {title!r} -> {mb_title!r}")

        return ResearchResult(
            matched=True,
            artist=mb_artist,
            title=mb_title,
            release=release,
            year=year,
            mbid=rec.get("id"),
            score=score,
            confidence=round(best_conf, 3),
            notes=notes,
        )

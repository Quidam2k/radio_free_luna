"""Keyless sources for DJ notes: MusicBrainz, Wikidata, English Wikipedia (#6006).

Synchronous urllib on purpose: the batch is throttled to ~1 request/second per
host anyway, so async buys nothing, and staying stdlib keeps the batch runnable
from any interpreter. Every network call is a `get_json` so tests can swap the
client for a canned one.
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

USER_AGENT = "RadioFreeLuna-djnotes/0.1 (https://github.com/Quidam2k/radio_free_luna)"
MB = "https://musicbrainz.org/ws/2"
WIKIDATA = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKI_API = "https://en.wikipedia.org/w/api.php"

# MusicBrainz blocks clients above 1 req/s; Wikimedia asks for polite serial use.
HOST_INTERVAL = {"musicbrainz.org": 1.1, "www.wikidata.org": 0.5, "en.wikipedia.org": 0.5}


class HttpClient:
    """Serial JSON client with a per-host minimum interval. Never raises on HTTP."""

    def __init__(self, timeout: float = 20.0, intervals: Optional[Dict[str, float]] = None):
        self.timeout = timeout
        self.intervals = intervals or HOST_INTERVAL
        self._last: Dict[str, float] = {}
        self.requests = 0

    def get_json(self, url: str) -> Optional[Dict]:
        host = urllib.parse.urlsplit(url).netloc
        wait = self.intervals.get(host, 1.0) - (time.monotonic() - self._last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self._last[host] = time.monotonic()
            self.requests += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                if e.code != 404:
                    logger.warning("HTTP %s for %s", e.code, url)
                return None
            except Exception as e:  # network blip, bad JSON: fewer facts, never a crash
                if attempt < 2:
                    time.sleep(2)
                    continue
                logger.warning("fetch failed for %s: %s", url, e)
                return None
        return None


# --- MusicBrainz ----------------------------------------------------------------


# Compilations and live albums swamp the top results for a popular song and hide
# the original release; excluding them is what makes "first released" right.
ORIGINALS_ONLY = (' AND status:official AND -secondarytype:compilation'
                  ' AND -secondarytype:live AND -secondarytype:"dj-mix"')


def mb_search_recordings(client, artist: str, title: str, limit: int = 10,
                         originals_only: bool = False) -> List[Dict]:
    q = f'recording:"{title}" AND artist:"{artist}"' if artist else f'recording:"{title}"'
    if originals_only:
        q += ORIGINALS_ONLY
    data = client.get_json(f"{MB}/recording?" + urllib.parse.urlencode(
        {"query": q, "fmt": "json", "limit": limit}))
    return (data or {}).get("recordings") or []


def mb_recording(client, mbid: str) -> Optional[Dict]:
    return client.get_json(
        f"{MB}/recording/{mbid}?inc=work-rels+recording-rels+artist-credits+releases&fmt=json")


def mb_work(client, mbid: str) -> Optional[Dict]:
    return client.get_json(f"{MB}/work/{mbid}?inc=artist-rels+url-rels&fmt=json")


def mb_artist(client, mbid: str) -> Optional[Dict]:
    return client.get_json(f"{MB}/artist/{mbid}?inc=url-rels&fmt=json")


def wikidata_id(entity: Optional[Dict]) -> Optional[str]:
    """Q-id from a MusicBrainz work/artist's url relations."""
    for rel in (entity or {}).get("relations") or []:
        url = (rel.get("url") or {}).get("resource") or ""
        if rel.get("type") == "wikidata" and "/wiki/Q" in url:
            return url.rsplit("/", 1)[-1]
    return None


def wikipedia_url_from_rels(entity: Optional[Dict]) -> Optional[str]:
    for rel in (entity or {}).get("relations") or []:
        url = (rel.get("url") or {}).get("resource") or ""
        if rel.get("type") == "wikipedia" and "en.wikipedia.org/wiki/" in url:
            return url
    return None


# --- Wikidata / Wikipedia -------------------------------------------------------


def enwiki_title(client, qid: str) -> Optional[str]:
    data = client.get_json(WIKIDATA.format(qid=qid))
    ent = ((data or {}).get("entities") or {}).get(qid) or {}
    link = (ent.get("sitelinks") or {}).get("enwiki")
    return link.get("title") if link else None


def wiki_page_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def wiki_extracts(client, titles: List[str], intro_only: bool = False) -> Dict[str, str]:
    """Plain-text extracts keyed by resolved page title (redirects followed)."""
    params = {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
              "format": "json", "titles": "|".join(titles)}
    if intro_only:
        params.update({"exintro": 1, "exlimit": len(titles)})
    data = client.get_json(f"{WIKI_API}?" + urllib.parse.urlencode(params))
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    return {p["title"]: p.get("extract") or "" for p in pages.values()
            if "missing" not in p and p.get("extract")}


def wiki_search(client, query: str, limit: int = 5) -> List[str]:
    data = client.get_json(f"{WIKI_API}?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": query, "srlimit": limit,
         "format": "json"}))
    return [h["title"] for h in ((data or {}).get("query") or {}).get("search") or []]

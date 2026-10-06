"""Build sourced DJ notes for one song (#6006).

Pipeline per song:
  1. MusicBrainz recording search -> the earliest confident recording, preferring
     one linked to a work (the composition).
  2. Work -> writers, and the Wikidata id of the song.
  3. Wikidata -> English Wikipedia song article; failing that, a Wikipedia
     search that must name the artist and call the page a song/single.
  4. Facts = VERBATIM sentences from that article, picked by section, plus
     MusicBrainz facts (first release, writers, cover, samples) and a one-line
     artist intro. Each fact keeps the URL it came from.

No model rewrites anything, so nothing here can be invented; the worst case is
fewer facts. Lyrics are never stored (copyright) - a 'theme' fact is only ever
an encyclopedia sentence saying what the song is about.
"""

import re
from typing import Dict, List, Optional, Tuple

from src.notes import sources
from src.notes.store import clean_song_title, norm_artist, norm_title, _fold

MAX_FACT_CHARS = 300
MIN_FACT_CHARS = 40
MAX_WIKI_FACTS = 7
PER_SECTION = 2

# Section heading (lowercased, substring) -> fact kind. None = skip the section.
SECTION_KINDS = [
    ("track listing", None), ("personnel", None), ("credits", None), ("chart", None),
    ("certification", None), ("release history", None), ("formats", None),
    ("references", None), ("external links", None), ("see also", None), ("notes", None),
    ("sources", None), ("further reading", None), ("accolades", None), ("ranking", None),
    ("sample", "samples"), ("cover", "covers"), ("other version", "covers"),
    ("lyric", "theme"), ("theme", "theme"), ("meaning", "theme"), ("interpretation", "theme"),
    ("content", "theme"), ("composition", "theme"),
    ("recording", "recording"), ("production", "recording"),
    ("background", "history"), ("history", "history"), ("writing", "history"),
    ("inspiration", "history"), ("origin", "history"), ("release", "history"),
    ("music video", "history"), ("popular culture", "history"), ("in media", "history"),
    ("usage", "history"), ("legacy", "history"), ("live", "history"),
    ("reception", "reception"), ("commercial", "reception"), ("performance", "reception"),
]

_THEME_HINT = re.compile(r"\b(?:is about|was about|lyrics (?:describe|tell|are about)|"
                         r"song (?:describes|tells|concerns|deals with)|inspired by|written about)\b",
                         re.I)
_ABBREV = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|St|Jr|Sr|No|vs|Vol|feat|Mt|Ft|Co|Inc|Ltd)|\b[A-Z])\.$")
# Sentences that lean on the previous one ('One of them, ...', 'She wanted ...')
# make no sense read alone on air.
_DANGLING = re.compile(r"^(?:However|Also|Additionally|Meanwhile|He|She|They|Them|His|Her|Their|"
                       r"These|Those|This|That|One of them|The latter|The former|Both)\b")
_IPA_PAREN = re.compile(r"\s*\([^()]*[\[;:][^()]*\)")
_LONG_QUOTE = re.compile(r"[\"“][^\"”]{70,}[\"”]")


# --- text helpers ---------------------------------------------------------------


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?:(?<=[.!?])|(?<=[.!?][\"”)]))\s+(?=[A-Z0-9\"“(])", text.strip())
    out: List[str] = []
    for p in parts:
        if out and _ABBREV.search(out[-1]):
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    return [re.sub(r"\s+", " ", s).strip() for s in out if s.strip()]


def usable(sentence: str) -> bool:
    """Short, self-contained, and not a block of quoted lyrics."""
    if not (MIN_FACT_CHARS <= len(sentence) <= MAX_FACT_CHARS):
        return False
    if _LONG_QUOTE.search(sentence):
        return False
    if sentence.endswith(":") or "\n" in sentence:
        return False
    if _DANGLING.match(sentence):
        return False
    return True


def parse_sections(extract: str) -> List[Tuple[str, str]]:
    """[(heading, body)] with '' for the lead. Sub-sections keep their own heading."""
    sections, heading, buf = [], "", []
    for line in extract.splitlines():
        m = re.match(r"^\s*(=={1,4})\s*(.+?)\s*\1\s*$", line)
        if m:
            sections.append((heading, "\n".join(buf).strip()))
            heading, buf = m.group(2), []
        else:
            buf.append(line)
    sections.append((heading, "\n".join(buf).strip()))
    return [(h, b) for h, b in sections if b]


def section_kind(heading: str) -> Optional[str]:
    h = heading.lower()
    for needle, kind in SECTION_KINDS:
        if needle in h:
            return kind
    return "history"


def wiki_facts(extract: str, url: str, max_facts: int = MAX_WIKI_FACTS) -> List[Dict]:
    """Pick verbatim sentences: a lead summary, then a couple per useful section."""
    facts: List[Dict] = []
    seen = set()

    def add(sentence, kind):
        if sentence in seen or not usable(sentence):
            return False
        if _THEME_HINT.search(sentence):
            kind = "theme"
        seen.add(sentence)
        facts.append({"kind": kind, "text": sentence, "source_name": "Wikipedia",
                      "source_url": url})
        return True

    sections = parse_sections(extract)
    lead = [b for h, b in sections if h == ""]
    if lead:
        taken = 0
        for s in split_sentences(lead[0]):
            if taken >= 2:
                break
            taken += add(s, "summary")
        # A theme sentence anywhere in the lead is worth more than a chart position.
        for s in split_sentences(lead[0]):
            if _THEME_HINT.search(s):
                add(s, "theme")
                break
    for heading, body in sections:
        if heading == "" or len(facts) >= max_facts:
            continue
        kind = section_kind(heading)
        if kind is None:
            continue
        taken = 0
        for s in split_sentences(body):
            if taken >= PER_SECTION or len(facts) >= max_facts:
                break
            taken += add(s, kind)
    order = {"summary": 0, "theme": 1, "history": 2, "recording": 3, "samples": 4,
             "covers": 5, "reception": 6}
    facts.sort(key=lambda f: order.get(f["kind"], 9))
    return facts[:max_facts]


def artist_intro(extract: str, url: str) -> List[Dict]:
    lead = parse_sections(extract)
    if not lead or lead[0][0] != "":
        return []
    # Drop pronunciation/IPA and birth-date parentheticals: unreadable on air.
    for s in split_sentences(_IPA_PAREN.sub("", lead[0][1]))[:2]:
        if usable(s):
            return [{"kind": "artist", "text": s, "source_name": "Wikipedia", "source_url": url}]
    return []


# --- MusicBrainz ----------------------------------------------------------------


def _credit(artist_credit) -> str:
    parts = []
    for c in artist_credit or []:
        if isinstance(c, dict):
            parts.append((c.get("name") or (c.get("artist") or {}).get("name") or "")
                         + (c.get("joinphrase") or ""))
    return "".join(parts).strip()


def artist_matches(want: str, credit: str) -> bool:
    a, b = norm_artist(want), norm_artist(credit)
    return bool(a and b) and (a == b or a in b or b in a)


def title_matches(want: str, got: str) -> bool:
    a, b = norm_title(want), norm_title(got)
    if not (a and b):
        return False
    short, long_ = sorted((a, b), key=len)
    # Containment only when nearly the whole title matches: 'Lullaby' is not 'Lullaby of Birdland'.
    return a == b or (short in long_ and len(short) >= 0.8 * len(long_))


def rank_recordings(recordings: List[Dict], artist: str, title: str,
                    min_score: int = 85) -> List[Dict]:
    """Confident matches, earliest first-release first (originals before compilations)."""
    good = [r for r in recordings
            if int(r.get("score") or 0) >= min_score
            and title_matches(title, r.get("title") or "")
            and artist_matches(artist, _credit(r.get("artist-credit")))]
    return sorted(good, key=lambda r: (r.get("first-release-date") or "9999"))


def mb_facts(recording: Dict, work: Optional[Dict], first_date: Optional[str],
             release_title: Optional[str]) -> List[Dict]:
    facts: List[Dict] = []
    rec_url = f"https://musicbrainz.org/recording/{recording['id']}"
    performer = _credit(recording.get("artist-credit"))

    if first_date and first_date[:4].isdigit():
        text = f"First released in {first_date[:4]}"
        if release_title:
            text += f', on the album "{release_title}"'
        facts.append({"kind": "release", "text": text + ".", "source_name": "MusicBrainz",
                      "source_url": rec_url})

    is_cover = False
    for rel in recording.get("relations") or []:
        if rel.get("type") == "performance" and "cover" in (rel.get("attributes") or []):
            is_cover = True
        if rel.get("type") == "samples material" and rel.get("direction") == "forward":
            target = rel.get("recording") or {}
            who = _credit(target.get("artist-credit"))
            if target.get("title"):
                facts.append({
                    "kind": "samples",
                    "text": f'Samples "{target["title"]}"' + (f" by {who}." if who else "."),
                    "source_name": "MusicBrainz", "source_url": rec_url})

    if work:
        work_url = f"https://musicbrainz.org/work/{work['id']}"
        writers = []
        for rel in work.get("relations") or []:
            if rel.get("type") in ("writer", "composer", "lyricist") and rel.get("artist"):
                name = rel["artist"].get("name")
                if name and name not in writers:
                    writers.append(name)
        if writers:
            names = writers[0] if len(writers) == 1 else ", ".join(writers[:-1]) + " and " + writers[-1]
            if is_cover:
                facts.append({"kind": "cover_of",
                              "text": f"{performer}'s recording is a cover; the song was written by {names}.",
                              "source_name": "MusicBrainz", "source_url": work_url})
            else:
                facts.append({"kind": "writers", "text": f"Written by {names}.",
                              "source_name": "MusicBrainz", "source_url": work_url})
        elif is_cover:
            facts.append({"kind": "cover_of", "text": f"{performer}'s recording is a cover version.",
                          "source_name": "MusicBrainz", "source_url": rec_url})
    return facts


def first_release(recordings: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
    """(earliest date, studio album title or None) across confident recordings.

    Compilations, live albums and DJ mixes dominate MusicBrainz search results,
    so the album is only named when an original studio album (no secondary
    types) carries that same earliest year; otherwise we say the year alone.
    """
    dates = [r.get("first-release-date") for r in recordings
             if (r.get("first-release-date") or "")[:4].isdigit()]
    if not dates:
        return None, None
    first = min(dates)
    albums = []
    for r in recordings:
        for rel in r.get("releases") or []:
            rg = rel.get("release-group") or {}
            date = rel.get("date") or ""
            if (rg.get("primary-type") == "Album" and not rg.get("secondary-types")
                    and date[:4] == first[:4]):
                albums.append((date, rel.get("title")))
    return first, (min(albums)[1] if albums else None)


def _lists_title(release: Optional[Dict], title: str) -> bool:
    want = norm_title(title)
    return any(norm_title(t.get("title")) == want
               for m in (release or {}).get("media") or [] for t in m.get("tracks") or [])


def original_album(client, recordings: List[Dict], title: str, first: Optional[str],
                   max_groups: int = 3) -> Optional[Tuple[str, str]]:
    """(date, album) when a studio album older than `first` really carried the song.

    Search hits are often reissues (Armed Forces 1987 CD for a 1979 song) or a
    deluxe edition that adds the song as a bonus track to an older album (My
    Aim Is True 2026), so an older album only counts when one of the releases
    from its first year lists the title.
    """
    groups = {}
    for r in recordings:
        for rel in r.get("releases") or []:
            rg = rel.get("release-group") or {}
            if rg.get("id") and rg.get("primary-type") == "Album" and not rg.get("secondary-types"):
                groups.setdefault(rg["id"], rel.get("title"))
    found = []
    for rg_id in list(groups)[:max_groups]:
        rg = sources.mb_release_group(client, rg_id) or {}
        date = rg.get("first-release-date") or ""
        if not date[:4].isdigit() or (first and date[:4] >= first[:4]):
            continue
        early = sorted((rel.get("date") or "", rel["id"]) for rel in rg.get("releases") or []
                       if (rel.get("date") or "")[:4] == date[:4] and rel.get("id"))
        if any(_lists_title(sources.mb_release(client, rid), title) for _, rid in early[:3]):
            found.append((date, rg.get("title") or groups[rg_id]))
    return min(found) if found else None


# --- Wikipedia resolution -------------------------------------------------------


def find_song_article(client, artist: str, title: str, qid: Optional[str]) -> Optional[str]:
    """Resolved enwiki title for the song, or None. Wikidata first, then search."""
    if qid:
        t = sources.enwiki_title(client, qid)
        if t:
            return t
    clean = clean_song_title(title, artist)
    hits = sources.wiki_search(client, f'"{clean}" {artist} song')
    want = norm_title(clean)
    cands = [h for h in hits if _fold(re.sub(r"\s*\(.*?\)\s*", "", h)) == want]
    if not cands:
        return None
    intros = sources.wiki_extracts(client, cands[:4], intro_only=True)
    a = norm_artist(artist)
    for name in cands[:4]:
        intro = intros.get(name, "")
        lead = _fold(intro[:600])
        if a and a in lead and re.search(r"\b(?:song|single|track|ballad|anthem)\b", intro[:600], re.I):
            return name
    return None


# --- the whole song -------------------------------------------------------------


class SongEnricher:
    def __init__(self, client=None):
        self.client = client or sources.HttpClient()
        self._artist_cache: Dict[str, List[Dict]] = {}

    def _artist_facts(self, artist_id: Optional[str]) -> List[Dict]:
        if not artist_id:
            return []
        if artist_id not in self._artist_cache:
            facts: List[Dict] = []
            ent = sources.mb_artist(self.client, artist_id)
            qid = sources.wikidata_id(ent)
            t = sources.enwiki_title(self.client, qid) if qid else None
            if t:
                ext = sources.wiki_extracts(self.client, [t], intro_only=True)
                if ext:
                    name, text = next(iter(ext.items()))
                    facts = artist_intro(text, sources.wiki_page_url(name))
            self._artist_cache[artist_id] = facts
        return self._artist_cache[artist_id]

    def enrich(self, artist: str, title: str) -> Dict:
        """-> {status, detail, facts, ids}. Never raises for a network failure."""
        clean = clean_song_title(title, artist)
        if not clean or not artist or norm_artist(artist) in ("variousartists", "unknownartist", "unknown"):
            return {"status": "nomatch", "detail": "no usable artist/title", "facts": [], "ids": {}}

        recs = rank_recordings(sources.mb_search_recordings(
            self.client, artist, clean, limit=25, originals_only=True), artist, clean)
        if not recs:
            recs = rank_recordings(sources.mb_search_recordings(
                self.client, artist, clean, limit=25), artist, clean)
        recording, work = None, None
        for cand in recs[:3]:
            full = sources.mb_recording(self.client, cand["id"])
            if not full:
                continue
            if recording is None:
                recording = full
            wrel = [r for r in full.get("relations") or [] if r.get("type") == "performance" and r.get("work")]
            if wrel:
                recording = full
                work = sources.mb_work(self.client, wrel[0]["work"]["id"])
                break

        ids: Dict = {}
        facts: List[Dict] = []
        artist_id = None
        if recording:
            ids["mb_recording"] = recording["id"]
            date, album = first_release(recs)
            older = original_album(self.client, recs, clean, date)
            if older:
                date, album = older
            facts += mb_facts(recording, work, date, album)
            ac = recording.get("artist-credit") or []
            if ac and isinstance(ac[0], dict):
                artist_id = (ac[0].get("artist") or {}).get("id")
        if work:
            ids["mb_work"] = work["id"]

        qid = sources.wikidata_id(work)
        if qid:
            ids["wikidata"] = qid
        article = find_song_article(self.client, artist, clean, qid)
        wiki: List[Dict] = []
        if article:
            ext = sources.wiki_extracts(self.client, [article])
            if ext:
                name, text = next(iter(ext.items()))
                ids["wiki_url"] = sources.wiki_page_url(name)
                wiki = wiki_facts(text, ids["wiki_url"])

        artist_facts = self._artist_facts(artist_id)
        # Encyclopedia prose first, then MusicBrainz specifics, then the artist intro.
        facts = wiki + facts + artist_facts
        for i, f in enumerate(facts):
            f["rank"] = i
        if not recording and not article:
            return {"status": "nomatch", "detail": "no MusicBrainz or Wikipedia match",
                    "facts": [], "ids": ids}
        return {"status": "ok", "detail": None, "facts": facts, "ids": ids}

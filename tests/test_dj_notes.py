"""Tests for per-track sourced DJ notes (#6006). No network: a canned client
stands in for MusicBrainz / Wikidata / Wikipedia.

What matters most: every stored fact carries a source, nothing is made up when
the sources are silent, and the read path never raises for a caller.
"""

import asyncio
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.notes import enrich, store
from src.notes.enrich import SongEnricher, split_sentences, usable, wiki_facts

ROOT = Path(__file__).resolve().parent.parent

WIKI_EXTRACT = """"Jump Around" is a song by American hip hop group House of Pain, released in May 1992 as the first single from their debut album. The song is popular among dancehall DJs and is widely regarded in the United Kingdom as a club classic.

== Background ==
DJ Muggs has stated that he originally produced the beat for Cypress Hill, but rapper B-Real could not come up with the lyrics. It was subsequently offered to Ice Cube, who refused it, before finally being taken and used by House of Pain.

=== Samples ===
The song features a distinctive horn fanfare intro, sampled from Bob & Earl's 1963 track "Harlem Shuffle". However, the origin of the squeal is debated.

== Track listing ==
"Jump Around" (radio edit) - 3:38 and some other listing text that is long enough.

== Charts ==
The song reached number three on the Billboard Hot 100 in the United States that year.
"""

ARTIST_EXTRACT = "House of Pain (pronounced [haʊs]; formed 1991) was an American hip-hop trio. They were known for Jump Around."


class FakeClient:
    """Routes URLs to canned JSON by substring; records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = 0
        self.urls = []

    def get_json(self, url):
        self.requests += 1
        self.urls.append(url)
        for needle, payload in self.routes:
            if needle in url:
                return payload
        return None


def _recording(rid, date, secondary=None, rels=None):
    return {
        "id": rid, "score": 100, "title": "Jump Around", "first-release-date": date,
        "artist-credit": [{"name": "House of Pain", "artist": {"id": "art-1", "name": "House of Pain"}}],
        "releases": [{"title": "House of Pain", "date": date,
                      "release-group": {"primary-type": "Album", "secondary-types": secondary or []}}],
        "relations": rels or [],
    }


def jump_around_routes():
    work_rel = {"type": "performance", "attributes": [], "work": {"id": "work-1"}}
    sample_rel = {"type": "samples material", "direction": "forward",
                  "recording": {"title": "Harlem Shuffle", "artist-credit": [{"name": "Bob & Earl"}]}}
    return [
        ("/recording?", {"recordings": [
            _recording("rec-late", "2010-02-07", ["Compilation"]),
            _recording("rec-1", "1992-05-05"),
        ]}),
        ("/recording/rec-1", _recording("rec-1", "1992-05-05", rels=[work_rel, sample_rel])),
        ("/recording/rec-late", _recording("rec-late", "2010-02-07")),
        ("/work/work-1", {"id": "work-1", "relations": [
            {"type": "writer", "artist": {"name": "Erik Schrody"}},
            {"type": "writer", "artist": {"name": "Larry Muggerud"}},
            {"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q3811222"}},
        ]}),
        ("/artist/art-1", {"relations": [
            {"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q99"}}]}),
        ("Q3811222.json", {"entities": {"Q3811222": {"sitelinks": {"enwiki": {"title": "Jump Around"}}}}}),
        ("Q99.json", {"entities": {"Q99": {"sitelinks": {"enwiki": {"title": "House of Pain"}}}}}),
        ("titles=House+of+Pain", {"query": {"pages": {"2": {"title": "House of Pain", "extract": ARTIST_EXTRACT}}}}),
        ("titles=Jump+Around", {"query": {"pages": {"1": {"title": "Jump Around", "extract": WIKI_EXTRACT}}}}),
    ]


# --- normalization / matching ---------------------------------------------------


@pytest.mark.parametrize("artist,title,expected", [
    ("House Of Pain", "Jump Around", "houseofpain|jumparound"),
    ("The Cure", "Lullaby (Remastered 2010)", "cure|lullaby"),
    ("Mark Knopfler", "05 - Mark Knopfler - Devil Baby", "markknopfler|devilbaby"),
    ("Colin Hay", "Beautiful World (Alternate Mix", "colinhay|beautifulworld"),
    ("Simon & Garfunkel", "The Boxer - 2001 Remaster", "simonandgarfunkel|theboxer"),
    ("Bjork feat. Moby", "Big Time Sensuality", "bjork|bigtimesensuality"),
    ("Björk", "Big Time Sensuality", "bjork|bigtimesensuality"),
])
def test_song_key_normalizes_library_tags(artist, title, expected):
    assert store.song_key(artist, title) == expected


def test_title_match_rejects_different_song():
    assert enrich.title_matches("Jump Around", "Jump Around (radio edit)")
    assert not enrich.title_matches("Lullaby", "Lullaby of Birdland")


# --- sentence selection ---------------------------------------------------------


def test_split_sentences_keeps_abbreviations_together():
    s = split_sentences('It reached No. 2 on the chart. Dr. John played on it. "Wow." Next one.')
    assert s[0] == "It reached No. 2 on the chart."
    assert s[1] == "Dr. John played on it."


def test_usable_rejects_lyric_blocks_and_dangling_sentences():
    assert not usable('The chorus goes "I\'ll be there for you when the rain starts to pour and the night is long and cold".')
    assert not usable("She wanted him to play his parts on it with the old amplifier found in the studio.")
    assert not usable("Short.")
    assert usable("DJ Muggs has stated that he originally produced the beat for Cypress Hill.")


def test_wiki_facts_are_verbatim_sourced_and_skip_listing_sections():
    facts = wiki_facts(WIKI_EXTRACT, "https://en.wikipedia.org/wiki/Jump_Around")
    texts = [f["text"] for f in facts]
    assert all(f["source_name"] == "Wikipedia" and f["source_url"] for f in facts)
    assert all(t in WIKI_EXTRACT for t in texts)  # verbatim, never rewritten
    assert facts[0]["kind"] == "summary"
    assert any(f["kind"] == "samples" and "Harlem Shuffle" in f["text"] for f in facts)
    assert not any("radio edit" in t for t in texts)          # track listing skipped
    assert not any(t.startswith("However") for t in texts)   # dangling sentence skipped
    assert any(f["kind"] == "reception" for f in facts) is False  # charts section skipped


# --- whole-song enrichment ------------------------------------------------------


def test_enrich_song_end_to_end_with_canned_sources():
    client = FakeClient(jump_around_routes())
    r = SongEnricher(client).enrich("House Of Pain", "Jump Around")
    assert r["status"] == "ok"
    assert r["ids"]["mb_recording"] == "rec-1"      # earliest original, not the 2010 compilation
    assert r["ids"]["wikidata"] == "Q3811222"
    by_kind = {}
    for f in r["facts"]:
        by_kind.setdefault(f["kind"], []).append(f["text"])
        assert f["source_url"].startswith("https://")
    assert by_kind["release"] == ['First released in 1992, on the album "House of Pain".']
    assert by_kind["writers"] == ["Written by Erik Schrody and Larry Muggerud."]
    assert 'Samples "Harlem Shuffle" by Bob & Earl.' in by_kind["samples"]
    assert by_kind["artist"] == ["House of Pain was an American hip-hop trio."]  # IPA paren dropped
    assert r["facts"][0]["kind"] == "summary"  # encyclopedia prose leads


def test_enrich_cover_is_labelled():
    routes = jump_around_routes()
    rec = _recording("rec-1", "1992-05-05", rels=[
        {"type": "performance", "attributes": ["cover"], "work": {"id": "work-1"}}])
    routes = [(k, rec if k == "/recording/rec-1" else v) for k, v in routes]
    r = SongEnricher(FakeClient(routes)).enrich("House Of Pain", "Jump Around")
    covers = [f["text"] for f in r["facts"] if f["kind"] == "cover_of"]
    assert covers == ["House of Pain's recording is a cover; the song was written by Erik Schrody and Larry Muggerud."]


def test_enrich_silent_sources_invent_nothing():
    r = SongEnricher(FakeClient([])).enrich("Nobody", "Unknown Song")
    assert r == {"status": "nomatch", "detail": "no MusicBrainz or Wikipedia match", "facts": [], "ids": {}}


def test_enrich_skips_various_artists_without_network():
    client = FakeClient([])
    r = SongEnricher(client).enrich("Various Artists", "Shining Star")
    assert r["status"] == "nomatch" and client.requests == 0


def test_search_fallback_requires_artist_and_song_in_lead():
    routes = [
        ("list=search", {"query": {"search": [{"title": "Devil Baby"}, {"title": "Devil Baby (film)"}]}}),
        ("exintro", {"query": {"pages": {
            "1": {"title": "Devil Baby", "extract": "Devil Baby is a 1990s horror film."},
            "2": {"title": "Devil Baby (film)", "extract": "A film."}}}}),
    ]
    assert enrich.find_song_article(FakeClient(routes), "Mark Knopfler", "Devil Baby", None) is None


# --- store + read path ----------------------------------------------------------


def test_store_roundtrip_and_title_only_fallback(tmp_path):
    db = tmp_path / "notes.db"
    with store.NotesStore(db) as s:
        s.save("House Of Pain", "Jump Around", "ok", [
            {"kind": "summary", "text": "A song.", "source_name": "Wikipedia", "source_url": "https://w/1"},
            {"kind": "history", "text": "No source here."},  # unsourced -> dropped
        ], mb_recording="rec-1")
        assert s.has(store.song_key("House of Pain", "Jump Around"))
    notes = store.lookup("house of pain", "Jump Around (Official Video)", db_path=db)
    assert notes["found"] and notes["matched_by"] == "artist+title"
    assert [f["text"] for f in notes["facts"]] == ["A song."]
    # 'Various Artists' tag in the player still finds the unique title
    va = store.lookup("Various Artists", "Jump Around", db_path=db)
    assert va["found"] and va["matched_by"] == "title-only"


def test_title_only_fallback_refuses_ambiguous_titles(tmp_path):
    db = tmp_path / "notes.db"
    fact = [{"kind": "summary", "text": "x", "source_name": "W", "source_url": "https://w"}]
    with store.NotesStore(db) as s:
        s.save("Artist A", "Home", "ok", fact)
        s.save("Artist B", "Home", "ok", fact)
    assert store.lookup("Artist C", "Home", db_path=db)["found"] is False


def test_add_facts_appends_without_duplicates(tmp_path):
    db = tmp_path / "notes.db"
    f = {"kind": "history", "text": "Recorded in one take.", "source_name": "Rolling Stone",
         "source_url": "https://example.org/a"}
    with store.NotesStore(db) as s:
        assert s.add_facts("Rush", "Animate", [f, f]) == 1
        assert s.add_facts("Rush", "Animate", [f]) == 0
    assert store.lookup("Rush", "Animate", db_path=db)["facts"][0]["source"] == "Rolling Stone"


def test_lookup_fails_open(tmp_path):
    assert store.lookup("a", "b", db_path=tmp_path / "missing.db")["facts"] == []
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a sqlite database at all" * 100)
    assert store.lookup("a", "b", db_path=bad)["facts"] == []
    assert store.lookup("a", "", db_path=bad)["facts"] == []


def test_lookup_cli_json_and_missing_db(tmp_path):
    db = tmp_path / "notes.db"
    with store.NotesStore(db) as s:
        s.save("Rush", "Animate", "ok", [
            {"kind": "summary", "text": "A Rush song.", "source_name": "Wikipedia", "source_url": "https://w/a"}])
    out = subprocess.run([sys.executable, "-m", "src.notes.lookup", "--db", str(db),
                          "--artist", "Rush", "--title", "Animate", "--json"],
                         cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and json.loads(out.stdout)["facts"][0]["text"] == "A Rush song."
    miss = subprocess.run([sys.executable, "-m", "src.notes.lookup", "--db", str(tmp_path / "nope.db"),
                           "--title", "X", "--json"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert miss.returncode == 0 and json.loads(miss.stdout)["found"] is False


def test_mcp_tool_formats_sourced_lines(tmp_path, monkeypatch):
    db = tmp_path / "notes.db"
    with store.NotesStore(db) as s:
        s.save("Rush", "Animate", "ok", [
            {"kind": "summary", "text": "A Rush song.", "source_name": "Wikipedia", "source_url": "https://w/a"}])
    pytest.importorskip("mcp")  # the MCP servers run under an interpreter with mcp; .venv lacks it
    monkeypatch.setattr(store, "DEFAULT_DB", db)
    from rfl_mcp.toolkit import rfl_track_notes
    out = asyncio.run(rfl_track_notes("Rush", "Animate"))
    assert "- A Rush song. (Wikipedia: https://w/a)" in out
    assert asyncio.run(rfl_track_notes("Nobody", "Nothing")).startswith("No notes")


# --- RFL's own DJ uses the notes (#431: RFL-first) ------------------------------


def test_commentary_uses_sourced_facts(tmp_path, monkeypatch):
    from src.dj.commentary_generator import DJCommentaryGenerator

    db = tmp_path / "notes.db"
    with store.NotesStore(db) as s:
        s.save("Rush", "Animate", "ok", [
            {"kind": "summary", "text": "Animate is a 1993 Rush song.", "source_name": "Wikipedia",
             "source_url": "https://w/a"}])
    monkeypatch.setattr(store, "DEFAULT_DB", db)
    gen = DJCommentaryGenerator(openai_api_key="test-key")
    rush, other = {"artist": "Rush", "title": "Animate"}, {"artist": "X", "title": "Y"}
    assert "Animate is a 1993 Rush song. (Wikipedia)" in gen._build_transition_prompt(other, rush, {}, {})
    assert "say nothing specific" in gen._build_transition_prompt(rush, other, {}, {})
    fb = gen._create_fallback_transition(other, rush, {})
    assert fb.content == "Coming up, Animate by Rush. Animate is a 1993 Rush song."
    assert gen._create_fallback_feature(rush, "song_story").content == "Animate is a 1993 Rush song."


def test_batch_save_keeps_research_facts_and_still_enriches_stub(tmp_path):
    db = tmp_path / "notes.db"
    web = {"kind": "trivia", "text": "Recorded in a barn.", "source_name": "Songfacts",
           "source_url": "https://example.org/b"}
    auto = {"kind": "summary", "text": "A song by Rush.", "source_name": "Wikipedia",
            "source_url": "https://w/a"}
    with store.NotesStore(db) as s:
        s.add_facts("Rush", "Animate", [web])
        key = store.song_key("Rush", "Animate")
        assert not s.has(key)  # research-only stub: the batch still owes it a pass
        s.save("Rush", "Animate", "ok", [auto])
        s.save("Rush", "Animate", "ok", [auto])  # a --redo replaces only batch facts
        assert s.has(key)
    texts = [f["text"] for f in store.lookup("Rush", "Animate", db_path=db)["facts"]]
    assert texts == ["A song by Rush.", "Recorded in a barn."]


# --- wrong-version guard (#3522) -------------------------------------------------


def _f(kind, text, source="Wikipedia"):
    return {"kind": kind, "text": text, "source": source, "url": "https://x"}


COSTELLO = [
    _f("summary", "\"(What's So Funny 'Bout) Peace, Love, and Understanding\" is a 1974 song "
                  "written by English singer/songwriter Nick Lowe."),
    _f("history", "Initially released by Lowe with his band Brinsley Schwarz on their 1974 album."),
    _f("history", "And that was amazing—I'm amazed nowadays, looking back, that I did that.\""),
    _f("history", "It reached number 3 on the UK charts."),
    _f("recording", "Costello and the Attractions recorded it during the sessions for Armed Forces."),
    _f("release", 'First released in 1979, on the album "Armed Forces".', "MusicBrainz"),
    _f("writers", "Written by Nick Lowe.", "MusicBrainz"),
    _f("cover_of", "Elvis Costello's recording is a cover; the song was written by Nick Lowe.",
       "MusicBrainz"),
]


def test_version_guard_drops_unlabelled_facts_about_the_original():
    kept, info = store.version_guard(COSTELLO, "Elvis Costello")
    assert info["is_cover"] and info["dropped"] == 2
    texts = [f["text"] for f in kept]
    assert not any("amazed" in t or "UK charts" in t for t in texts)
    assert any(t.startswith("Initially released by Lowe") for t in texts)  # labelled -> kept
    assert len(kept) == 6


def test_version_guard_detects_cover_from_wikipedia_wording():
    facts = [
        _f("summary", '"Hurt" is a song by American industrial rock band Nine Inch Nails.'),
        _f("history", "The song was originally recorded by Nine Inch Nails in 1994."),
        _f("reception", "It peaked at number 1 on the charts."),
        _f("recording", "Cash recorded it in 2002 with producer Rick Rubin."),
    ]
    assert store.original_performers(facts, "Johnny Cash") == ["Nine Inch Nails"]
    kept, info = store.version_guard(facts, "Johnny Cash")
    assert info["dropped"] == 1 and "peaked" not in " ".join(f["text"] for f in kept)


def test_version_guard_leaves_originals_and_generic_tags_alone():
    rush = [_f("summary", '"The Big Wheel" is a song by Canadian rock band Rush.'),
            _f("history", "It was first performed by the band live in 1991."),
            _f("reception", "It charted at No. 5.")]
    assert store.version_guard(rush, "Rush") == (rush, {"is_cover": False, "dropped": 0, "original": []})
    kept, info = store.version_guard(COSTELLO, "Various Artists")
    assert kept == COSTELLO and info["dropped"] == 0


def test_mentions_artist_whole_words_and_surnames():
    assert store.mentions_artist("Rush rushed the tempo", "Rush")
    assert not store.mentions_artist("they rushed it", "Rush")
    assert store.mentions_artist("Costello sang", "Elvis Costello & the Attractions")
    assert store.mentions_artist("The Police toured", "Police")


def test_lookup_applies_guard_and_refuses_cross_artist_title_only(tmp_path):
    db = tmp_path / "notes.db"
    with store.NotesStore(db) as s:
        s.save("Elvis Costello", "Peace, Love and Understanding", "ok",
               [{"kind": f["kind"], "text": f["text"], "source_name": f["source"],
                 "source_url": f["url"]} for f in COSTELLO])
    notes = store.lookup("Elvis Costello", "Peace, Love and Understanding", db_path=db, limit=20)
    assert notes["version_guard"]["dropped"] == 2 and len(notes["facts"]) == 6
    # Nick Lowe (the original, named in the article) gets the song facts, never
    # the MusicBrainz facts about Costello's recording; an unrelated artist gets nothing
    lowe = store.lookup("Nick Lowe", "Peace, Love and Understanding", db_path=db, limit=20)
    assert lowe["matched_by"] == "title-only" and lowe["facts"]
    assert all(f["source"] != "MusicBrainz" for f in lowe["facts"])
    assert store.lookup("Bob Smith", "Peace, Love and Understanding", db_path=db)["found"] is False
    assert store.lookup("", "Peace, Love and Understanding", db_path=db)["found"] is True


def test_title_only_original_artist_keeps_song_facts_from_cover_row(tmp_path):
    # #6038 mirror: Supertramp playing, only the Goo Goo Dolls cover is stored
    db = tmp_path / "notes.db"
    rows = [("summary", '"Give a Little Bit" is the opening song on a 1977 album by Supertramp.', "Wikipedia"),
            ("history", "The song was written years before the band recorded it.", "Wikipedia"),
            ("release", "First released in 2005.", "MusicBrainz"),
            ("cover_of", "The Goo Goo Dolls's recording is a cover.", "MusicBrainz"),
            ("artist", "Goo Goo Dolls are an American rock band formed in 1986 in Buffalo, New York.",
             "Wikipedia")]
    with store.NotesStore(db) as s:
        s.save("Goo Goo Dolls", "Give A Little Bit", "ok",
               [{"kind": k, "text": t, "source_name": src, "source_url": "https://x"} for k, t, src in rows])
    got = store.lookup("Supertramp", "Give A Little Bit", db_path=db)
    # #4056: only facts that NAME the playing artist; "the band" could be either
    assert sorted(f["kind"] for f in got["facts"]) == ["summary"]
    assert got["artist"] == "Supertramp" and got["version_guard"]["stored_artist"] == "Goo Goo Dolls"
    assert store.lookup("Goo Goo Dolls", "Give A Little Bit", db_path=db)["found"]
    # a non-cover row never lends its facts to a different artist
    with store.NotesStore(db) as s:
        s.save("Example Band", "Oslo Nights", "ok", [
            {"kind": "summary", "text": '"Oslo Nights" is a song by Example Band.',
             "source_name": "Wikipedia", "source_url": "https://x"}])
    assert store.lookup("Other Band", "Oslo Nights", db_path=db)["found"] is False


def test_title_only_cover_row_never_lends_its_own_facts_to_the_original(tmp_path):
    # #4056 (Todd 2026-10-08): Kate Bush playing, only a cover row stored; the
    # cover's chart run was read out as Kate Bush's under a header naming the cover act.
    db = tmp_path / "notes.db"
    rows = [("summary", '"Running Up That Hill" is a song by English singer Kate Bush.', "Wikipedia"),
            ("chart", "The single reached number 9 in the UK in 2003.", "Wikipedia"),
            ("history", "The band recorded it in one take in London.", "Wikipedia"),
            ("cover_of", "Placebo's recording is a cover.", "MusicBrainz")]
    with store.NotesStore(db) as s:
        s.save("Placebo", "Running Up That Hill", "ok",
               [{"kind": k, "text": t, "source_name": src, "source_url": "https://x"} for k, t, src in rows])
    got = store.lookup("Kate Bush", "Running Up That Hill", db_path=db)
    assert [f["kind"] for f in got["facts"]] == ["summary"]
    assert got["artist"] == "Kate Bush"


def test_title_strip_drops_video_suffix():
    assert store.clean_song_title("Little Blue | @MahoganySessions") == "Little Blue"


# --- first release: reissues and bonus tracks ------------------------------------


def test_original_album_prefers_older_album_that_really_had_the_song(monkeypatch):
    recs = [{"releases": [
        {"title": "Armed Forces", "date": "1987-07-13",
         "release-group": {"id": "rg-af", "primary-type": "Album", "secondary-types": []}},
        {"title": "My Aim Is True", "date": "2026-10-02",
         "release-group": {"id": "rg-maint", "primary-type": "Album", "secondary-types": []}}]}]
    groups = {
        "rg-af": {"title": "Armed Forces", "first-release-date": "1979-01-05",
                  "releases": [{"id": "uk", "date": "1979-01-05"}, {"id": "us", "date": "1979-01-19"}]},
        "rg-maint": {"title": "My Aim Is True", "first-release-date": "1977-07-22",
                     "releases": [{"id": "maint", "date": "1977-07-22"}]},
    }
    tracks = {"uk": ["Accidents Will Happen"], "us": ["(What's So Funny 'Bout) Peace, Love and Understanding"],
              "maint": ["Alison"]}
    monkeypatch.setattr(enrich.sources, "mb_release_group", lambda c, i: groups[i])
    monkeypatch.setattr(enrich.sources, "mb_release", lambda c, i: {
        "media": [{"tracks": [{"title": t} for t in tracks[i]]}]})
    got = enrich.original_album(None, recs, "Peace, Love and Understanding", "1987-07-13")
    assert got == ("1979-01-05", "Armed Forces")  # not the 1977 bonus-track album

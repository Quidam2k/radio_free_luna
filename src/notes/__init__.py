"""Per-track sourced DJ notes (#6006): store, keyless enrichment, fail-open lookup.

  store   — SQLite store at data/dj_notes.db; stdlib-only lookup() for any caller
  sources — throttled MusicBrainz / Wikidata / Wikipedia JSON client
  enrich  — one song -> verbatim, source-linked facts (no model rewriting)
  lookup  — CLI: python -m src.notes.lookup --artist A --title T --json
"""

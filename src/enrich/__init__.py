"""RFL-the-toolkit: folder-scoped music enrichment, decoupled from broadcasting.

Everything in this package is a pure library: it takes a folder path as an
argument, touches no broadcaster state, and requires no running server. That is
the whole point of the split (#894) — the station keeps streaming on :8080 while
the toolkit can be pointed at an arbitrary folder with the station down.

Modules:
  identify  — derive candidate artist/title from existing tags (filename fallback)
  classify  — music vs. not-music gate (podcasts, focus mixes, TV clips)
  research  — MusicBrainz confirmation/correction (keyless, no OpenAI)
  tagio     — tag reads, mandatory pre-write JSON snapshots, guarded writeback
  pipeline  — scan orchestration producing a dry-run report

Design constraint from plan-back #8901: this path is AI-optional. MusicBrainz is
primary; no OpenAI key is required or installed. Which provider (if any) does the
richer analysis is an open question for Todd, deliberately left unresolved here.
"""

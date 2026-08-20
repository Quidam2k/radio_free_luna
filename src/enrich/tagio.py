"""Tag reads, mandatory pre-write snapshots, and guarded writeback.

Safety contract (plan-back #8901 Q2, made mandatory by review):

  * Nothing here writes to an audio file unless the caller passes
    dry_run=False AND supplies a snapshot path that already exists.
  * A JSON snapshot of ALL pre-existing tags is taken before any .save().
    Other tools may read the library live, so an unrecoverable retag is not acceptable.

Phase 2 is dry-run only; write_tags() exists and is tested but is not exercised
against the library until the Phase 3 diff review.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from mutagen import File as MutagenFile

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".flac", ".ogg", ".opus", ".wav", ".aac"}

# Same-meaning tag keys across MP4 atoms, ID3 frames, and Vorbis comments.
_KEY_ALIASES = {
    "title": ["\xa9nam", "TIT2", "TITLE"],
    "artist": ["\xa9ART", "TPE1", "ARTIST"],
    "album": ["\xa9alb", "TALB", "ALBUM"],
    "albumartist": ["aART", "TPE2", "ALBUMARTIST"],
    "genre": ["\xa9gen", "TCON", "GENRE"],
    "date": ["\xa9day", "TDRC", "DATE"],
    "comment": ["\xa9cmt", "COMM", "COMMENT"],
}


def _first(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def read_tags(path: str) -> Dict:
    """Read normalized tags plus duration. Returns {} for unreadable files."""
    try:
        audio = MutagenFile(path)
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return {}
    if audio is None:
        return {}

    # Build a lookup by iterating keys rather than testing membership: mutagen's
    # Vorbis comment class raises ValueError on any non-lowercase key test, so
    # `'TITLE' in tags` blows up on .ogg/.opus/.flac instead of returning False.
    present: Dict[str, object] = {}
    try:
        for key in (audio.tags or {}).keys():
            present[str(key).lower()] = audio.tags[key]
    except Exception as e:
        logger.warning(f"Could not enumerate tags on {path}: {e}")

    out: Dict = {}
    for name, aliases in _KEY_ALIASES.items():
        for alias in aliases:
            if alias.lower() in present:
                out[name] = _first(present[alias.lower()])
                break

    info = getattr(audio, "info", None)
    out["duration"] = float(getattr(info, "length", 0.0)) if info else 0.0
    return out


def read_raw_tags(path: str) -> Dict:
    """Every tag key on the file, stringified — the basis for the snapshot.

    Deliberately captures unknown/extra keys too: the point of a snapshot is to
    restore what was there, including fields this toolkit does not understand.
    """
    try:
        audio = MutagenFile(path)
    except Exception as e:
        logger.warning(f"Could not read raw tags from {path}: {e}")
        return {}
    if audio is None or audio.tags is None:
        return {}

    raw: Dict = {}
    for key in audio.tags.keys():
        try:
            value = audio.tags[key]
            if isinstance(value, list):
                # Cover art and similar binary atoms are noted, not embedded.
                raw[str(key)] = [
                    str(v) if not isinstance(v, bytes) else f"<{len(v)} bytes>"
                    for v in value
                ]
            else:
                raw[str(key)] = str(value)
        except Exception as e:
            raw[str(key)] = f"<unreadable: {e}>"
    return raw


def find_audio_files(folder: str, recursive: bool = True) -> List[str]:
    """Audio files under a folder, sorted for stable reporting."""
    root = Path(folder)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")
    walker = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        str(p) for p in walker
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )


def write_snapshot(paths: List[str], snapshot_path: str) -> str:
    """Record every pre-existing tag for `paths` to a JSON file.

    This is the rollback source. It must succeed before any write is allowed.
    """
    snapshot = {
        "version": 1,
        "file_count": len(paths),
        "files": {path: read_raw_tags(path) for path in paths},
    }
    out = Path(snapshot_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    logger.info(f"Wrote tag snapshot for {len(paths)} files to {snapshot_path}")
    return str(out)


def write_tags(
    path: str,
    artist: Optional[str] = None,
    title: Optional[str] = None,
    album: Optional[str] = None,
    dry_run: bool = True,
    snapshot_path: Optional[str] = None,
) -> Dict:
    """Write tags back to one file. Refuses unless explicitly unlocked.

    Returns a description of the change either way, so a dry run and a real run
    produce the same shape of report.
    """
    before = read_tags(path)
    # Empty and whitespace-only values are dropped, not written: a candidate
    # with no recoverable title would otherwise blank out the existing frame,
    # which is strictly worse than leaving it alone.
    proposed = {
        k: v.strip() for k, v in
        (("artist", artist), ("title", title), ("album", album))
        if v is not None and v.strip() and v.strip() != (before.get(k) or "")
    }
    result = {
        "path": path,
        "before": {k: before.get(k) for k in ("artist", "title", "album")},
        "changes": proposed,
        "written": False,
    }

    if dry_run:
        result["status"] = "dry-run"
        return result

    # Guard: a real write requires a snapshot that already exists on disk.
    if not snapshot_path or not os.path.exists(snapshot_path):
        result["status"] = "refused: no tag snapshot on disk"
        logger.error(f"Refusing to write {path}: snapshot missing ({snapshot_path})")
        return result

    if not proposed:
        result["status"] = "no-change"
        return result

    try:
        # easy=True normalizes across formats: EasyMP3 (ID3), EasyMP4 (atoms),
        # and Vorbis all accept plain-string assignment on the same lowercase
        # keys ('artist'/'title'/'album'). The raw path assigned a list straight
        # to a tag key, which ID3 rejects ("not a Frame instance") — MP3s never
        # got written. easy=True writes the correct frame/atom per format.
        audio = MutagenFile(path, easy=True)
        if audio is None:
            result["status"] = "refused: unreadable file"
            return result
        if audio.tags is None:
            audio.add_tags()
        for key, value in proposed.items():
            audio[key] = value
        audio.save()
        result["written"] = True
        result["status"] = "written"
    except Exception as e:
        result["status"] = f"error: {e}"
        logger.error(f"Failed writing tags to {path}: {e}")
    return result


def restore_snapshot(snapshot_path: str, dry_run: bool = True) -> Dict:
    """Report what restoring a snapshot would change (rollback preview).

    Actual restoration is intentionally not implemented in Phase 2 — the
    snapshot format is proven first, and rollback lands with Phase 3 apply.
    """
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    files = snapshot.get("files", {})
    differing = [
        path for path, saved in files.items()
        if os.path.exists(path) and read_raw_tags(path) != saved
    ]
    return {
        "snapshot": snapshot_path,
        "files_in_snapshot": len(files),
        "files_now_differing": len(differing),
        "differing": differing[:50],
        "restored": False,
        "status": "preview-only (restore lands with Phase 3)",
    }

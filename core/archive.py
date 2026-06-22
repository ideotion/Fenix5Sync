# SPDX-License-Identifier: GPL-3.0-or-later
"""Liberate Your History: expand account-export archives into importable files.

Garmin's GDPR "Full Data Export" is a zip-of-zips with gzip-compressed activity
files inside; Strava's bulk export ships ``*.fit.gz`` / ``*.gpx.gz`` alongside a
CSV. The activity files themselves are ordinary FIT/TCX/GPX -- the only thing
standing between a user and owning their whole cloud history locally is the
nesting and the gzip. This module unwraps both.

It expands a ``.zip`` (recursively, including nested zips) and decompresses
``*.<fmt>.gz`` activity files **into a temporary directory**, never writing to the
source. The result is a flat-ish tree the normal pipeline imports and
content-deduplicates exactly as it does watch files -- so a watch sync and a
cloud export of the same activity collapse to one.

Safety: every zip member is checked for path traversal ("zip slip") before
extraction, and recursion is depth-bounded to contain pathological archives.

Honest scope (foundation): this surfaces the *activity files* from an export.
Sidecar metadata enrichment (Strava ``activities.csv`` names/gear; Apple Health
``export.xml`` workouts) is a deliberate follow-up, documented in
``docs/history/decision-brief.md``.
"""

from __future__ import annotations

import gzip
import shutil
import zipfile
from pathlib import Path

from . import importers
from .logging_setup import get_logger

logger = get_logger()

_MAX_DEPTH = 8
# Read/write gzip in chunks so a large export file never loads wholly into memory.
_CHUNK = 1 << 20


def _supported_exts(formats: list[str] | None = None) -> set[str]:
    return importers.extensions(formats or None)


def _unique_path(dest_dir: Path, name: str) -> Path:
    """A non-colliding path in ``dest_dir`` for ``name`` (keeps the suffix)."""
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while (candidate := dest_dir / f"{stem}_{i}{suffix}").exists():
        i += 1
    return candidate


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract ``zf`` into ``dest``, refusing path-traversal ("zip slip") members."""
    dest = dest.resolve()
    for member in zf.infolist():
        if member.is_dir():
            continue
        target = (dest / member.filename).resolve()
        if target != dest and dest not in target.parents:
            raise ValueError(f"unsafe path in zip archive: {member.filename!r}")
    zf.extractall(dest)


def _is_activity_gz(path: Path, exts: set[str]) -> bool:
    """True for ``something.fit.gz`` / ``.tcx.gz`` / ``.gpx.gz`` (supported inner)."""
    return path.suffix.lower() == ".gz" and Path(path.stem).suffix.lower() in exts


def _gunzip(src: Path, dest_dir: Path) -> Path | None:
    inner_name = Path(src.stem).name  # drop the trailing .gz
    out = _unique_path(dest_dir, inner_name)
    try:
        with gzip.open(src, "rb") as fh_in, open(out, "wb") as fh_out:
            shutil.copyfileobj(fh_in, fh_out, _CHUNK)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        logger.warning("could not decompress %s: %s", src.name, exc)
        out.unlink(missing_ok=True)
        return None
    return out


def expand_into(
    src: str | Path, dest_dir: str | Path, formats: list[str] | None = None,
    _depth: int = 0,
) -> list[Path]:
    """Expand ``src`` (a file, directory or ``.zip``) into ``dest_dir``.

    Recursively extracts nested zips and decompresses ``*.<fmt>.gz`` activity
    files, copying plain supported files through. ``src`` is never modified.
    Returns the activity files now present under ``dest_dir``.
    """
    src = Path(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    exts = _supported_exts(formats)
    out: list[Path] = []

    if _depth > _MAX_DEPTH:
        logger.warning("archive nesting deeper than %d levels; stopping at %s", _MAX_DEPTH, src)
        return out

    if src.is_dir():
        for child in sorted(src.iterdir()):
            out += expand_into(child, dest_dir, formats, _depth)
        return out

    if not src.is_file():
        return out

    suffix = src.suffix.lower()
    if suffix == ".zip":
        sub = _unique_path(dest_dir, src.stem + "._unzipped")
        sub.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(src) as zf:
                _safe_extract_zip(zf, sub)
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            logger.warning("failed to read zip %s: %s", src, exc)
            return out
        out += expand_into(sub, dest_dir, formats, _depth + 1)
    elif _is_activity_gz(src, exts):
        got = _gunzip(src, dest_dir)
        if got is not None:
            out.append(got)
    elif suffix in exts:
        out.append(shutil.copy2(src, _unique_path(dest_dir, src.name)))
    return out

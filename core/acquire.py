# SPDX-License-Identifier: GPL-3.0-or-later
"""Acquire activity files from a Garmin device or a local source.

The source is treated as **strictly read-only**: this module only ever *reads*
(locating files and copying them into the local raw store). It never creates,
modifies or deletes anything on a connected device.

Acquisition modes (``source.mode``):
  * ``mass_storage`` -- the watch is mounted as a USB drive; we scan the usual
    mountpoint roots for ``GARMIN/Activity``.
  * ``mtp`` -- mounted on demand with ``jmtpfs`` (FUSE), searched, then unmounted.
    ``gio`` is documented as an alternative in the README.
  * ``path`` -- read directly from ``source.path`` (a directory, a single file
    or a ``.zip``; a device root containing ``activity_subdir`` also works).
  * ``folder`` -- a directory of activity files (optionally recursive).
  * ``file`` -- a single activity file.
  * ``zip`` -- a ``.zip`` archive of activity files (extracted to a temp dir).
  * ``auto`` -- the ``path`` hint, then mass storage, then MTP.

Files of any registered format (FIT/TCX/GPX) are discovered, so the same
pipeline ingests exports from devices and platforms beyond the Fenix 5.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import archive, importers
from .config import Config, _expand
from .logging_setup import get_logger

logger = get_logger()

_FIT_SUFFIXES = {".fit"}


@dataclass
class Source:
    """A located source: a directory to scan and/or an explicit file list.

    ``cleanup`` (e.g. an MTP unmount or temp-dir removal) must be called when
    done. When ``files`` is set it is the authoritative list to import;
    otherwise files are discovered under ``activity_dir``.
    """

    activity_dir: Path | None = None
    description: str = ""
    cleanup: Callable[[], None] = field(default=lambda: None)
    files: list[Path] | None = None
    recursive: bool = False
    monitoring_dir: Path | None = None  # wellness/monitoring files, scanned alongside activities


def known_extensions(formats: list[str] | None = None) -> set[str]:
    """Activity file extensions handled by the importers (optionally filtered)."""
    return importers.extensions(formats or None)


def list_activity_files(
    directory: str | Path,
    recursive: bool = False,
    formats: list[str] | None = None,
) -> list[Path]:
    """Return supported activity files in a directory (case-insensitive), sorted.

    Recognises every registered format (FIT/TCX/GPX) by extension, optionally
    restricted to ``formats``. Set ``recursive`` to descend into subdirectories.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []
    exts = known_extensions(formats)
    walker = directory.rglob("*") if recursive else directory.iterdir()
    return sorted(
        p for p in walker if p.is_file() and p.suffix.lower() in exts
    )


def list_fit_files(activity_dir: str | Path) -> list[Path]:
    """Return the ``.FIT`` files in a directory (case-insensitive), sorted.

    Retained for callers that specifically want FIT files; the pipeline uses
    :func:`list_activity_files` to discover all supported formats.
    """
    activity_dir = Path(activity_dir)
    if not activity_dir.is_dir():
        return []
    return sorted(
        p for p in activity_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _FIT_SUFFIXES
    )


def source_files(source: Source, cfg: Config) -> list[Path]:
    """Resolve the list of files to import for a located :class:`Source`.

    Monitoring/wellness ``.FIT`` files from ``monitoring_dir`` (when located) are
    appended; the import pipeline routes them to the wellness store.
    """
    if source.files is not None:
        files = list(source.files)
    elif source.activity_dir is not None:
        files = list_activity_files(
            source.activity_dir,
            recursive=source.recursive,
            formats=cfg.source.formats or None,
        )
    else:
        files = []
    if source.monitoring_dir is not None:
        seen = set(files)
        files += [f for f in list_fit_files(source.monitoring_dir) if f not in seen]
    return files


def copy_to_raw(
    src: str | Path, raw_dir: str | Path, file_hash: str, suffix: str | None = None
) -> Path:
    """Copy a source file into the raw store, content-addressed by hash.

    Reads from ``src`` (the device/source) and writes only into the local
    ``raw_dir``; the source is never written to. The original extension is
    preserved (so the format is re-detectable and re-parseable) -- defaulting to
    ``.fit`` when unknown. If a raw file with this hash already exists it is
    reused (no re-copy). Returns the destination path.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = (suffix if suffix is not None else Path(src).suffix) or ".fit"
    suffix = suffix.lower()
    if not suffix.startswith("."):
        suffix = "." + suffix
    dest = raw_dir / f"{file_hash}{suffix}"
    if not dest.exists():
        shutil.copy2(src, dest)  # copy2 reads src, writes dest; src untouched
    return dest


def _activity_subdir_parts(activity_subdir: str) -> list[str]:
    return [p for p in activity_subdir.replace("\\", "/").split("/") if p]


def _find_activity_dir_under(
    root: Path, activity_subdir: str, max_depth: int = 4
) -> Path | None:
    """Find a directory matching ``activity_subdir`` under ``root`` (bounded walk).

    Matches case-insensitively on the trailing path components, so both
    ``GARMIN/Activity`` and ``Garmin/activity`` are found, at any nesting up to
    ``max_depth`` (handles volume-label wrappers like ``/media/u/GARMIN/GARMIN/Activity``).
    """
    if not root.is_dir():
        return None
    parts = [p.lower() for p in _activity_subdir_parts(activity_subdir)]
    if not parts:
        return None
    leaf = parts[-1]
    root_depth = len(root.parts)
    try:
        for dirpath, dirnames, _ in os.walk(root):
            depth = len(Path(dirpath).parts) - root_depth
            if depth >= max_depth:
                dirnames[:] = []  # prune deeper traversal
                continue
            for d in dirnames:
                if d.lower() != leaf:
                    continue
                candidate = Path(dirpath) / d
                tail = [p.lower() for p in candidate.parts[-len(parts):]]
                if tail == parts:
                    return candidate
    except (PermissionError, OSError):
        return None
    return None


def _mass_storage_roots(cfg: Config) -> list[Path]:
    user = getpass.getuser()
    roots = [
        *(Path(_expand(r)) for r in cfg.source.extra_mount_roots),
        Path(f"/media/{user}"),
        Path("/media"),
        Path(f"/run/media/{user}"),
        Path("/mnt"),
    ]
    # De-duplicate while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _detect_mass_storage(cfg: Config) -> Source | None:
    for root in _mass_storage_roots(cfg):
        if not root.is_dir():
            continue
        # Check immediate children (mountpoints) and the root itself.
        candidates = [root, *[c for c in root.iterdir() if c.is_dir()]] if root.is_dir() else [root]
        for base in candidates:
            found = _find_activity_dir_under(base, cfg.source.activity_subdir)
            if found:
                mon = _find_activity_dir_under(base, cfg.source.monitoring_subdir)
                logger.info("Detected mass-storage activity dir: %s", found)
                return Source(activity_dir=found, monitoring_dir=mon,
                              description=f"mass storage ({found})")
    return None


def _detect_mtp(cfg: Config) -> Source | None:
    """Mount the device via jmtpfs and locate the activity dir under it."""
    if shutil.which("jmtpfs") is None:
        logger.info("jmtpfs not available; skipping MTP detection")
        return None
    mountpoint = Path(_expand(cfg.source.mtp_mountpoint))
    mountpoint.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["jmtpfs", str(mountpoint)],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("jmtpfs mount failed: %s", exc)
        return None
    if proc.returncode != 0:
        logger.info("jmtpfs reported no device (rc=%s): %s",
                    proc.returncode, proc.stderr.strip())
        _unmount_mtp(mountpoint)
        return None

    found = _find_activity_dir_under(mountpoint, cfg.source.activity_subdir, max_depth=6)
    if not found:
        logger.info("No activity dir found under MTP mount %s", mountpoint)
        _unmount_mtp(mountpoint)
        return None

    mon = _find_activity_dir_under(mountpoint, cfg.source.monitoring_subdir, max_depth=6)
    logger.info("Detected MTP activity dir: %s", found)
    return Source(
        activity_dir=found,
        monitoring_dir=mon,
        description=f"MTP ({found})",
        cleanup=lambda: _unmount_mtp(mountpoint),
    )


def _unmount_mtp(mountpoint: Path) -> None:
    for cmd in (["fusermount", "-u", str(mountpoint)], ["umount", str(mountpoint)]):
        if shutil.which(cmd[0]) is None:
            continue
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
            return
        except (OSError, subprocess.SubprocessError):
            continue


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


def _extract_zip_source(zip_path: Path, cfg: Config) -> Source | None:
    """Extract a ``.zip`` of activity files to a temp dir and return a Source."""
    try:
        tmpdir = Path(tempfile.mkdtemp(prefix="fenix5sync-zip-"))
    except OSError as exc:
        logger.warning("could not create temp dir for zip extraction: %s", exc)
        return None

    def cleanup() -> None:
        shutil.rmtree(tmpdir, ignore_errors=True)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            _safe_extract_zip(zf, tmpdir)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        logger.warning("failed to read zip %s: %s", zip_path, exc)
        cleanup()
        return None

    files = list_activity_files(tmpdir, recursive=True, formats=cfg.source.formats or None)
    logger.info("Extracted %d activity file(s) from %s", len(files), zip_path)
    return Source(
        activity_dir=tmpdir,
        files=files,
        recursive=True,
        description=f"zip ({zip_path}, {len(files)} file(s))",
        cleanup=cleanup,
    )


def _source_from_export(cfg: Config) -> Source | None:
    """Resolve ``source.path`` as a Garmin/Strava-style *account export*.

    Accepts the downloaded ``.zip`` (including Garmin's zip-of-zips) or an already
    unzipped folder, expands nested archives and gzip-compressed activity files
    into a temp dir (the source is never modified), and returns a Source over the
    surfaced FIT/TCX/GPX. Everything is then content-deduplicated as usual, so a
    cloud export and a watch sync of the same activity collapse to one.
    """
    if not cfg.source.path:
        logger.warning("export mode needs source.path (the export .zip or folder)")
        return None
    src = Path(_expand(cfg.source.path))
    if not src.exists():
        logger.warning("export source.path does not exist: %s", src)
        return None
    try:
        tmpdir = Path(tempfile.mkdtemp(prefix="fenix5sync-export-"))
    except OSError as exc:
        logger.warning("could not create temp dir for export expansion: %s", exc)
        return None

    def cleanup() -> None:
        shutil.rmtree(tmpdir, ignore_errors=True)

    files = archive.expand_into(src, tmpdir, formats=cfg.source.formats or None)
    logger.info("Expanded %d activity file(s) from export %s", len(files), src)
    return Source(
        activity_dir=tmpdir,
        files=sorted(files),
        recursive=True,
        description=f"export ({src}, {len(files)} file(s))",
        cleanup=cleanup,
    )


def _source_from_file(cfg: Config) -> Source | None:
    """Resolve ``source.path`` as a single activity file."""
    if not cfg.source.path:
        return None
    p = Path(_expand(cfg.source.path))
    if not p.is_file():
        logger.warning("source.path is not a file: %s", p)
        return None
    return Source(files=[p], description=f"file ({p})")


def _source_from_folder(cfg: Config) -> Source | None:
    """Resolve ``source.path`` as a folder of activity files."""
    if not cfg.source.path:
        return None
    p = Path(_expand(cfg.source.path))
    if not p.is_dir():
        logger.warning("source.path is not a folder: %s", p)
        return None
    return Source(
        activity_dir=p, recursive=cfg.source.recursive, description=f"folder ({p})"
    )


def _source_from_zip(cfg: Config) -> Source | None:
    """Resolve ``source.path`` as a ``.zip`` archive of activity files."""
    if not cfg.source.path:
        return None
    p = Path(_expand(cfg.source.path))
    if not p.is_file():
        logger.warning("source.path zip archive not found: %s", p)
        return None
    return _extract_zip_source(p, cfg)


def _source_from_path(cfg: Config) -> Source | None:
    """Resolve an explicit ``source.path`` (file, ``.zip``, folder or device root)."""
    if not cfg.source.path:
        return None
    base = Path(_expand(cfg.source.path))
    if not base.exists():
        logger.warning("Configured source.path does not exist: %s", base)
        return None
    # A single file or a zip archive.
    if base.is_file():
        if base.suffix.lower() == ".zip":
            return _extract_zip_source(base, cfg)
        return Source(files=[base], description=f"path ({base})")
    # A directory that already holds activity files (any supported format).
    if list_activity_files(base, recursive=cfg.source.recursive, formats=cfg.source.formats or None):
        return Source(
            activity_dir=base, recursive=cfg.source.recursive, description=f"path ({base})"
        )
    # A device root containing the activity subdir.
    found = _find_activity_dir_under(base, cfg.source.activity_subdir)
    if found:
        mon = _find_activity_dir_under(base, cfg.source.monitoring_subdir)
        return Source(activity_dir=found, monitoring_dir=mon, description=f"path ({found})")
    # Fall back to the joined path even if currently empty.
    joined = base / Path(*_activity_subdir_parts(cfg.source.activity_subdir))
    if joined.is_dir():
        return Source(activity_dir=joined, description=f"path ({joined})")
    return None


def locate_source(cfg: Config) -> Source | None:
    """Locate the activity source according to the configured mode.

    Returns a :class:`Source` (whose ``cleanup`` must be called when done), or
    ``None`` if nothing could be located.
    """
    mode = cfg.source.mode
    if mode == "path":
        return _source_from_path(cfg)
    if mode == "folder":
        return _source_from_folder(cfg)
    if mode == "file":
        return _source_from_file(cfg)
    if mode == "zip":
        return _source_from_zip(cfg)
    if mode == "export":
        return _source_from_export(cfg)
    if mode == "mass_storage":
        return _detect_mass_storage(cfg)
    if mode == "mtp":
        return _detect_mtp(cfg)
    # auto: explicit path hint, then mass storage, then MTP.
    return (
        _source_from_path(cfg)
        or _detect_mass_storage(cfg)
        or _detect_mtp(cfg)
    )

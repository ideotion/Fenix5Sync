"""Acquire .FIT files from a connected Garmin Fenix 5.

The device is treated as **strictly read-only**: this module only ever *reads*
from the watch (locating the activity directory and copying files off it). It
never creates, modifies or deletes anything on the device.

Two acquisition styles are supported, with auto-detection attempted first:
  * mass storage -- the watch is mounted as a USB drive; we scan the usual
    mountpoint roots for ``GARMIN/Activity``.
  * MTP -- mounted on demand with ``jmtpfs`` (FUSE), searched, then unmounted.
    ``gio`` is documented as an alternative in the README.
The source path/mode is configurable; ``mode: path`` reads a directory directly.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Config, _expand
from .logging_setup import get_logger

logger = get_logger()

_FIT_SUFFIXES = {".fit"}


@dataclass
class Source:
    """A located activity directory plus an optional cleanup (e.g. MTP unmount)."""

    activity_dir: Path
    description: str = ""
    cleanup: Callable[[], None] = field(default=lambda: None)


def list_fit_files(activity_dir: str | Path) -> list[Path]:
    """Return the ``.FIT`` files in a directory (case-insensitive), sorted."""
    activity_dir = Path(activity_dir)
    if not activity_dir.is_dir():
        return []
    return sorted(
        p for p in activity_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _FIT_SUFFIXES
    )


def copy_to_raw(src: str | Path, raw_dir: str | Path, file_hash: str) -> Path:
    """Copy a source .FIT into the raw store, content-addressed by hash.

    Reads from ``src`` (the device) and writes only into the local ``raw_dir``;
    the device is never written to. Returns the destination path. If a raw file
    with this hash already exists, it is reused (no re-copy).
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{file_hash}.fit"
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
                logger.info("Detected mass-storage activity dir: %s", found)
                return Source(activity_dir=found, description=f"mass storage ({found})")
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

    logger.info("Detected MTP activity dir: %s", found)
    return Source(
        activity_dir=found,
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


def _source_from_path(cfg: Config) -> Source | None:
    """Resolve an explicit ``source.path``.

    Accepts either the activity directory itself or a device-root that contains
    ``activity_subdir``.
    """
    if not cfg.source.path:
        return None
    base = Path(_expand(cfg.source.path))
    if not base.exists():
        logger.warning("Configured source.path does not exist: %s", base)
        return None
    # Direct activity dir?
    if list_fit_files(base):
        return Source(activity_dir=base, description=f"path ({base})")
    # Device root containing the activity subdir?
    found = _find_activity_dir_under(base, cfg.source.activity_subdir)
    if found:
        return Source(activity_dir=found, description=f"path ({found})")
    # Fall back to the joined path even if currently empty.
    joined = base / Path(*_activity_subdir_parts(cfg.source.activity_subdir))
    if joined.is_dir():
        return Source(activity_dir=joined, description=f"path ({joined})")
    return None


def locate_source(cfg: Config) -> Source | None:
    """Locate the activity directory according to the configured mode.

    Returns a :class:`Source` (whose ``cleanup`` must be called when done), or
    ``None`` if no device/directory could be found.
    """
    mode = cfg.source.mode
    if mode == "path":
        return _source_from_path(cfg)
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

# SPDX-License-Identifier: GPL-3.0-or-later
"""Pluggable activity importers.

A small registry maps a *format id* (``fit`` / ``tcx`` / ``gpx``) to an
:class:`Importer` that knows how to recognise (``sniff``) and ``parse`` files of
that format into the canonical :class:`~core.models.Activity`.

* :func:`detect_format` identifies a file by content signature (FIT magic, XML
  root element) with an extension fallback.
* :func:`parse_activity_file` detects the format and dispatches to the right
  parser, recording the source format on the activity for provenance.

New formats register here without the pipeline needing to know about them, which
is what lets Fenix5Sync ingest exports from devices and platforms beyond the
Fenix 5 (anything that produces FIT, TCX or GPX).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..models import Activity

# parse(path, file_hash, raw_path) -> Activity ; sniff(head_bytes, path) -> bool
ParseFn = Callable[..., Activity]
SniffFn = Callable[[bytes, Path], bool]


@dataclass(frozen=True)
class Importer:
    """A registered format handler."""

    name: str
    extensions: tuple[str, ...]
    parse: ParseFn
    sniff: SniffFn


_REGISTRY: dict[str, Importer] = {}
_ORDER: list[str] = []  # registration order; also the content-sniff priority

# How many bytes to read for content detection (enough for an XML prolog/root).
_HEAD_BYTES = 4096


def register(importer: Importer) -> None:
    """Add (or replace) an importer in the registry."""
    if importer.name not in _REGISTRY:
        _ORDER.append(importer.name)
    _REGISTRY[importer.name] = importer


def get_importer(name: str) -> Importer | None:
    return _REGISTRY.get(name)


def formats() -> list[str]:
    """Registered format ids, in registration order."""
    return list(_ORDER)


def extensions(names: list[str] | None = None) -> set[str]:
    """Lower-case file extensions handled by the given formats (default: all)."""
    selected = names if names else _ORDER
    out: set[str] = set()
    for name in selected:
        imp = _REGISTRY.get(name)
        if imp:
            out.update(e.lower() for e in imp.extensions)
    return out


def detect_format(path: str | Path) -> str | None:
    """Return the format id for a file, or None if unrecognised.

    Content signatures are checked first (robust to wrong/missing extensions),
    then the file extension as a fallback.
    """
    p = Path(path)
    try:
        with open(p, "rb") as fh:
            head = fh.read(_HEAD_BYTES)
    except OSError:
        head = b""
    for name in _ORDER:
        try:
            if _REGISTRY[name].sniff(head, p):
                return name
        except Exception:  # a misbehaving sniffer must not break detection
            continue
    ext = p.suffix.lower()
    for name in _ORDER:
        if ext in _REGISTRY[name].extensions:
            return name
    return None


def parse_activity_file(
    path: str | Path,
    file_hash: str = "",
    raw_path: str | None = None,
    fmt: str | None = None,
) -> Activity:
    """Parse any supported activity file into an :class:`Activity`.

    Args:
        path: file to parse.
        file_hash: SHA-256 of the content (stored on the activity).
        raw_path: where the raw file is kept (defaults to ``path``).
        fmt: force a specific format id; auto-detected when omitted.

    Raises:
        ParseError: if the format is unrecognised or the file cannot be parsed.
    """
    from ..parse import ParseError  # shared error type used across importers

    p = Path(path)
    chosen = fmt or detect_format(p)
    importer = _REGISTRY.get(chosen) if chosen else None
    if importer is None:
        raise ParseError(f"{p.name}: unrecognised or unsupported activity format")
    activity = importer.parse(p, file_hash, raw_path)
    # Record provenance without clobbering anything a parser already set.
    activity.extra.setdefault("source_format", {"value": importer.name, "units": None})
    return activity


# --------------------------------------------------------------------------- #
# Built-in importers
# --------------------------------------------------------------------------- #
def _fit_sniff(head: bytes, path: Path) -> bool:
    # FIT files carry the ASCII tag ".FIT" at byte offset 8 of the header.
    return len(head) >= 12 and head[8:12] == b".FIT"


def _fit_parse(path, file_hash: str = "", raw_path: str | None = None) -> Activity:
    from ..parse import parse_fit_file  # lazy: keeps fitparse optional at import

    return parse_fit_file(path, file_hash, raw_path)


def _register_builtins() -> None:
    from . import gpx, tcx

    register(Importer("fit", (".fit",), _fit_parse, _fit_sniff))
    register(Importer("tcx", (".tcx",), tcx.parse_tcx_file, tcx.sniff))
    register(Importer("gpx", (".gpx",), gpx.parse_gpx_file, gpx.sniff))


_register_builtins()

__all__ = [
    "Importer",
    "register",
    "get_importer",
    "formats",
    "extensions",
    "detect_format",
    "parse_activity_file",
]

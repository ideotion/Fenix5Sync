"""Small, dependency-free helpers shared by the XML-based importers (TCX/GPX).

Kept separate so the individual format parsers stay focused on mapping their
schema onto the canonical model. Everything here is pure and stdlib-only.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable


# --------------------------------------------------------------------------- #
# XML helpers (namespace-agnostic: we match on *local* element names so the
# same code parses files from any exporter regardless of namespace prefixes).
# --------------------------------------------------------------------------- #
def local_name(tag: object) -> str:
    """Return the local part of an ElementTree tag (strip any ``{ns}`` prefix)."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def child(parent, name: str):
    """First *direct* child element whose local name matches, or None."""
    if parent is None:
        return None
    for c in parent:
        if local_name(c.tag) == name:
            return c
    return None


def children(parent, name: str) -> list:
    """All *direct* child elements whose local name matches."""
    if parent is None:
        return []
    return [c for c in parent if local_name(c.tag) == name]


def descendants(parent, name: str) -> list:
    """All descendant elements (any depth) whose local name matches, in document order."""
    if parent is None:
        return []
    return [e for e in parent.iter() if local_name(e.tag) == name]


def text_of(elem) -> str | None:
    """Stripped text of an element, or None if empty/absent."""
    if elem is None:
        return None
    t = elem.text
    return t.strip() if isinstance(t, str) and t.strip() else None


def first_text(parent, name: str) -> str | None:
    """Text of the first descendant with the given local name, or None."""
    if parent is None:
        return None
    for e in parent.iter():
        if local_name(e.tag) == name:
            return text_of(e)
    return None


# --------------------------------------------------------------------------- #
# Numeric / time coercion
# --------------------------------------------------------------------------- #
def to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value) -> int | None:
    f = to_float(value)
    return int(round(f)) if f is not None else None


def parse_time(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into a naive UTC datetime.

    Normalising to naive-UTC matches what fitparse yields for FIT files, so the
    store holds timestamps consistently regardless of source format.
    """
    if not value:
        return None
    s = value.strip()
    dt: datetime | None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:  # tolerate a trailing 'Z' on older inputs
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# --------------------------------------------------------------------------- #
# Geometry / derived series
# --------------------------------------------------------------------------- #
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    radius = 6371000.0  # mean Earth radius (m)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def ascent_descent(altitudes: Iterable[float | None]) -> tuple[int | None, int | None]:
    """Total ascent/descent (m, rounded) from a sequence of altitudes.

    Formats like GPX/TCX don't carry summary ascent/descent, so we derive them
    from the altitude series. Returns ``(None, None)`` when there's nothing to
    integrate.
    """
    vals = [a for a in altitudes if a is not None]
    if len(vals) < 2:
        return (None, None)
    asc = desc = 0.0
    prev = vals[0]
    for a in vals[1:]:
        delta = a - prev
        if delta > 0:
            asc += delta
        elif delta < 0:
            desc += -delta
        prev = a
    return (int(round(asc)), int(round(desc)))

"""Cross-source duplicate detection (pure, stdlib-only).

The exact-content SHA-256 dedupe in :mod:`core.dedupe` only catches byte-identical
files. The *same* workout exported from different places -- a watch ``.FIT`` and a
Strava ``.GPX``, say -- hashes differently and slips through. This finds those
**semantic** duplicates by matching start time, duration and distance (and start
GPS when present), grouping the activities that almost certainly represent one
effort so the user can review them.

It is strictly a **report**: it never edits or deletes anything (the archive stays
read-only). Two activities are considered the same effort when their start times
are within :data:`_START_TOL_S`, their duration and distance each agree within
:data:`_REL_TOL` (where both are present), their start positions are within
:data:`_GPS_TOL_DEG` (where both are present), and their sports don't conflict.
Grouping is transitive (union-find), so a watch + phone + Strava copy of one run
collapse into a single group.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .models import Activity

_START_TOL_S = 180.0   # start times within 3 minutes
_REL_TOL = 0.10        # duration / distance agree within 10%
_GPS_TOL_DEG = 0.0015  # ~150 m; only applied when both have a start position


def _epoch(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _rel_close(a: float | None, b: float | None) -> bool | None:
    """True/False if both present and (not) within tolerance; None if indeterminate."""
    if a is None or b is None:
        return None
    return abs(a - b) <= _REL_TOL * max(a, b, 1.0)


def _same_effort(a: Activity, b: Activity) -> bool:
    if a.start_time is None or b.start_time is None:
        return False
    if abs(_epoch(a.start_time) - _epoch(b.start_time)) > _START_TOL_S:
        return False
    # Conflicting sports rule it out (a run and a ride at the same time aren't dups).
    if a.sport and b.sport and a.sport != b.sport:
        return False
    dur = _rel_close(a.total_timer_time, b.total_timer_time)
    dist = _rel_close(a.total_distance, b.total_distance)
    if dur is False or dist is False:
        return False
    # Require at least one of duration/distance to actually corroborate the match.
    if dur is None and dist is None:
        return False
    # Start-position sanity check when both have GPS.
    if None not in (a.start_latitude, a.start_longitude, b.start_latitude, b.start_longitude):
        if (abs(a.start_latitude - b.start_latitude) > _GPS_TOL_DEG
                or abs(a.start_longitude - b.start_longitude) > _GPS_TOL_DEG):
            return False
    return True


def _member(a: Activity) -> dict:
    device = " ".join(p for p in (a.device_manufacturer, a.device_product) if p) or None
    return {
        "id": a.id,
        "start_time": a.start_time.isoformat() if a.start_time else None,
        "sport": a.sport,
        "distance_m": a.total_distance,
        "duration_s": a.total_timer_time,
        "device": device,
        "file_hash": a.file_hash,
    }


def find_duplicate_groups(activities: Iterable[Activity]) -> dict:
    """Group activities that look like the same effort across sources (report only).

    Returns ``groups`` (each with the matched activities, most recent first) plus
    counts. Nothing is modified or removed.
    """
    acts = [a for a in activities if a.start_time is not None]
    n = len(acts)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Compare in start-time order so only nearby activities are tested.
    order = sorted(range(n), key=lambda i: _epoch(acts[i].start_time))
    for oi in range(n):
        i = order[oi]
        for oj in range(oi + 1, n):
            j = order[oj]
            if _epoch(acts[j].start_time) - _epoch(acts[i].start_time) > _START_TOL_S:
                break  # sorted: nothing further can be within the start tolerance
            if _same_effort(acts[i], acts[j]):
                parent[find(i)] = find(j)

    clusters: dict[int, list[Activity]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(acts[i])

    groups = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda a: _epoch(a.start_time), reverse=True)
        groups.append({"count": len(members), "activities": [_member(a) for a in members]})
    groups.sort(key=lambda g: g["activities"][0]["start_time"] or "", reverse=True)

    return {
        "groups": groups,
        "total_activities": len(list(acts)),
        "duplicate_groups": len(groups),
        "duplicate_activities": sum(g["count"] for g in groups),
    }

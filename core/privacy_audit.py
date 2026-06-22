# SPDX-License-Identifier: GPL-3.0-or-later
"""Personal privacy audit: show what your *own* tracks reveal, before you share.

A defensive, local-only self-audit. It clusters the start points of your
activities to surface the places your data most exposes -- typically home -- and
the weekday/time regularity that turns a location into a routine. It then
recommends a privacy radius that would mask the most-exposed place, feeding the
anonymization the app already ships (``core.anonymize``).

Design choices, deliberately conservative:

* **Summary-only.** It works from each activity's ``start_latitude`` /
  ``start_longitude`` (already in the store) plus ``start_time`` -- no trackpoint
  load, so it is cheap and offline. Start points are where the "home" leak lives.
* **Never persists an inference.** The likely-home cluster is computed on demand
  and returned to the local UI only; nothing is written anywhere it could leak.
* **Probabilistic, and says so.** Clusters are reported as *likely* places with
  counts and confidence, never as asserted identities.

Why this matters is documented (with sources) in
``docs/privacy/decision-brief.md`` and surfaced discreetly in the UI.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .geo import haversine_m
from .models import Activity

# Points within this distance of a cluster centroid join it (greedy clustering).
_CLUSTER_EPS_M = 150.0
# Sensible recommended-radius rounding and floor (metres).
_RADIUS_STEP_M = 50.0
_RADIUS_FLOOR_M = 200.0
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class _Cluster:
    lat: float
    lon: float
    members: list[Activity] = field(default_factory=list)

    def add(self, a: Activity, lat: float, lon: float) -> None:
        # Incremental centroid update keeps the cluster centre stable as it grows.
        n = len(self.members)
        self.lat = (self.lat * n + lat) / (n + 1)
        self.lon = (self.lon * n + lon) / (n + 1)
        self.members.append(a)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo is not None else dt


def _start_point(a: Activity) -> tuple[float, float] | None:
    if a.start_latitude is None or a.start_longitude is None:
        return None
    return (a.start_latitude, a.start_longitude)


def _cluster_points(acts: list[Activity], eps_m: float) -> list[_Cluster]:
    clusters: list[_Cluster] = []
    for a in acts:
        pt = _start_point(a)
        if pt is None:
            continue
        lat, lon = pt
        nearest, best = None, eps_m
        for c in clusters:
            d = haversine_m(lat, lon, c.lat, c.lon)
            if d <= best:
                nearest, best = c, d
        if nearest is None:
            clusters.append(_Cluster(lat, lon, [a]))
        else:
            nearest.add(a, lat, lon)
    return clusters


def _round_up(value: float, step: float, floor: float) -> int:
    import math
    return int(max(floor, math.ceil(value / step) * step))


def _cluster_radius_m(c: _Cluster) -> float:
    """Spread of the cluster: the farthest member from its centroid."""
    return max((haversine_m(c.lat, c.lon, *_start_point(a)) for a in c.members), default=0.0)


def _cluster_summary(c: _Cluster, total: int, kind: str) -> dict:
    times = [t for a in c.members if (t := _utc(a.start_time))]
    weekday_counts = Counter(t.weekday() for t in times)
    hour_counts = Counter(t.hour for t in times)
    dates = sorted(t.date().isoformat() for t in times)
    spread = _cluster_radius_m(c)
    peak_weekday = weekday_counts.most_common(1)[0][0] if weekday_counts else None
    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else None
    # Regularity: share of visits falling on the single most common weekday.
    regularity = (weekday_counts.most_common(1)[0][1] / len(times)) if times else 0.0
    return {
        "kind": kind,  # "primary" (most exposed) | "frequent"
        "lat": round(c.lat, 5),
        "lon": round(c.lon, 5),
        "count": len(c.members),
        "share_pct": round(100.0 * len(c.members) / total, 1) if total else 0.0,
        "spread_m": round(spread, 1),
        "first_seen": dates[0] if dates else None,
        "last_seen": dates[-1] if dates else None,
        "peak_weekday": _WEEKDAYS[peak_weekday] if peak_weekday is not None else None,
        "peak_hour": peak_hour,
        "weekday_counts": [weekday_counts.get(i, 0) for i in range(7)],
        "regularity_pct": round(100.0 * regularity, 1),
    }


def compute_privacy_audit(
    activities: Iterable[Activity], eps_m: float = _CLUSTER_EPS_M, top_n: int = 8
) -> dict:
    """Audit what the activity start points reveal, and recommend a privacy radius.

    Accepts activity *summaries* (needs ``start_latitude``/``start_longitude`` and
    ``start_time``). Returns the most-exposed location clusters (likely home
    first), how many activities a privacy-radius scrub would mask, and a
    recommended radius. All inferences are probabilistic and are never persisted.
    """
    acts = list(activities)
    total = len(acts)
    with_gps = [a for a in acts if _start_point(a) is not None]

    clusters = _cluster_points(with_gps, eps_m)
    clusters.sort(key=lambda c: len(c.members), reverse=True)

    summaries: list[dict] = []
    for i, c in enumerate(clusters[:top_n]):
        summaries.append(_cluster_summary(c, len(with_gps), "primary" if i == 0 else "frequent"))

    primary = clusters[0] if clusters else None
    recommended_radius_m = 0
    exposed = 0
    if primary is not None:
        # Cover the cluster's own spread, with a sensible floor, so a scrub at this
        # radius hides every start that lands in the most-exposed place.
        recommended_radius_m = _round_up(
            _cluster_radius_m(primary) + _RADIUS_STEP_M, _RADIUS_STEP_M, _RADIUS_FLOOR_M
        )
        exposed = sum(
            1 for a in with_gps
            if haversine_m(*_start_point(a), primary.lat, primary.lon) <= recommended_radius_m
        )

    return {
        "total_activities": total,
        "with_gps": len(with_gps),
        "location_count": len(clusters),
        "clusters": summaries,
        "primary": summaries[0] if summaries else None,
        "recommended_radius_m": recommended_radius_m,
        "exposed_activities": exposed,
        "exposed_pct": round(100.0 * exposed / len(with_gps), 1) if with_gps else 0.0,
    }

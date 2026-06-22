# SPDX-License-Identifier: GPL-3.0-or-later
"""Personal segments: race yourself over a route, privately and offline.

Strava's killer feature without the social network, the cloud or the
subscription. A *segment* is an ordered sequence of waypoints with a corridor
tolerance; an activity produces an *effort* on it when its track passes near each
waypoint in order. The effort time is the elapsed time between hitting the first
and last waypoint -- so you can compare every time you have ever run/ridden your
own local loop or climb.

Design (robust over fiddly):

* **Waypoint sequence, not raw geometry.** Capturing a route as ~10 ordered
  waypoints with a corridor tolerance tolerates GPS noise and encodes direction
  (an out-and-back differs from the reverse) without heavyweight line geometry.
* **Greedy in-order match.** We walk the activity's trackpoints once and advance
  to the next waypoint when a point falls within the corridor -- O(points).
* **Pure & local.** Functions of activities + a segment; no DB handle, no
  network. Efforts need each activity's trackpoint series (the caller loads them,
  pruned by sport, exactly as :mod:`core.records` does).

Strava segment *leaderboards* are a paywalled, cloud, social feature; this is the
private, self-only inverse -- no global board, no kudos, no account.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

from .geo import haversine_m
from .models import Activity

_DEFAULT_RADIUS_M = 30.0
_DEFAULT_WAYPOINTS = 12


@dataclass
class Segment:
    """A user-defined route to compare efforts on."""

    name: str
    waypoints: list[tuple[float, float]]  # ordered (lat, lon)
    radius_m: float = _DEFAULT_RADIUS_M
    sport: str | None = None
    distance_m: float | None = None
    id: int | None = None
    source_activity_id: int | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "sport": self.sport,
            "radius_m": self.radius_m,
            "distance_m": round(self.distance_m, 1) if self.distance_m is not None else None,
            "waypoints": [[round(la, 6), round(lo, 6)] for la, lo in self.waypoints],
            "source_activity_id": self.source_activity_id,
        }


@dataclass
class SegmentEffort:
    """One activity's effort on a segment."""

    activity_id: int | None
    date: str | None
    time_s: float
    distance_m: float
    pace_s_per_km: int | None = None
    avg_hr: int | None = None

    def as_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "date": self.date,
            "time_s": round(self.time_s, 1),
            "distance_m": round(self.distance_m, 1),
            "pace_s_per_km": self.pace_s_per_km,
            "avg_hr": self.avg_hr,
        }


def _utc_date(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat()


def _polyline_length_m(points: Sequence[tuple[float, float]]) -> float:
    return sum(
        haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:])
    )


def segment_from_activity(
    activity: Activity,
    name: str,
    *,
    num_waypoints: int = _DEFAULT_WAYPOINTS,
    radius_m: float = _DEFAULT_RADIUS_M,
) -> Segment:
    """Build a segment by evenly subsampling a reference activity's GPS track."""
    fixes = [
        (tp.latitude, tp.longitude)
        for tp in activity.trackpoints
        if tp.latitude is not None and tp.longitude is not None
    ]
    if len(fixes) < 2:
        raise ValueError("activity has no usable GPS track to build a segment from")
    n = max(2, min(num_waypoints, len(fixes)))
    step = (len(fixes) - 1) / (n - 1)
    waypoints = [fixes[round(i * step)] for i in range(n)]
    return Segment(
        name=name,
        waypoints=waypoints,
        radius_m=radius_m,
        sport=activity.sport,
        distance_m=_polyline_length_m(waypoints),
        source_activity_id=activity.id,
    )


def match_effort(activity: Activity, segment: Segment) -> SegmentEffort | None:
    """Return this activity's effort on ``segment``, or None if it doesn't match.

    Greedily advances through the segment's waypoints as the activity's track
    passes within ``radius_m`` of each in order. A match requires every waypoint
    to be reached; the effort spans the first to the last waypoint hit.
    """
    wps = segment.waypoints
    if len(wps) < 2:
        return None
    pts = [
        tp for tp in activity.trackpoints
        if tp.latitude is not None and tp.longitude is not None and tp.timestamp is not None
    ]
    if len(pts) < 2:
        return None

    idx = 0
    hit_time: list[datetime] = []
    hit_dist: list[float | None] = []
    for tp in pts:
        if idx >= len(wps):
            break
        wlat, wlon = wps[idx]
        if haversine_m(tp.latitude, tp.longitude, wlat, wlon) <= segment.radius_m:
            hit_time.append(tp.timestamp)
            hit_dist.append(tp.distance)
            idx += 1
    if idx < len(wps):
        return None  # did not reach every waypoint in order

    time_s = (hit_time[-1] - hit_time[0]).total_seconds()
    if time_s <= 0:
        return None
    # Prefer the activity's own cumulative distance between the endpoints; fall
    # back to the segment's polyline length when distance isn't recorded.
    if hit_dist[0] is not None and hit_dist[-1] is not None and hit_dist[-1] > hit_dist[0]:
        distance_m = hit_dist[-1] - hit_dist[0]
    else:
        distance_m = segment.distance_m or _polyline_length_m(wps)

    pace = round(time_s / (distance_m / 1000.0)) if distance_m > 0 else None
    return SegmentEffort(
        activity_id=activity.id,
        date=_utc_date(activity.start_time),
        time_s=time_s,
        distance_m=distance_m,
        pace_s_per_km=pace,
        avg_hr=activity.avg_heart_rate,
    )


def compute_segment_efforts(activities: Iterable[Activity], segment: Segment) -> dict:
    """All matching efforts on a segment: a private leaderboard plus a trend.

    Each activity should have its trackpoints loaded. Returns efforts ranked
    fastest-first (the personal leaderboard), the chronological series (for a
    progress trend), the best effort and the count considered.
    """
    efforts = [e for a in activities if (e := match_effort(a, segment)) is not None]
    ranked = sorted(efforts, key=lambda e: e.time_s)
    chronological = sorted(efforts, key=lambda e: (e.date or ""))
    return {
        "segment": segment.as_dict(),
        "leaderboard": [e.as_dict() for e in ranked],
        "history": [e.as_dict() for e in chronological],
        "best": ranked[0].as_dict() if ranked else None,
        "count": len(efforts),
    }

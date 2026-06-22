# SPDX-License-Identifier: GPL-3.0-or-later
"""All-time personal records from the local archive (pure, stdlib-only).

Aggregates each activity's best efforts (fastest time to cover each standard
distance, from :func:`core.best_efforts.compute_best_efforts`) into lifetime
bests -- your fastest-ever 1 K / 5 K / 10 K, each tagged with the activity it
came from.

Cost note: unlike the summary-only insight endpoints, all-time records need each
activity's trackpoint series to find in-run best windows, so the caller loads
those series (an N+1 over the relevant activities). The API prunes to one sport
with a distance signal to bound it; a future cache could precompute per activity.
Read-only over the activities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .best_efforts import compute_best_efforts
from .models import Activity


def _utc_date(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat()


def compute_personal_records(activities: Iterable[Activity]) -> dict:
    """Lifetime fastest time per standard distance across the given activities.

    Each activity should have its trackpoints loaded. Returns ``records`` (one per
    distance that any activity reached, ascending) with the activity id/date the
    record came from, plus the number of activities considered.
    """
    acts = list(activities)
    best: dict[float, dict] = {}
    for a in acts:
        for e in compute_best_efforts(a)["best_distances"]:
            d = e["distance_m"]
            if d not in best or e["time_s"] < best[d]["time_s"]:
                best[d] = {
                    "distance_m": d,
                    "label": e["label"],
                    "time_s": e["time_s"],
                    "pace_s_per_km": e["pace_s_per_km"],
                    "activity_id": a.id,
                    "date": _utc_date(a.start_time),
                }
    return {"records": [best[d] for d in sorted(best)], "activities": len(acts)}

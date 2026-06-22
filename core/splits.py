# SPDX-License-Identifier: GPL-3.0-or-later
"""Even-distance splits over an activity's track (pure, stdlib-only).

Breaks the recorded series into fixed-distance segments -- 1 km by default, or
miles, or any distance the caller picks -- and reports pace, heart rate and
elevation change for each. This is the "how did every kilometre go" view and the
basis for pacing / negative-split analysis. It works from cumulative trackpoint
distance plus timestamps, so it covers any activity that recorded distance, even
one with no laps (or laps at a different interval than you want to see).

Time is *moving* time: a gap longer than ``_MAX_GAP_S`` between samples is treated
as a stop (auto-pause / rest) and not counted, matching :mod:`core.zones`. A split
keeps the metrics of the samples whose cumulative distance falls inside its
band; the trailing split may be shorter than the chosen distance. Read-only over
the activity, with no third-party dependency.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from .models import Activity, Trackpoint

# Samples more than this far apart (seconds) bracket a stop, so the gap is not
# added to moving time (matches the convention in core.zones / core.metrics).
_MAX_GAP_S = 30.0

# One statute mile in metres (so callers can ask for mile splits exactly).
MILE_M = 1609.344


@dataclass
class Split:
    """One fixed-distance segment of an activity."""

    index: int                  # 1-based split number
    distance_m: float           # metres covered (the last split may be short)
    time_s: float               # moving time within the split
    pace_s_per_km: float | None  # moving pace
    avg_hr_bpm: int | None
    elev_gain_m: float
    elev_loss_m: float

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "distance_m": round(self.distance_m, 1),
            "time_s": round(self.time_s, 1),
            "pace_s_per_km": (round(self.pace_s_per_km) if self.pace_s_per_km is not None else None),
            "avg_hr_bpm": self.avg_hr_bpm,
            "elev_gain_m": round(self.elev_gain_m, 1),
            "elev_loss_m": round(self.elev_loss_m, 1),
        }


def compute_splits(activity: Activity, *, metres: float = 1000.0) -> dict:
    """Fixed-distance splits for an activity (default 1 km).

    Args:
        activity: the activity to split (uses its trackpoints; read-only).
        metres: split length in metres (e.g. ``MILE_M`` for mile splits).

    Returns a serialisable dict: the split ``metres``/``unit``, the ordered
    ``splits`` list, and the 1-based ``fastest_index`` / ``slowest_index`` (by
    pace), or an empty list when the activity has no usable distance series.
    """
    if metres <= 0:
        raise ValueError("metres must be positive")

    pts: Sequence[Trackpoint] = [
        tp for tp in activity.trackpoints if tp.distance is not None
    ]
    acc: dict[int, dict] = defaultdict(
        lambda: {"time": 0.0, "hr_sum": 0.0, "hr_n": 0, "gain": 0.0, "loss": 0.0}
    )
    total = 0.0
    prev: Trackpoint | None = None
    for tp in pts:
        idx = int(tp.distance // metres)
        bucket = acc[idx]
        total = max(total, tp.distance)
        if tp.heart_rate is not None:
            bucket["hr_sum"] += tp.heart_rate
            bucket["hr_n"] += 1
        if prev is not None:
            # Time and elevation change for this segment belong to the split the
            # segment *starts* in (the earlier sample).
            start = acc[int(prev.distance // metres)]
            if prev.timestamp is not None and tp.timestamp is not None:
                dt = (tp.timestamp - prev.timestamp).total_seconds()
                if 0.0 < dt <= _MAX_GAP_S:
                    start["time"] += dt
            if prev.altitude is not None and tp.altitude is not None:
                delta = tp.altitude - prev.altitude
                if delta > 0:
                    start["gain"] += delta
                else:
                    start["loss"] += -delta
        prev = tp

    splits: list[Split] = []
    for idx in sorted(acc):
        bucket = acc[idx]
        seg_dist = min(metres, total - idx * metres)
        if seg_dist <= 0:
            continue
        pace = (bucket["time"] / (seg_dist / 1000.0)) if bucket["time"] > 0 else None
        avg_hr = int(round(bucket["hr_sum"] / bucket["hr_n"])) if bucket["hr_n"] else None
        splits.append(Split(
            idx + 1, seg_dist, bucket["time"], pace, avg_hr,
            bucket["gain"], bucket["loss"],
        ))

    paced = [s for s in splits if s.pace_s_per_km is not None]
    fastest = min(paced, key=lambda s: s.pace_s_per_km).index if paced else None
    slowest = max(paced, key=lambda s: s.pace_s_per_km).index if paced else None
    return {
        "metres": metres,
        "unit": "mi" if abs(metres - MILE_M) < 1.0 else "km",
        "splits": [s.as_dict() for s in splits],
        "fastest_index": fastest,
        "slowest_index": slowest,
    }

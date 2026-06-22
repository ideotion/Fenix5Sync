# SPDX-License-Identifier: GPL-3.0-or-later
"""Heart-rate and power training-zone analysis (pure, stdlib-only).

Computes time-in-zone from an activity's trackpoint series, given athlete
thresholds. These are conventional defaults; both schemes are configurable:

  * **Heart rate** -- a 5-zone model as a percentage of maximum HR
    (Z1 <60%, Z2 60-70%, Z3 70-80%, Z4 80-90%, Z5 >=90%). When no max HR is
    configured we fall back to the activity's own observed maximum, so the
    breakdown is still meaningful out of the box (and we say so via ``basis``).
  * **Power** -- the 7-zone model as a percentage of Functional Threshold Power
    (Coggan: Z1 <=55%, Z2 56-75%, Z3 76-90%, Z4 91-105%, Z5 106-120%,
    Z6 121-150%, Z7 >150%). Power zones need an FTP; without one they're omitted.

Time is integrated from trackpoint timestamps; a gap longer than ``_MAX_GAP_S``
is treated as a pause/stop and not attributed to any zone, so auto-pause and
rests don't inflate a band. When timestamps are absent each sample counts as one
second. Everything runs locally with no network and no third-party dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from .config import AthleteConfig
from .models import Activity, Trackpoint

# Default zone *upper* bounds as fractions of the threshold (max HR / FTP). The
# final bound is open-ended (``math.inf``). Boundaries follow common practice.
_HR_ZONE_PCTS = (0.60, 0.70, 0.80, 0.90, math.inf)
_HR_ZONE_NAMES = ("Z1 Recovery", "Z2 Endurance", "Z3 Tempo", "Z4 Threshold", "Z5 VO2 Max")

_POWER_ZONE_PCTS = (0.55, 0.75, 0.90, 1.05, 1.20, 1.50, math.inf)
_POWER_ZONE_NAMES = (
    "Z1 Active Recovery", "Z2 Endurance", "Z3 Tempo", "Z4 Threshold",
    "Z5 VO2 Max", "Z6 Anaerobic", "Z7 Neuromuscular",
)

# Trackpoint gaps longer than this (seconds) are treated as a stop, not time in zone.
_MAX_GAP_S = 30.0


@dataclass
class ZoneBin:
    """Time spent in one training zone."""

    index: int          # 1-based zone number
    name: str
    low: float          # inclusive lower bound, in the metric's unit (bpm or W)
    high: float | None  # exclusive upper bound; None = open-ended (top zone)
    seconds: float
    percent: float      # share of total in-zone time, 0..100

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "low": int(round(self.low)),
            "high": (int(round(self.high)) if self.high is not None else None),
            "seconds": round(self.seconds, 1),
            "percent": round(self.percent, 1),
        }


def _sample_durations(points: Sequence[Trackpoint]) -> list[float]:
    """Seconds attributable to each trackpoint (forward delta, gaps capped).

    Uses the interval to the next sample; the final sample mirrors the previous
    interval so it isn't dropped. Falls back to 1s/sample when timestamps are
    missing.
    """
    n = len(points)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    times = [tp.timestamp for tp in points]
    if any(t is None for t in times):
        return [1.0] * n
    durs = [0.0] * n
    for i in range(n - 1):
        dt = (times[i + 1] - times[i]).total_seconds()
        durs[i] = dt if 0.0 < dt <= _MAX_GAP_S else 0.0
    durs[-1] = durs[-2]  # mirror the last known interval
    return durs


def _bin(
    points: Sequence[Trackpoint],
    value_of: Callable[[Trackpoint], float | int | None],
    threshold: float,
    pcts: tuple[float, ...],
    names: tuple[str, ...],
) -> list[ZoneBin]:
    """Bucket time-in-zone for ``points`` given absolute ``threshold`` and bands."""
    edges = [threshold * p for p in pcts]  # upper bounds; last is inf
    durs = _sample_durations(points)
    secs = [0.0] * len(names)
    for tp, dt in zip(points, durs):
        v = value_of(tp)
        if v is None or dt <= 0:
            continue
        for zi, hi in enumerate(edges):
            if v < hi or zi == len(edges) - 1:
                secs[zi] += dt
                break
    total = sum(secs)
    bins: list[ZoneBin] = []
    low = 0.0
    for i, (name, hi) in enumerate(zip(names, edges)):
        high = None if math.isinf(hi) else hi
        pct = (secs[i] / total * 100.0) if total > 0 else 0.0
        bins.append(ZoneBin(i + 1, name, low, high, secs[i], pct))
        low = hi
    return bins


def hr_zones(points: Sequence[Trackpoint], max_hr: float | int | None) -> list[ZoneBin]:
    """Heart-rate time-in-zone (5-zone %-of-max model). Empty if no usable max HR."""
    if not max_hr or max_hr <= 0:
        return []
    return _bin(points, lambda tp: tp.heart_rate, float(max_hr), _HR_ZONE_PCTS, _HR_ZONE_NAMES)


def power_zones(points: Sequence[Trackpoint], ftp: float | int | None) -> list[ZoneBin]:
    """Power time-in-zone (7-zone %-of-FTP / Coggan model). Empty if no FTP."""
    if not ftp or ftp <= 0:
        return []
    return _bin(points, lambda tp: tp.power, float(ftp), _POWER_ZONE_PCTS, _POWER_ZONE_NAMES)


def compute_zones(activity: Activity, athlete: AthleteConfig) -> dict:
    """HR + power zone breakdown for an activity using athlete thresholds.

    HR uses ``athlete.max_heart_rate`` when set, otherwise the activity's own
    observed maximum (so zones render without configuration). Power uses
    ``athlete.ftp_w`` and is omitted -- with a ``needs_ftp`` hint -- when no FTP
    is configured. The local archive is only read, never modified.
    """
    pts = activity.trackpoints
    has_hr = any(tp.heart_rate is not None for tp in pts)
    has_power = any(tp.power is not None for tp in pts)

    hr_max = athlete.max_heart_rate or activity.max_heart_rate
    hr_basis = (
        "configured" if athlete.max_heart_rate
        else "observed" if activity.max_heart_rate
        else None
    )
    hr = hr_zones(pts, hr_max) if (has_hr and hr_max) else []
    power = power_zones(pts, athlete.ftp_w) if (has_power and athlete.ftp_w) else []

    return {
        "hr": {
            "max_heart_rate": int(hr_max) if hr_max else None,
            "basis": hr_basis,
            "zones": [z.as_dict() for z in hr],
        },
        "power": {
            "ftp_w": int(athlete.ftp_w) if athlete.ftp_w else None,
            "available": bool(power),
            "needs_ftp": bool(has_power and not athlete.ftp_w),
            "zones": [z.as_dict() for z in power],
        },
    }

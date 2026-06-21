"""Best-efforts and mean-max curves for a single activity (pure, stdlib-only).

Two complementary "peak performance" views, both computed from one activity's
own trackpoint series (so there is no archive-wide N+1 -- a later module can
aggregate these per-activity results into all-time PRs):

  * **best distances** -- the fastest time to cover each standard distance
    (200 m … marathon) found anywhere in the activity, via a sliding window over
    cumulative distance and timestamps. This is the runner's "fastest 1 K / 5 K
    in this run", pauses and all (a window straddling a stop is simply slower, so
    the fastest window never includes one).
  * **mean-max curves** -- the highest sustained average **power** and **speed**
    over each standard duration (5 s … 60 min): the classic power-duration /
    pace-duration curve. Windows are measured in samples, i.e. seconds at the
    usual 1 Hz recording (documented approximation, matching core.metrics /
    core.training_load).

Read-only over the activity; no third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .models import Activity

# Standard race distances (metres) and their labels, ascending.
_DISTANCES: tuple[tuple[float, str], ...] = (
    (200, "200 m"), (400, "400 m"), (800, "800 m"), (1000, "1 km"),
    (1609.344, "1 mile"), (5000, "5 km"), (10000, "10 km"),
    (21097.5, "Half marathon"), (42195, "Marathon"),
)

# Standard durations (seconds ≈ samples at 1 Hz) for the mean-max curves.
_DURATIONS: tuple[tuple[int, str], ...] = (
    (5, "5 s"), (15, "15 s"), (30, "30 s"), (60, "1 min"), (300, "5 min"),
    (600, "10 min"), (1200, "20 min"), (1800, "30 min"), (3600, "60 min"),
)


@dataclass
class BestEffort:
    """The fastest time to cover one standard distance within an activity."""

    distance_m: float
    label: str
    time_s: float
    pace_s_per_km: int

    def as_dict(self) -> dict:
        return {
            "distance_m": self.distance_m,
            "label": self.label,
            "time_s": round(self.time_s, 1),
            "pace_s_per_km": self.pace_s_per_km,
        }


def _fastest_time_for_distance(
    dist: Sequence[float], secs: Sequence[float], target: float
) -> float | None:
    """Smallest elapsed time covering ``target`` metres (monotone two-pointer)."""
    n = len(dist)
    best: float | None = None
    j = 0
    for i in range(n):
        if j <= i:
            j = i + 1
        while j < n and dist[j] - dist[i] < target:
            j += 1
        if j >= n:
            break  # no window starting at i (or later) reaches the distance
        dt = secs[j] - secs[i]
        if dt > 0 and (best is None or dt < best):
            best = dt
    return best


def _peak_rolling_mean(values: Sequence[float], window: int) -> float | None:
    """Maximum average over any ``window``-sample run, or None if too short."""
    n = len(values)
    if n < window or window <= 0:
        return None
    acc = sum(values[:window])
    best = acc
    for i in range(window, n):
        acc += values[i] - values[i - window]
        if acc > best:
            best = acc
    return best / window


def compute_best_efforts(activity: Activity) -> dict:
    """Best-effort times and mean-max power/speed curves for one activity.

    Returns ``best_distances`` (fastest time per standard distance that fits in
    the activity), ``power_curve`` (peak mean watts per duration; ``None`` without
    power) and ``speed_curve`` (peak mean m/s per duration; ``None`` without
    speed). Each list only includes entries the data can actually support.
    """
    pts = activity.trackpoints

    # ---- best distances (needs cumulative distance + timestamps) -----------
    fixes = [
        (tp.distance, tp.timestamp)
        for tp in pts
        if tp.distance is not None and tp.timestamp is not None
    ]
    best_distances: list[dict] = []
    if len(fixes) >= 2:
        dist = [f[0] for f in fixes]
        t0: datetime = fixes[0][1]
        secs = [(f[1] - t0).total_seconds() for f in fixes]
        covered = dist[-1] - dist[0]
        for metres, label in _DISTANCES:
            if metres > covered:
                break  # distances are ascending; nothing longer will fit either
            best = _fastest_time_for_distance(dist, secs, metres)
            if best is not None and best > 0:
                best_distances.append(
                    BestEffort(metres, label, best, round(best / (metres / 1000.0))).as_dict()
                )

    # ---- mean-max curves (duration-based; 1 Hz assumption) -----------------
    powers = [float(tp.power) for tp in pts if tp.power is not None]
    speeds = [float(tp.speed) for tp in pts if tp.speed is not None]

    power_curve = None
    if powers:
        power_curve = []
        for dur, label in _DURATIONS:
            peak = _peak_rolling_mean(powers, dur)
            if peak is not None:
                power_curve.append({"duration_s": dur, "label": label, "watts": int(round(peak))})

    speed_curve = None
    if speeds:
        speed_curve = []
        for dur, label in _DURATIONS:
            peak = _peak_rolling_mean(speeds, dur)
            if peak is not None:
                speed_curve.append({
                    "duration_s": dur,
                    "label": label,
                    "speed_mps": round(peak, 3),
                    "pace_s_per_km": (round(1000.0 / peak) if peak > 0 else None),
                })

    return {
        "best_distances": best_distances,
        "power_curve": power_curve,
        "speed_curve": speed_curve,
    }

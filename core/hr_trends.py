# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-activity heart-rate & efficiency trends (pure, stdlib-only).

Tracks how the aerobic engine changes over time from activity *summaries* only
(avg/max HR, avg speed/power) -- a single cheap pass over the archive, never an
N+1 over trackpoints:

  * **avg / max HR per activity** over time, plus the observed maximum -- a useful
    sanity check for (or nudge toward) a configured max-HR threshold.
  * **Efficiency Factor** per activity -- output per heartbeat, i.e. power/HR when
    a power meter was used, otherwise speed/HR -- whose upward drift over weeks is
    the classic sign of improving aerobic fitness.

Honest-basis ethos (mirrors :mod:`core.training_load`): the EF basis is recorded
(``power`` / ``pace`` / ``mixed``) and is ``None`` when nothing supports it. Pass
``sport`` to scope every figure to one sport. Read-only over the activities, with
no third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .models import Activity

# Per-basis EF unit family, collapsed to the series' overall ``ef_basis``.
_EF_UNIT = {"power": "power", "pace": "pace"}


def _utc_date(dt: datetime) -> str:
    """Calendar date (UTC) as YYYY-MM-DD (tz-aware converted; naive assumed UTC)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat()


def _efficiency(activity: Activity) -> tuple[float, str] | tuple[None, None]:
    """Efficiency Factor for an activity: power/HR, else speed/HR, else nothing."""
    hr = activity.avg_heart_rate
    if not hr:
        return None, None
    if activity.avg_power and activity.avg_power > 0:
        return activity.avg_power / hr, "power"          # W per bpm
    if activity.avg_speed and activity.avg_speed > 0:
        return activity.avg_speed * 60.0 / hr, "pace"    # m/min per bpm
    return None, None


@dataclass
class HRPoint:
    """One activity's heart-rate / efficiency datapoint on the trend."""

    date: str
    activity_id: int | None
    avg_hr: int
    max_hr: int | None
    efficiency: float | None
    ef_basis: str | None

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "activity_id": self.activity_id,
            "avg_hr": self.avg_hr,
            "max_hr": self.max_hr,
            "efficiency": (round(self.efficiency, 2) if self.efficiency is not None else None),
            "ef_basis": self.ef_basis,
        }


def compute_hr_trends(
    activities: Iterable[Activity], *, sport: str | None = None
) -> dict:
    """Heart-rate and efficiency trend over the activity history.

    Returns chronological per-activity ``points`` (date, avg/max HR, Efficiency
    Factor), a ``summary`` (counts, observed max HR, mean avg HR) and the overall
    ``ef_basis`` (``power`` / ``pace`` / ``mixed`` / ``None``). Computed from
    summaries only; the activities are read, never modified.
    """
    acts = [a for a in activities if sport is None or a.sport == sport]

    points: list[HRPoint] = []
    bases: set[str] = set()
    for a in acts:
        if a.start_time is None or not a.avg_heart_rate:
            continue
        ef, basis = _efficiency(a)
        if basis is not None:
            bases.add(_EF_UNIT[basis])
        points.append(HRPoint(
            _utc_date(a.start_time), a.id, int(a.avg_heart_rate),
            int(a.max_heart_rate) if a.max_heart_rate else None, ef, basis,
        ))
    points.sort(key=lambda p: (p.date, p.activity_id or 0))

    max_hrs = [p.max_hr for p in points if p.max_hr is not None]
    avg_hrs = [p.avg_hr for p in points]
    if not bases:
        ef_basis = None
    elif len(bases) == 1:
        ef_basis = next(iter(bases))
    else:
        ef_basis = "mixed"

    return {
        "sport": sport,
        "ef_basis": ef_basis,
        "points": [p.as_dict() for p in points],
        "summary": {
            "activities": len(acts),
            "with_hr": len(points),
            "observed_max_hr": max(max_hrs) if max_hrs else None,
            "avg_hr": int(round(sum(avg_hrs) / len(avg_hrs))) if avg_hrs else None,
        },
    }

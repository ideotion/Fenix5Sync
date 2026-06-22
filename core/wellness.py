# SPDX-License-Identifier: GPL-3.0-or-later
"""Daily wellness / readiness summaries from Garmin *monitoring* files (stdlib + fitparse).

The watch writes separate **monitoring** FIT files (steps, all-day heart rate, and
stress) apart from activity files. This reads those into one summary per UTC day:

  * **steps** -- the day's cumulative step count;
  * an all-day **heart-rate** profile -- ``resting_hr`` (the day's minimum, a decent
    resting proxy), plus average and maximum;
  * average **stress** and the number of valid stress samples.

Scope and honesty: HRV, sleep stages and SpO2 live in monitoring message types that
``fitparse``'s profile does not currently decode, so they are deliberately out of
scope here and await an SDK-grade decode pass. Real devices sometimes store a 16-bit
timestamp offset (resolved against a ``monitoring_info`` reference) rather than a full
timestamp; this first pass summarises records that carry a full timestamp. ``fitparse``
is imported lazily (like :mod:`core.parse`) so the rest of ``core`` stays importable
without it. The file is only read, never modified.
"""

from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class WellnessParseError(Exception):
    """Raised when a monitoring file cannot be read."""


def _intish(value: Any) -> int | None:
    try:
        return int(round(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def _utc_date(dt: _dt.datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt.timezone.utc)
    return dt.date().isoformat()


@dataclass
class DayWellness:
    """One UTC day of monitoring-derived wellness."""

    date: str
    steps: int | None
    resting_hr: int | None  # day minimum HR (resting proxy)
    avg_hr: int | None
    max_hr: int | None
    avg_stress: int | None
    stress_samples: int

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "steps": self.steps,
            "resting_hr": self.resting_hr,
            "avg_hr": self.avg_hr,
            "max_hr": self.max_hr,
            "avg_stress": self.avg_stress,
            "stress_samples": self.stress_samples,
        }


def summarize_wellness(records: Iterable[dict]) -> list[DayWellness]:
    """Aggregate per-sample monitoring records into one summary per day.

    Each record is ``{"date", "hr", "steps", "stress"}`` with any field optional.
    Steps are treated as cumulative (the day's maximum is taken); HR yields
    min/avg/max; stress is averaged over valid samples.
    """
    buckets: dict[str, dict[str, list]] = defaultdict(lambda: {"hr": [], "steps": [], "stress": []})
    for r in records:
        date = r.get("date")
        if not date:
            continue
        b = buckets[date]
        if r.get("hr") is not None:
            b["hr"].append(r["hr"])
        if r.get("steps") is not None:
            b["steps"].append(r["steps"])
        if r.get("stress") is not None:
            b["stress"].append(r["stress"])

    out: list[DayWellness] = []
    for date in sorted(buckets):
        b = buckets[date]
        hrs, steps, stress = b["hr"], b["steps"], b["stress"]
        out.append(DayWellness(
            date=date,
            steps=int(max(steps)) if steps else None,
            resting_hr=int(min(hrs)) if hrs else None,
            avg_hr=int(round(sum(hrs) / len(hrs))) if hrs else None,
            max_hr=int(max(hrs)) if hrs else None,
            avg_stress=int(round(sum(stress) / len(stress))) if stress else None,
            stress_samples=len(stress),
        ))
    return out


def _read_records(path: str | Path) -> list[dict]:
    try:
        from fitparse import FitFile
        from fitparse.utils import FitParseError
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise WellnessParseError(f"fitparse is not available: {exc}") from exc

    path = Path(path)
    try:
        fit = FitFile(str(path))
        fit.parse()
    except FitParseError as exc:
        raise WellnessParseError(f"{path.name}: corrupt or truncated FIT ({exc})") from exc
    except Exception as exc:  # defensive
        raise WellnessParseError(f"{path.name}: failed to read FIT ({exc})") from exc

    records: list[dict] = []
    for msg in fit.get_messages("monitoring"):
        vals = {f.name: f.value for f in msg.fields if f.value is not None}
        ts = vals.get("timestamp")
        if not isinstance(ts, _dt.datetime):
            continue
        records.append({
            "date": _utc_date(ts),
            "hr": _intish(vals.get("heart_rate")),
            "steps": _intish(vals.get("steps") if vals.get("steps") is not None else vals.get("cycles")),
            "stress": None,
        })
    for msg in fit.get_messages("stress_level"):
        vals = {f.name: f.value for f in msg.fields if f.value is not None}
        ts = vals.get("stress_level_time")
        val = _intish(vals.get("stress_level_value"))
        if not isinstance(ts, _dt.datetime) or val is None or not (0 <= val <= 100):
            continue  # -1/-2 are device sentinels for invalid / too-active
        records.append({"date": _utc_date(ts), "hr": None, "steps": None, "stress": val})
    return records


def parse_wellness_file(path: str | Path) -> dict:
    """Parse a monitoring FIT file into ``{"days": [DayWellness.as_dict(), ...]}``.

    Read-only. Raises :class:`WellnessParseError` if the file can't be read.
    """
    days = summarize_wellness(_read_records(path))
    return {"days": [d.as_dict() for d in days]}

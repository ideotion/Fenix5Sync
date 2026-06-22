# SPDX-License-Identifier: GPL-3.0-or-later
"""Year-in-Sport recap: a private, local annual (and all-time) summary.

Pure, stdlib-only aggregation over the summary fields already in the store -- no
trackpoints needed, so it is cheap and runs entirely offline. The web layer turns
the result into a self-contained, shareable HTML card; nothing leaves the machine
unless the user chooses to share the exported file.

Why this exists is documented (with sources) in ``docs/recap/decision-brief.md``
and surfaced discreetly in the UI: end-of-year recaps were a free staple for ~a
decade before both major platforms moved them behind subscriptions in Dec 2025.
A recap computed from your own archive needs no account and no cloud.

Everything here is a deterministic function of a list of
:class:`~core.models.Activity` summaries, which keeps it trivially testable.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Iterable

from .models import Activity

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _local_date(dt: datetime | None) -> date | None:
    """Calendar date of an activity (UTC), matching the store's other analytics."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def available_years(activities: Iterable[Activity]) -> list[int]:
    """Distinct calendar years that have at least one dated activity, descending."""
    years = {d.year for a in activities if (d := _local_date(a.start_time))}
    return sorted(years, reverse=True)


def _num(value: float | int | None) -> float:
    return float(value) if value is not None else 0.0


def _highlight(activity: Activity, value: float) -> dict:
    return {
        "activity_id": activity.id,
        "date": d.isoformat() if (d := _local_date(activity.start_time)) else None,
        "sport": activity.sport,
        "value": round(value, 2),
    }


def _longest_streak(days: set[date]) -> int:
    """Longest run of consecutive calendar days that have an activity."""
    if not days:
        return 0
    ordered = sorted(days)
    best = run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    return best


def _totals(scope: list[Activity]) -> dict:
    return {
        "count": len(scope),
        "distance_m": round(sum(_num(a.total_distance) for a in scope), 1),
        "duration_s": round(sum(_num(a.total_timer_time) for a in scope), 1),
        "ascent_m": round(sum(_num(a.total_ascent) for a in scope), 1),
        "calories": round(sum(_num(a.total_calories) for a in scope), 1),
    }


def _by_sport(scope: list[Activity]) -> list[dict]:
    agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "distance_m": 0.0, "duration_s": 0.0})
    for a in scope:
        sport = a.sport or "unknown"
        agg[sport]["count"] += 1
        agg[sport]["distance_m"] += _num(a.total_distance)
        agg[sport]["duration_s"] += _num(a.total_timer_time)
    out = [
        {"sport": s, "count": v["count"],
         "distance_m": round(v["distance_m"], 1), "duration_s": round(v["duration_s"], 1)}
        for s, v in agg.items()
    ]
    # Busiest sport first (by time, then distance, then count).
    out.sort(key=lambda r: (r["duration_s"], r["distance_m"], r["count"]), reverse=True)
    return out


def _highlights(scope: list[Activity]) -> dict:
    def top(metric) -> dict | None:
        best = None
        for a in scope:
            v = metric(a)
            if v and (best is None or v > best[1]):
                best = (a, v)
        return _highlight(best[0], best[1]) if best else None

    return {
        "longest_distance": top(lambda a: _num(a.total_distance)),
        "longest_duration": top(lambda a: _num(a.total_timer_time)),
        "biggest_climb": top(lambda a: _num(a.total_ascent)),
        "fastest_avg_speed": top(lambda a: _num(a.avg_speed)),
    }


def _biggest_day(scope: list[Activity]) -> dict | None:
    per_day: dict[date, dict] = defaultdict(lambda: {"distance_m": 0.0, "count": 0})
    for a in scope:
        d = _local_date(a.start_time)
        if d is None:
            continue
        per_day[d]["distance_m"] += _num(a.total_distance)
        per_day[d]["count"] += 1
    if not per_day:
        return None
    day, agg = max(per_day.items(), key=lambda kv: kv[1]["distance_m"])
    return {"date": day.isoformat(), "distance_m": round(agg["distance_m"], 1), "count": agg["count"]}


def _months(scope: list[Activity], year: int) -> list[dict]:
    """Twelve-entry month-by-month breakdown for a single year (calendar sparkline)."""
    buckets = [{"month": m, "name": _MONTH_NAMES[m - 1], "count": 0,
                "distance_m": 0.0, "duration_s": 0.0} for m in range(1, 13)]
    for a in scope:
        d = _local_date(a.start_time)
        if d is None:
            continue
        b = buckets[d.month - 1]
        b["count"] += 1
        b["distance_m"] += _num(a.total_distance)
        b["duration_s"] += _num(a.total_timer_time)
    for b in buckets:
        b["distance_m"] = round(b["distance_m"], 1)
        b["duration_s"] = round(b["duration_s"], 1)
    return buckets


def _years(scope: list[Activity]) -> list[dict]:
    """Year-by-year breakdown (the all-time recap's equivalent of the month chart)."""
    buckets: dict[int, dict] = defaultdict(lambda: {"count": 0, "distance_m": 0.0, "duration_s": 0.0})
    for a in scope:
        d = _local_date(a.start_time)
        if d is None:
            continue
        buckets[d.year]["count"] += 1
        buckets[d.year]["distance_m"] += _num(a.total_distance)
        buckets[d.year]["duration_s"] += _num(a.total_timer_time)
    return [
        {"year": y, "count": v["count"],
         "distance_m": round(v["distance_m"], 1), "duration_s": round(v["duration_s"], 1)}
        for y, v in sorted(buckets.items())
    ]


def compute_recap(activities: Iterable[Activity], year: int | None = None) -> dict:
    """Build a recap for one calendar ``year`` (or all-time when ``year`` is None).

    Accepts activity *summaries* (no trackpoints required). Returns a JSON-able
    dict with totals, per-sport and per-period breakdowns, headline highlights,
    consistency metrics, and -- for a single year -- a delta versus the year
    before. ``available_years`` always lists every year with data so the UI can
    offer a picker.
    """
    acts = [a for a in activities if a.start_time is not None]
    years_present = available_years(acts)

    if year is None:
        scope = acts
        period_label = "All time"
        period_buckets = {"by_year": _years(scope)}
    else:
        scope = [a for a in acts if (d := _local_date(a.start_time)) and d.year == year]
        period_label = str(year)
        period_buckets = {"by_month": _months(scope, year)}

    days_active = {d for a in scope if (d := _local_date(a.start_time))}
    by_sport = _by_sport(scope)
    months = _months(scope, year) if year is not None else None
    busiest_month = None
    if months:
        top = max(months, key=lambda m: (m["count"], m["distance_m"]))
        if top["count"]:
            busiest_month = {"month": top["month"], "name": top["name"],
                             "count": top["count"], "distance_m": top["distance_m"]}

    # Year-over-year comparison (single-year recaps only).
    comparison = None
    if year is not None:
        prev = [a for a in acts if (d := _local_date(a.start_time)) and d.year == year - 1]
        if prev:
            pt = _totals(prev)
            ct = _totals(scope)
            comparison = {
                "prev_year": year - 1,
                "count_delta": ct["count"] - pt["count"],
                "distance_delta_m": round(ct["distance_m"] - pt["distance_m"], 1),
                "duration_delta_s": round(ct["duration_s"] - pt["duration_s"], 1),
            }

    dates = sorted(days_active)
    return {
        "period": period_label,
        "year": year,
        "available_years": years_present,
        "totals": _totals(scope),
        "by_sport": by_sport,
        "primary_sport": by_sport[0]["sport"] if by_sport else None,
        "highlights": _highlights(scope),
        "biggest_day": _biggest_day(scope),
        "active_days": len(days_active),
        "longest_streak_days": _longest_streak(days_active),
        "first_activity": dates[0].isoformat() if dates else None,
        "last_activity": dates[-1].isoformat() if dates else None,
        "busiest_month": busiest_month,
        "comparison": comparison,
        **period_buckets,
    }

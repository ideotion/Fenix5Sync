# SPDX-License-Identifier: GPL-3.0-or-later
"""Training-load & form analytics -- the Performance Management Chart (pure, stdlib-only).

Turns a local activity history into the three numbers serious endurance athletes
track over time (the model popularised by TrainingPeaks and mirrored by
Intervals.icu / Runalyze):

  * **Fitness (CTL)** -- Chronic Training Load: a slow, ``ctl_days``-window
    (42 by default) exponentially-weighted moving average of daily training
    stress. "How much work you're used to."
  * **Fatigue (ATL)** -- Acute Training Load: the same EWMA over a short
    ``atl_days`` window (7 by default). "How tired recent work has left you."
  * **Form (TSB)** -- Training Stress Balance: *yesterday's* fitness minus
    *yesterday's* fatigue. Positive = fresh/tapered, negative = loaded/building.

The pipeline is two stages. First, every activity is reduced to a single
**training-load** number on the best basis its data (and the athlete's
thresholds) supports -- and we record which basis was used, never pretending to
more precision than the inputs allow:

  * **power** (needs ``athlete.ftp_w`` + power): Coggan TSS. Intensity Factor
    ``IF = NP / FTP`` and ``TSS = 100 * hours * IF**2``. Normalized Power is the
    4th root of the mean of the 30-second rolling-average power raised to the 4th
    power; with only a summary loaded (no series) we approximate ``NP ~= avg_power``
    and say so via the ``power`` coverage count.
  * **hr** (needs ``athlete.max_heart_rate``; ``resting_heart_rate`` optional,
    defaulting to :data:`_DEFAULT_RESTING_HR`): Banister TRIMP,
    ``TRIMP = minutes * HRr * 0.64 * e**(1.92 * HRr)`` with the heart-rate reserve
    ``HRr = (HR - rest) / (max - rest)`` clamped to ``[0, 1]``, then linearly
    scaled (:data:`_TRIMP_SCALE`) so a hard hour -- ~60 min at ``HRr ~= 0.85`` --
    lands near 100, keeping it comparable to a power TSS.
  * **duration** (no usable thresholds): ``minutes * k`` with a flat, documented
    ``k`` (:data:`_DURATION_LOAD_PER_MIN`). These days are honest guesses and are
    counted under ``duration`` so callers can flag them low-confidence.

Second, one daily total per **UTC calendar day** is laid out on a gap-free
timeline from the first to the last active day (empty days contribute 0) and the
two EWMAs are run forward:

    CTL_d = CTL_{d-1} + (load_d - CTL_{d-1}) * (1 - e**(-1/ctl_days))
    ATL_d = ATL_{d-1} + (load_d - ATL_{d-1}) * (1 - e**(-1/atl_days))
    TSB_d = CTL_{d-1} - ATL_{d-1}

seeded with ``CTL = ATL = 0``. Because of that zero seed the first ~6 weeks
*understate* CTL (the "early ramp" caveat): treat the opening of a fresh history
as warming up, not as ground truth.

The whole series is kept in one ``unit`` (``"tss" | "trimp" | "mixed"``). This is
an open, defensible approximation -- it deliberately does **not** try to
reproduce Garmin's proprietary FirstBeat Training Status / Load Focus figures.
Everything runs locally with no network, is read-only over the activities (never
mutated), and adds no third-party dependency.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Sequence

from .config import AthleteConfig
from .models import Activity

# Banister TRIMP coefficients (the conventional male reference) plus a normaliser
# that puts a hard hour (~60 min at HRr ~= 0.85) near 100, so HR-scored days stay
# comparable to a power TSS rather than living on their own arbitrary scale.
_TRIMP_B = 0.64
_TRIMP_C = 1.92
_TRIMP_REF_MINUTES = 60.0
_TRIMP_REF_HRR = 0.85
_TRIMP_REF_TARGET = 100.0
_TRIMP_SCALE = _TRIMP_REF_TARGET / (
    _TRIMP_REF_MINUTES * _TRIMP_REF_HRR * _TRIMP_B * math.exp(_TRIMP_C * _TRIMP_REF_HRR)
)

# Resting HR assumed when the athlete hasn't configured one (a common adult value).
_DEFAULT_RESTING_HR = 60

# Load per minute for the duration-only fallback (~60 per hour: a moderate effort
# in TSS-equivalent terms). Flat and intentionally rough -- see the module docstring.
_DURATION_LOAD_PER_MIN = 1.0

# Normalized-power rolling window, in samples (~seconds at the typical 1 Hz recording).
_NP_WINDOW_S = 30

# The "unit family" each basis reports in (a duration estimate is TSS-shaped).
_BASIS_UNIT = {"power": "tss", "hr": "trimp", "duration": "tss"}


def _normalized_power(powers: Sequence[float | int], window: int = _NP_WINDOW_S) -> float:
    """Normalized Power from a (roughly 1 Hz) power series.

    The 4th root of the mean of the ``window``-second rolling-average power raised
    to the 4th power (Coggan). Samples are treated as consecutive seconds and
    dropouts are dropped rather than interpolated; series shorter than one window
    fall back to a plain mean. Returns 0.0 for an empty series.
    """
    vals = [float(p) for p in powers if p is not None]
    n = len(vals)
    if n == 0:
        return 0.0
    w = window if n >= window else n
    acc = sum(vals[:w])
    rolled = [acc / w]
    for i in range(w, n):
        acc += vals[i] - vals[i - w]
        rolled.append(acc / w)
    return (sum(r ** 4 for r in rolled) / len(rolled)) ** 0.25


def _has_power(activity: Activity) -> bool:
    """True if the activity carries any power data (summary average or a series)."""
    return bool(activity.avg_power) or any(tp.power for tp in activity.trackpoints)


def _activity_np(activity: Activity) -> float | None:
    """Best Normalized Power estimate: from the series if loaded, else ``avg_power``."""
    series = [tp.power for tp in activity.trackpoints if tp.power is not None]
    if series:
        return _normalized_power(series)
    return float(activity.avg_power) if activity.avg_power else None


def _score_activity(
    activity: Activity, athlete: AthleteConfig, *, resting_hr: float
) -> tuple[float, str] | tuple[None, None]:
    """One activity's daily-load contribution and the basis it used.

    Prefers power TSS, then HR TRIMP, then a flat duration estimate. Returns
    ``(None, None)`` when the activity has no usable duration to score at all.
    """
    duration_s = activity.total_timer_time or 0.0
    if duration_s <= 0:
        return None, None
    minutes = duration_s / 60.0

    # Power TSS -- the most precise basis, when an FTP and power data are present.
    if athlete.ftp_w and athlete.ftp_w > 0:
        np = _activity_np(activity)
        if np and np > 0:
            intensity = np / float(athlete.ftp_w)
            return 100.0 * (duration_s / 3600.0) * intensity * intensity, "power"

    # HR TRIMP -- needs a max HR and an average HR for the session.
    if athlete.max_heart_rate and athlete.max_heart_rate > 0 and activity.avg_heart_rate:
        span = float(athlete.max_heart_rate) - resting_hr
        if span > 0:
            hrr = (float(activity.avg_heart_rate) - resting_hr) / span
            hrr = min(1.0, max(0.0, hrr))
            trimp = minutes * hrr * _TRIMP_B * math.exp(_TRIMP_C * hrr)
            return trimp * _TRIMP_SCALE, "hr"

    # Duration fallback -- a flat, low-confidence estimate (no thresholds available).
    return minutes * _DURATION_LOAD_PER_MIN, "duration"


def _utc_date(dt: datetime) -> date:
    """Calendar date in UTC (tz-aware values are converted; naive assumed UTC)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


@dataclass
class DayLoad:
    """One calendar day on the Performance Management Chart."""

    date: str    # YYYY-MM-DD (UTC)
    load: float  # daily training-load total
    ctl: float   # fitness
    atl: float   # fatigue
    tsb: float   # form (prior-day ctl - atl)

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "load": round(self.load, 1),
            "ctl": round(self.ctl, 1),
            "atl": round(self.atl, 1),
            "tsb": round(self.tsb, 1),
        }


@dataclass
class TrainingLoad:
    """A computed Performance Management Chart, ready to serialise."""

    unit: str
    ctl_days: int
    atl_days: int
    series: list[DayLoad]
    coverage: dict
    needs: list[str]

    def as_dict(self) -> dict:
        last = self.series[-1].as_dict() if self.series else None
        current = (
            {"date": last["date"], "ctl": last["ctl"], "atl": last["atl"], "tsb": last["tsb"]}
            if last
            else None
        )
        return {
            "unit": self.unit,
            "ctl_days": self.ctl_days,
            "atl_days": self.atl_days,
            "current": current,
            "series": [d.as_dict() for d in self.series],
            "coverage": self.coverage,
            "needs": self.needs,
        }


def _pmc_series(daily: dict[str, float], ctl_days: int, atl_days: int) -> list[DayLoad]:
    """Run the CTL/ATL/TSB EWMAs over a gap-free daily timeline.

    The timeline spans the first to the last day present in ``daily`` (inclusive);
    days with no activity contribute a load of 0. Form (TSB) is taken from the
    *prior* day's fitness and fatigue, seeded at zero.
    """
    if not daily:
        return []
    a_ctl = 1.0 - math.exp(-1.0 / ctl_days)
    a_atl = 1.0 - math.exp(-1.0 / atl_days)
    first = date.fromisoformat(min(daily))
    last = date.fromisoformat(max(daily))

    series: list[DayLoad] = []
    prev_ctl = prev_atl = 0.0
    day = first
    while day <= last:
        load = daily.get(day.isoformat(), 0.0)
        tsb = prev_ctl - prev_atl  # form uses the *prior* day's fitness/fatigue
        ctl = prev_ctl + (load - prev_ctl) * a_ctl
        atl = prev_atl + (load - prev_atl) * a_atl
        series.append(DayLoad(day.isoformat(), load, ctl, atl, tsb))
        prev_ctl, prev_atl = ctl, atl
        day += timedelta(days=1)
    return series


def compute_training_load(
    activities: Iterable[Activity],
    athlete: AthleteConfig,
    *,
    sport: str | None = None,
    ctl_days: int = 42,
    atl_days: int = 7,
    as_of: date | None = None,
) -> dict:
    """Performance Management Chart (CTL/ATL/TSB) over an activity history.

    Scores each activity to a daily training load on the best basis its data and
    ``athlete`` thresholds allow (power TSS, HR TRIMP, or a duration estimate),
    sums per UTC calendar day, then runs the fitness/fatigue EWMAs over a gap-free
    timeline. Pass ``sport`` to scope every figure to one sport (mirrors the
    Insights endpoint). Pass ``as_of`` (a date) to evaluate the chart up to that
    day: the timeline is extended with zero-load days so fitness and fatigue
    decay correctly when the most recent activity is in the past (the basis for
    "what's my form *today*, after a rest week?"). The activities are only read,
    never modified.

    Returns the serialisable shape documented at module scope: ``unit``,
    ``ctl_days``/``atl_days``, ``current`` (the latest day, or ``None`` when the
    history is empty), the full daily ``series``, a ``coverage`` summary (how many
    activities were scored and on which basis), and ``needs`` -- threshold hints
    (e.g. ``"ftp_w"``, ``"max_heart_rate"``) that would sharpen the estimate.
    """
    if ctl_days <= 0 or atl_days <= 0:
        raise ValueError("ctl_days and atl_days must be positive")

    acts = [a for a in activities if sport is None or a.sport == sport]
    resting_hr = float(athlete.resting_heart_rate or _DEFAULT_RESTING_HR)

    daily: dict[str, float] = defaultdict(float)
    basis_counts = {"power": 0, "hr": 0, "duration": 0}
    units_seen: set[str] = set()
    scored = 0
    for a in acts:
        if a.start_time is None:
            continue
        load, basis = _score_activity(a, athlete, resting_hr=resting_hr)
        if basis is None:
            continue
        daily[_utc_date(a.start_time).isoformat()] += load
        basis_counts[basis] += 1
        units_seen.add(_BASIS_UNIT[basis])
        scored += 1

    # Evaluate the chart "as of" a given day (typically today) by extending the
    # timeline with a zero-load day, so fitness/fatigue decay correctly when the
    # latest activity is in the past. Only ever extends an existing history.
    if as_of is not None and daily:
        daily.setdefault(as_of.isoformat(), 0.0)

    series = _pmc_series(daily, ctl_days, atl_days)

    if not units_seen:
        unit = "tss"
    elif len(units_seen) == 1:
        unit = next(iter(units_seen))
    else:
        unit = "mixed"

    needs: list[str] = []
    if any(_has_power(a) for a in acts) and not (athlete.ftp_w and athlete.ftp_w > 0):
        needs.append("ftp_w")
    if any(a.avg_heart_rate for a in acts) and not (
        athlete.max_heart_rate and athlete.max_heart_rate > 0
    ):
        needs.append("max_heart_rate")

    coverage = {"activities": len(acts), "scored": scored, "basis": basis_counts}
    return TrainingLoad(unit, ctl_days, atl_days, series, coverage, needs).as_dict()

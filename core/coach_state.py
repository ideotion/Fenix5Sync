# SPDX-License-Identifier: GPL-3.0-or-later
"""Dynamic-coach state -- the *sensor* layer the adaptive coach reads (pure, stdlib-only).

The dynamic coach is a closed-loop controller, not a chatbot: it never generates
text with an LLM. It reads a handful of well-established load/recovery signals off
your own history and (in :mod:`core.coach_plan`) prescribes the next sessions by
rule. This module is the sensor half -- it reduces an activity history (plus
optional wellness days) to a single :class:`CoachState`: where your
fitness/fatigue/form sit *today*, how fast you are ramping, whether recent load
looks risky, how monotonous it has been, and how long since your last hard day.

Everything here is derived from signals we already compute. It calls
:func:`core.training_load.compute_training_load` (with ``as_of`` so fitness and
fatigue decay to *today*) for the CTL/ATL/TSB timeline and reuses its honest
per-activity ``basis`` -- so there is one source of truth for the load maths and
no new dependency.

Signals
-------
* **CTL / ATL / TSB** -- fitness, fatigue and form, straight from the Performance
  Management Chart (see :mod:`core.training_load`).
* **Ramp rate** -- the change in CTL over the last 7 days (``ctl_today -
  ctl_7d_ago``): how fast you are adding fitness. Too fast is the classic
  injury/illness risk; Coggan's commonly-cited safe band is roughly +3..+7
  CTL/week.
* **ACWR** -- the Acute:Chronic Workload Ratio (Gabbett): the last 7 days of load
  over the 28-day rolling weekly average (a *coupled* rolling-average ACWR). The
  often-quoted "sweet spot" is ~0.8-1.3 with risk climbing past ~1.5. This model
  is genuinely contested (Lolli, Impellizzeri et al.), so we surface it as *one*
  signal with a caveat in ``notes`` -- never as a verdict.
* **Monotony & strain** -- Foster's training monotony (mean daily load over the
  week / its standard deviation, rest days included) and strain (weekly load x
  monotony): high monotony with high load is the overtraining red flag.
* **Days since hard** -- days since the most recent "hard" day (a daily load a
  configurable multiple of current fitness), to protect hard/easy alternation.
* **Readiness** -- when wellness days are supplied, the latest resting heart rate
  versus its recent baseline plus the day's stress: a light freshness check the
  recovery gate can read.

PROVISIONAL THRESHOLDS
----------------------
The interpretive bands (ramp, ACWR, "hard day", readiness) are collected as named
constants at the top of this module and are deliberately isolated so the evidence
pass (``docs/coach/dynamic-coach-research-brief.md``) can replace the numbers in
one place without touching the logic. The *formulas* are settled; only the
*thresholds* await citation.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable

from .config import AthleteConfig
from .models import Activity
from .training_load import compute_training_load
from .wellness import DayWellness

# --- interpretive thresholds (PROVISIONAL -- anchored by the evidence pass) --- #

# Acute:Chronic Workload Ratio windows and bands (Gabbett). A coupled
# rolling-average ACWR: acute = the last ACWR_ACUTE_DAYS of load; chronic = the
# average ACWR_ACUTE_DAYS-block over the last ACWR_CHRONIC_DAYS. Contested model
# (Lolli/Impellizzeri) -- treated as one signal, see the module docstring.
ACWR_ACUTE_DAYS = 7
ACWR_CHRONIC_DAYS = 28
ACWR_UNDERTRAINING_BELOW = 0.8   # below this: very fresh / detraining drift
ACWR_SWEET_SPOT_HIGH = 1.3       # 0.8..1.3 = the productive "sweet spot"
ACWR_CAUTION_HIGH = 1.5          # 1.3..1.5 = caution; above = elevated risk

# A day counts as "hard" once its training load reaches this multiple of current
# fitness (CTL) -- i.e. clearly above what you are used to...
HARD_DAY_LOAD_RATIO = 1.5
# ...but never below this absolute load, so early-history days (when CTL is still
# tiny) don't all read as "hard".
HARD_DAY_MIN_LOAD = 50.0

# Resting-HR elevation (bpm over the recent baseline) that reads as "not fresh".
READINESS_RHR_ELEVATED = 5
# Days of wellness history used as the resting-HR baseline.
READINESS_BASELINE_DAYS = 7

# Minimum gap-free days of history each signal needs to be meaningful.
_RAMP_MIN_DAYS = 8  # today plus 7 days ago


@dataclass
class CoachState:
    """The dynamic coach's read of where you stand today, ready to serialise."""

    as_of: str                       # YYYY-MM-DD (UTC) the state was evaluated for
    unit: str                        # load-unit family ("tss" | "trimp" | "mixed")
    ctl: float | None                # fitness
    atl: float | None                # fatigue
    tsb: float | None                # form (fitness - fatigue, prior day)
    ramp_rate: float | None          # change in CTL over the last 7 days
    acwr: float | None               # acute:chronic workload ratio
    acwr_zone: str | None            # undertraining | sweet_spot | caution | high_risk
    monotony: float | None           # Foster training monotony (last 7 days)
    strain: float | None             # Foster training strain (last 7 days)
    days_since_hard: int | None      # days since the most recent hard day
    last_hard_date: str | None       # YYYY-MM-DD of that day
    readiness: dict | None           # resting-HR / stress freshness (when wellness given)
    history_days: int                # gap-free days spanned by the timeline
    coverage: dict                   # how many activities were scored, and on which basis
    needs: list[str] = field(default_factory=list)   # thresholds that would sharpen this
    notes: list[str] = field(default_factory=list)   # honest caveats for the UI

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "unit": self.unit,
            "ctl": self.ctl,
            "atl": self.atl,
            "tsb": self.tsb,
            "ramp_rate": self.ramp_rate,
            "acwr": self.acwr,
            "acwr_zone": self.acwr_zone,
            "monotony": self.monotony,
            "strain": self.strain,
            "days_since_hard": self.days_since_hard,
            "last_hard_date": self.last_hard_date,
            "readiness": self.readiness,
            "history_days": self.history_days,
            "coverage": self.coverage,
            "needs": self.needs,
            "notes": self.notes,
        }


def _acwr_zone(acwr: float | None) -> str | None:
    """Classify an ACWR value into its interpretive band (or ``None``)."""
    if acwr is None:
        return None
    if acwr < ACWR_UNDERTRAINING_BELOW:
        return "undertraining"
    if acwr <= ACWR_SWEET_SPOT_HIGH:
        return "sweet_spot"
    if acwr <= ACWR_CAUTION_HIGH:
        return "caution"
    return "high_risk"


def _readiness(wellness: Iterable[DayWellness] | None, as_of: date) -> dict | None:
    """A light freshness read from wellness: resting HR vs baseline, plus stress.

    Returns ``None`` when no wellness day on or before ``as_of`` is available.
    ``fresh`` is ``None`` (unknown) unless there is enough baseline to judge.
    """
    days = sorted(
        (w for w in (wellness or []) if date.fromisoformat(w.date) <= as_of),
        key=lambda w: w.date,
    )
    if not days:
        return None
    latest = days[-1]
    baseline_days = days[-(READINESS_BASELINE_DAYS + 1):-1]  # the prior week, excl. latest
    rhrs = [w.resting_hr for w in baseline_days if w.resting_hr is not None]
    baseline = round(statistics.mean(rhrs), 1) if rhrs else None
    rhr_delta = (
        round(latest.resting_hr - baseline, 1)
        if baseline is not None and latest.resting_hr is not None
        else None
    )
    fresh = None if rhr_delta is None else rhr_delta < READINESS_RHR_ELEVATED
    return {
        "date": latest.date,
        "resting_hr": latest.resting_hr,
        "baseline_resting_hr": baseline,
        "rhr_delta": rhr_delta,
        "avg_stress": latest.avg_stress,
        "fresh": fresh,
        "basis": "wellness:resting_hr+stress",
    }


def compute_coach_state(
    activities: Iterable[Activity],
    athlete: AthleteConfig,
    *,
    sport: str | None = None,
    as_of: date | None = None,
    wellness: Iterable[DayWellness] | None = None,
) -> CoachState:
    """Reduce an activity history to the dynamic coach's current state.

    Reuses :func:`core.training_load.compute_training_load` (evaluated ``as_of``,
    defaulting to today UTC) for the CTL/ATL/TSB timeline, then derives ramp rate,
    ACWR, Foster monotony/strain, time since the last hard day and -- when
    ``wellness`` is supplied -- a resting-HR readiness read. Scope to one ``sport``
    to mirror the rest of Insights. The history is only read, never modified.

    Returns a :class:`CoachState`; serialise with :meth:`CoachState.as_dict`.
    Honest by construction: signals that lack enough history are ``None`` with an
    explanatory ``notes`` entry, and ``needs`` carries the threshold hints
    (``ftp_w``/``max_heart_rate``) that would sharpen the underlying load.
    """
    as_of = as_of or datetime.now(timezone.utc).date()
    tl = compute_training_load(list(activities), athlete, sport=sport, as_of=as_of)
    series = tl["series"]
    readiness = _readiness(wellness, as_of)
    notes: list[str] = []

    if not series:
        notes.append("No scored activities yet -- import history to start coaching.")
        return CoachState(
            as_of=as_of.isoformat(), unit=tl["unit"], ctl=None, atl=None, tsb=None,
            ramp_rate=None, acwr=None, acwr_zone=None, monotony=None, strain=None,
            days_since_hard=None, last_hard_date=None, readiness=readiness,
            history_days=0, coverage=tl["coverage"], needs=list(tl["needs"]), notes=notes,
        )

    current = series[-1]
    ctl, atl, tsb = current["ctl"], current["atl"], current["tsb"]
    loads = [d["load"] for d in series]
    history_days = len(series)

    # Ramp: change in CTL over the last 7 days (gap-free, so 7 days back == [-8]).
    if history_days >= _RAMP_MIN_DAYS:
        ramp_rate = round(ctl - series[-_RAMP_MIN_DAYS]["ctl"], 1)
    else:
        ramp_rate = None
        notes.append(f"Ramp rate needs {_RAMP_MIN_DAYS} days of history ({history_days} so far).")

    # ACWR: acute (7d total) over chronic (28d weekly average). Needs 28 days.
    acwr = None
    if history_days >= ACWR_CHRONIC_DAYS:
        acute = sum(loads[-ACWR_ACUTE_DAYS:])
        chronic = sum(loads[-ACWR_CHRONIC_DAYS:]) / (ACWR_CHRONIC_DAYS / ACWR_ACUTE_DAYS)
        acwr = round(acute / chronic, 2) if chronic > 0 else None
    if acwr is not None:
        notes.append("ACWR is a useful but contested signal -- treat it as one input, not a verdict.")
    elif history_days < ACWR_CHRONIC_DAYS:
        notes.append(f"ACWR needs {ACWR_CHRONIC_DAYS} days of history ({history_days} so far).")

    # Foster monotony & strain over the last 7 days (rest days included -- they are
    # what create the variation that keeps monotony low).
    last7 = loads[-7:]
    monotony = strain = None
    if len(last7) >= 2:
        mean7 = statistics.mean(last7)
        sd7 = statistics.pstdev(last7)
        if sd7 > 0:
            monotony = round(mean7 / sd7, 2)
            strain = round(sum(last7) * monotony, 0)
        elif mean7 > 0:
            notes.append("Every day this week carried similar load (very monotonous) -- vary your days.")

    # Days since the most recent hard day (load >= ratio x that day's fitness,
    # floored at an absolute minimum so early-history days don't all qualify).
    last_hard_date = None
    for d in reversed(series):
        if d["load"] >= max(HARD_DAY_MIN_LOAD, HARD_DAY_LOAD_RATIO * d["ctl"]):
            last_hard_date = d["date"]
            break
    days_since_hard = (
        (as_of - date.fromisoformat(last_hard_date)).days if last_hard_date else None
    )

    if history_days < 42:
        notes.append("Fitness (CTL) is still warming up in the first ~6 weeks of history (understated).")

    return CoachState(
        as_of=as_of.isoformat(), unit=tl["unit"], ctl=ctl, atl=atl, tsb=tsb,
        ramp_rate=ramp_rate, acwr=acwr, acwr_zone=_acwr_zone(acwr),
        monotony=monotony, strain=strain, days_since_hard=days_since_hard,
        last_hard_date=last_hard_date, readiness=readiness, history_days=history_days,
        coverage=tl["coverage"], needs=list(tl["needs"]), notes=notes,
    )

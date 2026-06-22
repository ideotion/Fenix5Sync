"""Dynamic-coach controller -- turns CoachState + a goal into an adaptive plan (pure, stdlib-only).

This is the *controller* half of the LLM-less dynamic coach (the sensor half is
:mod:`core.coach_state`). It takes where you stand today and a goal, and emits a
concrete schedule -- today's session, the days ahead, and the projected form
trajectory -- entirely by rule. No text generation, no network; just arithmetic
and well-established training principles, every recommendation carrying its own
rationale.

How it decides
--------------
1. **Target ramp.** Each goal maps to a target weekly rise in fitness (CTL):
   build/event aim for a productive climb, maintain holds, return/lose-weight
   climb gently. The build target is capped at the safe upper ramp band.
2. **Weekly load budget.** The ramp is converted to an average daily load via the
   42-day CTL response (``avg_daily = CTL + ramp / response``), then capped so the
   week's acute:chronic ratio stays inside the sweet spot (a built-in ACWR
   ceiling -- low fitness can't safely absorb a big jump, and the plan respects
   that automatically).
3. **Microcycle.** A sensible default weekly pattern (two spaced quality days, a
   long day, easy aerobic volume around them, one full rest day) is intersected
   with the days you say you're available. Quality and long sessions are anchored;
   easy volume is the knob that's scaled to hit the budget, within your per-day
   time caps.
4. **Periodization & taper.** Every 4th week is a deload (reduced load). For an
   event with a date, the final fortnight tapers -- volume comes down while
   intensity holds -- to shed fatigue and lift form for race day.
5. **Recovery gate.** Today's prescription is overridden to easy/recovery when the
   signals say back off (deeply negative form, or resting HR elevated over
   baseline). This is the "rest X hours" instinct, generalised.
6. **Projection.** Every prescribed day is run through the same CTL/ATL/TSB EWMAs
   the rest of the app uses, so the plan ships with the form curve it should
   produce -- and, because it's recomputed from current state on every sync, a
   missed or added session reshapes everything from today forward.

Structured vs rolling
---------------------
With a goal *and* an event date the plan is **structured**: a periodized block to
race day with a taper. Otherwise it's **rolling**: the next couple of weeks,
recomputed each sync. (Honest scope: "adapts to live data" means re-planned at
each ingest -- this is an offline, file-based app, not an in-workout feed.)

PROVISIONAL THRESHOLDS
----------------------
The ramp targets, intensity factors, taper depth/length, deload size and recovery
gate cut-offs are isolated as named constants below and await the evidence pass
(``docs/coach/dynamic-coach-research-brief.md``). The control logic does not
change when the numbers do.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from .coach_state import (
    ACWR_SWEET_SPOT_HIGH,
    CoachState,
    compute_coach_state,
)
from .config import AthleteConfig
from .models import Activity
from .wellness import DayWellness

# --- EWMA constants (must mirror core.training_load) -------------------------- #
_CTL_DAYS = 42
_ATL_DAYS = 7
_A_CTL = 1.0 - math.exp(-1.0 / _CTL_DAYS)
_A_ATL = 1.0 - math.exp(-1.0 / _ATL_DAYS)
# Fraction of the gap (avg daily load - CTL) realised in CTL over 7 days. Used to
# size a weekly budget for a target ramp: ramp ~= (avg_daily - CTL) * response.
_WEEKLY_CTL_RESPONSE = 1.0 - (1.0 - _A_CTL) ** 7

# --- session intensities (PROVISIONAL): zone + intensity factor --------------- #
# TSS per minute follows the power model TSS = 100 * hours * IF**2, i.e.
# load/min = 100 * IF**2 / 60. Honest, open approximation -- not Garmin's figures.
_SESSION_INTENSITY = {
    "recovery":  ("Z1", 0.60),
    "easy":      ("Z2", 0.68),
    "endurance": ("Z2", 0.72),
    "long":      ("Z2", 0.75),
    "tempo":     ("Z3", 0.85),
    "threshold": ("Z4", 0.95),
    "intervals": ("Z5", 1.05),
}
_QUALITY_ROTATION = ("threshold", "intervals", "tempo")
_HARD_KINDS = {"tempo", "threshold", "intervals", "long"}

# Default weekly microcycle by weekday (Mon=0..Sun=6): two spaced quality days, a
# long day, easy aerobic volume, one full rest day. A defensible default; the
# evidence pass / user availability refine it.
_MICROCYCLE = {0: "easy", 1: "quality", 2: "endurance", 3: "quality",
               4: "rest", 5: "easy", 6: "long"}
_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# --- plan parameters (PROVISIONAL) -------------------------------------------- #
# Safe upper weekly CTL ramp (Coggan): a ceiling applied to build-goal targets.
RAMP_SAFE_HIGH = 7.0
_RAMP_BY_GOAL = {
    "build": 5.0,        # mid of the safe band
    "event": 5.0,        # build phase before the taper
    "maintain": 0.0,
    "return": 3.0,       # conservative re-entry
    "lose_weight": 2.0,  # gentle, volume-biased
    "general": 1.0,
}
_QUALITY_MINUTES = 50     # anchored duration of a quality session
_TAPER_DAYS = 14          # length of the pre-event taper
_TAPER_MIN = 0.5          # weekly load floor at the bottom of the taper (x build)
_MESO_WEEKS = 4           # 3 build : 1 deload
_DELOAD_SCALE = 0.6       # weekly load on a deload week (x build)
_TSB_OVERREACH = -30.0    # form below this forces recovery today
_STARTER_CTL = 25.0       # sizing baseline when there is no history yet
_RECOVERY_MINUTES = 30    # duration of a gated recovery day
_DEFAULT_ROLLING_HORIZON = 14
_MAX_STRUCTURED_DAYS = 7 * 18  # cap a structured block at 18 weeks
_GATE_DAYS = 1            # apply the recovery gate to today only

_OBJECTIVE = {
    "rest": "Full rest -- recovery and adaptation.",
    "recovery": "Very easy movement (Z1) -- promote recovery, minimal stress.",
    "easy": "Easy aerobic (Z2) -- conversational; build the base.",
    "endurance": "Steady aerobic endurance (Z2) -- controlled aerobic volume.",
    "tempo": "Tempo (Z3) -- comfortably hard and sustained.",
    "threshold": "Threshold (Z4) -- at/near lactate threshold; lift sustainable pace.",
    "intervals": "Intervals (Z5) -- short hard reps with recovery; develop VO2max.",
    "long": "Long session (Z2) -- time on feet / aerobic endurance.",
    "event": "Goal event -- race day.",
}


@dataclass
class CoachGoal:
    """What the athlete is training for, and the time they have for it.

    ``available_days`` and ``long_day`` use Python weekday numbering (Mon=0 ..
    Sun=6). ``kind`` is one of build | event | maintain | return | lose_weight |
    general; ``event_date`` (YYYY-MM-DD) switches the plan into structured mode.
    """

    kind: str = "build"
    event_date: str | None = None
    sport: str = "running"
    available_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    daily_minutes: int = 60
    long_day: int | None = 6
    long_minutes: int = 90
    target_ramp: float | None = None  # override CTL/week; else derived from kind

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "event_date": self.event_date,
            "sport": self.sport,
            "available_days": list(self.available_days),
            "daily_minutes": self.daily_minutes,
            "long_day": self.long_day,
            "long_minutes": self.long_minutes,
            "target_ramp": self.target_ramp,
        }


@dataclass
class PrescribedSession:
    """One prescribed day in the plan."""

    date: str
    weekday: str
    kind: str
    zone: str
    target_load: float
    duration_min: int
    objective: str
    rationale: str

    def as_dict(self) -> dict:
        return {
            "date": self.date,
            "weekday": self.weekday,
            "kind": self.kind,
            "zone": self.zone,
            "target_load": round(self.target_load, 1),
            "duration_min": self.duration_min,
            "objective": self.objective,
            "rationale": self.rationale,
        }


@dataclass
class Plan:
    """A computed adaptive plan, ready to serialise."""

    as_of: str
    mode: str            # "structured" | "rolling"
    goal: dict
    today: dict | None
    sessions: list
    projected: list      # forward-simulated [{date, load, ctl, atl, tsb}]
    summary: dict
    needs: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "mode": self.mode,
            "goal": self.goal,
            "today": self.today,
            "sessions": self.sessions,
            "projected": self.projected,
            "summary": self.summary,
            "needs": self.needs,
            "notes": self.notes,
        }


def _load_per_min(kind: str) -> float:
    """TSS-equivalent load per minute for a session kind (0 for rest)."""
    if kind not in _SESSION_INTENSITY:
        return 0.0
    intensity = _SESSION_INTENSITY[kind][1]
    return 100.0 * intensity * intensity / 60.0


def _zone_for(kind: str) -> str:
    if kind == "rest":
        return "rest"
    if kind == "event":
        return "race"
    return _SESSION_INTENSITY[kind][0]


def _week_roles(goal: CoachGoal) -> dict[int, str]:
    """The role for each weekday (Mon..Sun) under this goal's availability.

    Unavailable days are rest; the long session is moved to ``long_day`` when set
    and available.
    """
    base = dict(_MICROCYCLE)
    if goal.long_day is not None and goal.long_day in goal.available_days:
        for wd, role in list(base.items()):
            if role == "long":
                base[wd] = "easy"
        base[goal.long_day] = "long"
    return {
        wd: (base.get(wd, "easy") if wd in goal.available_days else "rest")
        for wd in range(7)
    }


def _weekly_budget(ctl: float, target_ramp: float) -> float:
    """Weekly load that targets ``target_ramp`` CTL/week, capped by the ACWR ceiling."""
    avg_daily = ctl + target_ramp / _WEEKLY_CTL_RESPONSE
    avg_daily = min(avg_daily, ACWR_SWEET_SPOT_HIGH * ctl)  # don't exceed the sweet spot
    return max(avg_daily, 0.0) * 7.0


def _size_week(weekly_budget: float, week_roles: dict[int, str], goal: CoachGoal) -> dict[int, tuple[str, float]]:
    """Distribute a weekly load budget across the microcycle.

    Quality and long sessions are anchored at their default durations; the easy /
    endurance days absorb the remainder (evenly, capped at the daily time budget).
    If the anchored sessions alone exceed the budget they are scaled down together.
    """
    out: dict[int, list] = {}
    fixed_load = 0.0
    flex_wd: list[int] = []
    for wd, role in week_roles.items():
        if role == "quality":
            load = min(goal.daily_minutes, _QUALITY_MINUTES) * _load_per_min("threshold")
            out[wd] = ["quality", load]
            fixed_load += load
        elif role == "long":
            load = goal.long_minutes * _load_per_min("long")
            out[wd] = ["long", load]
            fixed_load += load
        elif role in ("easy", "endurance"):
            out[wd] = [role, 0.0]
            flex_wd.append(wd)
        else:
            out[wd] = ["rest", 0.0]

    if fixed_load > weekly_budget and fixed_load > 0:
        scale = weekly_budget / fixed_load
        for wd in out:
            if out[wd][0] in ("quality", "long"):
                out[wd][1] *= scale
    elif flex_wd:
        per_flex = (weekly_budget - fixed_load) / len(flex_wd)
        cap = goal.daily_minutes * _load_per_min("endurance")
        per_flex = max(0.0, min(per_flex, cap))
        for wd in flex_wd:
            out[wd][1] = per_flex

    return {wd: (k, l) for wd, (k, l) in out.items()}


def _phase(d: date, goal: CoachGoal, week_index: int, target_ramp: float) -> tuple[str, float]:
    """Phase label and weekly-load scale for day ``d``."""
    if goal.kind == "event" and goal.event_date:
        days_to = (date.fromisoformat(goal.event_date) - d).days
        if days_to <= 0:
            return "event", 0.0
        if days_to <= _TAPER_DAYS:
            scale = _TAPER_MIN + (1.0 - _TAPER_MIN) * (days_to / _TAPER_DAYS)
            return "taper", scale
    if (week_index + 1) % _MESO_WEEKS == 0:
        return "deload", _DELOAD_SCALE
    return ("build" if target_ramp > 0 else "maintain"), 1.0


def _gate_reason(state: CoachState) -> str | None:
    """Why today should be recovery instead of quality, or None if fresh enough."""
    if state.tsb is not None and state.tsb < _TSB_OVERREACH:
        return f"form is deeply negative (TSB {state.tsb}) -- back off to recover"
    r = state.readiness
    if r and r.get("fresh") is False and r.get("rhr_delta") is not None:
        return f"resting HR is {r['rhr_delta']} bpm over baseline -- prioritise recovery"
    return None


def _rationale(kind: str, state: CoachState, phase: str, gate_reason: str | None) -> str:
    """A short, honest explanation of why this session, today."""
    bits: list[str] = []
    if gate_reason:
        bits.append(gate_reason)
    bits.append(f"{phase} phase")
    if state.tsb is not None:
        bits.append(f"form TSB {state.tsb}")
    if state.acwr is not None:
        bits.append(f"ACWR {state.acwr}")
    return "; ".join(bits)


def compute_plan(
    state: CoachState,
    goal: CoachGoal,
    *,
    horizon_days: int | None = None,
) -> Plan:
    """Build an adaptive plan from the current :class:`CoachState` and a goal.

    Structured (to ``goal.event_date``, with a taper) when the goal is an event
    with a date; otherwise a rolling ``horizon_days`` window (default 14). The
    result carries today's session, the schedule, the projected CTL/ATL/TSB curve,
    a summary and honest ``notes``. Pure and deterministic; recompute it on every
    sync to adapt to new data.
    """
    as_of = date.fromisoformat(state.as_of)
    ctl_known = state.ctl is not None
    target_ramp = goal.target_ramp if goal.target_ramp is not None else _RAMP_BY_GOAL.get(goal.kind, 0.0)
    target_ramp = min(target_ramp, RAMP_SAFE_HIGH)  # safe band is a ceiling, not a floor

    # Horizon & mode.
    mode = "structured" if (goal.kind == "event" and goal.event_date) else "rolling"
    if mode == "structured":
        total_days = (date.fromisoformat(goal.event_date) - as_of).days + 1
        if total_days < 1:  # event already passed -> fall back to rolling
            mode, total_days = "rolling", (horizon_days or _DEFAULT_ROLLING_HORIZON)
        else:
            total_days = min(total_days, _MAX_STRUCTURED_DAYS)
    else:
        total_days = horizon_days or _DEFAULT_ROLLING_HORIZON

    week_roles = _week_roles(goal)
    proj_ctl = state.ctl or 0.0
    proj_atl = state.atl or 0.0

    sessions: list[dict] = []
    projected: list[dict] = []
    quality_idx = 0
    week_plan: dict[int, tuple[str, float]] = {}
    week1_budget = 0.0
    week1_load = 0.0

    for i in range(total_days):
        d = as_of + timedelta(days=i)
        week_index = i // 7
        phase, scale = _phase(d, goal, week_index, target_ramp)

        # (Re)size the week at each boundary, from the running projected fitness.
        if i % 7 == 0:
            ctl_for_sizing = proj_ctl if ctl_known else _STARTER_CTL
            weekly_budget = _weekly_budget(ctl_for_sizing, target_ramp) * scale
            week_plan = _size_week(weekly_budget, week_roles, goal)
            if i == 0:
                week1_budget = weekly_budget
                week1_load = sum(l for _, l in week_plan.values())

        kind, load = week_plan[d.weekday()]

        # Event day overrides everything.
        if mode == "structured" and d == date.fromisoformat(goal.event_date):
            kind, load = "event", max(goal.long_minutes, 60) * _load_per_min("threshold")

        # Resolve a quality slot to a concrete rotating session.
        if kind == "quality":
            kind = _QUALITY_ROTATION[quality_idx % len(_QUALITY_ROTATION)]
            quality_idx += 1

        # Recovery gate (today only): downgrade hard work when not recovered.
        gate_reason = _gate_reason(state) if i < _GATE_DAYS else None
        if gate_reason and kind in _HARD_KINDS:
            kind = "recovery"
            load = _RECOVERY_MINUTES * _load_per_min("recovery")

        rate = _load_per_min(kind)
        duration = int(round(load / rate)) if rate > 0 else 0
        session = PrescribedSession(
            date=d.isoformat(),
            weekday=_WEEKDAY_NAMES[d.weekday()],
            kind=kind,
            zone=_zone_for(kind),
            target_load=load,
            duration_min=duration,
            objective=_OBJECTIVE.get(kind, ""),
            rationale=_rationale(kind, state, phase, gate_reason),
        )
        sessions.append(session.as_dict())

        # Forward-simulate the same CTL/ATL/TSB EWMAs the chart uses.
        tsb = round(proj_ctl - proj_atl, 1)
        proj_ctl += (load - proj_ctl) * _A_CTL
        proj_atl += (load - proj_atl) * _A_ATL
        projected.append({
            "date": d.isoformat(),
            "load": round(load, 1),
            "ctl": round(proj_ctl, 1),
            "atl": round(proj_atl, 1),
            "tsb": tsb,
        })

    notes = _plan_notes(state, goal, ctl_known, week1_budget, week1_load)
    summary = {
        "mode": mode,
        "goal_kind": goal.kind,
        "target_ramp_per_week": round(target_ramp, 1),
        "week1_load_target": round(week1_budget, 0),
        "week1_load_planned": round(week1_load, 0),
        "projected_ctl_start": state.ctl,
        "projected_ctl_end": round(proj_ctl, 1),
        "projected_tsb_end": projected[-1]["tsb"] if projected else None,
        "event_date": goal.event_date,
        "horizon_days": total_days,
    }
    return Plan(
        as_of=as_of.isoformat(), mode=mode, goal=goal.as_dict(),
        today=sessions[0] if sessions else None, sessions=sessions,
        projected=projected, summary=summary, needs=list(state.needs), notes=notes,
    )


def _plan_notes(
    state: CoachState, goal: CoachGoal, ctl_known: bool, budget: float, planned: float
) -> list[str]:
    notes = ["Targets are PROVISIONAL pending the evidence pass; the default microcycle is a sensible starting template."]
    if not ctl_known:
        notes.append("No training history yet -- these are conservative starter sessions; the plan sharpens as you sync.")
    if state.needs:
        notes.append(f"Configure {', '.join(state.needs)} for sharper intensity targets.")
    if ctl_known and budget > 0 and planned < 0.9 * budget:
        notes.append("Your available time caps weekly load below the target ramp -- add minutes or days to build faster.")
    if state.acwr is not None and state.acwr_zone in ("caution", "high_risk"):
        notes.append(f"Recent load looks risky (ACWR {state.acwr}); the plan holds back until it settles.")
    notes.extend(n for n in state.notes if "warming up" in n)
    return notes


def plan_from_activities(
    activities: Iterable[Activity],
    athlete: AthleteConfig,
    goal: CoachGoal,
    *,
    as_of: date | None = None,
    wellness: Iterable[DayWellness] | None = None,
    horizon_days: int | None = None,
) -> Plan:
    """Convenience: compute the :class:`CoachState` then the :class:`Plan` in one call."""
    as_of = as_of or datetime.now(timezone.utc).date()
    state = compute_coach_state(activities, athlete, sport=goal.sport, as_of=as_of, wellness=wellness)
    return compute_plan(state, goal, horizon_days=horizon_days)

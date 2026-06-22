# SPDX-License-Identifier: GPL-3.0-or-later
"""Objective -> dated, personalized running plan (pure, stdlib-only).

Turns a plain objective (goal distance, dates, optional goal time, days, level)
into a dated agenda: a base -> build -> peak -> taper -> race periodization with
step-back weeks, a tune-up effort and rest days, where every session carries a
target presented as a RANGE with a confidence and the evidence grade behind it.

It reuses the adaptive controller in :mod:`core.coach_plan` for the periodized
session skeleton (dates, session kinds, the projected load curve) and overlays
the macro-phase calendar plus pace/HR/RPE targets derived from the running-science
parameter block (:data:`PLAN_PARAMS`, the Appendix-A defaults, each tagged with an
evidence grade).

HONESTY (load-bearing, do not weaken):
* Pace/HR ranges are estimates with explicit confidence; ranges widen when goal
  time is unknown or training volume is low. No false precision.
* The 10% rule is **not** validated as injury-protective and is never asserted as
  such; ACWR is a signal only, never a gate/guarantee. E3/E4 values are tunable
  defaults, not physical constants.
* This is general training information, not medical advice — get clearance first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .coach_plan import CoachGoal, compute_plan
from .coach_state import CoachState
from .config import AthleteConfig

# --- Appendix-A parameter block (tunable defaults; grades are E1..E4) --------- #
# Mirrors docs/incoming/coach_plan_params.json. E3/E4 are practice-based or
# contested defaults, NOT physical constants — never present them as proven.
PLAN_PARAMS: dict = {
    "evidence_grades": {"E1": "strong (meta/RCT)", "E2": "moderate",
                        "E3": "practice-based", "E4": "contested/refuted"},
    "phases": {"grade": "E3", "order": ["base", "build", "peak", "taper", "race"],
               "share_of_prep": {"base": 0.52, "build": 0.30, "peak": 0.18}},
    "session_mix": {"grade": "E3", "easy_fraction_of_volume": 0.80,
                    "hard_days_cap": {"beginner": 1, "intermediate": 2, "advanced": 3},
                    "templates": {  # [easy, long, quality] per week
                        2: {"beginner": [1, 1, 0], "intermediate": [1, 1, 0], "advanced": [1, 1, 1]},
                        3: {"beginner": [2, 1, 0], "intermediate": [1, 1, 1], "advanced": [1, 1, 1]},
                        4: {"beginner": [3, 1, 0], "intermediate": [2, 1, 1], "advanced": [2, 1, 1]},
                        5: {"beginner": [4, 1, 0], "intermediate": [3, 1, 1], "advanced": [2, 1, 2]},
                        6: {"beginner": [4, 1, 1], "intermediate": [3, 1, 2], "advanced": [3, 1, 2]}}},
    "vdot": {"grade": "E2_E3",
             "zone_pct_vo2max": {"E": [0.59, 0.74], "M": [0.75, 0.84],
                                 "T": [0.83, 0.88], "I": [0.95, 1.00]}},
    "heart_rate": {"grade": "E2", "hrmax_eq": "208 - 0.7*age",
                   "zones_pct_hrr": {"E": [0.55, 0.74], "M": [0.74, 0.84],
                                     "T": [0.84, 0.88], "I": [0.92, 1.00]},
                   "zones_pct_hrmax": {"E": [0.65, 0.79], "M": [0.80, 0.89],
                                       "T": [0.88, 0.92], "I": [0.95, 1.00]}},
    "rpe": {"grade": "E2", "foster_0_10": {"E": [3, 4], "M": [4, 5], "T": [6, 7],
                                           "I": [8, 9], "RACE": [7, 10]}},
    "riegel": {"grade": "E2", "k_default": 1.06,
               "low_mileage_bias": "optimistic; widen range when volume is low"},
    "progression": {
        "ten_percent_rule": {"grade": "E4", "claim": "NOT validated as injury-protective; never assert"},
        "acwr": {"grade": "E2_E4", "use": "signal_only_never_gate"},
        "stepback_cadence": "3:1", "recovery_week_volume_frac": [0.60, 0.75]},
    "taper": {"core_grade": "E1", "maintain_intensity": True,
              "per_distance_days": {"5k": 9, "10k": 12, "half": 12, "marathon": 17}},
    "tune_up_race": {"grade": "E3", "min_weeks_before_goal": 3, "shorter_than_goal": True},
    "safety": {"app_is_not_clinician": True,
               "recommend_clearance_if": ["known cardiovascular/metabolic/renal disease",
                                          "cardiac symptoms", "sedentary with vigorous intent",
                                          "pregnancy", "a new or undiagnosed symptom"]},
}

_DISTANCE_M = {"5k": 5000.0, "10k": 10000.0, "half": 21097.5, "marathon": 42195.0, "general": None}
_DISTANCE_LABEL = {"5k": "5K", "10k": "10K", "half": "half marathon", "marathon": "marathon", "general": "general fitness"}
# A shorter distance for the tune-up effort, by goal.
_TUNE_UP_FOR = {"marathon": "half", "half": "10k", "10k": "5k", "5k": "5k"}
# compute_plan session kind -> VDOT training zone.
_KIND_TO_ZONE = {"recovery": "E", "easy": "E", "endurance": "M", "long": "E",
                 "tempo": "T", "threshold": "T", "intervals": "I", "event": "RACE"}
_LEVEL_DAILY_MIN = {"beginner": 35, "intermediate": 50, "advanced": 65}
_LONG_MIN = {"5k": 55, "10k": 75, "half": 105, "marathon": 150, "general": 80}
_DEFAULT_VDOT = {"beginner": 38.0, "intermediate": 46.0, "advanced": 54.0}
_RACE_ZONE_BY_DISTANCE = {"5k": "I", "10k": "T", "half": "T", "marathon": "M", "general": "M"}


# ------------------------------ pace mathematics ----------------------------- #
def _vo2(v_m_per_min: float) -> float:
    """Daniels/Gilbert VO2 cost of running velocity ``v`` (m/min)."""
    return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min * v_m_per_min


def _pct_vo2max(t_min: float) -> float:
    """Fraction of VO2max sustainable for a race lasting ``t`` minutes."""
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_race(distance_m: float, time_s: float) -> float:
    """VDOT implied by covering ``distance_m`` in ``time_s`` seconds."""
    t_min = time_s / 60.0
    v = distance_m / t_min
    return _vo2(v) / _pct_vo2max(t_min)


def velocity_for_pct(vdot: float, pct: float) -> float:
    """Velocity (m/min) at ``pct`` of VDOT — invert the quadratic VO2(v)."""
    target = vdot * pct
    a, b, c = 0.000104, 0.182258, -(4.60 + target)
    disc = b * b - 4 * a * c
    return (-b + math.sqrt(disc)) / (2 * a)


def pace_sec_per_km(v_m_per_min: float) -> float:
    """Seconds per km for a velocity in m/min."""
    return 60.0 * 1000.0 / v_m_per_min


def predict_time_s(vdot: float, distance_m: float) -> float:
    """Predicted race time (s) for ``distance_m`` at ``vdot`` (bisection)."""
    # vdot_from_race is monotonically decreasing in time: a faster (smaller) time
    # implies a higher VDOT. Bisect for the time whose implied VDOT matches.
    lo, hi = 60.0, 8.0 * 3600.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if vdot_from_race(distance_m, mid) > vdot:
            lo = mid  # implied VDOT too high -> mid is too fast -> need more time
        else:
            hi = mid
    return (lo + hi) / 2.0


def riegel_time_s(t1_s: float, d1_m: float, d2_m: float, k: float = 1.06) -> float:
    """Riegel endurance prediction: T2 = T1 * (D2/D1)**k."""
    return t1_s * (d2_m / d1_m) ** k


def parse_time(text: str) -> float:
    """Parse 'H:MM:SS' or 'MM:SS' (or seconds) to seconds."""
    text = str(text).strip()
    if ":" not in text:
        return float(text)
    parts = [float(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return h * 3600 + m * 60 + s


def fmt_pace(sec_per_km: float) -> str:
    """Format seconds/km as 'M:SS/km'."""
    sec = int(round(sec_per_km))
    return f"{sec // 60}:{sec % 60:02d}/km"


def fmt_time(time_s: float) -> str:
    """Format seconds as 'H:MM:SS' (or 'MM:SS')."""
    total = int(round(time_s))
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# --------------------------------- objective --------------------------------- #
@dataclass
class Objective:
    """What the runner is training for and the time/structure they have for it."""

    goal_distance: str = "general"             # 5k | 10k | half | marathon | general
    start_date: str | None = None              # YYYY-MM-DD (defaults to today)
    target_date: str | None = None             # YYYY-MM-DD (race day)
    weeks: int | None = None                   # used when target_date is absent
    target_time: str | None = None             # goal finish time (H:MM:SS / MM:SS)
    sessions_per_week: int | None = None
    available_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # Mon=0..Sun=6
    level: str = "intermediate"                # beginner | intermediate | advanced

    def as_dict(self) -> dict:
        return {
            "goal_distance": self.goal_distance, "start_date": self.start_date,
            "target_date": self.target_date, "weeks": self.weeks,
            "target_time": self.target_time, "sessions_per_week": self.sessions_per_week,
            "available_days": list(self.available_days), "level": self.level,
        }


@dataclass
class CoachAgenda:
    """A dated, personalized plan ready to serialise (JSON) or export (ICS)."""

    objective: dict
    start_date: str
    end_date: str
    weeks: int
    phases: list                  # [{phase, week_start, weeks}]
    paces: dict                   # zone -> {pace, hr?, rpe, basis, grade}
    sessions: list                # [{date, weekday, week, phase, kind, title, ...}]
    projected: list               # forward CTL/ATL/TSB curve from compute_plan
    summary: dict
    evidence: dict
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "objective": self.objective, "start_date": self.start_date,
            "end_date": self.end_date, "weeks": self.weeks, "phases": self.phases,
            "paces": self.paces, "sessions": self.sessions, "projected": self.projected,
            "summary": self.summary, "evidence": self.evidence, "notes": self.notes,
        }


# ------------------------------ helper builders ------------------------------ #
def _starter_state(as_of: date) -> CoachState:
    """A conservative blank state (no training history) for compute_plan sizing."""
    return CoachState(
        as_of=as_of.isoformat(), unit="tss", ctl=None, atl=None, tsb=None,
        ramp_rate=None, acwr=None, acwr_zone=None, monotony=None, strain=None,
        days_since_hard=None, last_hard_date=None, readiness=None,
        history_days=0, coverage={}, needs=[], notes=[],
    )


def _resolve_dates(obj: Objective, today: date) -> tuple[date, date, int]:
    start = date.fromisoformat(obj.start_date) if obj.start_date else today
    if obj.target_date:
        end = date.fromisoformat(obj.target_date)
        weeks = max(1, math.ceil(((end - start).days + 1) / 7))
    elif obj.weeks:
        weeks = max(1, int(obj.weeks))
        end = start + timedelta(days=weeks * 7 - 1)
    else:
        weeks = 12
        end = start + timedelta(days=weeks * 7 - 1)
    return start, end, weeks


def _phase_calendar(obj: Objective, weeks: int) -> list[dict]:
    """Allocate weeks to base/build/peak/taper (race is the final day)."""
    racing = obj.goal_distance != "general" and obj.target_date is not None
    taper_w = 0
    if racing:
        taper_days = PLAN_PARAMS["taper"]["per_distance_days"].get(obj.goal_distance, 12)
        taper_w = min(max(1, round(taper_days / 7)), max(1, weeks - 1))
    prep = weeks - taper_w
    share = PLAN_PARAMS["phases"]["share_of_prep"]
    base = max(1, round(prep * share["base"])) if prep else 0
    peak = round(prep * share["peak"]) if prep else 0
    build = max(0, prep - base - peak)
    seq = ["base"] * base + ["build"] * build + ["peak"] * peak + ["taper"] * taper_w
    seq = (seq + ["base"] * weeks)[:weeks]  # pad defensively
    out, i = [], 0
    while i < weeks:
        phase = seq[i]
        j = i
        while j < weeks and seq[j] == phase:
            j += 1
        out.append({"phase": phase, "week_start": i + 1, "weeks": j - i})
        i = j
    return out


def _effective_goal(obj: Objective, start: date, end: date) -> CoachGoal:
    days = sorted(set(obj.available_days)) or list(range(7))
    if obj.sessions_per_week and 0 < obj.sessions_per_week < len(days):
        # Spread the chosen number of sessions across the available days.
        step = len(days) / obj.sessions_per_week
        days = sorted({days[min(len(days) - 1, int(i * step))] for i in range(obj.sessions_per_week)})
    long_day = next((d for d in (6, 5) if d in days), max(days))
    racing = obj.goal_distance != "general" and obj.target_date is not None
    return CoachGoal(
        kind="event" if racing else "build",
        event_date=end.isoformat() if racing else None,
        sport="running", available_days=days,
        daily_minutes=_LEVEL_DAILY_MIN.get(obj.level, 50),
        long_day=long_day, long_minutes=_LONG_MIN.get(obj.goal_distance, 80),
    )


def _resolve_vdot(obj: Objective) -> tuple[float, str, str]:
    """Return (vdot, basis, confidence)."""
    dist = _DISTANCE_M.get(obj.goal_distance)
    if obj.target_time and dist:
        vdot = vdot_from_race(dist, parse_time(obj.target_time))
        return vdot, f"your goal time ({obj.target_time} for the {_DISTANCE_LABEL[obj.goal_distance]})", "moderate"
    vdot = _DEFAULT_VDOT.get(obj.level, 46.0)
    return vdot, f"a typical {obj.level} fitness estimate (no goal time given)", "low"


def _hr_range(zone: str, athlete: AthleteConfig | None) -> tuple[str | None, str | None]:
    if not athlete or not athlete.max_heart_rate:
        return None, None
    hrmax = athlete.max_heart_rate
    rest = athlete.resting_heart_rate
    if rest:  # Karvonen (heart-rate reserve)
        lo, hi = PLAN_PARAMS["heart_rate"]["zones_pct_hrr"][zone]
        a = round(rest + lo * (hrmax - rest))
        b = round(rest + hi * (hrmax - rest))
        return f"{a}-{b} bpm", "HRR (Karvonen)"
    lo, hi = PLAN_PARAMS["heart_rate"]["zones_pct_hrmax"][zone]
    return f"{round(lo * hrmax)}-{round(hi * hrmax)} bpm", "%HRmax"


def _pace_table(vdot: float, confidence: str, low_mileage: bool, athlete: AthleteConfig | None) -> dict:
    """Pace/HR/RPE ranges per training zone, widened for low confidence/mileage."""
    pad = (8.0 if confidence == "low" else 0.0) + (6.0 if low_mileage else 0.0)  # +/- s/km
    out = {}
    for zone, (lo, hi) in PLAN_PARAMS["vdot"]["zone_pct_vo2max"].items():
        fast = pace_sec_per_km(velocity_for_pct(vdot, hi)) - pad
        slow = pace_sec_per_km(velocity_for_pct(vdot, lo)) + pad
        hr, hr_basis = _hr_range(zone, athlete)
        rpe = PLAN_PARAMS["rpe"]["foster_0_10"][zone]
        out[zone] = {
            "pace": f"{fmt_pace(fast)}-{fmt_pace(slow)}",
            "pace_sec_per_km": [round(fast, 1), round(slow, 1)],
            "hr": hr, "hr_basis": hr_basis,
            "rpe": f"RPE {rpe[0]}-{rpe[1]}/10",
            "grade": PLAN_PARAMS["vdot"]["grade"],
        }
    return out


_KIND_TITLE = {
    "recovery": "Recovery jog", "easy": "Easy run", "endurance": "Steady run",
    "long": "Long run", "tempo": "Tempo run", "threshold": "Threshold run",
    "intervals": "Intervals", "event": "RACE DAY", "rest": "Rest",
    "tune_up": "Tune-up race",
}


def _stepback_weeks(phases: list[dict], weeks: int) -> set[int]:
    """Every 3rd week of base/build is a step-back (3:1), per the params cadence."""
    out, count = set(), 0
    phase_of = {}
    for ph in phases:
        for w in range(ph["week_start"], ph["week_start"] + ph["weeks"]):
            phase_of[w] = ph["phase"]
    for w in range(1, weeks + 1):
        if phase_of.get(w) in ("base", "build"):
            count += 1
            if count % 3 == 0:
                out.add(w)
        else:
            count = 0
    return out


def build_plan(
    objective: Objective,
    *,
    state: CoachState | None = None,
    athlete: AthleteConfig | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> CoachAgenda:
    """Build a dated, personalized plan from an objective (pure & deterministic)."""
    today = today or (now or datetime.now(timezone.utc)).date()
    start, end, weeks = _resolve_dates(objective, today)
    phases = _phase_calendar(objective, weeks)
    phase_of_week = {}
    for ph in phases:
        for w in range(ph["week_start"], ph["week_start"] + ph["weeks"]):
            phase_of_week[w] = ph["phase"]
    stepbacks = _stepback_weeks(phases, weeks)

    goal = _effective_goal(objective, start, end)
    coach_state = state or _starter_state(start)
    skeleton = compute_plan(coach_state, goal, horizon_days=(end - start).days + 1)

    # Confidence reflects the pace ANCHOR (a goal time vs a level estimate); low or
    # unknown training volume additionally widens the ranges (honest, not a gate).
    vdot, vdot_basis, confidence = _resolve_vdot(objective)
    low_mileage = coach_state.ctl is None or (coach_state.ctl or 0) < 30
    paces = _pace_table(vdot, confidence, low_mileage, athlete)

    # Tune-up race: a quality/long day ~min_weeks_before_goal weeks before the race.
    tune_up_iso = None
    racing = objective.goal_distance != "general" and objective.target_date is not None
    if racing and weeks >= 6:
        wk = max(1, weeks - PLAN_PARAMS["tune_up_race"]["min_weeks_before_goal"])
        target_day = start + timedelta(days=(wk - 1) * 7 + goal.long_day)
        if start < target_day < end:
            tune_up_iso = target_day.isoformat()

    sessions = []
    for s in skeleton.sessions:
        d = date.fromisoformat(s["date"])
        week = (d - start).days // 7 + 1
        phase = "race" if (racing and d == end) else phase_of_week.get(week, "base")
        kind = s["kind"]
        if tune_up_iso and s["date"] == tune_up_iso and kind not in ("rest", "event"):
            kind = "tune_up"
        zone = _RACE_ZONE_BY_DISTANCE.get(objective.goal_distance, "M") if kind in ("event", "tune_up") else _KIND_TO_ZONE.get(kind)
        target = dict(paces[zone]) if zone else None
        title = _KIND_TITLE.get(kind, kind.title())
        if kind == "tune_up":
            title = f"Tune-up race ({_DISTANCE_LABEL[_TUNE_UP_FOR[objective.goal_distance]]})"
        rationale = _session_rationale(kind, phase, week in stepbacks, confidence)
        sessions.append({
            "date": s["date"], "weekday": s["weekday"], "week": week, "phase": phase,
            "kind": kind, "title": title, "duration_min": s["duration_min"],
            "zone": zone, "target": target,
            "stepback": week in stepbacks and kind not in ("rest", "event"),
            "rationale": rationale, "grade": PLAN_PARAMS["phases"]["grade"],
        })

    summary = _summary(objective, vdot, vdot_basis, confidence, low_mileage, weeks, phases, racing)
    return CoachAgenda(
        objective=objective.as_dict(), start_date=start.isoformat(), end_date=end.isoformat(),
        weeks=weeks, phases=phases, paces=paces, sessions=sessions,
        projected=skeleton.projected, summary=summary, evidence=_evidence_block(),
        notes=_plan_notes(objective, confidence, low_mileage, athlete, racing),
    )


def _session_rationale(kind: str, phase: str, stepback: bool, confidence: str) -> str:
    if kind == "rest":
        return "Rest day — recovery is where adaptation happens."
    bits = [f"{phase} phase"]
    if stepback:
        bits.append("step-back week (reduced volume to absorb the work — a common cadence, not a guarantee against injury)")
    if kind == "long":
        bits.append("time on feet builds aerobic endurance")
    elif kind in ("tempo", "threshold"):
        bits.append("sustained effort at/near threshold to lift comfortable pace")
    elif kind == "intervals":
        bits.append("short hard reps develop VO2max")
    elif kind in ("event", "tune_up"):
        bits.append("race-effort; use the result to re-anchor paces")
    else:
        bits.append("easy aerobic volume — most of the week should feel conversational")
    if confidence == "low":
        bits.append("targets are wide (limited data)")
    return "; ".join(bits)


def _summary(obj, vdot, vdot_basis, confidence, low_mileage, weeks, phases, racing) -> dict:
    out = {
        "goal": _DISTANCE_LABEL.get(obj.goal_distance, obj.goal_distance),
        "weeks": weeks, "level": obj.level, "vdot": round(vdot, 1),
        "vdot_basis": vdot_basis, "confidence": confidence, "low_mileage": low_mileage,
        "phase_breakdown": {ph["phase"]: ph["weeks"] for ph in phases},
    }
    dist = _DISTANCE_M.get(obj.goal_distance)
    if dist:
        # Race-time prediction window: VDOT model + Riegel from the goal/VDOT.
        vdot_pred = predict_time_s(vdot, dist)
        out["predicted_time"] = fmt_time(vdot_pred)
        # Equivalent performances at the common distances (VDOT-consistent).
        out["equivalents"] = {
            _DISTANCE_LABEL[k]: fmt_time(predict_time_s(vdot, _DISTANCE_M[k]))
            for k in ("5k", "10k", "half", "marathon")
        }
        out["race_pace"] = fmt_pace(pace_sec_per_km(dist / (vdot_pred / 60.0)))
    return out


def _evidence_block() -> dict:
    return {
        "grades": PLAN_PARAMS["evidence_grades"],
        "pace_model": PLAN_PARAMS["vdot"]["grade"],
        "hr_model": PLAN_PARAMS["heart_rate"]["grade"],
        "riegel": PLAN_PARAMS["riegel"]["grade"],
        "phases": PLAN_PARAMS["phases"]["grade"],
        "taper": PLAN_PARAMS["taper"]["core_grade"],
        "caveats": [
            "The 10% rule is NOT validated as injury-protective and is not used as a gate here.",
            "ACWR is a signal only — never a guarantee or a hard limit.",
            "E3/E4 values are tunable defaults, not physical constants.",
            "Pace/HR targets are estimates with confidence, not prescriptions.",
        ],
    }


def _plan_notes(obj: Objective, confidence: str, low_mileage: bool, athlete, racing) -> list[str]:
    notes = ["This is general training information, not medical advice — get clearance "
             "(PAR-Q+) before starting if you are older, deconditioned, pregnant, or "
             "living with a condition, or have any new symptom."]
    if confidence == "low":
        notes.append("No goal time given — paces are derived from a level estimate and are "
                     "wide; they will sharpen once you set a goal time or log runs.")
    if low_mileage:
        notes.append("Little training history yet — ranges are widened and the early weeks "
                     "are kept conservative.")
    if not (athlete and athlete.max_heart_rate):
        notes.append("Set your max heart rate in Settings to add HR target ranges.")
    if racing and obj.target_time:
        notes.append("Goal-time paces assume the training is actually completed; a tune-up "
                     "race mid-plan lets you re-anchor them honestly.")
    return notes


# ----------------------------------- ICS ------------------------------------- #
def agenda_to_ics(agenda: CoachAgenda, *, now: datetime | None = None) -> str:
    """Render the agenda's training sessions as an iCalendar string."""
    from .ics import IcsEvent, write_calendar

    events = []
    for s in agenda.sessions:
        if s["kind"] == "rest":
            continue
        title = s["title"]
        if s["duration_min"]:
            title += f" - {s['duration_min']} min"
        lines = [s["rationale"]]
        if s.get("target"):
            t = s["target"]
            tgt = f"Target: {t['pace']}  ·  {t['rpe']}"
            if t.get("hr"):
                tgt += f"  ·  {t['hr']}"
            lines.append(tgt)
        lines.append(f"Phase: {s['phase']} · basis: VDOT/Riegel/Karvonen/RPE (evidence-graded; estimates, not medical advice)")
        events.append(IcsEvent(
            uid=f"{s['date']}-{s['kind']}@fenix5sync",
            day=date.fromisoformat(s["date"]),
            summary=title, description="\n".join(lines),
        ))
    return write_calendar(events, now=now)

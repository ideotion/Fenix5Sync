# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the dynamic-coach sensor layer (CoachState).

Activities are scored on the *duration* basis (no athlete thresholds), where load
equals the session's minutes -- so every derived signal here is hand-checkable.
"""

from __future__ import annotations

import datetime as _dt

from core import compute_coach_state
from core.coach_state import ACWR_CAUTION_HIGH
from core.config import AthleteConfig
from core.models import Activity
from core.wellness import DayWellness

_START = _dt.date(2023, 6, 1)


def _act(d: _dt.date, minutes: float = 60.0, sport: str = "running") -> Activity:
    return Activity(
        sport=sport,
        start_time=_dt.datetime(d.year, d.month, d.day, 8, 0, 0),
        total_timer_time=minutes * 60.0,
    )


def _span(n: int, minutes: float) -> list[Activity]:
    """``n`` consecutive daily sessions of ``minutes`` each, starting at _START."""
    return [_act(_START + _dt.timedelta(days=i), minutes=minutes) for i in range(n)]


def test_empty_history_is_all_none_with_a_note():
    s = compute_coach_state([], AthleteConfig(), as_of=_dt.date(2023, 7, 1)).as_dict()
    assert s["ctl"] is None and s["acwr"] is None and s["history_days"] == 0
    assert s["readiness"] is None
    assert any("import history" in n for n in s["notes"])
    # Full serialised shape is stable.
    assert set(s) == {
        "as_of", "unit", "ctl", "atl", "tsb", "ramp_rate", "acwr", "acwr_zone",
        "monotony", "strain", "days_since_hard", "last_hard_date", "readiness",
        "history_days", "coverage", "needs", "notes",
    }


def test_ramp_rate_positive_during_a_build():
    acts = _span(40, 60.0)
    s = compute_coach_state(acts, AthleteConfig(), as_of=_START + _dt.timedelta(days=39))
    assert s.history_days == 40
    assert s.ramp_rate is not None and s.ramp_rate > 0  # CTL still climbing


def test_ramp_rate_needs_a_week_of_history():
    s = compute_coach_state(_span(3, 60.0), AthleteConfig(), as_of=_START + _dt.timedelta(days=2))
    assert s.ramp_rate is None
    assert any("Ramp rate needs" in n for n in s.notes)


def test_acwr_sweet_spot_when_load_is_steady():
    # Steady 60/day: acute (7x60=420) == chronic (28x60/4=420) -> ACWR ~= 1.0.
    s = compute_coach_state(_span(40, 60.0), AthleteConfig(), as_of=_START + _dt.timedelta(days=39))
    assert s.acwr is not None and abs(s.acwr - 1.0) < 0.1
    assert s.acwr_zone == "sweet_spot"
    assert any("contested" in n for n in s.notes)


def test_acwr_flags_a_recent_spike():
    # 21 easy days (20 min) then a 7-day block of long (120 min) sessions.
    easy = [_act(_START + _dt.timedelta(days=i), minutes=20) for i in range(21)]
    spike = [_act(_START + _dt.timedelta(days=21 + i), minutes=120) for i in range(7)]
    s = compute_coach_state(easy + spike, AthleteConfig(), as_of=_START + _dt.timedelta(days=27))
    assert s.acwr is not None and s.acwr > ACWR_CAUTION_HIGH
    assert s.acwr_zone == "high_risk"


def test_acwr_none_without_28_days():
    s = compute_coach_state(_span(20, 60.0), AthleteConfig(), as_of=_START + _dt.timedelta(days=19))
    assert s.acwr is None and s.acwr_zone is None
    assert any("ACWR needs" in n for n in s.notes)


def test_monotony_and_strain_reflect_weekly_variation():
    # Alternating hard/rest over the last week -> finite, positive monotony.
    pattern = [80, 0, 80, 0, 80, 0, 80]
    acts = [_act(_START + _dt.timedelta(days=i), minutes=m) for i, m in enumerate(pattern) if m]
    s = compute_coach_state(acts, AthleteConfig(), as_of=_START + _dt.timedelta(days=6))
    assert s.monotony is not None and s.monotony > 0
    assert s.strain is not None and s.strain > 0


def test_days_since_hard_counts_rest_after_a_hard_day():
    base = [_act(_START + _dt.timedelta(days=i), minutes=40) for i in range(20)]  # not hard (40 < 50)
    hard = [_act(_START + _dt.timedelta(days=20), minutes=120)]                   # hard (120 >= 50)
    as_of = _START + _dt.timedelta(days=23)                                       # 3 rest days later
    s = compute_coach_state(base + hard, AthleteConfig(), as_of=as_of)
    assert s.last_hard_date == (_START + _dt.timedelta(days=20)).isoformat()
    assert s.days_since_hard == 3


def test_readiness_flags_elevated_resting_hr():
    well = [
        DayWellness(date=(_START + _dt.timedelta(days=i)).isoformat(), steps=None,
                    resting_hr=50, avg_hr=None, max_hr=None, avg_stress=20, stress_samples=1)
        for i in range(7)
    ]
    well.append(DayWellness(date=(_START + _dt.timedelta(days=7)).isoformat(), steps=None,
                            resting_hr=58, avg_hr=None, max_hr=None, avg_stress=40, stress_samples=1))
    s = compute_coach_state([], AthleteConfig(), as_of=_START + _dt.timedelta(days=7), wellness=well)
    r = s.readiness
    assert r is not None
    assert r["baseline_resting_hr"] == 50.0 and r["rhr_delta"] == 8.0
    assert r["fresh"] is False


def test_needs_propagates_threshold_hints():
    a = Activity(sport="running", start_time=_dt.datetime(2023, 6, 1, 8),
                 total_timer_time=3600.0, avg_heart_rate=150)
    s = compute_coach_state([a], AthleteConfig(), as_of=_dt.date(2023, 6, 1))
    assert "max_heart_rate" in s.needs  # HR present but no max configured -> duration basis

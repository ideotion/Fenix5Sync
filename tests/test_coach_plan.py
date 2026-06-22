# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the dynamic-coach controller (compute_plan).

States are constructed directly so the plan logic is exercised in isolation from
state derivation. 2023-06-05 is a Monday, so weekday-dependent rules are
predictable (Tue/Thu are the microcycle's quality days).
"""

from __future__ import annotations

from core import CoachGoal, compute_plan
from core.coach_state import CoachState


def _state(*, as_of="2023-06-05", ctl=50.0, atl=50.0, tsb=0.0, readiness=None,
           history_days=60, needs=None, acwr=1.0, acwr_zone="sweet_spot",
           notes=None) -> CoachState:
    return CoachState(
        as_of=as_of, unit="tss", ctl=ctl, atl=atl, tsb=tsb, ramp_rate=3.0,
        acwr=acwr, acwr_zone=acwr_zone, monotony=1.5, strain=400.0,
        days_since_hard=1, last_hard_date="2023-06-04", readiness=readiness,
        history_days=history_days, coverage={}, needs=needs or [], notes=notes or [],
    )


def test_build_plan_is_rolling_and_progresses():
    p = compute_plan(_state(), CoachGoal(kind="build"))
    assert p.mode == "rolling" and len(p.sessions) == 14
    assert p.today == p.sessions[0] and p.today["date"] == "2023-06-05"
    assert len(p.projected) == 14
    assert p.summary["projected_ctl_end"] > p.summary["projected_ctl_start"]


def test_event_goal_is_structured_to_the_date():
    p = compute_plan(_state(), CoachGoal(kind="event", event_date="2023-06-30"))
    assert p.mode == "structured"
    assert p.sessions[-1]["date"] == "2023-06-30"
    assert p.sessions[-1]["kind"] == "event"


def test_recovery_gate_downgrades_today():
    # Tuesday is a quality day; elevated resting HR forces recovery instead.
    st = _state(as_of="2023-06-06", tsb=-20.0, readiness={"fresh": False, "rhr_delta": 8.0})
    p = compute_plan(st, CoachGoal(kind="build"))
    assert p.today["kind"] == "recovery"
    assert "resting HR" in p.today["rationale"]


def test_deep_negative_form_forces_recovery_today():
    st = _state(as_of="2023-06-06", tsb=-35.0)  # below the overreach floor
    p = compute_plan(st, CoachGoal(kind="build"))
    assert p.today["kind"] == "recovery"
    assert "TSB" in p.today["rationale"]


def test_availability_forces_rest_on_off_days():
    p = compute_plan(_state(), CoachGoal(kind="build", available_days=[0, 2, 4], long_day=None))
    sundays = [s for s in p.sessions if s["weekday"] == "Sun"]
    assert sundays and all(s["kind"] == "rest" for s in sundays)


def test_maintain_holds_fitness():
    p = compute_plan(_state(), CoachGoal(kind="maintain"))
    assert p.summary["target_ramp_per_week"] == 0.0
    assert abs(p.summary["projected_ctl_end"] - p.summary["projected_ctl_start"]) < 2.0


def test_deload_week_has_less_load_than_the_build_week():
    p = compute_plan(_state(), CoachGoal(kind="build"), horizon_days=28)

    def week(i):
        return sum(s["target_load"] for s in p.sessions[i * 7:(i + 1) * 7])

    assert week(3) < week(0)  # the 4th week is a deload


def test_no_history_produces_a_starter_plan():
    st = _state(ctl=None, atl=None, tsb=None, history_days=0, acwr=None, acwr_zone=None)
    p = compute_plan(st, CoachGoal(kind="general"))
    assert p.today is not None and len(p.sessions) == 14
    assert any("starter" in n for n in p.notes)


def test_ramp_target_is_capped_at_the_safe_band():
    # An aggressive override is clamped down to the safe upper ramp.
    p = compute_plan(_state(), CoachGoal(kind="build", target_ramp=20.0))
    assert p.summary["target_ramp_per_week"] == 7.0


def test_plan_as_dict_shape_is_stable():
    p = compute_plan(_state(), CoachGoal(kind="build")).as_dict()
    assert set(p) == {
        "as_of", "mode", "goal", "today", "sessions", "projected",
        "summary", "needs", "notes",
    }
    assert set(p["sessions"][0]) == {
        "date", "weekday", "kind", "zone", "target_load", "duration_min",
        "objective", "rationale",
    }

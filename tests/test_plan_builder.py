# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the objective -> personalized plan builder (core/plan_builder.py)."""

from __future__ import annotations

from datetime import date

import pytest

from core import plan_builder as pb
from core.config import AthleteConfig
from core.ics import parse_calendar
from core.plan_builder import Objective, agenda_to_ics, build_plan

TODAY = date(2026, 6, 22)


# ------------------------------ pace mathematics ----------------------------- #
def test_vdot_from_a_20min_5k_matches_daniels():
    v = pb.vdot_from_race(5000, 1200)
    assert 49.0 < v < 51.0  # Daniels VDOT 50 ~ 19:57 5K


def test_predicted_time_round_trips_the_reference():
    v = pb.vdot_from_race(5000, 1200)
    assert abs(pb.predict_time_s(v, 5000) - 1200) < 3


def test_equivalent_distances_are_ordered_and_plausible():
    v = pb.vdot_from_race(5000, 1200)
    t5, t10, thalf = (pb.predict_time_s(v, d) for d in (5000, 10000, 21097.5))
    assert t5 < t10 < thalf
    assert 2400 < t10 < 2520  # ~41-42 min 10K for a 20:00-5K runner


def test_velocity_for_pct_inverts_the_vo2_cost():
    v = pb.velocity_for_pct(50.0, 0.85)
    assert abs(pb._vo2(v) - 50.0 * 0.85) < 1e-6


def test_riegel_scales_with_the_exponent():
    t = pb.riegel_time_s(1200, 5000, 10000)
    assert abs(t - 1200 * 2 ** 1.06) < 1.0


@pytest.mark.parametrize("text,secs", [("50:00", 3000), ("1:30:00", 5400), ("90", 90)])
def test_parse_time(text, secs):
    assert pb.parse_time(text) == secs


def test_pace_and_time_formatting():
    assert pb.fmt_pace(300) == "5:00/km"
    assert pb.fmt_time(3661) == "1:01:01"
    assert pb.fmt_time(305) == "5:05"


# --------------------------------- the plan ---------------------------------- #
def _race_objective(**over):
    base = dict(goal_distance="10k", start_date="2026-07-01", target_date="2026-09-30",
                target_time="50:00", level="intermediate", available_days=[1, 3, 5, 6])
    base.update(over)
    return Objective(**base)


def test_plan_is_deterministic():
    o = _race_objective()
    assert build_plan(o, today=TODAY).as_dict() == build_plan(o, today=TODAY).as_dict()


def test_phases_cover_every_week_and_end_with_taper_then_race():
    a = build_plan(_race_objective(), today=TODAY)
    assert sum(p["weeks"] for p in a.phases) == a.weeks
    assert [p["phase"] for p in a.phases] == ["base", "build", "peak", "taper"]
    last = a.sessions[-1]
    assert last["date"] == a.end_date and last["phase"] == "race" and last["kind"] == "event"


def test_one_session_per_day_and_targets_present():
    a = build_plan(_race_objective(), today=TODAY)
    start, end = date.fromisoformat(a.start_date), date.fromisoformat(a.end_date)
    assert len(a.sessions) == (end - start).days + 1
    for s in a.sessions:
        if s["kind"] != "rest":
            assert s["target"] and "/km" in s["target"]["pace"] and "RPE" in s["target"]["rpe"]


def test_goal_time_gives_moderate_confidence_and_race_pace():
    a = build_plan(_race_objective(), today=TODAY)
    assert a.summary["confidence"] == "moderate"
    assert a.summary["race_pace"] == "5:00/km"  # 50:00 / 10K
    assert a.summary["predicted_time"] == "50:00"


def test_no_goal_time_widens_to_low_confidence():
    a = build_plan(_race_objective(target_time=None), today=TODAY)
    assert a.summary["confidence"] == "low"
    # Low-confidence easy pace is wider than the moderate one.
    moderate = build_plan(_race_objective(), today=TODAY)
    lo_w = _range_width(a.paces["E"]["pace_sec_per_km"])
    mod_w = _range_width(moderate.paces["E"]["pace_sec_per_km"])
    assert lo_w > mod_w


def _range_width(pair):
    return pair[1] - pair[0]


def test_hr_targets_only_when_max_hr_configured():
    without = build_plan(_race_objective(), today=TODAY)
    assert without.paces["E"]["hr"] is None
    with_hr = build_plan(_race_objective(), today=TODAY,
                         athlete=AthleteConfig(max_heart_rate=190, resting_heart_rate=50))
    assert with_hr.paces["E"]["hr"] and "bpm" in with_hr.paces["E"]["hr"]
    assert with_hr.paces["E"]["hr_basis"] == "HRR (Karvonen)"


def test_tune_up_race_is_scheduled_in_the_run_up():
    a = build_plan(_race_objective(), today=TODAY)
    tune = [s for s in a.sessions if s["kind"] == "tune_up"]
    assert len(tune) == 1
    d = date.fromisoformat(tune[0]["date"])
    assert date.fromisoformat(a.start_date) < d < date.fromisoformat(a.end_date)
    assert "Tune-up" in tune[0]["title"]


def test_stepback_weeks_are_marked():
    a = build_plan(_race_objective(), today=TODAY)
    assert any(s["stepback"] for s in a.sessions)


def test_weeks_from_explicit_count_without_target_date():
    a = build_plan(Objective(goal_distance="5k", start_date="2026-07-01", weeks=8,
                             target_time="22:00"), today=TODAY)
    assert a.weeks == 8 and sum(p["weeks"] for p in a.phases) == 8


def test_general_goal_has_no_race_or_taper():
    a = build_plan(Objective(goal_distance="general", start_date="2026-07-01", weeks=6),
                   today=TODAY)
    assert all(p["phase"] != "taper" for p in a.phases)
    assert all(s["kind"] != "event" for s in a.sessions)
    assert "predicted_time" not in a.summary


def test_evidence_block_states_the_honesty_caveats():
    a = build_plan(_race_objective(), today=TODAY)
    caveats = " ".join(a.evidence["caveats"]).lower()
    assert "10% rule" in caveats and "not validated" in caveats
    assert "acwr" in caveats and "signal only" in caveats


def test_notes_include_clearance_framing():
    a = build_plan(_race_objective(), today=TODAY)
    assert any("not medical advice" in n.lower() for n in a.notes)


# ----------------------------------- ICS ------------------------------------- #
def test_agenda_exports_valid_ics_without_rest_days():
    a = build_plan(_race_objective(), today=TODAY)
    ics = agenda_to_ics(a)
    parsed = parse_calendar(ics)
    non_rest = [s for s in a.sessions if s["kind"] != "rest"]
    assert len(parsed) == len(non_rest)
    # Every event maps to a real session date and carries a target line.
    dates = {s["date"].replace("-", "") for s in non_rest}
    for ev in parsed:
        assert ev["UID"].endswith("@fenix5sync")
    first = parsed[0]
    assert "Target:" in first["DESCRIPTION"] or "Rest" in first["SUMMARY"]
    assert any(d in ics for d in dates)

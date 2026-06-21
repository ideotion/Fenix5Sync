"""Tests for training-load / form (CTL/ATL/TSB) analytics and its API endpoint."""

from __future__ import annotations

import datetime as _dt
import math
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import compute_training_load
from core.config import AthleteConfig, write_config
from core.models import Activity
from server.app import create_app


def _act(day: int, *, minutes: float = 60.0, sport: str = "running",
         power: int | None = None, hr: int | None = None) -> Activity:
    """A summary activity on 2023-06-``day`` with the given duration/metrics."""
    return Activity(
        sport=sport,
        start_time=_dt.datetime(2023, 6, day, 8, 0, 0),
        total_timer_time=minutes * 60.0,
        avg_power=power,
        avg_heart_rate=hr,
    )


def _ref_pmc(loads: list[float], ctl_days: int = 42, atl_days: int = 7):
    """Independent reference EWMA, mirroring the documented formulas exactly."""
    a_ctl = 1.0 - math.exp(-1.0 / ctl_days)
    a_atl = 1.0 - math.exp(-1.0 / atl_days)
    out, pc, pa = [], 0.0, 0.0
    for load in loads:
        tsb = pc - pa
        pc = pc + (load - pc) * a_ctl
        pa = pa + (load - pa) * a_atl
        out.append((round(pc, 1), round(pa, 1), round(tsb, 1)))
    return out


# --------------------------------------------------------------------------- #
# core: per-activity basis selection
# --------------------------------------------------------------------------- #
def test_duration_basis_when_no_thresholds():
    # A 60-min activity with no thresholds -> flat duration estimate (k = 1/min).
    tl = compute_training_load([_act(15, minutes=60)], AthleteConfig())
    assert tl["unit"] == "tss"
    assert tl["coverage"] == {
        "activities": 1, "scored": 1, "basis": {"power": 0, "hr": 0, "duration": 1},
    }
    assert tl["series"][0]["load"] == 60.0


def test_power_basis_uses_tss():
    # NP ~= avg_power = FTP -> IF = 1.0, so one hour scores exactly 100 TSS.
    tl = compute_training_load([_act(15, minutes=60, power=200)], AthleteConfig(ftp_w=200))
    assert tl["unit"] == "tss"
    assert tl["coverage"]["basis"] == {"power": 1, "hr": 0, "duration": 0}
    assert tl["series"][0]["load"] == 100.0
    assert tl["needs"] == []


def test_hr_basis_uses_scaled_trimp():
    # HRr = (169 - 50) / (190 - 50) = 0.85 -> a hard 60-min hour lands at ~100.
    tl = compute_training_load(
        [_act(15, minutes=60, hr=169)],
        AthleteConfig(max_heart_rate=190, resting_heart_rate=50),
    )
    assert tl["unit"] == "trimp"
    assert tl["coverage"]["basis"] == {"power": 0, "hr": 1, "duration": 0}
    assert tl["series"][0]["load"] == 100.0


def test_power_basis_wins_over_hr_when_both_available():
    a = _act(15, minutes=60, power=200, hr=169)
    tl = compute_training_load(
        [a], AthleteConfig(ftp_w=200, max_heart_rate=190, resting_heart_rate=50)
    )
    assert tl["coverage"]["basis"] == {"power": 1, "hr": 0, "duration": 0}


def test_mixed_unit_when_bases_differ():
    acts = [_act(15, minutes=60, power=200), _act(16, minutes=60, hr=169)]
    tl = compute_training_load(
        acts, AthleteConfig(ftp_w=200, max_heart_rate=190, resting_heart_rate=50)
    )
    assert tl["unit"] == "mixed"
    assert tl["coverage"]["basis"] == {"power": 1, "hr": 1, "duration": 0}


def test_needs_reports_missing_thresholds():
    # Power + HR data present but nothing configured -> both hints, duration fallback.
    tl = compute_training_load([_act(15, minutes=60, power=200, hr=150)], AthleteConfig())
    assert tl["needs"] == ["ftp_w", "max_heart_rate"]
    assert tl["coverage"]["basis"]["duration"] == 1


# --------------------------------------------------------------------------- #
# core: the EWMA / PMC timeline
# --------------------------------------------------------------------------- #
def test_single_activity_seeds_from_zero():
    # Hand-checked: load 60 on day 0 -> ctl = 60*(1-e^-1/42), atl = 60*(1-e^-1/7).
    tl = compute_training_load([_act(15, minutes=60)], AthleteConfig())
    cur = tl["current"]
    assert cur["date"] == "2023-06-15"
    assert cur["ctl"] == 1.4
    assert cur["atl"] == 8.0
    assert cur["tsb"] == 0.0  # form seeds at zero on the first day
    assert len(tl["series"]) == 1


def test_gap_days_filled_with_zero_load():
    acts = [_act(15, minutes=60), _act(17, minutes=30)]  # nothing on the 16th
    tl = compute_training_load(acts, AthleteConfig())
    assert [d["date"] for d in tl["series"]] == ["2023-06-15", "2023-06-16", "2023-06-17"]
    assert tl["series"][1]["load"] == 0.0
    # CTL/ATL/TSB must match an independent reference over [60, 0, 30].
    got = [(d["ctl"], d["atl"], d["tsb"]) for d in tl["series"]]
    assert got == _ref_pmc([60.0, 0.0, 30.0])


def test_as_of_extends_timeline_and_decays_fatigue():
    # One hard day, evaluated a week later: with no new training, fatigue (ATL,
    # 7-day) decays faster than fitness (CTL, 42-day), so form (TSB) goes positive.
    tl = compute_training_load([_act(15, minutes=60)], AthleteConfig(), as_of=_dt.date(2023, 6, 22))
    assert tl["series"][0]["date"] == "2023-06-15"
    assert tl["series"][-1]["date"] == "2023-06-22"  # extended to as_of
    assert tl["series"][-1]["load"] == 0.0
    # Reference EWMA over the 15th..22nd inclusive (8 days): one load then rest.
    got = [(d["ctl"], d["atl"], d["tsb"]) for d in tl["series"]]
    assert got == _ref_pmc([60.0] + [0.0] * 7)
    # Fatigue clears over the rest week: ATL decays from its post-load peak and
    # form (TSB) recovers from its trough the day after the hard session.
    assert tl["series"][-1]["atl"] < tl["series"][0]["atl"]   # ~8.0 -> ~3.4
    assert tl["series"][-1]["tsb"] > tl["series"][1]["tsb"]   # -2.2 > -6.6 (recovering)


def test_as_of_does_not_fabricate_history_when_empty():
    # No activities: as_of must not invent a day out of thin air.
    tl = compute_training_load([], AthleteConfig(), as_of=_dt.date(2023, 6, 22))
    assert tl["series"] == [] and tl["current"] is None


def test_same_day_activities_sum_into_one_day():
    tl = compute_training_load([_act(15, minutes=60), _act(15, minutes=30)], AthleteConfig())
    assert len(tl["series"]) == 1
    assert tl["series"][0]["load"] == 90.0  # 60 + 30 on the same calendar day


def test_empty_history():
    tl = compute_training_load([], AthleteConfig())
    assert tl["series"] == []
    assert tl["current"] is None
    assert tl["unit"] == "tss"
    assert tl["needs"] == []
    assert tl["coverage"] == {
        "activities": 0, "scored": 0, "basis": {"power": 0, "hr": 0, "duration": 0},
    }


def test_sport_filter_scopes_everything():
    acts = [_act(15, minutes=60, sport="running"), _act(15, minutes=60, sport="cycling")]
    tl = compute_training_load(acts, AthleteConfig(), sport="running")
    assert tl["coverage"]["activities"] == 1
    assert tl["series"][0]["load"] == 60.0  # only the run, not the (same-day) ride


def test_window_lengths_are_reported_and_honoured():
    tl = compute_training_load([_act(15)], AthleteConfig(), ctl_days=30, atl_days=10)
    assert tl["ctl_days"] == 30 and tl["atl_days"] == 10
    assert tl["series"][0]["ctl"] == _ref_pmc([60.0], 30, 10)[0][0]


def test_unscorable_activity_counts_but_is_not_scored():
    # No duration and no thresholds -> nothing to score, but still counted.
    tl = compute_training_load([Activity(sport="running", start_time=_dt.datetime(2023, 6, 15))], AthleteConfig())
    assert tl["coverage"]["activities"] == 1
    assert tl["coverage"]["scored"] == 0
    assert tl["series"] == []


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def _sync(client: TestClient) -> None:
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


@pytest.fixture
def client_ftp(tmp_config, tmp_path) -> TestClient:
    tmp_config.athlete = AthleteConfig(max_heart_rate=190, ftp_w=220)
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_training_load_endpoint_falls_back_without_thresholds(client: TestClient):
    _sync(client)
    tl = client.get("/api/insights/training-load").json()
    assert set(tl) == {"unit", "ctl_days", "atl_days", "current", "series", "coverage", "needs"}
    assert tl["ctl_days"] == 42 and tl["atl_days"] == 7
    assert tl["coverage"]["activities"] == 1 and tl["coverage"]["scored"] == 1
    # The fixture has power + HR but the config has no thresholds: duration fallback.
    assert tl["coverage"]["basis"]["duration"] == 1
    assert tl["unit"] == "tss"
    assert "ftp_w" in tl["needs"]
    assert tl["series"] and tl["current"]["date"] == tl["series"][-1]["date"]


def test_training_load_endpoint_uses_power_with_ftp(client_ftp: TestClient):
    _sync(client_ftp)
    tl = client_ftp.get("/api/insights/training-load").json()
    assert tl["coverage"]["basis"]["power"] == 1
    assert tl["unit"] == "tss"
    assert tl["needs"] == []  # FTP + max HR configured -> nothing missing


def test_training_load_endpoint_sport_filter_empty(client: TestClient):
    _sync(client)
    tl = client.get("/api/insights/training-load", params={"sport": "cycling"}).json()
    assert tl["coverage"]["activities"] == 0
    assert tl["series"] == [] and tl["current"] is None

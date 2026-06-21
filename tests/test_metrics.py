"""Tests for per-activity performance metrics and the metrics API endpoint."""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import compute_activity_metrics, parse_fit_file, sha256_file
from core.config import AthleteConfig, write_config
from core.metrics import _grade_cost, _normalized_power
from core.models import Activity, Trackpoint
from server.app import create_app

_BASE = _dt.datetime(2023, 6, 15, 8, 0, 0)


def _series(n: int, step_s: int = 1, **fields) -> list[Trackpoint]:
    """``n`` trackpoints ``step_s`` apart. Each kwarg is a per-sample list."""
    out = []
    for i in range(n):
        tp = Trackpoint(timestamp=_BASE + _dt.timedelta(seconds=step_s * i))
        for key, values in fields.items():
            setattr(tp, key, values[i])
        out.append(tp)
    return out


def _activity(points: list[Trackpoint], *, sport="cycling", duration=None) -> Activity:
    return Activity(
        sport=sport,
        total_timer_time=(duration if duration is not None else float(len(points))),
        trackpoints=points,
    )


def _ref_np(powers: list[float], window: int = 30) -> float:
    """Independent Normalized Power reference (rolling mean, 4th-power mean, root)."""
    n = len(powers)
    w = min(window, n)
    rolled = [sum(powers[i:i + w]) / w for i in range(n - w + 1)]
    return (sum(r ** 4 for r in rolled) / len(rolled)) ** 0.25


# --------------------------------------------------------------------------- #
# core: normalized power
# --------------------------------------------------------------------------- #
def test_normalized_power_matches_reference_and_exceeds_average():
    powers = [100.0] * 60 + [300.0] * 60  # blocky -> NP should exceed the mean
    np = _normalized_power(powers)
    assert np == pytest.approx(_ref_np(powers))
    assert np > sum(powers) / len(powers)  # variability pushes NP above avg (200)


def test_normalized_power_constant_equals_mean():
    assert _normalized_power([200.0] * 90) == pytest.approx(200.0)
    assert _normalized_power([]) is None


# --------------------------------------------------------------------------- #
# core: intensity (NP / IF / VI / TSS)
# --------------------------------------------------------------------------- #
def test_intensity_with_ftp():
    powers = [100] * 60 + [300] * 60
    a = _activity(_series(120, power=powers), duration=120.0)
    m = compute_activity_metrics(a, AthleteConfig(ftp_w=250))
    np = _ref_np([float(p) for p in powers])
    inten = m["intensity"]
    assert inten["basis"] == "power"
    assert inten["np_w"] == round(np, 1)
    assert inten["avg_power_w"] == 200.0
    assert inten["variability_index"] == round(np / 200.0, 2)
    assert inten["intensity_factor"] == round(np / 250.0, 2)
    assert inten["tss"] == round(100.0 * (120.0 / 3600.0) * (np / 250.0) ** 2, 1)
    assert m["needs"] == []


def test_intensity_without_ftp_flags_need():
    a = _activity(_series(60, power=[200] * 60), duration=60.0)
    m = compute_activity_metrics(a, AthleteConfig())
    assert m["intensity"]["np_w"] == pytest.approx(200.0)
    assert m["intensity"]["intensity_factor"] is None
    assert m["intensity"]["tss"] is None
    assert m["needs"] == ["ftp_w"]


# --------------------------------------------------------------------------- #
# core: efficiency factor + aerobic decoupling
# --------------------------------------------------------------------------- #
def test_efficiency_and_decoupling_power_basis():
    # Power flat at 200; HR 150 (first half) then 165 (second) -> positive drift.
    hr = [150] * 30 + [165] * 30
    a = _activity(_series(60, power=[200] * 60, heart_rate=hr))
    eff = compute_activity_metrics(a, AthleteConfig())["efficiency"]
    assert eff["basis"] == "power"
    assert eff["efficiency_factor"] == round(200.0 / 157.5, 2)  # NP / mean HR
    # (200/150 - 200/165) / (200/150) * 100
    assert eff["decoupling_pct"] == pytest.approx(9.1, abs=0.05)
    assert eff["decoupling_basis"] == "power"


def test_efficiency_falls_back_to_pace_without_power():
    hr = [150] * 30 + [160] * 30
    speed = [3.0] * 60
    a = _activity(_series(60, speed=speed, heart_rate=hr), sport="running")
    eff = compute_activity_metrics(a, AthleteConfig())["efficiency"]
    assert eff["basis"] == "pace"  # m/min per bpm
    assert eff["efficiency_factor"] == round(3.0 * 60.0 / 155.0, 2)
    assert eff["decoupling_basis"] == "pace"


# --------------------------------------------------------------------------- #
# core: pace + grade-adjusted pace
# --------------------------------------------------------------------------- #
def test_grade_adjusted_pace_running_uphill():
    # 3 m/s on a steady 5% climb -> GAP is the faster flat-equivalent speed.
    dist = [3.0 * i for i in range(60)]
    alt = [0.15 * i for i in range(60)]  # +0.15 m per 3 m = 5% grade
    a = _activity(_series(60, speed=[3.0] * 60, distance=dist, altitude=alt), sport="running")
    pace = compute_activity_metrics(a, AthleteConfig())["pace"]
    factor = _grade_cost(0.05) / _grade_cost(0.0)
    assert pace["gap_speed_mps"] == pytest.approx(3.0 * factor, abs=0.002)
    assert pace["gap_speed_mps"] > 3.0  # uphill -> equivalent flat speed is faster
    assert pace["gap_pace_s_per_km"] < pace["avg_pace_s_per_km"]


def test_pace_block_absent_for_non_foot_sports():
    a = _activity(_series(10, distance=[i * 5.0 for i in range(10)]), sport="cycling")
    assert compute_activity_metrics(a, AthleteConfig())["pace"] is None


# --------------------------------------------------------------------------- #
# core: dynamics, heart rate, environment
# --------------------------------------------------------------------------- #
def test_max_acceleration_from_speed_jump():
    a = _activity(_series(4, speed=[2.0, 2.0, 5.0, 5.0], cadence=[80, 82, 90, 88]))
    dyn = compute_activity_metrics(a, AthleteConfig())["dynamics"]
    assert dyn["max_acceleration_mps2"] == 3.0  # (5 - 2) / 1 s
    assert dyn["max_cadence"] == 90 and dyn["cadence_unit"] == "rpm"  # cycling


def test_running_cadence_doubled_to_spm_with_stride_length():
    # Running stores per-leg cadence (~80); true cadence is steps/min (~160).
    a = _activity(_series(6, speed=[3.0] * 6, cadence=[80] * 6), sport="running")
    dyn = compute_activity_metrics(a, AthleteConfig())["dynamics"]
    assert dyn["cadence_unit"] == "spm"
    assert dyn["avg_cadence"] == 160          # 80 per leg -> 160 spm
    assert dyn["stride_length_m"] == 2.25     # 3 m/s * 120 / 160 spm


def test_heart_rate_drift_and_environment():
    hr = [150] * 30 + [165] * 30
    temp = [20.0] * 30 + [24.0] * 30
    a = _activity(_series(60, heart_rate=hr, temperature=temp))
    m = compute_activity_metrics(a, AthleteConfig())
    assert m["heart_rate"]["max_bpm"] == 165
    assert m["heart_rate"]["drift_pct"] == pytest.approx(10.0, abs=0.05)  # 150 -> 165
    assert m["environment"] == {"avg_temp_c": 22.0, "min_temp_c": 20.0, "max_temp_c": 24.0}


def test_empty_activity_has_no_metrics():
    m = compute_activity_metrics(_activity([]), AthleteConfig())
    assert m["available"] is False
    assert all(m[k] is None for k in
               ("intensity", "efficiency", "pace", "dynamics", "heart_rate", "environment"))


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_compute_metrics_on_fixture(sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    m = compute_activity_metrics(a, AthleteConfig(ftp_w=220))
    assert m["available"] is True
    assert m["intensity"]["basis"] == "power" and m["intensity"]["intensity_factor"] is not None
    assert m["efficiency"]["basis"] == "power"
    assert m["pace"] is not None  # fixture is a run
    assert m["environment"]["avg_temp_c"] == 21.0
    assert m["heart_rate"]["max_bpm"] == 131


def _sync(client: TestClient) -> int:
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)
    return client.get("/api/activities").json()["items"][0]["id"]


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


@pytest.fixture
def client_ftp(tmp_config, tmp_path) -> TestClient:
    tmp_config.athlete = AthleteConfig(ftp_w=220)
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_metrics_endpoint_needs_ftp(client: TestClient):
    aid = _sync(client)
    m = client.get(f"/api/activities/{aid}/metrics").json()
    assert set(m) == {"available", "intensity", "efficiency", "pace",
                      "dynamics", "heart_rate", "environment", "needs"}
    assert m["intensity"]["basis"] == "power"
    assert m["intensity"]["intensity_factor"] is None  # no FTP configured
    assert m["needs"] == ["ftp_w"]
    assert client.get("/api/activities/9999/metrics").status_code == 404


def test_metrics_endpoint_with_ftp(client_ftp: TestClient):
    aid = _sync(client_ftp)
    m = client_ftp.get(f"/api/activities/{aid}/metrics").json()
    assert m["intensity"]["intensity_factor"] is not None
    assert m["intensity"]["tss"] is not None
    assert m["needs"] == []
    assert m["heart_rate"]["max_bpm"] == 131

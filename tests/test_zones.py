"""Tests for HR/power training-zone analysis and the zones API endpoint."""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import compute_zones, hr_zones, parse_fit_file, power_zones, sha256_file
from core.config import AthleteConfig, write_config
from core.models import Trackpoint
from server.app import create_app


def _pts(values: list[int], key: str) -> list[Trackpoint]:
    """Trackpoints 10s apart, each carrying ``value`` under attribute ``key``."""
    base = _dt.datetime(2023, 6, 15, 8, 0, 0)
    out = []
    for i, v in enumerate(values):
        tp = Trackpoint(timestamp=base + _dt.timedelta(seconds=10 * i))
        setattr(tp, key, v)
        out.append(tp)
    return out


# --------------------------------------------------------------------------- #
# core: zone binning
# --------------------------------------------------------------------------- #
def test_hr_zones_partition_time_by_band():
    # max HR 200 -> Z1<120, Z2 120-140, Z3 140-160, Z4 160-180, Z5 >=180.
    zones = hr_zones(_pts([130, 130, 170, 190], "heart_rate"), max_hr=200)
    assert len(zones) == 5
    secs = {z.index: z.seconds for z in zones}
    assert secs[2] == pytest.approx(20)   # 130, 130 -> Z2
    assert secs[4] == pytest.approx(10)   # 170    -> Z4
    assert secs[5] == pytest.approx(10)   # 190    -> Z5
    assert sum(z.seconds for z in zones) == pytest.approx(40)
    assert sum(z.percent for z in zones) == pytest.approx(100, abs=0.1)


def test_power_zones_use_coggan_bands():
    zones = power_zones(_pts([100, 200, 250, 400], "power"), ftp=200)
    assert len(zones) == 7
    secs = {z.index: z.seconds for z in zones}
    assert secs[1] == pytest.approx(10)   # 100 W -> Z1 (<=110)
    assert secs[4] == pytest.approx(10)   # 200 W -> Z4 (~threshold)
    assert secs[6] == pytest.approx(10)   # 250 W -> Z6
    assert secs[7] == pytest.approx(10)   # 400 W -> Z7
    assert zones[-1].high is None         # top zone is open-ended


def test_no_threshold_yields_no_zones():
    assert hr_zones(_pts([120, 130], "heart_rate"), max_hr=None) == []
    assert power_zones(_pts([120, 130], "power"), ftp=0) == []


def test_gaps_are_not_counted_as_time_in_zone():
    # A 10-minute gap between two samples must not be attributed to any zone.
    base = _dt.datetime(2023, 6, 15, 8, 0, 0)
    pts = [
        Trackpoint(timestamp=base, heart_rate=130),
        Trackpoint(timestamp=base + _dt.timedelta(minutes=10), heart_rate=130),
    ]
    zones = hr_zones(pts, max_hr=200)
    # First interval is a >30s gap (dropped); the last sample mirrors it -> 0 total.
    assert sum(z.seconds for z in zones) == 0


# --------------------------------------------------------------------------- #
# core: compute_zones (threshold selection + fallbacks)
# --------------------------------------------------------------------------- #
def test_compute_zones_falls_back_to_observed_max(sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    z = compute_zones(a, AthleteConfig())
    assert z["hr"]["basis"] == "observed"
    assert z["hr"]["max_heart_rate"] == a.max_heart_rate
    assert z["hr"]["zones"] and sum(b["seconds"] for b in z["hr"]["zones"]) > 0
    # The fixture has power but no FTP is configured -> omitted, flagged as needed.
    assert z["power"]["available"] is False
    assert z["power"]["needs_ftp"] is True


def test_compute_zones_uses_configured_thresholds(sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    z = compute_zones(a, AthleteConfig(max_heart_rate=190, ftp_w=220))
    assert z["hr"]["basis"] == "configured" and z["hr"]["max_heart_rate"] == 190
    assert z["power"]["available"] is True and z["power"]["ftp_w"] == 220
    assert len(z["power"]["zones"]) == 7


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    tmp_config.athlete = AthleteConfig(max_heart_rate=190, ftp_w=220)
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def _sync(client: TestClient) -> int:
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)
    return client.get("/api/activities").json()["items"][0]["id"]


def test_zones_endpoint(client: TestClient):
    aid = _sync(client)
    z = client.get(f"/api/activities/{aid}/zones").json()
    assert z["hr"]["max_heart_rate"] == 190 and z["hr"]["basis"] == "configured"
    assert sum(b["seconds"] for b in z["hr"]["zones"]) > 0
    assert z["power"]["available"] is True and len(z["power"]["zones"]) == 7
    assert client.get("/api/activities/9999/zones").status_code == 404


def test_config_roundtrips_athlete(client: TestClient):
    cfg = client.get("/api/config").json()
    assert cfg["athlete"]["max_heart_rate"] == 190
    cfg["athlete"]["max_heart_rate"] = 185
    put = client.put("/api/config", json=cfg)
    assert put.status_code == 200 and put.json()["athlete"]["max_heart_rate"] == 185
    # Non-positive threshold is rejected by validation.
    cfg["athlete"]["ftp_w"] = -5
    assert client.put("/api/config", json=cfg).status_code == 422

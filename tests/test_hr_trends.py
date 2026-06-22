# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for cross-activity heart-rate / efficiency trends and the API endpoint."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core import compute_hr_trends
from core.config import write_config
from core.models import Activity
from server.app import create_app


def _act(day: int, *, sport="running", avg_hr=None, max_hr=None,
         avg_speed=None, avg_power=None, aid=None) -> Activity:
    return Activity(
        id=aid, sport=sport,
        start_time=_dt.datetime(2023, 6, day, 8, 0, 0),
        avg_heart_rate=avg_hr, max_heart_rate=max_hr,
        avg_speed=avg_speed, avg_power=avg_power,
    )


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def test_points_sorted_with_efficiency_and_summary():
    acts = [
        _act(17, avg_hr=150, max_hr=180, avg_speed=3.0, aid=2),
        _act(15, avg_hr=140, max_hr=170, avg_speed=2.8, aid=1),
    ]
    t = compute_hr_trends(acts)
    assert [p["date"] for p in t["points"]] == ["2023-06-15", "2023-06-17"]  # chronological
    assert t["ef_basis"] == "pace"
    # EF (pace) = avg_speed * 60 / avg_hr
    assert t["points"][0]["efficiency"] == round(2.8 * 60 / 140, 2)
    assert t["summary"] == {"activities": 2, "with_hr": 2, "observed_max_hr": 180, "avg_hr": 145}


def test_power_efficiency_basis():
    t = compute_hr_trends([_act(15, avg_hr=150, avg_power=225)])
    assert t["ef_basis"] == "power"
    assert t["points"][0]["efficiency"] == round(225 / 150, 2)  # W per bpm


def test_mixed_basis():
    acts = [_act(15, avg_hr=150, avg_power=225), _act(16, avg_hr=150, avg_speed=3.0)]
    assert compute_hr_trends(acts)["ef_basis"] == "mixed"


def test_activities_without_hr_are_excluded_but_counted():
    acts = [_act(15, avg_hr=150, avg_speed=3.0), _act(16, avg_speed=3.0)]  # 2nd has no HR
    t = compute_hr_trends(acts)
    assert t["summary"]["activities"] == 2 and t["summary"]["with_hr"] == 1
    assert len(t["points"]) == 1


def test_sport_filter():
    acts = [_act(15, sport="running", avg_hr=150), _act(15, sport="cycling", avg_hr=120)]
    t = compute_hr_trends(acts, sport="cycling")
    assert t["summary"]["with_hr"] == 1 and t["points"][0]["avg_hr"] == 120


def test_empty_history():
    t = compute_hr_trends([])
    assert t["points"] == [] and t["ef_basis"] is None
    assert t["summary"] == {"activities": 0, "with_hr": 0, "observed_max_hr": None, "avg_hr": None}


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


def test_hr_trends_endpoint(client: TestClient):
    _sync(client)
    t = client.get("/api/insights/hr-trends").json()
    assert set(t) == {"sport", "ef_basis", "points", "summary"}
    assert t["summary"]["with_hr"] == 1
    assert t["points"][0]["max_hr"] == 131  # fixture's max HR
    assert client.get("/api/insights/hr-trends", params={"sport": "cycling"}).json()["points"] == []

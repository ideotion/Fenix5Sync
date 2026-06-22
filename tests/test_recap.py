# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the Year-in-Sport recap aggregation and endpoint."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core.config import write_config
from core.models import Activity
from core.recap import available_years, compute_recap
from server.app import create_app


def _act(aid, y, mo, d, *, sport="running", dist=10000.0, dur=3000.0, ascent=100.0):
    return Activity(
        id=aid, sport=sport, start_time=_dt.datetime(y, mo, d, 8),
        total_distance=dist, total_timer_time=dur, total_ascent=ascent, total_calories=500,
    )


def test_available_years_descending():
    acts = [_act(1, 2024, 1, 1), _act(2, 2025, 1, 1), _act(3, 2024, 6, 1)]
    assert available_years(acts) == [2025, 2024]


def test_year_scoped_totals_and_sport_breakdown():
    acts = [
        _act(1, 2025, 1, 5, sport="running", dist=5000, dur=1800),
        _act(2, 2025, 2, 5, sport="cycling", dist=30000, dur=3600),
        _act(3, 2024, 2, 5, sport="running", dist=9999, dur=1000),  # different year, excluded
    ]
    r = compute_recap(acts, year=2025)
    assert r["period"] == "2025"
    assert r["totals"]["count"] == 2
    assert r["totals"]["distance_m"] == 35000.0
    # Busiest sport by time is cycling.
    assert r["primary_sport"] == "cycling"
    assert {s["sport"] for s in r["by_sport"]} == {"running", "cycling"}
    assert len(r["by_month"]) == 12


def test_all_time_uses_year_buckets():
    acts = [_act(1, 2024, 1, 1, dist=1000), _act(2, 2025, 1, 1, dist=2000)]
    r = compute_recap(acts, year=None)
    assert r["period"] == "All time"
    assert r["totals"]["count"] == 2
    assert r["totals"]["distance_m"] == 3000.0
    assert [b["year"] for b in r["by_year"]] == [2024, 2025]
    assert "by_month" not in r


def test_highlights_and_biggest_day():
    acts = [
        _act(1, 2025, 3, 1, dist=9000, ascent=50),
        _act(2, 2025, 3, 1, dist=8000, ascent=400),   # same day -> biggest day stacks to 17 km
        _act(3, 2025, 7, 1, dist=15000, ascent=100),  # longest single distance
    ]
    r = compute_recap(acts, year=2025)
    assert r["highlights"]["longest_distance"]["activity_id"] == 3
    assert r["highlights"]["biggest_climb"]["activity_id"] == 2
    assert r["biggest_day"]["date"] == "2025-03-01"
    assert r["biggest_day"]["count"] == 2
    assert r["biggest_day"]["distance_m"] == 17000.0


def test_streak_and_active_days():
    acts = [_act(i, 2025, 1, d) for i, d in enumerate([1, 2, 3, 5], start=1)]
    r = compute_recap(acts, year=2025)
    assert r["active_days"] == 4
    assert r["longest_streak_days"] == 3  # Jan 1-2-3


def test_year_over_year_comparison():
    acts = [
        _act(1, 2024, 1, 1, dist=1000),
        _act(2, 2025, 1, 1, dist=3000),
        _act(3, 2025, 2, 1, dist=1000),
    ]
    r = compute_recap(acts, year=2025)
    assert r["comparison"]["prev_year"] == 2024
    assert r["comparison"]["count_delta"] == 1
    assert r["comparison"]["distance_delta_m"] == 3000.0


def test_empty():
    r = compute_recap([], year=None)
    assert r["totals"]["count"] == 0
    assert r["available_years"] == []
    assert r["primary_sport"] is None


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def _sync(client: TestClient):
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)


def test_recap_endpoints(client: TestClient):
    _sync(client)
    # All-time recap.
    r = client.get("/api/insights/recap").json()
    assert r["period"] == "All time"
    assert r["totals"]["count"] >= 1
    assert isinstance(r["available_years"], list) and r["available_years"]
    # Year-scoped recap for a present year.
    y = r["available_years"][0]
    ry = client.get("/api/insights/recap", params={"year": y}).json()
    assert ry["year"] == y
    assert len(ry["by_month"]) == 12

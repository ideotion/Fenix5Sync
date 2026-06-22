# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for cross-source semantic duplicate detection and its endpoint."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core import find_duplicate_groups
from core.config import write_config
from core.models import Activity
from server.app import create_app

_BASE = _dt.datetime(2023, 6, 15, 8, 0, 0)


def _act(aid, *, offset_s=0, sport="running", dur=3600.0, dist=10000.0,
         device="garmin", lat=None, lon=None) -> Activity:
    return Activity(
        id=aid, sport=sport,
        start_time=_BASE + _dt.timedelta(seconds=offset_s),
        total_timer_time=dur, total_distance=dist,
        device_product=device, start_latitude=lat, start_longitude=lon,
    )


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def test_matches_same_effort_across_sources():
    # Same run, watch vs Strava export: starts 40 s apart, ~same dur/dist.
    a = _act(1, device="fenix5")
    b = _act(2, offset_s=40, dur=3625.0, dist=10120.0, device="strava")
    g = find_duplicate_groups([a, b])
    assert g["duplicate_groups"] == 1
    assert {m["id"] for m in g["groups"][0]["activities"]} == {1, 2}


def test_distinct_efforts_not_grouped():
    a = _act(1)
    b = _act(2, offset_s=7200, dist=5000.0)   # 2 h later, half the distance
    assert find_duplicate_groups([a, b])["duplicate_groups"] == 0


def test_distance_mismatch_breaks_match():
    a = _act(1, dist=10000.0)
    b = _act(2, offset_s=30, dist=15000.0)    # >10% distance apart
    assert find_duplicate_groups([a, b])["duplicate_groups"] == 0


def test_conflicting_sport_not_grouped():
    a = _act(1, sport="running")
    b = _act(2, offset_s=20, sport="cycling")  # same time, different sport
    assert find_duplicate_groups([a, b])["duplicate_groups"] == 0


def test_gps_far_apart_breaks_match():
    a = _act(1, lat=51.5, lon=-0.12)
    b = _act(2, offset_s=20, lat=48.85, lon=2.35)  # London vs Paris
    assert find_duplicate_groups([a, b])["duplicate_groups"] == 0


def test_three_way_transitive_group():
    members = [_act(1, device="fenix5"), _act(2, offset_s=30, device="phone"),
               _act(3, offset_s=60, device="strava")]
    g = find_duplicate_groups(members)
    assert g["duplicate_groups"] == 1 and g["groups"][0]["count"] == 3


def test_empty_history():
    g = find_duplicate_groups([])
    assert g == {"groups": [], "total_activities": 0,
                 "duplicate_groups": 0, "duplicate_activities": 0}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_duplicates_endpoint(client: TestClient):
    # The single fixture activity yields no duplicate groups.
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)
    d = client.get("/api/insights/duplicates").json()
    assert set(d) == {"groups", "total_activities", "duplicate_groups", "duplicate_activities"}
    assert d["duplicate_groups"] == 0

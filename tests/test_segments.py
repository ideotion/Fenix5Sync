# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for personal segments (matching, efforts) and the segments API."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core.config import write_config
from core.models import Activity, Trackpoint
from core.segments import (
    compute_segment_efforts,
    match_effort,
    segment_from_activity,
)
from server.app import create_app

# A short straight west->east line near the equator-ish; ~0.0009 deg lon ~ 100 m.
_LAT = 45.0


def _run(aid, day, *, speed_mps, lon_start=0.0, lon_end=0.01, lat=_LAT):
    """A constant-speed run along a lon line; 1 Hz points with cumulative distance."""
    from core.geo import haversine_m
    span_m = haversine_m(lat, lon_start, lat, lon_end)
    n = max(2, int(span_m / speed_mps) + 1)
    pts = []
    for i in range(n):
        frac = i / (n - 1)
        lon = lon_start + (lon_end - lon_start) * frac
        pts.append(Trackpoint(
            timestamp=_dt.datetime(2025, 1, day, 8) + _dt.timedelta(seconds=i),
            latitude=lat, longitude=lon, distance=span_m * frac, heart_rate=150,
        ))
    return Activity(id=aid, sport="running", start_time=_dt.datetime(2025, 1, day, 8),
                    start_latitude=lat, start_longitude=lon_start,
                    avg_heart_rate=150, trackpoints=pts)


def test_build_segment_from_activity_subsamples_track():
    a = _run(1, 1, speed_mps=3.0)
    seg = segment_from_activity(a, "My loop", num_waypoints=5, radius_m=40)
    assert seg.name == "My loop"
    assert len(seg.waypoints) == 5
    assert seg.sport == "running"
    assert seg.distance_m and seg.distance_m > 0
    assert seg.source_activity_id == 1


def test_match_effort_times_a_repeat_of_the_route():
    ref = _run(1, 1, speed_mps=3.0)
    seg = segment_from_activity(ref, "Line", num_waypoints=6, radius_m=40)
    faster = _run(2, 2, speed_mps=5.0)
    e = match_effort(faster, seg)
    assert e is not None
    assert e.activity_id == 2 and e.date == "2025-01-02"
    assert e.time_s > 0 and e.distance_m > 0
    assert e.avg_hr == 150


def test_non_matching_activity_returns_none():
    ref = _run(1, 1, speed_mps=3.0)
    seg = segment_from_activity(ref, "Line", num_waypoints=6, radius_m=20)
    # A run on a different line (far north) never enters the corridor.
    elsewhere = _run(3, 3, speed_mps=3.0, lat=46.0)
    assert match_effort(elsewhere, seg) is None


def test_compute_efforts_ranks_and_tracks_history():
    ref = _run(1, 1, speed_mps=3.0)
    seg = segment_from_activity(ref, "Line", num_waypoints=6, radius_m=40)
    slow = _run(2, 5, speed_mps=3.0)
    fast = _run(3, 2, speed_mps=6.0)
    out = compute_segment_efforts([slow, fast], seg)
    assert out["count"] == 2
    # Leaderboard fastest-first.
    assert out["leaderboard"][0]["activity_id"] == 3
    assert out["best"]["activity_id"] == 3
    # History chronological by date (Jan 2 before Jan 5).
    assert [e["activity_id"] for e in out["history"]] == [3, 2]


def test_segment_from_activity_without_gps_raises():
    a = Activity(id=9, sport="running", start_time=_dt.datetime(2025, 1, 1, 8),
                 trackpoints=[Trackpoint(timestamp=_dt.datetime(2025, 1, 1, 8))])
    with pytest.raises(ValueError):
        segment_from_activity(a, "no gps")


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def _sync(client: TestClient) -> None:
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)


def test_segments_crud_endpoints(client: TestClient):
    _sync(client)
    # Pick an activity with a GPS track to base a segment on.
    items = client.get("/api/activities").json()["items"]
    gps = [a for a in items if a.get("start_latitude_deg") is not None]
    if not gps:
        pytest.skip("sample fixture has no GPS track")
    aid = gps[0]["id"]

    created = client.post("/api/segments", json={"activity_id": aid, "name": "Test seg",
                                                 "num_waypoints": 6, "radius_m": 50})
    assert created.status_code == 201
    seg_id = created.json()["id"]

    listed = client.get("/api/segments").json()["segments"]
    assert any(s["id"] == seg_id for s in listed)

    efforts = client.get(f"/api/segments/{seg_id}/efforts").json()
    assert set(efforts) >= {"segment", "leaderboard", "history", "best", "count"}
    # The source activity should at least match its own segment.
    assert efforts["count"] >= 1

    assert client.delete(f"/api/segments/{seg_id}").status_code == 204
    assert all(s["id"] != seg_id for s in client.get("/api/segments").json()["segments"])

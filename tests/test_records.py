# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for all-time personal records and the records endpoint."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core import compute_personal_records
from core.config import write_config
from core.models import Activity, Trackpoint
from server.app import create_app

_BASE = _dt.datetime(2023, 6, 15, 8, 0, 0)


def _run(aid: int, day: int, *, speed: float, metres: float) -> Activity:
    """A constant-pace run: 1 Hz trackpoints covering ``metres`` at ``speed`` m/s."""
    n = int(metres / speed) + 1
    pts = [Trackpoint(timestamp=_dt.datetime(2023, 6, day, 8) + _dt.timedelta(seconds=i),
                      distance=speed * i) for i in range(n)]
    return Activity(id=aid, sport="running",
                    start_time=_dt.datetime(2023, 6, day, 8), trackpoints=pts)


def _by_label(recs: list[dict], label: str) -> dict:
    return next(r for r in recs if r["label"] == label)


def test_keeps_fastest_per_distance_across_activities():
    slow = _run(1, 15, speed=3.0, metres=2000)   # 1 km in ~333 s
    fast = _run(2, 16, speed=5.0, metres=2000)   # 1 km in 200 s
    out = compute_personal_records([slow, fast])
    one_k = _by_label(out["records"], "1 km")
    assert one_k["time_s"] == 200.0
    assert one_k["activity_id"] == 2 and one_k["date"] == "2023-06-16"
    assert out["activities"] == 2


def test_empty():
    assert compute_personal_records([]) == {"records": [], "activities": 0}


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_records_endpoint(client: TestClient):
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)
    r = client.get("/api/insights/records").json()
    assert set(r) == {"records", "activities"}
    # The fixture run (~308 m) sets a 200 m best time linked to its activity.
    assert _by_label(r["records"], "200 m")["activity_id"] is not None
    # A sport with no activities yields no records.
    assert client.get("/api/insights/records", params={"sport": "cycling"}).json()["records"] == []

# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for even-distance splits and the splits API endpoint."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core import compute_splits
from core.config import write_config
from core.models import Activity, Trackpoint
from core.splits import MILE_M
from server.app import create_app

_BASE = _dt.datetime(2023, 6, 15, 8, 0, 0)


def _series(n: int, *, step_s: int = 1, **fields) -> list[Trackpoint]:
    out = []
    for i in range(n):
        tp = Trackpoint(timestamp=_BASE + _dt.timedelta(seconds=step_s * i))
        for key, values in fields.items():
            setattr(tp, key, values[i])
        out.append(tp)
    return out


def _activity(points: list[Trackpoint], **kw) -> Activity:
    return Activity(sport=kw.get("sport", "running"), trackpoints=points)


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def test_even_km_splits():
    # 10 m/s for 2000 m at 1 Hz -> two clean 1 km splits of 100 s each.
    pts = _series(
        201,
        distance=[10.0 * i for i in range(201)],
        heart_rate=[140] * 100 + [150] * 101,
        altitude=[float(i) for i in range(201)],  # +1 m/s -> +100 m per split
    )
    s = compute_splits(_activity(pts))
    assert s["unit"] == "km"
    assert len(s["splits"]) == 2
    assert s["splits"][0] == {
        "index": 1, "distance_m": 1000.0, "time_s": 100.0, "pace_s_per_km": 100,
        "avg_hr_bpm": 140, "elev_gain_m": 100.0, "elev_loss_m": 0.0,
    }
    assert s["splits"][1]["avg_hr_bpm"] == 150


def test_partial_trailing_split():
    pts = _series(151, distance=[10.0 * i for i in range(151)])  # 1500 m
    s = compute_splits(_activity(pts))
    assert [sp["distance_m"] for sp in s["splits"]] == [1000.0, 500.0]
    assert s["splits"][1]["pace_s_per_km"] == 100  # 50 s over 500 m


def test_fastest_and_slowest_index():
    # First km at 10 m/s (100 s), second km at 5 m/s (200 s).
    dist = [10.0 * i for i in range(101)] + [1000.0 + 5.0 * i for i in range(1, 201)]
    s = compute_splits(_activity(_series(len(dist), distance=dist)))
    assert s["splits"][0]["pace_s_per_km"] == 100
    assert s["splits"][1]["pace_s_per_km"] == 200
    assert s["fastest_index"] == 1 and s["slowest_index"] == 2


def test_mile_unit():
    pts = _series(201, distance=[10.0 * i for i in range(201)])
    s = compute_splits(_activity(pts), metres=MILE_M)
    assert s["unit"] == "mi"
    assert s["splits"][0]["distance_m"] == round(MILE_M, 1)


def test_gap_is_not_counted_as_moving_time():
    pts = _series(2, step_s=60, distance=[0.0, 100.0])  # 60 s gap > _MAX_GAP_S
    s = compute_splits(_activity(pts))
    assert s["splits"][0]["time_s"] == 0.0
    assert s["splits"][0]["pace_s_per_km"] is None


def test_no_distance_series_yields_no_splits():
    s = compute_splits(_activity(_series(5, heart_rate=[150] * 5)))
    assert s["splits"] == [] and s["fastest_index"] is None


def test_invalid_metres_rejected():
    with pytest.raises(ValueError):
        compute_splits(_activity([]), metres=0)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
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


def test_splits_endpoint(client: TestClient):
    aid = _sync(client)
    s = client.get(f"/api/activities/{aid}/splits").json()
    assert set(s) == {"metres", "unit", "splits", "fastest_index", "slowest_index"}
    assert s["unit"] == "km" and s["metres"] == 1000.0
    assert len(s["splits"]) >= 1  # fixture is ~308 m -> one partial split
    assert s["splits"][0]["index"] == 1

    mi = client.get(f"/api/activities/{aid}/splits", params={"unit": "mi"}).json()
    assert mi["unit"] == "mi"

    assert client.get("/api/activities/9999/splits").status_code == 404

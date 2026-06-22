# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for per-activity best-efforts / mean-max curves and the API endpoint."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core import compute_best_efforts
from core.best_efforts import _peak_rolling_mean
from core.config import write_config
from core.models import Activity, Trackpoint
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


def _activity(points: list[Trackpoint], sport: str = "running") -> Activity:
    return Activity(sport=sport, trackpoints=points)


def _by_label(rows: list[dict], label: str) -> dict:
    return next(r for r in rows if r["label"] == label)


# --------------------------------------------------------------------------- #
# core: best distances
# --------------------------------------------------------------------------- #
def test_fastest_distance_constant_pace():
    pts = _series(401, distance=[5.0 * i for i in range(401)])  # 5 m/s, 2000 m
    e = compute_best_efforts(_activity(pts))
    one_k = _by_label(e["best_distances"], "1 km")
    assert one_k == {"distance_m": 1000, "label": "1 km", "time_s": 200.0, "pace_s_per_km": 200}


def test_fastest_distance_finds_best_window():
    # First 1000 m at 4 m/s (slow), next 1000 m at 8 m/s (fast).
    dist = [4.0 * i for i in range(251)] + [1000.0 + 8.0 * k for k in range(1, 126)]
    e = compute_best_efforts(_activity(_series(len(dist), distance=dist)))
    one_k = _by_label(e["best_distances"], "1 km")
    assert one_k["time_s"] == 125.0  # the fast second kilometre, not the average


def test_long_distances_skipped_when_too_short():
    pts = _series(151, distance=[1.0 * i for i in range(151)])  # only 150 m
    e = compute_best_efforts(_activity(pts))
    assert e["best_distances"] == []


# --------------------------------------------------------------------------- #
# core: mean-max curves
# --------------------------------------------------------------------------- #
def test_peak_rolling_mean():
    assert _peak_rolling_mean([1.0, 2.0, 3.0, 4.0], 2) == 3.5  # best 2-run is (3+4)/2
    assert _peak_rolling_mean([5.0], 2) is None


def test_power_curve_peak_window():
    powers = [100] * 60 + [200] * 60 + [100] * 60
    e = compute_best_efforts(_activity(_series(180, power=powers)))
    assert _by_label(e["power_curve"], "1 min")["watts"] == 200  # the all-200 minute
    assert e["speed_curve"] is None  # no speed recorded


def test_speed_curve_without_power():
    e = compute_best_efforts(_activity(_series(60, speed=[3.0] * 60)))
    assert e["power_curve"] is None
    five_s = _by_label(e["speed_curve"], "5 s")
    assert five_s["speed_mps"] == 3.0 and five_s["pace_s_per_km"] == 333


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


def test_best_efforts_endpoint(client: TestClient):
    aid = _sync(client)
    e = client.get(f"/api/activities/{aid}/best-efforts").json()
    assert set(e) == {"best_distances", "power_curve", "speed_curve"}
    # The fixture is ~308 m, so the 200 m best effort fits (but nothing longer).
    assert e["best_distances"][0]["label"] == "200 m"
    assert e["power_curve"] is not None and e["speed_curve"] is not None
    assert client.get("/api/activities/9999/best-efforts").status_code == 404

"""Tests for VO₂max / race-prediction estimates and the API endpoint."""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import compute_race_predictions
from core.config import write_config
from core.models import Activity, Trackpoint
from core.race import _vdot
from server.app import create_app

_BASE = _dt.datetime(2023, 6, 15, 8, 0, 0)


def _run(distance_m: float, duration_s: int, *, sport: str = "running") -> Activity:
    """A constant-pace activity: one trackpoint per second covering the distance."""
    step = distance_m / duration_s
    pts = [
        Trackpoint(timestamp=_BASE + _dt.timedelta(seconds=i), distance=step * i)
        for i in range(duration_s + 1)
    ]
    return Activity(sport=sport, trackpoints=pts)


def _pred(result: dict, label: str) -> dict:
    return next(p for p in result["predictions"] if p["label"] == label)


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def test_vdot_known_value():
    # A 5 K in 20:00 is ~VDOT 49.8 in Daniels' tables.
    assert _vdot(5000, 1200) == pytest.approx(49.8, abs=0.2)


def test_predictions_from_5k_run():
    r = compute_race_predictions(_run(5000, 1200))
    assert r["available"] is True
    assert r["vo2max"] == pytest.approx(49.8, abs=0.2)
    assert r["reference"]["label"] == "5 km"  # longest effort wins at constant pace
    # Riegel: 10 K = 1200 * 2 ** 1.06
    assert _pred(r, "10K")["time_s"] == pytest.approx(1200 * 2 ** 1.06, abs=1.0)
    assert {p["label"] for p in r["predictions"]} >= {"5K", "10K", "Half marathon", "Marathon"}


def test_non_running_is_unavailable():
    r = compute_race_predictions(_run(5000, 1200, sport="cycling"))
    assert r == {"available": False, "vo2max": None, "reference": None, "predictions": []}


def test_too_short_effort_is_unavailable():
    # 800 m is below the 1 km anchor threshold -> nothing to predict from.
    assert compute_race_predictions(_run(800, 200))["available"] is False


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


def test_race_predictions_endpoint(client: TestClient):
    aid = _sync(client)
    r = client.get(f"/api/activities/{aid}/race-predictions").json()
    assert set(r) == {"available", "vo2max", "reference", "predictions"}
    # The fixture is only ~308 m -> no effort long enough to anchor a prediction.
    assert r["available"] is False
    assert client.get("/api/activities/9999/race-predictions").status_code == 404

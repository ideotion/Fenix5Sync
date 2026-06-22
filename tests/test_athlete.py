# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for athlete-profile parsing/suggestions and the suggestions endpoint."""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import parse_fit_file, sha256_file, suggest_athlete
from core.config import write_config
from core.models import Activity
from server.app import create_app


# --------------------------------------------------------------------------- #
# parsing
# --------------------------------------------------------------------------- #
def test_parse_extracts_user_profile(sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    assert a.extra["user_profile"] == {
        "weight_kg": 74.0, "height_m": 1.81, "gender": "male", "resting_heart_rate": 48,
    }


# --------------------------------------------------------------------------- #
# suggestions
# --------------------------------------------------------------------------- #
def test_suggest_uses_observed_max_and_latest_profile():
    older = Activity(start_time=_dt.datetime(2023, 6, 15), max_heart_rate=188)
    newer = Activity(
        start_time=_dt.datetime(2023, 6, 17), max_heart_rate=175,
        extra={"user_profile": {"weight_kg": 70.0, "resting_heart_rate": 45}},
    )
    s = suggest_athlete([older, newer])
    assert s["observed_max_hr"] == 188            # highest across all activities
    assert s["weight_kg"] == 70.0                 # from the most recent profile
    assert s["resting_heart_rate"] == 45
    assert s["height_m"] is None and s["gender"] is None


def test_suggest_empty_history():
    assert suggest_athlete([]) == {
        "observed_max_hr": None, "resting_heart_rate": None,
        "weight_kg": None, "height_m": None, "gender": None,
    }


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


def test_athlete_suggestions_endpoint(client: TestClient):
    _sync(client)
    s = client.get("/api/athlete/suggestions").json()
    assert s["observed_max_hr"] == 131                       # fixture's max HR
    assert s["weight_kg"] == 74.0 and s["height_m"] == 1.81  # from user_profile
    assert s["gender"] == "male" and s["resting_heart_rate"] == 48

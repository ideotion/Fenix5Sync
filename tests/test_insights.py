# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the insights/analytics aggregation and its API endpoint."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import Store, parse_fit_file, sha256_file
from core.config import write_config
from core.store import _longest_daily_streak
from server.app import create_app


def test_longest_daily_streak():
    assert _longest_daily_streak([]) == 0
    assert _longest_daily_streak(["2023-06-15"]) == 1
    assert _longest_daily_streak(["2023-06-15", "2023-06-16", "2023-06-17"]) == 3
    # A gap resets the run; the longest of two separate runs wins.
    assert _longest_daily_streak(
        ["2023-06-15", "2023-06-16", "2023-06-20", "2023-06-21", "2023-06-22"]
    ) == 3


def test_insights_single_activity(tmp_path: Path, sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    with Store(tmp_path / "db.sqlite") as store:
        store.add_activity(a)
        ins = store.insights()

    assert ins["totals"]["count"] == 1
    assert ins["totals"]["distance_m"] == pytest.approx(308.0)
    assert ins["totals"]["ascent_m"] == pytest.approx(11.0)
    assert ins["totals"]["active_days"] == 1
    assert ins["totals"]["longest_streak_days"] == 1
    assert ins["years"] == ["2023"]
    assert ins["by_month"][0]["month"] == "2023-06"
    assert ins["by_sport"][0]["sport"] == "running"
    assert ins["calendar"][0] == {"date": "2023-06-15", "count": 1, "distance_m": pytest.approx(308.0)}

    rec = ins["records"]
    assert rec["longest_distance"]["value"] == pytest.approx(308.0)
    assert rec["most_ascent"]["value"] == pytest.approx(11.0)
    # The fixture is < 1 km, so it's excluded from the "fastest" record threshold.
    assert rec["fastest_avg_speed"] is None


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_insights_endpoint(client: TestClient):
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline and client.get(f"/api/sync/{job_id}").json()["status"] == "running":
        time.sleep(0.1)

    ins = client.get("/api/insights").json()
    assert ins["totals"]["count"] == 1
    assert "running" in ins["sports"]

    # Scoping to a sport with no activities yields empty aggregates.
    none = client.get("/api/insights", params={"sport": "cycling"}).json()
    assert none["totals"]["count"] == 0
    assert none["by_month"] == [] and none["calendar"] == []
    assert none["records"]["longest_distance"] is None

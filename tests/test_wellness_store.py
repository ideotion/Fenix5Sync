"""Tests for wellness storage, sync-pipeline routing, and the wellness endpoint."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import Store, import_activities
from core.config import Config, write_config
from server.app import create_app
from tests.fixtures.make_fit import build_monitoring_fit


def _config(tmp_path: Path) -> Config:
    src = tmp_path / "src"
    src.mkdir()
    (src / "monitoring.fit").write_bytes(build_monitoring_fit())
    cfg = Config()
    cfg.storage.data_dir = str(tmp_path / "data")
    cfg.storage.db_file = str(tmp_path / "data" / "db.sqlite")
    cfg.export.output_dir = str(tmp_path / "exp")
    cfg.logging.log_dir = str(tmp_path / "logs")
    cfg.source.mode = "path"
    cfg.source.path = str(src)
    return cfg


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #
def test_store_wellness_upsert(tmp_path: Path):
    with Store(tmp_path / "w.sqlite") as s:
        assert s.add_wellness_days([
            {"date": "2023-06-15", "steps": 8000, "resting_hr": 50, "avg_hr": 70,
             "max_hr": 95, "avg_stress": 40, "stress_samples": 4},
        ]) == 1
        # Same date upserts (replaces) rather than duplicating.
        s.add_wellness_days([
            {"date": "2023-06-15", "steps": 9000, "resting_hr": 48, "avg_hr": 68,
             "max_hr": 90, "avg_stress": 35, "stress_samples": 5},
        ])
        days = s.all_wellness_days()
    assert len(days) == 1
    assert days[0]["steps"] == 9000 and days[0]["resting_hr"] == 48


# --------------------------------------------------------------------------- #
# pipeline routing
# --------------------------------------------------------------------------- #
def test_pipeline_routes_monitoring_to_wellness(tmp_path: Path):
    cfg = _config(tmp_path)
    summary = import_activities(cfg)
    assert summary.wellness == 1     # the monitoring file became a wellness day
    assert summary.imported == 0     # it is not an activity
    assert summary.failed == 0       # and is not counted as a failure
    with Store(cfg.storage.db_path) as store:
        days = store.all_wellness_days()
    assert len(days) == 1
    assert days[0]["date"] == "2023-06-15" and days[0]["steps"] == 8000


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    cfg = _config(tmp_path)
    cfg_path = tmp_path / "config.yaml"
    write_config(cfg, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_wellness_endpoint(client: TestClient):
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)
    w = client.get("/api/insights/wellness").json()
    assert len(w["days"]) == 1
    d = w["days"][0]
    assert d["date"] == "2023-06-15" and d["steps"] == 8000 and d["resting_hr"] == 50

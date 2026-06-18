"""API tests using FastAPI's TestClient against a temp-configured app."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import write_config
from server.app import create_app


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    app = create_app(str(cfg_path))
    return TestClient(app)


def _wait_for_sync(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/sync/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] != "running":
            return data
        time.sleep(0.1)
    raise AssertionError("sync did not finish in time")


def test_health_and_stats(client: TestClient):
    h = client.get("/api/health")
    assert h.status_code == 200 and h.json()["status"] == "ok"

    s = client.get("/api/stats")
    assert s.status_code == 200
    assert s.json()["count"] == 0


def test_sync_then_browse_and_export(client: TestClient):
    # Trigger an import from the fixture directory (mode=path in tmp_config).
    started = client.post("/api/sync")
    assert started.status_code == 200
    job_id = started.json()["job_id"]

    final = _wait_for_sync(client, job_id)
    assert final["status"] == "done"
    assert final["summary"]["found"] == 1
    assert final["summary"]["imported"] == 1

    # List
    listing = client.get("/api/activities").json()
    assert listing["total"] == 1
    assert listing["count"] == 1
    assert listing["items"][0]["sport"] == "running"
    assert "running" in listing["sports"]
    activity_id = listing["items"][0]["id"]

    # Filter that excludes it
    none = client.get("/api/activities", params={"sport": "cycling"}).json()
    assert none["total"] == 0

    # Detail with time series
    detail = client.get(f"/api/activities/{activity_id}").json()
    assert len(detail["trackpoints"]) == 12
    assert len(detail["laps"]) == 1
    assert detail["total_distance_m"] == pytest.approx(308.0)

    # Exports
    for fmt, ctype in (("json", "application/json"), ("csv", "text/csv"), ("gpx", "application/gpx+xml")):
        r = client.get(f"/api/activities/{activity_id}/export", params={"format": fmt})
        assert r.status_code == 200, fmt
        assert ctype in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]

    # Bulk export
    bulk = client.get("/api/export", params={"format": "csv"})
    assert bulk.status_code == 200
    assert "total_distance_m" in bulk.text.splitlines()[0]

    # 404 for unknown activity
    assert client.get("/api/activities/9999").status_code == 404


def test_logs_endpoint(client: TestClient):
    # Run a sync so something gets logged, then read logs back.
    job_id = client.post("/api/sync").json()["job_id"]
    _wait_for_sync(client, job_id)
    logs = client.get("/api/logs", params={"lines": 50}).json()
    assert isinstance(logs["lines"], list)
    assert any("Import complete" in line for line in logs["lines"])


def test_config_get_and_put(client: TestClient):
    cfg = client.get("/api/config").json()
    assert cfg["server"]["host"] == "127.0.0.1"

    # Change the log level and persist it.
    cfg["logging"]["level"] = "DEBUG"
    put = client.put("/api/config", json=cfg)
    assert put.status_code == 200
    assert put.json()["logging"]["level"] == "DEBUG"

    # Reject a non-loopback bind (privacy invariant).
    cfg["server"]["host"] = "0.0.0.0"
    bad = client.put("/api/config", json=cfg)
    assert bad.status_code == 422

# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests using FastAPI's TestClient against a temp-configured app."""

from __future__ import annotations

import time

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

    # Full-fidelity NDJSON archive export (one activity per line, with series)
    archive = client.get("/api/export", params={"format": "ndjson", "full": "true"})
    assert archive.status_code == 200
    assert "application/x-ndjson" in archive.headers["content-type"]
    lines = archive.text.strip().splitlines()
    assert len(lines) == 1
    import json as _json
    rec = _json.loads(lines[0])
    assert len(rec["trackpoints"]) == 12

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


def test_coach_plan_endpoint_returns_a_dated_agenda(client: TestClient):
    body = {
        "goal_distance": "10k", "start_date": "2026-07-01", "target_date": "2026-09-30",
        "target_time": "50:00", "level": "intermediate", "available_days": [1, 3, 5, 6],
    }
    r = client.post("/api/coach/plan", json=body)
    assert r.status_code == 200
    plan = r.json()
    assert plan["weeks"] >= 8 and plan["sessions"]
    assert plan["sessions"][-1]["phase"] == "race"
    assert plan["summary"]["race_pace"] == "5:00/km"
    # The honesty caveats must ride along.
    caveats = " ".join(plan["evidence"]["caveats"]).lower()
    assert "10% rule" in caveats and "not validated" in caveats


def test_coach_plan_ics_download(client: TestClient):
    r = client.get("/api/coach/plan.ics", params={
        "goal_distance": "5k", "start_date": "2026-07-01", "weeks": 8,
        "target_time": "22:00", "available_days": "2,4,6",
    })
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR") and "BEGIN:VEVENT" in body


def test_coach_plan_rejects_bad_distance(client: TestClient):
    r = client.post("/api/coach/plan", json={"goal_distance": "ultra"})
    assert r.status_code == 422


def test_coach_state_endpoint_empty_store(client: TestClient):
    # No history: an honest empty state (never a 404), with the onboarding note.
    r = client.get("/api/coach/state")
    assert r.status_code == 200
    s = r.json()
    assert s["history_days"] == 0 and s["ctl"] is None and s["readiness"] is None
    assert any("import history" in n for n in s["notes"])


def test_coach_state_reads_run_variants_and_wellness(client: TestClient, tmp_config):
    import datetime as dt

    from core.models import Activity
    from core.store import Store

    today = dt.datetime.now(dt.timezone.utc).date()
    with Store(tmp_config.storage.db_file) as store:
        # A trail run must count toward coach state (not only plain "running").
        store.add_activity(Activity(
            sport="trail_running",
            start_time=dt.datetime.combine(today - dt.timedelta(days=2), dt.time(8, 0)),
            total_timer_time=3600.0,
        ))
        # A week of resting-HR 50 baseline, then today spikes to 58 (+8 bpm).
        store.add_wellness_days(
            [{"date": (today - dt.timedelta(days=i)).isoformat(), "steps": None,
              "resting_hr": 50, "avg_hr": None, "max_hr": None,
              "avg_stress": 20, "stress_samples": 4} for i in range(1, 8)]
            + [{"date": today.isoformat(), "steps": None, "resting_hr": 58,
                "avg_hr": None, "max_hr": None, "avg_stress": 45, "stress_samples": 4}]
        )

    s = client.get("/api/coach/state").json()
    assert s["as_of"] == today.isoformat()
    assert s["history_days"] >= 3 and s["ctl"] is not None  # the trail run counted
    ready = s["readiness"]
    assert ready is not None and ready["fresh"] is False
    assert ready["rhr_delta"] == 8.0 and ready["baseline_resting_hr"] == 50.0

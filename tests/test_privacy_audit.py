# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the personal privacy audit (start-point clustering)."""

from __future__ import annotations

import datetime as _dt
import time

import pytest
from fastapi.testclient import TestClient

from core.config import write_config
from core.models import Activity
from core.privacy_audit import compute_privacy_audit
from server.app import create_app

# Two well-separated places (~kilometres apart): a "home" and a "trailhead".
_HOME = (48.8566, 2.3522)
_TRAIL = (48.9000, 2.4000)


def _act(aid, lat, lon, *, day=1, hour=7):
    return Activity(
        id=aid, sport="running", start_latitude=lat, start_longitude=lon,
        start_time=_dt.datetime(2025, 1, day, hour),
    )


def _jitter(pt, d_lat=0.0003, d_lon=0.0):
    return (pt[0] + d_lat, pt[1] + d_lon)


def test_clusters_and_identifies_primary_place():
    acts = [_act(i, *_jitter(_HOME, d_lat=0.0002 * (i % 3))) for i in range(6)]
    acts += [_act(100 + i, *_jitter(_TRAIL, d_lat=0.0001 * i)) for i in range(2)]
    out = compute_privacy_audit(acts)
    assert out["total_activities"] == 8
    assert out["with_gps"] == 8
    assert out["location_count"] == 2
    # The home cluster (6 starts) is the most-exposed primary.
    assert out["primary"]["count"] == 6
    assert out["primary"]["kind"] == "primary"
    assert out["primary"]["share_pct"] == 75.0


def test_recommended_radius_masks_primary_cluster():
    acts = [_act(i, *_jitter(_HOME, d_lat=0.0002 * (i % 4))) for i in range(8)]
    out = compute_privacy_audit(acts)
    assert out["recommended_radius_m"] >= 200  # floor respected
    # A scrub at the recommended radius masks every start in the only cluster.
    assert out["exposed_activities"] == 8
    assert out["exposed_pct"] == 100.0


def test_regularity_reflects_weekday_concentration():
    # All on the same weekday (2025-01-06 is a Monday) -> high regularity.
    acts = [_act(i, *_jitter(_HOME, d_lat=0.0001 * i), day=6) for i in range(4)]
    out = compute_privacy_audit(acts)
    assert out["primary"]["peak_weekday"] == "Mon"
    assert out["primary"]["regularity_pct"] == 100.0


def test_handles_activities_without_gps():
    acts = [Activity(id=1, sport="running", start_time=_dt.datetime(2025, 1, 1, 7))]
    out = compute_privacy_audit(acts)
    assert out["total_activities"] == 1
    assert out["with_gps"] == 0
    assert out["primary"] is None
    assert out["recommended_radius_m"] == 0


def test_empty():
    out = compute_privacy_audit([])
    assert out["with_gps"] == 0
    assert out["clusters"] == []


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_privacy_audit_endpoint(client: TestClient):
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)
    r = client.get("/api/insights/privacy-audit").json()
    # Endpoint adds config context to the audit payload.
    assert "recommended_radius_m" in r
    assert "current_radius_m" in r
    assert "radius_sufficient" in r
    assert r["total_activities"] >= 1

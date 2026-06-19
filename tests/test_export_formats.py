"""Tests for TCX export, raw passthrough, and the export API (incl. anonymize)."""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import activity_tcx, parse_fit_file, sha256_file, write_activity_export
from core.config import write_config
from server.app import create_app


def _activity(sample_fit_path: Path):
    return parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))


# --------------------------------------------------------------------------- #
# core: TCX + raw
# --------------------------------------------------------------------------- #
def test_activity_tcx_is_well_formed(sample_fit_path: Path):
    a = _activity(sample_fit_path)
    root = ET.fromstring(activity_tcx(a))
    assert root.tag.endswith("TrainingCenterDatabase")
    activity_el = next(e for e in root.iter() if e.tag.endswith("Activity"))
    assert activity_el.get("Sport") == "Running"
    tps = [e for e in root.iter() if e.tag.endswith("Trackpoint")]
    assert len(tps) == 12
    # Position + HR made it into the trackpoints.
    assert any(e.tag.endswith("LatitudeDegrees") for e in root.iter())
    assert any(e.tag.endswith("HeartRateBpm") for e in root.iter())


def test_write_activity_export_tcx_and_raw(tmp_path: Path, sample_fit_path: Path):
    a = _activity(sample_fit_path)
    raw = tmp_path / "src.fit"
    raw.write_bytes(Path(sample_fit_path).read_bytes())
    a.raw_path = str(raw)
    out = tmp_path / "out"

    tcx_path = write_activity_export(a, "tcx", out)
    assert tcx_path.suffix == ".tcx" and tcx_path.is_file()

    raw_path = write_activity_export(a, "raw", out)
    assert raw_path.suffix == ".fit"
    assert raw_path.read_bytes() == raw.read_bytes()  # byte-for-byte original


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def _sync(client: TestClient) -> int:
    job_id = client.post("/api/sync").json()["job_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        if client.get(f"/api/sync/{job_id}").json()["status"] != "running":
            break
        time.sleep(0.1)
    return client.get("/api/activities").json()["items"][0]["id"]


def test_export_tcx_and_raw_endpoints(client: TestClient):
    aid = _sync(client)

    tcx = client.get(f"/api/activities/{aid}/export", params={"format": "tcx"})
    assert tcx.status_code == 200
    assert "tcx" in tcx.headers["content-type"]
    assert ET.fromstring(tcx.text).tag.endswith("TrainingCenterDatabase")

    raw = client.get(f"/api/activities/{aid}/export", params={"format": "raw"})
    assert raw.status_code == 200
    assert raw.headers["content-disposition"].endswith('.fit"')

    # raw + anonymize is a contradiction -> rejected.
    bad = client.get(
        f"/api/activities/{aid}/export", params={"format": "raw", "anonymize": "true"}
    )
    assert bad.status_code == 422


def test_export_anonymize_strips_sensitive_fields(client: TestClient):
    aid = _sync(client)
    plain = client.get(f"/api/activities/{aid}/export", params={"format": "json"}).json()
    assert plain["device_manufacturer"] is not None and plain["raw_path"]

    anon = client.get(
        f"/api/activities/{aid}/export", params={"format": "json", "anonymize": "true"}
    ).json()
    assert anon["device_manufacturer"] is None
    assert anon["raw_path"] == ""

    # Bulk export honours anonymize too.
    bulk = client.get("/api/export", params={"format": "json", "full": "true", "anonymize": "true"})
    assert bulk.status_code == 200
    assert json.loads(bulk.text)[0]["device_manufacturer"] is None


def test_config_roundtrips_anonymize_section(client: TestClient):
    cfg = client.get("/api/config").json()
    assert "anonymize" in cfg and cfg["anonymize"]["enabled"] is False

    cfg["anonymize"]["enabled"] = True
    cfg["anonymize"]["privacy_radius_m"] = 200
    put = client.put("/api/config", json=cfg)
    assert put.status_code == 200
    assert put.json()["anonymize"]["privacy_radius_m"] == 200

    # Negative radius is rejected by validation.
    cfg["anonymize"]["privacy_radius_m"] = -1
    assert client.put("/api/config", json=cfg).status_code == 422

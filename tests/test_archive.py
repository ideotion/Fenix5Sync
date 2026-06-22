# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for account-export expansion (nested zips + gzip) and the import path."""

from __future__ import annotations

import gzip
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.archive import expand_into
from core.config import write_config
from server.app import create_app
from tests.fixtures.make_gpx import build_sample_gpx


def gpx_bytes() -> bytes:
    return build_sample_gpx().encode("utf-8")


def _write_gpx(path: Path) -> None:
    path.write_bytes(gpx_bytes())


def test_gunzips_activity_files(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    raw = src / "ride.gpx"
    _write_gpx(raw)
    with open(raw, "rb") as fh:
        (src / "ride.gpx.gz").write_bytes(gzip.compress(fh.read()))
    raw.unlink()  # only the .gz remains

    dest = tmp_path / "out"
    files = expand_into(src, dest)
    assert len(files) == 1
    assert files[0].suffix.lower() == ".gpx"
    assert files[0].read_bytes() == gpx_bytes()


def test_recurses_into_nested_zips(tmp_path: Path):
    # Build a Garmin-style zip-of-zips: outer.zip -> inner.zip -> run.gpx.gz
    work = tmp_path / "work"
    work.mkdir()
    inner_zip = work / "inner.zip"
    with zipfile.ZipFile(inner_zip, "w") as zf:
        zf.writestr("DI_CONNECT/run.gpx.gz", gzip.compress(gpx_bytes()))
    outer_zip = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_zip, "w") as zf:
        zf.write(inner_zip, "inner.zip")

    dest = tmp_path / "out"
    files = expand_into(outer_zip, dest)
    assert len(files) == 1
    assert files[0].read_bytes() == gpx_bytes()


def test_copies_plain_supported_files_and_ignores_others(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _write_gpx(src / "a.gpx")
    (src / "notes.txt").write_text("not an activity")
    (src / "readme.csv").write_text("name,sport\n")  # sidecar, ignored for now

    files = expand_into(src, tmp_path / "out")
    assert [f.name for f in files] == ["a.gpx"]


def test_unsafe_zip_member_is_refused(tmp_path: Path):
    bad = tmp_path / "evil.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../escape.gpx", gpx_bytes())
    # Zip-slip is rejected: nothing is extracted from the unsafe archive.
    files = expand_into(bad, tmp_path / "out")
    assert files == []


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def _wait(client: TestClient, job_id: str):
    deadline = time.time() + 15
    while time.time() < deadline:
        st = client.get(f"/api/sync/{job_id}").json()
        if st["status"] != "running":
            return st
        time.sleep(0.1)
    return client.get(f"/api/sync/{job_id}").json()


def test_import_export_endpoint(client: TestClient, tmp_path: Path):
    # A tiny "account export" zip with a gzipped GPX inside.
    export_zip = tmp_path / "garmin_export.zip"
    with zipfile.ZipFile(export_zip, "w") as zf:
        zf.writestr("DI_CONNECT/DI-Connect-Uploaded-Files/act.gpx.gz", gzip.compress(gpx_bytes()))

    r = client.post("/api/sync/import-export", json={"path": str(export_zip)})
    assert r.status_code == 200
    st = _wait(client, r.json()["job_id"])
    assert st["status"] == "done"
    assert st["summary"]["imported"] >= 1

    # Missing path is a clean 404.
    assert client.post("/api/sync/import-export", json={"path": str(tmp_path / "nope.zip")}).status_code == 404

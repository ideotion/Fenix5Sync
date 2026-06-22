# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for FIT salvage (recovering corrupt/truncated activity files)."""

from __future__ import annotations

import struct

import pytest
from fastapi.testclient import TestClient

from core.config import write_config
from core.salvage import fit_crc, salvage_fit, salvage_fit_file
from server.app import create_app
from tests.fixtures.make_fit import build_sample_fit


def test_intact_file_is_complete_and_reparses(tmp_path):
    data = build_sample_fit()
    report = salvage_fit(data)
    assert report.ok and report.reason == "complete"
    assert report.records_recovered > 0
    # The repaired stream is a valid FIT (correct trailer CRC).
    body = report.repaired[:-2]
    assert struct.unpack("<H", report.repaired[-2:])[0] == fit_crc(body)


def test_truncated_file_recovers_the_prefix(tmp_path):
    data = build_sample_fit()
    # Chop off the trailing CRC and the session/lap trailer (and then some),
    # simulating a watch that rebooted before finishing the write.
    truncated = data[:-160]
    report = salvage_fit(truncated)
    assert report.ok
    assert report.reason == "truncated"
    assert 0 < report.bytes_recovered < report.declared_data_size
    assert report.records_recovered > 0

    # The repaired bytes parse into a usable activity with its trackpoints, even
    # though the session/lap trailer was lost.
    p = tmp_path / "broken.fit"
    p.write_bytes(truncated)
    rep2, activity = salvage_fit_file(p)
    assert activity is not None
    assert activity.trackpoints  # records were recovered
    assert activity.start_time is not None  # derived from the first record


def test_non_fit_bytes_are_rejected(tmp_path):
    report = salvage_fit(b"this is not a fit file at all, just text")
    assert not report.ok
    assert report.reason == "no-header"
    assert report.repaired is None


def test_empty_input(tmp_path):
    report = salvage_fit(b"")
    assert not report.ok and report.reason == "empty"


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def test_salvage_endpoint_reports_and_imports(client: TestClient, tmp_path):
    broken = tmp_path / "crashed.fit"
    broken.write_bytes(build_sample_fit()[:-160])

    # Report-only first.
    r = client.post("/api/salvage", json={"path": str(broken)}).json()
    assert r["ok"] is True
    assert r["records_recovered"] > 0
    assert r["preview"] and r["preview"]["trackpoints"] > 0
    assert r["imported"] is None

    # Now salvage AND import.
    r2 = client.post("/api/salvage", json={"path": str(broken), "import": True}).json()
    assert r2["ok"] is True
    assert r2["imported"]["imported"] >= 1

    # Missing file -> clean 404.
    assert client.post("/api/salvage", json={"path": str(tmp_path / "nope.fit")}).status_code == 404

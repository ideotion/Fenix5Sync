# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the read-only filesystem listing that powers the GUI picker."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.config import write_config
from server.app import create_app


@pytest.fixture
def client(tmp_config, tmp_path) -> TestClient:
    cfg_path = tmp_path / "config.yaml"
    write_config(tmp_config, cfg_path)
    return TestClient(create_app(str(cfg_path)))


def _tree(tmp_path: Path) -> Path:
    base = tmp_path / "picktest"
    base.mkdir()
    (base / "sub").mkdir()
    (base / "export.zip").write_bytes(b"PK\x03\x04")
    (base / "notes.txt").write_text("x")
    (base / ".hidden").write_text("secret")
    return base


def test_lists_dirs_and_files(client: TestClient, tmp_path: Path):
    base = _tree(tmp_path)
    r = client.get("/api/fs/list", params={"path": str(base)}).json()
    assert r["path"] == str(base.resolve())
    names = {e["name"]: e["is_dir"] for e in r["entries"]}
    assert names == {"sub": True, "export.zip": False, "notes.txt": False}  # dotfile hidden
    assert r["parent"] == str(base.resolve().parent)
    assert any(q["name"] == "Home" for q in r["quick"])


def test_dirs_only(client: TestClient, tmp_path: Path):
    base = _tree(tmp_path)
    r = client.get("/api/fs/list", params={"path": str(base), "dirs_only": "true"}).json()
    assert [e["name"] for e in r["entries"]] == ["sub"]


def test_extension_filter_keeps_dirs(client: TestClient, tmp_path: Path):
    base = _tree(tmp_path)
    r = client.get("/api/fs/list", params={"path": str(base), "exts": ".zip"}).json()
    names = sorted(e["name"] for e in r["entries"])
    assert names == ["export.zip", "sub"]  # .txt filtered out, dir kept for navigation


def test_missing_path_falls_back_gracefully(client: TestClient, tmp_path: Path):
    r = client.get("/api/fs/list", params={"path": str(tmp_path / "does" / "not" / "exist")})
    assert r.status_code == 200
    assert "path" in r.json() and r.json()["entries"] is not None


def test_default_path_is_home(client: TestClient):
    r = client.get("/api/fs/list").json()
    assert r["path"] == str(Path.home().resolve())

# SPDX-License-Identifier: GPL-3.0-or-later
"""The locator scans GARMIN/Monitor alongside GARMIN/Activity (wellness on sync)."""

from __future__ import annotations

import shutil
from pathlib import Path

from core import Store, import_activities
from core.acquire import locate_source, source_files
from core.config import Config
from tests.fixtures.make_fit import build_monitoring_fit


def _device_config(tmp_path: Path, sample_fit_path: Path) -> Config:
    root = tmp_path / "GARMIN"
    (root / "Activity").mkdir(parents=True)
    (root / "Monitor").mkdir(parents=True)
    shutil.copy(sample_fit_path, root / "Activity" / "a.fit")
    (root / "Monitor" / "m.fit").write_bytes(build_monitoring_fit())
    cfg = Config()
    cfg.storage.data_dir = str(tmp_path / "data")
    cfg.storage.db_file = str(tmp_path / "data" / "db.sqlite")
    cfg.logging.log_dir = str(tmp_path / "logs")
    cfg.source.mode = "path"
    cfg.source.path = str(tmp_path)  # a device root containing GARMIN/
    return cfg


def test_source_files_includes_monitoring(tmp_path: Path, sample_fit_path: Path):
    cfg = _device_config(tmp_path, sample_fit_path)
    source = locate_source(cfg)
    assert source is not None and source.monitoring_dir is not None
    names = sorted(p.name for p in source_files(source, cfg))
    assert names == ["a.fit", "m.fit"]


def test_import_routes_monitoring_to_wellness(tmp_path: Path, sample_fit_path: Path):
    cfg = _device_config(tmp_path, sample_fit_path)
    summary = import_activities(cfg)
    assert summary.imported == 1   # the activity file
    assert summary.wellness == 1   # the monitoring file -> a wellness day
    assert summary.failed == 0
    with Store(cfg.storage.db_path) as store:
        assert len(store.all_wellness_days()) == 1

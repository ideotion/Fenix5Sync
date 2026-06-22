# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for multi-format import: detection, TCX/GPX parsing, sources, pipeline."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from core import (
    Config,
    Store,
    detect_format,
    import_activities,
    parse_activity_file,
)
from core import acquire
from core.importers import extensions, formats
from core.parse import ParseError
from tests.fixtures.make_fit import write_sample as write_fit
from tests.fixtures.make_gpx import build_sample_gpx
from tests.fixtures.make_tcx import build_sample_tcx


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_source_dir(root: Path) -> Path:
    """Create a directory holding one each of FIT, TCX and GPX activities."""
    src = root / "src"
    src.mkdir()
    write_fit(src / "run.fit")
    (src / "ride.tcx").write_text(build_sample_tcx(), encoding="utf-8")
    (src / "walk.gpx").write_text(build_sample_gpx(), encoding="utf-8")
    return src


def _cfg_for(root: Path, mode: str, path: Path | str) -> Config:
    cfg = Config()
    data = root / "data"
    cfg.storage.data_dir = str(data)
    cfg.storage.db_file = str(data / "fenix5sync.sqlite")
    cfg.export.output_dir = str(root / "exports")
    cfg.logging.log_dir = str(root / "logs")
    cfg.source.mode = mode
    cfg.source.path = str(path)
    return cfg


# --------------------------------------------------------------------------- #
# format detection
# --------------------------------------------------------------------------- #
def test_registered_formats():
    assert set(formats()) == {"fit", "tcx", "gpx"}
    assert extensions() == {".fit", ".tcx", ".gpx"}
    assert extensions(["gpx"]) == {".gpx"}


def test_detect_format_by_content(tmp_path: Path, sample_fit_path: Path):
    tcx = tmp_path / "a.tcx"
    tcx.write_text(build_sample_tcx(), encoding="utf-8")
    gpx = tmp_path / "a.gpx"
    gpx.write_text(build_sample_gpx(), encoding="utf-8")

    assert detect_format(sample_fit_path) == "fit"
    assert detect_format(tcx) == "tcx"
    assert detect_format(gpx) == "gpx"

    # Content wins over a misleading extension.
    mislabelled = tmp_path / "mystery.dat"
    mislabelled.write_text(build_sample_gpx(), encoding="utf-8")
    assert detect_format(mislabelled) == "gpx"

    # Unknown content with unknown extension -> None.
    junk = tmp_path / "notes.txt"
    junk.write_text("just some text", encoding="utf-8")
    assert detect_format(junk) is None


# --------------------------------------------------------------------------- #
# TCX parsing
# --------------------------------------------------------------------------- #
def test_parse_tcx(tmp_path: Path):
    p = tmp_path / "a.tcx"
    p.write_text(build_sample_tcx(), encoding="utf-8")
    a = parse_activity_file(p, file_hash="h", raw_path=str(p))

    assert a.sport == "running"
    assert len(a.laps) == 1
    assert len(a.trackpoints) == 5
    assert a.total_distance == pytest.approx(320.0)
    assert a.total_timer_time == pytest.approx(40.0)
    assert a.avg_heart_rate == 124 and a.max_heart_rate == 128
    assert a.avg_speed == pytest.approx(8.0)
    assert a.avg_power == 212  # mean of 210..214
    assert a.total_ascent == 4 and a.total_descent == 0
    assert a.start_latitude == pytest.approx(51.5007, abs=1e-4)
    assert a.device_product == "Forerunner 945"
    assert a.device_manufacturer == "garmin"
    assert a.extra["source_format"]["value"] == "tcx"


# --------------------------------------------------------------------------- #
# GPX parsing
# --------------------------------------------------------------------------- #
def test_parse_gpx(tmp_path: Path):
    p = tmp_path / "a.gpx"
    p.write_text(build_sample_gpx(), encoding="utf-8")
    a = parse_activity_file(p, file_hash="h", raw_path=str(p))

    assert a.sport == "running"
    assert len(a.trackpoints) == 5
    assert a.avg_heart_rate == 134 and a.max_heart_rate == 138
    # Distance/elapsed/speed are derived (GPX states none of them).
    assert a.total_distance is not None and a.total_distance > 0
    assert a.total_elapsed_time == pytest.approx(40.0)
    assert a.avg_speed is not None and a.avg_speed > 0
    assert a.total_ascent == 4 and a.total_descent == 0
    assert a.start_latitude == pytest.approx(51.5007, abs=1e-4)
    assert a.device_product == "StravaGPX"
    assert a.extra["source_format"]["value"] == "gpx"
    # First geolocated point has zero cumulative distance, last is the max.
    assert a.trackpoints[0].distance == pytest.approx(0.0)
    assert a.trackpoints[-1].distance == pytest.approx(a.total_distance)


def test_parse_unknown_format_raises(tmp_path: Path):
    junk = tmp_path / "x.dat"
    junk.write_bytes(b"definitely not an activity file")
    with pytest.raises(ParseError):
        parse_activity_file(junk)


# --------------------------------------------------------------------------- #
# source discovery + copy_to_raw
# --------------------------------------------------------------------------- #
def test_list_activity_files(tmp_path: Path):
    src = _make_source_dir(tmp_path)
    (src / "ignore.txt").write_text("nope", encoding="utf-8")
    assert len(acquire.list_activity_files(src)) == 3
    assert [p.name for p in acquire.list_activity_files(src, formats=["gpx"])] == ["walk.gpx"]


def test_copy_to_raw_preserves_extension(tmp_path: Path):
    raw = tmp_path / "raw"
    gpx = tmp_path / "a.gpx"
    gpx.write_text(build_sample_gpx(), encoding="utf-8")
    dest = acquire.copy_to_raw(gpx, raw, "deadbeef", gpx.suffix)
    assert dest.name == "deadbeef.gpx" and dest.is_file()

    # An extensionless source defaults to .fit (back-compat with the old store).
    noext = tmp_path / "blob"
    noext.write_bytes(b"x")
    assert acquire.copy_to_raw(noext, raw, "abc", "").name == "abc.fit"


# --------------------------------------------------------------------------- #
# pipeline: folder / file / zip
# --------------------------------------------------------------------------- #
def test_pipeline_imports_mixed_folder(tmp_path: Path):
    src = _make_source_dir(tmp_path)
    cfg = _cfg_for(tmp_path, "folder", src)

    first = import_activities(cfg)
    assert first.found == 3 and first.imported == 3 and first.failed == 0

    with Store(cfg.storage.db_path) as store:
        assert store.count() == 3
        assert store.sports() == ["running"]
        # Raw files were stored under their real extensions.
        raw_suffixes = {p.suffix for p in cfg.storage.raw_dir.iterdir()}
        assert raw_suffixes == {".fit", ".tcx", ".gpx"}

    # Dedupe: a second run re-finds the same three but imports none.
    second = import_activities(cfg)
    assert second.found == 3 and second.imported == 0 and second.skipped == 3


def test_pipeline_single_file_mode(tmp_path: Path):
    gpx = tmp_path / "one.gpx"
    gpx.write_text(build_sample_gpx(), encoding="utf-8")
    cfg = _cfg_for(tmp_path, "file", gpx)
    summary = import_activities(cfg)
    assert summary.found == 1 and summary.imported == 1


def test_pipeline_zip_mode(tmp_path: Path):
    src = _make_source_dir(tmp_path)
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for f in src.iterdir():
            zf.write(f, f.name)
    cfg = _cfg_for(tmp_path, "zip", archive)
    summary = import_activities(cfg)
    assert summary.found == 3 and summary.imported == 3


def test_zip_slip_is_refused(tmp_path: Path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.gpx", build_sample_gpx())
    dest = tmp_path / "out"
    dest.mkdir()
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(ValueError):
            acquire._safe_extract_zip(zf, dest)
    # And the pipeline refuses such an archive rather than writing outside dest.
    cfg = _cfg_for(tmp_path, "zip", archive)
    assert acquire.locate_source(cfg) is None
    assert not (tmp_path / "escaped.gpx").exists()


# --------------------------------------------------------------------------- #
# export of a non-FIT-sourced activity
# --------------------------------------------------------------------------- #
def test_gpx_source_exports_via_builtin_writer(tmp_path: Path):
    from core import activity_gpx

    gpx = tmp_path / "one.gpx"
    gpx.write_text(build_sample_gpx(), encoding="utf-8")
    cfg = _cfg_for(tmp_path, "file", gpx)
    import_activities(cfg)
    with Store(cfg.storage.db_path) as store:
        a = store.get_activity(1, with_series=True)

    # raw is .gpx, so gpsbabel (garmin_fit input) is skipped; built-in writer runs.
    out = activity_gpx(a, prefer_gpsbabel=True)
    assert out.startswith("<?xml") and out.count("<trkpt") == 5


# --------------------------------------------------------------------------- #
# config validation for the new knobs
# --------------------------------------------------------------------------- #
def test_config_accepts_new_source_options():
    cfg = Config.from_dict(
        {"source": {"mode": "folder", "recursive": True, "formats": ["gpx", "fit"]}}
    )
    assert cfg.source.mode == "folder"
    assert cfg.source.recursive is True
    assert cfg.source.formats == ["gpx", "fit"]


def test_config_rejects_bad_mode_and_formats():
    with pytest.raises(ValueError):
        Config.from_dict({"source": {"mode": "telepathy"}})
    with pytest.raises(ValueError):
        Config.from_dict({"source": {"formats": ["fit", "bogus"]}})

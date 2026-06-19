"""Tests for optional, non-destructive anonymization."""

from __future__ import annotations

from pathlib import Path

from core import anonymize_activity, effective_options, parse_fit_file, sha256_file
from core.config import AnonymizeConfig
from core.models import Activity


def _activity(sample_fit_path: Path) -> Activity:
    return parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))


def test_disabled_returns_unchanged_copy(sample_fit_path: Path):
    a = _activity(sample_fit_path)
    out = anonymize_activity(a, AnonymizeConfig(enabled=False))
    assert out is not a  # always a copy
    assert out.start_latitude == a.start_latitude
    assert out.device_manufacturer == a.device_manufacturer
    assert out.raw_path == a.raw_path


def test_drop_gps_is_non_destructive(sample_fit_path: Path):
    a = _activity(sample_fit_path)
    out = anonymize_activity(a, AnonymizeConfig(enabled=True, drop_gps=True))
    assert out.start_latitude is None and out.start_longitude is None
    assert all(tp.latitude is None and tp.longitude is None for tp in out.trackpoints)
    # The source activity is untouched.
    assert any(tp.latitude is not None for tp in a.trackpoints)


def test_privacy_radius_trims_start_and_end(sample_fit_path: Path):
    a = _activity(sample_fit_path)
    out = anonymize_activity(a, AnonymizeConfig(enabled=True, privacy_radius_m=50))
    assert out.start_latitude is None  # start is always within its own zone
    assert out.trackpoints[0].latitude is None
    assert out.trackpoints[-1].latitude is None
    # A mid-track point (well outside both zones) keeps its coordinates.
    assert out.trackpoints[6].latitude is not None


def test_fuzz_is_deterministic_and_bounded(sample_fit_path: Path):
    a = _activity(sample_fit_path)
    opts = AnonymizeConfig(enabled=True, fuzz_gps_m=20)
    out1 = anonymize_activity(a, opts)
    out2 = anonymize_activity(a, opts)
    coords1 = [(tp.latitude, tp.longitude) for tp in out1.trackpoints]
    coords2 = [(tp.latitude, tp.longitude) for tp in out2.trackpoints]
    assert coords1 == coords2  # seeded by file_hash -> stable exports
    # Every located point moved, but only slightly (~20 m << 0.001 deg).
    for o, s in zip(out1.trackpoints, a.trackpoints):
        if s.latitude is not None:
            assert o.latitude != s.latitude
            assert abs(o.latitude - s.latitude) < 0.001


def test_strip_device_and_personal():
    a = Activity(
        file_hash="h",
        device_manufacturer="garmin",
        device_product="fenix5",
        extra={
            "serial_number": {"value": 123456, "units": None},
            "age": {"value": 35, "units": "years"},
            "total_distance": {"value": 1000, "units": "m"},
        },
    )
    out = anonymize_activity(a, AnonymizeConfig(enabled=True, strip_device=True, strip_personal=True))
    assert out.device_manufacturer is None and out.device_product is None
    assert "serial_number" not in out.extra
    assert "age" not in out.extra
    assert "total_distance" in out.extra  # non-sensitive metric is kept


def test_shift_dates_preserves_intervals(sample_fit_path: Path):
    a = _activity(sample_fit_path)
    out = anonymize_activity(a, AnonymizeConfig(enabled=True, shift_dates=True))
    assert out.start_time.year == 2000
    assert (out.trackpoints[-1].timestamp - out.trackpoints[0].timestamp) == (
        a.trackpoints[-1].timestamp - a.trackpoints[0].timestamp
    )
    assert out.imported_at is None


def test_raw_path_always_cleared(sample_fit_path: Path):
    a = _activity(sample_fit_path)
    out = anonymize_activity(a, AnonymizeConfig(enabled=True))
    assert out.raw_path == "" and a.raw_path != ""


def test_effective_options_forces_enabled_only_when_asked():
    off = AnonymizeConfig(enabled=False)
    assert effective_options(off, force=False).enabled is False
    assert effective_options(off, force=True).enabled is True
    on = AnonymizeConfig(enabled=True)
    assert effective_options(on, force=False) is on  # unchanged when already on

# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end core test: parse -> store -> export, plus dedupe and resilience."""

from __future__ import annotations

from pathlib import Path

import pytest

import json

from core import (
    ParseError,
    Store,
    activities_ndjson,
    activities_summary_csv,
    activity_gpx,
    activity_json,
    activity_trackpoints_csv,
    import_activities,
    parse_fit_file,
    sha256_file,
    write_archive,
)


def test_parse_sample(sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    assert a.sport == "running"
    assert a.total_distance == pytest.approx(308.0)
    assert a.total_timer_time == pytest.approx(110.0)
    assert a.avg_heart_rate == 126 and a.max_heart_rate == 131
    assert a.avg_speed == pytest.approx(2.8)
    assert a.avg_power == 215
    assert a.total_ascent == 11
    assert a.start_latitude == pytest.approx(51.5007, abs=1e-4)
    assert len(a.laps) == 1
    assert len(a.trackpoints) == 12
    # Units preserved in extra.
    assert a.extra["total_distance"]["units"] == "m"
    assert a.extra["avg_speed"]["units"] == "m/s"


def test_parse_corrupt(tmp_path: Path):
    bad = tmp_path / "bad.fit"
    bad.write_bytes(b"not a real fit file at all")
    with pytest.raises(ParseError):
        parse_fit_file(bad)


def test_store_roundtrip(tmp_path: Path, sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    with Store(tmp_path / "db.sqlite") as store:
        activity_id = store.add_activity(a)
        assert activity_id > 0
        assert store.is_imported(a.file_hash)

        fetched = store.get_activity(activity_id)
        assert fetched is not None
        assert fetched.sport == "running"
        assert len(fetched.trackpoints) == 12
        assert len(fetched.laps) == 1
        assert fetched.total_distance == pytest.approx(308.0)
        # trackpoint ordering preserved
        assert fetched.trackpoints[0].timestamp < fetched.trackpoints[-1].timestamp

        assert store.count() == 1
        assert store.sports() == ["running"]
        stats = store.summary_stats()
        assert stats["count"] == 1
        assert stats["total_distance"] == pytest.approx(308.0)


def test_dedupe_via_pipeline(tmp_config):
    # First run imports the single fixture; second run skips it (same hash).
    first = import_activities(tmp_config)
    assert first.found == 1 and first.imported == 1 and first.skipped == 0

    second = import_activities(tmp_config)
    assert second.found == 1 and second.imported == 0 and second.skipped == 1


def test_exports(tmp_path: Path, sample_fit_path: Path):
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    with Store(tmp_path / "db.sqlite") as store:
        store.add_activity(a)
        full = store.get_activity(a.id)

    # JSON
    js = activity_json(full)
    assert '"sport": "running"' in js
    assert '"trackpoints"' in js

    # CSV (per-activity trackpoints)
    csv_text = activity_trackpoints_csv(full)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("timestamp,latitude_deg,longitude_deg")
    assert len(lines) == 1 + 12  # header + 12 trackpoints

    # CSV (bulk summary)
    summary_csv = activities_summary_csv([full])
    assert "total_distance_m" in summary_csv.splitlines()[0]
    assert len(summary_csv.strip().splitlines()) == 2

    # GPX (built-in writer path; gpsbabel not required for the test)
    gpx = activity_gpx(full, prefer_gpsbabel=False)
    assert gpx.startswith("<?xml")
    assert gpx.count("<trkpt") == 12
    assert "<gpx" in gpx and "</gpx>" in gpx


def test_archive_ndjson(tmp_path, sample_fit_path):
    """The long-term archive is full-fidelity NDJSON: one activity per line."""
    a = parse_fit_file(sample_fit_path, sha256_file(sample_fit_path), str(sample_fit_path))
    with Store(tmp_path / "db.sqlite") as store:
        store.add_activity(a)
        activities = store.all_activities(with_series=True)

    # NDJSON string: one JSON object per line, parseable, with full series.
    nd = activities_ndjson(activities, include_series=True)
    lines = nd.strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["sport"] == "running"
    assert len(record["trackpoints"]) == 12
    assert len(record["laps"]) == 1
    # units preserved for downstream mining
    assert record["extra"]["total_distance"]["units"] == "m"

    # write_archive produces a timestamped .ndjson file
    path = write_archive(activities, tmp_path / "archive")
    assert path.suffix == ".ndjson" and path.is_file()
    assert json.loads(path.read_text().strip())["total_distance_m"] == pytest.approx(308.0)

# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for monitoring-file wellness parsing and daily summarization."""

from __future__ import annotations

from pathlib import Path

from core import DayWellness, parse_wellness_file, summarize_wellness
from tests.fixtures.make_fit import build_monitoring_fit


# --------------------------------------------------------------------------- #
# pure summarization
# --------------------------------------------------------------------------- #
def test_summarize_groups_by_day():
    records = [
        {"date": "2023-06-15", "hr": 50}, {"date": "2023-06-15", "hr": 90},
        {"date": "2023-06-15", "steps": 2000}, {"date": "2023-06-15", "steps": 8000},
        {"date": "2023-06-15", "stress": 30}, {"date": "2023-06-15", "stress": 50},
        {"date": "2023-06-16", "hr": 60},
    ]
    days = summarize_wellness(records)
    assert [d.date for d in days] == ["2023-06-15", "2023-06-16"]
    d0 = days[0]
    assert d0.steps == 8000          # cumulative -> max
    assert d0.resting_hr == 50 and d0.max_hr == 90 and d0.avg_hr == 70
    assert d0.avg_stress == 40 and d0.stress_samples == 2
    assert days[1].steps is None and days[1].resting_hr == 60


def test_summarize_empty():
    assert summarize_wellness([]) == []


def test_day_wellness_as_dict_shape():
    d = DayWellness("2023-06-15", 8000, 50, 70, 95, 40, 4)
    assert set(d.as_dict()) == {
        "date", "steps", "resting_hr", "avg_hr", "max_hr", "avg_stress", "stress_samples",
    }


# --------------------------------------------------------------------------- #
# end-to-end parse of a synthesized monitoring file
# --------------------------------------------------------------------------- #
def test_parse_monitoring_file(tmp_path: Path):
    p = tmp_path / "monitoring.fit"
    p.write_bytes(build_monitoring_fit())
    out = parse_wellness_file(p)
    assert list(out) == ["days"]
    assert len(out["days"]) == 1
    d = out["days"][0]
    assert d["date"] == "2023-06-15"
    assert d["steps"] == 8000                      # cumulative max
    assert d["resting_hr"] == 50                   # overnight minimum
    assert d["max_hr"] == 95
    assert d["avg_hr"] == 70                        # (50+65+72+95+68)/5
    assert d["avg_stress"] == 40                    # (20+40+60+40)/4, -1 sentinel dropped
    assert d["stress_samples"] == 4

# SPDX-License-Identifier: GPL-3.0-or-later
"""Search/filter tests against a store populated with synthetic activities."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from core import ActivityFilter, Store
from core.models import Activity


def _activity(hash_: str, sport: str, when: str, distance: float, duration: float) -> Activity:
    return Activity(
        file_hash=hash_,
        raw_path=f"/tmp/{hash_}.fit",
        sport=sport,
        start_time=_dt.datetime.fromisoformat(when),
        total_distance=distance,
        total_timer_time=duration,
    )


def _seed(store: Store) -> None:
    store.add_activity(_activity("h1", "running", "2023-01-10T07:00:00", 5000, 1800))
    store.add_activity(_activity("h2", "cycling", "2023-02-15T09:00:00", 30000, 3600))
    store.add_activity(_activity("h3", "running", "2023-03-20T18:30:00", 10000, 3000))
    store.add_activity(_activity("h4", "swimming", "2023-03-25T12:00:00", 1500, 2400))


def test_filter_by_sport(tmp_path: Path):
    with Store(tmp_path / "db.sqlite") as store:
        _seed(store)
        res = store.search(ActivityFilter(sport="running"))
        assert {a.file_hash for a in res} == {"h1", "h3"}
        # case-insensitive
        assert len(store.search(ActivityFilter(sport="RUNNING"))) == 2


def test_filter_by_date_range(tmp_path: Path):
    with Store(tmp_path / "db.sqlite") as store:
        _seed(store)
        res = store.search(ActivityFilter(date_from="2023-02-01", date_to="2023-03-21"))
        assert {a.file_hash for a in res} == {"h2", "h3"}


def test_filter_by_distance_and_duration(tmp_path: Path):
    with Store(tmp_path / "db.sqlite") as store:
        _seed(store)
        res = store.search(ActivityFilter(min_distance=4000, max_distance=12000))
        assert {a.file_hash for a in res} == {"h1", "h3"}

        res = store.search(ActivityFilter(min_duration=3000))
        assert {a.file_hash for a in res} == {"h2", "h3"}


def test_sort_and_paginate(tmp_path: Path):
    with Store(tmp_path / "db.sqlite") as store:
        _seed(store)
        res = store.search(ActivityFilter(sort="total_distance", order="desc"))
        assert [a.file_hash for a in res] == ["h2", "h3", "h1", "h4"]

        page = store.search(ActivityFilter(sort="start_time", order="asc", limit=2, offset=1))
        assert [a.file_hash for a in page] == ["h2", "h3"]


def test_count_with_filter(tmp_path: Path):
    with Store(tmp_path / "db.sqlite") as store:
        _seed(store)
        assert store.count() == 4
        assert store.count(ActivityFilter(sport="running")) == 2

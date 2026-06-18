"""Domain models for Fenix5Sync.

These are plain dataclasses with no dependency on the web or CLI layers, so the
core library can be used on its own. Field comments record the physical units of
each value (FIT stores SI-ish units; we preserve them rather than reducing to a
minimal subset). Any additional FIT fields not promoted to a dedicated attribute
are retained in the ``extra`` mapping as ``{name: {"value": ..., "units": ...}}``
so nothing is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Trackpoint:
    """A single record-level sample from an activity time series."""

    timestamp: datetime | None = None  # UTC
    latitude: float | None = None  # degrees
    longitude: float | None = None  # degrees
    heart_rate: int | None = None  # bpm
    cadence: int | None = None  # rpm
    speed: float | None = None  # m/s
    altitude: float | None = None  # m
    distance: float | None = None  # m, cumulative
    temperature: float | None = None  # deg C
    power: int | None = None  # W
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Lap:
    """Per-lap summary."""

    lap_index: int = 0
    start_time: datetime | None = None  # UTC
    total_timer_time: float | None = None  # s
    total_elapsed_time: float | None = None  # s
    total_distance: float | None = None  # m
    avg_heart_rate: int | None = None  # bpm
    max_heart_rate: int | None = None  # bpm
    avg_speed: float | None = None  # m/s
    max_speed: float | None = None  # m/s
    total_ascent: int | None = None  # m
    total_descent: int | None = None  # m
    total_calories: int | None = None  # kcal
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Activity:
    """One activity: session summary plus optional laps and trackpoints.

    ``laps`` and ``trackpoints`` may be empty when an activity is loaded in a
    list/summary context and populated when fetched in full.
    """

    file_hash: str = ""  # SHA-256 of the source .FIT content
    raw_path: str = ""  # path to the stored raw .FIT file
    sport: str | None = None
    sub_sport: str | None = None
    start_time: datetime | None = None  # UTC
    total_timer_time: float | None = None  # s (moving/timer time)
    total_elapsed_time: float | None = None  # s (wall clock)
    total_distance: float | None = None  # m
    total_calories: int | None = None  # kcal
    avg_heart_rate: int | None = None  # bpm
    max_heart_rate: int | None = None  # bpm
    avg_speed: float | None = None  # m/s
    max_speed: float | None = None  # m/s
    avg_cadence: int | None = None  # rpm
    avg_power: int | None = None  # W
    avg_temperature: float | None = None  # deg C
    total_ascent: int | None = None  # m
    total_descent: int | None = None  # m
    start_latitude: float | None = None  # degrees
    start_longitude: float | None = None  # degrees
    device_manufacturer: str | None = None
    device_product: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    laps: list[Lap] = field(default_factory=list)
    trackpoints: list[Trackpoint] = field(default_factory=list)
    id: int | None = None  # DB row id, set after storage
    imported_at: datetime | None = None  # UTC


@dataclass
class RunSummary:
    """Outcome of an import/sync run.

    Counts are reported to the GUI/CLI as ``found / imported / skipped / failed``.
    """

    found: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    imported_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "imported": self.imported,
            "skipped": self.skipped,
            "failed": self.failed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "imported_ids": list(self.imported_ids),
            "errors": list(self.errors),
            "messages": list(self.messages),
        }

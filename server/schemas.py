# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed request/response models for the JSON API (drives /docs)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str = "ok"
    version: str


class Stats(BaseModel):
    count: int
    total_distance_m: float
    total_duration_s: float
    sports: list[str]


class ActivitySummary(BaseModel):
    id: int | None = None
    file_hash: str
    sport: str | None = None
    sub_sport: str | None = None
    start_time: str | None = None
    total_timer_time_s: float | None = None
    total_elapsed_time_s: float | None = None
    total_distance_m: float | None = None
    total_calories: int | None = None
    avg_heart_rate_bpm: int | None = None
    max_heart_rate_bpm: int | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    avg_cadence_rpm: int | None = None
    avg_power_w: int | None = None
    avg_temperature_c: float | None = None
    total_ascent_m: int | None = None
    total_descent_m: int | None = None
    start_latitude_deg: float | None = None
    start_longitude_deg: float | None = None
    device_manufacturer: str | None = None
    device_product: str | None = None
    imported_at: str | None = None


class ActivityList(BaseModel):
    total: int
    count: int
    items: list[ActivitySummary]
    sports: list[str]


class Lap(BaseModel):
    lap_index: int
    start_time: str | None = None
    total_timer_time_s: float | None = None
    total_elapsed_time_s: float | None = None
    total_distance_m: float | None = None
    avg_heart_rate_bpm: int | None = None
    max_heart_rate_bpm: int | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    total_ascent_m: int | None = None
    total_descent_m: int | None = None
    total_calories: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Trackpoint(BaseModel):
    timestamp: str | None = None
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    heart_rate_bpm: int | None = None
    cadence_rpm: int | None = None
    speed_mps: float | None = None
    altitude_m: float | None = None
    distance_m: float | None = None
    temperature_c: float | None = None
    power_w: int | None = None


class ActivityDetail(ActivitySummary):
    raw_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    laps: list[Lap] = Field(default_factory=list)
    trackpoints: list[Trackpoint] = Field(default_factory=list)


class SyncStatus(BaseModel):
    job_id: str
    status: str  # running | done | error
    created_at: str | None = None
    finished_at: str | None = None
    current: int = 0
    total: int = 0
    phase: str | None = None
    filename: str | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None


class LogsResponse(BaseModel):
    lines: list[str]


class ExportImportRequest(BaseModel):
    """Import an account export (Garmin/Strava .zip or folder) from a local path."""

    path: str = Field(min_length=1)


class SegmentCreate(BaseModel):
    """Create a personal segment from a reference activity's GPS track."""

    activity_id: int
    name: str = Field(min_length=1, max_length=120)
    num_waypoints: int = Field(default=12, ge=2, le=64)
    radius_m: float = Field(default=30.0, gt=0, le=500)


# ---- config models (mirror core.config dataclasses) ------------------------
class SourceModel(BaseModel):
    mode: str = "auto"
    path: str = ""
    extra_mount_roots: list[str] = Field(default_factory=list)
    activity_subdir: str = "GARMIN/Activity"
    monitoring_subdir: str = "GARMIN/Monitor"
    mtp_mountpoint: str = "~/.cache/fenix5sync/mtp"
    recursive: bool = False
    formats: list[str] = Field(default_factory=list)


class StorageModel(BaseModel):
    data_dir: str
    raw_subdir: str = "raw"
    db_file: str


class ExportModel(BaseModel):
    output_dir: str
    gpsbabel_bin: str = "gpsbabel"


class DedupeModel(BaseModel):
    enabled: bool = True


class AnonymizeModel(BaseModel):
    enabled: bool = False
    drop_gps: bool = False
    privacy_radius_m: float = 0.0
    fuzz_gps_m: float = 0.0
    strip_device: bool = True
    strip_personal: bool = True
    shift_dates: bool = False


class AthleteModel(BaseModel):
    max_heart_rate: int | None = None
    resting_heart_rate: int | None = None
    ftp_w: int | None = None


class ServerModel(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True


class LoggingModel(BaseModel):
    log_dir: str
    level: str = "INFO"


class ConfigModel(BaseModel):
    source: SourceModel
    storage: StorageModel
    export: ExportModel
    dedupe: DedupeModel
    anonymize: AnonymizeModel = AnonymizeModel()
    athlete: AthleteModel = AthleteModel()
    server: ServerModel
    logging: LoggingModel

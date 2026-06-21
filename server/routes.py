"""JSON API routes, mounted under ``/api``.

Each request opens a short-lived :class:`~core.store.Store` (SQLite is cheap to
open locally and this keeps connections within a single thread). Config and the
import :class:`~server.progress.JobManager` live on ``app.state``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from core import __version__
from core.anonymize import anonymize_activity, effective_options
from core.athlete import suggest_athlete
from core.best_efforts import compute_best_efforts
from core.config import Config, write_config
from core.export import (
    ExportError,
    activities_json,
    activities_ndjson,
    activities_summary_csv,
    activity_gpx,
    activity_json,
    activity_tcx,
    activity_to_dict,
    activity_trackpoints_csv,
)
from core.hr_trends import compute_hr_trends
from core.logging_setup import read_recent_logs
from core.metrics import compute_activity_metrics
from core.race import compute_race_predictions
from core.search import ActivityFilter
from core.splits import MILE_M, compute_splits
from core.store import Store
from core.training_load import compute_training_load
from core.zones import compute_zones
from .progress import JobManager
from .schemas import (
    ActivityDetail,
    ActivityList,
    ConfigModel,
    Health,
    LogsResponse,
    Stats,
    SyncStatus,
)

router = APIRouter(prefix="/api")

_MEDIA = {
    "csv": "text/csv",
    "json": "application/json",
    "ndjson": "application/x-ndjson",
    "gpx": "application/gpx+xml",
    "tcx": "application/vnd.garmin.tcx+xml",
}


# ---- dependencies ----------------------------------------------------------
def get_config(request: Request) -> Config:
    return request.app.state.config


def get_jobs(request: Request) -> JobManager:
    return request.app.state.jobs


def get_store(request: Request) -> Iterator[Store]:
    store = Store(request.app.state.config.storage.db_path)
    try:
        yield store
    finally:
        store.close()


# ---- meta ------------------------------------------------------------------
@router.get("/health", response_model=Health)
def health() -> Health:
    return Health(version=__version__)


@router.get("/stats", response_model=Stats)
def stats(store: Store = Depends(get_store)) -> Stats:
    s = store.summary_stats()
    return Stats(
        count=s["count"],
        total_distance_m=s["total_distance"],
        total_duration_s=s["total_duration"],
        sports=store.sports(),
    )


@router.get("/athlete/suggestions")
def athlete_suggestions(store: Store = Depends(get_store)) -> dict:
    """Suggested athlete values from the archive (observed max HR + watch profile).

    Read-only hints for the Settings page: the highest observed max HR, and
    weight/height/gender/resting HR from the most recent device ``user_profile``.
    """
    return suggest_athlete(store.all_activities(with_series=False))


@router.get("/insights")
def insights(
    sport: str | None = Query(None, description="Scope all figures to one sport."),
    store: Store = Depends(get_store),
) -> dict:
    """Aggregate analytics for the Insights view (totals, trends, PRs, calendar)."""
    return store.insights(sport)


@router.get("/insights/training-load")
def insights_training_load(
    sport: str | None = Query(None, description="Scope the chart to one sport."),
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> dict:
    """Performance Management Chart: Fitness (CTL), Fatigue (ATL) and Form (TSB).

    Computed locally from activity *summaries* only (``total_timer_time``,
    ``avg_power``, ``avg_heart_rate``, ``start_time``, ``sport``) -- a single
    query, deliberately not loading every trackpoint (which would be an N+1 over
    the whole archive). Per-activity stress uses the best basis the athlete config
    supports (power TSS, HR TRIMP, else a duration estimate); at this summary level
    Normalized Power is approximated by ``avg_power``. ``needs`` lists thresholds
    (e.g. ``ftp_w``) that would sharpen the numbers.
    """
    activities = store.all_activities(with_series=False)
    return compute_training_load(activities, cfg.athlete, sport=sport)


@router.get("/insights/wellness")
def insights_wellness(store: Store = Depends(get_store)) -> dict:
    """Daily wellness summaries (steps, resting/avg/max HR, stress) from monitoring files."""
    return {"days": store.all_wellness_days()}


@router.get("/insights/hr-trends")
def insights_hr_trends(
    sport: str | None = Query(None, description="Scope the trend to one sport."),
    store: Store = Depends(get_store),
) -> dict:
    """Cross-activity heart-rate & efficiency trends (avg/max HR, Efficiency Factor).

    Computed from activity summaries only (one query, no per-activity trackpoint
    load). ``ef_basis`` reports whether efficiency is power- or pace-derived.
    """
    return compute_hr_trends(store.all_activities(with_series=False), sport=sport)


# ---- activities ------------------------------------------------------------
@router.get("/activities", response_model=ActivityList)
def list_activities(
    store: Store = Depends(get_store),
    date_from: str | None = Query(None, description="ISO date/datetime lower bound"),
    date_to: str | None = Query(None, description="ISO date/datetime upper bound"),
    sport: str | None = Query(None),
    min_distance: float | None = Query(None, description="metres"),
    max_distance: float | None = Query(None, description="metres"),
    min_duration: float | None = Query(None, description="seconds"),
    max_duration: float | None = Query(None, description="seconds"),
    sort: str = Query("start_time"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> ActivityList:
    f = ActivityFilter(
        date_from=date_from, date_to=date_to, sport=sport,
        min_distance=min_distance, max_distance=max_distance,
        min_duration=min_duration, max_duration=max_duration,
        sort=sort, order=order, limit=limit, offset=offset,
    )
    items = store.search(f)
    total = store.count(f)
    payload = [activity_to_dict(a, include_series=False) for a in items]
    return ActivityList(
        total=total,
        count=len(payload),
        items=payload,  # type: ignore[arg-type]
        sports=store.sports(),
    )


@router.get("/activities/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int, store: Store = Depends(get_store)) -> ActivityDetail:
    activity = store.get_activity(activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")
    return activity_to_dict(activity, include_series=True)  # type: ignore[return-value]


@router.get("/activities/{activity_id}/zones")
def activity_zones(
    activity_id: int,
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> dict:
    """Heart-rate and power time-in-zone for one activity (computed locally).

    Uses athlete thresholds from config; HR falls back to the activity's observed
    maximum when none is set, and power is omitted until an FTP is configured.
    """
    activity = store.get_activity(activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")
    return compute_zones(activity, cfg.athlete)


@router.get("/activities/{activity_id}/metrics")
def activity_metrics(
    activity_id: int,
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> dict:
    """Advanced per-activity metrics (intensity, efficiency, pace, HR, …).

    Computed locally from the trackpoint series using athlete thresholds from
    config. Power figures (NP/IF/VI/TSS) need a power series and an FTP; without
    those, efficiency/decoupling fall back to pace and ``needs`` flags what's
    missing. Empty groups are returned as ``null`` so the UI can omit them.
    """
    activity = store.get_activity(activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")
    return compute_activity_metrics(activity, cfg.athlete)


@router.get("/activities/{activity_id}/splits")
def activity_splits(
    activity_id: int,
    unit: str = Query("km", pattern="^(km|mi)$", description="Split distance unit."),
    metres: float | None = Query(
        None, gt=0, le=100000, description="Custom split length in metres (overrides unit)."
    ),
    store: Store = Depends(get_store),
) -> dict:
    """Even-distance splits (pace / HR / elevation per segment) for one activity.

    Defaults to 1 km splits; pass ``unit=mi`` for miles or ``metres`` for any
    custom length. Computed locally from the trackpoint distance series.
    """
    activity = store.get_activity(activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")
    length = metres if metres is not None else (MILE_M if unit == "mi" else 1000.0)
    return compute_splits(activity, metres=length)


@router.get("/activities/{activity_id}/best-efforts")
def activity_best_efforts(activity_id: int, store: Store = Depends(get_store)) -> dict:
    """Best-effort times per distance and mean-max power/speed curves.

    Computed locally from this one activity's series (no archive-wide scan):
    ``best_distances`` (fastest 200 m … marathon found in the run), ``power_curve``
    and ``speed_curve`` (peak sustained average over standard durations).
    """
    activity = store.get_activity(activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")
    return compute_best_efforts(activity)


@router.get("/activities/{activity_id}/race-predictions")
def activity_race_predictions(activity_id: int, store: Store = Depends(get_store)) -> dict:
    """VO₂max estimate + race-time predictions (running), from this activity.

    An open Daniels/Riegel model over the activity's best effort, computed
    locally. ``available`` is False for non-running activities or efforts too
    short to anchor a prediction. Explicitly not Garmin's FirstBeat VO₂max.
    """
    activity = store.get_activity(activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")
    return compute_race_predictions(activity)


@router.get("/activities/{activity_id}/export")
def export_activity(
    activity_id: int,
    format: str = Query("json", pattern="^(csv|json|gpx|tcx|raw)$"),
    anonymize: bool = Query(False, description="Scrub location & sensitive data."),
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> Response:
    activity = store.get_activity(activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")

    opts = effective_options(cfg.anonymize, anonymize)

    if format == "raw":
        if opts.enabled:
            raise HTTPException(
                status_code=422,
                detail="raw export returns the original file and cannot be anonymized; "
                "choose gpx, tcx, json or csv to anonymize",
            )
        src = Path(activity.raw_path)
        if not src.is_file():
            raise HTTPException(status_code=422, detail="original raw file is not available")
        suffix = (src.suffix or ".fit").lower()
        return Response(
            content=src.read_bytes(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="activity-{activity_id}{suffix}"'},
        )

    activity = anonymize_activity(activity, opts)
    try:
        if format == "json":
            body = activity_json(activity)
        elif format == "csv":
            body = activity_trackpoints_csv(activity)
        elif format == "tcx":
            body = activity_tcx(activity)
        else:
            body = activity_gpx(activity, cfg.export.gpsbabel_bin)
    except ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _download(body, f"activity-{activity_id}.{format}", format)


# ---- bulk export -----------------------------------------------------------
@router.get("/export")
def export_bulk(
    format: str = Query("csv", pattern="^(csv|json|ndjson)$"),
    full: bool = Query(False, description="Include laps + trackpoints (json/ndjson)."),
    anonymize: bool = Query(False, description="Scrub location & sensitive data."),
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> Response:
    activities = store.all_activities(with_series=full)
    opts = effective_options(cfg.anonymize, anonymize)
    if opts.enabled:
        activities = [anonymize_activity(a, opts) for a in activities]
    if format == "ndjson":
        body = activities_ndjson(activities, include_series=full)
    elif format == "json":
        body = activities_json(activities, include_series=full)
    else:
        body = activities_summary_csv(activities)
    return _download(body, f"activities.{format}", format)


# ---- import / sync ---------------------------------------------------------
@router.post("/sync", response_model=SyncStatus)
def start_sync(
    cfg: Config = Depends(get_config), jobs: JobManager = Depends(get_jobs)
) -> SyncStatus:
    job = jobs.start(cfg)
    return SyncStatus(**job.snapshot())


@router.get("/sync", response_model=SyncStatus | None)
def active_sync(jobs: JobManager = Depends(get_jobs)) -> Any:
    job = jobs.active()
    return SyncStatus(**job.snapshot()) if job else None


@router.get("/sync/{job_id}", response_model=SyncStatus)
def sync_status(job_id: str, jobs: JobManager = Depends(get_jobs)) -> SyncStatus:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return SyncStatus(**job.snapshot())


@router.get("/sync/{job_id}/stream")
async def sync_stream(job_id: str, jobs: JobManager = Depends(get_jobs)) -> StreamingResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_gen() -> Any:
        cursor = 0
        while True:
            # Snapshot under the manager's lock-free read of the list length.
            events = job.events
            while cursor < len(events):
                yield f"data: {json.dumps(events[cursor])}\n\n"
                cursor += 1
            if job.status != "running":
                yield f"event: end\ndata: {json.dumps(job.snapshot())}\n\n"
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---- logs ------------------------------------------------------------------
@router.get("/logs", response_model=LogsResponse)
def logs(
    lines: int = Query(200, ge=1, le=5000), cfg: Config = Depends(get_config)
) -> LogsResponse:
    return LogsResponse(lines=read_recent_logs(cfg.logging.log_path, lines))


# ---- config ----------------------------------------------------------------
@router.get("/config", response_model=ConfigModel)
def get_config_endpoint(cfg: Config = Depends(get_config)) -> ConfigModel:
    return ConfigModel(**cfg.to_dict())


@router.put("/config", response_model=ConfigModel)
def put_config(new: ConfigModel, request: Request) -> ConfigModel:
    try:
        cfg = Config.from_dict(new.model_dump())  # also enforces loopback invariant
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    path = request.app.state.config_path
    write_config(cfg, path)
    cfg.source_path = str(path)
    request.app.state.config = cfg
    return ConfigModel(**cfg.to_dict())


# ---- helpers ---------------------------------------------------------------
def _download(body: str, filename: str, fmt: str) -> Response:
    return Response(
        content=body,
        media_type=_MEDIA.get(fmt, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

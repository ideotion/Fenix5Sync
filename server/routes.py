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
from core.logging_setup import read_recent_logs
from core.search import ActivityFilter
from core.store import Store
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


@router.get("/insights")
def insights(
    sport: str | None = Query(None, description="Scope all figures to one sport."),
    store: Store = Depends(get_store),
) -> dict:
    """Aggregate analytics for the Insights view (totals, trends, PRs, calendar)."""
    return store.insights(sport)


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

# SPDX-License-Identifier: GPL-3.0-or-later
"""JSON API routes, mounted under ``/api``.

Each request opens a short-lived :class:`~core.store.Store` (SQLite is cheap to
open locally and this keeps connections within a single thread). Config and the
import :class:`~server.progress.JobManager` live on ``app.state``.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from core import __version__
from core.anonymize import anonymize_activity, effective_options
from core.athlete import suggest_athlete
from core.best_efforts import compute_best_efforts
from core.config import Config, write_config
from core.consolidate import find_duplicate_groups
from core.records import compute_personal_records
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
from core.pipeline import import_activities
from core.race import compute_race_predictions
from core.privacy_audit import compute_privacy_audit
from core.recap import compute_recap
from core.salvage import salvage_fit_file
from core.search import ActivityFilter
from core.segments import compute_segment_efforts, segment_from_activity
from core.splits import MILE_M, compute_splits
from core.store import Store
from core.training_load import compute_training_load
from core.zones import compute_zones
from .progress import JobManager
from core.coach_state import compute_coach_state
from core.plan_builder import Objective, agenda_to_ics, build_plan
from .schemas import (
    ActivityDetail,
    ActivityList,
    CoachPlanRequest,
    ConfigModel,
    ExportImportRequest,
    Health,
    LogsResponse,
    SalvageRequest,
    SegmentCreate,
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


@router.get("/insights/duplicates")
def insights_duplicates(store: Store = Depends(get_store)) -> dict:
    """Likely cross-source duplicate activities (same effort, different file).

    A read-only report grouped by start time / duration / distance / GPS; nothing
    is modified or deleted. Catches what content-hash dedupe can't (e.g. the same
    run as a watch ``.FIT`` and a Strava ``.GPX``).
    """
    return find_duplicate_groups(store.all_activities(with_series=False))


@router.get("/insights/records")
def insights_records(
    sport: str = Query("running", description="Sport to compute distance PRs for."),
    store: Store = Depends(get_store),
) -> dict:
    """All-time best times per distance (fastest-ever 1K/5K/10K…), with the source.

    Loads trackpoint series for the chosen sport's activities (an N+1, pruned to
    that sport and to activities with a distance signal) to find in-run best
    windows; computed locally and read-only.
    """
    ids = [
        a.id for a in store.all_activities(with_series=False)
        if a.id is not None and a.sport == sport and a.total_distance
    ]
    full = [store.get_activity(i, with_series=True) for i in ids]
    return compute_personal_records([a for a in full if a is not None])


@router.get("/insights/recap")
def insights_recap(
    year: int | None = Query(None, description="Calendar year; omit for an all-time recap."),
    store: Store = Depends(get_store),
) -> dict:
    """Private Year-in-Sport recap, computed from activity summaries (no cloud).

    Aggregates totals, per-sport and per-period breakdowns, headline highlights
    and consistency metrics over the local archive -- a free, ownable equivalent
    of the annual recaps the major platforms now put behind a subscription. The
    GUI renders a self-contained, shareable card; nothing leaves the machine.
    """
    return compute_recap(store.all_activities(with_series=False), year=year)


# ---- personal segments -----------------------------------------------------
@router.get("/segments")
def list_segments(store: Store = Depends(get_store)) -> dict:
    """All saved personal segments (private; no leaderboards, no cloud)."""
    return {"segments": [s.as_dict() for s in store.list_segments()]}


@router.post("/segments", status_code=201)
def create_segment(body: SegmentCreate, store: Store = Depends(get_store)) -> dict:
    """Create a segment from a reference activity's GPS track."""
    activity = store.get_activity(body.activity_id, with_series=True)
    if activity is None:
        raise HTTPException(status_code=404, detail="activity not found")
    try:
        segment = segment_from_activity(
            activity, body.name, num_waypoints=body.num_waypoints, radius_m=body.radius_m
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.add_segment(segment)
    return segment.as_dict()


@router.delete("/segments/{segment_id}", status_code=204)
def delete_segment(segment_id: int, store: Store = Depends(get_store)) -> Response:
    if not store.delete_segment(segment_id):
        raise HTTPException(status_code=404, detail="segment not found")
    return Response(status_code=204)


@router.get("/segments/{segment_id}/efforts")
def segment_efforts(segment_id: int, store: Store = Depends(get_store)) -> dict:
    """Every matching effort on a segment: a private leaderboard plus a trend.

    Loads trackpoint series for activities of the segment's sport (an N+1, pruned
    to that sport with a GPS signal) to match the route; computed locally.
    """
    segment = store.get_segment(segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="segment not found")
    candidates = [
        a for a in store.all_activities(with_series=False)
        if a.id is not None and (segment.sport is None or a.sport == segment.sport)
        and a.start_latitude is not None
    ]
    full = [store.get_activity(a.id, with_series=True) for a in candidates]
    return compute_segment_efforts([a for a in full if a is not None], segment)


@router.get("/insights/privacy-audit")
def insights_privacy_audit(
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> dict:
    """Defensive self-audit: what your own activity start points reveal.

    Clusters start locations (likely home first) and the weekday/time regularity
    that exposes a routine, then recommends a privacy radius that feeds the
    existing anonymization. Computed locally from summaries; inferences are
    probabilistic and never persisted. Includes the currently configured radius
    so the UI can show whether it already covers the most-exposed place.
    """
    audit = compute_privacy_audit(store.all_activities(with_series=False))
    audit["current_radius_m"] = cfg.anonymize.privacy_radius_m
    audit["radius_sufficient"] = (
        cfg.anonymize.privacy_radius_m >= audit["recommended_radius_m"]
        and audit["recommended_radius_m"] > 0
    )
    return audit


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


# ---- local filesystem picker (loopback-only; powers the GUI "Browse" button) -
def _fs_quick_locations() -> list[dict]:
    home = Path.home()
    out = [{"name": "Home", "path": str(home)}]
    for sub in ("Downloads", "Documents", "Desktop"):
        p = home / sub
        if p.is_dir():
            out.append({"name": sub, "path": str(p)})
    out.append({"name": "Filesystem root", "path": str(Path(home.anchor or "/"))})
    return out


@router.get("/fs/list")
def fs_list(
    path: str | None = Query(None, description="Directory to list; defaults to home."),
    dirs_only: bool = Query(False, description="List only directories (folder picker)."),
    exts: str | None = Query(None, description="Comma-separated file extensions to include."),
) -> dict:
    """List a local directory for the GUI file/folder picker.

    Read-only and loopback-only (same trust boundary as the rest of the local
    app): it never writes, and lets the GUI offer a "Browse" button so users
    never have to type a path. Defaults to the home directory; hidden entries are
    omitted; unreadable entries are skipped rather than failing the listing.
    """
    home = Path.home()
    base = Path(path).expanduser() if path else home
    try:
        base = base.resolve()
    except OSError:
        base = home
    if not base.is_dir():
        base = base.parent if base.parent.is_dir() else home

    ext_set = {
        (e if e.startswith(".") else "." + e).lower()
        for e in (exts.split(",") if exts else []) if e.strip()
    }

    entries: list[dict] = []
    error: str | None = None
    try:
        children = sorted(base.iterdir(), key=lambda p: (not _safe_is_dir(p), p.name.lower()))
    except (PermissionError, OSError) as exc:
        children, error = [], str(exc)
    for child in children:
        if child.name.startswith("."):
            continue
        is_dir = _safe_is_dir(child)
        if not is_dir:
            if dirs_only:
                continue
            if ext_set and child.suffix.lower() not in ext_set:
                continue
        entries.append({"name": child.name, "path": str(child), "is_dir": is_dir})
        if len(entries) >= 2000:
            break

    parent = str(base.parent) if base.parent != base else None
    return {
        "path": str(base),
        "parent": parent,
        "name": base.name or str(base),
        "entries": entries,
        "quick": _fs_quick_locations(),
        "error": error,
    }


def _safe_is_dir(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False


@router.post("/sync/import-export", response_model=SyncStatus)
def start_export_import(
    body: ExportImportRequest,
    cfg: Config = Depends(get_config),
    jobs: JobManager = Depends(get_jobs),
) -> SyncStatus:
    """Liberate your history: import a Garmin/Strava account export from disk.

    Runs the normal import pipeline with a one-off ``export``-mode config over the
    given local path (the downloaded ``.zip`` or an unzipped folder). Nested zips
    and gzip-compressed activity files are expanded into a temp dir; the source is
    never modified, and everything is content-deduplicated against what you have.
    """
    import copy

    path = Path(body.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"path not found: {path}")
    one_off = copy.deepcopy(cfg)
    one_off.source.mode = "export"
    one_off.source.path = str(path)
    one_off.source.recursive = True
    job = jobs.start(one_off)
    return SyncStatus(**job.snapshot())


@router.post("/salvage")
def salvage(
    body: SalvageRequest,
    cfg: Config = Depends(get_config),
) -> dict:
    """Recover a corrupt/truncated FIT file, locally and offline.

    Walks the record stream to the last complete record, repairs the header and
    CRC, and re-parses — deriving the summary from records when the session
    trailer was lost. The original is only read, never modified. With
    ``import: true`` the recovered activity is also stored (content-deduplicated).
    """
    import copy

    path = Path(body.path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"file not found: {path}")

    report, activity = salvage_fit_file(path)
    preview = None
    if activity is not None:
        preview = {
            "sport": activity.sport,
            "start_time": activity.start_time.isoformat() if activity.start_time else None,
            "trackpoints": len(activity.trackpoints),
            "laps": len(activity.laps),
        }

    imported = None
    if body.do_import and report.ok and report.repaired is not None and activity is not None:
        tmp = tempfile.NamedTemporaryFile(prefix="fenix5sync-salvaged-", suffix=".fit", delete=False)
        try:
            tmp.write(report.repaired)
            tmp.close()
            one_off = copy.deepcopy(cfg)
            one_off.source.mode = "file"
            one_off.source.path = tmp.name
            imported = import_activities(one_off).as_dict()
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    return {**report.as_dict(), "preview": preview, "imported": imported}


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


# ---- coach: objective -> personalized plan ---------------------------------
_RUN_SPORTS = {"running", "run", "trail_running", "treadmill_running", "track_running"}


def _coach_state(store: Store, cfg: Config):
    """A CoachState from the local running history, or None if there's none yet."""
    runs = [a for a in store.all_activities(with_series=False)
            if (a.sport or "").lower() in _RUN_SPORTS]
    if not runs:
        return None
    return compute_coach_state(runs, cfg.athlete, sport="running")


def _objective_from(body: CoachPlanRequest) -> Objective:
    return Objective(
        goal_distance=body.goal_distance, start_date=body.start_date,
        target_date=body.target_date, weeks=body.weeks, target_time=body.target_time,
        sessions_per_week=body.sessions_per_week,
        available_days=body.available_days or [0, 1, 2, 3, 4, 5, 6], level=body.level,
    )


@router.post("/coach/plan")
def coach_plan(
    body: CoachPlanRequest,
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> dict:
    """Build a dated, personalized training plan from an objective."""
    try:
        agenda = build_plan(_objective_from(body), state=_coach_state(store, cfg), athlete=cfg.athlete)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return agenda.as_dict()


@router.get("/coach/plan.ics")
def coach_plan_ics(
    goal_distance: str = Query("general", pattern="^(5k|10k|half|marathon|general)$"),
    start_date: str | None = Query(None),
    target_date: str | None = Query(None),
    weeks: int | None = Query(None, ge=1, le=52),
    target_time: str | None = Query(None),
    sessions_per_week: int | None = Query(None, ge=1, le=7),
    available_days: str | None = Query(None, description="comma-separated weekday numbers, Mon=0"),
    level: str = Query("intermediate", pattern="^(beginner|intermediate|advanced)$"),
    store: Store = Depends(get_store),
    cfg: Config = Depends(get_config),
) -> Response:
    """Download the plan as an .ics calendar (one all-day event per session)."""
    days = ([int(x) for x in available_days.split(",") if x.strip().isdigit()]
            if available_days else [0, 1, 2, 3, 4, 5, 6])
    obj = Objective(
        goal_distance=goal_distance, start_date=start_date, target_date=target_date,
        weeks=weeks, target_time=target_time, sessions_per_week=sessions_per_week,
        available_days=days or [0, 1, 2, 3, 4, 5, 6], level=level,
    )
    try:
        agenda = build_plan(obj, state=_coach_state(store, cfg), athlete=cfg.athlete)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=agenda_to_ics(agenda), media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="coach-plan.ics"'},
    )


# ---- helpers ---------------------------------------------------------------
def _download(body: str, filename: str, fmt: str) -> Response:
    return Response(
        content=body,
        media_type=_MEDIA.get(fmt, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

"""Fenix5Sync core library.

A pure-Python toolkit to acquire, deduplicate, parse, store, search and export
Garmin Fenix 5 activity data. It has no dependency on the web API or the CLI and
can be used directly::

    from core import load_config, Store, import_activities

    cfg = load_config()
    summary = import_activities(cfg)
    with Store(cfg.storage.db_path) as store:
        activities = store.search(ActivityFilter(sport="running"))
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

from .anonymize import anonymize_activity, effective_options
from .config import (
    AnonymizeConfig,
    AthleteConfig,
    Config,
    find_config_path,
    load_config,
    write_config,
)
from .dedupe import sha256_bytes, sha256_file
from .export import (
    ExportError,
    activities_json,
    activities_ndjson,
    activities_summary_csv,
    activity_gpx,
    activity_json,
    activity_tcx,
    activity_to_dict,
    activity_trackpoints_csv,
    gpx_available,
    write_activity_export,
    write_archive,
    write_bulk_export,
)
from .importers import detect_format, parse_activity_file
from .logging_setup import get_logger, read_recent_logs, setup_logging
from .metrics import ActivityMetrics, compute_activity_metrics
from .models import Activity, Lap, RunSummary, Trackpoint
from .parse import ParseError, parse_fit_file
from .pipeline import import_activities, open_store
from .search import ActivityFilter, build_where
from .splits import Split, compute_splits
from .store import Store
from .training_load import DayLoad, TrainingLoad, compute_training_load
from .zones import ZoneBin, compute_zones, hr_zones, power_zones

# Single source of truth for the version is pyproject.toml; we read the installed
# distribution metadata so it never drifts. Falls back when running from a raw
# (uninstalled) source tree.
try:
    __version__ = _pkg_version("fenix5sync")
except PackageNotFoundError:  # pragma: no cover - only when not pip-installed
    __version__ = "0.0.0+local"

__all__ = [
    "__version__",
    # config
    "Config",
    "AnonymizeConfig",
    "AthleteConfig",
    "load_config",
    "find_config_path",
    "write_config",
    # models
    "Activity",
    "Lap",
    "Trackpoint",
    "RunSummary",
    # dedupe
    "sha256_file",
    "sha256_bytes",
    # parse / importers
    "parse_fit_file",
    "parse_activity_file",
    "detect_format",
    "ParseError",
    # store / search
    "Store",
    "ActivityFilter",
    "build_where",
    # pipeline
    "import_activities",
    "open_store",
    # export
    "activity_to_dict",
    "activity_json",
    "activities_json",
    "activities_ndjson",
    "activity_trackpoints_csv",
    "activities_summary_csv",
    "activity_gpx",
    "activity_tcx",
    "gpx_available",
    "write_activity_export",
    "write_bulk_export",
    "write_archive",
    "ExportError",
    # anonymize
    "anonymize_activity",
    "effective_options",
    # zones
    "compute_zones",
    "hr_zones",
    "power_zones",
    "ZoneBin",
    # training load
    "compute_training_load",
    "TrainingLoad",
    "DayLoad",
    # metrics
    "compute_activity_metrics",
    "ActivityMetrics",
    # splits
    "compute_splits",
    "Split",
    # logging
    "setup_logging",
    "get_logger",
    "read_recent_logs",
]

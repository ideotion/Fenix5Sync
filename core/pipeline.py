# SPDX-License-Identifier: GPL-3.0-or-later
"""Import pipeline: acquire -> dedupe -> parse -> store.

Orchestrates the core modules into a single idempotent run and returns a
:class:`RunSummary` (found / imported / skipped / failed). The run is resilient:
one corrupt file is logged and counted as failed without aborting the batch. An
optional ``on_progress`` callback receives structured events so the API can show
live progress.
"""

from __future__ import annotations

import datetime as _dt
from typing import Callable

from . import acquire
from .config import Config
from .dedupe import sha256_file
from .importers import parse_activity_file
from .logging_setup import get_logger, setup_logging
from .models import RunSummary
from .parse import ParseError
from .store import Store

# Progress events are simple dicts so they serialise straight to JSON/SSE.
ProgressCallback = Callable[[dict], None]


def open_store(cfg: Config) -> Store:
    """Open (creating if needed) the SQLite store described by ``cfg``."""
    return Store(cfg.storage.db_path)


def ensure_logging(cfg: Config):
    """Configure logging from config (idempotent) and return the logger."""
    return setup_logging(cfg.logging.log_path, cfg.logging.level)


def _emit(cb: ProgressCallback | None, **event) -> None:
    if cb is not None:
        try:
            cb(event)
        except Exception:  # a broken progress sink must not break the import
            pass


def _try_wellness(path) -> list[dict]:
    """Best-effort: parse a non-activity FIT as a monitoring/wellness file.

    Returns daily wellness summaries, or an empty list if it isn't one. Never
    raises — a monitoring miss simply falls back to the normal failed path.
    """
    try:
        from .wellness import parse_wellness_file

        return parse_wellness_file(path).get("days", [])
    except Exception:
        return []


def import_activities(
    cfg: Config,
    store: Store | None = None,
    on_progress: ProgressCallback | None = None,
) -> RunSummary:
    """Run a full import according to ``cfg``.

    Args:
        cfg: configuration controlling source, storage and dedupe.
        store: an open :class:`Store` to reuse; one is opened from ``cfg`` if not
            supplied (and closed before returning).
        on_progress: optional callback receiving progress event dicts.

    Returns:
        A :class:`RunSummary` with counts and any error messages.
    """
    ensure_logging(cfg)
    logger = get_logger()
    summary = RunSummary(started_at=_dt.datetime.now(_dt.timezone.utc))

    owns_store = store is None
    store = store or open_store(cfg)

    try:
        _emit(on_progress, phase="locating")
        logger.info("Locating device/source (mode=%s)...", cfg.source.mode)
        source = acquire.locate_source(cfg)
        if source is None:
            msg = (
                "No Garmin device or activity directory found. Connect the watch "
                "(unlock it / allow file access) or set source.path in the config."
            )
            logger.warning(msg)
            summary.messages.append(msg)
            summary.finished_at = _dt.datetime.now(_dt.timezone.utc)
            _emit(on_progress, phase="done", summary=summary.as_dict())
            return summary

        logger.info("Using source: %s", source.description)
        summary.messages.append(f"Source: {source.description}")
        try:
            files = acquire.source_files(source, cfg)
            summary.found = len(files)
            logger.info("Found %d activity file(s)", summary.found)
            _emit(on_progress, phase="scanning", total=summary.found)

            raw_dir = cfg.storage.raw_dir
            for index, src in enumerate(files, start=1):
                _emit(
                    on_progress, phase="file", current=index,
                    total=summary.found, filename=src.name,
                )
                try:
                    file_hash = sha256_file(src)
                except OSError as exc:
                    summary.failed += 1
                    err = f"{src.name}: could not read source ({exc})"
                    logger.error(err)
                    summary.errors.append(err)
                    _emit(on_progress, phase="file_done", current=index,
                          total=summary.found, filename=src.name, status="failed")
                    continue

                if cfg.dedupe.enabled and store.is_imported(file_hash):
                    summary.skipped += 1
                    logger.info("Skip (already imported): %s", src.name)
                    _emit(on_progress, phase="file_done", current=index,
                          total=summary.found, filename=src.name, status="skipped")
                    continue

                # Copy off the device into the local raw store (source read-only).
                raw_path = acquire.copy_to_raw(src, raw_dir, file_hash, src.suffix)

                try:
                    activity = parse_activity_file(raw_path, file_hash, str(raw_path))
                except ParseError as exc:
                    # Not a parseable activity? It may be a Garmin monitoring
                    # (wellness) file — route it there before counting it failed.
                    wdays = _try_wellness(raw_path)
                    if wdays:
                        added = store.add_wellness_days(wdays)
                        summary.wellness += added
                        logger.info("Imported wellness: %s (%d day[s])", src.name, added)
                        store.record_ledger(file_hash, src.name, "wellness", detail=f"{added} day(s)")
                        _emit(on_progress, phase="file_done", current=index,
                              total=summary.found, filename=src.name, status="wellness")
                        continue
                    summary.failed += 1
                    logger.error("Parse failed: %s", exc)
                    summary.errors.append(str(exc))
                    store.record_ledger(
                        file_hash, src.name, "failed", detail=str(exc)
                    )
                    _emit(on_progress, phase="file_done", current=index,
                          total=summary.found, filename=src.name, status="failed")
                    continue

                activity_id = store.add_activity(activity)
                summary.imported += 1
                summary.imported_ids.append(activity_id)
                logger.info(
                    "Imported %s -> activity #%d (%s)",
                    src.name, activity_id, activity.sport or "unknown",
                )
                _emit(on_progress, phase="file_done", current=index,
                      total=summary.found, filename=src.name, status="imported")
        finally:
            source.cleanup()
    finally:
        if owns_store:
            store.close()

    summary.finished_at = _dt.datetime.now(_dt.timezone.utc)
    logger.info(
        "Import complete: found=%d imported=%d skipped=%d failed=%d",
        summary.found, summary.imported, summary.skipped, summary.failed,
    )
    _emit(on_progress, phase="done", summary=summary.as_dict())
    return summary

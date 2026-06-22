# SPDX-License-Identifier: GPL-3.0-or-later
"""Structured logging: a dated log file plus console output.

The same run log is surfaced in the GUI via :func:`read_recent_logs`. Setup is
idempotent so repeated calls (CLI then server, say) don't duplicate handlers.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

LOGGER_NAME = "fenix5sync"
_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def log_file_for(log_dir: Path, on: date | None = None) -> Path:
    """Path of the dated log file for a given day (today by default)."""
    on = on or date.today()
    return log_dir / f"fenix5sync-{on.isoformat()}.log"


def setup_logging(
    log_dir: str | Path,
    level: str = "INFO",
    console: bool = True,
) -> logging.Logger:
    """Configure and return the package logger.

    Writes to ``<log_dir>/fenix5sync-YYYY-MM-DD.log`` and (optionally) stderr.
    Safe to call multiple times.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    target_file = log_file_for(log_dir)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Avoid duplicate handlers for the same destination on repeat calls.
    existing_files = {
        getattr(h, "baseFilename", None) for h in logger.handlers
    }
    if str(target_file.resolve()) not in existing_files:
        fh = logging.FileHandler(target_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    if console and not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    ):
        ch = logging.StreamHandler(stream=sys.stderr)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


def get_logger() -> logging.Logger:
    """Return the package logger (configure with :func:`setup_logging` first)."""
    return logging.getLogger(LOGGER_NAME)


def read_recent_logs(log_dir: str | Path, lines: int = 200) -> list[str]:
    """Return the last ``lines`` lines of today's log file (most recent last).

    Returns an empty list if today's log does not exist yet.
    """
    path = log_file_for(Path(log_dir))
    if not path.is_file():
        return []
    # Files are small (per-day); reading fully then slicing is fine and simple.
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        content = fh.read().splitlines()
    return content[-lines:]

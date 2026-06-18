"""FastAPI application factory.

Builds an app that exposes the core over JSON (under ``/api``), serves the
vendored static frontend from ``web/`` and offers auto-docs at ``/docs``. The
server is intended to bind to loopback only (enforced in config and by the CLI).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core import __version__
from core.config import Config, find_config_path, load_config
from core.logging_setup import setup_logging
from .progress import JobManager
from .routes import router

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
DEFAULT_CONFIG_PATH = "~/.config/fenix5sync/config.yaml"


def _resolve_config_path(config_path: str | None, cfg: Config) -> Path:
    """Where config writes (PUT /api/config) should go."""
    if config_path:
        return Path(config_path).expanduser()
    if cfg.source_path:
        return Path(cfg.source_path)
    return Path(DEFAULT_CONFIG_PATH).expanduser()


def _ensure_dirs(cfg: Config) -> None:
    for path in (
        cfg.storage.db_path.parent,
        cfg.storage.raw_dir,
        cfg.export.output_path,
        cfg.logging.log_path,
    ):
        path.mkdir(parents=True, exist_ok=True)


def create_app(config_path: str | None = None) -> FastAPI:
    """Create the FastAPI app, loading config from ``config_path`` (or defaults)."""
    cfg = load_config(config_path)
    if config_path is None and find_config_path() is None:
        # Running on pure defaults; remember where a future save would land.
        cfg.source_path = None
    _ensure_dirs(cfg)
    setup_logging(cfg.logging.log_path, cfg.logging.level)

    app = FastAPI(
        title="Fenix5Sync",
        version=__version__,
        description="Local-first, offline Garmin Fenix 5 activity browser.",
    )
    app.state.config = cfg
    app.state.config_path = _resolve_config_path(config_path, cfg)
    app.state.jobs = JobManager()

    app.include_router(router)

    # Serve the vendored frontend last so /api and /docs take precedence.
    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app

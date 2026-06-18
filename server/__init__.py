"""Fenix5Sync HTTP server (FastAPI).

Exposes the core library over a JSON API bound to loopback only and serves the
static frontend. Build the app with :func:`server.app.create_app`.
"""

from __future__ import annotations

from .app import create_app

__all__ = ["create_app"]

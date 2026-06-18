"""Thin CLI for development and headless automation.

Commands wrap the core pipeline and the server. Nothing here contains business
logic -- it all lives in :mod:`core` and :mod:`server`.

    fenix5sync sync                 # import from the connected watch
    fenix5sync list --sport running # search the local store
    fenix5sync show 12              # activity summary + laps
    fenix5sync export 12 --format gpx
    fenix5sync serve --open         # launch the local GUI
    fenix5sync init-config          # write a default config file
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import typer

from core import (
    ActivityFilter,
    Config,
    Store,
    import_activities,
    load_config,
    write_config,
)
from core.config import _expand
from core.export import write_activity_export, write_archive, write_bulk_export

app = typer.Typer(
    add_completion=False,
    help="Local-first, offline Garmin Fenix 5 activity tool.",
    no_args_is_help=True,
)

DEFAULT_CONFIG_PATH = "~/.config/fenix5sync/config.yaml"


@app.callback()
def _main(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", envvar="FENIX5SYNC_CONFIG",
        help="Path to the YAML config file (defaults to the usual locations).",
    ),
) -> None:
    ctx.obj = {"config_path": str(config) if config else None}


def _cfg(ctx: typer.Context) -> Config:
    return load_config(ctx.obj["config_path"])


def _fmt_dur(seconds: float | None) -> str:
    if not seconds:
        return "-"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def _fmt_km(metres: float | None) -> str:
    return f"{metres / 1000:.2f} km" if metres else "-"


# --------------------------------------------------------------------------- #
@app.command()
def sync(ctx: typer.Context) -> None:
    """Acquire, dedupe, parse and store new activities from the device."""
    cfg = _cfg(ctx)
    typer.echo("Starting import...")
    summary = import_activities(cfg)
    typer.echo(
        f"\nDone: found={summary.found} imported={summary.imported} "
        f"skipped={summary.skipped} failed={summary.failed}"
    )
    for msg in summary.messages:
        typer.echo(f"  - {msg}")
    for err in summary.errors:
        typer.secho(f"  ! {err}", fg=typer.colors.RED)
    if summary.imported == 0 and summary.found == 0:
        typer.secho(
            "No files found. Connect/unlock the watch or set source.path.",
            fg=typer.colors.YELLOW,
        )


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    sport: Optional[str] = typer.Option(None),
    date_from: Optional[str] = typer.Option(None, "--from"),
    date_to: Optional[str] = typer.Option(None, "--to"),
    min_distance: Optional[float] = typer.Option(None, help="metres"),
    max_distance: Optional[float] = typer.Option(None, help="metres"),
    limit: int = typer.Option(50),
) -> None:
    """List/search activities in the local store."""
    cfg = _cfg(ctx)
    with Store(cfg.storage.db_path) as store:
        rows = store.search(ActivityFilter(
            sport=sport, date_from=date_from, date_to=date_to,
            min_distance=min_distance, max_distance=max_distance, limit=limit,
        ))
        if not rows:
            typer.echo("No matching activities.")
            return
        typer.echo(f"{'ID':>4}  {'Date':<19}  {'Sport':<10}  {'Distance':>9}  {'Time':>8}  HR")
        typer.echo("-" * 64)
        for a in rows:
            when = a.start_time.strftime("%Y-%m-%d %H:%M") if a.start_time else "-"
            typer.echo(
                f"{a.id:>4}  {when:<19}  {(a.sport or '-'):<10}  "
                f"{_fmt_km(a.total_distance):>9}  {_fmt_dur(a.total_timer_time):>8}  "
                f"{a.avg_heart_rate or '-'}"
            )


@app.command()
def show(ctx: typer.Context, activity_id: int) -> None:
    """Show an activity's summary and laps."""
    cfg = _cfg(ctx)
    with Store(cfg.storage.db_path) as store:
        a = store.get_activity(activity_id, with_series=True)
        if a is None:
            typer.secho(f"Activity {activity_id} not found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        typer.echo(f"Activity #{a.id}: {a.sport or '-'} / {a.sub_sport or '-'}")
        typer.echo(f"  Start     : {a.start_time}")
        typer.echo(f"  Distance  : {_fmt_km(a.total_distance)}")
        typer.echo(f"  Time      : {_fmt_dur(a.total_timer_time)}")
        typer.echo(f"  HR avg/max: {a.avg_heart_rate or '-'} / {a.max_heart_rate or '-'}")
        typer.echo(f"  Ascent    : {a.total_ascent or '-'} m")
        typer.echo(f"  Device    : {a.device_manufacturer or '-'} {a.device_product or ''}")
        typer.echo(f"  Trackpoints: {len(a.trackpoints)}   Laps: {len(a.laps)}")


@app.command()
def export(
    ctx: typer.Context,
    activity_id: Optional[int] = typer.Argument(None, help="Activity id; omit for bulk."),
    fmt: str = typer.Option("json", "--format", "-f", help="csv | json | gpx"),
    bulk: bool = typer.Option(False, help="Export a summary of all activities."),
    out: Optional[Path] = typer.Option(None, help="Output dir (defaults to config)."),
) -> None:
    """Export one activity (csv/json/gpx) or a bulk summary (csv/json)."""
    cfg = _cfg(ctx)
    out_dir = str(out) if out else cfg.export.output_dir
    with Store(cfg.storage.db_path) as store:
        if bulk or activity_id is None:
            activities = store.all_activities(with_series=False)
            path = write_bulk_export(activities, fmt, out_dir)
        else:
            a = store.get_activity(activity_id, with_series=True)
            if a is None:
                typer.secho(f"Activity {activity_id} not found.", fg=typer.colors.RED)
                raise typer.Exit(1)
            path = write_activity_export(a, fmt, out_dir, cfg.export.gpsbabel_bin)
    typer.secho(f"Wrote {path}", fg=typer.colors.GREEN)


@app.command()
def archive(
    ctx: typer.Context,
    out: Optional[Path] = typer.Option(None, help="Output dir (defaults to config export dir)."),
) -> None:
    """Write a full-fidelity NDJSON archive of all activities for long-term keeping.

    Complements the raw .FIT store and the SQLite DB: one complete activity per
    line (laps + full time series + all preserved FIT fields), ready for future
    analysis. The raw .FIT files remain the canonical, lossless source.
    """
    cfg = _cfg(ctx)
    out_dir = str(out) if out else cfg.export.output_dir
    with Store(cfg.storage.db_path) as store:
        activities = store.all_activities(with_series=True)
        path = write_archive(activities, out_dir)
    typer.secho(f"Archived {len(activities)} activit{'y' if len(activities)==1 else 'ies'} -> {path}", fg=typer.colors.GREEN)


@app.command()
def serve(
    ctx: typer.Context,
    host: Optional[str] = typer.Option(None, help="Override config host (loopback only)."),
    port: Optional[int] = typer.Option(None, help="Override config port."),
    open_browser: bool = typer.Option(False, "--open", help="Open the GUI in a browser."),
) -> None:
    """Run the local web GUI/API server."""
    import uvicorn

    from server.app import create_app

    cfg = _cfg(ctx)
    host = host or cfg.server.host
    port = port or cfg.server.port
    application = create_app(ctx.obj["config_path"])
    url = f"http://{host}:{port}/"

    if open_browser or cfg.server.open_browser:
        threading.Thread(
            target=_open_when_ready, args=(host, port, url), daemon=True
        ).start()

    typer.secho(f"Serving Fenix5Sync at {url} (Ctrl-C to stop)", fg=typer.colors.GREEN)
    uvicorn.run(application, host=host, port=port, log_level=cfg.logging.level.lower())


@app.command("init-config")
def init_config(
    path: Path = typer.Option(Path(_expand(DEFAULT_CONFIG_PATH)), help="Where to write."),
    force: bool = typer.Option(False, help="Overwrite an existing config."),
) -> None:
    """Write a default config file (does not overwrite unless --force)."""
    if path.exists() and not force:
        typer.secho(f"Config already exists at {path} (use --force).", fg=typer.colors.YELLOW)
        raise typer.Exit(0)
    written = write_config(Config(), path)
    typer.secho(f"Wrote default config to {written}", fg=typer.colors.GREEN)


def _open_when_ready(host: str, port: int, url: str, timeout: float = 20.0) -> None:
    """Wait for the server socket to accept, then open the default browser."""
    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((connect_host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    else:
        return
    if shutil.which("xdg-open"):
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    app()

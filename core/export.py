"""Export activities to CSV, JSON, GPX, TCX and the original raw file.

Design notes:
  * CSV/JSON are produced with the standard library.
  * GPX: the spec names ``gpsbabel`` as the mechanism. When a gpsbabel binary is
    available we convert the *raw* ``.FIT`` directly (authoritative, and possible
    because we keep raw files). When it is absent we fall back to a small,
    dependency-free GPX writer built from the parsed trackpoints, so GPX export
    still works fully offline. No third-party dependency is added either way.
  * TCX is built from the canonical model with the standard library. It's the
    format Garmin Connect ingests natively (and Strava/others accept it too), so
    it's the "upload to another app" companion to the universal GPX.
  * raw: the original ``.FIT``/``.TCX``/``.GPX`` is served byte-for-byte from the
    content-addressed store -- the most faithful, Garmin-native re-upload.
All functions are pure/string-returning where possible so the API can stream
them without touching disk; thin ``write_*`` helpers persist to a directory.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence
from xml.sax.saxutils import escape

from .models import Activity, Lap, Trackpoint


class ExportError(Exception):
    """Raised when an export cannot be produced."""


# --------------------------------------------------------------------------- #
# Serialisation to dicts
# --------------------------------------------------------------------------- #
def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def lap_to_dict(lap: Lap) -> dict[str, Any]:
    return {
        "lap_index": lap.lap_index,
        "start_time": _iso(lap.start_time),
        "total_timer_time_s": lap.total_timer_time,
        "total_elapsed_time_s": lap.total_elapsed_time,
        "total_distance_m": lap.total_distance,
        "avg_heart_rate_bpm": lap.avg_heart_rate,
        "max_heart_rate_bpm": lap.max_heart_rate,
        "avg_speed_mps": lap.avg_speed,
        "max_speed_mps": lap.max_speed,
        "total_ascent_m": lap.total_ascent,
        "total_descent_m": lap.total_descent,
        "total_calories": lap.total_calories,
        "extra": lap.extra,
    }


def trackpoint_to_dict(tp: Trackpoint) -> dict[str, Any]:
    return {
        "timestamp": _iso(tp.timestamp),
        "latitude_deg": tp.latitude,
        "longitude_deg": tp.longitude,
        "heart_rate_bpm": tp.heart_rate,
        "cadence_rpm": tp.cadence,
        "speed_mps": tp.speed,
        "altitude_m": tp.altitude,
        "distance_m": tp.distance,
        "temperature_c": tp.temperature,
        "power_w": tp.power,
        "extra": tp.extra,
    }


def activity_to_dict(activity: Activity, include_series: bool = True) -> dict[str, Any]:
    """Serialise an activity to a JSON-able dict (units encoded in key names)."""
    data: dict[str, Any] = {
        "id": activity.id,
        "file_hash": activity.file_hash,
        "raw_path": activity.raw_path,
        "sport": activity.sport,
        "sub_sport": activity.sub_sport,
        "start_time": _iso(activity.start_time),
        "total_timer_time_s": activity.total_timer_time,
        "total_elapsed_time_s": activity.total_elapsed_time,
        "total_distance_m": activity.total_distance,
        "total_calories": activity.total_calories,
        "avg_heart_rate_bpm": activity.avg_heart_rate,
        "max_heart_rate_bpm": activity.max_heart_rate,
        "avg_speed_mps": activity.avg_speed,
        "max_speed_mps": activity.max_speed,
        "avg_cadence_rpm": activity.avg_cadence,
        "avg_power_w": activity.avg_power,
        "avg_temperature_c": activity.avg_temperature,
        "total_ascent_m": activity.total_ascent,
        "total_descent_m": activity.total_descent,
        "start_latitude_deg": activity.start_latitude,
        "start_longitude_deg": activity.start_longitude,
        "device_manufacturer": activity.device_manufacturer,
        "device_product": activity.device_product,
        "imported_at": _iso(activity.imported_at),
        "extra": activity.extra,
        "laps": [lap_to_dict(l) for l in activity.laps],
    }
    if include_series:
        data["trackpoints"] = [trackpoint_to_dict(tp) for tp in activity.trackpoints]
    return data


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #
def activity_json(activity: Activity, include_series: bool = True) -> str:
    return json.dumps(activity_to_dict(activity, include_series), indent=2)


def activities_json(activities: Iterable[Activity], include_series: bool = False) -> str:
    return json.dumps(
        [activity_to_dict(a, include_series) for a in activities], indent=2
    )


def activities_ndjson(activities: Iterable[Activity], include_series: bool = True) -> str:
    """Newline-delimited JSON: one complete activity object per line.

    This is the long-term archive format: append/stream friendly, line-oriented
    (so it ingests directly into pandas/DuckDB/jq and converts cleanly to Parquet
    later), and full-fidelity when ``include_series`` is True (laps + trackpoints
    + every preserved FIT field with units).
    """
    lines = [json.dumps(activity_to_dict(a, include_series)) for a in activities]
    return ("\n".join(lines) + "\n") if lines else ""


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
_TRACKPOINT_FIELDS = [
    "timestamp", "latitude_deg", "longitude_deg", "heart_rate_bpm", "cadence_rpm",
    "speed_mps", "altitude_m", "distance_m", "temperature_c", "power_w",
]

_SUMMARY_FIELDS = [
    "id", "start_time", "sport", "sub_sport", "total_distance_m",
    "total_timer_time_s", "total_elapsed_time_s", "total_calories",
    "avg_heart_rate_bpm", "max_heart_rate_bpm", "avg_speed_mps", "max_speed_mps",
    "avg_cadence_rpm", "avg_power_w", "avg_temperature_c", "total_ascent_m",
    "total_descent_m", "device_manufacturer", "device_product", "file_hash",
]


def activity_trackpoints_csv(activity: Activity) -> str:
    """Per-activity CSV: one row per trackpoint (the time series)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_TRACKPOINT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for tp in activity.trackpoints:
        writer.writerow({k: trackpoint_to_dict(tp).get(k) for k in _TRACKPOINT_FIELDS})
    return buf.getvalue()


def activities_summary_csv(activities: Sequence[Activity]) -> str:
    """Bulk CSV: one row per activity (summary columns)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_SUMMARY_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for a in activities:
        d = activity_to_dict(a, include_series=False)
        writer.writerow({k: d.get(k) for k in _SUMMARY_FIELDS})
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# GPX
# --------------------------------------------------------------------------- #
def gpx_available(gpsbabel_bin: str = "gpsbabel") -> bool:
    """True if a usable gpsbabel binary is on PATH (or at the given path)."""
    return shutil.which(gpsbabel_bin) is not None or Path(gpsbabel_bin).is_file()


def _builtin_gpx(activity: Activity) -> str:
    """Minimal but valid GPX 1.1 built from parsed trackpoints (offline fallback)."""
    pts = [
        tp for tp in activity.trackpoints
        if tp.latitude is not None and tp.longitude is not None
    ]
    name = escape(f"{activity.sport or 'activity'} {activity.start_time or ''}".strip())
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="Fenix5Sync" '
        'xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">',
        f"  <trk><name>{name}</name><trkseg>",
    ]
    for tp in pts:
        lines.append(f'    <trkpt lat="{tp.latitude:.7f}" lon="{tp.longitude:.7f}">')
        if tp.altitude is not None:
            lines.append(f"      <ele>{tp.altitude:.2f}</ele>")
        if tp.timestamp is not None:
            lines.append(f"      <time>{_iso(tp.timestamp)}</time>")
        if tp.heart_rate is not None or tp.cadence is not None or tp.temperature is not None:
            ext = ["      <extensions><gpxtpx:TrackPointExtension>"]
            if tp.temperature is not None:
                ext.append(f"<gpxtpx:atemp>{tp.temperature}</gpxtpx:atemp>")
            if tp.heart_rate is not None:
                ext.append(f"<gpxtpx:hr>{tp.heart_rate}</gpxtpx:hr>")
            if tp.cadence is not None:
                ext.append(f"<gpxtpx:cad>{tp.cadence}</gpxtpx:cad>")
            ext.append("</gpxtpx:TrackPointExtension></extensions>")
            lines.append("".join(ext))
        lines.append("    </trkpt>")
    lines.append("  </trkseg></trk>")
    lines.append("</gpx>")
    return "\n".join(lines) + "\n"


def _gpsbabel_gpx(raw_fit_path: str | Path, gpsbabel_bin: str = "gpsbabel") -> str:
    """Convert a raw .FIT to GPX with gpsbabel. Raises ExportError on failure."""
    raw_fit_path = Path(raw_fit_path)
    if not raw_fit_path.is_file():
        raise ExportError(f"raw FIT not found for gpsbabel conversion: {raw_fit_path}")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.gpx"
        cmd = [
            gpsbabel_bin, "-t", "-i", "garmin_fit", "-f", str(raw_fit_path),
            "-o", "gpx", "-F", str(out),
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExportError(f"gpsbabel invocation failed: {exc}") from exc
        if proc.returncode != 0 or not out.is_file():
            raise ExportError(
                f"gpsbabel failed (rc={proc.returncode}): {proc.stderr.strip()}"
            )
        return out.read_text(encoding="utf-8")


def activity_gpx(
    activity: Activity,
    gpsbabel_bin: str = "gpsbabel",
    prefer_gpsbabel: bool = True,
) -> str:
    """Return GPX text for an activity.

    Uses gpsbabel on the raw ``.FIT`` when available; otherwise the built-in
    writer. Raises :class:`ExportError` only if neither path can produce output.
    """
    # gpsbabel is invoked with ``-i garmin_fit``, so it only applies to FIT raw
    # files; TCX/GPX-sourced activities use the built-in writer directly.
    raw_is_fit = bool(activity.raw_path) and str(activity.raw_path).lower().endswith(".fit")
    if prefer_gpsbabel and raw_is_fit and gpx_available(gpsbabel_bin):
        try:
            return _gpsbabel_gpx(activity.raw_path, gpsbabel_bin)
        except ExportError:
            # Fall through to the built-in writer rather than failing the export.
            pass
    if not activity.trackpoints:
        raise ExportError("no GPS trackpoints available to build GPX")
    return _builtin_gpx(activity)


# --------------------------------------------------------------------------- #
# TCX (Garmin Connect / Strava friendly)
# --------------------------------------------------------------------------- #
# TCX only allows these Sport values; everything else maps to "Other".
_TCX_SPORTS = {"running": "Running", "cycling": "Biking", "biking": "Biking"}
_TCX_EPOCH = "1970-01-01T00:00:00Z"


def _tcx_time(dt) -> str | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_points_by_lap(activity: Activity, laps: list[Lap]) -> list[list[Trackpoint]]:
    """Assign trackpoints to laps by timestamp; all into lap 0 if not splittable."""
    pts = activity.trackpoints
    if len(laps) <= 1 or any(l.start_time is None for l in laps):
        return [list(pts)] + [[] for _ in laps[1:]]
    starts = [l.start_time for l in laps]
    buckets: list[list[Trackpoint]] = [[] for _ in laps]
    for tp in pts:
        idx = 0
        if tp.timestamp is not None:
            for i, s in enumerate(starts):
                if s <= tp.timestamp:
                    idx = i
                else:
                    break
        buckets[idx].append(tp)
    return buckets


def _synth_lap(a: Activity) -> Lap:
    """A single lap mirroring the activity summary (for files that have no laps)."""
    return Lap(
        lap_index=0, start_time=a.start_time, total_timer_time=a.total_timer_time,
        total_elapsed_time=a.total_elapsed_time, total_distance=a.total_distance,
        avg_heart_rate=a.avg_heart_rate, max_heart_rate=a.max_heart_rate,
        max_speed=a.max_speed, total_calories=a.total_calories,
        total_ascent=a.total_ascent, total_descent=a.total_descent,
    )


def _tcx_trackpoint(tp: Trackpoint, fallback_start) -> list[str]:
    t = _tcx_time(tp.timestamp) or _tcx_time(fallback_start)
    out = ["          <Trackpoint>"]
    if t:
        out.append(f"            <Time>{t}</Time>")
    if tp.latitude is not None and tp.longitude is not None:
        out += [
            "            <Position>",
            f"              <LatitudeDegrees>{tp.latitude:.7f}</LatitudeDegrees>",
            f"              <LongitudeDegrees>{tp.longitude:.7f}</LongitudeDegrees>",
            "            </Position>",
        ]
    if tp.altitude is not None:
        out.append(f"            <AltitudeMeters>{tp.altitude}</AltitudeMeters>")
    if tp.distance is not None:
        out.append(f"            <DistanceMeters>{tp.distance}</DistanceMeters>")
    if tp.heart_rate is not None:
        out.append(f"            <HeartRateBpm><Value>{int(tp.heart_rate)}</Value></HeartRateBpm>")
    if tp.cadence is not None:
        out.append(f"            <Cadence>{min(254, max(0, int(tp.cadence)))}</Cadence>")
    if tp.speed is not None or tp.power is not None:
        out.append("            <Extensions>")
        out.append("              <ns3:TPX>")
        if tp.speed is not None:
            out.append(f"                <ns3:Speed>{tp.speed}</ns3:Speed>")
        if tp.power is not None:
            out.append(f"                <ns3:Watts>{int(tp.power)}</ns3:Watts>")
        out.append("              </ns3:TPX>")
        out.append("            </Extensions>")
    out.append("          </Trackpoint>")
    return out


def _tcx_lap(lap: Lap, pts: list[Trackpoint], a: Activity) -> list[str]:
    start = _tcx_time(lap.start_time) or _tcx_time(a.start_time) or _TCX_EPOCH
    pick = lambda x, y: x if x is not None else y  # noqa: E731 (terse local fallback)
    total_time = pick(lap.total_timer_time, a.total_timer_time) or 0.0
    distance = pick(lap.total_distance, a.total_distance) or 0.0
    out = [
        f'      <Lap StartTime="{start}">',
        f"        <TotalTimeSeconds>{total_time}</TotalTimeSeconds>",
        f"        <DistanceMeters>{distance}</DistanceMeters>",
    ]
    max_speed = pick(lap.max_speed, a.max_speed)
    if max_speed is not None:
        out.append(f"        <MaximumSpeed>{max_speed}</MaximumSpeed>")
    calories = pick(lap.total_calories, a.total_calories)
    if calories is not None:
        out.append(f"        <Calories>{int(calories)}</Calories>")
    avg_hr = pick(lap.avg_heart_rate, a.avg_heart_rate)
    if avg_hr is not None:
        out.append(f"        <AverageHeartRateBpm><Value>{int(avg_hr)}</Value></AverageHeartRateBpm>")
    max_hr = pick(lap.max_heart_rate, a.max_heart_rate)
    if max_hr is not None:
        out.append(f"        <MaximumHeartRateBpm><Value>{int(max_hr)}</Value></MaximumHeartRateBpm>")
    out += ["        <Intensity>Active</Intensity>", "        <TriggerMethod>Manual</TriggerMethod>"]
    if pts:
        out.append("        <Track>")
        for tp in pts:
            out += _tcx_trackpoint(tp, a.start_time)
        out.append("        </Track>")
    out.append("      </Lap>")
    return out


def activity_tcx(activity: Activity) -> str:
    """Return Garmin TCX for an activity (uploadable to Garmin Connect, Strava, …)."""
    sport = _TCX_SPORTS.get((activity.sport or "").lower(), "Other")
    start = (
        _tcx_time(activity.start_time)
        or (_tcx_time(activity.trackpoints[0].timestamp) if activity.trackpoints else None)
        or _TCX_EPOCH
    )
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<TrainingCenterDatabase '
        'xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
        'xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 '
        'http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd">',
        "  <Activities>",
        f'    <Activity Sport="{sport}">',
        f"      <Id>{start}</Id>",
    ]
    laps = activity.laps or [_synth_lap(activity)]
    for lap, pts in zip(laps, _split_points_by_lap(activity, laps)):
        lines += _tcx_lap(lap, pts, activity)
    if activity.device_product:
        lines.append(
            f'      <Creator xsi:type="Device_t"><Name>'
            f"{escape(str(activity.device_product))}</Name></Creator>"
        )
    lines += ["    </Activity>", "  </Activities>", "</TrainingCenterDatabase>"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# File-writing convenience wrappers (used by the CLI and the export endpoint)
# --------------------------------------------------------------------------- #
def _safe_stem(activity: Activity) -> str:
    when = activity.start_time.strftime("%Y%m%d-%H%M%S") if activity.start_time else "unknown"
    sport = (activity.sport or "activity").replace("/", "-").replace(" ", "_")
    return f"{when}_{sport}_{activity.id or 'x'}"


def write_activity_export(
    activity: Activity,
    fmt: str,
    output_dir: str | Path,
    gpsbabel_bin: str = "gpsbabel",
) -> Path:
    """Write a single activity to ``output_dir`` in ``fmt`` (csv|json|gpx)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(activity)
    fmt = fmt.lower()
    if fmt == "json":
        path, text = output_dir / f"{stem}.json", activity_json(activity)
    elif fmt == "csv":
        path, text = output_dir / f"{stem}.csv", activity_trackpoints_csv(activity)
    elif fmt == "gpx":
        path, text = output_dir / f"{stem}.gpx", activity_gpx(activity, gpsbabel_bin)
    elif fmt == "tcx":
        path, text = output_dir / f"{stem}.tcx", activity_tcx(activity)
    elif fmt == "raw":
        src = Path(activity.raw_path)
        if not src.is_file():
            raise ExportError("original raw file is not available for this activity")
        dest = output_dir / f"{stem}{(src.suffix or '.fit').lower()}"
        shutil.copy2(src, dest)
        return dest
    else:
        raise ExportError(f"unsupported format: {fmt!r}")
    path.write_text(text, encoding="utf-8")
    return path


def write_bulk_export(
    activities: Sequence[Activity],
    fmt: str,
    output_dir: str | Path,
    full: bool = False,
) -> Path:
    """Write a bulk export of ``activities`` to ``output_dir``.

    ``full`` includes laps + trackpoints (ignored for flat CSV). Formats:
    csv (summary table), json, ndjson.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "json":
        path, text = output_dir / "activities.json", activities_json(activities, full)
    elif fmt == "ndjson":
        path, text = output_dir / "activities.ndjson", activities_ndjson(activities, full)
    elif fmt == "csv":
        path, text = output_dir / "activities.csv", activities_summary_csv(activities)
    else:
        raise ExportError(f"unsupported bulk format: {fmt!r} (use csv, json or ndjson)")
    path.write_text(text, encoding="utf-8")
    return path


def write_archive(activities: Sequence[Activity], output_dir: str | Path) -> Path:
    """Write a timestamped, full-fidelity NDJSON archive of all activities.

    This is the portable long-term archive (complementing the raw ``.FIT`` store
    and the SQLite DB). Every activity is written with its full time series, laps
    and preserved FIT fields, ready for future analysis/data-mining.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"fenix5sync-archive-{ts}.ndjson"
    path.write_text(activities_ndjson(activities, include_series=True), encoding="utf-8")
    return path

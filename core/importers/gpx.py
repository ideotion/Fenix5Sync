"""Parse GPX 1.1 tracks into the canonical Activity model.

GPX is the most widely supported interchange format (Strava, Komoot, Wahoo,
Suunto, Coros, phone apps, ...). It carries the track geometry and time, plus
heart rate / cadence / temperature / power via the common ``TrackPointExtension``
and power extensions. It does *not* carry cumulative distance, speed or
ascent/descent, so we derive those from the geometry (haversine) and the
altitude series. Namespaces are ignored (we match on local element names).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..models import Activity, Trackpoint
from ._util import (
    ascent_descent,
    child,
    descendants,
    first_text,
    haversine_m,
    parse_time,
    text_of,
    to_float,
    to_int,
)


def sniff(head: bytes, path: Path) -> bool:
    """True if the file looks like GPX (contains a ``<gpx`` root element)."""
    return b"<gpx" in head.lower()


def _build_trackpoint(el) -> Trackpoint:
    tp = Trackpoint()
    tp.latitude = to_float(el.get("lat"))
    tp.longitude = to_float(el.get("lon"))
    tp.altitude = to_float(text_of(child(el, "ele")))
    tp.timestamp = parse_time(text_of(child(el, "time")))
    ext = child(el, "extensions")
    if ext is not None:
        # gpxtpx:TrackPointExtension fields (matched by local name).
        tp.heart_rate = to_int(first_text(ext, "hr"))
        tp.cadence = to_int(first_text(ext, "cad"))
        tp.temperature = to_float(first_text(ext, "atemp"))
        tp.speed = to_float(first_text(ext, "speed"))
        # Power appears as <power> (Garmin/Strava) or gpxpx:PowerInWatts.
        tp.power = to_int(first_text(ext, "power") or first_text(ext, "PowerInWatts"))
    return tp


def _fill_distance_and_speed(points: list[Trackpoint]) -> None:
    """Populate cumulative ``distance`` (and ``speed`` where missing) in place."""
    cumulative = 0.0
    prev_lat = prev_lon = None
    prev_time = None
    for tp in points:
        if tp.latitude is None or tp.longitude is None:
            continue
        if prev_lat is not None:
            step = haversine_m(prev_lat, prev_lon, tp.latitude, tp.longitude)
            cumulative += step
            if tp.speed is None and prev_time is not None and tp.timestamp is not None:
                dt = (tp.timestamp - prev_time).total_seconds()
                if dt > 0:
                    tp.speed = step / dt
        tp.distance = cumulative
        prev_lat, prev_lon = tp.latitude, tp.longitude
        prev_time = tp.timestamp


def _mean_int(values: list[int]) -> int | None:
    return int(round(sum(values) / len(values))) if values else None


def parse_gpx_file(path, file_hash: str = "", raw_path: str | None = None) -> Activity:
    """Parse a GPX file into an :class:`Activity` (summary + trackpoints)."""
    from ..parse import ParseError  # reuse the shared error type

    path = Path(path)
    raw_path = str(raw_path) if raw_path is not None else str(path)

    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        raise ParseError(f"{path.name}: invalid GPX XML ({exc})") from exc

    activity = Activity(file_hash=file_hash, raw_path=raw_path)

    creator = root.get("creator")
    if creator:
        activity.device_product = creator
        activity.extra["gpx_creator"] = {"value": creator, "units": None}

    # sport/name come from the first <trk> that declares them.
    for trk in descendants(root, "trk"):
        if activity.sport is None:
            sport = text_of(child(trk, "type"))
            if sport:
                activity.sport = sport.strip().lower()
        name = text_of(child(trk, "name"))
        if name and "name" not in activity.extra:
            activity.extra["name"] = {"value": name, "units": None}

    for trkpt in descendants(root, "trkpt"):
        activity.trackpoints.append(_build_trackpoint(trkpt))
    pts = activity.trackpoints
    if not pts:
        raise ParseError(f"{path.name}: GPX contained no track points")

    _fill_distance_and_speed(pts)

    meta = child(root, "metadata")
    meta_time = parse_time(text_of(child(meta, "time"))) if meta is not None else None
    activity.start_time = meta_time or pts[0].timestamp

    last_dist = next((tp.distance for tp in reversed(pts) if tp.distance is not None), None)
    activity.total_distance = last_dist

    times = [tp.timestamp for tp in pts if tp.timestamp is not None]
    if len(times) >= 2:
        activity.total_elapsed_time = (times[-1] - times[0]).total_seconds()
        activity.total_timer_time = activity.total_elapsed_time

    for tp in pts:
        if tp.latitude is not None and tp.longitude is not None:
            activity.start_latitude = tp.latitude
            activity.start_longitude = tp.longitude
            break

    hrs = [tp.heart_rate for tp in pts if tp.heart_rate is not None]
    if hrs:
        activity.avg_heart_rate = _mean_int(hrs)
        activity.max_heart_rate = max(hrs)
    speeds = [tp.speed for tp in pts if tp.speed is not None]
    if speeds:
        activity.max_speed = max(speeds)
    if activity.total_distance and activity.total_timer_time:
        activity.avg_speed = activity.total_distance / activity.total_timer_time
    activity.avg_cadence = _mean_int([tp.cadence for tp in pts if tp.cadence is not None])
    activity.avg_power = _mean_int([tp.power for tp in pts if tp.power is not None])
    temps = [tp.temperature for tp in pts if tp.temperature is not None]
    if temps:
        activity.avg_temperature = sum(temps) / len(temps)

    activity.total_ascent, activity.total_descent = ascent_descent(tp.altitude for tp in pts)
    return activity

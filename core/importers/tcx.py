# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse Garmin TCX (Training Center XML) into the canonical Activity model.

TCX is what many non-Garmin platforms and older devices export. We read the
first ``<Activity>`` (the common case for a single-activity export), map its
laps and trackpoints onto :class:`~core.models.Activity`, and derive the summary
fields that TCX doesn't state explicitly (e.g. average HR/speed, ascent/descent)
from the time series. Namespaces are ignored (we match on local element names)
so files from any exporter parse the same way.
"""

from __future__ import annotations

# defusedxml hardens stdlib XML parsing against entity-expansion / external-entity
# attacks in untrusted activity files (TCX from arbitrary exporters).
import defusedxml.ElementTree as ET
from pathlib import Path

from ..models import Activity, Lap, Trackpoint
from ._util import (
    ascent_descent,
    child,
    children,
    descendants,
    local_name,
    parse_time,
    text_of,
    to_float,
    to_int,
)

# TCX sport names -> our (FIT-aligned) sport vocabulary.
_SPORT_MAP = {"running": "running", "biking": "cycling", "other": None}


def sniff(head: bytes, path: Path) -> bool:
    """True if the file looks like TCX (root is TrainingCenterDatabase)."""
    return b"trainingcenterdatabase" in head.lower()


def _map_sport(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower()
    return _SPORT_MAP.get(key, key)


def _build_lap(lap_el, index: int) -> Lap:
    lap = Lap(lap_index=index)
    lap.start_time = parse_time(lap_el.get("StartTime"))
    lap.total_timer_time = to_float(text_of(child(lap_el, "TotalTimeSeconds")))
    lap.total_elapsed_time = lap.total_timer_time  # TCX states one duration only
    lap.total_distance = to_float(text_of(child(lap_el, "DistanceMeters")))
    lap.max_speed = to_float(text_of(child(lap_el, "MaximumSpeed")))
    lap.total_calories = to_int(text_of(child(lap_el, "Calories")))
    avg_hr = child(lap_el, "AverageHeartRateBpm")
    if avg_hr is not None:
        lap.avg_heart_rate = to_int(text_of(child(avg_hr, "Value")))
    max_hr = child(lap_el, "MaximumHeartRateBpm")
    if max_hr is not None:
        lap.max_heart_rate = to_int(text_of(child(max_hr, "Value")))
    return lap


def _build_trackpoint(tp_el) -> Trackpoint:
    tp = Trackpoint()
    tp.timestamp = parse_time(text_of(child(tp_el, "Time")))
    pos = child(tp_el, "Position")
    if pos is not None:
        tp.latitude = to_float(text_of(child(pos, "LatitudeDegrees")))
        tp.longitude = to_float(text_of(child(pos, "LongitudeDegrees")))
    tp.altitude = to_float(text_of(child(tp_el, "AltitudeMeters")))
    tp.distance = to_float(text_of(child(tp_el, "DistanceMeters")))
    hr = child(tp_el, "HeartRateBpm")
    if hr is not None:
        tp.heart_rate = to_int(text_of(child(hr, "Value")))
    cad = child(tp_el, "Cadence")
    if cad is not None:
        tp.cadence = to_int(text_of(cad))
    # Garmin ActivityExtension (TPX): speed / watts / running cadence.
    ext = child(tp_el, "Extensions")
    if ext is not None:
        for tpx in descendants(ext, "TPX"):
            if tp.speed is None:
                tp.speed = to_float(text_of(child(tpx, "Speed")))
            if tp.power is None:
                tp.power = to_int(text_of(child(tpx, "Watts")))
            if tp.cadence is None:
                tp.cadence = to_int(text_of(child(tpx, "RunCadence")))
    return tp


def _mean_int(values: list[int]) -> int | None:
    return int(round(sum(values) / len(values))) if values else None


def parse_tcx_file(path, file_hash: str = "", raw_path: str | None = None) -> Activity:
    """Parse a TCX file into an :class:`Activity` (summary + laps + trackpoints)."""
    from ..parse import ParseError  # reuse the shared error type

    path = Path(path)
    raw_path = str(raw_path) if raw_path is not None else str(path)

    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        raise ParseError(f"{path.name}: invalid TCX XML ({exc})") from exc

    activity_els = [e for e in root.iter() if local_name(e.tag) == "Activity"]
    if not activity_els:
        raise ParseError(f"{path.name}: no <Activity> element found in TCX")
    act_el = activity_els[0]

    activity = Activity(file_hash=file_hash, raw_path=raw_path)
    activity.sport = _map_sport(act_el.get("Sport"))

    creator = child(act_el, "Creator")
    if creator is not None:
        name = text_of(child(creator, "Name"))
        if name:
            activity.device_product = name
            activity.device_manufacturer = activity.device_manufacturer or "garmin"

    # ---- laps + aggregate summary ------------------------------------------
    total_timer = total_dist_laps = 0.0
    total_calories = 0
    have_timer = have_dist_laps = False
    max_speed: float | None = None
    max_hr: int | None = None
    for idx, lap_el in enumerate(children(act_el, "Lap")):
        lap = _build_lap(lap_el, idx)
        activity.laps.append(lap)
        if lap.total_timer_time:
            total_timer += lap.total_timer_time
            have_timer = True
        if lap.total_distance:
            total_dist_laps += lap.total_distance
            have_dist_laps = True
        if lap.total_calories:
            total_calories += lap.total_calories
        if lap.max_speed is not None:
            max_speed = lap.max_speed if max_speed is None else max(max_speed, lap.max_speed)
        if lap.max_heart_rate is not None:
            max_hr = lap.max_heart_rate if max_hr is None else max(max_hr, lap.max_heart_rate)

    # ---- trackpoints (in document order across laps) -----------------------
    for tp_el in descendants(act_el, "Trackpoint"):
        activity.trackpoints.append(_build_trackpoint(tp_el))

    pts = activity.trackpoints

    # ---- start time: Activity/Id, then first lap, then first trackpoint ----
    activity.start_time = parse_time(text_of(child(act_el, "Id")))
    if activity.start_time is None and activity.laps:
        activity.start_time = activity.laps[0].start_time
    if activity.start_time is None and pts:
        activity.start_time = pts[0].timestamp

    # ---- summary fields ----------------------------------------------------
    activity.total_timer_time = total_timer if have_timer else None
    activity.total_elapsed_time = activity.total_timer_time
    # Distance: prefer the last cumulative trackpoint distance; else sum laps.
    last_dist = next((tp.distance for tp in reversed(pts) if tp.distance is not None), None)
    activity.total_distance = last_dist if last_dist is not None else (
        total_dist_laps if have_dist_laps else None
    )
    activity.total_calories = total_calories or None
    activity.max_speed = max_speed
    activity.max_heart_rate = max_hr

    activity.avg_heart_rate = _mean_int([tp.heart_rate for tp in pts if tp.heart_rate is not None])
    activity.avg_cadence = _mean_int([tp.cadence for tp in pts if tp.cadence is not None])
    activity.avg_power = _mean_int([tp.power for tp in pts if tp.power is not None])
    temps = [tp.temperature for tp in pts if tp.temperature is not None]
    if temps:
        activity.avg_temperature = sum(temps) / len(temps)
    if activity.total_distance and activity.total_timer_time:
        activity.avg_speed = activity.total_distance / activity.total_timer_time

    for tp in pts:
        if tp.latitude is not None and tp.longitude is not None:
            activity.start_latitude = tp.latitude
            activity.start_longitude = tp.longitude
            break

    activity.total_ascent, activity.total_descent = ascent_descent(tp.altitude for tp in pts)

    if not activity.laps and not pts:
        raise ParseError(f"{path.name}: TCX contained no laps or trackpoints")
    return activity

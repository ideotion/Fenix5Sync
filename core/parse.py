"""FIT parsing via fitparse.

Extracts a session-level summary, per-lap summaries and record-level time series
from a ``.FIT`` file. Corrupt or truncated files raise :class:`ParseError`
(carrying a human-readable reason) rather than crashing the caller, so one bad
file never aborts a batch.

Unit handling:
  * GPS positions are stored by FIT in *semicircles*; we convert to degrees.
  * speed (m/s), altitude (m), distance (m), temperature (deg C), heart rate
    (bpm), cadence (rpm) and power (W) are passed through with fitparse's scaled
    values.
Every field present on a message is preserved: recognised fields are promoted to
typed attributes, and anything else is kept in the model's ``extra`` mapping as
``{name: {"value": ..., "units": ...}}``.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from .models import Activity, Lap, Trackpoint

# Conversion factor: 1 semicircle = 180 / 2**31 degrees.
_SEMI_TO_DEG = 180.0 / (2**31)


class ParseError(Exception):
    """Raised when a FIT file cannot be parsed (corrupt/truncated/unsupported)."""


def _jsonable(value: Any) -> Any:
    """Coerce a FIT field value into something JSON/SQLite-serialisable."""
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _semicircles_to_degrees(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * _SEMI_TO_DEG
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _intish(value: Any) -> int | None:
    n = _num(value)
    return int(round(n)) if n is not None else None


def _collect_fields(message) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (values, extras) for a fitparse message.

    ``values`` maps field name -> raw value (for promotion to attributes);
    ``extras`` maps field name -> {"value", "units"} for every field with a
    non-None value (so units and uncommon fields are preserved).
    """
    values: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for fdata in message.fields:
        name = fdata.name
        value = fdata.value
        if value is None:
            continue
        values[name] = value
        extras[name] = {"value": _jsonable(value), "units": fdata.units}
    return values, extras


def _build_lap(message, index: int) -> Lap:
    values, extras = _collect_fields(message)
    return Lap(
        lap_index=index,
        start_time=values.get("start_time"),
        total_timer_time=_num(values.get("total_timer_time")),
        total_elapsed_time=_num(values.get("total_elapsed_time")),
        total_distance=_num(values.get("total_distance")),
        avg_heart_rate=_intish(values.get("avg_heart_rate")),
        max_heart_rate=_intish(values.get("max_heart_rate")),
        avg_speed=_num(values.get("enhanced_avg_speed") or values.get("avg_speed")),
        max_speed=_num(values.get("enhanced_max_speed") or values.get("max_speed")),
        total_ascent=_intish(values.get("total_ascent")),
        total_descent=_intish(values.get("total_descent")),
        total_calories=_intish(values.get("total_calories")),
        extra=extras,
    )


def _build_trackpoint(message) -> Trackpoint:
    values, extras = _collect_fields(message)
    return Trackpoint(
        timestamp=values.get("timestamp"),
        latitude=_semicircles_to_degrees(values.get("position_lat")),
        longitude=_semicircles_to_degrees(values.get("position_long")),
        heart_rate=_intish(values.get("heart_rate")),
        cadence=_intish(values.get("cadence")),
        speed=_num(values.get("enhanced_speed") or values.get("speed")),
        altitude=_num(values.get("enhanced_altitude") or values.get("altitude")),
        distance=_num(values.get("distance")),
        temperature=_num(values.get("temperature")),
        power=_intish(values.get("power")),
        extra=extras,
    )


def parse_fit_file(
    path: str | Path,
    file_hash: str = "",
    raw_path: str | None = None,
) -> Activity:
    """Parse a FIT file into an :class:`Activity` (summary + laps + trackpoints).

    Args:
        path: filesystem path to the ``.FIT`` file to parse.
        file_hash: SHA-256 of the file content (stored on the activity).
        raw_path: where the raw file is/should be kept (defaults to ``path``).

    Raises:
        ParseError: if the file is corrupt, truncated or otherwise unreadable.
    """
    # Imported lazily so the rest of the core can be imported without fitparse
    # installed (e.g. for config/storage-only use).
    try:
        from fitparse import FitFile
        from fitparse.utils import FitParseError
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ParseError(f"fitparse is not available: {exc}") from exc

    path = Path(path)
    raw_path = str(raw_path) if raw_path is not None else str(path)

    try:
        fit = FitFile(str(path))
        fit.parse()
    except FitParseError as exc:
        raise ParseError(f"{path.name}: corrupt or truncated FIT ({exc})") from exc
    except Exception as exc:  # defensive: any reader failure -> ParseError
        raise ParseError(f"{path.name}: failed to read FIT ({exc})") from exc

    activity = Activity(file_hash=file_hash, raw_path=raw_path)

    # ---- session summary (usually exactly one) -----------------------------
    try:
        sessions = list(fit.get_messages("session"))
    except FitParseError as exc:
        raise ParseError(f"{path.name}: error iterating sessions ({exc})") from exc

    if sessions:
        values, extras = _collect_fields(sessions[0])
        activity.extra.update(extras)
        activity.sport = _as_str(values.get("sport"))
        activity.sub_sport = _as_str(values.get("sub_sport"))
        activity.start_time = values.get("start_time")
        activity.total_timer_time = _num(values.get("total_timer_time"))
        activity.total_elapsed_time = _num(values.get("total_elapsed_time"))
        activity.total_distance = _num(values.get("total_distance"))
        activity.total_calories = _intish(values.get("total_calories"))
        activity.avg_heart_rate = _intish(values.get("avg_heart_rate"))
        activity.max_heart_rate = _intish(values.get("max_heart_rate"))
        activity.avg_speed = _num(
            values.get("enhanced_avg_speed") or values.get("avg_speed")
        )
        activity.max_speed = _num(
            values.get("enhanced_max_speed") or values.get("max_speed")
        )
        # Cadence is a dynamic FIT field: for running activities fitparse exposes
        # it as the `avg_running_cadence` subfield rather than `avg_cadence`.
        activity.avg_cadence = _intish(
            values.get("avg_cadence")
            or values.get("avg_running_cadence")
        )
        activity.avg_power = _intish(values.get("avg_power"))
        activity.avg_temperature = _num(values.get("avg_temperature"))
        activity.total_ascent = _intish(values.get("total_ascent"))
        activity.total_descent = _intish(values.get("total_descent"))
        activity.start_latitude = _semicircles_to_degrees(values.get("start_position_lat"))
        activity.start_longitude = _semicircles_to_degrees(values.get("start_position_long"))

    # ---- file_id / device info (manufacturer, product, time fallback) ------
    for msg_name in ("file_id", "device_info"):
        for msg in fit.get_messages(msg_name):
            vals, _ = _collect_fields(msg)
            if activity.device_manufacturer is None:
                activity.device_manufacturer = _as_str(vals.get("manufacturer"))
            if activity.device_product is None:
                activity.device_product = _as_str(
                    vals.get("garmin_product") or vals.get("product")
                )
            if activity.start_time is None:
                activity.start_time = vals.get("time_created")

    # ---- user_profile (athlete data the watch carries) ---------------------
    # Stored under a namespaced ``extra`` key so athlete auto-fill can offer it
    # (weight/height/gender/resting HR) without changing the DB schema.
    for msg in fit.get_messages("user_profile"):
        vals, _ = _collect_fields(msg)
        profile: dict[str, Any] = {}
        weight = _num(vals.get("weight"))
        height = _num(vals.get("height"))
        gender = _as_str(vals.get("gender"))
        resting = _intish(vals.get("resting_heart_rate"))
        if weight:
            profile["weight_kg"] = weight
        if height:
            profile["height_m"] = height
        if gender:
            profile["gender"] = gender
        if resting:  # 0 means "unset" on the device
            profile["resting_heart_rate"] = resting
        if profile:
            activity.extra["user_profile"] = profile
        break

    # ---- laps ---------------------------------------------------------------
    for idx, msg in enumerate(fit.get_messages("lap")):
        try:
            activity.laps.append(_build_lap(msg, idx))
        except Exception:  # one bad lap shouldn't drop the whole activity
            continue

    # ---- records (time series) ---------------------------------------------
    for msg in fit.get_messages("record"):
        try:
            activity.trackpoints.append(_build_trackpoint(msg))
        except Exception:
            continue

    # Derive a start position from the first geolocated trackpoint if needed.
    if activity.start_latitude is None:
        for tp in activity.trackpoints:
            if tp.latitude is not None and tp.longitude is not None:
                activity.start_latitude = tp.latitude
                activity.start_longitude = tp.longitude
                break

    # Derive start_time from first trackpoint if the session lacked it.
    if activity.start_time is None and activity.trackpoints:
        activity.start_time = activity.trackpoints[0].timestamp

    if not sessions and not activity.trackpoints:
        raise ParseError(f"{path.name}: no session or record data found")

    return activity


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

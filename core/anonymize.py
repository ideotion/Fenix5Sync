# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional, non-destructive anonymization of activities for export/sharing.

The local archive is the lossless source of truth and is **never** modified by
this module: :func:`anonymize_activity` works on a deep copy and returns it, so
the SQLite row and the raw file on disk are untouched. Every transform is opt-in
and configured via :class:`~core.config.AnonymizeConfig`.

What can be scrubbed (all independently toggleable):
  * **Location** -- drop all GPS, and/or null positions within a privacy radius
    of the start *and* end (home/finish zones), and/or jitter remaining points.
  * **Device identity** -- make/model plus serial / unit / ANT ids.
  * **Personal profile** -- age, weight, height, gender and similar fields that
    some files embed.
  * **Dates** -- rebase timestamps so the time-of-day / calendar date is hidden
    while durations and intervals are preserved.

The local raw-file path (which can leak a username / home directory) is always
cleared on the returned copy.
"""

from __future__ import annotations

import copy
import datetime as _dt
import random
from dataclasses import replace
from typing import Any

from .config import AnonymizeConfig
from .geo import haversine_m, offset_point
from .models import Activity, Trackpoint

# Reference instant used when rebasing dates (preserves intervals, hides "when").
_DATE_ANCHOR = _dt.datetime(2000, 1, 1, 0, 0, 0)

# extra/field keys treated as device-identifying.
_DEVICE_KEYS = frozenset({
    "serial_number", "unit_id", "ant_device_number", "antplus_device_type",
    "product", "garmin_product", "manufacturer", "product_name", "descriptor",
    "device_index", "source_type", "software_version", "hardware_version",
})
# extra/field keys treated as personal profile data.
_PERSONAL_KEYS = frozenset({
    "age", "weight", "height", "gender", "default_max_heart_rate",
    "resting_heart_rate", "user_walking_step_length", "user_running_step_length",
    "friendly_name", "user_profile",
})


def effective_options(opts: AnonymizeConfig, force: bool) -> AnonymizeConfig:
    """Return options with ``enabled`` turned on when an export forces it.

    Lets callers always go through :func:`anonymize_activity` (which is a no-op
    when ``enabled`` is False) without branching on the request flag themselves.
    """
    if force and not opts.enabled:
        return replace(opts, enabled=True)
    return opts


def anonymize_activity(activity: Activity, opts: AnonymizeConfig) -> Activity:
    """Return an anonymized **deep copy** of ``activity`` per ``opts``.

    When ``opts.enabled`` is False the copy is returned unchanged (apart from the
    deep copy itself), so callers can apply it unconditionally.
    """
    a = copy.deepcopy(activity)
    if not opts.enabled:
        return a

    if opts.drop_gps:
        _drop_all_gps(a)
    elif opts.privacy_radius_m and opts.privacy_radius_m > 0:
        _apply_privacy_zones(a, float(opts.privacy_radius_m))

    if not opts.drop_gps and opts.fuzz_gps_m and opts.fuzz_gps_m > 0:
        _fuzz_gps(a, float(opts.fuzz_gps_m))

    if opts.strip_device:
        _strip_device(a)
    if opts.strip_personal:
        _strip_personal(a)
    if opts.shift_dates:
        _shift_dates(a)

    # A local filesystem path can leak a username / home directory.
    a.raw_path = ""
    return a


# --------------------------------------------------------------------------- #
# GPS
# --------------------------------------------------------------------------- #
def _geolocated(points: list[Trackpoint]) -> list[Trackpoint]:
    return [tp for tp in points if tp.latitude is not None and tp.longitude is not None]


def _drop_all_gps(a: Activity) -> None:
    a.start_latitude = None
    a.start_longitude = None
    for tp in a.trackpoints:
        tp.latitude = None
        tp.longitude = None


def _apply_privacy_zones(a: Activity, radius_m: float) -> None:
    """Null positions within ``radius_m`` of the first and last located point."""
    located = _geolocated(a.trackpoints)
    a.start_latitude = None
    a.start_longitude = None
    if not located:
        return
    first, last = located[0], located[-1]
    anchors = ((first.latitude, first.longitude), (last.latitude, last.longitude))
    for tp in located:
        if any(haversine_m(alat, alon, tp.latitude, tp.longitude) <= radius_m
               for alat, alon in anchors):
            tp.latitude = None
            tp.longitude = None


def _fuzz_gps(a: Activity, meters: float) -> None:
    """Jitter each remaining position by up to ``meters`` (deterministic per activity)."""
    rng = random.Random(a.file_hash or repr(a.start_time))
    for tp in _geolocated(a.trackpoints):
        tp.latitude, tp.longitude = offset_point(
            tp.latitude, tp.longitude,
            rng.uniform(-meters, meters), rng.uniform(-meters, meters),
        )
    if a.start_latitude is not None and a.start_longitude is not None:
        a.start_latitude, a.start_longitude = offset_point(
            a.start_latitude, a.start_longitude,
            rng.uniform(-meters, meters), rng.uniform(-meters, meters),
        )


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def _remove_keys(extra: dict[str, Any], keys: frozenset[str]) -> None:
    for k in list(extra):
        if k in keys:
            del extra[k]


def _scrub_all_extras(a: Activity, keys: frozenset[str]) -> None:
    _remove_keys(a.extra, keys)
    for lap in a.laps:
        _remove_keys(lap.extra, keys)
    for tp in a.trackpoints:
        _remove_keys(tp.extra, keys)


def _strip_device(a: Activity) -> None:
    a.device_manufacturer = None
    a.device_product = None
    _scrub_all_extras(a, _DEVICE_KEYS)


def _strip_personal(a: Activity) -> None:
    _scrub_all_extras(a, _PERSONAL_KEYS)


def _shift_dates(a: Activity) -> None:
    if a.start_time is None:
        return
    delta = _DATE_ANCHOR - a.start_time
    a.start_time = a.start_time + delta
    for lap in a.laps:
        if lap.start_time is not None:
            lap.start_time = lap.start_time + delta
    for tp in a.trackpoints:
        if tp.timestamp is not None:
            tp.timestamp = tp.timestamp + delta
    # When the import happened also reveals timing; drop it.
    a.imported_at = None

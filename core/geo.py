"""Geographic helpers (pure, stdlib-only).

Small functions shared across the codebase: great-circle distance and a
metre-based coordinate offset. Kept in one place so the importers and the
anonymizer don't each carry their own copy.
"""

from __future__ import annotations

import math

# Metres per degree of latitude (mean). Longitude is scaled by cos(latitude).
_M_PER_DEG_LAT = 111320.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    radius = 6371000.0  # mean Earth radius (m)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def offset_point(
    lat: float, lon: float, north_m: float, east_m: float
) -> tuple[float, float]:
    """Return ``(lat, lon)`` shifted by ``north_m``/``east_m`` metres (small-offset approx)."""
    dlat = north_m / _M_PER_DEG_LAT
    cos_lat = math.cos(math.radians(lat))
    dlon = east_m / (_M_PER_DEG_LAT * (cos_lat if abs(cos_lat) > 1e-9 else 1e-9))
    return (lat + dlat, lon + dlon)

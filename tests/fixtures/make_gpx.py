"""Build a small, valid GPX 1.1 file for tests (namespaced like real exports).

Test support code, not part of the shipped library. The generated file has one
track (type "running") with ``n_records`` points carrying elevation, time and a
gpxtpx ``TrackPointExtension`` (heart rate, cadence, temperature). GPX has no
cumulative distance/speed, so the importer derives those -- which is what the
tests check.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

_BASE_LAT, _BASE_LON = 51.5007, -0.1246  # near London


def _iso(dt: _dt.datetime) -> str:
    return dt.replace(tzinfo=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_sample_gpx(
    start: _dt.datetime | None = None, n_records: int = 5
) -> str:
    """Return GPX text for a short running activity.

    Heart rates are ``130, 132, ...`` (avg 134, max 138 for n=5); coordinates
    advance each point so the derived distance is non-zero; altitude rises 1 m
    per point.
    """
    start = start or _dt.datetime(2023, 6, 15, 8, 0, 0, tzinfo=_dt.timezone.utc)

    points = []
    for i in range(n_records):
        ts = start + _dt.timedelta(seconds=10 * i)
        points.append(
            f'      <trkpt lat="{_BASE_LAT + i * 0.00025:.6f}" '
            f'lon="{_BASE_LON + i * 0.00015:.6f}">\n'
            f"        <ele>{35 + i}</ele>\n"
            f"        <time>{_iso(ts)}</time>\n"
            "        <extensions>\n"
            "          <gpxtpx:TrackPointExtension>\n"
            f"            <gpxtpx:hr>{130 + 2 * i}</gpxtpx:hr>\n"
            f"            <gpxtpx:cad>{85 + i}</gpxtpx:cad>\n"
            "            <gpxtpx:atemp>21</gpxtpx:atemp>\n"
            "          </gpxtpx:TrackPointExtension>\n"
            "        </extensions>\n"
            "      </trkpt>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="StravaGPX" '
        'xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">\n'
        f"  <metadata><time>{_iso(start)}</time></metadata>\n"
        "  <trk>\n"
        "    <name>Morning Run</name>\n"
        "    <type>running</type>\n"
        "    <trkseg>\n"
        + "\n".join(points)
        + "\n"
        "    </trkseg>\n"
        "  </trk>\n"
        "</gpx>\n"
    )


def write_sample(path: str | Path) -> Path:
    path = Path(path)
    path.write_text(build_sample_gpx(), encoding="utf-8")
    return path


if __name__ == "__main__":
    out = write_sample(Path(__file__).with_name("sample.gpx"))
    print(f"wrote {out} ({out.stat().st_size} bytes)")

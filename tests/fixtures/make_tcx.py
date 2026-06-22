# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a small, valid TCX file for tests (namespaced, like real exports).

Test support code, not part of the shipped library. The generated file has one
running Activity with a single Lap and ``n_records`` trackpoints carrying
position, altitude, cumulative distance, heart rate, cadence and the Garmin
ActivityExtension (TPX) speed/watts. Namespaces (default + ns3) are included so
the importer's namespace-agnostic parsing is genuinely exercised.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

_BASE_LAT, _BASE_LON = 51.5007, -0.1246  # near London


def _iso(dt: _dt.datetime) -> str:
    return dt.replace(tzinfo=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_sample_tcx(
    start: _dt.datetime | None = None, n_records: int = 5
) -> str:
    """Return TCX text for a short running activity.

    Trackpoint heart rates are ``120, 122, ... `` (avg 124, max 128 for n=5);
    cumulative distance reaches ``80 * (n-1)`` m; altitude rises 1 m per point.
    """
    start = start or _dt.datetime(2023, 6, 15, 8, 0, 0, tzinfo=_dt.timezone.utc)
    duration_s = 10 * (n_records - 1)
    total_distance = 80.0 * (n_records - 1)

    points = []
    for i in range(n_records):
        ts = start + _dt.timedelta(seconds=10 * i)
        points.append(
            "          <Trackpoint>\n"
            f"            <Time>{_iso(ts)}</Time>\n"
            "            <Position>\n"
            f"              <LatitudeDegrees>{_BASE_LAT + i * 0.00025:.6f}</LatitudeDegrees>\n"
            f"              <LongitudeDegrees>{_BASE_LON + i * 0.00015:.6f}</LongitudeDegrees>\n"
            "            </Position>\n"
            f"            <AltitudeMeters>{35 + i}</AltitudeMeters>\n"
            f"            <DistanceMeters>{80.0 * i:.1f}</DistanceMeters>\n"
            f"            <HeartRateBpm><Value>{120 + 2 * i}</Value></HeartRateBpm>\n"
            f"            <Cadence>{80 + i}</Cadence>\n"
            "            <Extensions>\n"
            "              <ns3:TPX>\n"
            "                <ns3:Speed>8.0</ns3:Speed>\n"
            f"                <ns3:Watts>{210 + i}</ns3:Watts>\n"
            "              </ns3:TPX>\n"
            "            </Extensions>\n"
            "          </Trackpoint>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<TrainingCenterDatabase '
        'xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
        'xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">\n'
        "  <Activities>\n"
        '    <Activity Sport="Running">\n'
        f"      <Id>{_iso(start)}</Id>\n"
        f'      <Lap StartTime="{_iso(start)}">\n'
        f"        <TotalTimeSeconds>{duration_s}</TotalTimeSeconds>\n"
        f"        <DistanceMeters>{total_distance:.1f}</DistanceMeters>\n"
        "        <MaximumSpeed>3.4</MaximumSpeed>\n"
        "        <Calories>45</Calories>\n"
        "        <AverageHeartRateBpm><Value>124</Value></AverageHeartRateBpm>\n"
        "        <MaximumHeartRateBpm><Value>128</Value></MaximumHeartRateBpm>\n"
        "        <Intensity>Active</Intensity>\n"
        "        <TriggerMethod>Manual</TriggerMethod>\n"
        "        <Track>\n"
        + "\n".join(points)
        + "\n"
        "        </Track>\n"
        "      </Lap>\n"
        "      <Creator><Name>Forerunner 945</Name></Creator>\n"
        "    </Activity>\n"
        "  </Activities>\n"
        "</TrainingCenterDatabase>\n"
    )


def write_sample(path: str | Path) -> Path:
    path = Path(path)
    path.write_text(build_sample_tcx(), encoding="utf-8")
    return path


if __name__ == "__main__":
    out = write_sample(Path(__file__).with_name("sample.tcx"))
    print(f"wrote {out} ({out.stat().st_size} bytes)")

"""A tiny, dependency-free FIT encoder used to generate test fixtures.

This is *test* support code, not part of the shipped library: it lets us create
a small but valid ``.FIT`` file (with file_id, session, lap and record messages)
without adding a FIT-writer dependency. The bytes follow the FIT file format:
a 12-byte header, a sequence of definition/data messages, and a trailing CRC-16.

Run directly to (re)write ``sample.fit`` next to this module.
"""

from __future__ import annotations

import datetime as _dt
import struct
from pathlib import Path

# Seconds between the Unix epoch and the FIT epoch (1989-12-31 00:00:00 UTC).
FIT_EPOCH_OFFSET = 631065600
_SEMI_PER_DEG = (2**31) / 180.0

# base type number -> (struct format char, size in bytes)
_BASE = {
    "enum": ("B", 1),
    "sint8": ("b", 1),
    "uint8": ("B", 1),
    "sint16": ("h", 2),
    "uint16": ("H", 2),
    "sint32": ("i", 4),
    "uint32": ("I", 4),
}
# base type number byte as defined by the FIT spec (bit 7 = endian ability).
_BASE_NUM = {
    "enum": 0x00,
    "sint8": 0x01,
    "uint8": 0x02,
    "sint16": 0x83,
    "uint16": 0x84,
    "sint32": 0x85,
    "uint32": 0x86,
}

_CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]


def fit_crc(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc & 0xFFFF


def fit_timestamp(dt: _dt.datetime) -> int:
    return int(dt.replace(tzinfo=_dt.timezone.utc).timestamp()) - FIT_EPOCH_OFFSET


def semicircles(deg: float) -> int:
    return int(round(deg * _SEMI_PER_DEG))


class _Message:
    """A definition + the field list for one local message type."""

    def __init__(self, local_type: int, global_num: int, fields: list[tuple[int, str]]):
        self.local_type = local_type
        self.global_num = global_num
        self.fields = fields  # list of (field_def_num, base_type_name)

    def definition_bytes(self) -> bytes:
        out = bytearray()
        out.append(0x40 | self.local_type)  # definition message header
        out.append(0x00)  # reserved
        out.append(0x00)  # architecture: little-endian
        out += struct.pack("<H", self.global_num)
        out.append(len(self.fields))
        for field_num, base_name in self.fields:
            out.append(field_num)
            out.append(_BASE[base_name][1])  # size
            out.append(_BASE_NUM[base_name])
        return bytes(out)

    def data_bytes(self, values: dict[int, int]) -> bytes:
        out = bytearray()
        out.append(self.local_type)  # data message header (definition bit clear)
        for field_num, base_name in self.fields:
            fmt, _ = _BASE[base_name]
            out += struct.pack("<" + fmt, values[field_num])
        return bytes(out)


def build_sample_fit(start: _dt.datetime | None = None, n_records: int = 12) -> bytes:
    """Build a small valid FIT file for a short running activity."""
    start = start or _dt.datetime(2023, 6, 15, 8, 0, 0, tzinfo=_dt.timezone.utc)

    body = bytearray()

    # --- file_id (global 0) -------------------------------------------------
    file_id = _Message(0, 0, [
        (0, "enum"),    # type: 4 = activity
        (1, "uint16"),  # manufacturer: 1 = garmin
        (2, "uint16"),  # garmin product
        (4, "uint32"),  # time_created
    ])
    body += file_id.definition_bytes()
    body += file_id.data_bytes({0: 4, 1: 1, 2: 2697, 4: fit_timestamp(start)})

    # --- record (global 20) -------------------------------------------------
    record = _Message(3, 20, [
        (253, "uint32"),  # timestamp
        (0, "sint32"),    # position_lat (semicircles)
        (1, "sint32"),    # position_long
        (2, "uint16"),    # altitude raw = (m + 500) * 5
        (3, "uint8"),     # heart_rate
        (4, "uint8"),     # cadence
        (5, "uint32"),    # distance raw = m * 100
        (6, "uint16"),    # speed raw = m/s * 1000
        (7, "uint16"),    # power
        (13, "sint8"),    # temperature (C)
    ])
    body += record.definition_bytes()

    base_lat, base_lon = 51.5007, -0.1246  # near London
    for i in range(n_records):
        ts = start + _dt.timedelta(seconds=10 * i)
        lat = base_lat + i * 0.00025
        lon = base_lon + i * 0.00015
        alt_m = 35 + i  # metres
        dist_m = 28.0 * i  # metres (cumulative, ~2.8 m/s)
        body += record.data_bytes({
            253: fit_timestamp(ts),
            0: semicircles(lat),
            1: semicircles(lon),
            2: int((alt_m + 500) * 5),
            3: 120 + i,                 # bpm
            4: 80 + (i % 5),            # rpm
            5: int(dist_m * 100),
            6: int(2.8 * 1000),         # m/s
            7: 210 + i,                 # W
            13: 21,                     # deg C
        })

    duration_s = 10 * (n_records - 1)
    total_distance_m = 28.0 * (n_records - 1)

    # --- lap (global 19) ----------------------------------------------------
    lap = _Message(2, 19, [
        (253, "uint32"),  # timestamp
        (2, "uint32"),    # start_time
        (7, "uint32"),    # total_elapsed_time (s*1000)
        (8, "uint32"),    # total_timer_time (s*1000)
        (9, "uint32"),    # total_distance (m*100)
        (11, "uint16"),   # total_calories
        (13, "uint16"),   # avg_speed (m/s*1000)
        (14, "uint16"),   # max_speed
        (15, "uint8"),    # avg_heart_rate
        (16, "uint8"),    # max_heart_rate
        (21, "uint16"),   # total_ascent
        (22, "uint16"),   # total_descent
    ])
    body += lap.definition_bytes()
    body += lap.data_bytes({
        253: fit_timestamp(start + _dt.timedelta(seconds=duration_s)),
        2: fit_timestamp(start),
        7: duration_s * 1000,
        8: duration_s * 1000,
        9: int(total_distance_m * 100),
        11: 45,
        13: int(2.8 * 1000),
        14: int(3.4 * 1000),
        15: 126,
        16: 131,
        21: 11,
        22: 0,
    })

    # --- session (global 18) ------------------------------------------------
    session = _Message(1, 18, [
        (253, "uint32"),  # timestamp
        (2, "uint32"),    # start_time
        (3, "sint32"),    # start_position_lat
        (4, "sint32"),    # start_position_long
        (5, "enum"),      # sport: 1 = running
        (6, "enum"),      # sub_sport
        (7, "uint32"),    # total_elapsed_time
        (8, "uint32"),    # total_timer_time
        (9, "uint32"),    # total_distance
        (11, "uint16"),   # total_calories
        (14, "uint16"),   # avg_speed
        (15, "uint16"),   # max_speed
        (16, "uint8"),    # avg_heart_rate
        (17, "uint8"),    # max_heart_rate
        (18, "uint8"),    # avg_cadence
        (20, "uint16"),   # avg_power
        (22, "uint16"),   # total_ascent
        (23, "uint16"),   # total_descent
        (57, "sint8"),    # avg_temperature
    ])
    body += session.definition_bytes()
    body += session.data_bytes({
        253: fit_timestamp(start + _dt.timedelta(seconds=duration_s)),
        2: fit_timestamp(start),
        3: semicircles(base_lat),
        4: semicircles(base_lon),
        5: 1,
        6: 0,
        7: duration_s * 1000,
        8: duration_s * 1000,
        9: int(total_distance_m * 100),
        11: 45,
        14: int(2.8 * 1000),
        15: int(3.4 * 1000),
        16: 126,
        17: 131,
        18: 82,
        20: 215,
        22: 11,
        23: 0,
        57: 21,
    })

    # --- header (12 bytes) + CRC -------------------------------------------
    header = bytearray()
    header.append(12)            # header size
    header.append(0x10)          # protocol version 1.0
    header += struct.pack("<H", 2078)   # profile version
    header += struct.pack("<I", len(body))
    header += b".FIT"

    file_bytes = bytes(header) + bytes(body)
    crc = fit_crc(file_bytes)
    return file_bytes + struct.pack("<H", crc)


def write_sample(path: str | Path) -> Path:
    path = Path(path)
    path.write_bytes(build_sample_fit())
    return path


if __name__ == "__main__":
    out = write_sample(Path(__file__).with_name("sample.fit"))
    print(f"wrote {out} ({out.stat().st_size} bytes)")

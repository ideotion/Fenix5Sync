# SPDX-License-Identifier: GPL-3.0-or-later
"""FIT Salvage: recover activities from corrupt or truncated ``.FIT`` files.

The disaster every Garmin owner fears: the watch reboots on save and leaves an
activity file that won't import anywhere. Existing fixes are Windows-only, paid,
or web services you upload your private GPS track to. This recovers as much as is
readable, **locally and offline**, preserving your original untouched.

How it works (no third-party dependency):

1. Walk the FIT record stream with a minimal decoder (definition/data messages,
   compressed-timestamp headers and developer fields), stopping at the first
   record that can't be fully read -- the truncation point.
2. Rebuild a valid file from the complete-record prefix: a fresh 12-byte header
   with a corrected ``data_size`` and a recomputed CRC-16 (the two things a
   crash usually corrupts).
3. Re-parse the repaired bytes with the normal parser, which derives the summary
   from the records when the truncated file lost its session/lap trailer.

Salvage is inherently best-effort: it never presents a guess as ground truth and
reports exactly how much was recovered and why it stopped. The lossless original
is never modified; the recovered file is a separate, clearly-labelled derivative.
"""

from __future__ import annotations

import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .models import Activity
from .parse import ParseError, parse_fit_file

_FIT_MAGIC = b".FIT"

# Standard FIT CRC-16 (same routine the format uses for its own trailer).
_CRC_TABLE = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)


def fit_crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc & 0xFFFF


@dataclass
class SalvageReport:
    """Outcome of a salvage attempt (recovery is best-effort, never guaranteed)."""

    ok: bool                       # a usable repaired file was produced
    reason: str                    # complete | truncated | corrupt | no-header | empty
    bytes_total: int
    bytes_recovered: int           # record bytes kept
    records_recovered: int
    declared_data_size: int        # what the header claimed
    repaired: bytes | None = None  # rebuilt valid FIT bytes (None if unrecoverable)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "bytes_total": self.bytes_total,
            "bytes_recovered": self.bytes_recovered,
            "records_recovered": self.records_recovered,
            "declared_data_size": self.declared_data_size,
            "recovery_pct": (
                round(100.0 * self.bytes_recovered / self.declared_data_size, 1)
                if self.declared_data_size else 0.0
            ),
        }


def _read_header(data: bytes) -> tuple[int, int] | None:
    """Return (header_size, declared_data_size) if this looks like FIT, else None."""
    if len(data) < 12:
        return None
    header_size = data[0]
    if header_size < 12 or len(data) < header_size:
        return None
    if data[8:12] != _FIT_MAGIC:
        return None
    declared = struct.unpack("<I", data[4:8])[0]
    return header_size, declared


def _scan_records(data: bytes, start: int, end: int) -> tuple[int, int, str]:
    """Walk records in ``data[start:end]``; return (boundary, count, reason).

    ``boundary`` is the offset just past the last *complete* record. ``reason`` is
    "complete" if we consumed the whole region cleanly, "truncated" if a record
    ran past the available bytes, or "corrupt" on a malformed/unknown record.
    """
    defs: dict[int, int] = {}  # local message type -> data message length
    pos = start
    count = 0
    while pos < end:
        header = data[pos]
        if header & 0x80:  # compressed-timestamp header: a data message
            local = (header >> 5) & 0x3
            if local not in defs:
                return pos, count, "corrupt"
            rec_len = 1 + defs[local]
            if pos + rec_len > end:
                return pos, count, "truncated"
            pos += rec_len
            count += 1
            continue

        is_def = bool(header & 0x40)
        has_dev = bool(header & 0x20)
        local = header & 0x0F
        if is_def:
            if pos + 6 > end:
                return pos, count, "truncated"
            num_fields = data[pos + 5]
            fields_start = pos + 6
            fields_end = fields_start + num_fields * 3
            if fields_end > end:
                return pos, count, "truncated"
            data_len = sum(data[fields_start + 3 * i + 1] for i in range(num_fields))
            cursor = fields_end
            if has_dev:
                if cursor + 1 > end:
                    return pos, count, "truncated"
                num_dev = data[cursor]
                dev_start = cursor + 1
                dev_end = dev_start + num_dev * 3
                if dev_end > end:
                    return pos, count, "truncated"
                data_len += sum(data[dev_start + 3 * i + 1] for i in range(num_dev))
                cursor = dev_end
            defs[local] = data_len
            pos = cursor
            count += 1
        else:
            if local not in defs:
                return pos, count, "corrupt"
            rec_len = 1 + defs[local]
            if pos + rec_len > end:
                return pos, count, "truncated"
            pos += rec_len
            count += 1
    return pos, count, "complete"


def salvage_fit(data: bytes) -> SalvageReport:
    """Attempt to recover a corrupt/truncated FIT byte stream into a valid file."""
    if not data:
        return SalvageReport(False, "empty", 0, 0, 0, 0)
    head = _read_header(data)
    if head is None:
        return SalvageReport(False, "no-header", len(data), 0, 0, 0)
    header_size, declared = head

    # Scan the records region. For a truncated file the available bytes are fewer
    # than the header claims, so bound the walk by what's actually present.
    declared_end = header_size + declared
    scan_end = min(declared_end, len(data)) if declared else len(data)
    boundary, count, reason = _scan_records(data, header_size, scan_end)

    recovered_bytes = boundary - header_size
    # A definition with no data record yields nothing importable.
    if recovered_bytes <= 0:
        return SalvageReport(False, reason if reason != "complete" else "corrupt",
                             len(data), 0, count, declared)

    # Rebuild a clean 12-byte header + the complete-record prefix + a fresh CRC.
    new_header = bytearray(12)
    new_header[0] = 12
    new_header[1] = data[1]            # protocol version (preserved)
    new_header[2:4] = data[2:4]        # profile version (preserved)
    struct.pack_into("<I", new_header, 4, recovered_bytes)
    new_header[8:12] = _FIT_MAGIC
    repaired = bytes(new_header) + data[header_size:boundary]
    repaired += struct.pack("<H", fit_crc(repaired))

    return SalvageReport(
        ok=True, reason=reason, bytes_total=len(data), bytes_recovered=recovered_bytes,
        records_recovered=count, declared_data_size=declared, repaired=repaired,
    )


def salvage_fit_file(path: str | Path) -> tuple[SalvageReport, Activity | None]:
    """Salvage a FIT file on disk; also parse the repaired bytes for a preview.

    Returns the :class:`SalvageReport` and the recovered :class:`Activity` (or
    ``None`` if even the repaired bytes can't be parsed into something usable).
    The input file is only read, never written.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return SalvageReport(False, f"unreadable: {exc}", 0, 0, 0, 0), None

    report = salvage_fit(data)
    if not report.ok or report.repaired is None:
        return report, None

    # Parse the repaired bytes via the normal parser (writes to a temp file so the
    # original is untouched). It derives the summary from records if the session
    # trailer was lost to truncation.
    with tempfile.NamedTemporaryFile(suffix=".fit", delete=True) as tmp:
        tmp.write(report.repaired)
        tmp.flush()
        try:
            activity = parse_fit_file(tmp.name, raw_path=str(path))
        except ParseError:
            activity = None
    return report, activity

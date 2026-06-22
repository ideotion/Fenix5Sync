# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal RFC 5545 (iCalendar) writer — stdlib only, offline.

Just enough to export a coach training plan as a ``.ics`` a calendar app can
import: a ``VCALENDAR`` with one all-day ``VEVENT`` per session (``DTSTART`` as a
DATE, ``SUMMARY``, ``DESCRIPTION``, ``UID``, ``DTSTAMP``), CRLF line endings and
content-line folding. No timezones, alarms or recurrence — a flat dated agenda.

The text-escaping and folding follow RFC 5545 §3.1/§3.3.11 so the output parses
in standard clients; :func:`parse_calendar` is a small inverse used by the tests
to round-trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

PRODID = "-//Fenix5Sync//Coach Plan//EN"
_MAX_OCTETS = 73  # fold below the 75-octet limit, leaving room for CRLF+space


@dataclass(frozen=True)
class IcsEvent:
    """One all-day calendar event."""

    uid: str
    day: date
    summary: str
    description: str = ""


def _ascii(text: str) -> str:
    """Keep content ASCII so octet folding can never split a multibyte char."""
    return (text.replace("–", "-").replace("—", "-")
            .replace("‘", "'").replace("’", "'")
            .replace("“", '"').replace("”", '"')
            .encode("ascii", "replace").decode("ascii"))


def _escape(text: str) -> str:
    """Escape per RFC 5545 §3.3.11 (TEXT): backslash, semicolon, comma, newlines."""
    return (_ascii(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Fold a content line to <=75 octets with CRLF + a leading space (§3.1)."""
    if len(line) <= _MAX_OCTETS:
        return line
    out, rest = [line[:_MAX_OCTETS]], line[_MAX_OCTETS:]
    while rest:
        out.append(" " + rest[: _MAX_OCTETS - 1])
        rest = rest[_MAX_OCTETS - 1:]
    return "\r\n".join(out)


def _stamp(now: datetime | None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def write_calendar(events: list[IcsEvent], *, now: datetime | None = None) -> str:
    """Serialize events to a complete VCALENDAR string (CRLF-terminated lines)."""
    dtstamp = _stamp(now)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for ev in events:
        lines.extend([
            "BEGIN:VEVENT",
            _fold(f"UID:{_ascii(ev.uid)}"),
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{ev.day.strftime('%Y%m%d')}",
            _fold(f"SUMMARY:{_escape(ev.summary)}"),
            _fold(f"DESCRIPTION:{_escape(ev.description)}"),
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def parse_calendar(text: str) -> list[dict]:
    """Tiny inverse of :func:`write_calendar` (unfold + read VEVENTs) for tests."""
    unfolded = re.sub(r"\r\n[ \t]", "", text)
    events: list[dict] = []
    cur: dict | None = None
    for raw in unfolded.split("\r\n"):
        if raw == "BEGIN:VEVENT":
            cur = {}
        elif raw == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in raw:
            key, val = raw.split(":", 1)
            name = key.split(";", 1)[0]
            cur[name] = (val.replace("\\n", "\n").replace("\\,", ",")
                         .replace("\\;", ";").replace("\\\\", "\\"))
    return events

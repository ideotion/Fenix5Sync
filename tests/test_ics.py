# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the minimal RFC 5545 iCalendar writer (core/ics.py)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from core.ics import IcsEvent, parse_calendar, write_calendar


def _events():
    return [
        IcsEvent(uid="a@fenix5sync", day=date(2026, 7, 1), summary="Easy run - 40 min",
                 description="Easy aerobic; conversational.\nTarget: 5:30/km · RPE 3-4/10"),
        IcsEvent(uid="b@fenix5sync", day=date(2026, 7, 3), summary="Intervals",
                 description="6x800m; semicolons; commas, and \\ backslashes."),
    ]


def test_calendar_has_envelope_and_one_event_each():
    ics = write_calendar(_events(), now=datetime(2026, 6, 22, 15, 0, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.rstrip().endswith("END:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") == 2 and ics.count("END:VEVENT") == 2
    assert "VERSION:2.0" in ics and "PRODID:-//Fenix5Sync//Coach Plan//EN" in ics


def test_lines_are_crlf_terminated():
    ics = write_calendar(_events())
    # Every line ends with CRLF; no bare LF.
    assert "\n" in ics and ics.replace("\r\n", "").count("\n") == 0


def test_dtstart_is_an_all_day_date():
    ics = write_calendar(_events())
    assert "DTSTART;VALUE=DATE:20260701" in ics
    assert "DTSTART;VALUE=DATE:20260703" in ics
    assert "DTSTAMP:" in ics


def test_text_is_escaped_and_round_trips():
    ics = write_calendar(_events())
    parsed = parse_calendar(ics)
    assert len(parsed) == 2
    assert parsed[0]["UID"] == "a@fenix5sync"
    assert parsed[0]["SUMMARY"] == "Easy run - 40 min"
    # Newlines, semicolons, commas and backslashes survive the round-trip.
    assert "\n" in parsed[0]["DESCRIPTION"]
    assert "semicolons; commas, and \\ backslashes." in parsed[1]["DESCRIPTION"]


def test_long_lines_are_folded_under_75_octets():
    long_desc = "word " * 60  # ~300 chars, must fold
    ics = write_calendar([IcsEvent(uid="x", day=date(2026, 1, 1), summary="s", description=long_desc)])
    for line in ics.split("\r\n"):
        assert len(line) <= 75, f"unfolded line too long: {len(line)}"
    # And it still round-trips back to the original text.
    parsed = parse_calendar(ics)
    assert parsed[0]["DESCRIPTION"].strip() == long_desc.strip()

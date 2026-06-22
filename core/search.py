# SPDX-License-Identifier: GPL-3.0-or-later
"""Activity search/filtering.

Pure SQL-fragment construction (no database handle), so it is trivially testable
and reusable. :class:`ActivityFilter` captures the supported predicates; the
store executes the resulting ``WHERE`` clause.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Columns that may be sorted on (whitelist guards against SQL injection via the
# sort parameter, which can come from the API query string).
SORTABLE = {
    "start_time",
    "sport",
    "total_distance",
    "total_timer_time",
    "total_elapsed_time",
    "avg_heart_rate",
    "total_calories",
    "imported_at",
    "id",
}


@dataclass
class ActivityFilter:
    """Search predicates. ``None`` fields are ignored."""

    date_from: str | None = None  # ISO date/datetime, inclusive lower bound
    date_to: str | None = None  # ISO date/datetime, inclusive upper bound
    sport: str | None = None  # exact sport match (case-insensitive)
    min_distance: float | None = None  # metres
    max_distance: float | None = None  # metres
    min_duration: float | None = None  # seconds (timer time)
    max_duration: float | None = None  # seconds (timer time)
    sort: str = "start_time"
    order: str = "desc"  # asc | desc
    limit: int | None = None
    offset: int = 0

    def normalised_sort(self) -> str:
        return self.sort if self.sort in SORTABLE else "start_time"

    def normalised_order(self) -> str:
        return "ASC" if str(self.order).lower() == "asc" else "DESC"


def build_where(f: ActivityFilter) -> tuple[str, list[Any]]:
    """Build a parameterised ``WHERE`` clause for an :class:`ActivityFilter`.

    Returns ``("", [])`` when no predicates are set.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if f.date_from:
        clauses.append("start_time >= ?")
        params.append(f.date_from)
    if f.date_to:
        # Make the upper bound inclusive of the whole day when only a date is
        # given by appending a high time component.
        upper = f.date_to
        if len(upper) == 10:  # "YYYY-MM-DD"
            upper = upper + "T23:59:59.999999"
        clauses.append("start_time <= ?")
        params.append(upper)
    if f.sport:
        clauses.append("LOWER(sport) = LOWER(?)")
        params.append(f.sport)
    if f.min_distance is not None:
        clauses.append("total_distance >= ?")
        params.append(f.min_distance)
    if f.max_distance is not None:
        clauses.append("total_distance <= ?")
        params.append(f.max_distance)
    if f.min_duration is not None:
        clauses.append("total_timer_time >= ?")
        params.append(f.min_duration)
    if f.max_duration is not None:
        clauses.append("total_timer_time <= ?")
        params.append(f.max_duration)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params

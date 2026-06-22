# SPDX-License-Identifier: GPL-3.0-or-later
"""SQLite persistence for activities, laps, trackpoints and the import ledger.

Writes are atomic (one transaction per activity) so a crash mid-import never
leaves a half-written activity. Raw ``.FIT`` files are kept on disk alongside the
DB (see :mod:`core.pipeline`) so re-parsing is always possible and nothing is
lossy. The schema is indexed for search by date, sport, distance and duration.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .models import Activity, Lap, Trackpoint
from .search import ActivityFilter, build_where

if TYPE_CHECKING:
    from .segments import Segment

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash           TEXT NOT NULL UNIQUE,
    raw_path            TEXT NOT NULL,
    sport               TEXT,
    sub_sport           TEXT,
    start_time          TEXT,
    total_timer_time    REAL,
    total_elapsed_time  REAL,
    total_distance      REAL,
    total_calories      INTEGER,
    avg_heart_rate      INTEGER,
    max_heart_rate      INTEGER,
    avg_speed           REAL,
    max_speed           REAL,
    avg_cadence         INTEGER,
    avg_power           INTEGER,
    avg_temperature     REAL,
    total_ascent        INTEGER,
    total_descent       INTEGER,
    start_latitude      REAL,
    start_longitude     REAL,
    device_manufacturer TEXT,
    device_product      TEXT,
    extra               TEXT,
    imported_at         TEXT
);

CREATE TABLE IF NOT EXISTS laps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id         INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    lap_index           INTEGER,
    start_time          TEXT,
    total_timer_time    REAL,
    total_elapsed_time  REAL,
    total_distance      REAL,
    avg_heart_rate      INTEGER,
    max_heart_rate      INTEGER,
    avg_speed           REAL,
    max_speed           REAL,
    total_ascent        INTEGER,
    total_descent       INTEGER,
    total_calories      INTEGER,
    extra               TEXT
);

CREATE TABLE IF NOT EXISTS trackpoints (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id  INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    seq          INTEGER,
    timestamp    TEXT,
    latitude     REAL,
    longitude    REAL,
    heart_rate   INTEGER,
    cadence      INTEGER,
    speed        REAL,
    altitude     REAL,
    distance     REAL,
    temperature  REAL,
    power        INTEGER,
    extra        TEXT
);

CREATE TABLE IF NOT EXISTS import_ledger (
    file_hash   TEXT PRIMARY KEY,
    filename    TEXT,
    status      TEXT,
    detail      TEXT,
    imported_at TEXT,
    activity_id INTEGER
);

CREATE TABLE IF NOT EXISTS wellness_days (
    date           TEXT PRIMARY KEY,
    steps          INTEGER,
    resting_hr     INTEGER,
    avg_hr         INTEGER,
    max_hr         INTEGER,
    avg_stress     INTEGER,
    stress_samples INTEGER,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL,
    sport              TEXT,
    radius_m           REAL,
    distance_m         REAL,
    waypoints          TEXT NOT NULL,
    source_activity_id INTEGER,
    created_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_activities_start_time ON activities(start_time);
CREATE INDEX IF NOT EXISTS idx_activities_sport      ON activities(sport);
CREATE INDEX IF NOT EXISTS idx_activities_distance   ON activities(total_distance);
CREATE INDEX IF NOT EXISTS idx_activities_duration   ON activities(total_timer_time);
CREATE INDEX IF NOT EXISTS idx_trackpoints_activity  ON trackpoints(activity_id, seq);
CREATE INDEX IF NOT EXISTS idx_laps_activity         ON laps(activity_id, lap_index);
"""

# Columns persisted for an activity, in order (excludes the autoincrement id).
_ACTIVITY_COLS = [
    "file_hash", "raw_path", "sport", "sub_sport", "start_time",
    "total_timer_time", "total_elapsed_time", "total_distance", "total_calories",
    "avg_heart_rate", "max_heart_rate", "avg_speed", "max_speed", "avg_cadence",
    "avg_power", "avg_temperature", "total_ascent", "total_descent",
    "start_latitude", "start_longitude", "device_manufacturer", "device_product",
    "extra", "imported_at",
]

_LAP_COLS = [
    "activity_id", "lap_index", "start_time", "total_timer_time",
    "total_elapsed_time", "total_distance", "avg_heart_rate", "max_heart_rate",
    "avg_speed", "max_speed", "total_ascent", "total_descent", "total_calories",
    "extra",
]

_TP_COLS = [
    "activity_id", "seq", "timestamp", "latitude", "longitude", "heart_rate",
    "cadence", "speed", "altitude", "distance", "temperature", "power", "extra",
]


def _dt_to_iso(value: _dt.datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, _dt.datetime) else value


def _iso_to_dt(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _longest_daily_streak(days: list[str]) -> int:
    """Longest run of consecutive calendar days from sorted distinct ``YYYY-MM-DD``."""
    if not days:
        return 0
    parsed = [_dt.date.fromisoformat(d) for d in days]
    longest = run = 1
    for prev, cur in zip(parsed, parsed[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    return longest


class Store:
    """A SQLite-backed activity store.

    Usable as a context manager::

        with Store(db_path) as store:
            store.add_activity(activity)
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.init_schema()

    # ---- lifecycle ---------------------------------------------------------
    def init_schema(self) -> None:
        """Create tables and indexes if absent (idempotent)."""
        with self.conn:
            self.conn.executescript(_SCHEMA)
            self.conn.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES('version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- ledger / dedupe ---------------------------------------------------
    def is_imported(self, file_hash: str) -> bool:
        """True if this content hash has already been imported successfully."""
        row = self.conn.execute(
            "SELECT 1 FROM activities WHERE file_hash = ? LIMIT 1", (file_hash,)
        ).fetchone()
        return row is not None

    def ledger_status(self, file_hash: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM import_ledger WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return row["status"] if row else None

    def record_ledger(
        self,
        file_hash: str,
        filename: str,
        status: str,
        detail: str = "",
        activity_id: int | None = None,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO import_ledger
                       (file_hash, filename, status, detail, imported_at, activity_id)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_hash) DO UPDATE SET
                       filename=excluded.filename, status=excluded.status,
                       detail=excluded.detail, imported_at=excluded.imported_at,
                       activity_id=excluded.activity_id""",
                (
                    file_hash,
                    filename,
                    status,
                    detail,
                    _dt.datetime.now(_dt.timezone.utc).isoformat(),
                    activity_id,
                ),
            )

    # ---- writes ------------------------------------------------------------
    def add_activity(self, activity: Activity) -> int:
        """Persist an activity with its laps and trackpoints atomically.

        Returns the new activity id (also set on ``activity.id``). The whole
        write is a single transaction: it either fully lands or not at all.
        """
        if activity.imported_at is None:
            activity.imported_at = _dt.datetime.now(_dt.timezone.utc)

        with self.conn:  # transaction: commit on success, rollback on error
            cur = self.conn.execute(
                f"INSERT INTO activities ({', '.join(_ACTIVITY_COLS)}) "
                f"VALUES ({', '.join('?' for _ in _ACTIVITY_COLS)})",
                self._activity_row(activity),
            )
            activity_id = int(cur.lastrowid)
            activity.id = activity_id

            if activity.laps:
                self.conn.executemany(
                    f"INSERT INTO laps ({', '.join(_LAP_COLS)}) "
                    f"VALUES ({', '.join('?' for _ in _LAP_COLS)})",
                    [self._lap_row(activity_id, lap) for lap in activity.laps],
                )
            if activity.trackpoints:
                self.conn.executemany(
                    f"INSERT INTO trackpoints ({', '.join(_TP_COLS)}) "
                    f"VALUES ({', '.join('?' for _ in _TP_COLS)})",
                    [
                        self._tp_row(activity_id, seq, tp)
                        for seq, tp in enumerate(activity.trackpoints)
                    ],
                )
            # Record the ledger entry inside the same transaction.
            self.conn.execute(
                """INSERT INTO import_ledger
                       (file_hash, filename, status, detail, imported_at, activity_id)
                   VALUES (?, ?, 'imported', '', ?, ?)
                   ON CONFLICT(file_hash) DO UPDATE SET
                       status='imported', imported_at=excluded.imported_at,
                       activity_id=excluded.activity_id""",
                (
                    activity.file_hash,
                    Path(activity.raw_path).name,
                    activity.imported_at.isoformat(),
                    activity_id,
                ),
            )
        return activity_id

    # ---- reads -------------------------------------------------------------
    def get_activity(self, activity_id: int, with_series: bool = True) -> Activity | None:
        row = self.conn.execute(
            "SELECT * FROM activities WHERE id = ?", (activity_id,)
        ).fetchone()
        if row is None:
            return None
        activity = self._row_to_activity(row)
        activity.laps = self._laps_for(activity_id)
        if with_series:
            activity.trackpoints = self._trackpoints_for(activity_id)
        return activity

    def get_activity_by_hash(self, file_hash: str) -> Activity | None:
        row = self.conn.execute(
            "SELECT id FROM activities WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return self.get_activity(int(row["id"])) if row else None

    def search(self, f: ActivityFilter) -> list[Activity]:
        """Return summary activities (no trackpoints) matching the filter."""
        where, params = build_where(f)
        sql = (
            f"SELECT * FROM activities{where} "
            f"ORDER BY {f.normalised_sort()} {f.normalised_order()}"
        )
        if f.limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = [*params, int(f.limit), int(f.offset)]
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_activity(r) for r in rows]

    def count(self, f: ActivityFilter | None = None) -> int:
        where, params = build_where(f or ActivityFilter())
        row = self.conn.execute(
            f"SELECT COUNT(*) AS n FROM activities{where}", params
        ).fetchone()
        return int(row["n"])

    def all_activities(self, with_series: bool = False) -> list[Activity]:
        """Every activity (for bulk export). Series included only if requested."""
        ids = [int(r["id"]) for r in self.conn.execute(
            "SELECT id FROM activities ORDER BY start_time"
        ).fetchall()]
        return [self.get_activity(i, with_series=with_series) for i in ids]  # type: ignore[misc]

    def sports(self) -> list[str]:
        """Distinct sports present, for populating filter dropdowns."""
        rows = self.conn.execute(
            "SELECT DISTINCT sport FROM activities WHERE sport IS NOT NULL ORDER BY sport"
        ).fetchall()
        return [r["sport"] for r in rows]

    # ---- wellness (monitoring-derived daily summaries) --------------------
    def add_wellness_days(self, days: Iterable[dict]) -> int:
        """Upsert daily wellness summaries (keyed by date); returns the count."""
        rows = list(days)
        if not rows:
            return 0
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        with self.conn:
            for d in rows:
                self.conn.execute(
                    """INSERT INTO wellness_days
                           (date, steps, resting_hr, avg_hr, max_hr, avg_stress, stress_samples, updated_at)
                       VALUES (:date, :steps, :resting_hr, :avg_hr, :max_hr, :avg_stress, :stress_samples, :updated_at)
                       ON CONFLICT(date) DO UPDATE SET
                           steps=excluded.steps, resting_hr=excluded.resting_hr, avg_hr=excluded.avg_hr,
                           max_hr=excluded.max_hr, avg_stress=excluded.avg_stress,
                           stress_samples=excluded.stress_samples, updated_at=excluded.updated_at""",
                    {
                        "date": d.get("date"), "steps": d.get("steps"),
                        "resting_hr": d.get("resting_hr"), "avg_hr": d.get("avg_hr"),
                        "max_hr": d.get("max_hr"), "avg_stress": d.get("avg_stress"),
                        "stress_samples": d.get("stress_samples"), "updated_at": now,
                    },
                )
        return len(rows)

    def all_wellness_days(self) -> list[dict]:
        """Every stored daily wellness summary, chronological."""
        rows = self.conn.execute(
            "SELECT date, steps, resting_hr, avg_hr, max_hr, avg_stress, stress_samples "
            "FROM wellness_days ORDER BY date"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- personal segments -------------------------------------------------
    def add_segment(self, segment: "Segment") -> int:
        """Persist a user-defined segment; returns its new id (also set on it)."""
        cur = self.conn.execute(
            """INSERT INTO segments
                   (name, sport, radius_m, distance_m, waypoints, source_activity_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                segment.name, segment.sport, segment.radius_m, segment.distance_m,
                json.dumps([[la, lo] for la, lo in segment.waypoints]),
                segment.source_activity_id,
                _dt.datetime.now(_dt.timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        segment.id = int(cur.lastrowid)
        return segment.id

    @staticmethod
    def _row_to_segment(row) -> "Segment":
        from .segments import Segment
        return Segment(
            id=int(row["id"]),
            name=row["name"],
            sport=row["sport"],
            radius_m=row["radius_m"],
            distance_m=row["distance_m"],
            waypoints=[(float(la), float(lo)) for la, lo in json.loads(row["waypoints"])],
            source_activity_id=row["source_activity_id"],
        )

    def list_segments(self) -> list["Segment"]:
        rows = self.conn.execute(
            "SELECT * FROM segments ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [self._row_to_segment(r) for r in rows]

    def get_segment(self, segment_id: int) -> "Segment | None":
        row = self.conn.execute(
            "SELECT * FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()
        return self._row_to_segment(row) if row else None

    def delete_segment(self, segment_id: int) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM segments WHERE id = ?", (segment_id,))
        return cur.rowcount > 0

    def summary_stats(self) -> dict[str, Any]:
        """Aggregate totals for the dashboard header."""
        row = self.conn.execute(
            """SELECT COUNT(*) AS count,
                      COALESCE(SUM(total_distance), 0) AS total_distance,
                      COALESCE(SUM(total_timer_time), 0) AS total_duration
               FROM activities"""
        ).fetchone()
        return {
            "count": int(row["count"]),
            "total_distance": float(row["total_distance"]),
            "total_duration": float(row["total_duration"]),
        }

    # ---- insights / analytics ---------------------------------------------
    def _record(self, where: str, params: list, col: str, threshold_sql: str = "") -> dict | None:
        """Top activity by ``col`` (the activity with the max value), or None."""
        row = self.conn.execute(
            f"SELECT id, start_time, sport, {col} AS v FROM activities{where} "
            f"AND {col} IS NOT NULL{threshold_sql} ORDER BY {col} DESC LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "start_time": row["start_time"],
            "sport": row["sport"],
            "value": float(row["v"]),
        }

    def insights(self, sport: str | None = None) -> dict[str, Any]:
        """Aggregate analytics over the local store (totals, trends, PRs, calendar).

        Computed entirely in SQLite (no network). Pass ``sport`` to scope every
        figure to a single sport. Timestamps are ISO strings, so grouping uses
        ``substr`` over ``start_time`` (year/month/day prefixes).
        """
        where = " WHERE start_time IS NOT NULL"
        params: list = []
        if sport:
            where += " AND sport = ?"
            params.append(sport)

        totals = self.conn.execute(
            f"""SELECT COUNT(*) n,
                       COALESCE(SUM(total_distance), 0) dist,
                       COALESCE(SUM(total_timer_time), 0) dur,
                       COALESCE(SUM(total_ascent), 0) ascent,
                       COALESCE(SUM(total_calories), 0) cal
                FROM activities{where}""",
            params,
        ).fetchone()

        by_month = [
            {"month": r["m"], "count": int(r["n"]), "distance_m": float(r["dist"]),
             "duration_s": float(r["dur"]), "ascent_m": float(r["ascent"])}
            for r in self.conn.execute(
                f"""SELECT substr(start_time, 1, 7) m, COUNT(*) n,
                           COALESCE(SUM(total_distance), 0) dist,
                           COALESCE(SUM(total_timer_time), 0) dur,
                           COALESCE(SUM(total_ascent), 0) ascent
                    FROM activities{where} GROUP BY m ORDER BY m""",
                params,
            )
        ]

        by_sport = [
            {"sport": r["sport"] or "unknown", "count": int(r["n"]),
             "distance_m": float(r["dist"]), "duration_s": float(r["dur"])}
            for r in self.conn.execute(
                f"""SELECT sport, COUNT(*) n,
                           COALESCE(SUM(total_distance), 0) dist,
                           COALESCE(SUM(total_timer_time), 0) dur
                    FROM activities{where} GROUP BY sport ORDER BY dist DESC""",
                params,
            )
        ]

        calendar = [
            {"date": r["d"], "count": int(r["n"]), "distance_m": float(r["dist"])}
            for r in self.conn.execute(
                f"""SELECT substr(start_time, 1, 10) d, COUNT(*) n,
                           COALESCE(SUM(total_distance), 0) dist
                    FROM activities{where} GROUP BY d ORDER BY d""",
                params,
            )
        ]

        days = [c["date"] for c in calendar]
        return {
            "sport": sport,
            "sports": self.sports(),
            "years": sorted({d[:4] for d in days}),
            "totals": {
                "count": int(totals["n"]),
                "distance_m": float(totals["dist"]),
                "duration_s": float(totals["dur"]),
                "ascent_m": float(totals["ascent"]),
                "calories": float(totals["cal"]),
                "active_days": len(days),
                "longest_streak_days": _longest_daily_streak(days),
            },
            "by_month": by_month,
            "by_sport": by_sport,
            "calendar": calendar,
            "records": {
                "longest_distance": self._record(where, params, "total_distance"),
                "longest_duration": self._record(where, params, "total_timer_time"),
                "most_ascent": self._record(where, params, "total_ascent"),
                "fastest_avg_speed": self._record(
                    where, params, "avg_speed", " AND total_distance > 1000"
                ),
            },
        }

    # ---- row mapping helpers ----------------------------------------------
    def _laps_for(self, activity_id: int) -> list[Lap]:
        rows = self.conn.execute(
            "SELECT * FROM laps WHERE activity_id = ? ORDER BY lap_index", (activity_id,)
        ).fetchall()
        return [
            Lap(
                lap_index=r["lap_index"],
                start_time=_iso_to_dt(r["start_time"]),
                total_timer_time=r["total_timer_time"],
                total_elapsed_time=r["total_elapsed_time"],
                total_distance=r["total_distance"],
                avg_heart_rate=r["avg_heart_rate"],
                max_heart_rate=r["max_heart_rate"],
                avg_speed=r["avg_speed"],
                max_speed=r["max_speed"],
                total_ascent=r["total_ascent"],
                total_descent=r["total_descent"],
                total_calories=r["total_calories"],
                extra=_loads(r["extra"]),
            )
            for r in rows
        ]

    def _trackpoints_for(self, activity_id: int) -> list[Trackpoint]:
        rows = self.conn.execute(
            "SELECT * FROM trackpoints WHERE activity_id = ? ORDER BY seq", (activity_id,)
        ).fetchall()
        return [
            Trackpoint(
                timestamp=_iso_to_dt(r["timestamp"]),
                latitude=r["latitude"],
                longitude=r["longitude"],
                heart_rate=r["heart_rate"],
                cadence=r["cadence"],
                speed=r["speed"],
                altitude=r["altitude"],
                distance=r["distance"],
                temperature=r["temperature"],
                power=r["power"],
                extra=_loads(r["extra"]),
            )
            for r in rows
        ]

    def _row_to_activity(self, r: sqlite3.Row) -> Activity:
        return Activity(
            id=r["id"],
            file_hash=r["file_hash"],
            raw_path=r["raw_path"],
            sport=r["sport"],
            sub_sport=r["sub_sport"],
            start_time=_iso_to_dt(r["start_time"]),
            total_timer_time=r["total_timer_time"],
            total_elapsed_time=r["total_elapsed_time"],
            total_distance=r["total_distance"],
            total_calories=r["total_calories"],
            avg_heart_rate=r["avg_heart_rate"],
            max_heart_rate=r["max_heart_rate"],
            avg_speed=r["avg_speed"],
            max_speed=r["max_speed"],
            avg_cadence=r["avg_cadence"],
            avg_power=r["avg_power"],
            avg_temperature=r["avg_temperature"],
            total_ascent=r["total_ascent"],
            total_descent=r["total_descent"],
            start_latitude=r["start_latitude"],
            start_longitude=r["start_longitude"],
            device_manufacturer=r["device_manufacturer"],
            device_product=r["device_product"],
            extra=_loads(r["extra"]),
            imported_at=_iso_to_dt(r["imported_at"]),
        )

    def _activity_row(self, a: Activity) -> tuple:
        return (
            a.file_hash, a.raw_path, a.sport, a.sub_sport, _dt_to_iso(a.start_time),
            a.total_timer_time, a.total_elapsed_time, a.total_distance, a.total_calories,
            a.avg_heart_rate, a.max_heart_rate, a.avg_speed, a.max_speed, a.avg_cadence,
            a.avg_power, a.avg_temperature, a.total_ascent, a.total_descent,
            a.start_latitude, a.start_longitude, a.device_manufacturer, a.device_product,
            json.dumps(a.extra), _dt_to_iso(a.imported_at),
        )

    def _lap_row(self, activity_id: int, lap: Lap) -> tuple:
        return (
            activity_id, lap.lap_index, _dt_to_iso(lap.start_time), lap.total_timer_time,
            lap.total_elapsed_time, lap.total_distance, lap.avg_heart_rate,
            lap.max_heart_rate, lap.avg_speed, lap.max_speed, lap.total_ascent,
            lap.total_descent, lap.total_calories, json.dumps(lap.extra),
        )

    def _tp_row(self, activity_id: int, seq: int, tp: Trackpoint) -> tuple:
        return (
            activity_id, seq, _dt_to_iso(tp.timestamp), tp.latitude, tp.longitude,
            tp.heart_rate, tp.cadence, tp.speed, tp.altitude, tp.distance,
            tp.temperature, tp.power, json.dumps(tp.extra),
        )

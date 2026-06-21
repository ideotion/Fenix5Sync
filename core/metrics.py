"""Per-activity performance metrics (pure, stdlib-only).

The advanced single-workout numbers serious athletes look at beyond the basic
summary -- grouped so the UI can show (or hide) each block honestly:

  * **intensity** -- Normalized Power (NP), Intensity Factor (IF = NP/FTP),
    Variability Index (VI = NP/avg) and TSS. Needs a power series; IF/TSS also
    need an FTP. NP is the 4th root of the mean of the 30-sample rolling-average
    power to the 4th power (Coggan).
  * **efficiency** -- Efficiency Factor (output per heartbeat) and **aerobic
    decoupling**, the drift in output:HR from the first to the second half of the
    workout. Low decoupling = a durable aerobic engine; it's the most useful
    single endurance signal you can get from one activity.
  * **pace** (running) -- average pace and **grade-adjusted pace** (GAP), using
    Minetti's metabolic cost-of-running-on-a-slope model so hilly and flat efforts
    compare fairly.
  * **dynamics** -- peak acceleration (from the speed derivative) and cadence.
  * **heart_rate** -- average / maximum and HR drift across the workout.
  * **environment** -- temperature average / min / max.

Honest-basis ethos (mirrors :mod:`core.zones` / :mod:`core.training_load`):
power-based figures need power; without it we fall back to pace-based equivalents
and record the ``basis``. ``needs`` lists thresholds (e.g. ``ftp_w``) that would
unlock more. Everything reads the activity's trackpoints, never modifies them,
and uses no third-party dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .config import AthleteConfig
from .models import Activity, Trackpoint

# Trackpoint gaps longer than this (seconds) are treated as a stop, so auto-pause
# and rests don't pollute rate-of-change metrics (matches core.zones).
_MAX_GAP_S = 30.0

# Normalized-power rolling window, in samples (~seconds at the typical 1 Hz rate).
_NP_WINDOW_S = 30

# Minetti et al. (2002) energy cost of running on a gradient i (rise/run),
# J/kg/m. The grade-adjustment factor is C(i)/C(0); C(0) is the flat cost.
_MINETTI = (155.4, -30.4, -43.3, 46.3, 19.5, 3.6)  # highest power first
_FLAT_COST = _MINETTI[-1]
# Clamp grades to a sane running range so noisy altitude can't explode GAP.
_MAX_GRADE = 0.45

# Sports for which a running-style pace / GAP block is meaningful.
_FOOT_SPORTS = {"running", "trail_running", "hiking", "walking"}


def _mean(values: Sequence[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _fractional_cadence(tp: Trackpoint) -> float:
    """The sub-unit cadence FIT keeps in ``extra`` (0 when absent)."""
    raw = tp.extra.get("fractional_cadence") if tp.extra else None
    value = raw.get("value") if isinstance(raw, dict) else raw
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _r(value: float | None, ndigits: int) -> float | None:
    return round(value, ndigits) if value is not None else None


def _normalized_power(powers: Sequence[float | int], window: int = _NP_WINDOW_S) -> float | None:
    """Normalized Power from a (roughly 1 Hz) power series, or None if empty.

    The 4th root of the mean of the ``window``-sample rolling-average power raised
    to the 4th power (Coggan). Series shorter than one window use a plain mean.
    """
    vals = [float(p) for p in powers if p is not None]
    n = len(vals)
    if n == 0:
        return None
    w = window if n >= window else n
    acc = sum(vals[:w])
    rolled = [acc / w]
    for i in range(w, n):
        acc += vals[i] - vals[i - w]
        rolled.append(acc / w)
    return (sum(r ** 4 for r in rolled) / len(rolled)) ** 0.25


def _grade_cost(grade: float) -> float:
    """Metabolic cost of running at gradient ``grade`` (Minetti polynomial)."""
    cost = 0.0
    for coef in _MINETTI:  # Horner evaluation, highest power first
        cost = cost * grade + coef
    return cost


def _half_split_drift(
    points: Sequence[Trackpoint], output: str
) -> float | None:
    """Percent drift in (output / HR) from the first to the second time-half.

    ``output`` is a Trackpoint attribute (``power`` or ``speed``). Positive means
    the ratio fell in the second half (HR rose relative to output) -- i.e. you
    decoupled / fatigued. Needs HR and the output in both halves.
    """
    rows = [
        (tp.timestamp, float(getattr(tp, output)), float(tp.heart_rate))
        for tp in points
        if tp.timestamp is not None
        and getattr(tp, output) is not None
        and tp.heart_rate
    ]
    if len(rows) < 4:
        return None
    midpoint = rows[0][0] + (rows[-1][0] - rows[0][0]) / 2
    first = [(o, h) for (t, o, h) in rows if t <= midpoint]
    second = [(o, h) for (t, o, h) in rows if t > midpoint]
    if not first or not second:
        return None

    def ratio(pairs: list[tuple[float, float]]) -> float | None:
        hr = _mean([h for _, h in pairs])
        out = _mean([o for o, _ in pairs])
        return (out / hr) if (hr and out is not None) else None

    r1, r2 = ratio(first), ratio(second)
    if not r1 or not r2:
        return None
    return (r1 - r2) / r1 * 100.0


def _max_acceleration(points: Sequence[Trackpoint]) -> float | None:
    """Largest positive speed change per second (m/s^2), ignoring gaps."""
    best: float | None = None
    prev_t = prev_v = None
    for tp in points:
        if tp.timestamp is None or tp.speed is None:
            prev_t = prev_v = None
            continue
        if prev_t is not None:
            dt = (tp.timestamp - prev_t).total_seconds()
            if 0.0 < dt <= _MAX_GAP_S:
                accel = (tp.speed - prev_v) / dt
                if best is None or accel > best:
                    best = accel
        prev_t, prev_v = tp.timestamp, tp.speed
    return best


def _grade_adjusted_speed(points: Sequence[Trackpoint]) -> float | None:
    """Time-weighted grade-adjusted speed (m/s), flat-equivalent, or None.

    Each segment's actual speed (distance/time) is scaled by ``C(grade)/C(0)`` so
    a slow climb counts as the faster flat speed it is equivalent to.
    """
    total_time = 0.0
    total_adj = 0.0
    prev = None
    for tp in points:
        if tp.timestamp is None or tp.distance is None:
            prev = None
            continue
        if prev is not None:
            dt = (tp.timestamp - prev.timestamp).total_seconds()
            dd = tp.distance - prev.distance
            if 0.0 < dt <= _MAX_GAP_S and dd > 0:
                speed = dd / dt
                grade = 0.0
                if prev.altitude is not None and tp.altitude is not None:
                    grade = (tp.altitude - prev.altitude) / dd
                    grade = max(-_MAX_GRADE, min(_MAX_GRADE, grade))
                total_adj += speed * (_grade_cost(grade) / _FLAT_COST) * dt
                total_time += dt
        prev = tp
    return (total_adj / total_time) if total_time > 0 else None


def _pace_s_per_km(speed_mps: float | None) -> int | None:
    return int(round(1000.0 / speed_mps)) if speed_mps and speed_mps > 0 else None


@dataclass
class ActivityMetrics:
    """A computed per-activity metric set, ready to serialise.

    Each group is either a populated dict or ``None`` when the data can't support
    it (so the UI can omit empty blocks). ``needs`` carries threshold hints.
    """

    intensity: dict | None
    efficiency: dict | None
    pace: dict | None
    dynamics: dict | None
    heart_rate: dict | None
    environment: dict | None
    needs: list[str]

    def as_dict(self) -> dict:
        groups = (self.intensity, self.efficiency, self.pace,
                  self.dynamics, self.heart_rate, self.environment)
        return {
            "available": any(g for g in groups),
            "intensity": self.intensity,
            "efficiency": self.efficiency,
            "pace": self.pace,
            "dynamics": self.dynamics,
            "heart_rate": self.heart_rate,
            "environment": self.environment,
            "needs": self.needs,
        }


def compute_activity_metrics(activity: Activity, athlete: AthleteConfig) -> dict:
    """Advanced metrics for one activity, using athlete thresholds where set.

    Power figures (NP/IF/VI/TSS) need a power series; IF/TSS also need
    ``athlete.ftp_w`` (flagged via ``needs``). Efficiency and decoupling fall back
    from power to pace when no power is recorded. The local archive is read-only.
    """
    pts = activity.trackpoints
    powers = [tp.power for tp in pts if tp.power is not None]
    hrs = [float(tp.heart_rate) for tp in pts if tp.heart_rate is not None]
    temps = [tp.temperature for tp in pts if tp.temperature is not None]
    has_power = bool(powers)
    is_foot = (activity.sport or "").lower() in _FOOT_SPORTS
    avg_hr = _mean(hrs) if hrs else (float(activity.avg_heart_rate) if activity.avg_heart_rate else None)
    duration_s = activity.total_timer_time or 0.0

    needs: list[str] = []

    # ---- intensity (power) -------------------------------------------------
    intensity = None
    np_w = _normalized_power(powers) if has_power else None
    if np_w is not None:
        avg_power = _mean([float(p) for p in powers])
        intensity_factor = tss = None
        if athlete.ftp_w and athlete.ftp_w > 0:
            intensity_factor = np_w / float(athlete.ftp_w)
            if duration_s > 0:
                tss = 100.0 * (duration_s / 3600.0) * intensity_factor ** 2
        else:
            needs.append("ftp_w")
        intensity = {
            "np_w": _r(np_w, 1),
            "avg_power_w": _r(avg_power, 1),
            "variability_index": _r(np_w / avg_power, 2) if avg_power else None,
            "intensity_factor": _r(intensity_factor, 2),
            "tss": _r(tss, 1),
            "basis": "power",
        }

    # ---- efficiency factor + aerobic decoupling ----------------------------
    efficiency = None
    if avg_hr:
        ef = ef_basis = None
        if np_w is not None:
            ef, ef_basis = np_w / avg_hr, "power"
        else:
            avg_speed = _mean([tp.speed for tp in pts if tp.speed is not None])
            if avg_speed:
                ef, ef_basis = avg_speed * 60.0 / avg_hr, "pace"  # m/min per bpm
        decoupling = _half_split_drift(pts, "power" if has_power else "speed")
        decoupling_basis = ("power" if has_power else "pace") if decoupling is not None else None
        if ef is not None or decoupling is not None:
            efficiency = {
                "efficiency_factor": _r(ef, 2),
                "basis": ef_basis,
                "decoupling_pct": _r(decoupling, 1),
                "decoupling_basis": decoupling_basis,
            }

    # ---- pace + grade-adjusted pace (foot sports) --------------------------
    pace = None
    if (activity.sport or "").lower() in _FOOT_SPORTS:
        avg_speed = activity.avg_speed or _mean([tp.speed for tp in pts if tp.speed is not None])
        gap_speed = _grade_adjusted_speed(pts)
        if avg_speed or gap_speed:
            pace = {
                "avg_speed_mps": _r(avg_speed, 3),
                "gap_speed_mps": _r(gap_speed, 3),
                "avg_pace_s_per_km": _pace_s_per_km(avg_speed),
                "gap_pace_s_per_km": _pace_s_per_km(gap_speed),
            }

    # ---- dynamics: acceleration, cadence, stride length --------------------
    # Running cadence is stored per leg; true cadence (steps/min) doubles it and
    # adds the fractional part. Cycling cadence is already whole-crank rpm.
    dynamics = None
    cadences: list[float] = []
    strides: list[float] = []
    for tp in pts:
        if tp.cadence is None:
            continue
        cad = (tp.cadence + _fractional_cadence(tp)) * 2 if is_foot else float(tp.cadence)
        cadences.append(cad)
        if is_foot and cad > 0 and tp.speed:
            strides.append(tp.speed * 120.0 / cad)  # distance per stride (2 steps)
    avg_cad = _mean(cadences)
    if avg_cad is None and activity.avg_cadence:
        avg_cad = float(activity.avg_cadence) * (2 if is_foot else 1)
    max_accel = _max_acceleration(pts)
    avg_stride = _mean(strides)
    if max_accel is not None or avg_cad is not None or avg_stride is not None:
        dynamics = {
            "max_acceleration_mps2": _r(max_accel, 2),
            "avg_cadence": int(round(avg_cad)) if avg_cad is not None else None,
            "max_cadence": int(round(max(cadences))) if cadences else None,
            "cadence_unit": "spm" if is_foot else "rpm",
            "stride_length_m": _r(avg_stride, 2),
        }

    # ---- heart rate: avg / max / drift -------------------------------------
    heart_rate = None
    if hrs or activity.avg_heart_rate:
        max_hr = max(hrs) if hrs else (float(activity.max_heart_rate) if activity.max_heart_rate else None)
        drift = _half_split_hr_drift(pts)
        heart_rate = {
            "avg_bpm": int(round(avg_hr)) if avg_hr else None,
            "max_bpm": int(round(max_hr)) if max_hr else None,
            "drift_pct": _r(drift, 1),
        }

    # ---- environment: temperature ------------------------------------------
    environment = None
    if temps:
        environment = {
            "avg_temp_c": _r(_mean(temps), 1),
            "min_temp_c": _r(min(temps), 1),
            "max_temp_c": _r(max(temps), 1),
        }
    elif activity.avg_temperature is not None:
        environment = {
            "avg_temp_c": _r(activity.avg_temperature, 1),
            "min_temp_c": None,
            "max_temp_c": None,
        }

    return ActivityMetrics(
        intensity, efficiency, pace, dynamics, heart_rate, environment, needs
    ).as_dict()


def _half_split_hr_drift(points: Sequence[Trackpoint]) -> float | None:
    """Percent change in mean HR from the first to the second time-half."""
    rows = [(tp.timestamp, float(tp.heart_rate)) for tp in points
            if tp.timestamp is not None and tp.heart_rate]
    if len(rows) < 4:
        return None
    midpoint = rows[0][0] + (rows[-1][0] - rows[0][0]) / 2
    first = _mean([h for t, h in rows if t <= midpoint])
    second = _mean([h for t, h in rows if t > midpoint])
    if not first or second is None:
        return None
    return (second - first) / first * 100.0

# SPDX-License-Identifier: GPL-3.0-or-later
"""VO₂max estimate and race-time predictions for a single activity (pure, stdlib).

An open, defensible take on the two numbers runners most want -- explicitly **not**
Garmin's proprietary FirstBeat VO₂max:

  * **VO₂max / VDOT** -- estimated with the Daniels–Gilbert running model from the
    activity's best sustained effort: convert the effort's velocity to an oxygen
    cost, divide by the fraction of VO₂max sustainable for that duration.
  * **Race predictions** -- projected finish times for standard race distances
    from that same reference effort via **Riegel's** endurance law,
    ``T₂ = T₁ · (D₂ / D₁) ** 1.06``.

The reference is chosen as the **highest-VDOT** best effort of at least
:data:`_MIN_REF_DIST` / :data:`_MIN_REF_TIME` (so a short sprint can't inflate the
estimate, and we don't extrapolate a marathon from 200 m). Accuracy assumes that
effort was roughly maximal; an easy run will read low. Running only (the models
are running-specific). Reuses :func:`core.best_efforts.compute_best_efforts`;
read-only, no third-party dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .best_efforts import compute_best_efforts
from .models import Activity

_RIEGEL_EXP = 1.06          # Riegel fatigue exponent for endurance running
_MIN_REF_DIST = 1000.0      # m -- shortest effort trusted as a prediction anchor
_MIN_REF_TIME = 120.0       # s -- and it must have lasted at least this long
_FOOT_SPORTS = {"running", "trail_running"}

# Standard race distances to project, with labels.
_RACE_DISTANCES: tuple[tuple[float, str], ...] = (
    (1609.344, "1 mile"), (5000, "5K"), (10000, "10K"),
    (21097.5, "Half marathon"), (42195, "Marathon"),
)


def _vdot(distance_m: float, time_s: float) -> float | None:
    """Daniels–Gilbert VDOT (≈ VO₂max, ml/kg/min) for a distance/time effort."""
    if distance_m <= 0 or time_s <= 0:
        return None
    t_min = time_s / 60.0
    velocity = distance_m / t_min  # m/min
    vo2 = -4.60 + 0.182258 * velocity + 0.000104 * velocity * velocity
    pct_max = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * t_min)
        + 0.2989558 * math.exp(-0.1932605 * t_min)
    )
    return (vo2 / pct_max) if pct_max > 0 else None


@dataclass
class RacePrediction:
    """A distance with its (reference or predicted) time and pace."""

    distance_m: float
    label: str
    time_s: float
    pace_s_per_km: int

    def as_dict(self) -> dict:
        return {
            "distance_m": self.distance_m,
            "label": self.label,
            "time_s": round(self.time_s, 1),
            "pace_s_per_km": self.pace_s_per_km,
        }


def _empty() -> dict:
    return {"available": False, "vo2max": None, "reference": None, "predictions": []}


def compute_race_predictions(activity: Activity) -> dict:
    """VO₂max estimate and Riegel race-time predictions for one running activity.

    Returns ``available=False`` (with empty fields) for non-running activities or
    when no effort is long enough to anchor a prediction. Otherwise: ``vo2max``
    (VDOT of the reference effort), the ``reference`` effort, and ``predictions``
    for the standard race distances.
    """
    if (activity.sport or "").lower() not in _FOOT_SPORTS:
        return _empty()

    efforts = compute_best_efforts(activity)["best_distances"]
    candidates = [
        e for e in efforts
        if e["distance_m"] >= _MIN_REF_DIST and e["time_s"] >= _MIN_REF_TIME
    ]
    if not candidates:
        return _empty()

    ref = max(candidates, key=lambda e: _vdot(e["distance_m"], e["time_s"]) or 0.0)
    vo2 = _vdot(ref["distance_m"], ref["time_s"])

    predictions = []
    for dist, label in _RACE_DISTANCES:
        t = ref["time_s"] * (dist / ref["distance_m"]) ** _RIEGEL_EXP
        predictions.append(RacePrediction(dist, label, t, round(t / (dist / 1000.0))).as_dict())

    return {
        "available": True,
        "vo2max": round(vo2, 1) if vo2 is not None else None,
        "reference": RacePrediction(
            ref["distance_m"], ref["label"], ref["time_s"], ref["pace_s_per_km"]
        ).as_dict(),
        "predictions": predictions,
    }

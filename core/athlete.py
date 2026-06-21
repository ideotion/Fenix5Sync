"""Athlete-profile suggestions from the local archive (pure, stdlib-only).

Helps fill in the athlete config without typing: the **observed maximum heart
rate** across all activities (a good basis for HR zones / training load when no
threshold is set), plus **weight / height / gender / resting HR** read from the
watch's ``user_profile`` (preserved in ``activity.extra`` at parse time). These
are *suggestions* the Settings UI can apply; nothing is written automatically.
Read-only over the activities, no third-party dependency.
"""

from __future__ import annotations

from typing import Iterable

from .models import Activity


def suggest_athlete(activities: Iterable[Activity]) -> dict:
    """Suggested athlete values derived from the activity history.

    ``observed_max_hr`` is the highest per-activity maximum HR seen; the profile
    fields come from the most recent activity whose device recorded a
    ``user_profile``. Any field with no evidence is ``None``.
    """
    acts = list(activities)
    max_hrs = [a.max_heart_rate for a in acts if a.max_heart_rate]

    profile: dict = {}
    dated = [a for a in acts if a.start_time is not None]
    for a in sorted(dated, key=lambda x: x.start_time, reverse=True):
        candidate = (a.extra or {}).get("user_profile")
        if candidate:
            profile = candidate
            break

    return {
        "observed_max_hr": max(max_hrs) if max_hrs else None,
        "resting_heart_rate": profile.get("resting_heart_rate"),
        "weight_kg": profile.get("weight_kg"),
        "height_m": profile.get("height_m"),
        "gender": profile.get("gender"),
    }

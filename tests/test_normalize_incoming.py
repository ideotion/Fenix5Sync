# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the WS0 incoming-data normalizer (scripts/normalize_incoming.py).

Covers the pure conversions: the per-phase Tai Chi schema -> canonical engine
schema (non-hold loop and hold rise/hold/lower cycle) and the home engine+library
merge. The shipped content packs are additionally guarded by the integrity tests
in test_home_content.py / test_taichi_content.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "normalize_incoming",
    Path(__file__).resolve().parent.parent / "scripts" / "normalize_incoming.py",
)
norm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(norm)


def _front_pose(**over):
    base = {"head": [120, 70], "sh": [120, 100], "hip": [120, 180],
            "lknee": [104, 248], "rknee": [136, 248], "lankle": [102, 312],
            "rankle": [138, 312], "lelb": [100, 140], "relb": [140, 140],
            "lhand": [100, 182], "rhand": [140, 182]}
    base.update(over)
    return base


def test_non_hold_movement_loops_into_each_named_pose():
    mv = {
        "id": "x", "name": "X", "view": "front", "object": None,
        "targetReps": 6, "isHold": False, "holdMs": 0,
        "staticLabels": ["A", "B", "C"],
        "phases": [
            {"name": "A", "durationMs": 1000, "cue": "ca", "pose": _front_pose()},
            {"name": "B", "durationMs": 2000, "cue": "cb", "pose": _front_pose(head=[120, 60])},
            {"name": "C", "durationMs": 3000, "cue": "cc", "pose": _front_pose(head=[120, 50])},
        ],
    }
    out = norm.normalize_taichi_movement(mv)
    assert set(out["views"]["front"].keys()) == {"A", "B", "C"}
    # Each phase animates *into* its named pose; the first loops back to the last.
    assert out["phases"][0] == {"name": "A", "dur": 1000, "from": "C", "to": "A"}
    assert out["phases"][1] == {"name": "B", "dur": 2000, "from": "A", "to": "B"}
    assert out["phases"][2] == {"name": "C", "dur": 3000, "from": "B", "to": "C"}
    assert out["cues"] == {"A": "ca", "B": "cb", "C": "cc"}
    assert out["staticCues"] == ["ca", "cb", "cc"]
    assert out["object"] == {"side": None, "front": None}
    assert out["targetReps"] == 6 and "isHold" not in out


def test_hold_movement_becomes_rise_hold_lower_cycle():
    mv = {
        "id": "h", "name": "H", "view": "front", "object": "wall",
        "targetReps": 2, "isHold": True, "holdMs": 8000,
        "staticLabels": ["Settle", "Lift & Hold"],
        "phases": [
            {"name": "Settle", "durationMs": 4000, "cue": "stand tall", "pose": _front_pose()},
            {"name": "Lift & Hold", "durationMs": 4000, "cue": "lift & hold", "pose": _front_pose(lknee=[104, 230])},
        ],
    }
    out = norm.normalize_taichi_movement(mv)
    names = [p["name"] for p in out["phases"]]
    assert names == ["Lift & Hold", "Hold", "Settle"]
    rise, hold, lower = out["phases"]
    assert rise == {"name": "Lift & Hold", "dur": 4000, "from": "Settle", "to": "Lift & Hold"}
    assert hold["from"] == hold["to"] == "Lift & Hold" and hold["isHold"] is True
    assert hold["dur"] == 8000  # the hold lasts holdMs, not durationMs
    assert lower == {"name": "Settle", "dur": 4000, "from": "Lift & Hold", "to": "Settle"}
    assert out["cues"]["Hold"]  # a generated, breathe-through-it hold cue
    assert out["object"] == {"side": None, "front": "wall"}
    assert out["isHold"] is True and out["holdMs"] == 8000
    # static fallback always has 3 captions (start / mid / return).
    assert len(out["staticLabels"]) == 3


def test_object_maps_to_the_single_authored_view():
    mv = {"id": "s", "name": "S", "view": "side", "object": "chair",
          "targetReps": 5, "isHold": False, "holdMs": 0, "staticLabels": ["a", "b"],
          "phases": [
              {"name": "P1", "durationMs": 1000, "cue": "c1", "pose": {"head": [120, 70], "ankle": [112, 312], "toe": [140, 312]}},
              {"name": "P2", "durationMs": 1000, "cue": "c2", "pose": {"head": [120, 70], "ankle": [112, 312], "toe": [140, 312]}},
          ]}
    out = norm.normalize_taichi_movement(mv)
    assert out["object"] == {"side": "chair", "front": None}
    assert list(out["views"].keys()) == ["side"]


def test_home_merge_unions_engine_and_library_metadata():
    engine = {"id": "e", "name": "E", "pattern": "squat", "tier": "standing",
              "views": {"side": {}}, "phases": [], "cues": {}, "staticCues": ["a"]}
    meta = {"id": "e", "pattern": "squat", "tier": "standing",
            "default_object": "chair", "regression_object": "higher seat",
            "progression_lever": "slow it down", "primary_benefit": "legs",
            "refs": ["R02"], "red_flags": True, "notes": "keep knees over toes"}
    out = norm.merge_home_exercise(engine, meta)
    assert out["primary_benefit"] == "legs" and out["refs"] == ["R02"]
    assert out["default_object"] == "chair" and out["notes"]
    # engine fields are preserved.
    assert out["views"] == {"side": {}} and out["name"] == "E"


def test_home_merge_rejects_pattern_mismatch():
    engine = {"id": "e", "name": "E", "pattern": "squat", "tier": "standing",
              "views": {}, "phases": [], "cues": {}, "staticCues": []}
    with pytest.raises(ValueError):
        norm.merge_home_exercise(engine, {"pattern": "hinge", "tier": "standing"})

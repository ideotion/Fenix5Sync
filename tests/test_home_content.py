# SPDX-License-Identifier: GPL-3.0-or-later
"""Integrity checks for the bundled "Sports at Home" content + exercise library.

Guards the shape of the offline content pack and the data-driven form-model
exercise library: every cited ref resolves (no dangling citations), bibliography
entries have locators, and each exercise's phases reference poses that actually
exist (so the engine never interpolates against a missing keyframe).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent / "web" / "content" / "home"
OVERVIEW = ROOT / "overview.json"
EXERCISES = ROOT / "exercises.json"


@pytest.fixture(scope="module")
def pack() -> dict:
    return json.loads(OVERVIEW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def library() -> dict:
    return json.loads(EXERCISES.read_text(encoding="utf-8"))


def test_required_top_level_keys(pack):
    for key in ("title", "disclaimer", "levels", "programs", "objects",
                "movement_patterns", "benefits", "not_supported", "safety",
                "screening", "intensity", "bibliography", "sessions"):
        assert key in pack, f"missing key: {key}"


def test_levels_have_met_ranges(pack):
    ids = {lvl["id"] for lvl in pack["levels"]}
    assert {"seated", "standing", "loaded", "conditioning"} <= ids
    for lvl in pack["levels"]:
        met = lvl["intensity_met"]
        assert len(met) == 2 and 1.0 <= met[0] <= met[1] <= 9.0


def test_benefits_are_graded_and_described(pack):
    grades = {"Strong", "Moderate", "Limited"}
    assert pack["benefits"]
    for b in pack["benefits"]:
        assert b["outcome"] and b["detail"]
        assert b["grade"] in grades, f"unexpected grade: {b['grade']}"


def test_every_citation_resolves(pack):
    known = {b["ref_id"] for b in pack["bibliography"]}
    cited: set[str] = set()
    for b in pack["benefits"]:
        cited.update(b.get("refs", []))
    for p in pack["programs"]:
        cited.update(p.get("refs", []))
    for pt in pack["premise"]["points"]:
        cited.update(pt.get("refs", []))
    for sig in pack["intensity"]["signals"]:
        cited.update(sig.get("refs", []))
    cited.update(pack["screening"].get("refs", []))
    dangling = cited - known
    assert not dangling, f"citations with no bibliography entry: {sorted(dangling)}"


def test_bibliography_entries_have_locators(pack):
    for b in pack["bibliography"]:
        assert b["ref_id"] and b["url"], f"bad bibliography entry: {b}"
        assert b["url"].startswith("http")


def test_sessions_marked_pending(pack):
    assert pack["sessions"]["status"] == "pending"


def test_objects_have_required_fields(pack):
    for o in pack["objects"]:
        for key in ("id", "name", "role", "load_logic", "movements", "safety"):
            assert key in o, f"object {o.get('id')} missing {key}"


# ---- exercise library (drives the form-model engine) ----

def test_exercise_library_shape(library):
    exs = library["exercises"]
    assert exs
    ids = [e["id"] for e in exs]
    assert len(ids) == len(set(ids)), "duplicate exercise ids"
    # The two proven exemplars from the reference prototype must be present.
    assert {"sts", "wall"} <= set(ids)


def test_phases_reference_existing_poses(library):
    for ex in library["exercises"]:
        assert ex["views"], f"{ex['id']} has no views"
        # The union of pose names across all views must cover every phase from/to.
        pose_names = set()
        for view in ex["views"].values():
            pose_names.update(view.keys())
            for pose in view.values():
                assert "head" in pose, f"{ex['id']} pose missing head joint"
        for ph in ex["phases"]:
            assert ph["from"] in pose_names, f"{ex['id']} phase '{ph['name']}' from-pose missing"
            assert ph["to"] in pose_names, f"{ex['id']} phase '{ph['name']}' to-pose missing"
            assert ph["name"] in ex["cues"], f"{ex['id']} phase '{ph['name']}' has no cue"
        assert ex.get("targetReps") or ex.get("holdMs"), f"{ex['id']} needs reps or a hold"
        assert ex["staticCues"], f"{ex['id']} needs a static fallback"


def test_isometric_flag_present_for_wall(library):
    wall = next(e for e in library["exercises"] if e["id"] == "wall")
    assert wall.get("isometric") is True

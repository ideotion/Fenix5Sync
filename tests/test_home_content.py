# SPDX-License-Identifier: GPL-3.0-or-later
"""Integrity checks for the bundled "Sports at Home" content + exercise library.

Guards the shape of the offline content pack and the data-driven form-model
exercise library: every cited ref resolves (no dangling citations), bibliography
entries have locators, and each exercise's phases reference poses that actually
exist (so the engine never interpolates against a missing keyframe).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent / "web" / "content" / "home"
OVERVIEW = ROOT / "overview.json"
EXERCISES = ROOT / "exercises.json"
FORM_MODEL_JS = Path(__file__).resolve().parent.parent / "web" / "js" / "formModel.js"


def glyph_registry() -> set[str]:
    """The object-glyph ids the engine can actually draw (OBJECTS + IMPLEMENTS).

    Parsed from formModel.js so content can never reference a glyph the engine
    has no markup for. The registries are zero-arg arrow values keyed by id.
    """
    src = FORM_MODEL_JS.read_text(encoding="utf-8")
    return set(re.findall(r"(\w+):\s*\(\)\s*=>", src))


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

PUSHUP_PROGRESSION = [
    "wall-pushup", "countertop-pushup", "incline-pushup-chair", "knee-pushup", "full-pushup",
]


def test_exercise_library_shape(library):
    exs = library["exercises"]
    assert len(exs) == 35, "the full home library ships 35 exercises"
    ids = [e["id"] for e in exs]
    assert len(ids) == len(set(ids)), "duplicate exercise ids"
    # The full push-up progression (wall -> counter -> chair -> knee -> floor)
    # must be present and in ascending order.
    assert set(PUSHUP_PROGRESSION) <= set(ids)
    positions = [ids.index(p) for p in PUSHUP_PROGRESSION]
    assert positions == sorted(positions), "push-up progression is out of order"


def test_every_exercise_carries_library_metadata(library):
    for ex in library["exercises"]:
        for key in ("pattern", "tier", "primary_benefit", "refs", "notes"):
            assert ex.get(key), f"{ex['id']} missing library field {key}"


def test_exercise_refs_resolve(pack, library):
    known = {b["ref_id"] for b in pack["bibliography"]}
    for ex in library["exercises"]:
        dangling = set(ex.get("refs", [])) - known
        assert not dangling, f"{ex['id']} cites unknown refs {sorted(dangling)}"


def test_exercise_tiers_and_patterns_are_valid(pack, library):
    tiers = {lvl["id"] for lvl in pack["levels"]}
    patterns = {p["id"] for p in pack["movement_patterns"]}
    for ex in library["exercises"]:
        assert ex["tier"] in tiers, f"{ex['id']} unknown tier {ex['tier']}"
        assert ex["pattern"] in patterns, f"{ex['id']} unknown pattern {ex['pattern']}"


def test_exercise_objects_exist_in_glyph_registry(library):
    glyphs = glyph_registry()
    assert {"chair", "wall", "counter", "step"} <= glyphs
    for ex in library["exercises"]:
        for side in ("side", "front"):
            gid = (ex.get("object") or {}).get(side)
            if gid is not None:
                assert gid in glyphs, f"{ex['id']} references unknown glyph {gid}"


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


def test_isometric_holds_are_flagged(library):
    # Isometric exercises hold (holdMs, no targetReps) and carry the flag the
    # home UI uses to gate them behind the PAR-Q+ readiness check.
    holds = [e for e in library["exercises"] if e.get("isometric")]
    assert holds, "expected isometric holds in the library"
    wph = next(e for e in library["exercises"] if e["id"] == "wall-press-hold")
    assert wph.get("isometric") is True and wph.get("holdMs")
    for e in holds:
        assert e.get("holdMs") and not e.get("targetReps"), f"{e['id']} bad hold shape"

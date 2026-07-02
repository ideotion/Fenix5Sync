# SPDX-License-Identifier: GPL-3.0-or-later
"""Integrity checks for the bundled Tai Chi content pack.

This content is rendered by the offline Tai Chi tab; the tests guard its shape and
that every cited ref_id resolves to a real bibliography entry (no dangling
citations), so the evidence trail stays intact as the pack grows.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

TAICHI = Path(__file__).resolve().parent.parent / "web" / "content" / "taichi"
CONTENT = TAICHI / "overview.json"
MOVEMENTS = TAICHI / "movements.json"
FORM_MODEL_JS = Path(__file__).resolve().parent.parent / "web" / "js" / "formModel.js"


def glyph_registry() -> set[str]:
    """Object-glyph ids the shared engine can draw (parsed from formModel.js)."""
    src = FORM_MODEL_JS.read_text(encoding="utf-8")
    return set(re.findall(r"(\w+):\s*\(\)\s*=>", src))


@pytest.fixture(scope="module")
def pack() -> dict:
    return json.loads(CONTENT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def movements() -> dict:
    return json.loads(MOVEMENTS.read_text(encoding="utf-8"))


def test_required_top_level_keys(pack):
    for key in ("title", "disclaimer", "levels", "programs", "benefits",
                "safety", "bibliography", "sessions"):
        assert key in pack, f"missing key: {key}"


def test_levels_have_met_ranges(pack):
    ids = {lvl["id"] for lvl in pack["levels"]}
    assert {"chair", "supported", "standing", "advanced"} <= ids
    for lvl in pack["levels"]:
        met = lvl["intensity_met"]
        assert len(met) == 2 and 1.0 <= met[0] <= met[1] <= 6.0


def test_benefits_are_graded_and_described(pack):
    grades = {"Strong", "Strong–Moderate", "Moderate", "Moderate–Limited",
              "Limited", "Limited / Emerging"}
    assert pack["benefits"]
    for b in pack["benefits"]:
        assert b["outcome"] and b["detail"]
        assert b["grade"] in grades


def test_every_citation_resolves(pack):
    known = {b["ref_id"] for b in pack["bibliography"]}
    cited: set[str] = set()
    for b in pack["benefits"]:
        cited.update(b.get("refs", []))
    for p in pack["programs"]:
        cited.update(p.get("refs", []))
    dangling = cited - known
    assert not dangling, f"citations with no bibliography entry: {sorted(dangling)}"


def test_bibliography_entries_have_locators(pack):
    for b in pack["bibliography"]:
        assert b["ref_id"] and b["url"], f"bad bibliography entry: {b}"
        assert b["url"].startswith("http")


def test_sessions_shipped_with_valid_templates(pack):
    # The flow builder/player are live; the pack now ships one-click templates
    # whose opts must be valid SessionBuilder.buildTaiChi inputs.
    s = pack["sessions"]
    assert s["status"] == "shipped" and s["note"]
    assert s["templates"], "shipped sessions must offer at least one template"
    for t in s["templates"]:
        assert t["id"] and t["name"] and t["desc"], f"bad template: {t}"
        o = t["opts"]
        assert 5 <= o["lengthMin"] <= 30
        assert o["level"] in {"chair", "supported", "standing"}
        assert o["focus"] in {"full", "balance", "mobility", "lower-limb", "breathing"}


def test_every_movement_carries_stage_and_origin(movements):
    # The enriched library: session position (groups the picker) + lineage label.
    stages = {"warmup", "drill", "form", "seated", "closing"}
    for mv in movements["movements"]:
        assert mv["stage"] in stages, f"{mv['id']}: unknown stage {mv.get('stage')!r}"
        assert mv["origin"].strip(), f"{mv['id']}: empty origin"
    by_stage = {s: [m["id"] for m in movements["movements"] if m["stage"] == s] for s in stages}
    assert len(by_stage["form"]) == 7, "the simplified Yang-24 selection ships 7 forms"
    assert all("24-form" in m["origin"] for m in movements["movements"] if m["stage"] == "form")
    assert by_stage["closing"] == ["tc_gather_qi_close"]


# ---- shared form-model engine: Tai Chi movement pacers ----

def test_taichi_movements_drive_the_shared_engine(movements):
    mvs = movements["movements"]
    assert len(mvs) == 21 and movements.get("disclaimer")
    ids = [mv["id"] for mv in mvs]
    assert len(ids) == len(set(ids)), "duplicate movement ids"
    for mv in mvs:
        assert mv["id"] and mv["name"] and mv["views"]
        pose_names = set()
        for view in mv["views"].values():
            pose_names.update(view.keys())
            for pose in view.values():
                assert "head" in pose, f"{mv['id']} pose missing head joint"
        for ph in mv["phases"]:
            assert ph["from"] in pose_names and ph["to"] in pose_names, \
                f"{mv['id']} phase '{ph['name']}' references a missing pose"
            assert ph["name"] in mv["cues"], f"{mv['id']} phase '{ph['name']}' has no cue"
        assert mv.get("targetReps") or mv.get("holdMs")
        assert mv["staticCues"]


def test_taichi_hold_phase_is_static(movements):
    # Normalized holds carry a from==to, isHold hold phase whose duration is the
    # intended holdMs (the rise/lower transitions surround it).
    for mv in movements["movements"]:
        if not mv.get("isHold"):
            continue
        holds = [p for p in mv["phases"] if p.get("isHold")]
        assert holds, f"{mv['id']} flagged isHold but has no hold phase"
        for p in holds:
            assert p["from"] == p["to"], f"{mv['id']} hold phase is not static"


def test_taichi_movement_refs_resolve(pack, movements):
    known = {b["ref_id"] for b in pack["bibliography"]}
    for mv in movements["movements"]:
        dangling = set(mv.get("refs", [])) - known
        assert not dangling, f"{mv['id']} cites unknown refs {sorted(dangling)}"


def test_taichi_movement_levels_are_valid(pack, movements):
    levels = {lvl["id"] for lvl in pack["levels"]}
    for mv in movements["movements"]:
        assert mv.get("level") in levels, f"{mv['id']} unknown level {mv.get('level')}"
        assert mv.get("focus"), f"{mv['id']} missing focus"


def test_taichi_objects_exist_in_glyph_registry(movements):
    glyphs = glyph_registry()
    for mv in movements["movements"]:
        for side in ("side", "front"):
            gid = (mv.get("object") or {}).get(side)
            if gid is not None:
                assert gid in glyphs, f"{mv['id']} references unknown glyph {gid}"

# SPDX-License-Identifier: GPL-3.0-or-later
"""Integrity checks for the bundled Tai Chi content pack.

This content is rendered by the offline Tai Chi tab; the tests guard its shape and
that every cited ref_id resolves to a real bibliography entry (no dangling
citations), so the evidence trail stays intact as the pack grows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTENT = Path(__file__).resolve().parent.parent / "web" / "content" / "taichi" / "overview.json"


@pytest.fixture(scope="module")
def pack() -> dict:
    return json.loads(CONTENT.read_text(encoding="utf-8"))


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


def test_sessions_marked_pending(pack):
    # Movement library + videos are not shipped yet; the pack must say so.
    assert pack["sessions"]["status"] == "pending"

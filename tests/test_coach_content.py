"""Integrity checks for the bundled Coach (training-program) content pack.

Guards the evidence trail: every ref_id cited anywhere must resolve to a real
bibliography entry, and web-verified sources must carry a locator. Keeps the
"no dangling citations" rule enforced as the pack grows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CONTENT = Path(__file__).resolve().parent.parent / "web" / "content" / "coach" / "overview.json"


@pytest.fixture(scope="module")
def pack() -> dict:
    return json.loads(CONTENT.read_text(encoding="utf-8"))


def test_required_top_level_keys(pack):
    for key in ("title", "disclaimer", "approach", "reference_program",
                "personalization", "normative_tables", "safety", "coverage",
                "glossary", "bibliography"):
        assert key in pack, f"missing key: {key}"


def test_personalization_lists_named_metric_fields(pack):
    fields = pack["personalization"]["metric_fields"]
    # Must reference the app's real metric names so the rules can be coded.
    for expected in ("ctl", "atl", "tsb", "vo2max_vdot", "ftp_w", "aerobic_decoupling"):
        assert expected in fields


def test_every_citation_resolves(pack):
    known = {b["ref_id"] for b in pack["bibliography"]}
    cited: set[str] = set()
    cited.update(*(a.get("refs", []) for a in pack["approach"]) or [[]])
    for a in pack["approach"]:
        cited.update(a.get("refs", []))
    cited.update(pack["reference_program"].get("refs", []))
    for step in pack["personalization"]["worked_example"]:
        cited.update(step.get("refs", []))
    for t in pack["normative_tables"]:
        cited.update(t.get("refs", []))
    cited.update(pack["safety"].get("refs", []))
    dangling = cited - known
    assert not dangling, f"citations with no bibliography entry: {sorted(dangling)}"


def test_bibliography_verification_and_locators(pack):
    for b in pack["bibliography"]:
        assert b["ref_id"] and b["citation"]
        assert b["verification"] in ("web_verified", "UNVERIFIED")
        # Anything claimed web-verified must carry a resolvable locator.
        if b["verification"] == "web_verified":
            assert b["url"].startswith("http"), f"verified but no URL: {b['ref_id']}"


def test_reference_program_phases_sum_to_duration(pack):
    rp = pack["reference_program"]
    assert sum(p["weeks"] for p in rp["phases"]) == rp["duration_weeks"]

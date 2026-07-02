# SPDX-License-Identifier: GPL-3.0-or-later
"""Integrity + anti-drift checks for the dynamic-coach evidence pack.

Guards ``web/content/coach/coach-evidence.pack.json``: the schema is stable,
every citation resolves to a bibliography entry that carries a locator (DOI or
URL), and — the load-bearing part — every numeric threshold recorded in the pack
still equals the constant it maps to in the live code. That last check is what
keeps the citations and the engine from drifting apart: change a constant without
updating its cited value (or vice versa) and this test fails.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import core.coach_plan as coach_plan
import core.coach_state as coach_state

PACK_PATH = Path(__file__).resolve().parent.parent / "web" / "content" / "coach" / "coach-evidence.pack.json"
_MODULES = {"coach_state": coach_state, "coach_plan": coach_plan}


@pytest.fixture(scope="module")
def pack() -> dict:
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def test_schema_and_generated_date(pack):
    assert pack["schema"] == "fenix5sync.coach.evidence.v1"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", pack["generated"]), "generated must be YYYY-MM-DD"
    assert pack["summary"].strip()


def test_every_parameter_is_well_formed(pack):
    params = pack["parameters"]
    # The seven sensor/controller parameters the pack is meant to anchor.
    assert set(params) == {
        "acwr", "ctl_ramp_rate", "tsb_bands", "readiness_rhr",
        "monotony_strain", "hard_day", "maintenance_dose",
    }
    for name, p in params.items():
        assert p["recommended"], f"{name}: no recommended values"
        assert p["grade"] and p["caveat"].strip(), f"{name}: missing grade/caveat"
        assert isinstance(p["citations"], list), f"{name}: citations must be a list"
        assert isinstance(p["constants"], dict), f"{name}: constants must be a dict"
        assert p["module"] in _MODULES or p["module"] is None, f"{name}: bad module {p['module']!r}"


def test_every_citation_resolves_to_a_bibliography_entry(pack):
    known = set(pack["bibliography"])
    for name, p in pack["parameters"].items():
        dangling = set(p["citations"]) - known
        assert not dangling, f"{name} cites unknown refs: {sorted(dangling)}"


def test_bibliography_entries_have_authors_year_title_and_a_locator(pack):
    for key, b in pack["bibliography"].items():
        assert b.get("authors") and b.get("title"), f"{key}: missing authors/title"
        assert isinstance(b.get("year"), int), f"{key}: year must be an int"
        assert b.get("doi") or (b.get("url", "").startswith("http")), f"{key}: no DOI or URL locator"


def test_at_least_the_peer_reviewed_anchors_are_present(pack):
    # The pack must retain its verified journal citations (guards against a future
    # edit quietly dropping the evidence behind a contested band).
    for key in ("gabbett2016", "lolli2019", "impellizzeri2020", "foster1998", "buchheit2014"):
        assert key in pack["bibliography"], f"missing anchor citation: {key}"
        assert pack["bibliography"][key].get("doi"), f"{key}: peer-reviewed anchor must carry a DOI"


def test_recorded_constants_match_the_live_code(pack):
    """Anti-drift: each pack 'constants' value equals the module constant it maps to."""
    checked = 0
    for name, p in pack["parameters"].items():
        module = _MODULES.get(p["module"])
        for const_name, recorded in p["constants"].items():
            assert module is not None, f"{name}: constants given but module is null"
            assert hasattr(module, const_name), f"{name}: {const_name} not found in {p['module']}"
            actual = getattr(module, const_name)
            assert actual == recorded, f"drift: {p['module']}.{const_name} is {actual}, pack says {recorded}"
            checked += 1
    assert checked >= 9, "expected the ACWR/ramp/TSB/readiness/hard-day constants to be checked"

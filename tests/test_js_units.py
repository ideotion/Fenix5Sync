# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the browser-engine JS unit suites under Node, from the same pytest gate.

The form-model's pure math (pseudo-3-D yaw projection, foot/heel geometry) and
the session-builder selection logic live in dependency-free JS modules that also
export under Node. These tests execute them with ``node --test`` so the math is
verified in CI alongside the Python suite. Skipped only when Node is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path(__file__).resolve().parent / "js"
REPO = JS_DIR.parent.parent


def _node_test_files() -> list[str]:
    return sorted(str(p) for p in JS_DIR.glob("*.test.js"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_js_unit_suites_pass():
    files = _node_test_files()
    assert files, "no JS test files found under tests/js/"
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, repo-local files
        [shutil.which("node"), "--test", *files],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, f"node --test failed:\n{proc.stdout}\n{proc.stderr}"

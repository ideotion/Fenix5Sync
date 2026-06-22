# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared pytest fixtures.

Provides a generated (and committed) sample ``.FIT`` file plus a fully isolated
:class:`~core.config.Config` that points all storage at a temp directory, so
tests never touch real user data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the project importable when tests are run from a checkout.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import Config  # noqa: E402
from tests.fixtures.make_fit import write_sample  # noqa: E402

FIXTURE_FIT = Path(__file__).parent / "fixtures" / "sample.fit"


@pytest.fixture(scope="session")
def sample_fit_path() -> Path:
    """Path to the sample FIT file (regenerated if missing)."""
    if not FIXTURE_FIT.is_file():
        write_sample(FIXTURE_FIT)
    return FIXTURE_FIT


@pytest.fixture
def tmp_config(tmp_path: Path, sample_fit_path: Path) -> Config:
    """A Config with all paths under a temp dir and source pointing at fixtures."""
    cfg = Config()
    data_dir = tmp_path / "data"
    cfg.storage.data_dir = str(data_dir)
    cfg.storage.db_file = str(data_dir / "fenix5sync.sqlite")
    cfg.export.output_dir = str(tmp_path / "exports")
    cfg.logging.log_dir = str(tmp_path / "logs")
    # Acquire directly from the fixtures directory (mode=path).
    cfg.source.mode = "path"
    cfg.source.path = str(sample_fit_path.parent)
    return cfg

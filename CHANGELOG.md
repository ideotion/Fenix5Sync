# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases are tagged automatically from the `version` in `pyproject.toml`; see the
GitHub Releases page for the auto-generated notes per tag.

## [Unreleased]

### Added
- **Form-model engine: pseudo-3-D, corrected feet, free weights.** The shared SVG
  movement engine now runs every joint through a unit-tested yaw projection
  (`web/js/formGeom.js`), so poses can carry optional depth (`z`); a gentle
  auto-turn toggle and a manual turn slider give a subtle 3-D feel (persisted).
  Side-view feet gain a synthesized heel so the foot reads as a wedge and the toe
  leads the facing direction, plus a mirror/face control to flip left/right. New
  object glyphs: `counter` and `step` (rooms) and `dumbbell`/`kettlebell`
  (free weights that track the hands). All existing preferences, 60 fps
  attribute-only updates, and the reduced-motion static fallback are preserved.
  The projection/foot/shading math is verified under Node via a new pytest gate
  (`tests/test_js_units.py`, `tests/js/`).
- **FIT Salvage** — recover corrupt/truncated `.FIT` files locally: walks the
  record stream to the last complete record, repairs the header/CRC and
  re-parses (deriving the summary from records when the session trailer was
  lost). Available as `fenix5sync salvage`, `POST /api/salvage`, and a "Recover
  a corrupt file" panel on Import/Sync. The original is never modified.
- **Sports at Home** — guided, evidence-based home training with household
  objects: a bundled offline content pack + curation report, a PAR-Q+-style
  readiness screen (client-only) that gates isometric work, a data-driven SVG
  form-model animation engine (tempo pacer, front/side views, reduced-motion
  fallback) and a 30-second sit-to-stand capacity check.
- **Year in Sport recap** — a private, local annual/all-time recap with a
  self-contained, shareable HTML export.
- **Personal privacy audit** — a defensive, local self-audit of what your tracks
  reveal (likely home, routine), recommending a privacy radius.
- **Personal segments** — capture a route from an activity and race yourself over
  your history (private leaderboard + trend).
- **Liberate Your History** — import a Garmin/Strava account export (nested zips +
  gzip) via an `export` source mode, the Import/Sync page and a
  `fenix5sync import-export` CLI command.
- **File/folder picker** — a "Browse…" button (backed by a read-only
  `GET /api/fs/list`) on the export-import and Settings source fields, so paths
  never have to be typed; plus an editable activity-source section in Settings.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR templates, and
  a Dependabot config for community readiness.
- CI now runs `ruff` (lint), `bandit` (security, medium+), and `pip-audit`
  (dependency vulnerabilities) alongside the test suite.
- `dev` optional-dependency group (`ruff`, `bandit`, `pip-audit`) and `[tool.ruff]`
  / `[tool.bandit]` configuration in `pyproject.toml`.

### Changed
- GPX/TCX imports now parse XML with `defusedxml` to harden against
  entity-expansion / external-entity attacks in untrusted activity files.

## [0.1.0]

- Initial development version: local-first acquisition (mass storage / MTP / path
  / folder / file / zip), lossless raw `.FIT` storage, SQLite store, FastAPI
  loopback server, vanilla-JS GUI, CLI, multi-format import (FIT/TCX/GPX),
  content-hash dedupe, anonymized export (CSV/JSON/GPX/TCX/raw + NDJSON archive),
  training zones, insights, and analytics.

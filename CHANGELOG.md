# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases are tagged automatically from the `version` in `pyproject.toml`; see the
GitHub Releases page for the auto-generated notes per tag.

## [Unreleased]

### Added
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

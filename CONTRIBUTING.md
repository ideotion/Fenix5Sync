# Contributing to Fenix5Sync

Thanks for your interest in improving Fenix5Sync! This is a small, focused,
**local-first / offline** project, and contributions that keep it that way are
very welcome.

## Guiding principles

Please keep changes aligned with the project's invariants:

- **Read-only device.** Never write to the connected watch.
- **Offline & private.** No runtime network calls, no telemetry, no CDNs. New
  frontend assets must be vendored under `web/vendor/` with their license noted.
- **Loopback only.** The server binds to `127.0.0.1`; do not add ways to expose it.
- **Lossless capture.** Raw files remain the canonical source of truth.
- **Minimal dependencies.** Prefer the standard library; justify new dependencies.

## Development setup

```sh
git clone https://github.com/ideotion/Fenix5Sync.git
cd Fenix5Sync
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test,dev]"
```

## Before you open a PR

Run the same checks CI runs:

```sh
ruff check .                         # lint
pytest                               # full test suite
bandit -ll -c pyproject.toml -r core server cli   # security (medium+)
pip-audit                            # dependency vulnerabilities
```

- **Add tests** for new behaviour. The suite generates its own `.FIT`/`.TCX`/`.GPX`
  fixtures (see `tests/fixtures/`), so tests stay self-contained and offline.
- **Keep the layers clean.** `core/` must not depend on the web/CLI layers.
- **Update docs** (`README.md`, `config.example.yaml`) when behaviour or config changes.

## Commit & PR conventions

- Write clear, imperative commit subjects (e.g. "Add power-zone export").
- Keep PRs focused; one logical change per PR is easiest to review.
- Describe what changed and why, and how you tested it.

## Releases

Releases are version-file driven. The only manual step is bumping `version` in
[`pyproject.toml`](pyproject.toml) in a normal PR; merging to `main` tags and
publishes the release automatically. See the README's *Releases* section.

## Code of Conduct

By participating you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

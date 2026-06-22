<!-- Thanks for contributing! Please keep PRs focused on one logical change. -->

## What & why

<!-- What does this change do, and what problem does it solve? -->

## How tested

<!-- Commands you ran and results. CI runs: ruff, pytest, bandit, pip-audit. -->

- [ ] `ruff check .`
- [ ] `pytest`
- [ ] `bandit -ll -c pyproject.toml -r core server cli`
- [ ] `pip-audit`

## Checklist

- [ ] Preserves the project invariants (read-only device, offline, loopback-only,
      lossless capture, minimal deps).
- [ ] Added/updated tests for the change.
- [ ] Updated docs (`README.md` / `config.example.yaml`) if behaviour or config changed.
- [ ] Updated `CHANGELOG.md` under **Unreleased** if user-facing.

# Security Policy

Fenix5Sync is a **local-first, offline** tool. By design it:

- treats the connected watch as **strictly read-only** — it never writes to the device;
- binds its server to **loopback only** (`127.0.0.1`), enforced in
  [`core/config.py`](core/config.py) and re-validated when config is changed via the API;
- makes **no network calls at runtime** and ships no telemetry — every frontend
  asset (including Chart.js) is vendored.

These properties mean the realistic attack surface is small (a local user, or a
crafted activity file you choose to import). We still take security seriously and
welcome reports.

## Supported versions

This project is pre-1.0 and released from `main`. Security fixes are applied to
the latest release only. Please test against the latest `main` before reporting.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Preferred: open a private report via GitHub Security Advisories —
**Security → Report a vulnerability** on the repository.

Alternatively, email **github@ideotion.com** with:

- a description of the issue and its impact,
- steps to reproduce (a minimal crafted file or request is ideal),
- the version / commit you tested.

We aim to acknowledge reports within **7 days** and to provide a remediation
plan or assessment within **30 days**. Please give us a reasonable window to
release a fix before any public disclosure.

## Scope notes

- Imported `.FIT`/`.TCX`/`.GPX` files are treated as untrusted input: XML is
  parsed with `defusedxml`, and `.zip` archives are extracted with
  path-traversal ("zip slip") protection.
- Because the server is loopback-only and unauthenticated by design, exposing it
  to a network (e.g. via a reverse proxy or by editing the loopback guard) is
  **out of scope** and unsupported.

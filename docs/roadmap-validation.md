# Roadmap brief — validation against the codebase

This document checks the claims in [`roadmap-brief.html`](roadmap-brief.html)
against the actual Fenix5Sync source tree, and flags where they diverge. It is
analyst commentary on the brief, not a change to the roadmap itself.

- **Validated at commit:** `main` after PRs #5/#7/#8 (TCX/raw export +
  anonymization + Insights all merged).
- **Method:** read every module the brief's baseline and RICE items touch, plus
  the test suite (which is a precise behavioural spec).

> **Note on a correction.** An earlier draft of this validation was run against a
> stale local checkout (only up to PR #4) and wrongly reported that anonymization
> and TCX export were missing. Both exist and are well-tested. The findings below
> are against the current tree.

---

## Bottom line

The brief is **accurate and well-aligned with the code.** Every capability it
lists as the existing baseline is genuinely present, and the "ingestion/interop
first" sequencing matches how the codebase is built. The corrections that remain
are about *how far along* a few items are, not whether the brief is right.

---

## Baseline scorecard

The brief's baseline: *"USB extraction, raw + SQLite + NDJSON storage, charts, a
basic GPS track, multi-format export, optional anonymization already exist."*
All of it checks out:

| Claim | Status | Evidence |
|---|---|---|
| USB extraction | ✅ Real | `core/acquire.py` — mass-storage + MTP (`jmtpfs`) + path/folder/file/zip/auto, read-only |
| Raw lossless store | ✅ Real | `core/acquire.py` `copy_to_raw`, content-addressed, original extension kept |
| SQLite | ✅ Real | `core/store.py` — activities/laps/trackpoints/ledger, indexed, WAL, atomic writes |
| NDJSON archive | ✅ Real | `core/export.py` `activities_ndjson` / `write_archive` |
| Charts | ✅ Real | `web/js/charts.js` (line + bar/area), vendored Chart.js, offline |
| Basic GPS track | ✅ Real | `web/js/track.js` — self-drawn canvas polyline (correctly *not* a basemap) |
| Multi-format export | ✅ Real | CSV/JSON/GPX/**TCX**/**raw** + bulk CSV/JSON/NDJSON (`core/export.py`) |
| Optional anonymization | ✅ Real | `core/anonymize.py` + `core/geo.py` — non-destructive, opt-in, tested |

The data-flow diagram in the brief ("Export & share: TCX/FIT") is **accurate**:
TCX comes from `activity_tcx`, and FIT re-upload is covered by the `raw`
passthrough, which serves the original file byte-for-byte — the most faithful
re-upload possible.

---

## RICE items vs. reality

Legend: ✅ done · ◑ partial · ◔ minimal · ❌ not started

| # | Feature | Brief tier | Reality in code |
|---|---------|-----------|-----------------|
| 1 | HR & power zone analytics | Now 7.2 | ✅ **shipped in this PR** — `core/zones.py`, `/api/.../zones`, activity-page UI |
| 2 | Round-trip multi-format interop | Now 6.1 | ◑ export/round-trip done (TCX writer + raw passthrough); **decode robustness** still `fitparse`, not SDK-grade |
| 3 | Harden cross-generation ingestion | Now 5.4 | ◑ mass-storage + MTP work; cross-generation hardening is ongoing |
| 4 | Training-load & form (CTL/ATL/TSB) | Now 5.1 | ❌ not started — Insights is descriptive stats, not training load |
| 5 | Strengthen + automate anonymized export | Now 5.1 | ✅ **already done** — opt-in, per-request + config, bulk-aware, GUI toggle + CLI flag, tested |
| 6 | Distribution & trust hardening | Next 4.5 | ◔ `install.sh` + CI exist; no `.deb`/Flatpak/AppImage, no signing/reproducible builds |
| 7 | Multi-device consolidation + dedup hub | Next 4.2 | ❌ only exact-content SHA-256 dedup; cross-source **semantic** dedup missing |
| 8 | Full offline vector maps + routes | Next 3.6 | ❌ only the self-drawn track polyline; no tiles/basemap |
| 9 | VO₂max trend + race predictions | Next 3.3 | ❌ not started |
| 10 | PR / best-efforts tracking | Next 3.3 | ◑ basic personal records shipped in Insights; time-window best-efforts (fastest 5k/10k) missing |
| 11 | Gear / equipment mileage | Later 2.8 | ❌ not started |
| 12 | Sleep / HRV / recovery | Later 2.4 | ❌ not started (no wellness/monitoring-FIT ingestion) |
| 13 | Manual + strength logging | Later 1.0 | ❌ not started |
| 14 | Local LLM insights (Ollama) | Later 0.5 | ❌ not started |

---

## Corrections to the brief

1. **#5 (anonymized export) is essentially complete**, not a "Now, to-build"
   item. `core/anonymize.py` already does home/finish privacy-radius nulling, GPS
   fuzzing, full drop, device + personal-field stripping, and date shifting — all
   on a deep copy, with the stored archive never modified, exposed via a GUI
   toggle, a CLI `--anonymize` flag, and `?anonymize=true`. It should move to
   *done / maintain*.

2. **#2 (interop) should be split.** The *export / round-trip* half is shipped
   (TCX writer + raw passthrough — and raw passthrough is a strong robustness
   hedge: even an imperfectly-decoded new FIT re-exports losslessly). What
   genuinely remains is **decode robustness**: parsing is `fitparse>=1.2`, not the
   official Garmin FIT SDK, so new post-2023 profile fields may decode as unknown.
   Reframe #2 as "SDK-grade decoding," scoped to the parser.

3. **#10 (PR/best-efforts) is partly shipped.** The Insights view already computes
   longest distance/duration, biggest climb and fastest average speed. Only
   time-window best-efforts and per-sport bests remain — so it's smaller than a
   full "Next" item.

4. **#1 (zones) and #4 (training load) shared a missing prerequisite** — there was
   nowhere to store athlete thresholds. This PR adds an `athlete` config section
   (`max_heart_rate`, `resting_heart_rate`, `ftp_w`); #4's TSS/TRIMP work can reuse
   it.

5. **Gap-matrix nits.** For the Fenix5Sync row today, *wellness/sleep* is ○ (no
   wellness data is ingested at all — only activity files), and *offline maps* is
   nearer ○→◐ (a polyline, not a map). Both are shown slightly generously.

---

## Still-valid technical findings

- **R1 — FIT decoding is `fitparse`, not SDK-grade.** This is now the core of
  what's left in #2. Mitigated by defensive parsing (corrupt files skipped,
  unknown fields preserved in `extra`) and by the raw passthrough, but parsed
  *analytics* still inherit fitparse's profile coverage.
- **R2 — the dedup "hub" (#7) can't reuse the existing dedup.** `core/dedupe.py`
  is exact SHA-256 of bytes; the same run as a watch `.FIT` and a Strava `.GPX`
  hash differently. The hub needs semantic matching (start-time/duration/distance/
  GPS), which is a different, harder mechanism.
- **R3 — athlete thresholds were absent.** Addressed in this PR for zones (#1);
  carry it forward for training load (#4).

---

## What shipped alongside this validation

The TCX-export "quick win" the brief implied was missing turned out to already be
done, so the code work was redirected to the brief's **#1 RICE item, HR & power
zones**, which was genuinely absent:

- `core/zones.py` — pure 5-zone HR (% max) and 7-zone power (% FTP, Coggan)
  time-in-zone, integrated from trackpoint timestamps (pauses/gaps excluded).
- `athlete` config section + API schema + validation.
- `GET /api/activities/{id}/zones`.
- A "Training zones" card on the activity page (hidden when there's nothing to
  show; HR falls back to the observed max when no threshold is configured).
- Tests in `tests/test_zones.py` (core binning, fallbacks, API, config roundtrip).

The genuine next "Now" gaps after this are **#4 training-load** (reusing the new
`athlete` thresholds) and **#2 SDK-grade FIT decoding**.

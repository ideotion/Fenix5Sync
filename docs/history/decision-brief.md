# Liberate Your History — decision brief

**Decision date:** 2026-06-22 · **Status:** shipped (foundation)

## Why this feature exists

Direct-from-device sync only captures *recent* activities — the watch doesn't
hold your whole history, and Garmin's website/API cap activity export at ~5 years.
The complete record lives in the **account export**:

- Garmin's GDPR **Full Data Export** returns everything in original FIT/GPX/TCX as
  a nested zip-of-zips with gzip-compressed files (deleted a few days after it's
  generated).
- Strava's **bulk data download** ships `*.fit.gz` / `*.gpx.gz` plus a CSV.

Crucially, free data downloads and device integrations are **exempt** from the
2025–2026 API paywalls — so while the live APIs are closing, the export path is
wide open and durable. This feature completes the project's core wedge ("escape
from Connect/Strava"): direct-from-device gets the recent activities; the export
gets the *history*.

## What it does (foundation)

- Expands an account export (the downloaded `.zip`, including Garmin's
  zip-of-zips, or an already-unzipped folder) by recursively extracting nested
  zips and decompressing `*.<fmt>.gz` activity files — **into a temp dir, never
  modifying the source**.
- Feeds the surfaced FIT/TCX/GPX through the normal import pipeline, so everything
  is parsed losslessly and **content-deduplicated** against the existing archive
  (a watch sync and a cloud export of the same activity collapse to one).
- New `export` source mode, a `POST /api/sync/import-export` endpoint, a GUI
  panel on Import/Sync, and a `fenix5sync import-export PATH` CLI command.

Safety: zip members are checked for path traversal ("zip slip") at every level,
and recursion is depth-bounded against pathological archives.

## Honest scope / follow-ups

This foundation surfaces the **activity files**. Deliberately deferred:

- **Sidecar metadata enrichment** — Strava's `activities.csv` (names, gear,
  perceived effort) and Garmin's CSVs are not yet merged onto imported activities.
- **Apple Health `export.xml`** — the large workout XML (and `workout-routes/`)
  is a separate streaming parser, not yet implemented.
- **Wellness CSVs** (sleep/HRV/stress) in the dump route to the wellness track.

These are tracked as the next steps for this capability.

## Sources

1. *Strava declares war on scrapers ahead of IPO* (downloads & device integrations exempt) — TechCrunch, 2026-06-01. <https://techcrunch.com/2026/06/01/strava-declares-war-on-scrapers-ahead-of-ipo/>
2. *How to Export Your Garmin Data (FIT, CSV, and Third-Party Apps)* — Gneta, 2026-04-16. <https://www.gneta.app/blog/export-garmin-data-guide>
3. *Garmin quietly confirms more features will likely be paywalled* — TechRadar, 2025. <https://www.techradar.com/health-fitness/smartwatches/garmin-quietly-confirms-our-worst-fears-about-garmin-connect-says-more-features-will-likely-be-paywalled-in-the-future>

# Personal privacy audit — decision brief

**Decision date:** 2026-06-22 · **Status:** shipped

## Why this feature exists

GPS activity data de-anonymizes easily. The start and end points of activities
cluster tightly around the places that matter most — home and work — and the
weekday/time regularity of those visits exposes a routine. The canonical
cautionary tale is Strava's 2018 global heatmap, which inadvertently revealed the
location and patrol routes of military bases. Strava's own 2024 justification for
tightening its API conceded that users are often "unaware their data is surfaced
in a public feed or heatmap."

Fenix5Sync already ships strong anonymization primitives (privacy-radius nulling,
GPS fuzz/drop, device/personal stripping, date shifting) but offered no *evidence*
of why or how much to apply. This audit makes that actionable, and does so in a
way only a no-cloud tool credibly can: it is the **inverse** of a public heatmap —
a defensive self-audit of your own data, run locally.

## What it computes (and its guardrails)

- Clusters activity start points to surface the most-exposed places (likely home
  first), with counts, spread, first/last seen and weekday/time regularity.
- Recommends a privacy radius that would mask the most-exposed cluster, and
  reports how many activities a scrub at that radius would cover.
- Compares against the user's currently configured radius.

Guardrails: summary-only (cheap, offline); inferences are explicitly
probabilistic; the inferred "home" is computed on demand and **never persisted**;
framed strictly as defensive (protect yourself), never as surveillance.

## Sources

1. *Fitness tracking app Strava gives away location of secret US army bases* — The Guardian, 2018-01-28. <https://www.theguardian.com/world/2018/jan/28/fitness-tracking-app-gives-away-location-of-secret-us-army-bases>
2. *Updates to Strava's API Agreement* — Strava Press, 2024-11-19. <https://press.strava.com/articles/updates-to-stravas-api-agreement>
3. *Strava's new API agreement will destroy the app, users warn* — Cybernews, 2024-11-20. <https://cybernews.com/security/strava-changes-api-agreement/>

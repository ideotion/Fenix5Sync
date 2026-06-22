# Personal segments — decision brief

**Decision date:** 2026-06-22 · **Status:** shipped (foundation)

## Why this feature exists

"Am I getting faster on this route?" is one of the few comparison features
amateur athletes genuinely rely on. Strava's segment *leaderboards* are a
paywalled, cloud, social feature, and the broader paywall creep (a flat
subscription for API access from June 2026; the Year-in-Sport recap walled in
Dec 2025) pushes users to look elsewhere for the basics.

A **private, self-only** segment explorer is something the social incumbents
can't offer without contradicting their model: no global leaderboard, no kudos,
no account. It also partly fills the project's own roadmap gap for repeatable
personal segments and time-window best efforts.

## Design

- A **segment** is an ordered sequence of waypoints (subsampled from a reference
  activity's GPS track) plus a corridor tolerance. This encodes route shape and
  direction while tolerating GPS noise — more robust than raw line geometry.
- An **effort** is produced when an activity's track passes within the corridor
  of every waypoint in order; the effort time spans the first to the last
  waypoint. Distance prefers the activity's own cumulative distance.
- Efforts are ranked fastest-first (a private leaderboard) and ordered
  chronologically (a progress trend).

All matching is local and read-only; it loads trackpoint series only for the
segment's sport (an N+1 pruned by sport + GPS signal), as the all-time records
endpoint already does.

## Sources

1. *Strava declares war on scrapers ahead of IPO* (API behind a flat fee; free downloads/device integrations exempt) — TechCrunch, 2026-06-01. <https://techcrunch.com/2026/06/01/strava-declares-war-on-scrapers-ahead-of-ipo/>
2. *Dear Strava, we have a paywall problem that's gone a step too far* — T3, 2025-12-24. <https://www.t3.com/tech/dear-strava-we-have-a-paywall-problem-thats-gone-a-step-too-far>

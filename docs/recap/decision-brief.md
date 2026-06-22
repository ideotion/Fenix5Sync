# Year in Sport — decision brief

**Decision date:** 2026-06-22 · **Status:** shipped (foundation)

## Why this feature exists

The end-of-year "recap" (Strava's *Year in Sport*, Garmin's *Rundown*) was a free
feature for roughly a decade. In December 2025 both major platforms moved their
recap behind a paid subscription within days of each other, drawing broad
criticism that the move "paywalled emotion" — the pain reported was social and
emotional (being locked out while friends share cards), not the price itself.

A recap computed **locally, from data the user already owns** restores a feature
that used to be free, and does so in a way the cloud products structurally can't:

- **No account, no cloud.** It runs over the local SQLite archive; nothing leaves
  the machine.
- **Ownable artifact.** The share output is a single self-contained HTML file that
  anyone can open with no login — a file, not an engagement hook.
- **Honest scope.** It reports only what the archive actually contains; it never
  fabricates platform-derived scores.

This is also the project's best low-effort acquisition vehicle: the shareable card
is the screenshot people post when recommending the tool.

## What it computes

Per calendar year (and all-time): totals (count, distance, duration, ascent,
calories), per-sport and per-period breakdowns, headline highlights (longest
distance/duration, biggest climb, fastest average), the biggest single day,
consistency metrics (active days, longest streak), the busiest month, and a
year-over-year delta. All derived from activity *summaries* — no trackpoints, so
it is cheap and fully offline.

## Sources

1. *Strava Puts Popular 'Year in Sport' Recap Behind an $80 Paywall* — Ars Technica via Slashdot, 2025-12-19. <https://news.slashdot.org/story/25/12/19/2158235/>
2. *Garmin locks year-in-review behind subscription paywall* — Notebookcheck, 2025-12-04. <https://www.notebookcheck.net/Garmin-locks-year-in-review-behind-subscription-paywall-users-react-angrily.1177473.0.html>
3. *Strava follows Garmin in locking its Year in Sport behind a paywall* — Gadgets & Wearables, 2025-12-20. <https://gadgetsandwearables.com/2025/12/20/strava-year-in-sport/>
4. *Dear Strava, we have a paywall problem that's gone a step too far* — T3, 2025-12-24. <https://www.t3.com/tech/dear-strava-we-have-a-paywall-problem-thats-gone-a-step-too-far>

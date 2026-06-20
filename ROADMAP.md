# Fenix5Sync — Roadmap Prioritization Brief

> **Product research brief · v1 · June 2026.** Where a local-first, fully offline
> Garmin extractor should invest next, read against what is pushing engaged
> athletes off the incumbent platforms right now.
>
> This is the Markdown rendering of the original brief
> ([`docs/roadmap-brief.html`](docs/roadmap-brief.html)). For how each item maps to
> the **actual codebase** — what already shipped vs. what's still open — see
> [`docs/roadmap-validation.md`](docs/roadmap-validation.md).
>
> The matrix and RICE numbers are analyst judgment, not benchmarked measurements —
> revalidate before committing engineering quarters.

---

## A. Executive summary

Fenix5Sync is entering its market at an unusually favourable moment. Within the
last 18 months the two dominant platforms have each, in effect, advertised the
exact value proposition Fenix5Sync embodies.

Garmin's March 2025 launch of the paid *Connect+* tier drew a backlash large
enough that a single boycott thread reached roughly ten thousand upvotes — driven
less by the $7/month price than by the fear that a historically subscription-free
platform had started down the road of paywalling future features. In November
2024, Strava's API clampdown broke the third-party "data hub" model in parallel:
connected apps may no longer show a user's data to anyone but that user, which cut
coaches off from athletes' synced activities and explicitly barred AI/analytics
use of exported data.

The net effect is a primed audience that wants to own its history and keep real
analytics, without a cloud account — and no existing tool fully serves it.
GoldenCheetah is local but cycling-power-centric with a steep interface;
Intervals.icu and Runalyze have the analytics depth but are cloud-hosted and
depend on the very sync pipes Strava just throttled; the self-hosted servers
(Endurain, FitTrackee, wger) own the data but offer shallow endurance analysis and
no direct-from-watch ingestion. Fenix5Sync's opening is the intersection none of
them occupy: **trustworthy local-first ingestion straight off the device, with
honest analytics and offline maps in a modern GUI.**

---

## B. User segments & top unmet needs

| Segment | Top unmet need |
|---|---|
| **01 · Privacy / data-sovereignty** | Lossless local ownership, zero telemetry, auditable open formats. |
| **02 · Ex- / supplementing-Connect** | Leave or hedge Garmin Connect after the paywall signal while keeping metrics and re-exporting to Connect-friendly formats. |
| **03 · Multi-device / multi-platform** | One local store that merges Garmin plus imported Strava/other exports and de-duplicates. |
| **04 · Serious endurance / quantified-self** | Intervals/Runalyze-grade training-load and physiology analytics. |
| **05 · Linux users** | A tool that simply works with a watch on Debian/Ubuntu, where Garmin ships no native desktop support. |

**Cross-cutting job-to-be-done:** *"Plug in my watch and get a private,
searchable, exportable database with analytics and an offline map — in one app I
trust."* No current product does all of this.

---

## C. Competitive gap matrix

Strong = ●, partial = ◐, weak/absent = ○.

| Tool | Data ownership | Analytics depth | Device direct-read | Offline maps | Wellness / sleep | Platform reach |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Garmin Connect | ○ | ● | ● | ● | ● | ● |
| Strava | ○ | ◐ | ◐ | ● | ○ | ● |
| GoldenCheetah | ● | ● | ◐ | ◐ | ○ | ◐ |
| Runalyze | ◐ | ● | ◐ | ◐ | ◐ | ◐ |
| Intervals.icu | ○ | ● | ◐ | ◐ | ◐ | ◐ |
| wger | ● | ○ | ○ | ○ | ◐ | ● |
| Endurain / FitTrackee | ● | ◐ | ◐ | ◐ | ○ | ◐ |
| GarminDB | ● | ◐ | ◐ | ○ | ◐ | ○ |
| **Fenix5Sync ↗ target** | **●** | **◐→●** | **●** | **◐→●** | **◐** | **◐** |

The white space is the combination Fenix5Sync can own: genuinely local +
direct-device, plus honest analytics and offline maps.

---

## D. Prioritized feature list (RICE)

`RICE = Reach × Impact × Confidence ÷ Effort`, relative to the existing baseline
(USB extraction, raw + SQLite + NDJSON storage, charts, basic GPS track,
multi-format export, optional anonymization). Reach is a 1–10 share-of-target
proxy; Impact 0.5/1/2/3; Confidence 0.5/0.8/0.9; Effort in person-months. With no
usage telemetry, treat ordering as directional.

| # | Feature (delta on baseline) | R | I | C | E | RICE | Tier | Rationale |
|---|---|:--:|:--:|:--:|:--:|:--:|---|---|
| 1 | HR & power zone analytics | 8 | 2 | .9 | 2 | **7.2** | Now | Cheap once parsing is solid; first thing power/HR users check. |
| 2 | Round-trip multi-format interop | 9 | 3 | .9 | 4 | **6.1** | Now | The mechanism to leave/consolidate; FIT churn makes robustness the moat. |
| 3 | Harden cross-generation device ingestion | 10 | 3 | .9 | 5 | **5.4** | Now | "Plug in → local DB" reliably; the foundational enabler. |
| 4 | Training-load & form (CTL/ATL/TSB) | 8 | 3 | .85 | 4 | **5.1** | Now | The headline reason serious users prefer Intervals/Runalyze. |
| 5 | Strengthen + automate anonymized export | 6 | 2 | .85 | 2 | **5.1** | Now | Turns the privacy promise into a shareable artifact no cloud tool matches. |
| 6 | Distribution & trust hardening | 8 | 2 | .85 | 3 | **4.5** | Next | `.deb` + Flatpak/AppImage, signed reproducible builds; widens reach. |
| 7 | Multi-device consolidation + dedup hub | 7 | 3 | .8 | 4 | **4.2** | Next | Fills the cross-app history hole Strava's API clampdown opened. |
| 8 | Full offline vector maps + routes | 9 | 2 | .8 | 4 | **3.6** | Next | Expected for any GPS app; MapLibre + bundled OSM extracts. |
| 9 | VO₂max trend + race-time predictions | 7 | 2 | .7 | 3 | **3.3** | Next | Commonly expected; be explicit it differs from Garmin's FirstBeat figure. |
| 10 | PR / best-efforts tracking | 7 | 2 | .7 | 3 | **3.3** | Next | Low-effort retention; table-stakes parity. |
| 11 | Gear / equipment mileage + reminders | 6 | 1 | .7 | 1.5 | **2.8** | Later | Popular parity feature; demand inferred. |
| 12 | Sleep / HRV / recovery from raw FIT | 6 | 2 | .6 | 3 | **2.4** | Later | Show raw signals honestly; can't replicate Body Battery. |
| 13 | Manual + strength/gym logging | 5 | 1 | .6 | 3 | **1.0** | Later | Consolidates wger-style use, but tangential to the endurance wedge. |
| 14 | Optional local LLM insights (Ollama) | 4 | 2 | .4 | 6 | **0.5** | Later | Answers the private-AI appetite, but high effort and unproven. |

**Sequencing caveat.** RICE under-weights foundational work: HR/power zones top the
list only *because* they are cheap once data is flowing. Device ingestion and
interop must ship first regardless of their slightly lower per-unit scores.

---

## E. Top 3 wedge opportunities

1. **The escape hatch from Connect & Strava (timing).** One-action, fully offline
   capture of a user's Garmin history into a lossless local store, plus clean
   re-export to Connect-friendly TCX/FIT, so leaving or hedging costs nothing.
   Lands on the Connect+ paywall anxiety and the Strava API breakage.
2. **Direct-from-device ingestion that actually works on Linux (moat).** Solving
   MTP/USB cleanly across watch generations — read-only and offline — is a hard,
   fiddly capability competitors won't casually replicate, and it seeds every other
   feature.
3. **Honest, private analytics depth + offline maps in one modern GUI
   (differentiation).** Intervals/Runalyze-grade training-load and physiology views
   plus full offline OSM maps, all local — and transparent about what can and can't
   be reproduced versus Garmin's proprietary scores.

---

## Method, risks & evidence quality

Sourcing prioritized recent primary material: vendor announcements (Strava,
Garmin), tech press (TechRadar, gHacks, DC Rainmaker), and developer/community
sources (Garmin forums, GitHub, Hacker News). Strongest evidence is the Connect+
backlash and the Strava API change, each corroborated across multiple 2024–25
sources. The Linux MTP/USB mechanics rest on 2019–22 primary sources that remain
accurate but should be revalidated against current firmware. Gear-mileage and
PR-tracking demand are inferred from competitor parity (thin evidence).

**Format & legality.** GPX and TCX are open XML schemas, and Garmin's FIT SDK is
free for decoding. The legal sensitivity sits with scraping Connect's web service,
which Fenix5Sync sidesteps by reading local files and treating the device as
strictly read-only. These are software tools processing sensor-derived numbers,
not diagnostic outputs — no medical-device obligations attach. The main interop
risk is FIT format churn (profile changes effective late 2023): robust, SDK-grade
decoding is the mitigation.

---

## Sources

See the source list in [`docs/roadmap-brief.html`](docs/roadmap-brief.html) (22
cited primary sources: Strava/Garmin announcements, DC Rainmaker, TechRadar,
gHacks, Garmin developer forums, GoldenCheetah/Runalyze/Intervals comparisons,
OpenMapTiles, and the FIT SDK).

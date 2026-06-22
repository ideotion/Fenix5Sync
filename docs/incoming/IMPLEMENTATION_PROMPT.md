# Autonomous implementation prompt — form-model + coach

Copy the block below into a fully-autonomous Claude Code session running on this repo.
All input data referenced is already committed under `docs/incoming/`
(see `docs/incoming/README.md` for provenance and the two engine schemas).

```text
# AUTONOMOUS IMPLEMENTATION SESSION — Fenix5Sync form-model + coach

You are an autonomous senior engineer in the `ideotion/Fenix5Sync` repo. Implement the
five workstreams below end-to-end (code, tests, docs), in small verified commits, with a
draft PR per workstream (WS1 first; others can stack on it). All input data is already in
the repo at `docs/incoming/` (see `docs/incoming/README.md` for provenance + schemas).

## REPO INVARIANTS (do not violate)
- Local-first/offline: no runtime network; server loopback-only; no telemetry.
- No new RUNTIME dependencies (stdlib + existing `defusedxml` only). Dev tools (ruff,
  bandit, pip-audit) via the `dev` extra are fine.
- Evidence-cited & honest: every health claim cites a bibliography id (or a NEW ref with
  DOI/stable URL); never fabricate; adjunct-not-treatment; PAR-Q+ gating; surface red
  flags; no weight-loss/medical-treatment claims; label conventions (E3/E4) as defaults,
  never as proven — in particular DO NOT assert the 10% rule or ACWR sweet-spot prevent injury.
- Accessibility: keep the prefers-reduced-motion static fallback; keyboard-operable.

## QUALITY GATES (run exactly; all must pass before each PR)
- `python -m venv .venv && .venv/bin/pip install -e ".[test,dev]"`
- `.venv/bin/pytest`  · `ruff check .`  · `bandit -ll -c pyproject.toml -r core server cli`
- `node --check` on every touched/added JS file
- Content JSON must pass the integrity tests (extend `tests/test_home_content.py`,
  `tests/test_taichi_content.py`); CI (tests py3.11/py3.12 + lint&security) green.
- Commit-message footer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- You CANNOT see pixels or hear audio — rely on automated checks; unit-test all math; add a
  "could-not-visually-verify" note to each PR.

## DATA (already in repo)
- `docs/incoming/home_exercises.engine.json` (35) — CURRENT engine schema:
  `views:{side:{poseName:{joints}}}`, `phases:[{name,dur,from,to,isHold?}]`, `cues`,
  `staticCues`, `object:{side,front}`, `targetReps`|`holdMs`, `isometric?`. New glyph: `counter`.
- `docs/incoming/home_exercises.library.json` (35) — metadata: pattern, tier, default/
  regression/progression objects, primary_benefit, refs (R01–R17), red_flags, notes.
- `docs/incoming/taichi_movements.json` (21) — ALT schema: single `view`,
  `phases:[{name,durationMs,cue,pose:{joints}}]`, `object`(str|null), `targetReps`,
  `isHold`, `holdMs`, `staticLabels`.
- `docs/incoming/taichi_library.json` (21) — metadata: level, focus, refs (R01–R14),
  red_flags, notes.
- `docs/incoming/coach_plan_params.json` — running-plan parameter block (phases, session
  mix, pace models, progression caps, taper, feedback, safety; each with evidence grade).

Joint model (shared): SVG viewBox 240×340, ground y=318, figure faces +x, feet planted
(toe ahead of ankle). SIDE joints: head,sh,hip,knee,ankle,toe,elb,hand. FRONT joints:
head,sh,hip,lknee,rknee,lankle,rankle,lelb,relb,lhand,rhand.

## WS0 — Schema reconciliation (do before WS2/WS3)
Canonical engine schema = the CURRENT one (views + named poses + phases{from,to} + cues +
staticCues). Write a one-off normalizer (a script or test helper) that converts
`taichi_movements.json` → canonical: for each movement, `views.<view>` = {phaseName: phase.pose};
`phases` = [{name, dur: durationMs, from: prevPhaseName, to: thisPhaseName}] looping the
last phase back to the first (for `isHold` movements keep the hold phase from==to);
`cues` = {phaseName: phase.cue}; `staticCues` = ordered list of phase cues; carry over
`object` (as {side|front: value}), `targetReps`/`holdMs`/`isHold`/`staticLabels`.
Keep poses 2-D (z=0). Validate output against the integrity tests.

## WS1 — Engine: pseudo-3D infra, feet fix, depth (do FIRST)
1. Pose schema accepts optional `z` per joint (`[x,y]` or `[x,y,z]`; missing z = 0 →
   fully back-compatible with all current/incoming 2-D data).
2. Add a `yaw` projection (pure function, UNIT-TESTED): `x' = 120 + (x-120)*cos(yaw) + z*sin(yaw)`,
   `y' = y`; add subtle depth shading from projected z.
3. Ship a gentle auto-yaw (≈±15°, slow) toggle for a 3-D feel now. NOTE honestly: a full
   front↔side turn needs authored z (all incoming poses are z=0, so 90° degenerates to a
   vertical line) — wire the yaw control/slider so it becomes a true turn once exercises
   gain depth, but keep per-view 2-D rendering as the default. Persist in prefs.
4. Feet: add a heel so the foot reads correctly; ensure toe leads the facing direction;
   add a mirror/face option (left/right). Fixes the reported wrong-facing feet.
5. Keep 60 fps (build nodes once, update attributes), and ALL existing prefs (trails,
   breath ring, depth shading, sound w/ per-theme timbre, figure Minimal/Cartoon, character
   Neutral/Female/Male) + the static reduced-motion fallback.
6. Add object glyphs: `counter` (Home), and `dumbbell` + `kettlebell` (weighted variants,
   tracking the hands/hips). Unit-test projection; `node --check` clean.

## WS2 — Home exercise library
Replace/extend `web/content/home/exercises.json` with `home_exercises.engine.json` (35,
incl. the full push-up progression). Wire `home_exercises.library.json` metadata into the
home content pack/docs. Add the `counter` glyph (WS1). Extend `tests/test_home_content.py`:
every phase references a real pose; every phase has a cue; every cited ref resolves; tiers/
patterns valid; objects exist in the glyph registry.

## WS3 — Tai Chi movement library
Normalize (WS0) `taichi_movements.json` into `web/content/taichi/movements.json` (replacing
the 2 hand-authored stubs). Wire `taichi_library.json` (level/focus/refs/notes) into the
Tai Chi content pack/docs. Extend `tests/test_taichi_content.py` accordingly (phase↔pose,
citation resolution to R01–R14). Keep the honest "simplified pacer, not instructed form".

## WS4 — Coach: objective → personalized plan → ICS
1. `core/plan_builder.py` (pure/stdlib): encode `coach_plan_params.json` as a tunable
   constant; map an objective {goal_distance(5k/10k/half/marathon/general), start_date,
   target_date OR weeks, target_time?, sessions_per_week?, available_days, level} →
   CoachGoal + horizon → reuse `core/coach_plan.py:compute_plan` → a dated agenda
   (base→build→peak→taper→race, step-back/deload weeks, a tune-up effort, rest days) with
   per-session type, target (pace via VDOT/Riegel/Karvonen/RPE — present as RANGES with
   confidence), rationale, and the evidence grade. Honor every honesty rule (no false
   precision; widen ranges for low mileage; never assert 10%/ACWR as protective).
2. `core/ics.py` (stdlib): minimal RFC-5545 VCALENDAR writer — one VEVENT per session
   (DTSTART per date, SUMMARY=type, DESCRIPTION=target+rationale+basis, UID, DTSTAMP, CRLF
   folding). Unit-test it parses/round-trips.
3. API: `POST /api/coach/plan` (agenda JSON) + `GET /api/coach/plan.ics` (download).
   CLI: `fenix5sync plan ...` (+ `--ics PATH`). UI: a simple objective form in the Coach
   tab → weekly-plan preview → "Export .ics"; sources discreet; "not medical advice / get
   clearance" framing.
Acceptance: deterministic plan + valid ICS (both unit-tested); endpoints+CLI+UI wired.

## WS5 — GUI Session Builder (Home + Tai Chi), with length/series/weights/coverage
Derivations (apply since the incoming metadata lacks these fields):
- `region` from `pattern`: squat|hinge|carry|calf→lower_body; push|pull|press|row|raise|
  curl→upper_body; rotation|isometric(plank/anti-rot)→core; balance→balance; aerobic→cardio;
  hinge-flow/mobility→mobility; multi-joint carries→full_body.
- `equipment`: all support bodyweight/household; squat,hinge,pull,row,press,raise,curl,carry,
  lunge also support `weights` → generate a `weighted_variant` (swap object→`dumbbell`/
  `kettlebell` + cue "choose a weight you could lift ~12+ times"). Balance, mobility, cardio
  snacks, all isometrics, and all Tai Chi = bodyweight-only.
Builder (a pure SELECTION function + a UI):
- Inputs (persist in localStorage): session length (5/10/15/20/30/45 min), sets per exercise
  (1–4) and reps/work-seconds, equipment (Bodyweight / Household / Free weights), tier
  (from screening), optional focus (default Full body).
- Home rules: every session covers ≥1 lower_body, ≥1 upper_body, ≥1 core, and (mandatory at
  the fragile/entry tier) ≥1 balance; fill remaining time with cardio snacks; no two
  consecutive exercises share a region; don't repeat exercises; vary across sessions; pack to
  the time budget (sets×(reps×tempo or work_seconds)+rest), warm-up first/cool-down last;
  respect tier + PAR-Q+ gating (isometrics behind clearance); "Free weights" uses
  weighted_variant where available else bodyweight.
- Tai Chi rules: length-adjustable session covering balance+mobility+lower-limb+breathing by
  `focus`; balance mandatory at fragile level; no weights; opening warm-up + closing cool-down.
- Player: a "session mode" chaining selected exercises through the form-model engine with a
  rest screen + progress ("3/8") + a completion summary. Offline.
- Coach (WS4) cross-training/strength days draw from this builder so they're body-part varied.
Acceptance: UNIT-TEST the selection logic (region coverage, no-repeat-region, time budget,
weights substitution, gating); UI controls wired; runs through the engine.

## DELIVERABLES
- WS0–WS5 implemented with tests; all gates green; draft PR(s) to `main`; README + CHANGELOG
  updated; `docs/incoming/` may be deleted once wired (its data now lives in `web/content/`).
- Each PR: what changed + a short "not visually/audibly verified" note (avatars/audio need a
  human glance). If any incoming datum is internally inconsistent, fix minimally or leave a
  TODO with a safe default — never invent evidence or paces.
```

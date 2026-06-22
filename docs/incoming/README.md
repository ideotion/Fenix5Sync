# Incoming data — staging inputs for the form-model + coach implementation

These files are **research/authoring outputs** staged for an implementation session.
They are **inert**: not served by the web app (only `web/` is mounted) and not loaded
by tests. The implementation session validates, normalizes, and wires them into the
app, then these can be removed.

## Files & provenance
| File | What | Items |
|------|------|-------|
| `home_exercises.engine.json` | Home/Sports-at-Home form-model exercises (animation) | 35 |
| `home_exercises.library.json` | Home exercises metadata (pattern, tier, objects, refs, notes) | 35 |
| `taichi_movements.json` | Tai Chi form-model movements (animation) | 21 |
| `taichi_library.json` | Tai Chi movement metadata (level, focus, refs, notes) | 21 |
| `coach_plan_params.json` | Running-plan parameter block (Appendix A of the coach science reference) | — |

Bibliographies: Home cites the Sports-at-Home report ids (R01–R17); Tai Chi cites the
Tai Chi report ids (R01–R14); the coach params cite the running-science reference.

## IMPORTANT — two different engine schemas (must be reconciled)
- **`home_exercises.engine.json`** uses the **current engine schema**:
  `views: { side: { "<poseName>": {joints} } }`, `phases: [{name, dur, from, to, isHold?}]`,
  `cues: { phaseName: text }`, `staticCues: [...]`, `object: {side, front}`,
  `targetReps` or `holdMs`, `isometric?`. New object glyph used: **`counter`** (plus
  `chair`, `wall`). Some poses are floor/lying (e.g. push-ups, towel slider) — valid.
- **`taichi_movements.json`** uses a **self-contained phase schema**:
  single `view`, `phases: [{name, durationMs, cue, pose: {joints}}]`, `object` (string|null),
  `targetReps`, `isHold`, `holdMs`, `staticLabels` — **no** `views`/`from`/`to`/`cues`/`staticCues`.

The implementation session must normalize Tai Chi into the canonical engine schema
(build `views.<view>` from each phase's `pose` keyed by phase name; `phases` reference
consecutive pose names looping back to the first; `cues` = {phaseName: cue};
`staticCues` = the ordered phase cues), OR have the engine accept both. Joint model is
the shared 240×340 space (GROUND_Y 318); poses are 2-D (`z` = 0 under the pseudo-3D engine).

## Metadata fields not yet present (derive per the addendum)
The library files carry `pattern`/`tier`/objects/`refs`/`notes` (Home) and
`level`/`focus`/`refs`/`notes` (Tai Chi) but not explicit `region`/`equipment`/
`weighted_variant`/`default_sets`/`rep_range`. Derive `region` and `equipment` from
`pattern` per the master prompt's derivation rules; generate weighted variants for the
externally-loadable patterns.

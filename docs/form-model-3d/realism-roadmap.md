# Form-Model Realism Roadmap — precise, graceful, themeable 3-D movement guidance

The long-run plan to take the movement figure from today's simplistic capsule
mannequin to **realistic, precise, pleasing 3-D guidance** — full-body articulation
(arms, legs, shoulders, head, hips, knees, **hands, fingers, feet**), for both Tai
Chi and home sport (push-ups, chairs, walls, bottle packs, book piles, bed, sofa),
with **male/female avatars**, **cultural + animal themes**, and **per-theme sound**
— everything open-source, offline, and honest.

This document is the plan of record. It builds on (and does not replace) the
12-PR realism mission and the technical constants appendix; each phase below says
which mission PRs it consumes.

---

## 0. Where we actually are (audited 2026-08, verify before depending on it)

| Layer | State |
|---|---|
| Motion core (`web/js/pose3d.js`) | 12 bones; quats, FK, 2-D→3-D adapter; **root travel (PR1), foot grounding (PR2), AAOS-cited joint limits (PR3+), axial twist DoF (PR4)** — all merged/landing; unit-tested under the pytest node gate |
| Motion data | 35 home + 21 Tai Chi movements, **all single-view**, 2–4 keyframes each, **zero** hand-authored `poses3d`, no depth, no twist, no timing nuance |
| Renderers | SVG 2-D (default + reduced-motion), canvas 3-D volumetric (beta, no deps), three.js skinned-avatar **seam planned** (mission PR12) |
| Skeleton gaps | no segmented spine, no clavicles/neck, **no wrists/hands/fingers**, no toes → no shoulder shrug, no spinal curve ("grace"), no Tai Chi palms, no foot roll |
| Presentation | themes = dark/light only; characters = neutral/female/male silhouette cues (2-D engine only); sound = 2 synth palettes keyed to visual theme (opt-in) |
| Constraints | GPL-3.0; offline at runtime; no build step; license allowlist CC0/MIT/Apache-2.0/BSD/CC-BY; **no committed binaries (current policy — a decision point below)**; hard-reject Mixamo/SMPL/AMASS/RPM |

## 1. Root-cause ordering — why it looks simplistic

Realism is a **product**: `motion data × skeleton × interpolation × mesh ×
environment × sound`. Weakest factor dominates. In order of current damage:

1. **Motion-data poverty** (worst): 2–4 flat keyframes per movement cannot encode
   amplitude, sequencing, or flow, whatever the renderer does.
2. **Skeleton poverty**: a rigid single spine cannot curve (no grace); no hands
   means Tai Chi palm work — the heart of the form — is invisible.
3. **Interpolation**: linear slerp pose-to-pose stops dead at each keyframe;
   graceful movement flows *through* poses.
4. **Mesh/rendering**: capsules, no skinning, no materials — the visible symptom,
   but only fourth in causal order.
5. **Environment/sound**: context and pleasure, last.

**Rule for the whole roadmap: fix in causal order.** A photoreal avatar playing
2-keyframe motion is *worse* (uncanny) than a mannequin playing beautiful motion.

## 2. What "good" means (operationalized, testable where possible)

- **Precision**: each movement carries target joint angles per phase (from the
  AAOS/functional ROM appendix) with tolerance bands; an "amplitude audit" test
  compares achieved vs target. Teaching angles (knee-over-toe, neutral spine,
  elbow path) are visible from the authored camera.
- **Smoothness**: C1-continuous joint velocity through keyframes (measured: no
  angular-velocity discontinuities above threshold; max-jerk metric per movement).
- **Grace** (esp. Tai Chi): visible spinal curvature; weight transfer *leads*
  the movement; near-constant-speed "flow" pacing (suppressed ease-in/out);
  breath-coupled tempo; continuous curved (not linear) root paths; live hands.
- **Amplitude**: full, functional range — a squat reaches real hip flexion, a
  Tai Chi shift transfers weight fully — verified against Section A functional
  values, not eyeballed.
- **Pleasing**: soft light, grounded contact shadows, coherent theme palettes,
  gentle secondary motion (breath, sway) — bounded, reduced-motion-safe.
- **Honest**: Tai Chi remains "a simplified pacer, not instructed form" until a
  qualified instructor reviews an entry; home movements remain guidance with
  PAR-Q+ gating; no anatomical claim without a source.

## 3. Architecture: five independently shippable layers

```
L5  Sound        per-theme procedural soundscapes + movement cues
L4  Presentation avatars (M/F/animal) · themes (environment+palette+music) · props
L3  Renderers    SVG (a11y floor) · canvas 3-D (universal) · WebGL avatar (realism tier)
L2  Motion data  per-movement JSON: bone tracks · hand shapes · root path · contacts · timing
L1  Motion core  skeleton vN · quats/FK/IK · constraints (limits, grounding, COM)
```

Contracts between layers are versioned (skeleton version, pose schema version).
Renderer-specific code never leaks into L1/L2. Every layer keeps the one below's
tests green.

## 4. Skeleton evolution (versioned, migration-tested)

**SKEL-1 (today)**: 12 bones.

**SKEL-2 — posture & grace** *(mission PR6; near-term)*
- Split spine → **lumbar / thoracic / cervical** + separate **neck**; add
  **clavicles**; add **toe joints** (pairs with the heel for foot roll).
- ≈ 19–21 bones. Per-segment limits from the appendix (Apti 2023: lumbar barely
  rotates axially ~5–13° total; thoracic supplies trunk rotation — encode this,
  it is exactly what makes trunk motion look human).
- Migration: the 2-D adapter distributes the old single-spine rotation across
  segments (weighted: lumbar-dominant flexion, thoracic-dominant rotation);
  every existing movement must resolve to a valid pose on SKEL-2 (test), both
  renderers keep working (test), visual-regression re-baseline (human-approved).

**SKEL-3 — hands & wrists** *(the Tai Chi unlock; mid-term)*
- Add wrists + full finger joints (15/hand) **but author via hand-shape presets,
  not per-finger curves**: a curated library of ~12 shapes —
  `relaxed, open-palm, taichi-palm, hook-hand, fist, grip-bottle, grip-book,
  flat-press (wall/floor), spread-balance, point, cup, support-lean` — each a
  stored set of finger-joint rotations. A movement references
  `{phase: {handL: "taichi-palm", handR: "hook-hand", blend: ms}}`; the core
  blends shape-to-shape. 90 % of hand realism at 5 % of authoring cost; per-finger
  override remains possible for special cases.
- ≈ 53 joints total. Still trivial for attribute-update rendering.

**SKEL-4 (optional, far)**: gaze direction + blink timing (cheap life, no mesh
face needed at mannequin tier).

## 5. The movement-realism program (the heart of this roadmap)

### 5.1 Interpolation upgrade — flow through poses
Replace pose-pair slerp with **quaternion Catmull-Rom/SQUAD splines across the
whole phase sequence** so velocity is continuous through keyframes. Per-phase
easing (mission PR5) for reps (slow eccentric 2–4 s / concentric 1–2 s per the
tempo appendix); **near-constant-speed profile for Tai Chi** (flow reads as grace;
aggressive ease-in/out reads as robotic). Testable: velocity continuity + per-phase
duration conformance.

### 5.2 Sequencing & overlap — bodies don't move joints in unison
Per-bone onset offsets (proximal leads distal, ~40–120 ms in reaching; hips lead
knees in squats; gaze leads turns). Defaults per movement pattern
(squat/hinge/push/pull/flow…), overridable per movement. Bounded and tested.

### 5.3 Amplitude & precision audit
Per movement: target functional angles (Section A) → an automated report card
(achieved ROM vs target, grounding, limits, COM-over-base [mission PR7 +
Dempster/Winter constants], max-jerk). CI publishes the card; regressions block.

### 5.4 Tai Chi grace pack
Curved (elliptical) root weight-paths; thoracic-led counter-rotation; hand-shape
choreography (SKEL-3); breath-coupled phase durations (in-breath rise / out-breath
sink, ~14–16 br/min idle → slower with practice); a "continuity index" (no
zero-velocity dwell except authored holds).

### 5.5 Secondary motion (mission PR5)
Breath oscillation on chest/shoulders during holds; sub-1 Hz, few-mm postural
sway (appendix D.1); tiny critically-damped lag on distal joints. All bounded,
all off under `prefers-reduced-motion`.

### 5.6 Contacts & props — the home-sport unlock
A **contact schema** per movement phase: `{joint, target: plane|propAnchor,
window}`. Feet pin to floor (shipped); palms pin flat to **wall** during wall
push-ups; hips to **chair** seat; hands to **bottle-pack / book-pile / bed / sofa**
anchors. Solved with the existing two-bone IK. Props become first-class 3-D
objects (procedural geometry first — zero binaries): chair, wall, counter, step,
bottle pack, book pile, bed, sofa — each with named anchors and themed materials.
Tested: contact-window pinning within tolerance; no interpenetration on the prop's
bounding volume.

### 5.7 Motion data at scale — four tracks in parallel
1. **Automatic uplift** of all 56 (cheap, ships first): improved adapter +
   SKEL-2 spine distribution + pattern-default sequencing + per-phase easing +
   hand-shape defaults per pattern (`push→flat-press`, `carry→grip-bottle`,
   Tai Chi→`taichi-palm`…).
2. **Hero set** (~10 movements: full push-up, bodyweight squat, chair sit-stand,
   wall push-up, plank, commencement, cloud hands, weight shift, brush knee,
   golden rooster) hand-authored as full SKEL-3 `poses3d` with 6–12 keyframes,
   contacts, hand choreography — the quality exemplars and regression anchors.
3. **Self-mocap authoring tool** (mission PR10; **MoveNet** per appendix E —
   weights confirmed Apache-2.0; shin-axis foot fallback for its missing foot
   landmark) so a contributor can record themselves and export draft JSON to
   clean up — this is how the library grows beyond us.
4. **MIF (Movement Interchange Format)** formalization: the versioned schema +
   validator + provenance/license/review fields, so community entries scale
   (crossfit/martial-arts later live here, out of current scope).

### 5.8 Verification & honesty gates
- Machine: biomech validator (PR7), report cards (5.3), visual-regression harness
  (PR8 — baselines **human-approved**, never self-approved), reduced-motion parity
  as a permanent release gate.
- Human: screenshot+vision loops in connected sessions for look; a **qualified
  instructor review program** for Tai Chi form claims — until an entry is
  reviewed, it keeps the "simplified pacer" label. Movement correctness for a
  fragile audience is a governance problem, not a data-entry problem.

## 6. Avatars — realistic male/female (and animals) on the same motion

- **WebGL tier** (mission PR12 scaffold → swap seam): three.js **r178 pinned**
  (MIT; symbols + API traps verified in appendix F: no-arg `SMAAPass()` /
  `OutputPass()` / `RoomEnvironment()`; `OutputPass` last; detect WebGL2 *before*
  constructing; `RoomEnvironment` PMREM = asset-free image-based lighting).
- **Bodies**: CC0 only. Two style options, both license-clean:
  *stylized-clean* (Quaternius Universal Base, ~13 k tris, reads instantly) vs
  *realistic-mannequin* (MakeHuman official-GUI CC0 export, anatomical, closer to
  "realistic"). **Recommendation: MakeHuman mannequin as the realism default,
  Quaternius as the friendly option** — photoreal skin is explicitly out (uncanny
  valley + weight + this audience needs clarity).
- **Male/female**: separate CC0 rigs + **parametric skeleton scaling** from
  ANSUR II percentiles (appendix G) — also gives body-height/limb-length presets
  later. The existing neutral/female/male preference carries over.
- **Fingers**: chosen avatars must ship finger bones (verify per asset; MakeHuman
  rigs do; Quaternius varies by pack) — required for SKEL-3.
- **Animal avatars** (farm / jungle / forest cartoon): use **anthropomorphic
  bipedal** CC0 animal characters with humanoid rigs so retargeting is trivial
  **and the demonstrated form stays anatomically human** — a fox doing a push-up
  must still teach a correct human push-up. (True quadrupeds would falsify the
  movement; rejected.) Quaternius CC0 animal packs are the first candidates —
  verify rig + license per pack.
- **Retargeting**: direction/position-based (FK world targets → rig bones via
  rest-direction from-to in the rig's local frame) with a per-avatar bone-name
  map; foot-lock preserved through retarget; validated by the report cards + the
  visual harness.

## 7. Themes — culture, place, and play (with care)

A **theme = data, not code**: one theme pipeline, N theme packs:
`{environment set, lighting mood, material/color tokens, prop skins, soundscape,
optional avatar costume}`.

- **Cultural themes** (China, Japan, France, USA, Africa, Middle East, India):
  the guiding principle is **place, not caricature** — themes change the
  *environment and music*, not the person: a Chinese garden pavilion; a Japanese
  engawa with shoji-screen light; a French country room; a US porch/home-gym; a
  savanna-veranda at golden hour; a Middle-Eastern courtyard with mashrabiya
  shade; an Indian veranda with rangoli accents. The avatar's body stays the
  user's chosen avatar in every theme; costume variants only where respectful,
  optional, and reviewed. A written **cultural-content guideline** goes into
  CONTRIBUTING, and community review is invited (that is open-source's
  advantage). "Africa" and "Middle East" are regions, not countries — name the
  visual inspiration specifically in each pack's provenance notes.
- **Animal/cartoon themes** (farm barn, jungle, forest): pair with the animal
  avatars; brighter palettes, playful sound.
- **Environments are procedural first** (code-built low-poly geometry + three.js
  materials — zero binaries), CC0-asset upgrades later through the asset
  pipeline. Hard rule enforced by the visual harness: **the figure must always
  out-contrast the environment** (silhouette test + contrast ratio) — clarity for
  fragile users beats prettiness, always.

## 8. Sound — per-theme soundscapes, honest and offline

Extend the existing per-theme timbre system (dark/light already ship distinct
Web-Audio palettes) into full theme sound packs, **procedurally synthesized
first** (zero binaries, stays offline):

| Theme | Palette sketch (synthesized, labeled as evocative — not authentic performance) |
|---|---|
| China | pentatonic plucked strings (Karplus-Strong "guzheng-like"), soft chime reps |
| Japan | hirajōshi scale, filtered-noise flute ("shakuhachi-like"), wood-block ticks |
| France | detuned-reed accordion pad, musette lilt on completion |
| USA | acoustic-folk pluck, warm kick-tick metronome |
| Africa | kalimba-like plucks, djembe-pattern rep cues (region named per pack) |
| Middle East | maqam-scale oud-like pluck, frame-drum ticks |
| India | tanpura drone bed, tabla-like rep strokes |
| Farm/Jungle/Forest | marimba, whistles, playful animal-adjacent motifs |

Each pack defines the same six cue roles the engine already has (breath-up,
breath-down, phase, second-tick, rep, finish) plus an optional very-quiet ambient
bed. Sound stays **opt-in**, volume-bounded, never required to use the app
(a11y), and reduced to simple ticks under reduced-motion if desired. CC0 sampled
instruments are a later upgrade via the asset pipeline for themes where synthesis
falls short — each sample license-manifested (mission PR11).

## 9. The binary-asset question (owner decision required)

Avatown meshes, environment upgrades, and sampled sound eventually mean binaries.
Current policy: none committed. Options:

1. **Installer-time fetch (recommended)**: assets live in a companion
   `fenix5sync-assets` repo/release (each file license-manifested, SHA-256
   pinned); `install.sh` downloads once; **runtime stays fully offline**. Repo
   stays lean; PR11's manifest gate enforces license + hash + size budget.
2. Git-LFS in-repo (simple, but bloats clones and LFS quotas).
3. Commit small binaries directly under a strict size budget (simplest; repo
   grows forever).
4. User-supplied assets only (max purity; worst UX).

Until decided, everything above is sequenced so procedural placeholders ship
value without any binary.

## 10. Delivery phases (each shippable, each gated)

| Phase | Contents | Mission PRs consumed | Verification | Est. |
|---|---|---|---|---|
| **A — motion truth** (now, autonomous) | per-phase easing + breath/sway (PR5); SKEL-2 segmented spine (PR6); plausibility validator + report cards (PR7); visual-regression harness (PR8); data plumbing (PR9); license manifest (PR11) | PR5–9, 11 | unit/invariant tests; harness candidates (human approves baselines) | 1–2 wk |
| **B — realism tier** (connected + human eye) | three.js r178 scaffold (PR12) → CC0 M/F avatars via the swap seam; retargeting; asset-pipeline decision (§9); screenshot-driven quality loop | PR12 + deferred avatar track | smoke tests + screenshots judged by vision/human | 1–2 wk |
| **C — hands & contacts** | SKEL-3 wrists/fingers + hand-shape library; contact schema + props (chair/wall/bottles/books/bed/sofa); Tai Chi set uplift (hands + flow pack); hero-set authoring | (extends 6) | shape/contact tests; report cards; instructor review begins | 2–4 wk |
| **D — themes & sound** | theme pipeline + first packs (**China, Japan, Farm** first — Tai Chi affinity + fun), procedural environments + soundscapes; theme/avatar UI; cultural guideline | — | contrast/silhouette gate; per-pack provenance; community review | 2–3 wk |
| **E — scale & community** | remaining theme packs; animal avatars; MoveNet self-mocap tool (PR10); MIF formalization + contributor pipeline; body-type presets (ANSUR) | PR10 | validator + review program | ongoing |

Rough total to "flagship quality": **~2–3 months part-time**, parallelizable
across sessions exactly as we've been doing (autonomous test-verified work here;
connected sessions for assets/vendoring; human eyes for look; instructors for
form).

## 11. Risks & mitigations

- **Uncanny valley** → mannequin/stylized realism, never photoreal skin.
- **Cultural missteps** → place-not-caricature principle, per-pack provenance,
  community review, costumes optional & reviewed.
- **License drift** → PR11 manifest gate is a prerequisite for any binary; the
  reject-list (Mixamo/SMPL/AMASS/RPM/BlazePose-weights-unconfirmed) is absolute.
- **Motion falsification by cute avatars** → anthropomorphic-only animals;
  report cards run on the *retargeted* skeleton too.
- **Scope explosion in themes** → themes are packs; ship 3, evaluate, batch rest.
- **Perf on low-end devices** → four quality tiers already planned (SVG → canvas
  → WebGL-low [no post] → WebGL-high); budgets: canvas 60 fps mid-range phone,
  WebGL-low 30 fps low-end.
- **A11y regression** → reduced-motion parity + keyboard operability are
  permanent release gates; sound always optional.
- **Fragile-user clarity vs prettiness** → contrast/silhouette test in the
  visual harness fails the build, not a review comment.

## 12. Decision points for the owner (blocking inputs)

1. **Binary-asset policy** (§9) — recommended: installer-time fetch + manifest.
2. **Avatar realism style** — MakeHuman mannequin (realistic) vs Quaternius
   (stylized-clean) as the default; both CC0, both can ship.
3. **First theme batch** — proposal: China + Japan + Farm.
4. **Costume variants per cultural theme** — in or out of scope (default: out,
   environments-and-music only, until reviewed).
5. **Instructor review** — recruit a Tai Chi instructor (community call?) to
   graduate entries from "simplified pacer" to "instructor-reviewed".

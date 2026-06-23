# Form-model 3-D — architecture & roadmap

The "full 3-D" rebuild of the movement figure, structured so the hard, durable,
license-clean parts land first and are unit-tested, and the heavy WebGL avatar is
an optional layer on top of the same data.

## Layers (each one only depends on the one below)

```
 exercises.json (existing 2-D views)        web/content/**/*.json
        │  Pose3D.adaptExercise() — IK derives 3-D bone rotations
        ▼
 3-D pose tracks  { poseName: { bone: quaternion } }      ◄── ex.poses3d overrides
        │  Pose3D.forwardKinematics()  (web/js/pose3d.js)   (hand-authored, optional)
        ▼
 world joint positions
        ├── formModel3d.js   canvas software renderer (no deps, no WebGL)  ✅ shipped
        └── formModel3d-gl.js  three.js skinned avatar (WebGL)             ⏳ planned
```

## The motion core — `web/js/pose3d.js` (shipped, unit-tested)

Engine-agnostic and DOM-free (browser global + Node export). Provides:

- a humanoid **skeleton** (bone hierarchy, rest directions, lengths);
- **quaternion** math (`mul`, `conj`, `fromTo`, `slerp`, `rotate`);
- **forward kinematics** — per-bone local quaternions → world joint positions;
- **`slerpPose`** — per-bone interpolation between two keyframe poses;
- the **2-D → 3-D IK adapter** (`adaptPose` / `adaptExercise`): derives bone
  rotations from the existing 2-D joint keyframes. A pose authored in one view is
  *planar* 3-D (motion in that plane); a pose authored in **both** the side and
  front views is **fused** into true depth (X from front, Z from side).

This is why every one of the 56 shipped exercises is 3-D **with no
re-authoring**: the renderer calls `adaptExercise(ex)` unless the exercise
carries an explicit `poses3d` block.

Tests: `tests/js/pose3d.test.js` (run under the `pytest` node gate).

## Canonical 3-D schema (optional per-exercise override)

```jsonc
{
  "id": "bodyweight-squat",
  "views": { "side": { /* existing 2-D keyframes — still the fallback */ } },
  "poses3d": {                 // OPTIONAL: hand-authored bone rotations
    "stand": { "spine": [x,y,z,w], "thighL": [x,y,z,w], ... },
    "sit":   { ... }
  }
}
```

Bones: `spine, head, upperArm{L,R}, forearm{L,R}, thigh{L,R}, shin{L,R},
foot{L,R}`. Quaternions are **local** (relative to the parent bone's rest), unit
length. Phases (`from`/`to`/`dur`/`isHold`) are unchanged — they reference pose
names exactly as the 2-D engine does, so the same tempo clock drives both
renderers.

## Renderers

- **Canvas (shipped):** `formModel3d.js` — FK → orbitable perspective camera →
  depth-sorted capsule limbs on a `<canvas>`. No WebGL, no libraries, works
  everywhere a canvas does. Exposed in the Home tab via a **2-D / 3-D (beta)**
  toggle; the SVG engine remains the default and the reduced-motion fallback.
- **three.js skinned avatar (planned):** a CC0 rigged glTF avatar (e.g.
  Quaternius "Universal Base Characters", CC0) driven by the same pose tracks,
  rendered with lighting/shadows for maximum realism. Gated behind WebGL2 feature
  detection with the canvas renderer as the fallback. See "remaining work".

## Remaining work (the WebGL layer + authoring)

1. **Vendor three.js (MIT) via a native importmap** (no build step) — blocked in
   the implementing sandbox by no package-registry network; needs a connected
   session to fetch `three.module.js` + `GLTFLoader.js`.
2. **Vendor one CC0 avatar `.glb`** and map our bone names → the rig's bones.
3. `formModel3d-gl.js` — load the avatar, apply the pose tracks' local
   quaternions to the skeleton, render. **Needs a human visual pass** (this
   environment cannot see pixels).
4. **Hand-author `poses3d`** for the exercises that benefit most (the adapter's
   planar output is a good baseline; refine the highest-value movements first).
5. A Blender → JSON exporter so contributors can author bone tracks, plus a schema
   validator mirroring the content integrity tests.

## Asset licensing — hard rules (see CONTRIBUTING)

Everything is vendored and shipped offline under GPL-3.0, so any 3-D asset must be
**redistributable + offline + GPL-compatible**. Permitted: CC0 / MIT / Apache-2.0
/ Unlicense / CC-BY. **Rejected — never enter the repo in any form (including
hand-edited):** Mixamo (Adobe ToS forbids redistributing the files), SMPL /
SMPL-X / AMASS (non-commercial research license), Ready Player Me (CC BY-NC-SA).
CMU MoCap (BVH) is usable as an authoring *reference* only; the redistributed
artifact stays JSON authored by us.

## Could-not-verify note

The canvas renderer is verified to run end-to-end without errors (a DOM-mock
harness drives FK + projection + drawing across many exercises and frames), but
its **visual quality has not been seen** — camera framing, limb girths, shading,
and foot placement want a human glance in a browser. The WebGL avatar layer is
entirely pending a connected session + a visual pass.

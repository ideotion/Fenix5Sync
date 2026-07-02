/* pose3d — the engine-agnostic 3-D motion core for the form-model figure.

   This is the foundation of the "full 3-D" rebuild: a humanoid skeleton, a
   quaternion bone-rotation representation, forward kinematics, pose interpolation
   (slerp), and — crucially — an IK adapter that DERIVES 3-D bone rotations from
   the existing 2-D joint keyframes, so every shipped exercise gains a 3-D pose
   with no re-authoring (single-view poses are planar; poses authored in both
   views are fused into true depth).

   No DOM and no rendering: it runs identically in the browser (window.Pose3D)
   and under Node (module.exports), where the math is unit-tested. A renderer
   (canvas skeleton, or a three.js skinned avatar) consumes `forwardKinematics`
   for world joint positions, or the per-bone local quaternions to drive a rig.

   Axes: right-handed, X = screen-right, Y = up, Z = toward the viewer (the figure
   faces +Z). The shared 240x340 art space maps as world = (x-120, 318-y, z). */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Pose3D = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ---------------------------------------------------------------- vec3
  const V = {
    sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
    add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
    scale: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
    dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
    cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
    len: (a) => Math.hypot(a[0], a[1], a[2]),
    norm(a) { const l = V.len(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
  };

  // ------------------------------------------------------------- quaternion
  // Stored [x, y, z, w]; identity = [0,0,0,1].
  const Q = {
    IDENT: [0, 0, 0, 1],
    mul(a, b) {
      const [ax, ay, az, aw] = a, [bx, by, bz, bw] = b;
      return [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
      ];
    },
    conj: (q) => [-q[0], -q[1], -q[2], q[3]],
    norm(q) { const l = Math.hypot(q[0], q[1], q[2], q[3]) || 1; return [q[0] / l, q[1] / l, q[2] / l, q[3] / l]; },
    // Rotate a vector by a quaternion.
    rotate(q, v) {
      const u = [q[0], q[1], q[2]], s = q[3];
      const t = V.scale(V.cross(u, v), 2);
      return V.add(V.add(v, V.scale(t, s)), V.cross(u, t));
    },
    // Shortest-arc rotation taking unit vector a onto unit vector b (no twist).
    fromTo(a, b) {
      a = V.norm(a); b = V.norm(b);
      const d = V.dot(a, b);
      if (d >= 1 - 1e-8) return [0, 0, 0, 1];
      if (d <= -1 + 1e-8) {                 // opposite: rotate 180 about any perpendicular
        let axis = V.cross([1, 0, 0], a);
        if (V.len(axis) < 1e-6) axis = V.cross([0, 1, 0], a);
        axis = V.norm(axis);
        return [axis[0], axis[1], axis[2], 0];
      }
      const c = V.cross(a, b), w = 1 + d;
      return Q.norm([c[0], c[1], c[2], w]);
    },
    slerp(a, b, t) {
      let d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
      let bb = b;
      if (d < 0) { bb = [-b[0], -b[1], -b[2], -b[3]]; d = -d; }
      if (d > 0.9995) {                     // nearly parallel: lerp + normalize
        return Q.norm([
          a[0] + (bb[0] - a[0]) * t, a[1] + (bb[1] - a[1]) * t,
          a[2] + (bb[2] - a[2]) * t, a[3] + (bb[3] - a[3]) * t,
        ]);
      }
      const th0 = Math.acos(d), th = th0 * t;
      const s0 = Math.sin(th0), s1 = Math.sin(th0 - th) / s0, s2 = Math.sin(th) / s0;
      return [a[0] * s1 + bb[0] * s2, a[1] * s1 + bb[1] * s2, a[2] * s1 + bb[2] * s2, a[3] * s1 + bb[3] * s2];
    },
  };

  // ------------------------------------------------------ humanoid skeleton
  // Rest world joint positions (a relaxed standing pose, arms at the sides).
  // SKEL-2: the trunk is a lumbar -> thoracic -> cervical chain (so posture can
  // curve), clavicles root the arms off the cervicothoracic junction, and each
  // foot gains a toe joint (pairs with the 2-D heel for future foot roll). The
  // legacy joint names ("spine" = top of the thoracic segment, "head") survive,
  // so renderers and content keep working.
  const REST = {
    hips: [0, 96, 0], lspine: [0, 126, 0], spine: [0, 150, 0],
    neckBase: [0, 168, 0], head: [0, 196, 0],
    shoulderL: [-20, 168, 0], shoulderR: [20, 168, 0],
    elbowL: [-26, 130, 0], elbowR: [26, 130, 0],
    handL: [-30, 96, 0], handR: [30, 96, 0],
    hipL: [-12, 96, 0], hipR: [12, 96, 0],
    kneeL: [-13, 50, 0], kneeR: [13, 50, 0],
    ankleL: [-14, 6, 0], ankleR: [14, 6, 0],
    footL: [-14, 0, 14], footR: [14, 0, 14],
    toeL: [-14, 0, 21], toeR: [14, 0, 21],
  };
  // Bone hierarchy: each bone orients the segment parentJoint -> joint.
  // `pair` is the [from, to] 2-D joint names the IK adapter reads (side names;
  // front uses the l/r-prefixed variants); pair-less bones (clavicles, toes)
  // rest at identity until authored. The three trunk bones share one pair: the
  // adapter derives one trunk rotation and distributes it (rigid by default,
  // curved on request — see adaptPose). Order = parents before children.
  const BONES = [
    { name: "lumbar", parent: null, from: "hips", to: "lspine", pair: ["hip", "sh"] },
    { name: "thoracic", parent: "lumbar", from: "lspine", to: "spine", pair: ["hip", "sh"] },
    { name: "cervical", parent: "thoracic", from: "spine", to: "neckBase", pair: ["hip", "sh"] },
    { name: "clavicleL", parent: "cervical", from: "neckBase", to: "shoulderL" },
    { name: "clavicleR", parent: "cervical", from: "neckBase", to: "shoulderR" },
    { name: "head", parent: "cervical", from: "neckBase", to: "head", pair: ["sh", "head"] },
    { name: "thighL", parent: null, from: "hipL", to: "kneeL", pair: ["hip", "knee"], side: "L" },
    { name: "shinL", parent: "thighL", from: "kneeL", to: "ankleL", pair: ["knee", "ankle"], side: "L" },
    { name: "footL", parent: "shinL", from: "ankleL", to: "footL", pair: ["ankle", "toe"], side: "L" },
    { name: "toeL", parent: "footL", from: "footL", to: "toeL", side: "L" },
    { name: "thighR", parent: null, from: "hipR", to: "kneeR", pair: ["hip", "knee"], side: "R" },
    { name: "shinR", parent: "thighR", from: "kneeR", to: "ankleR", pair: ["knee", "ankle"], side: "R" },
    { name: "footR", parent: "shinR", from: "ankleR", to: "footR", pair: ["ankle", "toe"], side: "R" },
    { name: "toeR", parent: "footR", from: "footR", to: "toeR", side: "R" },
    { name: "upperArmL", parent: "clavicleL", from: "shoulderL", to: "elbowL", pair: ["sh", "elb"], side: "L" },
    { name: "forearmL", parent: "upperArmL", from: "elbowL", to: "handL", pair: ["elb", "hand"], side: "L" },
    { name: "upperArmR", parent: "clavicleR", from: "shoulderR", to: "elbowR", pair: ["sh", "elb"], side: "R" },
    { name: "forearmR", parent: "upperArmR", from: "elbowR", to: "handR", pair: ["elb", "hand"], side: "R" },
  ];
  const BONE_BY_NAME = Object.fromEntries(BONES.map((b) => [b.name, b]));
  // Rest world direction + length of each bone.
  const REST_DIR = {}, BONE_LEN = {};
  for (const b of BONES) {
    const d = V.sub(REST[b.to], REST[b.from]);
    BONE_LEN[b.name] = V.len(d);
    REST_DIR[b.name] = V.norm(d);
  }
  // Trunk-rotation share per segment as a function of the curve amount c in
  // [0, 1]. c = 0 -> all three segments carry the full rotation (a straight,
  // rigid trunk — exactly the legacy single-spine behaviour, and the SAFE
  // default: blind curvature would demonstrate rounded-back hinges to the
  // fragile users this app serves). c = 1 -> the lumbar lags most, the chest
  // (cervical) always reaches the full rotation, so arm/head placement is
  // orientation-stable while the spine visibly curves.
  const TRUNK_SHARE = {
    lumbar: (c) => 1 - 0.55 * c,
    thoracic: (c) => 1 - 0.25 * c,
    cervical: () => 1,
  };

  const GROUND_Y = 0; // world height of the floor (rest feet sit here)

  // ---- joint limits --------------------------------------------------------
  // Per-bone maximum SWING (degrees) of the local rotation from its rest
  // direction, used as a hard clamp. Ceilings are the AAOS clinical max/normal
  // values (Greene & Heckman, "The Clinical Measurement of Joint Motion", AAOS
  // 1994; cross-checked vs the public-domain VA/DSHS goniometry charts), set at
  // the high end of the cited ranges so valid deep squats/holds are untouched —
  // the clamp only catches clearly-impossible frames (e.g. a 177-degree elbow).
  // Knee/elbow are hinges: this caps the fold; the bend DIRECTION (no
  // hyperextension) is fixed by the IK pole, not here. Hip/shoulder are cones.
  // The LUMBAR (trunk root) stays wide because it carries the whole-body
  // rotation for floor/prone poses (push-ups, planks) under the rigid default;
  // thoracic/cervical LOCAL rotations are only curvature deltas, so they take
  // segment-scale limits (Apti 2023 measured spine norms). The tighter
  // FUNCTIONAL ranges feed animation defaults + the plausibility test
  // (PR5/PR7), not these hard clamps.
  const _RAD = Math.PI / 180;
  const JOINT_LIMITS = {
    lumbar: 140,                      // trunk root: whole-body rotation for floor poses
    thoracic: 45, cervical: 45,       // local curvature deltas (segmented spine)
    head: 70,                         // neck on top of the cervical segment
    clavicleL: 30, clavicleR: 30,     // shoulder-girdle shrug/protraction (authored later)
    upperArmL: 180, upperArmR: 180,   // shoulder flexion/abduction 0-180 (AAOS)
    forearmL: 150, forearmR: 150,     // elbow flexion 0-150 (AAOS)
    thighL: 130, thighR: 130,         // hip flexion 0-120 (to ~140 knee-bent)
    shinL: 150, shinR: 150,           // knee flexion 0-135..150 (AAOS range)
    footL: 140, footR: 140,           // wide: floor/prone whole-body rotation
    toeL: 60, toeR: 60,               // toe break (foot roll, authored later)
  };

  // Rotation angle of a unit quaternion (radians), double-cover safe.
  function swingAngle(q) {
    return 2 * Math.atan2(Math.hypot(q[0], q[1], q[2]), Math.abs(q[3]));
  }
  // Clamp a bone's local rotation to its cone limit, preserving the swing axis.
  function clampJoint(name, q) {
    const lim = (JOINT_LIMITS[name] != null ? JOINT_LIMITS[name] : 180) * _RAD;
    const a = swingAngle(q);
    if (a <= lim || a < 1e-6) return q;
    return Q.slerp(Q.IDENT, q, lim / a);
  }

  // Quaternion of a rotation by `angle` (radians) about a unit-ised `axis`.
  function axisAngleQuat(axis, angle) {
    const u = V.norm(axis), s = Math.sin(angle / 2);
    return [u[0] * s, u[1] * s, u[2] * s, Math.cos(angle / 2)];
  }

  // ---- timing: per-phase easing --------------------------------------------
  // A phase may carry `ease: "inout" | "linear" | "in" | "out"` in the content
  // JSON. "inout" is the historical default (cubic), so absent/unknown names
  // change nothing. "linear" is the near-constant-speed profile flowing motion
  // (Tai Chi) wants; "in"/"out" let an eccentric lower read slower than the
  // concentric rise within one phase.
  const EASINGS = {
    inout: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    linear: (t) => t,
    in: (t) => t * t * t,
    out: (t) => 1 - Math.pow(1 - t, 3),
  };
  function easingFor(name) { return EASINGS[name] || EASINGS.inout; }

  // ---- procedural life: breath + postural sway ------------------------------
  // Small, bounded, DETERMINISTIC oscillations so holds are not frozen. Values
  // anchor to the biomechanics appendix (Sect. D): resting breath 12-20/min
  // (default 15, inhale slightly faster than the exhale); quiet-standing sway is
  // quasi-random with power below ~1 Hz and a-few-mm amplitude — modeled as two
  // incommensurate sine octaves per axis (AP larger than ML). 1 world unit is
  // ~9 mm at our 192-unit stature, so the defaults sit in the cited mm range.
  // Everything clamps to LIFE_MAX regardless of overrides; scale 0 = no-op.
  const LIFE_DEFAULTS = {
    breathRate: 15,      // breaths/min
    breathAmpDeg: 1.6,   // spine pitch amplitude (degrees)
    inhaleFrac: 0.45,    // fraction of the cycle spent inhaling (< 0.5 = faster in)
    swayAP: 0.7,         // front-back amplitude, world units (~6 mm)
    swayML: 0.4,         // side-side amplitude, world units (~3.5 mm)
  };
  const LIFE_MAX = { breathAmpDeg: 3.0, sway: 2.0 };
  const _clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0));

  // Breath waveform in [-1, 1]: rises over the inhale fraction, falls over the
  // exhale (piecewise cosine, C1 at the joins), so inhale reads faster.
  function breathWave(tMs, rate, inhaleFrac) {
    const period = 60000 / (rate || LIFE_DEFAULTS.breathRate);
    const p = (((tMs % period) + period) % period) / period;
    const fi = inhaleFrac || LIFE_DEFAULTS.inhaleFrac;
    return p < fi ? -Math.cos(Math.PI * p / fi) : Math.cos(Math.PI * (p - fi) / (1 - fi));
  }

  // Overlay life onto a pose (pure: returns a new pose, input untouched).
  // opts: { breath: 0..1, sway: 0..1, breathAmpDeg?, swayAP?, swayML? }.
  function applyLife(pose, tMs, opts = {}) {
    const breath = _clamp01(opts.breath);
    const sway = _clamp01(opts.sway);
    if (!breath && !sway) return pose;
    const out = Object.assign({}, pose);
    if (breath) {
      const amp = Math.min(opts.breathAmpDeg != null ? opts.breathAmpDeg : LIFE_DEFAULTS.breathAmpDeg,
        LIFE_MAX.breathAmpDeg) * breath * _RAD;
      const w = breathWave(tMs, opts.breathRate, opts.inhaleFrac);
      out.thoracic = Q.mul(pose.thoracic || Q.IDENT, axisAngleQuat([1, 0, 0], amp * w));
    }
    if (sway) {
      const t = tMs / 1000;
      const ampAP = Math.min(opts.swayAP != null ? opts.swayAP : LIFE_DEFAULTS.swayAP, LIFE_MAX.sway) * sway;
      const ampML = Math.min(opts.swayML != null ? opts.swayML : LIFE_DEFAULTS.swayML, LIFE_MAX.sway) * sway;
      // weights sum to 1, so each axis never exceeds its amplitude.
      const ap = ampAP * (0.72 * Math.sin(2 * Math.PI * 0.30 * t) + 0.28 * Math.sin(2 * Math.PI * 0.85 * t + 1.7));
      const ml = ampML * (0.75 * Math.sin(2 * Math.PI * 0.23 * t + 0.9) + 0.25 * Math.sin(2 * Math.PI * 0.70 * t + 2.6));
      const base = pose.__root || REST.hips;
      out.__root = [base[0] + ml, base[1], base[2] + ap];
    }
    return out;
  }

  // ------------------------------------------------------ forward kinematics
  // Given per-bone LOCAL quaternions, return world positions for every joint.
  function forwardKinematics(localQ, opts = {}) {
    // Pelvis position: explicit opts.root, else the pose's own __root travel, else rest.
    const root = opts.root || localQ.__root || REST.hips;
    const worldQ = {}, jointPos = { hips: root.slice() };
    const lq = (n) => localQ[n] || Q.IDENT;

    const twist = localQ.__twist;
    for (const b of BONES) {
      const parentWorld = b.parent ? (worldQ[b.parent] || Q.IDENT) : Q.IDENT;
      // Compose the swing with an optional axial twist (roll about the bone's rest
      // axis). Twist about the bone's own axis leaves THIS bone's direction
      // unchanged but rolls the frame its children inherit (pronation, femoral
      // rotation, spinal/head turn). Default (no __twist) is bit-for-bit unchanged.
      let local = lq(b.name);
      if (twist && twist[b.name]) local = Q.mul(local, axisAngleQuat(REST_DIR[b.name], twist[b.name]));
      worldQ[b.name] = Q.mul(parentWorld, local);
      // Where the bone starts: the trunk roots at the pelvis, the thighs at the
      // (rigid) hip sockets, everything else at its parent-chain joint — the
      // clavicles hang off neckBase, so the shoulders are real chain joints now.
      let start;
      if (b.name === "lumbar") start = jointPos.hips;
      else if (b.name === "thighL") start = V.add(jointPos.hips, V.sub(REST.hipL, REST.hips));
      else if (b.name === "thighR") start = V.add(jointPos.hips, V.sub(REST.hipR, REST.hips));
      else start = jointPos[b.from];
      jointPos[b.from] = jointPos[b.from] || start;
      const dir = Q.rotate(worldQ[b.name], REST_DIR[b.name]);
      jointPos[b.to] = V.add(start, V.scale(dir, BONE_LEN[b.name]));
    }
    // Fill fixed joints for renderers.
    jointPos.hipL = V.add(jointPos.hips, V.sub(REST.hipL, REST.hips));
    jointPos.hipR = V.add(jointPos.hips, V.sub(REST.hipR, REST.hips));

    // Foot grounding (opt-in): translate the whole skeleton so the lowest foot
    // contact (heel-side foot joints or the toes) rests on the world ground
    // plane. With the pelvis pinned high (PR1) and the legs bent, this is what
    // pulls the body down into a squat and stops the feet floating — without
    // touching any authored bone angle.
    if (opts.ground) {
      const feet = [jointPos.footL, jointPos.footR, jointPos.toeL, jointPos.toeR].filter(Boolean);
      if (feet.length) {
        const shift = GROUND_Y - Math.min(...feet.map((f) => f[1]));
        if (Math.abs(shift) > 1e-9) {
          for (const k in jointPos) jointPos[k] = [jointPos[k][0], jointPos[k][1] + shift, jointPos[k][2]];
        }
      }
    }
    return jointPos;
  }

  // Two-bone analytic IK (law of cosines): orient a hip->knee->ankle chain so the
  // ankle reaches `target`, bending toward `pole`. Reach is clamped so an
  // out-of-range target straightens (or folds) the leg instead of breaking it.
  // The building block for grounding both feet in asymmetric double-support poses
  // (applied once authored poses need it; global grounding covers symmetric ones).
  function solveTwoBoneIK(hip, target, l1, l2, pole) {
    const u0 = V.sub(target, hip);
    let d = V.len(u0);
    const u = d > 1e-9 ? V.scale(u0, 1 / d) : [0, -1, 0];
    d = Math.max(Math.abs(l1 - l2) + 1e-3, Math.min(l1 + l2 - 1e-3, d)); // clamp to reachable
    const cosA = Math.max(-1, Math.min(1, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)));
    const sinA = Math.sqrt(Math.max(0, 1 - cosA * cosA));
    let n = V.sub(pole || [0, 0, 1], V.scale(u, V.dot(pole || [0, 0, 1], u)));
    if (V.len(n) < 1e-6) { n = V.sub([0, 0, 1], V.scale(u, V.dot([0, 0, 1], u))); }
    if (V.len(n) < 1e-6) n = [1, 0, 0];
    n = V.norm(n);
    const knee = V.add(hip, V.add(V.scale(u, l1 * cosA), V.scale(n, l1 * sinA)));
    const ankle = V.add(hip, V.scale(u, d));
    return { knee, ankle };
  }

  // ------------------------------------------------------------ 2-D -> 3-D
  // Map an art-space 2-D point [x, y] to a world direction component.
  // Front view: dx -> world X, -dy -> world Y. Side view (faces +Z): dx -> world
  // Z, -dy -> world Y. We work in DIRECTIONS (differences) so the origin cancels.
  function _dirFromView(view, from, to, axisIsSide) {
    if (!from || !to) return null;
    const dx = to[0] - from[0], dy = -(to[1] - from[1]);
    return axisIsSide ? [0, dy, dx] : [dx, dy, 0];
  }

  // Target world direction for a bone, fusing whatever views exist. Pair-less
  // bones (clavicles, toes) have no 2-D drive and rest at identity.
  function _targetDir(bone, sidePose, frontPose) {
    if (!bone.pair) return null;
    const [f, t] = bone.pair;
    const sideKey = (j) => j; // side pose uses unprefixed joints
    const frontKey = (j) => {
      if (bone.side && (j === "knee" || j === "ankle" || j === "elb" || j === "hand")) {
        return bone.side.toLowerCase() + j;
      }
      if (bone.side && j === "sh") return "sh";   // shoulder shared in front pose model
      return j;
    };
    const sideDir = sidePose ? _dirFromView("side", sidePose[sideKey(f)], sidePose[sideKey(t)], true) : null;
    let frontFrom = frontPose ? frontPose[frontKey(f)] : null;
    let frontTo = frontPose ? frontPose[frontKey(t)] : null;
    // Arms in the front model hang off the single shoulder point.
    const frontDir = frontPose ? _dirFromView("front", frontFrom, frontTo, false) : null;

    if (sideDir && frontDir) {                  // fuse: X from front, Z from side, Y avg
      return V.norm([frontDir[0], (frontDir[1] + sideDir[1]) / 2, sideDir[2]]);
    }
    return sideDir ? V.norm(sideDir) : (frontDir ? V.norm(frontDir) : null);
  }

  // ---- root (pelvis) travel ------------------------------------------------
  // The bone-direction adapter discards the body's absolute rise/fall and sway
  // (a squat lowers, a weight-shift translates). We recover it from the 2-D hip
  // joint: its displacement from the exercise's reference pose, scaled from art
  // units into skeleton units, becomes a per-pose pelvis offset from REST.hips.
  const ART_LEG = 134; // canonical standing hip->ankle vertical span in the 240x340 art space
  const ART_TO_WORLD = (REST.hips[1] - REST.ankleL[1]) / ART_LEG; // ~0.67

  // Map the 2-D hip to world axes for DISPLACEMENT (origin cancels): front x->X,
  // side x->Z, art-y->-Y. A missing view contributes 0 on its axis.
  function _hipVec(sidePose, frontPose) {
    const fh = frontPose && frontPose.hip, sh = sidePose && sidePose.hip;
    const ys = [];
    if (fh) ys.push(-fh[1]);
    if (sh) ys.push(-sh[1]);
    return [fh ? fh[0] : 0, ys.length ? ys.reduce((s, v) => s + v, 0) / ys.length : 0, sh ? sh[0] : 0];
  }

  // Convert one keyframe pose (the views' joint maps for a pose name) to per-bone
  // LOCAL quaternions, solved top-down so FK reproduces the target directions.
  // opts.curve in [0, 1] bends the trunk (see TRUNK_SHARE): 0 = rigid legacy
  // trunk (the safe default), 1 = full curvature with the chest orientation
  // preserved, so arm and head placement stays orientation-stable.
  function adaptPose(views, poseName, opts = {}) {
    const sidePose = views.side && views.side[poseName];
    const frontPose = views.front && views.front[poseName];
    const curve = _clamp01(opts.curve);
    const worldQ = {}, localQ = {};
    for (const b of BONES) {
      const parentWorld = b.parent ? (worldQ[b.parent] || Q.IDENT) : Q.IDENT;
      let local;
      if (!b.pair) {
        // Structural bones (clavicles, toes) have no 2-D drive: LOCAL identity,
        // i.e. they follow their parent (shoulders ride the chest, toes the foot).
        local = Q.IDENT;
      } else {
        const target = _targetDir(b, sidePose, frontPose);
        let wq = target ? Q.fromTo(REST_DIR[b.name], target) : Q.IDENT;
        // Trunk segments carry a share of the one trunk rotation.
        if (target && TRUNK_SHARE[b.name]) wq = Q.slerp(Q.IDENT, wq, TRUNK_SHARE[b.name](curve));
        // Clamp the joint to its limit, then carry the clamped world to children.
        local = clampJoint(b.name, Q.norm(Q.mul(Q.conj(parentWorld), wq)));
      }
      localQ[b.name] = local;
      worldQ[b.name] = Q.mul(parentWorld, local);
    }
    return localQ;
  }

  // Convert a whole exercise's views into 3-D bone-rotation pose tracks:
  //   { poseName: { boneName: [x,y,z,w], ... }, ... }
  // An exercise may opt into spinal curvature via `spineCurve` (0..1) — an
  // authoring decision per movement (e.g. a gentle crouch curves; a hinge must
  // stay neutral-spine), never a blind default.
  function adaptExercise(exercise) {
    const views = exercise.views || {};
    const curve = _clamp01(exercise.spineCurve);
    const poseNames = new Set();
    for (const v of Object.values(views)) for (const k of Object.keys(v)) poseNames.add(k);
    const poses = {};
    for (const name of poseNames) poses[name] = adaptPose(views, name, { curve });

    // Attach pelvis travel: each pose's hip displacement from the reference pose
    // (the rest pose if present, else the first), scaled into skeleton units.
    const names = [...poseNames];
    const refName = poseNames.has("stand") ? "stand" : names[0];
    if (refName) {
      const refVec = _hipVec(views.side && views.side[refName], views.front && views.front[refName]);
      for (const name of names) {
        const v = _hipVec(views.side && views.side[name], views.front && views.front[name]);
        poses[name].__root = [
          REST.hips[0] + (v[0] - refVec[0]) * ART_TO_WORLD,
          REST.hips[1] + (v[1] - refVec[1]) * ART_TO_WORLD,
          REST.hips[2] + (v[2] - refVec[2]) * ART_TO_WORLD,
        ];
      }
    }
    return poses;
  }

  // Interpolate two bone-rotation poses (per-bone slerp + linear pelvis travel).
  function slerpPose(a, b, t) {
    const out = {};
    const names = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const n of names) {
      if (n === "__root") continue;
      out[n] = clampJoint(n, Q.slerp(a[n] || Q.IDENT, b[n] || Q.IDENT, t));
    }
    if (a.__root || b.__root) {
      const ra = a.__root || REST.hips, rb = b.__root || REST.hips;
      out.__root = [ra[0] + (rb[0] - ra[0]) * t, ra[1] + (rb[1] - ra[1]) * t, ra[2] + (rb[2] - ra[2]) * t];
    }
    if (a.__twist || b.__twist) {
      const ta = a.__twist || {}, tb = b.__twist || {}, tw = {};
      for (const n of new Set([...Object.keys(ta), ...Object.keys(tb)])) {
        tw[n] = (ta[n] || 0) + ((tb[n] || 0) - (ta[n] || 0)) * t;
      }
      out.__twist = tw;
    }
    return out;
  }

  return {
    V, Q, REST, BONES, BONE_BY_NAME, REST_DIR, BONE_LEN, GROUND_Y, JOINT_LIMITS,
    forwardKinematics, adaptPose, adaptExercise, slerpPose, solveTwoBoneIK,
    swingAngle, clampJoint, axisAngleQuat,
    EASINGS, easingFor, LIFE_DEFAULTS, LIFE_MAX, breathWave, applyLife,
  };
});

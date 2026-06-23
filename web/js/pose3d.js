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
  const REST = {
    hips: [0, 96, 0], spine: [0, 150, 0], head: [0, 196, 0],
    shoulderL: [-20, 168, 0], shoulderR: [20, 168, 0],
    elbowL: [-26, 130, 0], elbowR: [26, 130, 0],
    handL: [-30, 96, 0], handR: [30, 96, 0],
    hipL: [-12, 96, 0], hipR: [12, 96, 0],
    kneeL: [-13, 50, 0], kneeR: [13, 50, 0],
    ankleL: [-14, 6, 0], ankleR: [14, 6, 0],
    footL: [-14, 0, 14], footR: [14, 0, 14],
  };
  // Bone hierarchy: each bone orients the segment parentJoint -> joint.
  // `pair` is the [from, to] 2-D joint names the IK adapter reads (side names;
  // front uses the l/r-prefixed variants). `mirror` flags arms/legs so a
  // side-only (profile) pose drives both limbs.
  const BONES = [
    { name: "spine", parent: null, from: "hips", to: "spine", pair: ["hip", "sh"] },
    { name: "head", parent: "spine", from: "spine", to: "head", pair: ["sh", "head"] },
    { name: "thighL", parent: null, from: "hipL", to: "kneeL", pair: ["hip", "knee"], side: "L" },
    { name: "shinL", parent: "thighL", from: "kneeL", to: "ankleL", pair: ["knee", "ankle"], side: "L" },
    { name: "footL", parent: "shinL", from: "ankleL", to: "footL", pair: ["ankle", "toe"], side: "L" },
    { name: "thighR", parent: null, from: "hipR", to: "kneeR", pair: ["hip", "knee"], side: "R" },
    { name: "shinR", parent: "thighR", from: "kneeR", to: "ankleR", pair: ["knee", "ankle"], side: "R" },
    { name: "footR", parent: "shinR", from: "ankleR", to: "footR", pair: ["ankle", "toe"], side: "R" },
    { name: "upperArmL", parent: "spine", from: "shoulderL", to: "elbowL", pair: ["sh", "elb"], side: "L" },
    { name: "forearmL", parent: "upperArmL", from: "elbowL", to: "handL", pair: ["elb", "hand"], side: "L" },
    { name: "upperArmR", parent: "spine", from: "shoulderR", to: "elbowR", pair: ["sh", "elb"], side: "R" },
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
  // Shoulder sockets hang off the (rotating) spine; arms inherit spine motion.
  const SHOULDER_OFFSET = {
    upperArmL: V.sub(REST.shoulderL, REST.spine), upperArmR: V.sub(REST.shoulderR, REST.spine),
  };

  // ------------------------------------------------------ forward kinematics
  // Given per-bone LOCAL quaternions, return world positions for every joint.
  function forwardKinematics(localQ, opts = {}) {
    const root = opts.root || REST.hips;
    const worldQ = {}, jointPos = { hips: root.slice() };
    const lq = (n) => localQ[n] || Q.IDENT;

    for (const b of BONES) {
      const parentWorld = b.parent ? (worldQ[b.parent] || Q.IDENT) : Q.IDENT;
      worldQ[b.name] = Q.mul(parentWorld, lq(b.name));
      // Determine where the bone starts.
      let start;
      if (b.name === "spine") start = jointPos.hips;
      else if (b.name === "thighL") start = V.add(jointPos.hips, V.sub(REST.hipL, REST.hips));
      else if (b.name === "thighR") start = V.add(jointPos.hips, V.sub(REST.hipR, REST.hips));
      else if (b.name === "upperArmL") start = V.add(jointPos.spine, Q.rotate(worldQ.spine, SHOULDER_OFFSET.upperArmL));
      else if (b.name === "upperArmR") start = V.add(jointPos.spine, Q.rotate(worldQ.spine, SHOULDER_OFFSET.upperArmR));
      else start = jointPos[b.from];
      jointPos[b.from] = jointPos[b.from] || start;
      const dir = Q.rotate(worldQ[b.name], REST_DIR[b.name]);
      jointPos[b.to] = V.add(start, V.scale(dir, BONE_LEN[b.name]));
    }
    // Fill fixed joints for renderers.
    jointPos.hipL = V.add(jointPos.hips, V.sub(REST.hipL, REST.hips));
    jointPos.hipR = V.add(jointPos.hips, V.sub(REST.hipR, REST.hips));
    jointPos.shoulderL = jointPos.shoulderL || V.add(jointPos.spine, SHOULDER_OFFSET.upperArmL);
    jointPos.shoulderR = jointPos.shoulderR || V.add(jointPos.spine, SHOULDER_OFFSET.upperArmR);
    return jointPos;
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

  // Target world direction for a bone, fusing whatever views exist.
  function _targetDir(bone, sidePose, frontPose) {
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

  // Convert one keyframe pose (the views' joint maps for a pose name) to per-bone
  // LOCAL quaternions, solved top-down so FK reproduces the target directions.
  function adaptPose(views, poseName) {
    const sidePose = views.side && views.side[poseName];
    const frontPose = views.front && views.front[poseName];
    const worldQ = {}, localQ = {};
    for (const b of BONES) {
      const target = _targetDir(b, sidePose, frontPose);
      const wq = target ? Q.fromTo(REST_DIR[b.name], target) : Q.IDENT;
      worldQ[b.name] = wq;
      const parentWorld = b.parent ? (worldQ[b.parent] || Q.IDENT) : Q.IDENT;
      localQ[b.name] = Q.norm(Q.mul(Q.conj(parentWorld), wq));
    }
    return localQ;
  }

  // Convert a whole exercise's views into 3-D bone-rotation pose tracks:
  //   { poseName: { boneName: [x,y,z,w], ... }, ... }
  function adaptExercise(exercise) {
    const views = exercise.views || {};
    const poseNames = new Set();
    for (const v of Object.values(views)) for (const k of Object.keys(v)) poseNames.add(k);
    const poses = {};
    for (const name of poseNames) poses[name] = adaptPose(views, name);
    return poses;
  }

  // Interpolate two bone-rotation poses (per-bone slerp).
  function slerpPose(a, b, t) {
    const out = {};
    const names = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const n of names) out[n] = Q.slerp(a[n] || Q.IDENT, b[n] || Q.IDENT, t);
    return out;
  }

  return {
    V, Q, REST, BONES, BONE_BY_NAME, REST_DIR, BONE_LEN,
    forwardKinematics, adaptPose, adaptExercise, slerpPose,
  };
});

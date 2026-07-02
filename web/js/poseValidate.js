/* poseValidate — biomechanical-plausibility checks for the 3-D motion core.

   Turns "realistic" into testable invariants: joint rotations inside human
   ranges (the motion core's AAOS-cited limits), unit quaternions, ground
   contacts that never pierce the floor, and the whole-body center of mass over
   the base of support for standing work. Pure and DOM-free: browser global
   (window.PoseValidate) + Node export, unit-tested in the pytest node gate and
   reusable by the visual-regression harness and future report cards.

   Segment masses / COM locations are the Dempster cadaver parameters as
   tabulated by Winter (Biomechanics and Motor Control of Human Movement, 4th
   ed., Table 4.1; original: Dempster, WADC-TR-55-159, 1955, US-gov public
   domain). Whole-body COM for a standing adult lands near 55% of stature — used
   here as a sanity anchor, not a clinical claim. */
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory(require("./pose3d.js"));
  } else {
    root.PoseValidate = factory(root.Pose3D);
  }
})(typeof self !== "undefined" ? self : this, function (P) {
  "use strict";

  // ---- Dempster/Winter body-segment parameters ------------------------------
  // mass: fraction of total body mass. com: fraction of the segment length from
  // the PROXIMAL joint. Forearm+hand is Winter's combined row (0.022 @ 0.682
  // from the elbow) because the rig has no wrist yet. Masses sum to 1.000.
  const SEGMENTS = [
    { name: "trunk", from: "hips", to: "neckBase", mass: 0.497, com: 0.50 },
    { name: "headNeck", from: "head", to: "head", mass: 0.081, com: 0 },   // point mass at the head joint
    { name: "thighL", from: "hipL", to: "kneeL", mass: 0.100, com: 0.433 },
    { name: "thighR", from: "hipR", to: "kneeR", mass: 0.100, com: 0.433 },
    { name: "shankL", from: "kneeL", to: "ankleL", mass: 0.0465, com: 0.433 },
    { name: "shankR", from: "kneeR", to: "ankleR", mass: 0.0465, com: 0.433 },
    { name: "footL", from: "ankleL", to: "toeL", mass: 0.0145, com: 0.50 },
    { name: "footR", from: "ankleR", to: "toeR", mass: 0.0145, com: 0.50 },
    { name: "upperArmL", from: "shoulderL", to: "elbowL", mass: 0.028, com: 0.436 },
    { name: "upperArmR", from: "shoulderR", to: "elbowR", mass: 0.028, com: 0.436 },
    { name: "forearmHandL", from: "elbowL", to: "handL", mass: 0.022, com: 0.682 },
    { name: "forearmHandR", from: "elbowR", to: "handR", mass: 0.022, com: 0.682 },
  ];

  // Whole-body center of mass from world joint positions (weighted segment sum).
  function centerOfMass(jp) {
    let m = 0;
    const c = [0, 0, 0];
    for (const s of SEGMENTS) {
      const a = jp[s.from], b = jp[s.to];
      if (!a || !b) continue;
      const p = [a[0] + (b[0] - a[0]) * s.com, a[1] + (b[1] - a[1]) * s.com, a[2] + (b[2] - a[2]) * s.com];
      c[0] += p[0] * s.mass; c[1] += p[1] * s.mass; c[2] += p[2] * s.mass;
      m += s.mass;
    }
    return m > 0 ? [c[0] / m, c[1] / m, c[2] / m] : [0, 0, 0];
  }

  // ---- ground contacts & base of support ------------------------------------
  // Candidate contact joints: feet and toes always; hands/knees/hips join the
  // support set in floor work (push-ups, planks, bridges) when they are at
  // ground level. `contactTol` is how close (world units) counts as touching.
  const CONTACT_JOINTS = ["footL", "footR", "toeL", "toeR", "ankleL", "ankleR",
    "handL", "handR", "kneeL", "kneeR", "hips"];
  const DEFAULTS = {
    contactTol: 3.0,     // a joint within this height of the floor is a contact
    pierceTol: 3.5,      // nothing may sit further below the floor than this
    contactRadius: 6.0,  // effective half-width of a real contact (foot/hand)
    comMargin: 10.0,     // extra allowance beyond the support hull (units)
  };

  function contactPoints(jp, opts = {}) {
    const tol = opts.contactTol != null ? opts.contactTol : DEFAULTS.contactTol;
    const out = [];
    for (const j of CONTACT_JOINTS) {
      const p = jp[j];
      if (p && p[1] <= P.GROUND_Y + tol) out.push({ joint: j, x: p[0], z: p[2], y: p[1] });
    }
    return out;
  }

  // Convex hull (x,z) via Andrew's monotone chain; returns the hull vertices.
  function convexHull(pts) {
    const P2 = pts.map((p) => [p.x, p.z]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (P2.length <= 2) return P2;
    const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lower = [], upper = [];
    for (const p of P2) {
      while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
      lower.push(p);
    }
    for (const p of P2.slice().reverse()) {
      while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
      upper.push(p);
    }
    return lower.slice(0, -1).concat(upper.slice(0, -1));
  }

  function _distToSegment(px, pz, a, b) {
    const dx = b[0] - a[0], dz = b[1] - a[1];
    const L2 = dx * dx + dz * dz;
    const t = L2 > 0 ? Math.max(0, Math.min(1, ((px - a[0]) * dx + (pz - a[1]) * dz) / L2)) : 0;
    return Math.hypot(px - (a[0] + t * dx), pz - (a[1] + t * dz));
  }

  // Horizontal distance from (x,z) to the support region: 0 inside the hull,
  // else the distance to its boundary (works for 1- and 2-point "hulls" too).
  function distToSupport(x, z, contacts) {
    if (!contacts.length) return Infinity;
    const hull = convexHull(contacts);
    if (hull.length === 1) return Math.hypot(x - hull[0][0], z - hull[0][1]);
    if (hull.length === 2) return _distToSegment(x, z, hull[0], hull[1]);
    // Inside test (hull is counter-clockwise from monotone chain construction).
    let inside = true;
    for (let i = 0; i < hull.length; i++) {
      const a = hull[i], b = hull[(i + 1) % hull.length];
      if ((b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (x - a[0]) < 0) { inside = false; break; }
    }
    if (inside) return 0;
    let d = Infinity;
    for (let i = 0; i < hull.length; i++) d = Math.min(d, _distToSegment(x, z, hull[i], hull[(i + 1) % hull.length]));
    return d;
  }

  // ---- the validator ---------------------------------------------------------
  // validatePose(pose, opts) -> { ok, issues: [{kind, detail}] }
  //   - "quat":    a bone rotation is not a unit quaternion
  //   - "limit":   a bone exceeds its joint-limit cone
  //   - "pierce":  a contact joint sits below the floor beyond tolerance
  //   - "balance": the COM falls outside the (inflated) base of support
  // opts.supported: the figure holds an external support (chair/wall/counter) —
  // the balance check is skipped with a note, because a braced human really can
  // hold their COM beyond their feet.
  function validatePose(pose, opts = {}) {
    const o = Object.assign({}, DEFAULTS, opts);
    const issues = [];

    for (const b of P.BONES) {
      const q = pose[b.name];
      if (!q) continue;
      const n = Math.hypot(q[0], q[1], q[2], q[3]);
      if (Math.abs(n - 1) > 1e-4) issues.push({ kind: "quat", detail: `${b.name} |q|=${n.toFixed(4)}` });
      const lim = (P.JOINT_LIMITS[b.name] != null ? P.JOINT_LIMITS[b.name] : 180) * Math.PI / 180;
      const a = P.swingAngle(q);
      if (a > lim + 1e-4) {
        issues.push({ kind: "limit", detail: `${b.name} ${(a * 180 / Math.PI).toFixed(1)}deg > ${P.JOINT_LIMITS[b.name]}deg` });
      }
    }

    const jp = P.forwardKinematics(pose, { ground: true });
    for (const j of CONTACT_JOINTS) {
      const p = jp[j];
      if (p && p[1] < P.GROUND_Y - o.pierceTol) {
        issues.push({ kind: "pierce", detail: `${j} at y=${p[1].toFixed(2)}` });
      }
    }

    if (o.supported) {
      // Externally braced: balance is legitimately shared with the support.
    } else {
      const contacts = contactPoints(jp, o);
      if (contacts.length) {
        const com = centerOfMass(jp);
        const d = distToSupport(com[0], com[2], contacts);
        if (d > o.contactRadius + o.comMargin) {
          issues.push({ kind: "balance", detail: `COM ${d.toFixed(1)} units outside support` });
        }
      }
    }

    return { ok: issues.length === 0, issues };
  }

  // Validate a whole exercise across its phases at interpolated times.
  // Movements whose object set includes an external support (chair, wall,
  // counter, step) run with the balance check relaxed — the real human is braced.
  const SUPPORT_OBJECTS = new Set(["chair", "wall", "counter", "step"]);
  function isSupported(exercise) {
    const obj = exercise.object || {};
    return Object.values(obj).some((v) => SUPPORT_OBJECTS.has(v));
  }

  function validateExercise(exercise, opts = {}) {
    const poses = exercise.poses3d || P.adaptExercise(exercise);
    const supported = opts.supported != null ? opts.supported : isSupported(exercise);
    const issues = [];
    for (const ph of exercise.phases || []) {
      for (const t of [0, 0.25, 0.5, 0.75, 1]) {
        const a = poses[ph.from] || poses[ph.to], b = poses[ph.to] || poses[ph.from];
        if (!a || !b) continue;
        const res = validatePose(P.slerpPose(a, b, t), Object.assign({}, opts, { supported }));
        for (const i of res.issues) issues.push(Object.assign({ phase: ph.name, t }, i));
      }
    }
    return { ok: issues.length === 0, issues, supported };
  }

  return {
    SEGMENTS, DEFAULTS, CONTACT_JOINTS, SUPPORT_OBJECTS,
    centerOfMass, contactPoints, convexHull, distToSupport,
    validatePose, validateExercise, isSupported,
  };
});

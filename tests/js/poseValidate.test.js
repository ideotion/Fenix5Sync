// SPDX-License-Identifier: GPL-3.0-or-later
// Tests for the biomechanical-plausibility validator (web/js/poseValidate.js):
// Dempster/Winter COM, base-of-support geometry, the validator's failure modes
// on deliberately-invalid poses, and a full-content RATCHET — every movement
// outside the documented waiver list must pass; waived movements carry known,
// named defects (missing weight-shift authoring, missing hand/knee/heel contact
// anchoring) that the roadmap's contact-schema and grace work will fix. The
// waiver may only shrink: a waived movement that starts passing fails the
// stale-waiver guard until it is removed.
"use strict";
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const P = require("../../web/js/pose3d.js");
const PV = require("../../web/js/poseValidate.js");

function identityPose() {
  const p = {};
  P.BONES.forEach((b) => { p[b.name] = [0, 0, 0, 1]; });
  return p;
}

function allMovements() {
  const home = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "web/content/home/exercises.json"), "utf8")).exercises;
  const tc = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "web/content/taichi/movements.json"), "utf8")).movements;
  return home.concat(tc);
}

// ------------------------------ COM & geometry ------------------------------ //
test("PR7: segment masses sum to 1.0 (Dempster/Winter)", () => {
  const total = PV.SEGMENTS.reduce((s, x) => s + x.mass, 0);
  assert.ok(Math.abs(total - 1.0) < 1e-9, `masses sum to ${total}`);
});

test("PR7: standing COM sits near the cited ~55% of stature, centered", () => {
  const jp = P.forwardKinematics(identityPose(), { ground: true });
  const com = PV.centerOfMass(jp);
  const stature = jp.head[1] + 17;  // head joint + head radius approximates the vertex
  const frac = com[1] / stature;
  assert.ok(frac > 0.50 && frac < 0.60, `COM at ${(frac * 100).toFixed(1)}% of stature`);
  assert.ok(Math.abs(com[0]) < 1.0, "COM centered in x");
});

test("PR7: distToSupport is 0 inside the hull and positive outside", () => {
  const contacts = [
    { joint: "a", x: -10, z: -10 }, { joint: "b", x: 10, z: -10 },
    { joint: "c", x: 10, z: 10 }, { joint: "d", x: -10, z: 10 },
  ];
  assert.strictEqual(PV.distToSupport(0, 0, contacts), 0);
  assert.ok(Math.abs(PV.distToSupport(20, 0, contacts) - 10) < 1e-9);
  // Two-point support degenerates to a segment; one point to a point.
  assert.ok(Math.abs(PV.distToSupport(0, 5, contacts.slice(0, 2)) - 15) < 1e-9);
  assert.ok(Math.abs(PV.distToSupport(3, -10, contacts.slice(0, 1)) - 13) < 1e-9);
});

// ------------------------- deliberately invalid poses ----------------------- //
test("PR7: an over-limit elbow fails with a 'limit' issue", () => {
  const pose = identityPose();
  const a = (179 * Math.PI / 180) / 2;
  pose.forearmL = [Math.sin(a), 0, 0, Math.cos(a)];   // 179deg fold — impossible
  const res = PV.validatePose(pose);
  assert.ok(!res.ok && res.issues.some((i) => i.kind === "limit" && i.detail.includes("forearmL")));
});

test("PR7: a denormalized quaternion fails with a 'quat' issue", () => {
  const pose = identityPose();
  pose.thighR = [0.5, 0.5, 0.5, 0.9];                  // |q| far from 1
  const res = PV.validatePose(pose);
  assert.ok(!res.ok && res.issues.some((i) => i.kind === "quat" && i.detail.includes("thighR")));
});

test("PR7: an extreme unsupported backward lean fails the balance check", () => {
  // Backward, not forward: toes extend the support forward (a human really can
  // lean far toward their toes), but nothing extends behind the ankles.
  const pose = identityPose();
  const a = (-80 * Math.PI / 180) / 2;
  pose.lumbar = [Math.sin(a), 0, 0, Math.cos(a)];      // trunk pitched ~80deg back, feet planted
  const res = PV.validatePose(pose);
  assert.ok(!res.ok && res.issues.some((i) => i.kind === "balance"), JSON.stringify(res.issues));
  // ...and the same pose passes when externally supported (hands on a wall).
  const braced = PV.validatePose(pose, { supported: true });
  assert.ok(!braced.issues.some((i) => i.kind === "balance"));
});

test("PR7: toes-up feet push the ankles through the floor -> 'pierce'", () => {
  const pose = identityPose();
  const a = (-50 * Math.PI / 180) / 2;                 // pitch both feet toes-up
  pose.footL = [Math.sin(a), 0, 0, Math.cos(a)];
  pose.footR = [Math.sin(a), 0, 0, Math.cos(a)];
  const res = PV.validatePose(pose);
  assert.ok(res.issues.some((i) => i.kind === "pierce"), JSON.stringify(res.issues));
});

test("PR7: the identity standing pose validates clean", () => {
  const res = PV.validatePose(identityPose());
  assert.ok(res.ok, JSON.stringify(res.issues));
});

// ------------------------------ content ratchet ----------------------------- //
// Known-defective movements, with the ROOT CAUSE named. These are real findings
// the validator surfaced in shipped content — not validator bugs:
//   balance — the authored 2-D motion never shifts the COM over the stance leg
//             (single-support phases stand on one foot with the body centered);
//             fixed by weight-shift authoring (roadmap grace/sequencing pack).
//   pierce  — floor/prone poses lack hand/knee contact anchoring, and heel-rock
//             movements have no heel contact joint; fixed by the contact schema
//             (roadmap 5.6) and a heel contact point.
// The list may only SHRINK: fixing a movement makes the stale-waiver guard fail
// until its entry is deleted. limit/quat issues are NEVER waivable.
const WAIVED = {
  "towel-hamstring-slider": ["pierce", "balance"],
  "knee-pushup": ["pierce"],
  "full-pushup": ["balance"],
  "prone-ytw": ["pierce", "balance"],
  "water-bottle-carry": ["balance"],
  "backpack-carry": ["balance"],
  "suitcase-carry": ["balance"],
  "heel-to-toe-walk": ["balance"],
  "marching-in-place": ["balance"],
  "knee-plank": ["pierce", "balance"],
  "full-plank": ["balance"],
  "tc_heel_toe_raises": ["pierce"],
  "tc_seated_marching": ["pierce"],
  "tc_ankle_calf_pumps": ["pierce"],
};

test("PR7: every non-waived movement passes the full validator", () => {
  const failures = [];
  for (const ex of allMovements()) {
    if (WAIVED[ex.id]) continue;
    const res = PV.validateExercise(ex);
    if (!res.ok) failures.push(`${ex.id}: ${res.issues[0].kind} ${res.issues[0].detail}`);
  }
  assert.deepStrictEqual(failures, [], failures.join("\n"));
});

test("PR7: no movement ever fails on limit or quat (never waivable)", () => {
  for (const ex of allMovements()) {
    const res = PV.validateExercise(ex);
    const hard = res.issues.filter((i) => i.kind === "limit" || i.kind === "quat");
    assert.deepStrictEqual(hard, [], `${ex.id} has non-waivable issues`);
  }
});

test("PR7: waived movements still fail as documented (stale-waiver guard)", () => {
  const byId = Object.fromEntries(allMovements().map((e) => [e.id, e]));
  for (const [id, kinds] of Object.entries(WAIVED)) {
    const ex = byId[id];
    assert.ok(ex, `waiver for unknown movement ${id} — remove it`);
    const res = PV.validateExercise(ex);
    assert.ok(!res.ok, `${id} now passes — remove its waiver (the ratchet only shrinks)`);
    const seen = new Set(res.issues.map((i) => i.kind));
    for (const k of seen) assert.ok(kinds.includes(k), `${id} fails with unexpected kind '${k}'`);
  }
});

test("PR7: support objects relax only the balance check", () => {
  const byId = Object.fromEntries(allMovements().map((e) => [e.id, e]));
  const supportedEx = allMovements().find((e) => PV.isSupported(e));
  assert.ok(supportedEx, "expected at least one chair/wall-supported movement");
  // A supported movement runs with supported=true by default...
  assert.strictEqual(PV.validateExercise(supportedEx).supported, true);
  // ...and a chair-based movement passes while braced.
  const sts = byId["supported-squat"];
  if (sts) assert.ok(PV.validateExercise(sts).ok, "supported-squat should validate braced");
});

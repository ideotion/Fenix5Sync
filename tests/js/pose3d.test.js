// SPDX-License-Identifier: GPL-3.0-or-later
// Unit tests for the engine-agnostic 3-D motion core (web/js/pose3d.js):
// quaternion math, forward kinematics, pose interpolation, and the 2-D -> 3-D
// IK adapter. Run via `node --test` (driven from tests/test_js_units.py).
"use strict";
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const P = require("../../web/js/pose3d.js");
const { Q, V } = P;

const close = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;
const vClose = (a, b, eps = 1e-5) => a.every((x, i) => close(x, b[i], eps));
const dir = (a, b) => V.norm(V.sub(b, a));

// --------------------------------- quaternion ------------------------------- //
test("quaternion multiply by identity is a no-op", () => {
  const q = Q.norm([0.1, 0.2, 0.3, 0.9]);
  assert.ok(vClose(Q.mul(q, Q.IDENT), q));
  assert.ok(vClose(Q.mul(Q.IDENT, q), q));
});

test("fromTo rotates one unit vector onto another", () => {
  const q = Q.fromTo([1, 0, 0], [0, 1, 0]);
  assert.ok(vClose(Q.rotate(q, [1, 0, 0]), [0, 1, 0]));
});

test("fromTo handles parallel and antiparallel vectors", () => {
  assert.ok(vClose(Q.fromTo([0, 1, 0], [0, 1, 0]), Q.IDENT));
  const flip = Q.fromTo([0, 1, 0], [0, -1, 0]);   // 180 degrees
  assert.ok(vClose(Q.rotate(flip, [0, 1, 0]), [0, -1, 0], 1e-5));
});

test("rotating preserves length and conj inverts the rotation", () => {
  const q = Q.fromTo([1, 0, 0], V.norm([1, 2, 3]));
  const v = [3, -1, 2];
  assert.ok(close(V.len(Q.rotate(q, v)), V.len(v)));
  assert.ok(vClose(Q.rotate(Q.conj(q), Q.rotate(q, v)), v));
});

test("slerp hits its endpoints and the halfway rotation", () => {
  const a = Q.IDENT, b = Q.fromTo([1, 0, 0], [0, 1, 0]); // 90deg about Z
  assert.ok(vClose(Q.slerp(a, b, 0), a));
  assert.ok(vClose(Q.slerp(a, b, 1), b));
  const mid = Q.slerp(a, b, 0.5);                          // 45deg
  const r = Q.rotate(mid, [1, 0, 0]);
  assert.ok(close(r[0], Math.SQRT1_2, 1e-4) && close(r[1], Math.SQRT1_2, 1e-4));
});

// ----------------------------- forward kinematics --------------------------- //
test("forward kinematics on an all-identity pose returns the rest skeleton dirs", () => {
  const localQ = {};
  P.BONES.forEach((b) => { localQ[b.name] = Q.IDENT; });
  const jp = P.forwardKinematics(localQ);
  // The spine should point straight up from the hips.
  assert.ok(vClose(dir(jp.hips, jp.spine), [0, 1, 0], 1e-6));
  // Head above the spine; feet below the hips.
  assert.ok(jp.head[1] > jp.spine[1] && jp.ankleL[1] < jp.hips[1]);
});

// ------------------------------- 2-D -> 3-D IK ------------------------------ //
function loadExercise(id) {
  const lib = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "web/content/home/exercises.json"), "utf8"));
  return lib.exercises.find((e) => e.id === id);
}

function loadTaichi(id) {
  const lib = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "web/content/taichi/movements.json"), "utf8"));
  return lib.movements.find((m) => m.id === id);
}

test("adaptPose then FK reproduces the 2-D-derived bone direction (spine)", () => {
  // A side pose: shoulders directly above the hips -> spine points up (+Y),
  // with a tiny forward lean from the small x offset.
  const views = { side: { stand: { hip: [116, 178], sh: [118, 98], head: [120, 70], knee: [114, 248], ankle: [112, 312], toe: [140, 312], elb: [136, 134], hand: [150, 170] } } };
  const pose = P.adaptPose(views, "stand");
  const jp = P.forwardKinematics(pose);
  const spineDir = dir(jp.hips, jp.spine);
  assert.ok(spineDir[1] > 0.98, `spine should point up, got ${spineDir}`);
});

test("a raised-arm front pose lifts the upper-arm direction", () => {
  // Arms overhead: hands and elbows above the shoulders.
  const overhead = {
    head: [120, 70], sh: [120, 100], hip: [120, 180],
    lknee: [104, 248], rknee: [136, 248], lankle: [102, 312], rankle: [138, 312],
    lelb: [96, 70], relb: [144, 70], lhand: [92, 36], rhand: [148, 36],
  };
  const pose = P.adaptPose({ front: { up: overhead } }, "up");
  const jp = P.forwardKinematics(pose);
  // The left elbow should sit above the left shoulder.
  assert.ok(jp.elbowL[1] > jp.shoulderL[1], "raised arm: elbow above shoulder");
});

test("adaptExercise covers every pose with every bone, normalized", () => {
  const sts = loadExercise("supported-squat") || loadExercise("bodyweight-squat");
  const poses = P.adaptExercise(sts);
  const poseNames = Object.keys(poses);
  assert.ok(poseNames.length >= 2);
  for (const name of poseNames) {
    for (const b of P.BONES) {
      const q = poses[name][b.name];
      assert.ok(q, `${name} missing bone ${b.name}`);
      assert.ok(close(Math.hypot(q[0], q[1], q[2], q[3]), 1, 1e-6), `${name}.${b.name} not unit`);
    }
  }
});

// ------------------------------ PR1: root travel ---------------------------- //
test("PR1: pelvis world displacement equals the scaled 2-D hip travel (squat)", () => {
  const ex = loadExercise("supported-squat") || loadExercise("bodyweight-squat");
  const side = ex.views.side, names = Object.keys(side);
  const poses = P.adaptExercise(ex);
  const a = names[0], b = names[1];
  const ha = side[a].hip, hb = side[b].hip;
  // side view: art-x -> world Z, art-y -> -world Y; scaled art->world (matches the core).
  const scale = (P.REST.hips[1] - P.REST.ankleL[1]) / 134;
  const expDY = -(hb[1] - ha[1]) * scale, expDZ = (hb[0] - ha[0]) * scale;
  const ra = poses[a].__root, rb = poses[b].__root;
  assert.ok(Math.abs((rb[1] - ra[1]) - expDY) < 1e-6, "pelvis Y tracks the authored hip art-y");
  assert.ok(Math.abs((rb[2] - ra[2]) - expDZ) < 1e-6, "pelvis Z tracks the authored hip art-x");
  // Every pose carries a bounded root (no runaway scaling).
  Object.values(poses).forEach((p) => {
    assert.ok(p.__root && p.__root.length === 3, "pose missing __root");
    assert.ok(Math.abs(p.__root[1] - P.REST.hips[1]) < 120, "pelvis travel runaway");
  });
});

test("PR1: a fixed-hip exercise keeps the pelvis at rest height", () => {
  // marching-in-place: the authored hip does not drop, so the pelvis should not.
  const ex = loadExercise("marching-in-place") || loadExercise("wall-pushup");
  const poses = P.adaptExercise(ex);
  const ys = Object.values(poses).map((p) => p.__root[1]);
  assert.ok(Math.max(...ys) - Math.min(...ys) < 25, "no authored descent -> little pelvis travel");
});

test("PR1: pelvis translates in depth with a weight shift (tai chi)", () => {
  const mv = loadTaichi("tc_weight_shift_fwd_back");
  if (!mv) return;
  const poses = P.adaptExercise(mv);
  const zs = Object.values(poses).map((p) => p.__root[2]);
  assert.ok(Math.max(...zs) - Math.min(...zs) > 5, "weight shift should translate the pelvis");
});

test("PR1: root is interpolated by slerpPose", () => {
  const ex = loadExercise("supported-squat") || loadExercise("bodyweight-squat");
  const poses = P.adaptExercise(ex);
  const ns = Object.keys(poses);
  const mid = P.slerpPose(poses[ns[0]], poses[ns[1]], 0.5);
  assert.ok(mid.__root, "slerpPose should carry __root");
  const expectY = (poses[ns[0]].__root[1] + poses[ns[1]].__root[1]) / 2;
  assert.ok(Math.abs(mid.__root[1] - expectY) < 1e-6, "root midpoint should be the average");
});

test("PR1: FK with all-identity (no __root) still rests at REST.hips (back-compat)", () => {
  const localQ = {};
  P.BONES.forEach((b) => { localQ[b.name] = Q.IDENT; });
  assert.deepStrictEqual(P.forwardKinematics(localQ).hips, P.REST.hips);
});

test("slerpPose blends two poses per bone and stays normalized", () => {
  const a = P.adaptPose({ side: { stand: { hip: [116, 178], sh: [118, 98], head: [120, 70], knee: [114, 248], ankle: [112, 312], toe: [140, 312], elb: [136, 134], hand: [150, 170] } } }, "stand");
  const b = P.adaptPose({ side: { sit: { hip: [150, 236], sh: [138, 170], head: [140, 150], knee: [112, 242], ankle: [112, 312], toe: [140, 312], elb: [170, 196], hand: [150, 224] } } }, "sit");
  const mid = P.slerpPose(a, b, 0.5);
  for (const bone of P.BONES) {
    const q = mid[bone.name];
    assert.ok(close(Math.hypot(q[0], q[1], q[2], q[3]), 1, 1e-6));
  }
});

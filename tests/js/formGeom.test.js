// SPDX-License-Identifier: GPL-3.0-or-later
// Unit tests for the form-model pseudo-3-D projection + foot/depth helpers.
// Run via `node --test` (driven from tests/test_js_units.py under pytest).
"use strict";
const assert = require("node:assert");
const { test } = require("node:test");
const G = require("../../web/js/formGeom.js");

test("project is the identity at yaw 0 (2-D back-compat)", () => {
  const p = G.project([140, 200], 0);
  assert.strictEqual(p.x, 140);
  assert.strictEqual(p.y, 200);
  assert.strictEqual(p.depth, 0);
});

test("project applies the documented yaw formula", () => {
  const yaw = 30 * G.DEG, x = 160, z = 10;
  const p = G.project([x, 200, z], yaw);
  const expected = 120 + (x - 120) * Math.cos(yaw) + z * Math.sin(yaw);
  assert.ok(Math.abs(p.x - expected) < 1e-9, `${p.x} != ${expected}`);
  assert.strictEqual(p.y, 200);
});

test("a point on the center axis is unaffected by yaw", () => {
  const p = G.project([120, 100], 45 * G.DEG);
  assert.ok(Math.abs(p.x - 120) < 1e-9);
});

test("yaw 90deg collapses flat (z=0) x toward the axis — the documented degeneracy", () => {
  const p = G.project([180, 100], 90 * G.DEG);
  assert.ok(Math.abs(p.x - 120) < 1e-9);
});

test("authored z becomes horizontal offset at yaw 90deg (turn works once z exists)", () => {
  const p = G.project([120, 100, 40], 90 * G.DEG);
  assert.ok(Math.abs(p.x - 160) < 1e-9);
});

test("projectXY returns just [x, y]", () => {
  const xy = G.projectXY([200, 50, 0], 20 * G.DEG);
  assert.strictEqual(xy.length, 2);
  assert.strictEqual(xy[1], 50);
});

test("heel sits behind the ankle, opposite the toe", () => {
  const h = G.heel([112, 312], [140, 312]); // toe ahead (+x)
  assert.ok(h[0] < 112, "heel behind ankle");
  assert.strictEqual(h[1], 312);
});

test("heel lifts with the ankle while the toe stays planted (calf raise)", () => {
  const h = G.heel([114, 296], [140, 312]);
  assert.ok(h[1] < 312, "heel off the ground");
  assert.ok(h[0] < 114, "heel still behind ankle");
});

test("heel mirrors correctly when the toe points the other way", () => {
  const h = G.heel([128, 312], [100, 312]); // toe behind (-x) => facing left
  assert.ok(h[0] > 128, "heel now on the +x side");
});

test("heel preserves a z component when joints are 3-D", () => {
  const h = G.heel([112, 312, 4], [140, 312, 0]);
  assert.strictEqual(h.length, 3);
});

test("depthShade is 1.0 for flat 2-D data and dims with depth", () => {
  assert.strictEqual(G.depthShade(0), 1);
  assert.ok(G.depthShade(-60) < 1);
  assert.ok(G.depthShade(60) >= 1 - 1e-9); // nearer is not brighter than 1
});

test("depthShade clamps to the floor and never goes negative", () => {
  assert.ok(G.depthShade(-100000) >= 0.6);
  assert.ok(G.depthShade(-100000) > 0);
});

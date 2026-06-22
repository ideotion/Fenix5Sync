// SPDX-License-Identifier: GPL-3.0-or-later
// Unit tests for the pure session-builder selection logic (web/js/sessionBuilder.js).
// Run via `node --test` (driven from tests/test_js_units.py under pytest).
"use strict";
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const SB = require("../../web/js/sessionBuilder.js");

const ROOT = path.resolve(__dirname, "..", "..");
const HOME = JSON.parse(fs.readFileSync(path.join(ROOT, "web/content/home/exercises.json"), "utf8")).exercises;
const TAICHI = JSON.parse(fs.readFileSync(path.join(ROOT, "web/content/taichi/movements.json"), "utf8")).movements;

const byId = (id) => HOME.find((e) => e.id === id);
const noAdjacentRegionRepeat = (items) => {
  for (let i = 1; i < items.length; i++) {
    if (items[i].region === items[i - 1].region) return false;
  }
  return true;
};

// ------------------------------- derivations -------------------------------- //
test("region is derived from pattern", () => {
  assert.strictEqual(SB.deriveRegion(byId("bodyweight-squat")), "lower_body");
  assert.strictEqual(SB.deriveRegion(byId("wall-pushup")), "upper_body");
  assert.strictEqual(SB.deriveRegion(byId("knee-plank")), "core");
  assert.strictEqual(SB.deriveRegion(byId("tandem-stand")), "balance");
  assert.strictEqual(SB.deriveRegion(byId("marching-in-place")), "cardio");
  assert.strictEqual(SB.deriveRegion(byId("water-bottle-carry")), "full_body");
});

test("a full-body carry covers lower+upper+core", () => {
  assert.deepStrictEqual(SB.deriveCovers(byId("water-bottle-carry")).sort(),
    ["core", "lower_body", "upper_body"]);
});

test("weight-capable excludes balance, cardio and isometrics", () => {
  assert.ok(SB.isWeightCapable(byId("bodyweight-squat")));
  assert.ok(SB.isWeightCapable(byId("backpack-row")));
  assert.ok(!SB.isWeightCapable(byId("tandem-stand")));        // balance
  assert.ok(!SB.isWeightCapable(byId("marching-in-place")));   // cardio
  assert.ok(!SB.isWeightCapable(byId("knee-plank")));          // isometric
  assert.ok(!SB.isWeightCapable(byId("wall-press-hold")));     // push but isometric
});

test("weighted variant swaps the object glyph and adds a load cue", () => {
  const v = SB.weightedVariant(byId("bodyweight-squat"));   // squat -> kettlebell
  assert.strictEqual(v.object.side, "kettlebell");
  assert.ok(v.weighted && /12\+/.test(v.loadCue));
  const row = SB.weightedVariant(byId("backpack-row"));     // pull -> dumbbell
  assert.strictEqual(row.object.side, "dumbbell");
  // never weights a non-capable movement.
  assert.strictEqual(SB.weightedVariant(byId("tandem-stand")).weighted, undefined);
});

// --------------------------------- home ------------------------------------- //
test("a home session covers lower, upper and core", () => {
  const s = SB.buildHome(HOME, { lengthMin: 20, tier: "standing", cleared: true, seed: 7 });
  assert.ok(s.coverageOk);
  for (const r of ["lower_body", "upper_body", "core"]) assert.ok(s.covered.includes(r));
});

test("no two consecutive exercises share a region", () => {
  const s = SB.buildHome(HOME, { lengthMin: 30, tier: "loaded", cleared: true, seed: 3 });
  assert.ok(noAdjacentRegionRepeat(s.items), s.items.map((i) => i.region).join(","));
});

test("no exercise repeats within a session", () => {
  const s = SB.buildHome(HOME, { lengthMin: 30, tier: "loaded", cleared: true, seed: 5 });
  const ids = s.items.map((i) => i.id);
  assert.strictEqual(ids.length, new Set(ids).size);
});

test("session is packed to roughly the time budget", () => {
  const s = SB.buildHome(HOME, { lengthMin: 20, sets: 2, reps: 10, tier: "standing", cleared: true, seed: 2 });
  assert.ok(s.seconds >= 20 * 60 * 0.6, `too short: ${s.seconds}s`);
  assert.ok(s.seconds <= 20 * 60 + 240, `too long: ${s.seconds}s`);  // <= budget + ~one cooldown
});

test("warm-up is first and cool-down is last", () => {
  const s = SB.buildHome(HOME, { lengthMin: 20, tier: "standing", cleared: true, seed: 9 });
  assert.strictEqual(s.items[0].role, "warmup");
  assert.strictEqual(s.items[s.items.length - 1].role, "cooldown");
});

test("free weights substitute weighted variants where available", () => {
  const s = SB.buildHome(HOME, { lengthMin: 30, equipment: "weights", tier: "loaded", cleared: true, seed: 4 });
  const weighted = s.items.filter((i) => i.ex.weighted);
  assert.ok(weighted.length >= 1, "expected at least one weighted exercise");
  for (const i of weighted) {
    assert.ok(["dumbbell", "kettlebell"].includes(i.ex.object.side || i.ex.object.front));
    assert.ok(SB.isWeightCapable(byId(i.id)));   // only capable patterns get weighted
  }
});

test("isometrics are gated behind PAR-Q+ clearance", () => {
  const gated = SB.buildHome(HOME, { lengthMin: 30, tier: "standing", cleared: false, seed: 1 });
  assert.ok(gated.items.every((i) => !i.ex.isometric), "an isometric leaked past the gate");
  const cleared = SB.buildHome(HOME, { lengthMin: 45, tier: "loaded", cleared: true, seed: 1 });
  // With clearance, holds are allowed back into the pool.
  assert.ok(cleared.items.length > 0);
});

test("balance is mandatory at the fragile (seated) tier", () => {
  const s = SB.buildHome(HOME, { lengthMin: 20, tier: "seated", cleared: true, seed: 6 });
  assert.ok(s.covered.includes("balance"), "fragile session must include balance");
});

test("sessions vary across seeds", () => {
  const a = SB.buildHome(HOME, { lengthMin: 20, tier: "loaded", cleared: true, seed: 1 }).items.map((i) => i.id).join();
  const b = SB.buildHome(HOME, { lengthMin: 20, tier: "loaded", cleared: true, seed: 99 }).items.map((i) => i.id).join();
  assert.notStrictEqual(a, b);
  // ...but a given seed is deterministic.
  const a2 = SB.buildHome(HOME, { lengthMin: 20, tier: "loaded", cleared: true, seed: 1 }).items.map((i) => i.id).join();
  assert.strictEqual(a, a2);
});

// -------------------------------- tai chi ----------------------------------- //
test("a tai chi session covers balance, mobility, lower-limb and breathing", () => {
  const s = SB.buildTaiChi(TAICHI, { lengthMin: 20, level: "standing", focus: "full", seed: 2 });
  for (const f of ["balance", "mobility", "lower-limb", "breathing"]) {
    assert.ok(s.covered.includes(f), `missing focus: ${f}`);
  }
});

test("tai chi opens and closes with breathing and is never weighted", () => {
  const s = SB.buildTaiChi(TAICHI, { lengthMin: 15, level: "chair", focus: "balance", seed: 1 });
  assert.strictEqual(s.items[0].region, "breathing");
  assert.strictEqual(s.items[s.items.length - 1].region, "breathing");
  assert.ok(s.items.every((i) => !i.ex.weighted));
  assert.ok(s.covered.includes("balance"));  // mandatory at the fragile (chair) level
});

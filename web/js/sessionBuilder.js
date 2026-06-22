/* Session builder: a pure SELECTION function for Sports at Home + Tai Chi.

   Given the exercise/movement library and the user's inputs (length, sets/reps,
   equipment, tier, focus), it returns an ordered, time-budgeted session that
   covers the right body regions, never repeats an exercise or two regions in a
   row, respects the readiness gate (isometrics behind PAR-Q+ clearance), and
   substitutes free-weight variants when asked. No DOM — it runs in the browser
   (window.SessionBuilder) and under Node (module.exports), where it is
   unit-tested. The incoming metadata lacks region/equipment/weighted_variant, so
   those are DERIVED here from `pattern` per the documented rules. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SessionBuilder = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TIER_ORDER = ["seated", "standing", "loaded", "conditioning"];
  const tierIndex = (t) => { const i = TIER_ORDER.indexOf(t); return i < 0 ? 1 : i; };

  // region derived from movement pattern (see docs/incoming/README addendum).
  const REGION_BY_PATTERN = {
    squat: "lower_body", hinge: "lower_body", calf: "lower_body", lunge: "lower_body",
    push: "upper_body", pull: "upper_body", press: "upper_body", row: "upper_body",
    raise: "upper_body", curl: "upper_body",
    rotation: "core", isometric: "core",
    balance: "balance", aerobic: "cardio", mobility: "mobility", carry: "full_body",
  };
  // patterns that can take an external load -> a weighted variant.
  const WEIGHT_PATTERNS = new Set(["squat", "hinge", "push", "pull", "carry",
    "press", "row", "raise", "curl", "lunge"]);

  const REST_S = 30, TRANSITION_S = 15;

  function deriveRegion(ex) { return REGION_BY_PATTERN[ex.pattern] || "full_body"; }
  // covers: a carry (full_body) counts toward lower+upper+core at once.
  function deriveCovers(ex) {
    const r = deriveRegion(ex);
    return r === "full_body" ? ["lower_body", "upper_body", "core"] : [r];
  }
  // weight-capable: a loadable pattern that is NOT an isometric hold.
  function isWeightCapable(ex) { return WEIGHT_PATTERNS.has(ex.pattern) && !ex.isometric; }

  // Swap a weight-capable exercise's object for a free weight that tracks the
  // hands, and add the honest load cue. Balance / mobility / cardio / isometrics
  // are never weighted (isWeightCapable already excludes them).
  function weightedVariant(ex) {
    if (!isWeightCapable(ex)) return ex;
    const glyph = (ex.pattern === "squat" || ex.pattern === "hinge") ? "kettlebell" : "dumbbell";
    const object = Object.assign({ side: null, front: null }, ex.object || {});
    Object.keys(ex.views || {}).forEach((v) => { object[v] = glyph; });
    return Object.assign({}, ex, {
      object, weighted: true,
      loadCue: "Choose a weight you could lift about 12+ times — effort by feel, not kilograms.",
    });
  }

  // Estimate a set's wall-clock from the engine's actual phase clock: one rep is
  // a full pass through the phases. Holds (one cycle = rise+hold+lower) and reps
  // (targetReps cycles, capped by the chosen reps) both follow from the phase
  // durations, so the estimate matches what the player will actually take.
  function _cycleSeconds(ex) {
    if (ex.phases && ex.phases.length) {
      return ex.phases.reduce((s, p) => s + (p.dur || 0), 0) / 1000;
    }
    return ex.holdMs ? ex.holdMs / 1000 : 6;
  }
  function estimateSeconds(ex, sets, opts) {
    const cyc = _cycleSeconds(ex);
    const reps = ex.targetReps ? Math.min((opts && opts.reps) || ex.targetReps, ex.targetReps) : 1;
    const perSet = Math.max(1, reps) * cyc;
    return Math.round(sets * perSet + Math.max(0, sets - 1) * REST_S + TRANSITION_S);
  }

  // Small deterministic PRNG so "vary across sessions" is reproducible per seed.
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function _annotate(ex) {
    return { ex, id: ex.id, region: deriveRegion(ex), covers: deriveCovers(ex),
             weightCap: isWeightCapable(ex), iso: !!ex.isometric, tier: ex.tier };
  }

  // Greedy: warm-up first, cover the required regions, fill the time budget with
  // variety, cool-down last — never repeating an exercise or two regions in a row.
  function buildHome(exercises, opts) {
    const o = Object.assign({
      lengthMin: 15, sets: 2, reps: 10, workSeconds: 30, equipment: "bodyweight",
      tier: "standing", focus: "full_body", cleared: true, seed: 1,
    }, opts || {});
    const rnd = mulberry32((o.seed >>> 0) || 1);
    const ceil = tierIndex(o.tier);

    let pool = exercises.map(_annotate).filter((a) => {
      if (a.iso && !o.cleared) return false;                      // PAR-Q+ gate
      if (o.tier === "seated" && tierIndex(a.tier) === 3) return false;  // no vigorous for fragile
      return true;
    });
    if (o.equipment === "weights") {
      pool = pool.map((a) => a.weightCap ? _annotate(weightedVariant(a.ex)) : a);
    }

    const used = new Set();
    const budget = o.lengthMin * 60;
    const chosen = [];   // {a, role, sets, seconds}
    const covered = new Set();
    let secs = 0;

    const sortKey = (a) => [tierIndex(a.tier) <= ceil ? 0 : 1, Math.abs(tierIndex(a.tier) - ceil), rnd()];
    const pick = (pred) => pool.filter((a) => !used.has(a.id) && pred(a))
      .map((a) => ({ a, k: sortKey(a) }))
      .sort((x, y) => x.k[0] - y.k[0] || x.k[1] - y.k[1] || x.k[2] - y.k[2])
      .map((x) => x.a)[0] || null;
    const add = (a, role) => {
      if (!a) return false;
      const sets = (role === "warmup" || role === "cooldown") ? 1 : o.sets;
      const seconds = estimateSeconds(a.ex, sets, o);
      used.add(a.id); chosen.push({ a, role, sets, seconds }); secs += seconds;
      a.covers.forEach((c) => covered.add(c));
      return true;
    };

    // 1) Warm-up: a gentle cardio (marching) if available, else any mobility.
    add(pick((a) => a.region === "cardio") || pick((a) => a.region === "mobility"), "warmup");
    // 2) Reserve a cool-down up front (a different cardio, else mobility/balance)
    //    so the fill loop can't consume it and the time is budgeted.
    add(pick((a) => a.region === "cardio") || pick((a) => a.region === "mobility")
      || pick((a) => a.region === "balance"), "cooldown");

    // 3) Required region coverage.
    const required = ["lower_body", "upper_body", "core"];
    const fragile = o.tier === "seated";
    if (fragile || o.focus === "balance") required.push("balance");
    if (["lower_body", "upper_body", "core", "balance"].includes(o.focus) && !required.includes(o.focus)) {
      required.push(o.focus);  // a focused region is guaranteed coverage
    }
    for (const region of required) {
      if (covered.has(region)) continue;
      add(pick((a) => a.covers.includes(region) && a.region !== "cardio"), "main");
    }

    // 4) Fill the remaining budget with variety (focus-biased), respecting time.
    let guard = 0;
    while (secs < budget && guard++ < 50) {
      const prevRegion = chosen.length ? chosen[chosen.length - 1].a.region : null;
      const biased = o.focus && o.focus !== "full_body"
        ? pick((a) => a.region === o.focus && a.region !== prevRegion) : null;
      const next = biased
        || pick((a) => a.region === "cardio" && a.region !== prevRegion)
        || pick((a) => a.region !== prevRegion && a.region !== "cardio")
        || pick(() => true);
      if (!next) break;
      if (secs + estimateSeconds(next.ex, o.sets, o) > budget && chosen.length > required.length + 1) break;
      add(next, "main");
    }

    const ordered = _arrange(chosen);
    return _result(ordered, o, required, secs);
  }

  // Tai Chi: length-adjustable, covers balance/mobility/lower-limb/breathing by
  // focus, balance mandatory at the fragile level, never weighted, warm-up +
  // cool-down breathing movements bookend.
  function buildTaiChi(movements, opts) {
    const o = Object.assign({ lengthMin: 15, level: "standing", focus: "full", seed: 1 }, opts || {});
    const rnd = mulberry32((o.seed >>> 0) || 1);
    const lvl = tierIndex(o.level === "chair" ? "seated" : o.level);  // chair~seated, supported~standing
    const pool = movements.map((mv) => ({ ex: mv, id: mv.id, region: mv.focus, covers: [mv.focus], tier: mv.level }));
    const used = new Set();
    const budget = o.lengthMin * 60;
    const chosen = [];
    let secs = 0;
    const pick = (pred) => pool.filter((a) => !used.has(a.id) && pred(a))
      .map((a) => ({ a, k: [Math.abs(tierIndex(a.tier) - lvl), rnd()] }))
      .sort((x, y) => x.k[0] - y.k[0] || x.k[1] - y.k[1]).map((x) => x.a)[0] || null;
    const add = (a, role) => {
      if (!a) return false;
      const seconds = estimateSeconds(a.ex, 1, o);
      used.add(a.id); chosen.push({ a, role, sets: 1, seconds }); secs += seconds; return true;
    };

    // Open and close on the breath; reserve the closing breath before filling.
    add(pick((a) => a.region === "breathing"), "warmup");
    add(pick((a) => a.region === "breathing"), "cooldown");

    const required = ["balance", "mobility", "lower-limb", "breathing"];
    const fragile = o.level === "chair" || o.focus === "balance";
    for (const f of required) {
      if (f === "balance" || f === "breathing" || o.focus === "full" || o.focus === f) {
        add(pick((a) => a.region === f), "main");
      }
    }
    if (fragile && !chosen.some((c) => c.role === "main" && c.a.region === "balance")) {
      add(pick((a) => a.region === "balance"), "main");
    }
    let guard = 0;
    while (secs < budget && guard++ < 40) {
      const prev = chosen.length ? chosen[chosen.length - 1].a.region : null;
      const next = pick((a) => a.region !== prev) || pick(() => true);
      if (!next) break;
      if (secs + estimateSeconds(next.ex, 1, o) > budget && chosen.length > 4) break;
      add(next, "main");
    }

    const ordered = _arrange(chosen);
    return _result(ordered, o, ["balance", "mobility", "lower-limb", "breathing"], secs);
  }

  // Reorder mains so no two adjacent share a region (warm-up first, cool-down last).
  function _arrange(chosen) {
    const warm = chosen.filter((c) => c.role === "warmup");
    const cool = chosen.filter((c) => c.role === "cooldown");
    const mains = chosen.filter((c) => c.role === "main");
    const out = [];
    let prev = warm.length ? warm[warm.length - 1].a.region : null;
    const remaining = mains.slice();
    while (remaining.length) {
      let idx = remaining.findIndex((c) => c.a.region !== prev);
      if (idx < 0) idx = 0;  // forced repeat (small pools); accept gracefully
      const next = remaining.splice(idx, 1)[0];
      out.push(next); prev = next.a.region;
    }
    return [...warm, ...out, ...cool];
  }

  function _result(ordered, o, required, seconds) {
    // Coverage is judged on the working (main) movements, not the bookends.
    const covered = new Set(ordered.filter((c) => c.role === "main").flatMap((c) => c.a.covers));
    return {
      items: ordered.map((c) => ({
        id: c.a.id, name: c.a.ex.name, region: c.a.region, role: c.role,
        sets: c.sets, seconds: c.seconds, ex: c.a.ex,
      })),
      seconds, minutes: Math.round(seconds / 60),
      required, covered: Array.from(covered),
      coverageOk: required.every((r) => covered.has(r)),
      options: o,
    };
  }

  return {
    deriveRegion, deriveCovers, isWeightCapable, weightedVariant, estimateSeconds,
    buildHome, buildTaiChi, REGION_BY_PATTERN, TIER_ORDER,
  };
});

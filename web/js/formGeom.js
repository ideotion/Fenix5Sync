/* Pure geometry for the form-model engine: a tiny pseudo-3-D yaw projection plus
   foot/heel and depth-shading helpers. No DOM and no globals beyond the exported
   namespace, so it runs identically in the browser (window.FormGeom) and under
   Node (module.exports) — where the projection math is unit-tested.

   Joint model (shared with the engine): SVG viewBox 240x340, ground y=318, the
   figure faces +x around the vertical axis at x=120. A joint is [x, y] or
   [x, y, z]; a missing z is 0, so every current and incoming 2-D pose renders
   unchanged at yaw 0. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FormGeom = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const CENTER_X = 120;        // vertical axis the figure faces around
  const DEG = Math.PI / 180;

  // Yaw rotates a joint about the vertical axis at CENTER_X:
  //   x' = 120 + (x-120)*cos(yaw) + z*sin(yaw),   y' = y
  // The out-of-screen component (depth) is z*cos(yaw) - (x-120)*sin(yaw); it is
  // used only for subtle shading. HONEST NOTE: because every current/incoming
  // pose is z=0, a 90deg yaw collapses the figure to a vertical line — a true
  // front<->side turn needs authored z. The control is wired so it becomes a
  // real turn once exercises gain depth; per-view 2-D stays the default.
  function project(coord, yaw) {
    const x = coord[0], y = coord[1], z = coord.length > 2 ? coord[2] : 0;
    const c = Math.cos(yaw || 0), s = Math.sin(yaw || 0);
    const dx = x - CENTER_X;
    return { x: CENTER_X + dx * c + z * s, y: y, depth: z * c - dx * s };
  }

  // Project just the screen position — the per-frame hot path.
  function projectXY(coord, yaw) {
    const p = project(coord, yaw);
    return [p.x, p.y];
  }

  // Synthesize a heel behind the ankle so the side-view foot reads as a wedge
  // (ankle apex, heel back, toe front) and the toe leads the facing direction.
  // Reflecting the toe partway across the ankle keeps the heel lifting when the
  // ankle rises (e.g. calf raises) while the planted toe stays on the ground.
  function heel(ankle, toe, ratio) {
    const k = ratio == null ? 0.5 : ratio;
    const az = ankle.length > 2 ? ankle[2] : 0, tz = toe.length > 2 ? toe[2] : 0;
    const h = [ankle[0] + (ankle[0] - toe[0]) * k, ankle[1] + (ankle[1] - toe[1]) * k];
    if (az || tz) h.push(az + (az - tz) * k);
    return h;
  }

  // Map a projected depth to a stroke-opacity for subtle front-lit shading.
  // depth 0 (all current 2-D data) -> 1.0 (no change); deeper/further -> dimmer,
  // clamped to a gentle floor so a limb never disappears.
  function depthShade(depth, span, floor) {
    const sp = span == null ? 120 : span;     // depth that reaches the floor
    const fl = floor == null ? 0.6 : floor;
    const v = 1 + ((depth || 0) / sp) * (1 - fl);
    return Math.max(fl, Math.min(1, v));
  }

  return { CENTER_X, DEG, project, projectXY, heel, depthShade };
});

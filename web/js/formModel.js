/* Form-model engine: tempo-paced SVG figures with the object drawn in place, so
   the user copies the setup, not just the pose. The figure doubles as the
   pacer/metronome. A shared component (used by Sports at Home and Tai Chi).
   Offline, dependency-free, themed from the app's CSS tokens, accessible
   (respects prefers-reduced-motion with a static key-pose fallback).

   Smoothness/quality: the SVG node tree is built once and only its attributes
   are updated per frame (no per-frame innerHTML reparse → steady 60fps); limbs
   are drawn as layered capsules (a background-coloured outline pass under a body
   pass) so overlapping limbs read cleanly; a soft ground shadow tracks the
   figure and a radial glow gently pulses on holds.

   Data-driven: renders any exercise/movement supplied as data (object glyphs are
   the only thing in code). FormModel.create(hostEl, exercise, { onFinish }). */
const FormModel = (() => {
  const SVGNS = "http://www.w3.org/2000/svg";
  const GROUND_Y = 318;
  let _seq = 0;

  // easeInOutCubic — gentle acceleration/deceleration for organic motion.
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // Skeleton segments per view (parent→child pairs of joint names).
  const SEG = {
    side: [["ankle", "toe"], ["ankle", "knee"], ["knee", "hip"], ["hip", "sh"], ["sh", "elb"], ["elb", "hand"]],
    front: [["hip", "lknee"], ["lknee", "lankle"], ["hip", "rknee"], ["rknee", "rankle"],
      ["hip", "sh"], ["sh", "lelb"], ["lelb", "lhand"], ["sh", "relb"], ["relb", "rhand"]],
  };

  // ---- object glyphs (drawn in place, tracking the body) ----
  const OBJECTS = {
    chair: () =>
      `<g class="fm-obj-fill"><rect x="140" y="232" width="60" height="10" rx="3"/></g>` +
      `<g class="fm-obj"><line x1="144" y1="242" x2="144" y2="312"/><line x1="196" y1="242" x2="196" y2="312"/>` +
      `<line x1="196" y1="232" x2="196" y2="168"/><line x1="196" y1="180" x2="178" y2="180"/></g>`,
    wall: () =>
      `<g class="fm-obj-fill"><rect x="72" y="40" width="10" height="${GROUND_Y - 40}" rx="3"/></g>` +
      `<g class="fm-obj"><line x1="82" y1="40" x2="82" y2="${GROUND_Y}"/></g>`,
  };
  const glyph = (id) => (id && OBJECTS[id] ? OBJECTS[id] : null);

  function lerpPose(a, b, t) {
    const out = {};
    for (const k in a) if (b[k]) out[k] = [a[k][0] + (b[k][0] - a[k][0]) * t, a[k][1] + (b[k][1] - a[k][1]) * t];
    return out;
  }

  // String markup (used by the static-fallback minis) — same layered look.
  function markup(p, view, objFn) {
    const line = (a, b, cls) => `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" class="${cls}"/>`;
    let s = `<line class="fm-ground" x1="40" y1="${GROUND_Y}" x2="200" y2="${GROUND_Y}"/>`;
    if (objFn) s += objFn();
    let out = "", core = "";
    for (const [a, b] of SEG[view]) if (p[a] && p[b]) { out += line(p[a], p[b], "fm-bone-outline"); core += line(p[a], p[b], "fm-bone"); }
    s += out + core;
    if (p.head) s += `<circle cx="${p.head[0]}" cy="${p.head[1]}" r="18" class="fm-head-outline"/>` +
      `<circle cx="${p.head[0]}" cy="${p.head[1]}" r="16" class="fm-head"/>`;
    return s;
  }

  function create(host, ex, opts = {}) {
    const onFinish = opts.onFinish || null;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const uid = "fm" + (++_seq);

    let view = ex.views.front && !ex.views.side ? "front" : "side";
    let tempoScale = 1, raf = null, phaseIdx = 0, phaseStart = 0, reps = 0;
    let playing = false, staticMode = reduceMotion, destroyed = false;

    const poses = () => ex.views[view] || ex.views.side || ex.views.front;
    const objFn = () => glyph((ex.object && ex.object[view]) || null);
    const restPoseName = () => (poses().stand ? "stand" : Object.keys(poses())[0]);

    // ---- DOM ----
    host.innerHTML = "";
    const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };

    const svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("viewBox", "0 0 240 340");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", ex.name + " movement figure");
    svg.setAttribute("shape-rendering", "geometricPrecision");
    const stage = el("div", "fm-stage"); stage.appendChild(svg);

    const phaseEl = el("span", "fm-phase", "Ready");
    const countEl = el("span", "fm-count");
    const meta = el("div", "fm-meta"); meta.append(phaseEl, countEl);
    const prog = el("i"); const bar = el("div", "fm-bar"); bar.appendChild(prog);
    const cue = el("div", "fm-cue"); cue.setAttribute("aria-live", "polite");

    const playBtn = el("button", "btn primary", "Start");
    const resetBtn = el("button", "btn", "Reset");
    const sideBtn = el("button", "btn sm active", "Side");
    const frontBtn = el("button", "btn sm", "Front");
    if (!ex.views.front) frontBtn.disabled = true;
    if (!ex.views.side) { sideBtn.classList.remove("active"); frontBtn.classList.add("active"); sideBtn.disabled = true; }
    const tempoNorm = el("button", "btn sm active", "Normal");
    const tempoSlow = el("button", "btn sm", "Slow");
    const staticBtn = el("button", "btn sm", staticMode ? "Show animation" : "Static view");

    const row1 = el("div", "fm-controls"); row1.append(playBtn, resetBtn, el("div", "fm-spring"), sideBtn, frontBtn);
    const row2 = el("div", "fm-controls"); row2.append(tempoNorm, tempoSlow, el("div", "fm-spring"), staticBtn);

    const rpe = el("div", "fm-rpe");
    const staticWrap = el("div", "fm-static hidden");

    const anim = el("div"); anim.append(stage, meta, bar, cue, row1, row2, rpe);
    host.append(anim, staticWrap);

    // ---- persistent SVG scene (built once; attributes updated per frame) ----
    const mk = (tag, attrs) => { const n = document.createElementNS(SVGNS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };
    svg.innerHTML =
      `<defs>` +
      `<radialGradient id="${uid}-glow" cx="50%" cy="44%" r="58%">` +
      `<stop offset="0%" stop-color="var(--accent)" stop-opacity="0.22"/>` +
      `<stop offset="70%" stop-color="var(--accent)" stop-opacity="0.05"/>` +
      `<stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/></radialGradient>` +
      `<filter id="${uid}-soft" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="5"/></filter>` +
      `</defs>`;
    const glowEll = mk("ellipse", { cx: 120, cy: 150, rx: 116, ry: 150, fill: `url(#${uid}-glow)`, class: "fm-glow" });
    const groundLine = mk("line", { x1: 40, y1: GROUND_Y, x2: 200, y2: GROUND_Y, class: "fm-ground" });
    const shadowEll = mk("ellipse", { cx: 120, cy: GROUND_Y + 9, rx: 46, ry: 9, class: "fm-shadow", filter: `url(#${uid}-soft)` });
    const objGroup = mk("g", { class: "fm-object" });
    const figGroup = mk("g", { class: "fm-figure" });
    svg.append(glowEll, groundLine, shadowEll, objGroup, figGroup);

    let segNodes = [], headOutline = null, headRing = null;
    function buildFigure() {
      figGroup.textContent = "";
      const of = objFn();
      objGroup.innerHTML = of ? of() : "";
      segNodes = SEG[view].map(([a, b]) => ({ a, b, outline: mk("line", { class: "fm-bone-outline" }), core: mk("line", { class: "fm-bone" }) }));
      segNodes.forEach((s) => figGroup.appendChild(s.outline));   // outlines under...
      segNodes.forEach((s) => figGroup.appendChild(s.core));      // ...cores
      headOutline = mk("circle", { r: 18, class: "fm-head-outline" });
      headRing = mk("circle", { r: 16, class: "fm-head" });
      figGroup.append(headOutline, headRing);
    }

    function drawPose(p) {
      for (const s of segNodes) {
        const a = p[s.a], b = p[s.b];
        if (a && b) {
          for (const n of [s.outline, s.core]) {
            n.setAttribute("x1", a[0]); n.setAttribute("y1", a[1]); n.setAttribute("x2", b[0]); n.setAttribute("y2", b[1]);
            n.style.display = "";
          }
        } else { s.outline.style.display = "none"; s.core.style.display = "none"; }
      }
      if (p.head) {
        for (const n of [headOutline, headRing]) { n.setAttribute("cx", p.head[0]); n.setAttribute("cy", p.head[1]); n.style.display = ""; }
      } else { headOutline.style.display = "none"; headRing.style.display = "none"; }
      // Ground shadow tracks the hips and softens/widens as the figure lowers.
      const hx = p.hip ? p.hip[0] : 120, hy = p.hip ? p.hip[1] : 190;
      shadowEll.setAttribute("cx", hx.toFixed(1));
      shadowEll.setAttribute("rx", clamp(40 + (hy - 178) * 0.16, 36, 60).toFixed(1));
    }

    function setGlow(o) { glowEll.style.opacity = o; }
    function showRest() { drawPose(poses()[restPoseName()]); }
    function showPhaseText(name) { phaseEl.textContent = name; if (ex.cues && ex.cues[name]) cue.innerHTML = ex.cues[name]; }

    function frame(ts) {
      if (!playing || destroyed) return;
      if (!svg.isConnected) { playing = false; return; }  // view replaced — stop the loop
      const ph = ex.phases[phaseIdx];
      const dur = ph.dur * (ph.isHold ? 1 : tempoScale);
      if (!phaseStart) phaseStart = ts;
      let t = (ts - phaseStart) / dur; if (t > 1) t = 1;
      const P = poses();
      drawPose(lerpPose(P[ph.from] || P[restPoseName()], P[ph.to] || P[restPoseName()], ease(t)));
      prog.style.width = (t * 100).toFixed(1) + "%";
      if (ph.isHold) {
        const elapsed = ts - phaseStart;
        const left = Math.ceil((dur - elapsed) / 1000);
        countEl.textContent = left > 0 ? left + "s hold" : "";
        setGlow((0.55 + 0.35 * Math.sin(elapsed / 650)).toFixed(3));  // calm breathing pulse
      } else {
        setGlow(0.7);
      }
      if (t >= 1) {
        phaseStart = 0; phaseIdx++;
        if (phaseIdx >= ex.phases.length) {
          phaseIdx = 0;
          if (ex.targetReps) {
            reps++; countEl.textContent = reps + " / " + ex.targetReps;
            if (reps >= ex.targetReps) return finishSet();
          } else return finishSet();
        }
        showPhaseText(ex.phases[phaseIdx].name);
      }
      raf = requestAnimationFrame(frame);
    }

    function start() {
      if (staticMode) return;
      playing = true; playBtn.textContent = "Pause"; rpe.classList.remove("show");
      if (!ex.targetReps) countEl.textContent = "";
      setGlow(0.7);
      showPhaseText(ex.phases[phaseIdx].name);
      raf = requestAnimationFrame(frame);
    }
    function pause() { playing = false; playBtn.textContent = "Resume"; if (raf) cancelAnimationFrame(raf); }
    function finishSet() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      playBtn.textContent = "Start"; phaseEl.textContent = "Done"; cue.innerHTML = "Nice work."; prog.style.width = "100%";
      setGlow(0.9);
      buildRpe();
    }
    function reset() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      phaseIdx = 0; phaseStart = 0; reps = 0;
      playBtn.textContent = "Start"; phaseEl.textContent = "Ready"; cue.innerHTML = "";
      prog.style.width = "0%"; rpe.classList.remove("show"); rpe.innerHTML = "";
      countEl.textContent = ex.targetReps ? "0 / " + ex.targetReps : "";
      setGlow(0.32);
      showRest();
    }

    function buildRpe() {
      rpe.classList.add("show");
      let h = `<div class="fm-rpe-q">Set done. How hard was that?</div>` +
        `<div class="fm-note">0 = could talk easily · 10 = could not say a word</div><div class="fm-scale">`;
      for (let i = 0; i <= 10; i++) h += `<button class="btn sm" data-v="${i}">${i}</button>`;
      rpe.innerHTML = h + "</div>";
      rpe.querySelector(".fm-scale").addEventListener("click", (e) => {
        const b = e.target.closest("button"); if (!b) return;
        rpe.innerHTML = `<div class="fm-rpe-q">Logged effort: ${b.dataset.v}/10</div>` +
          `<div class="fm-note">Feeds autoregulation: it nudges reps, tempo, or object load next time.</div>`;
        if (onFinish) onFinish(Number(b.dataset.v));
      });
    }

    // ---- static fallback (reduced motion / opt-in) ----
    function renderStatic() {
      const v = ex.views.side ? "side" : "front";
      const P = ex.views[v];
      const mid = Object.keys(P).find((k) => k !== restPoseName()) || Object.keys(P)[0];
      const seq = [P[restPoseName()], P[mid], P[restPoseName()]];
      const labels = ex.staticLabels || (ex.targetReps ? ["Start", "Bottom", "Return"] : ["Stand", "Hold", "Stand"]);
      const of = glyph((ex.object && ex.object[v]) || null);
      const mini = (p) => `<svg viewBox="0 0 240 340" role="img" aria-label="Key pose">${markup(p, v, of)}</svg>`;
      staticWrap.innerHTML =
        `<div class="fm-triptych">` + seq.map((p, i) => `<figure>${mini(p)}<figcaption>${labels[i]}</figcaption></figure>`).join("") + `</div>` +
        `<ol class="fm-cues">` + (ex.staticCues || []).map((c) => `<li>${c}</li>`).join("") + `</ol>`;
    }
    function applyStatic(on) {
      staticMode = on;
      anim.classList.toggle("hidden", on);
      staticWrap.classList.toggle("hidden", !on);
      staticBtn.textContent = on ? "Show animation" : "Static view";
      if (on) { pause(); renderStatic(); } else { reset(); }
    }

    function setView(v) {
      if (v === "front" && !ex.views.front) return;
      if (v === "side" && !ex.views.side) return;
      view = v;
      sideBtn.classList.toggle("active", v === "side");
      frontBtn.classList.toggle("active", v === "front");
      buildFigure();              // rebuild nodes for the new view's skeleton
      if (!playing) showRest();   // a running set keeps going, drawing into new nodes
    }
    function setTempo(slow) {
      tempoScale = slow ? 1.6 : 1;
      tempoNorm.classList.toggle("active", !slow);
      tempoSlow.classList.toggle("active", slow);
    }

    playBtn.onclick = () => (playing ? pause() : start());
    resetBtn.onclick = reset;
    sideBtn.onclick = () => setView("side");
    frontBtn.onclick = () => setView("front");
    tempoNorm.onclick = () => setTempo(false);
    tempoSlow.onclick = () => setTempo(true);
    staticBtn.onclick = () => applyStatic(!staticMode);

    buildFigure();
    reset();
    applyStatic(staticMode);

    return {
      destroy() { destroyed = true; if (raf) cancelAnimationFrame(raf); host.innerHTML = ""; },
      start, reset,
    };
  }

  return { create };
})();

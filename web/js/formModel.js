/* Form-model engine for "Sports at Home": tempo-paced SVG figures with the
   object drawn in place, so the user copies the setup, not just the pose. The
   figure doubles as the pacer/metronome. Offline, dependency-free, themed from
   the app's CSS tokens, and accessible (respects prefers-reduced-motion with a
   static key-pose fallback).

   Data-driven by design: the engine renders any exercise supplied as data
   (web/content/home/exercises.json) — object glyphs are the only thing kept in
   code (a small registry). Add exercises to the JSON; no engine change needed.

   FormModel.create(hostEl, exercise, { onFinish }) -> { destroy } */
const FormModel = (() => {
  const SVGNS = "http://www.w3.org/2000/svg";
  const GROUND_Y = 318;
  const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

  // ---- object glyphs (drawn in place, tracking the body) ----
  const OBJECTS = {
    chair: () =>
      `<g class="fm-obj-fill"><rect x="140" y="232" width="60" height="10" rx="2"/></g>` +
      `<g class="fm-obj"><line x1="144" y1="242" x2="144" y2="312"/><line x1="196" y1="242" x2="196" y2="312"/>` +
      `<line x1="196" y1="232" x2="196" y2="168"/><line x1="196" y1="180" x2="178" y2="180"/></g>`,
    wall: () =>
      `<g class="fm-obj"><line x1="82" y1="40" x2="82" y2="${GROUND_Y}"/></g>` +
      `<g class="fm-obj-fill"><rect x="74" y="40" width="8" height="${GROUND_Y - 40}" rx="2"/></g>`,
  };
  const glyph = (id) => (id && OBJECTS[id] ? OBJECTS[id] : null);

  function lerpPose(a, b, t) {
    const out = {};
    for (const k in a) if (b[k]) out[k] = [a[k][0] + (b[k][0] - a[k][0]) * t, a[k][1] + (b[k][1] - a[k][1]) * t];
    return out;
  }
  const boneSVG = (a, b) => `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" class="fm-bone"/>`;

  function figureSVG(p, view, objFn) {
    let s = `<line class="fm-ground" x1="40" y1="${GROUND_Y}" x2="200" y2="${GROUND_Y}"/>`;
    if (objFn) s += objFn();
    if (view === "front") {
      s += boneSVG(p.hip, p.lknee) + boneSVG(p.lknee, p.lankle) +
        boneSVG(p.hip, p.rknee) + boneSVG(p.rknee, p.rankle) + boneSVG(p.hip, p.sh) +
        boneSVG(p.sh, p.lelb) + boneSVG(p.lelb, p.lhand) + boneSVG(p.sh, p.relb) + boneSVG(p.relb, p.rhand);
    } else {
      s += boneSVG(p.ankle, p.toe) + boneSVG(p.ankle, p.knee) + boneSVG(p.knee, p.hip) +
        boneSVG(p.hip, p.sh) + boneSVG(p.sh, p.elb) + boneSVG(p.elb, p.hand);
    }
    s += `<circle cx="${p.head[0]}" cy="${p.head[1]}" r="16" class="fm-head"/>`;
    return s;
  }

  function create(host, ex, opts = {}) {
    const onFinish = opts.onFinish || null;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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
    const stage = el("div", "fm-stage"); stage.appendChild(svg);

    const phaseEl = el("span", "fm-phase", "Ready");
    const countEl = el("span", "fm-count");
    const meta = el("div", "fm-meta"); meta.append(phaseEl, countEl);
    const prog = el("i"); const bar = el("div", "fm-bar"); bar.appendChild(prog);
    const cue = el("div", "fm-cue");
    cue.setAttribute("aria-live", "polite");

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

    const rpe = el("div", "fm-rpe"); // shown on finish
    const staticWrap = el("div", "fm-static hidden");

    const anim = el("div"); anim.append(stage, meta, bar, cue, row1, row2, rpe);
    host.append(anim, staticWrap);

    // ---- rendering ----
    function draw(p) { svg.innerHTML = figureSVG(p, view, objFn()); }
    function showRest() { draw(poses()[restPoseName()]); }
    function showPhaseText(name) { phaseEl.textContent = name; if (ex.cues && ex.cues[name]) cue.innerHTML = ex.cues[name]; }

    function frame(ts) {
      if (!playing || destroyed) return;
      if (!svg.isConnected) { playing = false; return; }  // view was replaced — stop the loop
      const ph = ex.phases[phaseIdx];
      const dur = ph.dur * (ph.isHold ? 1 : tempoScale);
      if (!phaseStart) phaseStart = ts;
      let t = (ts - phaseStart) / dur; if (t > 1) t = 1;
      const P = poses();
      draw(lerpPose(P[ph.from] || P[restPoseName()], P[ph.to] || P[restPoseName()], ease(t)));
      prog.style.width = (t * 100).toFixed(1) + "%";
      if (ph.isHold) { const left = Math.ceil((dur - (ts - phaseStart)) / 1000); countEl.textContent = left > 0 ? left + "s hold" : ""; }
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
      showPhaseText(ex.phases[phaseIdx].name);
      raf = requestAnimationFrame(frame);
    }
    function pause() { playing = false; playBtn.textContent = "Resume"; if (raf) cancelAnimationFrame(raf); }
    function finishSet() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      playBtn.textContent = "Start"; phaseEl.textContent = "Done"; cue.innerHTML = "Nice work."; prog.style.width = "100%";
      buildRpe();
    }
    function reset() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      phaseIdx = 0; phaseStart = 0; reps = 0;
      playBtn.textContent = "Start"; phaseEl.textContent = "Ready"; cue.innerHTML = "";
      prog.style.width = "0%"; rpe.classList.remove("show"); rpe.innerHTML = "";
      countEl.textContent = ex.targetReps ? "0 / " + ex.targetReps : "";
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
      const P = ex.views.side || ex.views.front;
      const keys = Object.keys(P);
      const mid = keys.find((k) => k !== restPoseName()) || keys[0];
      const seq = [P[restPoseName()], P[mid], P[restPoseName()]];
      const labels = ex.staticLabels ||
        (ex.targetReps ? ["Start", "Bottom", "Return"] : ["Stand", "Hold", "Stand"]);
      const v = ex.views.side ? "side" : "front";
      const mini = (p) => `<svg viewBox="0 0 240 340" role="img" aria-label="Key pose">${figureSVG(p, v, glyph((ex.object && ex.object[v]) || null))}</svg>`;
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
      if (!playing) showRest();
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

    reset();
    applyStatic(staticMode);

    return {
      destroy() { destroyed = true; if (raf) cancelAnimationFrame(raf); host.innerHTML = ""; },
      start, reset,
    };
  }

  return { create };
})();

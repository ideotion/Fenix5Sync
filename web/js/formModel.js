/* Form-model engine: tempo-paced SVG figures with the object drawn in place, so
   the user copies the setup, not just the pose. The figure doubles as the
   pacer/metronome. A shared component (Sports at Home + Tai Chi). Offline,
   dependency-free, themed from CSS tokens, accessible (reduced-motion safe).

   Rendering is built once and updated by attribute per frame (60fps). Optional
   "wow" layers — all user-toggleable and persisted, so each person tunes it to
   taste:
     • Motion trails  — accent onion-skin echoes of recent poses.
     • Breath ring    — a soft ring that pulses a calm breathing rhythm.
     • Depth shading  — a top-lit gradient down the limbs.
     • Sound          — Web Audio cues (phase, breath, rep/hold/finish); opt-in.
   The static key-pose fallback (reduced motion) is always available.

   FormModel.create(hostEl, exercise, { onFinish }) -> { destroy } */
const FormModel = (() => {
  const SVGNS = "http://www.w3.org/2000/svg";
  const GROUND_Y = 318;
  let _seq = 0;

  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // ---- shared, persisted preferences ----
  const PREF_KEY = "f5s-fm-prefs";
  const DEFAULTS = { trails: true, ring: true, shading: true, sound: false, figure: "minimal" };
  const FIGURES = [["minimal", "Minimal"], ["cartoon", "Cartoon"]];
  function loadPrefs() {
    try { return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(PREF_KEY)) || {}); }
    catch (_) { return Object.assign({}, DEFAULTS); }
  }
  function savePrefs(p) { try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (_) {} }
  const prefs = loadPrefs();

  // ---- tiny Web Audio synth (created lazily on a user gesture) ----
  // One sound "type" per visual theme: the dark theme gets a warm sine timbre,
  // the light theme a brighter triangle timbre (with its own frequency set). The
  // active theme is read at cue time, so sound follows the theme toggle live.
  const PALETTES = {
    dark: {  // "Warm"
      type: "sine", gain: 0.06,
      breathUp: [330, 494], breathDown: [277, 196],
      tick: 587, second: 440, rep: 660, finishA: 587, finishB: 784,
    },
    light: {  // "Bright"
      type: "triangle", gain: 0.045,
      breathUp: [523, 784], breathDown: [392, 294],
      tick: 988, second: 740, rep: 1047, finishA: 784, finishB: 1175,
    },
  };
  const palette = () => PALETTES[document.documentElement.getAttribute("data-theme")] || PALETTES.dark;

  const Audio = (() => {
    let ctx = null;
    function ensure() {
      if (ctx) return ctx;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) ctx = new AC();
      return ctx;
    }
    function tone(freq, dur, { gain, type, glideTo = null } = {}) {
      if (!prefs.sound) return;
      const c = ensure(); if (!c) return;
      if (c.state === "suspended") c.resume();
      const pal = palette();
      const t0 = c.currentTime;
      const osc = c.createOscillator(); const g = c.createGain();
      osc.type = type || pal.type;
      osc.frequency.setValueAtTime(freq, t0);
      if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(gain != null ? gain : pal.gain, t0 + 0.012);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      osc.connect(g); g.connect(c.destination);
      osc.start(t0); osc.stop(t0 + dur + 0.02);
    }
    return {
      resume() { const c = ensure(); if (c && c.state === "suspended") c.resume(); },
      breath(up) { const p = palette(); const f = up ? p.breathUp : p.breathDown; tone(f[0], 0.5, { glideTo: f[1] }); },
      tick() { tone(palette().tick, 0.05, { gain: palette().gain * 0.7 }); },
      secondTick() { tone(palette().second, 0.04, { gain: palette().gain * 0.55 }); },
      rep() { tone(palette().rep, 0.09); },
      finish() { const p = palette(); tone(p.finishA, 0.14); setTimeout(() => tone(p.finishB, 0.22), 130); },
    };
  })();

  const SEG = {
    side: [["ankle", "toe"], ["ankle", "knee"], ["knee", "hip"], ["hip", "sh"], ["sh", "elb"], ["elb", "hand"]],
    front: [["hip", "lknee"], ["lknee", "lankle"], ["hip", "rknee"], ["rknee", "rankle"],
      ["hip", "sh"], ["sh", "lelb"], ["lelb", "lhand"], ["sh", "relb"], ["relb", "rhand"]],
  };

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
    const GHOSTS = 3, GHOST_GAP = 4;  // onion-skin depth + frame spacing

    let view = ex.views.front && !ex.views.side ? "front" : "side";
    let tempoScale = 1, raf = null, phaseIdx = 0, phaseStart = 0, reps = 0;
    let playing = false, staticMode = reduceMotion, destroyed = false;
    let history = [], lastSecond = -1;

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

    // Display & sound preferences (shared + persisted).
    const prefsPanel = el("details", "fm-prefs");
    const prefDefs = [
      ["trails", "Motion trails"], ["ring", "Breath ring"], ["shading", "Depth shading"], ["sound", "Sound"],
    ];
    prefsPanel.innerHTML = `<summary>Display &amp; sound</summary>`;

    // Figure style ("theme list") — Minimal stick figure or a Cartoon avatar.
    const figRow = el("div", "fm-pref-row");
    const figWrap = el("label", "fm-pref");
    const figSel = el("select");
    FIGURES.forEach(([v, label]) => { const o = el("option"); o.value = v; o.textContent = label; figSel.appendChild(o); });
    figSel.value = prefs.figure;
    figSel.addEventListener("change", () => { prefs.figure = figSel.value; savePrefs(prefs); applyPref("figure"); });
    figWrap.append(document.createTextNode("Figure "), figSel);
    figRow.appendChild(figWrap);
    prefsPanel.appendChild(figRow);

    const prefRow = el("div", "fm-pref-row");
    prefDefs.forEach(([key, label]) => {
      const id = `${uid}-${key}`;
      const wrap = el("label", "fm-pref");
      const input = el("input"); input.type = "checkbox"; input.id = id; input.checked = !!prefs[key];
      input.addEventListener("change", () => {
        prefs[key] = input.checked; savePrefs(prefs);
        if (key === "sound" && input.checked) Audio.resume();
        applyPref(key);
      });
      wrap.append(input, document.createTextNode(" " + label));
      prefRow.appendChild(wrap);
    });
    prefsPanel.appendChild(prefRow);

    const rpe = el("div", "fm-rpe");
    const staticWrap = el("div", "fm-static hidden");

    const anim = el("div"); anim.append(stage, meta, bar, cue, row1, row2, prefsPanel, rpe);
    host.append(anim, staticWrap);

    // ---- persistent SVG scene ----
    const mk = (tag, attrs) => { const n = document.createElementNS(SVGNS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };
    svg.innerHTML =
      `<defs>` +
      `<radialGradient id="${uid}-glow" cx="50%" cy="44%" r="58%">` +
      `<stop offset="0%" stop-color="var(--accent)" stop-opacity="0.22"/>` +
      `<stop offset="70%" stop-color="var(--accent)" stop-opacity="0.05"/>` +
      `<stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/></radialGradient>` +
      `<linearGradient id="${uid}-limb" gradientUnits="userSpaceOnUse" x1="0" y1="56" x2="0" y2="330">` +
      `<stop offset="0%" stop-color="var(--text)" stop-opacity="1"/>` +
      `<stop offset="100%" stop-color="var(--text)" stop-opacity="0.66"/></linearGradient>` +
      `<filter id="${uid}-soft" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="5"/></filter>` +
      `</defs>`;
    const glowEll = mk("ellipse", { cx: 120, cy: 150, rx: 116, ry: 150, fill: `url(#${uid}-glow)`, class: "fm-glow" });
    const groundLine = mk("line", { x1: 40, y1: GROUND_Y, x2: 200, y2: GROUND_Y, class: "fm-ground" });
    const shadowEll = mk("ellipse", { cx: 120, cy: GROUND_Y + 9, rx: 46, ry: 9, class: "fm-shadow", filter: `url(#${uid}-soft)` });
    const breathRing = mk("circle", { cx: 120, cy: 150, r: 74, class: "fm-breath" });
    const ghostsGroup = mk("g", { class: "fm-ghosts" });
    const objGroup = mk("g", { class: "fm-object" });
    const figGroup = mk("g", { class: "fm-figure" });
    svg.append(glowEll, breathRing, groundLine, shadowEll, ghostsGroup, objGroup, figGroup);

    let segNodes = [], headOutline = null, headRing = null, ghostNodes = [], faceNodes = null;

    function applyLines(lines, p) {
      SEG[view].forEach(([a, b], i) => {
        const pa = p[a], pb = p[b], ln = lines[i];
        if (pa && pb) { ln.setAttribute("x1", pa[0]); ln.setAttribute("y1", pa[1]); ln.setAttribute("x2", pb[0]); ln.setAttribute("y2", pb[1]); ln.style.display = ""; }
        else ln.style.display = "none";
      });
    }

    function buildFigure() {
      figGroup.textContent = ""; ghostsGroup.textContent = ""; ghostNodes = [];
      objGroup.innerHTML = (objFn() || (() => ""))();

      // Onion-skin ghost layers (core-only), drawn behind the figure.
      if (prefs.trails) {
        for (let k = 0; k < GHOSTS; k++) {
          const g = mk("g", { class: "fm-ghost", opacity: (0.20 - k * 0.05).toFixed(2) });
          const lines = SEG[view].map(() => { const l = mk("line", { class: "fm-ghost-bone" }); g.appendChild(l); return l; });
          ghostsGroup.appendChild(g); ghostNodes.push(lines);
        }
      }
      const cartoon = prefs.figure === "cartoon";
      segNodes = SEG[view].map(() => ({
        outline: mk("line", { class: cartoon ? "fm-cartoon-outline" : "fm-bone-outline" }),
        core: mk("line", { class: cartoon ? "fm-cartoon-bone" : "fm-bone" }),
      }));
      segNodes.forEach((s) => figGroup.appendChild(s.outline));
      segNodes.forEach((s) => { applyShadingTo(s.core); figGroup.appendChild(s.core); });
      if (cartoon) {
        headOutline = mk("circle", { r: 22, class: "fm-cartoon-headout" });  // collar/outline
        headRing = mk("circle", { r: 21, class: "fm-cartoon-head" });
        faceNodes = {
          eyeL: mk("circle", { r: 2.6, class: "fm-cartoon-eye" }),
          eyeR: mk("circle", { r: 2.6, class: "fm-cartoon-eye" }),
          mouth: mk("path", { class: "fm-cartoon-mouth" }),
        };
        figGroup.append(headOutline, headRing, faceNodes.mouth, faceNodes.eyeL, faceNodes.eyeR);
      } else {
        faceNodes = null;
        headOutline = mk("circle", { r: 18, class: "fm-head-outline" });
        headRing = mk("circle", { r: 16, class: "fm-head" });
        figGroup.append(headOutline, headRing);
      }
    }

    function applyShadingTo(coreLine) {
      // Depth gradient only applies to the minimal figure; the cartoon avatar
      // keeps its own flat fill colour.
      if (prefs.shading && prefs.figure === "minimal") coreLine.setAttribute("stroke", `url(#${uid}-limb)`);
      else coreLine.removeAttribute("stroke");
    }

    function drawPose(p) {
      applyLines(segNodes.map((s) => s.outline), p);
      applyLines(segNodes.map((s) => s.core), p);
      if (p.head) {
        const hx = p.head[0], hy = p.head[1];
        headOutline.setAttribute("cx", hx); headOutline.setAttribute("cy", hy); headOutline.style.display = "";
        headRing.setAttribute("cx", hx); headRing.setAttribute("cy", hy); headRing.style.display = "";
        if (faceNodes) {
          if (view === "front") {
            faceNodes.eyeL.setAttribute("cx", hx - 7); faceNodes.eyeL.setAttribute("cy", hy - 3);
            faceNodes.eyeR.setAttribute("cx", hx + 7); faceNodes.eyeR.setAttribute("cy", hy - 3);
            faceNodes.eyeR.style.display = "";
            faceNodes.mouth.setAttribute("d", `M ${hx - 7} ${hy + 6} Q ${hx} ${hy + 12} ${hx + 7} ${hy + 6}`);
          } else {  // side view — face looks forward (+x)
            faceNodes.eyeL.setAttribute("cx", hx + 6); faceNodes.eyeL.setAttribute("cy", hy - 3);
            faceNodes.eyeR.style.display = "none";
            faceNodes.mouth.setAttribute("d", `M ${hx + 2} ${hy + 7} Q ${hx + 9} ${hy + 11} ${hx + 13} ${hy + 5}`);
          }
          faceNodes.eyeL.style.display = ""; faceNodes.mouth.style.display = "";
        }
      } else {
        headOutline.style.display = "none"; headRing.style.display = "none";
        if (faceNodes) { faceNodes.eyeL.style.display = "none"; faceNodes.eyeR.style.display = "none"; faceNodes.mouth.style.display = "none"; }
      }
      const hx = p.hip ? p.hip[0] : 120, hy = p.hip ? p.hip[1] : 190;
      shadowEll.setAttribute("cx", hx.toFixed(1));
      shadowEll.setAttribute("rx", clamp(40 + (hy - 178) * 0.16, 36, 60).toFixed(1));
    }

    function updateGhosts() {
      if (!ghostNodes.length) return;
      for (let k = 0; k < ghostNodes.length; k++) {
        const idx = history.length - 1 - (k + 1) * GHOST_GAP;
        if (idx >= 0) { applyLines(ghostNodes[k], history[idx]); }
        else ghostNodes[k].forEach((l) => (l.style.display = "none"));
      }
    }

    const setGlow = (o) => { glowEll.style.opacity = o; };
    function showRest() { history = []; drawPose(poses()[restPoseName()]); updateGhosts(); }
    function showPhaseText(name) { phaseEl.textContent = name; if (ex.cues && ex.cues[name]) cue.innerHTML = ex.cues[name]; }

    function frame(ts) {
      if (!playing || destroyed) return;
      if (!svg.isConnected) { playing = false; return; }
      const ph = ex.phases[phaseIdx];
      const dur = ph.dur * (ph.isHold ? 1 : tempoScale);
      if (!phaseStart) phaseStart = ts;
      const elapsed = ts - phaseStart;
      let t = elapsed / dur; if (t > 1) t = 1;
      const P = poses();
      const cp = lerpPose(P[ph.from] || P[restPoseName()], P[ph.to] || P[restPoseName()], ease(t));
      drawPose(cp);
      history.push(cp); if (history.length > (GHOSTS + 1) * GHOST_GAP + 2) history.shift();
      updateGhosts();
      prog.style.width = (t * 100).toFixed(1) + "%";

      // Breath ring: a calm ~11 breaths/min pulse while moving.
      if (prefs.ring) { breathRing.style.display = ""; breathRing.setAttribute("r", (74 + 9 * Math.sin(ts / 875)).toFixed(1)); }
      else breathRing.style.display = "none";

      if (ph.isHold) {
        const left = Math.ceil((dur - elapsed) / 1000);
        countEl.textContent = left > 0 ? left + "s hold" : "";
        setGlow((0.55 + 0.35 * Math.sin(elapsed / 650)).toFixed(3));
        const sec = Math.floor(elapsed / 1000);
        if (sec !== lastSecond) { lastSecond = sec; if (sec > 0) Audio.secondTick(); }
      } else { setGlow(0.7); }

      if (t >= 1) {
        phaseStart = 0; phaseIdx++;
        if (phaseIdx >= ex.phases.length) {
          phaseIdx = 0;
          if (ex.targetReps) {
            reps++; countEl.textContent = reps + " / " + ex.targetReps; Audio.rep();
            if (reps >= ex.targetReps) return finishSet();
          } else return finishSet();
        }
        announcePhase(ex.phases[phaseIdx]);
      }
      raf = requestAnimationFrame(frame);
    }

    function announcePhase(ph) {
      showPhaseText(ph.name);
      lastSecond = -1;
      if (ph.isHold) { Audio.tick(); return; }
      // Pitch the cue by direction: head rising = inhale/up, falling = exhale/down.
      const P = poses();
      const from = P[ph.from] || {}, to = P[ph.to] || {};
      if (from.head && to.head) Audio.breath(to.head[1] < from.head[1]);
      else Audio.tick();
    }

    function start() {
      if (staticMode) return;
      Audio.resume();
      playing = true; playBtn.textContent = "Pause"; rpe.classList.remove("show");
      if (!ex.targetReps) countEl.textContent = "";
      setGlow(0.7); history = []; lastSecond = -1;
      announcePhase(ex.phases[phaseIdx]);
      raf = requestAnimationFrame(frame);
    }
    function pause() { playing = false; playBtn.textContent = "Resume"; if (raf) cancelAnimationFrame(raf); }
    function finishSet() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      playBtn.textContent = "Start"; phaseEl.textContent = "Done"; cue.innerHTML = "Nice work."; prog.style.width = "100%";
      setGlow(0.9); breathRing.style.display = "none"; Audio.finish();
      buildRpe();
    }
    function reset() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      phaseIdx = 0; phaseStart = 0; reps = 0; history = []; lastSecond = -1;
      playBtn.textContent = "Start"; phaseEl.textContent = "Ready"; cue.innerHTML = "";
      prog.style.width = "0%"; rpe.classList.remove("show"); rpe.innerHTML = "";
      countEl.textContent = ex.targetReps ? "0 / " + ex.targetReps : "";
      setGlow(0.32); breathRing.style.display = "none";
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

    // Live-apply a changed preference without losing place.
    function applyPref(key) {
      if (key === "trails" || key === "figure") { buildFigure(); if (!playing) showRest(); }
      else if (key === "shading") { segNodes.forEach((s) => applyShadingTo(s.core)); }
      else if (key === "ring" && !playing) { breathRing.style.display = "none"; }
    }

    function setView(v) {
      if ((v === "front" && !ex.views.front) || (v === "side" && !ex.views.side)) return;
      view = v;
      sideBtn.classList.toggle("active", v === "side");
      frontBtn.classList.toggle("active", v === "front");
      buildFigure();
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

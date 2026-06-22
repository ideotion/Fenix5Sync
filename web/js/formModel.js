/* Form-model engine: tempo-paced SVG figures with the object drawn in place, so
   the user copies the setup, not just the pose. The figure doubles as the
   pacer/metronome. A shared component (Sports at Home + Tai Chi). Offline,
   dependency-free, themed from CSS tokens, accessible (reduced-motion safe).

   Rendering is built once and updated by attribute per frame (60fps). Every
   joint is run through a pseudo-3-D yaw projection (web/js/formGeom.js) before
   it is drawn, so authored depth (z) will turn the figure for real; with today's
   flat (z=0) poses the projection is the identity at yaw 0, i.e. fully
   back-compatible. A gentle auto-yaw and a manual turn slider give a subtle 3-D
   feel now; a mirror/face control flips left/right (fixing foot facing).

   Optional, user-toggleable, persisted "wow" layers:
     • Motion trails  — accent onion-skin echoes of recent poses.
     • Breath ring    — a soft ring that pulses a calm breathing rhythm.
     • Depth shading  — a top-/front-lit gradient down the limbs.
     • Sound          — Web Audio cues (phase, breath, rep/hold/finish); opt-in.
   The static key-pose fallback (reduced motion) is always available.

   FormModel.create(hostEl, exercise, { onFinish }) -> { destroy } */
const FormModel = (() => {
  const SVGNS = "http://www.w3.org/2000/svg";
  const GROUND_Y = 318;
  const Geom = (typeof FormGeom !== "undefined") ? FormGeom : null;
  let _seq = 0;

  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const DEG = (Geom && Geom.DEG) || Math.PI / 180;

  // ---- shared, persisted preferences ----
  const PREF_KEY = "f5s-fm-prefs";
  const DEFAULTS = {
    trails: true, ring: true, shading: true, sound: false,
    figure: "minimal", character: "neutral",
    mirror: false, autoYaw: false, yaw: 0,
  };
  const FIGURES = [["minimal", "Minimal"], ["cartoon", "Cartoon"]];
  const CHARACTERS = [["neutral", "Neutral"], ["female", "Female"], ["male", "Male"]];
  const YAW_AMP = 15 * DEG;        // gentle auto-turn amplitude (~+/-15 degrees)
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

  // Side view grows a foot wedge: ankle->heel (back), heel->toe (sole) plus the
  // existing ankle->toe (front). The heel is synthesized each frame from
  // ankle+toe (FormGeom.heel), so the toe always leads the facing direction.
  const SEG = {
    side: [["ankle", "toe"], ["ankle", "heel"], ["heel", "toe"], ["ankle", "knee"],
      ["knee", "hip"], ["hip", "sh"], ["sh", "elb"], ["elb", "hand"]],
    front: [["hip", "lknee"], ["lknee", "lankle"], ["hip", "rknee"], ["rknee", "rankle"],
      ["hip", "sh"], ["sh", "lelb"], ["lelb", "lhand"], ["sh", "relb"], ["relb", "rhand"]],
  };

  // Static "room" objects, drawn once as markup behind the figure.
  const OBJECTS = {
    chair: () =>
      `<g class="fm-obj-fill"><rect x="140" y="232" width="60" height="10" rx="3"/></g>` +
      `<g class="fm-obj"><line x1="144" y1="242" x2="144" y2="312"/><line x1="196" y1="242" x2="196" y2="312"/>` +
      `<line x1="196" y1="232" x2="196" y2="168"/><line x1="196" y1="180" x2="178" y2="180"/></g>`,
    wall: () =>
      `<g class="fm-obj-fill"><rect x="72" y="40" width="10" height="${GROUND_Y - 40}" rx="3"/></g>` +
      `<g class="fm-obj"><line x1="82" y1="40" x2="82" y2="${GROUND_Y}"/></g>`,
    // Countertop / heavy table edge: a high brace for supported standing work.
    counter: () =>
      `<g class="fm-obj-fill"><rect x="150" y="196" width="56" height="12" rx="3"/></g>` +
      `<g class="fm-obj"><line x1="156" y1="208" x2="156" y2="312"/><line x1="200" y1="208" x2="200" y2="312"/></g>`,
    // A single step / low stair for step-ups and stair snacks.
    step: () =>
      `<g class="fm-obj-fill"><rect x="150" y="286" width="58" height="${GROUND_Y - 286}" rx="2"/></g>` +
      `<g class="fm-obj"><line x1="150" y1="286" x2="208" y2="286"/></g>`,
  };
  // Free-weight implements track a hand each (front: both hands), drawn at the
  // projected joint via a transform so they follow the movement.
  const IMPLEMENTS = {
    dumbbell: () =>
      `<line class="fm-obj" x1="-11" y1="0" x2="11" y2="0"/>` +
      `<rect class="fm-obj-fill" x="-13" y="-7" width="5" height="14" rx="1.5"/>` +
      `<rect class="fm-obj-fill" x="8" y="-7" width="5" height="14" rx="1.5"/>`,
    kettlebell: () =>
      `<path class="fm-obj" d="M -5 -10 A 6 6 0 0 1 5 -10" fill="none"/>` +
      `<circle class="fm-obj-fill" cx="0" cy="2" r="9"/>`,
  };
  const isImplement = (id) => !!(id && IMPLEMENTS[id]);
  const glyph = (id) => (id && OBJECTS[id] ? OBJECTS[id] : null);

  function lerpPose(a, b, t) {
    const out = {};
    for (const k in a) if (b[k]) {
      const az = a[k].length > 2 ? a[k][2] : 0, bz = b[k].length > 2 ? b[k][2] : 0;
      const x = a[k][0] + (b[k][0] - a[k][0]) * t, y = a[k][1] + (b[k][1] - a[k][1]) * t;
      const z = az + (bz - az) * t;
      out[k] = (az || bz) ? [x, y, z] : [x, y];
    }
    return out;
  }

  // Project a joint to screen space (the only place yaw/depth is applied).
  function proj(coord, yaw) {
    if (!Geom) return [coord[0], coord[1]];
    return Geom.projectXY(coord, yaw);
  }

  // Static-fallback markup (reduced motion): no yaw, no implements — a calm,
  // robust key-pose diagram. New room objects render here automatically.
  function markup(p, view, objFn) {
    const withHeel = view === "side" && p.ankle && p.toe ? Object.assign({ heel: Geom ? Geom.heel(p.ankle, p.toe) : p.ankle }, p) : p;
    const line = (a, b, cls) => `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" class="${cls}"/>`;
    let s = `<line class="fm-ground" x1="40" y1="${GROUND_Y}" x2="200" y2="${GROUND_Y}"/>`;
    if (objFn) s += objFn();
    let out = "", core = "";
    for (const [a, b] of SEG[view]) if (withHeel[a] && withHeel[b]) { out += line(withHeel[a], withHeel[b], "fm-bone-outline"); core += line(withHeel[a], withHeel[b], "fm-bone"); }
    s += out + core;
    if (withHeel.head) s += `<circle cx="${withHeel.head[0]}" cy="${withHeel.head[1]}" r="18" class="fm-head-outline"/>` +
      `<circle cx="${withHeel.head[0]}" cy="${withHeel.head[1]}" r="16" class="fm-head"/>`;
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
    let history = [], lastSecond = -1, yawRad = 0;

    const poses = () => ex.views[view] || ex.views.side || ex.views.front;
    const objId = () => (ex.object && ex.object[view]) || null;
    const objFn = () => glyph(objId());
    const restPoseName = () => (poses().stand ? "stand" : Object.keys(poses())[0]);

    // Manual turn (slider) when auto-yaw is off; gentle oscillation when on.
    function yawAt(ts) {
      if (prefs.autoYaw) return playing ? YAW_AMP * Math.sin((ts || 0) / 2200) : 0;
      return (prefs.yaw || 0) * DEG;
    }

    // Add a synthesized heel to a side-view pose so the foot reads correctly.
    function withFoot(p) {
      if (view !== "side" || !Geom || !p.ankle || !p.toe) return p;
      const out = Object.assign({}, p);
      out.heel = Geom.heel(p.ankle, p.toe);
      return out;
    }

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
    const mirrorBtn = el("button", "btn sm", "Mirror");
    mirrorBtn.setAttribute("aria-pressed", prefs.mirror ? "true" : "false");
    if (prefs.mirror) mirrorBtn.classList.add("active");
    if (!ex.views.front) frontBtn.disabled = true;
    if (!ex.views.side) { sideBtn.classList.remove("active"); frontBtn.classList.add("active"); sideBtn.disabled = true; }
    const tempoNorm = el("button", "btn sm active", "Normal");
    const tempoSlow = el("button", "btn sm", "Slow");
    const staticBtn = el("button", "btn sm", staticMode ? "Show animation" : "Static view");

    const row1 = el("div", "fm-controls"); row1.append(playBtn, resetBtn, el("div", "fm-spring"), sideBtn, frontBtn, mirrorBtn);
    const row2 = el("div", "fm-controls"); row2.append(tempoNorm, tempoSlow, el("div", "fm-spring"), staticBtn);

    // Pseudo-3-D turn: a gentle auto-yaw toggle plus a manual angle slider. NOTE
    // (honest): with today's flat poses a full 90deg turn would degenerate to a
    // line, so this stays a subtle tilt; it becomes a true turn once poses carry
    // depth (z). Persisted across sessions.
    const yawRow = el("div", "fm-controls fm-3d");
    const autoWrap = el("label", "fm-pref");
    const autoYaw = el("input"); autoYaw.type = "checkbox"; autoYaw.checked = !!prefs.autoYaw;
    autoWrap.append(autoYaw, document.createTextNode(" Auto-turn (3-D)"));
    const yawWrap = el("label", "fm-pref fm-yaw");
    const yawSlider = el("input"); yawSlider.type = "range"; yawSlider.min = "-45"; yawSlider.max = "45"; yawSlider.step = "1";
    yawSlider.value = String(prefs.yaw || 0); yawSlider.disabled = !!prefs.autoYaw;
    yawSlider.setAttribute("aria-label", "Turn angle in degrees");
    yawWrap.append(document.createTextNode("Turn "), yawSlider);
    yawRow.append(autoWrap, el("div", "fm-spring"), yawWrap);

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

    const charWrap = el("label", "fm-pref");
    const charSel = el("select");
    CHARACTERS.forEach(([v, label]) => { const o = el("option"); o.value = v; o.textContent = label; charSel.appendChild(o); });
    charSel.value = prefs.character;
    charSel.addEventListener("change", () => { prefs.character = charSel.value; savePrefs(prefs); applyPref("figure"); });
    charWrap.append(document.createTextNode("Character "), charSel);
    figRow.appendChild(charWrap);
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

    const anim = el("div"); anim.append(stage, meta, bar, cue, row1, row2, yawRow, prefsPanel, rpe);
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
    // worldGroup carries the mirror/face flip; ambient layers stay centered.
    const worldGroup = mk("g", { class: "fm-world" });
    const ghostsGroup = mk("g", { class: "fm-ghosts" });
    const envGroup = mk("g", { class: "fm-object" });    // static room objects
    const implGroup = mk("g", { class: "fm-implements" }); // tracking free weights
    const figGroup = mk("g", { class: "fm-figure" });
    worldGroup.append(ghostsGroup, envGroup, implGroup, figGroup);
    svg.append(glowEll, breathRing, groundLine, shadowEll, worldGroup);

    let segNodes = [], headOutline = null, headRing = null, ghostNodes = [], faceNodes = null;
    let charNodes = null, headR = 16, implNodes = [];

    function applyLines(lines, p) {
      SEG[view].forEach(([a, b], i) => {
        const pa = p[a], pb = p[b], ln = lines[i];
        if (pa && pb) {
          const qa = proj(pa, yawRad), qb = proj(pb, yawRad);
          ln.setAttribute("x1", qa[0]); ln.setAttribute("y1", qa[1]); ln.setAttribute("x2", qb[0]); ln.setAttribute("y2", qb[1]); ln.style.display = "";
        } else ln.style.display = "none";
      });
    }

    function applyMirror() {
      worldGroup.setAttribute("transform", prefs.mirror ? "translate(240 0) scale(-1 1)" : "");
    }

    function buildFigure() {
      figGroup.textContent = ""; ghostsGroup.textContent = ""; ghostNodes = [];
      const oid = objId();
      envGroup.innerHTML = (!isImplement(oid) && OBJECTS[oid]) ? OBJECTS[oid]() : "";

      // Free-weight implements: one per tracked hand (front view: both hands).
      implGroup.textContent = ""; implNodes = [];
      if (isImplement(oid)) {
        const keys = view === "side" ? ["hand"] : ["lhand", "rhand"];
        keys.forEach((k) => { const g = mk("g", { class: "fm-impl" }); g.innerHTML = IMPLEMENTS[oid](); implGroup.appendChild(g); implNodes.push([k, g]); });
      }

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
      headR = cartoon ? 21 : 16;
      const hairFill = cartoon ? "#3a2a1a" : "var(--text)";

      // Character cues (gender is read from silhouette): a skirt + long hair for
      // female, a short hair cap for male, nothing for neutral. Hair behind the
      // head; the male cap sits over the head; the skirt drapes over the hips.
      charNodes = {};
      const back = [], front = [];
      if (prefs.character === "female") {
        charNodes.hairBack = mk("circle", { r: headR + 3, class: "fm-hair", fill: hairFill });
        charNodes.lockL = mk("ellipse", { rx: (headR * 0.5).toFixed(1), ry: (headR * 1.25).toFixed(1), class: "fm-hair", fill: hairFill });
        charNodes.lockR = mk("ellipse", { rx: (headR * 0.5).toFixed(1), ry: (headR * 1.25).toFixed(1), class: "fm-hair", fill: hairFill });
        back.push(charNodes.hairBack, charNodes.lockL, charNodes.lockR);
        if (cartoon) { charNodes.skirt = mk("path", { class: "fm-skirt" }); back.unshift(charNodes.skirt); }
      } else if (prefs.character === "male") {
        charNodes.cap = mk("path", { class: "fm-hair", fill: hairFill });
        front.push(charNodes.cap);
      }

      if (cartoon) {
        headOutline = mk("circle", { r: 22, class: "fm-cartoon-headout" });  // collar/outline
        headRing = mk("circle", { r: 21, class: "fm-cartoon-head" });
        faceNodes = {
          eyeL: mk("circle", { r: 2.6, class: "fm-cartoon-eye" }),
          eyeR: mk("circle", { r: 2.6, class: "fm-cartoon-eye" }),
          mouth: mk("path", { class: "fm-cartoon-mouth" }),
        };
      } else {
        faceNodes = null;
        headOutline = mk("circle", { r: 18, class: "fm-head-outline" });
        headRing = mk("circle", { r: 16, class: "fm-head" });
      }

      back.forEach((n) => figGroup.appendChild(n));    // skirt + female hair (behind head)
      figGroup.append(headOutline, headRing);
      front.forEach((n) => figGroup.appendChild(n));   // male hair cap (over head)
      if (faceNodes) figGroup.append(faceNodes.mouth, faceNodes.eyeL, faceNodes.eyeR);
      applyMirror();
    }

    function applyShadingTo(coreLine) {
      // Depth gradient only applies to the minimal figure; the cartoon avatar
      // keeps its own flat fill colour.
      if (prefs.shading && prefs.figure === "minimal") coreLine.setAttribute("stroke", `url(#${uid}-limb)`);
      else coreLine.removeAttribute("stroke");
    }

    function drawPose(raw) {
      const p = withFoot(raw);
      applyLines(segNodes.map((s) => s.outline), p);
      applyLines(segNodes.map((s) => s.core), p);
      // Subtle per-limb depth shading from projected z (no-op for flat poses).
      if (prefs.shading && Geom) {
        SEG[view].forEach(([a, b], i) => {
          if (p[a] && p[b]) {
            const d = (Geom.project(p[a], yawRad).depth + Geom.project(p[b], yawRad).depth) / 2;
            segNodes[i].core.setAttribute("stroke-opacity", Geom.depthShade(d).toFixed(3));
          }
        });
      }
      if (p.head) {
        const hp = proj(p.head, yawRad), hx = hp[0], hy = hp[1];
        headOutline.setAttribute("cx", hx); headOutline.setAttribute("cy", hy); headOutline.style.display = "";
        headRing.setAttribute("cx", hx); headRing.setAttribute("cy", hy); headRing.style.display = "";
        if (faceNodes) {
          if (view === "front") {
            faceNodes.eyeL.setAttribute("cx", hx - 7); faceNodes.eyeL.setAttribute("cy", hy - 3);
            faceNodes.eyeR.setAttribute("cx", hx + 7); faceNodes.eyeR.setAttribute("cy", hy - 3);
            faceNodes.eyeR.style.display = "";
            faceNodes.mouth.setAttribute("d", `M ${hx - 7} ${hy + 6} Q ${hx} ${hy + 12} ${hx + 7} ${hy + 6}`);
          } else {  // side view — face looks forward (+x); mirror flips the whole world group
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
      // Free-weight implements follow the projected hand(s).
      implNodes.forEach(([k, g]) => {
        if (p[k]) { const q = proj(p[k], yawRad); g.setAttribute("transform", `translate(${q[0].toFixed(1)} ${q[1].toFixed(1)})`); g.style.display = ""; }
        else g.style.display = "none";
      });
      const hipp = p.hip ? proj(p.hip, yawRad) : [120, 190];
      shadowEll.setAttribute("cx", hipp[0].toFixed(1));
      shadowEll.setAttribute("rx", clamp(40 + (hipp[1] - 178) * 0.16, 36, 60).toFixed(1));
      updateChar(p);
    }

    function updateChar(p) {
      if (!charNodes) return;
      const h = p.head ? proj(p.head, yawRad) : null;
      const show = (n, on) => { if (n) n.style.display = on ? "" : "none"; };
      if (charNodes.hairBack) { if (h) { charNodes.hairBack.setAttribute("cx", h[0]); charNodes.hairBack.setAttribute("cy", h[1]); } show(charNodes.hairBack, !!h); }
      if (charNodes.lockL) { if (h) { charNodes.lockL.setAttribute("cx", (h[0] - headR * 0.78).toFixed(1)); charNodes.lockL.setAttribute("cy", (h[1] + headR * 0.6).toFixed(1)); } show(charNodes.lockL, !!h); }
      if (charNodes.lockR) { if (h) { charNodes.lockR.setAttribute("cx", (h[0] + headR * 0.78).toFixed(1)); charNodes.lockR.setAttribute("cy", (h[1] + headR * 0.6).toFixed(1)); } show(charNodes.lockR, !!h); }
      if (charNodes.cap) { if (h) charNodes.cap.setAttribute("d", `M ${h[0] - headR} ${h[1] - 1} A ${headR} ${headR} 0 0 1 ${h[0] + headR} ${h[1] - 1} Z`); show(charNodes.cap, !!h); }
      if (charNodes.skirt) {
        const kneeY = p.lknee ? p.lknee[1] : (p.knee ? p.knee[1] : (p.hip ? p.hip[1] + 60 : 0));
        if (p.hip) {
          const hp = proj(p.hip, yawRad), hipx = hp[0], hyy = hp[1], thighY = (hyy + kneeY) / 2;
          charNodes.skirt.setAttribute("d", `M ${(hipx - 26).toFixed(1)} ${thighY.toFixed(1)} L ${hipx} ${(hyy - 16).toFixed(1)} L ${(hipx + 26).toFixed(1)} ${thighY.toFixed(1)} Z`);
        }
        show(charNodes.skirt, !!p.hip);
      }
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
    function showRest() { history = []; yawRad = yawAt(0); const rp = withFoot(poses()[restPoseName()]); drawPose(rp); history.push(rp); updateGhosts(); }
    function showPhaseText(name) { phaseEl.textContent = name; if (ex.cues && ex.cues[name]) cue.innerHTML = ex.cues[name]; }

    function frame(ts) {
      if (!playing || destroyed) return;
      if (!svg.isConnected) { playing = false; return; }
      yawRad = yawAt(ts);
      const ph = ex.phases[phaseIdx];
      const dur = ph.dur * (ph.isHold ? 1 : tempoScale);
      if (!phaseStart) phaseStart = ts;
      const elapsed = ts - phaseStart;
      let t = elapsed / dur; if (t > 1) t = 1;
      const P = poses();
      const cp = withFoot(lerpPose(P[ph.from] || P[restPoseName()], P[ph.to] || P[restPoseName()], ease(t)));
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
      const oid = (ex.object && ex.object[v]) || null;
      const of = isImplement(oid) ? null : glyph(oid);
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
      else if (key === "shading") { segNodes.forEach((s) => applyShadingTo(s.core)); if (!playing) showRest(); }
      else if (key === "ring" && !playing) { breathRing.style.display = "none"; }
      else if (key === "mirror") { applyMirror(); }
      else if (key === "yaw") { if (!playing) showRest(); }
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
    function setMirror(on) {
      prefs.mirror = on; savePrefs(prefs);
      mirrorBtn.classList.toggle("active", on);
      mirrorBtn.setAttribute("aria-pressed", on ? "true" : "false");
      applyMirror();
    }

    playBtn.onclick = () => (playing ? pause() : start());
    resetBtn.onclick = reset;
    sideBtn.onclick = () => setView("side");
    frontBtn.onclick = () => setView("front");
    mirrorBtn.onclick = () => setMirror(!prefs.mirror);
    tempoNorm.onclick = () => setTempo(false);
    tempoSlow.onclick = () => setTempo(true);
    staticBtn.onclick = () => applyStatic(!staticMode);
    autoYaw.addEventListener("change", () => {
      prefs.autoYaw = autoYaw.checked; savePrefs(prefs);
      yawSlider.disabled = autoYaw.checked;
      if (!playing) showRest();
    });
    yawSlider.addEventListener("input", () => {
      prefs.yaw = Number(yawSlider.value) || 0; savePrefs(prefs);
      applyPref("yaw");
    });

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

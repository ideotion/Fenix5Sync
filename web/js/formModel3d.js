/* formModel3d — a dependency-free 3-D renderer for the form-model figure.

   Drives the Pose3D motion core (web/js/pose3d.js): per frame it interpolates the
   exercise's bone-rotation poses, runs forward kinematics, projects the world
   joints through an orbitable perspective camera, and paints depth-sorted capsule
   limbs onto a 2-D <canvas>. No WebGL and no libraries, so it runs everywhere a
   canvas does; the heavier three.js skinned-avatar renderer is an optional layer
   on the SAME pose data. Reduced motion shows a static key pose.

   Same contract as the SVG engine: FormModel3D.create(host, ex, { onFinish })
   -> { destroy, start, reset }. Poses come from ex.poses3d if authored, else are
   derived from the existing 2-D views by the IK adapter (so every exercise works
   with no re-authoring). */
const FormModel3D = (() => {
  const P = (typeof Pose3D !== "undefined") ? Pose3D : null;
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const DEG = Math.PI / 180;

  const PREF_KEY = "f5s-fm3d-prefs";
  const DEFAULTS = { yaw: 22, pitch: 8, shading: true };
  function loadPrefs() { try { return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(PREF_KEY)) || {}); } catch (_) { return Object.assign({}, DEFAULTS); } }
  function savePrefs(p) { try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch (_) {} }
  const prefs = loadPrefs();

  // Capsule limbs taper between joint girths; a filled torso + sphere-shaded
  // joints/head give the stick figure volume. Girth is a world-space radius per
  // joint (scaled by the projection at draw time).
  const GIRTH = {
    hips: 12, spine: 11, shoulderL: 7, shoulderR: 7, elbowL: 5.5, elbowR: 5.5,
    handL: 4, handR: 4, hipL: 9, hipR: 9, kneeL: 7.5, kneeR: 7.5,
    ankleL: 5.5, ankleR: 5.5, footL: 4.5, footR: 4.5,
  };
  const LIMBS = [
    ["shoulderL", "elbowL"], ["elbowL", "handL"], ["shoulderR", "elbowR"], ["elbowR", "handR"],
    ["hipL", "kneeL"], ["kneeL", "ankleL"], ["ankleL", "footL"],
    ["hipR", "kneeR"], ["kneeR", "ankleR"], ["ankleR", "footR"], ["spine", "head"],
  ];
  const TORSO_Q = ["shoulderL", "shoulderR", "hipR", "hipL"];
  const JOINTS = Object.keys(GIRTH);
  // Light direction in screen space (upper-left-front; y is down).
  const LIGHT = (() => { const v = [-0.45, -0.8]; const l = Math.hypot(v[0], v[1]); return [v[0] / l, v[1] / l]; })();

  function parseRGB(str, fb) {
    if (!str) return fb;
    str = str.trim();
    let m = str.match(/^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (m) return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
    m = str.match(/^#?([0-9a-f])([0-9a-f])([0-9a-f])$/i);
    if (m) return [17 * parseInt(m[1], 16), 17 * parseInt(m[2], 16), 17 * parseInt(m[3], 16)];
    m = str.match(/(\d+)\D+(\d+)\D+(\d+)/);
    if (m) return [+m[1], +m[2], +m[3]];
    return fb;
  }
  function rgbVar(name, fb) { try { return parseRGB(getComputedStyle(document.documentElement).getPropertyValue(name), fb); } catch (_) { return fb; } }
  // Lighten (+) / darken (-) an [r,g,b] by amount, to a CSS string.
  function shade(rgb, f) {
    const a = (c) => clamp(Math.round(c + f * 150), 0, 255);
    return `rgb(${a(rgb[0])}, ${a(rgb[1])}, ${a(rgb[2])})`;
  }

  function makeCamera() {
    const target = [0, 108, 0];
    let yaw = (prefs.yaw || 0) * DEG, pitch = (prefs.pitch || 0) * DEG;
    const dist = 540, focal = 560;
    return {
      set yaw(v) { yaw = v; }, get yaw() { return yaw; },
      set pitch(v) { pitch = v; }, get pitch() { return pitch; },
      project(p) {
        const x = p[0] - target[0], y = p[1] - target[1], z = p[2] - target[2];
        const cy = Math.cos(yaw), sy = Math.sin(yaw);
        const x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
        const cp = Math.cos(pitch), sp = Math.sin(pitch);
        const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;
        const viewZ = Math.max(60, dist - z2), s = focal / viewZ;
        return { x: x1 * s, y: -y2 * s, depth: viewZ, scale: s };
      },
    };
  }

  function create(host, ex, opts = {}) {
    if (!P) { host.innerHTML = "<div class='empty'>3-D engine unavailable.</div>"; return { destroy() {}, start() {}, reset() {} }; }
    const onFinish = opts.onFinish || null;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const poses = ex.poses3d || P.adaptExercise(ex);
    const phases = ex.phases || [];
    const restName = poses.stand ? "stand" : Object.keys(poses)[0];

    let raf = null, phaseIdx = 0, phaseStart = 0, reps = 0, playing = false, destroyed = false;
    let tempoScale = 1, staticMode = reduceMotion;
    const cam = makeCamera();

    host.innerHTML = "";
    const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };

    const stage = el("div", "fm-stage fm3d-stage");
    const canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", ex.name + " 3-D movement figure");
    stage.appendChild(canvas);
    const ctx = canvas.getContext("2d");

    const phaseEl = el("span", "fm-phase", "Ready"), countEl = el("span", "fm-count");
    const meta = el("div", "fm-meta"); meta.append(phaseEl, countEl);
    const prog = el("i"); const bar = el("div", "fm-bar"); bar.appendChild(prog);
    const cue = el("div", "fm-cue"); cue.setAttribute("aria-live", "polite");

    const playBtn = el("button", "btn primary", "Start");
    const resetBtn = el("button", "btn", "Reset");
    const tempoNorm = el("button", "btn sm active", "Normal");
    const tempoSlow = el("button", "btn sm", "Slow");
    const row1 = el("div", "fm-controls"); row1.append(playBtn, resetBtn, el("div", "fm-spring"), tempoNorm, tempoSlow);

    const orbit = el("div", "fm-controls fm-3d");
    const yawS = el("input"); yawS.type = "range"; yawS.min = "-180"; yawS.max = "180"; yawS.value = String(prefs.yaw || 0); yawS.setAttribute("aria-label", "Orbit (yaw)");
    const pitchS = el("input"); pitchS.type = "range"; pitchS.min = "-40"; pitchS.max = "40"; pitchS.value = String(prefs.pitch || 0); pitchS.setAttribute("aria-label", "Tilt (pitch)");
    const yawW = el("label", "fm-pref fm-yaw"); yawW.append(document.createTextNode("Turn "), yawS);
    const pitchW = el("label", "fm-pref fm-yaw"); pitchW.append(document.createTextNode("Tilt "), pitchS);
    orbit.append(yawW, el("div", "fm-spring"), pitchW);

    host.append(stage, meta, bar, cue, row1, orbit);

    // Crisp canvas sized to its box.
    function resize() {
      const dpr = window.devicePixelRatio || 1;
      const w = stage.clientWidth || 280, h = Math.round(w * 1.18);
      canvas.style.width = w + "px"; canvas.style.height = h + "px";
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!playing) drawPose(currentPose());
    }

    let _pose = null;
    function currentPose() {
      if (_pose) return _pose;
      const ph = phases[phaseIdx];
      if (!ph) return poses[restName];
      return P.slerpPose(poses[ph.from] || poses[restName], poses[ph.to] || poses[restName], 0);
    }

    function drawPose(pose) {
      const w = canvas.width / (window.devicePixelRatio || 1), h = canvas.height / (window.devicePixelRatio || 1);
      const cx = w / 2, cyc = h * 0.55;
      ctx.clearRect(0, 0, w, h);
      const jp = P.forwardKinematics(pose);
      const text = rgbVar("--text", [232, 232, 234]), surface = rgbVar("--surface", [26, 26, 32]);

      // Project every joint to absolute screen space once.
      const pj = {};
      JOINTS.concat(["head"]).forEach((nm) => {
        const p = cam.project(jp[nm]);
        pj[nm] = { x: cx + p.x, y: cyc + p.y, depth: p.depth, scale: p.scale };
      });
      const depthAmt = (d) => (prefs.shading ? clamp((540 - d) / 300, -0.34, 0.24) : 0);
      const avgDepth = (names) => names.reduce((s, n) => s + pj[n].depth, 0) / names.length;

      // Soft contact shadows under the feet (and hips), grounding the figure.
      const groundY = Math.max(pj.footL.y, pj.footR.y, pj.ankleL.y, pj.ankleR.y) + 6;
      ctx.save(); ctx.fillStyle = "rgba(0,0,0,0.20)";
      [["footL", 22], ["footR", 22], ["hips", 30]].forEach(([nm, rw]) => {
        ctx.beginPath(); ctx.ellipse(pj[nm].x, groundY, rw * pj[nm].scale, 7 * pj[nm].scale, 0, 0, Math.PI * 2); ctx.fill();
      });
      ctx.restore();

      // ---- drawing primitives ----
      const capsule = (a, b, ra, rb, depth) => {
        const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
        const nx = -dy / len, ny = dx / len;
        ctx.beginPath();
        ctx.moveTo(a.x + nx * ra, a.y + ny * ra); ctx.lineTo(b.x + nx * rb, b.y + ny * rb);
        ctx.lineTo(b.x - nx * rb, b.y - ny * rb); ctx.lineTo(a.x - nx * ra, a.y - ny * ra);
        ctx.closePath();
        const lit = nx * LIGHT[0] + ny * LIGHT[1], d = depthAmt(depth);
        const g = ctx.createLinearGradient(a.x + nx * ra, a.y + ny * ra, a.x - nx * ra, a.y - ny * ra);
        g.addColorStop(0, shade(text, d + (lit > 0 ? 0.16 : -0.15)));
        g.addColorStop(1, shade(text, d + (lit > 0 ? -0.15 : 0.16)));
        ctx.fillStyle = g; ctx.fill();
      };
      const ball = (p, r, depth, base) => {
        const hx = p.x + LIGHT[0] * r * 0.4, hy = p.y + LIGHT[1] * r * 0.4, d = depthAmt(depth);
        const g = ctx.createRadialGradient(hx, hy, r * 0.12, p.x, p.y, r);
        g.addColorStop(0, shade(base, d + 0.24)); g.addColorStop(1, shade(base, d - 0.17));
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
      };
      const torso = (depth) => {
        ctx.beginPath();
        TORSO_Q.forEach((nm, i) => { const p = pj[nm]; i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); });
        ctx.closePath();
        const top = pj[TORSO_Q[0]], bot = pj[TORSO_Q[2]], d = depthAmt(depth);
        const g = ctx.createLinearGradient(top.x, top.y, bot.x, bot.y);
        g.addColorStop(0, shade(text, d + 0.10)); g.addColorStop(1, shade(text, d - 0.10));
        ctx.fillStyle = g; ctx.fill();
      };

      // Collect every part with its depth, paint far -> near.
      const items = [{ depth: avgDepth(TORSO_Q), draw: () => torso(avgDepth(TORSO_Q)) }];
      LIMBS.forEach(([j1, j2]) => {
        const a = pj[j1], b = pj[j2], dep = (a.depth + b.depth) / 2;
        items.push({ depth: dep, draw: () => capsule(a, b, (GIRTH[j1] || 6) * a.scale, (GIRTH[j2] || 6) * b.scale, dep) });
      });
      JOINTS.forEach((nm) => { const p = pj[nm]; items.push({ depth: p.depth, draw: () => ball(p, GIRTH[nm] * p.scale, p.depth, text) }); });
      const head = pj.head;
      items.push({ depth: head.depth, draw: () => ball(head, 17 * head.scale, head.depth, surface) });
      items.sort((m, n) => n.depth - m.depth).forEach((it) => it.draw());
    }

    function frame(ts) {
      if (!playing || destroyed) return;
      if (!canvas.isConnected) { playing = false; return; }
      const ph = phases[phaseIdx];
      const dur = ph.dur * (ph.isHold ? 1 : tempoScale);
      if (!phaseStart) phaseStart = ts;
      const elapsed = ts - phaseStart;
      let t = elapsed / dur; if (t > 1) t = 1;
      _pose = P.slerpPose(poses[ph.from] || poses[restName], poses[ph.to] || poses[restName], ease(t));
      drawPose(_pose);
      prog.style.width = (t * 100).toFixed(1) + "%";
      if (ph.isHold) { const left = Math.ceil((dur - elapsed) / 1000); countEl.textContent = left > 0 ? left + "s hold" : ""; }

      if (t >= 1) {
        phaseStart = 0; phaseIdx++;
        if (phaseIdx >= phases.length) {
          phaseIdx = 0;
          if (ex.targetReps) { reps++; countEl.textContent = reps + " / " + ex.targetReps; if (reps >= ex.targetReps) return finishSet(); }
          else return finishSet();
        }
        announce(phases[phaseIdx]);
      }
      raf = requestAnimationFrame(frame);
    }

    function announce(ph) { phaseEl.textContent = ph.name; if (ex.cues && ex.cues[ph.name]) cue.innerHTML = ex.cues[ph.name]; }
    function start() {
      if (staticMode || !phases.length) return;
      playing = true; playBtn.textContent = "Pause";
      if (!ex.targetReps) countEl.textContent = "";
      announce(phases[phaseIdx]); raf = requestAnimationFrame(frame);
    }
    function pause() { playing = false; playBtn.textContent = "Resume"; if (raf) cancelAnimationFrame(raf); }
    function finishSet() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      playBtn.textContent = "Start"; phaseEl.textContent = "Done"; cue.innerHTML = "Nice work."; prog.style.width = "100%";
      if (onFinish) onFinish(null);
    }
    function reset() {
      playing = false; if (raf) cancelAnimationFrame(raf);
      phaseIdx = 0; phaseStart = 0; reps = 0; _pose = null;
      playBtn.textContent = "Start"; phaseEl.textContent = "Ready"; cue.innerHTML = "";
      prog.style.width = "0%"; countEl.textContent = ex.targetReps ? "0 / " + ex.targetReps : "";
      drawPose(currentPose());
    }

    playBtn.onclick = () => (playing ? pause() : start());
    resetBtn.onclick = reset;
    tempoNorm.onclick = () => { tempoScale = 1; tempoNorm.classList.add("active"); tempoSlow.classList.remove("active"); };
    tempoSlow.onclick = () => { tempoScale = 1.6; tempoSlow.classList.add("active"); tempoNorm.classList.remove("active"); };
    yawS.addEventListener("input", () => { prefs.yaw = Number(yawS.value) || 0; savePrefs(prefs); cam.yaw = prefs.yaw * DEG; if (!playing) drawPose(currentPose()); });
    pitchS.addEventListener("input", () => { prefs.pitch = Number(pitchS.value) || 0; savePrefs(prefs); cam.pitch = prefs.pitch * DEG; if (!playing) drawPose(currentPose()); });
    const onResize = () => resize();
    window.addEventListener("resize", onResize);

    resize();
    reset();
    return {
      destroy() { destroyed = true; if (raf) cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); host.innerHTML = ""; },
      start, reset,
    };
  }

  return { create };
})();

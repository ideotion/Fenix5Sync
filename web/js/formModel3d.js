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

  // Segments to draw, as joint pairs + a stroke weight (relative limb girth).
  const SEGMENTS = [
    ["hips", "spine", 26], ["spine", "head", 16],
    ["shoulderL", "shoulderR", 14], ["hipL", "hipR", 18],
    ["shoulderL", "elbowL", 15], ["elbowL", "handL", 12],
    ["shoulderR", "elbowR", 15], ["elbowR", "handR", 12],
    ["hipL", "kneeL", 20], ["kneeL", "ankleL", 16], ["ankleL", "footL", 11],
    ["hipR", "kneeR", 20], ["kneeR", "ankleR", 16], ["ankleR", "footR", 11],
  ];

  function cssVar(name, fallback) {
    try { const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim(); return v || fallback; }
    catch (_) { return fallback; }
  }
  // Mix a hex/rgb-ish colour toward black/white by f in [-1,1] for depth shading.
  function shade(color, f) {
    const m = color.match(/\d+/g);
    if (!m || m.length < 3) return color;
    const adj = (c) => clamp(Math.round(c + f * 90), 0, 255);
    return `rgb(${adj(+m[0])}, ${adj(+m[1])}, ${adj(+m[2])})`;
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
      const cx = w / 2, cyc = h * 0.54;
      ctx.clearRect(0, 0, w, h);
      const jp = P.forwardKinematics(pose);

      // Ground shadow under the hips.
      const hp = cam.project(jp.hips);
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,0.22)";
      ctx.beginPath();
      ctx.ellipse(cx + cam.project(jp.ankleL)[0] * 0 + hp.x, cyc + 150, 46, 12, 0, 0, Math.PI * 2);
      ctx.fill(); ctx.restore();

      const text = cssVar("--text", "#e8e8ea"), bg = cssVar("--bg", "#101014");
      // Build, project, depth-sort, and paint capsule segments far -> near.
      const segs = SEGMENTS.map(([a, b, gw]) => {
        const pa = cam.project(jp[a]), pb = cam.project(jp[b]);
        return { pa, pb, gw, depth: (pa.depth + pb.depth) / 2 };
      }).sort((s1, s2) => s2.depth - s1.depth);

      const depthShade = (d) => prefs.shading ? clamp((540 - d) / 220, -0.5, 0.5) : 0;
      for (const s of segs) {
        const x1 = cx + s.pa.x, y1 = cyc + s.pa.y, x2 = cx + s.pb.x, y2 = cyc + s.pb.y;
        const gw = s.gw * ((s.pa.scale + s.pb.scale) / 2);
        ctx.lineCap = "round"; ctx.lineJoin = "round";
        ctx.strokeStyle = bg; ctx.lineWidth = gw + 6;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        ctx.strokeStyle = shade(text, depthShade(s.depth)); ctx.lineWidth = gw;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      }
      // Head.
      const head = cam.project(jp.head), r = 17 * head.scale;
      ctx.fillStyle = cssVar("--surface", "#1a1a20"); ctx.strokeStyle = shade(text, 0); ctx.lineWidth = 5 * head.scale;
      ctx.beginPath(); ctx.arc(cx + head.x, cyc + head.y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
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

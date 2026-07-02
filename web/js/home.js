/* Sports at Home: guided, evidence-based training with household objects, built
   for fragile/deconditioned users and scalable for the fit. Renders the bundled
   offline content pack (web/content/home/overview.json) and drives the signature
   form-model engine (formModel.js) from a data-driven exercise library
   (exercises.json). Three interactive pieces run entirely client-side (nothing
   leaves the machine): a PAR-Q+-style screen, the guided movement player, and a
   30-second sit-to-stand capacity check. Every claim links to its source. */
const HomeView = (() => {
  let data = null, library = null;

  // ---- PAR-Q+-style screen (client-only; stored in localStorage) ----
  const SCREEN_KEY = "f5s-home-screen";
  const STS_KEY = "f5s-home-sts";
  const PARQ = [
    "Has a doctor ever said you have a heart condition or high blood pressure?",
    "Do you feel pain in your chest at rest, in daily life, or during physical activity?",
    "Do you lose balance from dizziness, or have you lost consciousness in the last 12 months?",
    "Have you been diagnosed with another chronic medical condition?",
    "Are you currently taking prescribed medication for a chronic medical condition?",
    "Do you have a bone, joint, or soft-tissue problem that could be worsened by activity?",
    "Has a doctor ever said you should only do medically supervised activity?",
  ];

  function getScreen() {
    try { return JSON.parse(localStorage.getItem(SCREEN_KEY)) || null; } catch (_) { return null; }
  }
  function setScreen(s) { try { localStorage.setItem(SCREEN_KEY, JSON.stringify(s)); } catch (_) {} }
  function isometricOk() { const s = getScreen(); return !!(s && s.status === "clear"); }

  async function render() {
    U.setView(U.spinner("Loading Sports at Home…"));
    try {
      if (!data) data = await (await fetch("/content/home/overview.json")).json();
      if (!library) library = await (await fetch("/content/home/exercises.json")).json();
    } catch (e) {
      U.setView(U.el("div", { class: "empty", text: "Could not load Sports at Home content: " + e.message }));
      return;
    }
    draw();
  }

  function refChips(refs) {
    if (!refs || !refs.length) return null;
    const m = {}; (data.bibliography || []).forEach((b) => { m[b.ref_id] = b; });
    return U.el("span", { class: "tc-refs" }, refs.map((id) => {
      const b = m[id];
      return U.el("a", { class: "tc-ref", href: b ? b.url : "#", target: "_blank", rel: "noopener",
        title: b ? `${b.authors} (${b.year}) — ${b.title}` : id, text: id });
    }));
  }

  const GRADE_COLOR = { "Strong": "--accent-strong", "Moderate": "--accent", "Limited": "--text-faint" };

  // ---------- screening ----------
  function screeningCard() {
    const card = U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" });
    function paint() {
      card.innerHTML = "";
      const s = getScreen();
      card.appendChild(U.el("h3", { class: "tc-h", text: "Readiness check (PAR-Q+ style)" }));
      if (!s) {
        card.appendChild(U.el("div", { class: "sub", text: "A quick self-check before you start. It runs only on this device — nothing is sent anywhere. Loaded and isometric work (like the wall sit) stays locked until you complete it." }));
        const answers = PARQ.map(() => false);
        const qs = U.el("div", { class: "home-parq" }, PARQ.map((q, i) =>
          U.el("label", { class: "home-parq-q" }, [
            U.el("input", { type: "checkbox", onchange: (e) => { answers[i] = e.target.checked; } }),
            document.createTextNode(" " + q),
          ])));
        card.appendChild(qs);
        card.appendChild(U.el("div", { class: "home-parq-actions" }, [
          U.el("button", { class: "btn primary", text: "Check readiness", onclick: () => {
            const anyYes = answers.some(Boolean);
            setScreen(anyYes
              ? { status: "refer", tier: "seated", at: new Date().toISOString() }
              : { status: "clear", tier: "standing", at: new Date().toISOString() });
            paint(); rebuildGuided();
          } }),
          U.el("span", { class: "set-hint", text: "Tick every statement that is true for you." }),
        ]));
      } else if (s.status === "clear") {
        card.appendChild(U.el("div", { class: "home-screen-ok" }, [
          U.el("strong", { text: "Cleared to self-start." }),
          document.createTextNode(" You answered no to all questions. Begin at the supported/standing tier and drop to seated on symptom days."),
        ]));
        card.appendChild(rescreenBtn(paint));
      } else {
        card.appendChild(U.el("div", { class: "home-screen-refer" }, [
          U.el("strong", { text: "Check with a professional first." }),
          document.createTextNode(" You flagged at least one item. This simplified screen can't clear you — complete the full "),
          U.el("a", { href: "https://eparmedx.com/", target: "_blank", rel: "noopener", text: "PAR-Q+" }),
          document.createTextNode(" and speak to a clinician before loaded or isometric work. You can still explore seated/supported movement gently; the wall sit stays locked."),
        ]));
        card.appendChild(rescreenBtn(paint));
      }
    }
    paint();
    return card;
  }
  function rescreenBtn(paint) {
    return U.el("button", { class: "btn sm", text: "Re-screen", style: "margin-top:var(--sp-3)",
      onclick: () => { localStorage.removeItem(SCREEN_KEY); paint(); rebuildGuided(); } });
  }

  // ---------- guided movement (form-model engine) ----------
  let guidedHost = null, player = null, currentEx = null;
  const ENGINE_KEY = "f5s-home-engine";
  function getEngine() { try { return localStorage.getItem(ENGINE_KEY) === "3d" ? "3d" : "2d"; } catch (_) { return "2d"; } }
  function setEngine(v) { try { localStorage.setItem(ENGINE_KEY, v); } catch (_) {} }
  function engineApi() { return getEngine() === "3d" && typeof FormModel3D !== "undefined" ? FormModel3D : FormModel; }
  function rebuildGuided() { if (guidedHost) drawGuided(guidedHost); }

  const PATTERN_GROUPS = [
    ["squat", "Squat"], ["hinge", "Hinge"], ["push", "Push"], ["pull", "Pull"],
    ["carry", "Carry"], ["rotation", "Rotation"], ["balance", "Balance"],
    ["aerobic", "Aerobic"], ["isometric", "Isometric holds"],
  ];

  function drawGuided(host) {
    host.innerHTML = "";
    const exercises = (library.exercises || []);
    const locked = (ex) => ex.isometric && !isometricOk();

    // Filterable, pattern-grouped picker (uses the library's space metadata so
    // anyone who can't get to the floor can hide floor work in one tap).
    const search = U.el("input", { class: "input sm", type: "search", placeholder: "Search exercises…" });
    const noFloor = U.el("input", { type: "checkbox" });
    const picker = U.el("div");
    search.oninput = () => paintPicker();
    noFloor.onchange = () => paintPicker();

    function paintPicker() {
      const q = (search.value || "").trim().toLowerCase();
      picker.innerHTML = "";
      PATTERN_GROUPS.forEach(([pat, label]) => {
        const group = exercises.filter((ex) => ex.pattern === pat
          && (!q || ex.name.toLowerCase().includes(q))
          && (!noFloor.checked || ex.space !== "floor"));
        if (!group.length) return;
        picker.appendChild(U.el("div", { class: "set-hint", style: "margin:6px 0 2px", text: label }));
        picker.appendChild(U.el("div", { class: "home-ex-picker" }, group.map((ex) => {
          const lock = locked(ex);
          return U.el("button", { class: "btn sm" + (currentEx === ex.id ? " active" : "") + (lock ? " home-ex-locked" : ""),
            title: lock ? "Complete the readiness check to unlock isometric work" : ex.name,
            onclick: () => { if (lock) { U.toast("Isometric holds unlock after the readiness check.", ""); return; } select(ex.id); } },
            [document.createTextNode(ex.name + (lock ? " 🔒" : ""))]);
        })));
      });
      if (!picker.childNodes.length) picker.appendChild(U.el("div", { class: "set-hint", text: "No exercises match." }));
    }

    const filters = U.el("div", { style: "display:flex;gap:var(--sp-3);align-items:center;flex-wrap:wrap;margin-bottom:4px" }, [
      search,
      U.el("label", { class: "set-hint", style: "display:flex;align-items:center;gap:6px;cursor:pointer" }, [
        noFloor, document.createTextNode("Hide floor work"),
      ]),
    ]);
    paintPicker();

    // 2-D / 3-D engine toggle (3-D is the new canvas renderer; offline, no WebGL).
    const engRow = U.el("div", { class: "home-engine-row" });
    const mk2d = U.el("button", { class: "btn sm" + (getEngine() === "2d" ? " active" : ""), text: "2-D" });
    const mk3d = U.el("button", { class: "btn sm" + (getEngine() === "3d" ? " active" : ""), text: "3-D (beta)" });
    mk2d.onclick = () => { if (getEngine() !== "2d") { setEngine("2d"); mk2d.classList.add("active"); mk3d.classList.remove("active"); if (currentEx) select(currentEx); } };
    mk3d.onclick = () => { if (getEngine() !== "3d") { setEngine("3d"); mk3d.classList.add("active"); mk2d.classList.remove("active"); if (currentEx) select(currentEx); } };
    engRow.append(U.el("span", { class: "set-hint", text: "Figure" }), mk2d, mk3d);

    const stageHost = U.el("div", { class: "home-fm" });
    const infoHost = U.el("div", { class: "home-ex-info" });
    host.append(filters, picker, engRow, stageHost, infoHost);

    function exInfo(ex) {
      const tagline = [ex.pattern, ex.tier, ex.space].filter(Boolean).join(" · ");
      const rows = [];
      if (ex.primary_benefit) rows.push(U.el("div", { class: "sub", text: ex.primary_benefit }));
      if (ex.dose) {
        const r = ex.dose.reps ? `${ex.dose.reps[0]}–${ex.dose.reps[1]} reps` : `${ex.dose.seconds[0]}–${ex.dose.seconds[1]} s`;
        rows.push(U.el("div", { class: "tc-met", style: "margin:2px 0", text: `Suggested start: ${ex.dose.sets} × ${r}${ex.dose.per_side ? " per side" : ""}` }));
      }
      if (ex.watch_for) rows.push(U.el("div", { class: "set-hint", text: "Watch for: " + ex.watch_for }));
      const prog = [];
      if (ex.default_object) prog.push(["Default", ex.default_object]);
      if (ex.regression_object) prog.push(["Easier", ex.regression_object]);
      if (ex.progression_lever) prog.push(["Progress", ex.progression_lever]);
      if (prog.length) rows.push(U.el("ul", { class: "home-ex-prog" }, prog.map(([k, v]) =>
        U.el("li", {}, [U.el("strong", { text: k + ": " }), document.createTextNode(v)]))));
      if (ex.notes) rows.push(U.el("div", { class: "set-hint", text: ex.notes }));
      return U.el("div", { class: "card pad" }, [
        U.el("div", { class: "tc-prog-head" }, [
          U.el("strong", { text: ex.name }),
          refChips(ex.refs),
        ]),
        tagline ? U.el("div", { class: "tc-met", text: tagline, style: "margin:2px 0 6px" }) : null,
        ...rows,
      ]);
    }

    function select(id) {
      currentEx = id;
      if (player) player.destroy();
      const ex = exercises.find((e) => e.id === id);
      paintPicker();  // repaint so the active state follows the (filtered) buttons
      player = engineApi().create(stageHost, ex);
      infoHost.innerHTML = "";
      infoHost.appendChild(exInfo(ex));
    }

    // Default to the first non-locked exercise.
    const first = exercises.find((e) => !locked(e)) || exercises[0];
    if (first) select(first.id);
  }

  // ---------- capacity check: 30s sit-to-stand ----------
  function capacityCard() {
    const card = U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" });
    const best = (() => { try { return JSON.parse(localStorage.getItem(STS_KEY)); } catch (_) { return null; } })();
    const status = U.el("div", { class: "sub" });
    const timeEl = U.el("div", { class: "home-cap-time", text: "30" });
    let timer = null;

    function showBest() {
      const b = (() => { try { return JSON.parse(localStorage.getItem(STS_KEY)); } catch (_) { return null; } })();
      status.textContent = b ? `Your best: ${b.count} stands (${U.fmtDate(b.date)}). Repeat periodically to see progress — no scale needed.`
        : "A simple capacity check: count how many full sit-to-stands you complete in 30 seconds.";
    }
    function finish() {
      clearInterval(timer); timer = null; timeEl.textContent = "0";
      const n = prompt("How many full sit-to-stands did you complete in 30 seconds?");
      const count = Math.max(0, Math.round(Number(n)) || 0);
      if (count > 0) {
        const prev = (() => { try { return JSON.parse(localStorage.getItem(STS_KEY)); } catch (_) { return null; } })();
        if (!prev || count >= prev.count) {
          localStorage.setItem(STS_KEY, JSON.stringify({ count, date: new Date().toISOString() }));
          U.toast(`Logged ${count} — a new best!`, "good");
        } else U.toast(`Logged ${count}. Best stays ${prev.count}.`, "");
      }
      timeEl.textContent = "30"; showBest();
    }
    const startBtn = U.el("button", { class: "btn primary", text: "Start 30-second test", onclick: () => {
      if (timer) return;
      let left = 30; timeEl.textContent = left;
      timer = setInterval(() => { left -= 1; timeEl.textContent = Math.max(0, left); if (left <= 0) finish(); }, 1000);
    } });

    showBest();
    card.append(
      U.el("h3", { class: "tc-h", text: "Capacity check — 30-second sit-to-stand" }),
      status,
      U.el("div", { class: "home-cap", style: "margin-top:var(--sp-3)" }, [timeEl, startBtn]),
      U.el("div", { class: "set-hint", style: "margin-top:var(--sp-2)", text: "Use a sturdy chair against a wall. Stop if you feel pain, chest tightness, or dizziness." }),
    );
    return card;
  }

  // ---------- session builder (balanced, time-budgeted) ----------
  const BUILD_KEY = "f5s-home-builder";
  const SEED_KEY = "f5s-home-seed";
  function loadBuild() { try { return JSON.parse(localStorage.getItem(BUILD_KEY)) || {}; } catch (_) { return {}; } }
  function saveBuild(b) { try { localStorage.setItem(BUILD_KEY, JSON.stringify(b)); } catch (_) {} }
  function nextSeed() {
    let n = 1; try { n = (Number(localStorage.getItem(SEED_KEY)) || 0) + 1; localStorage.setItem(SEED_KEY, String(n)); } catch (_) {}
    return n;
  }

  function startSession(session) {
    const host = U.el("div");
    U.setView(host);
    SessionPlayer.create(host, session, { title: "Sports at Home session", onExit: render });
  }

  function builderCard() {
    if (typeof SessionBuilder === "undefined") return null;
    const b = loadBuild();
    const card = U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" });
    const sel = (opts, val) => {
      const s = U.el("select");
      opts.forEach(([v, label]) => { const o = U.el("option", { value: v, text: label }); if (String(v) === String(val)) o.selected = true; s.appendChild(o); });
      return s;
    };
    const length = sel([[5, "5 min"], [10, "10 min"], [15, "15 min"], [20, "20 min"], [30, "30 min"], [45, "45 min"]], b.lengthMin || 15);
    const sets = sel([[1, "1 set"], [2, "2 sets"], [3, "3 sets"], [4, "4 sets"]], b.sets || 2);
    const reps = U.el("input", { type: "number", min: "4", max: "20", value: b.reps || 10 });
    const equip = sel([["bodyweight", "Bodyweight"], ["household", "Household objects"], ["weights", "Free weights"]], b.equipment || "bodyweight");
    const focus = sel([["full_body", "Full body"], ["lower_body", "Lower body"], ["upper_body", "Upper body"], ["core", "Core"], ["balance", "Balance"]], b.focus || "full_body");
    const field = (label, node) => U.el("label", { class: "coach-field" }, [U.el("span", { class: "coach-field-l", text: label }), node]);
    const preview = U.el("div", { class: "coach-plan-preview" });

    function opts() {
      return {
        lengthMin: Number(length.value), sets: Number(sets.value), reps: Number(reps.value),
        equipment: equip.value, focus: focus.value,
        tier: (getScreen() || {}).tier || "standing", cleared: isometricOk(), seed: nextSeed(),
      };
    }
    function buildAndShow() {
      const o = opts();
      saveBuild({ lengthMin: o.lengthMin, sets: o.sets, reps: o.reps, equipment: o.equipment, focus: o.focus });
      const session = SessionBuilder.buildHome(library.exercises || [], o);
      preview.innerHTML = "";
      preview.appendChild(sessionPreview(session, "Start session", () => startSession(session)));
    }

    // One-click sessions from the content pack's shipped templates (the screen
    // tier and isometric clearance still apply at build time).
    const templates = ((data && data.sessions) || {}).templates || [];
    const tplRow = !templates.length ? null : U.el("div", { style: "margin-bottom:var(--sp-3)" }, [
      U.el("div", { class: "coach-field-l", text: "One-click sessions" }),
      U.el("div", { class: "home-ex-picker", style: "margin-top:6px" }, templates.map((t) =>
        U.el("button", { class: "btn sm", title: t.desc, text: t.name, onclick: () => {
          const o = Object.assign({}, t.opts, {
            tier: (getScreen() || {}).tier || "standing", cleared: isometricOk(), seed: nextSeed(),
          });
          const session = SessionBuilder.buildHome(library.exercises || [], o);
          preview.innerHTML = "";
          preview.appendChild(sessionPreview(session, "Start session", () => startSession(session)));
        } }))),
    ]);

    card.append(
      U.el("h3", { class: "tc-h", text: "Build a balanced session" }),
      U.el("div", { class: "sub", style: "margin-bottom:var(--sp-3)", text: "A time-budgeted session covering lower body, upper body and core (plus balance for fragile starters), warmed up and cooled down. Free weights swap in a dumbbell/kettlebell where it’s safe; isometrics stay locked until you pass the readiness check." }),
      tplRow || document.createTextNode(""),
      U.el("div", { class: "coach-form" }, [
        field("Length", length), field("Sets", sets), field("Reps", reps),
        field("Equipment", equip), field("Focus", focus),
      ]),
      U.el("div", { style: "margin-top:var(--sp-3)" }, [
        U.el("button", { class: "btn primary", text: "Build session", onclick: buildAndShow }),
      ]),
      preview,
    );
    return card;
  }

  function sessionPreview(session, startLabel, onStart) {
    const wrap = U.el("div", { style: "margin-top:var(--sp-4)" });
    const cov = session.coverageOk ? "covers all target regions" : "partial coverage (small pool)";
    wrap.appendChild(U.el("div", { class: "sub", text: `${session.items.length} exercises · ~${session.minutes} min · ${cov}` }));
    wrap.appendChild(U.el("ol", { class: "sp-plan-list" }, session.items.map((i) =>
      U.el("li", {}, [
        U.el("span", { class: "sp-plan-role", text: i.role === "warmup" ? "warm-up" : i.role === "cooldown" ? "cool-down" : i.region.replace("_", " ") }),
        U.el("span", { class: "sp-plan-name", text: i.name }),
        U.el("span", { class: "sp-plan-dose", text: i.sets > 1 ? `${i.sets}×` : "" }),
      ])
    )));
    wrap.appendChild(U.el("button", { class: "btn primary", style: "margin-top:var(--sp-3)", text: startLabel, onclick: onStart }));
    return wrap;
  }

  function draw() {
    const root = U.el("div", { class: "tc home" });
    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: data.title }),
        U.el("div", { class: "sub", text: data.subtitle }),
      ]),
    ]));

    // Disclaimer (prominent, like Tai Chi).
    root.appendChild(U.el("div", { class: "card pad tc-disclaimer", style: "margin-bottom:var(--sp-5)" }, [
      U.el("strong", { text: "Please read — " }),
      document.createTextNode(data.disclaimer),
    ]));

    // Readiness screen.
    root.appendChild(screeningCard());

    // Guided movement engine.
    root.appendChild(U.el("h2", { class: "tc-section", text: "Guided movement" }));
    root.appendChild(U.el("div", { class: "sub", style: "margin-bottom:var(--sp-3)",
      text: "Tempo-paced figures with the object in place — move with the figure. Switch to a static key-pose view any time; reduced-motion is honoured automatically." }));
    guidedHost = U.el("div", { class: "card pad" });
    drawGuided(guidedHost);
    root.appendChild(guidedHost);

    // Session builder (balanced, time-budgeted, runs through the engine).
    const builder = builderCard();
    if (builder) {
      root.appendChild(U.el("h2", { class: "tc-section", text: "Build a session" }));
      root.appendChild(builder);
    }

    // Capacity check.
    root.appendChild(capacityCard());

    // Tiers (levels).
    root.appendChild(U.el("h2", { class: "tc-section", text: "Tiers" }));
    const levels = U.el("div", { class: "charts" });
    (data.levels || []).forEach((l) => levels.appendChild(U.el("div", { class: "card pad" }, [
      U.el("div", { class: "tc-level-head" }, [
        U.el("strong", { text: l.name }),
        U.el("span", { class: "tc-met", text: `${l.intensity_met[0]}–${l.intensity_met[1]} METs` }),
      ]),
      U.el("div", { class: "sub", text: l.desc, style: "margin-top:6px" }),
    ])));
    root.appendChild(levels);

    // Tracks (programs).
    root.appendChild(U.el("h2", { class: "tc-section", text: "Population tracks" }));
    const progs = U.el("div", { class: "charts" });
    (data.programs || []).forEach((p) => progs.appendChild(U.el("div", { class: "card pad" }, [
      U.el("div", { class: "tc-prog-head" }, [U.el("strong", { text: p.name }), refChips(p.refs)]),
      U.el("div", { class: "sub", text: p.desc, style: "margin-top:6px" }),
    ])));
    root.appendChild(progs);

    // Objects.
    root.appendChild(U.el("h2", { class: "tc-section", text: "Objects as equipment" }));
    const objs = U.el("div", { class: "charts" });
    (data.objects || []).forEach((o) => objs.appendChild(U.el("div", { class: "card pad" }, [
      U.el("strong", { text: o.name }),
      U.el("div", { class: "sub", style: "margin-top:4px", text: `${o.role} · ${o.load_logic}` }),
      U.el("div", { class: "home-obj-moves", text: (o.movements || []).join(" · ") }),
      U.el("div", { class: "set-hint", style: "margin-top:6px", text: "Safety: " + o.safety }),
    ])));
    root.appendChild(objs);

    // Benefits.
    root.appendChild(U.el("h2", { class: "tc-section", text: "What the evidence shows" }));
    root.appendChild(U.el("div", { class: "card pad" }, (data.benefits || []).map((b) =>
      U.el("div", { class: "tc-benefit" }, [
        U.el("div", { class: "tc-benefit-head" }, [
          U.el("span", { class: "tc-grade", style: `background:var(${GRADE_COLOR[b.grade] || "--text-faint"})`, text: b.grade }),
          U.el("strong", { text: b.outcome }),
          refChips(b.refs),
        ]),
        U.el("div", { class: "sub", text: b.detail, style: "margin-top:4px" }),
      ])
    )));

    // What it does not do (honesty).
    if ((data.not_supported || []).length) {
      root.appendChild(U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
        U.el("h3", { class: "tc-h", text: "What it does not do (honesty)" }),
        U.el("ul", { class: "tc-list muted" }, data.not_supported.map((n) => U.el("li", { text: n }))),
      ]));
    }

    // Safety.
    if (data.safety) {
      root.appendChild(U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
        U.el("h3", { class: "tc-h", text: "Before you start" }),
        U.el("ul", { class: "tc-list" }, data.safety.setup.map((s) => U.el("li", { text: s }))),
        U.el("div", { class: "sub", style: "margin-top:var(--sp-3)", text: "Stop and seek care if you feel:" }),
        U.el("ul", { class: "tc-list" }, data.safety.red_flags.map((s) => U.el("li", { text: s }))),
        data.safety.population_guards ? U.el("div", { class: "sub", style: "margin-top:var(--sp-3)", text: "Population guards:" }) : null,
        data.safety.population_guards ? U.el("ul", { class: "tc-list muted" }, data.safety.population_guards.map((s) => U.el("li", { text: s }))) : null,
        U.el("div", { class: "sub muted", style: "margin-top:var(--sp-3)", text: data.safety.note }),
      ]));
    }

    // Discreet sources.
    root.appendChild(U.el("details", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
      U.el("summary", { text: `Sources (${(data.bibliography || []).length})` }),
      U.el("ul", { class: "tc-bib" }, (data.bibliography || []).map((b) =>
        U.el("li", {}, [
          U.el("a", { href: b.url, target: "_blank", rel: "noopener", text: `${b.ref_id} — ${b.authors} (${b.year})` }),
          document.createTextNode(` · ${b.title} — ${b.source} [${b.grade}]`),
        ])
      )),
    ]));

    U.setView(root);
  }

  return { render };
})();

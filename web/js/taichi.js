/* Tai Chi: evidence-based overview, level tiers and graded benefits, from a
   bundled offline content pack (web/content/taichi/overview.json). Guided
   sessions (movement library + instructor-reviewed videos) ingest here as the
   research deliverables arrive. Every claim links to its source. */
const TaiChiView = (() => {
  let data = null;
  let movements = null;
  let tcPlayer = null;

  const GRADE_COLOR = {
    "Strong": "--accent-strong", "Strong–Moderate": "--accent-strong",
    "Moderate": "--accent", "Moderate–Limited": "--accent",
    "Limited": "--text-faint", "Limited / Emerging": "--text-faint",
  };

  async function render() {
    U.setView(U.spinner("Loading Tai Chi…"));
    try {
      const res = await fetch("/content/taichi/overview.json");
      if (!res.ok) throw new Error("content unavailable");
      data = await res.json();
    } catch (e) {
      U.setView(U.el("div", { class: "empty", text: "Could not load Tai Chi content: " + e.message }));
      return;
    }
    if (movements === null) {
      try { movements = await (await fetch("/content/taichi/movements.json")).json(); }
      catch (_) { movements = { movements: [] }; }
    }
    draw();
  }

  function refChips(refs) {
    if (!refs || !refs.length) return null;
    const m = {};
    (data.bibliography || []).forEach((b) => { m[b.ref_id] = b; });
    return U.el("span", { class: "tc-refs" }, refs.map((id) => {
      const b = m[id];
      return U.el("a", {
        class: "tc-ref", href: b ? b.url : "#", target: "_blank", rel: "noopener",
        title: b ? `${b.authors} (${b.year}) — ${b.title}` : id, text: id,
      });
    }));
  }

  // Movement & breathing pacer — driven by the SHARED form-model engine
  // (the same engine that powers Sports at Home). Honest framing: a tempo/breath
  // guide, not instructed Tai Chi form.
  function movementPacer() {
    const list = (movements && movements.movements) || [];
    if (!list.length || typeof FormModel === "undefined") return null;

    let current = null;
    const stageHost = U.el("div", { class: "home-fm" });
    const infoHost = U.el("div", { class: "home-ex-info" });
    const picker = U.el("div", { class: "home-ex-picker" }, list.map((mv) =>
      U.el("button", { class: "btn sm", text: mv.name, onclick: () => select(mv.id) })));

    function mvInfo(mv) {
      const tagline = [mv.level, mv.focus].filter(Boolean).join(" · ");
      return U.el("div", { class: "card pad" }, [
        U.el("div", { class: "tc-prog-head" }, [U.el("strong", { text: mv.name }), refChips(mv.refs)]),
        tagline ? U.el("div", { class: "tc-met", text: tagline, style: "margin:2px 0 6px" }) : null,
        mv.primary_benefit ? U.el("div", { class: "sub", text: mv.primary_benefit }) : null,
        mv.notes ? U.el("div", { class: "set-hint", text: mv.notes }) : null,
      ]);
    }

    function select(id) {
      current = id;
      if (tcPlayer) tcPlayer.destroy();
      const mv = list.find((m) => m.id === id);
      Array.from(picker.children).forEach((b, i) => b.classList.toggle("active", list[i].id === id));
      tcPlayer = FormModel.create(stageHost, mv);
      infoHost.innerHTML = "";
      infoHost.appendChild(mvInfo(mv));
    }
    select(list[0].id);

    return U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
      U.el("h3", { class: "tc-h", text: "Movement & breathing pacer" }),
      U.el("div", { class: "sub", text: (movements.disclaimer || "Move slowly, within comfort.") }),
      picker,
      stageHost,
      infoHost,
    ]);
  }

  // ---------- session builder (length-adjustable flow) ----------
  const BUILD_KEY = "f5s-taichi-builder";
  const SEED_KEY = "f5s-taichi-seed";
  function loadBuild() { try { return JSON.parse(localStorage.getItem(BUILD_KEY)) || {}; } catch (_) { return {}; } }
  function saveBuild(b) { try { localStorage.setItem(BUILD_KEY, JSON.stringify(b)); } catch (_) {} }
  function nextSeed() {
    let n = 1; try { n = (Number(localStorage.getItem(SEED_KEY)) || 0) + 1; localStorage.setItem(SEED_KEY, String(n)); } catch (_) {}
    return n;
  }
  function startSession(session) {
    const host = U.el("div");
    U.setView(host);
    SessionPlayer.create(host, session, { title: "Tai Chi flow", onExit: render });
  }

  function builderCard() {
    const list = (movements && movements.movements) || [];
    if (!list.length || typeof SessionBuilder === "undefined") return null;
    const b = loadBuild();
    const sel = (opts, val) => {
      const s = U.el("select");
      opts.forEach(([v, label]) => { const o = U.el("option", { value: v, text: label }); if (String(v) === String(val)) o.selected = true; s.appendChild(o); });
      return s;
    };
    const length = sel([[5, "5 min"], [10, "10 min"], [15, "15 min"], [20, "20 min"], [30, "30 min"]], b.lengthMin || 15);
    const level = sel([["chair", "Chair / fragile"], ["supported", "Supported"], ["standing", "Standing"]], b.level || "standing");
    const focus = sel([["full", "Whole flow"], ["balance", "Balance"], ["mobility", "Mobility"], ["lower-limb", "Lower limb"], ["breathing", "Breathing"]], b.focus || "full");
    const field = (label, node) => U.el("label", { class: "coach-field" }, [U.el("span", { class: "coach-field-l", text: label }), node]);
    const preview = U.el("div", { class: "coach-plan-preview" });

    function buildAndShow() {
      const o = { lengthMin: Number(length.value), level: level.value, focus: focus.value, seed: nextSeed() };
      saveBuild({ lengthMin: o.lengthMin, level: o.level, focus: o.focus });
      const session = SessionBuilder.buildTaiChi(list, o);
      preview.innerHTML = "";
      const wrap = U.el("div", { style: "margin-top:var(--sp-4)" });
      wrap.appendChild(U.el("div", { class: "sub", text: `${session.items.length} movements · ~${session.minutes} min` }));
      wrap.appendChild(U.el("ol", { class: "sp-plan-list" }, session.items.map((i) =>
        U.el("li", {}, [
          U.el("span", { class: "sp-plan-role", text: i.role === "warmup" ? "open" : i.role === "cooldown" ? "close" : i.region }),
          U.el("span", { class: "sp-plan-name", text: i.name }),
        ]))));
      wrap.appendChild(U.el("button", { class: "btn primary", style: "margin-top:var(--sp-3)", text: "Start flow", onclick: () => startSession(session) }));
      preview.appendChild(wrap);
    }

    return U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
      U.el("h3", { class: "tc-h", text: "Build a flow" }),
      U.el("div", { class: "sub", style: "margin-bottom:var(--sp-3)", text: "A length-adjustable sequence covering balance, mobility, lower-limb and breathing, opening and closing on the breath. Balance is always included at the chair/fragile level. A gentle pacer, not instructed form." }),
      U.el("div", { class: "coach-form" }, [field("Length", length), field("Level", level), field("Focus", focus)]),
      U.el("div", { style: "margin-top:var(--sp-3)" }, [U.el("button", { class: "btn primary", text: "Build flow", onclick: buildAndShow })]),
      preview,
    ]);
  }

  function draw() {
    const root = U.el("div", { class: "tc" });
    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: data.title }),
        U.el("div", { class: "sub", text: data.subtitle }),
      ]),
    ]));

    root.appendChild(U.el("div", { class: "card pad tc-disclaimer", style: "margin-bottom:var(--sp-5)" }, [
      U.el("strong", { text: "Please read — " }),
      document.createTextNode(data.disclaimer),
    ]));

    const pacer = movementPacer();
    if (pacer) root.appendChild(pacer);

    const builder = builderCard();
    if (builder) root.appendChild(builder);

    if (data.sessions) {
      root.appendChild(U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
        U.el("h3", { class: "tc-h", text: "Guided sessions — coming soon" }),
        U.el("div", { class: "sub", text: data.sessions.note }),
        U.el("ul", { class: "tc-list" }, (data.sessions.planned || []).map((p) => U.el("li", { text: p }))),
      ]));
    }

    root.appendChild(U.el("h2", { class: "tc-section", text: "Levels" }));
    const levels = U.el("div", { class: "charts" });
    (data.levels || []).forEach((l) => levels.appendChild(U.el("div", { class: "card pad" }, [
      U.el("div", { class: "tc-level-head" }, [
        U.el("strong", { text: l.name }),
        U.el("span", { class: "tc-met", text: `${l.intensity_met[0]}–${l.intensity_met[1]} METs` }),
      ]),
      U.el("div", { class: "sub", text: l.desc, style: "margin-top:6px" }),
    ])));
    root.appendChild(levels);

    root.appendChild(U.el("h2", { class: "tc-section", text: "Recommended forms" }));
    const progs = U.el("div", { class: "charts" });
    (data.programs || []).forEach((p) => progs.appendChild(U.el("div", { class: "card pad" }, [
      U.el("div", { class: "tc-prog-head" }, [U.el("strong", { text: p.name }), refChips(p.refs)]),
      U.el("div", { class: "sub", text: p.desc, style: "margin-top:6px" }),
    ])));
    root.appendChild(progs);

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

    if (data.not_supported && data.not_supported.length) {
      root.appendChild(U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
        U.el("h3", { class: "tc-h", text: "What it does not do (honesty)" }),
        U.el("ul", { class: "tc-list muted" }, data.not_supported.map((n) => U.el("li", { text: n }))),
      ]));
    }

    if (data.safety) {
      root.appendChild(U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
        U.el("h3", { class: "tc-h", text: "Before you start" }),
        U.el("div", { class: "sub", text: "Set up:" }),
        U.el("ul", { class: "tc-list" }, data.safety.setup.map((s) => U.el("li", { text: s }))),
        U.el("div", { class: "sub", style: "margin-top:var(--sp-3)", text: "Stop and seek care if you feel:" }),
        U.el("ul", { class: "tc-list" }, data.safety.red_flags.map((s) => U.el("li", { text: s }))),
        U.el("div", { class: "sub muted", style: "margin-top:var(--sp-3)", text: data.safety.note }),
      ]));
    }

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

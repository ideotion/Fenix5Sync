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
  function rebuildGuided() { if (guidedHost) drawGuided(guidedHost); }

  function drawGuided(host) {
    host.innerHTML = "";
    const exercises = (library.exercises || []);
    const locked = (ex) => ex.isometric && !isometricOk();

    const picker = U.el("div", { class: "home-ex-picker" }, exercises.map((ex) => {
      const lock = locked(ex);
      return U.el("button", { class: "btn sm" + (currentEx === ex.id ? " active" : "") + (lock ? " home-ex-locked" : ""),
        title: lock ? "Complete the readiness check to unlock isometric work" : ex.name,
        onclick: () => { if (lock) { U.toast("Wall-sit (isometric) unlocks after the readiness check.", ""); return; } select(ex.id); } },
        [document.createTextNode(ex.name + (lock ? " 🔒" : ""))]);
    }));

    const stageHost = U.el("div", { class: "home-fm" });
    host.append(picker, stageHost);

    function select(id) {
      currentEx = id;
      if (player) player.destroy();
      const ex = exercises.find((e) => e.id === id);
      Array.from(picker.children).forEach((b, i) => b.classList.toggle("active", exercises[i].id === id));
      player = FormModel.create(stageHost, ex);
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

    // Sessions coming soon.
    if (data.sessions) {
      root.appendChild(U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
        U.el("h3", { class: "tc-h", text: "Guided sessions — coming soon" }),
        U.el("div", { class: "sub", text: data.sessions.note }),
        U.el("ul", { class: "tc-list" }, (data.sessions.planned || []).map((p) => U.el("li", { text: p }))),
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

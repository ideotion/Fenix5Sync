/* Coach: evidence-based, deterministic training guidance, from a bundled offline
   content pack (web/content/coach/overview.json). Phase 0 ships the verified
   foundation (approach, one reference program, personalization, normative index,
   safety, full bibliography); the goal x sport program matrix ingests here as it
   is generated. Every claim links to its source. */
const CoachView = (() => {
  let data = null;
  let homeLib = null;  // lazily loaded so cross-training days can draw from the builder
  const DIM = "color:var(--text-dim);font-size:13.5px;line-height:1.5";
  const FAINT = "color:var(--text-faint);font-size:12px";
  const H = "font-size:14px;color:var(--text-dim);margin-bottom:var(--sp-3)";
  const SECTION = "font-size:15px;margin:var(--sp-5) 0 var(--sp-3);color:var(--text)";

  const GRADE_COLOR = {
    "Strong": "--accent-strong", "Moderate": "--accent",
    "Limited": "--text-faint", "Limited (contested)": "--text-faint",
    "Emerging": "--text-faint", "Practice": "--accent-2",
  };

  async function render() {
    U.setView(U.spinner("Loading Coach…"));
    try {
      const res = await fetch("/content/coach/overview.json");
      if (!res.ok) throw new Error("content unavailable");
      data = await res.json();
    } catch (e) {
      U.setView(U.el("div", { class: "empty", text: "Could not load Coach content: " + e.message }));
      return;
    }
    draw();
  }

  function refChips(refs) {
    if (!refs || !refs.length) return null;
    const m = {};
    (data.bibliography || []).forEach((b) => { m[b.ref_id] = b; });
    return U.el("span", { style: "display:inline-flex;gap:4px;flex-wrap:wrap;margin-left:6px" },
      refs.map((id) => {
        const b = m[id];
        const label = id.replace(/^ref_/, "");
        const attrs = { style: "font-size:11px;font-weight:600;color:var(--accent);background:var(--surface-2);border-radius:4px;padding:1px 5px;text-decoration:none",
          title: b ? b.citation : id, text: label };
        if (b && b.url) { attrs.href = b.url; attrs.target = "_blank"; attrs.rel = "noopener"; return U.el("a", attrs); }
        return U.el("span", attrs);
      }));
  }

  function gradeBadge(grade) {
    return U.el("span", {
      style: `font-size:10.5px;font-weight:700;color:#fff;border-radius:4px;padding:2px 7px;text-transform:uppercase;letter-spacing:.03em;background:var(${GRADE_COLOR[grade] || "--text-faint"})`,
      text: grade,
    });
  }

  function draw() {
    const root = U.el("div");
    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: data.title }),
        U.el("div", { class: "sub", text: data.subtitle }),
      ]),
      U.el("div", { class: "head-actions" }, [U.el("span", { style: FAINT, text: data.phase })]),
    ]));

    root.appendChild(U.el("div", { class: "card pad", style: "border-left:3px solid var(--accent);margin-bottom:var(--sp-5)" }, [
      U.el("strong", { text: "Please read — " }),
      U.el("span", { style: DIM, text: data.disclaimer }),
    ]));

    // objective -> personalized plan (+ .ics export)
    root.appendChild(plannerCard());

    // reference program
    const rp = data.reference_program;
    if (rp) {
      const phases = rp.phases.map((p) => `${p.name} ${p.weeks}w`).join(" · ");
      root.appendChild(U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
        U.el("h3", { style: H, html: "Reference program " }),
        U.el("div", { style: "font-weight:600;margin-bottom:6px" }, [
          document.createTextNode(`${U.cap(rp.goal)} · ${U.cap(rp.level)} · ${rp.duration_weeks} weeks`),
          refChips(rp.refs),
        ]),
        U.el("div", { class: "meta-grid" }, [
          metaItem("Phases", phases),
          metaItem("Distribution", rp.distribution),
          metaItem("Peak volume", `${rp.peak_volume_km} km/wk · long run ${rp.peak_long_run_km} km`),
          metaItem("Entry gate", rp.entry_gate),
          metaItem("Taper", rp.taper),
        ]),
        U.el("div", { style: FAINT + ";margin-top:var(--sp-3)", text: data.programs_note }),
      ]));
    }

    // approach
    root.appendChild(U.el("h2", { style: SECTION, text: "Approach" }));
    root.appendChild(U.el("div", { class: "card pad" }, (data.approach || []).map((a) =>
      U.el("div", { style: "padding:var(--sp-3) 0;border-bottom:1px solid var(--border-soft)" }, [
        U.el("div", { style: "display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap" }, [
          gradeBadge(a.grade), U.el("strong", { text: a.topic }), refChips(a.refs),
        ]),
        U.el("div", { style: DIM + ";margin-top:4px", text: a.detail }),
      ])
    )));

    // personalization
    const p = data.personalization;
    if (p) {
      root.appendChild(U.el("h2", { style: SECTION, text: "How it personalizes to you" }));
      const steps = U.el("ol", { style: DIM + ";padding-left:18px;line-height:1.7" },
        p.worked_example.map((s) => U.el("li", {}, [U.el("strong", { text: s.step + ": " }), document.createTextNode(s.detail), refChips(s.refs) || document.createTextNode("")])));
      root.appendChild(U.el("div", { class: "card pad" }, [
        U.el("div", { style: DIM, text: p.summary }),
        U.el("div", { style: FAINT + ";margin-top:var(--sp-3)", text: "Reads these metrics: " + p.metric_fields.join(", ") }),
        U.el("div", { style: "margin-top:var(--sp-3);font-weight:600;font-size:13px", text: "Worked example" }),
        steps,
      ]));
    }

    // normative tables
    root.appendChild(U.el("h2", { style: SECTION, text: "Normative reference data" }));
    root.appendChild(U.el("div", { class: "card pad" }, [
      U.el("ul", { style: DIM + ";padding-left:18px;line-height:1.8" }, (data.normative_tables || []).map((t) =>
        U.el("li", {}, [document.createTextNode(t.name), refChips(t.refs) || document.createTextNode("")]))),
    ]));

    // safety
    if (data.safety) {
      root.appendChild(U.el("h2", { style: SECTION, text: "Safety & contested evidence" }));
      const s = data.safety;
      root.appendChild(U.el("div", { class: "card pad" }, [
        safetyRow("Energy availability (RED-S)", s.red_s),
        safetyRow("Anti-doping", s.anti_doping),
        safetyRow("The ACWR debate", s.acwr),
      ]));
    }

    // coverage
    root.appendChild(U.el("h2", { style: SECTION, text: "Coverage" }));
    root.appendChild(U.el("div", { class: "card pad" }, [
      U.el("ul", { style: DIM + ";padding-left:18px;line-height:1.8;list-style:none" }, (data.coverage || []).map((c) =>
        U.el("li", {}, [
          U.el("span", { text: c.status === "complete" ? "✅ " : "▫️ " }),
          document.createTextNode(c.cell),
        ]))),
    ]));

    // glossary + bibliography (collapsible)
    root.appendChild(U.el("details", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
      U.el("summary", { text: `Glossary (${(data.glossary || []).length})` }),
      U.el("dl", { style: DIM + ";margin-top:var(--sp-3)" }, (data.glossary || []).flatMap((g) => [
        U.el("dt", { style: "font-weight:600;margin-top:8px", text: g.term }),
        U.el("dd", { style: "margin:2px 0 0", text: g.def }),
      ])),
    ]));

    root.appendChild(U.el("details", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
      U.el("summary", { text: `Sources (${(data.bibliography || []).length})` }),
      U.el("ul", { style: "margin-top:var(--sp-3);padding-left:18px;font-size:12.5px;color:var(--text-dim);line-height:1.7" },
        (data.bibliography || []).map((b) => U.el("li", {}, [
          b.url ? U.el("a", { href: b.url, target: "_blank", rel: "noopener", style: "color:var(--accent)", text: b.ref_id.replace(/^ref_/, "") })
                : U.el("span", { style: "font-weight:600", text: b.ref_id.replace(/^ref_/, "") }),
          document.createTextNode(` — ${b.citation} `),
          verifyBadge(b.verification),
        ]))),
    ]));

    U.setView(root);
  }

  function metaItem(k, v) {
    return U.el("div", { class: "meta" }, [
      U.el("div", { class: "k", text: k }),
      U.el("div", { class: "v", style: "font-size:13px;font-weight:600", text: v }),
    ]);
  }

  // ---------- objective -> dated plan ----------
  const PLAN_KEY = "f5s-coach-objective";
  const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  function loadObjective() {
    try { return JSON.parse(localStorage.getItem(PLAN_KEY)) || {}; } catch (_) { return {}; }
  }
  function saveObjective(o) { try { localStorage.setItem(PLAN_KEY, JSON.stringify(o)); } catch (_) {} }

  function plannerCard() {
    const o = loadObjective();
    const sel = (opts, val) => {
      const s = U.el("select", { class: "input sm" });
      opts.forEach(([v, label]) => { const op = U.el("option", { value: v, text: label }); if (v === val) op.selected = true; s.appendChild(op); });
      return s;
    };
    const goal = sel([["5k", "5K"], ["10k", "10K"], ["half", "Half marathon"], ["marathon", "Marathon"], ["general", "General fitness"]], o.goal_distance || "10k");
    const level = sel([["beginner", "Beginner"], ["intermediate", "Intermediate"], ["advanced", "Advanced"]], o.level || "intermediate");
    const start = U.el("input", { class: "input sm", type: "date", value: o.start_date || "" });
    const target = U.el("input", { class: "input sm", type: "date", value: o.target_date || "" });
    const weeks = U.el("input", { class: "input sm", type: "number", min: "1", max: "52", placeholder: "weeks", value: o.weeks || "" });
    const time = U.el("input", { class: "input sm", type: "text", placeholder: "e.g. 50:00", value: o.target_time || "" });
    const sessions = U.el("input", { class: "input sm", type: "number", min: "1", max: "7", placeholder: "auto", value: o.sessions_per_week || "" });

    const dayState = new Set(Array.isArray(o.available_days) ? o.available_days : [0, 2, 4, 6]);
    const dayBtns = DAY_NAMES.map((name, i) => U.el("button", {
      class: "btn sm" + (dayState.has(i) ? " active" : ""), type: "button", text: name,
      onclick: (e) => { dayState.has(i) ? dayState.delete(i) : dayState.add(i); e.target.classList.toggle("active"); },
    }));

    const preview = U.el("div", { class: "coach-plan-preview" });
    const field = (label, node) => U.el("label", { class: "coach-field" }, [U.el("span", { class: "coach-field-l", text: label }), node]);

    function currentObjective() {
      return {
        goal_distance: goal.value, level: level.value,
        start_date: start.value || null, target_date: target.value || null,
        weeks: weeks.value ? Number(weeks.value) : null,
        target_time: time.value || null,
        sessions_per_week: sessions.value ? Number(sessions.value) : null,
        available_days: Array.from(dayState).sort((a, b) => a - b),
      };
    }

    async function build() {
      const obj = currentObjective();
      saveObjective(obj);
      preview.innerHTML = "";
      preview.appendChild(U.spinner("Building your plan…"));
      try {
        const plan = await API.coachPlan(obj);
        renderPlan(preview, plan, obj);
      } catch (e) {
        preview.innerHTML = "";
        preview.appendChild(U.el("div", { class: "empty", text: "Could not build the plan: " + e.message }));
      }
    }

    const buildBtn = U.el("button", { class: "btn primary", text: "Build plan", onclick: build });

    return U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
      U.el("h3", { style: H, text: "Build your plan" }),
      U.el("div", { style: DIM + ";margin-bottom:var(--sp-3)", text: "Turn an objective into a dated week-by-week plan with pace, heart-rate and effort targets. Targets are evidence-graded estimates shown as ranges — not medical advice or guarantees. Get clearance (PAR-Q+) before starting." }),
      U.el("div", { class: "coach-form" }, [
        field("Goal", goal), field("Level", level),
        field("Start", start), field("Race day", target),
        field("Or weeks", weeks), field("Goal time", time),
        field("Runs/week", sessions),
      ]),
      U.el("div", { style: "margin-top:var(--sp-3)" }, [
        U.el("div", { class: "coach-field-l", text: "Available days" }),
        U.el("div", { class: "home-ex-picker", style: "margin:6px 0 0" }, dayBtns),
      ]),
      U.el("div", { style: "margin-top:var(--sp-3)" }, [buildBtn]),
      preview,
    ]);
  }

  function renderPlan(host, plan, obj) {
    host.innerHTML = "";
    const s = plan.summary;
    const head = [U.el("strong", { text: `${U.cap(s.goal)} · ${plan.weeks} weeks · ${U.cap(s.level)}` })];
    const wrap = U.el("div", { style: "margin-top:var(--sp-4)" });

    // summary + confidence + projection
    const bits = [`VDOT ${s.vdot} (${s.confidence} confidence)`];
    if (s.predicted_time) bits.push(`projected ${s.goal} ≈ ${s.predicted_time} @ ${s.race_pace}`);
    wrap.appendChild(U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-3)" }, [
      U.el("div", {}, head),
      U.el("div", { style: DIM + ";margin-top:4px", text: bits.join(" · ") }),
      s.equivalents ? U.el("div", { style: FAINT + ";margin-top:4px", text: "Equivalent efforts: " + Object.entries(s.equivalents).map(([k, v]) => `${k} ${v}`).join(" · ") }) : null,
    ]));

    // pace table
    const zoneLabel = { E: "Easy", M: "Steady", T: "Threshold", I: "Intervals" };
    const rows = ["E", "M", "T", "I"].map((z) => {
      const p = plan.paces[z];
      return U.el("tr", {}, [
        U.el("td", { style: "font-weight:600", text: zoneLabel[z] }),
        U.el("td", { text: p.pace }),
        U.el("td", { text: p.rpe }),
        U.el("td", { text: p.hr || "—" }),
      ]);
    });
    wrap.appendChild(U.el("table", { class: "coach-pace-table" }, [
      U.el("thead", {}, [U.el("tr", {}, ["Zone", "Pace", "Effort", "Heart rate"].map((h) => U.el("th", { text: h })))]),
      U.el("tbody", {}, rows),
    ]));

    // weekly agenda (grouped, rest days hidden)
    const byWeek = {};
    plan.sessions.forEach((sess) => { (byWeek[sess.week] = byWeek[sess.week] || []).push(sess); });
    const agenda = U.el("div", { style: "margin-top:var(--sp-3)" });
    Object.keys(byWeek).map(Number).sort((a, b) => a - b).forEach((w) => {
      const list = byWeek[w].filter((x) => x.kind !== "rest");
      if (!list.length) return;
      const phase = byWeek[w][0].phase;
      const sb = byWeek[w].some((x) => x.stepback) ? " · step-back" : "";
      agenda.appendChild(U.el("details", { class: "coach-week" }, [
        U.el("summary", {}, [U.el("strong", { text: `Week ${w}` }), U.el("span", { style: FAINT + ";margin-left:8px", text: phase + sb })]),
        U.el("ul", { class: "coach-week-list" }, list.map((x) => U.el("li", {}, [
          U.el("span", { class: "coach-sess-day", text: x.weekday }),
          U.el("span", { class: "coach-sess-title", text: x.title + (x.duration_min ? ` · ${x.duration_min} min` : "") }),
          x.target ? U.el("span", { style: FAINT, text: x.target.pace }) : null,
        ]))),
      ]));
    });
    wrap.appendChild(agenda);

    // export + honesty notes + discreet sources
    const icsParams = Object.assign({}, obj, { available_days: (obj.available_days || []).join(",") });
    wrap.appendChild(U.el("div", { style: "margin-top:var(--sp-4);display:flex;gap:var(--sp-2);flex-wrap:wrap;align-items:center" }, [
      U.el("a", { class: "btn", href: API.coachPlanIcsUrl(icsParams), download: "coach-plan.ics", text: "Export .ics" }),
      U.el("span", { style: FAINT, text: "Adds each session to your calendar." }),
    ]));
    // Cross-training / strength day — drawn from the Sports-at-Home session builder
    // so it is body-part varied (WS5 integration).
    if (typeof SessionBuilder !== "undefined" && typeof SessionPlayer !== "undefined") {
      const out = U.el("div", { style: "margin-top:6px" });
      const btn = U.el("button", { class: "btn", text: "Add a strength cross-training day" });
      btn.onclick = async () => {
        btn.disabled = true;
        try {
          if (!homeLib) homeLib = await (await fetch("/content/home/exercises.json")).json();
          const session = SessionBuilder.buildHome(homeLib.exercises || [], {
            lengthMin: 20, sets: 2, reps: 10, equipment: "bodyweight",
            focus: "full_body", tier: "standing", cleared: true, seed: (Date.now() & 0xffff) || 1,
          });
          out.innerHTML = "";
          out.appendChild(U.el("div", { style: DIM + ";margin:6px 0", text: `${session.items.length} exercises · ~${session.minutes} min · body-part varied` }));
          out.appendChild(U.el("ol", { class: "sp-plan-list" }, session.items.map((i) =>
            U.el("li", {}, [
              U.el("span", { class: "sp-plan-role", text: i.role === "warmup" ? "warm-up" : i.role === "cooldown" ? "cool-down" : i.region.replace("_", " ") }),
              U.el("span", { class: "sp-plan-name", text: i.name }),
            ]))));
          out.appendChild(U.el("button", {
            class: "btn primary", style: "margin-top:var(--sp-2)", text: "Start session",
            onclick: () => { const host = U.el("div"); U.setView(host); SessionPlayer.create(host, session, { title: "Cross-training", onExit: render }); },
          }));
        } catch (e) { U.toast("Could not build a session: " + e.message, "bad"); }
        btn.disabled = false;
      };
      wrap.appendChild(U.el("div", { style: "margin-top:var(--sp-4)" }, [
        U.el("div", { style: FAINT + ";margin-bottom:6px", text: "Easy or rest days can include a balanced strength session, drawn from the Sports at Home builder so it is body-part varied." }),
        btn, out,
      ]));
    }

    if (plan.notes && plan.notes.length) {
      wrap.appendChild(U.el("ul", { style: FAINT + ";margin-top:var(--sp-3);padding-left:18px;line-height:1.6" },
        plan.notes.map((n) => U.el("li", { text: n }))));
    }
    wrap.appendChild(U.el("details", { style: FAINT + ";margin-top:var(--sp-2)" }, [
      U.el("summary", { text: "Method & evidence grades" }),
      U.el("ul", { style: "padding-left:18px;margin-top:6px;line-height:1.6" },
        (plan.evidence.caveats || []).map((c) => U.el("li", { text: c }))),
    ]));
    host.appendChild(wrap);
  }

  function safetyRow(title, body) {
    return U.el("div", { style: "padding:var(--sp-3) 0;border-bottom:1px solid var(--border-soft)" }, [
      U.el("div", { style: "font-weight:600;font-size:13px;margin-bottom:3px", text: title }),
      U.el("div", { style: DIM, text: body }),
    ]);
  }

  function verifyBadge(state) {
    const verified = state === "web_verified";
    return U.el("span", {
      style: `font-size:10px;font-weight:700;border-radius:4px;padding:1px 5px;margin-left:4px;color:#fff;background:var(${verified ? "--accent-strong" : "--accent-2"})`,
      text: verified ? "verified" : "confirm DOI",
    });
  }

  return { render };
})();

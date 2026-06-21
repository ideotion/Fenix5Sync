/* Coach: evidence-based, deterministic training guidance, from a bundled offline
   content pack (web/content/coach/overview.json). Phase 0 ships the verified
   foundation (approach, one reference program, personalization, normative index,
   safety, full bibliography); the goal x sport program matrix ingests here as it
   is generated. Every claim links to its source. */
const CoachView = (() => {
  let data = null;
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

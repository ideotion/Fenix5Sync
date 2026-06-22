/* Privacy audit: a defensive, local self-audit of what your own start points
   reveal (likely home, routine regularity), with a recommended privacy radius
   that feeds the existing anonymization. Inferences are probabilistic and never
   leave the machine. Rationale + sources are shown discreetly at the foot. */
const PrivacyView = (() => {
  let about = null;
  const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const hour = (h) => (h == null ? "—" : String(h).padStart(2, "0") + ":00");

  function weekdayBars(counts) {
    const max = Math.max(1, ...counts);
    return U.el("div", { class: "pv-week" }, counts.map((c, i) =>
      U.el("div", { class: "pv-week-col", title: `${WD[i]}: ${c}` }, [
        U.el("div", { class: "pv-week-bar", style: `height:${Math.round((c / max) * 100)}%` }),
        U.el("div", { class: "pv-week-k", text: WD[i][0] }),
      ])));
  }

  async function render() {
    U.setView(U.spinner("Auditing your tracks — locally…"));
    if (about === null) {
      try { about = await (await fetch("/content/privacy/about.json")).json(); }
      catch (_) { about = {}; }
    }
    let d;
    try { d = await API.privacyAudit(); }
    catch (e) { U.setView(U.el("div", { class: "empty", text: "Could not run audit: " + e.message })); return; }
    draw(d);
  }

  function aboutDetails() {
    if (!about.rationale && !(about.sources || []).length) return null;
    return U.el("details", { class: "card pad rc-about" }, [
      U.el("summary", { text: "Why this is here" }),
      about.rationale ? U.el("p", { class: "sub", text: about.rationale }) : null,
      (about.sources || []).length ? U.el("ul", { class: "rc-srcs" }, about.sources.map((s) =>
        U.el("li", {}, [
          U.el("a", { href: s.url, target: "_blank", rel: "noopener", text: s.title }),
          document.createTextNode(` — ${s.publisher}${s.date ? " (" + s.date + ")" : ""}`),
        ]))) : null,
    ]);
  }

  function header() {
    return U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: about.title || "Privacy audit" }),
        U.el("div", { class: "sub", text: about.subtitle || "" }),
      ]),
    ]);
  }

  function draw(d) {
    const root = U.el("div", { class: "pv" });
    root.appendChild(header());

    if (!d.with_gps) {
      root.appendChild(U.el("div", { class: "card pad" }, [
        U.el("p", { class: "sub", text: `None of your ${d.total_activities} activities carry GPS start points, so there's nothing to audit here.` }),
      ]));
      const ad = aboutDetails(); if (ad) root.appendChild(ad);
      U.setView(root);
      return;
    }

    root.appendChild(U.el("div", { class: "card pad pv-summary" }, [
      U.el("p", {}, [
        document.createTextNode(`${d.with_gps} of ${d.total_activities} activities carry a GPS start point. `),
        U.el("strong", { text: `${d.location_count} distinct place${d.location_count === 1 ? "" : "s"}` }),
        document.createTextNode(" stand out — the one your data exposes most is likely where you live."),
      ]),
    ]));

    const p = d.primary;
    if (p) {
      root.appendChild(U.el("div", { class: "card pad pv-primary" }, [
        U.el("div", { class: "pv-primary-head" }, [
          U.el("h3", { text: "Most-exposed place (likely home)" }),
          U.el("span", { class: "pv-tag", text: `${p.share_pct}% of starts` }),
        ]),
        U.el("div", { class: "pv-grid" }, [
          stat(`${p.count}`, "Starts here"),
          stat(`±${Math.round(p.spread_m)} m`, "Spread"),
          stat(`${p.regularity_pct}%`, "On " + (p.peak_weekday || "—"), "weekday regularity"),
          stat(hour(p.peak_hour), "Typical start"),
        ]),
        U.el("div", { class: "pv-loc sub", text: `Approx. ${p.lat}, ${p.lon} · seen ${p.first_seen} → ${p.last_seen}` }),
        weekdayBars(p.weekday_counts),
      ]));

      // Exposure + recommendation.
      const rec = U.el("div", { class: "card pad pv-rec" }, [
        U.el("h3", { text: "What sharing would leak — and how to mask it" }),
        U.el("p", { class: "sub" }, [
          document.createTextNode(`${d.exposed_activities} activities (${d.exposed_pct}%) start within `),
          U.el("strong", { text: `${d.recommended_radius_m} m` }),
          document.createTextNode(" of this place. Nulling positions within a privacy radius of the start (and finish) on export would hide it."),
        ]),
        recRow(d),
      ]);
      root.appendChild(rec);
    }

    // Other frequent places (measured, not alarmist).
    const others = (d.clusters || []).filter((c) => c.kind !== "primary");
    if (others.length) {
      root.appendChild(U.el("div", { class: "card pad" }, [
        U.el("h3", { class: "tc-h", text: "Other frequent places" }),
        U.el("div", { class: "pv-others" }, others.map((c) =>
          U.el("div", { class: "pv-other" }, [
            U.el("strong", { text: `${c.count} starts` }),
            U.el("span", { class: "sub", text: ` · ${c.share_pct}% · ≈ ${c.lat}, ${c.lon} · mostly ${c.peak_weekday || "—"}` }),
          ]))),
      ]));
    }

    const ad = aboutDetails(); if (ad) root.appendChild(ad);
    U.setView(root);
  }

  function stat(value, label, sub) {
    return U.el("div", { class: "pv-stat" }, [
      U.el("div", { class: "pv-stat-v", text: value }),
      U.el("div", { class: "pv-stat-l", text: label }),
      sub ? U.el("div", { class: "pv-stat-s", text: sub }) : null,
    ]);
  }

  function recRow(d) {
    const current = d.current_radius_m || 0;
    const status = d.radius_sufficient
      ? U.el("span", { class: "pv-ok", text: `Your current privacy radius (${current} m) already covers it.` })
      : U.el("span", { class: "pv-warn", text: current
          ? `Your current radius is ${current} m — below the ${d.recommended_radius_m} m recommended.`
          : "You have no privacy radius set yet." });

    const apply = U.el("button", { class: "btn", onclick: async () => {
      apply.disabled = true;
      try {
        const cfg = await API.getConfig();
        cfg.anonymize = cfg.anonymize || {};
        cfg.anonymize.privacy_radius_m = d.recommended_radius_m;
        await API.putConfig(cfg);
        U.toast(`Privacy radius set to ${d.recommended_radius_m} m. It applies when you anonymize an export.`, "good");
        render();
      } catch (e) {
        U.toast("Could not update config: " + e.message, "bad");
        apply.disabled = false;
      }
    } }, [U.el("span", { text: `Set privacy radius to ${d.recommended_radius_m} m` })]);

    return U.el("div", { class: "pv-rec-row" }, [status, d.radius_sufficient ? null : apply]);
  }

  return { render };
})();

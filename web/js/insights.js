/* Insights: accomplishments, statistics, evolution-over-time and a calendar
   heatmap — all computed locally by /api/insights. Charts use the vendored
   Chart.js via the shared Charts module; the heatmap is plain DOM + CSS. */
const Insights = (() => {
  let state = { sport: "", year: "" };
  let data = null;
  let load = null;  // training-load (CTL/ATL/TSB) payload, fetched alongside insights
  let hr = null;    // heart-rate & efficiency trends
  let wellness = null;  // daily wellness/readiness from monitoring files
  let dups = null;      // cross-source duplicate report
  let records = null;   // all-time best times per distance

  async function render() {
    Charts.destroyAll();
    U.setView(U.spinner("Crunching your numbers…"));
    try {
      data = await API.insights(state.sport || undefined);
    } catch (e) {
      U.setView(U.el("div", { class: "empty", text: "Could not load insights: " + e.message }));
      return;
    }
    // Supplementary analytics — a failure here must not sink the page.
    try { load = await API.trainingLoad(state.sport || undefined); } catch (_) { load = null; }
    try { hr = await API.hrTrends(state.sport || undefined); } catch (_) { hr = null; }
    try { wellness = await API.wellness(); } catch (_) { wellness = null; }
    try { dups = await API.duplicates(); } catch (_) { dups = null; }
    try { records = await API.records(state.sport || undefined); } catch (_) { records = null; }
    if (!data.years.includes(state.year)) state.year = data.years[data.years.length - 1] || "";
    draw();
  }

  function draw() {
    const root = U.el("div");
    root.appendChild(pageHead());

    if (!data.totals.count) {
      root.appendChild(emptyState());
      U.setView(root);
      return;
    }

    root.appendChild(heroTiles(data.totals));
    const recs = recordsRow(data.records);
    if (recs) root.appendChild(recs);
    const bt = bestTimesCard();
    if (bt) root.appendChild(bt);
    const tl = trainingLoadCard();
    if (tl) root.appendChild(tl);
    const hrc = hrTrendsCard();
    if (hrc) root.appendChild(hrc);
    const wc = wellnessCard();
    if (wc) root.appendChild(wc);
    const dc = dupsCard();
    if (dc) root.appendChild(dc);
    root.appendChild(evolutionCard());
    if (!state.sport && data.by_sport.length > 1) root.appendChild(sportBreakdown(data.by_sport));
    root.appendChild(calendarCard());

    U.setView(root);
    requestAnimationFrame(() => {
      Charts.applyTheme();
      buildEvolutionCharts();
      buildTrainingLoad();
      buildHrTrends();
      buildWellness();
    });
  }

  // ---- header + sport control ----
  function pageHead() {
    const sel = U.el("select", { id: "in-sport" }, [U.el("option", { value: "", text: "All sports" })]);
    data.sports.forEach((sp) => sel.appendChild(U.el("option", { value: sp, text: U.cap(sp) })));
    sel.value = state.sport;
    sel.addEventListener("change", () => { state.sport = sel.value; render(); });

    return U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: "Insights" }),
        U.el("div", { class: "sub", text: "Your accomplishments and how they’ve grown over time — computed locally." }),
      ]),
      U.el("div", { class: "head-actions" }, [
        U.el("div", { class: "field inline" }, [U.el("label", { text: "Sport" }), sel]),
      ]),
    ]);
  }

  // ---- hero accomplishment tiles ----
  function heroTiles(t) {
    const tiles = U.el("div", { class: "stats", style: "margin-bottom:var(--sp-5)" });
    const tile = (label, value, unit) =>
      tiles.appendChild(U.el("div", { class: "tile" }, [
        U.el("div", { class: "label", text: label }),
        U.el("div", { class: "value tnum", html: `${value}${unit ? ` <span>${unit}</span>` : ""}` }),
      ]));
    tile("Activities", t.count, "");
    tile("Total distance", U.fmtKm(t.distance_m), "km");
    tile("Total time", U.fmtDuration(t.duration_s), "");
    tile("Total ascent", Math.round(t.ascent_m).toLocaleString(), "m");
    tile("Active days", t.active_days, "");
    tile("Longest streak", t.longest_streak_days, t.longest_streak_days === 1 ? "day" : "days");
    return tiles;
  }

  // ---- personal records ----
  function recordsRow(records) {
    const defs = [
      ["longest_distance", "Longest distance", (v) => `${U.fmtKm(v)} km`],
      ["longest_duration", "Longest activity", (v) => U.fmtDuration(v)],
      ["most_ascent", "Biggest climb", (v) => `${Math.round(v)} m`],
      ["fastest_avg_speed", "Fastest avg speed", (v) => `${U.fmtSpeedKmh(v)} km/h`],
    ];
    const cards = defs
      .filter(([key]) => records[key])
      .map(([key, label, fmt]) => {
        const r = records[key];
        return U.el("div", {
          class: "record-card",
          title: "Open this activity",
          onclick: () => (location.hash = "#/activity/" + r.id),
        }, [
          U.el("div", { class: "rl", text: label }),
          U.el("div", { class: "rv tnum", text: fmt(r.value) }),
          U.el("div", { class: "rm", text: `${U.cap(r.sport || "—")} · ${U.fmtDate(r.start_time)}` }),
        ]);
      });
    if (!cards.length) return null;
    return U.el("div", { class: "records", style: "margin-bottom:var(--sp-5)" }, cards);
  }

  // ---- evolution charts ----
  function evolutionCard() {
    const wrap = U.el("div", { class: "charts" });
    wrap.appendChild(chartBox("Distance per month", "in-month", "--accent"));
    wrap.appendChild(chartBox("Cumulative distance", "in-cumulative", "--accent-2"));
    return wrap;
  }

  function chartBox(title, canvasId, colorVar) {
    return U.el("div", { class: "card chart-card" }, [
      U.el("h3", {}, [
        U.el("span", { class: "swatch", style: `background:var(${colorVar})` }),
        document.createTextNode(title),
      ]),
      U.el("div", { class: "chart-box" }, [U.el("canvas", { id: canvasId })]),
    ]);
  }

  function buildEvolutionCharts() {
    const months = data.by_month;
    if (!months.length) return;
    const labels = months.map((m) => monthLabel(m.month));
    const perMonthKm = months.map((m) => +(m.distance_m / 1000).toFixed(1));
    let running = 0;
    const cumulativeKm = months.map((m) => +(running += m.distance_m / 1000).toFixed(1));

    const bar = document.getElementById("in-month");
    if (bar) Charts.makeBar(bar, labels, perMonthKm, U.cssVar("--accent"), { unit: " km" });
    const area = document.getElementById("in-cumulative");
    if (area) Charts.makeArea(area, labels, cumulativeKm, U.cssVar("--accent-2"), { unit: " km" });
  }

  // ---- training load: Fitness (CTL) / Fatigue (ATL) / Form (TSB) ----
  function trainingLoadCard() {
    if (!load || !load.series || !load.series.length) return null;  // hide when no data
    const cur = load.current || {};
    return U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
      U.el("div", { class: "cal-head" }, [
        U.el("h3", { style: "font-size:14px;color:var(--text-dim)", text: "Training load (Fitness / Fatigue / Form)" }),
        U.el("div", { class: "sub", style: "color:var(--text-dim);font-size:13px", text: `CTL ${load.ctl_days}d · ATL ${load.atl_days}d` }),
      ]),
      tlNow(cur),
      U.el("div", { class: "chart-box", style: "height:280px;margin-top:var(--sp-4)" }, [U.el("canvas", { id: "tl-canvas" })]),
      U.el("div", { style: "margin-top:var(--sp-3);font-size:12.5px;color:var(--text-dim);line-height:1.5", text: tlLegend() }),
      U.el("div", { style: "margin-top:4px;font-size:12px;color:var(--text-faint);line-height:1.5", text: tlNote() }),
    ]);
  }

  function tlNow(cur) {
    const tiles = U.el("div", { class: "stats" });
    const tile = (label, value) =>
      tiles.appendChild(U.el("div", { class: "tile" }, [
        U.el("div", { class: "label", text: label }),
        U.el("div", { class: "value tnum", text: value }),
      ]));
    tile("Fitness (CTL)", fmt1(cur.ctl));
    tile("Fatigue (ATL)", fmt1(cur.atl));
    tile("Form (TSB)", fmt1(cur.tsb));
    return tiles;
  }

  function buildTrainingLoad() {
    if (!load || !load.series || !load.series.length) return;
    const canvas = document.getElementById("tl-canvas");
    if (!canvas) return;
    const labels = load.series.map((d) => d.date);
    Charts.makeMultiLine(canvas, labels, [
      { label: "Fitness (CTL)", data: load.series.map((d) => d.ctl), color: U.cssVar("--accent"), fill: true },
      { label: "Fatigue (ATL)", data: load.series.map((d) => d.atl), color: U.cssVar("--accent-2") },
      { label: "Form (TSB)", data: load.series.map((d) => d.tsb), color: U.cssVar("--hr"), axis: "y1", dashed: true },
    ]);
  }

  // Plain-language legend so the three lines are readable without prior knowledge.
  function tlLegend() {
    return "Fitness (CTL) is your slow ~6-week training load, Fatigue (ATL) your recent ~1-week load, " +
      "and Form (TSB, right axis) is yesterday's fitness minus fatigue — positive means fresh, negative means loaded.";
  }

  // Honest note about the unit and what backed each day.
  function tlNote() {
    const c = load.coverage || { activities: 0, scored: 0, basis: {} };
    const b = c.basis || {};
    const mix = ["power", "hr", "duration"]
      .filter((k) => b[k]).map((k) => `${b[k]} ${k === "hr" ? "HR" : k}`);
    let note = `Unit: ${String(load.unit).toUpperCase()} · scored ${c.scored} of ${c.activities} activities` +
      (mix.length ? ` (${mix.join(", ")})` : "") +
      ". An open, local approximation — not Garmin's proprietary FirstBeat figures.";
    if (load.needs && load.needs.length) {
      const labels = { ftp_w: "FTP", max_heart_rate: "max HR" };
      note += " Set your " + load.needs.map((n) => labels[n] || n).join(" and ") + " in config for sharper numbers.";
    }
    return note;
  }

  function fmt1(v) {
    return (v === null || v === undefined) ? "—" : Number(v).toFixed(1);
  }

  // ---- heart-rate & efficiency trends ----
  function hrTrendsCard() {
    if (!hr || !hr.points || !hr.points.length) return null;  // hide when no HR data
    const s = hr.summary || {};
    const tiles = U.el("div", { class: "stats" });
    const tile = (label, value, unit) => tiles.appendChild(U.el("div", { class: "tile" }, [
      U.el("div", { class: "label", text: label }),
      U.el("div", { class: "value tnum", html: `${value}${unit ? ` <span>${unit}</span>` : ""}` }),
    ]));
    tile("Observed max HR", s.observed_max_hr ?? "—", "bpm");
    tile("Average HR", s.avg_hr ?? "—", "bpm");
    tile("Activities with HR", s.with_hr ?? 0, "");

    const charts = U.el("div", { class: "charts", style: "margin-top:var(--sp-4)" });
    charts.appendChild(chartBox("Heart rate over time", "in-hr", "--hr"));
    if (hr.ef_basis) charts.appendChild(chartBox("Efficiency factor (aerobic fitness)", "in-ef", "--accent-2"));

    return U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
      U.el("div", { class: "cal-head" }, [
        U.el("h3", { style: "font-size:14px;color:var(--text-dim)", text: "Heart rate & efficiency trends" }),
      ]),
      tiles,
      charts,
      U.el("div", { style: "margin-top:var(--sp-3);font-size:12px;color:var(--text-faint)", text: hrNote() }),
    ]);
  }

  function buildHrTrends() {
    if (!hr || !hr.points || !hr.points.length) return;
    const labels = hr.points.map((p) => p.date);
    const hrCanvas = document.getElementById("in-hr");
    if (hrCanvas) Charts.makeMultiLine(hrCanvas, labels, [
      { label: "Avg HR", data: hr.points.map((p) => p.avg_hr), color: U.cssVar("--hr"), fill: true },
      { label: "Max HR", data: hr.points.map((p) => p.max_hr), color: U.cssVar("--speed") },
    ], { unit: " bpm" });
    if (hr.ef_basis) {
      const efCanvas = document.getElementById("in-ef");
      if (efCanvas) Charts.makeArea(efCanvas, labels, hr.points.map((p) => p.efficiency), U.cssVar("--accent-2"), {});
    }
  }

  function hrNote() {
    if (hr.ef_basis === "mixed")
      return "Efficiency Factor mixes power- and pace-based activities — filter by sport to compare like with like.";
    const unit = hr.ef_basis === "power" ? "W/bpm" : hr.ef_basis === "pace" ? "m/min per bpm" : null;
    let n = "Efficiency Factor is output per heartbeat; a rising trend means improving aerobic fitness.";
    if (unit) n += ` Unit: ${unit}.`;
    return n;
  }

  // ---- wellness & readiness (from monitoring files) ----
  function wellnessCard() {
    if (!wellness || !wellness.days || !wellness.days.length) return null;
    const days = wellness.days;
    const latest = days[days.length - 1];
    const tiles = U.el("div", { class: "stats" });
    const tile = (label, value, unit) => tiles.appendChild(U.el("div", { class: "tile" }, [
      U.el("div", { class: "label", text: label }),
      U.el("div", { class: "value tnum", html: `${value}${unit ? ` <span>${unit}</span>` : ""}` }),
    ]));
    tile("Latest steps", latest.steps != null ? latest.steps.toLocaleString() : "—", "");
    tile("Resting HR", latest.resting_hr != null ? latest.resting_hr : "—", "bpm");
    tile("Avg stress", latest.avg_stress != null ? latest.avg_stress : "—", "");

    const charts = U.el("div", { class: "charts", style: "margin-top:var(--sp-4)" });
    charts.appendChild(chartBox("Steps per day", "in-steps", "--accent"));
    charts.appendChild(chartBox("Resting & average HR", "in-whr", "--hr"));

    return U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
      U.el("div", { class: "cal-head" }, [
        U.el("h3", { style: "font-size:14px;color:var(--text-dim)", text: "Wellness & readiness" }),
        U.el("div", { class: "sub", style: "color:var(--text-dim);font-size:13px", text: `${days.length} day${days.length === 1 ? "" : "s"} from your watch` }),
      ]),
      tiles,
      charts,
      U.el("div", { style: "margin-top:var(--sp-3);font-size:12px;color:var(--text-faint)",
        text: "From monitoring files (steps, all-day heart rate, stress). Resting HR is the day's minimum. Sleep, HRV and SpO₂ need richer decoding and aren't shown yet." }),
    ]);
  }

  function buildWellness() {
    if (!wellness || !wellness.days || !wellness.days.length) return;
    const days = wellness.days;
    const labels = days.map((d) => d.date);
    const steps = document.getElementById("in-steps");
    if (steps) Charts.makeBar(steps, labels, days.map((d) => d.steps || 0), U.cssVar("--accent"), {});
    const whr = document.getElementById("in-whr");
    if (whr) Charts.makeMultiLine(whr, labels, [
      { label: "Resting HR", data: days.map((d) => d.resting_hr), color: U.cssVar("--hr"), fill: true },
      { label: "Avg HR", data: days.map((d) => d.avg_hr), color: U.cssVar("--accent-2") },
    ], { unit: " bpm" });
  }

  // ---- all-time best times per distance ----
  function bestTimesCard() {
    if (!records || !records.records || !records.records.length) return null;
    const pace = (s) => (s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);
    const thead = U.el("thead", {}, [U.el("tr", {}, ["Distance", "Time", "Pace", "When"].map((h) => U.el("th", { text: h })))]);
    const tbody = U.el("tbody");
    records.records.forEach((r) => {
      tbody.appendChild(U.el("tr", {
        style: r.activity_id != null ? "cursor:pointer" : "cursor:default",
        onclick: () => { if (r.activity_id != null) location.hash = "#/activity/" + r.activity_id; },
      }, [
        U.el("td", { text: r.label }),
        U.el("td", { class: "tnum", text: U.fmtDuration(r.time_s) }),
        U.el("td", { class: "tnum", html: `${pace(r.pace_s_per_km)} <span class="muted">/km</span>` }),
        U.el("td", { class: "tnum", text: U.fmtDate(r.date) }),
      ]));
    });
    return U.el("div", { class: "card", style: "margin-bottom:var(--sp-5)" }, [
      U.el("h3", { style: "font-size:14px;color:var(--text-dim);padding:var(--sp-4) var(--sp-4) 0", text: "Best times (all-time)" }),
      U.el("div", { class: "table-wrap" }, [U.el("table", {}, [thead, tbody])]),
    ]);
  }

  // ---- possible duplicates (cross-source, report only) ----
  function dupsCard() {
    if (!dups || !dups.groups || !dups.groups.length) return null;
    const groups = dups.groups.map((g) =>
      U.el("div", { style: "border:1px solid var(--border-soft);border-radius:8px;padding:var(--sp-3);margin-bottom:var(--sp-3)" }, [
        U.el("div", { style: "font-weight:600;font-size:13px;margin-bottom:4px", text: `${g.count} copies of one effort` }),
        ...g.activities.map((a) => U.el("div", { style: "font-size:13px;color:var(--text-dim);padding:2px 0" }, [
          U.el("a", { href: "#/activity/" + a.id, text: `${U.fmtDate(a.start_time)} · ${U.cap(a.sport || "—")}` }),
          U.el("span", { style: "color:var(--text-faint)", text: `  ${U.fmtKm(a.distance_m)} km · ${U.fmtDuration(a.duration_s)} · ${a.device || "unknown source"}` }),
        ])),
      ]));
    return U.el("div", { class: "card pad", style: "margin-bottom:var(--sp-5)" }, [
      U.el("h3", { style: "font-size:14px;color:var(--text-dim);margin-bottom:var(--sp-2)", text: "Possible duplicates" }),
      U.el("div", { style: "font-size:13px;color:var(--text-dim);margin-bottom:var(--sp-3)",
        text: `${dups.duplicate_groups} group${dups.duplicate_groups === 1 ? "" : "s"} (${dups.duplicate_activities} activities) look like the same effort from different sources. Review and remove extras yourself — nothing is deleted automatically.` }),
      ...groups,
    ]);
  }

  // ---- per-sport breakdown ----
  function sportBreakdown(bySport) {
    const max = Math.max(...bySport.map((s) => s.distance_m), 1);
    const rows = bySport.map((s) => {
      const pct = Math.max(2, (s.distance_m / max) * 100);
      return U.el("div", { class: "sport-row" }, [
        U.el("div", { class: "sport-name", html: `<span class="dot"></span>${U.cap(s.sport)}` }),
        U.el("div", { class: "sport-bar" }, [U.el("div", { class: "fill", style: `width:${pct}%` })]),
        U.el("div", { class: "sport-fig tnum", html: `${U.fmtKm(s.distance_m)} <span class="muted">km</span> · ${s.count}` }),
      ]);
    });
    return U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
      U.el("h3", { style: "margin-bottom:var(--sp-4);font-size:14px;color:var(--text-dim)", text: "By sport" }),
      U.el("div", { class: "sport-list" }, rows),
    ]);
  }

  // ---- calendar heatmap ----
  function calendarCard() {
    const yearSel = U.el("select", { id: "in-year" },
      data.years.map((y) => U.el("option", { value: y, text: y })));
    yearSel.value = state.year;
    const grid = U.el("div", { id: "cal-host" });
    yearSel.addEventListener("change", () => { state.year = yearSel.value; renderHeatmap(grid); });

    const card = U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
      U.el("div", { class: "cal-head" }, [
        U.el("h3", { style: "font-size:14px;color:var(--text-dim)", text: "Activity calendar" }),
        U.el("div", { class: "field inline" }, [U.el("label", { text: "Year" }), yearSel]),
      ]),
      grid,
    ]);
    renderHeatmap(grid);
    return card;
  }

  function renderHeatmap(host) {
    host.innerHTML = "";
    const year = state.year || String(new Date().getFullYear());
    const byDate = {};
    data.calendar.forEach((c) => { if (c.date.startsWith(year)) byDate[c.date] = c; });
    const max = Math.max(0, ...Object.values(byDate).map((c) => c.distance_m));

    const level = (c) => {
      if (!c || !c.count) return 0;
      if (max <= 0) return 2;
      const f = c.distance_m / max;
      return f > 0.66 ? 4 : f > 0.33 ? 3 : 2;
    };

    const grid = U.el("div", { class: "cal-grid" });
    const start = new Date(Date.UTC(+year, 0, 1));
    for (let i = 0; i < start.getUTCDay(); i++) grid.appendChild(U.el("div", { class: "cal-cell empty" }));
    const end = new Date(Date.UTC(+year, 11, 31));
    for (const d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
      const iso = d.toISOString().slice(0, 10);
      const c = byDate[iso];
      const km = c ? (c.distance_m / 1000).toFixed(1) : "0";
      const title = c
        ? `${iso}: ${c.count} activit${c.count === 1 ? "y" : "ies"}, ${km} km`
        : `${iso}: rest day`;
      grid.appendChild(U.el("div", { class: "cal-cell lvl" + level(c), title }));
    }
    host.appendChild(grid);
    host.appendChild(U.el("div", { class: "cal-legend" }, [
      U.el("span", { text: "Less" }),
      ...[0, 2, 3, 4].map((l) => U.el("span", { class: "cal-cell lvl" + l })),
      U.el("span", { text: "More" }),
    ]));
  }

  // ---- misc ----
  function monthLabel(ym) {
    const [y, m] = ym.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "short", year: "2-digit" });
  }

  function emptyState() {
    return U.el("div", { class: "empty" }, [
      U.el("div", { class: "ic", html:
        '<svg viewBox="0 0 24 24" width="46" height="46" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg>' }),
      U.el("div", { html: "<strong>No insights yet</strong>" }),
      U.el("div", { text: "Import some activities and your stats, records and trends will appear here.", style: "margin:6px 0 16px" }),
      U.el("a", { class: "btn primary", href: "#/sync", text: "Go to Sync" }),
    ]);
  }

  return { render };
})();

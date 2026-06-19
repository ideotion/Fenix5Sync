/* Insights: accomplishments, statistics, evolution-over-time and a calendar
   heatmap — all computed locally by /api/insights. Charts use the vendored
   Chart.js via the shared Charts module; the heatmap is plain DOM + CSS. */
const Insights = (() => {
  let state = { sport: "", year: "" };
  let data = null;

  async function render() {
    Charts.destroyAll();
    U.setView(U.spinner("Crunching your numbers…"));
    try {
      data = await API.insights(state.sport || undefined);
    } catch (e) {
      U.setView(U.el("div", { class: "empty", text: "Could not load insights: " + e.message }));
      return;
    }
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
    root.appendChild(evolutionCard());
    if (!state.sport && data.by_sport.length > 1) root.appendChild(sportBreakdown(data.by_sport));
    root.appendChild(calendarCard());

    U.setView(root);
    requestAnimationFrame(() => {
      Charts.applyTheme();
      buildEvolutionCharts();
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

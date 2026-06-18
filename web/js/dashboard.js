/* Dashboard: summary tiles, filter controls, and the activity table. */
const Dashboard = (() => {
  const state = {
    date_from: "", date_to: "", sport: "",
    min_km: "", max_km: "", min_min: "",
    sort: "start_time", order: "desc",
  };

  async function render() {
    const root = U.el("div");

    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: "Dashboard" }),
        U.el("div", { class: "sub", id: "dash-sub", text: "Your local activity library" }),
      ]),
      U.el("div", { class: "head-actions" }, [
        U.el("a", { class: "btn primary", href: "#/sync", html:
          '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg> Sync now' }),
      ]),
    ]));

    // stat tiles
    const tiles = U.el("div", { class: "stats", id: "tiles", style: "margin-bottom:var(--sp-5)" });
    ["Activities", "Total distance", "Total time"].forEach((label) =>
      tiles.appendChild(U.el("div", { class: "tile" }, [
        U.el("div", { class: "label", text: label }),
        U.el("div", { class: "value skeleton", html: "&nbsp;", style: "height:30px;width:90px" }),
      ]))
    );
    root.appendChild(tiles);

    // filters
    root.appendChild(buildFilters());

    // table
    const tableCard = U.el("div", { class: "card", id: "table-card", style: "margin-top:var(--sp-4)" },
      [U.el("div", { class: "table-wrap", id: "table-wrap" }, [U.spinner("Loading activities…")])]);
    root.appendChild(tableCard);

    U.setView(root);
    await Promise.all([loadStats(), loadActivities()]);
  }

  function buildFilters() {
    const field = (label, inputAttrs) =>
      U.el("div", { class: "field" }, [
        U.el("label", { text: label }),
        U.el(inputAttrs.tag || "input", inputAttrs),
      ]);

    const apply = () => {
      ["date_from", "date_to", "sport", "min_km", "max_km", "min_min"].forEach((id) => {
        const node = document.getElementById("f-" + id);
        if (node) state[id] = node.value;
      });
      loadActivities();
    };
    const reset = () => {
      Object.assign(state, { date_from: "", date_to: "", sport: "", min_km: "", max_km: "", min_min: "" });
      render();
    };

    const card = U.el("div", { class: "card" }, [
      U.el("div", { class: "filters" }, [
        field("From", { id: "f-date_from", type: "date", value: state.date_from }),
        field("To", { id: "f-date_to", type: "date", value: state.date_to }),
        U.el("div", { class: "field" }, [
          U.el("label", { text: "Sport" }),
          U.el("select", { id: "f-sport" }, [U.el("option", { value: "", text: "All sports" })]),
        ]),
        field("Min distance (km)", { id: "f-min_km", type: "number", min: "0", step: "0.1", value: state.min_km, placeholder: "0" }),
        field("Max distance (km)", { id: "f-max_km", type: "number", min: "0", step: "0.1", value: state.max_km, placeholder: "∞" }),
        field("Min duration (min)", { id: "f-min_min", type: "number", min: "0", step: "1", value: state.min_min, placeholder: "0" }),
        U.el("div", { class: "field" }, [
          U.el("label", { html: "&nbsp;" }),
          U.el("div", { class: "actions" }, [
            U.el("button", { class: "btn primary", text: "Apply", onclick: apply }),
            U.el("button", { class: "btn ghost", text: "Reset", onclick: reset }),
          ]),
        ]),
      ]),
    ]);
    return card;
  }

  async function loadStats() {
    try {
      const s = await API.stats();
      const tiles = document.getElementById("tiles");
      tiles.innerHTML = "";
      const tile = (label, value, unit) =>
        U.el("div", { class: "tile" }, [
          U.el("div", { class: "label", text: label }),
          U.el("div", { class: "value tnum", html: `${value} <span>${unit || ""}</span>` }),
        ]);
      tiles.appendChild(tile("Activities", s.count, ""));
      tiles.appendChild(tile("Total distance", U.fmtKm(s.total_distance_m), "km"));
      tiles.appendChild(tile("Total time", U.fmtDuration(s.total_duration_s), ""));

      // populate sport select
      const sel = document.getElementById("f-sport");
      if (sel) {
        s.sports.forEach((sp) =>
          sel.appendChild(U.el("option", { value: sp, text: U.cap(sp) }))
        );
        sel.value = state.sport;
      }
    } catch (e) { U.toast("Failed to load stats: " + e.message, "bad"); }
  }

  function apiParams() {
    return {
      date_from: state.date_from || null,
      date_to: state.date_to || null,
      sport: state.sport || null,
      min_distance: state.min_km ? Number(state.min_km) * 1000 : null,
      max_distance: state.max_km ? Number(state.max_km) * 1000 : null,
      min_duration: state.min_min ? Number(state.min_min) * 60 : null,
      sort: state.sort, order: state.order, limit: 500,
    };
  }

  async function loadActivities() {
    const wrap = document.getElementById("table-wrap");
    try {
      const data = await API.listActivities(apiParams());
      const sub = document.getElementById("dash-sub");
      if (sub) sub.textContent = `${data.total} activit${data.total === 1 ? "y" : "ies"} match your filters`;
      wrap.innerHTML = "";
      if (!data.items.length) {
        wrap.appendChild(emptyState());
        return;
      }
      wrap.appendChild(buildTable(data.items));
    } catch (e) {
      wrap.innerHTML = "";
      wrap.appendChild(U.el("div", { class: "empty", text: "Could not load activities: " + e.message }));
    }
  }

  function header(label, key) {
    const active = state.sort === key;
    const arrow = active ? (state.order === "asc" ? " ↑" : " ↓") : "";
    return U.el("th", {
      text: label + arrow,
      style: "cursor:pointer;user-select:none",
      onclick: () => {
        if (state.sort === key) state.order = state.order === "asc" ? "desc" : "asc";
        else { state.sort = key; state.order = "desc"; }
        loadActivities();
        // refresh header arrows
        Dashboard._rerenderHeaders();
      },
    });
  }

  let _tableEl = null;
  function buildTable(items) {
    const thead = U.el("thead", {}, [U.el("tr", {}, [
      header("Date", "start_time"),
      U.el("th", { text: "Sport" }),
      header("Distance", "total_distance"),
      header("Time", "total_timer_time"),
      header("Avg HR", "avg_heart_rate"),
      U.el("th", { text: "Ascent" }),
    ])]);
    const tbody = U.el("tbody");
    items.forEach((a) => {
      tbody.appendChild(U.el("tr", { onclick: () => (location.hash = "#/activity/" + a.id) }, [
        U.el("td", { class: "tnum", text: U.fmtDateTime(a.start_time) }),
        U.el("td", {}, [U.el("span", { class: "badge", html: `<span class="dot"></span>${U.cap(a.sport || "—")}` })]),
        U.el("td", { class: "tnum", html: `${U.fmtKm(a.total_distance_m)} <span class="muted">km</span>` }),
        U.el("td", { class: "tnum", text: U.fmtDuration(a.total_timer_time_s) }),
        U.el("td", { class: "tnum", text: a.avg_heart_rate_bpm ?? "—" }),
        U.el("td", { class: "tnum", html: a.total_ascent_m != null ? `${a.total_ascent_m} <span class="muted">m</span>` : "—" }),
      ]));
    });
    _tableEl = U.el("table", {}, [thead, tbody]);
    return _tableEl;
  }

  function emptyState() {
    return U.el("div", { class: "empty" }, [
      U.el("div", { class: "ic", html:
        '<svg viewBox="0 0 24 24" width="46" height="46" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 17l5-7 4 5 3-4 6 8z"/><circle cx="17.5" cy="6.5" r="1.6"/></svg>' }),
      U.el("div", { html: "<strong>No activities yet</strong>" }),
      U.el("div", { text: "Connect your Fenix 5 and run a sync to import activities.", style: "margin:6px 0 16px" }),
      U.el("a", { class: "btn primary", href: "#/sync", text: "Go to Sync" }),
    ]);
  }

  // Re-render headers in place (cheap) so sort arrows update.
  function _rerenderHeaders() {
    // The table is rebuilt by loadActivities(); nothing extra needed here.
  }

  return { render, _rerenderHeaders };
})();

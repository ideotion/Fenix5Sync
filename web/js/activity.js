/* Activity detail: summary stats, HR/speed/elevation charts, offline GPS track,
   laps table and per-activity export. */
const ActivityView = (() => {
  let currentId = null;     // active activity id (for async re-fetches like splits)
  let splitsUnit = "km";    // user-tweakable split distance

  async function render(id) {
    currentId = id;
    Charts.destroyAll();
    U.setView(U.spinner("Loading activity…"));
    let a;
    try {
      a = await API.getActivity(id);
    } catch (e) {
      U.setView(U.el("div", { class: "empty" }, [
        U.el("div", { html: "<strong>Activity not found</strong>" }),
        U.el("a", { class: "btn", href: "#/dashboard", text: "Back to dashboard", style: "margin-top:12px" }),
      ]));
      return;
    }

    const root = U.el("div");
    root.appendChild(U.el("a", { class: "back-link", href: "#/dashboard", html:
      '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg> Dashboard' }));

    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: `${U.cap(a.sport || "Activity")}${a.sub_sport && a.sub_sport !== "generic" ? " · " + U.cap(a.sub_sport) : ""}` }),
        U.el("div", { class: "sub", text: `${U.fmtDateTime(a.start_time)}  ·  ${a.device_manufacturer || ""} ${a.device_product || ""}`.trim() }),
      ]),
      U.el("div", { class: "head-actions" }, exportControls(a)),
    ]));

    root.appendChild(metaGrid(a));

    // charts
    const chartsWrap = U.el("div", { class: "charts", style: "margin-top:var(--sp-5)" });
    chartsWrap.appendChild(chartCard("Heart rate", "--hr", "hr-canvas", "bpm"));
    chartsWrap.appendChild(chartCard("Speed", "--speed", "spd-canvas", "km/h"));
    root.appendChild(chartsWrap);
    root.appendChild(chartCard("Elevation", "--elev-line", "ele-canvas", "m", true));

    // performance metrics + training zones (loaded async; hidden until ready)
    root.appendChild(metricsCard());
    root.appendChild(zonesCard());

    // track
    root.appendChild(U.el("div", { class: "card track-card", style: "margin-top:var(--sp-5)" }, [
      U.el("h3", { class: "", style: "font-size:14px;color:var(--text-dim);margin-bottom:var(--sp-3)", text: "GPS track" }),
      U.el("div", { class: "track-box" }, [U.el("canvas", { id: "track-canvas" })]),
    ]));

    root.appendChild(splitsCard());
    root.appendChild(bestEffortsCard());
    if (a.laps && a.laps.length > 1) root.appendChild(lapsCard(a.laps));

    U.setView(root);
    loadMetrics(a.id);
    loadZones(a.id);
    loadSplits(a.id);
    loadBestEfforts(a.id);

    // Build visuals after layout so canvas sizes are known.
    requestAnimationFrame(() => {
      Charts.applyTheme();
      const tps = a.trackpoints || [];
      buildChart("hr-canvas", Charts.series(tps, "heart_rate_bpm"), U.cssVar("--hr"), { unit: "" });
      buildChart("spd-canvas", Charts.series(tps, "speed_mps", (v) => +(v * 3.6).toFixed(1)), U.cssVar("--speed"), { unit: "" });
      buildChart("ele-canvas", Charts.series(tps, "altitude_m"), U.cssVar("--elev-line"), { unit: "", fill: true });
      const tc = document.getElementById("track-canvas");
      if (tc) Track.draw(tc, tps);
    });
  }

  function buildChart(canvasId, data, color, opts) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (!data.length) {
      const box = canvas.closest(".chart-box");
      if (box) box.innerHTML = '<div class="empty" style="padding:var(--sp-5)">No data</div>';
      return;
    }
    Charts.makeLine(canvas, data, color, opts);
  }

  function chartCard(title, colorVar, canvasId, unit, full) {
    return U.el("div", { class: "card chart-card", style: full ? "margin-top:var(--sp-5)" : "" }, [
      U.el("h3", {}, [
        U.el("span", { class: "swatch", style: `background:var(${colorVar})` }),
        document.createTextNode(title),
      ]),
      U.el("div", { class: "chart-box" }, [U.el("canvas", { id: canvasId })]),
    ]);
  }

  function metaGrid(a) {
    const items = [];
    const add = (k, v) => { if (v !== null && v !== undefined && v !== "—") items.push([k, v]); };
    add("Distance", `${U.fmtKm(a.total_distance_m)} km`);
    add("Moving time", U.fmtDuration(a.total_timer_time_s));
    if ((a.sport || "").toLowerCase() === "running")
      add("Avg pace", `${U.fmtPace(a.avg_speed_mps)} /km`);
    add("Avg speed", `${U.fmtSpeedKmh(a.avg_speed_mps)} km/h`);
    add("Avg HR", a.avg_heart_rate_bpm != null ? `${a.avg_heart_rate_bpm} bpm` : null);
    add("Max HR", a.max_heart_rate_bpm != null ? `${a.max_heart_rate_bpm} bpm` : null);
    add("Ascent", a.total_ascent_m != null ? `${a.total_ascent_m} m` : null);
    add("Calories", a.total_calories != null ? `${a.total_calories} kcal` : null);
    add("Avg power", a.avg_power_w != null ? `${a.avg_power_w} W` : null);
    add("Avg cadence", a.avg_cadence_rpm != null ? `${a.avg_cadence_rpm} rpm` : null);
    add("Avg temp", a.avg_temperature_c != null ? `${a.avg_temperature_c}°C` : null);

    return U.el("div", { class: "card pad" }, [
      U.el("div", { class: "meta-grid" }, items.map(([k, v]) =>
        U.el("div", { class: "meta" }, [
          U.el("div", { class: "k", text: k }),
          U.el("div", { class: "v tnum", text: String(v) }),
        ])
      )),
    ]);
  }

  function lapsCard(laps) {
    const thead = U.el("thead", {}, [U.el("tr", {}, ["#", "Distance", "Time", "Avg HR", "Avg speed", "Ascent"].map((h) => U.el("th", { text: h })))]);
    const tbody = U.el("tbody");
    laps.forEach((l, i) => {
      tbody.appendChild(U.el("tr", { style: "cursor:default" }, [
        U.el("td", { class: "tnum", text: i + 1 }),
        U.el("td", { class: "tnum", html: `${U.fmtKm(l.total_distance_m)} <span class="muted">km</span>` }),
        U.el("td", { class: "tnum", text: U.fmtDuration(l.total_timer_time_s) }),
        U.el("td", { class: "tnum", text: l.avg_heart_rate_bpm ?? "—" }),
        U.el("td", { class: "tnum", text: `${U.fmtSpeedKmh(l.avg_speed_mps)} km/h` }),
        U.el("td", { class: "tnum", html: l.total_ascent_m != null ? `${l.total_ascent_m} <span class="muted">m</span>` : "—" }),
      ]));
    });
    return U.el("div", { class: "card", style: "margin-top:var(--sp-5)" }, [
      U.el("h3", { style: "font-size:14px;color:var(--text-dim);padding:var(--sp-4) var(--sp-4) 0", text: "Laps" }),
      U.el("div", { class: "table-wrap" }, [U.el("table", {}, [thead, tbody])]),
    ]);
  }

  // ---- performance metrics (intensity / efficiency / pace / dynamics / …) ----
  function metricsCard() {
    return U.el("div", { class: "card pad", id: "metrics-card", style: "margin-top:var(--sp-5);display:none" }, [
      U.el("h3", { style: "font-size:14px;color:var(--text-dim);margin-bottom:var(--sp-4)", text: "Performance metrics" }),
      U.el("div", { id: "metrics-host" }),
    ]);
  }

  async function loadMetrics(id) {
    let m;
    try { m = await API.activityMetrics(id); } catch (_) { return; }
    if (!m || !m.available) return;  // nothing to show -> leave the card hidden
    const host = document.getElementById("metrics-host");
    const card = document.getElementById("metrics-card");
    if (!host || !card) return;

    const pace = (s) => (s == null ? null : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);
    const efUnit = m.efficiency && m.efficiency.basis === "power" ? "W/bpm" : "m/min·bpm";

    const groups = [
      m.intensity && ["Intensity", [
        ["Normalized power", m.intensity.np_w, "W"],
        ["Intensity factor", m.intensity.intensity_factor, ""],
        ["Variability index", m.intensity.variability_index, ""],
        ["Training stress", m.intensity.tss, "TSS"],
        ["Avg power", m.intensity.avg_power_w, "W"],
      ]],
      m.efficiency && ["Efficiency & endurance", [
        ["Efficiency factor", m.efficiency.efficiency_factor, efUnit],
        ["Aerobic decoupling", m.efficiency.decoupling_pct, "%"],
      ]],
      m.pace && ["Pace", [
        ["Avg pace", pace(m.pace.avg_pace_s_per_km), "/km"],
        ["Grade-adjusted pace", pace(m.pace.gap_pace_s_per_km), "/km"],
      ]],
      m.dynamics && ["Dynamics", [
        ["Peak acceleration", m.dynamics.max_acceleration_mps2, "m/s²"],
        ["Avg cadence", m.dynamics.avg_cadence, m.dynamics.cadence_unit],
        ["Max cadence", m.dynamics.max_cadence, m.dynamics.cadence_unit],
        ["Stride length", m.dynamics.stride_length_m, "m"],
      ]],
      m.heart_rate && ["Heart rate", [
        ["Avg HR", m.heart_rate.avg_bpm, "bpm"],
        ["Max HR", m.heart_rate.max_bpm, "bpm"],
        ["HR drift", m.heart_rate.drift_pct, "%"],
      ]],
      m.environment && ["Environment", [
        ["Avg temp", m.environment.avg_temp_c, "°C"],
        ["Min temp", m.environment.min_temp_c, "°C"],
        ["Max temp", m.environment.max_temp_c, "°C"],
      ]],
    ];

    const blocks = groups.map((g) => g && metricGroup(g[0], g[1])).filter(Boolean);
    if (!blocks.length) return;
    blocks.forEach((b) => host.appendChild(b));
    if (m.needs && m.needs.length) {
      const labels = { ftp_w: "FTP" };
      host.appendChild(U.el("div", {
        style: "margin-top:var(--sp-2);font-size:12px;color:var(--text-faint)",
        text: "Set your " + m.needs.map((n) => labels[n] || n).join(", ") +
          " in config to unlock Intensity Factor & TSS.",
      }));
    }
    card.style.display = "";
  }

  function metricGroup(title, rows) {
    const items = rows.filter(([, v]) => v !== null && v !== undefined);
    if (!items.length) return null;
    return U.el("div", { style: "margin-bottom:var(--sp-4)" }, [
      U.el("div", {
        style: "font-size:11.5px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:var(--sp-3)",
        text: title,
      }),
      U.el("div", { class: "meta-grid" }, items.map(([k, v, u]) =>
        U.el("div", { class: "meta" }, [
          U.el("div", { class: "k", text: k }),
          U.el("div", { class: "v tnum", text: `${v}${u ? " " + u : ""}` }),
        ])
      )),
    ]);
  }

  // ---- splits (even-distance segments; km/mile is user-tweakable) ----
  function splitsCard() {
    const sel = U.el("select", { id: "splits-unit" }, [
      U.el("option", { value: "km", text: "per km" }),
      U.el("option", { value: "mi", text: "per mile" }),
    ]);
    sel.value = splitsUnit;
    sel.addEventListener("change", () => { splitsUnit = sel.value; loadSplits(currentId); });
    return U.el("div", { class: "card pad", id: "splits-card", style: "margin-top:var(--sp-5);display:none" }, [
      U.el("div", { class: "cal-head" }, [
        U.el("h3", { style: "font-size:14px;color:var(--text-dim)", text: "Splits" }),
        U.el("div", { class: "field inline" }, [U.el("label", { text: "Distance" }), sel]),
      ]),
      U.el("div", { class: "chart-box", id: "splits-chart-box", style: "height:200px;margin-bottom:var(--sp-4)" }),
      U.el("div", { class: "table-wrap", id: "splits-table" }),
    ]);
  }

  const _pace = (s) => (s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);

  async function loadSplits(id) {
    let s;
    try { s = await API.activitySplits(id, splitsUnit); } catch (_) { return; }
    const card = document.getElementById("splits-card");
    const tableHost = document.getElementById("splits-table");
    if (!card || !tableHost) return;
    if (!s.splits || !s.splits.length) { card.style.display = "none"; return; }
    card.style.display = "";
    const u = s.unit;
    const per = u === "mi" ? 1609.344 : 1000;

    const thead = U.el("thead", {}, [U.el("tr", {},
      ["#", "Distance", "Time", "Pace", "Avg HR", "Elev"].map((h) => U.el("th", { text: h })))]);
    const tbody = U.el("tbody");
    s.splits.forEach((sp) => {
      const tag = sp.index === s.fastest_index ? " ⚡" : sp.index === s.slowest_index ? " 🐌" : "";
      tbody.appendChild(U.el("tr", { style: "cursor:default" }, [
        U.el("td", { class: "tnum", text: sp.index }),
        U.el("td", { class: "tnum", html: `${(sp.distance_m / per).toFixed(2)} <span class="muted">${u}</span>` }),
        U.el("td", { class: "tnum", text: U.fmtDuration(sp.time_s) }),
        U.el("td", { class: "tnum", html: `${_pace(sp.pace_s_per_km)} <span class="muted">/${u}</span>${tag}` }),
        U.el("td", { class: "tnum", text: sp.avg_hr_bpm ?? "—" }),
        U.el("td", { class: "tnum", html: `+${Math.round(sp.elev_gain_m)} <span class="muted">m</span>` }),
      ]));
    });
    tableHost.innerHTML = "";
    tableHost.appendChild(U.el("table", {}, [thead, tbody]));

    // Pace-per-split bars (shorter = faster). Rebuild the canvas so re-toggling units is clean.
    const box = document.getElementById("splits-chart-box");
    if (box) {
      box.innerHTML = "";
      const canvas = U.el("canvas", { id: "splits-canvas" });
      box.appendChild(canvas);
      const labels = s.splits.map((sp) => sp.index);
      const mins = s.splits.map((sp) => (sp.pace_s_per_km != null ? +(sp.pace_s_per_km / 60).toFixed(2) : 0));
      Charts.makeBar(canvas, labels, mins, U.cssVar("--accent"), { unit: ` min/${u}` });
    }
  }

  // ---- best efforts + mean-max curve ----
  function bestEffortsCard() {
    return U.el("div", { class: "card pad", id: "efforts-card", style: "margin-top:var(--sp-5);display:none" }, [
      U.el("h3", { style: "font-size:14px;color:var(--text-dim);margin-bottom:var(--sp-4)", text: "Best efforts" }),
      U.el("div", { id: "efforts-table" }),
      U.el("div", { class: "chart-box", id: "efforts-chart-box", style: "height:200px;margin-top:var(--sp-4)" }),
      U.el("div", { id: "efforts-note", style: "margin-top:var(--sp-2);font-size:12px;color:var(--text-faint)" }),
    ]);
  }

  async function loadBestEfforts(id) {
    let e;
    try { e = await API.activityBestEfforts(id); } catch (_) { return; }
    const card = document.getElementById("efforts-card");
    if (!card) return;
    const hasDist = e.best_distances && e.best_distances.length;
    const curve = (e.power_curve && e.power_curve.length) ? { kind: "power", data: e.power_curve }
      : (e.speed_curve && e.speed_curve.length) ? { kind: "speed", data: e.speed_curve } : null;
    if (!hasDist && !curve) return;  // nothing to show -> leave hidden
    card.style.display = "";

    const tableHost = document.getElementById("efforts-table");
    tableHost.innerHTML = "";
    if (hasDist) {
      const thead = U.el("thead", {}, [U.el("tr", {}, ["Distance", "Time", "Pace"].map((h) => U.el("th", { text: h })))]);
      const tbody = U.el("tbody");
      e.best_distances.forEach((b) => {
        tbody.appendChild(U.el("tr", { style: "cursor:default" }, [
          U.el("td", { text: b.label }),
          U.el("td", { class: "tnum", text: U.fmtDuration(b.time_s) }),
          U.el("td", { class: "tnum", html: `${_pace(b.pace_s_per_km)} <span class="muted">/km</span>` }),
        ]));
      });
      tableHost.appendChild(U.el("div", { class: "table-wrap" }, [U.el("table", {}, [thead, tbody])]));
    }

    const box = document.getElementById("efforts-chart-box");
    const note = document.getElementById("efforts-note");
    if (box && curve) {
      box.style.display = "";
      box.innerHTML = "";
      const canvas = U.el("canvas", { id: "efforts-canvas" });
      box.appendChild(canvas);
      const labels = curve.data.map((p) => p.label);
      if (curve.kind === "power") {
        Charts.makeBar(canvas, labels, curve.data.map((p) => p.watts), U.cssVar("--speed"), { unit: " W" });
        if (note) note.textContent = "Mean-max power — best average watts sustained for each duration.";
      } else {
        Charts.makeBar(canvas, labels, curve.data.map((p) => +(p.speed_mps * 3.6).toFixed(1)), U.cssVar("--accent"), { unit: " km/h" });
        if (note) note.textContent = "Mean-max speed — best average pace held for each duration (≈1 Hz).";
      }
    } else if (box) {
      box.style.display = "none";
      if (note) note.textContent = "";
    }
  }

  // ---- training zones (HR + power) ----
  function zonesCard() {
    return U.el("div", { class: "card pad", id: "zones-card", style: "margin-top:var(--sp-5);display:none" }, [
      U.el("h3", { style: "font-size:14px;color:var(--text-dim);margin-bottom:var(--sp-4)", text: "Training zones" }),
      U.el("div", { id: "zones-host" }),
    ]);
  }

  async function loadZones(id) {
    let z;
    try { z = await API.activityZones(id); } catch (_) { return; }
    const host = document.getElementById("zones-host");
    const card = document.getElementById("zones-card");
    if (!host || !card) return;

    const blocks = [];
    if (z.hr && z.hr.zones && z.hr.zones.length) {
      const note = z.hr.basis === "observed"
        ? `max ${z.hr.max_heart_rate} bpm · observed (set yours in config)`
        : `max ${z.hr.max_heart_rate} bpm`;
      blocks.push(zoneBlock("Heart rate", z.hr.zones, "--hr", note));
    }
    if (z.power && z.power.zones && z.power.zones.length) {
      blocks.push(zoneBlock("Power", z.power.zones, "--speed", `FTP ${z.power.ftp_w} W`));
    } else if (z.power && z.power.needs_ftp) {
      blocks.push(U.el("div", { class: "sub", text: "Set your FTP in config to see power zones." }));
    }
    if (!blocks.length) return;  // nothing to show -> leave the card hidden

    blocks.forEach((b) => host.appendChild(b));
    card.style.display = "";
  }

  function zoneBlock(title, zones, colorVar, caption) {
    const maxPct = Math.max(...zones.map((z) => z.percent), 1);
    const rows = zones.map((z) =>
      U.el("div", { class: "zone-row" }, [
        U.el("div", { class: "zone-name", text: z.name }),
        U.el("div", { class: "zone-bar" }, [
          U.el("div", { class: "fill", style: `width:${Math.max(2, (z.percent / maxPct) * 100)}%;background:var(${colorVar})` }),
        ]),
        U.el("div", { class: "zone-fig tnum", html: `${z.percent}% <span class="muted">${U.fmtDuration(z.seconds)}</span>` }),
      ])
    );
    return U.el("div", { class: "zone-block" }, [
      U.el("div", { class: "zone-head" }, [
        U.el("span", { class: "swatch", style: `background:var(${colorVar})` }),
        document.createTextNode(title),
        caption ? U.el("span", { class: "zone-cap muted", text: caption }) : null,
      ]),
      U.el("div", { class: "zone-list" }, rows),
    ]);
  }

  function exportControls(a) {
    const id = a.id;
    let anon = false;
    const rawExt = ((a.extra && a.extra.source_format && a.extra.source_format.value) || "fit").toLowerCase();

    // Original raw file: lossless and Garmin-native, but cannot be anonymized.
    const rawBtn = U.el("button", {
      class: "btn sm",
      text: "Original",
      title: `Download the original .${rawExt} file (lossless; cannot be anonymized)`,
      onclick: () => {
        U.download(API.activityExportUrl(id, "raw", false), `activity-${id}.${rawExt}`);
        U.toast("Downloading original file…");
      },
    });

    const cb = U.el("input", { type: "checkbox" });
    cb.addEventListener("change", () => {
      anon = cb.checked;
      rawBtn.disabled = anon;
      rawBtn.title = anon
        ? "Disabled while anonymizing — the original file can't be scrubbed"
        : `Download the original .${rawExt} file (lossless; cannot be anonymized)`;
    });
    const toggle = U.el("label", {
      class: "anon-toggle",
      title: "Scrub GPS near start/end and strip device & personal data on export",
    }, [cb, U.el("span", { text: "Anonymize" })]);

    const fmtBtns = ["csv", "json", "gpx", "tcx"].map((fmt) =>
      U.el("button", {
        class: "btn sm",
        text: fmt.toUpperCase(),
        title: "Export as " + fmt.toUpperCase() + (fmt === "tcx" ? " — Garmin Connect / Strava" : fmt === "gpx" ? " — universal" : ""),
        onclick: () => {
          U.download(API.activityExportUrl(id, fmt, anon), `activity-${id}.${fmt}`);
          U.toast(`Exporting ${fmt.toUpperCase()}${anon ? " (anonymized)" : ""}…`);
        },
      })
    );
    return [toggle, ...fmtBtns, rawBtn];
  }

  return { render };
})();

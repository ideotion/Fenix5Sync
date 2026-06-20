/* Activity detail: summary stats, HR/speed/elevation charts, offline GPS track,
   laps table and per-activity export. */
const ActivityView = (() => {
  async function render(id) {
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

    // training zones (loaded async; hidden until there's something to show)
    root.appendChild(zonesCard());

    // track
    root.appendChild(U.el("div", { class: "card track-card", style: "margin-top:var(--sp-5)" }, [
      U.el("h3", { class: "", style: "font-size:14px;color:var(--text-dim);margin-bottom:var(--sp-3)", text: "GPS track" }),
      U.el("div", { class: "track-box" }, [U.el("canvas", { id: "track-canvas" })]),
    ]));

    if (a.laps && a.laps.length > 1) root.appendChild(lapsCard(a.laps));

    U.setView(root);
    loadZones(a.id);

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

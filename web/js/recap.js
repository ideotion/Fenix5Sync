/* Year in Sport: a private, local recap computed from the archive. Renders an
   on-screen card and exports a self-contained, shareable HTML file (inline CSS +
   data, no account, no network). Why it exists is documented discreetly at the
   foot of the page (web/content/recap/about.json). */
const RecapView = (() => {
  let about = null;

  const km = (m) => (m / 1000).toFixed(m >= 100000 ? 0 : 1);
  const hrs = (s) => (s / 3600).toFixed(s >= 36000 ? 0 : 1);
  const dateStr = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined,
    { year: "numeric", month: "short", day: "numeric" }) : "—");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const titleCase = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "—");

  function tile(value, label, sub) {
    return `<div class="rc-tile"><div class="rc-val">${value}</div>` +
      `<div class="rc-lbl">${label}</div>${sub ? `<div class="rc-sub">${sub}</div>` : ""}</div>`;
  }

  function bars(items, label, valueOf, fmt) {
    const max = Math.max(1, ...items.map(valueOf));
    const rows = items.map((it) => {
      const v = valueOf(it);
      const pct = Math.round((v / max) * 100);
      return `<div class="rc-bar-row"><span class="rc-bar-k">${esc(it.name || it.year)}</span>` +
        `<span class="rc-bar-track"><span class="rc-bar-fill" style="width:${pct}%"></span></span>` +
        `<span class="rc-bar-v">${v ? fmt(v) : ""}</span></div>`;
    }).join("");
    return `<div class="rc-bars"><div class="rc-bars-h">${label}</div>${rows}</div>`;
  }

  function highlightRow(h, label, fmt) {
    if (!h || !h.value) return "";
    return `<li><span class="rc-hl-k">${label}</span> <strong>${fmt(h.value)}</strong>` +
      `<span class="rc-hl-meta"> · ${titleCase(h.sport)} · ${dateStr(h.date)}</span></li>`;
  }

  /* Shared card markup — used both on-screen and inside the exported HTML file. */
  function cardInnerHTML(d) {
    const t = d.totals || {};
    const period = d.by_month
      ? bars(d.by_month, "By month", (m) => m.distance_m, (v) => km(v) + " km")
      : bars(d.by_year || [], "By year", (y) => y.distance_m, (v) => km(v) + " km");

    const tiles = [
      tile(km(t.distance_m) + " <small>km</small>", "Distance"),
      tile(hrs(t.duration_s) + " <small>h</small>", "Moving time"),
      tile(t.count, "Activities"),
      tile(Math.round(t.ascent_m).toLocaleString() + " <small>m</small>", "Elevation"),
      tile(d.active_days, "Active days"),
      tile(d.longest_streak_days, "Longest streak", "consecutive days"),
    ].join("");

    const hl = d.highlights || {};
    const highlights = [
      highlightRow(hl.longest_distance, "Longest distance", (v) => km(v) + " km"),
      highlightRow(hl.longest_duration, "Longest activity", (v) => hrs(v) + " h"),
      highlightRow(hl.biggest_climb, "Biggest climb", (v) => Math.round(v) + " m"),
      highlightRow(hl.fastest_avg_speed, "Fastest average", (v) => (v * 3.6).toFixed(1) + " km/h"),
    ].join("");

    const sports = (d.by_sport || []).slice(0, 6).map((s) =>
      `<div class="rc-bar-row"><span class="rc-bar-k">${esc(titleCase(s.sport))}</span>` +
      `<span class="rc-bar-v">${s.count} · ${km(s.distance_m)} km · ${hrs(s.duration_s)} h</span></div>`
    ).join("");

    let extra = "";
    if (d.biggest_day) {
      extra += `<p class="rc-note">Biggest day: <strong>${km(d.biggest_day.distance_m)} km</strong> ` +
        `across ${d.biggest_day.count} activit${d.biggest_day.count === 1 ? "y" : "ies"} on ${dateStr(d.biggest_day.date)}.</p>`;
    }
    if (d.busiest_month) {
      extra += `<p class="rc-note">Busiest month: <strong>${esc(d.busiest_month.name)}</strong> ` +
        `(${d.busiest_month.count} activities).</p>`;
    }
    if (d.comparison) {
      const c = d.comparison;
      const sign = (n) => (n > 0 ? "+" : "");
      extra += `<p class="rc-note">vs ${c.prev_year}: <strong>${sign(c.distance_delta_m)}${km(c.distance_delta_m)} km</strong>, ` +
        `${sign(c.count_delta)}${c.count_delta} activities.</p>`;
    }

    return `<div class="rc-card">
      <div class="rc-card-head"><div class="rc-brand">Fenix5Sync</div>
        <h2 class="rc-period">${esc(d.period)}</h2>
        <div class="rc-range">${dateStr(d.first_activity)} – ${dateStr(d.last_activity)}${d.primary_sport ? " · mostly " + esc(d.primary_sport) : ""}</div>
      </div>
      <div class="rc-tiles">${tiles}</div>
      ${highlights ? `<div class="rc-hl"><h3>Highlights</h3><ul>${highlights}</ul></div>` : ""}
      <div class="rc-cols">
        <div class="rc-col">${period}</div>
        <div class="rc-col"><div class="rc-bars"><div class="rc-bars-h">By sport</div>${sports || '<div class="rc-bar-row">—</div>'}</div></div>
      </div>
      ${extra}
      <div class="rc-foot">Generated locally by Fenix5Sync · your data never left this machine</div>
    </div>`;
  }

  const EXPORT_CSS = `
    :root{--bg:#0e1116;--card:#171b22;--ink:#e8eaed;--mut:#9aa3af;--acc:#ff5a1f;--line:#2a2f38}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
      font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:24px}
    .rc-card{max-width:760px;margin:0 auto;background:var(--card);border:1px solid var(--line);
      border-radius:16px;padding:28px;box-shadow:0 10px 40px rgba(0,0,0,.35)}
    .rc-brand{color:var(--acc);font-weight:700;letter-spacing:.04em;text-transform:uppercase;font-size:12px}
    .rc-period{margin:6px 0 2px;font-size:40px;line-height:1}.rc-range{color:var(--mut);font-size:13px}
    .rc-tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0}
    .rc-tile{background:#0e1116;border:1px solid var(--line);border-radius:12px;padding:14px}
    .rc-val{font-size:26px;font-weight:700}.rc-val small{font-size:14px;color:var(--mut);font-weight:600}
    .rc-lbl{color:var(--mut);font-size:12px;margin-top:2px}.rc-sub{color:var(--mut);font-size:11px;opacity:.8}
    .rc-hl h3,.rc-bars-h{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);margin:0 0 8px}
    .rc-hl ul{list-style:none;padding:0;margin:0 0 18px}.rc-hl li{padding:5px 0;border-bottom:1px solid var(--line)}
    .rc-hl-k{color:var(--mut)}.rc-hl-meta{color:var(--mut);font-size:12px}
    .rc-cols{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:6px 0 4px}
    @media(max-width:620px){.rc-cols,.rc-tiles{grid-template-columns:1fr 1fr}}
    .rc-bar-row{display:flex;align-items:center;gap:8px;font-size:13px;padding:3px 0}
    .rc-bar-k{width:74px;color:var(--mut);flex:none}.rc-bar-track{flex:1;height:8px;background:#0e1116;border-radius:6px;overflow:hidden}
    .rc-bar-fill{display:block;height:100%;background:var(--acc)}.rc-bar-v{flex:none;color:var(--ink);font-variant-numeric:tabular-nums}
    .rc-note{color:var(--mut);font-size:13px;margin:6px 0 0}.rc-foot{margin-top:20px;color:var(--mut);font-size:11px;text-align:center}`;

  function exportHTML(d) {
    return `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">` +
      `<meta name="viewport" content="width=device-width,initial-scale=1">` +
      `<title>Fenix5Sync — ${esc(d.period)} recap</title><style>${EXPORT_CSS}</style></head>` +
      `<body>${cardInnerHTML(d)}</body></html>`;
  }

  async function fetchRecap(year) {
    return API.recap(year);
  }

  async function render() {
    U.setView(U.spinner("Building your recap…"));
    if (about === null) {
      try { about = await (await fetch("/content/recap/about.json")).json(); }
      catch (_) { about = {}; }
    }
    let data;
    try { data = await fetchRecap(null); }
    catch (e) { U.setView(U.el("div", { class: "empty", text: "Could not build recap: " + e.message })); return; }

    if (!data.totals || data.totals.count === 0) {
      U.setView(U.el("div", { class: "empty" }, [
        U.el("div", { text: "No activities yet — import some from the watch, then come back for your recap." }),
      ]));
      return;
    }
    draw(data);
  }

  function draw(data) {
    const root = U.el("div", { class: "rc" });

    // Header: title + period picker + export.
    const picker = U.el("select", { onchange: async (e) => {
      const val = e.target.value;
      const d = await fetchRecap(val === "all" ? null : val);
      cardHost.innerHTML = cardInnerHTML(d);
      current = d;
    } }, [U.el("option", { value: "all", text: "All time" }),
      ...(data.available_years || []).map((y) => U.el("option", { value: y, text: String(y) }))]);

    let current = data;
    const exportBtn = U.el("button", { class: "btn", onclick: () => {
      const blob = new Blob([exportHTML(current)], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      U.download(url, `fenix5sync-recap-${current.year || "all-time"}.html`);
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      U.toast("Recap saved — a self-contained HTML file, yours to keep or share.", "good");
    } }, [U.el("span", { text: "Export recap (.html)" })]);

    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: about.title || "Year in Sport" }),
        U.el("div", { class: "sub", text: about.subtitle || "" }),
      ]),
      U.el("div", { class: "head-actions" }, [
        U.el("div", { class: "field inline" }, [U.el("label", { text: "Period" }), picker]),
        exportBtn,
      ]),
    ]));

    const cardHost = U.el("div", { class: "rc-host" });
    cardHost.innerHTML = cardInnerHTML(current);
    root.appendChild(cardHost);

    // Discreet "why this is here" + sources.
    if (about.rationale || (about.sources || []).length) {
      root.appendChild(U.el("details", { class: "card pad rc-about" }, [
        U.el("summary", { text: "Why this is here" }),
        about.rationale ? U.el("p", { class: "sub", text: about.rationale }) : null,
        (about.sources || []).length ? U.el("ul", { class: "rc-srcs" }, about.sources.map((s) =>
          U.el("li", {}, [
            U.el("a", { href: s.url, target: "_blank", rel: "noopener", text: s.title }),
            document.createTextNode(` — ${s.publisher}${s.date ? " (" + s.date + ")" : ""}`),
          ])
        )) : null,
      ]));
    }

    U.setView(root);
  }

  return { render };
})();

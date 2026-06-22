/* Import / Sync view: trigger acquisition+parse, stream live progress over SSE,
   and show the final run summary (found / imported / skipped / failed). */
const SyncView = (() => {
  let es = null;

  function cleanup() {
    if (es) { try { es.close(); } catch (_) {} es = null; }
  }

  async function render() {
    cleanup();
    const root = U.el("div");
    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: "Import / Sync" }),
        U.el("div", { class: "sub", text: "Read new activities from your connected Fenix 5. The device is never modified." }),
      ]),
    ]));

    const btn = U.el("button", { class: "btn primary", id: "sync-btn", html:
      '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg> Sync now',
      onclick: start });

    root.appendChild(U.el("div", { class: "card pad sync-hero" }, [
      U.el("div", { style: "display:flex;gap:var(--sp-3);align-items:center;flex-wrap:wrap" }, [
        btn,
        U.el("span", { class: "sub", text: "Auto-detects USB mass-storage or MTP. Configure a source path in Logs/Config if needed." }),
      ]),
      U.el("div", { class: "progress" }, [U.el("div", { class: "bar", id: "sync-bar" })]),
      U.el("div", { class: "sync-status", id: "sync-status", text: "Idle." }),
    ]));

    root.appendChild(await exportPanel());
    root.appendChild(salvagePanel());

    const summary = U.el("div", { id: "sync-summary", style: "margin-top:var(--sp-5);display:none" });
    root.appendChild(summary);

    U.setView(root);

    // Resume a sync already in progress (e.g. navigated away and back).
    try {
      const active = await API.activeSync();
      if (active && active.status === "running") attach(active.job_id);
    } catch (_) {}
  }

  async function exportPanel() {
    let about = {};
    try { about = await (await fetch("/content/history/about.json")).json(); } catch (_) {}

    const input = U.el("input", { type: "text", id: "export-path",
      style: "flex:1;min-width:240px",
      placeholder: "Choose a Garmin/Strava export .zip or folder…" });
    const browse = U.el("button", { class: "btn", onclick: async () => {
      const picked = await Picker.open({ mode: "any", exts: [".zip"], title: "Choose your account export" });
      if (picked) input.value = picked;
    } }, [U.el("span", { text: "Browse…" })]);
    const btn = U.el("button", { class: "btn primary", id: "export-btn", onclick: () => startExport(input.value) },
      [U.el("span", { text: "Import history" })]);

    const details = (about.rationale || (about.sources || []).length)
      ? U.el("details", { class: "rc-about", style: "margin-top:var(--sp-3)" }, [
          U.el("summary", { text: "Why this is here" }),
          about.rationale ? U.el("p", { class: "sub", text: about.rationale }) : null,
          (about.sources || []).length ? U.el("ul", { class: "rc-srcs" }, about.sources.map((s) =>
            U.el("li", {}, [
              U.el("a", { href: s.url, target: "_blank", rel: "noopener", text: s.title }),
              document.createTextNode(` — ${s.publisher}${s.date ? " (" + s.date + ")" : ""}`),
            ]))) : null,
        ])
      : null;

    return U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
      U.el("h3", { style: "margin:0 0 4px", text: about.title || "Liberate your history" }),
      U.el("div", { class: "sub", text: "Import your full Garmin/Strava account export (the downloaded .zip or folder). Nested zips and gzipped files are handled; the source is never modified and everything is de-duplicated." }),
      U.el("div", { class: "browse-row", style: "margin-top:var(--sp-3)" }, [input, browse, btn]),
      details,
    ]);
  }

  async function startExport(path) {
    if (!path || !path.trim()) { U.toast("Enter the path to your export .zip or folder.", "bad"); return; }
    const btn = document.getElementById("export-btn");
    if (btn) btn.disabled = true;
    setStatus("Expanding export…");
    setBar(4);
    try {
      const job = await API.startExportImport(path.trim());
      attach(job.job_id);
    } catch (e) {
      U.toast("Import failed to start: " + e.message, "bad");
      if (btn) btn.disabled = false;
      setStatus("Idle.");
    }
  }

  function salvagePanel() {
    const input = U.el("input", { type: "text", id: "salvage-path", style: "flex:1;min-width:240px",
      placeholder: "Choose a corrupt or truncated .FIT file…" });
    const browse = U.el("button", { class: "btn", onclick: async () => {
      const picked = await Picker.open({ mode: "file", exts: [".fit"], title: "Choose a .FIT file to recover" });
      if (picked) input.value = picked;
    } }, [U.el("span", { text: "Browse…" })]);
    const out = U.el("div", { class: "salvage-out", style: "margin-top:var(--sp-3)" });

    const attempt = U.el("button", { class: "btn", id: "salvage-btn", onclick: async () => {
      const path = input.value.trim();
      if (!path) { U.toast("Choose a .FIT file to recover.", "bad"); return; }
      attempt.disabled = true; out.innerHTML = "";
      out.appendChild(U.spinner("Attempting recovery…"));
      try {
        const r = await API.salvage(path, false);
        renderReport(r, path);
      } catch (e) { out.innerHTML = ""; out.appendChild(U.el("div", { class: "sub", text: "Salvage failed: " + e.message })); }
      finally { attempt.disabled = false; }
    } }, [U.el("span", { text: "Attempt salvage" })]);

    function renderReport(r, path) {
      out.innerHTML = "";
      if (!r.ok) {
        out.appendChild(U.el("div", { class: "sub", text: `Could not recover this file (${r.reason}).` }));
        return;
      }
      const p = r.preview || {};
      out.appendChild(U.el("div", { class: "card pad" }, [
        U.el("div", {}, [
          U.el("strong", { text: `Recovered ${r.records_recovered} records ` }),
          U.el("span", { class: "sub", text: `(${r.recovery_pct}% of the data; stopped: ${r.reason}).` }),
        ]),
        p.trackpoints != null ? U.el("div", { class: "sub", style: "margin-top:4px",
          text: `Activity preview: ${U.cap(p.sport || "unknown")} · ${p.trackpoints} trackpoints · ${p.laps} laps · ${U.fmtDateTime(p.start_time)}` }) : null,
        p.trackpoints ? U.el("button", { class: "btn primary", style: "margin-top:var(--sp-3)", onclick: async (e) => {
          e.target.disabled = true;
          try {
            const r2 = await API.salvage(path, true);
            const imp = r2.imported || {};
            U.toast(imp.imported ? `Recovered activity imported.` : "Recovered, but it was already in your archive.", imp.imported ? "good" : "");
            onEnd({ status: "done", summary: imp });
          } catch (err) { U.toast("Import failed: " + err.message, "bad"); }
        } }, [U.el("span", { text: "Import recovered activity" })]) : null,
      ]));
    }

    return U.el("div", { class: "card pad", style: "margin-top:var(--sp-5)" }, [
      U.el("h3", { style: "margin:0 0 4px", text: "Recover a corrupt file" }),
      U.el("div", { class: "sub", text: "Your watch rebooted and left a file that won't import? Salvage recovers every readable record — locally, with your original untouched." }),
      U.el("div", { class: "browse-row", style: "margin-top:var(--sp-3)" }, [input, browse, attempt]),
      out,
    ]);
  }

  async function start() {
    const btn = document.getElementById("sync-btn");
    btn.disabled = true;
    setStatus("Starting…");
    setBar(4);
    try {
      const job = await API.startSync();
      attach(job.job_id);
    } catch (e) {
      U.toast("Sync failed to start: " + e.message, "bad");
      btn.disabled = false;
      setStatus("Idle.");
    }
  }

  function attach(jobId) {
    cleanup();
    const btn = document.getElementById("sync-btn");
    if (btn) btn.disabled = true;
    es = new EventSource(API.syncStreamUrl(jobId));
    es.onmessage = (ev) => {
      try { onEvent(JSON.parse(ev.data)); } catch (_) {}
    };
    es.addEventListener("end", (ev) => {
      try { onEnd(JSON.parse(ev.data)); } catch (_) {}
      cleanup();
    });
    es.onerror = () => {
      // Stream closed; fall back to a one-shot status poll.
      cleanup();
      API.syncStatus(jobId).then((s) => { if (s.status !== "running") onEnd(s); }).catch(() => {});
      const b = document.getElementById("sync-btn");
      if (b) b.disabled = false;
    };
  }

  function onEvent(e) {
    if (e.phase === "locating") { setStatus("Locating device…"); setBar(6); return; }
    if (e.phase === "scanning") { setStatus(`Found ${e.total} file(s). Importing…`); setBar(e.total ? 10 : 100); return; }
    if (e.total) {
      const pct = Math.max(10, Math.round((e.current / e.total) * 100));
      setBar(pct);
    }
    if (e.phase === "file") setStatus(`(${e.current}/${e.total}) reading ${e.filename}…`);
    if (e.phase === "file_done") setStatus(`(${e.current}/${e.total}) ${e.filename} — ${e.status}`);
  }

  function onEnd(snap) {
    const btn = document.getElementById("sync-btn");
    if (btn) btn.disabled = false;
    const ebtn = document.getElementById("export-btn");
    if (ebtn) ebtn.disabled = false;
    setBar(100);
    if (snap.status === "error") {
      setStatus("Error: " + (snap.error || "unknown"));
      U.toast("Sync error: " + (snap.error || "unknown"), "bad");
      return;
    }
    const s = snap.summary || {};
    setStatus(`Done — found ${s.found || 0}, imported ${s.imported || 0}, skipped ${s.skipped || 0}, failed ${s.failed || 0}.`);
    showSummary(s);
    if (s.imported > 0) U.toast(`Imported ${s.imported} new activit${s.imported === 1 ? "y" : "ies"}.`, "good");
    else if (s.found === 0) U.toast("No device or files found.", "");
    else U.toast("No new activities (all up to date).", "");
  }

  function showSummary(s) {
    const wrap = document.getElementById("sync-summary");
    if (!wrap) return;
    wrap.style.display = "block";
    wrap.innerHTML = "";
    const cards = U.el("div", { class: "summary-cards" });
    const card = (n, label, cls) =>
      U.el("div", { class: "card scard " + cls }, [
        U.el("div", { class: "n tnum", text: n ?? 0 }),
        U.el("div", { class: "l", text: label }),
      ]);
    cards.appendChild(card(s.found, "Found", "found"));
    cards.appendChild(card(s.imported, "Imported", "imported"));
    cards.appendChild(card(s.skipped, "Skipped", "skipped"));
    cards.appendChild(card(s.failed, "Failed", "failed"));
    wrap.appendChild(cards);

    if (s.errors && s.errors.length) {
      wrap.appendChild(U.el("div", { class: "card pad", style: "margin-top:var(--sp-4)" }, [
        U.el("h3", { style: "font-size:14px;color:var(--bad);margin-bottom:var(--sp-2)", text: "Errors" }),
        U.el("ul", { style: "margin:0;padding-left:18px;color:var(--text-dim)" },
          s.errors.map((e) => U.el("li", { text: e }))),
      ]));
    }
    if (s.imported > 0) {
      wrap.appendChild(U.el("a", { class: "btn primary", href: "#/dashboard", text: "View activities", style: "margin-top:var(--sp-4)" }));
    }
  }

  const setBar = (pct) => { const b = document.getElementById("sync-bar"); if (b) b.style.width = pct + "%"; };
  const setStatus = (t) => { const s = document.getElementById("sync-status"); if (s) s.textContent = t; };

  return { render, cleanup };
})();

/* Settings: edit the athlete thresholds that drive every analytic (HR/power
   zones, training load, per-activity metrics, VO2max). Saved locally via
   PUT /api/config. Values can be auto-filled from your own activity history
   (observed max HR) and from your watch's recorded profile (weight/height/
   gender/resting HR). */
const SettingsView = (() => {
  let cfg = null;
  let suggest = null;

  async function render() {
    U.setView(U.spinner("Loading settings…"));
    try {
      cfg = await API.getConfig();
    } catch (e) {
      U.setView(U.el("div", { class: "empty", text: "Could not load settings: " + e.message }));
      return;
    }
    try { suggest = await API.athleteSuggestions(); } catch (_) { suggest = null; }
    draw();
  }

  function draw() {
    const a = cfg.athlete || {};
    const root = U.el("div");
    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: "Settings" }),
        U.el("div", { class: "sub", text: "Athlete thresholds that power your analytics — stored locally, never uploaded." }),
      ]),
    ]));

    root.appendChild(U.el("div", { class: "card pad", style: "max-width:560px" }, [
      U.el("h3", { class: "set-title", text: "Athlete profile" }),
      thresholdField("set-maxhr", "Max heart rate", "bpm", a.max_heart_rate,
        "HR zones, training-load TRIMP and HR-based VO₂max.",
        suggest && suggest.observed_max_hr ? { label: `Use observed ${suggest.observed_max_hr}`, value: suggest.observed_max_hr } : null),
      thresholdField("set-resthr", "Resting heart rate", "bpm", a.resting_heart_rate,
        "Sharpens HR-reserve training load.",
        suggest && suggest.resting_heart_rate ? { label: `Use watch ${suggest.resting_heart_rate}`, value: suggest.resting_heart_rate } : null),
      thresholdField("set-ftp", "Functional Threshold Power", "W", a.ftp_w,
        "Unlocks power zones, Intensity Factor and TSS.", null),
      U.el("div", { class: "set-actions" }, [
        U.el("button", { class: "btn primary", id: "set-save", text: "Save", onclick: save }),
      ]),
    ]));

    const watch = watchPanel();
    if (watch) root.appendChild(watch);

    U.setView(root);
  }

  function thresholdField(id, label, unit, value, hint, suggestion) {
    const input = U.el("input", { id, type: "number", min: "1", step: "1", value: value ?? "" });
    const row = U.el("div", { class: "set-row" }, [
      input,
      U.el("span", { class: "set-unit", text: unit }),
    ]);
    if (suggestion) {
      row.appendChild(U.el("button", {
        class: "btn sm", text: suggestion.label,
        onclick: () => { input.value = suggestion.value; },
      }));
    }
    return U.el("div", { class: "set-field" }, [
      U.el("label", { for: id, text: label }),
      row,
      hint ? U.el("div", { class: "set-hint", text: hint }) : null,
    ]);
  }

  // Read-only panel showing what the watch's recorded profile contained.
  function watchPanel() {
    if (!suggest) return null;
    const rows = [];
    if (suggest.weight_kg) rows.push(["Weight", `${suggest.weight_kg} kg`]);
    if (suggest.height_m) rows.push(["Height", `${suggest.height_m} m`]);
    if (suggest.gender) rows.push(["Gender", U.cap(suggest.gender)]);
    if (suggest.observed_max_hr) rows.push(["Observed max HR", `${suggest.observed_max_hr} bpm`]);
    if (!rows.length) return null;
    return U.el("div", { class: "card pad", style: "max-width:560px;margin-top:var(--sp-5)" }, [
      U.el("h3", { class: "set-title", text: "Detected from your data" }),
      U.el("div", { class: "meta-grid" }, rows.map(([k, v]) =>
        U.el("div", { class: "meta" }, [
          U.el("div", { class: "k", text: k }),
          U.el("div", { class: "v tnum", text: v }),
        ])
      )),
      U.el("div", { class: "set-hint", style: "margin-top:var(--sp-3)",
        text: "From your activities and your watch's stored profile. Use the buttons above to apply." }),
    ]);
  }

  function readInt(id) {
    const v = document.getElementById(id).value.trim();
    if (v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
  }

  async function save() {
    const btn = document.getElementById("set-save");
    btn.disabled = true;
    cfg.athlete = {
      max_heart_rate: readInt("set-maxhr"),
      resting_heart_rate: readInt("set-resthr"),
      ftp_w: readInt("set-ftp"),
    };
    try {
      cfg = await API.putConfig(cfg);
      U.toast("Settings saved.", "good");
    } catch (e) {
      U.toast("Could not save: " + e.message, "bad");
    } finally {
      const b = document.getElementById("set-save");
      if (b) b.disabled = false;
    }
  }

  return { render };
})();

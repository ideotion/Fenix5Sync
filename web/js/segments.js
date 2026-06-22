/* Personal segments: capture a route from one of your activities and see every
   effort you've made on it — ranked, with a progress trend. Private and local:
   no leaderboard, no account, no cloud. Rationale + sources shown discreetly. */
const SegmentsView = (() => {
  let about = null;

  const paceStr = (s) => (s == null ? "—" :
    `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}/km`);

  async function loadAbout() {
    if (about === null) {
      try { about = await (await fetch("/content/segments/about.json")).json(); }
      catch (_) { about = {}; }
    }
  }

  async function render() {
    U.setView(U.spinner("Loading segments…"));
    await loadAbout();
    let segments, activities;
    try {
      segments = (await API.listSegments()).segments;
      activities = (await API.listActivities({ limit: 500 })).items || [];
    } catch (e) {
      U.setView(U.el("div", { class: "empty", text: "Could not load segments: " + e.message }));
      return;
    }
    draw(segments, activities.filter((a) => a.start_latitude_deg != null));
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

  function createForm(activities) {
    const sel = U.el("select", {},
      [U.el("option", { value: "", text: activities.length ? "Choose a GPS activity…" : "No GPS activities yet" }),
       ...activities.map((a) => U.el("option", { value: a.id,
         text: `${U.fmtDate(a.start_time)} · ${U.cap(a.sport || "activity")} · ${U.fmtKm(a.total_distance_m)} km` }))]);
    const name = U.el("input", { type: "text", placeholder: "Segment name (e.g. River loop)", maxlength: "120" });
    const btn = U.el("button", { class: "btn primary", onclick: async () => {
      if (!sel.value) { U.toast("Pick an activity to capture the route from.", "bad"); return; }
      if (!name.value.trim()) { U.toast("Give the segment a name.", "bad"); return; }
      btn.disabled = true;
      try {
        await API.createSegment({ activity_id: Number(sel.value), name: name.value.trim() });
        U.toast("Segment created.", "good");
        render();
      } catch (e) { U.toast("Could not create segment: " + e.message, "bad"); btn.disabled = false; }
    } }, [U.el("span", { text: "Create segment" })]);

    return U.el("div", { class: "card pad seg-create" }, [
      U.el("h3", { text: "New segment from an activity" }),
      U.el("div", { class: "sub", text: "The route is captured from the chosen activity, then matched against your history." }),
      U.el("div", { class: "seg-form" }, [
        U.el("div", { class: "field" }, [U.el("label", { text: "Activity" }), sel]),
        U.el("div", { class: "field" }, [U.el("label", { text: "Name" }), name]),
        btn,
      ]),
    ]);
  }

  function effortsPanel(seg, host) {
    host.innerHTML = "";
    host.appendChild(U.spinner("Matching your history…"));
    API.segmentEfforts(seg.id).then((data) => {
      host.innerHTML = "";
      if (!data.count) {
        host.appendChild(U.el("div", { class: "sub", text: "No matching efforts found yet." }));
        return;
      }
      const best = data.best;
      host.appendChild(U.el("div", { class: "seg-best sub" }, [
        document.createTextNode("Best: "),
        U.el("strong", { text: U.fmtDuration(best.time_s) }),
        document.createTextNode(` · ${paceStr(best.pace_s_per_km)} · ${U.fmtDate(best.date)} · ${data.count} effort${data.count === 1 ? "" : "s"}`),
      ]));

      const rows = data.leaderboard.map((e, i) => U.el("div", { class: "seg-row" + (i === 0 ? " seg-row-top" : "") }, [
        U.el("span", { class: "seg-rank", text: "#" + (i + 1) }),
        U.el("span", { class: "seg-time", text: U.fmtDuration(e.time_s) }),
        U.el("span", { class: "seg-pace", text: paceStr(e.pace_s_per_km) }),
        U.el("span", { class: "seg-hr", text: e.avg_hr ? e.avg_hr + " bpm" : "—" }),
        U.el("a", { class: "seg-date", href: "#/activity/" + e.activity_id, text: U.fmtDate(e.date) }),
      ]));
      host.appendChild(U.el("div", { class: "seg-board" }, [
        U.el("div", { class: "seg-row seg-head" }, [
          U.el("span", { text: "Rank" }), U.el("span", { text: "Time" }),
          U.el("span", { text: "Pace" }), U.el("span", { text: "Avg HR" }), U.el("span", { text: "Date" }),
        ]),
        ...rows,
      ]));
    }).catch((e) => { host.innerHTML = ""; host.appendChild(U.el("div", { class: "sub", text: "Could not load efforts: " + e.message })); });
  }

  function segmentCard(seg) {
    const panel = U.el("div", { class: "seg-efforts" });
    let open = false;
    const toggle = U.el("button", { class: "btn", onclick: () => {
      open = !open;
      panel.style.display = open ? "block" : "none";
      if (open && !panel.dataset.loaded) { effortsPanel(seg, panel); panel.dataset.loaded = "1"; }
    } }, [U.el("span", { text: "View efforts" })]);
    panel.style.display = "none";

    const del = U.el("button", { class: "btn ghost sm", title: "Delete segment", onclick: async () => {
      if (!confirm(`Delete segment "${seg.name}"? Your activities are untouched.`)) return;
      try { await API.deleteSegment(seg.id); U.toast("Segment deleted.", "good"); render(); }
      catch (e) { U.toast("Could not delete: " + e.message, "bad"); }
    } }, [U.el("span", { text: "Delete" })]);

    return U.el("div", { class: "card pad seg-card" }, [
      U.el("div", { class: "seg-card-head" }, [
        U.el("div", {}, [
          U.el("strong", { text: seg.name }),
          U.el("div", { class: "sub", text: `${U.cap(seg.sport || "any")} · ${U.fmtKm(seg.distance_m)} km · ${seg.waypoints.length} waypoints` }),
        ]),
        U.el("div", { class: "head-actions" }, [toggle, del]),
      ]),
      panel,
    ]);
  }

  function draw(segments, activities) {
    const root = U.el("div", { class: "seg" });
    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: about.title || "Segments" }),
        U.el("div", { class: "sub", text: about.subtitle || "" }),
      ]),
    ]));

    root.appendChild(createForm(activities));

    if (!segments.length) {
      root.appendChild(U.el("div", { class: "empty", text: "No segments yet — create one from an activity above." }));
    } else {
      const list = U.el("div", { class: "seg-list" });
      segments.forEach((s) => list.appendChild(segmentCard(s)));
      root.appendChild(list);
    }

    const ad = aboutDetails(); if (ad) root.appendChild(ad);
    U.setView(root);
  }

  return { render };
})();

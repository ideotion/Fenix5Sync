/* Server-side file/folder picker modal. Because the app runs on a loopback
   server, the browser can't hand the server a real path — so we let the server
   list local directories (read-only) and the user navigates here. Powers every
   "Browse…" button so a path never has to be typed.

   Picker.open({ mode, exts, start, title }) -> Promise<string|null>
     mode: "file" | "folder" | "any"   exts: [".zip", ...] | null (file filter)
   Resolves with the chosen absolute path, or null if cancelled. */
const Picker = (() => {
  function open(opts = {}) {
    const mode = opts.mode || "any";          // file | folder | any
    const exts = opts.exts || null;
    const dirsOnly = mode === "folder";
    const extsParam = exts ? exts.join(",") : null;

    return new Promise((resolve) => {
      let cur = opts.start || null;
      let settled = false;

      const overlay = U.el("div", { class: "pick-overlay" });
      const pathLabel = U.el("div", { class: "pick-path tnum" });
      const listEl = U.el("div", { class: "pick-list" });
      const quickEl = U.el("div", { class: "pick-quick" });

      function done(value) {
        if (settled) return;
        settled = true;
        document.removeEventListener("keydown", onKey);
        overlay.remove();
        resolve(value);
      }
      function onKey(e) { if (e.key === "Escape") done(null); }
      document.addEventListener("keydown", onKey);
      overlay.addEventListener("click", (e) => { if (e.target === overlay) done(null); });

      async function load(path) {
        listEl.innerHTML = "";
        listEl.appendChild(U.el("div", { class: "sub", text: "Loading…" }));
        let data;
        try { data = await API.fsList({ path, dirs_only: dirsOnly, exts: extsParam }); }
        catch (e) { listEl.innerHTML = ""; listEl.appendChild(U.el("div", { class: "sub", text: "Could not list folder: " + e.message })); return; }
        cur = data.path;
        pathLabel.textContent = data.path;
        renderQuick(data.quick);
        renderEntries(data);
      }

      function renderQuick(quick) {
        quickEl.innerHTML = "";
        (quick || []).forEach((q) => quickEl.appendChild(
          U.el("button", { class: "btn ghost sm", text: q.name, onclick: () => load(q.path) })));
      }

      function row(icon, name, cls, onclick) {
        return U.el("button", { class: "pick-row " + (cls || ""), onclick }, [
          U.el("span", { class: "pick-icon", html: icon }),
          U.el("span", { class: "pick-name", text: name }),
        ]);
      }
      const FOLDER = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h6l2 2h10v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/></svg>';
      const FILE = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2h8l4 4v16H6z"/><path d="M14 2v4h4"/></svg>';

      function renderEntries(data) {
        listEl.innerHTML = "";
        if (data.parent) listEl.appendChild(row(FOLDER, "..", "pick-up", () => load(data.parent)));
        if (data.error) listEl.appendChild(U.el("div", { class: "sub", text: "Some items couldn't be read here." }));
        if (!data.entries.length && !data.parent) listEl.appendChild(U.el("div", { class: "sub", text: "Empty." }));
        data.entries.forEach((e) => {
          if (e.is_dir) listEl.appendChild(row(FOLDER, e.name, "", () => load(e.path)));
          else listEl.appendChild(row(FILE, e.name, "pick-file", () => done(e.path)));
        });
      }

      const useFolderBtn = (mode === "folder" || mode === "any")
        ? U.el("button", { class: "btn primary", text: "Use this folder", onclick: () => done(cur) })
        : null;

      const modal = U.el("div", { class: "pick-modal" }, [
        U.el("div", { class: "pick-head" }, [
          U.el("strong", { text: opts.title || (mode === "folder" ? "Choose a folder" : "Choose a file or folder") }),
          U.el("button", { class: "btn ghost sm", text: "✕", title: "Close", onclick: () => done(null) }),
        ]),
        quickEl,
        pathLabel,
        listEl,
        U.el("div", { class: "pick-foot" }, [
          U.el("span", { class: "sub", text: mode === "file" ? "Click a file to select it." : "Open folders to navigate; click a file, or use the current folder." }),
          U.el("div", { class: "pick-actions" }, [
            U.el("button", { class: "btn ghost", text: "Cancel", onclick: () => done(null) }),
            useFolderBtn,
          ]),
        ]),
      ]);

      overlay.appendChild(modal);
      document.body.appendChild(overlay);
      load(cur);
    });
  }

  return { open };
})();

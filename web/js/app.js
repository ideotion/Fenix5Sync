/* App shell: hash router, nav highlighting, theme toggle, version badge. */
(() => {
  function parseRoute() {
    const hash = location.hash.replace(/^#\/?/, "");
    const [name, arg] = hash.split("/");
    return { name: name || "dashboard", arg };
  }

  function setActiveNav(name) {
    document.querySelectorAll("#nav a").forEach((a) => {
      a.classList.toggle("active", a.dataset.route === name);
    });
  }

  async function route() {
    // Tear down anything stateful from the previous view.
    SyncView.cleanup();
    Charts.destroyAll();

    const { name, arg } = parseRoute();
    setActiveNav(name === "activity" ? "dashboard" : name);

    try {
      switch (name) {
        case "dashboard": return await Dashboard.render();
        case "activity": return await ActivityView.render(arg);
        case "sync": return await SyncView.render();
        case "export": return await ExportView.render();
        case "logs": return await LogsView.render();
        default: location.hash = "#/dashboard";
      }
    } catch (e) {
      U.toast("Something went wrong: " + e.message, "bad");
      console.error(e);
    }
  }

  // ---- theme ----
  function initTheme() {
    const saved = localStorage.getItem("f5s-theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    updateThemeIcon(saved);
  }
  function toggleTheme() {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("f5s-theme", next);
    updateThemeIcon(next);
    route(); // re-render so charts/track adopt the new palette
  }
  function updateThemeIcon(theme) {
    const icon = document.getElementById("theme-icon");
    if (!icon) return;
    icon.innerHTML = theme === "dark"
      ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>'
      : '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>';
  }

  async function loadVersion() {
    try {
      const h = await API.health();
      const v = document.getElementById("app-version");
      if (v) v.textContent = "v" + h.version;
    } catch (_) {}
  }

  window.addEventListener("hashchange", route);
  window.addEventListener("DOMContentLoaded", () => {
    initTheme();
    document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
    if (!location.hash) location.hash = "#/dashboard";
    loadVersion();
    route();
  });
})();

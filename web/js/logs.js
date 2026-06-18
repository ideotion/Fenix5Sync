/* Logs view: surface the latest run log from the local server. */
const LogsView = (() => {
  async function render() {
    const root = U.el("div");
    root.appendChild(U.el("div", { class: "page-head" }, [
      U.el("div", {}, [
        U.el("h1", { text: "Logs" }),
        U.el("div", { class: "sub", text: "Today's run log (also written to a dated file on disk)." }),
      ]),
      U.el("div", { class: "head-actions" }, [
        U.el("button", { class: "btn sm", text: "Refresh", onclick: load }),
      ]),
    ]));
    root.appendChild(U.el("div", { class: "logs", id: "log-box" }, [U.spinner("Loading logs…")]));
    U.setView(root);
    load();
  }

  async function load() {
    const box = document.getElementById("log-box");
    if (!box) return;
    try {
      const data = await API.logs(500);
      box.innerHTML = "";
      if (!data.lines.length) {
        box.appendChild(U.el("div", { class: "empty", text: "No log entries yet today." }));
        return;
      }
      data.lines.forEach((line) => {
        const m = line.match(/\b(ERROR|WARNING|INFO|DEBUG)\b/);
        const cls = m ? "lvl-" + m[1] : "";
        box.appendChild(U.el("div", { class: cls, text: line }));
      });
      box.scrollTop = box.scrollHeight;
    } catch (e) {
      box.innerHTML = "";
      box.appendChild(U.el("div", { class: "empty", text: "Could not load logs: " + e.message }));
    }
  }

  return { render };
})();

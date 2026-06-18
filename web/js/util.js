/* Small DOM + formatting helpers and a toast. Shared via the global `U`. */
const U = (() => {
  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on") && typeof v === "function")
        node.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    (Array.isArray(children) ? children : [children]).forEach((c) => {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  const view = () => document.getElementById("view");
  function setView(node) {
    const v = view();
    v.innerHTML = "";
    v.appendChild(node);
    v.scrollTop = 0;
    window.scrollTo(0, 0);
  }

  // ---- formatters ----
  const pad = (n) => String(n).padStart(2, "0");

  function fmtDuration(seconds) {
    if (!seconds && seconds !== 0) return "—";
    const s = Math.round(seconds);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
  }
  function fmtKm(metres) {
    if (!metres && metres !== 0) return "—";
    return (metres / 1000).toFixed(2);
  }
  function fmtSpeedKmh(mps) {
    if (!mps && mps !== 0) return "—";
    return (mps * 3.6).toFixed(1);
  }
  function fmtPace(mps) {
    if (!mps) return "—";
    const secPerKm = 1000 / mps;
    return `${Math.floor(secPerKm / 60)}:${pad(Math.round(secPerKm % 60))}`;
  }
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
  }
  function fmtDateTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  // ---- toast ----
  function toast(message, type = "") {
    const wrap = document.getElementById("toasts");
    const t = el("div", { class: "toast " + type, text: message });
    wrap.appendChild(t);
    setTimeout(() => {
      t.style.transition = "opacity .3s, transform .3s";
      t.style.opacity = "0";
      t.style.transform = "translateY(8px)";
      setTimeout(() => t.remove(), 320);
    }, 3600);
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function download(url, filename) {
    const a = el("a", { href: url, download: filename || "" });
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function spinner(label = "Loading…") {
    return el("div", { class: "empty" }, [
      el("div", { html: '<span class="spinner"></span>' }),
      el("div", { text: label, style: "margin-top:10px" }),
    ]);
  }

  return {
    el, setView, view, fmtDuration, fmtKm, fmtSpeedKmh, fmtPace,
    fmtDate, fmtDateTime, cap, toast, cssVar, download, spinner,
  };
})();

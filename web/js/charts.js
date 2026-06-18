/* Chart.js wrappers — theme-aware line charts built from a trackpoint series.
   Chart.js is loaded globally (window.Chart) from /vendor/chart.umd.js. */
const Charts = (() => {
  const registry = [];

  function applyTheme() {
    if (!window.Chart) return;
    Chart.defaults.font.family = U.cssVar("--font") || "sans-serif";
    Chart.defaults.color = U.cssVar("--text-dim");
    Chart.defaults.borderColor = U.cssVar("--border-soft");
    Chart.defaults.animation = { duration: 350 };
  }

  function destroyAll() {
    while (registry.length) {
      const c = registry.pop();
      try { c.destroy(); } catch (_) {}
    }
  }

  // Build {x: elapsedSeconds, y: value} pairs, skipping missing y values.
  function series(trackpoints, key, transform) {
    const out = [];
    let t0 = null;
    trackpoints.forEach((tp, i) => {
      const y = tp[key];
      if (y === null || y === undefined) return;
      let x = i;
      if (tp.timestamp) {
        const t = new Date(tp.timestamp).getTime() / 1000;
        if (t0 === null) t0 = t;
        x = t - t0;
      }
      out.push({ x, y: transform ? transform(y) : y });
    });
    return out;
  }

  function makeLine(canvas, data, color, { fill = false, unit = "" } = {}) {
    if (!window.Chart || !data.length) return null;
    const ctx = canvas.getContext("2d");
    const grad = ctx.createLinearGradient(0, 0, 0, canvas.height || 220);
    grad.addColorStop(0, color + "55");
    grad.addColorStop(1, color + "00");

    const chart = new Chart(ctx, {
      type: "line",
      data: {
        datasets: [{
          data,
          borderColor: color,
          backgroundColor: fill ? grad : "transparent",
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: color,
          tension: 0.25,
          fill,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: {
            type: "linear",
            grid: { display: false },
            ticks: {
              maxTicksLimit: 6,
              callback: (v) => U.fmtDuration(v),
            },
          },
          y: {
            grid: { color: U.cssVar("--border-soft") },
            ticks: { maxTicksLimit: 5, callback: (v) => `${v}${unit}` },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: U.cssVar("--elev"),
            titleColor: U.cssVar("--text"),
            bodyColor: U.cssVar("--text-dim"),
            borderColor: U.cssVar("--border"),
            borderWidth: 1,
            padding: 10,
            displayColors: false,
            callbacks: {
              title: (items) => U.fmtDuration(items[0].parsed.x),
              label: (item) => `${item.parsed.y}${unit}`,
            },
          },
        },
      },
    });
    registry.push(chart);
    return chart;
  }

  return { applyTheme, destroyAll, series, makeLine };
})();

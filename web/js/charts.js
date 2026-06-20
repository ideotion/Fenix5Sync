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

  // Category charts (labelled x axis) for the Insights view: monthly bars and
  // a cumulative area. Kept separate from makeLine (which formats x as elapsed
  // time for per-activity series).
  function _category(canvas, type, labels, values, color, { unit = "", fill = false } = {}) {
    if (!window.Chart) return null;
    const ctx = canvas.getContext("2d");
    let bg = color + "cc";
    if (type === "line" && fill) {
      const grad = ctx.createLinearGradient(0, 0, 0, canvas.height || 220);
      grad.addColorStop(0, color + "55");
      grad.addColorStop(1, color + "00");
      bg = grad;
    }
    const chart = new Chart(ctx, {
      type,
      data: {
        labels,
        datasets: [{
          data: values,
          borderColor: color,
          backgroundColor: bg,
          borderWidth: type === "bar" ? 0 : 2,
          borderRadius: type === "bar" ? 6 : 0,
          maxBarThickness: 38,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: color,
          tension: 0.25,
          fill: type === "line" ? fill : true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
          y: {
            beginAtZero: true,
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
            callbacks: { label: (item) => `${item.parsed.y}${unit}` },
          },
        },
      },
    });
    registry.push(chart);
    return chart;
  }

  const makeBar = (canvas, labels, values, color, opts) => _category(canvas, "bar", labels, values, color, opts);
  const makeArea = (canvas, labels, values, color, opts) =>
    _category(canvas, "line", labels, values, color, { ...opts, fill: true });

  // Multi-series labelled line chart with a legend — used for the Performance
  // Management Chart (CTL/ATL on the left axis, TSB on an optional right axis).
  // Each dataset: {label, data, color, fill?, dashed?, axis?: "y"|"y1"}.
  function makeMultiLine(canvas, labels, datasets, { unit = "" } = {}) {
    if (!window.Chart || !labels.length) return null;
    const ctx = canvas.getContext("2d");
    const useRight = datasets.some((d) => d.axis === "y1");

    const ds = datasets.map((d) => {
      let bg = "transparent";
      if (d.fill) {
        const grad = ctx.createLinearGradient(0, 0, 0, canvas.height || 240);
        grad.addColorStop(0, d.color + "44");
        grad.addColorStop(1, d.color + "00");
        bg = grad;
      }
      return {
        label: d.label,
        data: d.data,
        borderColor: d.color,
        backgroundColor: bg,
        borderWidth: 2,
        borderDash: d.dashed ? [5, 4] : [],
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: d.color,
        tension: 0.25,
        fill: !!d.fill,
        yAxisID: d.axis || "y",
      };
    });

    const scales = {
      x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
      y: { grid: { color: U.cssVar("--border-soft") }, ticks: { maxTicksLimit: 5, callback: (v) => `${v}${unit}` } },
    };
    if (useRight) {
      scales.y1 = { position: "right", grid: { display: false }, ticks: { maxTicksLimit: 5 } };
    }

    const chart = new Chart(ctx, {
      type: "line",
      data: { labels, datasets: ds },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales,
        plugins: {
          legend: {
            display: true,
            position: "bottom",
            labels: { boxWidth: 12, boxHeight: 12, usePointStyle: true, padding: 14 },
          },
          tooltip: {
            backgroundColor: U.cssVar("--elev"),
            titleColor: U.cssVar("--text"),
            bodyColor: U.cssVar("--text-dim"),
            borderColor: U.cssVar("--border"),
            borderWidth: 1,
            padding: 10,
          },
        },
      },
    });
    registry.push(chart);
    return chart;
  }

  return { applyTheme, destroyAll, series, makeLine, makeBar, makeArea, makeMultiLine };
})();

/* API client — all requests are same-origin to the local server under /api. */
const API = (() => {
  const base = "/api";

  async function req(path, opts = {}) {
    const res = await fetch(base + path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return res.status === 204 ? null : res.json();
  }

  function qs(params) {
    const p = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== "") p.set(k, v);
    });
    const s = p.toString();
    return s ? "?" + s : "";
  }

  return {
    health: () => req("/health"),
    stats: () => req("/stats"),
    insights: (sport) => req("/insights" + qs({ sport })),
    listActivities: (params) => req("/activities" + qs(params)),
    getActivity: (id) => req("/activities/" + id),
    activityZones: (id) => req("/activities/" + id + "/zones"),
    startSync: () => req("/sync", { method: "POST" }),
    syncStatus: (jobId) => req("/sync/" + jobId),
    activeSync: () => req("/sync"),
    logs: (lines = 300) => req("/logs" + qs({ lines })),
    getConfig: () => req("/config"),
    putConfig: (cfg) => req("/config", { method: "PUT", body: JSON.stringify(cfg) }),

    // Streaming + download URLs (used directly by EventSource / <a download>).
    syncStreamUrl: (jobId) => base + "/sync/" + jobId + "/stream",
    activityExportUrl: (id, format, anonymize) =>
      base + "/activities/" + id + "/export" +
      qs({ format, anonymize: anonymize ? "true" : null }),
    bulkExportUrl: (format, full, anonymize) =>
      base + "/export" +
      qs({ format, full: full ? "true" : null, anonymize: anonymize ? "true" : null }),
  };
})();

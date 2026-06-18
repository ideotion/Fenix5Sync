/* Offline GPS track plot on a <canvas>.
   No map tiles or network: we project lat/lon to the canvas with an
   equirectangular projection (longitude scaled by cos(latitude)) so the shape
   is undistorted, fit to a padded bounding box, and draw the path plus
   start/end markers. */
const Track = (() => {
  function draw(canvas, points) {
    const pts = (points || []).filter(
      (p) => p.latitude_deg != null && p.longitude_deg != null
    );
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth || 600;
    const cssH = canvas.clientHeight || 380;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    // background panel
    ctx.fillStyle = U.cssVar("--bg");
    roundRect(ctx, 0, 0, cssW, cssH, 10);
    ctx.fill();

    if (pts.length < 2) {
      ctx.fillStyle = U.cssVar("--text-faint");
      ctx.font = "13px " + (U.cssVar("--font") || "sans-serif");
      ctx.textAlign = "center";
      ctx.fillText("No GPS data for this activity", cssW / 2, cssH / 2);
      return;
    }

    const lat0 = pts.reduce((s, p) => s + p.latitude_deg, 0) / pts.length;
    const k = Math.cos((lat0 * Math.PI) / 180) || 1;
    const proj = pts.map((p) => ({ x: p.longitude_deg * k, y: -p.latitude_deg }));

    const xs = proj.map((p) => p.x), ys = proj.map((p) => p.y);
    let minX = Math.min(...xs), maxX = Math.max(...xs);
    let minY = Math.min(...ys), maxY = Math.max(...ys);
    const pad = 26;
    const spanX = maxX - minX || 1e-6, spanY = maxY - minY || 1e-6;
    const scale = Math.min((cssW - 2 * pad) / spanX, (cssH - 2 * pad) / spanY);
    const offX = (cssW - spanX * scale) / 2;
    const offY = (cssH - spanY * scale) / 2;
    const sx = (p) => offX + (p.x - minX) * scale;
    const sy = (p) => offY + (p.y - minY) * scale;

    // soft glow underlay
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.strokeStyle = U.cssVar("--track") + "33";
    ctx.lineWidth = 7;
    stroke(ctx, proj, sx, sy);

    // gradient path along the route
    const g = ctx.createLinearGradient(0, 0, cssW, cssH);
    g.addColorStop(0, U.cssVar("--accent-2"));
    g.addColorStop(1, U.cssVar("--accent"));
    ctx.strokeStyle = g;
    ctx.lineWidth = 2.6;
    stroke(ctx, proj, sx, sy);

    marker(ctx, sx(proj[0]), sy(proj[0]), U.cssVar("--good"), "Start");
    marker(ctx, sx(proj[proj.length - 1]), sy(proj[proj.length - 1]), U.cssVar("--bad"), "End");
  }

  function stroke(ctx, proj, sx, sy) {
    ctx.beginPath();
    proj.forEach((p, i) => (i ? ctx.lineTo(sx(p), sy(p)) : ctx.moveTo(sx(p), sy(p))));
    ctx.stroke();
  }

  function marker(ctx, x, y, color, label) {
    ctx.beginPath();
    ctx.fillStyle = color;
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = U.cssVar("--bg");
    ctx.stroke();
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  return { draw };
})();

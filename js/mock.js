// Synthetic z-score rasters over the real demo AOIs and acquisition dates.
// The pipeline will replace this with a GeoTIFF/PNG raster per site plus per-pixel series on demand.
window.OB = window.OB || {};

(function () {
  function rng(seed) { // mulberry32
    return function () {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gauss(r) { return Math.sqrt(-2 * Math.log(r() + 1e-12)) * Math.cos(2 * Math.PI * r()); }

  // NISAR 12-day repeat; gaps are ranges with no data in the ASF/CMR catalogue.
  const GLOBAL_GAP = ["2026-07-27", "2026-08-10"];
  function dates(start, end, gaps) {
    const out = [], d0 = new Date(start + "T00:00:00Z");
    for (let i = 0; ; i++) {
      const d = new Date(d0.getTime() + i * 12 * 864e5).toISOString().slice(0, 10);
      if (d > end) break;
      if ([GLOBAL_GAP].concat(gaps || []).some(([a, b]) => d >= a && d <= b)) continue;
      out.push(d);
    }
    return out;
  }

  // Smooth 0..1 field for land cover patches (two octaves of value noise).
  function noiseField(r, w, h, cells) {
    const g = [], G = cells + 1;
    for (let i = 0; i < G * G; i++) g.push(r());
    const at = (x, y) => {
      const fx = x / w * cells, fy = y / h * cells, ix = Math.floor(fx), iy = Math.floor(fy), tx = fx - ix, ty = fy - iy;
      const s = t => t * t * (3 - 2 * t), a = g[iy * G + ix], b = g[iy * G + ix + 1], c = g[(iy + 1) * G + ix], d = g[(iy + 1) * G + ix + 1];
      return a + (b - a) * s(tx) + (c - a) * s(ty) + (a - b - c + d) * s(tx) * s(ty);
    };
    return at;
  }

  OB.STYLE_KEYS = [null, "drop", "flood", "drift", "step"];
  const CODE = { drop: 1, flood: 2, drift: 3, step: 4 };

  // Typical L-band gamma0 in dB per WorldCover class: [HH, HV, seasonal amplitude].
  const BASE = { 10: [-7.0, -12.5, 0.3], 30: [-10.5, -18.0, 1.2], 40: [-9.5, -16.5, 1.8], 50: [-3.0, -11.0, 0.2], 80: [-20, -27, 0.5], 90: [-8.5, -15.0, 1.0] };

  // Feature contribution to z at (lat, lon). Distances in degrees.
  function contrib(f, lat, lon) {
    if (f.type === "blob") {
      const d2 = (lat - f.lat) ** 2 + ((lon - f.lon) * f.k) ** 2;
      return f.z * Math.exp(-d2 / (2 * f.r * f.r));
    }
    if (f.type === "rect") {
      const dx = Math.abs((lon - f.lon) * f.k) - f.w / 2, dy = Math.abs(lat - f.lat) - f.h / 2;
      const out = Math.max(dx, dy);
      return out <= 0 ? f.z : out < f.soft ? f.z * (1 - out / f.soft) : 0;
    }
    if (f.type === "line") { // distance to a polyline; signed = opposite sign on each side
      let best = 1e9, side = 1;
      for (let i = 0; i < f.pts.length - 1; i++) {
        const [ay, ax] = f.pts[i], [by, bx] = f.pts[i + 1];
        const px = (lon - ax) * f.k, py = lat - ay, vx = (bx - ax) * f.k, vy = by - ay;
        const t = Math.max(0, Math.min(1, (px * vx + py * vy) / (vx * vx + vy * vy)));
        const d = Math.hypot(px - t * vx, py - t * vy);
        if (d < best) { best = d; side = Math.sign(vx * py - vy * px) || 1; }
      }
      return f.z * (f.signed ? side : 1) * Math.exp(-best / f.r);
    }
    return 0;
  }

  function makeSite(cfg) {
    const r = rng(cfg.seed);
    const D = dates(cfg.start, cfg.end, cfg.gaps);
    const k = Math.cos(cfg.center[0] * Math.PI / 180);       // lon degrees -> ground degrees
    const N = cfg.grid || 400;
    const latS = cfg.span, lonS = cfg.span / k;
    const bbox = { s: cfg.center[0] - latS / 2, n: cfg.center[0] + latS / 2, w: cfg.center[1] - lonS / 2, e: cfg.center[1] + lonS / 2 };
    const evIdx = date => Math.max(0, D.findIndex(d => d >= date));

    const feats = cfg.features(r, bbox).map(f => Object.assign({ k, soft: 0.003 }, f, { code: CODE[f.style], since: evIdx(f.since) }));

    const z = new Float32Array(N * N), style = new Uint8Array(N * N), cover = new Uint8Array(N * N), since = new Int16Array(N * N).fill(-1);
    const cov = noiseField(r, N, N, 7), cov2 = noiseField(r, N, N, 23);
    // warp + gain fields make shapes irregular, like real deformation and clearing edges
    const wx = noiseField(r, N, N, 9), wy = noiseField(r, N, N, 9), gain = noiseField(r, N, N, 15), warp = cfg.warp || 0;
    for (let y = 0; y < N; y++) {
      const lat = bbox.n - (y + 0.5) / N * latS;
      for (let x = 0; x < N; x++) {
        const lon = bbox.w + (x + 0.5) / N * lonS, i = y * N + x;
        if (cfg.water && cfg.water(lat, lon)) { cover[i] = 80; continue; }
        const c = 0.7 * cov(x, y) + 0.3 * cov2(x, y);
        cover[i] = cfg.covers[Math.min(cfg.covers.length - 1, Math.floor(c * cfg.covers.length))];
        let best = 0, bf = null;
        const la = lat + (wy(x, y) - 0.5) * warp, lo = lon + (wx(x, y) - 0.5) * warp / k, m = warp ? 0.7 + 0.6 * gain(x, y) : 1;
        for (const f of feats) { const v = contrib(f, la, lo) * m; if (Math.abs(v) > Math.abs(best)) { best = v; bf = f; } }
        z[i] = best + gauss(r) * 0.75;
        if (bf && Math.abs(best) > 1.5) {
          style[i] = bf.code; since[i] = bf.since;
          if (bf.cover) cover[i] = bf.cover;
        }
      }
    }

    // One pixel's series, rebuilt on demand so its last value matches the raster's z.
    function series(x, y) {
      const i = y * N + x, pr = rng(cfg.seed * 7919 + i);
      const cv = cover[i], [bh, bv, amp] = BASE[cv] || BASE[30], st = OB.STYLE_KEYS[style[i]], zi = z[i];
      const n = D.length, ev = since[i] < 0 ? n : since[i];
      const hhMed = [], hvMed = [], hh = [], hv = [], disp = [], pdisp = [];
      for (let t = 0; t < n; t++) {
        const season = amp * Math.sin((t / n) * 2 * Math.PI);
        hhMed.push(+(bh + season).toFixed(2)); hvMed.push(+(bv + season * 0.8).toFixed(2));
        let h = bh + season + gauss(pr) * 0.5, v = bv + season * 0.8 + gauss(pr) * 0.55;
        if (st === "drop" && t >= ev) { v += zi * 0.9; h += zi * 0.3; }
        if (st === "flood" && t >= ev) { h += zi * 0.8; v += 0.5; }
        if (!st && t === n - 1) v = bv + season * 0.8 + zi * 0.9;
        hh.push(+h.toFixed(2)); hv.push(+v.toFixed(2));
        const peer = cfg.peerRate * t + (cfg.peerStep && t >= evIdx(cfg.event ? cfg.event.date : "9999") ? cfg.peerStep : 0);
        let d = peer + gauss(pr) * 0.3;
        if (st === "drift") d += zi * 1.2 * Math.min(1, t / (n - 1));
        if (st === "step" && t >= ev) d += zi * 1.2;
        pdisp.push(+peer.toFixed(2)); disp.push(+d.toFixed(2));
      }
      return {
        id: `${cfg.id.slice(0, 3).toUpperCase()} r${y} c${x}`,
        lat: +(bbox.n - (y + 0.5) / N * latS).toFixed(5), lon: +(bbox.w + (x + 0.5) / N * lonS).toFixed(5),
        cover: cv, peers: 60 + Math.floor(pr() * 400), z: +zi.toFixed(2), style: st,
        since: st && since[i] >= 0 ? D[since[i]] : null,
        hh, hv, peer: { hh_med: hhMed, hh_sd: hh.map(() => 0.8), hv_med: hvMed, hv_sd: hv.map(() => 0.9) },
        disp: cfg.gunw ? disp : null, peer_disp: cfg.gunw ? pdisp : null
      };
    }

    const cellM = Math.round(latS * 111320 / N);
    return {
      id: cfg.id, name: cfg.name, region: cfg.region, center: cfg.center, zoom: cfg.zoom,
      event: cfg.event, dates: D, source: "synthetic",
      grid: { n: N, bbox, z, style, cover, since, cellM }, series
    };
  }

  // Random rectangles along a road and its side roads: the fishbone pattern of frontier clearing.
  function fishbone(r, a, b, count, since) {
    const out = [];
    for (let j = 0; j < count; j++) {
      const t = r(), lat = a[0] + (b[0] - a[0]) * t, lon = a[1] + (b[1] - a[1]) * t;
      const off = (r() - 0.5) * 0.12;
      out.push({ type: "rect", style: "drop", cover: 10,
        lat: lat + off * 0.7, lon: lon + off, w: 0.004 + r() * 0.011, h: 0.003 + r() * 0.007,
        z: -(4.5 + r() * 4), since: since[Math.floor(r() * since.length)] });
    }
    return out;
  }

  // Piecewise-linear coast (lon, lat), sampled from Sentinel-2 cloudless tiles; sea is north of it.
  function coastNorth(pts) {
    return (lat, lon) => {
      let j = pts.findIndex(p => p[0] >= lon); if (j <= 0) j = j < 0 ? pts.length - 1 : 1;
      const [x0, y0] = pts[j - 1], [x1, y1] = pts[j], t = Math.max(0, Math.min(1, (lon - x0) / (x1 - x0)));
      return lat > y0 + (y1 - y0) * t;
    };
  }

  // AOIs, tracks and dates checked in the ASF/CMR catalogue; z values are synthetic.
  OB.SITES = [
    // track 019A/011, 2025-10-30 -> 2026-10-13, 28 GUNW pairs
    makeSite({ id: "mexico", name: "Mexico City", region: "Ground sinking on the old lake bed",
      center: [19.425, -99.075], zoom: 11, span: 0.34, seed: 11, warp: 0.035, covers: [30, 50, 50, 50, 40],
      start: "2025-10-30", end: "2026-10-13", gunw: true, peerRate: -0.15, event: null,
      features: () => [
        { type: "blob", style: "drift", lat: 19.44, lon: -99.01, r: 0.035, z: -7.5, since: "2025-11-20" },  // Nezahualcóyotl
        { type: "blob", style: "drift", lat: 19.36, lon: -99.06, r: 0.03, z: -6.0, since: "2025-11-20" },   // Iztapalapa
        { type: "blob", style: "drift", lat: 19.29, lon: -99.10, r: 0.022, z: -4.5, since: "2025-11-20" },  // Xochimilco
        { type: "blob", style: "drift", lat: 19.50, lon: -99.03, r: 0.018, z: -3.6, since: "2025-11-20" }
      ] }),
    // track 045A/175: 5 uncalibrated BETA dates, nothing until PROVISIONAL starts on 2026-06-17
    makeSite({ id: "amazon", name: "Itupiranga, Pará", region: "Forest clearing in the 2026 dry season",
      center: [-4.775, -49.275], zoom: 11, span: 0.4, seed: 23, covers: [10, 10, 10, 30, 30],
      start: "2025-11-01", end: "2026-10-27", gaps: [["2026-01-20", "2026-06-16"]],
      gunw: true, peerRate: 0, event: null,
      features: r => fishbone(r, [-4.62, -49.45], [-4.95, -49.12], 40, ["2026-07-11", "2026-08-16", "2026-09-09", "2026-10-03"])
        .concat(fishbone(r, [-4.70, -49.12], [-4.88, -49.42], 18, ["2026-08-16", "2026-09-21"]))
        .concat([{ type: "line", style: "flood", cover: 90, r: 0.0025, z: 5.5, since: "2025-12-07",
          pts: [[-4.58, -49.33], [-4.66, -49.30], [-4.74, -49.34], [-4.83, -49.31], [-4.97, -49.36]] }]) }),
    // track 162A/007: 2026-06-13 before, 2026-06-25 about 12 h after the doublet
    makeSite({ id: "venezuela", name: "Caracas and Catia La Mar", region: "M7.2 + M7.5 earthquakes, 24 June 2026",
      center: [10.47, -67.08], zoom: 11, span: 0.3, seed: 37, warp: 0.02, covers: [10, 10, 30, 50, 40],
      start: "2025-11-09", end: "2026-10-20", gunw: true, peerRate: 0, peerStep: -1.5,
      event: { date: "2026-06-24", label: "M7.5" },
      water: coastNorth([[-67.40, 10.538], [-67.30, 10.542], [-67.225, 10.552], [-67.175, 10.56], [-67.124, 10.572],
        [-67.073, 10.592], [-67.047, 10.61], [-67.0, 10.607], [-66.9, 10.605]]),
      features: r => [
        // offshore San Sebastián fault: one smooth lobe of motion decaying inland from the coast
        { type: "line", style: "step", r: 0.032, z: -7, since: "2026-06-24",
          pts: [[10.585, -67.45], [10.60, -67.22], [10.625, -66.9]] }
      ].concat(Array.from({ length: 9 }, () => ({ type: "blob", style: "drop", cover: 10,
        lat: 10.5 + r() * 0.05, lon: -67.2 + r() * 0.25, r: 0.003 + r() * 0.004, z: -(5 + r() * 3), since: "2026-06-24" }))) })
  ];
})();

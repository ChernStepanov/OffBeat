// Synthetic sites in the shape of docs/data-contract.md.
// Replace with fetch("data/<site>.json") once the NISAR pipeline writes real files.
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

  // NISAR 12-day repeat, from the start of science operations onward.
  function dates(start, n) {
    const out = [], d0 = new Date(start + "T00:00:00Z");
    for (let i = 0; i < n; i++) out.push(new Date(d0.getTime() + i * 12 * 864e5).toISOString().slice(0, 10));
    return out;
  }

  const BASE = { // typical L-band dB per WorldCover class: [HH, HV, seasonal amplitude]
    10: [-7.0, -12.5, 0.3], 40: [-9.5, -16.5, 1.8], 50: [-3.0, -11.0, 0.2], 90: [-8.5, -15.0, 1.0], 30: [-10.5, -18.0, 1.2]
  };

  function makeSite(cfg) {
    const r = rng(cfg.seed);
    const D = dates("2025-11-07", 26);
    const n = D.length, ev = cfg.eventIndex;
    const px = [];

    for (let k = 0; k < cfg.count; k++) {
      const cover = cfg.covers[Math.floor(r() * cfg.covers.length)];
      const [bh, bv, amp] = BASE[cover];
      const lat = cfg.center[0] + (r() - 0.5) * cfg.span;
      const lon = cfg.center[1] + (r() - 0.5) * cfg.span * 1.2;

      // pick a style: most pixels are fine, some carry the site's story, a few carry another.
      const u = r();
      let style = null;
      if (u < cfg.rate) style = cfg.main;
      else if (u < cfg.rate + 0.03 && cfg.other) style = cfg.other;

      const hhMed = [], hvMed = [], hhSd = [], hvSd = [], hh = [], hv = [];
      const disp = cfg.gunw ? [] : null, pdisp = cfg.gunw ? [] : null;
      const rate = -(0.06 + r() * 0.26); // extra cm per acquisition on top of the peers' own sinking
      const jump = (r() < 0.5 ? -1 : 1) * (5 + r() * 6);
      const evAt = style ? Math.max(3, ev + Math.floor((r() - 0.5) * 6)) : ev;

      for (let i = 0; i < n; i++) {
        const season = amp * Math.sin((i / n) * 2 * Math.PI);
        hhMed.push(bh + season); hvMed.push(bv + season * 0.8);
        hhSd.push(0.8); hvSd.push(0.9);
        let h = bh + season + gauss(r) * 0.55, v = bv + season * 0.8 + gauss(r) * 0.6;
        if (style === "drop" && i >= evAt) { v -= 6.5; h -= 2.2; }
        if (style === "flood" && i >= evAt) { h += 6; v += 0.6; }
        hh.push(+h.toFixed(2)); hv.push(+v.toFixed(2));

        if (cfg.gunw) {
          let peer = cfg.peerRate * i + (cfg.main === "step" && i >= ev ? cfg.peerStep : 0);
          let d = peer + gauss(r) * 0.35;
          if (style === "drift") d += rate * i;
          if (style === "step" && i >= ev) d += jump;
          pdisp.push(+peer.toFixed(2)); disp.push(+d.toFixed(2));
        }
      }

      // z against peers on the channel the style lives in, at the last acquisition.
      const L = n - 1;
      let z;
      if (style === "drift" || style === "step") z = (disp[L] - pdisp[L]) / 1.2;
      else if (style === "flood") z = (hh[L] - hhMed[L]) / hhSd[L];
      else if (style === "drop") z = (hv[L] - hvMed[L]) / hvSd[L];
      else z = gauss(r) * 0.9;

      px.push({
        id: cfg.id.slice(0, 3).toUpperCase() + "-" + String(k + 1).padStart(4, "0"),
        lat: +lat.toFixed(5), lon: +lon.toFixed(5),
        cover, peers: 40 + Math.floor(r() * 220),
        z: +z.toFixed(2),
        style: Math.abs(z) >= 2 ? style : null,
        since: style ? D[style === "drift" ? 2 : (style === "step" ? ev : evAt)] : null,
        hh, hv,
        peer: { hh_med: hhMed.map(x => +x.toFixed(2)), hh_sd: hhSd, hv_med: hvMed.map(x => +x.toFixed(2)), hv_sd: hvSd },
        disp, peer_disp: pdisp
      });
    }
    return {
      id: cfg.id, name: cfg.name, region: cfg.region,
      center: cfg.center, zoom: cfg.zoom,
      event: cfg.event, dates: D, pixels: px, source: "synthetic"
    };
  }

  // Sites are placeholders until docs/coverage.md confirms frames and dates.
  OB.SITES = [
    makeSite({ id: "mexico", name: "Mexico City", region: "Subsidence of the lake-bed clays",
      center: [19.40, -99.06], zoom: 11, span: 0.28, seed: 11, count: 420, covers: [50, 50, 50, 30],
      main: "drift", other: null, rate: 0.12, eventIndex: 0, gunw: true, peerRate: -0.15, peerStep: 0, event: null }),
    makeSite({ id: "amazon", name: "Novo Progresso, Pará", region: "Clearing along BR-163",
      center: [-7.05, -55.42], zoom: 11, span: 0.3, seed: 23, count: 420, covers: [10, 10, 10, 30, 90],
      main: "drop", other: "flood", rate: 0.09, eventIndex: 14, gunw: false, event: null }),
    makeSite({ id: "venezuela", name: "Venezuela", region: "Earthquake, date to be confirmed",
      center: [10.15, -67.6], zoom: 10, span: 0.4, seed: 37, count: 420, covers: [10, 40, 50, 30],
      main: "step", other: "drop", rate: 0.08, eventIndex: 16, gunw: true, peerRate: 0, peerStep: -1.5, event: { index: 16, label: "Main shock" } })
  ];
})();

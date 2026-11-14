// Reads what pipeline/export.py writes to data/<site>/ and returns a site in the shape app.js uses.
// Falls back to the in-browser mock (js/mock.js) when the folder is missing or the page runs from file://.
window.OB = window.OB || {};

OB.data = (function () {
  const NO_U8 = 255, NO_I8 = -128, NO_I16 = -32768;

  function view(buf, L) {
    const n = L.shape.reduce((a, b) => a * b, 1);
    const T = { uint8: Uint8Array, int8: Int8Array, int16: Int16Array }[L.dtype];
    return new T(buf, L.offset, n);
  }
  const dec = {
    z:     a => Float32Array.from(a, q => q === NO_I8 ? NaN : q / 10),
    cm:    a => Float32Array.from(a, q => q === NO_I16 ? NaN : q / 10),
    db:    a => Float32Array.from(a, q => q === NO_U8 ? NaN : q / 4 - 40),
    sd:    a => Float32Array.from(a, q => q === NO_U8 ? NaN : q / 20),
    code:  a => a,
    index: a => Int16Array.from(a, q => q === NO_U8 ? -1 : q)
  };
  const decode = (buf, L) => dec[L.kind](view(buf, L));

  async function get(url, type) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url + " " + r.status);
    return type === "json" ? r.json() : r.arrayBuffer();
  }

  async function load(id, fallback) {
    let meta;
    try { meta = await get(`data/${id}/meta.json`, "json"); }
    catch (e) { return fallback; }
    const [gbuf, pbuf] = await Promise.all([get(`data/${id}/grid.bin`), get(`data/${id}/peers.bin`)]);
    const W = meta.width, H = meta.height, [w, s, e, n] = meta.bounds, T = meta.dates.length;

    const layers = {};
    for (const [k, L] of Object.entries(meta.grid)) layers[k] = decode(gbuf, L);
    const peers = {};
    for (const [k, L] of Object.entries(meta.peers.layers)) peers[k] = decode(pbuf, L);

    const grid = {
      w: W, h: H, bbox: { w, s, e, n }, cellM: meta.pixel_m,
      z: layers.z, style: layers.style, since: layers.since, cover: layers.cover,
      extra: Object.fromEntries(["damage", "coseismic", "up", "east"].filter(k => layers[k]).map(k => [k, layers[k]]))
    };

    const tiles = new Map(), TS = meta.series.tile;
    async function tile(ty, tx) {
      const key = ty + "_" + tx;
      if (!tiles.has(key)) tiles.set(key, get(`data/${id}/series/${key}.bin`).then(buf =>
        Object.fromEntries(Object.entries(meta.series.layers).map(([k, L]) => [k, decode(buf, L)]))));
      return tiles.get(key);
    }

    // block peers for one class at one pixel, as a per-date array
    const PB = meta.peers;
    function peerCurve(cls, name, x, y) {
      const a = peers[`${cls}.${name}`]; if (!a) return null;
      const bx = Math.min(PB.bw - 1, Math.floor(x / PB.block)), by = Math.min(PB.bh - 1, Math.floor(y / PB.block));
      const out = new Array(T);
      for (let t = 0; t < T; t++) out[t] = a[(t * PB.bh + by) * PB.bw + bx];
      return out;
    }

    async function series(x, y) {
      const i = y * W + x, cls = grid.cover[i];
      const tl = await tile(Math.floor(y / TS), Math.floor(x / TS));
      const ix = x % TS, iy = y % TS, pick = a => a ? Array.from({ length: T }, (_, t) => a[(t * TS + iy) * TS + ix]) : null;
      const st = meta.styles[grid.style[i]] || null;
      const dlat = (n - s) / H, dlon = (e - w) / W;
      const blank = () => new Array(T).fill(NaN);
      return {
        id: `${id.slice(0, 3).toUpperCase()} r${y} c${x}`,
        lat: n - (y + 0.5) * dlat, lon: w + (x + 0.5) * dlon,
        cover: cls, peers: null, z: isNaN(grid.z[i]) ? 0 : grid.z[i], style: st,
        since: st && grid.since[i] >= 0 ? meta.dates[grid.since[i]] : null,
        hh: pick(tl.hh), hv: pick(tl.hv),
        peer: {
          hh_med: peerCurve(cls, "hh_med", x, y) || blank(), hh_sd: peerCurve(cls, "hh_sd", x, y) || blank(),
          hv_med: peerCurve(cls, "hv_med", x, y) || blank(), hv_sd: peerCurve(cls, "hv_sd", x, y) || blank()
        },
        disp: pick(tl.disp), peer_disp: tl.disp ? (peerCurve(cls, "disp_med", x, y) || blank()) : null,
        extra: Object.fromEntries(Object.entries(grid.extra).map(([k, a]) => [k, a[i]]))
      };
    }

    // optional context files written next to the site (fires, deforestation alerts)
    const context = {};
    for (const [k, f] of Object.entries(meta.context || {})) {
      try { context[k] = await get(`data/${id}/${f}`, "json"); } catch (e) { console.warn(f, e); }
    }

    return {
      id, name: fallback ? fallback.name : meta.name, region: fallback ? fallback.region : "",
      event: meta.event ? { date: meta.event } : null, damagePair: meta.damage_pair,
      dates: meta.dates, source: meta.source, grid, series, context
    };
  }

  return { load };
})();

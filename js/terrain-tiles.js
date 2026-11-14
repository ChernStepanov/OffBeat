// Global Web Mercator addressing and bounded streaming; independent of NISAR coverage.
window.OB = window.OB || {};
OB.terrainTiles = (() => {
  const MAX_LAT = 85.05112878, C = 40075016.68557849;
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const wrap = (x, n) => ((x % n) + n) % n;
  function mercator(lon, lat) {
    const a = clamp(lat, -MAX_LAT, MAX_LAT) * Math.PI / 180;
    return { x: (lon + 180) / 360, y: (1 - Math.asinh(Math.tan(a)) / Math.PI) / 2 };
  }
  function geographic(x, y) { return { lon: wrap(x * 360, 360) - 180, lat: Math.atan(Math.sinh(Math.PI * (1 - 2 * clamp(y, 0, 1)))) * 180 / Math.PI }; }
  function descriptor(z, x, y) {
    const n = 2 ** z, canonical = wrap(x, n);
    return { z, x, y, key: `${z}/${canonical}/${y}`, meshKey: `${z}/${x}/${y}`, url: `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/${z}/${canonical}/${y}.png` };
  }
  function cover(bounds, level, budget = 64) {
    let z = clamp(Math.floor(level), 0, 14);
    while (true) {
      const n = 2 ** z, x0 = Math.floor(bounds.w * n), x1 = Math.floor(bounds.e * n);
      const y0 = clamp(Math.floor(bounds.n * n), 0, n - 1), y1 = clamp(Math.floor(bounds.s * n), 0, n - 1);
      if ((x1 - x0 + 1) * (y1 - y0 + 1) > budget && z > 0) { z--; continue; }
      const list = [];
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) list.push(descriptor(z, x, y));
      const cx = (bounds.w + bounds.e) / 2 * n, cy = (bounds.n + bounds.s) / 2 * n;
      return list.sort((a, b) => Math.hypot(a.x + .5 - cx, a.y + .5 - cy) - Math.hypot(b.x + .5 - cx, b.y + .5 - cy));
    }
  }
  function decode(rgba, size) {
    if (rgba.length !== size * size * 4) throw new Error('Invalid DEM pixel data');
    const heights = new Float32Array(size * size);
    for (let i = 0; i < heights.length; i++) {
      if (!rgba[i * 4 + 3]) throw new Error('DEM tile contains transparent elevations');
      heights[i] = rgba[i * 4] * 256 + rgba[i * 4 + 1] + rgba[i * 4 + 2] / 256 - 32768;
    }
    return { size, heights };
  }
  // Preload an orbit around the geographic centre. Camera yaw/pitch must never
  // choose a different elevation source, tessellation or height colour range.
  function orbitCoverage(center, zoom) {
    const radius = 12 / (2 * 2 ** zoom);
    const bounds = { w: center.x - radius, e: center.x + radius, n: center.y - radius, s: center.y + radius };
    if (zoom < 1.5) { bounds.w = Math.max(0, bounds.w); bounds.e = Math.min(1 - 1e-12, bounds.e); }
    return cover(bounds, zoom + 2, 64);
  }
  function sample(tile, u, v) {
    const s = tile.size, x = clamp(u * s - .5, 0, s - 1), y = clamp(v * s - .5, 0, s - 1);
    const ix = Math.min(s - 2, Math.floor(x)), iy = Math.min(s - 2, Math.floor(y)), fx = x - ix, fy = y - iy;
    const a = tile.heights[iy * s + ix] * (1 - fx) + tile.heights[iy * s + ix + 1] * fx;
    const b = tile.heights[(iy + 1) * s + ix] * (1 - fx) + tile.heights[(iy + 1) * s + ix + 1] * fx;
    return a * (1 - fy) + b * fy;
  }
  function create(onChange, { limit = 96, concurrency = 5, fetcher = fetch, decodeImage, rootUrl = 'data/terrain/world-0.png', onEvict = () => {} } = {}) {
    const cache = new Map(), running = new Map(), failures = new Map();
    let wanted = new Map(), queue = [], stopped = false;
    async function png(blob) {
      const image = await createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
      try {
        if (image.width !== image.height || image.width < 2 || image.width > 1024) throw new Error('Invalid DEM tile dimensions');
        const cv = document.createElement('canvas'); cv.width = cv.height = image.width;
        const ctx = cv.getContext('2d', { willReadFrequently: true }); ctx.drawImage(image, 0, 0);
        return decode(ctx.getImageData(0, 0, cv.width, cv.height).data, cv.width);
      } finally { image.close(); }
    }
    function trim() {
      for (const key of cache.keys()) {
        if (cache.size <= limit) break;
        if (key !== '0/0/0' && !wanted.has(key)) { const entry = cache.get(key); cache.delete(key); onEvict(entry); }
      }
    }
    function pump() {
      if (stopped) return;
      while (running.size < concurrency && queue.length) {
        const tile = queue.shift();
        if (!wanted.has(tile.key) || cache.has(tile.key) || running.has(tile.key)) continue;
        const failed = failures.get(tile.key);
        if (failed && failed.retryAt > Date.now()) continue;
        const controller = new AbortController(); running.set(tile.key, controller);
        const timeout = setTimeout(() => controller.abort('timeout'), 18000);
        (async () => {
          try {
            const response = await fetcher(tile.z === 0 && rootUrl ? rootUrl : tile.url, { signal: controller.signal });
            if (!response.ok) throw new Error(`DEM HTTP ${response.status}`);
            const data = await (decodeImage || png)(await response.blob());
            if (controller.signal.aborted) { onEvict(data); return; }
            cache.set(tile.key, { ...data, z: tile.z, x: wrap(tile.x, 2 ** tile.z), y: tile.y });
            failures.delete(tile.key); trim(); onChange({ tile, ready: true });
          } catch (error) {
            if (controller.signal.aborted && controller.signal.reason !== 'timeout') return;
            const attempts = (failures.get(tile.key)?.attempts || 0) + 1;
            failures.set(tile.key, { attempts, retryAt: Date.now() + Math.min(30000, 1500 * 2 ** attempts), message: error.message });
            onChange({ tile, error: error.message });
          } finally {
            clearTimeout(timeout); running.delete(tile.key);
            if (!stopped && wanted.has(tile.key) && !cache.has(tile.key) && controller.signal.aborted && controller.signal.reason !== 'timeout') queue.unshift(wanted.get(tile.key));
            pump();
          }
        })();
      }
    }
    function setWanted(tiles) {
      wanted = new Map(tiles.map(t => [t.key, t]));
      for (const key of failures.keys()) if (!wanted.has(key)) failures.delete(key);
      for (const [key, controller] of running) if (!wanted.has(key)) controller.abort('obsolete viewport');
      queue = [...wanted.values()].filter(t => !cache.has(t.key) && !running.has(t.key)); trim(); pump();
    }
    function heightAt(x, y, maxLevel = 14) {
      x = wrap(x, 1); y = clamp(y, 0, 1 - 1e-12);
      for (let z = maxLevel; z >= 0; z--) {
        const n = 2 ** z, gx = x * n, gy = y * n, tx = Math.floor(gx), ty = Math.floor(gy);
        const tile = cache.get(`${z}/${tx}/${ty}`);
        if (tile) return { height_m: sample(tile, gx - tx, gy - ty), level: z };
      }
      return null;
    }
    return {
      setWanted, heightAt, cache,
      retry() { failures.clear(); setWanted([...wanted.values()]); },
      info() { const keys = [...wanted.keys()]; return { cached: cache.size, pending: keys.filter(k => !cache.has(k) && !failures.has(k)).length, failed: keys.filter(k => failures.has(k)).length, running: running.size }; },
      stop() { stopped = true; for (const controller of running.values()) controller.abort('paused'); queue = []; },
      resume() { stopped = false; setWanted([...wanted.values()]); },
    };
  }
  return { MAX_LAT, C, clamp, wrap, mercator, geographic, descriptor, cover, orbitCoverage, decode, sample, create };
})();

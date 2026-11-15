window.OB = window.OB || {};

OB.bindNisarMap = function (map, toggle, status) {
  const base = 'https://gibs.earthdata.nasa.gov';
  const product = 'NISAR_L2_Geocoded_Polarimetric_Covariance';
  const matrix = 'GoogleMapsCompatible_Level13';
  const mosaicDays = 12;
  const day = 86400000;
  const tileSize = 256;
  const nativeZoom = 13;
  const tiles = new Set();
  const imageCache = new Map();
  const renderedTiles = new Map();
  let failedTiles = 0, inflight = 0, statusTimer;
  let layer, loading, caption, legend;
  // A NASA browse pixel is ~19 m (native level 13). Up to zoom 16 it spans at most ~8 screen
  // pixels and smooth scaling hides the hatching; from zoom 17 it spans 16+ and smoothing turns
  // each one into a soft blob, so it is drawn as the honest square it is.
  const CRISP_FROM = nativeZoom + 4;
  const rendering = () => map.getZoom() >= CRISP_FROM ? 'pixelated' : 'auto';
  // Date-coloured strips answer "where did NISAR look?" from country down to city scale. Closer
  // in, one strip covers the whole window in a single colour and only washes the measured
  // samples in the same reds and blues, so it steps aside.
  const HIDE_FROM = 13;

  map.createPane('nisarRadar');
  map.getPane('nisarRadar').style.zIndex = 250;
  map.getPane('nisarRadar').style.pointerEvents = 'none';

  function loadImage(url) {
    if (imageCache.has(url)) return imageCache.get(url);
    inflight++; scheduleStatus();
    const attempt = () => new Promise(resolve => {
      const image = new Image();
      let timer;
      const finish = value => {
        clearTimeout(timer); image.onload = image.onerror = null; resolve(value);
      };
      image.crossOrigin = 'anonymous';
      image.onload = () => finish(image);
      image.onerror = () => finish(null);
      timer = setTimeout(() => finish(null), 15000);
      image.src = url;
    });
    const pending = (async () => {
      let image = await attempt();
      if (!image) {
        await new Promise(resolve => setTimeout(resolve, 800));
        image = await attempt();
      }
      // Never cache a failed request as missing satellite coverage.
      if (!image) imageCache.delete(url);
      inflight--; scheduleStatus();
      return image;
    })();
    imageCache.set(url, pending);
    if (imageCache.size > 384) imageCache.delete(imageCache.keys().next().value);
    return pending;
  }

  function scheduleStatus() {
    if (statusTimer) return;
    statusTimer = setTimeout(() => { statusTimer = null; showStatus(); }, 150);
  }

  function showStatus() {
    if (!caption) return;
    if (map.getZoom() >= HIDE_FROM) { status.textContent = 'NISAR coverage dates appear when you zoom out to city scale.'; return; }
    const past = '';
    // say what is actually drawn: a coloured strip in any loaded tile on screen
    const view = map.getPixelBounds();
    const visible = [...tiles].filter(tile => {
      const c = tile.radar && tile.radar.coords; if (!c || c.z !== Math.round(map.getZoom())) return false;
      const x = c.x * tileSize - (view.min.x), y = c.y * tileSize - (view.min.y);
      return x > -tileSize && y > -tileSize && x < view.max.x - view.min.x && y < view.max.y - view.min.y;
    });
    const coloured = visible.some(tile => tile.radar.owner && tile.radar.owner.some(d => d >= 0));
    const busy = inflight > 0 ? ` | Loading NASA radar: ${inflight} request${inflight === 1 ? '' : 's'} left` : '';
    const text = caption + past + busy + (failedTiles
      ? ` | ${failedTiles} incomplete tile${failedTiles === 1 ? '' : 's'}: NASA did not answer, retrying. These gaps are not confirmed missing coverage.`
      : inflight ? ' | Coverage is still loading.' : coloured ? '' : ' | No colour: no coverage detected in this window.');
    status.textContent = '';
    if (legend) status.append(legend, ' ');
    status.append(text);
  }

  // The layer's own time domain via DescribeDomains: under 1 KB and ~0.3 s, instead of the
  // 5.8 MB capabilities document for every GIBS layer (~9 s) that this used to download.
  async function getDates() {
    const url = `${base}/wmts/epsg3857/best/wmts.cgi?SERVICE=WMTS&REQUEST=DescribeDomains&VERSION=1.0.0` +
      `&LAYER=${product}&TILEMATRIXSET=${matrix}`;
    const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error('GIBS time domain unavailable');
    const domain = (await response.text()).match(/<Domain>([^<]*)<\/Domain>/)?.[1];
    if (!domain) throw new Error('GIBS returned no time domain');
    // "2025-10-29/2026-03-01/P1D,2026-03-04/..." -> [[first, last], ...]; a bare date is a one-day range
    const ranges = domain.split(',').map(part => {
      const [first, last = first] = part.trim().split('/');
      return [Date.parse(first), Date.parse(last)];
    });
    const latest = Math.max(...ranges.map(([, last]) => last));
    if (!Number.isFinite(latest)) throw new Error('GIBS returned no default date');
    const available = date => ranges.some(([first, last]) => date >= first && date <= last);
    const iso = date => new Date(date).toISOString().slice(0, 10);
    const end = await lastCompleteDay(latest, available, iso);
    const dates = [];
    for (let date = end - (mosaicDays - 1) * day; date <= end; date += day) {
      if (available(date)) dates.push(iso(date));
    }
    if (!dates.length) throw new Error('GIBS returned no mosaic dates');
    dates.latest = iso(latest);
    return dates;
  }

  // NASA publishes browse tiles with a lag: the newest week or so is nearly empty. A mosaic that
  // ends on the newest listed day therefore shows a fraction of the world. Probe one whole-world
  // tile per recent day (about 30 tiny requests, under a second, once a day per browser) and end
  // the mosaic on the last day whose coverage is normal. If the probe fails, keep the newest day.
  async function lastCompleteDay(latest, available, iso) {
    const key = `offbeat.nisarEnd.${iso(latest)}`;
    try { const kept = localStorage.getItem(key); if (kept) return Date.parse(kept); } catch { /* storage off */ }
    const days = [];
    for (let date = latest; days.length < 30 && date > latest - 60 * day; date -= day) if (available(date)) days.unshift(date);
    try {
      const counts = await Promise.all(days.map(async date => {
        const image = await loadImage(`${base}/wmts/epsg3857/best/${product}/default/${iso(date)}/${matrix}/0/0/0.png`);
        if (!image) return null;
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = tileSize;
        const context = canvas.getContext('2d');
        context.drawImage(image, 0, 0);
        const alpha = context.getImageData(0, 0, tileSize, tileSize).data;
        let n = 0;
        for (let i = 3; i < alpha.length; i += 4) if (alpha[i]) n++;
        return n;
      }));
      const known = counts.filter(Number.isFinite).sort((a, b) => a - b);
      if (known.length < 8) return latest;
      const normal = known[Math.floor(known.length / 2)];      // median day: most recent days are complete
      let end = latest;
      for (let i = days.length - 1; i >= 0; i--) if (counts[i] >= 0.6 * normal) { end = days[i]; break; }
      try { localStorage.setItem(key, iso(end)); } catch { /* storage off */ }
      return end;
    } catch {
      return latest;
    }
  }

  // Which mosaic dates have any data under a tile, read from one ancestor tile 4 levels up
  // (it covers 256 tiles). A tile then requests only those dates, usually 1 to 3 of the 12,
  // and a tile over ocean or outside any swath requests nothing at all.
  const ANCESTOR_LEVELS = 4, MASK = 64;                      // coverage kept at 64 x 64 per date
  const ancestors = new Map();                               // "z/x/y" -> Promise<Uint8Array[] | null>
  function ancestorMasks(dates, z, x, y) {
    const key = `${z}/${x}/${y}`;
    if (!ancestors.has(key)) {
      ancestors.set(key, Promise.all(dates.map(async date => {
        const image = await loadImage(`${base}/wmts/epsg3857/best/${product}/default/${date}/${matrix}/${z}/${y}/${x}.png`);
        if (!image) return undefined;                        // unknown: a failed request is never "no data"
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = tileSize;
        const context = canvas.getContext('2d');
        context.drawImage(image, 0, 0);
        const alpha = context.getImageData(0, 0, tileSize, tileSize).data, step = tileSize / MASK;
        const mask = new Uint8Array(MASK * MASK);
        for (let py = 0; py < tileSize; py++) for (let px = 0; px < tileSize; px++)
          if (alpha[(py * tileSize + px) * 4 + 3]) mask[Math.floor(py / step) * MASK + Math.floor(px / step)] = 1;
        return { mask };
      })));
      if (ancestors.size > 64) ancestors.delete(ancestors.keys().next().value);
    }
    return ancestors.get(key);
  }
  async function datesFor(dates, coords) {
    const k = Math.min(ANCESTOR_LEVELS, coords.z);
    if (k === 0) return dates.map((_, i) => i);
    const ax = coords.x >> k, ay = coords.y >> k, masks = await ancestorMasks(dates, coords.z - k, ax, ay);
    // the child's square inside the ancestor, one mask cell wider on each side for thin swath edges
    const cells = MASK >> k, ox = (coords.x - (ax << k)) * cells, oy = (coords.y - (ay << k)) * cells;
    const wanted = dates.map((_, i) => i).filter(i => {
      const mask = masks[i] && masks[i].mask;
      if (!mask) return true;                                // ancestor unknown for this date: ask the tile
      for (let my = Math.max(0, oy - 1); my < Math.min(MASK, oy + cells + 1); my++)
        for (let mx = Math.max(0, ox - 1); mx < Math.min(MASK, ox + cells + 1); mx++)
          if (mask[my * MASK + mx]) return true;
      return false;
    });
    return wanted;
  }

  function createMosaic(dates) {
    const Mosaic = L.GridLayer.extend({
      createTile(coords, done) {
        const tile = document.createElement('canvas');
        tile.width = tile.height = tileSize;
        tile.style.imageRendering = rendering();
        const context = tile.getContext('2d');
        // Keep the previous zoom's tiles visible until all dates for this tile have settled.
        // Otherwise each arriving date replaces the colours and the map flashes while panning.
        const cacheKey = `${coords.z}/${coords.x}/${coords.y}`;
        const cached = renderedTiles.get(cacheKey);
        if (cached) {
          tile.radar = { coords, ...cached };
          context.putImageData(cached.cells, 0, 0);
          requestAnimationFrame(() => { if (!tile.unloaded) done(null, tile); });
          return tile;
        }
        let shown = false;
        const show = error => { if (!shown) { shown = true; done(error, tile); } };
        const levels = new Array(dates.length).fill(null);     // per date: coverage mask
        const colours = dates.map((_, i) => dateColour(i, dates.length));
        let remaining = 0, complete = true;
        const paint = () => {
          if (tile.unloaded) return;
          const owner = new Int8Array(tileSize * tileSize).fill(-1);
          levels.forEach((mask, d) => { if (mask) for (let p = 0; p < mask.length; p++) if (mask[p]) owner[p] = d; });  // newest wins
          const out = new ImageData(tileSize, tileSize);
          for (let p = 0; p < owner.length; p++) {
            const d = owner[p];
            if (d < 0) continue;
            const [r, g, b] = colours[d], i = p * 4;
            out.data[i] = r; out.data[i + 1] = g; out.data[i + 2] = b;
            out.data[i + 3] = 110;
          }
          tile.radar = { coords, cells: out, owner, dates };
          context.putImageData(out, 0, 0);
          if (complete) {
            renderedTiles.set(cacheKey, { cells: out, owner, dates });
            if (renderedTiles.size > 128) renderedTiles.delete(renderedTiles.keys().next().value);
          }
          show(null);
        };
        const settled = () => { if (--remaining === 0) paint(); };
        const url = date => `${base}/wmts/epsg3857/best/${product}/default/${date}/${matrix}/${coords.z}/${coords.y}/${coords.x}.png`;
        // one date; a failed request is tried again later (twice), so a slow NASA reply heals itself
        const fetchDate = (i, tries = 0) => loadImage(url(dates[i])).then(image => {
          if (tile.unloaded) return;
          if (image) {
            try {
              levels[i] = coverage(image);
              settled();
            } catch (error) { complete = false; settled(); }
            return;
          }
          if (tries < 2) { setTimeout(() => !tile.unloaded && fetchDate(i, tries + 1), 3000 * (tries + 1)); return; }
          if (!tile.incomplete) { tile.incomplete = true; failedTiles++; showStatus(); }
          complete = false;
          settled();
        });
        datesFor(dates, coords).then(wanted => {
          if (tile.unloaded) return;
          if (!wanted.length) { paint(); return; }           // no swath here in this window
          remaining = wanted.length;
          wanted.forEach(i => fetchDate(i));
        });
        return tile;
      },
    });
    const mosaic = new Mosaic({
      pane: 'nisarRadar', maxNativeZoom: nativeZoom, maxZoom: 19, opacity: 0.9,
      updateWhenIdle: true, updateWhenZooming: false, keepBuffer: 1,   // one ring of spare tiles: 12 requests each
      attribution: 'Radar &copy; NASA/ISRO NISAR, NASA GIBS',
    });
    mosaic.on('tileload', e => { tiles.add(e.tile); scheduleStatus(); });
    mosaic.on('tileunload', e => {
      tiles.delete(e.tile);
      e.tile.unloaded = true;
      if (e.tile.incomplete) { failedTiles = Math.max(0, failedTiles - 1); showStatus(); }
    });
    return mosaic;
  }

  // The layer shows where and when NISAR imaged the ground in the mosaic window, not brightness.
  // NASA's browse tiles are a stretched false-colour picture whose level jumps from tile to tile
  // and whose detail is speckle on a half-transparent checkerboard: fine for "is there data", not
  // for a seamless image. Coverage = a 3 x 3 neighbourhood that is at least 35 % opaque, which
  // closes the checkerboard without growing real swath edges.
  const MIN_COVER = 0.35;
  function coverage(image) {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = tileSize;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(image, 0, 0);
    const px = ctx.getImageData(0, 0, tileSize, tileSize).data;
    const mask = new Uint8Array(tileSize * tileSize);
    const horizontal = new Uint16Array(tileSize * tileSize);
    for (let y = 0; y < tileSize; y++) for (let x = 0; x < tileSize; x++) {
      const p = y * tileSize + x;
      horizontal[p] = px[p * 4 + 3] + (x ? px[(p - 1) * 4 + 3] : 0) + (x + 1 < tileSize ? px[(p + 1) * 4 + 3] : 0);
    }
    for (let y = 0; y < tileSize; y++) for (let x = 0; x < tileSize; x++) {
      const p = y * tileSize + x;
      const a = horizontal[p] + (y ? horizontal[p - tileSize] : 0) + (y + 1 < tileSize ? horizontal[p + tileSize] : 0);
      const cells = (x === 0 || x === tileSize - 1 ? 2 : 3) * (y === 0 || y === tileSize - 1 ? 2 : 3);
      if (a >= 255 * cells * MIN_COVER) mask[p] = 1;
    }
    return mask;
  }

  // date order -> colour: oldest deep blue, through teal and amber, to coral for the newest day
  const DATE_STOPS = [[0, [38, 70, 140]], [0.35, [42, 157, 143]], [0.7, [233, 196, 106]], [1, [231, 111, 81]]];
  function dateColour(d, count) {
    const t = count > 1 ? d / (count - 1) : 1;
    let k = 1; while (k < DATE_STOPS.length - 1 && t > DATE_STOPS[k][0]) k++;
    const [t0, a] = DATE_STOPS[k - 1], [t1, b] = DATE_STOPS[k], f = (t - t0) / (t1 - t0);
    return a.map((c, j) => Math.round(c + (b[j] - c) * f));
  }
  const legendCss = n => `linear-gradient(90deg, ${Array.from({ length: n }, (_, d) => `rgb(${dateColour(d, n).join(',')})`).join(',')})`;

  // Hidden coverage is detached, not made transparent, so it stops downloading NASA tiles
  // that would compete with the imagery the user is looking at.
  function attach() {
    const visible = map.getZoom() < HIDE_FROM;
    if (visible && !map.hasLayer(layer)) layer.addTo(map).setOpacity(0.9);
    if (!visible && map.hasLayer(layer)) map.removeLayer(layer);
  }

  async function update() {
    status.hidden = !toggle.checked;
    if (!toggle.checked) {
      if (layer) map.removeLayer(layer);
      return;
    }
    if (loading) return;
    loading = true;
    try {
      if (!layer) {
        status.textContent = 'Loading NISAR radar coverage…';
        const dates = await getDates();
        layer = createMosaic(dates);
        const lag = dates.latest !== dates.at(-1) ? ` (NASA tiles after this are still incomplete, newest ${dates.latest})` : '';
        caption = `Where NISAR imaged the ground, coloured by date${lag} | from NASA GIBS browse tiles`;
        legend = document.createElement('span');
        legend.className = 'nisar-legend';
        legend.innerHTML = `<span class="nisar-legend__ramp" style="background:${legendCss(dates.length)}"></span>`;
        legend.prepend(dates[0] + ' ');
        legend.append(' ' + dates.at(-1));
      }
      if (toggle.checked) {
        attach();
        showStatus();
      }
    } catch {
      status.textContent = 'NASA radar imagery unavailable. Toggle the layer to retry.';
    } finally {
      loading = false;
    }
  }

  toggle.addEventListener('change', update);
  map.whenReady(update);
  map.on('moveend', scheduleStatus);
  map.on('zoomend', () => {
    const r = rendering();
    for (const tile of tiles) tile.style.imageRendering = r;
    if (layer && toggle.checked) attach();
    showStatus();
  });

  return function cellBounds(latlng) {
    if (!toggle.checked || !layer || !map.hasLayer(layer)) return null;
    const zoom = Math.min(map.getZoom(), nativeZoom);
    const point = map.project(latlng, zoom);
    const column = Math.floor(point.x / tileSize);
    const row = Math.floor(point.y / tileSize);
    const wrapped = L.Util.wrapNum(column, [0, 2 ** zoom]);
    for (const tile of tiles) {
      if (!tile.radar || !tile.radar.cells) continue;          // a tile with no swath in the window has no cells
      const { coords, cells } = tile.radar;
      if (coords.z !== zoom || coords.x !== wrapped || coords.y !== row) continue;
      const size = tileSize / cells.width;
      const x = Math.floor((point.x - column * tileSize) / size);
      const y = Math.floor((point.y - row * tileSize) / size);
      if (!cells.data[(y * cells.width + x) * 4 + 3]) return null;
      const origin = L.point(column * tileSize + x * size, row * tileSize + y * size);
      return [map.unproject(origin, zoom), map.unproject(origin.add([size, size]), zoom)];
    }
    return null;
  };
};

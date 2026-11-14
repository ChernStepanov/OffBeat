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
  let failedTiles = 0, inflight = 0, statusTimer;
  let layer, loading, caption;
  // Smooth scaling at every zoom: hard-edged magnified pixels read as noise and blocks, and the
  // tiles Leaflet stretches while the next zoom loads look broken when they are pixelated.
  const rendering = () => 'auto';

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
    const busy = inflight > 0 ? ` | Loading NASA radar: ${inflight} request${inflight === 1 ? '' : 's'} left` : '';
    status.textContent = caption + busy + (failedTiles
      ? ` | ${failedTiles} incomplete tile${failedTiles === 1 ? '' : 's'}: NASA did not answer, retrying. These gaps are not confirmed missing coverage.`
      : ' | Transparent gaps: no browse coverage in this time window.');
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
        return mask;
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
    return dates.map((_, i) => i).filter(i => {
      const mask = masks[i];
      if (!mask) return true;                                // ancestor unknown for this date: ask the tile
      for (let my = Math.max(0, oy - 1); my < Math.min(MASK, oy + cells + 1); my++)
        for (let mx = Math.max(0, ox - 1); mx < Math.min(MASK, ox + cells + 1); mx++)
          if (mask[my * MASK + mx]) return true;
      return false;
    });
  }

  function createMosaic(dates) {
    const Mosaic = L.GridLayer.extend({
      createTile(coords, done) {
        const tile = document.createElement('canvas');
        tile.width = tile.height = tileSize;
        tile.style.imageRendering = rendering();
        const context = tile.getContext('2d');
        // Show the tile as soon as any date arrives and repaint as the rest come in, instead of
        // waiting for the slowest of all the mosaic requests. Older dates are always painted
        // first, so a newer acquisition covers an older one whatever order they arrive in.
        const slots = new Array(dates.length).fill(null);
        let shown = false;
        const show = error => { if (!shown) { shown = true; done(error, tile); } };
        const paint = () => {
          context.clearRect(0, 0, tileSize, tileSize);
          for (const image of slots) if (image) context.drawImage(image, 0, 0);
          tile.radar = { coords, pixels: context.getImageData(0, 0, tileSize, tileSize) };
          colorTile(tile);
        };
        const url = date => `${base}/wmts/epsg3857/best/${product}/default/${date}/${matrix}/${coords.z}/${coords.y}/${coords.x}.png`;
        // one date; a failed request is tried again later (twice), so a slow NASA reply heals itself
        const fetchDate = (i, tries = 0) => loadImage(url(dates[i])).then(image => {
          if (tile.unloaded) return;
          if (image) {
            slots[i] = image;
            try { paint(); } catch (error) { context.clearRect(0, 0, tileSize, tileSize); show(error); return; }
            show(null);
            return;
          }
          if (tries < 2) { setTimeout(() => !tile.unloaded && fetchDate(i, tries + 1), 3000 * (tries + 1)); return; }
          if (!tile.incomplete) { tile.incomplete = true; failedTiles++; showStatus(); }
          show(null);
        });
        datesFor(dates, coords).then(wanted => {
          if (tile.unloaded) return;
          if (!wanted.length) { show(null); return; }        // no swath here in this window: nothing to ask for
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
    mosaic.on('tileload', e => tiles.add(e.tile));
    mosaic.on('tileunload', e => {
      tiles.delete(e.tile);
      e.tile.unloaded = true;
      if (e.tile.incomplete) { failedTiles = Math.max(0, failedTiles - 1); showStatus(); }
    });
    return mosaic;
  }

  // Recolour every pixel of the NASA browse tile in place: one screen cell is one data cell at
  // the tile's own level, never an artificial block whose ground size changes with zoom.
  function colorTile(tile) {
    const context = tile.getContext('2d');
    const image = new ImageData(new Uint8ClampedArray(tile.radar.pixels.data), tileSize, tileSize);
    const pixels = image.data;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] === 0) continue;
      // Brightness of the NASA browse image on a display-only ramp.
      const strength = Math.round(0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2]);
      pixels[i] = strength;
      pixels[i + 1] = 70;
      pixels[i + 2] = 255 - strength;
      pixels[i + 3] = 255;
    }
    tile.radar.cells = image;
    context.putImageData(image, 0, 0);
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
        caption = `NASA NISAR quick-look | ${mosaicDays}-day mosaic through ${dates.at(-1)}${lag} | Blue to red: browse brightness, not calibrated; straight seams come from NASA's tiles`;
      }
      if (toggle.checked) {
        layer.addTo(map);
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
  map.on('zoomend', () => { const r = rendering(); for (const tile of tiles) tile.style.imageRendering = r; });

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

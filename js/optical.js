// Датированные RGB-вырезки; мозаика остаётся явно обозначенным контекстом.
window.OB = window.OB || {};

OB.opticalScenes = function (index, site) {
  const bbox = site.grid.bbox, expected = [bbox.w, bbox.s, bbox.e, bbox.n];
  if (!index || index.site !== site.id || !Array.isArray(index.entries) || JSON.stringify(index.bbox) !== JSON.stringify(expected)) return [];
  const unique = new Map();
  for (const row of index.entries || []) {
    if (!row || typeof row.scene?.scene_id !== 'string') continue;
    const scene = row.scene, render = scene && scene.render;
    if (row.crop_status !== 'ready' || !render || render.crs !== 'EPSG:4326' ||
        JSON.stringify(render.bbox) !== JSON.stringify(expected) ||
        !/^[\w-]+\.png$/.test(render.file) || !/^\d{4}-\d{2}-\d{2}$/.test(scene.date) ||
        !(render.valid_fraction > 0 && render.valid_fraction <= 1)) continue;
    unique.set(scene.scene_id, scene);
  }
  return [...unique.values()].sort((a, b) => a.date.localeCompare(b.date) || a.scene_id.localeCompare(b.scene_id));
};

OB.nearestOpticalScene = function (scenes, date) {
  const target = Date.parse(date);
  return scenes.reduce((best, scene) => !best || Math.abs(Date.parse(scene.date) - target) <
    Math.abs(Date.parse(best.date) - target) ? scene : best, null);
};

OB.createOpticalView = function (map) {
  const select = document.getElementById('optical-date');
  const caption = document.getElementById('optical-caption');
  const details = document.getElementById('optical-detail');
  let site = null, scenes = [], reference = null, layer = null, generation = 0, imageGeneration = 0;
  const cache = new Map();
  map.createPane('opticalImagery');
  map.getPane('opticalImagery').style.zIndex = 250;
  map.getPane('opticalImagery').style.pointerEvents = 'none';

  function removeImage() {
    ++imageGeneration;
    if (layer) map.removeLayer(layer);
    layer = null;
  }
  function context(message = 'Esri World Imagery; dates vary by location. Geographic context only.') {
    removeImage();
    caption.textContent = 'Esri mosaic - geographic context';
    caption.title = message;
    details.textContent = message;
  }
  function resetOptions() {
    select.replaceChildren();
    const option = document.createElement('option');
    option.value = 'context'; option.textContent = 'Esri mosaic (dates vary)';
    select.appendChild(option); select.value = 'context';
  }
  function show() {
    if (!site || select.value === 'context') { context(); return; }
    const scene = select.value === 'auto' ? OB.nearestOpticalScene(scenes, reference) : scenes.find(s => s.scene_id === select.value);
    if (!scene) { context('No prepared RGB image for this selection. Esri context is shown.'); return; }
    removeImage();
    const ticket = imageGeneration;
    const b = scene.render.bbox;
    const cloud = Number.isFinite(scene.scene_cloud_cover_pct) ? scene.scene_cloud_cover_pct.toFixed(1) + '%' : 'unknown';
    const message = `Sentinel-2 ${scene.date}; tile cloud ${cloud}; clouds over this study area not assessed. Scene: ${scene.scene_id}. RGB inside the study area; Esri context outside and through nodata gaps.`;
    caption.textContent = `Loading Sentinel-2 ${scene.date}...`;
    details.textContent = message;
    caption.title = message;
    layer = L.imageOverlay(`data/${site.id}/optical/${scene.render.file}`, [[b[1], b[0]], [b[3], b[2]]], {
      pane: 'opticalImagery', interactive: false,
      attribution: 'Contains modified Copernicus Sentinel data; Sentinel-2 via Earth Search'
    });
    layer.on('load', () => {
      if (ticket !== imageGeneration) return;
      caption.textContent = `Sentinel-2 ${scene.date} - tile cloud ${cloud}`;
    });
    layer.on('error', () => {
      if (ticket !== imageGeneration) return;
      select.value = 'context';
      context(`RGB image ${scene.date} failed to load. Esri context is shown; no dated image is available in this view.`);
    });
    layer.addTo(map);
  }
  select.addEventListener('change', show);
  resetOptions();

  return {
    async loadSite(nextSite) {
      const ticket = ++generation;
      site = nextSite; scenes = []; reference = nextSite.dates.at(-1);
      resetOptions(); select.disabled = true;
      context('Loading prepared optical images. Esri context is shown until an image is ready.');
      if (!cache.has(site.id)) {
        cache.set(site.id, fetch(`data/${site.id}/optical/index.json`, {signal: AbortSignal.timeout(12000)}).then(r => {
          if (!r.ok) throw new Error('Optical index unavailable');
          return r.json();
        }).catch(() => null));
      }
      const index = await cache.get(nextSite.id);
      if (ticket !== generation) return;
      scenes = index ? OB.opticalScenes(index, nextSite) : [];
      if (!scenes.length) {
        context('No prepared dated RGB images for this site. Esri mosaic is geographic context only.');
        return;
      }
      const auto = document.createElement('option');
      auto.value = 'auto'; auto.textContent = 'Auto - nearest to sample change date or latest NISAR';
      select.appendChild(auto);
      for (const scene of scenes) {
        const option = document.createElement('option');
        option.value = scene.scene_id;
        option.textContent = `Sentinel-2 ${scene.date}`;
        option.title = scene.scene_id;
        select.appendChild(option);
      }
      select.disabled = false; select.value = 'auto'; show();
    },
    pickPixel(pixel) {
      if (!site) return;
      reference = pixel.since || site.dates.at(-1);
      if (select.value === 'auto') show();
    },
    clear() {
      ++generation; site = null; scenes = [];
      resetOptions(); select.disabled = true; context();
    }
  };
};

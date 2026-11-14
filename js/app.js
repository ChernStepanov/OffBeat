// Wires sites, the z-score raster, the pixel card, the patch list and the player.
(async function () {
  const $ = id => document.getElementById(id);
  try { await OB.loadData(); } catch (error) {
    $('data-status').textContent = 'Real data unavailable: ' + error.message;
    $('sb-state').textContent = error.message;
    $('sb-src').textContent = 'No measurements loaded';
    $('play-hint').textContent = 'Cannot load real data. Check the static server and data/mexico.json.';
    return;
  }
  const state = { site: null, pixel: null, cell: null, z: 2.5, patches: [], raster: null, coverRaster: null, extra: {}, vectors: [], loading: 0 };

  // Identical imagery and zoom limits; grey basemap under the colour NISAR layer.
  const IMAGERY = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const LABELS = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
  // the data map gets a quiet light canvas so measurements read clearly; the photo stays on the right
  const CANVAS = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
  const CANVAS_LABELS = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}";
  const canvasCredit = 'Basemap &copy; Esri, HERE, Garmin, OpenStreetMap contributors';
  const imageryCredit = 'Imagery &copy; Esri, Vantor, Earthstar Geographics';
  const labelsCredit = 'Labels &copy; Esri, HERE, Garmin, OpenStreetMap contributors';
  // minZoom 2 keeps the world filling the panel instead of grey margins around a tiny globe
  const map = L.map("map", { zoomControl: true, maxZoom: 19, minZoom: 2, worldCopyJump: true });
  const optic = L.map("optic", { zoomControl: true, maxZoom: 19, minZoom: 2, worldCopyJump: true });
  const optical = OB.bindOptical(optic, $('optical-date'), $('optical-status'));
  const labelLayers = [map, optic].map(m => {
    m.attributionControl.setPrefix('Leaflet');
    const isData = m === map;
    L.tileLayer(isData ? CANVAS : IMAGERY, { maxZoom: 19, maxNativeZoom: isData ? 16 : 19, className: isData ? 'context-canvas' : 'context-imagery', attribution: isData ? canvasCredit : imageryCredit }).addTo(m);
    m.createPane('placeLabels');
    m.getPane('placeLabels').style.zIndex = 625;
    m.getPane('placeLabels').style.pointerEvents = 'none';
    m.createPane('selectedCell');
    m.getPane('selectedCell').style.zIndex = 640;
    m.getPane('selectedCell').style.pointerEvents = 'none';
    return L.tileLayer(isData ? CANVAS_LABELS : LABELS, { pane: 'placeLabels', maxZoom: 19, maxNativeZoom: isData ? 16 : 19, attribution: isData ? canvasCredit : labelsCredit }).addTo(m);
  });
  let areaLayers = [];
  let syncing = false;
  const sync = (a, b) => a.on("move", () => { if (syncing) return; syncing = true; b.setView(a.getCenter(), a.getZoom(), { animate: false }); syncing = false; });
  sync(map, optic); sync(optic, map);
  function updateViewMetrics() {
    const size = map.getSize();
    const center = size.divideBy(2);
    if (!size.x || !size.y) return;
    const metersPerPixel = map.distance(
      map.containerPointToLatLng(center.subtract([1, 0])),
      map.containerPointToLatLng(center.add([1, 0])),
    ) / 2;
    // Equivalent nadir camera altitude for an assumed 45° vertical field of view.
    const altitude = metersPerPixel * size.y / (2 * Math.tan(Math.PI / 8));
    const scale = metersPerPixel >= 10 ? Math.round(metersPerPixel)
      : Number(metersPerPixel.toPrecision(2));
    const height = altitude >= 1000 ? `${Math.round(altitude / 100) / 10} km` : `${Math.round(altitude)} m`;
    $('map-view-metrics').textContent = `Scale: ${scale} m/px | Approx. viewing altitude: ${height}`;
    $('map-view-metrics').title = 'Altitude equivalent for a top-down view with a 45° vertical field of view.';
  }
  map.on('move resize', updateViewMetrics);
  OB.bindArchive(() => map.getCenter().wrap());
  const labelsButton = $('l-labels');
  const labelsVisible = () => labelsButton.getAttribute('aria-pressed') === 'true';
  const updateWaterLabels = OB.bindWaterLabels([map, optic], $('water-status'));
  const viewportKey = 'offbeat.map.viewport.v1';
  let previousViewport = null, viewportReady = !!OB.tourWanted;
  try { previousViewport = JSON.parse(localStorage.getItem(viewportKey) || 'null'); } catch (_) { /* storage unavailable */ }
  function viewportAnchor() {
    const p = new URL(location.href).searchParams;
    return JSON.stringify([p.get('lat'), p.get('lon')]);
  }
  function saveViewport() {
    if (!viewportReady || !state.site) return;
    const c = map.getCenter();
    try { localStorage.setItem(viewportKey, JSON.stringify({site:state.site.id, anchor:viewportAnchor(), lat:c.lat, lon:c.lng, zoom:map.getZoom()})); } catch (_) { /* storage unavailable */ }
  }
  map.on('moveend', saveViewport);
  const box = () => L.rectangle([[0, 0], [0, 0]], {
    pane: 'selectedCell', color: '#ffcc00', weight: 3, fill: false, interactive: false,
  });
  const cellBox = box(), cellBoxOptic = box();
  function showCellBounds(bounds) {
    const [a, b] = bounds.map(corner => map.project(corner, 0));
    const center = map.unproject(a.add(b).divideBy(2), 0);
    const coordinates = `${center.lat.toFixed(6)}, ${center.wrap().lng.toFixed(6)}`;
    $('p-loc').textContent = coordinates;
  }

  // --- side lists ---
  $("sites").innerHTML = OB.SITES.map(s =>
    `<li><button type="button" data-site="${s.id}" aria-pressed="false">${s.name}<small>${s.region}</small></button></li>`).join("");
  $("sites").addEventListener("click", e => { const b = e.target.closest("button"); if (b) { ++navigationSerial; ++searchSerial; $('place-submit').disabled = false; $('place-results').replaceChildren(); $('place-status').textContent = ''; $('place-query').value = ''; document.dispatchEvent(new Event('ob:manual-navigation')); clearSearchMarkers(); const url = new URL(location.href); url.searchParams.delete('lat'); url.searchParams.delete('lon'); history.replaceState(null, '', url); loadSite(b.dataset.site); } });
  $("styles").innerHTML = Object.entries(OB.STYLES).map(([k, s]) =>
    `<li><i class="dot" style="background:${s.color}"></i><div><b>${s.name}</b><span class="d">${s.what}</span></div></li>`).join("");

  $("z").addEventListener("input", e => { state.z = +e.target.value; $("z-out").textContent = state.z; refresh(); });
  $("l-offbeat").addEventListener("change", drawRaster);
  $("l-cover").addEventListener("change", drawCover);
  labelsButton.addEventListener('click', () => {
    labelsButton.setAttribute('aria-pressed', String(!labelsVisible()));
    [map, optic].forEach((m, i) => {
      if (labelsVisible()) labelLayers[i].addTo(m);
      else m.removeLayer(labelLayers[i]);
    });
    updateWaterLabels(labelsVisible());
    drawAreaLabels();
  });

  // The endpoint can be replaced by the operator without changing the UI.
  const geocoder = window.OB_GEOCODER_URL || 'https://photon.komoot.io/api/';
  const searchCache = new Map();
  let lastSearch = 0, searchMarkers = [], searchSerial = 0, navigationSerial = 0;
  const regions = {
    world: [[-45, -125], [62, 45]],                        // centred west: every demo site is in the Americas
    europe: [[35, -12], [71, 45]],
    africa: [[-35, -18], [37, 52]],
    asia: [[-10, 40], [75, 180]],
    oceania: [[-48, 110], [10, 180]],
    americas: [[-56, -170], [72, -34]],
  };
  async function showRegion(id) {
    const bounds = regions[id];
    $('place-query').value = '';
    $('l-offbeat').checked = false; drawRaster();
    $('l-cover').checked = false; drawCover(); clearSiteLayers();
    if (!await showPlace({lat: (bounds[0][0] + bounds[1][0]) / 2, lon: (bounds[0][1] + bounds[1][1]) / 2, bounds})) return;
    clearSearchMarkers();
    $('site-name').textContent = id === 'world' ? 'World' : id[0].toUpperCase() + id.slice(1);
    $('map-caption').textContent = 'Measured NISAR series exist at the marked demo sites. Click one to open it.';
    document.querySelectorAll('#regions button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.region === id)));
  }
  $('regions').addEventListener('click', event => {
    const button = event.target.closest('button[data-region]');
    if (button) showRegion(button.dataset.region);
  });
  function clearSearchMarkers() {
    searchMarkers.forEach(([m, marker]) => m.removeLayer(marker));
    searchMarkers = [];
  }
  function clearPixel() {
    OB.sonify.stop(); state.cell = null; state.pixel = null;
    $('val-win').hidden = true;
    [map, optic].forEach((m, i) => { const layer = i ? cellBoxOptic : cellBox; if (m.hasLayer(layer)) m.removeLayer(layer); });
    $('px-id').textContent = 'No prepared measurement series here';
    for (const id of ['p-cover','p-peers','p-z','p-style','p-since','p-loc','p-quality']) $(id).textContent = 'Unavailable';
    $('p-extra').innerHTML = '';
    $('plot-s1').hidden = true;
    for (const id of ['c-bs','c-disp']) OB.chart.empty($(id), 'No measured NISAR series here. Open a demo site on the map or in the list.');
    $('play').disabled = true; $('stop').disabled = true;
    $('play-hint').textContent = 'No measured series covers the selected location.';
  }
  async function showPlace(place) {
    const ticket = ++navigationSerial;
    ++state.loading;
    ++searchSerial; $('place-submit').disabled = false; $('place-results').replaceChildren();
    document.querySelectorAll('#regions button').forEach(button => button.setAttribute('aria-pressed', 'false'));
    document.dispatchEvent(new Event('ob:manual-navigation'));
    const site = OB.SITES.find(s => { const b = s.grid.bbox; return place.lat >= b.s && place.lat <= b.n && place.lon >= b.w && place.lon <= b.e; });
    clearSearchMarkers();
    if (site) await loadSite(site.id);
    if (ticket !== navigationSerial) return false;
    if (site) {
      const g = site.grid, b = g.bbox;
      const x = Math.min(g.w - 1, Math.floor((place.lon - b.w) / (b.e - b.w) * g.w));
      const y = Math.min(g.h - 1, Math.floor((b.n - place.lat) / (b.n - b.s) * g.h));
      await pickCell(y * g.w + x, false);
      if (ticket !== navigationSerial) return false;
      $('data-status').textContent = `${site.message} Showing a measured sample at the selected location.`;
      $('place-status').textContent = `Inside ${site.name}: measured sample selected.`;
    } else {
      optical.context();
      clearPixel();
      $('data-status').textContent = 'No prepared pixel series at this location. Radar imagery is available where the global mosaic has coverage.';
      $('place-status').textContent = 'No pixel series here. Choose a demo site for charts and audio.';
      $('site-name').textContent = 'Search location'; $('map-caption').textContent = 'Pixel series unavailable at this location';
      $('source-link').hidden = true; $('site-layers').hidden = true;
      $('sb-state').textContent = 'No prepared NISAR series at search location'; $('sb-count').textContent = 'No measured series'; $('sb-src').textContent = 'Context: Esri basemap and photo mosaic';
      document.querySelectorAll('#sites button').forEach(b => b.setAttribute('aria-pressed', 'false'));
      $('top').tBodies[0].innerHTML = '<tr><td colspan="5">No prepared NISAR data at this location.</td></tr>';
    }
    const url = new URL(location.href); url.searchParams.set('lat', String(place.lat)); url.searchParams.set('lon', String(place.lon)); history.replaceState(null, '', url);
    if (place.bounds && !site) map.fitBounds(place.bounds, { padding: [16, 16], maxZoom: 13 });
    else map.setView([place.lat, place.lon], site ? Math.max(map.getZoom(), 13) : 12);
    [map, optic].forEach(m => {
      const marker = L.circleMarker([place.lat, place.lon], { radius: 7, color: '#fff', weight: 2, fillColor: '#c00000', fillOpacity: 1, interactive: false }).addTo(m);
      searchMarkers.push([m, marker]);
    });
    saveViewport();
    $('map-win').scrollIntoView({ block: 'start', behavior: 'smooth' });
    return true;
  }
  $('place-search').addEventListener('submit', async e => {
    e.preventDefault();
    const serial = ++searchSerial;
    $('place-submit').disabled = false;
    const query = OB.normalizePlaceQuery($('place-query').value), parsed = OB.parseCoordinates(query), results = $('place-results');
    results.replaceChildren();
    if (!query) { $('place-status').textContent = ''; return; }
    if (parsed.kind === 'invalid') { $('place-status').textContent = 'Enter latitude, longitude (for example 19.43, -99.08). Latitude must be between -85.05 and 85.05; longitude between -180 and 180.'; return; }
    if (parsed.kind === 'coordinates') { await showPlace(parsed); return; }
    if (query.length > 200) { $('place-status').textContent = 'Search text is too long.'; return; }
    $('place-submit').disabled = true; $('place-status').textContent = 'Searching places...';
    try {
      let features = searchCache.get(query.toLowerCase());
      if (!features) {
        const delay = Math.max(0, 1000 - (Date.now() - lastSearch));
        if (delay) await new Promise(resolve => setTimeout(resolve, delay));
        lastSearch = Date.now();
        features = await OB.geocodePlace(query, geocoder);
        searchCache.set(query.toLowerCase(), features);
      }
      if (serial !== searchSerial) return;
      for (const feature of features) {
        const coords = feature.geometry && feature.geometry.coordinates;
        if (!Array.isArray(coords) || !Number.isFinite(coords[0]) || !Number.isFinite(coords[1]) || Math.abs(coords[0]) > 180 || Math.abs(coords[1]) > 85.05112878) continue;
        const props = feature.properties || {}, names = [props.name, props.city, props.county, props.state, props.country].filter((v,i,a) => typeof v === 'string' && v && a.indexOf(v) === i);
        const label = names.join(', ') || `${coords[1].toFixed(4)}, ${coords[0].toFixed(4)}`;
        const li = document.createElement('li'), button = document.createElement('button');
        button.type = 'button'; button.textContent = label; button.dir = 'auto'; button.translate = false;
        button.addEventListener('click', async () => {
          results.replaceChildren(); $('place-query').value = label;
          let bounds = null; const extent = props.extent;
          if (Array.isArray(extent) && extent.length === 4 && extent.every(Number.isFinite) && extent[0] <= extent[2] && extent[3] <= extent[1] && extent[0] >= -180 && extent[2] <= 180 && extent[3] >= -85.05112878 && extent[1] <= 85.05112878) bounds = [[extent[3],extent[0]],[extent[1],extent[2]]];
          await showPlace({lat:coords[1],lon:coords[0],bounds});
        });
        li.appendChild(button); results.appendChild(li);
      }
      $('place-status').textContent = results.children.length ? 'Choose a result.' : 'No places found. Try another name or coordinates.';
    } catch (error) {
      if (serial === searchSerial) $('place-status').textContent = 'Place search is unavailable. Try again or enter coordinates.';
    } finally { if (serial === searchSerial) $('place-submit').disabled = false; }
  });

  function drawAreaLabels() {
    areaLayers.forEach(([m, layer]) => m.removeLayer(layer));
    areaLayers = [];
    if (!state.site || !labelsVisible()) return;
  }

  // --- colours ---
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const STYLE_RGB = OB.STYLE_KEYS.map(k => k ? rgb(OB.STYLES[k].color) : [90, 90, 90]);
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  // diverging: negative (sinking, away from the satellite) red, positive blue
  const diverging = max => v => {
    if (isNaN(v) || Math.abs(v) < max * 0.15) return null;   // hide motion within noise
    const t = Math.min(1, Math.abs(v) / max);
    return (v < 0 ? mix([255, 200, 160], [192, 0, 0], t) : mix([170, 200, 255], [0, 40, 200], t)).concat(Math.round(90 + 165 * t));
  };
  const heat = (lo, hi) => v => {
    if (isNaN(v) || v < lo) return null;
    const t = Math.min(1, (v - lo) / (hi - lo));
    return mix([255, 255, 0], [255, 0, 0], t).concat(Math.round(150 + 105 * t));
  };

  // layers a site may carry beyond the Off-Beat raster (written by pipeline/run.py)
  const SITE_LAYERS = {
    damage:    { label: "Damage proxy (coherence loss)", unit: "z", lo: "2", hi: "8", ramp: "linear-gradient(90deg,#ffff00,#ff0000)", paint: heat(2, 8), card: "Damage z", fmt: v => v.toFixed(1) },
    coseismic: { label: "Ground motion in the quake",    unit: "cm, line of sight", lo: "-10", hi: "+10", ramp: "linear-gradient(90deg,#c00000,#ffc8a0,#c0c0c0,#aac8ff,#0028c8)", paint: diverging(10), card: "Quake motion", fmt: v => v.toFixed(1) + " cm" },
    up:        { label: "Vertical motion",               unit: "cm/yr", lo: "-30", hi: "+30", ramp: "linear-gradient(90deg,#c00000,#ffc8a0,#c0c0c0,#aac8ff,#0028c8)", paint: diverging(30), card: "Vertical", fmt: v => v.toFixed(1) + " cm/yr" },
    east:      { label: "East-west motion",              unit: "cm/yr, east +", lo: "-8", hi: "+8", ramp: "linear-gradient(90deg,#c00000,#ffc8a0,#c0c0c0,#aac8ff,#0028c8)", paint: diverging(8), card: "East-west", fmt: v => v.toFixed(1) + " cm/yr" },
    fires:     { label: "Active fires (NASA FIRMS)" },
    alerts:    { label: "Deforestation alerts" }
  };

  function paint(fn) {
    const g = state.site.grid, cv = document.createElement("canvas");
    cv.width = g.w; cv.height = g.h;
    const ctx = cv.getContext("2d"), img = ctx.createImageData(g.w, g.h);
    for (let i = 0; i < g.w * g.h; i++) {
      const px = fn(i); if (!px) continue;
      img.data.set(px, i * 4);
    }
    ctx.putImageData(img, 0, 0);
    const b = g.bbox;
    return L.imageOverlay(cv.toDataURL(), [[b.s, b.w], [b.n, b.e]], { className: "raster", interactive: false });
  }

  // Leaflet stretches the raster between its corners in Web Mercator.
  function projectedGrid(g) {
    const b = g.bbox;
    const origin = map.project([b.n, b.w], 0);
    const end = map.project([b.s, b.e], 0);
    return { origin, width: (end.x - origin.x) / g.w, height: (end.y - origin.y) / g.h };
  }

  function drawRaster() {
    $('map-caption').textContent = 'Measured samples: grey in step, blue below and red above their same-class neighbours (|z| over the threshold)';
    if (state.raster) map.removeLayer(state.raster);
    state.raster = null;
    if (!$("l-offbeat").checked) return;
    const g = state.site.grid, t = state.z;
    if (state.site.analysis_status === 'exploratory_sparse_samples') {
      const pts = state.site.pixels.filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon));
      state.raster = L.featureGroup(pts.map(p => {
        const off = Number.isFinite(p.z) && Math.abs(p.z) >= t;
        return L.circleMarker([p.lat, p.lon], off
          ? { radius: 4.5, weight: 1, color: '#fff', fillColor: p.z < 0 ? '#1d4fd8' : '#d0161b', fillOpacity: .9, interactive: false }
          : { radius: 2, weight: 0, fillColor: '#5b6470', fillOpacity: .55, interactive: false });
      })).addTo(map);
      return;
    }
    if (!g.z.some(Number.isFinite) && state.site.pixels) {
      // Prepared series belong in the charts, not a separate square on the map.
      return;
    }
    state.raster = paint(i => {
      const a = Math.abs(g.z[i]);
      if (!Number.isFinite(g.z[i]) || a < t || g.cover[i] === 80) return null;
      const [r, gg, b] = STYLE_RGB[g.style[i]];
      return [r, gg, b, Math.round(255 * Math.min(1, 0.55 + (a - t) / 6))];
    }).addTo(map);
  }

  function drawCover() {
    if (state.coverRaster) map.removeLayer(state.coverRaster);
    state.coverRaster = null;
    if (!$("l-cover").checked) return;
    const g = state.site.grid;
    state.coverRaster = paint(i => OB.COVER[g.cover[i]] ? rgb(OB.COVER[g.cover[i]].color).concat(150) : null).addTo(map);
    if (state.raster) state.raster.bringToFront();
  }

  function restack() {
    Object.values(state.extra).forEach(l => l && l.bringToFront && l.bringToFront());
    if (state.raster) state.raster.bringToFront();
  }

  // --- site layers: list only what this site has ---
  function buildSiteLayers() {
    const s = state.site, have = Object.keys(s.grid.extra || {});
    if (s.context && s.context.fires) have.push("fires");
    if (s.context && s.context.alerts) have.push("alerts");
    $("site-layers").hidden = !have.length;
    $("site-layer-list").innerHTML = have.map(k =>
      `<label><input type="checkbox" data-layer="${k}"> ${SITE_LAYERS[k].label}</label>`).join("");
    $("legend").hidden = true;
  }
  $("site-layer-list").addEventListener("change", e => {
    const k = e.target.dataset.layer; if (!k) return;
    toggleLayer(k, e.target.checked);
  });

  function toggleLayer(k, on) {
    const s = state.site, L0 = SITE_LAYERS[k];
    if (state.extra[k]) { [map, optic].forEach(m => m.hasLayer(state.extra[k]) && m.removeLayer(state.extra[k])); delete state.extra[k]; }
    if (state.extra[k + "_o"]) { optic.removeLayer(state.extra[k + "_o"]); delete state.extra[k + "_o"]; }
    if (on) {
      if (k === "fires") {
        const pts = s.context.fires.map(f => L.circleMarker([f.lat, f.lon], { radius: 2.5, color: "#000", weight: 1, fillColor: "#ff6600", fillOpacity: 1 })
          .bindTooltip(`Fire ${f.date}${f.source ? ", " + f.source : ""}`));
        state.extra[k] = L.layerGroup(pts).addTo(map);
        state.extra[k + "_o"] = L.layerGroup(s.context.fires.map(f => L.circleMarker([f.lat, f.lon], { radius: 2.5, color: "#ff6600", weight: 1, fill: false }))).addTo(optic);
      } else if (k === "alerts") {
        const style = { color: "#ffff00", weight: 1, fill: false };
        state.extra[k] = L.geoJSON(s.context.alerts, { style, onEachFeature: (f, l) => l.bindTooltip(`Alert ${f.properties.date}, ${f.properties.area_ha ? f.properties.area_ha.toFixed(1) + " ha" : ""}`) }).addTo(map);
        state.extra[k + "_o"] = L.geoJSON(s.context.alerts, { style }).addTo(optic);
      } else {
        const a = s.grid.extra[k];
        state.extra[k] = paint(i => L0.paint(a[i])).addTo(map);
      }
    }
    showLegend();
    restack();
  }

  function showLegend() {
    const on = Object.keys(state.extra).filter(k => SITE_LAYERS[k] && SITE_LAYERS[k].ramp);
    const k = on[on.length - 1];
    $("legend").hidden = !k;
    if (!k) return;
    const L0 = SITE_LAYERS[k];
    $("legend").innerHTML = `<div>${L0.label}, ${L0.unit}</div><div class="legend__ramp" style="background:${L0.ramp}"></div>` +
      `<div class="legend__ends"><span>${L0.lo}</span><span>${L0.hi}</span></div>`;
  }

  function clearSiteLayers() {
    Object.keys(state.extra).forEach(k => { [map, optic].forEach(m => m.hasLayer(state.extra[k]) && m.removeLayer(state.extra[k])); });
    state.extra = {};
  }

  // --- patches: connected pixels of one style above the threshold ---
  function findPatches() {
    if (state.site.analysis_status === 'exploratory_sparse_samples') {
      return state.site.pixels.map((p,peak)=>({style:p.style,cells:1,peak,mean:Math.abs(p.z)}))
        .filter(p=>p.style && Number.isFinite(state.site.pixels[p.peak].z) && p.mean>=state.z)
        .sort((a,b)=>b.mean-a.mean);
    }
    const g = state.site.grid, W = g.w, H = g.h, t = state.z, seen = new Uint8Array(W * H), out = [];
    for (let i = 0; i < W * H; i++) {
      if (seen[i] || !g.style[i] || !(Math.abs(g.z[i]) >= t)) continue;
      const st = g.style[i], stack = [i]; seen[i] = 1;
      let cells = 0, peak = i, sum = 0;
      while (stack.length) {
        const c = stack.pop(), x = c % W, y = (c - x) / W;
        cells++; sum += Math.abs(g.z[c]);
        if (Math.abs(g.z[c]) > Math.abs(g.z[peak])) peak = c;
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const X = x + dx, Y = y + dy, j = Y * W + X;
          if (X < 0 || Y < 0 || X >= W || Y >= H || seen[j] || g.style[j] !== st || !(Math.abs(g.z[j]) >= t)) continue;
          seen[j] = 1; stack.push(j);
        }
      }
      if (cells >= 3) out.push({ style: OB.STYLE_KEYS[st], cells, peak, mean: sum / cells });
    }
    return out.sort((a, b) => b.cells * b.mean - a.cells * a.mean);
  }

  function area(cells) {
    if (state.site.grid.cellM == null) return `${cells} sample${cells===1?'':'s'}; area unknown`;
    const ha = cells * state.site.grid.cellM ** 2 / 1e4;
    return ha >= 100 ? (ha / 100).toFixed(1) + " sq km" : Math.round(ha) + " ha";
  }

  function drawTop() {
    const s = state.site, g = s.grid, rows = state.patches.slice(0, 10);
    $("top").tBodies[0].innerHTML = rows.length ? rows.map((p, i) => {
      const st = OB.STYLES[p.style], since = g.since[p.peak] >= 0 ? s.dates[g.since[p.peak]] : "-";
      return `<tr data-cell="${p.peak}" tabindex="0" aria-selected="${state.cell === p.peak}">
        <td>${i + 1}</td><td><i class="tag" style="background:${st.color}"></i>${st.name}</td>
        <td>${area(p.cells)}</td><td>${Math.abs(g.z[p.peak]).toFixed(1)}</td><td>${since}</td></tr>`;
    }).join("") : `<tr><td colspan="5">${g.z.some(Number.isFinite) ? `No classified shape passes |z| ≥ ${state.z}.` : 'No classified candidates with valid peer measurements.'}</td></tr>`;
  }
  const rowPick = e => { const tr = e.target.closest("tr[data-cell]"); if (tr) pickCell(+tr.dataset.cell, true).then(pixelSound); };
  $("top").addEventListener("click", rowPick);
  $("top").addEventListener("keydown", e => { if (e.key === "Enter") rowPick(e); });

  function refresh() {
    const g = state.site.grid;
    state.patches = findPatches();
    // every sample past the threshold, as the map draws them; styles are not assigned on sparse samples
    let px = 0; for (let i = 0; i < g.z.length; i++) if (Number.isFinite(g.z[i]) && Math.abs(g.z[i]) >= state.z && g.cover[i] !== 80) px++;
    drawRaster(); drawTop();
    $("sb-count").textContent = g.z.some(Number.isFinite) ? `${state.patches.length} candidates · ${px} samples at |z| ≥ ${state.z}; area unknown` : 'No valid peer deviations';
  }

  // --- validation summary (Amazon, from pipeline) ---
  function drawValidation() {
    const v = state.site.context && state.site.context.validation;
    $("val-win").hidden = !v;
    if (!v) return;
    if (v.kind === 'sparse_sample_validation') {
      $('val-body').textContent = `${v.n_candidates} HV-drop candidates: ${v.n_alert_matches} overlap a dated alert within +/-${v.max_days} days; ${v.n_fire_matches} have a fire within ${v.fire_radius_m/1000} km and the same date window. These are context matches, not confirmed clearing. No event area, recall or accuracy is estimated from sparse samples. Missing alerts do not rule out change.`;
      return;
    }
    const pct = x => x == null ? "-" : Math.round(x * 100) + "%";
    $("val-body").innerHTML =
      `<p>${v.n_patches} clearing patches found by OffBeat, checked against ${v.source || "deforestation alerts"}.</p>` +
      `<p><b>${pct(v.share_confirmed)}</b> overlap an alert. Median lag to the alert: <b>${v.median_lag_days == null ? "-" : v.median_lag_days + " days"}</b> (negative: OffBeat saw it first). ` +
      `<b>${pct(v.share_with_fire)}</b> have a FIRMS fire nearby. OffBeat caught <b>${pct(v.alert_recall)}</b> of the alert area.</p>`;
  }

  // --- picking a pixel ---
  let coordinateTips = [];
  function showClickedCoordinates(latlng) {
    const point = latlng.wrap();
    const text = `${point.lat.toFixed(6)}, ${point.lng.toFixed(6)}`;
    coordinateTips.forEach(([target, tip]) => target.removeLayer(tip));
    coordinateTips = [map, optic].map(target => {
      const tip = L.tooltip({permanent:true, direction:'top', offset:[0,-8], interactive:false})
        .setLatLng(point).setContent(text).addTo(target);
      return [target, tip];
    });
    return text;
  }
  function onMapClick(e) {
    document.dispatchEvent(new Event('ob:manual-navigation'));
    const coordinates = showClickedCoordinates(e.latlng);
    if (!state.site) return;
    const g = state.site.grid;
    const { origin, width, height } = projectedGrid(g);
    const point = map.project(e.latlng, 0);
    const x = Math.floor((point.x - origin.x) / width);
    const y = Math.floor((point.y - origin.y) / height);
    const index = y * g.w + x;
    const localVisible = $('l-offbeat').checked && x >= 0 && y >= 0 && x < g.w && y < g.h;
    const isAnomaly = Number.isFinite(g.z[index]) && Math.abs(g.z[index]) >= state.z && g.cover[index] !== 80;
    if (localVisible && (isAnomaly || Number.isFinite(state.site.pixels?.[index]?.hv.at(-1)))) {
      pickCell(index, false).then(pixelSound);
      return;
    }
    clearPixel();
    $('p-loc').textContent = coordinates;
    if (localVisible) {
      pickCell(index, false).then(pixelSound);
    }
  }
  map.on('click', onMapClick);
  optic.on('click', onMapClick);
  function pixelSound() {
    const p = state.pixel; if (!p || !OB.sfx) return;
    OB.sfx.play(p.style && Number.isFinite(p.z) && Math.abs(p.z) >= state.z ? "offbeat" : "instep");
  }

  async function pickCell(i, fly) {
    OB.sonify.stop();
    const s = state.site, g = s.grid, x = i % g.w, y = (i - x) / g.w;
    state.cell = i;
    const p = await s.series(x, y);
    if (state.cell !== i || state.site !== s) return;      // another click won the race
    state.pixel = p;
    $('data-status').textContent = s.message || s.source;
    $('site-name').textContent = s.name; $('source-link').hidden = false;
    $('map-caption').textContent = $('l-offbeat').checked ? 'Measured samples: grey in step, blue below and red above their same-class neighbours' : 'Measured samples hidden; switch them on under Layers';
    const st = p.style ? OB.STYLES[p.style] : null;
    $("px-id").textContent = p.id;
    $("p-cover").textContent = OB.COVER[p.cover] ? `${OB.COVER[p.cover].name} (${p.cover})` : 'No WorldCover measurement';
    $("p-peers").textContent = p.peers == null ? 'Unavailable' : `${p.peers} valid HV samples at latest date; same class, ≤1 km`;
    $("p-z").textContent = Number.isFinite(p.z) ? (p.z > 0 ? "+" : "") + p.z.toFixed(2) : 'Unavailable';
    $("p-style").innerHTML = !Number.isFinite(p.z) ? 'Not classified' : st ? `<i class="tag" style="background:${st.color}"></i>${st.name} (unverified shape)` : 'No classified shape';
    $("p-since").textContent = p.since || "—";
    $('p-quality').textContent = p.coherence == null ? 'Unavailable' : `Coherence ${p.coherence.toFixed(2)}; component ${p.component}; ${p.disp ? 'accepted' : 'rejected'}; ionosphere ${p.ionosphere_interpolated ? 'product-interpolated' : 'not flagged as interpolated'}, σ ${p.ionosphere_sd_rad == null ? 'unavailable' : p.ionosphere_sd_rad.toFixed(2)} rad`;
    $('p-extra').innerHTML = Object.entries(p.extra || {}).filter(([, v]) => Number.isFinite(v))
      .map(([k, v]) => `<tr><th scope="row">${SITE_LAYERS[k].card}</th><td>${SITE_LAYERS[k].fmt(v)}</td></tr>`).join('');
    const { origin, width, height } = projectedGrid(g);
    const rect = [
      map.unproject(origin.add([x * width, y * height]), 0),
      map.unproject(origin.add([(x + 1) * width, (y + 1) * height]), 0),
    ];
    showCellBounds(rect);
    if (fly) map.setView([p.lat, p.lon], Math.max(map.getZoom(), 13));
    drawCharts();
    optical.setDate(p.since || s.dates.at(-1));
    const v = voice(p);
    $("play").disabled = !v.pix.some((x, i) => Number.isFinite(x) && Number.isFinite(v.med[i]) && Number.isFinite(v.sd[i]));
    $("play-hint").textContent = $("play").disabled ? 'Audio unavailable: measured pixel and peer series required.' : `Peers keep the beat, the pixel plays its ${channelName(p)} curve.`;
    drawTop();
  }

  function sinceIdx() { const p = state.pixel; return p && p.since ? state.site.dates.indexOf(p.since) : null; }
  function drawCharts(head) {
    const p = state.pixel; if (!p) return;
    OB.chart.backscatter($("c-bs"), state.site.dates, p, sinceIdx(), head);
    const dispDates = state.site.displacement_dates || state.site.dates;
    OB.chart.displacement($("c-disp"), dispDates, p, null, head != null && head < dispDates.length ? head : null);
    // Sentinel-1 at the same sample point, when the site has it (data/<site>/sentinel1.json)
    const s1 = state.site.context && state.site.context.sentinel1, i = state.cell;
    const vv = s1 && Number.isInteger(i) ? s1.points.vv.map(row => row[i] ?? NaN) : null;
    const vh = s1 && Number.isInteger(i) ? s1.points.vh.map(row => row[i] ?? NaN) : null;
    $("plot-s1").hidden = !(vv && vv.concat(vh).some(Number.isFinite));
    if (!$("plot-s1").hidden) OB.chart.cband($("c-s1"), s1.dates, vv, vh, state.site.dates);
  }

  function channelName(p) {
    if ((p.style === "drift" || p.style === "step") && p.disp) return "displacement";
    return p.style === "flood" ? "HH" : "HV";
  }
  function voice(p) {
    if ((p.style === "drift" || p.style === "step") && p.disp && p.peer_disp && p.peer_disp_sd) return { pix: p.disp, med: p.peer_disp, sd: p.peer_disp_sd };
    if (p.style === "flood") return { pix: p.hh, med: p.peer.hh_med, sd: p.peer.hh_sd };
    return { pix: p.hv, med: p.peer.hv_med, sd: p.peer.hv_sd };
  }
  $("play").addEventListener("click", () => {
    const p = state.pixel; if (!p) return;
    $("stop").disabled = false; $("sb-state").textContent = `Playing ${p.id}...`;
    OB.sonify.play(voice(p), i => drawCharts(i), () => { $("stop").disabled = true; $("sb-state").textContent = "Ready"; drawCharts(); });
  });
  $("stop").addEventListener("click", () => { OB.sonify.stop(); $("stop").disabled = true; $("sb-state").textContent = "Ready"; drawCharts(); });

  // --- site switch ---
  async function loadSite(id) {
    OB.sonify.stop();
    const selected = OB.SITES.find(x => x.id === id) || OB.SITES[0];
    const ticket = ++state.loading;
    $("sb-state").textContent = `Loading ${selected.name}...`;
    let s;
    try { s = selected; }
    catch (e) { $('data-status').textContent = `Real data unavailable: ${e.message}`; $('sb-state').textContent = 'Load failed'; OB.sfx && OB.sfx.play("error"); return; }
    if (ticket !== state.loading) return;
    clearSiteLayers();
    state.site = s; state.pixel = null; state.cell = null;
    document.querySelectorAll('#regions button').forEach(button => button.setAttribute('aria-pressed', 'false'));
    await optical.load(s,s.dates.at(-1));
    if (ticket !== state.loading) return;
    document.querySelectorAll("#sites button").forEach(b => b.setAttribute("aria-pressed", b.dataset.site === s.id));
    $("site-name").textContent = s.name;
    $('source-link').hidden = false;
    $('source-link').href = `data/${s.id}-manifest.json`;
    $('data-status').textContent = (s.message || s.source) + (OB.dataErrors.length ? ' Unavailable: ' + OB.dataErrors.join('; ') : '');
    $('z').disabled = !s.grid.z.some(Number.isFinite);
    $('raster-label').textContent = 'Measured NISAR samples';
    if (!OB.tourActive) $('l-offbeat').checked = true;     // the measurements are the point of a site: show them
    $('map-caption').textContent = 'Measured samples: grey in step, blue below and red above their same-class neighbours';
    const b = s.grid.bbox; map.fitBounds([[b.s, b.w], [b.n, b.e]], { paddingTopLeft: [16, 32], paddingBottomRight: [16, 16] });
    drawAreaLabels();
    buildSiteLayers(); drawValidation();
    drawCover(); refresh();
    $("sb-src").textContent = "Source: " + s.source;
    $("sb-state").textContent = s.message || `Ready · ${s.dates.length} acquisitions`;
    if (!OB.tourActive) { const url = new URL(location.href); url.searchParams.set('site', s.id); if (OB.SITES.some(x => url.hash === '#' + x.id)) url.hash = ''; history.replaceState(null, '', url); }
    if (state.patches[0]) await pickCell(state.patches[0].peak, false);
    else {
      const first = s.pixels ? s.pixels.findIndex(p => p.disp && p.disp.some(Number.isFinite) && p.hv.some(Number.isFinite)) : -1;
      await pickCell(first >= 0 ? first : Math.floor(s.grid.h / 2) * s.grid.w + Math.floor(s.grid.w / 2), false);
    }
    return s;
  }

  // --- demo sites as clickable labels on the data map, while zoomed out far enough to need them ---
  const sitePins = L.layerGroup(OB.SITES.map(s => {
    const b = s.grid.bbox;
    const pin = L.marker([(b.s + b.n) / 2, (b.w + b.e) / 2], {
      icon: L.divIcon({ className: 'site-pin', html: `<span class="site-pin__dot"></span><span class="site-pin__name"></span>`, iconSize: null }),
      keyboard: true, title: `Open ${s.name}`, riseOnHover: true,
    });
    pin.on('add', () => { const el = pin.getElement(); if (el) el.querySelector('.site-pin__name').textContent = s.name; });
    pin.on('click', () => { document.dispatchEvent(new Event('ob:manual-navigation')); loadSite(s.id); });
    return pin;
  }));
  const updatePins = () => { const show = map.getZoom() <= 9; if (show && !map.hasLayer(sitePins)) sitePins.addTo(map); if (!show && map.hasLayer(sitePins)) map.removeLayer(sitePins); };
  map.on('zoomend load', updatePins);                     // 'load' fires with the first view

  // --- what the guided tour (js/story.js) may drive ---
  OB.app = {
    sites: () => OB.SITES,
    site: () => state.site,
    pixel: () => state.pixel,
    loadSite(id) {
      ++navigationSerial; ++searchSerial; $('place-submit').disabled = false; $('place-results').replaceChildren();
      $('place-status').textContent = '';
      return (state.site && state.site.id === id && state.pixel) ? Promise.resolve(state.site) : loadSite(id);
    },
    setZ(v) { $("z").value = v; state.z = +$("z").value; $("z-out").textContent = state.z; refresh(); },
    setLayers({ offbeat = true, cover = false, extra = [] } = {}) {
      $("l-offbeat").checked = offbeat; drawRaster();
      $("l-cover").checked = cover; drawCover();
      document.querySelectorAll("#site-layer-list input[data-layer]").forEach(c => {
        const on = extra.includes(c.dataset.layer);
        if (c.checked !== on || (on && !state.extra[c.dataset.layer])) { c.checked = on; toggleLayer(c.dataset.layer, on); }
      });
      restack();
    },
    patches: () => state.patches,
    pickCell: (i, fly) => pickCell(i, fly),
    zoomTo: (lat, lon, z) => map.setView([lat, lon], z, { animate: false }),
    fit: () => { const b = state.site.grid.bbox; map.fitBounds([[b.s, b.w], [b.n, b.e]], { paddingTopLeft: [16, 32], paddingBottomRight: [16, 16], animate: false }); },
    play: () => $("play").click(),
    stop: () => OB.sonify.stop()
  };
  document.dispatchEvent(new Event("ob:ready"));

  window.addEventListener("resize", () => drawCharts());
  if (document.fonts) document.fonts.ready.then(() => drawCharts()); // canvas text needs W95FA loaded
  window.addEventListener("hashchange", () => {
    const id = location.hash.slice(1);
    if (OB.SITES.some(s => s.id === id) && (!state.site || state.site.id !== id)) loadSite(id);
  });
  if (!OB.tourWanted) {
    const legacy = location.hash.slice(1);
    const params = new URL(location.href).searchParams, saved = params.get('site') || (previousViewport && previousViewport.site);
    const lat = params.get('lat'), lon = params.get('lon');
    const savedPlace = lat !== null && lon !== null ? OB.parseCoordinates(`${lat}, ${lon}`) : null;
    const startupNavigation = navigationSerial;
    loadSite(OB.SITES.some(s => s.id === legacy) ? legacy : saved).then(async () => {
      if (navigationSerial !== startupNavigation) return;
      const worldStart = !params.has('site') && !OB.SITES.some(s => s.id === legacy) && !savedPlace;
      if (worldStart) await showRegion('world');
      if (savedPlace && savedPlace.kind === 'coordinates') { $('place-query').value = `${savedPlace.lat}, ${savedPlace.lon}`; await showPlace(savedPlace); }
      const v = previousViewport;
      if (!worldStart && v && state.site && v.site === state.site.id && v.anchor === viewportAnchor() && Number.isFinite(v.lat) && Math.abs(v.lat) <= 85.05112878 && Number.isFinite(v.lon) && Math.abs(v.lon) <= 180 && Number.isFinite(v.zoom) && v.zoom >= 0 && v.zoom <= 19) map.setView([v.lat, v.lon], v.zoom, { animate: false });
      viewportReady = true; saveViewport();
    });
  }
})();

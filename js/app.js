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

  // Identical imagery and zoom limits on both sides; grey styling only on the SAR pane.
  const IMAGERY = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const LABELS = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
  const imageryCredit = 'Imagery &copy; Esri, Vantor, Earthstar Geographics';
  const labelsCredit = 'Labels &copy; Esri, HERE, Garmin, OpenStreetMap contributors';
  const map = L.map("map", { zoomControl: true, maxZoom: 19 });
  const optic = L.map("optic", { zoomControl: true, maxZoom: 19 });
  const labelLayers = [map, optic].map(m => {
    L.tileLayer(IMAGERY, { maxZoom: 19, maxNativeZoom: 19, className: 'context-imagery', attribution: imageryCredit }).addTo(m);
    m.createPane('placeLabels');
    m.getPane('placeLabels').style.zIndex = 625;
    m.getPane('placeLabels').style.pointerEvents = 'none';
    L.control.scale({ metric: true, imperial: false, maxWidth: 100 }).addTo(m);
    return L.tileLayer(LABELS, { pane: 'placeLabels', maxZoom: 19, maxNativeZoom: 19, attribution: labelsCredit }).addTo(m);
  });
  let areaLayers = [];
  let syncing = false;
  const sync = (a, b) => a.on("move", () => { if (syncing) return; syncing = true; b.setView(a.getCenter(), a.getZoom(), { animate: false }); syncing = false; });
  sync(map, optic); sync(optic, map);
  const box = () => L.rectangle([[0, 0], [0, 0]], { color: "#ffcc00", weight: 2, fill: false, interactive: false });
  const cellBox = box(), cellBoxOptic = box();

  // --- side lists ---
  $("sites").innerHTML = OB.SITES.map(s =>
    `<li><button type="button" data-site="${s.id}" aria-pressed="false">${s.name}<small>${s.region}</small></button></li>`).join("");
  $("sites").addEventListener("click", e => { const b = e.target.closest("button"); if (b) loadSite(b.dataset.site); });
  $("styles").innerHTML = Object.entries(OB.STYLES).map(([k, s]) =>
    `<li><i class="dot" style="background:${s.color}"></i><div><b>${s.name}</b><span class="d">${s.what}</span></div></li>`).join("");

  $("z").addEventListener("input", e => { state.z = +e.target.value; $("z-out").textContent = state.z; refresh(); });
  $("l-offbeat").addEventListener("change", drawRaster);
  $("l-cover").addEventListener("change", drawCover);
  $('l-labels').addEventListener('change', () => {
    [map, optic].forEach((m, i) => {
      if ($('l-labels').checked) labelLayers[i].addTo(m);
      else m.removeLayer(labelLayers[i]);
    });
    drawAreaLabels();
  });

  function drawAreaLabels() {
    areaLayers.forEach(([m, layer]) => m.removeLayer(layer));
    areaLayers = [];
    if (!state.site || !$('l-labels').checked) return;
    const s = state.site, b = s.grid.bbox;
    [map, optic].forEach(m => {
      const outline = L.rectangle([[b.s, b.w], [b.n, b.e]], { color: '#fff', weight: 2, dashArray: '6 4', fill: false, interactive: false }).addTo(m);
      const text = document.createElement('span');
      text.textContent = s.name;
      const label = L.marker([b.n, (b.w + b.e) / 2], { interactive: false, icon: L.divIcon({ className: 'area-label', html: text, iconSize: null }) }).addTo(m);
      areaLayers.push([m, outline], [m, label]);
    });
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

  function drawRaster() {
    if (state.raster) map.removeLayer(state.raster);
    state.raster = null;
    if (!$("l-offbeat").checked) return;
    const g = state.site.grid, t = state.z;
    if (!g.z.some(Number.isFinite) && state.site.pixels) {
      state.raster = paint(i => {
        const value = state.site.pixels[i].hv.at(-1);
        if (!Number.isFinite(value)) return null;
        const q = Math.max(0, Math.min(1, (value + 25) / 25));
        return [Math.round(255*q), 70, Math.round(255*(1-q)), 180];
      }).addTo(map);
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
    }).join("") : `<tr><td colspan="5">${g.z.some(Number.isFinite) ? `Nothing passes |z| ≥ ${state.z}.` : 'No anomaly classification: one measured pair is insufficient for a trend.'}</td></tr>`;
  }
  const rowPick = e => { const tr = e.target.closest("tr[data-cell]"); if (tr) pickCell(+tr.dataset.cell, true).then(pixelSound); };
  $("top").addEventListener("click", rowPick);
  $("top").addEventListener("keydown", e => { if (e.key === "Enter") rowPick(e); });

  function refresh() {
    const g = state.site.grid;
    state.patches = findPatches();
    let px = 0; for (let i = 0; i < g.z.length; i++) if (g.style[i] && Math.abs(g.z[i]) >= state.z) px++;
    drawRaster(); drawTop();
    $("sb-count").textContent = g.z.some(Number.isFinite) ? `${state.patches.length} patches · ${px} px at |z| ≥ ${state.z}` : 'No validated anomaly scores';
  }

  // --- validation summary (Amazon, from pipeline) ---
  function drawValidation() {
    const v = state.site.context && state.site.context.validation;
    $("val-win").hidden = !v;
    if (!v) return;
    const pct = x => x == null ? "-" : Math.round(x * 100) + "%";
    $("val-body").innerHTML =
      `<p>${v.n_patches} clearing patches found by OffBeat, checked against ${v.source || "deforestation alerts"}.</p>` +
      `<p><b>${pct(v.share_confirmed)}</b> overlap an alert. Median lag to the alert: <b>${v.median_lag_days == null ? "-" : v.median_lag_days + " days"}</b> (negative: OffBeat saw it first). ` +
      `<b>${pct(v.share_with_fire)}</b> have a FIRMS fire nearby. OffBeat caught <b>${pct(v.alert_recall)}</b> of the alert area.</p>`;
  }

  // --- picking a pixel ---
  map.on("click", e => {
    const g = state.site.grid, b = g.bbox;
    const x = Math.floor((e.latlng.lng - b.w) / (b.e - b.w) * g.w), y = Math.floor((b.n - e.latlng.lat) / (b.n - b.s) * g.h);
    if (x >= 0 && y >= 0 && x < g.w && y < g.h) pickCell(y * g.w + x, false).then(pixelSound);
  });
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
    const st = p.style ? OB.STYLES[p.style] : null;
    $("px-id").textContent = p.id;
    $("p-cover").textContent = OB.COVER[p.cover] ? `${OB.COVER[p.cover].name} (${p.cover})` : 'No WorldCover measurement';
    $("p-peers").textContent = p.peers == null ? 'Unavailable' : `${p.peers} valid HV samples at latest date; same class, ≤1 km`;
    $("p-z").textContent = Number.isFinite(p.z) ? (p.z > 0 ? "+" : "") + p.z.toFixed(2) : 'Unavailable';
    $("p-style").innerHTML = !Number.isFinite(p.z) ? 'Not classified' : st && Math.abs(p.z) >= 2 ? `<i class="tag" style="background:${st.color}"></i>${st.name}` : "in step";
    $("p-since").textContent = p.since || "—";
    $("p-loc").textContent = `${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`;
    $('p-quality').textContent = p.coherence == null ? 'Unavailable' : `Coherence ${p.coherence.toFixed(2)}; component ${p.component}; ${p.disp ? 'accepted' : 'rejected'}; ionosphere ${p.ionosphere_interpolated ? 'product-interpolated' : 'not flagged as interpolated'}, σ ${p.ionosphere_sd_rad == null ? 'unavailable' : p.ionosphere_sd_rad.toFixed(2)} rad`;
    $('p-extra').innerHTML = Object.entries(p.extra || {}).filter(([, v]) => Number.isFinite(v))
      .map(([k, v]) => `<tr><th scope="row">${SITE_LAYERS[k].card}</th><td>${SITE_LAYERS[k].fmt(v)}</td></tr>`).join('');
    const b = g.bbox, dl = (b.n - b.s) / g.h, dw = (b.e - b.w) / g.w;
    const rect = [[b.n - (y + 1) * dl, b.w + x * dw], [b.n - y * dl, b.w + (x + 1) * dw]];
    cellBox.setBounds(rect).addTo(map); cellBoxOptic.setBounds(rect).addTo(optic);
    if (fly) map.setView([p.lat, p.lon], Math.max(map.getZoom(), 13));
    drawCharts();
    const v = voice(p);
    $("play").disabled = !v.pix.some((x, i) => Number.isFinite(x) && Number.isFinite(v.med[i]) && Number.isFinite(v.sd[i]));
    $("play-hint").textContent = $("play").disabled ? 'Audio unavailable: measured pixel and peer series required.' : `Peers keep the beat, the pixel plays its ${channelName(p)} curve.`;
    drawTop();
  }

  function sinceIdx() { const p = state.pixel; return p && p.since ? state.site.dates.indexOf(p.since) : null; }
  function drawCharts(head) {
    const p = state.pixel; if (!p) return;
    OB.chart.backscatter($("c-bs"), state.site.dates, p, sinceIdx(), head);
    OB.chart.displacement($("c-disp"), state.site.displacement_dates || state.site.dates, p, null, head);
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
    document.querySelectorAll("#sites button").forEach(b => b.setAttribute("aria-pressed", b.dataset.site === s.id));
    $("site-name").textContent = s.name;
    $('source-link').href = `data/${s.id}-manifest.json`;
    $('data-status').textContent = (s.message || s.source) + (OB.dataErrors.length ? ' Unavailable: ' + OB.dataErrors.join('; ') : '');
    $('z').disabled = !s.grid.z.some(Number.isFinite);
    $('raster-label').textContent = s.grid.z.some(Number.isFinite) ? 'Off-Beat raster' : 'Measured HV backscatter';
    $('map-caption').textContent = s.grid.z.some(Number.isFinite) ? 'z-score vs. same-class peers, click any pixel' : 'Measured HV gamma0, blue −25 to red 0 dB; click a sample';
    const b = s.grid.bbox; map.fitBounds([[b.s, b.w], [b.n, b.e]], { paddingTopLeft: [16, 32], paddingBottomRight: [16, 16] });
    drawAreaLabels();
    buildSiteLayers(); drawValidation();
    drawCover(); refresh();
    $("sb-src").textContent = "Source: " + s.source;
    $("sb-state").textContent = s.message || `Ready · ${s.dates.length} acquisitions`;
    if (location.hash !== "#" + s.id && !OB.tourActive) history.replaceState(null, "", "#" + s.id);
    if (state.patches[0]) await pickCell(state.patches[0].peak, false);
    else {
      const first = s.pixels ? s.pixels.findIndex(p => p.disp && p.disp.some(Number.isFinite) && p.hv.some(Number.isFinite)) : -1;
      await pickCell(first >= 0 ? first : Math.floor(s.grid.h / 2) * s.grid.w + Math.floor(s.grid.w / 2), false);
    }
    return s;
  }

  // --- what the guided tour (js/story.js) may drive ---
  OB.app = {
    sites: () => OB.SITES,
    site: () => state.site,
    pixel: () => state.pixel,
    loadSite: id => (state.site && state.site.id === id) ? Promise.resolve(state.site) : loadSite(id),
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
  if (!OB.tourWanted) loadSite((location.hash || "").slice(1));
})();

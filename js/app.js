// Wires sites, the z-score raster, the pixel card, the patch list and the player.
(async function () {
  const $ = id => document.getElementById(id);
  try { await OB.loadData(); } catch (error) {
    $('sb-state').textContent = error.message;
    $('sb-src').textContent = 'No measurements loaded';
    $('play-hint').textContent = 'Cannot load real data. Check the static server and data/mexico.json.';
    return;
  }
  const state = { site: null, pixel: null, cell: null, z: 2.5, patches: [], raster: null, coverRaster: null };

  // --- maps: anomaly raster over greyed imagery + optical map that follows it ---
  const IMAGERY = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const map = L.map("map", { zoomControl: true, attributionControl: false });
  L.tileLayer(IMAGERY, { maxZoom: 17 }).addTo(map);
  const optic = L.map("optic", { zoomControl: false, attributionControl: false });
  L.tileLayer("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg", { maxZoom: 17 }).addTo(optic);
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

  // --- rasters ---
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const STYLE_RGB = OB.STYLE_KEYS.map(k => k ? rgb(OB.STYLES[k].color) : [90, 90, 90]);

  function paint(fn) {
    const g = state.site.grid, cv = document.createElement("canvas");
    cv.width = cv.height = g.n;
    const ctx = cv.getContext("2d"), img = ctx.createImageData(g.n, g.n);
    for (let i = 0; i < g.n * g.n; i++) {
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

  // --- patches: connected pixels of one style above the threshold ---
  function findPatches() {
    const g = state.site.grid, n = g.n, t = state.z, seen = new Uint8Array(n * n), out = [];
    for (let i = 0; i < n * n; i++) {
      if (seen[i] || !g.style[i] || Math.abs(g.z[i]) < t) continue;
      const st = g.style[i], stack = [i]; seen[i] = 1;
      let cells = 0, peak = i, sum = 0;
      while (stack.length) {
        const c = stack.pop(), x = c % n, y = (c - x) / n;
        cells++; sum += Math.abs(g.z[c]);
        if (Math.abs(g.z[c]) > Math.abs(g.z[peak])) peak = c;
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const X = x + dx, Y = y + dy, j = Y * n + X;
          if (X < 0 || Y < 0 || X >= n || Y >= n || seen[j] || g.style[j] !== st || Math.abs(g.z[j]) < t) continue;
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
    }).join("") : `<tr><td colspan="5">${g.z.some(Number.isFinite) ? `Nothing passes |z| ≥ ${state.z}.` : 'Anomaly analysis unavailable: measured peers and land cover required.'}</td></tr>`;
  }
  const rowPick = e => { const tr = e.target.closest("tr[data-cell]"); if (tr) pickCell(+tr.dataset.cell, true); };
  $("top").addEventListener("click", rowPick);
  $("top").addEventListener("keydown", e => { if (e.key === "Enter") rowPick(e); });

  function refresh() {
    const g = state.site.grid;
    state.patches = findPatches();
    let px = 0; for (let i = 0; i < g.z.length; i++) if (g.style[i] && Math.abs(g.z[i]) >= state.z) px++;
    drawRaster(); drawTop();
    $("sb-count").textContent = g.z.some(Number.isFinite) ? `${state.patches.length} patches · ${px} px at |z| ≥ ${state.z}` : 'No validated anomaly scores';
  }

  // --- picking a pixel ---
  map.on("click", e => {
    const g = state.site.grid, b = g.bbox;
    const x = Math.floor((e.latlng.lng - b.w) / (b.e - b.w) * g.n), y = Math.floor((b.n - e.latlng.lat) / (b.n - b.s) * g.n);
    if (x >= 0 && y >= 0 && x < g.n && y < g.n) pickCell(y * g.n + x, false);
  });

  function pickCell(i, fly) {
    OB.sonify.stop();
    const s = state.site, g = s.grid, x = i % g.n, y = (i - x) / g.n, p = s.series(x, y);
    state.cell = i; state.pixel = p;
    const st = p.style ? OB.STYLES[p.style] : null;
    $("px-id").textContent = p.id;
    $("p-cover").textContent = OB.COVER[p.cover] ? `${OB.COVER[p.cover].name} (${p.cover})` : 'No WorldCover measurement';
    $("p-peers").textContent = p.peers == null ? 'Unavailable' : `${p.peers} px, same class`;
    $("p-z").textContent = Number.isFinite(p.z) ? (p.z > 0 ? "+" : "") + p.z.toFixed(2) : 'Unavailable';
    $("p-style").innerHTML = !Number.isFinite(p.z) ? 'Not classified' : st && Math.abs(p.z) >= 2 ? `<i class="tag" style="background:${st.color}"></i>${st.name}` : "in step";
    $("p-since").textContent = p.since || "—";
    $("p-loc").textContent = `${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`;
    const b = g.bbox, dl = (b.n - b.s) / g.n, dw = (b.e - b.w) / g.n;
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
    if ((p.style === "drift" || p.style === "step") && p.disp) return { pix: p.disp, med: p.peer_disp, sd: p.peer_disp.map(() => 1.2) };
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
  function loadSite(id) {
    OB.sonify.stop();
    const s = OB.SITES.find(x => x.id === id) || OB.SITES[0];
    state.site = s; state.pixel = null; state.cell = null;
    document.querySelectorAll("#sites button").forEach(b => b.setAttribute("aria-pressed", b.dataset.site === s.id));
    $("site-name").textContent = s.name;
    const b = s.grid.bbox; map.fitBounds([[b.s, b.w], [b.n, b.e]], { padding: [4, 4] });
    drawCover(); refresh();
    $("sb-src").textContent = "Source: " + s.source;
    $("sb-state").textContent = s.message || `Ready · ${s.dates.length} acquisitions`;
    if (state.patches[0]) pickCell(state.patches[0].peak, false);
    else pickCell(Math.floor(s.grid.n / 2) * s.grid.n + Math.floor(s.grid.n / 2), false);
    if (location.hash !== "#" + s.id) history.replaceState(null, "", "#" + s.id);
  }

  window.addEventListener("resize", () => drawCharts());
  if (document.fonts) document.fonts.ready.then(() => drawCharts()); // canvas text needs W95FA loaded
  window.addEventListener("hashchange", () => {
    const id = location.hash.slice(1);
    if (OB.SITES.some(s => s.id === id) && (!state.site || state.site.id !== id)) loadSite(id);
  });
  loadSite((location.hash || "").slice(1));
})();

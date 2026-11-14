// Wires sites, maps, the pixel card, the top list and the player.
(function () {
  const $ = id => document.getElementById(id);
  const state = { site: null, pixel: null, z: 2.5, layer: null, coverLayer: null };

  // --- maps: anomaly map + optical map that follows it ---
  const map = L.map("map", { zoomControl: true, attributionControl: false });
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", { maxZoom: 16 }).addTo(map);
  const optic = L.map("optic", { zoomControl: false, attributionControl: false, dragging: true });
  L.tileLayer("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg", { maxZoom: 17 }).addTo(optic);
  let syncing = false;
  const sync = (a, b) => a.on("move", () => { if (syncing) return; syncing = true; b.setView(a.getCenter(), a.getZoom(), { animate: false }); syncing = false; });
  sync(map, optic); sync(optic, map);
  const cross = L.circleMarker([0, 0], { radius: 9, color: "#ffcc00", weight: 2, fill: false, interactive: false });
  const crossOptic = L.circleMarker([0, 0], { radius: 9, color: "#ffcc00", weight: 2, fill: false, interactive: false });

  // --- side lists ---
  $("sites").innerHTML = OB.SITES.map(s =>
    `<li><button type="button" data-site="${s.id}" aria-pressed="false">${s.name}<small>${s.region}</small></button></li>`).join("");
  $("sites").addEventListener("click", e => { const b = e.target.closest("button"); if (b) loadSite(b.dataset.site); });

  $("styles").innerHTML = Object.entries(OB.STYLES).map(([k, s]) =>
    `<li><i class="dot" style="background:${s.color}"></i><div><b>${s.name}</b><span class="d">${s.what}</span></div></li>`).join("");

  $("z").addEventListener("input", e => { state.z = +e.target.value; $("z-out").textContent = state.z; drawLayer(); drawTop(); });
  $("l-offbeat").addEventListener("change", drawLayer);
  $("l-cover").addEventListener("change", drawLayer);

  function colourOf(p) { return p.style ? OB.STYLES[p.style].color : "#555"; }

  function drawLayer() {
    const s = state.site;
    if (state.layer) map.removeLayer(state.layer);
    if (state.coverLayer) map.removeLayer(state.coverLayer);
    if ($("l-cover").checked) {
      state.coverLayer = L.layerGroup(s.pixels.map(p => L.circleMarker([p.lat, p.lon], {
        radius: 3, stroke: false, fillColor: OB.COVER[p.cover].color, fillOpacity: 0.6, interactive: false
      }))).addTo(map);
    }
    const shown = s.pixels.filter(p => Math.abs(p.z) >= state.z);
    if ($("l-offbeat").checked) {
      state.layer = L.layerGroup(shown.map(p => {
        const m = L.circleMarker([p.lat, p.lon], {
          radius: 3 + Math.min(9, Math.abs(p.z) * 1.4), weight: 1, color: "#000",
          fillColor: colourOf(p), fillOpacity: Math.min(0.9, 0.25 + Math.abs(p.z) / 8)
        });
        m.bindTooltip(`${p.id} · |z| ${Math.abs(p.z).toFixed(1)}`);
        m.on("click", () => pick(p));
        return m;
      })).addTo(map);
    }
    $("sb-count").textContent = `${shown.length} of ${s.pixels.length} pixels at |z| ≥ ${state.z}`;
  }

  function drawTop() {
    const rows = state.site.pixels.filter(p => p.style && Math.abs(p.z) >= state.z)
      .sort((a, b) => Math.abs(b.z) - Math.abs(a.z)).slice(0, 10);
    $("top").tBodies[0].innerHTML = rows.length ? rows.map((p, i) =>
      `<tr data-id="${p.id}" tabindex="0" aria-selected="${state.pixel && state.pixel.id === p.id}">
        <td>${i + 1}</td><td>${p.id}</td><td>${OB.COVER[p.cover].name}</td>
        <td><i class="tag" style="background:${OB.STYLES[p.style].color}"></i>${OB.STYLES[p.style].name}</td>
        <td>${Math.abs(p.z).toFixed(1)}</td><td>${p.since}</td></tr>`).join("")
      : `<tr><td colspan="6">No pixel passes |z| ≥ ${state.z}. Lower the threshold.</td></tr>`;
  }
  $("top").addEventListener("click", e => { const tr = e.target.closest("tr[data-id]"); if (tr) pickId(tr.dataset.id, true); });
  $("top").addEventListener("keydown", e => { if (e.key === "Enter") { const tr = e.target.closest("tr[data-id]"); if (tr) pickId(tr.dataset.id, true); } });

  function pickId(id, fly) {
    const p = state.site.pixels.find(x => x.id === id);
    if (p) { pick(p); if (fly) map.setView([p.lat, p.lon], Math.max(map.getZoom(), 13)); }
  }

  // --- pixel card ---
  function pick(p) {
    OB.sonify.stop();
    state.pixel = p;
    const s = state.site, st = p.style ? OB.STYLES[p.style] : null;
    $("px-id").textContent = p.id;
    $("p-cover").textContent = `${OB.COVER[p.cover].name} (${p.cover})`;
    $("p-peers").textContent = `${p.peers} px, same class`;
    $("p-z").textContent = (p.z > 0 ? "+" : "") + p.z.toFixed(2);
    $("p-style").innerHTML = st ? `<i class="tag" style="background:${st.color}"></i>${st.name}` : "in step";
    $("p-since").textContent = p.since || "—";
    $("p-loc").textContent = `${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`;
    cross.setLatLng([p.lat, p.lon]).addTo(map); crossOptic.setLatLng([p.lat, p.lon]).addTo(optic);
    drawCharts();
    $("play").disabled = false;
    $("play-hint").textContent = `Peers keep the beat, the pixel plays its ${channelName(p)} curve. When it slips, you hear it.`;
    drawTop();
  }

  function sinceIdx() { const p = state.pixel; return p && p.since ? state.site.dates.indexOf(p.since) : null; }
  function drawCharts(head) {
    const p = state.pixel; if (!p) return;
    OB.chart.backscatter($("c-bs"), state.site.dates, p, sinceIdx(), head);
    OB.chart.displacement($("c-disp"), state.site.dates, p, sinceIdx(), head);
  }

  function channelName(p) {
    if ((p.style === "drift" || p.style === "step") && p.disp) return "displacement";
    return p.style === "flood" ? "HH" : "HV";
  }
  // the channel the style lives in is the one we play
  function voice(p) {
    if ((p.style === "drift" || p.style === "step") && p.disp) return { pix: p.disp, med: p.peer_disp, sd: p.peer_disp.map(() => 1.2) };
    if (p.style === "flood") return { pix: p.hh, med: p.peer.hh_med, sd: p.peer.hh_sd };
    return { pix: p.hv, med: p.peer.hv_med, sd: p.peer.hv_sd };
  }
  $("play").addEventListener("click", () => {
    const p = state.pixel; if (!p) return;
    $("stop").disabled = false; $("sb-state").textContent = `Playing ${p.id}…`;
    OB.sonify.play(voice(p), i => drawCharts(i), () => { $("stop").disabled = true; $("sb-state").textContent = "Ready"; drawCharts(); });
  });
  $("stop").addEventListener("click", () => { OB.sonify.stop(); $("stop").disabled = true; $("sb-state").textContent = "Ready"; drawCharts(); });

  // --- site switch ---
  function loadSite(id) {
    OB.sonify.stop();
    const s = OB.SITES.find(x => x.id === id) || OB.SITES[0];
    state.site = s; state.pixel = null;
    document.querySelectorAll("#sites button").forEach(b => b.setAttribute("aria-pressed", b.dataset.site === s.id));
    $("site-name").textContent = s.name;
    map.setView(s.center, s.zoom);
    drawLayer(); drawTop();
    $("sb-src").textContent = "Source: " + s.source;
    $("sb-state").textContent = `Ready · ${s.dates.length} acquisitions, ${s.dates[0]} – ${s.dates[s.dates.length - 1]}`;
    // open the strongest pixel so the card is never blank
    const top = s.pixels.filter(p => p.style).sort((a, b) => Math.abs(b.z) - Math.abs(a.z))[0];
    if (top) pick(top);
    if (location.hash !== "#" + s.id) history.replaceState(null, "", "#" + s.id);
  }

  window.addEventListener("resize", () => drawCharts());
  window.addEventListener("hashchange", () => {
    const id = location.hash.slice(1);
    if (OB.SITES.some(s => s.id === id) && (!state.site || state.site.id !== id)) loadSite(id);
  });
  loadSite((location.hash || "").slice(1));
})();

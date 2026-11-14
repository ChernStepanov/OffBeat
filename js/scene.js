// Inline terrain keeps the original maps and measured NISAR selections alive.
(() => {
  const $ = id => document.getElementById(id), cloud = OB.pointCloud;
  const scene = $('scene-win'), launcher = $('scene-open'), mapWindow = $('map-win');
  const canvas = $('cloud-canvas');
  // The same terrain panel lives directly below the paired maps.
  mapWindow.after(scene);
  scene.hidden = false;
  scene.classList.add('scene--inline');
  scene.removeAttribute('role'); scene.removeAttribute('aria-modal');
  let active = false, channel = 'hv', view = 'orbit', frame = 0, points = [];
  let selectedSite = null, date = 0, selection = null, dragging = null, hovered = null;
  let gpu = null, gpuPromise = null, starting = false, pendingMapFocus = false, terrain = null, terrainSite = null, terrainTicket = 0, loadedSignalKey = '';
  const terrainCache = new Map();
  const ru = () => document.documentElement.lang === 'ru';
  const phrase = (en, russian) => ru() ? russian : en;
  const fixed = value => Number.isFinite(value) ? value.toFixed(2) : '-';

  function schedule() {
    if (!active || frame) return;
    frame = requestAnimationFrame(() => { frame = 0; render(); });
  }
  function fitCanvas(element) {
    const rect = element.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.round(rect.width), height = Math.round(rect.height);
    if (element.width !== Math.round(width * dpr) || element.height !== Math.round(height * dpr)) {
      element.width = Math.round(width * dpr); element.height = Math.round(height * dpr);
    }
    const ctx = element.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, width, height };
  }
  function render() {
    gpu?.render();
    if (gpu) document.querySelector('.cloud__compass svg').style.transform = `rotate(${-gpu.info().yaw * 180 / Math.PI}deg)`;
    refreshStreamStatus();
    drawHistory();
  }

  function refreshStreamStatus() {
    if (!gpu) return;
    const info = gpu.info(), geo = info.center;
    $('terrain-centre').textContent = `${geo.lat.toFixed(4)}, ${geo.lon.toFixed(4)} / zoom ${info.zoom.toFixed(1)}`;
    $('terrain-status').textContent = `${phrase('DEM tiles', 'Тайлы DEM')}: ${info.fineTiles}/${info.desiredTiles} / z${info.sourceLevel}`
      + (info.pending ? ` / ${phrase('loading', 'загрузка')}: ${info.pending}` : '')
      + (info.failed ? ` / ${phrase('unavailable', 'недоступно')}: ${info.failed}` : '')
      + (info.mode === 'topo' ? ` | ${phrase('Map tiles', 'Тайлы карты')}: ${info.mapReady}/${info.desiredTiles}`
        + (info.mapPending ? ` / ${phrase('loading', 'загрузка')}: ${info.mapPending}` : '')
        + (info.mapFailed ? ` / ${phrase('unavailable; DEM colours shown', 'недоступны; показаны цвета высот')}: ${info.mapFailed}` : '') : '');
    $('terrain-retry').hidden = !info.failed && !info.mapFailed;
    document.querySelector('.terrain-height-key').hidden = info.mode === 'topo' && !info.mapFailed;
    $('terrain-contours').disabled = info.mode === 'topo';
    $('terrain-low').textContent = Math.round(info.min_m).toLocaleString();
    $('terrain-high').textContent = Math.round(info.max_m).toLocaleString();
    $('terrain-scale').textContent = `${(info.span_m / 1000).toFixed(info.span_m < 10000 ? 1 : 0)} km / ${phrase('height', 'высота')} ${info.exaggeration}x`;
    if (info.terrainTiles > 0) $('cloud-empty').hidden = true;
    else if (info.failed && !info.pending) empty(phrase('Elevation tiles unavailable', 'Тайлы высот недоступны'), phrase('Use Retry tiles to reconnect.', 'Нажмите «Повторить загрузку».'));
    const h = selection ? gpu.elevationAt(selection.lon, selection.lat) : null;
    $('terrain-elevation').textContent = Number.isFinite(h) ? `${h.toFixed(1)} m` : '-';
    const b = selectedSite?.grid.bbox, overStudy = b && geo.lon >= b.w && geo.lon <= b.e && geo.lat >= b.s && geo.lat <= b.n && info.zoom >= 8;
    $('cloud-site-name').textContent = overStudy ? selectedSite.name : phrase('World terrain', 'Рельеф мира');
    $('cloud-count').textContent = overStudy ? `${points.length.toLocaleString(ru() ? 'ru-RU' : 'en-US')} / ${selectedSite.pixels.length} ${phrase('measured samples', 'точек с измерениями')}` : phrase('No prepared NISAR series at map centre.', 'В центре карты нет подготовленного ряда NISAR.');
  }

  function empty(title, message) {
    $('cloud-empty').hidden = false;
    $('cloud-empty').querySelector('strong').textContent = title;
    $('cloud-empty').querySelector('span').textContent = message;
  }
  async function loadTerrain(site) {
    const ticket = ++terrainTicket;
    terrainSite = site?.id || null; terrain = null; loadedSignalKey = '';
    gpu?.setTerrain(null, site);
    if (!site) { gpu?.setSamples(null, 0, channel); return; }
    gpu.focusSite(site);
    try {
      if (!terrainCache.has(site.id)) terrainCache.set(site.id, fetch(`data/terrain/${site.id}.json`).then(async response => {
        if (!response.ok) throw new Error(`DEM HTTP ${response.status}`);
        return OB.terrain.validate(await response.json(), site);
      }).catch(error => { terrainCache.delete(site.id); throw error; }));
      const data = await terrainCache.get(site.id);
      if (ticket !== terrainTicket) return;
      terrain = data;
      gpu.setTerrain(data, site);
      update();
    } catch (error) {
      if (ticket !== terrainTicket) return;
      // Prepared DEM context is optional; globally streamed terrain still works for new sites.
      terrain = null; update();
    }
  }

  function drawHistory() {
    const { ctx, width, height } = fitCanvas($('cloud-history'));
    ctx.clearRect(0, 0, width, height);
    const values = selection?.[channel];
    if (!values || !selectedSite) return;
    const times = selectedSite.dates.map(d => Date.parse(d + 'T00:00:00Z'));
    const extent = times.at(-1) - times[0] || 1;
    const x = i => 5 + (width - 10) * (times[i] - times[0]) / extent;
    const y = v => height - 5 - (height - 10) * cloud.clamp((v - cloud.LOW) / (cloud.HIGH - cloud.LOW), 0, 1);
    ctx.strokeStyle = '#d8d8d8'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, height - 6); ctx.lineTo(width, height - 6); ctx.stroke();
    ctx.strokeStyle = channel === 'hv' ? '#007b7b' : '#000080';
    ctx.beginPath(); let gap = true;
    values.forEach((value, i) => {
      if (!Number.isFinite(value)) { gap = true; return; }
      if (gap) ctx.moveTo(x(i), y(value)); else ctx.lineTo(x(i), y(value));
      gap = false;
    }); ctx.stroke();
    values.forEach((value, i) => {
      if (!Number.isFinite(value)) return;
      ctx.fillStyle = i === date ? '#000080' : '#007b7b';
      ctx.fillRect(x(i) - (i === date ? 3 : 1.5), y(value) - (i === date ? 3 : 1.5), i === date ? 6 : 3, i === date ? 6 : 3);
    });
    ctx.strokeStyle = '#808080'; ctx.setLineDash([2, 2]);
    ctx.beginPath(); ctx.moveTo(x(date), 0); ctx.lineTo(x(date), height); ctx.stroke(); ctx.setLineDash([]);
  }

  function update() {
    if (!active || !OB.app) return;
    $('terrain-query').placeholder = phrase('Place or latitude, longitude', 'Место или широта, долгота');
    selectedSite = $('acquisition').hidden ? null : OB.app.site();
    selection = selectedSite ? OB.app.pixel() : null;
    date = OB.app.date();
    points = selectedSite ? selectedSite.pixels.flatMap((p, index) => Number.isFinite(p[channel]?.[date]) && Number.isFinite(p.lat) && Number.isFinite(p.lon) ? [{ index, value: p[channel][date] }] : []) : [];
    $('scene-site').value = selectedSite?.id || '';
    $('scene-site').dispatchEvent(new Event('ob:select-sync'));
    $('cloud-site-name').textContent = selectedSite?.name || phrase('World terrain', 'Рельеф мира');
    $('cloud-date').textContent = selectedSite?.dates[date] || '-';
    $('terrain-date-label').textContent = selectedSite?.dates[date] || '-';
    $('terrain-date').max = String(Math.max(0, (selectedSite?.dates.length || 1) - 1));
    $('terrain-date').value = String(date);
    $('terrain-date').setAttribute('aria-valuetext', selectedSite?.dates[date] || '-');
    $('terrain-date').disabled = !selectedSite || selectedSite.dates.length < 2;
    $('terrain-date-prev').disabled = !selectedSite || date === 0;
    $('terrain-date-next').disabled = !selectedSite || date >= selectedSite.dates.length - 1;
    $('cloud-count').textContent = `${points.length.toLocaleString(ru() ? 'ru-RU' : 'en-US')} / ${selectedSite?.pixels.length || 0} ${phrase('measured samples', 'точек с измерениями')}`;
    if (gpu && terrainSite !== (selectedSite?.id || null)) loadTerrain(selectedSite);
    if (gpu) {
      const signalKey = `${selectedSite?.id || 'world'}/${date}/${channel}/${terrainSite}`;
      if (signalKey !== loadedSignalKey) { gpu.setSamples(selectedSite, date, channel); loadedSignalKey = signalKey; }
      gpu.select(selectedSite?.pixels.indexOf(selection) ?? -1);
    }
    $('cloud-sample-id').textContent = selection?.id || phrase('Select a measured sample', 'Выберите точку измерения');
    $('cloud-value').textContent = selection ? (Number.isFinite(selection[channel][date]) ? `${channel.toUpperCase()} ${fixed(selection[channel][date])} dB` : phrase('Unavailable', 'Недоступно')) : '-';
    $('cloud-cover').textContent = selection ? (OB.COVER[selection.cover]?.name || phrase('Unavailable', 'Недоступно')) : '-';
    $('cloud-coordinates').textContent = selection ? `${selection.lat.toFixed(5)}, ${selection.lon.toFixed(5)}` : '-';
    const elevation = selection && gpu ? gpu.elevationAt(selection.lon, selection.lat) : null;
    $('terrain-elevation').textContent = Number.isFinite(elevation) ? `${elevation.toFixed(1)} m` : '-';
    $('cloud-history-label').textContent = selectedSite ? `${channel.toUpperCase()} / ${selectedSite.dates[0]} - ${selectedSite.dates.at(-1)}` : phrase('Sample history', 'История измерений');
    $('scene-status').textContent = selectedSite ? `${selectedSite.name} / ${selectedSite.dates[date]} / ${channel.toUpperCase()} / ${points.length} ${phrase('samples', 'точек')}` : phrase('Choose a prepared study area', 'Выберите подготовленный участок');
    for (const id of ['cloud-prev', 'cloud-next']) $(id).disabled = !points.length;
    $('cloud-card').disabled = !selection;
    $('scene-fit').disabled = !selectedSite;
    $('terrain-study').disabled = !selectedSite;
    canvas.setAttribute('aria-label', phrase(`3D terrain map with ${points.length} measured ${channel.toUpperCase()} samples. Drag or use arrow keys to orbit; shift-drag to pan; plus and minus zoom.`, `3D-карта рельефа: ${points.length} точек ${channel.toUpperCase()}. Перетаскивание или стрелки вращают карту; Shift - перемещение; плюс и минус - масштаб.`));
    schedule();
  }
  function setChannel(next) {
    channel = next;
    ['hh', 'hv'].forEach(key => $('cloud-' + key).setAttribute('aria-pressed', String(key === channel)));
    hovered = null; update();
  }
  function setView(next) {
    view = next; gpu?.setView(next);
    $('cloud-orbit').setAttribute('aria-pressed', String(next === 'orbit'));
    $('cloud-ground').setAttribute('aria-pressed', String(next === 'ground'));
    $('cloud-plan').setAttribute('aria-pressed', String(next === 'plan'));
    schedule();
  }
  function zoom(factor) { gpu?.zoom(factor); schedule(); }
  // Start WebGL only when the embedded panel approaches the viewport. Stop
  // streaming when it leaves view; map and sample state remain available.
  async function startInline() {
    if (!active || !OB.app) return;
    if (gpu) { gpu.setActive(true); focusMapIfNeeded(); update(); return; }
    if (starting) return;
    starting = true;
    empty(phrase('Starting 3D terrain...', 'Запуск 3D-рельефа...'), 'WebGL / DEM / NISAR');
    try {
      if (!gpuPromise) gpuPromise = OB.createTerrainRenderer(canvas);
      gpu = await gpuPromise;
      OB.terrainView = gpu;
      gpu.setActive(active);
      if (!active) return;
      if ($('acquisition').hidden) pendingMapFocus = true;
      focusMapIfNeeded();
      $('cloud-viewport').classList.toggle('terrain-crt', $('terrain-crt').checked);
      update();
    } catch (error) {
      gpuPromise = null;
      empty(phrase('3D renderer unavailable', '3D-рендерер недоступен'), error.message);
      $('terrain-status').textContent = error.message;
    } finally { starting = false; }
  }
  function focusMapIfNeeded() {
    if (!pendingMapFocus || !gpu) return;
    pendingMapFocus = false;
    const v = OB.app.viewport(); gpu.goTo(v.lon, v.lat, Math.max(0, v.zoom - 2)); setView('plan');
  }
  function showTerrain() {
    if (mapWindow.classList.contains('win--max')) $('map-max').click();
    scene.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  async function step(direction) {
    if (!points.length) return;
    const current = points.findIndex(p => p.index === selectedSite.pixels.indexOf(selection));
    const next = (current + direction + points.length) % points.length;
    await OB.app.pickCell(points[next].index, false);
  }

  launcher.addEventListener('click', showTerrain);
  $('scene-fit').addEventListener('click', () => OB.app.fit());
  $('scene-site').addEventListener('change', async event => {
    const id = event.target.value;
    if (!OB.SITES.some(s => s.id === id)) { update(); return; }
    const url = new URL(location.href); url.searchParams.delete('lat'); url.searchParams.delete('lon'); history.replaceState(null, '', url);
    cancelSearch(); hovered = null; await OB.app.loadSite(id); OB.app.fit(); setView('orbit'); gpu?.focusSite(OB.app.site()); update();
  });
  ['hh', 'hv'].forEach(key => $('cloud-' + key).addEventListener('click', () => setChannel(key)));
  ['orbit', 'ground', 'plan'].forEach(key => $('cloud-' + key).addEventListener('click', () => setView(key)));
  $('cloud-reset').addEventListener('click', () => setView(view));
  $('cloud-zoom-in').addEventListener('click', () => zoom(1.15));
  $('cloud-zoom-out').addEventListener('click', () => zoom(1 / 1.15));
  $('cloud-prev').addEventListener('click', () => step(-1));
  $('cloud-next').addEventListener('click', () => step(1));
  $('cloud-card').addEventListener('click', () => { $('card-win').scrollIntoView({ block: 'start' }); });
  $('terrain-mode').addEventListener('change', event => { gpu?.setMode(event.target.value); schedule(); });
  $('terrain-exaggeration').addEventListener('change', event => { gpu?.setExaggeration(+event.target.value); update(); });
  $('terrain-radar').addEventListener('change', event => { gpu?.setPointsVisible(event.target.checked); schedule(); });
  $('terrain-contours').addEventListener('change', event => { gpu?.setContours(event.target.checked); schedule(); });
  $('terrain-crt').addEventListener('change', event => { $('cloud-viewport').classList.toggle('terrain-crt', event.target.checked); });
  $('terrain-date-prev').addEventListener('click', () => OB.app.selectDate(date - 1));
  $('terrain-date-next').addEventListener('click', () => OB.app.selectDate(date + 1));
  $('terrain-date').addEventListener('input', event => OB.app.selectDate(+event.target.value));
  $('terrain-world').addEventListener('click', () => { cancelSearch(); setView('plan'); gpu?.goTo(0, 15, 0); $('terrain-search-status').textContent = phrase('Global terrain. NISAR measurements are available only at marked study areas.', 'Рельеф мира. Измерения NISAR доступны на отмеченных участках.'); schedule(); });
  $('terrain-study').addEventListener('click', () => { cancelSearch(); if (selectedSite) { setView('orbit'); gpu?.focusSite(selectedSite); schedule(); } });
  $('terrain-map-centre').addEventListener('click', () => { cancelSearch(); const v = OB.app.viewport(); setView('orbit'); gpu?.goTo(v.lon, v.lat, Math.max(0, v.zoom - 2)); schedule(); });
  $('terrain-retry').addEventListener('click', () => { gpu?.retry(); schedule(); });
  let searchTicket = 0, lastSearchAt = 0;
  function cancelSearch() { ++searchTicket; $('terrain-go').disabled = false; }
  const placeCache = new Map();
  $('terrain-search').addEventListener('submit', async event => {
    event.preventDefault();
    const ticket = ++searchTicket, query = OB.normalizePlaceQuery($('terrain-query').value), parsed = OB.parseCoordinates(query);
    if (!query || query.length > 200) { $('terrain-search-status').textContent = phrase('Enter a place name or coordinates (up to 200 characters).', 'Введите место или координаты (до 200 символов).'); return; }
    if (parsed.kind === 'invalid') { $('terrain-search-status').textContent = phrase('Enter latitude, longitude within the map bounds.', 'Введите широту и долготу в пределах карты.'); return; }
    $('terrain-go').disabled = true;
    try {
      let place = parsed;
      if (parsed.kind !== 'coordinates') {
        $('terrain-search-status').textContent = phrase('Searching...', 'Поиск...');
        if (!placeCache.has(query)) {
          const delay = Math.max(0, 1000 - (Date.now() - lastSearchAt));
          if (delay) await new Promise(resolve => setTimeout(resolve, delay));
          if (ticket !== searchTicket) return;
          lastSearchAt = Date.now();
          const results = await OB.geocodePlace(query, window.OB_GEOCODER_URL || 'https://photon.komoot.io/api/');
          if (!results.length) throw new Error(phrase('No place found.', 'Место не найдено.'));
          placeCache.set(query, { lon: results[0].geometry.coordinates[0], lat: results[0].geometry.coordinates[1], name: results[0].properties.name });
        }
        place = placeCache.get(query);
      }
      if (ticket !== searchTicket) return;
      setView('orbit'); gpu?.goTo(place.lon, place.lat, 11); schedule();
      $('terrain-search-status').textContent = `${place.name || query}. ${phrase('Terrain context; no additional NISAR measurements are inferred.', 'Рельеф местности; дополнительные измерения NISAR не подразумеваются.')}`;
    } catch (error) { if (ticket === searchTicket) $('terrain-search-status').textContent = error.message; }
    finally { if (ticket === searchTicket) $('terrain-go').disabled = false; }
  });

  function pointer(event) { const rect = canvas.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; }
  canvas.addEventListener('pointerdown', event => {
    if (![0, 2].includes(event.button) || dragging) return;
    cancelSearch();
    canvas.focus({ preventScroll: true });
    const start = pointer(event);
    dragging = { id: event.pointerId, ...start, startX: start.x, startY: start.y, moved: false, pan: event.shiftKey || event.button === 2 };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add('is-dragging');
  });
  canvas.addEventListener('pointermove', event => {
    const p = pointer(event);
    if (dragging && dragging.id === event.pointerId) {
      const dx = p.x - dragging.x, dy = p.y - dragging.y;
      if (Math.hypot(p.x - dragging.startX, p.y - dragging.startY) > 3) dragging.moved = true;
      if (dragging.moved) {
        if (dragging.pan) gpu?.pan(dx, dy);
        else {
          // A drag from the fixed top view becomes a free 3D orbit.
          if (view === 'plan') setView('orbit');
          gpu?.rotate(dx, dy);
        }
      }
      dragging.x = p.x; dragging.y = p.y;
    } else {
      const hit = gpu?.pick(p.x, p.y);
      hovered = hit?.index ?? null;
      canvas.title = hit?.kind === 'site' ? OB.SITES.find(s => s.id === hit.siteId)?.name || '' : hit ? `${selectedSite.pixels[hit.index].id} / ${hit.height_m.toFixed(1)} m / ${channel.toUpperCase()} ${hit.value.toFixed(2)} dB` : '';
    }
    schedule();
  });
  canvas.addEventListener('pointerup', event => {
    if (!dragging || dragging.id !== event.pointerId) return;
    if (!dragging.moved) {
      const p = pointer(event), hit = gpu?.pick(p.x, p.y);
      if (hit?.kind === 'site') { setView('orbit'); OB.app.loadSite(hit.siteId).then(() => { gpu.focusSite(OB.app.site()); schedule(); }); }
      else if (hit) OB.app.pickCell(hit.index, false);
    }
    dragging = null; canvas.classList.remove('is-dragging');
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  });
  const cancelDrag = () => { dragging = null; canvas.classList.remove('is-dragging'); };
  canvas.addEventListener('pointercancel', cancelDrag); canvas.addEventListener('lostpointercapture', cancelDrag);
  canvas.addEventListener('contextmenu', event => event.preventDefault());
  canvas.addEventListener('pointerleave', () => { hovered = null; schedule(); });
  canvas.addEventListener('wheel', event => { event.preventDefault(); cancelSearch(); zoom(Math.exp(-event.deltaY * .001)); }, { passive: false });
  canvas.addEventListener('dblclick', () => setView(view));
  canvas.addEventListener('keydown', event => {
    const key = /^Key[WASD]$/.test(event.code) ? event.code.slice(3).toLowerCase() : event.key.toLowerCase();
    if (view === 'ground' && ['w', 'a', 's', 'd'].includes(key)) {
      event.preventDefault(); gpu?.walk(key === 'w' ? 1 : key === 's' ? -1 : 0, key === 'd' ? 1 : key === 'a' ? -1 : 0); schedule(); return;
    }
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', '0'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'ArrowLeft') gpu?.rotate(-15, 0);
    if (event.key === 'ArrowRight') gpu?.rotate(15, 0);
    if (event.key === 'ArrowUp') gpu?.rotate(0, -15);
    if (event.key === 'ArrowDown') gpu?.rotate(0, 15);
    if (['+', '='].includes(event.key)) zoom(1.15);
    if (event.key === '-') zoom(1 / 1.15);
    if (event.key === '0') setView(view);
    schedule();
  });
  document.addEventListener('ob:sample-change', () => { if (active) requestAnimationFrame(update); });
  document.addEventListener('ob:map-navigation', () => {
    if (!$('acquisition').hidden) return;
    pendingMapFocus = true;
    if (active && gpu) { focusMapIfNeeded(); update(); }
  });
  document.addEventListener('ob:window-resize', schedule);
  canvas.addEventListener('ob:terrain-stream', schedule);
  canvas.addEventListener('ob:gpu-status', event => {
    if (event.detail === 'lost') empty(phrase('Graphics connection lost', 'Графический контекст потерян'), phrase('Waiting for WebGL to recover...', 'Ожидание восстановления WebGL...'));
    else update();
  });
  new ResizeObserver(() => { if (active) { OB.app?.resizeMaps(); schedule(); } }).observe($('cloud-viewport'));
  new MutationObserver(update).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  document.addEventListener('ob:ready', () => {
    // Include every prepared site from the merged catalogue, including future additions.
    const select = $('scene-site');
    for (const site of OB.SITES) {
      if (![...select.options].some(option => option.value === site.id)) {
        const option = document.createElement('option'); option.value = site.id; option.textContent = site.name; select.add(option);
      }
    }
    for (const option of $('scene-site').options) option.disabled = !OB.SITES.some(site => site.id === option.value);
    $('scene-site').dispatchEvent(new Event('ob:select-sync'));
    launcher.disabled = false;
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(entries => {
        active = entries[0].isIntersecting;
        if (active) startInline();
        else { gpu?.setActive(false); if (frame) cancelAnimationFrame(frame); frame = 0; }
      }, { rootMargin: '250px' }).observe($('terrain-win'));
    } else { active = true; startInline(); }
    if (new URL(location.href).searchParams.get('view') === 'scene') requestAnimationFrame(showTerrain);
  });
  if (document.fonts) document.fonts.ready.then(schedule);
})();

// Focused exploration keeps the original Leaflet maps alive and links each dot to its pixel card.
(() => {
  const $ = id => document.getElementById(id), cloud = OB.pointCloud;
  const scene = $('scene-win'), launcher = $('scene-open'), mapWindow = $('map-win');
  const canvas = $('cloud-canvas'), context = canvas.getContext('2d');
  const home = document.createComment('Map window returns here after Scene view');
  mapWindow.before(home);
  const camera = { yaw: -.55, pitch: .53, zoom: 1 };
  let active = false, channel = 'hv', view = 'orbit', frame = 0, projected = [], points = [];
  let selectedSite = null, date = 0, selection = null, dragging = null, hovered = null, returnFocus = null;
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
  function line(a, b, width, height, color, dash = []) {
    const p = cloud.project(a, camera, width, height), q = cloud.project(b, camera, width, height);
    context.strokeStyle = color; context.setLineDash(dash);
    context.beginPath(); context.moveTo(p.x, p.y); context.lineTo(q.x, q.y); context.stroke();
    context.setLineDash([]);
  }
  function render() {
    const { width, height } = fitCanvas(canvas);
    if (!width || !height) return;
    context.clearRect(0, 0, width, height);
    context.fillStyle = '#091322'; context.fillRect(0, 0, width, height);
    // Quiet pixel grid on the viewport, with a separate geographic reference plane.
    context.fillStyle = '#1a2839';
    for (let y = 12; y < height; y += 24) for (let x = 12; x < width; x += 24) context.fillRect(x, y, 1, 1);
    context.lineWidth = 1;
    for (let i = -5; i <= 5; i++) {
      line({ x: i / 5, y: -1, z: 0 }, { x: i / 5, y: 1, z: 0 }, width, height, '#24374b');
      line({ x: -1, y: i / 5, z: 0 }, { x: 1, y: i / 5, z: 0 }, width, height, '#24374b');
    }
    const origin = { x: -1.13, y: -1.13, z: 0 };
    const axes = [[{ x: 1.18, y: -1.13, z: 0 }, 'E / longitude'], [{ x: -1.13, y: 1.18, z: 0 }, 'N / latitude']];
    if (view !== 'plan') axes.push([{ x: -1.13, y: -1.13, z: 1.35 }, channel.toUpperCase() + ' / dB']);
    context.font = '12.5px W95FA, Tahoma, sans-serif';
    axes.forEach(([end, label]) => {
      line(origin, end, width, height, '#6b8198');
      const p = cloud.project(end, camera, width, height);
      context.fillStyle = '#9aaec7'; context.fillText(label, cloud.clamp(p.x + 6, 8, Math.max(8, width - 95)), cloud.clamp(p.y, 18, height - 60));
    });
    projected = points.map(p => ({ ...p, ...cloud.project(p, camera, width, height) })).sort((a, b) => b.depth - a.depth);
    const selectionIndex = selectedSite?.pixels.indexOf(selection);
    for (const p of projected) {
      const size = Math.max(2, Math.min(5, 3 * p.perspective * Math.sqrt(camera.zoom)));
      const faded = .6 + .4 * cloud.clamp(p.perspective - .7, 0, 1);
      context.fillStyle = `rgba(${p.color.join(',')},${faded})`;
      context.fillRect(Math.round(p.x - size / 2), Math.round(p.y - size / 2), size, size);
    }
    for (const index of [hovered, selectionIndex]) {
      const p = projected.find(p => p.index === index); if (!p) continue;
      line({ ...points.find(p => p.index === index), z: 0 }, points.find(p => p.index === index), width, height, '#f4e29c', [2, 3]);
      context.strokeStyle = index === selectionIndex ? '#fff0a8' : '#fff';
      context.lineWidth = 1; context.strokeRect(Math.round(p.x) - 6.5, Math.round(p.y) - 6.5, 13, 13);
      context.fillStyle = '#fff0a8'; context.fillRect(Math.round(p.x) - 1, Math.round(p.y) - 1, 3, 3);
    }
    // The compass follows the rotation; top view always resets to north up.
    document.querySelector('.cloud__compass svg').style.transform = `rotate(${-camera.yaw * 180 / Math.PI}deg)`;
    drawHistory();
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
    selectedSite = $('acquisition').hidden ? null : OB.app.site();
    selection = selectedSite ? OB.app.pixel() : null;
    date = OB.app.date();
    points = cloud.samples(selectedSite, date, channel);
    $('scene-site').value = selectedSite?.id || '';
    $('scene-site').dispatchEvent(new Event('ob:select-sync'));
    $('cloud-site-name').textContent = selectedSite?.name || 'NISAR / L-BAND';
    $('cloud-date').textContent = selectedSite?.dates[date] || '-';
    $('cloud-count').textContent = `${points.length.toLocaleString(ru() ? 'ru-RU' : 'en-US')} / ${selectedSite?.pixels.length || 0} ${phrase('measured samples', 'точек с измерениями')}`;
    $('cloud-empty').hidden = points.length > 0;
    $('cloud-sample-id').textContent = selection?.id || phrase('Select a measured sample', 'Выберите точку измерения');
    $('cloud-value').textContent = selection ? (Number.isFinite(selection[channel][date]) ? `${channel.toUpperCase()} ${fixed(selection[channel][date])} dB` : phrase('Unavailable', 'Недоступно')) : '-';
    $('cloud-cover').textContent = selection ? (OB.COVER[selection.cover]?.name || phrase('Unavailable', 'Недоступно')) : '-';
    $('cloud-coordinates').textContent = selection ? `${selection.lat.toFixed(5)}, ${selection.lon.toFixed(5)}` : '-';
    $('cloud-history-label').textContent = selectedSite ? `${channel.toUpperCase()} / ${selectedSite.dates[0]} - ${selectedSite.dates.at(-1)}` : phrase('Sample history', 'История измерений');
    $('scene-status').textContent = selectedSite ? `${selectedSite.name} / ${selectedSite.dates[date]} / ${channel.toUpperCase()} / ${points.length} ${phrase('samples', 'точек')}` : phrase('Choose a prepared study area', 'Выберите подготовленный участок');
    for (const id of ['cloud-prev', 'cloud-next']) $(id).disabled = !points.length;
    $('cloud-card').disabled = !selection;
    $('scene-fit').disabled = !selectedSite;
    canvas.setAttribute('aria-label', phrase(`Interactive ${channel.toUpperCase()} sample cloud, ${points.length} measured points. Drag or use arrow keys to rotate; plus and minus zoom.`, `Облако ${channel.toUpperCase()}: ${points.length} точек. Перетаскивание или стрелки вращают облако; плюс и минус изменяют масштаб.`));
    schedule();
  }
  function setChannel(next) {
    channel = next;
    ['hh', 'hv'].forEach(key => $('cloud-' + key).setAttribute('aria-pressed', String(key === channel)));
    hovered = null; update();
  }
  function setView(next) {
    view = next; camera.yaw = next === 'plan' ? 0 : -.55; camera.pitch = next === 'plan' ? Math.PI / 2 : .53; camera.zoom = 1;
    $('cloud-orbit').setAttribute('aria-pressed', String(next === 'orbit'));
    $('cloud-plan').setAttribute('aria-pressed', String(next === 'plan'));
    schedule();
  }
  function zoom(factor) { camera.zoom = cloud.clamp(camera.zoom * factor, .5, 2.5); schedule(); }
  function setURL(on) {
    const url = new URL(location.href);
    if (on) url.searchParams.set('view', 'scene'); else url.searchParams.delete('view');
    history.replaceState(null, '', url);
  }
  async function open() {
    if (active || !OB.app) return;
    document.dispatchEvent(new Event('ob:manual-navigation'));
    returnFocus = document.activeElement;
    active = true; scene.hidden = false;
    $('scene-map-slot').append(mapWindow);
    $('desk').inert = true;
    document.body.classList.add('scene-active');
    launcher.setAttribute('aria-expanded', 'true');
    setURL(true);
    $('scene-back').focus();
    OB.app.resizeMaps();
    if ($('acquisition').hidden) {
      const url = new URL(location.href); url.searchParams.delete('lat'); url.searchParams.delete('lon'); history.replaceState(null, '', url);
      await OB.app.loadSite('amazon');
    }
    if (!active) return;
    OB.app.resizeMaps(); update();
  }
  function close() {
    if (!active) return;
    active = false; dragging = null; hovered = null;
    if (frame) cancelAnimationFrame(frame); frame = 0;
    home.after(mapWindow); scene.hidden = true;
    $('desk').inert = false;
    document.body.classList.remove('scene-active');
    launcher.setAttribute('aria-expanded', 'false');
    setURL(false); OB.app.stop();
    OB.app.resizeMaps();
    (returnFocus?.isConnected && !returnFocus.closest('#scene-win') ? returnFocus : launcher).focus({ preventScroll: true });
    window.dispatchEvent(new Event('resize'));
  }
  async function step(direction) {
    if (!points.length) return;
    const current = points.findIndex(p => p.index === selectedSite.pixels.indexOf(selection));
    const next = (current + direction + points.length) % points.length;
    await OB.app.pickCell(points[next].index, false);
  }

  launcher.addEventListener('click', open);
  $('scene-close').addEventListener('click', close);
  $('scene-back').addEventListener('click', close);
  $('scene-fit').addEventListener('click', () => OB.app.fit());
  $('scene-site').addEventListener('change', async event => {
    const id = event.target.value;
    if (!OB.SITES.some(s => s.id === id)) { update(); return; }
    const url = new URL(location.href); url.searchParams.delete('lat'); url.searchParams.delete('lon'); history.replaceState(null, '', url);
    hovered = null; await OB.app.loadSite(id); OB.app.fit(); update();
  });
  ['hh', 'hv'].forEach(key => $('cloud-' + key).addEventListener('click', () => setChannel(key)));
  ['orbit', 'plan'].forEach(key => $('cloud-' + key).addEventListener('click', () => setView(key)));
  $('cloud-reset').addEventListener('click', () => setView(view));
  $('cloud-zoom-in').addEventListener('click', () => zoom(1.15));
  $('cloud-zoom-out').addEventListener('click', () => zoom(1 / 1.15));
  $('cloud-prev').addEventListener('click', () => step(-1));
  $('cloud-next').addEventListener('click', () => step(1));
  $('cloud-card').addEventListener('click', () => { close(); $('card-win').scrollIntoView({ block: 'start' }); });

  function pointer(event) { const rect = canvas.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; }
  canvas.addEventListener('pointerdown', event => {
    if (event.button !== 0 || dragging) return;
    canvas.focus({ preventScroll: true });
    const start = pointer(event);
    dragging = { id: event.pointerId, ...start, startX: start.x, startY: start.y, moved: false };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add('is-dragging');
  });
  canvas.addEventListener('pointermove', event => {
    const p = pointer(event);
    if (dragging && dragging.id === event.pointerId) {
      const dx = p.x - dragging.x, dy = p.y - dragging.y;
      if (Math.hypot(p.x - dragging.startX, p.y - dragging.startY) > 3) dragging.moved = true;
      if (dragging.moved) {
        camera.yaw += dx * .008;
        if (view === 'orbit') camera.pitch = cloud.clamp(camera.pitch + dy * .006, .08, 1.48);
      }
      dragging.x = p.x; dragging.y = p.y;
    } else {
      const hit = cloud.hitTest(projected, p.x, p.y);
      hovered = hit?.index ?? null;
      canvas.title = hit ? `${selectedSite.pixels[hit.index].id} / ${channel.toUpperCase()} ${hit.value.toFixed(2)} dB` : '';
    }
    schedule();
  });
  canvas.addEventListener('pointerup', event => {
    if (!dragging || dragging.id !== event.pointerId) return;
    if (!dragging.moved) { const p = pointer(event), hit = cloud.hitTest(projected, p.x, p.y); if (hit) OB.app.pickCell(hit.index, false); }
    dragging = null; canvas.classList.remove('is-dragging');
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  });
  const cancelDrag = () => { dragging = null; canvas.classList.remove('is-dragging'); };
  canvas.addEventListener('pointercancel', cancelDrag); canvas.addEventListener('lostpointercapture', cancelDrag);
  canvas.addEventListener('pointerleave', () => { hovered = null; schedule(); });
  canvas.addEventListener('wheel', event => { event.preventDefault(); zoom(Math.exp(-event.deltaY * .001)); }, { passive: false });
  canvas.addEventListener('dblclick', () => setView(view));
  canvas.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', '0'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'ArrowLeft') camera.yaw -= .1;
    if (event.key === 'ArrowRight') camera.yaw += .1;
    if (event.key === 'ArrowUp' && view === 'orbit') camera.pitch = cloud.clamp(camera.pitch + .1, .08, 1.48);
    if (event.key === 'ArrowDown' && view === 'orbit') camera.pitch = cloud.clamp(camera.pitch - .1, .08, 1.48);
    if (['+', '='].includes(event.key)) zoom(1.15);
    if (event.key === '-') zoom(1 / 1.15);
    if (event.key === '0') setView(view);
    schedule();
  });
  scene.addEventListener('keydown', event => {
    if (event.key === 'Escape') event.sceneHadPopup = !!scene.querySelector('[aria-expanded="true"][aria-haspopup="listbox"]');
  }, true);
  scene.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (event.sceneHadPopup) return;
      event.preventDefault(); close();
    } else if (event.key === 'Tab') {
      const focusable = [...scene.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), [tabindex="0"]')].filter(el => el.getClientRects().length && !el.closest('[hidden]'));
      const index = focusable.indexOf(document.activeElement);
      if (event.shiftKey && index <= 0) { event.preventDefault(); focusable.at(-1)?.focus(); }
      else if (!event.shiftKey && index === focusable.length - 1) { event.preventDefault(); focusable[0]?.focus(); }
    }
  });
  document.addEventListener('ob:sample-change', () => { if (active) requestAnimationFrame(update); });
  new ResizeObserver(() => { if (active) { OB.app?.resizeMaps(); schedule(); } }).observe($('cloud-viewport'));
  new MutationObserver(update).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  document.addEventListener('ob:ready', () => {
    for (const option of $('scene-site').options) option.disabled = !OB.SITES.some(site => site.id === option.value);
    $('scene-site').dispatchEvent(new Event('ob:select-sync'));
    launcher.disabled = false;
    if (new URL(location.href).searchParams.get('view') === 'scene') requestAnimationFrame(open);
  });
  if (document.fonts) document.fonts.ready.then(schedule);
})();

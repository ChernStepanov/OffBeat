// One desktop-style window manager for panels, individual maps and the 3D workspace.
window.OB = window.OB || {};
OB.windows = (() => {
  const layer = document.createElement('div'); layer.id = 'window-layer'; layer.hidden = true;
  const shade = document.createElement('div'); shade.className = 'window-shade'; shade.setAttribute('aria-hidden', 'true');
  layer.append(shade); document.body.append(layer);
  let state = null, fullscreenOwner = null, fullscreenReturn = null;
  const ru = () => document.documentElement.lang === 'ru';
  const names = () => ru() ? ['Увеличить окно', 'Развернуть окно', 'На весь экран'] : ['Enlarge window', 'Maximize window', 'Browser fullscreen'];
  const icons = [
    '<path d="M1 4h8v7H1zM4 1h7v7M6 3h3v3"/>',
    '<path d="M1 1h10v10H1zM1 3h10"/>',
    '<path d="M1 5V1h4m2 0h4v4m0 2v4H7m-2 0H1V7"/>',
  ];
  function resized() {
    requestAnimationFrame(() => {
      OB.app?.resizeMaps(); window.dispatchEvent(new Event('resize'));
      document.dispatchEvent(new Event('ob:window-resize'));
    });
  }
  function relabel() {
    document.querySelectorAll('[data-window-action]').forEach(button => {
      const label = names()[['large', 'max', 'screen'].indexOf(button.dataset.windowAction)];
      const window = button.closest('.win, .maps__pane');
      const pressed = state?.element === window && (button.dataset.windowAction === state.mode || (button.dataset.windowAction === 'screen' && document.fullscreenElement === window));
      const actionLabel = pressed ? (ru() ? 'Вернуть прежний размер' : 'Restore previous size') : label;
      button.title = actionLabel; button.setAttribute('aria-label', actionLabel);
      button.setAttribute('aria-pressed', String(!!pressed));
    });
  }
  function restoreDOM() {
    if (!state) return;
    const old = state; state = null;
    old.home.after(old.element); old.home.remove();
    old.element.classList.remove('window-expanded', 'window-large', 'window-max');
    for (const name of ['role', 'aria-modal']) {
      if (old.attributes[name] === null) old.element.removeAttribute(name); else old.element.setAttribute(name, old.attributes[name]);
    }
    old.inert.forEach(([element, value]) => { element.inert = value; });
    layer.hidden = true; document.body.classList.remove('window-active');
    (old.focus?.isConnected ? old.focus : old.element.querySelector('button'))?.focus({ preventScroll: true });
    relabel(); resized();
  }
  async function restore() {
    fullscreenOwner = null;
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
    restoreDOM();
  }
  function applyMode(mode) {
    if (!state) return;
    state.mode = mode;
    state.element.classList.toggle('window-large', mode === 'large');
    state.element.classList.toggle('window-max', mode === 'max');
    relabel(); resized();
  }
  function promote(element, mode) {
    if (state?.element === element) { applyMode(mode); return; }
    restoreDOM();
    const home = document.createComment('Expanded panel returns here'); element.before(home);
    state = { element, home, mode, focus: document.activeElement, attributes: { role: element.getAttribute('role'), 'aria-modal': element.getAttribute('aria-modal') }, inert: [] };
    layer.append(element); layer.hidden = false;
    for (const element of [document.getElementById('desk'), document.getElementById('scene-win'), document.querySelector('.sbar')]) {
      if (element && !element.contains(state.element) && element !== state.element) { state.inert.push([element, element.inert]); element.inert = true; }
    }
    element.classList.add('window-expanded'); element.setAttribute('role', 'dialog'); element.setAttribute('aria-modal', 'true');
    document.body.classList.add('window-active'); applyMode(mode);
    element.querySelector('[data-window-action="' + mode + '"]')?.focus({ preventScroll: true });
  }
  async function action(element, mode) {
    if (mode === 'screen') {
      if (document.fullscreenElement === element) { await document.exitFullscreen(); return; }
      fullscreenReturn = state?.element === element ? state.mode : null;
      promote(element, 'max'); fullscreenOwner = element;
      try { await element.requestFullscreen(); } catch (_) { fullscreenOwner = null; /* maximized viewport remains usable */ }
      relabel(); resized(); return;
    }
    if (document.fullscreenElement) { fullscreenOwner = null; await document.exitFullscreen(); }
    if (state?.element === element && state.mode === mode) restoreDOM(); else promote(element, mode);
  }
  // Only panels whose contents benefit from more space get window controls.
  // The main map has its own maximize button; the 3D workspace already fills the screen.
  const windows = [...document.querySelectorAll('#radar-pane, #optical-pane, #terrain-win, #card-win, #top-win')];
  for (const element of windows) {
    const title = [...element.children].find(child => child.classList.contains('win-t'));
    if (!title) continue;
    const controls = document.createElement('div'); controls.className = 'window-buttons'; controls.setAttribute('role', 'group');
    ['large', 'max', 'screen'].forEach((mode, index) => {
      const button = document.createElement('button'); button.type = 'button'; button.dataset.windowAction = mode;
      button.innerHTML = `<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" fill="none" stroke="currentColor" shape-rendering="crispEdges">${icons[index]}</svg>`;
      button.addEventListener('click', () => action(element, mode)); controls.append(button);
    });
    title.insertBefore(controls, title.querySelector('#scene-close'));
    title.addEventListener('dblclick', event => { if (!event.target.closest('button')) action(element, 'max'); });
  }
  shade.addEventListener('click', restore);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') event.windowHadPopup = !!document.querySelector('.select98 [aria-expanded="true"]'); }, true);
  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && fullscreenOwner) {
      fullscreenOwner = null;
      if (fullscreenReturn) applyMode(fullscreenReturn); else restoreDOM();
    }
    relabel(); resized();
  });
  document.addEventListener('keydown', event => {
    if (!state || event.defaultPrevented) return;
    if (event.key === 'Escape') {
      // Let an open select popup consume its first Escape.
      if (event.windowHadPopup) return;
      event.preventDefault(); event.stopPropagation(); restore();
    } else if (event.key === 'Tab') {
      const focus = [...state.element.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]')].filter(e => e.getClientRects().length && !e.closest('[hidden]'));
      const i = focus.indexOf(document.activeElement);
      if (event.shiftKey && i <= 0) { event.preventDefault(); focus.at(-1)?.focus(); }
      else if (!event.shiftKey && i === focus.length - 1) { event.preventDefault(); focus[0]?.focus(); }
    }
  });
  new MutationObserver(relabel).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  relabel();
  return { restore, active: () => state?.element || null, mode: () => state?.mode || null };
})();

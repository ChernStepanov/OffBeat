// "What the data says": statistical conclusions precomputed by scripts/findings.py from measured samples.
window.OB = window.OB || {};
(() => {
  const $ = id => document.getElementById(id);
  const list = $('findings-list'), more = $('findings-more'), intro = $('findings-intro'), warning = $('data-quality');
  if (!list) return;
  const ru = () => document.documentElement.lang === 'ru';
  const t = (en, ruText) => ru() ? ruText : en;
  const STRENGTH = {
    strong: ['Strong', 'Надёжно'], suggestive: ['Suggestive', 'Вероятно'],
    none: ['Not supported', 'Не подтверждено'], issue: ['Data issue', 'Проблема данных'],
  };
  const FIRST = 3;
  let data = null, expanded = false, rendering = false;
  const cursor = {};

  const siteId = () => OB.app?.site?.()?.id || null;
  const ordered = () => {
    const here = siteId();
    // the open site's own findings first, otherwise the analysis order (issues, strong, suggestive, none)
    return data.findings.map((f, i) => ({ f, i })).sort((a, b) => ((b.f.site === here) - (a.f.site === here)) || a.i - b.i).map(x => x.f);
  };

  function button(text, onClick) {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'btn'; b.textContent = text;
    b.addEventListener('click', onClick); return b;
  }

  async function show(f) {
    document.dispatchEvent(new Event('ob:manual-navigation'));
    await OB.app.loadSite(f.site);
    if (f.samples?.length) {
      const k = cursor[f.id] || 0;
      OB.app.pickCell(f.samples[k], true);
      cursor[f.id] = (k + 1) % f.samples.length;
      render();
    }
    $('map-win')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function item(f) {
    const li = document.createElement('li');
    li.className = `finding finding--${f.strength}`;
    if (f.site && f.site === siteId()) li.classList.add('finding--here');
    const badge = document.createElement('span'); badge.className = 'finding__badge'; badge.textContent = t(...STRENGTH[f.strength]);
    const text = document.createElement('p'); text.className = 'finding__text'; text.textContent = t(f.en, f.ru);
    const how = document.createElement('details'); how.className = 'finding__how';
    const summary = document.createElement('summary'); summary.textContent = t('How we know', 'Как это проверено');
    const body = document.createElement('p'); body.textContent = t(f.how_en, f.how_ru);
    how.append(summary, body);
    li.append(badge, text);
    if (f.site) {
      const actions = document.createElement('div'); actions.className = 'finding__actions';
      if (f.samples?.length) {
        // first press shows the strongest sample; later presses step through the others
        const k = cursor[f.id] || 0, n = f.samples.length;
        actions.append(button(n === 1 || (k === 0 && !(f.id in cursor)) ? t('Show on map', 'Показать на карте') : t(`Next sample (${k + 1} of ${n})`, `Следующая точка (${k + 1} из ${n})`), () => show(f)));
      } else if (f.site !== siteId()) {
        actions.append(button(t('Show on map', 'Показать на карте'), () => show(f)));
      }
      if (actions.childElementCount) li.append(actions);
    }
    li.append(how);
    if (f.drivers_en) {
      // the challenge asks for hypotheses about physical drivers; they are labelled as such
      const why = document.createElement('details'); why.className = 'finding__how';
      const label = document.createElement('summary'); label.textContent = t('Why might this happen?', 'Почему так может быть?');
      const text = document.createElement('p'); text.textContent = t(f.drivers_en, f.drivers_ru);
      why.append(label, text); li.append(why);
    }
    return li;
  }

  // Key numbers, the ones the presentation video shows, each with the view that proves it.
  async function openSubsidence() {
    document.dispatchEvent(new Event('ob:manual-navigation'));
    await OB.app.loadSite('mexico');
    OB.app.setLayers({ offbeat: false, extra: ['opera_tied'] });
    document.querySelectorAll('#side details').forEach(d => { if (d.querySelector('#site-layers')) d.open = true; });
    OB.app.fit();
    $('map-win')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  async function playStrongest() {
    const trends = data.sites.mexico?.trends; if (!trends) return;
    // the steepest drift among the most significant ones (q < 0.001): the sample the video plays
    const sure = trends.strongest.filter(h => h.q < 0.001);
    const best = (sure.length ? sure : trends.strongest).sort((a, b) => Math.abs(b.slope_db_per_year) - Math.abs(a.slope_db_per_year))[0];
    document.dispatchEvent(new Event('ob:manual-navigation'));
    await OB.app.loadSite('mexico');
    OB.app.setLayers({ offbeat: true, extra: [] });
    await OB.app.pickCell(best.index, true);
    $('map-win')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(() => OB.app.play(), 600);   // the click is the user gesture that allows audio
  }
  function tile(value, label, note, down, action) {
    const box = document.createElement('div'); box.className = 'keynum';
    const v = document.createElement('span'); v.className = 'keynum__value' + (down ? ' keynum__value--down' : ''); v.textContent = value;
    const l = document.createElement('span'); l.className = 'keynum__label'; l.textContent = label;
    const n = document.createElement('span'); n.className = 'keynum__note'; n.append(...note);
    box.append(v, l, n);
    if (action) box.append(button(action[0], action[1]));
    return box;
  }
  function keys() {
    const g = data.opera_vs_gnss, tie = data.opera_tied, mx = data.sites.mexico;
    const out = [];
    if (g && tie) {
      const med = Object.values(tie.percentiles_5_50_95).map(p => Math.abs(p[1])).sort((a, b) => a - b);
      out.push(tile(`${g.gnss_up_cm_per_year} ${t('cm/yr', 'см/год')}`, t('Mexico City sinks (GNSS MMX1)', 'Мехико проседает (GNSS MMX1)'),
        [t(`vertical. OPERA 20 m away: ${g.opera_los_cm_per_year_common} cm/yr relative line of sight, a different reference and geometry. Anchored at this station, OPERA suggests about ${med[0].toFixed(0)}-${med[1].toFixed(0)} cm/yr along the radar line (estimate).`,
           `по вертикали. OPERA в 20 м: ${g.opera_los_cm_per_year_common} см/год относительного смещения вдоль луча, другая опора и геометрия. С привязкой к этой станции OPERA даёт около ${med[0].toFixed(0)}-${med[1].toFixed(0)} см/год вдоль луча (оценка).`)],
        true, [t('Show subsidence map', 'Показать карту проседания'), openSubsidence]));
    }
    if (mx?.trends) out.push(tile(String(mx.trends.samples), t('Mexico City points drift from their neighbours', 'точек Мехико уходят от соседей'),
      [t(`over ${mx.dates} dates, false discovery rate 5%`, `за ${mx.dates} дат, доля ложных открытий 5%`)], false,
      [t('Play the steepest trend', 'Проиграть самый крутой тренд'), playStrongest]));
    if (mx?.clustering) out.push(tile(`p = ${mx.clustering.p}`, t('Changes cluster in Mexico City', 'Изменения в Мехико образуют пятна'),
      [t(`${mx.clustering.adjacent_pairs} neighbouring pairs vs ${mx.clustering.expected_pairs} by chance`, `${mx.clustering.adjacent_pairs} соседних пар против ${mx.clustering.expected_pairs} случайно`)]));
    const overlap = Object.values(data.sites).map(s => s.polarisation?.both_of_either).filter(Number.isFinite);
    if (overlap.length) out.push(tile(`${Math.round(100 * Math.min(...overlap))}-${Math.round(100 * Math.max(...overlap))}%`, t('flagged in both HH and HV', 'отмечены и в HH, и в HV'),
      [t('the two polarisations see different changes', 'две поляризации видят разные изменения')]));
    $('findings-keys').replaceChildren(...out);
  }

  function render() {
    if (!data) return;
    rendering = true;
    keys();
    const all = ordered(), shown = expanded ? all : all.slice(0, FIRST);
    const samples = Object.values(data.sites).reduce((n, s) => n + s.clustering.valid, 0);
    intro.textContent = t(
      `Statistical tests over ${Object.keys(data.sites).length} sites and ${samples.toLocaleString('en')} measured samples. Nothing is interpolated or simulated, and causes are not attributed.`,
      `Статистические тесты по ${Object.keys(data.sites).length} участкам и ${samples.toLocaleString('ru')} измеренным точкам. Ничего не интерполировано и не смоделировано, причины не приписываются.`);
    list.replaceChildren(...shown.map(item));
    more.hidden = all.length <= FIRST;
    more.textContent = expanded ? t('Show fewer', 'Свернуть') : t(`Show all ${all.length} findings`, `Показать все выводы (${all.length})`);
    const issue = data.findings.find(f => f.strength === 'issue' && f.site && f.site === siteId());
    warning.hidden = !issue;
    if (issue) warning.textContent = t(issue.en, issue.ru);
    rendering = false;
  }

  more.addEventListener('click', () => { expanded = !expanded; render(); });

  // the presentation video in a Win98-era media player dialog
  const modal = $('video-modal'), player = $('video-player');
  if (modal && player) {
    const mmss = v => `${String(Math.floor(v / 60)).padStart(2, '0')}:${String(Math.floor(v % 60)).padStart(2, '0')}`;
    const status = () => {
      const d = Number.isFinite(player.duration) ? player.duration : 30;
      $('mp-state').textContent = player.ended ? t('Finished', 'Завершено') : player.paused ? (player.currentTime > 0 ? t('Paused', 'Пауза') : t('Stopped', 'Остановлено')) : t('Playing', 'Воспроизведение');
      $('mp-time').textContent = `${mmss(player.currentTime)} / ${mmss(d)}`;
      if (!seeking) $('mp-seek').value = String(Math.round(1000 * player.currentTime / d));
      $('mp-play').setAttribute('aria-pressed', String(!player.paused));
      $('mp-pause').setAttribute('aria-pressed', String(player.paused && player.currentTime > 0 && !player.ended));
    };
    let seeking = false;
    const play = () => player.play().catch(() => {});
    const toggle = () => player.paused ? play() : player.pause();
    const stopAll = () => { player.pause(); player.currentTime = 0; status(); };
    const closeVideo = () => { stopAll(); modal.hidden = true; $('video-open').focus(); };
    ['play', 'pause', 'timeupdate', 'ended', 'loadedmetadata', 'seeked'].forEach(e => player.addEventListener(e, status));
    $('mp-play').addEventListener('click', play);
    $('mp-pause').addEventListener('click', () => player.pause());
    $('mp-stop').addEventListener('click', stopAll);
    $('mp-start').addEventListener('click', () => { player.currentTime = 0; });
    $('mp-back').addEventListener('click', () => { player.currentTime = Math.max(0, player.currentTime - 5); });
    $('mp-fwd').addEventListener('click', () => { player.currentTime = Math.min(player.duration || 30, player.currentTime + 5); });
    $('mp-menu-play').addEventListener('click', toggle);
    $('mp-view').addEventListener('click', () => (player.requestFullscreen ? player.requestFullscreen() : Promise.reject()).catch(() => {}));
    player.addEventListener('click', toggle);
    const seek = $('mp-seek');
    seek.addEventListener('input', () => { seeking = true; player.currentTime = (player.duration || 30) * seek.value / 1000; });
    seek.addEventListener('change', () => { seeking = false; });
    const volume = $('mp-volume'), mute = $('mp-mute');
    volume.addEventListener('input', () => { player.volume = volume.value / 100; player.muted = false; mute.setAttribute('aria-pressed', 'false'); });
    mute.addEventListener('click', () => { player.muted = !player.muted; mute.setAttribute('aria-pressed', String(player.muted)); });
    player.volume = volume.value / 100;
    $('video-open')?.addEventListener('click', () => { const stop = $('stop'); if (stop && !stop.disabled) stop.click(); modal.hidden = false; play(); $('video-close').focus(); });
    $('video-close')?.addEventListener('click', closeVideo);
    modal.addEventListener('click', e => { if (e.target === modal) closeVideo(); });
    document.addEventListener('keydown', e => {
      if (modal.hidden) return;
      if (e.key === 'Escape') closeVideo();
      if (e.key === ' ' && !['INPUT', 'BUTTON', 'A'].includes(document.activeElement?.tagName)) { e.preventDefault(); toggle(); }
    });
    status();
  }
  document.addEventListener('ob:sample-change', () => { if (!rendering) render(); });
  new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });

  fetch('data/findings.json', { cache: 'no-cache' })
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(json => { data = json; render(); })
    .catch(() => { list.replaceChildren(Object.assign(document.createElement('li'), { textContent: t('Findings unavailable.', 'Выводы недоступны.') })); });
  OB.findings = { data: () => data, render };
})();

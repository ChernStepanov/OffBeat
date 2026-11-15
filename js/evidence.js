// A short investigation, backed by stored source receipts and explicit unknowns.
window.OB = window.OB || {};
OB.evidence = (() => {
  const $ = id => document.getElementById(id), model = OB.evidenceModel;
  const initialParams = new URL(location.href).searchParams;
  const ru = () => document.documentElement.lang === 'ru';
  const local = value => typeof value === 'object' ? value[ru() ? 'ru' : 'en'] : value;
  const words = {
    introTitle: ['A change in the signal. What changed on Earth?', 'Сигнал изменился. А что изменилось на Земле?'],
    intro: ['Follow a real Amazon sample from radar measurement to independent evidence and a practical next step.', 'Пройдите путь реальной точки Амазонии: от измерения радара до независимых свидетельств и решения.'],
    welcome: ['Start with one Amazon investigation, or take a two-minute tour of the available sites.', 'Начните с одного исследования в Амазонии или пройдите двухминутный обзор доступных участков.'],
    start: ['Investigate a change', 'Исследовать пример изменения'],
    visibleClearing: ['See visually reviewed clearing', 'Посмотреть расчистку на снимках'],
    visibleCaveat: ['Optical review; NISAR detection has not been validated.', 'Визуальная проверка по снимкам; обнаружение радаром не подтверждено.'],
    surpriseTitle: ['Not sure where to start?', 'Не знаете, с чего начать?'],
    surpriseHint: ['Open one of three prepared Amazon investigations, then follow its evidence.', 'Откройте одно из трёх подготовленных исследований Амазонии и проверьте доказательства.'],
    surprise: ['Surprise me ✦', 'Удиви меня ✦'],
    close: ['Close story', 'Закрыть историю'],
    scope: ['Development casebook: 0 eligible confirmed events for detector evaluation. Accuracy is not established.', 'Исследовательские примеры: 0 пригодных подтверждённых событий для оценки детектора. Точность не установлена.'],
    selection: ['Evidence for selected sample', 'Доказательства для выбранной точки'],
    copy: ['Copy point link', 'Скопировать ссылку на точку'], json: ['Download evidence / JSON', 'Скачать доказательства / JSON'],
    geojson: ['Download point / GeoJSON', 'Скачать точку / GeoJSON'], permalink: ['Open saved view', 'Открыть сохранённый вид'],
  };
  const t = (en, rus) => ru() ? rus : en;
  let book, active = null, step = 0, engaged = false, opening = false, serial = 0;
  let latestReport = null;
  // Attach rejection handling immediately; a failed casebook must not break the map.
  const ready = fetch('data/cases/amazon-v1.json').then(r => {
    if (!r.ok) throw new Error('Casebook unavailable'); return r.json();
  }).then(data => { book = data; return data; }).catch(() => {
    $('case-status').textContent = t('Casebook could not load. The map remains available.', 'Не удалось загрузить примеры. Карта доступна.');
    return null;
  });
  function el(tag, text, className) {
    const node = document.createElement(tag); if (text !== undefined) node.textContent = text;
    if (className) node.className = className; return node;
  }
  function button(text, action) {
    const node = el('button', text, 'btn'); node.type = 'button'; node.addEventListener('click', action); return node;
  }
  function source(path, label = path) {
    const a = el('a', label); a.href = path; a.target = '_blank'; a.rel = 'noopener'; return a;
  }
  function currentCase() {
    const s = OB.app?.site(), p = OB.app?.pixel();
    return book?.cases.find(c => c.id === active && c.site === s?.id && c.sample_id === p?.id) || null;
  }
  function heading(text) { $('case-page').append(el('h3', text)); }
  function paragraph(text) { $('case-page').append(el('p', text)); }
  function fmt(n) { return Number.isFinite(n) ? n.toFixed(2) : t('Missing', 'Нет данных'); }
  function table(rows) {
    const node = el('table', undefined, 'casebook__facts');
    const body = document.createElement('tbody');
    rows.forEach(([key, value]) => {
      const row = el('tr'), th = el('th', key); th.scope = 'row'; row.append(th, el('td', value)); body.append(row);
    }); node.append(body); $('case-page').append(node);
  }
  function renderChart(site, pixel) {
    const svgNS = 'http://www.w3.org/2000/svg', svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 600 160'); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', t('HV backscatter: sample and same-class peer median. Values are in the table below.', 'HV: точка и медиана соседей того же класса. Значения в таблице ниже.'));
    const values = [...pixel.hv, ...(pixel.peer?.hv_med || [])].filter(Number.isFinite);
    if (!values.length) { paragraph(t('No HV measurements or peer values available.', 'Измерения HV и значения соседей отсутствуют.')); return () => {}; }
    const lo = Math.min(...values) - 1, hi = Math.max(...values) + 1;
    const positions = model.timeline(site.dates);
    const x = i => 45 + positions[i] * 510, y = v => 125 - (v - lo) * 100 / (hi - lo);
    function node(tag, attrs, text) { const n = document.createElementNS(svgNS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); if (text) n.textContent = text; svg.append(n); }
    for (let i = 0; i < 3; i++) {
      const v = lo + i * (hi - lo) / 2;
      node('line', {x1: 40, x2: 560, y1: y(v), y2: y(v), stroke: '#d0d0d0'});
      node('text', {x: 0, y: y(v) + 4, 'font-size': 12}, v.toFixed(1));
    }
    const beat = document.createElementNS(svgNS, 'line');
    beat.setAttribute('y1', '15'); beat.setAttribute('y2', '130'); beat.setAttribute('stroke', '#67217a');
    beat.setAttribute('stroke-width', '2'); beat.setAttribute('visibility', 'hidden'); svg.append(beat);
    [[pixel.hv, '#000080'], [pixel.peer?.hv_med || [], '#008080']].forEach(([series, color]) => {
      let d = '', connected = false;
      series.forEach((v, i) => {
        if (!Number.isFinite(v)) { connected = false; return; }
        d += `${connected ? 'L' : 'M'}${x(i)} ${y(v)} `; connected = true;
        node('circle', {cx: x(i), cy: y(v), r: i === OB.app.date() ? 5 : 3, fill: color});
      }); node('path', {d, fill: 'none', stroke: color, 'stroke-width': 2});
    });
    node('text', {x: 45, y: 150, 'font-size': 12}, site.dates[0]);
    node('text', {x: 480, y: 150, 'font-size': 12}, site.dates.at(-1));
    $('case-page').append(svg);
    return index => {
      if (!Number.isInteger(index) || index < 0 || index >= positions.length) { beat.setAttribute('visibility', 'hidden'); return; }
      beat.setAttribute('x1', x(index)); beat.setAttribute('x2', x(index)); beat.setAttribute('visibility', 'visible');
    };
  }
  function opticalPair(dossier, pixel) {
    const pair = el('div', undefined, 'casebook__optics');
    dossier.optical.forEach(image => {
      const figure = el('figure'), viewport = el('div', undefined, 'casebook__image');
      const b = image.bounds, px = (pixel.lon - b.w) / (b.e - b.w), py = (b.n - pixel.lat) / (b.n - b.s);
      const img = document.createElement('img'); img.src = image.path; img.alt = `${image.source} / ${image.date}`;
      img.style.left = `${50 - px * 400}%`; img.style.top = `${50 - py * 400}%`;
      img.addEventListener('error', () => { viewport.replaceChildren(el('p', t('Image unavailable. Open source below.', 'Снимок недоступен. Источник ниже.'))); });
      viewport.append(img, el('span', '+', 'casebook__cross'));
      const caption = el('figcaption'); caption.append(source(image.item_url, `Sentinel-2 / ${image.date}`));
      caption.append(el('p', t(`AOI clear: ${(100 * image.aoi_clear_fraction).toFixed(1)}%; not point quality.`, `Ясная площадь AOI: ${(100 * image.aoi_clear_fraction).toFixed(1)}%; не качество точки.`)));
      figure.append(viewport, caption); pair.append(figure);
    }); $('case-page').append(pair);
    if (dossier.optical.length === 2) {
      const compare = el('div', undefined, 'story-compare');
      const frame = el('div', undefined, 'story-compare__frame');
      frame.setAttribute('aria-hidden', 'true');
      const layers = dossier.optical.map(image => {
        const layer = el('div', undefined, 'story-compare__layer');
        const b = image.bounds, px = (pixel.lon - b.w) / (b.e - b.w), py = (b.n - pixel.lat) / (b.n - b.s);
        const img = document.createElement('img'); img.src = image.path; img.alt = '';
        img.style.left = `${50 - px * 400}%`; img.style.top = `${50 - py * 400}%`;
        layer.append(img); frame.append(layer); return layer;
      });
      frame.append(el('span', '+', 'casebook__cross'));
      const slider = document.createElement('input'); slider.type = 'range'; slider.min = '0'; slider.max = '100'; slider.value = '50';
      slider.setAttribute('aria-label', t('Compare earlier and later optical images', 'Сравнить ранний и поздний оптические снимки'));
      const update = () => { layers[1].style.clipPath = `inset(0 0 0 ${slider.value}%)`; };
      slider.addEventListener('input', update); update();
      const labels = el('div', undefined, 'story-compare__labels');
      labels.append(el('span', `${t('Earlier', 'Раньше')} / ${dossier.optical[0].date}`), el('span', `${t('Later', 'Позже')} / ${dossier.optical[1].date}`));
      compare.append(el('strong', t('Slide to compare', 'Передвиньте ползунок для сравнения')), frame, slider, labels);
      $('case-page').append(compare);
    }
    paragraph(t('Same geographic crop, 4x preview; cross marks the sample. Transparent pixels are masked. Optical dates differ from radar dates. AOI-wide clarity cannot rule out cloud or shadow at this point.', 'Одинаковый географический фрагмент, превью 4x; крест — точка. Прозрачные пиксели замаскированы. Даты оптики отличаются от радара. Ясность всего AOI не исключает облако или тень в точке.'));
  }
  function setStep(n, focus = true) {
    OB.app?.stop(); step = Math.max(0, Math.min(3, n)); render(); persist();
    if (focus) {
      $('case-page').focus({preventScroll: true});
      $('case-page').scrollIntoView({behavior: 'smooth', block: 'start'});
    }
  }
  function persist() {
    if (engaged && latestReport) history.replaceState(null, '', latestReport.permalink);
  }
  function render() {
    document.querySelectorAll('[data-case-text]').forEach(n => { n.textContent = words[n.dataset.caseText][ru() ? 1 : 0]; });
    if (!book || !OB.app) return;
    $('evidence-selection').disabled = !OB.app.pixel();
    const choices = $('case-choices'); choices.replaceChildren();
    book.cases.forEach(c => { const b = button(local(c.title), () => open(c.id)); b.setAttribute('aria-pressed', String(c.id === active)); choices.append(b); });
    if (!engaged) return;
    const site = OB.app.site(), pixel = OB.app.pixel();
    ['evidence-copy', 'evidence-json', 'evidence-geojson'].forEach(id => { $(id).disabled = !site || !pixel; });
    if (!site || !pixel) {
      latestReport = null; $('case-workspace').hidden = true; return;
    }
    const dossier = currentCase();
    if (!dossier) active = null;
    $('case-workspace').hidden = false;
    const permalink = model.link(location.href, site, pixel, OB.app.date(), dossier?.id, step);
    latestReport = model.report(site, pixel, OB.app.date(), dossier, book, permalink, ru() ? 'ru' : 'en');
    $('evidence-link').href = permalink;
    const steps = [t('1 / Place', '1 / Место'), t('2 / Radar + sound', '2 / Радар + звук'), t('3 / Independent evidence', '3 / Независимые данные'), t('4 / Decision', '4 / Решение')];
    const nav = $('case-steps'); nav.replaceChildren();
    steps.forEach((name, i) => { const b = button(name, () => setStep(i)); if (i === step) b.setAttribute('aria-current', 'step'); nav.append(b); });
    $('case-progress').textContent = `${step + 1} / 4`; $('case-back').disabled = step === 0;
    $('case-next').disabled = step === 3;
    const page = $('case-page'); page.replaceChildren();
    heading(dossier ? local(dossier.title) : t('Selected sample / not independently reviewed', 'Выбранная точка / независимой проверки нет'));
    if (dossier) paragraph(local(dossier.question));
    paragraph(`${site.name} / ${pixel.id} / ${pixel.lat.toFixed(5)}, ${pixel.lon.toFixed(5)}`);
    if (step === 0) {
      paragraph(t('Start with the place, then compare the measured series, inspect dated optical evidence and decide what to check next.', 'Начните с места, сравните измеренный ряд, проверьте датированную оптику и решите, что проверять дальше.'));
      table([[t('NISAR observations', 'Наблюдения NISAR'), `${site.dates[0]} / ${site.dates.at(-1)}`],
        [t('Valid HV dates', 'Валидные даты HV'), `${pixel.hv.filter(Number.isFinite).length} / ${site.dates.length}`],
        [t('Historical cover', 'Исторический покров'), `ESA WorldCover 2021 / ${pixel.cover}`],
        [t('Spatial support', 'Пространственная поддержка'), t('Sparse samples. No event area estimate.', 'Разреженные точки. Площадь события не оценена.')]]);
      page.append(button(t('Locate on the map', 'Показать на карте'), () => {
        OB.app.zoomTo(pixel.lat, pixel.lon, 15); $('map-win').scrollIntoView({behavior: 'smooth', block: 'start'});
      }));
    } else if (step === 1) {
      paragraph(t('Navy: sample HV; teal: same-class peer median (stored local reference, not the separate benchmark model). Sound follows the measured series; it is not a classifier.', 'Синий: HV точки; бирюзовый: медиана соседей того же класса (сохранённый локальный фон, а не отдельная модель бенчмарка). Звук следует измеренному ряду; он не классификатор.'));
      const showBeat = renderChart(site, pixel);
      const pair = dossier?.radar_pair || [0, site.dates.length - 1];
      const controls = el('div', undefined, 'casebook__bar');
      pair.forEach((index, i) => controls.append(button(`${t(i ? 'After' : 'Before', i ? 'После' : 'До')} / ${site.dates[index]}`, () => OB.app.selectDate(index))));
      const audioStatus = el('p', t('Sound is a designed representation of HV, not a recording from space.', 'Звук — способ представить измерения HV, а не запись из космоса.'), 'casebook__audio-status');
      audioStatus.setAttribute('role', 'status');
      const audio = {pix: pixel.hv, med: pixel.peer?.hv_med || [], sd: pixel.peer?.hv_sd || []};
      const canPlay = audio.pix.some((v, i) => Number.isFinite(v) && Number.isFinite(audio.med[i]) && Number.isFinite(audio.sd[i]) && audio.sd[i] > 0);
      const play = button(t('Hear sample and neighbours', 'Слушать точку и соседей'), () => {
        try {
          OB.app.stop();
          OB.sonify.play(audio, i => {
            showBeat(i);
            const available = Number.isFinite(audio.pix[i]) && Number.isFinite(audio.med[i]) && Number.isFinite(audio.sd[i]) && audio.sd[i] > 0;
            audioStatus.textContent = site.dates[i] + ' / ' + (available ? t('HV sample and neighbours', 'HV точки и соседей') : t('missing values: silent beat', 'нет данных: пауза'));
          }, () => { showBeat(null); audioStatus.textContent = t('Playback finished.', 'Воспроизведение завершено.'); });
        } catch (_) { audioStatus.textContent = t('Audio is unavailable in this browser.', 'Звук недоступен в этом браузере.'); }
      });
      play.disabled = !canPlay;
      controls.append(play, button(t('Stop', 'Стоп'), () => { OB.app.stop(); showBeat(null); audioStatus.textContent = t('Playback stopped.', 'Воспроизведение остановлено.'); }));
      page.append(controls, audioStatus);
      table(site.dates.map((d, i) => [d + (i === OB.app.date() ? ' *' : ''), `HH ${fmt(pixel.hh?.[i])} dB / HV ${fmt(pixel.hv[i])} dB / HV ${t('peers', 'соседи')} ${fmt(pixel.peer?.hv_med?.[i])} dB`]));
      paragraph(`${t('Pairwise HH difference', 'Разность HH выбранной пары')}: ${fmt(Number.isFinite(pixel.hh?.[pair[0]]) && Number.isFinite(pixel.hh?.[pair[1]]) ? pixel.hh[pair[1]] - pixel.hh[pair[0]] : null)} dB.`);
      paragraph(`${t('Pairwise HV difference', 'Разность HV выбранной пары')}: ${fmt(Number.isFinite(pixel.hv[pair[0]]) && Number.isFinite(pixel.hv[pair[1]]) ? pixel.hv[pair[1]] - pixel.hv[pair[0]] : null)} dB.`);
      if (dossier) paragraph(local(dossier.observed));
      paragraph(t('Backscatter changes can reflect moisture, structure, speckle or acquisition effects. A radar change alone does not identify the cause. These before/after buttons select observations, not verified event boundaries.', 'На обратное рассеяние влияют влажность, структура, спекл и условия съёмки. Изменение радара само по себе не определяет причину. Кнопки «до/после» выбирают наблюдения, а не доказанные границы события.'));
    } else if (step === 2) {
      if (dossier) { opticalPair(dossier, pixel); paragraph(local(dossier.independent)); }
      else paragraph(t('No independent review is attached to this point. Open the source manifest and collect dated, quality-checked optical or field evidence before interpreting the cause.', 'Для этой точки нет независимого разбора. Откройте исходные данные и соберите датированную оптику с проверкой качества или полевые свидетельства до вывода о причине.'));
    } else {
      heading(t('Evidence passport', 'Паспорт данных'));
      const selected = OB.app.date(), peerCount = pixel.peer_counts?.hv?.[selected], peerZ = pixel.z_hv?.[selected];
      table([[t('Selected observation', 'Выбранное наблюдение'), `${site.dates[selected]} / HV ${fmt(pixel.hv[selected])} dB`],
        [t('Comparable neighbours on this date', 'Соседи того же класса на эту дату'), Number.isFinite(peerCount) ? String(peerCount) : t('Unavailable', 'Нет данных')],
        [t('Deviation from neighbours', 'Отклонение от соседей'), Number.isFinite(peerZ) ? `z ${peerZ.toFixed(2)}` : t('Unavailable', 'Нет данных')],
        [t('Missing HV observations', 'Пропущенные наблюдения HV'), String(site.dates.length - pixel.hv.filter(Number.isFinite).length)],
        [t('Dated optical context', 'Датированная оптика'), dossier?.optical?.length ? dossier.optical.map(image => image.date).join(' / ') : t('No reviewed images for this sample', 'Для этой точки нет проверенных снимков')],
        [t('Coverage / quality', 'Покрытие / качество'), t(`${pixel.hv.filter(Number.isFinite).length}/${site.dates.length} valid HV dates. Provisional NISAR; event cause is not quality-validated.`, `${pixel.hv.filter(Number.isFinite).length}/${site.dates.length} валидных дат HV. Предварительный продукт NISAR; качество не подтверждает причину события.`)],
        [t('Evidence status', 'Статус свидетельств'), dossier ? local(dossier.interpretation) : t('Not independently reviewed; cause unknown.', 'Независимой проверки нет; причина неизвестна.')],
        [t('Next action', 'Следующее действие'), dossier ? local(dossier.action) : t('Review dated independent observations and quality masks.', 'Проверить датированные независимые наблюдения и маски качества.')],
        [t('Evaluation', 'Оценка качества'), t('0 eligible positive events; 0 blind negative controls; precision, recall and FPR are unknown.', '0 пригодных положительных событий; 0 слепых отрицательных контролей; precision, recall и FPR неизвестны.')]]);
      paragraph(t('Retrospective development examples. These three points are not independent test events or a validated stable / changed / false-alarm benchmark.', 'Ретроспективные исследовательские примеры. Эти три точки не являются независимыми тестовыми событиями или валидированным набором «стабильно / изменение / ложное срабатывание».'));
    }
    const sources = el('details'); sources.append(el('summary', t('Sources, dates and reproducibility', 'Источники, даты и воспроизводимость')));
    const list = el('ul');
    (dossier?.sources || [`data/${site.id}.json`]).forEach(path => {
      const li = el('li'); li.append(source(path));
      const sha = book.input_sha256[path]; if (sha) li.append(el('code', `SHA-256 ${sha}`)); list.append(li);
    }); sources.append(list); page.append(sources);
  }
  async function open(id, options = {}) {
    const ticket = ++serial; opening = true;
    try {
      if (!await ready || !OB.app) return;
      document.dispatchEvent(new Event('ob:manual-navigation')); OB.app.stop();
      const dossier = book.cases.find(c => c.id === id);
      if (dossier) {
        await OB.app.loadSite(dossier.site);
        if (ticket !== serial || OB.app.site()?.id !== dossier.site) return;
        await OB.app.pickCell(dossier.sample_index, false);
        if (ticket !== serial || OB.app.pixel()?.id !== dossier.sample_id) return;
        OB.app.selectDate(options.date ?? dossier.radar_pair[1]);
        OB.app.zoomTo(OB.app.pixel().lat, OB.app.pixel().lon, 15);
      }
      active = dossier?.id || null; engaged = true; step = options.step ?? (dossier ? 0 : 3);
      $('evidence-disclosure').open = true;
      render(); persist();
      if (options.scroll !== false) { $('evidence-win').scrollIntoView({behavior: 'smooth', block: 'start'}); $('case-page').focus({preventScroll: true}); }
    } catch (_) {
      $('case-status').textContent = t('Could not open the sample. Please choose an example again.', 'Не удалось открыть точку. Выберите пример ещё раз.');
    } finally { if (ticket === serial) opening = false; }
  }
  async function restore() {
    if (!initialParams.has('case') && !initialParams.has('sample')) return;
    if (!await ready) return;
    const saved = model.selection(initialParams, OB.app.sites(), book.cases);
    if (!saved) { $('case-status').textContent = t('Saved sample or date is unavailable. Choose an example.', 'Сохранённая точка или дата недоступна. Выберите пример.'); return; }
    await OB.app.loadSite(saved.site.id); await OB.app.pickCell(saved.index, false); OB.app.selectDate(saved.date);
    const pixel = OB.app.pixel();
    if (pixel) OB.app.zoomTo(pixel.lat, pixel.lon, 15);
    await open(saved.caseId, {date: saved.date, step: saved.step, scroll: false});
  }
  function download(geo) {
    if (!latestReport) return;
    const data = geo ? model.geojson(latestReport) : latestReport;
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], {type: geo ? 'application/geo+json' : 'application/json'}));
    const a = el('a'); a.href = url; a.download = `offbeat-${latestReport.site}-${latestReport.sample_id.replace(/\W+/g, '-')}.${geo ? 'geojson' : 'json'}`;
    a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('launch-example').addEventListener('click', event => {
    if (!$('case-start').disabled) { event.preventDefault(); open('amazon-hv-step'); }
  });
  $('case-start').addEventListener('click', () => open('amazon-hv-step'));
  $('case-surprise').addEventListener('click', () => {
    const choices = (book?.cases || []).filter(c => c.id !== active);
    if (choices.length) open(choices[Math.floor(Math.random() * choices.length)].id);
  });
  $('case-visible-clearing').addEventListener('click', () => open('amazon-visible-clearing', {step: 2}));
  $('evidence-selection').addEventListener('click', () => open(null));
  $('case-back').addEventListener('click', () => setStep(step - 1));
  $('case-next').addEventListener('click', () => setStep(step + 1));
  $('case-close').addEventListener('click', () => {
    serial++; opening = false; engaged = false; active = null; latestReport = null;
    OB.app?.stop(); $('case-workspace').hidden = true;
    const url = new URL(location.href);
    ['case', 'step', 'sample'].forEach(key => url.searchParams.delete(key));
    history.replaceState(null, '', url);
    render(); $('case-surprise').focus();
  });
  $('evidence-json').addEventListener('click', () => download(false));
  $('evidence-geojson').addEventListener('click', () => download(true));
  $('evidence-copy').addEventListener('click', async () => {
    if (!latestReport) return;
    const href = latestReport.permalink;
    try { await navigator.clipboard.writeText(href); $('case-status').textContent = t('Point link copied.', 'Ссылка на точку скопирована.'); }
    catch (_) { const field = $('evidence-link-fallback'); field.hidden = false; field.value = href; field.focus(); field.select(); $('case-status').textContent = t('Select and copy the link below.', 'Выделите и скопируйте ссылку ниже.'); }
  });
  document.addEventListener('ob:ready', async () => {
    const available = await ready;
    ['case-start', 'case-visible-clearing', 'case-surprise', 'welcome-case', 'evidence-selection'].forEach(id => { $(id).disabled = !available; }); render();
  }, {once: true});
  document.addEventListener('ob:sample-change', () => requestAnimationFrame(() => {
    if (!opening) { OB.app?.stop(); render(); persist(); }
  }));
  new MutationObserver(() => render()).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
  return {open, restore, report: () => latestReport};
})();

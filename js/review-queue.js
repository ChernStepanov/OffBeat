// Retrospective evidence collection priorities. Never probabilities or event diagnoses.
window.OB = window.OB || {};
OB.reviewQueue = (() => {
  const $ = id => document.getElementById(id);
  const initial = new URL(location.href);
  const initialSample = initial.hash === '#review-win' && initial.searchParams.get('site') === 'amazon' ? initial.searchParams.get('sample') : null;
  const t = (en, ru) => document.documentElement.lang === 'ru' ? ru : en;
  let data = null, method = 's1_nisar_context', selected = null, count = 8, busy = false, serial = 0, navigationFailed = false;
  const names = () => ({s1_only: 'Sentinel-1', s1_nisar: 'Sentinel-1 + NISAR', s1_nisar_context: t('S1 + NISAR + evidence gaps', 'S1 + NISAR + пробелы в свидетельствах')});
  const agreements = () => ({both_drop: t('Both above threshold', 'Оба выше порога'), threshold_disagreement: t('Threshold disagreement', 'Расхождение по порогу'), neither_above_threshold: t('Below thresholds', 'Ниже порогов'), unavailable: t('Sensor unavailable', 'Сенсор недоступен')});
  const actions = () => ({obtain_clear_optical: t('Obtain point-clear optical before/after', 'Получить ясную оптику до/после в точке'), obtain_missing_sensor: t('Obtain the missing radar channel', 'Получить недостающий радарный канал'), inspect_sensor_disagreement: t('Check geometry, timing and sensor disagreement', 'Проверить геометрию, даты и расхождение сенсоров'), independent_image_review: t('Independently review dated images', 'Независимо проверить датированные снимки')});
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  function button(text, fn) { const n = el('button', text, 'btn'); n.type = 'button'; n.addEventListener('click', fn); return n; }
  function link(text, href) { const a = el('a', text); a.href = href; a.target = '_blank'; a.rel = 'noopener'; return a; }
  function fileLink(text, href) { const a = link(text, href); a.download = href.split('/').at(-1); return a; }
  function download(value, name, type = 'application/json') {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + '\n'], {type}));
    const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function pointLink(row) {
    const url = new URL(location.href); url.search = ''; url.hash = 'review-win';
    url.searchParams.set('site', row.site); url.searchParams.set('sample', row.sample_index);
    url.searchParams.set('date', data.decision_date); url.searchParams.set('step', 4); return url.href;
  }
  async function locate(row, evidence = false) {
    const ticket = ++serial; busy = true; navigationFailed = false; render();
    try {
      document.dispatchEvent(new Event('ob:manual-navigation')); OB.app.stop();
      await OB.app.loadSite(row.site);
      if (ticket !== serial || OB.app.site()?.id !== row.site) return;
      await OB.app.pickCell(row.sample_index, false);
      if (ticket !== serial || OB.app.pixel()?.id !== row.sample_id) return;
      const date = OB.app.site().dates.indexOf(data.decision_date);
      if (date < 0) throw new Error('Date unavailable');
      OB.app.selectDate(date); OB.app.zoomTo(row.lat, row.lon, 15);
      if (evidence) await OB.evidence.open(null);
      else $('map-win').scrollIntoView({behavior: 'smooth', block: 'start'});
    } catch (_) { navigationFailed = true; }
    finally { if (ticket === serial) { busy = false; render(); } }
  }
  function facts(rows, parent) {
    const dl = el('dl', undefined, 'review__facts');
    for (const [a, b] of rows) dl.append(el('dt', a), el('dd', b)); parent.append(dl);
  }
  const fmt = x => Number.isFinite(x) ? x.toFixed(2) : t('Unavailable', 'Нет данных');
  function detail(row) {
    const panel = $('review-detail'); panel.replaceChildren(); panel.hidden = !row;
    if (!row) return;
    panel.append(el('h3', `${row.sample_id} / ${data.decision_date}`));
    facts([[t('Priority', 'Приоритет'), `${fmt(row.scores[method])} / ${t('heuristic score, not %', 'эвристический балл, не %')}`],
      [t('NISAR / L-band', 'NISAR / L-диапазон'), `${t('Residual mean drop', 'Падение среднего остатка')}: ${fmt(row.l_band?.drop_db)} dB; ${t('raw', 'исходный')}: ${fmt(row.l_band?.raw_drop_db)} dB`],
      [t('Sentinel-1 / C-band', 'Sentinel-1 / C-диапазон'), `${t('Residual mean drop', 'Падение среднего остатка')}: ${fmt(row.c_band?.drop_db)} dB; ${t('raw', 'исходный')}: ${fmt(row.c_band?.raw_drop_db)} dB`],
      [t('Post-date support L / C', 'Поддержка по датам после L / C'), `${row.l_band ? row.l_band.post_below_history + '/' + row.l_band.post_count : '—'} / ${row.c_band ? row.c_band.post_below_history + '/' + row.c_band.post_count : '—'}`],
      [t('Sensors', 'Сенсоры'), agreements()[row.agreement]],
      [t('Point optical visibility', 'Видимость точки в оптике'), row.optical.status === 'point_clear_pair_available' ? t('Clear SCL pair available; event not reviewed', 'Ясная SCL-пара есть; событие не проверено') : t('A clear pair is not established; AOI clarity is insufficient', 'Ясная пара не установлена; ясности AOI недостаточно')],
      [t('Next observation / check', 'Следующее наблюдение / проверка'), actions()[row.next_action]],
      [t('Independent label', 'Независимая метка'), t('Unknown. No verified cause or event area.', 'Неизвестна. Причина и площадь события не подтверждены.')]], panel);
    const dates = el('p', t('Aligned SAR acquisitions: ', 'Сопоставленные даты SAR: '));
    dates.append(el('span', data.aligned_dates.map(d => `${d.nisar} / ${d.s1 || '—'}`).join('; '))); panel.append(dates);
    for (const [name, image] of [[t('Clear before', 'Ясно до'), row.optical.clear_before], [t('Clear after', 'Ясно после'), row.optical.clear_after]]) {
      if (image) { const p = el('p', `${name}: ${image.date}, SCL ${image.scl}. `); if (image.scl_asset) p.append(link(t('Quality source', 'Источник качества'), image.scl_asset)); panel.append(p); }
    }
    const controls = el('div', undefined, 'review__controls');
    const map = button(t('Show on map', 'Показать на карте'), () => locate(row));
    const evidence = button(t('Open evidence card', 'Открыть карточку доказательств'), () => locate(row, true));
    map.disabled = evidence.disabled = !OB.app || busy;
    controls.append(map, evidence, link(t('Point link', 'Ссылка на точку'), pointLink(row)),
      button(t('Download point evidence', 'Скачать свидетельства точки'), () => download({schema_version: 1, row, decision_date: data.decision_date, aligned_dates: data.aligned_dates, input_sha256: data.input_sha256, limitations: data.limitations}, `offbeat-review-${row.sample_index}.json`)));
    panel.append(controls);
    const annotations = el('details'); annotations.append(el('summary', t('Record a development review', 'Записать исследовательскую проверку')));
    annotations.append(el('p', t('You have seen the ranking: this note is not a blind independent test label. It is exported as development-only and will not train the event model.', 'Вы уже видели рейтинг: эта заметка не является слепой независимой тестовой меткой. Она выгружается только как исследовательская и не используется для обучения модели событий.')));
    const form = el('form', undefined, 'review__annotation');
    function field(label, kind = 'input') {
      const wrapper = el('label', label); const control = document.createElement(kind); control.required = true;
      wrapper.append(control); form.append(wrapper); return control;
    }
    const reviewer = field(t('Reviewer', 'Проверяющий')); reviewer.name = 'reviewer';
    const source = field(t('Evidence source URL', 'URL источника свидетельств')); source.type = 'url'; source.name = 'source';
    const note = field(t('What is visible, dates and quality limitations', 'Что видно, даты и ограничения качества'), 'textarea'); note.name = 'note';
    const submit = el('button', t('Export development note', 'Выгрузить исследовательскую заметку'), 'btn'); submit.type = 'submit'; form.append(submit);
    form.addEventListener('submit', e => {
      e.preventDefault();
      download({schema_version: 1, sample_id: row.sample_id, event_group: row.event_group, split: 'development', label: 'unknown', independent: false, blind_to_scores: false,
        reviewer: reviewer.value.trim(), evidence_sources: [source.value], observation: note.value.trim(), reviewed_at: new Date().toISOString(), queue_input_sha256: data.input_sha256}, `offbeat-development-note-${row.sample_index}.json`);
    }); annotations.append(form); panel.append(annotations);
  }
  function render() {
    $('review-title').textContent = t('OffBeat / Inspection priorities', 'OffBeat / Приоритеты проверки');
    $('review-summary').textContent = t('Review queue / NISAR + Sentinel-1', 'Очередь проверок / NISAR + Sentinel-1');
    $('review-intro').textContent = t('Amazonia: inspect persistent radar changes, sensor disagreement and missing evidence. Development snapshot through 28 September 2026; historical publication availability is unknown.', 'Амазония: проверяйте устойчивые изменения радара, расхождения сенсоров и недостающие свидетельства. Исследовательский срез по 28 сентября 2026; историческая доступность продуктов не установлена.');
    $('review-candidates-label').textContent = t('Candidates from either radar channel', 'Кандидаты хотя бы по одному радарному каналу');
    $('review-how').textContent = t('Methods and limitations', 'Методы и ограничения');
    if (!data) return;
    const list = $('review-methods'); list.replaceChildren();
    for (const [key, name] of Object.entries(names())) { const b = button(name, () => { method = key; count = 8; render(); }); b.setAttribute('aria-pressed', String(key === method)); list.append(b); }
    const candidates = $('review-candidates').checked;
    const ids = (candidates ? data.candidate_rankings : data.rankings)[method];
    const byId = new Map(data.rows.map(row => [row.sample_id, row]));
    const rows = ids.map(id => byId.get(id)).filter(Boolean);
    $('review-status').textContent = t(`${data.rows.length} forest samples; ${data.rows.filter(r => r.candidate).length} candidate samples. Showing ${Math.min(count, rows.length)} of ${rows.length} spaced review locations.`, `${data.rows.length} лесных точек; ${data.rows.filter(r => r.candidate).length} точек-кандидатов. Показано ${Math.min(count, rows.length)} из ${rows.length} разнесённых мест проверки.`);
    if (navigationFailed) $('review-status').textContent += t(' Sample could not open. Try the point link.', ' Не удалось открыть точку. Используйте ссылку на неё.');
    $('review-metrics').textContent = t('Independent test events: 0. Precision, recall and saved review effort are unknown. Score is a heuristic, not probability. Locations are not independent events.', 'Независимых тестовых событий: 0. Precision, recall и экономия проверок неизвестны. Балл — эвристика, не вероятность. Места проверки не являются независимыми событиями.');
    $('review-caption').textContent = `${names()[method]} / ${t('higher priority first', 'сначала больший приоритет')}`;
    const head = el('tr'); for (const text of [t('Sample / priority', 'Точка / приоритет'), 'L / C · dB', t('Next check', 'Следующая проверка')]) { const th = el('th', text); th.scope = 'col'; head.append(th); }
    $('review-head').replaceChildren(head); const body = $('review-body'); body.replaceChildren();
    rows.slice(0, count).forEach(row => {
      const tr = el('tr'); tr.dataset.sample = row.sample_id; tr.classList.toggle('review__selected', selected === row.sample_id);
      const first = el('td'); first.append(button(`${row.sample_id} / ${fmt(row.scores[method])}`, () => { selected = row.sample_id; render(); $('review-detail').focus({preventScroll: true}); $('review-detail').scrollIntoView({behavior: 'auto', block: 'nearest'}); }));
      const signals = el('td', `${fmt(row.l_band?.drop_db)} / ${fmt(row.c_band?.drop_db)}`); signals.append(el('small', agreements()[row.agreement]));
      tr.append(first, signals, el('td', actions()[row.next_action])); body.append(tr);
    });
    $('review-more').hidden = count >= rows.length; $('review-more').textContent = t('Show more', 'Показать ещё');
    detail(byId.get(selected));
    const explanation = $('review-explanation'); explanation.replaceChildren();
    for (const text of [t('Drop = first-three-date mean minus last-three-date mean after subtracting same-class peers at 300–1200 m (minimum 10). Positive means lower backscatter. Cover is WorldCover 2021; samples are sparse.', 'Падение = среднее первых трёх дат минус среднее последних трёх после вычитания фона соседей того же класса на 300–1200 м (минимум 10). Положительное число означает снижение рассеяния. Покров — WorldCover 2021; точки разрежены.'),
      t('S1 uses only acquisitions on/before each NISAR date, within 2 days. No future-date match. Fusion takes the stronger normalised score plus fixed persistence/disagreement terms. A missing sensor stays missing.', 'S1 использует съёмки не позже каждой даты NISAR с разницей до 2 дней. Будущие даты не подставляются. Объединённый балл использует более сильный нормированный сигнал и фиксированные добавки за устойчивость/расхождение. Отсутствующий сенсор остаётся отсутствующим.'),
      t('Context adds a fixed evidence-gap priority when a point-clear optical pair is not established. Weather is context only; it does not correct the score or prove a cause. This is a collection-priority experiment, not event classification.', 'Контекст добавляет фиксированный приоритет сбора данных, если ясная оптическая пара в точке не установлена. Погода — только контекст: она не корректирует балл и не доказывает причину. Это эксперимент по приоритетам сбора данных, а не классификация событий.')]) explanation.append(el('p', text));
    const rain = data.weather_context.acquisitions;
    explanation.append(el('p', t('Previous 7 full UTC days precipitation / mm: ', 'Осадки за 7 предыдущих полных UTC-дней / мм: ') + rain.map(r => `${r.nisar_date}: ${r.previous_7_utc_days_mm}`).join('; ')));
    explanation.append(link(t('Frozen development protocol', 'Фиксированный исследовательский протокол'), 'data/review-queue/protocol-v1.json'));
    const downloads = $('review-downloads'); downloads.replaceChildren(fileLink(t('Queue / JSON', 'Очередь / JSON'), 'data/review-queue/amazon-v1.json'), fileLink('GeoJSON', 'data/review-queue/amazon-v1.geojson'), fileLink(t('Variant comparison', 'Сравнение вариантов'), 'data/review-queue/comparison-v1.json'), fileLink(t('Training status', 'Статус обучения'), 'data/review-queue/learning-status-v1.json'), link(t('Independent training data format', 'Формат независимых данных для обучения'), 'docs/review-queue.md'));
  }
  $('review-candidates').addEventListener('change', () => { count = 8; render(); });
  $('review-more').addEventListener('click', () => { count += 8; render(); });
  document.addEventListener('ob:ready', render, {once: true});
  new MutationObserver(render).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
  render();
  const ready = fetch('data/review-queue/amazon-v1.json').then(r => { if (!r.ok) throw new Error('unavailable'); return r.json(); }).then(d => {
    data = d;
    if (/^(0|[1-9]\d*)$/.test(initialSample || '')) selected = data.rows.find(r => r.sample_index === Number(initialSample))?.sample_id || null;
    render(); return d;
  }).catch(() => { $('review-status').textContent = t('Review queue unavailable; maps remain accessible.', 'Очередь недоступна; карты доступны.'); return null; });
  return {ready, selected: () => selected};
})();

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
    return li;
  }

  function render() {
    if (!data) return;
    rendering = true;
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
  document.addEventListener('ob:sample-change', () => { if (!rendering) render(); });
  new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });

  fetch('data/findings.json', { cache: 'no-cache' })
    .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(json => { data = json; render(); })
    .catch(() => { list.replaceChildren(Object.assign(document.createElement('li'), { textContent: t('Findings unavailable.', 'Выводы недоступны.') })); });
  OB.findings = { data: () => data, render };
})();

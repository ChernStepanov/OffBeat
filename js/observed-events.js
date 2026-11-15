// NASA-published image comparisons, kept separate from OffBeat detector results.
(() => {
  const $ = id => document.getElementById(id);
  const disclosure = $('observed-events-disclosure');
  const ru = () => document.documentElement.lang === 'ru';
  const t = (en, russian) => ru() ? russian : en;
  let catalog = null, pending = null;
  function render() {
    $('observed-events-summary').textContent = t('Documented changes: images before and after', 'Документированные изменения: снимки до и после');
    $('observed-events-title').textContent = t('Documented changes', 'Документированные изменения');
    $('observed-events-note').textContent = t('Images published by NASA, not detections by OffBeat. The Hubbard example uses NISAR; NISAR coverage for the other examples has not been checked.', 'Снимки опубликованы NASA: это не находки алгоритма OffBeat. В примере ледника Хаббард использован NISAR; его покрытие для остальных примеров пока не проверено.');
    if (!catalog) return;
    const list = $('observed-events-list'); list.replaceChildren();
    catalog.cases.forEach(item => {
      const article = document.createElement('article'); article.className = 'observed-event';
      const title = document.createElement('h3'); title.textContent = item.title[ru() ? 'ru' : 'en'];
      const desc = document.createElement('p'); desc.textContent = item.description[ru() ? 'ru' : 'en'];
      const images = document.createElement('div'); images.className = 'observed-event__images';
      item.images.forEach((image, index) => {
        const figure = document.createElement('figure'), img = document.createElement('img'), caption = document.createElement('figcaption');
        img.src = image.path; img.loading = 'lazy'; img.decoding = 'async';
        img.alt = `${item.title[ru() ? 'ru' : 'en']} / ${image.date}`;
        caption.textContent = `${index ? t('After', 'После') : t('Before', 'До')} / ${image.date} · ${item.credit}`;
        figure.append(img, caption); images.append(figure);
      });
      const actions = document.createElement('div'); actions.className = 'observed-event__actions';
      const source = document.createElement('a'); source.href = item.source; source.target = '_blank'; source.rel = 'noopener'; source.textContent = t('NASA source and image details', 'Источник NASA и описание снимков');
      actions.append(source); article.append(title, desc, images, actions); list.append(article);
    });
    $('observed-events-status').textContent = '';
  }
  disclosure.addEventListener('toggle', async () => {
    if (!disclosure.open || catalog) return;
    $('observed-events-status').textContent = t('Loading images…', 'Загрузка снимков…');
    try {
      pending ||= fetch('data/observed-events/index.json?v=1').then(r => { if (!r.ok) throw Error(); return r.json(); });
      catalog = await pending;
      if (catalog.schema_version !== 1 || !Array.isArray(catalog.cases)) throw Error();
      render();
    } catch (_) { pending = null; catalog = null; $('observed-events-status').textContent = t('Images are unavailable. Please try again.', 'Снимки недоступны. Попробуйте ещё раз.'); }
  });
  new MutationObserver(render).observe(document.documentElement, {attributes:true, attributeFilter:['lang']});
  render();
})();

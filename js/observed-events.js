// NASA-published image comparisons, kept separate from OffBeat detector results.
(() => {
  window.OB = window.OB || {};
  const $ = id => document.getElementById(id);
  const disclosure = $('observed-events-disclosure');
  const ru = () => document.documentElement.lang === 'ru';
  const t = (en, russian) => ru() ? russian : en;
  let catalog = null, pending = null, selected = null;
  async function load() {
    if (catalog) return catalog;
    pending ||= fetch('data/observed-events/index.json?v=1').then(r => { if (!r.ok) throw Error(); return r.json(); });
    try {
      const data = await pending;
      if (data.schema_version !== 1 || !Array.isArray(data.cases)) throw Error();
      catalog = data; return data;
    } catch (error) { pending = null; throw error; }
  }
  const eligible = item => item.images?.length === 2 && item.images.every(i => i.path && i.date) && item.images[0].date < item.images[1].date;
  const params = item => ({site:'reference-'+item.id,marker:'comparison',dataset:item.images.map(i=>i.sha256.slice(0,16)).join('.')});
  function render() {
    $('observed-events-summary').textContent = t('Documented changes: images before and after', 'Документированные изменения: снимки до и после');
    $('observed-events-title').textContent = selected ? selected.title[ru() ? 'ru' : 'en'] : t('Documented changes', 'Документированные изменения');
    $('observed-events-note').textContent = t('Images published by NASA, not detections by OffBeat. The Hubbard example uses NISAR; NISAR coverage for the other examples has not been checked.', 'Снимки опубликованы NASA: это не находки алгоритма OffBeat. В примере ледника Хаббард использован NISAR; его покрытие для остальных примеров пока не проверено.');
    if (!catalog) return;
    const list = $('observed-events-list'); list.replaceChildren();
    (selected ? [selected] : catalog.cases).forEach(item => {
      const article = document.createElement('article'); article.className = 'observed-event';
      const title = document.createElement('h3'); title.textContent = item.title[ru() ? 'ru' : 'en'];
      const badge = document.createElement('strong'); badge.textContent = t('Documented NASA example · not an OffBeat detection', 'Документированный пример NASA · не находка OffBeat');
      const desc = document.createElement('p'); desc.textContent = item.description[ru() ? 'ru' : 'en'];
      const images = document.createElement('div'); images.className = 'observed-event__images';
      item.images.forEach((image, index) => {
        const figure = document.createElement('figure'), img = document.createElement('img'), caption = document.createElement('figcaption');
        img.src = image.path; img.loading = 'lazy'; img.decoding = 'async';
        img.alt = `${item.title[ru() ? 'ru' : 'en']} / ${image.date}`;
        img.addEventListener('error', () => { img.hidden = true; caption.textContent = `${image.date} · ${t('Image unavailable. Open the source below.', 'Снимок недоступен. Откройте источник ниже.')}`; });
        caption.textContent = `${index ? t('After', 'После') : t('Before', 'До')} / ${image.date} · ${item.credit}`;
        figure.append(img, caption); images.append(figure);
      });
      const actions = document.createElement('div'); actions.className = 'observed-event__actions';
      const source = document.createElement('a'); source.href = item.source; source.target = '_blank'; source.rel = 'noopener'; source.textContent = t('NASA source and image details', 'Источник NASA и описание снимков');
      actions.append(source);
      if (selected) {
        const review = document.createElement('div'); review.className='observed-event__actions';
        const status = document.createElement('p'); status.role='status';
        for (const [verdict,en,russian] of [['visible_change','Change visible','Изменение видно'],['no_visible_change','No visible change','Изменения нет'],['uncertain','Cannot tell / pass','Не видно / пропустить']]) {
          const b=document.createElement('button'); b.type='button'; b.className='btn'; b.dataset.referenceVerdict=verdict; b.textContent=t(en,russian);
          b.addEventListener('click',async()=>{
            review.querySelectorAll('button').forEach(n=>{n.disabled=true;});
            try { await OB.reviews.save(params(item),verdict,/NISAR GSLC/.test(item.credit)?'radar':'optical'); status.textContent=t('Saved.','Сохранено.'); }
            catch (_) { status.textContent=t('Could not save. Please try again.','Не удалось сохранить. Попробуйте ещё раз.'); }
            finally { review.querySelectorAll('button').forEach(n=>{n.disabled=false;}); }
          }); review.append(b);
        }
        const undo=document.createElement('button'); undo.type='button'; undo.className='btn';undo.textContent=t('Reset review','Сбросить оценку');
        undo.addEventListener('click',async()=>{undo.disabled=true;try{await OB.reviews.save(params(item),'clear','');status.textContent=t('Review cleared.','Оценка сброшена.')}catch(_){status.textContent=t('Could not reset review.','Не удалось сбросить оценку.')}finally{undo.disabled=false;}});review.append(undo);
        article.append(review,status);
        const next = document.createElement('button'); next.type = 'button'; next.className = 'btn'; next.dataset.reviewNext = '';
        next.textContent = t('Explore another area', 'Исследовать другой район');
        next.addEventListener('click', () => OB.evidence?.surprise());
        actions.append(next);
      }
      const limits = document.createElement('p'); limits.textContent = t('Published regional images, without a georeferenced detection point. These examples do not enter OffBeat detector review counts or accuracy estimates.', 'Опубликованные снимки региона без геопривязанной точки детектора. Эти примеры не входят в оценки находок OffBeat и расчёт точности.');
      article.prepend(badge, title, desc, images, limits); article.append(actions); list.append(article);
    });
    if (selected) {
      const all = document.createElement('button'); all.type = 'button'; all.className = 'btn'; all.textContent = t('Show all documented examples', 'Все документированные примеры');
      all.addEventListener('click', () => { selected = null; const url = new URL(location.href); url.searchParams.delete('reference'); history.replaceState(null, '', url); render(); }); list.append(all);
    }
    $('observed-events-status').textContent = '';
  }
  disclosure.addEventListener('toggle', async () => {
    if (!disclosure.open || catalog) return;
    $('observed-events-status').textContent = t('Loading images…', 'Загрузка снимков…');
    try {
      await load();
      render();
    } catch (_) { pending = null; catalog = null; $('observed-events-status').textContent = t('Images are unavailable. Please try again.', 'Снимки недоступны. Попробуйте ещё раз.'); }
  });
  async function choices() {
    try { const data=await load(); await OB.reviews.refresh(true); return data.cases.filter(item=>eligible(item)&&OB.reviews.available(params(item))).map(item => ({id: `reference:${item.id}`, region: `reference:${item.id}`, kind: 'reference', reference: item.id})); }
    catch (_) { return []; }
  }
  async function open(id, scroll = true) {
    try {
      const item = (await load()).cases.find(c => c.id === id && eligible(c)); if (!item) return false;
      OB.detected?.dismiss(); OB.evidence?.dismiss(); OB.app?.stop(); selected = item;
      render(); disclosure.open = true;
      const url = new URL(location.href); ['candidate', 'case', 'sample', 'step'].forEach(k => url.searchParams.delete(k));
      url.searchParams.set('reference', id); history.replaceState(null, '', url);
      if (scroll) disclosure.scrollIntoView({behavior:'smooth', block:'start'}); return true;
    } catch (_) { return false; }
  }
  function dismiss() {
    selected = null; disclosure.open = false;
    const url = new URL(location.href); url.searchParams.delete('reference'); history.replaceState(null, '', url);
  }
  OB.observedEvents = {choices, open, dismiss};
  const restored = new URL(location.href).searchParams.get('reference');
  if (restored) document.addEventListener('ob:ready', () => { open(restored, false); }, {once:true});
  new MutationObserver(render).observe(document.documentElement, {attributes:true, attributeFilter:['lang']});
  render();
})();

// Fixed, measured two-date candidates. A marker is not a sparse time-series pixel.
window.OB = window.OB || {};
OB.createDenseCandidates = function (map, leaflet) {
  const $ = id => document.getElementById(id);
  map.createPane('detectedCandidates'); map.getPane('detectedCandidates').style.zIndex = 620;
  const catalogPath = 'data/change-candidates/catalog-9b22c7d45ddb.json';
  const reviewEndpoint = location.hostname === 'offbeat.chern.su'
    ? 'https://offbeat-shared-reviews.glazedbream.chatgpt.site/api/v1/reviews'
    : '/api/v1/reviews';
  const cache = new Map(); let catalog = null, report = null, current = null, layer = null, serial = 0, reviews = {};
  const visualScreen = fetch('data/analysis/amazon-candidate-visual-check-2026-11-15.json').then(r=>r.ok?r.json():null).catch(()=>null);
  const polarizations = fetch('data/analysis/amazon-dense-polarizations-2026-11-15.json').then(r=>r.ok?r.json():null).catch(()=>null);
  const lang = () => document.documentElement.lang === 'ru';
  const t = (en, ru) => lang() ? ru : en;
  const words = {
    show:['Show automatic change candidates','Показать автоматически найденные точки'], browse:['Browse automatic candidates','Посмотреть найденные точки списком'], close:['Close','Закрыть'],
    warning:['Experimental radar signal difference, not a confirmed event or cause. Two-date rankings do not establish accuracy.','Экспериментальное изменение сигнала радара, а не подтверждённое событие или его причина. По двум датам нельзя оценить точность.'],
    locate:['Show on maps','Показать на картах'], terrain:['View this place in 3D','Посмотреть это место в 3D'],
    radarNote:['Black-and-white radar images show signal strength, not a photograph. The cross marks the candidate.','Чёрно-белые радарные изображения показывают силу сигнала, это не фотография. Крест отмечает выбранную точку.'],
    filters:['Image filters','Фильтры снимков'], contrast:['Contrast','Контраст'], brightness:['Brightness','Яркость'], palette:['Tint','Оттенок'],
    original:['Original','Оригинал'], warm:['Warm','Тёплый'], cool:['Cool','Холодный'], filterReset:['Reset filters','Сбросить фильтры'],
    filterNote:['Both dates use the same display filters. Tints are artificial; they do not show natural colours or add detail.','Одинаковые фильтры применяются к обеим датам. Цвета условные: они не показывают реальные цвета и не добавляют деталей.'],
    radar:['NISAR radar images and filters','Радарные снимки NISAR и фильтры'], optical:['Dated optical context','Датированные оптические снимки'],
    opticalNote:['Optical dates differ from radar dates. Clouds, shadows or masks may hide the point; visual differences do not establish the cause.','Даты оптики отличаются от радарных. Облака, тени или маски могут скрыть точку; снимки не доказывают причину изменения.'],
    review:['Your visual review','Ваша визуальная проверка'], private:['Reviews are shared when the server is available. Comments stay in this browser. Reviews are not independent validation.','Оценки общие, когда сервер доступен. Комментарии остаются в этом браузере. Оценки не заменяют независимую проверку.'],
    verdict:['Result','Результат'], unreviewed:['Not reviewed','Не проверено'], visible:['Change visible','Изменение видно'], notVisible:['No visible change','Изменения не видно'], uncertain:['Uncertain / cannot see','Не уверен / плохо видно'],
    basis:['Images reviewed','Что вы смотрели'], choose:['Choose source','Выберите источник'], opticalOnly:['Optical','Оптические снимки'], radarOnly:['Radar','Радарные снимки'], both:['Both','Оба источника'], comment:['Comment (optional)','Комментарий (необязательно)'],
    save:['Save review','Сохранить оценку'], reset:['Reset review','Сбросить оценку'], export:['Download reviews','Скачать оценки'], source:['Granules and method','Гранулы и метод'], code:['Detection code','Код сравнения'], opticalSource:['Optical sources','Источники оптики']
  };
  const localize = () => document.querySelectorAll('[data-dense]').forEach(n => { const w=words[n.dataset.dense]; if(w)n.textContent=w[lang()?1:0]; });
  const ready = fetch(catalogPath).then(r => {if(!r.ok)throw Error('catalogue');return r.json()}).then(c => {
    if(c.schema_version!==1 || !Array.isArray(c.sites))throw Error('invalid catalogue');catalog=c;return c;
  }).catch(() => null);
  async function get(site) {
    const c=await ready, entry=c?.sites.find(x=>x.id===site); if(!entry)return null;
    if(cache.has(site))return cache.get(site);
    const r=await fetch(entry.path); if(!r.ok)throw Error('candidate data unavailable'); const d=await r.json();
    if(d.site!==site || !Array.isArray(d.markers) || !Array.isArray(d.inputs) || d.inputs.length!==2)throw Error('invalid candidate data');
    cache.set(site,d);return d;
  }
  function reviewKey(d) {return 'offbeat.dense-review.v2.'+datasetKey(d);}
  function readReviews(d){try{return JSON.parse(localStorage.getItem(reviewKey(d)))||{}}catch{return {}}}
  function datasetKey(d){return [...d.inputs,...(d.optical_images||[])].map(x=>x.sha256.slice(0,16)).join('.')}
  function token(){
    const key='offbeat.review-token.v1'; let value=localStorage.getItem(key);
    if(!/^[a-f0-9]{64}$/.test(value||'')){const bytes=crypto.getRandomValues(new Uint8Array(32));value=[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('');localStorage.setItem(key,value)}
    return value;
  }
  function reviewParams(d,m){return {site:d.site,marker:m.id,dataset:datasetKey(d)}}
  function showCounts(c){$('detected-community').textContent=`${t('Community reviews','Оценки пользователей')}: ${t('change visible','изменение видно')} ${c.visible_change} · ${t('no visible change','не видно')} ${c.no_visible_change} · ${t('uncertain','не уверен')} ${c.uncertain}`}
  async function refreshCounts(){
    if(!report||!current)return;const d=report,m=current;
    $('detected-community').textContent=t('Loading community reviews…','Загружаем общие оценки…');
    try{const response=await fetch(reviewEndpoint+'?'+new URLSearchParams(reviewParams(d,m)),{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();if(report===d&&current===m)showCounts(data.counts)}
    catch(_){if(report===d&&current===m)$('detected-community').textContent=t('Shared reviews are unavailable; no review can be submitted.','Общие оценки недоступны: сервер не подключён или не отвечает. Отправка оценок невозможна.')}
  }
  async function saveShared(verdict,basis){
    const response=await fetch(reviewEndpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...reviewParams(report,current),token:token(),verdict,basis})});
    if(!response.ok)throw Error('unavailable');return response.json();
  }
  function pointCovered(image){const b=image.bounds;return b && current && current.lon>=b.w && current.lon<=b.e && current.lat>=b.s && current.lat<=b.n;}
  function clearLayer(){if(layer){map.removeLayer(layer);layer=null}}
  function mapStatus(){if(report)$('detected-map-status').textContent=`${t('Fixed pair, independent of date slider','Фиксированная пара, не зависит от ползунка дат')}: ${report.dates.join(' → ')} · ${report.markers.length}/${report.total_marker_count} ${t('candidates; not confirmed events','кандидатов; события не подтверждены')}`;}
  function drawMarkers(){
    clearLayer(); if(!report || !$('detected-visible').checked)return;
    layer=leaflet.layerGroup(report.markers.map(m => {
      const marker=leaflet.circleMarker([m.lat,m.lon],{pane:'detectedCandidates',radius:5,color:'#fff',weight:1.5,fillColor:m.direction==='below'?'#104fe0':'#d32323',fillOpacity:.95,bubblingMouseEvents:false});
      marker.bindTooltip(`${m.id} · ${m.score}`);marker.on('click',e=>{if(e.originalEvent)leaflet.DomEvent.stopPropagation(e.originalEvent);show(m.id,true)});return marker;
    })).addTo(map);
  }
  function drawList(){
    const list=$('detected-list');list.replaceChildren();if(!report)return;
    report.markers.forEach((m,i)=>{const b=document.createElement('button');b.type='button';b.className='btn';
      b.textContent=`${i+1}. ${m.direction==='below'?'↓':'↑'} ${m.id} · ${m.score}`;
      b.addEventListener('click',()=>openCandidate(report.site,m.id));list.append(b)});
  }
  function imageRow(container,images,radar){
    container.replaceChildren(); images.forEach((image,i)=>{
      const figure=document.createElement('figure'), frame=document.createElement('div'), img=document.createElement('img'), caption=document.createElement('figcaption');
      frame.className='dense-case__frame';img.src=image.path+(radar?'':`?v=${image.sha256}`);img.alt=`${radar?'NISAR GCOV':'Sentinel-2'} / ${image.date}`;
      img.addEventListener('error',()=>{frame.textContent=t('Image unavailable','Снимок недоступен')});frame.append(img);
      let x,y;if(radar){x=100*(current.col+.5)/report.grid.shape[1];y=100*(current.row+.5)/report.grid.shape[0]}
      else{const b=image.bounds;x=100*(current.lon-b.w)/(b.e-b.w);y=100*(b.n-current.lat)/(b.n-b.s)}
      if(Number.isFinite(x)&&Number.isFinite(y)&&x>=0&&x<=100&&y>=0&&y<=100){const cross=document.createElement('span');cross.className='dense-case__cross';cross.textContent='+';cross.style.left=x+'%';cross.style.top=y+'%';cross.setAttribute('aria-hidden','true');frame.append(cross)}
      caption.textContent=`${radar?'NISAR GCOV':'Sentinel-2'} / ${image.date}`; if(!radar&&image.nisar_date)caption.append(document.createTextNode(` (${t('matched radar','к радарной дате')} ${image.nisar_date})`)); if(!radar&&image.item_url){const a=document.createElement('a');a.href=image.item_url;a.target='_blank';a.rel='noopener';a.textContent=t(' source',' источник');caption.append(a)}
      figure.append(frame,caption);container.append(figure);
    });
  }
  function applyRadarFilters() {
    const contrast=$('radar-contrast').value, brightness=$('radar-brightness').value, palette=$('radar-palette').value;
    const tint=palette==='warm'?' sepia(1) saturate(1.5)':palette==='cool'?' sepia(1) saturate(1.5) hue-rotate(165deg)':'';
    $('radar-contrast-value').textContent=contrast+'%'; $('radar-brightness-value').textContent=brightness+'%';
    $('detected-radar').querySelectorAll('img').forEach(img=>{img.style.filter=`brightness(${brightness}%) contrast(${contrast}%)${tint}`});
  }
  function render(){
    localize(); if(!report || !current)return;
    $('detected-title').textContent=t('Automatic change candidate','Автоматически найденная точка');
    $('detected-summary').textContent=`${report.site_name} · ${current.id} · ${current.lat.toFixed(6)}, ${current.lon.toFixed(6)} · ${report.dates.join(' → ')} · ${t('native grid','шаг сетки')} ${Math.abs(report.grid.x_step)} m · ${t('smoothed deviation score','оценка сглаженного отклонения')} ${current.score} · HV Δ ${current.delta_db} dB`;
    imageRow($('detected-radar'),report.radar_images||[],true);const optical=report.optical_images||[];imageRow($('detected-optical'),optical.filter(pointCovered),false);
    applyRadarFilters();
    const covered=optical.filter(pointCovered).length;
    const bracket=optical.length>=2&&optical[0].date<=report.dates[0]&&optical.at(-1).date>=report.dates.at(-1);
    $('detected-optical-status').textContent=covered>=2?(bracket?t('Optical images bracket the radar pair, but their wider interval does not date or prove the change.','Оптические снимки охватывают радарную пару, но более широкий интервал не доказывает изменение и его дату.'):t('These optical dates do not bracket the radar pair; they cannot show a before/after view of the full radar interval.','Даты оптики не охватывают радарную пару целиком: они не показывают «до и после» всего радарного интервала.')):covered===1?t('Only one image covers this point; before/after comparison is unavailable.','Точку покрывает только один снимок; сравнение до и после невозможно.'):t('No dated optical image covers this point.','Точку не покрывает ни один датированный оптический снимок.');
    $('detected-source').href=catalog.sites.find(x=>x.id===report.site).path; $('detected-optical-source').href=`data/${report.site}/optical/index.json`;
    const saved=reviews[current.id]||{};$('detected-verdict').value=saved.verdict||'';$('detected-basis').value=saved.basis||'';$('detected-comment').value=saved.comment||'';
    ['detected-verdict','detected-basis'].forEach(id=>$(id).dispatchEvent(new Event('ob:select-sync')));
    const d=report,m=current,box=$('detected-visual-check');box.hidden=true;box.replaceChildren();
    if(d.site==='amazon')visualScreen.then(screen=>{if(report!==d||current!==m||!screen)return;const item=screen.items.find(x=>x.id===m.id);if(!item)return;box.replaceChildren();
      const title=document.createElement('strong');title.textContent=t('OffBeat preliminary visual check (not independent): ','Предварительный визуальный осмотр OffBeat (не независимая проверка): ');
      const a=document.createElement('a');a.href='data/analysis/amazon-candidate-visual-check-2026-11-15.json';a.target='_blank';a.rel='noopener';a.textContent=t(' Method and sources',' Метод и источники');
      box.append(title,document.createTextNode(item[lang()?'ru':'en']),a);box.hidden=false;
    });
    const pol=$('detected-polarizations');pol.hidden=true;pol.replaceChildren();
    if(d.site==='amazon')polarizations.then(audit=>{if(report!==d||current!==m||!audit||audit.source_report_sha256!==catalog.sites.find(x=>x.id==='amazon')?.sha256)return;
      const item=audit.items.find(x=>x.id===m.id);if(!item)return;pol.replaceChildren();const fmt=v=>Number.isFinite(v)?`${v>0?'+':''}${v.toFixed(2)} dB`:t('unavailable','нет данных');
      const title=document.createElement('strong');title.textContent=t('HH/HV check across the radar pair','Проверка HH/HV за радарную пару');pol.append(title);
      for(const channel of ['hh','hv']){const c=item[channel],line=document.createElement('p');line.textContent=`${channel.toUpperCase()}: ${t('cell','ячейка')} ${fmt(c.cell_delta_db)} · ${t('3×3 median','медиана 3×3')} ${fmt(c.near_3x3.median_db)} (${c.near_3x3.count}/9) · ${t('surrounding median','медиана окрестности')} ${fmt(c.surrounding_31x31_excluding_3x3.median_db)} (n=${c.surrounding_31x31_excluding_3x3.count})`;pol.append(line)}
      const note=document.createElement('p');note.textContent=t('3×3 includes the selected cell; surrounding 31×31 excludes it and its 3×3 neighbours. These are spatial context, not independent confirmations or proof of cause.','3×3 включает выбранную ячейку; окрестность 31×31 исключает её и соседей 3×3. Это пространственный контекст, не независимое подтверждение и не доказательство причины.');
      if(item.context_truncated_at_edge)note.append(document.createTextNode(t(' Context is truncated at the edge.',' Окрестность обрезана краем данных.')));
      const a=document.createElement('a');a.href='data/analysis/amazon-dense-polarizations-2026-11-15.json';a.target='_blank';a.rel='noopener';a.textContent=t('Calculation and sources','Расчёт и источники');pol.append(note,a);pol.hidden=false;
    });
  }
  function show(id,scroll){
    const item=report?.markers.find(m=>m.id===id);if(!item)return false;current=item;reviews=readReviews(report);
    OB.app?.clearForCandidate?.();OB.evidence?.dismiss?.();$('detected-panel').hidden=false;$('detected-review-status').textContent='';render();refreshCounts();
    const url=new URL(location.href);['sample','case','step','lat','lon'].forEach(k=>url.searchParams.delete(k));url.searchParams.set('site',report.site);url.searchParams.set('candidate',id);history.replaceState(null,'',url);
    if(scroll)(OB.pages?.openFor($('detected-panel')), $('detected-panel')).scrollIntoView({behavior:'smooth',block:'start'});return true;
  }
  async function setSite(id){
    const ticket=++serial;clearLayer();report=null;current=null;$('detected-panel').hidden=true;$('detected-list-panel').hidden=true;$('detected-list').replaceChildren();
    if(!id){$('detected-map-status').textContent='';return null}
    $('detected-map-status').textContent=t('Loading candidates…','Загрузка найденных точек…');
    try{const data=await get(id);if(ticket!==serial)return null;report=data;
      if(data)mapStatus();else $('detected-map-status').textContent=t('No prepared candidates','Нет подготовленных кандидатов');$('detected-list-panel').hidden=!data?.markers.length;drawList();drawMarkers();return data;
    }catch(_){if(ticket===serial)$('detected-map-status').textContent=t('Candidates unavailable','Найденные точки недоступны');return null}
  }
  async function openCandidate(site,id){
    if(!OB.app?.sites().some(s=>s.id===site))return false;
    if(OB.app.site()?.id!==site)await OB.app.loadSite(site);
    if(OB.app.site()?.id!==site)return false;
    if(report?.site!==site)await setSite(site);
    if(report?.site!==site)return false;
    $('detected-visible').checked=true;drawMarkers();const item=report.markers.find(x=>x.id===id);if(!item)return false;
    OB.app.zoomTo(item.lat,item.lon,15);return show(id,true);
  }
  async function choices(){const c=await ready;if(!c)return [];const results=await Promise.allSettled(c.sites.map(s=>get(s.id)));return results.flatMap(r=>{
    if(r.status!=='fulfilled'||!r.value)return [];
    const d=r.value;
    // The remaining prepared detection windows are urban; do not present them
    // as rural discoveries until land-cover and event context are checked.
    if(d.site!=='amazon')return [];
    return d.markers.filter(m=>new Set((d.optical_images||[]).filter(i=>{const b=i.bounds;return b&&m.lon>=b.w&&m.lon<=b.e&&m.lat>=b.s&&m.lat<=b.n}).map(i=>i.date)).size>=2)
      .map(m=>({id:`dense:${d.site}:${m.id}`,site:d.site,marker:m.id}));
  })}
  function dismiss(){ $('detected-panel').hidden=true;const u=new URL(location.href);u.searchParams.delete('candidate');history.replaceState(null,'',u); }
  function locate(terrain) {
    if (!current) return;
    OB.app.zoomTo(current.lat, current.lon, 15);
    if (terrain) {
      if ($('scene-win').hidden) $('scene-open').click();
      else (OB.pages?.openFor($('scene-win')), $('scene-win')).scrollIntoView({behavior:'smooth',block:'start'});
    } else (OB.pages?.openFor($('map-win')), $('map-win')).scrollIntoView({behavior:'smooth',block:'start'});
  }
  $('detected-locate').addEventListener('click',()=>locate(false));
  $('detected-3d').addEventListener('click',()=>locate(true));
  ['radar-contrast','radar-brightness'].forEach(id=>$(id).addEventListener('input',applyRadarFilters));
  $('radar-palette').addEventListener('change',applyRadarFilters);
  $('radar-filter-reset').addEventListener('click',()=>{
    $('radar-contrast').value='100'; $('radar-brightness').value='100'; $('radar-palette').value='none';
    $('radar-palette').dispatchEvent(new Event('ob:select-sync')); applyRadarFilters();
  });
  $('detected-visible').addEventListener('change',drawMarkers);
  $('detected-close').addEventListener('click',dismiss);
  $('detected-save').addEventListener('click',async()=>{if(!report||!current)return;const d=report,m=current,verdict=$('detected-verdict').value,basis=$('detected-basis').value,optical=report.optical_images||[];
    if(!verdict||!basis){$('detected-review-status').textContent=t('Choose a result and source.','Выберите результат и источник.');return}
    const covered=optical.filter(pointCovered).length;
    if((basis==='optical'||basis==='both')&&(!covered||(covered<2&&verdict!=='uncertain'))){$('detected-review-status').textContent=t('Two optical images do not cover this point; choose uncertain or an available source.','Два оптических снимка не покрывают эту точку: выберите «не уверен» или доступный источник.');return}
    $('detected-save').disabled=true;
    try{const result=await saveShared(verdict,basis);if(report!==d||current!==m)return;showCounts(result.counts);const next={...reviews,[m.id]:{verdict,basis,comment:$('detected-comment').value.trim(),reviewed_at:new Date().toISOString()}};try{localStorage.setItem(reviewKey(d),JSON.stringify(next));reviews=next}catch(_){}$('detected-review-status').textContent=t('Saved and shared.','Оценка сохранена и доступна другим.')}catch(_){if(report===d&&current===m)$('detected-review-status').textContent=t('Could not submit: the shared review server is unavailable.','Не удалось отправить оценку: общий сервер недоступен.')}finally{$('detected-save').disabled=false}
  });
  $('detected-clear').addEventListener('click',async()=>{if(!report||!current)return;const d=report,m=current;$('detected-clear').disabled=true;try{const result=await saveShared('clear','');if(report!==d||current!==m)return;const next={...reviews};delete next[m.id];try{localStorage.setItem(reviewKey(d),JSON.stringify(next));reviews=next}catch(_){}render();showCounts(result.counts);$('detected-review-status').textContent=t('Shared review cleared.','Общая оценка удалена.')}catch(_){if(report===d&&current===m)$('detected-review-status').textContent=t('Could not clear shared review: server unavailable.','Не удалось удалить общую оценку: сервер недоступен.')}finally{$('detected-clear').disabled=false}});
  $('detected-export').addEventListener('click',()=>{if(!report)return;const data={kind:'local_human_review_not_validation',site:report.site,dates:report.dates,inputs:report.inputs,method:report.method,markers:report.markers,reviews};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`offbeat-${report.site}-reviews.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
  new MutationObserver(()=>{localize();mapStatus();drawList();if(current)render()}).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});localize();
  return {ready,setSite,openCandidate,choices,dismiss};
};

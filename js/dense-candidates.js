// Fixed, measured two-date candidates. A marker is not a sparse time-series pixel.
window.OB = window.OB || {};
OB.createDenseCandidates = function (map, leaflet) {
  const $ = id => document.getElementById(id);
  map.createPane('detectedCandidates'); map.getPane('detectedCandidates').style.zIndex = 620;
  const catalogPath = 'data/change-candidates/catalog-d9ad08d48004.json';
  const cache = new Map(); let catalog = null, report = null, current = null, layer = null, serial = 0, reviews = {};
  const lang = () => document.documentElement.lang === 'ru';
  const t = (en, ru) => lang() ? ru : en;
  const words = {
    show:['Show automatic change candidates','Показать автоматически найденные точки'], browse:['Browse automatic candidates','Посмотреть найденные точки списком'], close:['Close','Закрыть'],
    warning:['Experimental radar signal difference, not a confirmed event or cause. Two-date rankings do not establish accuracy.','Экспериментальное изменение сигнала радара, а не подтверждённое событие или его причина. По двум датам нельзя оценить точность.'],
    radar:['NISAR radar before and after','Радарные снимки NISAR до и после'], optical:['Dated optical context','Датированные оптические снимки'],
    opticalNote:['Optical dates differ from radar dates. Clouds, shadows or masks may hide the point; visual differences do not establish the cause.','Даты оптики отличаются от радарных. Облака, тени или маски могут скрыть точку; снимки не доказывают причину изменения.'],
    review:['Your visual review','Ваша визуальная проверка'], private:['Reviews stay in this browser only; they are not shared. A review is not independent validation.','Оценки хранятся только в этом браузере и не отправляются другим людям. Оценка не является независимой валидацией.'],
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
  function reviewKey(d) {return 'offbeat.dense-review.v1.'+d.inputs.map(x=>x.sha256.slice(0,16)).join('.');}
  function readReviews(d){try{return JSON.parse(localStorage.getItem(reviewKey(d)))||{}}catch{return {}}}
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
  function render(){
    localize(); if(!report || !current)return;
    $('detected-title').textContent=t('Automatic change candidate','Автоматически найденная точка');
    $('detected-summary').textContent=`${report.site_name} · ${current.id} · ${current.lat.toFixed(6)}, ${current.lon.toFixed(6)} · ${report.dates.join(' → ')} · ${t('native grid','шаг сетки')} ${Math.abs(report.grid.x_step)} m · ${t('smoothed deviation score','оценка сглаженного отклонения')} ${current.score} · HV Δ ${current.delta_db} dB`;
    imageRow($('detected-radar'),report.radar_images||[],true);const optical=report.optical_images||[];imageRow($('detected-optical'),optical,false);
    const covered=optical.filter(pointCovered).length;
    $('detected-optical-status').textContent=covered>=2?t('Images selected for the two radar dates; optical dates and actual event timing may differ.','Снимки подобраны к двум датам радара; даты оптики и время события могут отличаться.'):covered===1?t('Only one image covers this point; before/after comparison is unavailable.','Точку покрывает только один снимок; сравнение до и после невозможно.'):t('No dated optical image covers this point.','Точку не покрывает ни один датированный оптический снимок.');
    $('detected-source').href=catalog.sites.find(x=>x.id===report.site).path; $('detected-optical-source').href=`data/${report.site}/optical/index.json`;
    const saved=reviews[current.id]||{};$('detected-verdict').value=saved.verdict||'';$('detected-basis').value=saved.basis||'';$('detected-comment').value=saved.comment||'';
    ['detected-verdict','detected-basis'].forEach(id=>$(id).dispatchEvent(new Event('ob:select-sync')));
  }
  function show(id,scroll){
    const item=report?.markers.find(m=>m.id===id);if(!item)return false;current=item;reviews=readReviews(report);
    OB.app?.clearForCandidate?.();OB.evidence?.dismiss?.();$('detected-panel').hidden=false;$('detected-review-status').textContent='';render();
    const url=new URL(location.href);['sample','case','step','lat','lon'].forEach(k=>url.searchParams.delete(k));url.searchParams.set('site',report.site);url.searchParams.set('candidate',id);history.replaceState(null,'',url);
    if(scroll)$('detected-panel').scrollIntoView({behavior:'smooth',block:'start'});return true;
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
  async function choices(){const c=await ready;if(!c)return [];const results=await Promise.allSettled(c.sites.map(s=>get(s.id)));return results.flatMap(r=>r.status==='fulfilled'&&r.value?r.value.markers.map(m=>({id:`dense:${r.value.site}:${m.id}`,site:r.value.site,marker:m.id})):[])}
  function dismiss(){ $('detected-panel').hidden=true;const u=new URL(location.href);u.searchParams.delete('candidate');history.replaceState(null,'',u); }
  $('detected-visible').addEventListener('change',drawMarkers);
  $('detected-close').addEventListener('click',dismiss);
  $('detected-save').addEventListener('click',()=>{if(!report||!current)return;const verdict=$('detected-verdict').value,basis=$('detected-basis').value,optical=report.optical_images||[];
    if(!verdict||!basis){$('detected-review-status').textContent=t('Choose a result and source.','Выберите результат и источник.');return}
    const covered=optical.filter(pointCovered).length;
    if((basis==='optical'||basis==='both')&&(!covered||(covered<2&&verdict!=='uncertain'))){$('detected-review-status').textContent=t('Two optical images do not cover this point; choose uncertain or an available source.','Два оптических снимка не покрывают эту точку: выберите «не уверен» или доступный источник.');return}
    const next={...reviews,[current.id]:{verdict,basis,comment:$('detected-comment').value.trim(),reviewed_at:new Date().toISOString()}};
    try{localStorage.setItem(reviewKey(report),JSON.stringify(next));reviews=next;$('detected-review-status').textContent=t('Saved in this browser.','Сохранено в этом браузере.')}catch(_){$('detected-review-status').textContent=t('Browser storage unavailable.','Не удалось сохранить оценку.')}
  });
  $('detected-clear').addEventListener('click',()=>{if(!report||!current)return;const next={...reviews};delete next[current.id];try{localStorage.setItem(reviewKey(report),JSON.stringify(next));reviews=next;render();$('detected-review-status').textContent=t('Review cleared.','Оценка сброшена.')}catch(_){$('detected-review-status').textContent=t('Storage unavailable.','Не удалось сбросить оценку.')}});
  $('detected-export').addEventListener('click',()=>{if(!report)return;const data={kind:'local_human_review_not_validation',site:report.site,dates:report.dates,inputs:report.inputs,method:report.method,markers:report.markers,reviews};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`offbeat-${report.site}-reviews.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
  new MutationObserver(()=>{localize();mapStatus();drawList();if(current)render()}).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});localize();
  return {ready,setSite,openCandidate,choices,dismiss};
};

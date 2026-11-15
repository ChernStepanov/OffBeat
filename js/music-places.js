// A selection of existing measured time series; no new radar observations.
window.OB = window.OB || {};
OB.musicPlaces = function(sites, limit = 18) {
  const candidates = [];
  for (const site of sites) for (const [index, pixel] of site.pixels.entries()) {
    if (![10,20,30,40,60,90,95,100].includes(pixel.cover) || ['drift','step'].includes(pixel.style)) continue;
    const channel = pixel.style === 'flood' ? 'hh' : 'hv';
    const values = pixel[channel] || [], med = pixel.peer?.[channel+'_med'] || [], sd = pixel.peer?.[channel+'_sd'] || [];
    const valid = values.filter((v,i) => Number.isFinite(v) && Number.isFinite(med[i]) && Number.isFinite(sd[i]) && sd[i] > 0);
    if (valid.length < 3) continue;
    const span = Math.max(...valid)-Math.min(...valid);
    candidates.push({site,index,pixel,channel,valid:valid.length,span});
  }
  candidates.sort((a,b)=>b.span-a.span || a.site.id.localeCompare(b.site.id) || a.index-b.index);
  const selected=[], groups=new Set();
  const spaced = c => selected.filter(s=>s.site.id===c.site.id).length < Math.max(1,Math.ceil(limit/3)) && !selected.some(s=>s.site.id===c.site.id && Math.hypot(s.pixel.lat-c.pixel.lat,(s.pixel.lon-c.pixel.lon)*Math.cos(c.pixel.lat*Math.PI/180)) < .0045);
  for (const c of candidates) {const key=c.site.id+'/'+c.pixel.cover;if(!groups.has(key)&&spaced(c)){selected.push(c);groups.add(key)}if(selected.length>=limit)return selected;}
  for (const c of candidates) {if(!selected.includes(c)&&spaced(c))selected.push(c);if(selected.length>=limit)break;}
  return selected;
};
(() => {
  const $=id=>document.getElementById(id), ru=()=>document.documentElement.lang==='ru';
  const t=(en,russian)=>ru()?russian:en;
  let choices=[],opening=false;
  function render(){
    $('music-title').textContent=t('Listen to measured places','Послушать измерения Земли');
    $('music-note').textContent=t('Choose a measured sample, then press Play the pixel in its card. Pitch follows radar values; missing measurements are silent. Land cover is from WorldCover 2021.','Выберите точку, затем нажмите «Проиграть пиксель» в её карточке. Высота звука следует измерениям радара, пропуски звучат как паузы. Класс покрова — WorldCover 2021.');
    const list=$('music-places');list.replaceChildren();
    for(const c of choices){const b=document.createElement('button');b.type='button';b.className='btn';b.disabled=opening;
      b.textContent=`${c.site.name} · ${c.pixel.id} · ${c.valid}/${c.site.dates.length} ${t('dates','дат')} · ${c.channel.toUpperCase()}`;
      b.title=`${c.pixel.lat.toFixed(5)}, ${c.pixel.lon.toFixed(5)} · ${t('historical land cover','исторический покров')}: ${OB.COVER[c.pixel.cover]?.name||c.pixel.cover}`;
      b.addEventListener('click',async()=>{if(opening)return;opening=true;render();try{OB.app.stop();OB.detected?.dismiss();OB.evidence?.dismiss();await OB.app.loadSite(c.site.id);if(OB.app.site()?.id!==c.site.id)return;await OB.app.pickCell(c.index,false);OB.app.zoomTo(c.pixel.lat,c.pixel.lon,15);$('card-win').scrollIntoView({behavior:'smooth',block:'start'});$('play').focus({preventScroll:true});$('music-status').textContent=t('Sample ready. Press Play the pixel.','Точка открыта. Нажмите «Проиграть пиксель».');}catch(_){$('music-status').textContent=t('Could not open sample. Try again.','Не удалось открыть точку. Попробуйте ещё раз.');}finally{opening=false;render()}});list.append(b);
    }
  }
  document.addEventListener('ob:ready',()=>{choices=OB.musicPlaces(OB.app.sites());render()});
  new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});render();
})();

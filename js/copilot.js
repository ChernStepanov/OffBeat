window.OB = window.OB || {};
OB.copilot = (() => {
  const $ = id => document.getElementById(id), box = $('copilot-win'), log = $('copilot-log');
  let history = [], controller = null, epoch = 0;
  const home=document.createComment('Copilot dock');box.before(home);
  const dock=()=>{const floating=box.classList.contains('copilot--float')||box.classList.contains('copilot--full');if(floating&&box.parentElement!==document.body)document.body.append(box);else if(!floating&&box.parentElement===document.body)home.after(box);};
  new MutationObserver(dock).observe(box,{attributes:true,attributeFilter:['class']});
  box.addEventListener('keydown',e=>{if(e.key==='Tab'&&(box.classList.contains('copilot--float')||box.classList.contains('copilot--full')))e.stopPropagation();});

  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  function say(text, role='assistant') { const n=document.createElement('div');n.className='copilot__message copilot__message--'+role;n.textContent=text;log.append(n);n.scrollIntoView({block:'nearest',behavior:reduced()?'auto':'smooth'});return n; }
  function reveal(node) { if(node!==box)box.classList.remove('copilot--full');const parent=node.closest('details');if(parent)parent.open=true;node.hidden=false;node.scrollIntoView({block:'start',behavior:reduced()?'auto':'smooth'});if(!reduced())node.animate([{opacity:.2,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}],{duration:350,easing:'ease-out'}); }
  function sample() { const s=OB.app.site(),p=OB.app.pixel();return {site:s?.id,sample:p?s.pixels.findIndex(x=>x.id===p.id):null}; }
  function measured() {const s=OB.app.site(),p=OB.app.pixel();if(!p)throw Error('No measured series at the selected location');return {s,p};}
  async function choose(a) {
    if(a.site){if(!OB.app.sites().some(s=>s.id===a.site))throw Error('Unknown measured site');await OB.app.loadSite(a.site);}
    if(a.sample!==undefined){const s=OB.app.site();if(!Number.isInteger(a.sample)||!s?.pixels[a.sample])throw Error('Invalid sample');await OB.app.pickCell(a.sample,false);}
  }
  function chart(a){const {s,p}=measured(),channel=a.channel||'HV',v=channel==='HH'?p.hh:p.hv;if(!['HV','HH'].includes(channel))throw Error('Unsupported measured channel');const kind=a.chart_kind||'line';if(!['line','bar','histogram'].includes(kind))throw Error('Unsupported chart');
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 640 230');svg.setAttribute('role','img');svg.setAttribute('aria-label',`${p.id} ${channel} ${kind}`);
    function draw(tag,attrs,text){const n=document.createElementNS(ns,tag);for(const[k,val]of Object.entries(attrs))n.setAttribute(k,val);if(text!==undefined)n.textContent=text;svg.append(n);}
    let series=v.map((y,i)=>({x:s.dates[i],y}));
    if(kind==='histogram'){const finite=v.filter(Number.isFinite);if(!finite.length)throw Error('No finite observations');const lo=Math.min(...finite),step=(Math.max(...finite)-lo||1)/8;series=Array.from({length:8},(_,i)=>({x:(lo+i*step).toFixed(1),y:0}));for(const n of finite)series[Math.min(7,Math.floor((n-lo)/step))].y++;}
    const vals=series.map(x=>x.y).filter(Number.isFinite);if(!vals.length)throw Error('No measurements');const lo=kind==='histogram'?0:Math.min(...vals)-1,hi=Math.max(...vals)+1;const time0=Date.parse(s.dates[0]),timeSpan=Date.parse(s.dates.at(-1))-time0;const x=i=>45+(kind==='line'&&timeSpan?(Date.parse(s.dates[i])-time0)/timeSpan:i/Math.max(1,series.length-1))*550,y=v=>180-(v-lo)/(hi-lo)*145;
    for(let i=0;i<4;i++){const val=lo+i*(hi-lo)/3;draw('line',{x1:45,x2:610,y1:y(val),y2:y(val),stroke:'#ddd'});draw('text',{x:2,y:y(val)+4,'font-size':12},val.toFixed(1));}
    let path='',connected=false;series.forEach((d,i)=>{if(!Number.isFinite(d.y)){connected=false;return;}if(kind==='line'){path+=`${connected?'L':'M'}${x(i)} ${y(d.y)} `;connected=true;draw('circle',{cx:x(i),cy:y(d.y),r:3,fill:'#008080'});}else draw('rect',{x:45+i*550/series.length,y:y(d.y),width:Math.max(2,550/series.length-3),height:180-y(d.y),fill:'#008080'});});if(kind==='line')draw('path',{d:path,fill:'none',stroke:'#000080','stroke-width':2});
    draw('text',{x:45,y:210,'font-size':12},series[0].x);draw('text',{x:510,y:210,'font-size':12},series.at(-1).x);
    const figure=document.createElement('figure'),caption=document.createElement('figcaption');caption.textContent=(a.title||`${p.id} / ${channel}`)+` · ${kind==='histogram'?'count':'dB'} · ${s.dates[0]} — ${s.dates.at(-1)} · NASA NISAR`;figure.append(caption,svg);log.append(figure);
    return {sample:p.id,dates:s.dates,values:v,units:kind==='histogram'?'count':'dB',source:s.source};
  }
  async function execute(a, cancelled=()=>false){
    if(cancelled())throw Error("Cancelled");
    if(!a||!['place','site','inspect','window','settings','chart','play'].includes(a.action))throw Error('Unsupported action');
    if(a.action==='place'){
      if(typeof a.query!=='string'||!a.query.trim()||a.query.length>200)throw Error('Place query required');
      let place=OB.parseCoordinates(a.query);if(place.kind==='invalid')throw Error('Invalid coordinates');
      if(place.kind==='place'){const results=await OB.geocodePlace(a.query,'https://photon.komoot.io/api/');if(!results.length)throw Error('Place not found');const f=results[0];place={lat:f.geometry.coordinates[1],lon:f.geometry.coordinates[0],name:f.properties.name};}
      if(cancelled())throw Error('Cancelled');if(a.zoom!==undefined&&(!Number.isInteger(a.zoom)||a.zoom<0||a.zoom>19))throw Error('Invalid zoom');const previous=OB.app.viewport();await OB.app.visitPlace(place);if(cancelled())throw Error('Cancelled');const target=OB.app.viewport();OB.app.zoomTo(previous.lat,previous.lon,previous.zoom);OB.app.flyTo(target.lat,target.lon,a.zoom??target.zoom);reveal($('map-win'));return {place,measurement_available:!!OB.app.pixel(),zoom:a.zoom??target.zoom};
    }
    if(a.action==='window'){
      const ids={map:'map-win',terrain:'scene-win',evidence:'evidence-win',review:'review-win',charts:'card-win',chat:'copilot-win'};const id=ids[a.window];if(!id)throw Error('Unknown window');const node=$(id);if(!node)throw Error('Window unavailable');if(a.window!=='chat'&&a.mode!=='close'){const active=OB.windows.active();if(active&&active!==node&&!node.contains(active))await OB.windows.restore();if(a.window!=='map'&&$('map-max').getAttribute('aria-pressed')==='true')$('map-max').click();}
      if(a.window==='chat'){if(a.mode==='close')throw Error('Restore chat instead of closing it');reveal(box);box.classList.toggle('copilot--full',a.mode==='maximize');$('copilot-full').setAttribute('aria-pressed',String(a.mode==='maximize'));return {window:a.window,mode:a.mode};}
      if(a.window==='terrain'&&node.hidden&&a.mode!=='close')$('scene-open').click();
      if(a.mode==='close'){if(a.window==='terrain'&&OB.windows.active()?.id==='terrain-win')await OB.windows.restore();if(a.window==='terrain'&&!node.hidden)$('scene-close').click();else if(node.closest('details'))node.closest('details').open=false;else throw Error('This panel cannot be closed');}
      else if(a.mode==='maximize'){reveal(node);box.classList.add('copilot--float');const b=a.window==='map'?$('map-max'):node.querySelector('[data-window-action="max"]');if(b&&b.getAttribute('aria-pressed')!=='true')b.click();else if(!b)throw Error('Maximize not available for this panel');}
      else if(a.mode==='restore'){if(a.window==='map'&&$('map-max').getAttribute('aria-pressed')==='true')$('map-max').click();else await OB.windows.restore();}
      else reveal(node);return {window:a.window,mode:a.mode||'open'};
    }
    const before=OB.app.viewport();await choose(a);if(cancelled())throw Error("Cancelled");
    if(a.action==='site'){const {s,p}=measured();OB.app.zoomTo(before.lat,before.lon,before.zoom);OB.app.flyTo(p.lat,p.lon,14);reveal($('map-win'));return {site:s.id,source:s.source,dates:s.dates};}
    if(a.action==='inspect'){const {s,p}=measured();return {site:s.id,sample:p,dates:s.dates,source:s.source,top_samples:s.pixels.map((p,i)=>({index:i,id:p.id,z:p.z})).filter(p=>Number.isFinite(p.z)).sort((a,b)=>Math.abs(b.z)-Math.abs(a.z)).slice(0,5)};}
    if(a.action==='settings'){
      if(a.threshold!==undefined){if(!Number.isFinite(a.threshold)||a.threshold<1.5||a.threshold>6)throw Error('Threshold must be 1.5–6');OB.app.setZ(a.threshold);}
      if(a.date){const i=OB.app.site().dates.indexOf(a.date);if(i<0)throw Error('No measurement on that date');OB.app.selectDate(i);}
      if(a.offbeat!==undefined||a.cover!==undefined)OB.app.setLayers({offbeat:a.offbeat??$('l-offbeat').checked,cover:a.cover??$('l-cover').checked});
      if(a.channel){if(!['HH','HV'].includes(a.channel))throw Error('Invalid channel');const b=$(a.channel==='HH'?'cloud-hh':'cloud-hv');if(b)b.click();}
      return {selected_date:OB.app.site().dates[OB.app.date()],threshold:$('z').value};
    }
    if(a.action==='chart')return chart(a);
    if(a.action==='play'){measured();OB.app.play();return {playing:true};}
  }
  async function send(text){if(controller||!OB.app)return;const token=++epoch;controller=new AbortController();$('copilot-send').disabled=true;$('copilot-stop').disabled=false;history=history.slice(-16);while(history[0]?.role==='tool'||history[0]?.role==='assistant')history.shift();history.push({role:'user',content:text});say(text,'user');$('copilot-input').value='';
    let actions=0;try{for(let turn=0;turn<7;turn++){
      $('copilot-state').textContent='gpt-oss-20b · работает…';
      const r=await fetch('/api/v1/copilot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:history,context:sample()}),signal:controller.signal});const d=await r.json();if(!r.ok)throw Error(typeof d.error==='string'?d.error:'Chat server unavailable');if(token!==epoch)return;
      const m=d.message;history.push(m);if(m.content)say(m.content);if(!m.tool_calls?.length)return;
      for(const call of m.tool_calls){if(token!==epoch)return;let result;try{if(turn>=6||++actions>6)throw Error('Action limit reached');if(call.function.name!=='workspace')throw Error('Unsupported tool');const a=JSON.parse(call.function.arguments);$('copilot-state').textContent='Действие: '+a.action;result=await execute(a,()=>token!==epoch);say('✓ '+a.action,'tool');}catch(e){result={error:e.message};say('Не выполнено: '+e.message,'tool');}history.push({role:'tool',tool_call_id:call.id,content:JSON.stringify(result)});}
    }say('Лимит действий достигнут. Уточните следующий шаг.');
    }catch(e){say(e.name==='AbortError'?'Остановлено.':'Ошибка: '+e.message,'error');history=[];}finally{controller=null;$('copilot-send').disabled=false;$('copilot-stop').disabled=true;$('copilot-state').textContent='Groq / openai/gpt-oss-20b';}}
  $('copilot-form').addEventListener('submit',e=>{e.preventDefault();const q=$('copilot-input').value.trim();if(q)send(q);});
  $('copilot-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('copilot-form').requestSubmit();}});
  $('copilot-stop').addEventListener('click',()=>{epoch++;controller?.abort();OB.app?.stop();});
  $('copilot-full').addEventListener('click',()=>{box.classList.toggle('copilot--full');$('copilot-full').setAttribute('aria-pressed',String(box.classList.contains('copilot--full')));});
  $('copilot-float').addEventListener('click',()=>box.classList.toggle('copilot--float'));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){box.classList.remove('copilot--full');$('copilot-full').setAttribute('aria-pressed','false');}});
  document.querySelectorAll('[data-copilot-prompt]').forEach(b=>b.addEventListener('click',()=>send(b.dataset.copilotPrompt)));
  let drag=null;box.querySelector('.win-t').addEventListener('pointerdown',e=>{if(!box.classList.contains('copilot--float')||box.classList.contains('copilot--full')||e.target.closest('button'))return;const r=box.getBoundingClientRect();drag={x:e.clientX-r.left,y:e.clientY-r.top};e.currentTarget.setPointerCapture(e.pointerId);});
  box.querySelector('.win-t').addEventListener('pointermove',e=>{if(!drag)return;box.style.left=Math.max(0,Math.min(innerWidth-box.offsetWidth,e.clientX-drag.x))+'px';box.style.top=Math.max(0,Math.min(innerHeight-box.offsetHeight-32,e.clientY-drag.y))+'px';box.style.right='auto';box.style.bottom='auto';});box.querySelector('.win-t').addEventListener('pointerup',()=>drag=null);box.querySelector('.win-t').addEventListener('pointercancel',()=>drag=null);
  if(OB.app)$('copilot-send').disabled=false;else document.addEventListener('ob:ready',()=>{$('copilot-send').disabled=false;},{once:true});
  return {execute,send};
})();

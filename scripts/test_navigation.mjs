import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
  constructor(id='') { this.id=id; this.children=[]; this.listeners={}; this.attrs={}; this.dataset={}; this.checked=false; this.value=''; this.hidden=false; this.tBodies=[{innerHTML:''}]; }
  addEventListener(name,fn) { this.listeners[name]=fn; }
  setAttribute(name,value) { this.attrs[name]=value; }
  getAttribute(name) { return this.attrs[name]; }
  replaceChildren() { this.children=[]; }
  appendChild(node) { this.children.push(node); }
  insertAdjacentHTML() {}
  closest() { return this; }
  scrollIntoView() {}
  getContext() { return {clearRect(){}}; }
}
const elements={};
const $=id=>elements[id] ||= new Element(id);
const sites=['mexico','amazon','venezuela'].map(id=>JSON.parse(fs.readFileSync(`data/${id}.json`)));
const siteButtons=sites.map(s=>Object.assign(new Element(),{dataset:{site:s.id}}));
const regionButtons=['world','europe','africa','asia','oceania','americas'].map(region=>Object.assign(new Element(),{dataset:{region}}));
const listeners={};
const document={getElementById:$,createElement:()=>new Element(),createTextNode:text=>({textContent:text}),
  querySelectorAll:selector=>selector==='#sites button'?siteButtons:selector==='#regions button'?regionButtons:[],
  addEventListener:(name,fn)=>(listeners[name] ||= []).push(fn),dispatchEvent:event=>(listeners[event.type]||[]).forEach(fn=>fn(event))};
const vector=(x=0,y=0)=>({x,y,add(v){return vector(x+(v.x??v[0]),y+(v.y??v[1]));},subtract(v){return vector(x-(v.x??v[0]),y-(v.y??v[1]));},divideBy(n){return vector(x/n,y/n);}});
const maps=[];
function newMap() {
  const handlers={},panes={};const map={handlers,attributionControl:{setPrefix(){}},on(names,fn){for(const name of names.split(' '))handlers[name]=fn;return map;},
    createPane:name=>panes[name]={style:{}},getPane:name=>panes[name],getCenter:()=>({lat:0,lng:0,wrap(){return this;}}),getZoom:()=>12,
    setView(){return map;},fitBounds(){return map;},getSize:()=>vector(400,360),distance:()=>10,
    containerPointToLatLng:()=>({lat:0,lng:0}),project:p=>vector(p.lng??p[1],p.lat??p[0]),unproject:p=>({lat:p.y,lng:p.x,wrap(){return this;}}),
    hasLayer:()=>false,removeLayer(){},getBounds:()=>({})};maps.push(map);return map;
}
const layer=()=>({addTo(){return this;},setBounds(){return this;},setLatLng(){return this;},setContent(){return this;},bringToFront(){},bindTooltip(){return this;},on(){return this;}});
const tileLayers=[], imageLayers=[];
let href='http://localhost/?site=mexico';
const location={get href(){return href;},get hash(){return new URL(href).hash;}};
const opticalLoads=[];let holdMexico=null; let radarBinding=null; const imagery=[];
const context={URL,AbortSignal,Event,console,document,location,history:{replaceState(_a,_b,url){href=new URL(url,href).href;}},
  localStorage:{getItem:()=>null,setItem(){}},addEventListener(){},
  fetch:async path=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(path))}),
  L:{map:newMap,tileLayer:(url,options)=>{tileLayers.push({url,options});return layer();},imageOverlay:(url,bounds,options)=>{imageLayers.push({url,bounds,options});return layer();},rectangle:layer,tooltip:layer,circleMarker:layer,layerGroup:layer,geoJSON:layer,point:vector,marker:layer,divIcon:()=>({}),featureGroup:layer},
};context.window=context;vm.createContext(context);
for(const file of ['styles','search','data','acquisitions','amazon-ranking','suggestions'])vm.runInContext(fs.readFileSync(`js/${file}.js`,'utf8'),context);
const OB=context.OB;
Object.assign(OB,{tourWanted:true,bindArchive(){},bindNisarMap:(map,toggle,status)=>{radarBinding={map,toggle,status};return ()=>null;},bindWaterLabels:()=>()=>{},
  bindImagery:(map,url,options)=>{const entry={map,url,options,setUrl(next){this.url=next;}};imagery.push(entry);return entry;},
  bindOptical:()=>({load(s){opticalLoads.push(s.id);return s.id==='mexico'&&holdMexico?holdMexico:Promise.resolve();},setDate(){},context(){}}),
  chart:{backscatter(){},displacement(){},cband(){},opera(){},gnss(){},empty(){}},sonify:{stop(){},play(){}}});
vm.runInContext(fs.readFileSync('js/app.js','utf8'),context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
await tick();await tick();assert(OB.app);
assert.equal(radarBinding.map,maps[0],'NASA coverage must be bound to the left map');
assert.equal(radarBinding.toggle,$('l-nisar'));
assert.equal(radarBinding.status,$('nisar-status'));
for (const {options} of tileLayers) {
  assert.equal(options.maxNativeZoom,16,'High zoom must enlarge available tiles instead of requesting Esri placeholders');
  assert.equal(options.maxZoom,19,'Both maps must remain zoomable');
}
assert.equal(tileLayers.length,2);
assert.equal(imagery.length,2);
assert.equal(imagery[0].url,imagery[1].url,'Both maps must use the same imagery');
assert.match(imagery[0].url,/clarity\.maptiles/,'Sharper archival imagery is selected by default');
$('imagery-clarity').listeners.click();
assert.equal(imagery[0].url,imagery[1].url,'Switching imagery must affect both maps');
assert.match(imagery[0].url,/services\.arcgisonline/);
assert.equal($('imagery-clarity').getAttribute('aria-pressed'),'false');
assert.match(imagery[0].options.className,/grayscale/);
assert.doesNotMatch(imagery[1].options.className,/grayscale/);
await OB.app.loadSite('mexico');
const clicks=(id,button)=>$(id).listeners.click({target:button});
clicks('regions',regionButtons[0]);await tick();
assert.equal(OB.app.pixel(),null);
assert.equal($('card-content').hidden,true,'Нет пустых графиков вне участка');
assert.equal($('card-empty').hidden,false);
assert.equal($('card-empty-sites').hidden,false);
assert.equal(regionButtons[0].getAttribute('aria-pressed'),'true');
const loadsBefore=opticalLoads.length;
await OB.app.loadSite('mexico');
assert.equal(opticalLoads.length,loadsBefore+1,'Тур должен восстановить оптику после World');
assert(OB.app.pixel());assert(regionButtons.every(b=>b.getAttribute('aria-pressed')==='false'));
assert.equal($('card-content').hidden,false,'Карточка с данными возвращается при выборе участка');
assert.equal($('card-empty').hidden,true);

// Запоздалые результаты поиска не возвращаются после перехода в регион.
let completeSearch;
OB.geocodePlace=()=>new Promise(resolve=>completeSearch=resolve);
$('place-query').value='Москва';
const search=$('place-search').listeners.submit({preventDefault(){}});
clicks('regions',regionButtons[0]);await tick();
completeSearch([{geometry:{coordinates:[37.6,55.7]},properties:{name:'Москва'}}]);await search;
assert.equal($('place-results').children.length,0);
assert.equal($('place-submit').disabled,false);

// Старый координатный поиск ждёт оптику Мехико, пользователь уже выбрал Амазонию.
let release;
holdMexico=new Promise(resolve=>release=resolve);
$('place-query').value='19.43, -99.08';
const coordinates=$('place-search').listeners.submit({preventDefault(){}});
await tick();clicks('sites',siteButtons[1]);await tick();
release();await coordinates;await tick();
assert.equal(OB.app.site().id,'amazon');
assert(OB.app.pixel().id.startsWith('AMA'));
assert(!$('place-status').textContent.includes('Inside Mexico'));
assert(!new URL(href).searchParams.has('lat'));
$('site-layer-list').listeners.change({target:{dataset:{layer:'dense_z'},checked:true}});
assert.equal(imageLayers.length,1);
assert(imageLayers[0].url.startsWith('data/amazon/dense-peer-z.png?v='));
assert.equal($('legend').hidden,false);

// Переход в World отменяет незавершённую загрузку участка.
holdMexico=new Promise(resolve=>release=resolve);
const pendingSite=OB.app.loadSite('mexico');
await tick();clicks('regions',regionButtons[0]);await tick();
release();await pendingSite;await tick();
assert.equal(OB.app.pixel(),null);
assert.equal($('site-name').textContent,'World');
assert.equal(regionButtons[0].getAttribute('aria-pressed'),'true');

console.log('PASS: restart tour after world, region selection, stale geocoding and stale coordinates');

for (const m of maps) {
  m.handlers.click({latlng:{lat:48.8566,lng:2.3522,wrap(){return this;}}});
  assert.equal($('p-loc').textContent,'48.856600, 2.352200');
  assert.equal($('px-id').textContent,'No prepared measurement series here');
}
console.log('PASS: coordinates outside measured coverage on both maps');

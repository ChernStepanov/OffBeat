import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const elements={},listeners={};
const $=id=>elements[id] ||= {hidden:false,disabled:false,addEventListener(name,fn){this[name]=fn;},click(){return this.clickHandler?.();},scrollIntoView(){}};
let href='http://localhost/?site=amazon&lat=10&lon=0#tour/1';
const sites=['mexico','amazon','venezuela'].map(id=>JSON.parse(fs.readFileSync(`data/${id}.json`)));
for(const s of sites){s.grid.style=s.pixels.map(p=>p.style==='drop'?1:0);s.grid.z=s.pixels.map(p=>p.z);}
let site=sites[0],pixel=site.pixels[0];
const context={URL,console,location:{get href(){return href;},get hash(){return new URL(href).hash;}},
  history:{replaceState(_a,_b,url){href=new URL(url,href).href;}},
  document:{getElementById:$,addEventListener:(name,fn)=>(listeners[name] ||= []).push(fn)},
  OB:{STYLE_KEYS:[null,'drop'],app:{sites:()=>sites,site:()=>site,pixel:()=>pixel,patches:()=>[],
    async loadSite(id){site=sites.find(s=>s.id===id);},async pickCell(i){pixel=site.pixels[i];},stop(){},setLayers(){},setZ(){},fit(){},zoomTo(){}}}};
context.window=context;
// Различаем регистрацию обработчика и нажатие, как в DOM.
for(const id of ['tour-next','tour-back','tour-close','tour-open','tour-play']){
  $(id).addEventListener=function(name,fn){this[name+'Handler']=fn;};
}
vm.runInNewContext(fs.readFileSync('js/story.js','utf8'),context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));await tick();
assert.equal(new URL(href).searchParams.has('lat'),false);
assert.equal(new URL(href).searchParams.get('site'),'mexico');
const key=listeners.keydown[0];
key({key:'ArrowRight',target:{closest:()=>({})}});await tick();
assert.equal(new URL(href).hash,'#tour/1','Стрелки селектора не должны двигать тур');
key({key:'ArrowRight',target:{closest:()=>null}});await tick();
assert.equal(new URL(href).hash,'#tour/2');
for(let i=2;i<8;i++){await $('tour-next').click();await tick();assert(!$('tour-text').innerHTML.includes('could not load'));}
assert.equal($('tour-count').textContent,'Step 8 of 8');
await $('tour-next').click();assert($('tour-win').hidden);
assert.equal(new URL(href).hash,'');
console.log('PASS: tour input keys, URL cleanup, eight chapters and finish');

import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
  constructor() { this.value = ''; this.children = []; this.listeners = {}; }
  replaceChildren() { this.children = []; }
  appendChild(child) { this.children.push(child); }
  addEventListener(event, callback) { this.listeners[event] = callback; }
}
const elements = Object.fromEntries(['optical-date','optical-caption','optical-detail'].map(k => [k,new Element()]));
const overlays = [], removed = [], panes = {};
let fetcher;
const context = {
  AbortSignal,
  document: {getElementById: id => elements[id], createElement: () => new Element()},
  fetch: (...args) => fetcher(...args),
  L: {imageOverlay: (url,bounds,options) => {
    const overlay = {url,bounds,options,listeners:{},on(event,fn) { this.listeners[event]=fn; return this; },addTo() { return this; }};
    overlays.push(overlay); return overlay;
  }},
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('js/optical.js','utf8'),context);
const map = {createPane: name => panes[name] = {style:{}}, getPane: name => panes[name], removeLayer: layer => removed.push(layer)};
const read = path => JSON.parse(fs.readFileSync(path,'utf8'));
const sites = ['mexico','amazon','venezuela'].map(name => read(`data/${name}.json`));
const indexes = sites.map(site => read(`data/${site.id}/optical/index.json`));
for (let i=0;i<sites.length;i++) {
  const scenes = context.OB.opticalScenes(indexes[i], sites[i]);
  assert(scenes.length>1);
  assert(scenes.every(scene => fs.existsSync(`data/${sites[i].id}/optical/${scene.render.file}`)));
  assert.equal(context.OB.nearestOpticalScene(scenes,scenes[0].date).scene_id,scenes[0].scene_id);
}
const malformed = structuredClone(indexes[0]);
malformed.entries.forEach(row => row.scene.render.file = '../outside.png');
assert.equal(context.OB.opticalScenes(malformed,sites[0]).length,0);
malformed.bbox = [0,0,1,1];
assert.equal(context.OB.opticalScenes(malformed,sites[0]).length,0);

fetcher = async url => ({ok:true,json:async () => read(url)});
const view = context.OB.createOpticalView(map);
await view.loadSite(sites[0]);
assert.equal(elements['optical-date'].value,'auto');
assert(overlays.at(-1).url.includes('/mexico/'));
overlays.at(-1).listeners.load();
assert(elements['optical-caption'].textContent.startsWith('Sentinel-2'));
view.pickPixel({since: context.OB.opticalScenes(indexes[0],sites[0])[0].date});
const firstImage = overlays.at(-1);
assert(firstImage.url.includes(context.OB.opticalScenes(indexes[0],sites[0])[0].render.file));
elements['optical-date'].value='context'; elements['optical-date'].listeners.change();
assert(removed.includes(firstImage));
assert(elements['optical-caption'].textContent.includes('Esri'));
elements['optical-date'].value='auto'; elements['optical-date'].listeners.change();
overlays.at(-1).listeners.error();
assert.equal(elements['optical-date'].value,'context');
assert(elements['optical-detail'].textContent.includes('failed to load'));

// Старый ответ каталога и старое событие загрузки не должны менять новый участок.
let resolveAmazon;
fetcher = url => url.includes('amazon') ? new Promise(resolve => resolveAmazon=resolve) : Promise.resolve({ok:true,json:async () => indexes[2]});
const pending = view.loadSite(sites[1]);
await view.loadSite(sites[2]);
const current = overlays.at(-1);
resolveAmazon({ok:true,json:async () => indexes[1]});
await pending;
assert.equal(overlays.at(-1),current);
assert(current.url.includes('/venezuela/'));
view.clear(); current.listeners.load();
assert.equal(elements['optical-date'].disabled,true);
assert(elements['optical-caption'].textContent.includes('Esri'));

fetcher = async () => ({ok:false});
const unavailableView = context.OB.createOpticalView(map);
await unavailableView.loadSite(sites[0]);
assert(elements['optical-detail'].textContent.includes('No prepared'));
assert.equal(elements['optical-date'].disabled,true);
console.log('PASS: optical dates, files, nearest scene, context, failures and stale responses');

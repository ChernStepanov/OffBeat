import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const c={window:{}};c.window=c;vm.createContext(c);
vm.runInContext(fs.readFileSync('js/music-places.js','utf8').split('(() => {')[0],c);
const sites=['mexico','amazon','venezuela','delhi','tokyo','nairobi','sydney'].map(id=>JSON.parse(fs.readFileSync(`data/${id}.json`)));
const selected=c.OB.musicPlaces(sites);
assert(selected.length>=12 && selected.length<=18);
assert.equal(new Set(selected.map(x=>`${x.site.id}/${x.index}`)).size,selected.length);
for(const item of selected){
  assert(item.valid>=3);assert.strictEqual(item.pixel,item.site.pixels[item.index]);
  assert.equal(item.valid,item.pixel[item.channel].filter((v,i)=>Number.isFinite(v)&&Number.isFinite(item.pixel.peer[item.channel+'_med'][i])&&Number.isFinite(item.pixel.peer[item.channel+'_sd'][i])&&item.pixel.peer[item.channel+'_sd'][i]>0).length);
  assert(selected.filter(x=>x.site.id===item.site.id).length<=6);
}
assert.equal(c.OB.musicPlaces([{id:'missing',dates:['a'],pixels:[{cover:10,hv:[null],peer:{}}]}]).length,0);
console.log(`PASS: ${selected.length} existing playable samples, three measured dates minimum, valid peer spread and site diversity`);

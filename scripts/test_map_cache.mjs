import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const entries=new Map(), handlers={}; let network=0, directive='public, max-age=3600', fail=false;
const cache={async match(k){return entries.get(k)?.clone();}, async put(k,v){entries.set(k,v.clone());}, async keys(){return [...entries.keys()];}, async delete(k){entries.delete(k);}};
const context={URL,Headers,Response,Date,console,caches:{open:async()=>cache},self:{addEventListener:(name,fn)=>handlers[name]=fn,skipWaiting(){},clients:{claim(){}}},fetch:async()=>{network++;if(fail)throw Error('offline');return new Response('tile',{headers:{'cache-control':directive,'content-type':'image/png'}});}};
vm.createContext(context);vm.runInContext(fs.readFileSync('map-cache-worker.js','utf8'),context);
const request=new Request('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/5/12/8');
async function send(req=request){let result;handlers.fetch({request:req,respondWith(p){result=p;}});return result?await result:null;}
assert.equal(await (await send()).text(),'tile');assert.equal(network,1);
assert.equal(await (await send()).text(),'tile');assert.equal(network,1,'repeat view must use cached tile');
const saved=entries.get(request.url);const h=new Headers(saved.headers);h.set('x-offbeat-expires','1');entries.set(request.url,new Response('old',{headers:h}));
assert.equal(await (await send()).text(),'tile');assert.equal(network,2,'expired tile must refresh');
entries.delete(request.url);directive='no-store, max-age=3600';await send();assert.equal(entries.size,0,'no-store must not be cached');
assert.equal(await send(new Request('https://example.org/tile/5/12/8')),null,'unrelated requests must not be intercepted');
entries.delete(request.url);directive='max-age=3600';const before=network;
await Promise.all([send(),send()]);assert.equal(network,before+1,'matching concurrent requests share one download');
console.log('PASS: map tile reuse, expiration, no-store and origin restriction');

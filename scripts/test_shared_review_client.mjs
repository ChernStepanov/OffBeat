import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const p={site:'amazon',marker:'test-cell',dataset:'source-image-pair'};
const votes=new Map(),sent=[];
function item(){
  const counts={visible_change:0,no_visible_change:0,uncertain:0};
  for(const v of votes.values())counts[v]++;
  return {...p,lat:-4.7,lon:-49.2,counts,status:counts.no_visible_change?'rejected':counts.visible_change?'visible':'pending'};
}
async function fetch(url,options={}){
  if(options.method==='POST'){
    const body=JSON.parse(options.body);sent.push(body);
    if(body.verdict==='clear')votes.delete(body.token);else votes.set(body.token,body.verdict);
    return Response.json(item());
  }
  return Response.json(url.includes('review-queue')?{items:[item()]}:item());
}
function browser(){
  const storage=new Map(),context={window:{OB:{}},location:{hostname:'offbeat.chern.su'},crypto:webcrypto,fetch,Response,URLSearchParams,Event,setInterval:()=>0,document:{hidden:false,dispatchEvent(){},addEventListener(){}},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}};
  context.OB=context.window.OB;vm.runInNewContext(fs.readFileSync('js/reviews.js','utf8'),context);
  return context.OB.reviews;
}
const a=browser(),b=browser();await Promise.all([a.refresh(),b.refresh()]);
await a.save(p,'uncertain','radar');await b.refresh(true);
assert.equal(a.available(p),false,'the sender must not get their own skipped card again');
assert.equal(b.available(p),true,'another person can review an uncertain card');
await a.save(p,'no_visible_change','radar');await b.refresh(true);assert.equal(b.available(p),false);
await a.save(p,'clear','');await b.refresh(true);assert.equal(b.available(p),true);
await a.save(p,'visible_change','radar');await b.refresh(true);
assert.equal(a.available(p),false);assert.equal(b.entry(p).status,'visible');assert.equal(b.available(p),true);
assert.equal(b.all()[0].lat,-4.7,'map coordinates survive updates');
await b.save(p,'no_visible_change','radar');await a.refresh(true);assert.equal(a.entry(p).status,'rejected');
assert.notEqual(sent[0].token,sent.at(-1).token,'different browsers use different anonymous tokens');
assert(sent.every(body=>!('comment' in body)));
console.log('PASS: two-browser skip handoff, shared rejection, undo, accepted map coordinates, no repeated own cards and no comments');

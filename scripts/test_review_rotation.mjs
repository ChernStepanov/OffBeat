import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context={window:{OB:{}}}; context.OB=context.window.OB;
vm.runInNewContext(fs.readFileSync('js/evidence-model.js','utf8'),context);
const next=context.OB.evidenceModel.nextInvestigation;
const refs=JSON.parse(fs.readFileSync('data/observed-events/index.json')).cases;
const cat=JSON.parse(fs.readFileSync('data/change-candidates/catalog-9b22c7d45ddb.json'));
const amazon=JSON.parse(fs.readFileSync(cat.sites.find(s=>s.id==='amazon').path));
const choices=[...amazon.markers.map(m=>({id:'dense:amazon:'+m.id,region:'amazon'})),...refs.map(c=>({id:'reference:'+c.id,region:c.id}))];
let state={},current=null;
const amazonShown=new Set();
for(let round=0;round<10;round++){
  const areas=new Set();
  for(let i=0;i<8;i++){
    const picked=next(choices,state,current,()=>0);
    const item=choices.find(c=>c.id===picked.id),before=choices.find(c=>c.id===current);
    assert.notEqual(item.region,before?.region,'do not revisit a neighbouring cell on the next click');
    assert(!areas.has(item.region),'every area must appear before its next round');
    areas.add(item.region);state=JSON.parse(JSON.stringify(picked.state));current=item.id;
    if(round<5&&item.region==='amazon') {assert(!amazonShown.has(item.id));amazonShown.add(item.id);}
  }
  assert.equal(areas.size,8);
}
assert.equal(amazonShown.size,5,'rotate individual Amazon cells across area rounds');
assert.equal(next([],{},null),null);
assert.equal(next([{id:'one',region:'one'}],{history:['stale'],regions:['stale']},null).id,'one');
const afterRemoval=next(choices.filter(c=>c.region!=='amazon'),state,current,()=>0);
assert(!afterRemoval.state.regions.includes('amazon'),'removed areas must not survive in the rotation');
const direct='dense:amazon:'+amazon.markers[0].id;
assert.notEqual(next(choices,{},direct,()=>0).id,direct,'respect the actual URL selection, not the last story');
console.log('PASS: 80 visits across 8 areas, no consecutive neighbouring cells, per-area history, reloads and removed cards');

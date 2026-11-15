import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';

const site = JSON.parse(fs.readFileSync('data/mexico.json', 'utf8'));
const manifest = JSON.parse(fs.readFileSync('data/mexico-manifest.json', 'utf8'));
assert.equal(manifest.products.gcov.length,29);
assert.equal(manifest.products.gunw.length,28);
assert(manifest.products.gcov.every(g=>g.id.includes('_019_A_011_4005_DHDH_')));
assert(manifest.products.gunw.every(g=>g.id.includes('_019_A_011_')));
const context = {window:{}, fetch:async path=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(path,'utf8'))})};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('js/data.js','utf8'), context);
await context.OB.loadData();
assert.equal(context.OB.SITES[0].series(0,0).hh.length,site.dates.length);
assert.deepEqual(Array.from(context.OB.SITES, s=>s.id),['mexico','amazon','venezuela','delhi','tokyo','khimki','nairobi','sydney']);
for (const loaded of context.OB.SITES) {
  assert(!/synthetic|mock/i.test(loaded.source));
  assert.equal(loaded.provenance.inputs.length,3);
  assert(loaded.pixels.some(p=>p.hh.some(Number.isFinite)&&p.hv.some(Number.isFinite)));
  for (const receipt of [...loaded.provenance.inputs,loaded.provenance.worldcover]) {
    assert.equal(createHash('sha256').update(fs.readFileSync(receipt.subset_path)).digest('hex'),receipt.sha256);
  }
  for (const receipt of loaded.provenance.additional_gcov || []) {
    assert.equal(createHash('sha256').update(fs.readFileSync(receipt.subset_path)).digest('hex'),receipt.sha256);
    assert(loaded.dates.includes(receipt.date));
  }
  assert(loaded.dates.every((date,i)=>i===0 || date>loaded.dates[i-1]));
}
const gunw = JSON.parse(fs.readFileSync('data/subsets/venezuela-gunw/2026-06-13_2026-06-25.json','utf8'));
assert.equal(createHash('sha256').update(fs.readFileSync(gunw.subset_path)).digest('hex'),gunw.sha256);
assert.equal(gunw.valid_samples,0);
context.fetch = async path=>({ok:true,json:async()=>({...JSON.parse(fs.readFileSync(path,'utf8')),source:'synthetic'})});
await assert.rejects(context.OB.loadData(), /measured provenance required/);
if (site.status === 'measured_pair') {
  assert(site.dates.length>=2);
  assert(site.pixels.some(p=>p.hh.slice(0,2).every(Number.isFinite)&&p.hv.slice(0,2).every(Number.isFinite)));
  assert(site.pixels.some(p=>p.disp&&p.disp.length===site.displacement_dates.length));
  assert(site.pixels.some(p=>p.disp===null));
  assert(site.pixels.some(p=>Number.isFinite(p.z)));
  assert.equal(site.analysis_status,'exploratory_sparse_samples');
  for (const p of site.pixels) {
    if (Number.isFinite(p.z)) {
      const channel=p.style==='flood'?'hh':'hv';
      const t=site.dates.length-1;
      assert(Number.isFinite(p[channel][t]) && Number.isFinite(p.peer[channel+'_med'][t]));
      assert(p.peer[channel+'_sd'][t]>0);
      assert(Math.abs(p.z-(p[channel][t]-p.peer[channel+'_med'][t])/p.peer[channel+'_sd'][t])<1e-3);
    }
  }
  assert(site.provenance.inputs.every(r=>r.sha256.length===64));
  for (const r of site.provenance.additional_gcov || []) assert.equal(createHash('sha256').update(fs.readFileSync(r.subset_path)).digest('hex'),r.sha256);
  assert(site.pixels.filter(p=>p.disp).every(p=>p.coherence>=.7&&p.component===site.provenance.reference.component));
}
context.fetch = async()=>({ok:false,status:503});
await assert.rejects(context.OB.loadData(), /503/);

const attempts = new Map();
context.fetch = async path => {
  if (/^data\/[^/]+\.json$/.test(path)) {
    const n = (attempts.get(path) || 0) + 1;
    attempts.set(path, n);
    if (n === 1) return {ok:false, status:503};
  }
  return {ok:true, json:async()=>JSON.parse(fs.readFileSync(path, 'utf8'))};
};
await context.OB.loadData();
assert.equal(context.OB.SITES.length, 8);
assert([...attempts.values()].every(n => n === 2));

const calls=[];
const drawing = new Proxy({}, {get:(_,name)=> (...args)=>{
  if (name === 'measureText') return {width: String(args[0]).length * 7};
  assert(!args.some(a=>typeof a==='number' && !Number.isFinite(a)), `${name} nonfinite coordinate`);
  calls.push([name,...args]);
},set:()=>true});
const canvas = ()=>({clientWidth:600,height:190,style:{},getContext:()=>drawing});
vm.runInContext(fs.readFileSync('js/chart.js','utf8'),context);
const pixel = {hh:[-10,null,-8],hv:[null,null,null],peer:{hh_med:[null,null,null],hh_sd:[null,null,null],hv_med:[null,null,null],hv_sd:[null,null,null]},disp:null};
context.OB.chart.backscatter(canvas(),['2026-01-01','2026-01-13','2026-02-06'],pixel,null);
assert(calls.some(c=>c[0]==='fillText'&&c[1]==='HV unavailable'));
// Separate segments: no lineTo joins across the missing middle measurement.
const start=calls.findIndex(c=>c[0]==='beginPath' && calls[calls.indexOf(c)+1]?.[0]==='moveTo');
assert(start>=0);
calls.length=0;
context.OB.chart.backscatter(canvas(),[],{...pixel,hh:[],hv:[],peer:{hh_med:[],hh_sd:[],hv_med:[],hv_sd:[]}},null);
assert(calls.some(c=>c[0]==='fillText'&&String(c[1]).includes('No GCOV')));
context.OB.chart.displacement(canvas(),[],pixel,null);
assert(calls.some(c=>c[0]==='fillText'&&String(c[1]).includes('No validated GUNW')));
console.log('PASS: catalogue selection, real-data load failure, missing channels and empty charts');

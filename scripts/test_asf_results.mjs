import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
const opera=JSON.parse(fs.readFileSync('data/mexico/opera-disp.json'));
assert.equal(opera.reference_date,'2025-12-25');
assert.equal(opera.granules.length,15);
let previous='';
for (const g of opera.granules) {
  assert(g.id.includes('_F01088_VV_20251225T003922Z_'));
  assert.equal(g.reference_date,opera.reference_date);
  assert(g.secondary_date>previous); previous=g.secondary_date;
  for (const name of ['displacement','short_wavelength_displacement']) {
    const values=g.values[name];assert.equal(values.length,1024);
    assert(values.every(v=>v===null||Number.isFinite(v)));
    assert.equal(values.filter(v=>v!==null).length,g.valid_samples);
  }
}
const paired=JSON.parse(fs.readFileSync('data/analysis/amazon-c-l-matched.json'));
assert.equal(paired.pairs.length,6);
for(const input of paired.inputs)assert.equal(createHash('sha256').update(fs.readFileSync(input.path)).digest('hex'),input.sha256);
assert(paired.pairs.every(p=>p.rtc_granules.length>0));
assert(Math.abs(paired.forest_minus_grassland_db.c_vh_db-1.16)<0.01);
assert(Math.abs(paired.forest_minus_grassland_db.l_hv_db-6.15)<0.01);
for (const name of ['20260508_20260520','20260520_20260601','20260601_20260613']) {
  const p=`data/subsets/venezuela-gunw/${name}-baseline.json`;
  const r=JSON.parse(fs.readFileSync(p));
  assert.equal(createHash('sha256').update(fs.readFileSync(r.subset_path)).digest('hex'),r.sha256);
  assert.equal(r.sample_count,1024);assert.equal(r.valid_quality_samples,0);
}
const dense=JSON.parse(fs.readFileSync('data/analysis/amazon-dense-pair.json'));
assert.deepEqual(dense.dates,['2026-08-23','2026-09-04']);
assert.equal(dense.candidate.local_3x3_valid,9);
for(const file of dense.source_receipts){const r=JSON.parse(fs.readFileSync(file));assert.equal(createHash('sha256').update(fs.readFileSync(r.subset_path)).digest('hex'),r.sha256);}
console.log('PASS: OPERA common-reference series, matched C/L provenance and GUNW baseline quality');

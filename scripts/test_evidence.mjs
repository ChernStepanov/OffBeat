import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
const context = {window: {}, URL}; context.window.OB = {}; context.OB = context.window.OB;
vm.runInNewContext(fs.readFileSync('js/evidence-model.js', 'utf8'), context);
const model = context.OB.evidenceModel;
const bounds = {w: 0, e: 1, s: 0, n: 1};
const firstCrop = model.opticalCrop(bounds, {lon: 0.3, lat: 0.7});
const secondCrop = model.opticalCrop(bounds, {lon: 0.7, lat: 0.3});
assert.notEqual(firstCrop.left, secondCrop.left);
assert.notEqual(firstCrop.top, secondCrop.top);
assert.equal(firstCrop.x, 50);
assert.equal(secondCrop.x, 50);
const edgeCrop = model.opticalCrop(bounds, {lon: 0, lat: 1});
assert.equal(Math.abs(edgeCrop.left), 0); assert.equal(Math.abs(edgeCrop.top), 0);
assert.equal(edgeCrop.x, 0); assert.equal(edgeCrop.y, 0);
let history = [], previous = null;
for (let cycle = 0; cycle < 3; cycle++) {
  const shown = new Set();
  for (let i = 0; i < 3; i++) {
    const next = model.nextSurprise(['a', 'b', 'c'], history, previous, () => 0);
    assert.notEqual(next.id, previous);
    shown.add(next.id); history = next.history; previous = next.id;
  }
  assert.equal(shown.size, 3);
}
assert.equal(model.nextSurprise([], [], null), null);
const book = JSON.parse(fs.readFileSync('data/cases/amazon-v1.json'));
const site = JSON.parse(fs.readFileSync('data/amazon.json'));
assert.deepEqual(Array.from(model.timeline(['2026-01-01','2026-01-02','2026-01-11'])), [0, 0.1, 1]);
assert.deepEqual(Array.from(model.timeline(['2026-01-01'])), [0.5]);
assert.throws(() => model.timeline(['2026-01-02','2026-01-01']), /strictly increasing/);
const candidate = book.cases[0], pixel = site.pixels[candidate.sample_index];
for (const [path, hash] of Object.entries(book.input_sha256)) {
  assert.equal(createHash('sha256').update(fs.readFileSync(path)).digest('hex'), hash, `Stale evidence input: ${path}`);
}
for (const c of book.cases) {
  assert.equal(site.pixels[c.sample_index].id, c.sample_id);
  for (const entry of c.optical) {
    assert.equal(createHash('sha256').update(fs.readFileSync(entry.path)).digest('hex'), entry.sha256);
    assert.ok(entry.date && entry.bounds && entry.item_url);
  }
}
const href = model.link('https://offbeat.test/?view=scene&lat=12&lon=15#tour/2',site,pixel,3,candidate.id,2);
const withoutCandidate = model.link('https://offbeat.test/?candidate=r1-c2',site,pixel,3,candidate.id,2);
assert.equal(new URL(withoutCandidate).searchParams.has('candidate'),false);
const params = new URL(href).searchParams;
assert.equal(params.has('lat'),false);assert.equal(params.has('view'),false);assert.equal(new URL(href).hash,'');
const saved = model.selection(params,[site],book.cases);
assert.equal(saved.index,175);assert.equal(saved.date,3);assert.equal(saved.step,2);assert.equal(saved.caseId,candidate.id);
for (const raw of ['-1','1.2','1e2','NaN','9999999','']) {
  const p = new URLSearchParams(params);p.set('sample',raw);assert.equal(model.selection(p,[site],book.cases),null);
}
const wrongDate = new URLSearchParams(params);wrongDate.set('date','2020-01-01');assert.equal(model.selection(wrongDate,[site],book.cases),null);
const mismatch = new URLSearchParams(params);mismatch.set('sample','0');assert.equal(model.selection(mismatch,[site],book.cases).caseId,null);
const missing = {...pixel,hv:[null,...pixel.hv.slice(1)]};
const report = model.report(site,missing,3,candidate,book,href,'en');
assert.equal(report.observations[0].hv_db,null);assert.equal(report.quality.valid_hv_observations,5);
assert.equal(report.independent_event_status,'unknown');assert.equal(report.evaluation.precision,null);
const generic = model.report(site,pixel,3,null,book,href,'en');assert.equal(generic.independent_event_status,'not_reviewed');
assert.equal(Object.keys(generic.source_sha256).length,0);
const feature = model.geojson(report).features[0];
assert.equal(feature.geometry.type,'Point');assert.equal(feature.geometry.coordinates[0],pixel.lon);assert.equal(feature.geometry.coordinates[1],pixel.lat);
assert.equal(feature.properties.independent_event_status,'unknown');
// A genuine clearing with insufficient pre-event SAR must remain excluded.
const positive = JSON.parse(fs.readFileSync('archive/preview-2026-11-14/data/amazon/positive-eval/results.json'));
const clearing = positive.samples.find(s=>s.id===book.cases[1].sample_id);
assert.equal(clearing.review.status,'forest_loss_visible');assert.equal(clearing.temporal_support.eligible,false);
assert.equal(book.evaluation.eligible_positive_events,0);assert.equal(book.evaluation.false_positive_rate,null);
console.log('PASS: evidence provenance, image hashes, nulls, link validation, verdict isolation and event eligibility');

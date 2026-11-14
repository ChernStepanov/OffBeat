import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';

const context = { window: {} }; context.window = context;
vm.createContext(context);
for (const file of ['point-cloud', 'terrain-model']) vm.runInContext(fs.readFileSync(`js/${file}.js`, 'utf8'), context);
const model = context.OB.terrain;

for (const name of ['mexico', 'amazon', 'venezuela']) {
  const site = JSON.parse(fs.readFileSync(`data/${name}.json`, 'utf8'));
  const dem = JSON.parse(fs.readFileSync(`data/terrain/${name}.json`, 'utf8'));
  const original = JSON.stringify(site);
  assert.equal(model.validate(dem, site), dem);
  assert.equal(dem.height_m.length, 66049);
  assert.equal(dem.min_m, dem.height_m.reduce((a, b) => Math.min(a, b)));
  assert.equal(dem.max_m, dem.height_m.reduce((a, b) => Math.max(a, b)));
  const canonical = '[' + dem.height_m.map(v => Number.isInteger(v) ? v.toFixed(1) : String(v)).join(',') + ']';
  const checksum = createHash('sha256').update(canonical).digest('hex');
  assert.equal(checksum, dem.provenance.height_sha256, 'Prepared numeric DEM must match its receipt');
  for (const source of dem.provenance.sources) { assert(source.url.startsWith('https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/')); assert.match(source.sha256, /^[a-f0-9]{64}$/); }
  const first = model.position(dem, dem.bbox.w, dem.bbox.n), last = model.position(dem, dem.bbox.e, dem.bbox.s);
  assert(first.x < last.x && first.z < last.z, 'Northwest and southeast must retain geographic orientation');
  assert.equal(first.height_m, dem.height_m[0]); assert.equal(last.height_m, dem.height_m.at(-1));
  const initial = model.samples(site, 0, 'hv', dem, 1);
  for (let date = 0; date < site.dates.length; date++) for (const channel of ['hh', 'hv']) {
    const points = model.samples(site, date, channel, dem, 1);
    assert.equal(points.length, site.pixels.filter(p => [p.lat, p.lon, p[channel][date]].every(Number.isFinite)).length);
    for (const p of points) {
      const source = site.pixels[p.index];
      assert.equal(p.value, source[channel][date]); assert.equal(p.lat, source.lat); assert.equal(p.lon, source.lon);
      assert.equal(p.height_m, model.heightAt(dem, source.lon, source.lat));
      const samePosition = initial.find(q => q.index === p.index);
      if (samePosition) assert.equal(p.y, samePosition.y, 'Signal/date must never change terrain altitude');
      assert(p.height_m >= dem.min_m && p.height_m <= dem.max_m);
    }
  }
  const normal = model.samples(site, 0, 'hv', dem, 1), amplified = model.samples(site, 0, 'hv', dem, 4);
  assert.equal(amplified[0].height_m, normal[0].height_m, 'Height readout stays physical under vertical exaggeration');
  assert(Math.abs((amplified[0].y - .004) - (normal[0].y - .004) * 4) < 1e-9);
  assert.equal(amplified[0].x, normal[0].x); assert.equal(amplified[0].z, normal[0].z);
  assert.equal(JSON.stringify(site), original);
  assert.equal(model.heightAt(dem, dem.bbox.w - 1, dem.bbox.n), null);
  assert.equal(model.samples(site, 999, 'hv', dem).length, 0);
}

// A known four-corner plane catches row inversion, wrong interpolation and missing-as-zero.
const plane = { n: 2, bbox: { w: 0, e: 2, s: 0, n: 2 }, height_m: [100, 200, 300, 400], min_m: 100, max_m: 400 };
assert.equal(model.heightAt(plane, 1, 1), 250);
assert.equal(model.heightAt(plane, .5, 1.5), 175);
assert.equal(model.heightAt(plane, null, 1), null);
const fixture = { dates: ['2026-01-01'], pixels: [{ lon: 1, lat: 1, hv: [null] }, { lon: 1, lat: 1, hv: [0] }] };
const valid = model.samples(fixture, 0, 'hv', plane);
assert.equal(valid.length, 1); assert.equal(valid[0].index, 1); assert.equal(valid[0].value, 0);
assert.equal(context.OB.pointCloud.color(null), null);
console.log('PASS: all real DEM grids, source receipts, registration, altitude independent of signal, missing samples and physical height under exaggeration');

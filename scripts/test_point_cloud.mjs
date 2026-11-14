import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const context = { window: {} }; context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('js/point-cloud.js', 'utf8'), context);
const { samples, color, project, hitTest, LOW, HIGH } = context.OB.pointCloud;

// Every displayed point retains its exact source index/value on every prepared date.
for (const name of ['mexico', 'amazon', 'venezuela']) {
  const site = JSON.parse(fs.readFileSync(`data/${name}.json`, 'utf8'));
  const before = JSON.stringify(site);
  for (let date = 0; date < site.dates.length; date++) {
    for (const channel of ['hh', 'hv']) {
      const points = samples(site, date, channel);
      assert.equal(points.length, site.pixels.filter(p => [p.lat, p.lon, p[channel][date]].every(Number.isFinite)).length);
      for (const point of points) {
        assert.equal(point.value, site.pixels[point.index][channel][date]);
        assert(Math.abs(point.z - (point.value - LOW) / (HIGH - LOW) * 1.25) < 1e-10);
        assert([point.x, point.y, point.z].every(Number.isFinite));
      }
    }
  }
  assert.equal(JSON.stringify(site), before, 'Rendering must not mutate measured data');
}

// Missing coordinates/signals are omitted; a valid zero stays a measured value.
const fixture = { dates: ['2026-01-01', '2026-01-13'], grid: { bbox: { w: 0, e: 1, s: 0, n: 1 } }, pixels: [
  { lat: .25, lon: .25, hh: [0, -10], hv: [null, -5] },
  { lat: .75, lon: .75, hh: [null, 0], hv: [-20, null] },
  { lat: null, lon: .5, hh: [-5, -5], hv: [-5, -5] },
  { lat: .5, lon: .5, hh: [Infinity, null], hv: [NaN, null] },
] };
assert.deepEqual(Array.from(samples(fixture, 0, 'hh'), p => p.index), [0]);
assert.deepEqual(Array.from(samples(fixture, 0, 'hv'), p => p.index), [1]);
assert.deepEqual(Array.from(samples(fixture, 1, 'hh'), p => p.value), [-10, 0]);
assert.equal(samples(fixture, 99, 'hv').length, 0);
assert.equal(samples(fixture, 0, 'disp').length, 0);
assert.equal(samples(null, 0, 'hv').length, 0);
assert.equal(color(null), null);
assert.deepEqual(Array.from(color(-100)), Array.from(color(LOW)));
assert.deepEqual(Array.from(color(100)), Array.from(color(HIGH)));

// North stays up in plan view and backscatter height cannot become fake XY motion.
const camera = { yaw: 0, pitch: Math.PI / 2, zoom: 1 };
const north = project({ x: 0, y: 1, z: 0 }, camera, 800, 600);
const south = project({ x: 0, y: -1, z: 0 }, camera, 800, 600);
assert(north.y < south.y);
const east = project({ x: 1, y: 0, z: 0 }, camera, 800, 600);
assert(east.x > north.x);
const elevatedNorth = project({ x: 0, y: 1, z: 1 }, camera, 800, 600);
assert(Math.abs(north.x - elevatedNorth.x) < 1e-10 && Math.abs(north.y - elevatedNorth.y) < 1e-10, 'Plan view position must be independent of backscatter');
const overlap = [{ index: 1, x: 20, y: 20, depth: 1 }, { index: 2, x: 20, y: 20, depth: -1 }];
assert.equal(hitTest(overlap, 20, 20).index, 2, 'Pick the visible foreground point');
assert.equal(hitTest([{ index: 1, x: 20, y: 20 }, { index: 2, x: 25, y: 20 }], 20, 20).index, 1, 'Prefer a directly clicked dot over a nearby dot');
assert.equal(hitTest(overlap, 100, 100), null);

console.log('PASS: measured point identities, date/polarization, missing values, projection and foreground picking');

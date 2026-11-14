import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createHash } from 'node:crypto';

const context = { window: {}, AbortController, setTimeout, clearTimeout, Float32Array, Date, Map, fetch }; context.window = context;
vm.createContext(context); vm.runInContext(fs.readFileSync('js/terrain-tiles.js', 'utf8'), context);
const m = context.OB.terrainTiles;
for (const [lon, lat] of [[0, 0], [179.99, 80], [-179.99, -80], [-67.08, 10.47], [86.925, 27.988]]) {
  const p = m.mercator(lon, lat), g = m.geographic(p.x, p.y);
  assert(Math.abs(g.lon - lon) < 1e-8 && Math.abs(g.lat - lat) < 1e-8);
}
assert.equal(m.descriptor(4, -1, 3).key, m.descriptor(4, 15, 3).key);
assert.notEqual(m.descriptor(4, -1, 3).meshKey, m.descriptor(4, 15, 3).meshKey);
for (let i = 0; i < 100; i++) {
  const centre = m.mercator(-180 + i * 3.6, -80 + (i % 40) * 4), span = 2 ** -(i % 19);
  const coverage = m.cover({ w: centre.x - span, e: centre.x + span, n: centre.y - span, s: centre.y + span }, i % 19);
  assert(coverage.length > 0 && coverage.length <= 64);
  for (const t of coverage) assert(t.z >= 0 && t.z <= 14 && t.y >= 0 && t.y < 2 ** t.z);
}
const bytes = new Uint8ClampedArray([128, 0, 0, 255, 128, 100, 0, 255, 127, 156, 0, 255, 131, 232, 0, 255]);
const decoded = m.decode(bytes, 2);
// A complete orbit always retains the same geographic tile set and source LOD.
for (const [lon, lat] of [[-67.08, 10.47], [86.925, 27.988], [179.99, 80]]) {
  const center = m.mercator(lon, lat);
  for (const zoom of [0, 4, 11, 12.2, 19]) {
    const tiles = m.orbitCoverage(center, zoom);
    assert(tiles.length > 0 && tiles.length <= 64);
    const n = 2 ** tiles[0].z;
    const xs = tiles.map(t => t.x), ys = tiles.map(t => t.y);
    // At local scales cover a full rotation around the centre, including valleys.
    if (zoom >= 4) {
      const radius = 12 / (2 * 2 ** zoom);
      assert(Math.min(...xs) / n <= center.x - radius);
      assert((Math.max(...xs) + 1) / n >= center.x + radius);
      assert(Math.min(...ys) / n <= Math.max(0, center.y - radius));
      assert((Math.max(...ys) + 1) / n >= Math.min(1, center.y + radius));
    }
  }
}
assert.deepEqual(Array.from(decoded.heights), [0, 100, -100, 1000]);
assert.equal(m.sample(decoded, .5, .5), 250);
assert.throws(() => m.decode(new Uint8ClampedArray(16), 2), /transparent/);
const receipt = JSON.parse(fs.readFileSync('data/terrain/world-0.json'));
assert.equal(createHash('sha256').update(fs.readFileSync('data/terrain/world-0.png')).digest('hex'), receipt.sha256);
console.log('PASS: world coordinates, antimeridian, polar bounds, LOD budget, Terrarium decoding and bundled global DEM receipt');

const tick = () => new Promise(resolve => setImmediate(resolve));
let active = 0, peak = 0, requests = [], changes = 0;
const loader = m.create(() => changes++, {
  limit: 5, concurrency: 2,
  fetcher: (url, { signal }) => new Promise((resolve, reject) => {
    active++; peak = Math.max(peak, active);
    const request = { url, resolve(ok = true) { active--; resolve({ ok, status: ok ? 200 : 503, blob: async () => ({}) }); } };
    requests.push(request);
    signal.addEventListener('abort', () => { active--; reject(new Error('aborted')); }, { once: true });
  }),
  decodeImage: async () => decoded,
});
loader.setWanted([m.descriptor(0, 0, 0), ...[0, 1, 2].map(x => m.descriptor(3, x, 2))]);
assert.equal(requests.length, 2);
requests[0].resolve(); requests[1].resolve(); await tick(); await tick();
assert.equal(requests.length, 4);
requests[2].resolve(); requests[3].resolve(); await tick(); await tick();
assert.equal(peak, 2); assert.equal(loader.info().pending, 0); assert.equal(changes, 4);
assert(loader.heightAt(.5, .5, 14));

// Returning to an aborted viewport before its promise settles must restart its tiles.
requests = [];
loader.setWanted([m.descriptor(3, 4, 2)]);
loader.setWanted([m.descriptor(3, 5, 2)]);
loader.setWanted([m.descriptor(3, 4, 2)]);
await tick(); await tick();
const restarted = requests.at(-1); assert(restarted.url.includes('/3/4/2.png'));
restarted.resolve(); await tick(); await tick();
assert.equal(loader.info().pending, 0);

// Failed downloads leave explicit failure state; Retry fetches measured bytes again.
requests = []; loader.setWanted([m.descriptor(3, 6, 2)]);
requests[0].resolve(false); await tick(); await tick(); assert.equal(loader.info().failed, 1);
loader.retry(); requests[1].resolve(); await tick(); await tick(); assert.equal(loader.info().failed, 0);
assert(loader.info().cached <= 5);
loader.stop();
console.log('PASS: bounded downloads/cache, aborted viewport races, measured fallback and failed-tile retry');

// Non-DEM streams use their own URLs and release decoded resources on eviction.
const mapUrls = [], evicted = [];
const maps = m.create(() => {}, {
  limit: 1, concurrency: 1, rootUrl: null,
  fetcher: async url => { mapUrls.push(url); return { ok: true, blob: async () => ({}) }; },
  decodeImage: async () => ({ resource: mapUrls.at(-1) }),
  onEvict: entry => evicted.push(entry.resource),
});
const first = { ...m.descriptor(1, 0, 0), url: 'https://example.org/map/1/0/0' };
const second = { ...m.descriptor(1, 1, 0), url: 'https://example.org/map/1/0/1' };
maps.setWanted([first]); await tick(); await tick();
maps.setWanted([second]); await tick(); await tick();
assert.deepEqual(mapUrls, [first.url, second.url]);
assert.deepEqual(evicted, [first.url]);
maps.stop();
console.log('PASS: independent map URLs and decoded resource eviction');

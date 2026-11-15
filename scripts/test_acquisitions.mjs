import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const context = { window: {} };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('js/acquisitions.js', 'utf8'), context);
const { available, color } = context.OB.acquisitions;
const site = { pixels: [{ hv: [-10, null, 0] }, { hv: [null, -25, 0] }] };
assert.equal(available(site, 0), 1);
assert.equal(available(site, 1), 1);
assert.equal(available(site, 2), 2);
assert.equal(available(site, 3), 0);
for (const value of [null, undefined, NaN, Infinity, -Infinity]) assert.equal(color(value), null);
assert.deepEqual(Array.from(color(-25)), [0, 70, 255, 180]);
assert.deepEqual(Array.from(color(0)), [255, 70, 0, 180]);
assert.deepEqual(Array.from(color(-100)), Array.from(color(-25)));
assert.deepEqual(Array.from(color(10)), Array.from(color(0)));
for (const id of ['mexico', 'amazon', 'venezuela', 'delhi', 'tokyo', 'nairobi', 'sydney']) {
  const real = JSON.parse(fs.readFileSync(`data/${id}.json`, 'utf8'));
  real.dates.forEach((date, index) => {
    assert.equal(available(real, index), real.pixels.filter(p => color(p.hv[index]) !== null).length, `${id}: ${date}`);
  });
}
console.log('PASS: acquisition availability, missing samples, fixed colour scale and real sites');

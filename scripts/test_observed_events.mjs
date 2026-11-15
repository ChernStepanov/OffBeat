import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const catalog = JSON.parse(readFileSync('data/observed-events/index.json', 'utf8'));
assert.equal(catalog.schema_version, 1);
assert.ok(catalog.cases.length >= 1);
const seen = new Set();
for (const item of catalog.cases) {
  assert.ok(!seen.has(item.id)); seen.add(item.id);
  assert.match(item.source, /^https:\/\/science\.nasa\.gov\//);
  assert.equal(item.images.length, 2);
  assert.ok(item.images[0].date < item.images[1].date);
  for (const image of item.images) {
    assert.match(image.path, /^data\/observed-events\/[a-z0-9-]+\.jpg$/);
    assert.match(image.url, /^https:\/\/assets\.science\.nasa\.gov\//);
    const data = readFileSync(image.path);
    assert.equal(data[0], 0xff); assert.equal(data[1], 0xd8);
    assert.equal(createHash('sha256').update(data).digest('hex'), image.sha256);
  }
}
assert.ok(catalog.cases.some(c => /NISAR GSLC/.test(c.credit)));
console.log(`PASS: ${catalog.cases.length} documented NASA comparisons, dates, JPEGs and source hashes`);

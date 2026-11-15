import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';

for (const site of ['mexico','amazon','venezuela','delhi','tokyo','nairobi','sydney']) {
  const measurements = JSON.parse(fs.readFileSync(`data/${site}.json`, 'utf8'));
  const index = JSON.parse(fs.readFileSync(`data/${site}/optical/index.json`, 'utf8'));
  assert.equal(index.site, site);
  assert.equal(index.schema_version, 1);
  for (const entry of index.entries) {
    assert(measurements.dates.includes(entry.nisar_date));
    if (entry.status !== 'ready') continue;
    assert(entry.date && entry.item_url && entry.bounds && Number.isFinite(entry.aoi_clear_fraction));
    assert.equal(createHash('sha256').update(fs.readFileSync(entry.path)).digest('hex'), entry.sha256);
    for (const key of ['w','s','e','n']) assert.equal(entry.bounds[key], measurements.grid.bbox[key]);
  }
}
console.log('PASS: optical previews, dates, bounds and source hashes for all prepared sites');

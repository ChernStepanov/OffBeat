import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';

const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const hash = p => createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const audit = read('data/analysis/amazon-candidate-visual-check-2026-11-15.json');
assert.equal(hash(audit.radar_source), audit.radar_source_sha256);
const radar = read(audit.radar_source);
assert.deepEqual(audit.radar_dates, radar.dates);
assert.deepEqual(audit.items.map(i => i.id), radar.markers.map(i => i.id));
assert.equal(audit.optical_images.length, 3);
for (const image of audit.optical_images) assert.equal(hash(image.path), image.sha256);
assert.equal(hash(audit.weather_context.source), audit.weather_context.sha256);
assert.ok(radar.optical_images[0].date <= radar.dates[0]);
assert.ok(radar.optical_images[1].date >= radar.dates[1]);
assert.match(audit.kind, /not_independent_validation/);
console.log('PASS: visual audit provenance, candidate IDs and optical dates bracket radar dates');

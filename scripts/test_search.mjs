import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context = {};
context.window = context;
vm.runInNewContext(fs.readFileSync('js/search.js','utf8'), context);
const parse = context.OB.parseCoordinates;
for (const query of ['19.43, -99.08','19.43 -99.08',' +19.43, -99.08 ']) {
  const result = parse(query);
  assert.equal(result.kind,'coordinates'); assert.equal(result.lat,19.43); assert.equal(result.lon,-99.08);
}
for (const query of ['91, 10','19, 181','1,2,3']) assert.equal(parse(query).kind,'invalid');
for (const query of ['Amazon forest','Московская область','-19.2 forest']) assert.equal(parse(query).kind,'place');
console.log('PASS: decimal coordinates, invalid ranges, region and forest names');

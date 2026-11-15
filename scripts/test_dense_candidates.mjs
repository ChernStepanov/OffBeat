import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';

const hash = p => createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const js = fs.readFileSync('js/dense-candidates.js','utf8');
const manifest = js.match(/data\/change-candidates\/catalog-[a-f0-9]{12}\.json/)[0];
assert.equal(hash(manifest).slice(0,12), manifest.match(/([a-f0-9]{12})\.json$/)[1]);
const c=JSON.parse(fs.readFileSync(manifest,'utf8'));assert.equal(c.schema_version,1);assert.equal(c.sites.length,7);
let total=0;
for(const entry of c.sites){
  assert.equal(hash(entry.path),entry.sha256);assert(entry.path.includes(entry.sha256.slice(0,12)));
  const d=JSON.parse(fs.readFileSync(entry.path,'utf8'));assert.equal(d.site,entry.id);assert.equal(d.inputs.length,2);
  assert.deepEqual(d.dates,entry.dates);assert.equal(d.markers.length,entry.marker_count);assert(d.markers.length<=30);
  const ids=new Set();for(const m of d.markers){assert(!ids.has(m.id));ids.add(m.id);assert(m.row>=0&&m.row<d.grid.shape[0]&&m.col>=0&&m.col<d.grid.shape[1]);assert(Number.isFinite(m.lat)&&Number.isFinite(m.lon)&&Number.isFinite(m.delta_db)&&Number.isFinite(m.score));assert.equal(m.direction,m.score<0?'below':'above')}
  for(const input of d.inputs){assert(input.granule_id&&input.concept_id&&input.url.startsWith('https://'));assert.equal(hash(input.subset_path),input.sha256)}
  for(const image of d.radar_images){assert.equal(hash(image.path),image.sha256);const b=fs.readFileSync(image.path);assert.equal(b.readUInt32BE(16),d.grid.shape[1]);assert.equal(b.readUInt32BE(20),d.grid.shape[0])}
  for(const image of d.optical_images){assert.equal(hash(image.path),image.sha256);assert(image.date&&image.bounds&&image.item_url)}
  total+=d.markers.length;
}
assert.equal(total,185);
console.log('PASS: seven candidate datasets, source hashes, imagery, dates and native grid coordinates');

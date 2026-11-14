// Public CMR metadata only; never persist signed redirects or credentials.
import fs from 'node:fs';
const products = {};
for (const product of ['gcov', 'gunw']) {
  const raw = JSON.parse(fs.readFileSync(`data/catalog/mexico-${product}.json`, 'utf8').replace(/^\uFEFF/, ''));
  products[product] = raw.feed.entry.filter(g => new RegExp(`_${product.toUpperCase()}_\\d+_019_A_011_`).test(g.producer_granule_id)).map(g => ({
    id: g.producer_granule_id, concept_id: g.id, collection: g.collection_concept_id,
    start: g.time_start, end: g.time_end, size_mb: Number(g.granule_size), polygons: g.polygons,
    url: g.links.find(l => l.href.startsWith('https:') && l.href.endsWith('.h5') && l.rel.endsWith('/data#'))?.href
  }));
}
const manifest = {
  checked_at: new Date().toISOString(), site: 'mexico', bbox: [-99.25, 19.25, -98.9, 19.6],
  track: 19, direction: 'Ascending', frame: 11, maturity: 'PROVISIONAL',
  queries: ['GCOV','GUNW'].map(p => `https://cmr.earthdata.nasa.gov/search/granules.json?short_name=NISAR_L2_${p}_PROVISIONAL_V1&bounding_box=-99.25,19.25,-98.9,19.6&page_size=2000&sort_key=start_date`),
  access: { status: 'earthdata_login_required', check: 'Range GET bytes=0-7 redirected to urs.earthdata.nasa.gov, HTML instead of HDF5' },
  products
};
fs.writeFileSync('data/mexico-manifest.json', JSON.stringify(manifest, null, 2) + '\n');
console.log(Object.fromEntries(Object.entries(products).map(([k,v])=>[k,{count:v.length,first:v[0]?.id,last:v.at(-1)?.id}])));

import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const context = {URL, AbortSignal, navigator: {languages:['ru-RU']}};
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
assert.equal(context.OB.normalizePlaceQuery('  東京　 都  '), '東京 都');
assert.equal(context.OB.normalizePlaceQuery('\u200fالقاهرة'), 'القاهرة');
assert.equal(context.OB.normalizePlaceQuery('Montre\u0301al'), 'Montréal');
for (const query of ['Москва', 'Париж', '東京', '北京', 'القاهرة', 'मुंबई', 'São Paulo']) {
  context.fetch = async url => {
    assert.equal(url.searchParams.get('name'), query);
    assert.equal(url.searchParams.get('language'), ({'東京':'zh','北京':'zh','القاهرة':'ar','मुंबई':'hi'})[query] || 'ru');
    assert(!url.searchParams.has('countryCode'));
    return {ok:true,json:async()=>({results:[{name:query,latitude:35,longitude:139}]})};
  };
  const features = await context.OB.geocodePlace(query, 'https://photon.komoot.io/api/');
  assert.equal(features[0].properties.name,query);
  assert.equal(features[0].geometry.coordinates[0],139);
}
for (const failPrimary of [false,true]) {
  let calls=0;
  context.fetch=async url=>{
    calls++;
    if(calls===1){if(failPrimary) throw Error('offline');return {ok:true,json:async()=>({})};}
    assert.equal(url.searchParams.get('q'),'森林');
    return {ok:true,json:async()=>({features:[{properties:{name:'森林'}}]})};
  };
  assert.equal((await context.OB.geocodePlace('森林','https://photon.komoot.io/api/'))[0].properties.name,'森林');
  assert.equal(calls,2);
}
context.fetch=async()=>({ok:false});
await assert.rejects(context.OB.geocodePlace('Москва','https://photon.komoot.io/api/'),/unavailable/);
console.log('PASS: multilingual queries preserved, Unicode normalization, fallback and errors');

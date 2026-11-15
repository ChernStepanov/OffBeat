// Append source strings without renumbering existing catalogue IDs.
const fs=require('node:fs'), vm=require('node:vm');
const pairs=JSON.parse(fs.readFileSync('locales/source-pairs.json','utf8'));
for(const [path,names] of [['js/research.js',['STRINGS']],['js/candidates.js',['STRINGS','EXTRA_STRINGS','SCIENCE_STRINGS','UI_STRINGS']]]){
  const source=fs.readFileSync(path,'utf8');
  for(const name of names){
    const m=source.match(new RegExp('const '+name+'\\s*=\\s*(\\{[\\s\\S]*?\\});\\s*(?:\\n|$)'));
    if(!m)continue;
    const d=vm.runInNewContext('('+m[1]+')');
    if(d.en&&d.ru)for(const[k,v]of Object.entries(d.en)){
      if(typeof v==='string'&&typeof d.ru[k]==='string'&&!pairs[v])pairs[v]=d.ru[k];
    }
  }
}
for(const name of fs.readdirSync('js')){
  if(!name.endsWith('.js'))continue;
  const source=fs.readFileSync('js/'+name,'utf8');
  const regex=/\b(?:t|tr)\(\s*('(?:\\.|[^'\\])*')\s*,\s*('(?:\\.|[^'\\])*')\s*\)/g;
  for(const m of source.matchAll(regex)){
    const en=vm.runInNewContext(m[1]),ru=vm.runInNewContext(m[2]);
    if(!pairs[en])pairs[en]=ru;
  }
}
function localized(d){
  if(!d||typeof d!=='object')return;
  if(typeof d.en==='string'&&typeof d.ru==='string'&&!pairs[d.en])pairs[d.en]=d.ru;
  for(const[k,v]of Object.entries(d)){
    if(k.endsWith('_en')&&typeof v==='string'&&typeof d[k.slice(0,-3)+'_ru']==='string'&&!pairs[v])pairs[v]=d[k.slice(0,-3)+'_ru'];
    if(v&&typeof v==='object')localized(v);
  }
}
for(const p of ['data/findings.json','data/cases/amazon-v1.json','data/observed-events/index.json','data/investigation/results.json','data/investigation/map-candidates.json','data/investigation/regional-events.json']){
  if(fs.existsSync(p))localized(JSON.parse(fs.readFileSync(p,'utf8')));
}
const target=process.argv[2]||'locales/source-pairs.json';
fs.writeFileSync(target,JSON.stringify(pairs,null,2)+'\n');
console.log('Source entries:',Object.keys(pairs).length);

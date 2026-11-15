// Bind HTML to exact first-party JS/CSS bytes so a release cannot reuse stale scripts.
import fs from 'node:fs';
import {createHash} from 'node:crypto';
let stale=false;
for(const path of ['index.html','research.html','candidates.html']){
  const original=fs.readFileSync(path,'utf8');
  const updated=original.replace(/\b(src|href)="((?:js|css)\/[^"?]+\.(?:js|css))(?:\?v=[^"\s]+)?"/g,
    (_,attribute,file)=>`${attribute}="${file}?v=${createHash('sha256').update(fs.readFileSync(file,'utf8').replace(/\r\n/g,'\n')).digest('hex').slice(0,12)}"`);
  if(process.argv.includes('--check')){
    if(original!==updated){console.error(`Stale asset hashes in ${path}: run node scripts/version_assets.mjs`);stale=true;}
  }else fs.writeFileSync(path,updated);
}
if(stale) process.exit(1);
if(process.argv.includes('--check')) console.log('PASS: all HTML entry points pin current JS/CSS content hashes');

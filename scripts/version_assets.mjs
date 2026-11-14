// Bind HTML to exact first-party JS/CSS bytes so a release cannot reuse stale scripts.
import fs from 'node:fs';
import {createHash} from 'node:crypto';
const path='index.html';
const original=fs.readFileSync(path,'utf8');
const updated=original.replace(/\b(src|href)="((?:js|css)\/[^"?]+\.(?:js|css))(?:\?v=[^"\s]+)?"/g,
  (_,attribute,file)=>`${attribute}="${file}?v=${createHash('sha256').update(fs.readFileSync(file,'utf8').replace(/\r\n/g,'\n')).digest('hex').slice(0,12)}"`);
if(process.argv.includes('--check')){
  if(original!==updated){console.error('Stale asset hashes: run node scripts/version_assets.mjs');process.exit(1);}
  console.log('PASS: HTML pins current JS/CSS content hashes');
}else fs.writeFileSync(path,updated);

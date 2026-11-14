import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const size=256, alpha=new Uint8ClampedArray(size*size*4);
for(let y=0;y<size;y++)for(let x=0;x<size;x++)alpha[(y*size+x)*4+3]=(x*29+y*17)%256;
const context={window:{},document:{createElement:()=>({getContext:()=>({drawImage(){},getImageData:()=>({data:alpha})})})},L:{},ImageData:class{},requestAnimationFrame(){}};
context.window=context;vm.createContext(context);
const source=fs.readFileSync('js/nisar-map.js','utf8').replace('  // date order -> colour:', '  OB.testCoverage = coverage;\n  // date order -> colour:');
vm.runInContext(source,context);
const pane={style:{}},map={createPane(){},getPane:()=>pane,whenReady(){},on(){},getZoom:()=>10};
context.OB.bindNisarMap(map,{addEventListener(){}},{});
const mask=context.OB.testCoverage({});
for(let y=0;y<size;y++)for(let x=0;x<size;x++){
 let a=0,n=0;for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)if(x+dx>=0&&x+dx<size&&y+dy>=0&&y+dy<size){a+=alpha[((y+dy)*size+x+dx)*4+3];n++;}
 assert.equal(mask[y*size+x],a/(255*n)>=0.35?1:0,`coverage mismatch at ${x},${y}`);
}
console.log('PASS: optimized coverage preserves all pixel and edge results');

import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
let pixels, detail; const detailOptions=[];
const ctx={drawImage(){},getImageData(){return {data:pixels};}};
function TileLayer() {}
TileLayer.prototype.createTile=function(coords,done){const image={style:{}};this.finish=()=>done(null,image);return image;};
TileLayer.extend=methods=>class extends TileLayer {constructor(url,options){super();detailOptions.push(options);detail=this;} addTo(){return this;} createTile(...args){return methods.createTile.apply(this,args);}};
const context={window:{},document:{createElement:()=>({getContext:()=>ctx})},L:{TileLayer,tileLayer:(url,options)=>({addTo(){assert.equal(options.maxNativeZoom,16);return this;}})}};
context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync('js/map-imagery.js','utf8'),context);
context.OB.bindImagery({},'https://example.test/{z}/{y}/{x}',{});
assert.deepEqual(detailOptions.map(o=>o.maxNativeZoom),[17,18,19]);
assert.deepEqual(detailOptions.map(o=>o.minZoom),[17,18,19]);
pixels=new Uint8Array([235,151,175,255,204,204,204,255,204,204,204,255,204,204,204,255]);
let result; detail.createTile({},(_err,img)=>result=img);detail.finish();assert.equal(result.style.visibility,'hidden','Esri placeholder must reveal the fallback');
pixels[4]=203;detail.createTile({},(_err,img)=>result=img);detail.finish();assert.equal(result.style.visibility,undefined,'valid imagery must remain visible');
console.log('PASS: detailed imagery, placeholder fallback and valid tiles');

import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
let overlays=0, removed=0, listener;
const select={value:'context',disabled:true,options:[],replaceChildren(option){this.value='context';this.options=[option];},add(option){this.options.push(option);},addEventListener(_name,cb){listener=cb;}};
const context={window:{},Option:function(text,value){this.text=text;this.value=value;},AbortSignal,
  fetch:async()=>({ok:true,json:async()=>({site:'a',schema_version:1,entries:[
    {status:'ready',nisar_date:'2026-01-01',date:'2026-01-02',path:'image.png',sha256:'abc',bounds:{s:0,w:0,n:1,e:1},aoi_cloud_shadow_snow_fraction:0,scene_id:'x'},
    {status:'ready',nisar_date:'2026-01-13',date:'2026-01-12',path:'image2.png',sha256:'def',bounds:{s:0,w:0,n:1,e:1},aoi_cloud_shadow_snow_fraction:0,scene_id:'y'},
    {status:'unavailable',nisar_date:'2026-01-25',reason:'No readable clear scene'}]})}),
  L:{imageOverlay:()=>({on(){return this;},addTo(){overlays++;return this;}})}};
context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync('js/optical.js','utf8'),context);
const status={},optic=context.OB.bindOptical({removeLayer(){removed++;}},select,status);
await optic.load({id:'a',dates:['2026-01-01','2026-01-13']});
assert.equal(select.value,'context');assert.equal(overlays,0);
optic.setDate('2026-01-01');assert.equal(overlays,0);
select.value='0';listener();assert.equal(overlays,1);
optic.setDate('2026-01-13');assert.equal(select.value,'1');assert.equal(overlays,2);
assert.match(select.options[3].text,/No clear optical image.*2026-01-25/);
select.value='2';listener();assert.match(status.textContent,/No readable clear scene/);assert.equal(overlays,2);
select.value='context';listener();assert(removed>=1);
optic.setDate('2026-01-01');assert.equal(select.value,'context');assert.equal(overlays,2);
console.log('PASS: sharp context by default, dated images only when selected');

import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const labels = [], fills = []; let path = [];
const g = { setTransform(){}, clearRect(){}, fillRect(){}, strokeRect(){}, setLineDash(){},
  measureText(t){return {width:String(t).length*6}}, fillText(t){labels.push(String(t))},
  beginPath(){path=[]}, moveTo(x,y){path.push([x,y])}, lineTo(x,y){path.push([x,y])},
  closePath(){}, stroke(){}, fill(){fills.push(path.slice())} };
const canvas = () => ({clientWidth:600,height:200,style:{},getContext(){return g}});
const context={window:{devicePixelRatio:1},Number,Math,Date};context.window.OB={};context.OB=context.window.OB;
vm.runInNewContext(fs.readFileSync('js/chart.js','utf8'),context);
const peer={hh_med:[-5,-5],hh_sd:[10,10],hv_med:[-20,-20],hv_sd:[12,12]};
context.OB.chart.backscatter(canvas(),['2026-08-23','2026-09-04'],{hh:[-4,-4],hv:[-20,-20],peer},null,null);
assert(labels.includes('08-23') && labels.includes('09-04'),'short acquisitions display distinct dates');
for(const band of fills)for(const [,y] of band)assert(y>=8 && y<=180,`peer band clipped: ${y}`);
labels.length=0; fills.length=0;
context.OB.chart.displacement(canvas(),['2025-12-31','2026-01-12'],{disp:[0,1],peer_disp:[0,1],peer_disp_sd:[20,20]},null,null);
assert(labels.includes('25-12-31')&&labels.includes('26-01-12'),'cross-year dates show year and day');
for(const band of fills)for(const [,y] of band)assert(y>=8 && y<=180,`displacement band clipped: ${y}`);
console.log('PASS: HH/HV and displacement peer bands remain in range; close and cross-year dates are distinct');

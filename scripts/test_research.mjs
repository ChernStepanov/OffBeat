import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Node {
  constructor(tag='div') { this.tagName=tag;this.children=[];this.attrs={};this.dataset={};this.style={setProperty(){},height:''};this.hidden=false;this.textContent='';this.listeners={};this.className='';this.clientWidth=500;this.height=220;this.width=300; }
  appendChild(child){this.children.push(child);return child;}
  replaceChildren(...children){this.children=children;}
  setAttribute(key,value){this.attrs[key]=String(value);}
  getAttribute(key){return this.attrs[key]??null;}
  addEventListener(name,fn){this.listeners[name]=fn;}
  getBoundingClientRect(){return {width:this.clientWidth,height:220};}
  getContext(){this.calls=[];this.rects=[];const node=this;return {setTransform(...args){node.transform=args;},clearRect(){},fillRect(...args){node.rects.push(args);},beginPath(){node.path={moves:0,lines:0};node.calls.push(node.path);},moveTo(){node.path.moves++;},lineTo(){node.path.lines++;},stroke(){node.lastStroke=node.path;},fillText(value){node.labels ||= [];node.labels.push(String(value));},save(){},restore(){},translate(){},rotate(){}};}
}
const ids=['research-language','research-content','research-status','research-heading','research-intro-copy','research-amazon-link','research-cards','finding-content','evidence-content','matching-content','ablation-content','sources-content','repro-content'];
const elements=Object.fromEntries(ids.map(id=>[id,new Node()]));
elements['research-content'].hidden=true;
const translatable=['skip','title','dashboard','finding','matching','ablation','heading','intro','loading','evidence','sources','repro','back'];
const labels=translatable.map(key=>Object.assign(new Node(),{attrs:{'data-i18n':key}}));
const document={documentElement:new Node('html'),getElementById:id=>elements[id],createElement:tag=>new Node(tag),createTextNode:text=>Object.assign(new Node('#text'),{textContent:text}),querySelectorAll:()=>labels};
let response={ok:false,status:404};
const context={document,window:null,fetch:async()=>response,console,URL,location:{href:'http://localhost:8787/research.html',origin:'http://localhost:8787'},devicePixelRatio:2};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('js/research.js','utf8'),context);
await new Promise(resolve=>setImmediate(resolve));
assert.match(elements['research-status'].textContent,/готовятся/i,'404 must produce a graceful missing-data state');
assert.equal(elements['research-content'].hidden,true,'missing data must not render empty result panels');
assert.equal(elements['research-language'].textContent,'EN');
elements['research-language'].listeners.click();
assert.equal(document.documentElement.lang,'en');
assert.match(elements['research-status'].textContent,/being prepared/i);

// Exercise the future-data adapter using synthetic test-only input; all content must remain text.
const malicious='<img src=x onerror=alert(1)>';
context.OBResearchData={
  headline:{ru:'Заголовок из отчёта',en:'Report-provided headline'},
  intro:{ru:'Вводный текст из отчёта',en:'Report-provided introduction'},
  finding:{ru:malicious,en:'A finding'},
  evidence:{strength:'Limited',limitations:['Small sample']},
  matching:{summary:'Matching description',table:{columns:['method','result'],rows:[{method:malicious,result:'available'}]}},
  ablations:{charts:[{title:'Ablation comparison',series:[{label:'baseline',values:[{label:'A',value:1},{label:'B',value:2}]}]}]},
  sources:['Source record'],reproducibility:{commands:['python -m pytest']}
};
context.OBResearch.render(context.OBResearchData);
assert.equal(elements['research-content'].hidden,false);
assert.equal(elements['research-heading'].textContent,'Report-provided headline');
assert.equal(elements['research-intro-copy'].textContent,'Report-provided introduction');
assert.equal(elements['finding-content'].children[0].textContent,'A finding');
assert.equal(elements['finding-content'].children[0].children.length,0,'untrusted strings are never parsed as markup');
const cell=elements['matching-content'].children[1].children[0].children[1].children[0].children[0];
assert.equal(cell.textContent,malicious);
assert.equal(cell.children.length,0);
assert.equal(elements['ablation-content'].children.some(node=>node.tagName==='canvas'),true,'chart series render with native canvas');
assert.match(labels.find(node=>node.attrs['data-i18n']==='heading').textContent,/What withstands scrutiny/,'loaded page has the actual research heading');
elements['research-language'].listeners.click();
assert.equal(document.documentElement.lang,'ru','language switch rerenders loaded report');
assert.equal(elements['finding-content'].children[0].textContent,malicious);
assert.equal(elements['research-heading'].textContent,'Заголовок из отчёта');
assert.equal(elements['research-intro-copy'].textContent,'Вводный текст из отчёта');

// Null and blank observations must break the line; labels are localized and DPR redraw remains stable.
const chartParent=new Node();
context.OBResearch.renderChart(chartParent,{title:'Gap check',series:[{label:'series',values:[
  {label:{ru:'янв',en:'Jan'},value:1},
  {label:'nested null',value:null},
  {label:'nested blank',value:''},
  {label:'valid middle',value:3},
  null,'',
  {label:'valid end',value:2}
]}]});
const chart=chartParent.children.find(node=>node.tagName==='canvas');
assert(chart,'chart should create a canvas');
assert.deepEqual(Array.from(chart.transform),[2,0,0,2,0,0]);
assert.equal(chart.width,1000);assert.equal(chart.height,440,'both canvas backing dimensions use DPR');
assert.deepEqual({moves:chart.lastStroke.moves,lines:chart.lastStroke.lines},{moves:3,lines:0},'nested null/blank observations split the line rather than becoming zero');
assert.equal(chart.rects.filter(([, , width, height])=>width===4&&height===4).length,3,'nested null/blank values create no phantom zero points');
assert(chart.labels.includes('янв'),'chart point labels use active locale');
chart.clientWidth=420;context.OBResearch.drawChart(chart,{series:[{values:[1,null,'',2]}]});
assert.equal(chart.width,840);assert.equal(chart.height,440,'redraw does not compound the canvas dimensions');
const barParent=new Node();
context.OBResearch.renderChart(barParent,{type:'bar',labels:['negative','positive'],series:[{values:[-1,2]}]});
const bars=barParent.children.find(node=>node.tagName==='canvas').rects.filter(([, , width])=>width<500);
assert.equal(bars.length,2);
assert(bars.every(([, , , height])=>height>0),'negative bars extend away from zero with positive canvas height');
assert(bars.some(([,y,,height])=>Math.abs(y-128)<0.01 && y+height>128),'negative bar extends below zero');
assert(bars.some(([,y,,height])=>y<128 && Math.abs(y+height-128)<0.01),'positive bar extends above zero');

// Sources accept same-origin relative report/raw links only; download remains an explicit option.
context.OBResearch.render({...context.OBResearchData,sources:[
  {label:{ru:'Отчёт',en:'Report'},href:'docs/report.md'},
  {label:'Raw JSON',href:'data/research/raw.json',download:true},
  {label:'Unsafe scheme',href:'javascript:alert(1)'},
  {label:'Outside root',href:'../../secret.json'}
]});
const sourceItems=elements['sources-content'].children[0].children;
assert.equal(sourceItems.length,4);
assert.equal(sourceItems[0].children[0].tagName,'a');assert.match(sourceItems[0].children[0].attrs.href,/docs\/report\.md$/);
assert.equal(sourceItems[1].children[0].attrs.download,'');
assert.equal(sourceItems[2].children.length,0,'unsafe schemes are rendered as plain text');
assert.equal(sourceItems[3].children.length,0,'parent traversal is not linked');

// Render the generated real-data report as an integration/DOM smoke check.
const realReport=JSON.parse(fs.readFileSync('data/research/results.json','utf8'));
context.OBResearch.render(realReport);
assert.equal(elements['research-content'].hidden,false);
assert.equal(elements['research-cards'].children.length,3,'report presents three derived key findings');
assert.match(elements['research-heading'].textContent,/What withstands scrutiny|Что выдерживает проверку/);
assert.equal(elements['finding-content'].children.filter(node=>node.tagName==='canvas').length,2,'trajectory and correlation charts render');
assert(elements['finding-content'].children.some(node=>node.tagName==='details'),'block-bootstrap contrast is available in an expandable detail');
assert(elements['matching-content'].children.some(node=>node.tagName==='table') || elements['matching-content'].children.some(node=>node.tagName==='div'),'matching table renders');
assert.equal(elements['sources-content'].children[0].children.length,7,'reports, raw JSON, protocol, synthesis and dashboard links are present');
assert.match(elements['research-amazon-link'].href,/\/index\.html\?site=amazon$/);
assert.match(elements['ablation-content'].children[0].textContent,/83/,'3 dB candidate counts are visible in the ablation summary');

// Ensure navigation and the requested standalone assets are wired without changing the main app.
const html=fs.readFileSync('research.html','utf8'), index=fs.readFileSync('index.html','utf8');
assert.match(fs.readFileSync('js/research.js','utf8'),/data\/research\/results\.json/); // stable future data location
assert.match(index,/href="research\.html"/);
assert.match(fs.readFileSync('js/i18n.js','utf8'),/Research results':'Результаты исследования/);
assert.match(html,/css\/research\.css/);assert.match(html,/js\/research\.js/);
console.log('PASS: research page missing state, bilingual rendering, safe text output and chart/table adapter');

import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
let oscillators=0, noise=0, interval=null;
const param={value:0,setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){}};
const node=()=>({connect(){return this},start(){},stop(){},gain:{...param},pan:{value:0}});
class AudioContext { constructor(){this.state='running';this.currentTime=0;this.sampleRate=1000;this.destination={}} createOscillator(){oscillators++;return {...node(),frequency:{value:0},detune:{value:0}}} createGain(){return node()} createStereoPanner(){return node()} createBuffer(){return {getChannelData(){return new Float32Array(20)}}} createBufferSource(){noise++;return node()} }
const c={window:{AudioContext},Math,Number,Float32Array,setInterval(fn){interval=fn;return 1},clearInterval(){interval=null}};c.window.OB={};c.OB=c.window.OB;
vm.runInNewContext(fs.readFileSync('js/sonify.js','utf8'),c);
const seen=[];let ended=false;
c.OB.sonify.play({pix:[-10,null,-15,-13],med:[-12,-12,-13,-12],sd:[2,2,0,2]},i=>seen.push(i),()=>{ended=true});
assert.equal(oscillators,4,'two valid dates each create two tones');
assert.equal(noise,2,'missing values and zero spread remain silent');
for(let i=0;i<4;i++)interval();
assert.deepEqual(seen,[0,1,2,3]);assert(ended);
console.log('PASS: measured HV playback, silent gaps and undefined spread');

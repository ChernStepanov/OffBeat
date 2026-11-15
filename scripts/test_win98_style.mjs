// Guards the Win98 look: no pale "modern" bluish panels or link-blue headings slipping back in.
// Controls use var(--face) grey, white fields, tooltip yellow or navy title bars instead.
import fs from 'node:fs';
import assert from 'node:assert/strict';

const css = fs.readFileSync('css/offbeat.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const hex = h => { h = h.slice(1); if (h.length === 3) h = [...h].map(c => c + c).join(''); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); };
const offenders = [];
for (const rule of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
  const [, selector, body] = rule;
  for (const decl of body.matchAll(/background(?:-color)?\s*:\s*([^;]+)/g)) {
    for (const [colour] of decl[1].matchAll(/#[0-9a-f]{6}\b|#[0-9a-f]{3}\b/gi)) {
      const [r, g, b] = hex(colour);
      // pale and visibly blue: the light panels Win98 never had
      if (Math.min(r, g, b) > 200 && b - r > 8) offenders.push(`${selector.trim()} -> ${colour}`);
    }
  }
  if (/#001b66/i.test(body)) offenders.push(`${selector.trim()} -> #001b66 text`);
}
assert.deepEqual(offenders, [], `Non-Win98 pale blue styling:\n${offenders.join('\n')}`);
console.log('PASS: no pale bluish panels in css/offbeat.css');

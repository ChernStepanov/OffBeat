// Deterministic frame rendering: set time, wait for images, screenshot. Usage:
//   node render.js frames            -> every frame at 30 fps into frames/
//   node render.js probe 1.2 5 9.3   -> single frames into probe/
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const [mode, ...times] = process.argv.slice(2);
const FPS = 30;
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/chromium-browser', headless: true, args: ['--hide-scrollbars', '--force-color-profile=srgb'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 960, height: 540, deviceScaleFactor: 2 });
  await page.goto('http://127.0.0.1:8766/index.html', { waitUntil: 'networkidle0' });
  await page.evaluate(() => window.ready);
  const duration = await page.evaluate(() => window.DURATION);
  const list = mode === 'probe' ? times.map(Number) : Array.from({ length: Math.round(duration * FPS) }, (_, i) => i / FPS);
  const dir = mode === 'probe' ? 'probe' : 'frames';
  fs.mkdirSync(dir, { recursive: true });
  const stage = await page.$('#stage');
  for (let k = 0; k < list.length; k++) {
    await page.evaluate(async t => { render(t); await Promise.all([...document.images].map(i => i.decode().catch(() => {}))); }, list[k]);
    const name = mode === 'probe' ? `${dir}/t${list[k].toFixed(2)}.png` : `${dir}/f${String(k).padStart(4, '0')}.jpg`;
    await stage.screenshot(mode === 'probe' ? { path: name } : { path: name, type: 'jpeg', quality: 94 });
    if (k % 60 === 0) console.log(k, '/', list.length);
  }
  console.log('duration', duration, 'frames', list.length);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });

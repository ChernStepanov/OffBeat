// Real screenshots of the running OffBeat app for the presentation video.
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const OUT = __dirname + '/stills';
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium-browser', headless: true,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--window-size=1920,1080', '--hide-scrollbars'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.evaluateOnNewDocument(() => { try { localStorage.setItem('offbeat.language.v1', 'en'); } catch (e) {} });
  const open = async url => {
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 90000 });
    await page.waitForFunction(() => window.OB && OB.app && OB.SITES && OB.SITES.length, { timeout: 60000 });
    await sleep(1500);
  };
  const tilesSettled = async (ms = 2500) => {
    await page.waitForFunction(() => ![...document.querySelectorAll('#map img.leaflet-tile')].some(i => !i.complete), { timeout: 30000 }).catch(() => {});
    await sleep(ms);
  };
  const maximise = async () => {
    await page.evaluate(() => { const b = document.getElementById('map-max'); if (!document.getElementById('map-win').classList.contains('win--max')) b.click(); });
    await sleep(800);
  };
  const shot = async (selector, name) => {
    const el = await page.$(selector);
    await el.screenshot({ path: `${OUT}/${name}.png` });
    console.log('saved', name);
  };

  // 1. world view with the measured-site pins and dated NISAR coverage
  await open('http://localhost:8765/?site=mexico');
  await maximise();
  await page.evaluate(() => document.querySelector('#regions button[data-region="world"]').click());
  await tilesSettled(6000);
  await shot('#map', 'world');

  // 2. Mexico City samples on every acquisition date
  await open('http://localhost:8765/?site=mexico');
  await maximise();
  await page.evaluate(() => { OB.app.fit(); });
  await tilesSettled(4000);
  await page.evaluate(() => OB.app.pickCell(258, false));
  await tilesSettled(2500);
  const dates = await page.evaluate(() => OB.app.site().dates);
  for (let i = 0; i < dates.length; i++) {
    await page.evaluate(i => OB.app.selectDate(i), i);
    await sleep(250);
    await shot('#map', `mex-${String(i).padStart(2, '0')}`);
  }
  await shot('#optic', 'mex-optic');
  fs.writeFileSync(`${OUT}/dates.json`, JSON.stringify(dates));

  // 3. GNSS-tied subsidence estimate layer
  await page.evaluate(() => {
    document.querySelectorAll('#side details').forEach(d => d.open = true);
    const box = document.querySelector('input[data-layer="opera_tied"]'); if (box && !box.checked) box.click();
    document.getElementById('l-offbeat').checked && document.getElementById('l-offbeat').click();
  });
  await sleep(1500);
  await shot('#map', 'subsidence');

  // 4. 3D terrain
  await open('http://localhost:8765/?site=mexico');
  await page.evaluate(() => document.getElementById('scene-open').click());
  await sleep(9000);
  await shot('#cloud-canvas', 'terrain');

  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });

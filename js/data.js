// Only prepared measured datasets may enter the application.
window.OB = window.OB || {};
OB.STYLE_KEYS = [null, 'drop', 'flood', 'drift', 'step'];
OB.SITES = [];
const CONTEXT = { amazon: { fires: 'fires.json', alerts: 'alerts.geojson', validation: 'validation.json' } };
OB.loadData = async function () {
  const results = await Promise.allSettled(['mexico', 'amazon', 'venezuela'].map(async id => {
    const response = await fetch(`data/${id}.json`);
    if (!response.ok) throw new Error(`${id}: data request failed (${response.status})`);
    const site = await response.json();
    if (/synthetic|mock/i.test(site.source || '') || !site.provenance?.inputs?.length) throw new Error(`${id}: measured provenance required`);
    const g = site.grid, count = g.n * g.n;
    if (site.id !== id || site.schema_version !== 2 || !Number.isInteger(g.n) || g.n < 1 || site.pixels.length !== count) throw new Error(`${id}: invalid site schema`);
    for (const p of site.pixels) {
      for (const arr of [p.hh, p.hv, ...Object.values(p.peer)]) {
        if (!Array.isArray(arr) || arr.length !== site.dates.length || arr.some(v => v !== null && !Number.isFinite(v))) throw new Error(`${id}: invalid series`);
      }
      if (p.disp !== null && (!Array.isArray(p.disp) || p.disp.length !== site.displacement_dates.length || p.disp.some(v => v !== null && !Number.isFinite(v)))) throw new Error(`${id}: invalid displacement`);
    }
    g.w = g.h = g.n;
    g.z = site.pixels.map(p => p.z);
    g.style = site.pixels.map(p => Math.max(0, OB.STYLE_KEYS.indexOf(p.style)));
    g.cover = site.pixels.map(p => p.cover);
    g.since = site.pixels.map(p => p.since ? site.dates.indexOf(p.since) : -1);
    site.series = (x, y) => site.pixels[y * g.n + x];
    // measured context next to a site (NASA FIRMS / INPE fires, INPE DETER / UMD GLAD alerts)
    site.context = {};
    for (const [key, file] of Object.entries(CONTEXT[id] || {})) {
      try { const r = await fetch(`data/${id}/${file}`); if (r.ok) site.context[key] = await r.json(); }
      catch (e) { console.warn(`${id}: ${file} unavailable`, e); }
    }
    return site;
  }));
  OB.SITES = results.filter(r => r.status === 'fulfilled').map(r => r.value);
  OB.dataErrors = results.filter(r => r.status === 'rejected').map(r => r.reason.message);
  if (!OB.SITES.length) throw new Error(OB.dataErrors.join('; '));
};

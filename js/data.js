// Real-data boundary. A failed request must never fall back to generated measurements.
window.OB = window.OB || {};
OB.STYLE_KEYS = [null, 'drop', 'flood', 'drift', 'step'];
OB.SITES = [];
OB.loadData = async function () {
  const response = await fetch('data/mexico.json');
  if (!response.ok) throw new Error(`Data request failed (${response.status})`);
  const site = await response.json();
  const g = site.grid, count = g.n * g.n;
  if (site.schema_version !== 2 || site.pixels.length !== count) throw new Error('Invalid site schema');
  for (const p of site.pixels) {
    for (const key of ['hh', 'hv']) {
      if (!Array.isArray(p[key]) || p[key].length !== site.dates.length || p[key].some(v => v !== null && !Number.isFinite(v))) throw new Error(`Invalid ${key} data`);
    }
  }
  g.z = site.pixels.map(p => p.z);
  g.style = site.pixels.map(p => Math.max(0, OB.STYLE_KEYS.indexOf(p.style)));
  g.cover = site.pixels.map(p => p.cover);
  g.since = site.pixels.map(p => p.since ? site.dates.indexOf(p.since) : -1);
  site.series = (x, y) => site.pixels[y * g.n + x];
  OB.SITES = [site];
};

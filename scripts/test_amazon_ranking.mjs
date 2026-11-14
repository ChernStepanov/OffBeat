import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const context = { window: {} }; context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('js/amazon-ranking.js', 'utf8'), context);
const appSource = fs.readFileSync('js/app.js', 'utf8');
assert.match(appSource, /ranking\.load\(fetch, 'data\/amazon-ranking-experiment\.json'\)/, 'app uses the tested async loader');
assert.match(appSource, /ranking\.setVisible\(!!site && site\.id === 'amazon'\)/, 'place search explicitly owns visibility');
assert.match(appSource, /ranking\.setVisible\(s\.id === 'amazon'\)/, 'site navigation explicitly owns visibility');

function control(value = '') {
  return { value, hidden: false, textContent: '', listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; }, change(value) { this.value = value; this.listeners.change(); } };
}
const markers = [];
const map = { layers: [], removeLayer(layer) { this.layers = this.layers.filter(x => x !== layer); } };
const leaflet = {
  circleMarker(coords) { const marker = { coords, events: {}, bindTooltip(text) { this.tooltip = text; return this; }, on(type, fn) { this.events[type] = fn; return this; } }; markers.push(marker); return marker; },
  layerGroup(items) { return { items, addTo(target) { target.layers.push(this); return this; } }; },
  DomEvent: { stopPropagation() {} }
};
const panel = control(), pol = control('hh'), radius = control('5x5'), status = control();
const picked = [];
const ui = context.OB.amazonRanking({ map, leaflet, panel, polarization: pol, radius, status, onPick: p => picked.push(p.row) });
const signal = (raw, residual, validClass = true) => ({ raw_change_db: raw, neighbor_median_db: residual == null ? null : -1, residual_db: residual, paired_neighbors: 4, valid_class_pair: validClass, rank: 1, rank_population: 10 });
const points = [
  { row: 0, col: 0, lat: 1, lon: 1, worldcover_code: 10, signals: { hh: { '5x5': signal(-5, -4) } } },
  { row: 1, col: 1, lat: 2, lon: 2, worldcover_code: 30, signals: { hh: { '5x5': signal(2.5, null, false) } } },
  { row: 2, col: 2, lat: 3, lon: 3, worldcover_code: 10, signals: { hh: { '5x5': signal(null, null) } } }
];
ui.setData({ points, event_window: ['2026-08-23', '2026-09-04'], minimum_local_peers: 3 });
ui.setVisible(true);
assert.equal(panel.hidden, false);
assert.match(markers[1].tooltip, /Valid HH observation.*WorldCover 30.*no class-10 rank/);
assert.match(markers[2].tooltip, /No signal.*missing paired observation or insufficient/);
markers[1].events.click({});
assert.deepEqual(picked, [1], 'unrankable class-30 point still selects its pixel/plots');
assert.match(status.textContent, /valid raw change 2.50 dB.*not class 10.*no class-10 rank/);
markers[2].events.click({});
assert.deepEqual(picked, [1, 2], 'missing-value point still selects its pixel/plots');
assert.match(status.textContent, /no signal.*valid class-10 pair/i);
radius.change('3x3');
assert.equal(status.textContent, 'Choose a sampled point.', 'changing the window clears stale detail');
assert.equal(map.layers.length, 1, 'redraw replaces layer');
ui.setVisible(false);
assert.equal(panel.hidden, true);
assert.equal(map.layers.length, 0, 'hiding removes stale dots');
ui.setVisible(true);
assert.equal(panel.hidden, false, 'return to Amazon reopens the panel');
assert.equal(map.layers.length, 1);
ui.setVisible(false); ui.setError('HTTP 404'); ui.setVisible(true);
assert.equal(panel.hidden, false);
assert.match(status.textContent, /ranking data unavailable: HTTP 404/i);
assert.equal(map.layers.length, 0, 'failed payload never creates an empty-looking point layer');

// Same async loader used by app.js: navigation visibility must win over late success/failure.
ui.setVisible(false);
let resolveResponse;
const delayedSuccess = ui.load(() => new Promise(resolve => { resolveResponse = resolve; }), 'ranking.json');
await Promise.resolve();
ui.setVisible(true); // open Amazon while request is pending
ui.setVisible(false); // search outside prepared coverage (state.site may still be Amazon)
resolveResponse({ ok: true, json: async () => ({ points, event_window: ['2026-08-23', '2026-09-04'], minimum_local_peers: 3 }) });
await delayedSuccess;
assert.equal(panel.hidden, true, 'late success cannot reopen an off-site panel');
assert.equal(map.layers.length, 0, 'late success cannot create markers off-site');
ui.setVisible(true); // navigate back to Amazon after response
assert.equal(panel.hidden, false);
assert.equal(map.layers.length, 1, 'return to Amazon renders loaded points');

ui.setVisible(false);
let rejectResponse;
const delayedFailure = ui.load(() => new Promise((_, reject) => { rejectResponse = reject; }), 'ranking.json');
await Promise.resolve();
ui.setVisible(true);
ui.setVisible(false);
rejectResponse(new Error('network unavailable'));
await delayedFailure;
assert.equal(panel.hidden, true, 'late failure cannot reopen an off-site panel');
assert.equal(map.layers.length, 0);
ui.setVisible(true);
assert.equal(panel.hidden, false);
assert.match(status.textContent, /ranking data unavailable: network unavailable/i, 'return to Amazon exposes the stored load error');
assert.equal(map.layers.length, 0);
console.log('PASS: Amazon ranking interactions, unrankable selection, status reset, delayed-load navigation races and errors');

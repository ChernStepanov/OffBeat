// Retrospective point/alert screen. This is candidate triage, not event validation.
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const sitePath = 'data/amazon.json', alertsPath = 'data/amazon/alerts.geojson';
const read = path => JSON.parse(fs.readFileSync(path));
const hash = path => createHash('sha256').update(fs.readFileSync(path)).digest('hex');
const site = read(sitePath), alerts = read(alertsPath);
function inRing([x, y], ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}
function insidePolygon(point, polygon) {
  return inRing(point, polygon[0]) && !polygon.slice(1).some(ring => inRing(point, ring));
}
const first = site.dates[1], last = site.dates.at(-1);
let considered = 0, unsupported = 0, matches = [];
for (const [index, feature] of alerts.features.entries()) {
  const d = feature.properties.date;
  if (!d || d <= first || d > last) continue;
  considered++;
  const {type, coordinates} = feature.geometry || {};
  const polygons = type === 'Polygon' ? [coordinates] : type === 'MultiPolygon' ? coordinates : null;
  if (!polygons) { unsupported++; continue; }
  for (const p of site.pixels) {
    if (p.cover !== 10) continue;
    if (polygons.some(poly => poly.length && insidePolygon([p.lon, p.lat], poly)))
      matches.push({point_id: p.id, alert_index: index, alert_date: d, source: feature.properties.source, alert_class: feature.properties.class});
  }
}
const report = {input_sha256: {[sitePath]: hash(sitePath), [alertsPath]: hash(alertsPath)},
  alert_window: {after: first, through: last}, alert_records: considered,
  unsupported_geometries: unsupported, tree_cover_points: site.pixels.filter(p => p.cover === 10).length,
  point_alert_matches: matches,
  limitations: ['Retrospective development AOI, not an independent test.', 'Alert date is not necessarily the change date.', 'Geometries were not repaired; boundary cases may be excluded.', 'Local alert subset is not a complete archive. No match is not a stable-ground label.', 'Spatial intersections do not establish cause, event timing, area, precision or recall.']};
console.log(JSON.stringify(report, null, 2));

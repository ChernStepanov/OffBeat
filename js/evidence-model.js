// Pure evidence / link helpers. Missing measurements remain null, never zero.
window.OB = window.OB || {};
OB.evidenceModel = (() => {
  const finite = x => Number.isFinite(x) ? x : null;
  function timeline(dates) {
    if (!dates.length) return [];
    const times = dates.map(date => Date.parse(date + 'T00:00:00Z'));
    if (times.some(t => !Number.isFinite(t)) || times.some((t, i) => i > 0 && t <= times[i - 1]))
      throw new Error('Timeline dates must be valid and strictly increasing');
    const span = times.at(-1) - times[0];
    return times.map(t => span ? (t - times[0]) / span : 0.5);
  }
  function link(base, site, pixel, date, caseId, step = 0) {
    const url = new URL(base);
    for (const key of ['lat', 'lon', 'view', 'case', 'sample', 'date', 'step', 'candidate']) url.searchParams.delete(key);
    url.hash = '';
    url.searchParams.set('site', site.id);
    url.searchParams.set('sample', String(site.pixels.findIndex(p => p.id === pixel.id)));
    url.searchParams.set('date', site.dates[date]);
    if (caseId) url.searchParams.set('case', caseId);
    url.searchParams.set('step', String(step + 1));
    return url.href;
  }
  function selection(params, sites, cases) {
    const c = cases.find(c => c.id === params.get('case'));
    const site = sites.find(s => s.id === (params.get('site') || c?.site));
    if (!site) return null;
    const raw = params.get('sample');
    const index = raw === null && c ? c.sample_index : (/^(0|[1-9]\d*)$/.test(raw || '') ? Number(raw) : -1);
    if (!site.pixels[index]) return null;
    const date = params.has('date') ? site.dates.indexOf(params.get('date')) : (c ? c.radar_pair[1] : site.dates.length - 1);
    if (date < 0) return null;
    return {site, index, date, caseId: c && c.site === site.id && c.sample_index === index ? c.id : null,
      step: /^[1-4]$/.test(params.get('step') || '') ? Number(params.get('step')) - 1 : 0};
  }
  function report(site, pixel, date, dossier, book, permalink, language) {
    return {
      schema_version: 1, type: 'OffBeatEvidence', site: site.id, sample_id: pixel.id,
      coordinates: {lat: pixel.lat, lon: pixel.lon}, selected_date: site.dates[date], permalink,
      observations: site.dates.map((d, i) => ({date: d, hv_db: finite(pixel.hv?.[i]), hh_db: finite(pixel.hh?.[i]),
        same_class_peer_hv_median_db: finite(pixel.peer?.hv_med?.[i]),
        same_class_peer_hv_sd_db: finite(pixel.peer?.hv_sd?.[i]),
        hv_peer_count: finite(pixel.peer_counts?.hv?.[i]), peer_z_hv: finite(pixel.z_hv?.[i])})),
      quality: {valid_hv_observations: pixel.hv.filter(Number.isFinite).length, total_dates: site.dates.length,
        historical_worldcover_2021: pixel.cover, note: 'WorldCover is historical context. Backscatter quality does not validate displacement or an event cause.'},
      dataset_provenance: site.provenance,
      case: dossier ? JSON.parse(JSON.stringify(dossier)) : null,
      independent_event_status: dossier?.status || 'not_reviewed',
      evaluation: book.evaluation,
      source_sha256: dossier ? Object.fromEntries(dossier.sources.filter(s => book.input_sha256[s]).map(s => [s, book.input_sha256[s]])) : {},
      limitations: [book.policy, 'Six-date, sparse development sample. Sample spacing is not event area. No validated accuracy or operational alarm is claimed.'],
      language,
    };
  }
  function geojson(report) {
    return {type: 'FeatureCollection', features: [{type: 'Feature', geometry: {type: 'Point',
      coordinates: [report.coordinates.lon, report.coordinates.lat]}, properties: report}]};
  }
  function nextSurprise(ids, history, current, random = Math.random) {
    const available = [...new Set(ids)], seen = Array.isArray(history) ? history.filter(id => available.includes(id)) : [];
    if (!available.length) return null;
    let candidates = available.filter(id => !seen.includes(id));
    const cycle = candidates.length ? seen : [];
    if (!candidates.length) candidates = available;
    const previous = current || seen.at(-1);
    if (candidates.length > 1) candidates = candidates.filter(id => id !== previous);
    const id = candidates[Math.floor(random() * candidates.length)];
    return {id, history: [...cycle, id]};
  }
  function opticalCrop(bounds, pixel) {
    const x = (pixel.lon - bounds.w) / (bounds.e - bounds.w);
    const y = (bounds.n - pixel.lat) / (bounds.n - bounds.s);
    const clamp = value => Math.max(0, Math.min(0.5, value - 0.25));
    const left = clamp(x), top = clamp(y);
    return {left: -200 * left, top: -200 * top, x: 200 * (x - left), y: 200 * (y - top)};
  }
  return {timeline, link, selection, report, geojson, nextSurprise, opticalCrop};
})();

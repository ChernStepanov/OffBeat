// Interactive sampled-point experiment layer; deliberately draws dots, never polygons.
window.OB = window.OB || {};
OB.amazonRanking = function ({ map, leaflet, panel, polarization, radius, status, onPick }) {
  let data = null, error = null, layer = null, visible = false;
  const clearLayer = () => { if (layer) map.removeLayer(layer); layer = null; };
  function render() {
    clearLayer();
    status.textContent = 'Choose a sampled point.';
    if (!visible) return;
    if (error) { status.textContent = `Amazon ranking data unavailable: ${error}. Reload after restoring data/amazon-ranking-experiment.json.`; return; }
    if (!data) { status.textContent = 'Loading Amazon ranking data…'; return; }
    const pol = polarization.value, windowSize = radius.value;
    const markers = (data.points || []).map(point => {
      const signal = point.signals?.[pol]?.[windowSize];
      const residual = signal?.residual_db;
      const marker = leaflet.circleMarker([point.lat, point.lon], {
        radius: 4, color: '#fff', weight: 1,
        fillColor: Number.isFinite(residual) ? (residual < 0 ? '#c00000' : '#0040c0') : '#777', fillOpacity: .9
      });
      const validOtherClass = signal?.valid_class_pair === false && signal?.raw_change_db != null;
      marker.bindTooltip(Number.isFinite(residual)
        ? `${pol.toUpperCase()} corrected change ${residual.toFixed(2)} dB`
        : validOtherClass
          ? `Valid ${pol.toUpperCase()} observation; WorldCover ${point.worldcover_code}, not target class 10; no class-10 rank`
          : 'No signal: missing paired observation or insufficient same-class neighbors');
      marker.on('click', event => {
        leaflet.DomEvent.stopPropagation(event);
        onPick(point);
        const location = `Point ${point.row}, ${point.col} · WorldCover 2021 ${point.worldcover_code} · ${pol.toUpperCase()} ${data.event_window.join(' → ')}`;
        if (validOtherClass) {
          status.textContent = `${location}: valid raw change ${signal.raw_change_db.toFixed(2)} dB, but this is not class 10 and has no class-10 rank or correction. Cause unknown.`;
        } else if (!signal || !Number.isFinite(signal.residual_db)) {
          status.textContent = `${location}: no signal; raw change ${Number.isFinite(signal?.raw_change_db) ? signal.raw_change_db.toFixed(2) + ' dB' : 'unavailable'}; correction requires a valid class-10 pair and at least ${data.minimum_local_peers} same-class neighbors. Cause unknown.`;
        } else {
          status.textContent = `${location}: raw change ${signal.raw_change_db.toFixed(2)} dB; neighbor median ${signal.neighbor_median_db.toFixed(2)} dB; corrected ${signal.residual_db.toFixed(2)} dB; ${signal.paired_neighbors} same-class neighbors in ${windowSize}. Rank ${signal.rank}/${signal.rank_population} in sample, not probability; cause unknown.`;
        }
      });
      return marker;
    });
    layer = leaflet.layerGroup(markers).addTo(map);
  }
  polarization.addEventListener('change', render);
  radius.addEventListener('change', render);
  return {
    // Data completion never changes navigation visibility; the app owns that state.
    setData(value) { data = value; error = null; render(); },
    setError(value) { data = null; error = String(value); render(); },
    load(fetcher, url) {
      return Promise.resolve().then(() => fetcher(url)).then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      }).then(value => { data = value; error = null; render(); return value; }, reason => {
        data = null; error = reason && reason.message ? reason.message : String(reason); render(); return null;
      });
    },
    setVisible(value) {
      visible = Boolean(value);
      panel.hidden = !visible;
      if (!visible) { clearLayer(); status.textContent = 'Choose a sampled point.'; }
      else render();
    },
    render
  };
};

window.OB = window.OB || {};

OB.bindWaterLabels = function (maps, status) {
  const item = 'https://www.arcgis.com/sharing/rest/content/items/94329802cbfa44a18f423e6f1a0b875c';
  let layers = [], loading = false, visible = true;

  for (const map of maps) {
    const pane = map.createPane('waterLabels');
    pane.style.zIndex = 630;
    pane.style.pointerEvents = 'none';
  }

  async function update(show) {
    visible = show;
    status.hidden = true;
    if (!visible) {
      maps.forEach((map, index) => { if (layers[index]) map.removeLayer(layers[index]); });
      return;
    }
    if (loading) return;
    loading = true;
    try {
      if (!layers.length) {
        if (!L.maplibreGL || !window.maplibregl?.supported()) throw new Error('WebGL unavailable');
        const response = await fetch(`${item}/resources/styles/root.json`, {
          signal: AbortSignal.timeout(12000),
        });
        if (!response.ok) throw new Error('Water style unavailable');
        const style = await response.json();
        const source = style.sources.esri;
        const metadata = await fetch(`${source.url}?f=json`, { signal: AbortSignal.timeout(12000) });
        if (!metadata.ok) throw new Error('Water tiles unavailable');
        const { tiles, maxzoom, minzoom } = await metadata.json();
        if (!tiles?.length) throw new Error('No water tiles');
        style.sources.esri = {
          type: 'vector',
          tiles: tiles.map(path => `${source.url}/${path}`),
          minzoom, maxzoom,
        };
        style.layers = style.layers.filter(layer => layer.type === 'symbol' &&
          /^(Water |Marine waterbody)|^Ocean .*waterbody|^Disputed label point\/Waterbody$/i.test(layer.id) &&
          !/island|dam or weir|playa/i.test(layer.id)).map(layer => ({
          ...layer,
          paint: { ...layer.paint, 'text-color': '#d8f4ff', 'text-halo-color': '#153649', 'text-halo-width': 1.5 },
        }));
        layers = maps.map(() => L.maplibreGL({
          style, pane: 'waterLabels', interactive: false, attributionControl: false,
          attribution: 'Water names &copy; Esri',
        }));
      }
      if (visible) {
        maps.forEach((map, index) => map.whenReady(() => {
          if (visible) layers[index]?.addTo(map);
        }));
      }
    } catch {
      maps.forEach((map, index) => { if (layers[index]) map.removeLayer(layers[index]); });
      layers = [];
      status.textContent = 'Water labels unavailable.';
      status.hidden = !visible;
    } finally {
      loading = false;
    }
  }

  update(true);
  return update;
};

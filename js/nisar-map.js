window.OB = window.OB || {};

OB.bindNisarMap = function (map, toggle, status) {
  const base = 'https://gibs.earthdata.nasa.gov';
  const product = 'NISAR_L2_Geocoded_Polarimetric_Covariance';
  const matrix = 'GoogleMapsCompatible_Level13';
  const mosaicDays = 12;
  const day = 86400000;
  const tileSize = 256;
  const nativeZoom = 13;
  const tiles = new Set();
  let layer, loading, caption;
  const blockSize = () => Math.max(1, 16 / 2 ** Math.max(0, map.getZoom() - nativeZoom));

  map.createPane('nisarRadar');
  map.getPane('nisarRadar').style.zIndex = 250;
  map.getPane('nisarRadar').style.pointerEvents = 'none';

  async function getDates() {
    const response = await fetch(`${base}/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml`, {
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) throw new Error('GIBS capabilities unavailable');
    const xml = new DOMParser().parseFromString(await response.text(), 'application/xml');
    const children = (node, name) => [...node.children].filter(child => child.localName === name);
    const source = [...xml.getElementsByTagNameNS('*', 'Layer')].find(node =>
      children(node, 'Identifier')[0]?.textContent === product);
    const time = children(source, 'Dimension').find(node =>
      children(node, 'Identifier')[0]?.textContent === 'Time');
    const end = Date.parse(children(time, 'Default')[0]?.textContent);
    const ranges = children(time, 'Value').map(node => {
      const [first, last = first] = node.textContent.trim().split('/');
      return [Date.parse(first), Date.parse(last)];
    });
    if (!Number.isFinite(end)) throw new Error('GIBS returned no default date');
    const dates = [];
    for (let date = end - (mosaicDays - 1) * day; date <= end; date += day) {
      if (ranges.some(([first, last]) => date >= first && date <= last)) {
        dates.push(new Date(date).toISOString().slice(0, 10));
      }
    }
    if (!dates.length) throw new Error('GIBS returned no mosaic dates');
    return dates;
  }

  function createMosaic(dates) {
    const Mosaic = L.GridLayer.extend({
      createTile(coords, done) {
        const tile = document.createElement('canvas');
        tile.width = tile.height = tileSize;
        tile.style.imageRendering = 'pixelated';
        const context = tile.getContext('2d');
        const images = dates.map(date => new Promise(resolve => {
          const image = new Image();
          image.crossOrigin = 'anonymous';
          image.onload = () => resolve(image);
          image.onerror = () => resolve(null);
          image.src = `${base}/wmts/epsg3857/best/${product}/default/${date}/${matrix}/${coords.z}/${coords.y}/${coords.x}.png`;
        }));
        Promise.all(images).then(loaded => {
          // Paint oldest first so newer acquisitions cover older ones.
          for (const image of loaded) if (image) context.drawImage(image, 0, 0);
          if (!loaded.some(Boolean)) {
            done(new Error('NISAR tiles unavailable'), tile);
            return;
          }
          try {
            tile.radar = { coords, pixels: context.getImageData(0, 0, tileSize, tileSize) };
            colorTile(tile);
            done(null, tile);
          } catch (error) {
            context.clearRect(0, 0, tileSize, tileSize);
            done(error, tile);
          }
        });
        return tile;
      },
    });
    const mosaic = new Mosaic({
      pane: 'nisarRadar', maxNativeZoom: nativeZoom, maxZoom: 19, opacity: 0.9,
      attribution: 'Radar &copy; NASA/ISRO NISAR, NASA GIBS',
    });
    mosaic.on('tileload', e => tiles.add(e.tile));
    mosaic.on('tileunload', e => tiles.delete(e.tile));
    return mosaic;
  }

  function colorTile(tile) {
    const size = blockSize();
    const context = tile.getContext('2d');
    const small = document.createElement('canvas');
    small.width = small.height = tileSize / size;
    const reduced = small.getContext('2d');
    context.putImageData(tile.radar.pixels, 0, 0);
    reduced.drawImage(tile, 0, 0, small.width, small.height);
    const image = reduced.getImageData(0, 0, small.width, small.height);
    const pixels = image.data;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] === 0) continue;
      // Brightness of the NASA browse image on a display-only ramp.
      const strength = Math.round(0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2]);
      pixels[i] = strength;
      pixels[i + 1] = 70;
      pixels[i + 2] = 255 - strength;
      pixels[i + 3] = 255;
    }
    tile.radar.cells = image;
    reduced.putImageData(image, 0, 0);
    context.clearRect(0, 0, tileSize, tileSize);
    context.imageSmoothingEnabled = false;
    context.drawImage(small, 0, 0, tileSize, tileSize);
  }

  async function update() {
    status.hidden = !toggle.checked;
    if (!toggle.checked) {
      if (layer) map.removeLayer(layer);
      return;
    }
    if (loading) return;
    loading = true;
    try {
      if (!layer) {
        status.textContent = 'Loading NISAR radar coverage…';
        const dates = await getDates();
        layer = createMosaic(dates);
        caption = `NASA NISAR | ${mosaicDays}-day mosaic through ${dates.at(-1)} | Blue to red: image brightness`;
      }
      if (toggle.checked) {
        layer.addTo(map);
        status.textContent = caption;
      }
    } catch {
      status.textContent = 'NASA radar imagery unavailable. Toggle the layer to retry.';
    } finally {
      loading = false;
    }
  }

  toggle.addEventListener('change', update);
  map.whenReady(update);
  let previousSize = blockSize();
  map.on('zoomend', () => {
    const size = blockSize();
    if (size === previousSize) return;
    previousSize = size;
    for (const tile of tiles) colorTile(tile);
  });

  return function cellBounds(latlng) {
    if (!toggle.checked || !layer || !map.hasLayer(layer)) return null;
    const zoom = Math.min(map.getZoom(), nativeZoom);
    const point = map.project(latlng, zoom);
    const column = Math.floor(point.x / tileSize);
    const row = Math.floor(point.y / tileSize);
    const wrapped = L.Util.wrapNum(column, [0, 2 ** zoom]);
    for (const { radar: { coords, cells } } of tiles) {
      if (coords.z !== zoom || coords.x !== wrapped || coords.y !== row) continue;
      const size = tileSize / cells.width;
      const x = Math.floor((point.x - column * tileSize) / size);
      const y = Math.floor((point.y - row * tileSize) / size);
      if (!cells.data[(y * cells.width + x) * 4 + 3]) return null;
      const origin = L.point(column * tileSize + x * size, row * tileSize + y * size);
      return [map.unproject(origin, zoom), map.unproject(origin.add([size, size]), zoom)];
    }
    return null;
  };
};

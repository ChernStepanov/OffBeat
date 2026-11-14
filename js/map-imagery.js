// Keep a low-resolution Esri fallback underneath detailed tiles. Esri sometimes returns
// a successful JPEG containing its grey "Map data not yet available" placeholder.
window.OB = window.OB || {};
OB.bindImagery = function (map, url, options) {
  const base = L.tileLayer(url, {...options, maxNativeZoom: 16, maxZoom: 19}).addTo(map);
  const Detailed = L.TileLayer.extend({
    createTile(coords, done) {
      return L.TileLayer.prototype.createTile.call(this, coords, (error, image) => {
        if (!error) {
          try {
            const canvas = document.createElement('canvas');
            canvas.width = 4; canvas.height = 1;
            const ctx = canvas.getContext('2d', {willReadFrequently: true});
            // Match the pink mark and three flat corners in Esri's placeholder JPEG.
            [[157,89],[20,20],[220,20],[20,220]].forEach(([x,y],i) => ctx.drawImage(image, x, y, 1, 1, i, 0, 1, 1));
            const p = ctx.getImageData(0, 0, 4, 1).data;
            const pink = p[0] === 235 && p[1] === 151 && p[2] === 175;
            const grey = [4,8,12].every(i => p[i] === 204 && p[i+1] === 204 && p[i+2] === 204);
            if (pink && grey) image.style.visibility = 'hidden';
          } catch (_) { /* A CORS failure must not hide usable imagery. */ }
        }
        done(error, image);
      });
    }
  });
  // Keep each available level underneath the next: if level 19 is missing,
  // level 18 or 17 is sharper than jumping directly back to level 16.
  const details = [17, 18, 19].map(level => new Detailed(url, {
    ...options, crossOrigin: 'anonymous', minZoom: level,
    maxNativeZoom: level, maxZoom: 19, keepBuffer: 1,
  }).addTo(map));
  return {base, details, setUrl(next) { for (const layer of [base, ...details]) layer.setUrl(next); }};
};

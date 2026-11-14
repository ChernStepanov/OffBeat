// Geographic registration is shared by the DEM mesh and the unchanged NISAR sample positions.
window.OB = window.OB || {};
OB.terrain = (() => {
  const R = 6371008.8, DEG = Math.PI / 180;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function validate(data, site) {
    const b = data?.bbox;
    if (data?.schema_version !== 1 || data.kind !== 'measured_dem_context' || data.site !== site.id ||
        !Number.isInteger(data.n) || data.n < 2 || data.n > 1025 || !Array.isArray(data.height_m) ||
        data.height_m.length !== data.n ** 2 || !data.height_m.every(Number.isFinite) ||
        !b || ![b.w, b.e, b.s, b.n, data.min_m, data.max_m].every(Number.isFinite) || b.e <= b.w || b.n <= b.s ||
        data.min_m > data.max_m || !data.provenance?.sources?.length) throw new Error('Invalid measured DEM');
    const study = site.grid.bbox;
    if (study.w < b.w || study.e > b.e || study.s < b.s || study.n > b.n) throw new Error('DEM does not cover the study area');
    return data;
  }
  function frame(data) {
    const b = data.bbox, lon = (b.w + b.e) / 2, lat = (b.s + b.n) / 2;
    const cosine = Math.cos(lat * DEG), width = (b.e - b.w) * DEG * R * cosine, depth = (b.n - b.s) * DEG * R;
    return { lon, lat, cosine, scale: 2 / Math.max(width, depth), width_m: width, depth_m: depth, base_m: Math.floor(data.min_m / 25) * 25 - 25 };
  }
  function heightAt(data, lon, lat) {
    const b = data.bbox, n = data.n;
    if (![lon, lat].every(Number.isFinite) || lon < b.w - 1e-9 || lon > b.e + 1e-9 || lat < b.s - 1e-9 || lat > b.n + 1e-9) return null;
    const x = clamp((lon - b.w) / (b.e - b.w) * (n - 1), 0, n - 1);
    const y = clamp((b.n - lat) / (b.n - b.s) * (n - 1), 0, n - 1);
    const x0 = Math.min(n - 2, Math.floor(x)), y0 = Math.min(n - 2, Math.floor(y)), fx = x - x0, fy = y - y0;
    const a = data.height_m[y0 * n + x0], c = data.height_m[(y0 + 1) * n + x0];
    const v = (1 - fy) * (a * (1 - fx) + data.height_m[y0 * n + x0 + 1] * fx)
      + fy * (c * (1 - fx) + data.height_m[(y0 + 1) * n + x0 + 1] * fx);
    return Number.isFinite(v) ? v : null;
  }
  function position(data, lon, lat, exaggeration = 1) {
    const height = heightAt(data, lon, lat); if (height === null) return null;
    const f = frame(data);
    return { x: (lon - f.lon) * DEG * R * f.cosine * f.scale,
      y: (height - f.base_m) * f.scale * exaggeration,
      z: (f.lat - lat) * DEG * R * f.scale, height_m: height };
  }
  function samples(site, date, channel, data, exaggeration = 1) {
    if (!data || !site?.dates[date] || !['hh', 'hv'].includes(channel)) return [];
    return site.pixels.flatMap((p, index) => {
      const value = p[channel]?.[date]; if (!Number.isFinite(value)) return [];
      const pos = position(data, p.lon, p.lat, exaggeration); if (!pos) return [];
      // Small fixed clearance avoids z-fighting; signal never changes geometric elevation.
      return [{ index, value, ...pos, y: pos.y + .004, lat: p.lat, lon: p.lon, color: OB.pointCloud.color(value) }];
    });
  }
  function color(height, low, high) {
    const stops = [[34, 49, 39], [73, 89, 56], [126, 130, 76], [172, 153, 96], [203, 191, 145], [227, 223, 198]];
    const t = clamp((height - low) / (high - low || 1), 0, 1) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(t)), f = t - i;
    return stops[i].map((v, j) => Math.round(v + (stops[i + 1][j] - v) * f));
  }
  return { validate, frame, heightAt, position, samples, color };
})();

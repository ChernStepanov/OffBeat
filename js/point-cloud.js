// A small, dependency-free projection of measured SAR samples, not a terrain model.
window.OB = window.OB || {};
OB.pointCloud = (() => {
  const LOW = -35, HIGH = 5;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const stops = [[71, 134, 207], [68, 196, 191], [218, 215, 132], [255, 157, 94], [231, 99, 97]];
  function color(value) {
    if (!Number.isFinite(value)) return null;
    const t = clamp((value - LOW) / (HIGH - LOW), 0, 1) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(t)), f = t - i;
    return stops[i].map((v, j) => Math.round(v + (stops[i + 1][j] - v) * f));
  }
  function samples(site, date, channel) {
    if (!site?.pixels || !site.dates?.[date] || !['hh', 'hv'].includes(channel)) return [];
    const b = site.grid.bbox, midlat = (b.s + b.n) * Math.PI / 360;
    const width = (b.e - b.w) * Math.cos(midlat), depth = b.n - b.s;
    const scale = Math.max(width, depth);
    if (!(scale > 0)) return [];
    return site.pixels.flatMap((p, index) => {
      const value = p[channel]?.[date];
      if (![p.lat, p.lon, value].every(Number.isFinite)) return [];
      return [{ index, value, x: (p.lon - (b.w + b.e) / 2) * Math.cos(midlat) / scale * 2,
        y: (p.lat - (b.s + b.n) / 2) / scale * 2,
        z: (value - LOW) / (HIGH - LOW) * 1.25, color: color(value) }];
    });
  }
  function project(point, camera, width, height) {
    const c = Math.cos(camera.yaw), s = Math.sin(camera.yaw);
    const x = point.x * c - point.y * s, depth = point.x * s + point.y * c;
    const cp = Math.cos(camera.pitch), sp = Math.sin(camera.pitch);
    const vertical = depth * sp + (point.z - .45) * cp;
    const distance = depth * cp - (point.z - .45) * sp;
    const perspective = Math.abs(cp) < 1e-8 ? 1 : 5 / Math.max(1, 5 + distance);
    const scale = Math.min(width * .31, height * .31) * camera.zoom * perspective;
    return { x: width / 2 + x * scale, y: height * .54 - vertical * scale, depth: distance, perspective };
  }
  function hitTest(points, x, y, radius = 10) {
    // Prefer the nearest dot; equal-distance overlaps resolve to the frontmost one.
    let best = null, distance = radius;
    for (let i = points.length - 1; i >= 0; i--) {
      const candidate = Math.hypot(points[i].x - x, points[i].y - y);
      if (candidate <= radius && (best === null || candidate < distance - 1e-6)) { best = points[i]; distance = candidate; }
    }
    return best;
  }
  return { LOW, HIGH, clamp, color, samples, project, hitTest };
})();

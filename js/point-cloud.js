// Signal colours are independent of geographic elevation in the 3D terrain view.
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
  function hitTest(points, x, y, radius = 10) {
    // Prefer the nearest dot; equal-distance overlaps resolve to the frontmost one.
    let best = null, distance = radius;
    for (let i = points.length - 1; i >= 0; i--) {
      const candidate = Math.hypot(points[i].x - x, points[i].y - y);
      if (candidate <= radius && (best === null || candidate < distance - 1e-6)) { best = points[i]; distance = candidate; }
    }
    return best;
  }
  return { LOW, HIGH, clamp, color, hitTest };
})();

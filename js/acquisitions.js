// Acquisition-specific measured HV values; never substitute another date for a gap.
window.OB = window.OB || {};
OB.acquisitions = {
  available(site, index) {
    return site.pixels.filter(p => Number.isFinite(p.hv[index])).length;
  },
  color(value) {
    if (!Number.isFinite(value)) return null;
    const q = Math.max(0, Math.min(1, (value + 25) / 25));
    return [Math.round(255 * q), 70, Math.round(255 * (1 - q)), 180];
  }
};

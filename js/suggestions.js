// Rank at most one measured, quality-valid peer deviation per prepared site.
window.OB = window.OB || {};
OB.suggestPlaces = function(sites, threshold = 2.5, limit = 3) {
  return sites.flatMap(site => {
    if (!site || !Array.isArray(site.pixels) || !Array.isArray(site.dates) || !site.dates.length) return [];
    const candidates = site.pixels.map((pixel,index) => ({pixel,index}))
      .filter(({pixel}) => Number.isFinite(pixel.z) && Math.abs(pixel.z) >= threshold && pixel.cover !== 80 &&
        Array.isArray(pixel.hv) && Number.isFinite(pixel.hv[site.dates.length-1]));
    candidates.sort((a,b) => Math.abs(b.pixel.z)-Math.abs(a.pixel.z) || a.index-b.index);
    return candidates.length ? [{site, ...candidates[0]}] : [];
  }).sort((a,b) => Math.abs(b.pixel.z)-Math.abs(a.pixel.z) || a.site.id.localeCompare(b.site.id)).slice(0,limit);
};

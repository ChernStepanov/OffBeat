// Coordinate parsing is local; never forward malformed coordinate input to a geocoder.
window.OB = window.OB || {};
OB.parseCoordinates = function (input) {
  const s = input.trim();
  if (!/^[+\-\d.,\s]+$/.test(s)) return { kind: 'place' };
  const m = s.match(/^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:,|\s)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$/);
  if (!m) return { kind: 'invalid' };
  const lat = Number(m[1]), lon = Number(m[2]);
  if (Math.abs(lat) > 85.05112878 || Math.abs(lon) > 180) return { kind: 'invalid' };
  return { kind: 'coordinates', lat, lon };
};

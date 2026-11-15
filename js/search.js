// Coordinate parsing is local; never forward malformed coordinate input to a geocoder.
window.OB = window.OB || {};
OB.normalizePlaceQuery = input => input.normalize('NFKC').replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, '').trim().replace(/\s+/g, ' ');
OB.geocodePlace = async function (query, photon) {
  const languages = window.navigator?.languages || [window.navigator?.language || 'en'];
  const scripts = [[/\p{Script=Arabic}/u,'ar'],[/\p{Script=Hiragana}|\p{Script=Katakana}/u,'ja'],
    [/\p{Script=Han}/u,'zh'],[/\p{Script=Hangul}/u,'ko'],[/\p{Script=Devanagari}/u,'hi'],
    [/\p{Script=Hebrew}/u,'he'],[/\p{Script=Greek}/u,'el'],[/\p{Script=Thai}/u,'th'],
    [/\p{Script=Cyrillic}/u,'ru']];
  const language = scripts.find(([pattern]) => pattern.test(query))?.[1] || languages[0].split('-')[0].toLowerCase();
  const url = new URL(window.OB_MULTILINGUAL_GEOCODER_URL || 'https://geocoding-api.open-meteo.com/v1/search');
  url.searchParams.set('name', query);
  url.searchParams.set('count', '8');
  url.searchParams.set('language', language);
  let primaryFailed = false;
  try {
    const response = await fetch(url, {signal: AbortSignal.timeout(12000)});
    if (!response.ok) throw new Error('Multilingual geocoder unavailable');
    const data = await response.json();
    if (data.error) throw new Error('Multilingual geocoder rejected query');
    const features = (Array.isArray(data.results) ? data.results : [])
      .filter(p => Number.isFinite(p.latitude) && Number.isFinite(p.longitude))
      .map(p => ({geometry: {type: 'Point', coordinates: [p.longitude, p.latitude]},
        properties: {name: p.name, state: p.admin1, country: p.country}}));
    if (features.length) return features;
  } catch { primaryFailed = true; }
  const fallback = new URL(photon);
  fallback.searchParams.set('q', query);
  fallback.searchParams.set('limit', '8');
  const response = await fetch(fallback, {signal: AbortSignal.timeout(12000)});
  if (!response.ok) throw new Error('Place search unavailable');
  const data = await response.json();
  const features = Array.isArray(data.features) ? data.features : [];
  if (!features.length && primaryFailed) throw new Error('Multilingual search unavailable; try again');
  return features;
};
OB.parseCoordinates = function (input) {
  const s = input.normalize('NFKC').trim().replace(/[\u0660-\u0669\u06f0-\u06f9]/g,c=>String(c.charCodeAt(0)-(c.charCodeAt(0)<=0x669?0x660:0x6f0))).replace(/[\u060c\u3001]/g,',').replace(/\u066b/g,'.');
  if (!/^[+\-\d.,\s]+$/.test(s)) return { kind: 'place' };
  const m = s.match(/^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:,|\s)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$/);
  if (!m) return { kind: 'invalid' };
  const lat = Number(m[1]), lon = Number(m[2]);
  if (Math.abs(lat) > 85.05112878 || Math.abs(lon) > 180) return { kind: 'invalid' };
  return { kind: 'coordinates', lat, lon };
};

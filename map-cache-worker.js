// Only cache Esri map tiles the user actually views. Respect the server's cache lifetime.
const CACHE = 'offbeat-esri-tiles-v1';
const CANDIDATE_CACHE = 'offbeat-candidates-v1';
const LIMIT = 256;
const inFlight = new Map();
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  const own = url.origin === self.location?.origin;
  const versionedCandidate = own && /^\/data\/change-candidates\/(?:catalog|[a-z]+|radar-[a-z]+-\d{4}-\d{2}-\d{2})-[a-f0-9]{12}\.(?:json|png)$/.test(url.pathname);
  const versionedOptical = own && /^\/data\/[a-z]+\/optical\/[A-Za-z0-9_.-]+\.png$/.test(url.pathname) && /^[a-f0-9]{64}$/.test(url.searchParams.get('v') || '');
  if(event.request.method==='GET' && (versionedCandidate || versionedOptical)) {event.respondWith(candidateAsset(event.request));return;}
  const standard = url.origin === 'https://services.arcgisonline.com' && /^\/ArcGIS\/rest\/services\/(?:World_Imagery|World_Topo_Map|Reference\/World_Boundaries_and_Places|Canvas\/World_Light_Gray_(?:Base|Reference))\/MapServer\/tile\/\d+\/\d+\/\d+$/.test(url.pathname);
  const clarity = url.origin === 'https://clarity.maptiles.arcgis.com' && /^\/arcgis\/rest\/services\/World_Imagery\/MapServer\/tile\/\d+\/\d+\/\d+$/.test(url.pathname);
  if (event.request.method !== 'GET' || (!standard && !clarity)) return;
  event.respondWith(tile(event.request));
});
async function candidateAsset(request) {
  try {
    const cache=await caches.open(CANDIDATE_CACHE), stored=await cache.match(request);
    if(stored)return stored;
    const response=await fetch(request);
    if(response.ok && !/\b(?:no-store|private)\b/i.test(response.headers.get('cache-control') || '')) {
      try {await cache.put(request,response.clone());const keys=await cache.keys();for(let i=0;i<keys.length-128;i++)await cache.delete(keys[i]);}catch(_){}
    }
    return response;
  } catch (_) {return fetch(request);}
}
async function tile(request) {
  try {
    const cache = await caches.open(CACHE);
    const stored = await cache.match(request.url);
    if (stored && Number(stored.headers.get('x-offbeat-expires')) > Date.now()) return stored;
    if (inFlight.has(request.url)) return (await inFlight.get(request.url)).clone();
    const pending = fetchAndStore(request, cache, stored);
    inFlight.set(request.url, pending);
    try {
      return (await pending).clone();
    } finally { inFlight.delete(request.url); }
  } catch (_) { return fetch(request); }
}
async function fetchAndStore(request, cache, stored) {
    try {
      // Esri exposes these tiles with CORS, so cache directives and status are visible.
      const response = await fetch(request.url, { mode: 'cors', credentials: 'omit' });
      const control = response.headers.get('cache-control') || '';
      const maxAge = /(?:^|,)\s*max-age=(\d+)/i.exec(control);
      if (response.ok && maxAge && !/\b(?:no-store|no-cache|private)\b/i.test(control)) {
        const headers = new Headers(response.headers);
        headers.set('x-offbeat-expires', String(Date.now() + Math.min(Number(maxAge[1]), 86400) * 1000));
        const copy = new Response(await response.clone().blob(), {status: response.status, statusText: response.statusText, headers});
        await cache.put(request.url, copy);
        const keys = await cache.keys();
        for (let i=0; i<keys.length-LIMIT; i++) await cache.delete(keys[i]);
      }
      return response;
    } catch (_) {
      if (stored) return stored;
      return fetch(request);
    }
}

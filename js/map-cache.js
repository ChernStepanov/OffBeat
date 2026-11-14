// Enable a bounded, per-browser cache for map tiles where service workers are available.
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  navigator.serviceWorker.register('map-cache-worker.js').catch(() => {});
}

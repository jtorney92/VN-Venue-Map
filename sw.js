// Via Nova Route Planner offline support. Prepared by Josh Torney.
// Pages and the venue list: try the network first, fall back to the saved copy when there's no signal.
// Map library and map tiles: use the saved copy first.
const CACHE = 'vn-route-v3', TILES = 'vn-tiles-v1', MAX_TILES = 1500;
const CORE = ['route.html', 'index.html', 'locations.json', 'suburbs.geojson', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css', 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css', 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(CORE.map(u => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE && k !== TILES).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const u = new URL(req.url);
  const firstParty = u.origin === self.location.origin;
  const tile = /arcgisonline\.com/.test(u.host);
  const lib = /unpkg\.com|cdnjs\.cloudflare\.com/.test(u.host);
  if (firstParty) {
    e.respondWith(fetch(req).then(r => { if (r.ok) { const cp = r.clone(); caches.open(CACHE).then(c => c.put(req, cp)); } return r; })
      .catch(() => caches.match(req, { ignoreSearch: true })));
  } else if (tile || lib) {
    const store = tile ? TILES : CACHE;
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok || r.type === 'opaque') { const cp = r.clone(); caches.open(store).then(c => c.put(req, cp).then(() => tile && trim(c))); }
      return r;
    })));
  }
});

// Keep the saved map tiles to a sensible size: oldest go first once there are more than MAX_TILES
async function trim(c) { const ks = await c.keys(); if (ks.length > MAX_TILES) await Promise.all(ks.slice(0, ks.length - MAX_TILES).map(k => c.delete(k))); }

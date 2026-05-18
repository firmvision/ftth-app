const APP_VERSION = "v1.0.0";
const APP_CACHE   = "ftth-app-" + APP_VERSION;
const TILE_CACHE  = "ftth-tiles-" + APP_VERSION;
const MAX_TILES   = 3000;

const TILE_HOSTS = [
  "basemaps.cartocdn.com","tile.openstreetmap.org","arcgisonline.com",
  "opentopomap.org","mt0.google.com","mt1.google.com","mt2.google.com",
  "mt3.google.com","api.mapbox.com","nominatim.openstreetmap.org"
];

const APP_SHELL = [
  "/","index.html","manifest.json",
  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(APP_CACHE).then(cache =>
      Promise.allSettled(APP_SHELL.map(u => cache.add(u).catch(() => {})))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== APP_CACHE && k !== TILE_CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url  = new URL(e.request.url);
  const tile = TILE_HOSTS.some(h => url.hostname.includes(h));
  if (tile) {
    e.respondWith(
      caches.open(TILE_CACHE).then(async cache => {
        const hit = await cache.match(e.request);
        if (hit) return hit;
        const res = await fetch(e.request.clone(), {mode:"no-cors"}).catch(() => null);
        if (res && (res.ok || res.type === "opaque")) {
          const keys = await cache.keys();
          if (keys.length >= MAX_TILES) await cache.delete(keys[0]);
          cache.put(e.request, res.clone());
        }
        return res;
      })
    );
    return;
  }
  if (e.request.method !== "GET") return;
  e.respondWith(
    fetch(e.request).then(res => {
      if (res.ok) caches.open(APP_CACHE).then(c => c.put(e.request, res.clone()));
      return res;
    }).catch(() => caches.match(e.request))
  );
});

// Minimal service worker: exists mainly to satisfy the browser's PWA
// installability check (Chrome/Android requires a fetch handler present) and
// to keep the app usable if a phone opens it with a flaky connection. Not
// trying to be a full offline-first app - this is a status dashboard, so
// "network first, cached fallback" is the right tradeoff: always show the
// freshest data when online, fall back to whatever was last seen when not.
//
// CACHE_VERSION is replaced with a fresh value on every static-site deploy
// (see scripts/build_static.py) so a new deploy's assets can't get stuck
// behind an old cache indefinitely.
const CACHE_VERSION = "hta-firmware-20260918223435";

const APP_SHELL = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

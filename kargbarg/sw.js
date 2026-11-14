const CACHE_NAME = "kargbarg-school-v3";
const APP_FILES = ["./", "./index.html", "./manifest.webmanifest", "./icon.svg"];
const APP_BASE = new URL("./", self.location.href);
const APP_INDEX = new URL("./index.html", self.location.href).href;
const APP_FILE_URLS = new Set(APP_FILES.map(file => new URL(file, self.location.href).href));

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key.startsWith("kargbarg-school-") && key !== CACHE_NAME)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Only app navigation is handled here. Prefer the network so security fixes
  // and updated pages are not hidden behind an old cache; use the app shell offline.
  if (request.mode === "navigate" && url.pathname === APP_BASE.pathname) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok && response.type === "basic") {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put("./", copy)).catch(() => {});
          }
          return response;
        })
        .catch(async () => {
          const cache = await caches.open(CACHE_NAME);
          return (await cache.match("./")) || (await cache.match(APP_INDEX));
        })
    );
    return;
  }

  // Cache only the four known static app files. Never cache arbitrary pages,
  // query-driven URLs, or user-specific responses.
  if (!APP_FILE_URLS.has(url.href)) return;

  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(response => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy)).catch(() => {});
        }
        return response;
      });
    })
  );
});

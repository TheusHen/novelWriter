// novelWriter Mobile PWA — Service Worker
// Stores a recent snapshot of the last synced manuscript and queues offline notes.

const CACHE = "novelwriter-mobile-v3";
const PRECACHE = [
  "./",
  "./index.html",
  "./styles.css?v=3",
  "./app.js?v=3",
  "./manifest.webmanifest",
  "./icons/icon-192.svg",
  "./icons/icon-512.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }
  const useNetworkFirst = request.mode === "navigate" ||
    ["/app.js", "/styles.css", "/manifest.webmanifest"].some((path) => url.pathname.endsWith(path));
  const cacheResponse = (response) => {
    const copy = response.clone();
    caches.open(CACHE).then((cache) => cache.put(request, copy));
    return response;
  };
  const cachedResponse = () => caches.match(request).then((cached) =>
    cached || (request.mode === "navigate" ? caches.match("./index.html") : Response.error())
  );

  if (useNetworkFirst) {
    event.respondWith(fetch(request).then(cacheResponse).catch(cachedResponse));
    return;
  }
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then(cacheResponse).catch(cachedResponse);
    })
  );
});

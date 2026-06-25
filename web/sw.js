// Minimal service worker: cache the app shell so the PWA launches offline. Provider API
// calls are cross-origin and pass straight through to the network (never cached).
const CACHE = "aieasybatch-v1";
const SHELL = ["./", "./index.html", "./app.js", "./style.css", "./manifest.webmanifest", "./icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;                // provider calls -> network, untouched
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});

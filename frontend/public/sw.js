// Minimal service worker for PWA installability.
// No offline caching — YASTL requires live API access.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener('fetch', () => {
  // No-op: required for PWA installability but all requests use default
  // network behaviour (no caching, no interception).
});

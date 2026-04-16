// Service Worker for The Zombie History Project (PWA)
// Caches the app shell for fast loading; always fetches fresh API data.

const CACHE_NAME = 'zombie-history-v1';

// App shell — static assets that rarely change
const APP_SHELL = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
];

// Install: pre-cache the app shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(APP_SHELL);
    })
  );
  // Activate immediately (don't wait for old tabs to close)
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  // Take control of all pages immediately
  self.clients.claim();
});

// Fetch: network-first for API calls, cache-first for static assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API calls and POST requests — always go to network, never cache
  if (url.pathname.startsWith('/api/') || event.request.method !== 'GET') {
    event.respondWith(fetch(event.request));
    return;
  }

  // Generated images — cache after first fetch
  if (url.pathname.startsWith('/static/generated/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // Static assets — try cache first, fall back to network, update cache
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const networkFetch = fetch(event.request).then((response) => {
        // Update the cache with fresh version
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      }).catch(() => cached); // If offline, use cached version

      return cached || networkFetch;
    })
  );
});

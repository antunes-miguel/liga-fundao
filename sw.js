// Service worker: lets the installed app open instantly and work offline.
// - Page and data: network first (always fresh when online), cached copy when offline.
// - Images, icons and fonts: cache first (they rarely change).
// Bump VERSION when the list of cached files changes.
const VERSION = 'v1';

// Push notifications (OneSignal). In try/catch so the app still installs when offline.
try { importScripts('https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js'); } catch (e) { /* no push until the next update */ }

const CACHE = `fantasy-fundao-${VERSION}`;
const SHELL = [
  './',
  'index.html',
  'data/fpl.json',
  'manifest.webmanifest',
  'assets/crest.png',
  'assets/icon-180.png',
  'assets/icon-192.png',
  'assets/icon-512.png',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('fantasy-fundao-') && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  try {
    const fresh = await fetch(request, { cache: 'no-store' });
    if (fresh.ok) cache.put(request, fresh.clone());
    return fresh;
  } catch (err) {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    if (request.mode === 'navigate') {
      const page = await cache.match('index.html');
      if (page) return page;
    }
    throw err;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const fresh = await fetch(request);
  if (fresh.ok || fresh.type === 'opaque') cache.put(request, fresh.clone());
  return fresh;
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (url.origin === location.origin) {
    const isPageOrData = req.mode === 'navigate' || url.pathname.endsWith('.html') ||
      url.pathname.endsWith('/') || url.pathname.endsWith('.json') || url.pathname.endsWith('.webmanifest');
    event.respondWith(isPageOrData ? networkFirst(req) : cacheFirst(req));
  } else if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    event.respondWith(cacheFirst(req));
  }
});

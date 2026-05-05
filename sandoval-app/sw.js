/* SANDOVAL PRO — Service Worker
 * v1.0.0 — cache versionado, network-first /api/*, cache-first shell, Web Push VAPID.
 * Para invalidar cache: bumpear CACHE_NAME (sandoval-v2, v3, ...).
 */
'use strict';

const CACHE_NAME = 'sandoval-v1777262844';
const SHELL = [
  '/app/',
  '/app/manifest.json',
  '/app/static/icons/icon-192.png',
  '/app/static/icons/icon-512.png',
  '/app/static/icons/apple-touch-icon.png'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((c) =>
      Promise.allSettled(SHELL.map((u) => c.add(u).catch(() => null)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll({ type: 'window' }))
      .then((clients) => clients.forEach((c) => c.navigate(c.url)))
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // /api/* → network-first, NUNCA se cachea (datos sensibles multi-tenant)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(req).catch(() =>
        new Response(JSON.stringify({ detail: 'Sin conexión' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    return;
  }

  // HTML principal /app/ → network-first para garantizar UI fresca tras deploys
  const isHtmlNav = url.pathname === '/app/' || url.pathname === '/app' ||
                    req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html');
  if (url.origin === location.origin && isHtmlNav) {
    event.respondWith(
      fetch(req, { cache: 'no-store' }).then((res) => {
        if (res && res.status === 200) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // Shell estático (manifest, iconos, JS externo cacheable) → cache-first con revalidación
  if (url.origin === location.origin) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const fetchPromise = fetch(req).then((res) => {
          if (res && res.status === 200 && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE_NAME).then((c) => c.put(req, copy));
          }
          return res;
        }).catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Terceros: pasar directo
  event.respondWith(fetch(req).catch(() => caches.match(req)));
});

/* Web Push */
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) { data = { title: 'SANDOVAL PRO', body: event.data ? event.data.text() : '' }; }
  const title = data.title || 'SANDOVAL PRO';
  const options = {
    body: data.body || '',
    icon: data.icon || '/assets/logo_sandoval_trans.png',
    badge: data.badge || '/assets/logo_sandoval_trans.png',
    tag: data.tag || 'sandoval',
    data: { url: data.url || '/app/', ...(data.data || {}) },
    vibrate: data.vibrate || [200, 100, 200],
    silent: false
  };
  event.waitUntil(Promise.all([
    self.registration.showNotification(title, options),
    self.clients.matchAll({type:'window', includeUncontrolled:true}).then(cs => {
      cs.forEach(c => c.postMessage({type:'play_sound', url: data.sound || '/assets/sounds/notify.mp3'}));
    })
  ]));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/app/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ('focus' in client) { client.navigate(url); return client.focus(); }
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});

self.addEventListener('message', (e) => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});

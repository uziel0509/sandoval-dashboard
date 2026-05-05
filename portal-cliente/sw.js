/* Sandoval Portal Cliente — Service Worker (push + cache) v3 */
const CACHE_NAME = 'sandoval-portal-v1777306182';
const SHELL = ['/portal/', '/portal/index.html', '/portal/pc/', '/portal/pc/index.html', '/portal/manifest.json'];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    try {
      const cache = await caches.open(CACHE_NAME);
      await Promise.all(SHELL.map(url => cache.add(url).catch(() => {})));
    } catch (_) {}
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    try {
      const ks = await caches.keys();
      await Promise.all(ks.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    } catch (_) {}
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const u = new URL(req.url);
  // Network-first /api/* (cachea solo data del cliente)
  if (u.pathname.startsWith('/api/')){
    e.respondWith(
      fetch(req).then(r => {
        if ((u.pathname === '/api/cliente/mis-ordenes' || u.pathname === '/api/cliente/mis-citas') && r.ok){
          const c = r.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, c).catch(() => {}));
        }
        return r;
      }).catch(() => caches.match(req))
    );
    return;
  }
  // HTML del portal: NETWORK-FIRST siempre fresco
  const isHtml = u.pathname.endsWith('/') || u.pathname.endsWith('.html');
  if (u.pathname.startsWith('/portal/') && isHtml){
    e.respondWith(
      fetch(req).then(resp => {
        if (resp.ok){
          const cl = resp.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, cl).catch(() => {}));
        }
        return resp;
      }).catch(() => caches.match(req))
    );
    return;
  }
  // Assets: cache-first
  if (u.pathname.startsWith('/portal/')){
    e.respondWith(
      caches.match(req).then(r => r || fetch(req).then(resp => {
        if (resp.ok){
          const cl = resp.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, cl).catch(() => {}));
        }
        return resp;
      }))
    );
  }
});

self.addEventListener('push', (event) => {
  let data = {};
  try { if (event.data) data = event.data.json(); } catch (_) { data = { title: 'Sandoval', body: event.data ? event.data.text() : '' }; }
  const title = data.title || 'Sandoval';
  const opts = {
    body: data.body || '',
    icon: data.icon || '/assets/logo_sandoval_trans.png',
    badge: data.badge || '/assets/logo_sandoval_trans.png',
    tag: data.tag || 'sandoval-default', renotify: true,
    vibrate: data.vibrate || [200, 100, 200], silent: false,
    data: { url: data.url || '/portal/', ...(data.data || {}) }
  };
  event.waitUntil(Promise.all([
    self.registration.showNotification(title, opts),
    self.clients.matchAll({type:'window', includeUncontrolled:true}).then(cs => {
      cs.forEach(c => c.postMessage({type:'play_sound', url: data.sound || '/assets/sounds/notify.mp3'}));
    })
  ]));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/portal/';
  event.waitUntil(self.clients.matchAll({ type:'window' }).then(cls => {
    for (const c of cls) { if (c.url.includes('/portal/') && 'focus' in c) { c.navigate(url); return c.focus(); } }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  }));
});

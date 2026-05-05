/* Sandoval Portal Cliente PC -- Service Worker (push + cache) v1
 * Creado 2026-04-29 -- push notifications con sonido
 */
const CACHE_NAME = 'sandoval-portal-pc-v1777520695';
const SHELL = ['/portal/pc/', '/portal/pc/index.html'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_NAME).then(c =>
    Promise.allSettled(SHELL.map(u => c.add(u).catch(() => {})))
  ).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const u = new URL(req.url);
  if (u.pathname.startsWith('/api/')) {
    e.respondWith(fetch(req).catch(() => new Response(JSON.stringify({detail:'Sin conexion'}),
      {status:503, headers:{'Content-Type':'application/json'}})));
    return;
  }
  if (u.pathname.startsWith('/portal/pc/') && (u.pathname.endsWith('/') || u.pathname.endsWith('.html'))) {
    e.respondWith(fetch(req, {cache:'no-store'}).then(r => {
      if (r && r.ok) { const cl = r.clone(); caches.open(CACHE_NAME).then(c => c.put(req, cl).catch(() => {})); }
      return r;
    }).catch(() => caches.match(req)));
    return;
  }
});

self.addEventListener('push', (e) => {
  let d = {};
  try { if (e.data) d = e.data.json(); } catch (_) { d = {title:'SANDOVAL PRO', body: e.data ? e.data.text() : ''}; }
  const title = d.title || 'SANDOVAL PRO';
  const opts = {
    body: d.body || '',
    icon: d.icon || '/assets/logo_sandoval_trans.png',
    badge: d.badge || '/assets/logo_sandoval_trans.png',
    tag: d.tag || 'sandoval-pc', renotify: true,
    vibrate: d.vibrate || [200, 100, 200], silent: false,
    data: { url: d.url || '/portal/pc/', ...(d.data || {}) }
  };
  e.waitUntil(Promise.all([
    self.registration.showNotification(title, opts),
    self.clients.matchAll({type:'window', includeUncontrolled:true}).then(cs => {
      cs.forEach(c => c.postMessage({type:'play_sound', url: d.sound || '/assets/sounds/notify.mp3'}));
    })
  ]));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/portal/pc/';
  e.waitUntil(self.clients.matchAll({type:'window'}).then(cs => {
    for (const c of cs) { if (c.url.includes('/portal/pc/') && 'focus' in c) { c.navigate(url); return c.focus(); } }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  }));
});

self.addEventListener('message', (e) => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});

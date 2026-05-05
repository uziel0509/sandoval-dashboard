/* Sandoval Admin SPA -- Service Worker (push) v2
 * Creado 2026-04-29 -- push notifications para admin con sonido
 * Actualizado 2026-05-01 -- NO interceptar APIs (causaba logout en mobile con red 4G inestable)
 */
const CACHE_NAME = 'sandoval-admin-sw-v1777598400';

self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => {
  e.waitUntil(self.clients.claim());
});

// IMPORTANTE: NO interceptar fetches. El SW antes atrapaba errores de red en
// /admin/api/* y devolvia 503 "Sin conexion" fake. Eso hacia que el frontend
// interpretara cualquier glitch de 4G como "token invalido" y cerrara sesion
// en cada reload. Ahora dejamos al navegador manejar la red nativamente: si
// hay error real, el frontend puede distinguir entre TypeError (red) y 401 (auth).

self.addEventListener('push', (e) => {
  let d = {};
  try { if (e.data) d = e.data.json(); } catch (_) { d = {title:'SANDOVAL PRO', body: e.data ? e.data.text() : ''}; }
  const title = d.title || 'SANDOVAL PRO';
  const opts = {
    body: d.body || '',
    icon: d.icon || '/assets/logo_sandoval_trans.png',
    badge: d.badge || '/assets/logo_sandoval_trans.png',
    tag: d.tag || 'sandoval-admin', renotify: true,
    vibrate: d.vibrate || [200, 100, 200], silent: false,
    data: { url: d.url || '/admin/index.html', ...(d.data || {}) }
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
  const url = (e.notification.data && e.notification.data.url) || '/admin/index.html';
  e.waitUntil(self.clients.matchAll({type:'window'}).then(cs => {
    for (const c of cs) { if ('focus' in c && (c.url.includes('/admin/') || c.url.includes('/admin/'))) { c.navigate(url); return c.focus(); } }
    if (self.clients.openWindow) return self.clients.openWindow(url);
  }));
});

self.addEventListener('message', (e) => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});

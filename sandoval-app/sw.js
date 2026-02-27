const CACHE_NAME = 'sandoval-v1';
const PRECACHE = ['/app/', '/app/index.html'];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE_NAME).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    // Solo cachear GET, no la API
    if (e.request.method !== 'GET' || e.request.url.includes('/api/')) return;
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request))
    );
});

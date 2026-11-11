// Service worker расписания 612-Б.
// Идея: данные всегда берём из сети (актуальность важнее), кэш — только запас, когда сети нет.
const CACHE = "raspisanie-v1";   // увеличить номер, если поменялся sw.js или картинки (png берутся из кэша)
const SHELL = ["./", "index.html", "bells.html", "schedule.js", "changes.json",
               "manifest.json", "icon-192.png", "icon-512.png", "scream.png"];
const NET_TIMEOUT = 4000;        // медленная сеть дольше 4 с — показываем сохранённое

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  const key = req.url.split("?")[0];            // changes.json?123 и changes.json — один и тот же файл
  const net = fetch(req.url, { cache: "no-store" }).then(r => {
    if (r.ok) cache.put(key, r.clone());
    return r;
  });
  net.catch(() => {});                           // чтобы поздний сбой не шумел в консоли
  const timeout = new Promise((_, rej) => setTimeout(rej, NET_TIMEOUT));
  try {
    return await Promise.race([net, timeout]);
  } catch (_) {
    const hit = await cache.match(key);
    if (!hit) return net;                        // кэша нет — ждём сеть как есть
    const headers = new Headers(hit.headers);
    headers.set("x-from-cache", "1");            // страница по этому признаку пишет «Нет сети»
    return new Response(hit.body, { status: hit.status, statusText: hit.statusText, headers });
  }
}

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req.url);
  if (hit) return hit;
  const r = await fetch(req);
  if (r.ok) cache.put(req.url, r.clone());
  return r;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (req.headers.has("range")) return;          // звук и видео отдаём браузеру как есть
  if (/\.(png|ico)$/.test(url.pathname)) return e.respondWith(cacheFirst(req));
  if (/\.(html|js|json)$/.test(url.pathname) || url.pathname.endsWith("/"))
    return e.respondWith(networkFirst(req));
});

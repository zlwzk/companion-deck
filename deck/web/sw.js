// CompanionDeck Service Worker —— 缓存静态资源以支持离线打开与 PWA 安装
// 版本升级时 CACHE_NAME 递增，activate 阶段会清掉旧缓存。
const CACHE_NAME = "companiondeck-v2";
const ASSETS = ["/", "/static/style.css", "/static/app.js", "/static/icon.svg", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  // 只处理同源的 GET
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // API 与 WS 永远走网络
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) return;
  // 页面与脚本样式：network-first —— 保证新版本 UI 能立即生效，
  // 避免旧缓存把「版本号/新功能」挡住；离线时回退缓存。
  event.respondWith(
    fetch(req).then((resp) => {
      if (resp && resp.status === 200) {
        const respClone = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, respClone));
      }
      return resp;
    }).catch(() => caches.match(req))
  );
});

// Offline support: the page and map library are kept so the app opens without signal.
var CACHE = "mithagar-v1";
var SHELL = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png"];
self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener("fetch", function (e) {
  var u = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  var own = u.origin === self.location.origin, lib = u.hostname === "cdnjs.cloudflare.com";
  if (!own && !lib) return;                       // forecast and map tiles always come from the network
  if (lib) {                                      // library: cache first
    e.respondWith(caches.match(e.request).then(function (hit) {
      return hit || fetch(e.request).then(function (r) {
        var copy = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copy); }); return r;
      });
    }));
    return;
  }
  e.respondWith(fetch(e.request).then(function (r) {   // own files: newest first, saved copy when offline
    var copy = r.clone(); caches.open(CACHE).then(function (c) { c.put(e.request, copy); }); return r;
  }).catch(function () { return caches.match(e.request).then(function (hit) { return hit || caches.match("index.html"); }); }));
});

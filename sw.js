const CACHE='study-planner-v3';
const FILES=['./','index.html','manifest.webmanifest','icon.svg','icon-192.png','icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
  const req=e.request, url=new URL(req.url);
  if(req.method!=='GET')return;
  // Sync traffic to GitHub's API must always go to the network, never the cache.
  if(url.origin!==location.origin&&!/fonts\.(googleapis|gstatic)\.com$/.test(url.hostname))return;
  // Racing picks change every morning: always fetch them fresh.
  if(url.pathname.includes('/racing/picks/'))return;
  const put=r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(req,copy)).catch(()=>{});return r;};
  if(req.mode==='navigate'){
    // Page itself: network first so app updates arrive, cache when offline.
    e.respondWith(fetch(req).then(put).catch(()=>caches.match(req).then(h=>h||caches.match('index.html'))));
    return;
  }
  e.respondWith(caches.match(req).then(hit=>hit||fetch(req).then(put)));
});

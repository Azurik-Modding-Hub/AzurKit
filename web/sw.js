// The site's service worker (D1013): it keeps this release of the site whole in one cache, serves the page, its modules
// and its engine from it, so a page never runs another release's engine and needs no network once kept, and isolates
// what it serves (COOP, COEP and CORP, and the page's CSP as a header, which a worker started from its own URL keeps).
//
// scripts/web_tools.py's site() writes RELEASE below: the release's name (its list's digest), the page's CSP and every
// file the site serves with it, each with its sha256 and size (index.html, the page's modules, pyodide/, the wheel,
// host.json, art/ and characters/; never this file, .nojekyll or content-source/, which the network serves). Here, in
// the checkout (the app's page, which never registers it), it lists none, and the install fails: nothing is controlled.
//
// - The install keeps every listed file in the cache named by the release and the scope, each checked against its
//   sha256: a file of an older release's cache with the same bytes is copied, any other downloaded (revalidated past
//   the HTTP cache). One file that is missing or differs (a deploy half done) fails the install: the release before
//   stays. The first install takes over at once; an update waits for the page to ask ("An update is ready: Reload").
// - The activation deletes the older releases' caches of this scope (never another site's on this origin).
// - Each GET in the scope of a listed file (a navigation to the scope or index.html is index.html) is answered from
//   this release's cache; one gone from it (Storage's Clear) is downloaded again and kept only if its sha256 is the
//   list's, else answered 503: a page never gets another release's bytes. Any other GET goes to the network.
// - The page's messages, each answered on its port: "release" (this release's name, files and bytes, and how many are
//   kept), "check" (host.json from the network, compared with this release's: when it differs the registration looks
//   for the new release, which installs and waits), "reload" (to the waiting release: it takes over when the asking
//   page is the scope's only one, else it says how many others are open).
// - The install posts to the scope's pages its progress (core.progress's record, stage "release"), then "installed" or
//   "failed" (with the file's fault), the release's outcome, which a page may know before its registration shows it
//   (Firefox shows a new worker after its updatefound).
const RELEASE = null;

const SCOPE = self.registration.scope;
const PREFIX = `azurkit:${SCOPE}:`;
const NAME = RELEASE && PREFIX + RELEASE.name;
const ISOLATED = { "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Embedder-Policy": "require-corp",
                   "Cross-Origin-Resource-Policy": "same-origin" };
const AT_ONCE = 6;   // the downloads the install runs at once

const hex = async (data) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", data))]
  .map((b) => b.toString(16).padStart(2, "0")).join("");
const listed = (rel) => RELEASE && Object.hasOwn(RELEASE.files, rel) ? RELEASE.files[rel] : null;
const address = (rel) => new URL(rel, SCOPE).href;
const ours = async () => (await caches.keys()).filter((key) => key.startsWith(PREFIX));
const pages = () => self.clients.matchAll({ type: "window", includeUncontrolled: true })
  .then((all) => all.filter((c) => c.url.startsWith(SCOPE)));

// rel's bytes as this release lists them, as a response to keep: from `kept` (older releases' caches) when one holds
// the same bytes, else downloaded; Error names the file otherwise.
async function fetched(rel, kept = []) {
  const { sha256 } = listed(rel);
  for (const key of kept) {
    const reply = await (await caches.open(key)).match(address(rel));
    if (reply) {
      const data = await reply.arrayBuffer();
      if (await hex(data) === sha256) return new Response(data, { headers: reply.headers });
    }
  }
  const reply = await fetch(address(rel), { cache: "no-cache" });
  if (!reply.ok) throw new Error(`${rel}: HTTP ${reply.status}`);
  const data = await reply.arrayBuffer();
  if (await hex(data) !== sha256) throw new Error(`${rel} isn't this release's (sha256 ${sha256.slice(0, 12)})`);
  const type = reply.headers.get("Content-Type");
  return new Response(data, { headers: type ? { "Content-Type": type } : {} });
}

async function install() {
  if (!RELEASE) throw new Error("this sw.js lists no release (scripts/web_tools.py's site() writes it)");
  const cache = await caches.open(NAME);
  const kept = (await ours()).filter((key) => key !== NAME);
  const files = Object.keys(RELEASE.files), total = files.reduce((sum, rel) => sum + RELEASE.files[rel].size, 0);
  let next = 0, done = 0, told = 0;
  const tell = async (message) => {
    for (const page of await pages()) page.postMessage(message);
  };
  const run = async () => {
    while (next < files.length) {
      const rel = files[next++];
      if (!await cache.match(address(rel))) await cache.put(address(rel), await fetched(rel, kept));
      done += RELEASE.files[rel].size;
      if (Date.now() - told >= 250 || done === total) {
        told = Date.now();
        await tell({ type: "progress", stage: "release", label: "Keeping AzurKit for offline use", done, total,
                     percent: total > 0 ? Math.floor(done * 100 / total) : null });
      }
    }
  };
  try {
    await Promise.all(Array.from({ length: AT_ONCE }, run));
  } catch (error) {
    await tell({ type: "failed", release: RELEASE.name, message: error.message });
    throw error;
  }
  await tell({ type: "installed", release: RELEASE.name });
  if (!self.registration.active) await self.skipWaiting();   // the first: no page runs on another release
}

async function activate() {
  for (const key of await ours()) if (key !== NAME) await caches.delete(key);
}

// The response with this release's isolation and CSP headers.
function isolated(reply) {
  if (reply.type === "opaqueredirect" || reply.status === 0) return reply;
  const headers = new Headers(reply.headers);
  for (const [name, value] of Object.entries(ISOLATED)) headers.set(name, value);
  headers.set("Content-Security-Policy", RELEASE.csp);
  return new Response(reply.body, { status: reply.status, statusText: reply.statusText, headers });
}

async function serve(rel, request) {
  if (!listed(rel)) return isolated(await fetch(request));
  const cache = await caches.open(NAME);
  let reply = await cache.match(address(rel));
  if (!reply) {
    try {
      reply = await fetched(rel);
    } catch (error) {
      return new Response(`${error.message}: reload the page`, {
        status: 503, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" } });
    }
    await cache.put(address(rel), reply.clone());
  }
  return isolated(reply);
}

async function answer(data, source) {
  if (data?.type === "release") {
    const cached = NAME ? (await (await caches.open(NAME)).keys()).length : 0;
    const files = RELEASE ? Object.values(RELEASE.files) : [];
    return { type: "release", name: RELEASE?.name ?? null, files: files.length, cached,
             bytes: files.reduce((sum, f) => sum + f.size, 0) };
  }
  if (data?.type === "check") {
    let reply;
    try {
      reply = await fetch(address("host.json"), { cache: "no-store" });
    } catch {
      return { type: "checked", update: false, offline: true };
    }
    const update = reply.ok && await hex(await reply.arrayBuffer()) !== listed("host.json")?.sha256;
    if (update) await self.registration.update().catch(() => null);
    return { type: "checked", update, offline: false };
  }
  if (data?.type === "reload") {
    const others = (await pages()).filter((page) => page.id !== source?.id).length;
    if (others) return { type: "reload", ok: false, others };
    await self.skipWaiting();   // the waiting release's take-over (the active one's is a no-op)
    return { type: "reload", ok: true, others: 0 };
  }
  return { type: "refused", message: `sw.js answers release, check or reload, not ${String(data?.type)}` };
}

self.addEventListener("install", (event) => event.waitUntil(install()));
self.addEventListener("activate", (event) => event.waitUntil(activate()));
self.addEventListener("message", (event) => {
  const job = answer(event.data, event.source).then((reply) => (event.ports[0] ?? event.source)?.postMessage(reply));
  event.waitUntil?.(job);
});
self.addEventListener("fetch", (event) => {
  const { request } = event, url = new URL(request.url);
  if (!RELEASE || request.method !== "GET" || !url.href.startsWith(SCOPE)) return;
  let rel;
  try {
    rel = decodeURIComponent(url.pathname.slice(new URL(SCOPE).pathname.length));
  } catch {
    return;   // no listed file's address (a malformed escape): the network's
  }
  if (request.mode === "navigate" && rel === "") rel = "index.html";
  event.respondWith(serve(rel, request));
});

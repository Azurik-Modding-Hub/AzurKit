// Azurik-Custom-Content on the page (Step 4.3k; D913, D988): the source it is read from, its list and Install/Update,
// one path for every tab that lists its entries (the Characters tab's community variants, the Patches tab's community
// packs). The engine decides what an entry may hold (sdk.content_check on the site's worker, sdk.content and
// sdk.content_install in the app): this module fetches, keeps and hands over; what it fetches is data the engine reads
// (recipes, models, pictures, sounds), never code the page or the engine runs. Content from (default
// Azurik-Custom-Content on GitHub; on the site any https address, D1135) is remembered: by the site in this browser's
// storage, by the app in its config. An Install fetches the entry and each entry it requires that
// isn't kept at its version (the requires walk keeps a done set: each entry once, a cycle or an unknown id refused by
// name), at most MAX_ENTRY bytes as the manifest lists them and no reply past its listed size, then the engine checks
// every file's size and sha256 before anything is kept (D35); an installed entry stays at its version until its Update,
// which drops the files the new version doesn't hold. A built-in's shipped Check parts (later) are listed with their
// entry but left for the Check that asks for one: its engine fetches it then. The site keeps what it installed in IndexedDB and hands it to its
// engine (handoff) as the page starts and after each Install; the app writes it into its content folder. Each tab
// listens for a change (on) and draws the list its own way.
export const SOURCE = "azurkit.content_source";   // the site's remembered source (localStorage)
export const MAX_ENTRY = 256 * 1024 * 1024;        // the most bytes one Install fetches (the engine's entry cap)
const UNREACHED = "no answer: offline, or it doesn't let other sites read it";   // a fetch that rejects (CORS too)

// where(source, here): the address the site reads source at, or a refusal naming it (plain: said as it is). The page's
// CSP (connect-src 'self' https:) lets it read any https address and its own (relative, or plain http when the site is
// served from this computer); a folder is the app's. The app's engine holds its own (sdk._source and _secure: https, or
// http only on this computer).
export function where(source, here) {
  const plain = (message) => Object.assign(new Error(message), { plain: true });
  if (/^(\/|~|[A-Za-z]:\\)/.test(source)) {
    throw plain("The site reads a URL, not a folder: the desktop app reads a folder of your own.");
  }
  let url;
  try {
    url = new URL(source, here.href);
  } catch {
    throw plain(`${source} is no web address: the site reads an https one.`);
  }
  if (url.origin === here.origin || url.protocol === "https:") return url;
  throw plain(url.protocol === "http:"
    ? `${source} is plain http: the site reads an https address (the desktop app reads http on this computer too).`
    : `${source} is no https address: the site reads an https one.`);
}

// later(path): whether Install leaves a listed file for the Check that asks for it, a built-in's shipped Check part
// (variants/<id>/shipped/parts/), which the engine fetches from the entry's source then and holds to AzurKit's own row
// (Step 4.6p: booblord's are 117 MB of her entry's 133), so Install and a page start carry none. content.py's later
// holds the same.
export const later = (path) => /^variants\/[^/]+\/shipped\/parts\/[^/]+$/.test(path);

// keeper(db, name): this browser's keeping of what the site installed (the last manifest read, installed.json's record
// and the files), in IndexedDB's "azurkit-content" (the Characters tab's since Step 4.3d), opened on first use; with
// name another database of one store, as the Variants view keeps your variants in "azurkit-variants" (Step 4.6c).
export function keeper(db = globalThis.indexedDB, name = "azurkit-content") {
  let opened = null;
  const open = () => opened ??= new Promise((done, fail) => {
    const request = db.open(name, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("kept");
    request.onsuccess = () => {   // a Clear's delete of it never waits on this page (it closes, then reload)
      request.result.onversionchange = () => request.result.close();
      done(request.result);
    };
    request.onerror = () => fail(request.error);
  });
  const run = async (mode, act) => {
    const handle = await open();
    return new Promise((done, fail) => {
      const tx = handle.transaction("kept", mode), request = act(tx.objectStore("kept"));
      tx.oncomplete = () => done(request?.result);
      tx.onerror = tx.onabort = () => fail(tx.error);
    });
  };
  return { get: (key) => run("readonly", (s) => s.get(key)).catch(() => undefined),
           put: (entries) => run("readwrite", (s) => { for (const [k, v] of entries) s.put(v, k); }) };
}

// needs(entries, id): the ids an Install of id writes, those required first, each once (entries: a Map of id -> a
// manifest entry). Iterative, with a done set; an unknown id or a cycle is refused by name.
export function needs(entries, id) {
  const order = [], done = new Set(), stack = [[id, 0, [id]]];
  while (stack.length) {
    const top = stack[stack.length - 1], [name, next, path] = top;
    const entry = entries.get(name);
    if (!entry) throw new Error(`no entry ${JSON.stringify(name)} in the community list`);
    if (next < entry.requires.length) {
      top[1] += 1;
      const other = entry.requires[next];
      if (path.includes(other)) {
        throw new Error(`entry ${JSON.stringify(other)} requires itself (${[...path, other].join(" -> ")})`);
      }
      if (!done.has(other)) stack.push([other, 0, [...path, other]]);
      continue;
    }
    stack.pop();
    if (!done.has(name)) {
      done.add(name);
      order.push(name);
    }
  }
  return order;
}

// The reply's bytes, refused once past size (the manifest's): its Content-Length first, then as it streams.
async function capped(reply, path, size) {
  const told = Number(reply.headers?.get?.("content-length"));
  const past = () => new Error(`${path}: past the ${size.toLocaleString("en-US")} bytes its manifest lists`);
  if (told > size) throw past();
  if (!reply.body?.getReader) {
    const data = new Uint8Array(await reply.arrayBuffer());
    if (data.length > size) throw past();
    return data;
  }
  const reader = reply.body.getReader(), parts = [];
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    n += value.length;
    if (n > size) {
      reader.cancel().catch(() => {});
      throw past();
    }
    parts.push(value);
  }
  const data = new Uint8Array(n);
  let at = 0;
  for (const part of parts) {
    data.set(part, at);
    at += part.length;
  }
  return data;
}

// content({call, app, host, handoff, fallback, kept, fetch, storage, location}): call is the engine's (the site's
// worker, the app's api); host the app's (its content_source); handoff(files, installed) gives the site's engine what
// this browser keeps; fallback the source with no setting (Azurik-Custom-Content's, from the catalog). kept, fetch,
// storage and location are the browser's unless given.
export function content({ call, app, host = {}, handoff = () => {}, fallback, kept, fetch: get, storage,
                          location: here = globalThis.location }) {
  const base = fallback ?? host.catalog?.characters?.source ?? "";
  kept ??= app ? null : keeper();
  get ??= (...args) => globalThis.fetch(...args);
  const store = () => storage ?? globalThis.localStorage;
  const s = { source: base, manifest: null, why: null, entries: [], installed: {}, installing: null };
  let reads = 0;   // a read's answer or failure is dropped once a later read or an Install has begun
  const listeners = new Set();
  const changed = () => {
    for (const listen of listeners) listen(s);
  };
  if (app) s.source = host.content_source || base;
  else {
    try {
      s.source = store().getItem(SOURCE) || base;
    } catch {}
  }
  // What the site keeps installed, handed to its engine now, not at a tab's first open.
  const ready = app ? Promise.resolve() : Promise.all([kept.get("files"), kept.get("installed")])
    .then(([files, installed]) => {
      s.installed = installed ?? {};
      if (files && installed) handoff(files, installed);
    });

  // Each entry with its state against what is kept: install, installed (at its version) or update (an older one).
  const states = () => (s.manifest?.entries ?? []).map((e) => {
    const held = s.installed[e.id]?.version ?? null;
    return { ...e, installed: held, state: held === null ? "install" : held === e.version ? "installed" : "update" };
  });

  // The source's list: the app's engine reads it (a URL or a folder), the site fetches it (where's address: any https
  // one, Azurik-Custom-Content's on GitHub by default, or its own) and its worker checks it; the last one read is kept,
  // listed while the source can't be read (why says so plainly; each tab adds its own line).
  const read = async () => {
    await ready;
    const mine = ++reads;
    if (app) {
      const reply = await call("content", { source: s.source });
      if (mine !== reads) return s;
      if ("refused" in reply) s.why = reply.refused;
      else ({ manifest: s.manifest, why: s.why, entries: s.entries, installed: s.installed } = reply);
      changed();
      return s;
    }
    s.why = null;
    try {
      const reply = await get(new URL("manifest.json", where(s.source, here)), { cache: "no-store" })
        .catch(() => { throw new Error(UNREACHED); });
      if (!reply.ok) throw new Error(`HTTP ${reply.status}${reply.status === 404 ? ": no manifest.json there" : ""}`);
      const text = await reply.text();
      const checked = await call("content_check", { manifest: text });
      if (mine !== reads) return s;
      if ("refused" in checked) throw new Error(checked.refused);
      s.manifest = checked.manifest;
      await kept.put([["manifest", text]]).catch(() => {});
    } catch (error) {
      if (mine !== reads) return s;   // its failure dropped as its answer is: s.source is a later read's now
      const last = await kept.get("manifest");
      if (mine !== reads) return s;
      s.why = error.plain ? error.message : `Couldn't reach the community list at ${s.source} (${error.message}).`;
      if (last) s.manifest = JSON.parse(last);
    }
    s.entries = states();
    changed();
    return s;
  };

  // Install or Update an entry; progress(k, n) hears each file fetched. Nothing is kept unless every file passes.
  const install = async (entry, progress = () => {}) => {
    if (s.installing) throw new Error(`${s.installing} is installing: one at a time`);
    s.installing = entry.id;
    reads += 1;
    changed();
    try {
      if (app) {
        progress(0, 1);
        const reply = await call("install", { id: entry.id, source: s.source });
        if ("refused" in reply) throw new Error(reply.refused);
        ({ manifest: s.manifest, why: s.why, entries: s.entries, installed: s.installed } = reply);
        progress(1, 1);
        return s;
      }
      if (!s.manifest) throw new Error("the community list isn't read yet");
      const ids = new Map(s.manifest.entries.map((e) => [e.id, e]));
      const need = needs(ids, entry.id);
      const files = { ...((await kept.get("files")) ?? {}) }, record = { ...((await kept.get("installed")) ?? {}) };
      const todo = need.filter((id) => id === entry.id || record[id]?.version !== ids.get(id).version);
      const wanted = todo.flatMap((id) => ids.get(id).files.filter((f) => !later(f.path)));
      const bytes = wanted.reduce((n, f) => n + f.size, 0);
      if (bytes > MAX_ENTRY) {
        throw new Error(`its files are ${bytes.toLocaleString("en-US")} bytes, past the `
                        + `${MAX_ENTRY.toLocaleString("en-US")} one Install fetches`);
      }
      const fetched = {}, from = where(s.source, here);
      progress(0, wanted.length);
      for (const [k, f] of wanted.entries()) {
        const reply = await get(new URL(f.path, from), { cache: "no-store" })
          .catch(() => { throw new Error(`${f.path}: ${UNREACHED}`); });
        if (!reply.ok) throw new Error(`${f.path}: HTTP ${reply.status}`);
        fetched[f.path] = await capped(reply, f.path, f.size);
        progress(k + 1, wanted.length);
      }
      const held = Object.fromEntries(need.filter((id) => !todo.includes(id)).flatMap((id) => ids.get(id).files
        .filter((f) => !later(f.path)).map((f) => [f.path, files[f.path] ?? new Uint8Array()])));
      const checked = await call("content_check", { manifest: JSON.stringify(s.manifest), id: entry.id,
                                                    files: { ...held, ...fetched }, source: s.source });
      if ("refused" in checked) throw new Error(checked.refused);
      for (const id of todo) {
        // A path another installed entry holds now stays (content.py's install keeps it too).
        for (const path of Object.keys(record[id]?.files ?? {})) {
          if (!Object.entries(record).some(([k, o]) => k !== id && path in (o?.files ?? {}))) delete files[path];
        }
        record[id] = { version: ids.get(id).version, source: s.source,
                       files: Object.fromEntries(ids.get(id).files.map((f) => [f.path, f.sha256])) };
        for (const f of ids.get(id).files) if (!later(f.path)) files[f.path] = fetched[f.path];
      }
      await kept.put([["files", files], ["installed", record]]);
      s.installed = record;
      s.entries = states();
      handoff(files, record);
      return s;
    } finally {
      s.installing = null;
      changed();
    }
  };

  // Content from set (null or the fallback: Azurik-Custom-Content's), remembered, and the list read again. The site's
  // ends in a "/", as the sdk's _source ends a URL source, so a file's address is below it and one repository is one
  // source (an Update comes only from the source it was installed from, SEC-8).
  const source = (url) => {
    s.source = !url ? base : (app || url.endsWith("/") ? url : `${url}/`);
    if (app) call("content_source", { source: s.source === base ? null : s.source });
    else {
      try {
        if (s.source === base) store().removeItem(SOURCE);
        else store().setItem(SOURCE, s.source);
      } catch {}
    }
    return read();
  };

  return { state: s, ready, read, install, source, fallback: base,
           on: (listen) => (listeners.add(listen), () => listeners.delete(listen)) };
}

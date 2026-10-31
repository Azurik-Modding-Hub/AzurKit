// Azurik-Custom-Content on the page (Step 4.3k; D913, D988): the source it is read from, its list and Install/Update,
// one path for every tab that lists its entries (the Characters tab's community variants, the Patches tab's community
// packs). The engine decides what an entry may hold (sdk.content_check on the site's worker, sdk.content and
// sdk.content_install in the app): this module fetches, keeps and hands over. Content from is remembered: by the site
// in this browser's storage, by the app in its config. An Install fetches the entry and each entry it requires that
// isn't kept at its version (the requires walk keeps a done set: each entry once, a cycle or an unknown id refused by
// name), at most MAX_ENTRY bytes as the manifest lists them and no reply past its listed size, then the engine checks
// every file's size and sha256 before anything is kept (D35); an installed entry stays at its version until its Update,
// which drops the files the new version doesn't hold. The site keeps what it installed in IndexedDB and hands it to its
// engine (handoff) as the page starts and after each Install; the app writes it into its content folder. Each tab
// listens for a change (on) and draws the list its own way.
export const SOURCE = "azurkit.content_source";   // the site's remembered source (localStorage)
export const MAX_ENTRY = 256 * 1024 * 1024;        // the most bytes one Install fetches (the engine's entry cap)

// keeper(db): this browser's keeping of what the site installed (the last manifest read, installed.json's record and
// the files), in IndexedDB's "azurkit-content" (the Characters tab's since Step 4.3d), opened on first use.
export function keeper(db = globalThis.indexedDB) {
  let opened = null;
  const open = () => opened ??= new Promise((done, fail) => {
    const request = db.open("azurkit-content", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("kept");
    request.onsuccess = () => done(request.result);
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
  const past = (n) => new Error(`${path}: ${n.toLocaleString("en-US")} bytes or more, past the community list's `
                                + `${size.toLocaleString("en-US")}`);
  if (told > size) throw past(told);
  if (!reply.body?.getReader) {
    const data = new Uint8Array(await reply.arrayBuffer());
    if (data.length > size) throw past(data.length);
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
      throw past(n);
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

  // The source's list: the app's engine reads it (a URL or a folder), the site fetches it (an http(s) or relative URL
  // of its own address, never a folder) and its worker checks it; the last one read is kept, listed while the source
  // can't be read (why says so; each tab adds its own line).
  const read = async () => {
    await ready;
    if (app) {
      const reply = await call("content", { source: s.source });
      if ("refused" in reply) s.why = reply.refused;
      else ({ manifest: s.manifest, why: s.why, entries: s.entries, installed: s.installed } = reply);
      changed();
      return s;
    }
    s.why = null;
    try {
      if (/^(\/|~|[A-Za-z]:\\)/.test(s.source)) {
        throw Object.assign(new Error("The site reads a URL, not a folder: the desktop app reads a folder of your "
                                      + "own."), { plain: true });
      }
      if (new URL(s.source, here.href).origin !== here.origin) {   // the page's CSP: connect-src 'self'
        throw Object.assign(new Error("Community content comes to this site with AzurKit 4.4; the desktop app lists "
                                      + "it now."), { plain: true });
      }
      const reply = await get(new URL("manifest.json", new URL(s.source, here.href)), { cache: "no-store" })
        .catch(() => { throw new Error("no answer"); });
      if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
      const text = await reply.text();
      const checked = await call("content_check", { manifest: text });
      if ("refused" in checked) throw new Error(checked.refused);
      s.manifest = checked.manifest;
      await kept.put([["manifest", text]]).catch(() => {});
    } catch (error) {
      s.why = error.plain ? error.message : `Couldn't reach the community list at ${s.source} (${error.message}).`;
      const last = await kept.get("manifest");
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
      const wanted = todo.flatMap((id) => ids.get(id).files);
      const bytes = wanted.reduce((n, f) => n + f.size, 0);
      if (bytes > MAX_ENTRY) {
        throw new Error(`its files are ${bytes.toLocaleString("en-US")} bytes, past the `
                        + `${MAX_ENTRY.toLocaleString("en-US")} one Install fetches`);
      }
      const fetched = {}, from = new URL(s.source, here.href);
      progress(0, wanted.length);
      for (const [k, f] of wanted.entries()) {
        const reply = await get(new URL(f.path, from), { cache: "no-store" });
        if (!reply.ok) throw new Error(`${f.path}: HTTP ${reply.status}`);
        fetched[f.path] = await capped(reply, f.path, f.size);
        progress(k + 1, wanted.length);
      }
      const held = Object.fromEntries(need.filter((id) => !todo.includes(id))
        .flatMap((id) => ids.get(id).files.map((f) => [f.path, files[f.path] ?? new Uint8Array()])));
      const checked = await call("content_check", { manifest: JSON.stringify(s.manifest), id: entry.id,
                                                    files: { ...held, ...fetched } });
      if ("refused" in checked) throw new Error(checked.refused);
      for (const id of todo) {
        // A path another installed entry holds now stays (content.py's install keeps it too).
        for (const path of Object.keys(record[id]?.files ?? {})) {
          if (!Object.entries(record).some(([k, o]) => k !== id && path in (o?.files ?? {}))) delete files[path];
        }
        record[id] = { version: ids.get(id).version, source: s.source,
                       files: Object.fromEntries(ids.get(id).files.map((f) => [f.path, f.sha256])) };
        for (const f of ids.get(id).files) files[f.path] = fetched[f.path];
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

  // Content from set (null or the fallback: Azurik-Custom-Content's), remembered, and the list read again.
  const source = (url) => {
    s.source = url || base;
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

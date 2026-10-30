// The tracker's pictures (Step 4.2c3, D3: no picture of the game is in the site or the app): the level maps, the world
// map and the item icons, drawn by the engine (sdk.art, Modkit's drawing) from the player's own image the first time
// the tracker needs them, one part at a time, and kept: by the site in this browser's storage (IndexedDB, DB), by the
// app in its user cache folder (api/art draws there; art/<version>/<name> serves them). They are kept under the
// drawing's version (the tracker's world.art.version), so a new way of drawing them draws them again. A level's map
// can show once its part is drawn, the world map once every level's is.
//
// artStore({app, image, changed}) -> {status, start(version, parts), png(name), bitmap(name)}: status is
// {version, done: [part], total, drawing, error, levels: {level: maps.json entry}, index (maps.json, once the world map
// is drawn)}; changed() runs each time a part is kept.
const DB = "azurkit-art", STORE = "files";

const idb = (() => {
  let opened = null;
  const open = () => opened ??= new Promise((done, fail) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => done(request.result);
    request.onerror = () => fail(request.error);
  });
  const run = async (mode, act) => {
    const db = await open();
    return new Promise((done, fail) => {
      const tx = db.transaction(STORE, mode), request = act(tx.objectStore(STORE));
      tx.oncomplete = () => done(request?.result);
      tx.onerror = tx.onabort = () => fail(tx.error);
    });
  };
  return {
    get: (key) => run("readonly", (s) => s.get(key)),
    put: (entries) => run("readwrite", (s) => { for (const [k, v] of entries) s.put(v, k); }),
    keys: (prefix) => run("readonly", (s) => s.getAllKeys(IDBKeyRange.bound(prefix, `${prefix}￿`))),
  };
})();

export function artStore({ app, image, changed }) {
  const status = { version: null, done: [], total: 0, drawing: null, error: null, levels: {}, index: null,
                   icons: null };
  const bitmaps = new Map();   // name -> Promise<ImageBitmap | null>
  let parts = [], world = true, running = null, poll = null;

  // What is kept of this version: the site's from its storage, the app's from api/art.
  const read = async () => {
    if (app) {
      const reply = await post({ iso: image() ?? "", draw: false });
      return reply && !("refused" in reply) ? take(reply) : null;
    }
    const keys = new Set(await idb.keys(`${status.version}/`));
    status.done = parts.filter((p) => keys.has(`${status.version}/${p}.part`));
    for (const level of status.done.filter((p) => p !== "icons" && !(p in status.levels))) {
      status.levels[level] = (await idb.get(`${status.version}/${level}.part`)).entry;
    }
    status.index = keys.has(`${status.version}/maps.json`) ? await idb.get(`${status.version}/maps.json`) : null;
    status.icons = status.done.includes("icons") ? (await idb.get(`${status.version}/icons.part`)).pictures : null;
  };

  const post = async (body) => {
    try {
      const reply = await fetch("api/art", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify(body) });
      return reply.ok ? reply.json() : null;
    } catch {
      return null;
    }
  };

  const take = (reply) => {
    const more = reply.parts.length !== status.done.length || Boolean(reply.index) !== Boolean(status.index);
    Object.assign(status, { done: reply.parts, total: reply.total, drawing: reply.drawing, error: reply.error,
                            levels: reply.levels, index: reply.index, icons: reply.icons });
    if (more) changed();
    return reply;
  };

  // The app draws on its own thread: the page asks it to and looks every second until it has all.
  const startApp = async () => {
    const reply = await post({ iso: image(), draw: true });
    if (!reply) return;
    if ("refused" in reply) {
      status.error = reply.refused;
      return changed();
    }
    take(reply);
    clearInterval(poll);
    poll = setInterval(async () => {
      const next = await post({ iso: image() ?? "", draw: false });
      if (!next || "refused" in next) return;
      take(next);
      if (!next.drawing) {
        clearInterval(poll);
        changed();
      }
    }, 1000);
  };

  // The site draws in a worker of its own (the engine under Pyodide, with numpy), one part an ask, each kept as
  // it comes; the worker goes once they are all drawn (wasm memory never shrinks).
  const startSite = () => running ??= (async () => {
    const file = image();
    const entry = new URL("worker.mjs", location.href).href;
    const url = URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\n`], { type: "text/javascript" }));
    const worker = new Worker(url, { type: "module" });
    let next = null;
    const answer = () => new Promise((done) => { next = done; });
    worker.onmessage = ({ data }) => next?.(data);
    worker.onerror = (e) => {
      e.preventDefault();
      next?.({ type: "failed", message: e.message || "out of memory?" });
    };
    try {
      const ready = await answer();
      URL.revokeObjectURL(url);
      if (ready.type !== "ready") throw new Error(ready.message);
      const v = status.version;
      for (const part of parts) {
        if (status.done.includes(part)) continue;
        status.drawing = part;
        changed();
        worker.postMessage({ type: "art", file, part });
        const got = await answer();
        if (got.type !== "art") throw new Error(got.reply?.refused ?? got.message);
        const { pictures, entry, thumb } = got.reply;
        await idb.put([...Object.entries(pictures).map(([name, png]) => [`${v}/${name}.png`, png]),
                       ...(thumb ? [[`${v}/${part}.thumb`, thumb]] : []),
                       [`${v}/${part}.part`, entry ? { entry } : { pictures: Object.keys(pictures) }]]);
        status.done = [...status.done, part];
        if (entry) status.levels[part] = entry;
        else status.icons = Object.keys(pictures);
        changed();
      }
      if (!status.index && world) {
        const levels = parts.filter((p) => p !== "icons");
        const given = Object.fromEntries(await Promise.all(levels.map(async (level) =>
          [level, { entry: status.levels[level], thumb: await idb.get(`${v}/${level}.thumb`) }])));
        worker.postMessage({ type: "art_world", parts: given });
        const got = await answer();
        if (got.type !== "art") throw new Error(got.reply?.refused ?? got.message);
        await idb.put([[`${v}/world.png`, got.reply.pictures.world],
                       [`${v}/maps.json`, got.reply.index]]);
        status.index = got.reply.index;
      }
    } catch (error) {
      status.error = `The maps couldn't be drawn: ${String(error?.message ?? error ?? "the browser's storage refused "
        + "them").split("\n").at(-1)}`;
    } finally {
      worker.terminate();
      status.drawing = null;
      running = null;
      changed();
    }
  })();

  return {
    status,
    // This version's pictures: those kept are read, and the rest drawn from the image (when there is one); the world
    // map last, from every level's (all: each level of the world map, unless world is false).
    start: async (version, all, { world: whole = true } = {}) => {
      world = whole;
      if (status.version !== version) {
        Object.assign(status, { version, done: [], levels: {}, index: null, error: null, icons: null });
        bitmaps.clear();
      }
      parts = all;
      status.total = all.length;
      await read();
      changed();
      if (status.done.length === all.length && (status.index || !world)) return;
      if (!image() || running || status.drawing) return;
      return app ? startApp() : startSite();
    },
    // A kept picture's PNG bytes (null: not drawn).
    png: async (name) => {
      if (!app) return (await idb.get(`${status.version}/${name}.png`)) ?? null;
      const blob = await fetch(`art/${status.version}/${name}.png`).then((r) => r.ok ? r.blob() : null);
      return blob ? new Uint8Array(await blob.arrayBuffer()) : null;
    },
    // A kept picture as a bitmap (null: not drawn), read once.
    bitmap: (name) => {
      if (!bitmaps.has(name)) {
        bitmaps.set(name, (async () => {
          try {
            const reply = app ? await fetch(`art/${status.version}/${name}.png`) : null;
            const kept = app ? null : await idb.get(`${status.version}/${name}.png`);   // its PNG's bytes (WebKit's
            const blob = app ? (reply.ok ? await reply.blob() : null)                  // private storage keeps no Blob)
              : kept && new Blob([kept], { type: "image/png" });
            if (blob) return await createImageBitmap(blob);
          } catch {}
          bitmaps.delete(name);   // not drawn yet: asked again once it is
          return null;
        })());
      }
      return bitmaps.get(name);
    },
  };
}

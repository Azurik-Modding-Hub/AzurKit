// The parts of Checks' dresses this browser keeps (Step 4.6o, the Check design's L2), for the engine's worker
// (worker.mjs's checked(): the engine's Parts, tools.characters.parts.STORE): IndexedDB's azurkit-parts holds each part
// (part_codec's bytes) once, under its key ("part"), and for each recipe content's hint the keys its last Check took
// and worked out ("hint": {keys, at}, at the order it was kept in), so a copy of a variant under any name is offered
// what another's Check kept. The engine takes a part only under its own key (what its stage reads and the code's
// digest): another's is a miss, never another answer. PART_HINTS hints at most: keeping one past them drops the least
// recently kept, and every part no hint kept lists. Storage that refuses (a private window) keeps and offers nothing.

import { text } from "./memo.mjs";

export const PARTS = "azurkit-parts", PART_HINTS = 8;
const LEFT_OUT = ["title", "notes", "voice", "sfx", "wavs", "shouts"];   // a recipe's labels and sounds: no part reads them

// A Check's parts hint: the image's id and its recipe's content, its name, folder, labels and sounds left out; a
// built-in's (given by name alone) by its name, its content. A value JSON can't hold throws, as text() does.
export const partsHint = (id, { name, recipe } = {}) => text([id ?? null, recipe
  ? Object.fromEntries(Object.entries(recipe).filter(([field]) => !LEFT_OUT.includes(field))) : name ?? null], true);

// fn(hints, parts) in one transaction of mode over both stores; what it returns, filled as the transaction ran, once it
// completes (null where it fails, or storage is refused).
const parted = (mode, fn) => new Promise((resolve) => {
  let opened;
  try {
    opened = indexedDB.open(PARTS, 1);
  } catch {
    return resolve(null);
  }
  opened.onupgradeneeded = () => ["hint", "part"].forEach((name) => opened.result.createObjectStore(name));
  opened.onerror = () => resolve(null);
  opened.onsuccess = () => {
    const db = opened.result;
    db.onversionchange = () => db.close();   // Clear's delete never waits on a worker
    const done = db.transaction(["hint", "part"], mode), asked = fn(done.objectStore("hint"), done.objectStore("part"));
    done.oncomplete = () => { db.close(); resolve(asked); };
    done.onerror = done.onabort = () => { db.close(); resolve(null); };
  };
});

// Each Uint8Array among values (an object's) let go of in this thread now, not at a GC: once IndexedDB holds its clone
// (put() clones a value as it is called) or the engine its copy. The worker, idle between Checks, gets a GC late or not
// at all, and WebKit keeps a freed copy's pages resident: a Check's dress and parts, kept and offered, left about
// 0.35 GiB a Check in the capped WebKit Variants pass, past its 6 GiB line (Step 4.37e5). Only a view of its whole
// buffer is let go (never one of wasm's heap); a browser without ArrayBuffer's transfer() leaves them to a GC.
export const freed = (values) => {
  for (const bytes of Object.values(values ?? {})) {
    try {
      if (bytes?.byteOffset === 0 && bytes.byteLength === bytes.buffer.byteLength) bytes.buffer.transfer?.(0);
    } catch {}   // a buffer that can't be let go of is a GC's
  }
};

// {key: bytes} kept for hint (none: {}).
export const partsOf = (hint) => parted("readonly", (hints, stored) => {
  const found = {}, listed = hints.get(hint);
  listed.onsuccess = () => {
    for (const key of listed.result?.keys ?? []) {
      const one = stored.get(key);
      one.onsuccess = () => { if (one.result) found[key] = one.result; };
    }
  };
  return found;
});

// hint's Check took the parts keyed taken (each kept already) and worked out made ({key: bytes}, each let go of here
// once kept): those its record lists from now on, it the most recently kept.
export const keepParts = (hint, made, taken) => parted("readwrite", (hints, stored) => {
  for (const [key, bytes] of Object.entries(made)) stored.put(bytes, key);
  freed(made);   // IndexedDB holds their clones
  const kept = [], walk = hints.openCursor();
  walk.onsuccess = () => {
    if (walk.result) {
      if (walk.result.key !== hint) kept.push([walk.result.key, walk.result.value]);
      return walk.result.continue();
    }
    const at = Math.max(0, ...kept.map(([, value]) => value.at)) + 1;
    kept.push([hint, { keys: [...new Set([...taken, ...Object.keys(made)])], at }]);
    kept.sort((a, b) => b[1].at - a[1].at);
    for (const [old] of kept.splice(PART_HINTS)) hints.delete(old);
    hints.put(kept[0][1], hint);
    const used = new Set(kept.flatMap(([, value]) => value.keys)), all = stored.getAllKeys();
    all.onsuccess = () => all.result.filter((key) => !used.has(key)).forEach((key) => stored.delete(key));
  };
  return {};
});

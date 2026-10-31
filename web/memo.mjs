// Kept answers on the site (Step 4.3x; D1008's kept half, D1015's store): the twin of the app's
// src/azurkit/app/memo.py. The engine's small answers that are a pure function of what they are given (the tracker's
// view, the setup's restore, the Randomizer tab's answer, a seed's plan: CALLS) are kept as JSON in this browser
// under the sha256 of the code key (the wheel's integrity, which host.json gives before the worker is up), the
// randomizer database's key (the wheel ships its database, so the integrity stands for it unless a host gives
// dbcache.entry), the call, its arguments canonical (the inputs the call reads, as JSON with sorted keys) and the
// sha256 of what this browser keeps installed (installed.json's record): a change to any of them is a miss, never a
// wrong answer. The page paints a kept answer before the worker is up, then asks the worker as before; the worker's
// answer replaces the paint (confirm: equal by construction, so a difference is logged as a bug and the worker's is
// kept in its place). Never kept: anything with Live on, a tracker ask that marks (toggle) or resets or carries
// Live's kit or inventory, a refusal. An entry holds its call, key and digest: one that doesn't match them is a miss.
// The store is IndexedDB's (idbStore: any refusal, as WebKit's ephemeral context gives, is a miss) or, by default,
// this page's (MemStore). JSON only.

export const FORMAT = 1;
export const CALLS = ["tracker", "restore", "randomizer", "plan"];
export const MOST = 64 << 20;   // MemStore's bytes (counted as the JSON text's UTF-16 length)
const LIVE_ONLY = ["toggle", "kit"];   // a tracker ask that gives one of these (not null) is never kept, as one
const LIVE_TRUE = ["reset", "held"];   // that sets one of these (the tracker reads them by truth: a falsy one is none)
const GIVEN = ["plan", "marks", "kit", "held", "spoiler", "gems", "toggle", "reset"];   // tracking.GIVEN

// value as JSON with its object keys sorted (sorted) or as given; a value JSON can't hold (NaN, infinity, undefined,
// a function, a BigInt) throws, as Python's allow_nan=False does.
export function text(value, sorted = false) {
  const walk = (v) => {
    if (v === null || typeof v === "string" || typeof v === "boolean") return v;
    if (typeof v === "number") {
      if (!Number.isFinite(v)) throw new TypeError("memo: a number JSON can't hold");
      return v;
    }
    if (Array.isArray(v)) return v.map(walk);
    if (typeof v === "object" && [Object.prototype, null].includes(Object.getPrototypeOf(v))) {
      const keys = Object.keys(v);
      return Object.fromEntries((sorted ? keys.sort() : keys).map((k) => [k, walk(v[k])]));
    }
    throw new TypeError(`memo: a ${typeof v} JSON can't hold`);
  };
  return JSON.stringify(walk(value));
}

export async function sha256(string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(string));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

// The tracker's marks as tracking.marks_of reads them (a bare list is the collected spots; null, none), or null for
// marks it refuses (the worker names why). The tracker's own normalizing is the engine's; this only gives one ask's
// forms one key (no marks, {} and the warm-up's null alike).
function marksOf(given) {
  if (given === undefined || given === null) given = {};
  if (Array.isArray(given)) given = { collected: given };
  const known = ["collected", "live", "veto", "slot", "gems"];
  if (typeof given !== "object" || Object.keys(given).some((k) => !known.includes(k))) return null;
  const at = (k, none) => (k in given ? given[k] : none);   // tracker.marks: dict.get(k, none)
  return { collected: at("collected", []), live: at("live", {}), veto: at("veto", []), slot: at("slot", null),
           gems: at("gems", {}) };
}

// call's arguments canonical (as JSON with sorted keys), or null for one never kept.
export function canonical(call, args) {
  if (!CALLS.includes(call)) return null;
  if (call === "tracker") {
    if (!args || typeof args !== "object" || Object.keys(args).some((k) => !GIVEN.includes(k))) return null;
    if (LIVE_ONLY.some((k) => args[k] !== undefined && args[k] !== null) || LIVE_TRUE.some((k) => isSet(args[k]))) {
      return null;
    }
    const marks = marksOf(args.marks);
    if (!marks) return null;
    args = { plan: args.plan ?? null, marks, spoiler: Boolean(args.spoiler), gems: Boolean(args.gems) };
  }
  try {
    return text(args, true);
  } catch {
    return null;
  }
}
const refused = (answer) => Boolean(answer) && typeof answer === "object" && "refused" in answer;
const isSet = (v) => Boolean(v) && !(typeof v === "object" && Object.keys(v).length === 0);

export async function digest(answer) {
  return sha256(text(answer, true));
}

// This page's store: the newest used entries kept to `most`.
export class MemStore {
  constructor(most = MOST) {
    this.most = most;
    this.kept = new Map();
    this.size = 0;
  }

  async get(key) {
    const data = this.kept.get(key);
    if (data === undefined) return null;
    this.kept.delete(key);
    this.kept.set(key, data);
    return data;
  }

  async put(key, data) {
    if (this.kept.has(key)) this.size -= this.kept.get(key).length;
    this.kept.delete(key);
    this.kept.set(key, data);
    this.size += data.length;
    for (const [k, d] of this.kept) {
      if (this.size <= this.most) break;
      this.kept.delete(k);
      this.size -= d.length;
    }
  }
}

// IndexedDB's store `name` (one object store, "memo"): a read or write it refuses is a miss, never an error.
export function idbStore(name = "azurkit-memo") {
  const asked = (mode, fn) => new Promise((resolve) => {
    let opened;
    try {
      opened = indexedDB.open(name, 1);
    } catch {
      return resolve(null);
    }
    opened.onupgradeneeded = () => opened.result.createObjectStore("memo");
    opened.onerror = () => resolve(null);
    opened.onsuccess = () => {
      const db = opened.result;
      try {
        const done = db.transaction("memo", mode), request = fn(done.objectStore("memo"));
        done.oncomplete = () => { db.close(); resolve(request?.result ?? null); };
        done.onerror = done.onabort = () => { db.close(); resolve(null); };
      } catch {
        db.close();
        resolve(null);
      }
    };
  });
  return {
    get: (key) => asked("readonly", (store) => store.get(key)),
    put: (key, data) => asked("readwrite", (store) => store.put(data, key)),
  };
}

// Kept answers in `store` (MemStore by default), a difference confirm finds told to `log` (console.error).
// `space`: {code, entry, installed}: the code key (host.json's integrity), the database's (the same, or
// dbcache.entry), and what this browser keeps installed (installed.json's record, {} with none).
export class Memo {
  constructor({ store = new MemStore(), log = (line) => console.error(line) } = {}) {
    this.store = store;
    this.log = log;
  }

  async key(call, args, { code, entry, installed = {}, live = false } = {}) {
    const canon = canonical(call, args);
    if (live || canon === null || typeof code !== "string" || !code) return null;
    const held = await sha256(text(installed ?? {}, true));
    return sha256([`azurkit-memo ${FORMAT}`, code, entry ?? code, call, canon, held].join("\0"));
  }

  async read(call, key) {
    try {
      const data = await this.store.get(key);
      const entry = typeof data === "string" ? JSON.parse(data) : null;
      if (entry && entry.format === FORMAT && entry.call === call && entry.key === key && "answer" in entry
          && entry.sha256 === await digest(entry.answer)) return entry.answer;
    } catch {
      // a store that refused, or an entry another wrote: a miss
    }
    return null;
  }

  async write(call, key, answer) {
    let data;
    try {
      data = text({ format: FORMAT, call, key, sha256: await digest(answer), answer });
    } catch {
      return;   // an answer JSON can't hold is never kept
    }
    try {
      await this.store.put(key, data);
    } catch {
      // remembering is a convenience
    }
  }

  async get(call, args, space) {
    const key = await this.key(call, args, space);
    return key === null ? null : this.read(call, key);
  }

  async put(call, args, answer, space) {
    const key = await this.key(call, args, space);
    if (key !== null && !refused(answer)) await this.write(call, key, answer);
  }

  // {answer, kept}: the kept answer for args, else work()'s (a refusal, {refused}, is never kept), kept under the key
  // its inputs had as it started.
  async answer(call, args, work, space) {
    const key = await this.key(call, args, space);
    if (key !== null) {
      const kept = await this.read(call, key);
      if (kept !== null) return { answer: kept, kept: true };
    }
    const fresh = await work();
    if (key !== null && !refused(fresh)) await this.write(call, key, fresh);
    return { answer: fresh, kept: false };
  }

  // The worker's answer `fresh` to the ask whose kept answer `kept` the page showed: equal by construction, so a
  // difference is a bug, logged by both digests, and the worker's is kept in its place. true when they agree.
  async confirm(call, args, kept, fresh, space) {
    const [was, now] = [await digest(kept), await digest(fresh)];
    if (was === now) return true;
    this.log(`AzurKit: a kept ${call} answer (${was.slice(0, 12)}) differs from the engine's (${now.slice(0, 12)}): `
             + "a bug, the engine's is kept");
    await this.put(call, args, fresh, space);
    return false;
  }
}

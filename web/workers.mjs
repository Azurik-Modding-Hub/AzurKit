// The site's two engine workers (Step 4.3y; D1006, D1007; the amortize plan's AM-HUB-D): F answers the page's asks,
// and B works ahead on what the page says it will likely ask next (the typed seed's plan and its first view, the
// settled recipe's build, the warm-up's heavy items). Both run worker.mjs, so B's answer is the one F would give, and a
// click whose key is B's finished job takes B's answer at once; one whose key B is still working on follows B's
// records (D1006's bar) and F never starts it again. A worker can't stop a call it runs, so a change of the page's
// list drops B's job by terminate() (a heavy one goes on, unkept, while the list holds no heavy job: want()), and a new
// B loads (from R2.10's snapshot once the engine has it). Cancel answers
// at once, and a build it stops whose key the list still holds goes on as work ahead (the plan's D4: kept when it
// ends, dropped by a change), so Build again waits only for its rest. Memory: one heap (w-reshape): wasm memory never
// shrinks, and WebKit keeps a terminated worker's pages resident while a new worker's heap grows beside them, so the
// worker a job grew stays and runs the next heavy job, a click's or one ahead (the two swap places for it: oneHeap());
// only one whose heap reaches GROWN after a job (or reports none after a heavy one) is replaced. When F
// must go (GROWN, Cancel, a failure) an idle B under KEEP takes its place at once. One heavy job runs at a time, and B's
// work ahead never runs beside F's build: B starts nothing while F builds, and F's build drops B's job ahead (an idle
// B stays: terminated, its pages would stay resident in WebKit and its next load add its own, r1). B starts no
// job, and isn't kept, while the page's tally (both heaps, B's kept answers and the bytes the page holds) reaches
// TALLY, and a new B loads only while the last B's heap when it loaded fits under the line too (or each B would cross
// it, be retired and load again), nor on a computer with fewer than CORES cores. A worker's priority has no web API:
// B runs at the page's (a known flaw, D835), held small by the rules above.
//
// The workers speak worker.mjs's protocol: each is sent one message at a time, so every message it posts until the
// job's last (ends(): its answer) is that job's; {type: "progress"} is a record; {type: "at"} says the await it is in
// (state()'s at, Step 4.3r4t); {type: "failed"} ends the job and
// replaces the worker; {type: "ready"} once loaded (a heap in it is counted). Two are the pool's own (Step 4.4bf):
// {type: "wasm", module}, the engine's wasm a worker compiled, which is sent first to each later worker, which
// instantiates it and compiles none of its own; and {type: "id", id}, the image's id a worker read for the File of its
// job's message, which each later message with that File brings (as id: the File's ends read once a pick, not once a
// message, each a read Safari answers 200 ms late). A shared message (share(): what this
// browser keeps installed, the table pages F read) goes to every worker, and to each new one before its first job;
// it gets no answer. An ask resolves with its job's last message, or {type: "cancelled"} (Cancel), or
// {type: "stopped", message} (its worker stopped: a once or heavy ask, or one stopped twice); answer() hears each of
// its other messages first, progress() its records.
//
// workers({start, ready, told, free, cores, settle, keep, grown, tally, ends, held}) -> {ask, want, cancel, share, hold,
// took, up, state, close}: start(role) makes a worker ("f" or "b"); ready(data) hears F's ready, again when B takes F's
// place; told(data, role) hears what no job asked for (a CSP report, F's failed load, F's start's records); free(gone)
// hears a kept answer's messages when nothing can take them any more. All are called after the pool's own step (a
// microtask later), so they may call the pool. held(messages) is the bytes an answer holds in memory (bytesOf by default).
export const KEEP = 2 ** 30;          // a grown worker's heap: B isn't promoted past it, nor two of them kept
export const SLACK = 2 ** 26;         // a heap this much over the other's is the heavy jobs' (oneHeap())
export const GROWN = 3 * 2 ** 30;     // a worker whose heap reaches it after a job is replaced: a kept heap's own line
export const TALLY = 5 * 2 ** 30;     // the page's line (the plan's default): B starts no job at or past it
export const SETTLE = 250;            // ms the page's list holds still before B starts on it (app.mjs's remember())
export const CORES = 4;               // B only where navigator.hardwareConcurrency is at least this

// A value as one canonical JSON text: object keys sorted, so two recipes that differ only in their keys' order give
// one key, and a property holding undefined left out, as JSON.stringify leaves it. Only JSON's values: anything else
// (a File, a buffer, NaN) is refused by name, since a key that misses an input would serve a wrong answer.
export function canon(value) {
  const walk = (v, path) => {
    if (v === null || typeof v === "boolean" || typeof v === "string") return JSON.stringify(v);
    if (typeof v === "number") {
      if (!Number.isFinite(v)) throw new TypeError(`a key holds ${v} at ${path}`);
      return JSON.stringify(v);
    }
    if (Array.isArray(v)) return `[${v.map((x, i) => walk(x, `${path}[${i}]`)).join(",")}]`;
    if (typeof v === "object" && Object.getPrototypeOf(v) === Object.prototype) {
      return `{${Object.keys(v).filter((k) => v[k] !== undefined).sort()
        .map((k) => `${JSON.stringify(k)}:${walk(v[k], `${path}.${k}`)}`).join(",")}}`;
    }
    throw new TypeError(`a key holds ${Object.prototype.toString.call(v)} at ${path}`);
  };
  return walk(value, "key");
}

// Whether worker.mjs's message data is the last of the job its message started: a seed's "built" is followed by its
// "spoiled"; a vanilla read ends with "vanilla", "opened" or "unread"; the tracker's, plan's and Characters tab's
// calls with their "reply".
export function ends(data, message) {
  switch (message.type) {
    case "build":
      return data.type === "refused" || data.type === "spoiled"
        || data.type === "built" && !(data.report?.plan && !("spoiler" in data.report));
    case "vanilla": return ["vanilla", "opened", "unread"].includes(data.type);
    case "preset": return data.type === "preset" || data.type === "refused";
    case "decode": return data.type === "decoded" || data.type === "refused";
    case "restore": return data.type === "restored";
    case "randomizer": return data.type === "rando";
    default: return data.type === "reply";
  }
}

// The bytes a value holds in buffers and Blobs (a build's segments), for the tally.
export function bytesOf(value, depth = 0) {
  if (value === null || typeof value !== "object" || depth > 8) return 0;
  if (value instanceof ArrayBuffer) return value.byteLength;
  if (ArrayBuffer.isView(value)) return value.byteLength;
  if (typeof Blob !== "undefined" && value instanceof Blob) return value.size;
  return Object.values(value).reduce((n, v) => n + bytesOf(v, depth + 1), 0);
}

export function workers({ start, ready = () => {}, told = () => {}, free = () => {}, cores, settle = SETTLE, keep = KEEP,
                          grown = GROWN, tally = TALLY, ends: last = ends, held: heldBy = bytesOf } = {}) {
  cores ??= globalThis.navigator?.hardwareConcurrency ?? 1;
  let f = null, b = null, dead = null, noB = cores < CORES, closed = false, held = 0, list = [], changed = 0;
  let timer = null, clock = 0, base = 0;   // base: the last B's heap when it loaded
  const queue = [];                      // F's asks not yet sent, in order
  const kept = new Map();                // B's finished jobs by key: {messages, last, bytes, at}
  const taken = new Set();               // keys a click took, F runs, trim() freed or B failed on: B leaves them while
                                         // listed, and while an ask waits on them (asked(); its end frees one unlisted)
  const shared = new Map();              // share()'s messages by type
  const ahead = new WeakSet();           // every message that came from B's work ahead (took())
  const ids = new WeakMap();             // a File the page sent -> its image's id, as a worker read it ({type: "id"})
  let wasm = null;                       // the engine's compiled wasm, as the first worker that compiled it posted it
  const counts = { started: 0, dropped: 0, retired: 0, promoted: 0, demoted: 0, swapped: 0 };
  const now = () => globalThis.performance?.now() ?? Date.now();
  const later = (hook, ...args) => queueMicrotask(() => hook(...args));

  const spawn = (role) => {
    const slot = { role, worker: start(role), loaded: false, heap: 0, job: null, ready: null, last: null, at: null };
    counts.started += 1;
    if (wasm) slot.worker.postMessage({ type: "wasm", module: wasm });   // before anything: its load instantiates it
    slot.worker.onmessage = ({ data }) => heard(slot, data);
    slot.worker.onerror = (e) => {
      e?.preventDefault?.();
      stopped(slot, e?.message ?? "");
    };
    return slot;
  };
  const kill = (slot) => {
    slot.worker.terminate();
    if (slot === f) f = null;
    if (slot === b) b = null;
  };
  const heapOf = (slot) => slot && Number.isFinite(slot.heap) ? slot.heap : 0;
  const keptBytes = () => [...kept.values()].reduce((n, k) => n + k.bytes, 0);
  const total = () => heapOf(f) + heapOf(b) + held + keptBytes();
  const heavyF = () => Boolean(f?.job?.heavy) || queue.some((job) => job.heavy);
  const shown = (job) => !job.ahead || job.adopted;   // a job the page waits on: its records and answers go to it
  const small = (slot) => Number.isFinite(slot.heap) && slot.heap < keep;
  const stays = (slot) => Number.isFinite(slot.heap) && slot.heap < grown;
  const listed = (key) => key !== null && list.some((item) => item.key === key);
  // A key the page's ask still waits on (queued for F, F's job, or B's that a click took): it stays taken while the
  // list drops it, as a list holding it again before that job ends (the picked image read, after an ahead() made
  // while it was read listed no build) would have B build it once more after the job: a second dress of one visit.
  const asked = (key) => queue.some((job) => job.key === key)
    || [f, b].some((slot) => slot?.job && shown(slot.job) && slot.job.key === key);
  const unkeep = (key) => {   // a kept answer nothing can take any more
    const gone = kept.get(key);
    kept.delete(key);
    if (gone) later(free, gone.messages);
  };

  // F must go: an idle loaded B under KEEP takes its place at once (a new B loads later), else a new F loads.
  const replaceF = () => {
    if (f) kill(f);
    if (b?.loaded && !b.job && small(b)) promote();
    else f = spawn("f");
  };
  const promote = () => {
    f = b;
    b = null;
    f.role = "f";
    counts.promoted += 1;
    later(ready, f.ready);
  };
  const dropB = (why = "dropped") => {   // dropped: its work is lost (a change, F's build); else retired
    if (!b) return;
    kill(b);
    counts[why] += 1;
  };

  const run = (slot, job) => {
    slot.job = job;
    slot.at = null;
    if (job.heavy) slot.heap = null;   // known again once the job reports it: none reported means past KEEP
    const id = job.message?.file && ids.get(job.message.file);
    slot.worker.postMessage(id ? { ...job.message, id } : job.message, job.transfer ?? []);
  };

  const heard = (slot, data) => {
    if (closed || (slot !== f && slot !== b)) return;   // a worker this pool dropped
    slot.last = [data?.type ?? null, now()];   // for state(): what a silent worker said last, and when
    if (data?.type === "at") return void (slot.at = data.where);   // for state(): the await its job is in
    if (data?.type === "wasm") return void (wasm ??= data.module ?? null);
    if (data?.type === "id") {
      const file = slot.job?.message?.file;
      if (file && typeof file === "object" && typeof data.id === "string") ids.set(file, data.id);
      return;
    }
    if (typeof data?.heap === "number") slot.heap = data.heap;
    if (data?.type === "csp") return later(told, data, slot.role);   // a report, whatever the worker runs
    if (!slot.loaded) {
      if (data?.type === "ready") {
        slot.loaded = true;
        slot.ready = data;
        if (slot.role === "b") base = heapOf(slot);
        for (const message of shared.values()) slot.worker.postMessage(message);
        if (slot === f) later(ready, data);
      } else if (data?.type === "failed") {   // it didn't load: F's asks get its message, B isn't tried again
        kill(slot);
        if (slot.role === "b") noB = true;
        else {
          dead = data;
          noB = true;
          if (b) kill(b);
          later(told, data, "f");
          for (const job of queue.splice(0)) job.resolve(data);
        }
      } else if (data?.type !== "progress" || slot.role === "f") {   // B's start shows no bar: nothing waits on it
        later(told, data, slot.role);
      }
      return pump();
    }
    const job = slot.job;
    if (!job) return later(told, data, slot.role);
    if (data?.type === "progress") {
      job.record = data;
      if (shown(job)) job.progress?.(data);
      return;
    }
    if (data?.type === "failed") return finish(slot, job, data, true);
    job.messages.push(data);
    if (job.ahead) ahead.add(data);
    if (job.ends(data, job.message)) return finish(slot, job, data, false);
    if (shown(job)) job.answer?.(data);
  };

  const finish = (slot, job, data, failed) => {
    slot.job = null;
    slot.at = null;
    if (job.heavy && slot.heap === null) slot.heap = Infinity;
    if (job.ahead && !job.adopted) {
      if (!failed && listed(job.key)) {
        kept.set(job.key, { messages: job.messages, last: data, bytes: heldBy(job.messages), at: ++clock });
        if (job.kept) later(job.kept, data);
      } else if (!failed) later(free, job.messages);   // one the list dropped while it went on (want()): unkept
      else taken.add(job.key);   // not tried again while listed: a click asks F, which shows the failure itself
      if (failed || !stays(slot) || (f && !small(slot) && !small(f))) dropB("retired");   // never two heaps grown
      trim();
    } else {
      job.resolve(data);
      if (slot === f && (failed || !stays(slot))) replaceF();
      else if (slot === b && (failed || !stays(slot))) dropB("retired");
    }
    pump();
  };

  // A worker stopped (out of memory, say): F's running ask goes to the next F unless it is once or heavy or stopped a
  // worker before; a job a click took from B goes to F the same way; B's own work is dropped, and not tried again while
  // its key stays listed.
  const stopped = (slot, message) => {
    if (closed || (slot !== f && slot !== b)) return;
    if (!slot.loaded) return heard(slot, { type: "failed", message: `The engine stopped (${message})` });
    const job = slot.job;
    slot.job = null;
    if (slot === f) replaceF();
    else dropB("retired");
    if (job && !shown(job)) taken.add(job.key);
    else if (job) {
      if (job.once || job.heavy || job.tries) job.resolve({ type: "stopped", message });
      else {   // the click's own message, if it took the job from B
        Object.assign(job, { message: job.own ?? job.message, tries: 1, ahead: false, adopted: false, record: null,
                             messages: [] });
        queue.unshift(job);
      }
    }
    pump();
  };

  // A cancelled job whose answer the list still wants: it goes on as work ahead, its answer kept when it ends.
  const demote = (job) => {
    for (const data of job.messages) ahead.add(data);
    job.resolve({ type: "cancelled" });
    Object.assign(job, { ahead: true, adopted: false, progress: null, answer: null, resolve: () => {} });
    taken.delete(job.key);
    counts.demoted += 1;
  };

  // B's kept answers holding bytes, oldest first, while the tally is past its line (B doesn't make one again while
  // the list holds it).
  const trim = () => {
    for (const [key, k] of [...kept].sort((x, y) => x[1].at - y[1].at)) {
      if (total() < tally) break;
      if (!k.bytes) continue;
      unkeep(key);
      taken.add(key);
    }
  };

  // The next heavy job runs in the bigger heap, not in a second one: a click's as F (B swaps in), one ahead as B (F swaps
  // out), while both are idle.
  const bigger = (x, y) => Number.isFinite(x?.heap) && Number.isFinite(y?.heap) && x.heap > y.heap + SLACK;
  const next = () => list.find((i) => !kept.has(i.key) && !taken.has(i.key));
  const oneHeap = () => {
    if (!f?.loaded || f.job || !b?.loaded || b.job) return;
    const click = queue[0]?.heavy, ahead = !queue.length && next()?.heavy && !heavyF();
    if (!(click && bigger(b, f)) && !(ahead && bigger(f, b))) return;
    [f, b] = [b, f];
    f.role = "f";
    b.role = "b";
    counts.swapped += 1;
  };

  const pump = () => {
    if (closed) return;
    if (!f && !dead) f = spawn("f");
    oneHeap();
    if (f?.loaded && !f.job && queue.length && !(queue[0].heavy && b?.job?.adopted && b.job.heavy)) {   // one at a time
      const job = queue.shift();
      if (job.heavy && b?.job?.ahead && !b.job.adopted) dropB();   // none beside F's build: B's job ahead goes
      run(f, job);
    }
    // A small ask while F builds, or an aside one (it reads no image) while F runs anything: B answers it.
    const building = !f?.loaded || f.job?.heavy;
    const spare = queue.findIndex((job) => job.anywhere && !job.heavy && (building || job.aside && f.job));
    if (spare >= 0 && b?.loaded && !b.job) run(b, queue.splice(spare, 1)[0]);
    if (total() >= tally && b && !b.job) dropB("retired");
    if (!b && !noB && f?.loaded && !heavyF() && total() + base < tally) b = spawn("b");
    if (!b?.loaded || b.job || heavyF() || total() >= tally) return;
    const wait = changed + settle - now();
    if (wait > 0) {
      clearTimeout(timer);
      timer = setTimeout(pump, wait);
      return;
    }
    const item = next();
    if (item?.heavy && f?.job && bigger(f, b)) return;   // one heap: it waits for F to swap out, not beside F's
    if (item) {
      run(b, { message: item.message, transfer: item.transfer, key: item.key, heavy: Boolean(item.heavy),
               ends: item.ends ?? last, kept: item.kept, ahead: true, adopted: false, messages: [], record: null,
               tries: 0, resolve: () => {} });
    }
  };

  const pool = {
    // An ask of the page's. With a key: B's finished job of that key answers it at once, a running one is followed.
    ask: (message, { key = null, heavy = false, anywhere = false, aside = false, once = false, progress = null,
                     answer = null, transfer = null, ends: end = last } = {}) => new Promise((settle) => {
      const resolve = (data) => {   // its end, however it ends: the list then decides, as want() would have meanwhile
        if (!listed(key) && !asked(key)) taken.delete(key);
        settle(data);
      };
      if (dead) return resolve(dead);
      if (key !== null) {
        const done = kept.get(key);
        if (done) {
          kept.delete(key);
          taken.add(key);
          for (const data of done.messages.slice(0, -1)) answer?.(data);
          resolve(done.last);
          return pump();
        }
        const job = b?.job;
        if (job?.ahead && !job.adopted && job.key === key) {
          taken.add(key);
          Object.assign(job, { adopted: true, heavy: job.heavy || heavy, once, progress, answer, resolve,
                               own: message });
          if (job.record) progress?.(job.record);
          for (const data of job.messages) answer?.(data);
          return;
        }
        taken.add(key);
      }
      queue.push({ message, key, heavy, anywhere, aside, once, progress, answer, transfer, ends: end, resolve,
                   ahead: false, adopted: false, messages: [], record: null, tries: 0 });
      pump();
    }),
    // The work ahead, most wanted first: [{key, message, heavy, transfer, ends, kept}]; kept(its last message) hears a
    // job's end. A job whose key leaves the list is dropped (B's running one by terminate(), a kept one freed); one still
    // listed goes on or stays kept. begin: a pick, not a stream of changes: B needn't wait for the page to hold still.
    want: (items, { begin = false } = {}) => {
      const keys = new Set(items.map((i) => i.key));
      // B's job the list no longer holds is dropped, but a heavy one goes on, unkept, while the list holds no heavy job
      // (a reshape's: none is built ahead): terminated, its pages would stay resident in WebKit beside the heap the next
      // heavy job grows (0.5-0.75 GiB more in a reshape's build, 4.3r4s); ended, its heap is that job's (oneHeap())
      if (b?.job?.ahead && !b.job.adopted && !keys.has(b.job.key) && !(b.job.heavy && !items.some((i) => i.heavy))) {
        dropB();
      }
      for (const key of [...kept.keys()]) if (!keys.has(key)) unkeep(key);
      for (const key of [...taken]) if (!keys.has(key) && !asked(key)) taken.delete(key);
      if (items[0]?.key !== list[0]?.key) changed = begin ? -settle : now();   // an item added after it: no new wait
      list = [...items];
      pump();
    },
    // Cancel: each heavy ask answers {type: "cancelled"} at once. One that runs, for a key the list still holds, is
    // demoted to work ahead (D1007's: kept when it ends, dropped by a change), so Cancel then Build waits only for its
    // rest: F's goes on as B (an idle B under KEEP takes F's place, else a new F loads) where the B slot is free for
    // it, else F is replaced; one a click took from B goes on as B's own, else B is dropped. A light ask goes on.
    cancel: () => {
      for (const job of queue.filter((j) => j.heavy)) {
        queue.splice(queue.indexOf(job), 1);
        job.resolve({ type: "cancelled" });
      }
      const fj = f?.job?.heavy ? f.job : null;
      if (fj && listed(fj.key) && !noB && (!b || b.loaded && !b.job && small(b))) {
        const old = f;
        if (b) promote();
        else f = null;
        b = old;
        b.role = "b";
        demote(fj);
      } else if (fj) {
        f.job = null;
        replaceF();
        fj.resolve({ type: "cancelled" });
      }
      const bj = b?.job?.adopted && b.job.heavy ? b.job : null;
      if (bj && listed(bj.key)) demote(bj);
      else if (bj) {
        b.job = null;
        dropB("retired");
        bj.resolve({ type: "cancelled" });
      }
      pump();
    },
    share: (message) => {
      shared.set(message.type, message);
      for (const slot of [f, b]) if (slot?.loaded) slot.worker.postMessage(message);
    },
    hold: (bytes) => {
      held = bytes;
      trim();
      pump();
    },
    took: (data) => ahead.has(data),
    // F answers (or its queue does): not a worker that will be replaced when its running job ends.
    up: () => Boolean(f?.loaded && (!f.job || stays(f))),
    state: () => {
      const of = (slot) => slot && { loaded: slot.loaded, heap: slot.heap,
                                     job: slot.job && (slot.job.key ?? slot.job.message.type),
                                     last: slot.last && [slot.last[0], Math.round(now() - slot.last[1])], at: slot.at };
      return { f: of(f), b: of(b), queued: queue.length, kept: [...kept.keys()], tally: total(), ...counts };
    },
    close: () => {
      closed = true;
      clearTimeout(timer);
      for (const slot of [f, b]) if (slot) kill(slot);
    },
  };
  pump();   // F loads now; B once F is ready
  return pool;
}

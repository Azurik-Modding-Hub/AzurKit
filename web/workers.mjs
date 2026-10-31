// The site's two engine workers (Step 4.3y; D1006, D1007; the amortize plan's AM-HUB-D): F answers the page's asks,
// and B works ahead on what the page says it will likely ask next (the typed seed's plan and its first view, the
// settled recipe's build, the warm-up's heavy items). Both run worker.mjs, so B's answer is the one F would give, and a
// click whose key is B's finished job takes B's answer at once; one whose key B is still working on follows B's
// records (D1006's bar) and F never starts it again. A worker can't stop a call it runs, so a change of the page's
// list drops B's job by terminate(), and a new B loads (from R2.10's snapshot once the engine has it). Cancel answers
// at once, and a build it stops whose key the list still holds goes on as work ahead (the plan's D4: kept when it
// ends, dropped by a change), so Build again waits only for its rest. Memory: a worker whose heap reaches KEEP after a
// job (or reports none after a heavy one) is replaced (app.mjs's rule: wasm memory never shrinks); when F must go
// (KEEP, Cancel, a failure) an idle B under KEEP takes its place at once. One heavy job runs at a time: B starts
// nothing while F builds, and F's build drops B's heavy job. B starts no job, and isn't kept, while the page's tally
// (both heaps, B's kept answers and the bytes the page holds) reaches TALLY, nor on a computer with fewer than CORES
// cores. A worker's priority has no web API: B runs at the page's (a known flaw, D835), held small by the rules above.
//
// The workers speak worker.mjs's protocol: each is sent one message at a time, so every message it posts until the
// job's last (ends(): its answer) is that job's; {type: "progress"} is a record; {type: "failed"} ends the job and
// replaces the worker; {type: "ready"} once loaded (a heap in it is counted). A shared message (share(): what this
// browser keeps installed, the table pages F read) goes to every worker, and to each new one before its first job;
// it gets no answer. An ask resolves with its job's last message, or {type: "cancelled"} (Cancel), or
// {type: "stopped", message} (its worker stopped: a once or heavy ask, or one stopped twice); answer() hears each of
// its other messages first, progress() its records.
//
// workers({start, ready, told, cores, settle, keep, tally, ends}) -> {ask, want, cancel, share, hold, took, state,
// close}: start(role) makes a worker ("f" or "b"); ready(data) hears F's ready, again when B takes F's place;
// told(data, role) hears what no job asked for (a CSP report, F's failed load). Both are called after the pool's own
// step (a microtask later), so they may call the pool.
export const KEEP = 2 ** 30;          // a worker whose heap reaches it after a job is replaced (app.mjs's KEEP)
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

export function workers({ start, ready = () => {}, told = () => {}, cores, settle = SETTLE, keep = KEEP,
                          tally = TALLY, ends: last = ends } = {}) {
  cores ??= globalThis.navigator?.hardwareConcurrency ?? 1;
  let f = null, b = null, dead = null, noB = cores < CORES, closed = false, held = 0, list = [], changed = 0;
  let timer = null, clock = 0;
  const queue = [];                      // F's asks not yet sent, in order
  const kept = new Map();                // B's finished jobs by key: {messages, last, bytes, at}
  const taken = new Set();               // keys a click took, F runs, trim() freed or B failed on: B leaves them while
                                         // listed
  const shared = new Map();              // share()'s messages by type
  const ahead = new WeakSet();           // every message that came from B's work ahead (took())
  const counts = { started: 0, dropped: 0, retired: 0, promoted: 0, demoted: 0 };
  const now = () => globalThis.performance?.now() ?? Date.now();
  const later = (hook, ...args) => queueMicrotask(() => hook(...args));

  const spawn = (role) => {
    const slot = { role, worker: start(role), loaded: false, heap: 0, job: null, ready: null };
    counts.started += 1;
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
  const listed = (key) => key !== null && list.some((item) => item.key === key);

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
    if (job.heavy) slot.heap = null;   // known again once the job reports it: none reported means past KEEP
    slot.worker.postMessage(job.message, job.transfer ?? []);
  };

  const heard = (slot, data) => {
    if (closed || (slot !== f && slot !== b)) return;   // a worker this pool dropped
    if (typeof data?.heap === "number") slot.heap = data.heap;
    if (!slot.loaded) {
      if (data?.type === "ready") {
        slot.loaded = true;
        slot.ready = data;
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
      } else {
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
    if (job.heavy && slot.heap === null) slot.heap = Infinity;
    if (job.ahead && !job.adopted) {
      if (!failed) {
        kept.set(job.key, { messages: job.messages, last: data, bytes: bytesOf(job.messages), at: ++clock });
      } else taken.add(job.key);   // not tried again while listed: a click asks F, which shows the failure itself
      if (failed || !(slot.heap < keep)) dropB("retired");   // B after any job past KEEP: its answer is kept
      trim();
    } else {
      job.resolve(data);
      if (slot === f && (failed || !(slot.heap < keep))) replaceF();
      else if (slot === b && (failed || !(slot.heap < keep))) dropB("retired");
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
      kept.delete(key);
      taken.add(key);
    }
  };

  const pump = () => {
    if (closed) return;
    if (!f && !dead) f = spawn("f");
    if (f?.loaded && !f.job && queue.length) {
      const job = queue.shift();
      if (job.heavy && b?.job?.heavy && b.job.ahead && !b.job.adopted) dropB();   // one heavy job at a time
      run(f, job);
    }
    const spare = queue.findIndex((job) => job.anywhere && !job.heavy);   // a small ask while F works: B answers it
    if (spare >= 0 && (!f?.loaded || f.job) && b?.loaded && !b.job) run(b, queue.splice(spare, 1)[0]);
    if (total() >= tally && b && !b.job) dropB("retired");
    if (!b && !noB && f?.loaded && !heavyF() && total() < tally) b = spawn("b");
    if (!b?.loaded || b.job || heavyF() || total() >= tally) return;
    const wait = changed + settle - now();
    if (wait > 0) {
      clearTimeout(timer);
      timer = setTimeout(pump, wait);
      return;
    }
    const item = list.find((i) => !kept.has(i.key) && !taken.has(i.key));
    if (item) {
      run(b, { message: item.message, transfer: item.transfer, key: item.key, heavy: Boolean(item.heavy),
               ends: item.ends ?? last, ahead: true, adopted: false, messages: [], record: null, tries: 0,
               resolve: () => {} });
    }
  };

  const pool = {
    // An ask of the page's. With a key: B's finished job of that key answers it at once, a running one is followed.
    ask: (message, { key = null, heavy = false, anywhere = false, once = false, progress = null, answer = null,
                     transfer = null, ends: end = last } = {}) => new Promise((resolve) => {
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
      queue.push({ message, key, heavy, anywhere, once, progress, answer, transfer, ends: end, resolve,
                   ahead: false, adopted: false, messages: [], record: null, tries: 0 });
      pump();
    }),
    // The work ahead, most wanted first: [{key, message, heavy, transfer, ends}]. A job whose key leaves the list is
    // dropped (B's running one by terminate(), a kept one freed); one still listed goes on or stays kept.
    want: (items) => {
      const keys = new Set(items.map((i) => i.key));
      if (b?.job?.ahead && !b.job.adopted && !keys.has(b.job.key)) dropB();
      for (const key of [...kept.keys()]) if (!keys.has(key)) kept.delete(key);
      for (const key of [...taken]) if (!keys.has(key)) taken.delete(key);
      if (items.map((i) => i.key).join("\n") !== list.map((i) => i.key).join("\n")) changed = now();
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
    state: () => {
      const of = (slot) => slot && { loaded: slot.loaded, heap: slot.heap,
                                     job: slot.job && (slot.job.key ?? slot.job.message.type) };
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

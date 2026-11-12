// The site's hashes (AM-HUB-E): sha256 in WebCrypto, the browser's native one (about 10x wasm's), and md5, which WebCrypto
// lacks, in wasm (md5.wasm, from native/web/md5.c; about 3x Pyodide's hashlib: no copy into the engine's heap). Both off
// the engine's thread's Python, on bytes read from a File or a Blob with awaited reads, so neither heap holds them long.
const RUN = 128 << 20, HASHERS = 3;
// Where each read of a File waits (Safari's: WebKit's, the perf gate's lag model's 200 ms whatever its size), each of
// the HASHERS of an image's check (hashedApart's: the pick, Verify, a Save's) keeps AHEAD read in flight beyond the run it
// digests, so the wait overlaps its lane's other read and digests (Step 4.4bg). A build's hash of the files it changed
// (worker.mjs, hashed's default) reads none ahead: it runs in the engine's worker beside Pyodide's heap, where reads
// ahead made a seed build (S24) 0.31-0.39 GiB heavier at capped-site's peak for no time. Chromium's and Firefox's reads
// don't wait so, and Chromium's browser process reads the File for a Save's download as for its check: its Saves took
// 0.4-0.6 s longer with reads ahead, so there a lane reads one run at a time.
const AGENT = globalThis.navigator?.userAgent ?? "";
export const AHEAD = /AppleWebKit/.test(AGENT) && !/Chrome\//.test(AGENT) ? 1 : 0;
const CHUNK = 1 << 20;   // native/web/md5.c's
// A character's dress is the most the page's workers hold at once (keylord's build: about 1.6 GiB of WebKit's page):
// worker.mjs holds DRESSING (shared) while an ask that carries a character runs, and the rest of an image, hashed in
// the background after its pick, gives way to it (dressed()): its runs in flight, up to 768 MiB in Safari, took the
// kept-dress test's WebKit page from 1.7-1.8 to 2.7-2.9 GiB at its peak when a build followed the pick (Step 4.4ci25).
export const DRESSING = "azurkit-dressing";
// A Save made while the rest is hashed waits for its digests (app.mjs's checkSave, Step 4.4bl), holding WAITED (shared)
// meanwhile: the rest is then the Save's own hash, so it no longer gives way to a dress and reads as the Save's own
// hash would, every lane with its read ahead; else a Save after a dress waited on one run at a time (Step 4.4stack2).
export const WAITED = "azurkit-rest-waited";
const YIELD_MS = 100;   // between a lane's looks while it gives way
// The rest's say before its next read: 1 to give way (a dress runs and no Save waits on it), -1 while a Save waits on
// it, else 0.
export const dressed = async () => {
  const held = ((await globalThis.navigator?.locks?.query?.())?.held ?? []).map((lock) => lock.name);
  return held.includes(WAITED) ? -1 : held.includes(DRESSING) ? 1 : 0;
};
const hex = (buffer) => Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, "0")).join("");

let wasm = null;
export async function md5Ready() {
  if (wasm) return;
  const module = await fetch(new URL("md5.wasm", import.meta.url));
  if (!module.ok) throw new Error(`md5.wasm: HTTP ${module.status}`);
  wasm = (await WebAssembly.instantiate(await module.arrayBuffer())).instance.exports;
}

function md5(bytes) {
  const buffer = new Uint8Array(wasm.memory.buffer, wasm.md5_buffer(), CHUNK);
  wasm.md5_begin();
  let at = 0;
  for (; bytes.length - at > CHUNK; at += CHUNK) {
    buffer.set(bytes.subarray(at, at + CHUNK));
    wasm.md5_blocks(CHUNK);
  }
  buffer.set(bytes.subarray(at));
  const out = wasm.md5_end(bytes.length - at);
  return hex(wasm.memory.buffer.slice(out, out + 16));
}

// {key: sha256} of each of files ([key, offset, size, patches]) of source (a File or a Blob), runs of up to longest read
// HASHERS at a time, each file's digest taken in turn; progress(done, total) hears the bytes. A file with patches
// ([[its offset, bytes]...]; md5Ready first) is hashed with them over it, and its md5 comes as "md5:<path>" for a key
// "file:<path>". A source that gives fewer bytes than a run asks (the image got shorter since its pick) throws, as a read
// a browser refuses (WebKit's, Chromium's) does. Each run's buffer is freed once its digests are taken (transfer(0)), not
// left to a GC: WebKit counted the runs a check had read, not the three it holds (a Save's check, S49 capped-site: about
// 1.3 GiB less at its peak); a lane holds at most ahead + 1 runs (an image's check AHEAD + 1). at(step) hears where each
// of the HASHERS is: the run whose read it awaits (its number and offset), its digests or done, so a check that stalls
// says which await it waits on (Step 4.3r4t). A hash no ask waits on (worker.mjs's rest of an image) gives way
// (yields: an async () => > 0 to wait, dressed() in a browser): while it says so, no lane starts a read, each
// digests what it has in flight and then waits; it reads with one run in flight (one lane's, none ahead) from its
// start, not only once it gave way, as the page holds or will hold what it gives way to (a dress's heap, which wasm
// never gives back): its runs never sit on top of a dress, during it or after (Step 4.4ci25), and WebKit keeps what
// its reads held at once resident (the capped Variants pass 0.15 GiB lower, Step 4.37e5). Once an ask waits on it
// (yields says < 0: a Save, WAITED) it reads as that ask's own hash would, every lane again (widen()), and gives way
// no more while it does.
export async function hashed(source, files, progress = () => {}, longest = RUN, at = () => {}, ahead = 0,
                             yields = null) {
  const runs = [];
  for (const entry of [...files].sort((a, b) => a[1] - b[1])) {
    const run = runs.at(-1), [, at, size] = entry;
    if (run && at >= run.end && at + size - run.start <= longest) {
      run.files.push(entry);
      run.end = at + size;
    } else {
      runs.push({ start: at, end: at + size, files: [entry] });
    }
  }
  const digests = {}, total = runs.reduce((n, run) => n + run.end - run.start, 0), count = runs.length;
  const lanes = Array(HASHERS).fill("idle");
  const step = (lane, what) => {
    lanes[lane] = what;
    at(lanes.join(", "));
  };
  let done = 0;
  progress(done, total);
  const read = async (run) => new Uint8Array(await source.slice(run.start, run.end).arrayBuffer());
  const taken = Array.from({ length: HASHERS }, () => []);   // each lane's runs read or being read, oldest first
  const take = (mine) => {
    if (!runs.length) return;
    const run = runs.shift(), reading = read(run);
    reading.catch(() => {});   // awaited in its turn; a lane that throws first leaves its next one unawaited
    mine.push({ run, k: count - runs.length, reading });
  };
  let narrow = false;   // one run in flight, lane 0's (a hash no ask waits on, or one that gave way), till an ask waits
  const given = async (lane) => {   // once nothing it gives way to runs; its last say
    narrow = true;
    let say;
    for (let first = true; (say = await yields()) > 0; first = false) {
      if (first) step(lane, "giving way");
      await new Promise((later) => setTimeout(later, YIELD_MS));
    }
    return say;
  };
  const busy = Array(HASHERS).fill(false), pumps = [];
  const widen = () => {   // an ask waits on it: every lane reads again, each refilled in its own turn or started here
    narrow = false;
    taken.forEach((mine, lane) => {
      if (busy[lane]) return;
      for (let k = mine.length; k <= ahead; k++) take(mine);
      if (mine.length) pump(lane);
    });
  };
  const pump = (lane) => {   // a lane: its runs read and digested in turn, each refilled as it goes
    const mine = taken[lane];
    busy[lane] = true;
    const going = (async () => {
      try {
        for (let item; (item = mine[0]);) {
          const { run, k } = item;
          step(lane, `run ${k}/${count} read at ${Math.floor(run.start / 2 ** 20)} MiB`);
          const bytes = await item.reading;
          if (bytes.length !== run.end - run.start) throw new Error("the image got shorter after it was picked");
          step(lane, `run ${k}/${count} digest`);
          for (const [key, at, size, patches] of run.files) {
            const view = bytes.subarray(at - run.start, at - run.start + size);
            for (const [where, patch] of patches ?? []) view.set(patch, where);
            const sha = crypto.subtle.digest("SHA-256", view);   // WebCrypto's thread, while md5 takes this one
            if (patches) digests[key.replace("file:", "md5:")] = md5(view);
            digests[key] = hex(await sha);
          }
          bytes.buffer.transfer?.(0);   // its memory freed now, not at the next GC: WebCrypto and md5 copied what they read
          mine.shift();
          done += run.end - run.start;
          progress(done, total);
          const say = yields ? await yields() : 0;
          if (say > 0) {   // its read ahead digested first, then none until it may go on
            narrow = true;
            if (mine.length) continue;
            if (await given(lane) < 0) widen();
          } else if (say < 0 && narrow) widen();
          if (!narrow) for (let k = mine.length; k <= ahead; k++) take(mine);
          else if (!lane && !mine.length) take(mine);
        }
      } finally {
        busy[lane] = false;
      }
      step(lane, "done");
    })();
    going.catch(() => {});   // awaited below, but one may throw while an earlier one is awaited
    pumps.push(going);
  };
  if (yields) {   // a hash no ask waits on: one run in flight from its start, every lane once an ask waits on it
    let say = await yields();
    if (say > 0) say = await given(0);
    narrow = !(say < 0);
  }
  if (narrow) take(taken[0]);
  else for (let k = 0; k <= ahead; k++) taken.forEach(take);   // runs 1..HASHERS first, one a lane
  taken.forEach((_, lane) => pump(lane));
  for (let n = 0; n < pumps.length;) {   // with the lanes widen() started again meanwhile
    n = pumps.length;
    await Promise.all(pumps);
  }
  return digests;
}

// hashed in a worker of its own that ends with it (hashworker.mjs; started from its own URL on a page sw.js controls,
// else from a blob: URL so that it keeps the page's CSP: app.mjs's engine's way), as an image's whole check takes memory
// the thread it runs in wouldn't give back; hashed here where a worker can't start one.
// Its worker's at() comes as at("hash worker: …"), and at("hash worker: started") until its first. Each worker
// is held here (apart) until it settles: Firefox collects a Worker object that nothing holds (its own handlers don't),
// and the messages its worker posted last, its digests among them, never came, so about one check in 100 never
// settled (Step 4.3r4t: two full gates' characters tab waited 300 s for the USA image's answer).
// yields: it gives way to a character's dress (dressed()), as a hash no ask waits on does.
const apart = new Set();
export function hashedApart(source, rows, progress = () => {}, longest = RUN, at = () => {}, yields = false) {
  let worker, url;
  try {
    const entry = new URL("hashworker.mjs", import.meta.url).href;
    url = globalThis.navigator?.serviceWorker?.controller?.scriptURL === new URL("sw.js", import.meta.url).href ? entry
      : URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\n`], { type: "text/javascript" }));
    worker = new Worker(url, { type: "module" });
    apart.add(worker);
  } catch {
    return hashed(source, rows, progress, longest, at, AHEAD, yields ? dressed : null);
  }
  return new Promise((resolve, reject) => {
    const over = (settle, value) => {
      apart.delete(worker);
      worker.terminate();
      URL.revokeObjectURL(url);
      settle(value);
    };
    worker.onmessage = ({ data }) => {
      if (data.digests) over(resolve, data.digests);
      else if ("error" in data) over(reject, new Error(data.error));
      else if ("at" in data) at(`hash worker: ${data.at}`);
      else progress(data.done, data.total);
    };
    worker.onerror = (e) => {
      e.preventDefault();
      over(reject, new Error(e.message || "the hash's worker stopped"));
    };
    worker.postMessage({ source, rows, longest, yields });
    at("hash worker: started");
  });
}

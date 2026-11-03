// The site's hashes (AM-HUB-E): sha256 in WebCrypto, the browser's native one (about 10x wasm's), and md5, which WebCrypto
// lacks, in wasm (md5.wasm, from native/web/md5.c; about 3x Pyodide's hashlib: no copy into the engine's heap). Both off
// the engine's thread's Python, on bytes read from a File or a Blob with awaited reads, so neither heap holds them long.
const RUN = 128 << 20, HASHERS = 3;
const CHUNK = 1 << 20;   // native/web/md5.c's
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
// 1.3 GiB less at its peak). at(step) hears where each of its HASHERS is: a run's read (its number and offset), its
// digests or done, so a check that stalls says which await it waits on (Step 4.3r4t).
export async function hashed(source, files, progress = () => {}, longest = RUN, at = () => {}) {
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
  await Promise.all(Array.from({ length: HASHERS }, async (_, lane) => {
    for (let run; (run = runs.shift());) {
      const k = count - runs.length;
      step(lane, `run ${k}/${count} read at ${Math.floor(run.start / 2 ** 20)} MiB`);
      const bytes = new Uint8Array(await source.slice(run.start, run.end).arrayBuffer());
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
      done += run.end - run.start;
      progress(done, total);
    }
    step(lane, "done");
  }));
  return digests;
}

// hashed in a worker of its own that ends with it (hashworker.mjs; started from its own URL on a page sw.js controls,
// else from a blob: URL so that it keeps the page's CSP: app.mjs's engine's way), as an image's whole check takes memory
// the thread it runs in wouldn't give back; hashed here where a worker can't start one.
// Its worker's at() comes as at("hash worker: …"), and at("hash worker: started") until its first. Each worker
// is held here (apart) until it settles: Firefox collects a Worker object that nothing holds (its own handlers don't),
// and the messages its worker posted last, its digests among them, never came, so about one check in 100 never
// settled (Step 4.3r4t: two full gates' characters tab waited 300 s for the USA image's answer).
const apart = new Set();
export function hashedApart(source, rows, progress = () => {}, longest = RUN, at = () => {}) {
  let worker, url;
  try {
    const entry = new URL("hashworker.mjs", import.meta.url).href;
    url = globalThis.navigator?.serviceWorker?.controller?.scriptURL === new URL("sw.js", import.meta.url).href ? entry
      : URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\n`], { type: "text/javascript" }));
    worker = new Worker(url, { type: "module" });
    apart.add(worker);
  } catch {
    return hashed(source, rows, progress, longest, at);
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
    worker.postMessage({ source, rows, longest });
    at("hash worker: started");
  });
}

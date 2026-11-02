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

// {key: sha256} of each of files ([key, offset, size, patches]) of source (a File or a Blob), RUNS of up to 128 MiB read
// HASHERS at a time, each file's digest taken in turn; progress(done, total) hears the bytes. A file with patches
// ([[its offset, bytes]...]; md5Ready first) is hashed with them over it, and its md5 comes as "md5:<path>" for a key
// "file:<path>". A source that gives fewer bytes than a run asks (the image got shorter since its pick) throws, as a read
// a browser refuses (WebKit's, Chromium's) does.
export async function hashed(source, files, progress = () => {}) {
  const runs = [];
  for (const entry of [...files].sort((a, b) => a[1] - b[1])) {
    const run = runs.at(-1), [, at, size] = entry;
    if (run && at >= run.end && at + size - run.start <= RUN) {
      run.files.push(entry);
      run.end = at + size;
    } else {
      runs.push({ start: at, end: at + size, files: [entry] });
    }
  }
  const digests = {}, total = runs.reduce((n, run) => n + run.end - run.start, 0);
  let done = 0;
  progress(done, total);
  await Promise.all(Array.from({ length: HASHERS }, async () => {
    for (let run; (run = runs.shift());) {
      const bytes = new Uint8Array(await source.slice(run.start, run.end).arrayBuffer());
      if (bytes.length !== run.end - run.start) throw new Error("the image got shorter after it was picked");
      for (const [key, at, size, patches] of run.files) {
        const view = bytes.subarray(at - run.start, at - run.start + size);
        for (const [where, patch] of patches ?? []) view.set(patch, where);
        const sha = crypto.subtle.digest("SHA-256", view);   // WebCrypto's thread, while md5 takes this one
        if (patches) digests[key.replace("file:", "md5:")] = md5(view);
        digests[key] = hex(await sha);
      }
      done += run.end - run.start;
      progress(done, total);
    }
  }));
  return digests;
}

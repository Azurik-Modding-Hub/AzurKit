// The site's engine: AzurKit's wheel under Pyodide 314 in a module worker, one worker per build (WEB §3.6). The page
// starts it from a blob: URL that imports this file, so the page's CSP holds here too (WEB §6.4). Pyodide comes from
// this site alone; the wheel, fetched with the integrity host.json gives, is unpacked without its dependencies
// (WEB §6.3). The player's image is mounted read-only (WORKERFS, read in blocks: readInBlocks) and azurkit.sdk reads
// it and decides every output byte: the page gets the build as segments (WEB §3.4), spans of the image ("copy"), the
// bytes the build writes ("bytes") and zeros past the image's end ("zero"), which it joins into a Blob.
//
// One PyProxy only (Step 4.1d3): ENGINE's function, kept for the worker's life. It hands back plain JS values, so this
// file never drops a PyProxy for Pyodide's FinalizationRegistry to free later. That cleanup needs the GIL, and WebKit
// runs it inside FileReaderSync, under WORKERFS's read of the image, while CPython has released the GIL around read():
// Safari's build stopped with NoGilError there. Chromium runs it only between tasks.
//
// In:  {type: "build", file, packs: {name: {parameter: value}}, xbr: [operation]}, {type: "vanilla", file},
//      {type: "preset", recipe: {packs, xbr}, report}, {type: "decode", text}, {type: "restore", setup}
// Out: {type: "ready", catalog, version}, {type: "built", report, size, segments}, {type: "refused", message}
//      (the engine's refusal, which names what and why, never game bytes), {type: "failed", message},
//      {type: "vanilla", release, label, packs} (the image's own value of each slider at a site of its XBE),
//      {type: "opened", preset} (the image is an AzurKit build: its recipe, sdk.open_build of the files it changed),
//      {type: "preset", fragment} (the share link's #p=…), {type: "decoded", preset} (a link's recipe),
//      {type: "restored", ticked, values, xbr, dropped} (the remembered setup, sdk.restore), {type: "csp", directive,
//      blocked}
const base = new URL("./", import.meta.url);
const post = (message, transfer = []) => self.postMessage(message, transfer);
self.addEventListener("securitypolicyviolation", (e) =>
  post({ type: "csp", directive: e.violatedDirective, blocked: e.blockedURI }));

const lastLine = (error) => String(error?.message ?? error).trim().split("\n").at(-1);

// engine(request) -> a plain JS object: {catalog, version}, {report, size, segments} or {refused} (a refusal is a
// ValueError or OSError, by its message); anything else raises. to_js copies each piece's bytes into its own buffer.
const ENGINE = `
from js import Object
from pyodide.ffi import to_js

import azurkit
from azurkit import sdk
from azurkit.core import iso


def engine(request):
    def js(value):
        return to_js(value, dict_converter=Object.fromEntries, create_pyproxies=False)

    if request.type == "catalog":
        return js({"catalog": sdk.catalog(), "version": azurkit.__version__})
    if request.type == "restore":
        return js(sdk.restore(request.setup.to_py() if hasattr(request.setup, "to_py") else request.setup))
    if request.type in ("vanilla", "open", "preset", "decode"):
        try:
            if request.type == "vanilla":
                return js(sdk.vanilla(request.recipe.iso))
            if request.type == "open":
                return js({"preset": sdk.open_build(request.recipe.iso, whole=False)})
            if request.type == "preset":
                report = request.report.to_py() if request.report else None
                return js({"fragment": sdk.preset_encode(request.recipe.to_py(), report)})
            return js({"preset": sdk.preset_decode(request.text)})
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    try:
        image, report = sdk.image(request.recipe.to_py())
    except (OSError, ValueError) as exc:
        return js({"refused": str(exc)})
    pieces = [{"kind": "copy", "offset": p.offset, "size": p.size} if isinstance(p, iso.Copy)
              else {"kind": "zero", "size": p.size} if isinstance(p, iso.Zero)
              else {"kind": "bytes", "size": p.size, "data": p.data} for p in image.segments()]
    return js({"report": report, "size": image.size, "segments": pieces})


engine`;

// The image is read in blocks (Step 4.1g2). WebKit answers each read of a File's slice after about 200 ms, whatever
// its size (2 KiB and 64 MiB alike), and a build read the image about 650 times through WORKERFS (the folders'
// tables, which every iso.Reader reads again, and a 4 KiB read after each 8 MiB one): 131 s a build, 4 s in
// Chromium. So each read is served from what a File's blocks already hold, else from a block read for it: a 1 MiB
// page for a read under 1 MiB (the tables), else a 64 MiB block (a file's bytes); the last PAGES pages and BLOCKS
// blocks of each File are kept (160 MiB at most). Each message brings its own File object, so nothing outlives the
// message that read it.
const PAGE = 1 << 20, BLOCK = 64 << 20, PAGES = 32, BLOCKS = 2;
function readInBlocks(WORKERFS) {
  const kept = new WeakMap();   // File -> its unit -> index -> bytes, the least recently used first
  const units = [[BLOCK, BLOCKS], [PAGE, PAGES]];
  WORKERFS.stream_ops.read = (stream, buffer, offset, length, position) => {
    const file = stream.node.contents, end = Math.min(position + length, file.size);
    if (!(position < end)) return 0;
    if (!kept.has(file)) kept.set(file, new Map(units.map(([unit]) => [unit, new Map()])));
    const caches = kept.get(file);
    for (let at = position; at < end;) {
      const [unit, keep] = units.find(([u]) => caches.get(u).has(Math.floor(at / u))) ?? units[length < PAGE ? 1 : 0];
      const cache = caches.get(unit), index = Math.floor(at / unit);
      let data = cache.get(index);
      if (data) {
        cache.delete(index);   // used last now
      } else {
        data = new Uint8Array(WORKERFS.reader.readAsArrayBuffer(file.slice(index * unit, (index + 1) * unit)));
        if (cache.size >= keep) cache.delete(cache.keys().next().value);
      }
      cache.set(index, data);
      const from = at - index * unit, n = Math.min(end - at, data.length - from);
      if (!(n > 0)) throw new Error("the image got shorter while the engine read it");
      buffer.set(data.subarray(from, from + n), offset + (at - position));
      at += n;
    }
    return end - position;
  };
}

async function load() {
  const site = await (await fetch(new URL("host.json", base))).json();
  const pyodide = new URL("pyodide/", base).href;
  const { loadPyodide } = await import(new URL("pyodide.mjs", pyodide).href);
  const py = await loadPyodide({
    indexURL: pyodide, lockFileURL: new URL("pyodide-lock.json", pyodide).href, packageBaseUrl: pyodide,
    stdout: () => {}, stderr: () => {},
  });
  readInBlocks(py.FS.filesystems.WORKERFS);
  const wheel = await fetch(new URL(site.wheel, base), { integrity: site.integrity });
  if (!wheel.ok) throw new Error(`${site.wheel}: HTTP ${wheel.status}`);
  py.unpackArchive(await wheel.arrayBuffer(), "wheel",
                   { extractDir: py.runPython("import site; site.getsitepackages()[0]") });
  return { py, engine: py.runPython(ENGINE) };
}

// The image's own values of the sliders at its XBE's sites, or, when it is an AzurKit build, its recipe; the image
// mounted only for the read: a build mounts it again, then this worker is replaced.
function vanilla({ py, engine }, file) {
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  try {
    const recipe = { iso: `/in/${file.name}` };
    const read = engine({ type: "vanilla", recipe });
    if (!("refused" in read)) return post({ type: "vanilla", ...read });
    const opened = engine({ type: "open", recipe });
    if (!("refused" in opened)) post({ type: "opened", preset: opened.preset });
  } finally {
    py.FS.unmount("/in");
  }
}

function build({ py, engine }, file, packs, xbr) {
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  const made = engine({ type: "build", recipe: { iso: `/in/${file.name}`, packs, xbr } });
  if ("refused" in made) return post({ type: "refused", message: made.refused });
  post({ type: "built", ...made }, made.segments.flatMap((s) => s.kind === "bytes" ? [s.data.buffer] : []));
}

try {
  const loaded = await load();
  self.onmessage = ({ data }) => {
    if (!["build", "vanilla", "preset", "decode", "restore"].includes(data?.type)) return;
    try {
      if (data.type === "vanilla") return vanilla(loaded, data.file);
      if (data.type === "restore") return post({ type: "restored", ...loaded.engine(data) });
      if (data.type === "preset" || data.type === "decode") {
        const reply = loaded.engine(data);
        if ("refused" in reply) return post({ type: "refused", message: reply.refused, quiet: true });
        return post(data.type === "preset" ? { type: "preset", fragment: reply.fragment }
          : { type: "decoded", preset: reply.preset });
      }
      build(loaded, data.file, data.packs, data.xbr);
    } catch (error) {
      post({ type: "failed", message: lastLine(error) });
    }
  };
  post({ type: "ready", ...loaded.engine({ type: "catalog" }) });
} catch (error) {
  post({ type: "failed", message: `AzurKit didn't load: ${lastLine(error)}` });
}

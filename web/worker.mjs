// The site's engine: AzurKit's wheel under Pyodide 314 in a module worker, kept by the page after a build whose answer
// reports a heap under 1 GiB and replaced after any other (app.mjs's KEEP, Step 4.3i; WEB §3.6). The page
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
// In:  {type: "build", file, packs: {name: {parameter: value}}, xbr: [operation], randomizer, character},
//      {type: "vanilla", file},
//      {type: "preset", recipe: {packs, xbr, randomizer}, report}, {type: "decode", text}, {type: "restore", setup},
//      {type: "randomizer", given, ticket} (the Randomizer tab's settings, sdk.randomizer_settings),
//      {type: "tracker", call, given} (the item tracker's, sdk.tracker), {type: "plan", call, recipe} (sdk.plan),
//      the Characters tab's {type: "pickers", call, file, given}, {type: "preview" | "match", call, file, recipe}
//      (sdk.pickers, sdk.preview, sdk.match: numpy, Pyodide's pinned wheel from this site, is loaded for them) and
//      {type: "content_check", call, manifest, id, files} (an Install's check, sdk.content_check), and {type: "content", files, installed} (what this browser keeps installed, written
//      into the engine's content folder file by file once checked: kept). A message with a File has the image checked
//      first, once a File (prime).
// Out: {type: "ready", catalog, version}, {type: "progress", stage, label, done, total, percent} (core/progress.py's
//      record, mid-call: the check, then a build's stages), {type: "built", report, size, segments, heap} (a seed's
//      report without its spoiler, which {type: "spoiled", text | refused} brings next: the build shows sooner),
//      {type: "refused", message, heap}
//      (the engine's refusal, which names what and why, never game bytes), {type: "failed", message},
//      {type: "vanilla", release, label, packs} (the image's own value of each slider at a site of its XBE),
//      {type: "opened", preset} (the image is an AzurKit build: its recipe, sdk.open_build of the files it changed),
//      {type: "preset", fragment} (the share link's #p=…), {type: "decoded", preset} (a link's recipe),
//      {type: "restored", ticked, values, xbr, dropped, randomizer} (the remembered setup, sdk.restore),
//      {type: "rando", ticket, reply} (what the Randomizer tab shows, or {refused}), {type: "reply", call, reply}
//      (a tracker's or plan's answer: the view, {plan}, or {refused}), {type: "csp", directive, blocked}
const base = new URL("./", import.meta.url);
const post = (message, transfer = []) => self.postMessage(message, transfer);
self.addEventListener("securitypolicyviolation", (e) =>
  post({ type: "csp", directive: e.violatedDirective, blocked: e.blockedURI }));

const lastLine = (error) => String(error?.message ?? error).trim().split("\n").at(-1);

// engine(request) -> a plain JS object: {catalog, version}, {report, size, segments} or {refused} (a refusal is a
// ValueError or OSError, by its message); anything else raises. Each piece's bytes, and any bytes it hands back, come
// as a Uint8Array of their own through the file system: Pyodide 314.0.7's to_js (and assign, getBuffer) reads a buffer
// past 2 GiB of the heap at its address taken as signed, so a build that held more than that came out with other
// bytes (a seed wearing keylord: three of its levels).
const ENGINE = `
import hashlib
import json

import pyodide_js
from js import JSON, Object, postMessage
from pyodide.ffi import to_js

import azurkit
from azurkit import sdk
from azurkit.core import iso

PIECE = "/tmp/azurkit-piece"


def handed(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        with open(PIECE, "wb") as f:
            f.write(value)
        try:
            return pyodide_js.FS.readFile(PIECE)
        finally:
            pyodide_js.FS.unlink(PIECE)
    if isinstance(value, dict):
        return {k: handed(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [handed(v) for v in value]
    return value


def kept(files, installed):
    """What this browser keeps installed (IndexedDB, which any script of the site's origin may write) written into
    the engine's content folder: each file only where its path is one a manifest may list (content._path: no "..",
    under the content folders) and installed.json's record holds its sha256; installed.json last. The reasons the
    others were left out, each naming its path."""
    from azurkit.tools.characters import content

    record = installed if isinstance(installed, dict) else {}
    listed = {path: sha for held in record.values() if isinstance(held, dict) and isinstance(held.get("files"), dict)
              for path, sha in held["files"].items()}
    dropped = []
    for path in Object.keys(files):
        try:
            content._path("kept content", path)
            data = getattr(files, path).to_bytes()
            if (got := hashlib.sha256(data).hexdigest()) != listed.get(path):
                raise ValueError(f"kept content: {path}'s sha256 {got[:12]} isn't installed.json's")
        except (AttributeError, TypeError, ValueError) as exc:
            dropped.append(str(exc) if isinstance(exc, ValueError) else f"kept content: {path!r} holds no bytes")
            continue
        (content.ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (content.ROOT / path).write_bytes(data)
    content.ROOT.mkdir(parents=True, exist_ok=True)
    (content.ROOT / content.INSTALLED).write_text(json.dumps(installed), encoding="utf-8")
    return dropped


def progressed(record):   # a build's, a plan's or a tracker's stage, posted while it runs (core/progress.py's record)
    postMessage(to_js({"type": "progress", **record}, dict_converter=Object.fromEntries, create_pyproxies=False))


def engine(request):
    def js(value):
        return to_js(handed(value), dict_converter=Object.fromEntries, create_pyproxies=False)

    if request.type == "catalog":
        return js({"catalog": sdk.catalog(), "version": azurkit.__version__})
    if request.type == "content":
        return js({"dropped": kept(request.files, json.loads(JSON.stringify(getattr(request, "installed", None))
                                                             or "null"))})
    if request.type == "restore":
        return js(sdk.restore(json.loads(JSON.stringify(request.setup)) if request.setup else request.setup))
    if request.type in ("pickers", "preview", "match", "content_check"):
        try:
            if request.type == "content_check":
                entry, files = getattr(request, "id", None), getattr(request, "files", None)
                given = {"manifest": request.manifest} | ({"id": entry, "files": {
                    k: bytes(v) for k, v in files.to_py().items()}} if entry else {})
                return js(sdk.content_check(given))
            given = json.loads(JSON.stringify(request.given if request.type == "pickers" else request.recipe))
            if mounted := getattr(request, "iso", None):
                given["iso"] = mounted
            return js({"pickers": sdk.pickers, "preview": sdk.preview, "match": sdk.match}[request.type](given))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type in ("layout", "prime"):
        try:
            if request.type == "layout":
                return js(sdk.layout(request.recipe.iso))
            return js(sdk.prime(request.recipe.iso, request.digests.to_py()))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type in ("vanilla", "open", "preset", "decode", "randomizer", "tracker", "plan", "spoiler"):
        try:
            if request.type == "spoiler":   # the seed just built, its spoiler left out (sdk.image's spoiler false)
                return js(sdk.spoiler({"sha256": request.sha256}, built=True))
            if request.type == "randomizer":
                return js(sdk.randomizer_settings(request.given.to_py()))
            if request.type == "tracker":   # through JSON: a mark's null clock is None (to_py gives JsNull)
                return js(sdk.tracker(json.loads(JSON.stringify(request.given)), progress=progressed))
            if request.type == "plan":
                return js({"plan": sdk.plan(request.recipe.to_py(), progress=progressed)})
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
        image, report = sdk.image(request.recipe.to_py(), progress=progressed, spoiler=False)
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
// Chromium. So each read is served from what the image's blocks already hold, else from a block read for it: a 1 MiB
// page for a read under 1 MiB (the tables: USA's 59 lie in 29 pages), else a 64 MiB block (a file's bytes); the last
// PAGES pages and BLOCKS blocks are kept (256 MiB at most), for the last image only (by its id, which ids holds for
// each File: each message brings its own File object of it; a File with none keeps its own), from one message to the
// next, so a worker reads the folders' tables once, not once a call.
const PAGE = 1 << 20, BLOCK = 64 << 20, PAGES = 64, BLOCKS = 3;
const ids = new WeakMap();   // a message's File -> its image's id (identify)
function readInBlocks(WORKERFS) {
  const kept = new Map();   // the last image's id -> its unit -> index -> bytes, the least recently used first
  const units = [[BLOCK, BLOCKS], [PAGE, PAGES]];
  WORKERFS.stream_ops.read = (stream, buffer, offset, length, position) => {
    const file = stream.node.contents, end = Math.min(position + length, file.size), id = ids.get(file) ?? file;
    if (!(position < end)) return 0;
    if (!kept.has(id)) {
      kept.clear();
      kept.set(id, new Map(units.map(([unit]) => [unit, new Map()])));
    }
    const caches = kept.get(id);
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

// fn(the path of file mounted read-only at /in), unmounted after it. The mount's times are the File's lastModified
// (WORKERFS takes lastModifiedDate, which WebKit's File lacks, and else the time of the mount), so the engine's check
// of an image holds from one message to the next (sdk._stamp: by its path, size and times) and a changed File is
// checked again.
function mounted(py, file, fn) {
  if (!file.lastModifiedDate) Object.defineProperty(file, "lastModifiedDate", { value: new Date(file.lastModified) });
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  try {
    return fn(`/in/${file.name}`);
  } finally {
    py.FS.unmount("/in");
  }
}

// The image's check (D27), hashed here once a File: its build files (sdk.layout's offsets, 1.0 GB) in WebCrypto, the
// browser's native sha256 (about 10x wasm's), RUNS of up to 128 MiB read HASHERS at a time, then handed to the engine
// (sdk.prime), which checks them against its manifest and keeps the stamp for every later call on the image. Its
// progress is posted as the engine's record (core/progress.py). A refusal (not an image, a file that differs) is left
// to the call that follows, which names it. The digests of an image that passed are kept in the browser (IndexedDB,
// the last image's by its id), so the same File picked again after a reload is not read again (self.azurkitChecks
// counts the hashings, for the tests).
const HASHERS = 3, RUN = 128 << 20, STORE = "azurkit-stamp", SAMPLE = 1 << 20;
const hex = (buffer) => Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, "0")).join("");

// An image's id: its name, size and lastModified and the sha256 of its first and last MiB (the volume's descriptor
// and tables and, on both releases, the XBE's header, at 532 and 536 KiB; the last file's end), read in one read once
// a File (ids). A look-alike with the name, size and time of the image picked before it and other bytes there is
// checked as itself, and its reads never come from the other's blocks.
async function identify(file) {
  if (!ids.has(file)) {
    const ends = new Blob([file.slice(0, SAMPLE), file.slice(Math.max(SAMPLE, file.size - SAMPLE))]);
    const sample = hex(await crypto.subtle.digest("SHA-256", await ends.arrayBuffer()));
    ids.set(file, `${file.name}|${file.size}|${file.lastModified}|${sample}`);
  }
  return ids.get(file);
}
const stamps = (mode, fn) => new Promise((resolve) => {   // the browser's kept stamp; none where storage is refused
  const opened = indexedDB.open(STORE, 1);
  opened.onupgradeneeded = () => opened.result.createObjectStore("stamp");
  opened.onerror = () => resolve(null);
  opened.onsuccess = () => {
    const db = opened.result, done = db.transaction("stamp", mode), asked = fn(done.objectStore("stamp"));
    done.oncomplete = () => { db.close(); resolve(asked?.result ?? null); };
    done.onerror = done.onabort = () => { db.close(); resolve(null); };
  };
});
async function prime(loaded, file) {
  const { py, engine } = loaded, id = await identify(file);
  if (loaded.primed === id) return;
  loaded.primed = null;   // the engine's stamp is this File's from its prime on (sdk.prime checks it by its digests)
  const kept = await stamps("readonly", (store) => store.get("last")).catch(() => null);
  if (kept?.id === id) {
    const checked = mounted(py, file, (iso) => engine({ type: "prime", recipe: { iso }, digests: kept.digests }));
    if (!("refused" in checked)) return void (loaded.primed = id);
  }
  self.azurkitChecks = (self.azurkitChecks ?? 0) + 1;
  const listed = mounted(py, file, (iso) => engine({ type: "layout", recipe: { iso } }));
  if ("refused" in listed) return;
  const runs = [];
  for (const entry of [...listed.files].sort((a, b) => a[1] - b[1])) {   // [path, offset, size], by offset
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
  const checking = () => post({ type: "progress", stage: "check", label: "Checking your image", done, total,
                                percent: total ? Math.floor(done * 100 / total) : null });
  checking();
  await Promise.all(Array.from({ length: HASHERS }, async () => {
    for (let run; (run = runs.shift());) {
      const bytes = new Uint8Array(await file.slice(run.start, run.end).arrayBuffer());
      for (const [path, at, size] of run.files) {
        const from = at - run.start;
        digests[path] = hex(await crypto.subtle.digest("SHA-256", bytes.subarray(from, from + size)));
      }
      done += run.end - run.start;
      checking();
    }
  }));
  const checked = mounted(py, file, (iso) => engine({ type: "prime", recipe: { iso }, digests }));
  if ("refused" in checked) return;
  loaded.primed = id;
  await stamps("readwrite", (store) => store.put({ id, digests }, "last")).catch(() => null);
}

// The image's own values of the sliders at its XBE's sites, or, when it is an AzurKit build, its recipe; the image
// mounted only for the read: a build mounts it again.
function vanilla({ py, engine }, file) {
  mounted(py, file, (iso) => {
    const recipe = { iso };
    const read = engine({ type: "vanilla", recipe });
    if (!("refused" in read)) return post({ type: "vanilla", ...read });
    const opened = engine({ type: "open", recipe });
    if (!("refused" in opened)) post({ type: "opened", preset: opened.preset });
  });
}

// numpy (Pyodide's pinned wheel, which the site carries beside its core, checked by the lock's sha256), loaded once:
// every character call needs it (the swap's modules import it).
const numpy = (loaded) => loaded.numpy ??= loaded.py.loadPackage("numpy", { messageCallback: () => {},
                                                                           errorCallback: () => {} });
const CHARACTER = ["pickers", "preview", "match", "content_check"];
const needsNumpy = (data) => CHARACTER.includes(data.type) || data.character || data.recipe?.character
  || data.setup?.character || data.type === "decode";

// The content folder the engine reads (./content: the wheel has no user data folder here): what this browser keeps
// installed, written in whole once per worker, each file checked first (the engine's kept: a path a manifest may
// list, the sha256 installed.json holds for it); one that fails is left out with a line naming it, never written.
function content({ engine }, { files, installed }) {
  for (const why of engine({ type: "content", files, installed }).dropped) console.warn(`AzurKit left out ${why}`);
}

// A Characters tab's call, the image mounted for it (none picked: no image).
function character(loaded, data) {
  const { py, engine } = loaded;
  if (!data.file) return post({ type: "reply", call: data.call, reply: engine(data) });
  mounted(py, data.file, (iso) => post({ type: "reply", call: data.call, reply: engine({ ...data, iso }) }));
}

// A build, the image mounted for it and unmounted after; its answer carries the engine's heap then (wasm memory never
// shrinks: a page that keeps the worker keeps one whose heap is small enough for another build, Step 4.3i), undefined
// where Pyodide hides it. A seed's spoiler comes after it (the page shows the build meanwhile, and replaces a worker
// it doesn't keep only once it has it).
function build({ py, engine }, { file, packs, xbr, randomizer, character }) {
  const made = mounted(py, file, (iso) => engine({ type: "build", recipe: { iso, packs, xbr,
    ...(randomizer ? { randomizer } : {}), ...(character ? { character } : {}) } }));
  const heap = py._module?.HEAPU8?.length;
  if ("refused" in made) return post({ type: "refused", message: made.refused, heap });
  post({ type: "built", ...made, heap }, made.segments.flatMap((s) => s.kind === "bytes" ? [s.data.buffer] : []));
  if (!made.report.plan) return;
  let reply;
  try {
    reply = engine({ type: "spoiler", sha256: made.report.plan.sha256 });
  } catch (error) {
    reply = { refused: lastLine(error) };
  }
  post({ type: "spoiled", ...reply });
}

try {
  const loaded = await load();
  let queue = Promise.resolve();   // the messages in order: one that loads numpy holds those after it
  self.onmessage = ({ data }) => {
    if (!["build", "vanilla", "preset", "decode", "restore", "randomizer", "tracker", "plan", "content",
          ...CHARACTER].includes(data?.type)) return;
    queue = queue.then(() => needsNumpy(data) ? numpy(loaded) : null)
      .then(() => data.file ? prime(loaded, data.file).catch(() => null) : null).then(() => handle(data))
      .catch((error) => post({ type: "failed", message: lastLine(error) }));
  };
  const handle = (data) => {
    try {
      if (data.type === "content") return content(loaded, data);
      if (CHARACTER.includes(data.type)) {   // answered whatever happens: the page waits on it
        try {
          return character(loaded, data);
        } catch (error) {
          return post({ type: "reply", call: data.call, reply: { refused: lastLine(error) } });
        }
      }
      if (data.type === "vanilla") return vanilla(loaded, data.file);
      if (data.type === "tracker" || data.type === "plan") {   // answered whatever happens
        let reply;
        try {
          reply = loaded.engine(data);
        } catch (error) {
          reply = { refused: lastLine(error) };
        }
        return post({ type: "reply", call: data.call, reply });
      }
      if (data.type === "randomizer") return post({ type: "rando", ticket: data.ticket, reply: loaded.engine(data) });
      if (data.type === "restore") return post({ type: "restored", ...loaded.engine(data) });
      if (data.type === "preset" || data.type === "decode") {
        const reply = loaded.engine(data);
        if ("refused" in reply) return post({ type: "refused", message: reply.refused, quiet: true });
        return post(data.type === "preset" ? { type: "preset", fragment: reply.fragment }
          : { type: "decoded", preset: reply.preset });
      }
      build(loaded, data);
    } catch (error) {
      post({ type: "failed", message: lastLine(error) });
    }
  };
  post({ type: "ready", ...loaded.engine({ type: "catalog" }) });
} catch (error) {
  post({ type: "failed", message: `AzurKit didn't load: ${lastLine(error)}` });
}

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
// In:  {type: "build", file, packs: {name: {parameter: value}}, xbr: [operation], randomizer}, {type: "vanilla", file},
//      {type: "preset", recipe: {packs, xbr, randomizer}, report}, {type: "decode", text}, {type: "restore", setup},
//      {type: "randomizer", given, ticket} (the Randomizer tab's settings, sdk.randomizer_settings),
//      {type: "tracker", call, given} (the item tracker's, sdk.tracker), {type: "plan", call, recipe} (sdk.plan),
//      {type: "art", file, part} and {type: "art_world", parts} (the tracker's pictures, sdk.art and sdk.art_world:
//      numpy, Pyodide's pinned wheel from this site, is loaded for them and for a character),
//      the Characters tab's {type: "pickers", call, file, given}, {type: "preview" | "match", call, file, recipe}
//      (sdk.pickers, sdk.preview, sdk.match) and {type: "content_check", call, manifest, id, files} (an Install's
//      check, sdk.content_check), and {type: "content", files, installed} (what this browser keeps installed, written
//      into the engine's content folder)
// Out: {type: "ready", catalog, version}, {type: "built", report, size, segments}, {type: "refused", message}
//      (the engine's refusal, which names what and why, never game bytes), {type: "failed", message},
//      {type: "vanilla", release, label, packs} (the image's own value of each slider at a site of its XBE),
//      {type: "opened", preset} (the image is an AzurKit build: its recipe, sdk.open_build of the files it changed),
//      {type: "preset", fragment} (the share link's #p=…), {type: "decoded", preset} (a link's recipe),
//      {type: "restored", ticked, values, xbr, dropped, randomizer} (the remembered setup, sdk.restore),
//      {type: "rando", ticket, reply} (what the Randomizer tab shows, or {refused}), {type: "reply", call, reply}
//      (a tracker's or plan's answer: the view, {plan}, or {refused}), {type: "art", reply} (a part's pictures as
//      PNG bytes, its entry and thumb, or the world map and the index; or {refused}), {type: "csp", directive, blocked}
const base = new URL("./", import.meta.url);
const post = (message, transfer = []) => self.postMessage(message, transfer);
self.addEventListener("securitypolicyviolation", (e) =>
  post({ type: "csp", directive: e.violatedDirective, blocked: e.blockedURI }));

const lastLine = (error) => String(error?.message ?? error).trim().split("\n").at(-1);

// engine(request) -> a plain JS object: {catalog, version}, {report, size, segments} or {refused} (a refusal is a
// ValueError or OSError, by its message); anything else raises. to_js copies each piece's bytes into its own buffer.
const ENGINE = `
import json

from js import JSON, Object
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
    if request.type in ("art", "art_world"):
        try:
            if request.type == "art":
                return js(sdk.art(request.recipe.iso, request.part))
            parts = {lv: {"entry": p["entry"], "thumb": bytes(p["thumb"])} for lv, p in request.parts.to_py().items()}
            return js(sdk.art_world(parts))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type in ("vanilla", "open", "preset", "decode", "randomizer", "tracker", "plan"):
        try:
            if request.type == "randomizer":
                return js(sdk.randomizer_settings(request.given.to_py()))
            if request.type == "tracker":   # through JSON: a mark's null clock is None (to_py gives JsNull)
                return js(sdk.tracker(json.loads(JSON.stringify(request.given))))
            if request.type == "plan":
                return js({"plan": sdk.plan(request.recipe.to_py())})
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

// The tracker's pictures: numpy loaded once (Pyodide's wheel, which the site carries beside its core, checked by the
// lock's sha256), the image mounted for the part's read.
async function art(loaded, data) {
  const { py, engine } = loaded;
  await numpy(loaded);
  if (data.type === "art_world") return post({ type: "art", reply: engine({ type: "art_world", parts: data.parts }) });
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [data.file] }, "/in");
  try {
    const reply = engine({ type: "art", recipe: { iso: `/in/${data.file.name}` }, part: data.part });
    if ("refused" in reply) return post({ type: "failed", reply, message: reply.refused });
    post({ type: "art", reply });
  } finally {
    py.FS.unmount("/in");
  }
}

// numpy (Pyodide's pinned wheel, checked by the lock's sha256), loaded once: the tracker's pictures and every
// character call need it (the swap's modules import it).
const numpy = (loaded) => loaded.numpy ??= loaded.py.loadPackage("numpy", { messageCallback: () => {},
                                                                           errorCallback: () => {} });
const CHARACTER = ["pickers", "preview", "match", "content_check"];
const needsNumpy = (data) => CHARACTER.includes(data.type) || data.character || data.recipe?.character
  || data.setup?.character || data.type === "decode";

// The content folder the engine reads (./content: the wheel has no user data folder here): what this browser keeps
// installed, written in whole once per worker.
function content({ py }, { files, installed }) {
  const root = `${py.FS.cwd()}/content`;
  for (const [path, data] of Object.entries(files)) {
    py.FS.mkdirTree(`${root}/${path.split("/").slice(0, -1).join("/")}`);
    py.FS.writeFile(`${root}/${path}`, data);
  }
  py.FS.mkdirTree(root);
  py.FS.writeFile(`${root}/installed.json`, JSON.stringify(installed));
}

// A Characters tab's call, the image mounted for it (none picked: no image).
function character(loaded, data) {
  const { py, engine } = loaded;
  if (!data.file) return post({ type: "reply", call: data.call, reply: engine(data) });
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [data.file] }, "/in");
  try {
    post({ type: "reply", call: data.call, reply: engine({ ...data, iso: `/in/${data.file.name}` }) });
  } finally {
    py.FS.unmount("/in");
  }
}

function build({ py, engine }, file, packs, xbr, randomizer, character) {
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  const recipe = { iso: `/in/${file.name}`, packs, xbr, ...(randomizer ? { randomizer } : {}),
                   ...(character ? { character } : {}) };
  const made = engine({ type: "build", recipe });
  if ("refused" in made) return post({ type: "refused", message: made.refused });
  post({ type: "built", ...made }, made.segments.flatMap((s) => s.kind === "bytes" ? [s.data.buffer] : []));
}

try {
  const loaded = await load();
  let queue = Promise.resolve();   // the messages in order: one that loads numpy holds those after it
  self.onmessage = ({ data }) => {
    if (!["build", "vanilla", "preset", "decode", "restore", "randomizer", "tracker", "plan", "art",
          "art_world", "content", ...CHARACTER].includes(data?.type)) return;
    queue = queue.then(() => needsNumpy(data) ? numpy(loaded) : null).then(() => handle(data))
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
      if (data.type === "art" || data.type === "art_world") {
        return art(loaded, data).catch((error) => post({ type: "failed", message: lastLine(error) }));
      }
      if (data.type === "vanilla") return vanilla(loaded, data.file);
      if (data.type === "tracker" || data.type === "plan") {   // answered whatever happens: the page waits on it
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
      build(loaded, data.file, data.packs, data.xbr, data.randomizer, data.character);
    } catch (error) {
      post({ type: "failed", message: lastLine(error) });
    }
  };
  post({ type: "ready", ...loaded.engine({ type: "catalog" }) });
} catch (error) {
  post({ type: "failed", message: `AzurKit didn't load: ${lastLine(error)}` });
}

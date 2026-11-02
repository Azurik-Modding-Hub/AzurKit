// The site's engine: AzurKit's wheel under Pyodide 314 in a module worker, kept by the page after a build whose answer
// reports a heap under its line and replaced after any other (workers.mjs's GROWN; WEB §3.6). The page
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
//      {type: "randomizer", given, ticket, file?} (the Randomizer tab's settings, sdk.randomizer_settings; the image
//      mounted for it while the tab's given wears a character),
//      {type: "tracker", call, given} (the item tracker's, sdk.tracker), {type: "plan", call, recipe} (sdk.plan),
//      the Characters tab's {type: "pickers", call, file, given}, {type: "preview" | "match", call, file, recipe}
//      (sdk.pickers, sdk.preview, sdk.match: numpy, Pyodide's pinned wheel from this site, is loaded for them) and
//      {type: "content_check", call, manifest, id, files} (an Install's check, sdk.content_check), and {type: "content", files, installed} (what this browser keeps installed, written
//      into the engine's content folder file by file once checked: kept), {type: "warm"} (numpy and a dress's modules,
//      unanswered: a body's build ahead starts at its first step), and the Tools tab's {type: "info" |
//      "verify_all" | "files", call, file} (sdk.image_info, sdk.verify_all: the files its kept check hasn't hashed,
//      hashed here, sdk.files), {type: "open", call, build} (another File: an AzurKit build's recipe, sdk.open_build of
//      the files it changed), {type: "mods_file", call, text | recipe | preset} (sdk.mods_file) and {type:
//      "plan_spoiler", call, plan} (sdk.spoiler), and the Data tab's {type: "data" | "data_edit", call, given}
//      (sdk.data, sdk.data_edit: config.xbr's cells from the file the wheel ships, no image). A message with a File
//      (file) has the image checked first, once a File (prime).
// Out: {type: "native", kernel?, twin?} (the reach calls each path answered since the last, before the answer they
//      went into), {type: "ready", catalog, version, commit, start} (start: "snapshot" or "cold", load()'s), {type: "progress", stage, label, done, total, percent} (core/progress.py's
//      record, mid-call: the check, then a build's stages; the worker's own: its start before ready, the kept image's
//      walk), {type: "built", report, size, segments, heap} (a seed's report without its spoiler, which {type:
//      "spoiled", text | refused} brings next: the build shows sooner),
//      {type: "refused", message, heap}
//      (the engine's refusal, which names what and why, never game bytes), {type: "failed", message},
//      {type: "vanilla", release, label, packs} (the image's own value of each slider at a site of its XBE),
//      {type: "opened", preset} (the image is an AzurKit build: its recipe, sdk.open_build of the files it changed),
//      {type: "preset", fragment} (the share link's #p=…), {type: "decoded", preset} (a link's recipe),
//      {type: "restored", ticked, values, xbr, dropped, randomizer} (the remembered setup, sdk.restore),
//      {type: "rando", ticket, reply} (what the Randomizer tab shows, or {refused}), {type: "reply", call, reply}
//      (a tracker's, plan's, Characters', Data or Tools' answer: the view, {plan}, or {refused}), {type: "csp", directive,
//      blocked}. A read that is neither an image nor an AzurKit build ends with {type: "unread"}. Each but a progress record
//      carries the engine's heap then (undefined where Pyodide hides it), which the page's two workers count (workers.mjs).
import { hashed, hashedApart, md5Ready } from "./hasher.mjs";
import { text } from "./memo.mjs";
import { PREFIX } from "./outputs.mjs";

const base = new URL("./", import.meta.url);
let heap = () => undefined;
const post = (message, transfer = []) => self.postMessage(
  message.type === "progress" || "heap" in message ? message : { ...message, heap: heap() }, transfer);
self.addEventListener("securitypolicyviolation", (e) =>
  post({ type: "csp", directive: e.violatedDirective, blocked: e.blockedURI }));

const lastLine = (error) => String(error?.message ?? error).trim().split("\n").at(-1);

// engine(request) -> a plain JS object: {catalog, version}, {report, size, segments} or {refused} (a refusal is a
// ValueError or OSError, by its message); anything else raises. Each piece's bytes, and any bytes it hands back, come
// as their place in the heap where they are a bytes object's (placed), else as a Uint8Array of their own through the
// file system: Pyodide 314.0.7's to_js (and assign, getBuffer) reads a buffer
// past 2 GiB of the heap at its address taken as signed, so a build that held more than that came out with other
// bytes (a seed wearing keylord: three of its levels). A build's pieces reach the page as Blobs (blobbed).
const ENGINE = `
import hashlib
import json

import js as browser
import pyodide_js
from js import JSON, Blob, Object, postMessage
from pyodide.ffi import to_js

import azurkit
from azurkit import sdk
from azurkit.core import iso, native, progress
from azurkit.tools import characters
from azurkit.tools.characters import pool

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


def placed(data):
    """Where a bytes object's bytes lie in the heap (CPython's PyBytesObject; JS reads them there, as a view, unsigned, so
    no copy through the file system or past to_js's 2 GiB), a memoryview of all of one's too: a build's pieces are such
    views (iso.Image.segments), and each copy handed() made of one stayed in the worker's JS until a GC, which a worker
    building again at once doesn't get (twice a build's pieces a build in WebKit: 4.3r4s); None for any other kind of
    value."""
    if type(data) is memoryview and data.c_contiguous and type(data.obj) is bytes and data.nbytes == len(data.obj):
        data = data.obj
    return id(data) + bytes.__basicsize__ - 1 if type(data) is bytes else None


def blobbed(data):
    """One piece of a build as a Blob, made as soon as its bytes reach JS, so the worker holds one piece's bytes in JS
    at a time and the page none (mem-site L2): the browser keeps a Blob's bytes outside the page's heap. Where the
    worker holds a build file (P7, built() in worker.mjs), the piece is written there and stands as its offset."""
    if hasattr(browser, "azurkitOut"):
        at = placed(data)
        return {"opfs": browser.azurkitOut(handed(data)) if at is None else browser.azurkitOut(at, len(data))}
    return Blob.new(to_js([handed(data)], create_pyproxies=False))


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


LAST = {}   # the call's stage it posted last, and the last tick's percent
STAGED = None   # a build between its calls (sdk.image_staged, build()): its generator and the bytes it gave to hash


def posted(record):
    postMessage(to_js({"type": "progress", **record}, dict_converter=Object.fromEntries, create_pyproxies=False))


def progressed(record):   # a call's stage, posted while it runs (core/progress.py's record)
    LAST.update(record=record, percent=None)
    posted(record)


def ticked(done, total):   # pool.TICK: the swap's items, on the call's last stage (else the dress), each percent once
    last = LAST.get("record") or progress.record("dress")
    step = progress.record(last["stage"], last["label"], done, total)
    if step["percent"] != LAST.get("percent"):
        LAST["percent"] = step["percent"]
        posted(step)


pool.TICK = ticked


class Kept:
    """tools.characters.CACHE here (D1015, D1067): the answers this browser kept for a build's character (IndexedDB's,
    build() in this file), handed in with the build, and those the build works out (a plan's AZKP1: no pickle, its
    sizes checked as it inflates), made once its answer is out (the kept call) and handed back to be kept. The swap
    takes one only under its own key (its code, the layers under it, the content): a kept answer is the one it would
    work out again. Nothing is kept outside a build."""

    def __init__(self):
        self.offered, self.made = {}, None

    def get(self, key):
        return self.offered.get(key)

    def put(self, key, make):
        if self.made is not None:
            self.made[key] = make

    def taken(self, made=True):
        """The build's answers to keep, made, by key (none when made is false); none kept after."""
        put, self.offered, self.made = self.made or {}, {}, None
        return {key: make if isinstance(make, bytes) else make() for key, make in put.items()} if made else {}


KEPT = characters.CACHE = Kept()


def engine(request):
    LAST.clear()

    def js(value):
        return to_js(handed(value), dict_converter=Object.fromEntries, create_pyproxies=False)

    if request.type == "catalog":
        return js({"catalog": sdk.catalog(), "version": azurkit.__version__, "commit": azurkit.commit()})
    if request.type == "warm":   # numpy's loaded: what a dress imports, so a body's build starts at its first step
        from azurkit.tools.characters import _player_character  # noqa: F401
        characters._code()   # a kept answer's key's first part, worked out once a worker
        return js({})
    if request.type == "kept":   # after a build's answer: what it worked out to keep, made now
        return js(KEPT.taken())
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
            if request.type == "pickers":   # its steps posted: the tab's bar moves while it waits
                return js(sdk.pickers(given, progress=progressed))
            return js({"preview": sdk.preview, "match": sdk.match}[request.type](given))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type in ("data", "data_edit", "community"):   # through JSON: a null is None (to_py gives JsNull)
        try:
            if request.type == "community":
                return js(sdk.community())
            given = json.loads(JSON.stringify(request.given))
            return js((sdk.data if request.type == "data" else sdk.data_edit)(given))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type in ("layout", "prime"):
        try:
            if request.type == "layout":
                return js(sdk.layout(request.recipe.iso, whole=bool(getattr(request, "whole", False))))
            return js(sdk.prime(request.recipe.iso, request.digests.to_py()))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type in ("info", "verify_all", "files", "mods_file", "plan_spoiler", "replace", "saves"):   # the Tools tab's
        try:
            if request.type == "saves":
                given, blobs = json.loads(JSON.stringify(request.given)), request.blobs.to_py()
                if blobs["files"]:
                    given["files"] = {k: bytes(v) for k, v in blobs["files"].items()}
                return js(sdk.saves(given | {k: bytes(blobs[k]) for k in ("flash", "mcpx") if k in blobs}))
            if request.type == "replace":
                return js(sdk.file_entry(json.loads(JSON.stringify(request.given))))
            if request.type == "info":
                return js(sdk.image_info(request.recipe.iso))
            if request.type == "verify_all":
                return js(sdk.verify_all(request.recipe.iso, request.digests.to_py()))
            if request.type == "files":
                return js(sdk.files(request.recipe.iso))
            given = json.loads(JSON.stringify(request.given))   # through JSON: a null is None (to_py gives JsNull)
            if request.type == "plan_spoiler":
                return js({"lines": sdk.spoiler(given, progress=progressed)["lines"]})
            return js(sdk.mods_file(given))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type in ("vanilla", "open", "preset", "decode", "randomizer", "tracker", "plan", "spoiler"):
        try:
            if request.type == "spoiler":   # the seed just built, its spoiler left out (sdk.image's spoiler false)
                return js(sdk.spoiler({"sha256": request.sha256}, built=True))
            if request.type == "randomizer":   # through JSON: a character's null is None (to_py gives JsNull)
                return js(sdk.randomizer_settings(json.loads(JSON.stringify(request.given))))
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
    global STAGED
    try:
        if request.type == "hash":
            data = STAGED[1][request.key]
            at = placed(data)
            return js({"data": data} if at is None else {"at": at, "size": len(data)})
        if request.type == "hashed":   # the layout, the manifest, the read-back
            STAGED[0].send(json.loads(JSON.stringify(request.shas)))
            raise RuntimeError("the staged build asked for more")
        if request.type == "build":   # to the pages it reads next, then its composed files, which the worker hashes (build())
            extra = {"picked": {k: bytes(v) for k, v in request.picked.to_py().items()},
                     "hashed": request.hashed.to_py()} if getattr(request, "picked", None) else {}
            STAGED = sdk.image_staged(request.recipe.to_py(), progress=progressed, spoiler=False, ahead=True, **extra), None
            KEPT.taken(made=False)
            KEPT.made = {}
            if offered := getattr(request, "kept", None):
                KEPT.offered = {key: getattr(offered, key).to_bytes() for key in Object.keys(offered)}
        step = next(STAGED[0])   # "build" or "ahead": the pages it asked for are in the read cache
        if isinstance(step, list):
            return js({"ahead": step})
        STAGED = STAGED[0], step
        return js({"hash": [key for key, data in step.items() if not isinstance(data, iso.Patched)],
                   "patched": [[key, data.start, data.size, [list(patch) for patch in data.patches]]
                               for key, data in step.items() if isinstance(data, iso.Patched)]})
    except StopIteration as done:
        image, report = done.value
    except (OSError, ValueError) as exc:
        STAGED = None
        KEPT.taken(made=False)
        return js({"refused": str(exc)})
    STAGED = None
    pieces = [{"kind": "copy", "offset": p.offset, "size": p.size} if isinstance(p, iso.Copy)
              else {"kind": "zero", "size": p.size} if isinstance(p, iso.Zero)
              else {"kind": "bytes", "size": p.size, "data": blobbed(p.data)} for p in image.segments()]
    return js({"report": report, "size": image.size, "segments": pieces, "checks": sdk.image_checks(image, report)})


def answering(request):
    try:
        return engine(request)
    finally:
        if calls := native.taken():   # before the answer, as the page may end this worker on it
            postMessage(to_js({"type": "native", **calls}, dict_converter=Object.fromEntries, create_pyproxies=False))


answering`;

// The image is read in blocks (Step 4.1g2). WebKit answers each read of a File's slice after about 200 ms, whatever
// its size (2 KiB and 64 MiB alike), and a build read the image about 650 times through WORKERFS (the folders'
// tables, which every iso.Reader reads again, and a 4 KiB read after each 8 MiB one): 131 s a build, 4 s in
// Chromium. So each read is served from what the image's blocks already hold, else from a block read for it: a 1 MiB
// page for a read under 1 MiB (the tables: USA's 59 lie in 29 pages), else a 16 MiB block (a file's bytes); the last
// PAGES pages and BLOCKS blocks are kept (240 MiB at most), for the last image only (by its id, which ids holds for
// each File: each message brings its own File object of it; a File with none keeps its own), from one message to the
// next, so a worker reads the folders' tables once, not once a call. Before the engine's first walk of an image in a
// worker, its tables' pages are read ahead (ahead(): R2.5), every folder of a depth at once; a seed's build asks for
// its levels' TOCs and node sections' too (spans(): AM-HUB-E): 95 pages on USA, 147 on Europe, whose French.xbr and
// German.xbr it reads whole, and a worn body's its files (about 110 pages), so PAGES holds them with the tables.
const PAGE = 1 << 20, BLOCK = 16 << 20, PAGES = 192, BLOCKS = 3;
const ids = new WeakMap();   // a message's File -> its image's id (identify)
function readInBlocks(WORKERFS) {
  const kept = new Map();   // the last image's id -> its unit -> index -> bytes, the least recently used first
  const units = [[BLOCK, BLOCKS], [PAGE, PAGES]];
  const cachesOf = (id) => {
    if (!kept.has(id)) {
      kept.clear();
      kept.set(id, new Map(units.map(([unit]) => [unit, new Map()])));
    }
    return kept.get(id);
  };
  WORKERFS.stream_ops.read = (stream, buffer, offset, length, position) => {
    const file = stream.node.contents, end = Math.min(position + length, file.size), id = ids.get(file) ?? file;
    if (!(position < end)) return 0;
    const caches = cachesOf(id);
    for (let at = position; at < end;) {
      const [unit, keep] = units.find(([u]) => caches.get(u).has(Math.floor(at / u))) ?? units[length < PAGE ? 1 : 0];
      const cache = caches.get(unit), index = Math.floor(at / unit);
      let data = cache.get(index);
      if (data) {
        cache.delete(index);   // used last now
      } else {
        self.azurkitLateReads = (self.azurkitLateReads ?? 0) + 1;
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
  return { tables: (file, id, hint) => ahead(file, cachesOf(id).get(PAGE), hint),
           spans: (file, id, wanted) => spans(file, cachesOf(id).get(PAGE), wanted) };
}

// The pages of wanted ([image offset, size]) a seed's or a body's build reads next, all at once and awaited (AM-HUB-E: one by one,
// WebKit's 200 ms a read would cost about 90 x that), into the cache (used last now), as the engine's own reads would
// be. A hint: a page the cache lacks later is read by the engine.
async function spans(file, pages, wanted) {
  const indexes = new Set();
  for (const [at, n] of wanted) {
    const end = Math.min(at + n, file.size);
    for (let i = Math.floor(at / PAGE); i * PAGE < end; i++) indexes.add(i);
  }
  const listed = [...indexes].slice(0, PAGES);
  const got = await Promise.all(listed.map(async (i) => pages.get(i)
    ?? new Uint8Array(await file.slice(i * PAGE, (i + 1) * PAGE).arrayBuffer())));
  for (const [i, index] of listed.entries()) {
    pages.delete(index);
    if (pages.size >= PAGES) pages.delete(pages.keys().next().value);
    pages.set(index, got[i]);
  }
}

// The folders' tables read ahead (R2.5): the engine walks them (iso.Reader) with WORKERFS's reads, one at a time, which
// WebKit answers about 200 ms late each (Safari: the 34 reads of a first walk, 6.9 s); this walks the same XDVDFS tables
// first with reads it awaits, all the tables of a depth at once (the volume descriptor's candidates, the root, its
// folders, theirs), and leaves their 1 MiB pages in the read cache, where the engine's walk finds them. A hint only:
// the engine still reads and checks every byte, from the File's own bytes, and a table this misreads is read by it as
// before. The walk's pages are kept per image (walked; and with its stamp in the browser, so a later worker reads them
// all at once with no walk: hint), so a later call reads again only those the cache let go.
const SECTOR = 2048, VD = 32 * SECTOR, PARTITIONS = [0, 0x18300000, 0xFD90000, 0x2080000];   // core/iso.py's
const SLACK = 128 << 10;   // the engine reads a table through its file's buffer (io.DEFAULT_BUFFER_SIZE, 128 KiB): its pages too
const MAGIC = Array.from("MICROSOFT*XBOX*MEDIA", (c) => c.charCodeAt(0));
let TABLES = {};   // web/tables.json: each release's folder-table pages by "base:root sector:root size" (a hint)
const walked = new Map();   // an image's id -> the pages of its tables (the last image's only)
async function ahead(file, pages, hint) {
  const asked = new Map();   // index -> the promise of its page's bytes
  const fetchPage = async (index) => {
    const bytes = await file.slice(index * PAGE, (index + 1) * PAGE).arrayBuffer();
    return new Uint8Array(bytes);
  };
  const page = (index) => {
    if (!asked.has(index)) asked.set(index, pages.has(index) ? Promise.resolve(pages.get(index)) : fetchPage(index));
    return asked.get(index);
  };
  const read = async (at, n) => {   // n bytes at at, from their pages, or fewer at the File's end
    const first = Math.floor(at / PAGE), last = Math.floor((Math.min(at + n, file.size) - 1) / PAGE);
    const got = await Promise.all(Array.from({ length: Math.max(0, last - first + 1) }, (_, i) => page(first + i)));
    const out = new Uint8Array(got.reduce((s, b) => s + b.length, 0));
    got.reduce((o, b) => (out.set(b, o), o + b.length), 0);
    return out.subarray(at - first * PAGE, at - first * PAGE + n);
  };
  const id = ids.get(file) ?? file;
  if (!walked.has(id) && Array.isArray(hint) && hint.every(Number.isInteger)) {
    walked.clear();
    walked.set(id, hint.filter((i) => i >= 0 && i * PAGE < file.size).slice(0, PAGES));
  }
  if (!walked.has(id)) {   // else only the pages the cache let go are read again
    const bases = PARTITIONS.filter((base) => base + VD + SECTOR <= file.size);
    const vds = await Promise.all(bases.map((base) => read(base + VD, SECTOR)));
    const at = vds.findIndex((vd) => MAGIC.every((c, i) => vd[i] === c && vd[0x7EC + i] === c));
    if (at < 0) return;   // no XDVDFS here: the engine names it
    const base = bases[at], used = new Set(bases.slice(0, at + 1).map((b) => Math.floor((b + VD) / PAGE)));
    const head = new DataView(vds[at].buffer, vds[at].byteOffset, SECTOR);
    const root = [head.getUint32(20, true), head.getUint32(24, true)];
    const shipped = TABLES[`${base}:${root[0]}:${root[1]}`];   // a release's tables' pages (web/tables.json): one round
    if (Array.isArray(shipped) && shipped.every(Number.isInteger)) shipped.forEach((i) => used.add(i));
    else {   // another image on a release's root (an AzurKit build: its layout is the release's): its pages asked now,
      for (const [key, list] of Object.entries(TABLES)) {   // so the walk's depths find them asked, in this one round
        if (key.startsWith(`${base}:${root[0]}:`) && Array.isArray(list)) {
          list.filter((i) => Number.isInteger(i) && i >= 0 && i * PAGE < file.size).slice(0, PAGES)
            .forEach((i) => page(i).catch(() => null));
        }
      }
    }
    let level = Array.isArray(shipped) ? [] : [root];
    const seen = new Set([root[0]]);
    while (level.length) {   // a depth's tables at once
      for (const [sector, size] of level) {
        const from = base + sector * SECTOR;
        for (let i = Math.floor(from / PAGE); i <= Math.floor((from + size - 1 + SLACK) / PAGE); i++) used.add(i);
      }
      if (used.size > PAGES) break;   // more than the cache holds (a damaged table's size): the engine's to read and name
      const tables = await Promise.all(level.map(([sector, size]) => read(base + sector * SECTOR, size)));
      level = [];
      for (const table of tables) {
        if (table.length < 14 || (table[0] === 0xFF && table[1] === 0xFF)) continue;   // empty, or cut off
        const view = new DataView(table.buffer, table.byteOffset, table.length);
        const todo = [0], visited = new Set();
        while (todo.length && visited.size < 65536) {
          const rec = todo.pop();
          if (visited.has(rec) || rec + 14 > table.length) continue;
          visited.add(rec);
          const left = view.getUint16(rec, true), right = view.getUint16(rec + 2, true);
          const start = view.getUint32(rec + 4, true), length = view.getUint32(rec + 8, true);
          if (view.getUint8(rec + 12) & 0x10 && length && !seen.has(start)) {
            seen.add(start);
            level.push([start, length]);
          }
          for (const link of [right, left]) if (link) todo.push(link * 4);
        }
      }
    }
    walked.clear();
    walked.set(id, [...used].filter((i) => i * PAGE < file.size).sort((a, b) => a - b).slice(0, PAGES));
  }
  const listed = walked.get(id) ?? [], got = await Promise.all(listed.map(page));
  for (const [i, index] of listed.entries()) {   // into the cache (used last now), as the engine's own reads would be
    const data = got[i];
    pages.delete(index);
    if (pages.size >= PAGES) pages.delete(pages.keys().next().value);
    pages.set(index, data);
  }
}

// The worker's own stages (core/progress.py's "start" and "check"): the load's four steps (Pyodide's core, the wheel's
// fetch, its unpacking, the engine's import) before "ready", each posted as it starts, and the image's walk when its
// stamp is kept (prime), so a first visit, a return visit and a reload's pick show a bar (D980).
const stage = (name, label, done, total) => post({ type: "progress", stage: name, label, done, total,
                                                    percent: Math.floor(done * 100 / total) });
const starting = (done) => stage("start", "Starting the engine", done, 4);

const stored = (database, name, mode, fn) => new Promise((resolve) => {   // IndexedDB's record; none where storage is refused
  const opened = indexedDB.open(database, 1);
  opened.onupgradeneeded = () => opened.result.createObjectStore(name);
  opened.onerror = () => resolve(null);
  opened.onsuccess = () => {
    const db = opened.result, done = db.transaction(name, mode), asked = fn(done.objectStore(name));
    done.oncomplete = () => { db.close(); resolve(asked?.result ?? null); };
    done.onerror = done.onabort = () => { db.close(); resolve(null); };
  };
});

// Pyodide's memory snapshot (R2.10): its heap once the engine's modules are imported (IMPORTS, no numpy: a heap holding
// it can't run after a restore), made by the first worker of a site's wheel and kept in this browser (IndexedDB, the
// last only, by Pyodide's version and the wheel's integrity), so each later worker (a return visit, the one after a big
// build) starts from it and skips CPython's start and those imports. The wheel's files are unpacked again (the file
// system isn't in the heap). The heap holds no image: it is made before any is read. Any fault making, keeping or
// starting from one starts the worker as before; "ready" says which start it was (start). Stock Pyodide can't restore a
// heap grown past the module's initial memory, 31,457,280 B (a RangeError), so the restore grows it first (grown).
const SNAPSHOT = "azurkit-snapshot", IMPORTS = "import azurkit\nfrom azurkit import sdk\nfrom azurkit.core import iso\n";
const grown = (create, size) => (settings) => {
  const instantiate = settings.instantiateWasm;
  settings.instantiateWasm = (imports, ready) => instantiate(imports, (instance, module) => {
    const { memory } = instance.exports, short = Math.ceil(size / 65536) - memory.buffer.byteLength / 65536;
    if (short > 0) memory.grow(short);
    return ready(instance, module);
  });
  return create(settings);
};

async function load() {
  starting(0);
  const site = await (await fetch(new URL("host.json", base))).json();
  const pyodide = new URL("pyodide/", base).href;
  const { loadPyodide, version } = await import(new URL("pyodide.mjs", pyodide).href);
  const options = {
    indexURL: pyodide, lockFileURL: new URL("pyodide-lock.json", pyodide).href, packageBaseUrl: pyodide,
    stdout: () => {}, stderr: () => {},
  };
  const key = `${version} ${site.integrity}`;
  const heap = await stored(SNAPSHOT, "heap", "readonly", (store) => store.get(key)).catch(() => null);
  const restored = heap && await import(new URL("pyodide.asm.mjs", pyodide).href).then(({ default: create }) =>
    loadPyodide({ ...options, _loadSnapshot: heap, createPyodideModule: grown(create, heap.length) })).catch(() => null);
  const py = restored ?? await loadPyodide({ ...options, _makeSnapshot: true });
  const reads = readInBlocks(py.FS.filesystems.WORKERFS);
  starting(1);
  const wheel = await fetch(new URL(site.wheel, base), { integrity: site.integrity });
  if (!wheel.ok) throw new Error(`${site.wheel}: HTTP ${wheel.status}`);
  const archive = await wheel.arrayBuffer();
  starting(2);
  py.unpackArchive(archive, "wheel", { extractDir: py.runPython("import site; site.getsitepackages()[0]") });
  TABLES = await fetch(new URL("tables.json", base)).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  starting(3);
  if (!restored) {
    try {
      py.runPython(IMPORTS);
      const made = py.makeMemorySnapshot();
      stored(SNAPSHOT, "heap", "readwrite", (store) => { store.clear(); store.put(made, key); }).catch(() => null);   // not awaited
    } catch {
      // no snapshot: the next worker starts as this one did
    }
  }
  return { py, engine: py.runPython(ENGINE), reads, start: restored ? "snapshot" : "cold" };
}

// fn(the path of file mounted read-only at /in), unmounted after it (after the promise it gives, if it gives one). The
// mount's times are the File's lastModified (WORKERFS takes lastModifiedDate, which WebKit's File lacks, and else the
// time of the mount), so the engine's check of an image holds from one message to the next (sdk._stamp: by its path,
// size and times) and a changed File is checked again.
function mounted(py, file, fn) {
  if (!file.lastModifiedDate) Object.defineProperty(file, "lastModifiedDate", { value: new Date(file.lastModified) });
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  const unmount = () => py.FS.unmount("/in");
  let done;
  try {
    done = fn(`/in/${file.name}`);
  } catch (error) {
    unmount();
    throw error;
  }
  if (done instanceof Promise) return done.finally(unmount);
  unmount();
  return done;
}

// The image's check (D27), hashed here once a File: its build files (sdk.layout's offsets, 1.0 GB) in WebCrypto, the
// browser's native sha256 (about 10x wasm's; hasher.mjs), then handed to the engine
// (sdk.prime), which checks them against its manifest and keeps the stamp for every later call on the image. Its
// progress is posted as the engine's record (core/progress.py). A refusal (not an image, a file that differs) is left
// to the call that follows, which names it. The digests of an image that passed are kept in the browser (IndexedDB,
// the last image's by its id), so the same File picked again after a reload is not read again (self.azurkitChecks
// counts the hashings, for the tests).
const STORE = "azurkit-stamp", SAMPLE = 1 << 20;
const CHECK_RUN = 32 << 20;   // what WebKit keeps resident is what a thread held at once: a bar's op can read in smaller runs
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
const stamps = (mode, fn) => stored(STORE, "stamp", mode, fn);   // the browser's kept stamp
async function prime(loaded, file) {
  const { py, engine } = loaded, id = await identify(file);
  const kept = loaded.primed === id ? null : await stamps("readonly", (store) => store.get("last")).catch(() => null);
  if (kept?.id === id) stage("check", "Reading your image", 0, 1);   // its walk: the first read of its folders here
  await loaded.reads.tables(file, id, kept?.id === id ? kept.pages : null).catch(() => null);   // a hint: a failed read
  if (loaded.primed === id) return;                                                         // leaves them to the engine
  loaded.primed = null;   // the engine's stamp is this File's from its prime on (sdk.prime checks it by its digests)
  if (kept?.id === id) {
    const checked = mounted(py, file, (iso) => engine({ type: "prime", recipe: { iso }, digests: kept.digests }));
    if (!("refused" in checked)) {
      stage("check", "Reading your image", 1, 1);
      return void (loaded.primed = id);
    }
  }
  self.azurkitChecks = (self.azurkitChecks ?? 0) + 1;
  const listed = mounted(py, file, (iso) => engine({ type: "layout", recipe: { iso } }));
  if ("refused" in listed) return;
  const digests = await hashedApart(file, listed.files, checking("Checking your image"), CHECK_RUN);
  const checked = mounted(py, file, (iso) => engine({ type: "prime", recipe: { iso }, digests }));
  if ("refused" in checked) return;
  loaded.primed = id;
  await stamps("readwrite", (store) => store.put({ id, digests, pages: walked.get(id) }, "last")).catch(() => null);
}

// A hash's progress, posted as the engine's record with label (stage check).
const checking = (label) => (done, total) => post({ type: "progress", stage: "check", label, done, total,
                                                    percent: total ? Math.floor(done * 100 / total) : null });

// The image's own values of the sliders at its XBE's sites, or, when it is an AzurKit build, its recipe; the image
// mounted only for the read: a build mounts it again.
function vanilla({ py, engine }, file) {
  mounted(py, file, (iso) => {
    const recipe = { iso };
    const read = engine({ type: "vanilla", recipe });
    if (!("refused" in read)) return post({ type: "vanilla", ...read });
    const opened = engine({ type: "open", recipe });
    post("refused" in opened ? { type: "unread" } : { type: "opened", preset: opened.preset });
  });
}

// numpy (Pyodide's pinned wheel, which the site carries beside its core, checked by the lock's sha256), loaded once:
// every character call needs it (the swap's modules import it).
const numpy = (loaded) => loaded.numpy ??= loaded.py.loadPackage("numpy", { messageCallback: () => {},
                                                                           errorCallback: () => {} })
  .then(() => void (loaded.numpied = true));
const CHARACTER = ["pickers", "preview", "match", "content_check"];
const needsNumpy = (data) => data.type === "warm" || CHARACTER.includes(data.type) || data.character || data.recipe?.character
  || data.given?.character
  || data.setup?.character || data.type === "decode" || data.type === "mods_file" && (
    data.preset?.layers?.some((layer) => layer.tool === "characters") || typeof data.text === "string" && (
      !data.text.trimStart().startsWith("{") || data.text.includes('"characters"')));   // a link: it may wear one

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

// A file picked to replace one of the image's, in memory for one ask or build, and its sha256 in WebCrypto.
const pickedBytes = async (picked) => new Uint8Array(await picked.arrayBuffer());
const digested = async (bytes) => hex(await crypto.subtle.digest("SHA-256", bytes));
// Replace files' pick, read as one stream (one read: Safari answers each read of a File 200 ms late), the bottom bar
// moving with the bytes read (D980: a 148 MB file's pick passes 1 s in Safari's read model, S54/lag; a stream reads as
// fast as one arrayBuffer() in the three browsers), then hashed whole.
async function streamed(picked) {
  const bytes = new Uint8Array(picked.size), label = `Reading ${picked.name}`;
  let at = 0, shown = -1;
  const heard = () => {
    const percent = Math.floor(at * 100 / (bytes.length || 1));
    if (percent !== shown) stage("read", label, at, bytes.length || 1);
    shown = percent;
  };
  heard();
  const reader = picked.stream().getReader();
  for (let read; !(read = await reader.read()).done;) {
    if (at + read.value.length > bytes.length) throw new Error("your file changed after you picked it");
    bytes.set(read.value, at);
    at += read.value.length;
    heard();
  }
  if (at !== bytes.length) throw new Error("your file changed after you picked it");
  return bytes;
}

// A Tools tab's ask (answered whatever happens: the page waits on it): the picked image's (file: mounted, checked
// first, prime), another File's (build: an AzurKit build to open, mounted only for its read) or none (a mods file, a
// plan's spoiler). Verify every file hashes here what the image's kept check hasn't (sdk.layout's whole), in
// WebCrypto as prime does, its bar the bottom bar's, and hands the engine those digests (sdk.verify_all).
const TOOLS = ["info", "verify_all", "files", "open", "mods_file", "plan_spoiler", "replace", "saves"];
const DATA = ["data", "data_edit", "community"];   // the Data tab's and the Patches tab's community list: no image
async function tool({ py, engine }, data) {
  if (data.type === "saves") {   // the Saves section: a slot's Files, an HDD image or the image's XBE and BIOS files
    const given = data.given, blobs = { files: {} };   // read at once: Safari answers each read of a File 200 ms late
    await Promise.all([...Object.entries(data.files ?? {}).map(async ([path, one]) => blobs.files[path] = await pickedBytes(one)),
                       ...["flash", "mcpx"].filter((key) => data[key]).map(async (key) => blobs[key] = await pickedBytes(data[key]))]);
    const asked = (extra = {}) => engine({ type: "saves", given: { ...given, ...extra }, blobs });
    if (data.hdd) return mounted(py, data.hdd, (image) => asked({ image }));
    return data.file ? mounted(py, data.file, (iso) => asked({ iso })) : asked();
  }
  if (data.type === "replace") {   // a file picked to replace one of the image's: its entry; its bytes stay the File's
    const bytes = await streamed(data.picked);
    return engine({ type: "replace", given: { path: data.path, sha256: await digested(bytes), size: bytes.length } });
  }
  if (data.type === "open") return mounted(py, data.build, (iso) => engine({ type: "open", recipe: { iso } }));
  if (data.type === "mods_file" || data.type === "plan_spoiler") {
    const { type, call, ...given } = data;
    return engine({ type, given: data.type === "plan_spoiler" ? data.plan : given });
  }
  if (data.type !== "verify_all") return mounted(py, data.file, (iso) => engine({ type: data.type, recipe: { iso } }));
  const rest = mounted(py, data.file, (iso) => engine({ type: "layout", recipe: { iso }, whole: true }));
  if ("refused" in rest) return rest;
  const digests = await hashedApart(data.file, rest.files, checking("Checking every file"));
  return mounted(py, data.file, (iso) => engine({ type: "verify_all", recipe: { iso }, digests }));
}

// A build, the image mounted for it and unmounted after; its answer carries the engine's heap then (wasm memory never
// shrinks: a page that keeps the worker keeps one whose heap is small enough for another build, Step 4.3i), undefined
// where Pyodide hides it. A seed's spoiler comes after it (the page shows the build meanwhile, and replaces a worker
// it doesn't keep only once it has it). The build's changed files and the bytes its root files hold are hashed by the
// browser's SHA-256 (R2.6: about 10x wasm's), one at a time, as 14 at once take WebKit 8x as long, each a view of the
// engine's heap for its digest. A seed's build (AM-HUB-E) first asks for the
// pages it reads, twice at most, and its levels (668 MiB in all) never enter the heap: each is read here, its patches
// over it, for its sha256 and md5 (hasher.mjs), and only its patches are the build's bytes. The pieces are joined here,
// off the page's main thread, into the Blob the page saves (WEB §3.4: slices of the image and the bytes the build writes),
// and a segment hands over only its place in it. A character's pieces (218-240 MB) go into a build file of their own
// (outputs.mjs); a File slice holds no memory where a Blob holds its bytes.
let out = null;   // a build file's lock: its name and how to let go of it, kept until the page holds it ("held")
const letGo = () => {
  out?.release();
  out = null;
};
async function opened() {
  letGo();
  try {
    const name = `${PREFIX}${crypto.randomUUID()}.bin`;
    const release = await new Promise((held, fail) => {
      navigator.locks.request(name, { mode: "shared" }, () => new Promise((free) => held(free))).catch(fail);
    });
    out = { name, release };
    const handle = await (await navigator.storage.getDirectory()).getFileHandle(name, { create: true });
    return { name, handle, sync: await handle.createSyncAccessHandle(), at: 0 };
  } catch {
    letGo();
    return null;   // OPFS refuses (a private window, WebKit's ephemeral contexts): the pieces are Blobs
  }
}
function joined(file, { segments }, written) {
  const parts = segments.map((s) => s.kind === "copy" ? file.slice(s.offset, s.offset + s.size)
    : s.kind === "zero" ? new Uint8Array(s.size)
      : written && typeof s.data?.opfs === "number" ? written.slice(s.data.opfs, s.data.opfs + s.size) : s.data);
  return { blob: new Blob(parts, { type: "application/octet-stream" }),
           segments: segments.map(({ data, ...place }) => place),
           held: written ? 0 : segments.reduce((n, s) => n + (s.kind === "bytes" ? s.size : 0), 0) };
}
// The dresses this browser keeps (D1015, D1067): a character build's kept answers (the engine's Kept), by the build's
// hint: the image and what the dress stands on (the character, the packs, the seed). A hint finds the answers its last
// build kept, which the engine takes only under their own keys: another's are a miss, never another build. Made and kept
// after the build's answer (and its seed's spoiler), off the click's wait: a worker the page ends first keeps none, and
// the next build dresses again. DRESSES hints at most, the oldest dropped first.
const DRESS = "azurkit-dress", DRESSES = 32, ORDER = "";
const dresses = (mode, fn) => stored(DRESS, "dress", mode, fn);
const hintOf = (file, packs, randomizer, character) => {
  try {
    return character ? text([ids.get(file) ?? null, character, packs ?? null, randomizer ?? null], true) : null;
  } catch {
    return null;   // a value JSON can't hold: nothing kept
  }
};
const keep = (hint, kept) => dresses("readwrite", (store) => {
  const order = store.get(ORDER);
  order.onsuccess = () => {
    const hints = [...(order.result ?? []).filter((h) => h !== hint), hint];
    for (const old of hints.splice(0, Math.max(0, hints.length - DRESSES))) store.delete(old);
    store.put(hints, ORDER);
    store.put(kept, hint);
  };
  return order;
});

async function build({ py, engine, reads }, { file, packs, xbr, randomizer, character, community, files, picked }) {
  const before = self.azurkitLateReads ?? 0;
  const hint = hintOf(file, packs, randomizer, character);
  const offered = hint && await dresses("readonly", (store) => store.get(hint)).catch(() => null);
  const held = {}, hashes = {};
  for (const [path, one] of Object.entries(picked ?? {})) {
    held[path] = await pickedBytes(one);
    hashes[path] = await digested(held[path]);
  }
  const output = character ? await opened() : null;
  if (output) self.azurkitOut = (data, size) => {   // a Uint8Array, or a place in the heap and its size
    const at = output.at, bytes = size === undefined ? data : py._module.HEAPU8.subarray(data, data + size);
    output.sync.write(bytes, { at });
    output.at += bytes.length;
    return at;
  };
  const made = await mounted(py, file, async (iso) => {
    let composed = engine({ type: "build", ...(files ? { picked: held, hashed: hashes } : {}),
                           ...(offered ? { kept: offered } : {}), recipe: { iso, packs, xbr,
      ...(files ? { files } : {}),
      ...(randomizer ? { randomizer } : {}), ...(character ? { character } : {}),
      ...(community ? { community } : {}) } });
    while (composed.ahead) {
      await reads.spans(file, ids.get(file) ?? file, composed.ahead).catch(() => null);   // a hint: a failed read is the engine's
      composed = engine({ type: "ahead" });
    }
    if ("refused" in composed) return composed;
    const shas = {};
    if (composed.patched.length) {
      await md5Ready();
      Object.assign(shas, await hashed(file, composed.patched, (done, total) => post({ type: "progress", stage: "layout",
        label: "Hashing the changed files", done, total, percent: total ? Math.floor(done * 100 / total) : null })));
    }
    for (const key of composed.hash) {
      const { data, at, size } = engine({ type: "hash", key });   // digest copies them at the call
      shas[key] = hex(await crypto.subtle.digest("SHA-256", data ?? py._module.HEAPU8.subarray(at, at + size)));
    }
    return engine({ type: "hashed", shas });
  }).finally(() => {
    delete self.azurkitOut;
    output?.sync.flush();
    output?.sync.close();
  });
  const heap = py._module?.HEAPU8?.length;
  if ("refused" in made) return post({ type: "refused", message: made.refused, heap });
  post({ type: "built", ...made, ...joined(file, made, output && await output.handle.getFile()),
         ...(output ? { out: output.name } : {}), heap, late: (self.azurkitLateReads ?? 0) - before });
  if (made.report.plan) {
    let reply;
    try {
      reply = engine({ type: "spoiler", sha256: made.report.plan.sha256 });
    } catch (error) {
      reply = { refused: lastLine(error) };
    }
    post({ type: "spoiled", ...reply });
  }
  if (!hint) return;
  try {   // the dress the build worked out (none on a hit), made over the image mounted again, and kept
    const kept = mounted(py, file, () => engine({ type: "kept" }));
    if (Object.keys(kept).length) await keep(hint, kept);
  } catch {}   // a dress not kept is a dress made again
}

try {
  const loaded = await load();
  heap = () => loaded.py._module?.HEAPU8?.length;
  let queue = Promise.resolve();   // the messages in order: one that loads numpy holds those after it
  // The Characters tab's asks that stand on no image overtake an image's check (a player's Install lists its variants
  // now): the check's waits are the File's and WebCrypto's, the engine idle. They keep their own order (behind: those
  // of them queued), and the engine's answer is sync, so nothing runs beside them.
  let checking = false, behind = 0;
  self.onmessage = ({ data }) => {
    if (data?.type === "held") return letGo();   // the page holds the last build file now
    if (!["warm", "build", "vanilla", "preset", "decode", "restore", "randomizer", "tracker", "plan", "content",
          ...CHARACTER, ...TOOLS, ...DATA].includes(data?.type)) return;
    const aside = !data.file && ["content", ...CHARACTER].includes(data.type);
    if (aside && checking && !behind && loaded.numpied) return handle(data);
    if (aside) behind++;
    queue = queue.then(() => needsNumpy(data) ? numpy(loaded) : null)
      .then(() => {
        if (!data.file) return;
        checking = true;
        return prime(loaded, data.file).catch(() => null).finally(() => { checking = false; });
      }).then(() => {
        if (aside) behind--;
        return handle(data);
      }).catch((error) => post({ type: "failed", message: lastLine(error) }));
  };
  const handle = (data) => {
    try {
      if (data.type === "warm") return void loaded.engine(data);
      if (data.type === "content") return content(loaded, data);
      if (CHARACTER.includes(data.type)) {   // answered whatever happens: the page waits on it
        try {
          return character(loaded, data);
        } catch (error) {
          return post({ type: "reply", call: data.call, reply: { refused: lastLine(error) } });
        }
      }
      if (data.type === "vanilla") return vanilla(loaded, data.file);
      if (TOOLS.includes(data.type)) {   // answered whatever happens: the queue waits for its hashing
        return tool(loaded, data).catch((error) => ({ refused: lastLine(error) }))
          .then((reply) => post({ type: "reply", call: data.call, reply }));
      }
      if (data.type === "tracker" || data.type === "plan" || DATA.includes(data.type)) {   // answered whatever happens
        let reply;
        try {
          reply = loaded.engine(data);
        } catch (error) {
          reply = { refused: lastLine(error) };
        }
        return post({ type: "reply", call: data.call, reply });
      }
      if (data.type === "randomizer") {   // the image mounted while a body is worn: its size folds into the walk and roll
        return post({ type: "rando", ticket: data.ticket, reply: data.file ? mounted(loaded.py, data.file,
          (iso) => loaded.engine({ ...data, given: { ...data.given, iso } })) : loaded.engine(data) });
      }
      if (data.type === "restore") return post({ type: "restored", ...loaded.engine(data) });
      if (data.type === "preset" || data.type === "decode") {
        const reply = loaded.engine(data);
        if ("refused" in reply) return post({ type: "refused", message: reply.refused, quiet: true });
        return post(data.type === "preset" ? { type: "preset", fragment: reply.fragment }
          : { type: "decoded", preset: reply.preset });
      }
      return build(loaded, data).catch((error) => {   // its failure is the queue's to post
        delete self.azurkitOut;
        throw error;
      });
    } catch (error) {
      post({ type: "failed", message: lastLine(error) });
    }
  };
  post({ type: "ready", start: loaded.start, ...loaded.engine({ type: "catalog" }) });
} catch (error) {
  post({ type: "failed", message: `AzurKit didn't load: ${lastLine(error)}` });
}

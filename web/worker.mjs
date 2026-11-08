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
//      {type: "content_check", call, manifest, id, files, source} (an Install's check, sdk.content_check), and {type: "content", files, installed} (what this browser keeps installed, written
//      into the engine's content folder file by file once checked: kept), {type: "warm"} (numpy and a dress's modules,
//      unanswered: a body's build ahead starts at its first step), and the Tools tab's {type: "info" |
//      "verify_all" | "files", call, file} (sdk.image_info, sdk.verify_all: the files its kept check hasn't hashed,
//      hashed here, sdk.files), {type: "open", call, build} (another File: an AzurKit build's recipe, sdk.open_build of
//      the files it changed), {type: "mods_file", call, text | recipe | preset} (sdk.mods_file) and {type:
//      "plan_spoiler", call, plan} (sdk.spoiler), and the Data tab's {type: "data" | "data_edit", call, given}
//      (sdk.data, sdk.data_edit: config.xbr's cells from the file the wheel ships, no image), and the Variants view's
//      {type: "variants" | "variant_open" | ... (VARIANTS), call, given, file?, data?} (sdk.variants ...: data an
//      Import's or an Add WAV's bytes; file the image, for a Check, the calls on its dress and a base's reads) and {type: "library", folders} (what
//      this browser keeps of your variants, written as the engine's library, ./variants, whole). A
//      message with a File (file) has the image checked first, once a File (prime).
// Out: {type: "native", kernel?, twin?} (the reach calls each path answered since the last, before the answer they
//      went into), {type: "ready", catalog, version, commit, start, cold?} (start: "snapshot" or "cold", load()'s;
//      cold: why a kept snapshot wasn't started from), {type: "progress", stage, label, done, total, percent} (core/progress.py's
//      record, mid-call: the check, then a build's stages; the worker's own: its start before ready, the kept image's
//      walk), {type: "at", where} (the await the job is in: awaiting()), {type: "built", report, size, segments, heap} (a seed's report without its spoiler, which {type:
//      "spoiled", text | refused} brings next: the build shows sooner),
//      {type: "refused", message, heap}
//      (the engine's refusal, which names what and why, never game bytes), {type: "failed", message, trapped?}
//      (trapped: the engine's wasm trapped, failure()),
//      {type: "vanilla", release, label, packs, info} (the image's own value of each slider at a site of its XBE, and
//      sdk.image_info's answer, which the Tools tab shows with no ask of its own),
//      {type: "opened", preset} (the image is an AzurKit build: its recipe, sdk.open_build of the files it changed),
//      {type: "preset", fragment} (the share link's #p=…), {type: "decoded", preset} (a link's recipe),
//      {type: "restored", ticked, values, xbr, dropped, randomizer} (the remembered setup, sdk.restore),
//      {type: "rando", ticket, reply} (what the Randomizer tab shows, or {refused}), {type: "reply", call, reply}
//      (a tracker's, plan's, Characters', Data or Tools' answer: the view, {plan}, or {refused}), {type: "csp", directive,
//      blocked}. A read that is neither an image nor an AzurKit build ends with {type: "unread"}. Each but a progress record
//      carries the engine's heap then (undefined where Pyodide hides it), which the page's two workers count (workers.mjs).
import { DRESSING, hashed, hashedApart, md5Ready } from "./hasher.mjs";
import { text } from "./memo.mjs";
import { keepParts, partsHint, partsOf } from "./parts.mjs";
import { PREFIX } from "./outputs.mjs";

const base = new URL("./", import.meta.url);
let heap = () => undefined;
const post = (message, transfer = []) => self.postMessage(
  message.type === "progress" || message.type === "at" || "heap" in message ? message : { ...message, heap: heap() },
  transfer);
// Where a job is (Step 4.3r4t): the await its image's check or its queue is in, as {type: "at", where} (no heap: a
// job's heap is its answer's), which the pool keeps for its state (workers.mjs), so a wait that never ends names it.
const awaiting = (where) => post({ type: "at", where });
self.addEventListener("securitypolicyviolation", (e) =>
  post({ type: "csp", directive: e.violatedDirective, blocked: e.blockedURI }));

const lastLine = (error) => String(error?.message ?? error).trim().split("\n").at(-1);

// Where a call failed (Step 4.4ci44), as its message's last line and " · " parts: the engine's call (its request's
// type), the innermost FRAMES of Python's stack and, where the engine's WebAssembly itself failed (a trap, Pyodide's
// fatal error), the wasm functions it was in by index. A Python exception's traceback is in its message; a trap's stack
// is only in Pyodide's dump of it (dump_traceback, written to the engine's stdout), so the engine's first SAID lines
// out of a call are kept (said), from the dump's header on once it comes: the dump is its header, then the innermost
// frame first, and at numpy's import it ran 72 lines, so a call's last 40 lost its header and innermost frames and
// named importlib's frames from mid-stack as the innermost. A trap leaves that engine for good: every later call and
// mount says that first failure (dead, which Pyodide's on_fatal sets wherever it traps: numpy's load too), never
// Pyodide's "already fatally failed" (a failed prime's, a kept dress's or the rest's is not posted, and numpy's load
// swallows its own), and each failure it posts says so (trapped), so the pool replaces the worker at once and sends the
// page's job to the next once (workers.mjs's restart(), D1126). A page of CI's WebKit said only "access to a null
// reference (evaluating '__pyproxy_apply(t,e,n,o,s)')": JavaScriptCore's name for a fault of wasm code at an address
// below the lowest one a process may map (its fault handler's, meant for Wasm GC's struct and array reads), inside the
// C call of a Python function the worker called (pyproxy.c's), so a trap, not a destroyed PyProxy (Pyodide refuses a
// call of one in JS, before any wasm runs); and, bare, from a call no mount held (a build's unmount said "already
// fatally failed").
const SAID = 40, FRAMES = 4, said = [];
let dead = null, calling = null;   // the trap that ended this worker's engine, located; the call it was in
const told = (line) => {
  if (line.includes("most recent call first")) said.length = 0;   // the dump's header ("Stack (most recent ...):")
  if (said.length < SAID) said.push(line);
};
const FRAME = /^\s*File "([^"]+)", line (\d+),? in (.+)$/;
const where = (file) => file.replace(/^.*\/(site-packages|python\d+\.zip|python\d+\.\d+)\//, "");
function located(error, call) {
  const trapped = Boolean(error?.pyodide_fatal_error), message = lastLine(error);
  const frames = (trapped ? said : String(error?.message ?? "").split("\n").reverse()).map((line) => FRAME.exec(line))
    .filter(Boolean).slice(0, FRAMES).map(([, file, line, fn]) => `${where(file)} line ${line} (${fn})`);
  const wasm = trapped ? [...String(error?.stack ?? "").matchAll(/wasm-function\[(\d+)\]/g)].slice(0, FRAMES) : [];
  const parts = [trapped ? `The engine's WebAssembly failed${call ? ` in its ${call} call` : ""}: ${message}`
    : `${message}${call ? ` · in the engine's ${call} call` : ""}`];
  if (frames.length) parts.push(`Python at ${frames.join(" < ")}`);
  if (wasm.length) parts.push(`wasm functions ${wasm.map((m) => m[1]).join(", ")}`);
  return parts.join(" · ");
}
// A call's failure, as posted: after a trap, marked so (trapped), and the pool starts the engine again (workers.mjs).
const failure = (error) => ({ type: "failed", message: lastLine(error), ...(dead ? { trapped: true } : {}) });
// A tab's ask is answered whatever happens (the Characters, Tools, Tracker and Data tabs wait on it), its failure as a
// refusal; but a trapped engine's is thrown on, to be posted as failure() is, so the pool starts the engine again and
// sends the ask to the next once, as a build's (a refusal there left the engine dead, every later ask refused so).
const refusal = (error) => {
  if (dead) throw error;
  return { refused: lastLine(error) };
};

// The Variants view's (Step 4.6c): its library's calls, then Check with game data and Step 4.6b's calls on its dress
// and on a base species; each reads the loader, so numpy loads first. The engine's VARIANTS (ENGINE) holds the same.
const VARIANTS = ["variants", "variant_open", "variant_read", "variant_save", "variant_delete", "variant_import",
                  "variant_export", "variant_check", "variant_pictures", "variant_colours", "variant_preview",
                  "variant_rows", "export_pngs", "base_bones", "own_sounds", "kit_throw", "move_sources", "add_png",
                  "variant_weapons", "add_wav"];

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
from azurkit.tools.characters import parts, pool

PIECE = "/tmp/azurkit-piece"
VARIANTS = ("variants", "variant_open", "variant_read", "variant_save", "variant_delete", "variant_import",
            "variant_export", "variant_check", "variant_pictures", "variant_colours", "variant_preview",
            "variant_rows", "export_pngs", "base_bones", "own_sounds", "kit_throw", "move_sources", "add_png",
            "variant_weapons", "add_wav")   # the page's VARIANTS
PICKED = ("add_png",)   # a file the page read, copied into a variant's folder: its bytes in data, its name given's file
BARRED = ("variant_check", "variant_preview", "variant_rows", "export_pngs")   # their steps posted: the bar moves


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


def library(folders):
    """What this browser keeps of your variants (IndexedDB, which any script of the site's origin may write) written
    as the engine's library, ./variants (library.root() here: no user data folder), whole, the folders there before
    removed: each folder only where its name is a variant's and each file only where its path lies inside it (no
    "..", no absolute or empty part). The reasons the others were left out, each naming its folder or path. Written
    here, not by the library's module, which loads numpy: each worker writes it as it starts."""
    import re
    import shutil
    import sys
    from pathlib import Path

    root, dropped = Path("variants"), []
    shutil.rmtree(root, ignore_errors=True)
    if (held := sys.modules.get("azurkit.tools.characters.library")) is not None:
        held._parsed.clear()   # a recipe read before is read again
    for name, files in folders.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(name)) or not isinstance(files, dict):
            dropped.append(f"kept variant {name!r}: not a variant's folder")
            continue
        for path, data in files.items():
            parts = str(path).split("/")
            if chr(92) in path or ":" in path or any(part in ("", ".", "..") for part in parts):   # a backslash
                dropped.append(f"kept variant {name!r}: {path!r} is no file inside its folder")
                continue
            (root / name / path).parent.mkdir(parents=True, exist_ok=True)
            (root / name / path).write_bytes(bytes(data))
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
    work out again. Nothing is kept outside a build: any ask but its own (BUILDING) ends what it kept, as one the page
    asks nothing of (no character, or one that failed) leaves it open, where a reshape's pictures after it kept each
    shape's plan (D1054's one heap)."""

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


class Parts(Kept):
    """tools.characters.parts.STORE here (Step 4.6o): the parts this browser kept for a Check's recipe content
    (IndexedDB's, checked() in this file), handed in with the Check, each let go of as it is taken (part_codec's: no
    pickle, a stale one refused by name), and those its dress works out, made once its answer is out (the parts call)
    and handed back with the keys of those it took, so the page keeps what that content's Check used. A part this
    worker held, taken again (used), is one it took if this browser keeps it (this worker took it or handed it back
    made: known), else one worked out, so a copy checked after its original in one visit has its parts kept too."""

    def __init__(self):
        super().__init__()
        self.took, self.known = [], set()

    def get(self, key):
        found = self.offered.pop(key, None)
        if found is not None:
            self.took.append(key)
        return found

    def used(self, key, make):
        if self.made is None:
            return
        if key not in self.known:
            self.made[key] = make
        elif key not in self.took:
            self.took.append(key)

    def taken(self, made=True):
        """The parts to keep, made, by key, and the keys of those taken; none kept after (one the codec refuses left
        out: a part kept nowhere is worked out again)."""
        took, put, out = self.took, self.made or {}, {}
        self.took, self.offered, self.made = [], {}, None
        for key, make in put.items() if made else ():
            try:
                out[key] = make if isinstance(make, bytes) else make()
            except ValueError:
                pass
        self.known.update(took, out)
        return {"made": out, "taken": took}


KEPT = characters.CACHE = Kept()
PARTS = parts.STORE = Parts()
BUILDING = ("build", "ahead", "hash", "hashed", "spoiler", "kept", "parts")   # a build's own asks (build()), its kept
# asks last


def engine(request):
    LAST.clear()
    if request.type not in BUILDING:
        KEPT.taken(made=False)
        PARTS.taken(made=False)

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
    if request.type == "parts":   # after a Check's answer: the parts it took, and those it worked out, made now
        return js(PARTS.taken())
    if request.type == "content":
        return js({"dropped": kept(request.files, json.loads(JSON.stringify(getattr(request, "installed", None))
                                                             or "null"))})
    if request.type == "library":   # through to_py: each file a memoryview
        return js({"dropped": library(request.folders.to_py())})
    if request.type in VARIANTS:   # through JSON: a null is None; an Import's bytes beside it
        try:
            given = getattr(request, "given", None)
            given = (json.loads(JSON.stringify(given)) if given is not None else None) or {}
            if getattr(request, "data", None) is not None and request.type in PICKED:   # read from a file of its name
                from pathlib import Path

                picked = Path("/tmp/azurkit-picked") / (Path(str(given.get("file") or "")).name or "picked")
                picked.parent.mkdir(parents=True, exist_ok=True)
                picked.write_bytes(request.data.to_bytes())
                given["file"] = str(picked)
            elif getattr(request, "data", None) is not None:
                given["data"] = request.data.to_bytes()
            if mounted := getattr(request, "iso", None):
                given["iso"] = mounted
            call = getattr(sdk, request.type)
            if request.type == "variant_check":   # build()'s keeping: the dress this browser kept offered, its own kept
                KEPT.made, PARTS.made = {}, {}
                if offered := getattr(request, "kept", None):
                    KEPT.offered = {key: getattr(offered, key).to_bytes() for key in Object.keys(offered)}
                if offered := getattr(request, "parts", None):   # and the parts kept for its content (Step 4.6o)
                    PARTS.offered = {key: getattr(offered, key).to_bytes() for key in Object.keys(offered)}
            return js(call(given, progress=progressed) if request.type in BARRED else call(given))
        except (OSError, ValueError) as exc:
            return js({"refused": str(exc)})
    if request.type == "restore":
        out = sdk.restore(json.loads(JSON.stringify(request.setup)) if request.setup else request.setup)
        if out.get("randomizer", {}).get("on") is True:   # its logic read before the page is ready, as the app's
            sdk.randomizer_logic()                         # server reads it ahead (D1008), so a reopen's tab finds it
        return js(out)
    if request.type in ("pickers", "preview", "match", "content_check"):
        try:
            if request.type == "content_check":
                entry, files = getattr(request, "id", None), getattr(request, "files", None)
                given = {"manifest": request.manifest} | ({"id": entry, "source": getattr(request, "source", None),
                                                          "files": {k: bytes(v) for k, v in files.to_py().items()}}
                                                         if entry else {})
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
            if mounted := getattr(request, "iso", None):   # All files: another file than config.xbr, from the image
                given["iso"] = mounted
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
                return js(sdk.randomizer_settings(json.loads(JSON.stringify(request.given)), progress=progressed))
            if request.type == "tracker":   # through JSON: a mark's null clock is None (to_py gives JsNull)
                return js(sdk.tracker(json.loads(JSON.stringify(request.given)), progress=progressed))
            if request.type == "plan":
                return js({"plan": sdk.plan(request.recipe.to_py(), progress=progressed)})
            if request.type == "vanilla":   # with what the Tools tab says of it, so the tab's open asks nothing
                return js(sdk.vanilla(request.recipe.iso) | {"info": sdk.image_info(request.recipe.iso)})
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
// German.xbr it reads whole, a worn body's its files (107 pages) and, before a dress it works out, English.xbr (36),
// so PAGES holds them with the tables.
const PAGE = 1 << 20, BLOCK = 16 << 20, PAGES = 192, BLOCKS = 3;
const ids = new WeakMap();   // a message's File -> its image's id (identify)
// A read of the picked File the browser refuses (WebKit's, Chromium's: a File changed or gone since its pick), or one
// that comes short (an image made shorter, which Firefox reads silently), is the engine's OSError (Emscripten's EIO,
// 29, as its own terminal's failed reads give), never a throw through Pyodide's read, which took it as fatal: the
// build failed "Pyodide already fatally failed and can no longer be used", its worker gone with it. A call that met
// one is refused naming the change (CHANGED, engine(); Step 4.4ci30).
const EIO = 29, CHANGED = "Your image changed since you picked it, so it can't be read: pick it again";
let unreadable = false;   // whether the engine's call in flight met such a read
function readInBlocks(FS) {
  const WORKERFS = FS.filesystems.WORKERFS;
  const unread = () => {
    unreadable = true;
    return new FS.ErrnoError(EIO);
  };
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
        try {
          data = new Uint8Array(WORKERFS.reader.readAsArrayBuffer(file.slice(index * unit, (index + 1) * unit)));
        } catch {
          throw unread();
        }
        if (cache.size >= keep) cache.delete(cache.keys().next().value);
      }
      cache.set(index, data);
      const from = at - index * unit, n = Math.min(end - at, data.length - from);
      if (!(n > 0)) throw unread();   // the image got shorter while the engine read it
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
// starting from one starts the worker as before; "ready" says which start it was (start) and, where a kept one wasn't
// started from, why (cold). Stock Pyodide can't restore a heap grown past the module's initial memory, 31,457,280 B (a
// RangeError), so the restore grows it first (grown).
// It is kept as one record, {heap, size}, written in one transaction, and a worker starts only from a whole one: a
// record that isn't one, or whose heap isn't its size (another page's older form, a write cut short), is refused by name
// and deleted, and the worker starts cold. A heap cut to 60 % or 90 % of its bytes held the restoring worker's thread for
// good, the page never ready and saying nothing (Step 4.4ci37). Its length is all that is checked: a heap of its size
// spoiled (its header, magic, tail or middle) failed Pyodide's restore and started cold, 4 of 4, and a SHA-256 of it
// held each snapshot start 13-19 ms more and copied its 30 MB.
// Pyodide's wasm (9.6 MB) is compiled once a page (Step 4.4bf): the first worker compiles it as Pyodide does and posts
// its Module ({type: "wasm"}), which the pool sends each later worker first (workers.mjs), and Pyodide's own
// instantiateStreaming of its fetch is answered from that Module (about 0.1 s and 0.25-0.42 CPU-s a worker start: B's
// after a change, F's after a big build); one that won't instantiate compiles as before. In WebKit (Safari's engine)
// each worker compiles its own and posts none (Step 4.4ci47), a precaution against an unproven JSC fault: each CI
// failure of the WebKit pack golden on GitHub's Apple Silicon runner since 4.4bf (3 of 10 runs, 1 of 7 before: not
// significant) was JavaScriptCore's wasm going wrong (a load's ValueError, a trap's "null reference", then the page's
// process killed by JSC's own assertion while it made a trap's error: StackVisitor::readInlinableNativeCalleeFrame, a
// frame of optimized wasm whose code isn't its own), never reproduced here; one Module's compiled code run by two
// workers at once is the step's change in what JSC does, so a possible cause, not a likely one.
// Pyodide's instantiate catches what its instantiation and the callback it hands the instance throw (a grow refused, a
// RangeError where memory is short; a compile refused), warns and never settles its load: so grown hands that to
// `failed`, which ends loading()'s wait, and a restore refused so starts cold, a cold start refused says so by name.
const SNAPSHOT = "azurkit-snapshot", IMPORTS = "import azurkit\nfrom azurkit import sdk\nfrom azurkit.core import iso\n";
const STREAMING = WebAssembly.instantiateStreaming;
const SHARES = !(/AppleWebKit/.test(navigator.userAgent) && !/Chrome\//.test(navigator.userAgent));   // not WebKit
// In WebKit the worker's WebAssembly.instantiate compiles and instantiates at once (a worker may), its promise settled
// by itself (Step 4.5k): numpy's load (Pyodide's loadPackage) instantiates its 13 shared libraries each so, and in
// CI's Linux WebKit an engine sat in it 120 s and 596 s, where it takes 0.1-0.2 s (60 of 60 here): WebKit's own
// worker bug 208368 (GTK) leaves such a promise unsettled, its completion timer ignored on another run loop, closed
// unfixed. Its sync compile is JSC's, which no timer settles. md5.wasm's load (hasher.mjs) is one too.
if (!SHARES) {
  WebAssembly.instantiate = (source, imports) => {
    try {
      const module = source instanceof WebAssembly.Module ? source : new WebAssembly.Module(source);
      const instance = new WebAssembly.Instance(module, imports);
      return Promise.resolve(module === source ? instance : { module, instance });
    } catch (error) {
      return Promise.reject(error);
    }
  };
}
let compiled = null;   // the Module the pool sent this worker, if any
self.addEventListener("message", ({ data }) => {
  if (data?.type === "wasm" && data.module instanceof WebAssembly.Module) compiled = data.module;
}, { once: true });
const grown = (create, size, failed) => (settings) => {
  const instantiate = settings.instantiateWasm, given = compiled;
  let mine = !given;
  WebAssembly.instantiateStreaming = async (response, imports) => {   // Pyodide's one call, once
    WebAssembly.instantiateStreaming = STREAMING;
    if (given) {
      try {
        const instance = await WebAssembly.instantiate(given, imports);
        Promise.resolve(response).then((r) => r.body?.cancel()).catch(() => {});   // its fetch, unread
        return { instance, module: given };
      } catch {
        mine = true;
      }
    }
    return STREAMING.call(WebAssembly, response, imports).catch((error) => {
      failed(error);
      throw error;
    });
  };
  settings.instantiateWasm = (imports, ready) => instantiate(imports, (instance, module) => {
    WebAssembly.instantiateStreaming = STREAMING;
    try {
      if (mine && SHARES) post({ type: "wasm", module });
      const { memory } = instance.exports, short = Math.ceil(size / 65536) - memory.buffer.byteLength / 65536;
      if (short > 0) memory.grow(short);
      return ready(instance, module);
    } catch (error) {
      failed(error);
      throw error;
    }
  });
  return create(settings);
};
const loading = (loadPyodide, create, size, options) => new Promise((resolve, reject) => {
  loadPyodide({ ...options, createPyodideModule: grown(create, size, reject) }).then(resolve, reject);
});

// The kept record's heap if it is a whole one, [heap, null]; else [null, why it was refused] ([null, null]: none kept).
function whole(record) {
  if (record == null) return [null, null];
  const { heap, size } = record;
  if (!(heap instanceof Uint8Array) || !Number.isSafeInteger(size)) {
    return [null, "the kept snapshot was refused: it isn't a {heap, size} record"];
  }
  if (heap.length !== size) {
    return [null, `the kept snapshot was refused: its heap is ${heap.length} bytes, not ${size}`];
  }
  return [heap, null];
}

async function load() {
  starting(0);
  const site = await (await fetch(new URL("host.json", base))).json();
  const pyodide = new URL("pyodide/", base).href;
  const { loadPyodide, version } = await import(new URL("pyodide.mjs", pyodide).href);
  const options = {
    indexURL: pyodide, lockFileURL: new URL("pyodide-lock.json", pyodide).href, packageBaseUrl: pyodide,
    stdout: told, stderr: told,
  };
  const key = `${version} ${site.integrity}`;
  const record = await stored(SNAPSHOT, "heap", "readonly", (store) => store.get(key)).catch(() => null);
  let [heap, cold] = whole(record);
  if (cold) stored(SNAPSHOT, "heap", "readwrite", (store) => store.delete(key)).catch(() => null);   // not awaited
  const { default: create } = await import(new URL("pyodide.asm.mjs", pyodide).href);
  const restored = heap && await loading(loadPyodide, create, heap.length, { ...options, _loadSnapshot: heap })
    .catch((error) => {
      cold = `the kept snapshot didn't restore: ${lastLine(error)}`;
      return null;
    });
  heap = null;
  const py = restored ?? await loading(loadPyodide, create, 0, { ...options, _makeSnapshot: true });
  const reads = readInBlocks(py.FS);
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
      stored(SNAPSHOT, "heap", "readwrite", (store) => {
        store.clear();
        store.put({ heap: made, size: made.length }, key);
      }).catch(() => null);   // not awaited
    } catch {
      // no snapshot: the next worker starts as this one did
    }
  }
  if (py._api) py._api.on_fatal = (error) => { dead ??= located(error, calling); };   // after its dump, before its throw
  const asked = py.runPython(ENGINE);
  const engine = (request) => {   // a call that met an unreadable image (readInBlocks) refuses naming its change
    if (dead) throw new Error(dead);
    unreadable = false;
    said.length = 0;
    calling = request.type;
    let reply;
    try {
      reply = asked(request);
    } catch (error) {
      throw new Error(unreadable ? CHANGED : dead ?? located(error, request.type));
    } finally {
      calling = null;
    }
    if (unreadable && reply && typeof reply === "object" && "refused" in reply) reply.refused = CHANGED;
    return reply;
  };
  return { py, engine, reads, start: restored ? "snapshot" : "cold", cold };
}

// fn(the path of file mounted read-only at /in), unmounted after it (after the promise it gives, if it gives one). The
// mount's times are the File's lastModified (WORKERFS takes lastModifiedDate, which WebKit's File lacks, and else the
// time of the mount), so the engine's check of an image holds from one message to the next (sdk._stamp: by its path,
// size and times) and a changed File is checked again.
function mounted(py, file, fn) {
  if (dead) throw new Error(dead);
  if (!file.lastModifiedDate) Object.defineProperty(file, "lastModifiedDate", { value: new Date(file.lastModified) });
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  const unmount = () => py.FS.unmount("/in");
  const failed = (error) => {   // the call's own failure stands: after a trap Pyodide refuses its FS too (located())
    try {
      unmount();
    } catch {}
    throw error;
  };
  let done;
  try {
    done = fn(`/in/${file.name}`);
  } catch (error) {
    failed(error);
  }
  if (done instanceof Promise) return done.then((value) => (unmount(), value), failed);
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
// checked as itself, and its reads never come from the other's blocks. Each message brings its own clone of the
// page's File, so the id read is posted ({type: "id"}) and the pool sends it with each later message of that File
// (id, Step 4.4bf), to every worker: the ends are read once a pick, not once a message.
async function identify(file) {
  if (!ids.has(file)) {
    const ends = new Blob([file.slice(0, SAMPLE), file.slice(Math.max(SAMPLE, file.size - SAMPLE))]);
    const sample = hex(await crypto.subtle.digest("SHA-256", await ends.arrayBuffer()));
    ids.set(file, `${file.name}|${file.size}|${file.lastModified}|${sample}`);
    post({ type: "id", id: ids.get(file) });
  }
  return ids.get(file);
}
const stamps = (mode, fn) => stored(STORE, "stamp", mode, fn);   // the browser's kept stamp
async function prime(loaded, file) {
  const { py, engine } = loaded;
  awaiting("check: its id");
  const id = await identify(file);
  if (loaded.primed !== id) awaiting("check: the kept stamp");
  const kept = loaded.primed === id ? null : await stamps("readonly", (store) => store.get("last")).catch(() => null);
  if (kept?.id === id) stage("check", "Reading your image", 0, 1);   // its walk: the first read of its folders here
  awaiting("check: the tables' reads");
  await loaded.reads.tables(file, id, kept?.id === id ? kept.pages : null).catch(() => null);   // a hint: a failed read
  if (loaded.primed === id) return;                                                         // leaves them to the engine
  loaded.primed = null;   // the engine's stamp is this File's from its prime on (sdk.prime checks it by its digests)
  if (kept?.id === id) {
    awaiting("check: the engine's prime");
    const checked = mounted(py, file, (iso) => engine({ type: "prime", recipe: { iso }, digests: kept.digests }));
    if (!("refused" in checked)) {
      stage("check", "Reading your image", 1, 1);
      loaded.primed = id;
      return vouched(loaded, file, id, kept);
    }
  }
  self.azurkitChecks = (self.azurkitChecks ?? 0) + 1;
  awaiting("check: the engine's layout");
  const listed = mounted(py, file, (iso) => engine({ type: "layout", recipe: { iso } }));
  if ("refused" in listed) return;
  const digests = await hashedApart(file, listed.files, checking("Checking your image"), CHECK_RUN,
                                    (where) => awaiting(`check: ${where}`));
  awaiting("check: the engine's prime");
  const checked = mounted(py, file, (iso) => engine({ type: "prime", recipe: { iso }, digests }));
  if ("refused" in checked) return;
  loaded.primed = id;
  awaiting("check: keeping the stamp");
  await stamps("readwrite", (store) => store.put({ id, digests, pages: walked.get(id) }, "last")).catch(() => null);
  vouched(loaded, file, id, { digests });
}

// What a Save needn't hash again (Step 4.4ba): where a browser refuses every read of a File changed on disk since its
// pick (WebKit's, Chromium's: app.mjs's READS_REFUSED), the page is told the sha256 of each of the image's files hashed
// from the picked File, by the image's id ({type: "vouched", id, digests}; the pool's jobs ignore it): the build files'
// at its check, then the rest (sdk.layout's whole), hashed once an image in the background once the ask the check came
// with is answered (loaded.rest, the queue's), by one worker of this browser at a time (a Web Lock), and kept with the
// stamp, so a later visit hashes neither. A Save hashes what the page doesn't know yet. Firefox reads a changed File
// silently: there a Save hashes every file, and none of this runs. The rest gives way to a character's dress
// (hasher.mjs's DRESSING, held while an ask that carries a character runs: dressing()), Step 4.4ci25. While the rest is
// hashed the page hears so, with its progress ({type: "resting", id, done, total}), then {type: "rested", id} after its
// digests or its failure, so a Save meanwhile waits for them rather than hashing the same files again beside it (Step
// 4.4bl).
const VOUCHING = /AppleWebKit/.test(navigator.userAgent), resting = new Set();
// An ask that carries a character (a build wearing one, a reshape's pictures and matches) runs holding DRESSING, shared
// (any of this browser's workers may hold it at once), which the rest's hash gives way to (Step 4.4ci25). Where the
// browser refuses Web Locks (one that keeps no site data: Firefox with every cookie blocked), the ask runs without it:
// the rest's own lock is refused there too, so no rest runs beside it.
const dressing = (data, run) => {
  if (!(data.character || data.recipe?.character) || !navigator.locks) return run();
  let ran = false;
  return navigator.locks.request(DRESSING, { mode: "shared" }, () => { ran = true; return run(); })
    .catch((error) => { if (ran) throw error; return run(); });   // the ask's own failure stays its own
};
// A worker that primed while another hashes the rest (B, whose first job came with the pick, as F hashes it) looks
// before it walks the image for it: with the rest's lock held, or its digests in the stamp, it reads nothing of the
// image for the rest (Step 4.4ci30). It walked the image's whole layout after its job for nothing, its engine held
// meanwhile and the File read again; and on Windows WebKit opens each read of a File sharing it with readers only, so
// while one is open the image can't be written (a player's edit is refused by Windows then, not by the page).
const RESTING = (id) => `azurkit-rest ${id}`;
async function restElsewhere(id) {   // another of this browser's workers hashes the image's rest, or one hashed it
  const held = await Promise.resolve(navigator.locks?.query?.())
    .then((locks) => locks?.held?.some((lock) => lock.name === RESTING(id)), () => false);
  if (held) return true;
  const last = await stamps("readonly", (store) => store.get("last")).catch(() => null);
  return Boolean(last?.id === id && last.rest);
}
function vouched(loaded, file, id, kept) {
  if (!VOUCHING) return;
  self.postMessage({ type: "vouched", id, digests: { ...kept.digests, ...kept.rest } });
  if (kept.rest || resting.has(id)) return;
  loaded.rest = async () => {   // in the queue's turn (it waits for this, not for the hash): the engine's call
    if (await restElsewhere(id)) return;
    const rest = mounted(loaded.py, file, (iso) => loaded.engine({ type: "layout", recipe: { iso }, whole: true }));
    if ("refused" in rest || !rest.files.length) return;
    resting.add(id);
    const hash = async (lock) => {
      if (!lock) return;   // another worker of this browser hashes it
      const last = await stamps("readonly", (store) => store.get("last")).catch(() => null);
      if (last?.id === id && last.rest) return;   // another hashed it first
      const told = (done, total) => self.postMessage({ type: "resting", id, done, total });
      told(0, rest.files.reduce((n, [, , size]) => n + size, 0));
      try {
        const digests = await hashedApart(file, rest.files, told, undefined, undefined, true);   // gives way
        await stamps("readwrite", (store) => {
          const last = store.get("last");
          last.onsuccess = () => last.result?.id === id && store.put({ ...last.result, rest: digests }, "last");
          return last;
        });
        self.postMessage({ type: "vouched", id, digests });
      } finally {
        self.postMessage({ type: "rested", id });
      }
    };
    const locked = () => navigator.locks ? navigator.locks.request(RESTING(id), { ifAvailable: true }, hash)
      : hash(true);
    Promise.resolve().then(locked).catch(() => null).finally(() => resting.delete(id));   // a read refused: none vouched
  };
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
// every character call needs it (the swap's modules import it). After a trap it says that trap (dead), as engine()
// does: Pyodide refuses even a read of its loadPackage then ("already fatally failed"), and a trap no ask's failure
// posted (the rest's hash) was named so by the next ask that loads numpy (a shared warm-up).
const numpy = (loaded) => dead ? Promise.reject(new Error(dead))
  : loaded.numpy ??= (calling = "numpy load", loaded.py.loadPackage("numpy", {
    messageCallback: () => {}, errorCallback: () => {} })).finally(() => { calling = null; })
    .then(() => void (loaded.numpied = true));
const CHARACTER = ["pickers", "preview", "match", "content_check"];
const needsNumpy = (data) => data.type === "warm" || CHARACTER.includes(data.type) || VARIANTS.includes(data.type)
  || data.character || data.recipe?.character
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

// The engine's library (./variants): what this browser keeps of your variants, written whole once per worker and after
// each change the page keeps (a Save, an Import, a Delete); a folder or file that isn't one is left out, named.
function library({ engine }, { folders }) {
  for (const why of engine({ type: "library", folders }).dropped) console.warn(`AzurKit left out ${why}`);
}

// A Characters tab's call, the image mounted for it (none picked: no image).
function character(loaded, data) {
  const { py, engine } = loaded;
  if (!data.file) return post({ type: "reply", call: data.call, reply: engine(data) });
  if (data.type === "variant_check") return checked(loaded, data);
  mounted(py, data.file, (iso) => post({ type: "reply", call: data.call, reply: engine({ ...data, iso }) }));
}

// Check with game data (Step 4.6c): the dress this browser kept for the edit offered, as build()'s (D1015: the engine
// takes it only under its own key, by what the edit holds), and the one it works out kept after its answer, so a
// Check of content dressed before, here or in a worker since, answers without dressing again. And its dress's parts
// (Step 4.6o, parts.mjs): those kept for the recipe's content offered (no name: a copy's under any name), and the
// ones it took and worked out kept after its answer, a refusal's too (a refusal itself is never a part).
async function checked({ py, engine }, data) {
  let hint = null, parted = null;
  try {
    hint = text([ids.get(data.file) ?? null, data.type, data.given ?? null], true);
    parted = partsHint(ids.get(data.file), data.given);
  } catch {}   // a value JSON can't hold: nothing kept
  const [offered, parts] = await Promise.all([
    hint && dresses("readonly", (store) => store.get(hint)).catch(() => null),
    parted && partsOf(parted).catch(() => null)]);
  const reply = mounted(py, data.file, (iso) => engine({ ...data, iso, ...(offered ? { kept: offered } : {}),
                                                         ...(parts && Object.keys(parts).length ? { parts } : {}) }));
  post({ type: "reply", call: data.call, reply });
  try {
    const { made, taken } = engine({ type: "parts" });
    if (parted && (taken.length || Object.keys(made).length)) await keepParts(parted, made, taken);
  } catch {}   // parts not kept are parts worked out again
  if (!hint || "refused" in reply || reply.refusal) return;
  try {
    const kept = mounted(py, data.file, () => engine({ type: "kept" })), made = Object.keys(kept).length > 0;
    if (made || offered) await keep(hint, made ? kept : null);
  } catch {}   // a dress not kept is a dress made again
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
const DATA = ["data", "data_edit", "community"];   // the Data tab's (All files' asks mount the image) and the community list
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
  const digests = await hashedApart(data.file, rest.files, checking("Checking every file"), undefined,
                                    (where) => awaiting(`verify: ${where}`));
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
  const name = `${PREFIX}${crypto.randomUUID()}.bin`;
  let folder = null;
  try {
    const release = await new Promise((held, fail) => {
      navigator.locks.request(name, { mode: "shared" }, () => new Promise((free) => held(free))).catch(fail);
    });
    out = { name, release };
    folder = await navigator.storage.getDirectory();
    const handle = await folder.getFileHandle(name, { create: true });
    return { name, handle, sync: await handle.createSyncAccessHandle(), at: 0 };
  } catch {
    // OPFS refuses (a private window, WebKit's ephemeral contexts) or gives no sync handle to the file it made
    // (WebKit on Windows: NotSupportedError, its SharedFileHandle has no Windows form): the pieces are Blobs, no file
    await folder?.removeEntry(name).catch(() => null);
    letGo();
    return null;
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
// the next build dresses again. DRESSES hints at most, the least recently built dropped first: a hit is the newest again.
const DRESS = "azurkit-dress", DRESSES = 32, ORDER = "";
const dresses = (mode, fn) => stored(DRESS, "dress", mode, fn);
const hintOf = (file, packs, randomizer, character) => {
  try {
    return character ? text([ids.get(file) ?? null, character, packs ?? null, randomizer ?? null], true) : null;
  } catch {
    return null;   // a value JSON can't hold: nothing kept
  }
};
const keep = (hint, kept) => dresses("readwrite", (store) => {   // kept null: a hit's, only made the newest again
  const order = store.get(ORDER);
  order.onsuccess = () => {
    const hints = [...(order.result ?? []).filter((h) => h !== hint), hint];
    for (const old of hints.splice(0, Math.max(0, hints.length - DRESSES))) store.delete(old);
    store.put(hints, ORDER);
    if (kept) store.put(kept, hint);
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
        label: "Hashing the changed files", done, total, percent: total ? Math.floor(done * 100 / total) : null }))
        .catch((error) => { throw error instanceof DOMException ? new Error(CHANGED) : error; }));   // a read refused
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
  made.checks.id = ids.get(file) ?? null;   // whose files the page's vouched digests are (vouched())
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
  try {   // the dress the build worked out (none on a hit), made over the image mounted again, and kept; a hit's the newest
    const kept = mounted(py, file, () => engine({ type: "kept" })), made = Object.keys(kept).length > 0;
    if (made || offered) await keep(hint, made ? kept : null);
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
          "library", ...CHARACTER, ...TOOLS, ...DATA, ...VARIANTS].includes(data?.type)) return;
    if (data.file && typeof data.id === "string" && !ids.has(data.file)) ids.set(data.file, data.id);   // read before
    const aside = !data.file && ["content", ...CHARACTER].includes(data.type);
    if (aside && checking && !behind && loaded.numpied) return handle(data);
    if (aside) behind++;
    queue = queue.then(() => needsNumpy(data) && !loaded.numpied ? (awaiting("numpy"), numpy(loaded)) : null)
      .then(() => {
        if (!data.file) return;
        checking = true;
        return prime(loaded, data.file).catch(() => null).finally(() => { checking = false; });
      }).then(() => {
        if (aside) behind--;
        awaiting(data.type);
        return dressing(data, () => handle(data));
      }).then(() => {   // a check's rest (vouched()), once its ask is answered: work of no ask's, so never its failure
        const rest = loaded.rest;
        loaded.rest = null;
        return rest?.().catch(() => {});
      }).catch((error) => post(failure(error)));
  };
  const handle = (data) => {
    try {
      if (data.type === "warm") return void loaded.engine(data);
      if (data.type === "content") return content(loaded, data);
      if (data.type === "library") return library(loaded, data);
      if (CHARACTER.includes(data.type) || VARIANTS.includes(data.type)) {   // answered whatever happens: the page waits
        const refused = (error) => post({ type: "reply", call: data.call, reply: refusal(error) });
        try {
          return character(loaded, data)?.catch(refused);
        } catch (error) {
          return refused(error);
        }
      }
      if (data.type === "vanilla") return vanilla(loaded, data.file);
      if (TOOLS.includes(data.type)) {   // answered whatever happens: the queue waits for its hashing
        return tool(loaded, data).catch(refusal).then((reply) => post({ type: "reply", call: data.call, reply }));
      }
      if (data.type === "tracker" || data.type === "plan" || DATA.includes(data.type)) {   // answered whatever happens
        let reply;
        try {
          reply = DATA.includes(data.type) && data.file ? mounted(loaded.py, data.file, (iso) => loaded.engine({ ...data, iso }))
            : loaded.engine(data);
        } catch (error) {
          reply = refusal(error);
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
      post(failure(error));
    }
  };
  post({ type: "ready", start: loaded.start, ...(loaded.cold ? { cold: loaded.cold } : {}),
         ...loaded.engine({ type: "catalog" }) });
} catch (error) {
  post({ type: "failed", message: `AzurKit didn't load: ${located(error, null)}` });
}

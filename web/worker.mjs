// The site's engine: AzurKit's wheel under Pyodide 314 in a module worker, one worker per build (WEB §3.6). The page
// starts it from a blob: URL that imports this file, so the page's CSP holds here too (WEB §6.4). Pyodide comes from
// this site alone; the wheel, fetched with the integrity host.json gives, is unpacked without its dependencies
// (WEB §6.3). The player's image is mounted read-only (WORKERFS) and azurkit.sdk reads it and decides every output
// byte: the page gets the build as segments (WEB §3.4), spans of the image ("copy"), the bytes the build writes
// ("bytes") and zeros past the image's end ("zero"), which it joins into a Blob.
//
// One PyProxy only (Step 4.1d3): ENGINE's function, kept for the worker's life. It hands back plain JS values, so this
// file never drops a PyProxy for Pyodide's FinalizationRegistry to free later. That cleanup needs the GIL, and WebKit
// runs it inside FileReaderSync, under WORKERFS's read of the image, while CPython has released the GIL around read():
// Safari's build stopped with NoGilError there. Chromium runs it only between tasks.
//
// In:  {type: "build", file, packs: {name: {parameter: value}}}, {type: "vanilla", file}
// Out: {type: "ready", catalog, version}, {type: "built", report, size, segments}, {type: "refused", message},
//      {type: "vanilla", release, label, packs} (the image's own value of each slider at a site of its XBE)
//      (the engine's refusal, which names what and why, never game bytes), {type: "failed", message},
//      {type: "csp", directive, blocked}
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
    if request.type == "vanilla":
        try:
            return js(sdk.vanilla(request.recipe.iso))
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

async function load() {
  const site = await (await fetch(new URL("host.json", base))).json();
  const pyodide = new URL("pyodide/", base).href;
  const { loadPyodide } = await import(new URL("pyodide.mjs", pyodide).href);
  const py = await loadPyodide({
    indexURL: pyodide, lockFileURL: new URL("pyodide-lock.json", pyodide).href, packageBaseUrl: pyodide,
    stdout: () => {}, stderr: () => {},
  });
  const wheel = await fetch(new URL(site.wheel, base), { integrity: site.integrity });
  if (!wheel.ok) throw new Error(`${site.wheel}: HTTP ${wheel.status}`);
  py.unpackArchive(await wheel.arrayBuffer(), "wheel",
                   { extractDir: py.runPython("import site; site.getsitepackages()[0]") });
  return { py, engine: py.runPython(ENGINE) };
}

// The image's own values of the sliders at its XBE's sites, the image mounted only for the read: a build mounts it
// again, then this worker is replaced.
function vanilla({ py, engine }, file) {
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  try {
    const read = engine({ type: "vanilla", recipe: { iso: `/in/${file.name}` } });
    if (!("refused" in read)) post({ type: "vanilla", ...read });
  } finally {
    py.FS.unmount("/in");
  }
}

function build({ py, engine }, file, packs) {
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  const made = engine({ type: "build", recipe: { iso: `/in/${file.name}`, packs } });
  if ("refused" in made) return post({ type: "refused", message: made.refused });
  post({ type: "built", ...made }, made.segments.flatMap((s) => s.kind === "bytes" ? [s.data.buffer] : []));
}

try {
  const loaded = await load();
  self.onmessage = ({ data }) => {
    if (data?.type !== "build" && data?.type !== "vanilla") return;
    try {
      if (data.type === "vanilla") return vanilla(loaded, data.file);
      build(loaded, data.file, data.packs);
    } catch (error) {
      post({ type: "failed", message: lastLine(error) });
    }
  };
  post({ type: "ready", ...loaded.engine({ type: "catalog" }) });
} catch (error) {
  post({ type: "failed", message: `AzurKit didn't load: ${lastLine(error)}` });
}

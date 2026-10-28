// The site's engine: AzurKit's wheel under Pyodide 314 in a module worker, one worker per build (WEB §3.6). The page
// starts it from a blob: URL that imports this file, so the page's CSP holds here too (WEB §6.4). Pyodide comes from
// this site alone; the wheel, fetched with the integrity host.json gives, is unpacked without its dependencies
// (WEB §6.3). The player's image is mounted read-only (WORKERFS) and azurkit.sdk reads it and decides every output
// byte: the page gets the build as segments (WEB §3.4), spans of the image ("copy"), the bytes the build writes
// ("bytes") and zeros past the image's end ("zero"), which it joins into a Blob.
//
// In:  {type: "build", file, packs: {name: {parameter: value}}}
// Out: {type: "ready", catalog, version}, {type: "built", report, size, segments}, {type: "refused", message}
//      (the engine's refusal, which names what and why, never game bytes), {type: "failed", message},
//      {type: "csp", directive, blocked}
const base = new URL("./", import.meta.url);
const post = (message, transfer = []) => self.postMessage(message, transfer);
self.addEventListener("securitypolicyviolation", (e) =>
  post({ type: "csp", directive: e.violatedDirective, blocked: e.blockedURI }));

const lastLine = (error) => String(error?.message ?? error).trim().split("\n").at(-1);

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
  // A refusal (ValueError, OSError) comes back as its message; anything else is a failure.
  const call = py.runPython(`
def call(fn, *args):
    try:
        return fn(*args), None
    except (OSError, ValueError) as exc:
        return None, str(exc)
call`);
  return { py, call, sdk: py.pyimport("azurkit.sdk"), version: py.pyimport("azurkit").__version__ };
}

const plain = (proxy) => proxy.toJs({ dict_converter: Object.fromEntries, create_pyproxies: false });

function segments(image) {
  const out = [], transfer = [];
  for (const piece of image.segments()) {
    if (piece.type === "Copy") {
      out.push({ kind: "copy", offset: piece.offset, size: piece.size });
    } else if (piece.type === "Zero") {
      out.push({ kind: "zero", size: piece.size });
    } else {
      const view = piece.data.getBuffer("u8");
      const data = view.data.slice();
      view.release();
      out.push({ kind: "bytes", size: data.length, data });
      transfer.push(data.buffer);
    }
    piece.destroy();
  }
  return [out, transfer];
}

function build(engine, file, packs) {
  const { py, call, sdk } = engine;
  py.FS.mkdirTree("/in");
  py.FS.mount(py.FS.filesystems.WORKERFS, { files: [file] }, "/in");
  const recipe = py.toPy({ iso: `/in/${file.name}`, packs });
  const [made, refused] = call(sdk.image, recipe).toJs({ depth: 1 });
  if (refused !== undefined) return post({ type: "refused", message: refused });
  const [image, report] = made.toJs({ depth: 1 });
  const [pieces, transfer] = segments(image);
  post({ type: "built", report: plain(report), size: image.size, segments: pieces }, transfer);
}

try {
  const engine = await load();
  self.onmessage = ({ data }) => {
    if (data?.type !== "build") return;
    try {
      build(engine, data.file, data.packs);
    } catch (error) {
      post({ type: "failed", message: lastLine(error) });
    }
  };
  post({ type: "ready", catalog: plain(engine.sdk.catalog()), version: engine.version });
} catch (error) {
  post({ type: "failed", message: `AzurKit didn't load: ${lastLine(error)}` });
}

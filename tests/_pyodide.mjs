// The web tests' runner (tests/_pyodide.py): the `azurkit` command under Pyodide on Node.
//
//   node tests/_pyodide.mjs <pyodide dir> <wheel> <job JSON>
//
// The job is {"mounts": [[folder in Pyodide, folder on disk], ...], "argv": [...]}, or with "image": a recipe in
// place of "argv", and "packages": the wheels in the Pyodide folder to load first (numpy, which the site loads for a
// tab that needs it). It loads Pyodide, unpacks the wheel alone into site-packages (as the site does: no
// dependencies), loads the packages, mounts each folder (NODEFS), runs azurkit.cli.main(argv) (or sdk.image(recipe))
// and prints one JSON line: its exit code, stdout and stderr (or the image's report), and the runtime. An error is
// one line on stderr and exit 1 (Node would print the minified line it was thrown from).
import fs from "node:fs";
import { pathToFileURL } from "node:url";

process.on("uncaughtException", (e) => {
  process.stderr.write(`${e?.type ?? e?.name}: ${String(e?.message ?? e).split("\n").slice(-12).join("\n")}\n`);
  process.exit(1);
});
const [dir, wheel, job] = process.argv.slice(2);
const { loadPyodide } = await import(pathToFileURL(`${dir}/pyodide.mjs`).href);
const py = await loadPyodide({ indexURL: `${dir}/`, stdout: () => {}, stderr: (s) => process.stderr.write(`${s}\n`) });
const site = py.runPython("import site; site.getsitepackages()[0]");
py.unpackArchive(new Uint8Array(fs.readFileSync(wheel)), "wheel", { extractDir: site });
const { mounts, argv, image, packages = [] } = JSON.parse(job);
for (const name of packages) {
  await py.loadPackage(`${dir}/${name}`, { messageCallback: () => {} });
}
for (const [at, folder] of mounts) {
  py.FS.mkdirTree(at);
  py.FS.mount(py.FS.filesystems.NODEFS, { root: folder }, at);
}
py.globals.set("ARGV", JSON.stringify(argv ?? []));
py.globals.set("IMAGE", JSON.stringify(image ?? null));
console.log(py.runPython(`
import contextlib, io, json, sys
import azurkit
from azurkit import cli, sdk
out, err = io.StringIO(), io.StringIO()
report = None
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    if json.loads(IMAGE) is None:
        code = cli.main(json.loads(ARGV))
    else:
        code, report = 0, sdk.image(json.loads(IMAGE))[1]
json.dumps({"code": code, "stdout": out.getvalue(), "stderr": err.getvalue(), "report": report,
            "platform": sys.platform, "python": sys.version.split()[0], "azurkit": azurkit.__file__})
`));

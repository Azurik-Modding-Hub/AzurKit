// The web tests' runner (tests/_pyodide.py): the `azurkit` command under Pyodide on Node.
//
//   node tests/_pyodide.mjs <pyodide dir> <wheel> <job JSON>
//
// The job is {"mounts": [[folder in Pyodide, folder on disk], ...], "argv": [...]}. It loads Pyodide, unpacks the
// wheel alone into site-packages (as the site does: no dependencies), mounts each folder (NODEFS), runs
// azurkit.cli.main(argv) and prints one JSON line: its exit code, stdout and stderr, and the runtime. An error is
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
const { mounts, argv } = JSON.parse(job);
for (const [at, folder] of mounts) {
  py.FS.mkdirTree(at);
  py.FS.mount(py.FS.filesystems.NODEFS, { root: folder }, at);
}
py.globals.set("ARGV", JSON.stringify(argv));
console.log(py.runPython(`
import contextlib, io, json, sys
import azurkit
from azurkit import cli
out, err = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = cli.main(json.loads(ARGV))
json.dumps({"code": code, "stdout": out.getvalue(), "stderr": err.getvalue(), "platform": sys.platform,
            "python": sys.version.split()[0], "azurkit": azurkit.__file__})
`));

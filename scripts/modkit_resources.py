"""The models family's ``resources.json``: one hash per XBR resource of each
G3 build that wears a player model, as Modkit builds it (the plan's oracle
section, Step 4.3a1).

This program runs inside Modkit, never in AzurKit: ``scripts/oracle_sync.py``
copies it into its scratch clone of Modkit and runs it there, in Modkit's
locked environment, after Modkit's ``scripts/export_oracle.py``. AzurKit
never imports it (nor Modkit). For each case the models family's bundle
records in ``tests/goldens/pipelines.json`` and ``tests/goldens/europe/
pipelines.json``, it runs Modkit's own build of the case's recipe (G3's
spec, ``tests/test_randomize_full_golden.py``'s table, under its hash seed
0) in a child process with no ISO written, as G3's driver does
(``tests/_randomize_driver.py``), and keeps the files the build hands the
packer. Each one's sha256 must be G3's recorded one (a Europe build's XBRs
but index.xbr, the USA build's of the case, as G3 checks them), or nothing
is written (D35). Then for each changed ``.xbr`` file it records, against the
release's vanilla file read from the same image:

- ``sha256`` and ``size`` of the built file, its TOC's ``count`` and the
  vanilla file's (``vanilla_count``);
- ``changed``: each vanilla entry whose payload the build changed, as
  ``[index, tag, size, sha256]``;
- ``new``: each entry the build appended, as ``[name or null, tag, size,
  sha256, relocs]``, ``relocs`` the offsets of its relocated fields
  (Modkit's ``xbr.append.appended``);
- for ``index.xbr``, ``records``: the records the build added, as ``[key,
  archive, fourcc]``, in the order their strings follow vanilla's (the
  order the build added them).

Names, sizes, offsets and sha256s: no game bytes (D3).

    uv run --locked python scripts/<this file> OUT --bundle BUNDLE/models [--workers N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))  # for tests.* (the case table and the driver)

G3 = {"usa": "tests/goldens/pipelines.json", "europe": "tests/goldens/europe/pipelines.json"}
TIMEOUT = 600   # seconds a build, unless its spec says (booblord's 1,200)
CHILD = "--child"   # argv[1] of one build's process: then its image, its spec and its folder


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _shared(path: str) -> bool:
    """An XBR both releases hold byte for byte (all but index.xbr): G3 checks
    a Europe build's against the USA build's of the case."""
    return path.endswith(".xbr") and path != "gamedata/index/index.xbr"


def _view(vanilla: bytes, built: bytes, path: str) -> dict:
    from azurik_mod.xbr.append import appended
    from azurik_mod.xbr.toc_scan import parse_toc

    old, new = parse_toc(vanilla), parse_toc(built)
    out = {"sha256": _sha(built), "size": len(built), "count": len(new), "vanilla_count": len(old)}

    def payload(data: bytes, e) -> bytes:
        return data[e.file_offset:e.file_offset + e.size]

    out["changed"] = [[e.index, e.tag, e.size, _sha(payload(built, e))]
                      for e, v in zip(new, old) if payload(built, e) != payload(vanilla, v)]
    out["new"] = [[r.name, r.tag, len(r.payload), _sha(r.payload), list(r.relocs)]
                  for r in appended(len(old), built)]
    if path.endswith("index.xbr"):
        from azurik_mod.assets.index_xbr import _records

        had = {r.key for r, _, _ in _records(vanilla, "index.xbr")[1]}
        added = sorted((k, r) for r, k, _ in _records(built, "index.xbr")[1] if r.key not in had)
        out["records"] = [[r.key, r.archive, r.fourcc] for _, r in added]
    return out


def child(iso: str, spec: dict, job: Path) -> None:
    """Build ``spec`` from ``iso`` with no ISO written and write its files'
    hashes and resources to ``job/result.json``."""
    from unittest import mock

    from azurik_mod import cli
    from azurik_mod.iso import xiso

    handed: dict[str, bytes] = {}
    out = job / "out.iso"

    def pack(src, dest, overrides=None):
        handed.update({k: bytes(v) for k, v in (overrides or {}).items()})
        Path(dest).touch()

    def arg(value):
        if not isinstance(value, dict):
            return str(value)
        path = job / f"mod{len(list(job.glob('mod*')))}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    with mock.patch.object(xiso, "pack", pack):
        sys.argv = ["azurik-mod", *map(arg, spec["cli"]), "--iso", iso, "--output", str(out)]
        cli.main()
    files, resources = {}, {}
    with xiso.XisoReader(Path(iso)) as r:
        for path, data in sorted(handed.items()):
            files[path] = _sha(data)
            if path.endswith(".xbr"):
                vanilla = r.read_file(path)
                if vanilla != data:
                    resources[path] = _view(vanilla, data, path)
    (job / "result.json").write_text(json.dumps({"files": files, "resources": resources}), encoding="utf-8")


def _prebuild(shims: Path) -> None:
    """Every shim object a build may link, compiled once into ``shims``
    before the children start (as G3's driver does: no two compile one)."""
    import azurik_mod.patches  # noqa: F401  (registers the packs)
    from azurik_mod.patching.feature import shim_build_dir
    from azurik_mod.patching.registry import all_packs
    from azurik_mod.patching.shim_toolchain import CHECKOUT, compile_shim

    os.environ["AZURIK_SHIM_BUILD_DIR"] = str(shims)
    for pack in all_packs():
        if pack.shim is not None:
            compile_shim(pack.shim.source_path(), pack.shim.object_path(pack.name, CHECKOUT))
    for src in (CHECKOUT / "azurik_mod" / "patches" / "player_model").glob("*.c"):
        compile_shim(src, shim_build_dir(CHECKOUT) / f"player_model_{src.stem}.o")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--bundle", type=Path, required=True, help="the models family's folder export_oracle.py wrote")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", action="append", help="build only this case (repeatable; a trial run's)")
    args = ap.parse_args(argv)
    import tests.test_randomize_full_golden as g3
    from tests._xbe_fixture import EUROPE_ISO, VANILLA_ISO

    isos = {"usa": VANILLA_ISO, "europe": EUROPE_ISO}
    cases = json.loads((args.bundle / "cases.json").read_text(encoding="utf-8"))
    jobs = [(region, case) for region, rel in G3.items() for case in cases.get(rel, {})
            if not args.only or case in args.only]
    if missing := sorted({region for region, _ in jobs if isos[region] is None}):
        print(f"ERROR: no verified {', '.join(missing)} image for Modkit's builds", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="azurkit-resources-") as scratch:
        return _built(args, jobs, isos, Path(scratch), g3)


def _built(args, jobs, isos, work: Path, g3) -> int:
    _prebuild(work / "shims")
    env = {k: v for k, v in os.environ.items() if not k.startswith("AZURIK_")} | {
        "AZURIK_SHIM_BUILD_DIR": str(work / "shims"), "PYTHONHASHSEED": "0"}

    def run(n: int) -> dict:
        region, case = jobs[n]
        spec = dict(g3.CASES[case])
        limit = spec.pop("timeout", TIMEOUT)
        job = work / str(n)
        job.mkdir()
        with open(job / "log", "w", encoding="utf-8") as log:
            code = subprocess.run([sys.executable, __file__, CHILD, str(isos[region]), json.dumps(spec), str(job)],
                                  cwd=_REPO, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=limit).returncode
        if code or not (job / "result.json").exists():
            raise SystemExit(f"{region} {case}: Modkit's build failed (exit {code}):\n"
                             + (job / "log").read_text(encoding="utf-8")[-3000:])
        got = json.loads((job / "result.json").read_text(encoding="utf-8"))
        print(f"built {region} {case}", flush=True)
        return got

    order = sorted(range(len(jobs)), key=lambda n: -g3.CASES[jobs[n][1]].get("timeout", TIMEOUT))
    with ThreadPoolExecutor(args.workers) as pool:
        done = dict(zip(order, pool.map(run, order)))
    out: dict[str, dict] = {}
    goldens = {region: json.loads((args.bundle / rel).read_text(encoding="utf-8")) for region, rel in G3.items()}
    for n, (region, case) in enumerate(jobs):
        got = done[n]
        recorded = goldens[region][case] | (   # Europe's golden holds its own files; the XBRs both hold, USA's
            {} if region == "usa" else {p: sha for p, sha in goldens["usa"][case].items() if _shared(p)})
        want = {path: sha for path, sha in recorded.items() if path not in ("ISO", "filelist.txt")}
        if got["files"] != want:
            bad = sorted(p for p in want.keys() | got["files"].keys() if want.get(p) != got["files"].get(p))
            print(f"ERROR: {region} {case}: Modkit's build here isn't G3's recorded one ({', '.join(bad)})",
                  file=sys.stderr)
            return 1
        out.setdefault(G3[region], {})[case] = got["resources"]
    args.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == [CHILD]:
        child(sys.argv[2], json.loads(sys.argv[3]), Path(sys.argv[4]))
        sys.exit(0)
    sys.exit(main())

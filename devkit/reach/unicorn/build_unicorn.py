"""Build FastL3's patched libunicorn (Step R2.19a, ``devkit.reach.l3_fast``): PyPI's unicorn 2.1.4 sdist (the one
uv.lock pins, its sha256 checked), x86 only, with ``devkit/reach/unicorn/unicorn_fastl3.patch`` (each change behind its
own switch: with none set it runs as stock), into ``l3_fast.library()`` (the user cache dir's
``AzurKit/unicorn-fastl3/<the patch's sha12>``), and its x87 check flavour (Step R2.19m: the same source built with
``-DUC_X87_CHECK_BUILD``, the only one with ``UC_X87_CHECK``) into that folder's ``check/``; then checked: a process
with ``l3_fast.worker_env()`` (and ``worker_env(check=True)``) set loads it and reports unicorn's version.  The reach engine's pool (``devkit/reach/reach_engine.py --l3 fast``, the default)
uses it once it is there; without it FastL3 runs on the stock wheel (as exact, slower).  Needs cmake, ninja,
clang and patch (Xcode's command line tools and Homebrew's cmake and ninja); about a minute.  Revert: ``rm -rf``
the folder it prints.

    uv run --locked python -m devkit reach build-unicorn [--jobs 4] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from devkit.reach import l3_fast  # noqa: E402

SDIST = ("https://files.pythonhosted.org/packages/b2/1b/b4248aa8422e86de690cf8e85cf8feae4c33405a097d1ebe71570bdaa6f5/"
         "unicorn-2.1.4.tar.gz")
SDIST_SHA256 = "00567a70e323f749b419cd86bee4f9115beab7ebba32194581c090cbb7c59cff"   # uv.lock's


def build(out: Path, jobs: int) -> Path:
    """The patched library and its check flavour built in a scratch folder (removed after) and copied into ``out``
    and ``out/check``; the library's path."""
    scratch = Path(tempfile.mkdtemp(prefix="azurik-unicorn-fastl3."))
    try:
        tgz = scratch / "unicorn-2.1.4.tar.gz"
        with urllib.request.urlopen(SDIST, timeout=120) as r:
            tgz.write_bytes(r.read())
        if (got := hashlib.sha256(tgz.read_bytes()).hexdigest()) != SDIST_SHA256:
            raise SystemExit(f"the sdist's sha256 is {got[:12]}, not uv.lock's {SDIST_SHA256[:12]}")
        with tarfile.open(tgz) as t:
            t.extractall(scratch, filter="data")
        src = scratch / "unicorn-2.1.4"
        subprocess.run(["patch", "-p1", "-s", "-i", str(l3_fast.PATCH)], cwd=src, check=True)
        for flavour, dest, flags in (("build", out, []), ("build-check", out / l3_fast.CHECK,
                                                             ["-DCMAKE_C_FLAGS=-DUC_X87_CHECK_BUILD"])):
            b = scratch / flavour
            subprocess.run(["cmake", "-S", str(src / "src"), "-B", str(b), "-G", "Ninja", "-DUNICORN_ARCH=x86",
                            "-DCMAKE_BUILD_TYPE=Release", "-DUNICORN_BUILD_TESTS=OFF", *flags], check=True,
                           stdout=subprocess.DEVNULL)
            subprocess.run(["ninja", "-C", str(b), f"-j{jobs}"], check=True, stdout=subprocess.DEVNULL)
            dest.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(b / l3_fast.LIB_NAME, dest / l3_fast.LIB_NAME)
        return out / l3_fast.LIB_NAME
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="build again over a library already there")
    a = ap.parse_args(argv)
    out = l3_fast.library()
    if a.force or not all((d / l3_fast.LIB_NAME).is_file() for d in (out, out / l3_fast.CHECK)):
        build(out, a.jobs)
    got, chk = l3_fast.probe(), l3_fast.probe(check=True)
    for g, d in ((got, out), (chk, out / l3_fast.CHECK)):
        if Path(g["lib"]).resolve() != (d / l3_fast.LIB_NAME).resolve():
            raise SystemExit(f"a process with the switches set loaded {g['lib']}, not the build")
    print(json.dumps({"library": str(out), "sha12": got["sha12"], "check_sha12": chk["sha12"],
                      "unicorn": got["version"], "switches": got["switches"]}))


if __name__ == "__main__":
    main()

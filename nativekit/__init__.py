"""nativekit (dev only): builds the compiled kernels' libraries (D1009), so
neither the release build nor a player needs a compiler (AZ-045's pattern,
shimkit's).

The kernels are C99 in ``native/*.c``. :func:`build` compiles them with the
pinned zig (``ziglang`` 0.16.0, the dev group) into one library a target,
committed in ``src/azurkit/core/_native/`` (``azurkit.core.native`` loads
this platform's), every one from this machine: no float contraction (zig's
default fuses a multiply and an add, which rounds otherwise than Python),
no fast math, the target's baseline CPU (never the host's), no debug info,
stripped, so a rebuild on any machine gives the same bytes. The page's own
md5 (``native/web/md5.c``, for ``web/hasher.mjs``) is one module beside them,
``web/md5.wasm``, built the same way.

    uv run --locked python -m nativekit             # build every library
    uv run --locked python -m nativekit --check     # exit 1 when a library isn't its sources' build
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from shimkit import zig

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "native"
OUT = ROOT / "src" / "azurkit" / "core" / "_native"
FLAGS = ("-std=c99", "-O2", "-ffp-contract=off", "-fno-fast-math", "-mcpu=baseline", "-g0", "-s", "-shared",
         "-Wall", "-Werror")
SIDE = ("-fPIC", "-nostdlib", "-fvisibility=default", "-Wl,--export-dynamic")   # a side module Pyodide's ctypes loads
TARGETS = {   # the library (azurkit.core.native.TARGETS' names): zig's target and its own flags
    "macos-arm64.dylib": ("aarch64-macos", ("-Wl,-install_name,@rpath/macos-arm64.dylib",)),
    "macos-x86_64.dylib": ("x86_64-macos", ("-Wl,-install_name,@rpath/macos-x86_64.dylib",)),
    "linux-x86_64.so": ("x86_64-linux-gnu.2.17", ("-fPIC",)),
    "linux-aarch64.so": ("aarch64-linux-gnu.2.17", ("-fPIC",)),
    "windows-x86_64.dll": ("x86_64-windows-gnu", ()),
    "emscripten-wasm32.so": ("wasm32-emscripten", SIDE),
}
PAGE_OUT = ROOT / "web" / "md5.wasm"
PAGE_FLAGS = ("-std=c99", "-O2", "-mcpu=baseline", "-g0", "-s", "-Wall", "-Werror", "-nostdlib", "-fno-builtin",
              "-Wl,--no-entry")   # no libc, and exported by name: web/hasher.mjs instantiates it alone


def compile(name: str) -> bytes:
    """The library ``name`` (one of :data:`TARGETS`) zig builds from every
    source."""
    target, own = TARGETS[name]
    return _zig(name, target, (*FLAGS, *own), sorted(str(s) for s in SOURCES.glob("*.c")))


def _zig(name: str, target: str, flags: tuple[str, ...], sources: list[str]) -> bytes:
    """What zig builds of ``sources``, in a scratch folder of its own (its caches too)."""
    with tempfile.TemporaryDirectory(prefix="azurkit-nativekit-") as tmp:
        env = os.environ | {"ZIG_GLOBAL_CACHE_DIR": f"{tmp}/zig", "ZIG_LOCAL_CACHE_DIR": f"{tmp}/zig"}
        out = Path(tmp) / name
        done = subprocess.run([str(zig()), "cc", "-target", target, *flags, "-o", str(out), *sources],
                              cwd=tmp, env=env, capture_output=True, text=True, timeout=600)
        if done.returncode:
            raise RuntimeError(f"zig cc could not build {name} (exit {done.returncode}):\n{done.stderr.strip()}")
        return out.read_bytes()


def build(check: bool = False) -> list[Path]:
    """Build each library into :data:`OUT` and the page's md5 into
    :data:`PAGE_OUT` (``check``: write nothing); those that weren't their
    sources' build."""
    stale = []
    made = {OUT / name: compile(name) for name in TARGETS}
    made[PAGE_OUT] = _zig(PAGE_OUT.name, "wasm32-freestanding", PAGE_FLAGS, [str(SOURCES / "web" / "md5.c")])
    for lib, data in made.items():
        if not lib.is_file() or lib.read_bytes() != data:
            stale.append(lib)
            if not check:
                lib.parent.mkdir(parents=True, exist_ok=True)
                lib.write_bytes(data)
    return stale

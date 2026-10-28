"""shimkit (dev only): builds AzurKit's prebuilt shim objects, so neither the
site nor the app needs a compiler (AZ-045).

Each shim's C source is ``src/azurkit/tools/mods/shims/<name>.c``, and its
object ``<name>.o`` beside it, committed: :func:`build` compiles every
source with the pinned zig (``ziglang`` 0.16.0, the dev group) and Modkit's
flags, so an object's normalized sha256 is the oracle's G2 record, and a
rebuild gives the same bytes on any machine. A shim includes only the header
:func:`header` writes from the facts (``core.facts``: each game function's
name, convention and argument bytes, AZ-099), never a vendored one (Q85).

    uv run --locked python -m shimkit             # build every object
    uv run --locked python -m shimkit --check     # exit 1 when an object isn't its source's
    uv run --locked python -m shimkit --headers DIR   # write the headers a shim includes
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path

from azurkit.core import facts, gate

ROOT = Path(__file__).resolve().parent.parent
SHIMS = ROOT / "src" / "azurkit" / "tools" / "mods" / "shims"
FLAGS = (
    "-target", "x86-windows-msvc",       # i386 PE-COFF, MSVC's mangling
    "-mcpu=pentium3",                    # the Xbox's CPU: SSE, no SSE2, so double math is x87 (AZ-021)
    "-ffreestanding", "-nostdlib",       # no libc, no CRT
    "-fno-pic",                          # position-dependent code
    "-fno-stack-protector",              # no __security_cookie
    "-fno-asynchronous-unwind-tables",   # no unwind data the XBE can't use
    "-Os",
    "-fomit-frame-pointer",
    "-g0", "-mno-incremental-linker-compatible",   # no debug info, no timestamp: rebuilds are byte-identical
)
_PARAMS = {"stdcall": 0, "fastcall": 0, "thiscall": 1, "cdecl": 0}   # params past its arg bytes: thiscall's this


def zig() -> Path:
    """The pinned zig; ``RuntimeError`` when the dev group isn't installed."""
    spec = importlib.util.find_spec("ziglang")
    if spec is None or spec.origin is None:
        raise RuntimeError("the shim compiler is missing: ziglang isn't installed; `uv sync --locked` installs it")
    return Path(spec.origin).with_name("zig")


def header() -> str:
    """``azurik_vanilla.h``: a prototype for each game function in the USA
    facts, its calling convention and its argument bytes as 32-bit words,
    so C mangles it as the layout resolves it (``Function.mangled``; an
    undecorated one named so). A cdecl one leaves its arguments open; the
    facts hold no C types, so a shim that needs one casts at its call."""
    lines = ["/* azurik_vanilla.h: written by shimkit from src/azurkit/core/facts.usa.json, never by hand.",
             " * Each game function a shim may call. A build resolves each at its release's own address. */",
             "#ifndef AZURIK_VANILLA_H", "#define AZURIK_VANILLA_H", ""]
    for f in sorted(facts.of(gate.USA).functions.values(), key=lambda f: f.name):
        words = _PARAMS[f.convention] + f.arg_bytes // 4
        params = ("" if f.convention == "cdecl" else "void") if not words else ", ".join(["unsigned int"] * words)
        label = f' __asm__("{f.mangled}")' if f.undecorated else ""   # stdcall's cleanup, cdecl's name
        lines.append(f"unsigned int __attribute__(({f.convention})) {f.name}({params}){label};   /* 0x{f.va:08X} */")
    return "\n".join(lines + ["", "#endif", ""])


def compile(source: Path, out: Path | None = None) -> bytes:
    """The object zig builds from ``source`` with :data:`FLAGS`, against
    :func:`header`; written to ``out`` when given. ``RuntimeError`` carries
    the compiler's messages when it fails."""
    with tempfile.TemporaryDirectory(prefix="azurkit-shimkit-") as tmp:
        (Path(tmp) / "azurik_vanilla.h").write_text(header(), encoding="utf-8")
        obj = Path(tmp) / f"{Path(source).stem}.o"
        env = os.environ | {"ZIG_GLOBAL_CACHE_DIR": f"{tmp}/zig", "ZIG_LOCAL_CACHE_DIR": f"{tmp}/zig"}
        done = subprocess.run([str(zig()), "cc", *FLAGS, "-I", tmp, "-c", "-o", str(obj), str(source)],
                              capture_output=True, text=True, env=env, cwd=tmp)
        if done.returncode != 0:
            raise RuntimeError(f"zig cc could not compile {source} (exit {done.returncode}):\n{done.stderr.strip()}")
        data = obj.read_bytes()
    if out is not None:
        Path(out).write_bytes(data)
    return data


def build(check: bool = False) -> list[Path]:
    """Build each shim's object beside its source (``check``: write
    nothing); the objects that weren't their sources' build."""
    stale = []
    for source in sorted(SHIMS.glob("*.c")):
        obj, data = source.with_suffix(".o"), compile(source)
        if not obj.is_file() or obj.read_bytes() != data:
            stale.append(obj)
            if not check:
                obj.write_bytes(data)
    return stale

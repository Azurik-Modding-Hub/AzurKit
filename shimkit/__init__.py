"""shimkit (dev only): builds AzurKit's prebuilt shim objects, so neither the
site nor the app needs a compiler (AZ-045).

Each shim's C source is ``src/azurkit/tools/mods/shims/<name>.c``, and its
object ``<name>.o`` beside it, committed: :func:`build` compiles every
source with the pinned zig (``ziglang`` 0.16.0, the dev group) and Modkit's
flags, so an object's normalized sha256 is the oracle's G2 record, and a
rebuild gives the same bytes on any machine. A shim includes only the headers
shimkit writes from the facts, never a vendored one (Q85): :func:`header`'s
``azurik_vanilla.h`` (each game function's name, convention and argument
bytes, AZ-099, typed where :data:`TYPES` types it, with the types and the
parameter macros shims share) and :func:`kernel_header`'s
``azurik_kernel.h`` (the kernel exports in the facts); or a header of its own
beside it in ``shims/`` (``qol_memory_heap.h``).

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
# The C types of the game functions a shim calls with other than 32-bit words: (return type, parameters). The
# facts hold no C types; a wrong one changes the mangled name (its argument bytes), which the layout refuses.
TYPES = {
    "active_controller_state": ("ControllerState *", "void"),
    "cheat_owner_action": ("void", "void *owner, int action, void *scene"),
    "global_var_find_or_create": ("u32 *", "void *map, const char *name"),
    "hud_anchor": ("void", "int flags, const float *scale"),
    "hud_font": ("void *", "void"),
    "load_level_from_path": ("void", "int *scene, const char *path, const char *spot, char is_movie"),
    "player_armor_state_tick": ("void", "void *armor_mgr"),
    "run_pages_alloc": ("void *", "unsigned int size"),
    "world_text_clear": ("void", "void"),
}
# What every shim may use: fixed-width types, the active pad's state (the
# game's per-pad record: analog values 0..1, then a latch byte per button),
# and the parameters a build writes into a shim's .rdata (a FloatParam's
# float, a BytesParam's table: TrampolinePatch.floats and .tables).
PREAMBLE = """typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char i8;
typedef signed short i16;
typedef signed int i32;
typedef float f32;
typedef double f64;

typedef struct ControllerState {
    f32 left_stick_x, left_stick_y, right_stick_x, right_stick_y;   /* +0x00 */
    f32 dpad_y, dpad_x;                                              /* +0x10: X at +0x10, Y at +0x14 */
    f32 button_a, button_b, button_x, button_y, button_black, button_white;   /* +0x18 */
    f32 trigger_left, trigger_right;                                 /* +0x30 */
    f32 stick_left_click, stick_right_click, start_button, back_button;   /* +0x38 */
    u8 edge_state[12];   /* +0x48: a button's press taken, until it is let go */
} ControllerState;

#define AZURIK_FLOAT_PARAM(name, default_value) \\
    volatile const float name __attribute__((used, section(".rdata"))) = (default_value)
#define AZURIK_BYTES_PARAM(name, size) \\
    volatile const unsigned char name[size] __attribute__((used, section(".rdata"))) = {0}
"""


def zig() -> Path:
    """The pinned zig; ``RuntimeError`` when the dev group isn't installed."""
    spec = importlib.util.find_spec("ziglang")
    if spec is None or spec.origin is None:
        raise RuntimeError("the shim compiler is missing: ziglang isn't installed; `uv sync --locked` installs it")
    return Path(spec.origin).with_name("zig")


def header() -> str:
    """``azurik_vanilla.h``: :data:`PREAMBLE`, then a prototype for each
    game function in the USA facts, its calling convention and its argument
    bytes as 32-bit words (or the C types :data:`TYPES` gives it), so C
    mangles it as the layout resolves it (``Function.mangled``; an
    undecorated one named so). An untyped cdecl one leaves its arguments
    open."""
    lines = ["/* azurik_vanilla.h: written by shimkit from src/azurkit/core/facts.usa.json, never by hand.",
             " * Each game function a shim may call. A build resolves each at its release's own address. */",
             "#ifndef AZURIK_VANILLA_H", "#define AZURIK_VANILLA_H", "", PREAMBLE]
    for f in sorted(facts.of(gate.USA).functions.values(), key=lambda f: f.name):
        words = _PARAMS[f.convention] + f.arg_bytes // 4
        params = ("" if f.convention == "cdecl" else "void") if not words else ", ".join(["unsigned int"] * words)
        result, params = TYPES.get(f.name, ("unsigned int", params))
        label = f' __asm__("{f.mangled}")' if f.undecorated else ""   # stdcall's cleanup, cdecl's name
        lines.append(f"__attribute__(({f.convention})) {result} {f.name}({params}){label};   /* 0x{f.va:08X} */")
    return "\n".join(lines + ["", "#endif", ""])


def kernel_header() -> str:
    """``azurik_kernel.h``: each kernel export in the USA facts, a function
    with its convention and argument bytes as 32-bit words, or a variable
    (a 32-bit word) read through its slot (``__declspec(dllimport)``)."""
    lines = ["/* azurik_kernel.h: written by shimkit from src/azurkit/core/facts.usa.json, never by hand.",
             " * The kernel exports a shim may use, by ordinal through the game's kernel thunk table. */",
             "#ifndef AZURIK_KERNEL_H", "#define AZURIK_KERNEL_H", ""]
    for k in sorted(facts.of(gate.USA).kernel.values(), key=lambda k: k.name):
        if k.convention == "data":
            lines.append(f"__declspec(dllimport) extern unsigned int {k.name};   /* ordinal {k.ordinal} */")
        else:
            params = ", ".join(["unsigned int"] * (k.arg_bytes // 4)) or "void"
            lines.append(f"__attribute__(({k.convention})) unsigned int {k.name}({params});"
                         f"   /* ordinal {k.ordinal} */")
    return "\n".join(lines + ["", "#endif", ""])


HEADERS = {"azurik_vanilla.h": header, "azurik_kernel.h": kernel_header}


def compile(source: Path, out: Path | None = None) -> bytes:
    """The object zig builds from ``source`` with :data:`FLAGS`, against
    :data:`HEADERS`; written to ``out`` when given. ``RuntimeError`` carries
    the compiler's messages when it fails."""
    with tempfile.TemporaryDirectory(prefix="azurkit-shimkit-") as tmp:
        for name, write in HEADERS.items():
            (Path(tmp) / name).write_text(write(), encoding="utf-8")
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

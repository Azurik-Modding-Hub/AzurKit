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
PLAYER_MODEL = ROOT / "src" / "azurkit" / "tools" / "characters" / "player_model"
FOLDERS = (SHIMS, PLAYER_MODEL)   # the packs' shims; the player-model swap's, Modkit's sources the sync installs
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
    "ai_hit_handler": ("void", "void *controller, void *hit"),
    "aligned_node_offset": ("void", "void"),
    "anim_apply_translation": ("void",
                              "const float *rotation, int *anim_obj, float blend_time, unsigned char *reference_name,"
                              " float *ref_pos"),
    "anim_bone_matrix": ("void", "const float *parent_world"),
    "anim_change": ("void", "void *critter, int anim_index, int flags"),
    "anim_change_aligned": ("void",
                           "void *critter, int anim_index, void *place, void *target, void *turn, const char *node,"
                           " const char *next, float t0, float t1"),
    "anim_change_at_node": ("void", "void *critter, int anim_index, int flags, const char *node"),
    "anim_layer_fraction": ("float", "void *anim"),
    "anim_marker_box": ("void", "float *matrix, const void *marker"),
    "anim_marker_position": ("float *", "void *anim_obj, const char *name"),
    "anim_node_transform": ("void", "void *anim_obj, int index"),
    "anim_play_clip": ("void", "void *anim_obj, int handle, int flags"),
    "anim_sample_markers": ("void", "void *anim, const void *flags"),
    "apply_damage": ("void", "int entity, int kind, unsigned char caller_flag"),
    "asset_find": ("int", "const char *name, int kind, int flags"),
    "attack_anim_record_copy": ("void", "float heading, float bearing"),
    "attack_target_find": ("void", "void *critter, float facing, void *found"),
    "attack_transition_search": ("void", "void *record, float facing, float heading, int button, int flag, int cliff"),
    "button_pressed_once": ("unsigned char", "void"),
    "camera_reach": ("void", "void"),
    "camera_water_push": ("void", "void *camera"),
    "cheat_owner_action": ("void", "void *owner, int action, void *scene"),
    "collision_sweep": ("unsigned char",
                       "void *tree, void *self, int zero, const float *from, const float *to, float rxy, float rz,"
                       " unsigned mask, void *hit"),
    "critter_model_matrix": ("void", "void *critter"),
    "critter_play_fx": ("void", "void *critter, const char *key"),
    "critter_spawn": ("void *", "void *descriptor, void *world, int *flag"),
    "fall_damage_dispatch": ("unsigned char", "float fall_height, float fall_speed"),
    "font_draw_text": ("void", "const void *font, const char *text"),
    "fx_instance_detach": ("void", "void"),
    "fx_instantiate": ("void",
                      "void *handle, const char *key, void *world, unsigned cell, unsigned flags, void *bind,"
                      " unsigned zero1, unsigned zero2, unsigned zero3"),
    "glide_origin": ("float *", "const void *critter, float *out"),
    "global_var_find_or_create": ("u32 *", "void *map, const char *name"),
    "gravity_integrate_raw": ("void", "void *config, void *vel_accumulator, float gravity_dt"),
    "hit_send": ("void", "void *box, void *message"),
    "hud_anchor": ("void", "int flags, const float *scale"),
    "hud_font": ("void *", "void"),
    "hud_list_draw": ("void", "void *hud"),
    "load_level_from_path": ("void", "int *scene, const char *path, const char *spot, char is_movie"),
    "move_query_clear": ("void", "void"),
    "player_ai_factory": ("void *", "void *self"),
    "player_air_attack_start": ("unsigned char", "void *input"),
    "player_airborne_tick": ("unsigned char", "void *input"),
    "player_armor_state_tick": ("void", "void *armor_mgr"),
    "player_climb_tick": ("unsigned char", "void *input"),
    "player_ground_attack_tick": ("void", "void *pc"),
    "player_hard_land": ("void", "void *pc, void *input"),
    "player_input_tick": ("void", "int entity_input_state"),
    "player_jump_init": ("unsigned char", "void"),
    "player_land_classify": ("void", "void *input, void *result, void *query"),
    "player_move_fx": ("void", "void *frame"),
    "player_move_offsets_init": ("void", "void *critter"),
    "player_staff_wall_check": ("unsigned char", "void *player_control"),
    "quat_from_euler": ("void", "float x, float y, float z"),
    "quat_rotate": ("void", "void"),
    "run_pages_alloc": ("void *", "unsigned int size"),
    "sound_play_at": ("void", "int handle, const float *point, int unused"),
    "species_bind_clip_sounds": ("void", "int slot, const char *clip"),
    "species_clip_lookup": ("int *", "void *species"),
    "species_get_by_name": ("void *", "const char *name, int fallback"),
    "volume_query": ("void", "void *tree, const float *point, void *asker, void *flags, float *depth, int touch"),
    "wing_flap": ("unsigned char", "int *input_state"),
    "world_text_clear": ("void", "void"),
}
# The game functions that take an argument in a register a C prototype can't name: each a thunk that loads it from
# the stack and calls the function by its mangled name (Modkit's azurik_vanilla.h's ``*_call`` thunks).
THUNKS = {
    "attack_anim_record_copy_call": ("void", "void *record, int column, float heading, float bearing", (
        "movl 4(%esp), %ecx", "movl 8(%esp), %eax", "pushl 16(%esp)", "pushl 16(%esp)",
        'calll \\"_attack_anim_record_copy@8\\"', "retl $16")),
    "font_draw_text_call": ("void", "float *pen, const void *font, const char *text", (
        "pushl %esi", "movl 8(%esp), %esi", "pushl 16(%esp)", "pushl 16(%esp)", 'calll \\"_font_draw_text@8\\"',
        "popl %esi", "retl $12")),
    "fx_instance_detach_call": ("void", "void *instance", (
        "pushl %esi", "movl 8(%esp), %esi", "calll _fx_instance_detach", "popl %esi", "retl $4")),
    "player_air_attack_start_call": ("unsigned char", "void *pc, void *input", (
        "movl 4(%esp), %eax", "pushl 8(%esp)", 'calll \\"_player_air_attack_start@4\\"', "retl $8")),
    "player_jump_init_call": ("unsigned char", "void *entity, void *input", (
        "pushl %esi", "movl 8(%esp), %esi", "movl 12(%esp), %eax", "calll _player_jump_init", "popl %esi",
        "retl $8")),
    "species_bind_clip_sounds_call": ("void", "void *species, int slot, const char *clip", (
        "pushl %edi", "movl 8(%esp), %edi", "pushl 16(%esp)", "pushl 16(%esp)",
        'calll \\"_species_bind_clip_sounds@8\\"', "popl %edi", "retl $12")),
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
    for name, (result, params, body) in THUNKS.items():
        asm = "\n            ".join(f'"{line}\\n\\t"' for line in body[:-1]) + f'\n            "{body[-1]}"'
        lines += ["", "static inline __attribute__((naked, stdcall))", f"{result} {name}({params})",
                  "{", f"    __asm__({asm});", "}"]
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


def alias_header() -> str:
    """``azurik.h``, which Modkit's player-model shims include for the
    parameter macros: :func:`header`'s (no struct of Modkit's own)."""
    return "/* azurik.h: written by shimkit, never by hand: the parameter macros, azurik_vanilla.h's. */\n" \
           '#include "azurik_vanilla.h"\n'


HEADERS = {"azurik_vanilla.h": header, "azurik_kernel.h": kernel_header, "azurik.h": alias_header}


def compile(source: Path, out: Path | None = None) -> bytes:
    """The object zig builds from ``source`` with :data:`FLAGS`, against
    :data:`HEADERS`; written to ``out`` when given. ``RuntimeError`` carries
    the compiler's messages when it fails."""
    with tempfile.TemporaryDirectory(prefix="azurkit-shimkit-") as tmp:
        for name, write in HEADERS.items():
            (Path(tmp) / name).write_text(write(), encoding="utf-8")
        obj = Path(tmp) / f"{Path(source).stem}.o"
        env = os.environ | {"ZIG_GLOBAL_CACHE_DIR": f"{tmp}/zig", "ZIG_LOCAL_CACHE_DIR": f"{tmp}/zig"}
        if (filled := fill(source)) is not None:   # a table of game data, from the player's image
            (Path(tmp) / "src").mkdir()
            source = Path(tmp) / "src" / Path(source).name
            source.write_text(filled, encoding="utf-8")
        done = subprocess.run([str(zig()), "cc", *FLAGS, "-I", tmp, "-c", "-o", str(obj), str(source)],
                              capture_output=True, text=True, env=env, cwd=tmp)
        if done.returncode != 0:
            raise RuntimeError(f"zig cc could not compile {source} (exit {done.returncode}):\n{done.stderr.strip()}")
        data = obj.read_bytes()
    if out is not None:
        Path(out).write_bytes(data)
    return data


def fill(source: Path) -> str | None:
    """``source``'s text with each table of game data ``ports.HELD`` names
    for it (a callable: garret4's roll motion) filled from the player's USA
    image, which the source holds as zeros (D3): the object Modkit compiles,
    whose bytes there :func:`hold` then zeroes. ``None`` for a source with
    none. ``RuntimeError`` when the image isn't there."""
    from azurkit.tools.characters import ports

    held = ports.HELD.get(Path(source).stem, {}) if Path(source).parent == PLAYER_MODEL else {}
    tables = {name: value for name, value in held.items() if callable(value)}
    if not tables:
        return None
    if (image := gate.find(gate.USA)) is None:
        raise RuntimeError(f"{source}: its game data comes from the USA image, which isn't there (AZURKIT_ISO)")
    import re
    import struct

    text, vanilla = Path(source).read_text(encoding="utf-8"), ports.Vanilla(gate.USA, image)
    for name, value in tables.items():
        data = value(vanilla)
        floats = [format(v, ".9g") for v in struct.unpack(f"<{len(data) // 4}f", data)]
        head = re.search(rf"\b{re.escape(name.lstrip('_'))}\[(\w+)\]\[(\d+)\] = \{{", text)
        width = int(head.group(2))
        end = text.index("\n};", head.end())
        rows = [", ".join(f"{v}f" if "." in v or "e" in v else f"{v}.0f" for v in floats[k:k + width])
                for k in range(0, len(floats), width)]
        text = text[:head.end()] + "".join(f"\n    {{{row}}}," for row in rows) + text[end:]
    return text


def hold(source: Path, data: bytes) -> bytes:
    """``data``, the object built from ``source``, with each symbol
    ``ports.HELD`` names for a player-model shim's zeroed (a build writes it
    back as it lands the shim: game data, or a constant whose bytes meet a
    vanilla file's by chance); other objects as they are."""
    from azurkit.tools.characters.ports import HELD

    if Path(source).parent != PLAYER_MODEL or Path(source).stem not in HELD:
        return data
    import struct

    from azurkit.core import coff

    obj, out = coff.parse(data), bytearray(data)
    optional = struct.unpack_from("<H", data, 16)[0]
    for name, value in HELD[Path(source).stem].items():
        sym = obj.symbol(name)
        raw = struct.unpack_from("<I", data, 20 + optional + (sym.section - 1) * 40 + 20)[0]
        size = len(obj.sections[sym.section - 1].data) - sym.value if callable(value) else len(value)   # a table: its section
        out[raw + sym.value:raw + sym.value + size] = bytes(size)
    return bytes(out)


def build(check: bool = False) -> list[Path]:
    """Build each shim's object beside its source (``check``: write
    nothing); the objects that weren't their sources' build."""
    stale = []
    for source in sorted(s for folder in FOLDERS for s in folder.glob("*.c")):
        obj, data = source.with_suffix(".o"), hold(source, compile(source))
        if not obj.is_file() or obj.read_bytes() != data:
            stale.append(obj)
            if not check:
                obj.write_bytes(data)
    return stale

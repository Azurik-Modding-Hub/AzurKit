"""Dev-only model-sitting kit (Step X.45): the row families a model-swap sitting reuses, in one tested module.

Every model sitting from 2.75b to 2.105 copied the last one's drivers (2.105's: 65 files, 10,123 lines, exec'd into one
namespace with 18 names defined twice and ``capture``/``tick``/``clear_dialog`` monkeypatched), and a kit bug in the
copies became a game finding: the unchecked target HP hold that wrote into freed critters (AZ-530). This module holds
the last working version of each row family from Step 2.105's chain (its sitting's drivers: s105 over 2.104's
s104, s103, s98 and the 2.75 helpers), once each, on ``devkit/xemu/sitting.py``'s
``Sitting`` (its watcher, quiet loads, checked target hold and guest-string reader)::

    from devkit.xemu.sittings import model_kit as mk      # a driver, in the serve
    k = mk.kit(s)                                     # one per sitting: its pictures' hashes, the spots it recorded
    k.row_zip("C0-zip", "usa", "6989c84e96eb", pics=False, cast=True)     # f3's zipline set, the camera per tick
    k.row_ladder("C0-brk", "usa", "6989c84e96eb", cast=True)              # a1's ladder over the top and jumped off
    k.row_combo("C0-chk-e7", "usa", "6989c84e96eb", runs_n=4)             # e7's combo, the targets' HP checked
    k.row_sentinel("C0-sent", "usa", "6989c84e96eb", drs=((3.6, 1),), press=False)   # f6's lone blaze sentinel
    k.row_frame("GO-frame", iso, sha12, frame=mk.frame_body(characters_xbr, "golem"), s=2.111)   # Step 2.107: the
    #   frame scored per tick at f6, a1, f3 and w1 (results/frames.jsonl); k.row_swim(...) w1's ocean alone

    uv run --locked python -m devkit.xemu.sittings.model_kit selftest     # offline: one fake row (no xemu)

A row runs in the last row's xemu process unless a relaunch is due (Step X.96: its boot restores its state from an
in-memory checkpoint or loads it; a lost process, a guest bugcheck, a hung advance, a wall-clock boot or a rate row
relaunches), the build booted (``iso``: "usa", "europe" or a build ISO's path; ``sha``: its
sha256[:12], checked), its steps (an error costs the step, not the row), then one ``results/runs.jsonl`` row. Rows run
watched (``Sitting.watch``): a lost player tick ends the row with its census and one EIP sample, no hint loops. Every
VA is USA's and goes through the sitting's region map (``Sitting._va``: an unmapped one raises on Europe, never a USA
fallback). Readers return offsets (from the body centre or the cable point), distances, ticks, levels and VAs; spots
come from the D98 states at run time (``Sitting.record_spot``) and stay in memory, per-tick traces in the sitting's
private folder (0600); strings read from the guest are known names or sha12s. A kit fix found in a sitting goes into
this module in that step's record commit, never into a per-step override. Dev only (devkit, Step 4.14a3), never a
player's verb; pytest runs only its offline ``selftest`` (``tests/test_xemu_harness.py``, marked ``xemu``), which
launches no xemu (D11).
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
import re
import struct
import sys
import time
import tomllib
from collections import Counter
from pathlib import Path

from azurkit.tools.randomizer.live import recipes
from devkit.xemu import oracle as xo
from devkit.xemu import shim_ranges

# --- USA VAs (each through Sitting._va at its use) --------------------------------------------------------------------
SETTER = 0x8BDB0                 # the move-state setter (EAX entity, ECX state, [esp+4] anim)
APPLY_DAMAGE = 0x44640           # stdcall(critter, new_hp, flag)
HIT_T3, DMG_QUERY, CMM = 0x4323C, 0x460B0, 0x42200   # a hit's target (EDX) and record (EBX); a damage query; a draw
#   (0x4323C is the hit routine's first gate, so a hit there may deal nothing: it returns while the target's hit timer
#   +0x1E0 is positive, which 0x43591 sets to the damage type's Delay after a hit that dealt damage; Step 2.123)
STAFF_CLANK = 0x8CC21            # player_staff_wall_check's sweep hit: the move ends with no damage pass
HIT_STORE, HT_SET, HT_DONE = 0x43584, 0x43591, 0x43597   # the hit routine's Delay load and +0x1E4 store (X31's CALL on
#   a build with it), its FSTP of the target's window +0x1E0 (EAX the record, EDX the target, +0x1E4 already written),
#   and the instruction after it (Step 2.126)
STAFF_ENDS = 0x8CB52             # player_staff_wall_check with this tick's two sampled ends stored (the globals below)
STAFF_TIP, STAFF_BUTT = 0x38DFE4, 0x38DFD8   # the staff node's world row 3 + 0.9 x row 0, and - 0.95 x row 0
LEVEL_FN, LVL_AT = 0x30BD0, 0x30C26                  # the hit-level chooser, and after its light-hit compare (X18)
SEARCH_AT, ROW_AT, ROW_NONE = 0x7EF85, 0x7F1A8, 0x7F18B   # the transition search's result, its row, no row
FIND_AT, RAD_OP = 0x7EBB0, 0x7EDA4   # attack_target_find's entry; the instruction whose float operand is its radius
CAM_UPD, PT2_AT = 0x81277, 0x8129C   # the level camera's update after its target's point; where X20's CALL returns
SW1, SW2, SW_D71, SW_C3A, STICK_AT = 0x81066, 0x810F8, 0x80D71, 0x80C3A, 0x81952   # the camera's sweeps; the stick
SWEEP_FN = 0x60870               # collision_sweep (stdcall 36)
GLIDE_WRAP = 0x1A26C8            # 0x42070: an aligned move's clip fraction under this wraps (+1)
PLATFORM_VT = 0x19C810           # a moving platform's vtable (a hit's source)
ZIP, LADDER, KEYLORD, SENTINEL = ("vanilla-rz-f3-zipline", "vanilla-rz-a1-ladder", "vanilla-rz-e7-keylord",
                                  "vanilla-enemy")   # the D98 states whose spots the rows use
FLAT_SPOT, WALL_SPOT, OCEAN, BEACH = "vanilla-flat", "vanilla-wall", "vanilla-ocean", "vanilla-beach-shield5"
SAME_STATE = "combo-start"   # the in-memory checkpoint a same-state combo row's runs start from (Step 2.189a)
LADDER_JUMP = 66   # a1's jump-off climb tick (AZ-540): from 60 the landing meets the game's hard-landing speed test
#                    (7.539 m/s) by 1.4 mm/s and lands either way, vanilla too; 66 falls 39-40 ticks, hard by 0.3 m/s
# the frame's reads (Step 2.107, D280): the matrices the player is drawn with, X8's point and the water push
VIEW_M, PROJ_M, WORLD_M = 0x387890, 0x389B00, 0x387B00   # the view, projection and drawn object's world (4x4 f32)
DRAW_AT = {0x3F075: 0x18, 0x3E887: 0x8}  # a critter's draw (the critter at [esp + this]): the three matrices hold its own
CAM_PT_RET, CAM_PUSH_RET = 0x41F6C, 0x81EC0   # X8's point returned (EDI the critter, it at [esp+0x18]); the water push
NEAR = 0.11                              # the near plane (0x198414), m
LEVELS = {"f6": "levels/fire/f6", "a1": "levels/air/a1", "f3": "levels/fire/f3", "w1": "levels/water/w1",
          "e2": "levels/earth/e2"}
COST_LEVELS, COST_PHASES = ("a1", "w1", "e2"), ("idle", "turn", "run_stop", "attack")   # row_cost's scenes (Step 2.173)
COST_N, COST_SETTLE, RATE_N = 300, 30, 600   # vblanks a cost phase, player ticks settled after a load, vblanks a rate
BONES_N = {"usa": 122, "T6": 89, "KL": 66, "KKS": 41, "GO": 41}   # bones read per body (2.103-2.105's); else none
RADIUS = {"keylord": 0.7, "overlord": 0.4375, "blaze_sentinel": 1.0, "rock_shard": 1.0}   # collisionRadius x scale
COLS = ['basic1', 'basic2', 'basic3', 'finish', 'finish2', 'finish3', 'sweep1', 'sweep2', 'sweep ledge', 'elemental1',
        'elemental2', 'elemental3', 'hose_attack_3', 'jump attack', 'right1', 'right2', 'left1', 'left2', 'back1',
        'back2', 'roll forward', 'up1', 'up2', 'down']
_SPECIES = re.compile(r"[a-z][a-z0-9_]*")   # a species read from the guest counts only as a name
WORDS = (("x29_swaps", "PUSH", "_player_model_push_swaps", 0), ("x8_under", "EYE", "_player_model_swim_under", 0),
         ("b2_holds", "REGROW", "_player_model_regrow_holds", 0),
         *((f"r1_{name}", "LATCH", "_player_model_push_hold", off) for name, off in (
             ("base_p", 0x00), ("base_d", 0x04), ("last_p", 0x08), ("last_d", 0x0C), ("camera", 0x10),
             ("held", 0x14), ("snap", 0x18), ("off", 0x20), ("restores", 0x24), ("acts", 0x28), ("inband", 0x2C),
             ("snaps", 0x30), ("easing", 0x34))),
         ("x41_steps", "JIGGLE", "_player_model_jiggle_steps", 0), ("x41_resets", "JIGGLE", "_player_model_jiggle_resets", 0),
         ("x41_build", "JIGGLE", "_player_model_jiggle_build", 0))
"""The shim words a camera row reads per tick, each (key, hook, symbol, offset): X29's swap count and X8's swim side
(Step 2.116b), B2's regrow holds in X19's regrow landing (Step 2.116d), and R1's hold in X29's latch landing (Step
2.116e: its base and last pitch and distance as their float bits, which the scorer decodes, the camera, the held bits, 1
the pitch and 2 the distance, the snap, off on a call that held off, the calls that wrote back, whose push acted and that
held off, the snaps, easing). ``r1_acts`` is the push's own act on a lane build, read from the shim, not the kit's band
test (which a row files a tick early: the Step 2.116e design's 1d). X41's (Step 2.156): its steps and resets and the anim
it jiggled last (0 when the build it saw wasn't the player's: the sitting's R13); its shown offsets are ``jiggle_now``'s."""
JIGGLE_SHOWN = "_player_model_jiggle_shown"
"""X41's per-row shown offsets (Step 2.156): ``jiggle_rt.SHOWN_SIZE`` bytes a row, the offset (mm as drawn: side,
forward, up), roll and yaw (rad), the raw radius over the travel (f32 each), the clock (f64) and the squash's scales
along side, forward, up (f32 each, D481)."""
JIGGLE_ROWS = "_player_model_jiggle_bones"   # X41's table: +4 its row count


def shim_words(xbe: bytes) -> dict[str, int]:
    """Each :data:`WORDS` entry's VA in the build ``xbe`` (either release), found by its hook's CALL and its shim's
    relocations; a word whose hook the build doesn't carry is left out ({} for the vanilla image)."""
    from azurkit.tools.characters import _player_character as pc
    from azurkit.tools.characters.ports import trampoline_symbol_va, verify_trampoline_patch
    hooks = {"PUSH": (pc.PUSH_HOOK, pc.PUSH_SHIM), "EYE": (pc.EYE_HOOK, pc.EYE_SHIM),
             "REGROW": (pc.EYE_REGROW_HOOK, pc.EYE_SWEEP_SHIM), "LATCH": (pc.LATCH_HOOK, pc.PUSH_SHIM),
             "JIGGLE": (pc.JIGGLE_HOOK, pc.JIGGLE_SHIM)}
    with shim_ranges.building(xbe):
        return {key: trampoline_symbol_va(xbe, hooks[h][0], sym, shim_source=hooks[h][1].source_path()) + off
                for key, h, sym, off in WORDS if verify_trampoline_patch(xbe, hooks[h][0]) == "applied"}


def sets_at(xbe: bytes) -> tuple[int, int] | None:
    """X36's state VA in the build ``xbe`` (either release; its first int the set WHITE selected, 0 the game's combo)
    and its set count (the sets map's first byte), or ``None`` without X36 (Step 2.189a)."""
    from azurkit.core.xbe import resolve_va_to_file
    from azurkit.tools.characters import _player_character as pc
    from azurkit.tools.characters.ports import trampoline_symbol_va, verify_trampoline_patch
    hook = pc.SETS_HOOKS[0]
    with shim_ranges.building(xbe):
        if verify_trampoline_patch(xbe, hook) != "applied":
            return None
        va = lambda sym: trampoline_symbol_va(xbe, hook, sym, shim_source=pc.SETS_SHIM.source_path())  # noqa: E731
        return va(pc.SETS_STATE), xbe[resolve_va_to_file(xbe, va(pc.SETS_MAP.symbol))]


def jiggle_at(xbe: bytes) -> tuple[int, int] | None:
    """X41's shown words' VA and its row count in the build ``xbe`` (either release), or ``None`` without X41."""
    from azurkit.core.xbe import resolve_va_to_file
    from azurkit.tools.characters import _player_character as pc
    from azurkit.tools.characters.ports import trampoline_symbol_va, verify_trampoline_patch
    with shim_ranges.building(xbe):
        if verify_trampoline_patch(xbe, pc.JIGGLE_HOOK) != "applied":
            return None
        va = lambda sym: trampoline_symbol_va(xbe, pc.JIGGLE_HOOK, sym, shim_source=pc.JIGGLE_SHIM.source_path())
        at = resolve_va_to_file(xbe, va(JIGGLE_ROWS))
        return va(JIGGLE_SHOWN), struct.unpack_from("<I", xbe, at + 4)[0]


def jiggle_metric(rows: list[dict]) -> dict:
    """Per X41 row over capture ``rows`` (each tick's ``x["jg"]``, ``Kit.jiggle_now``'s): its peak radius and per axis
    (mm), the largest move in a tick and how many ticks moved over 10 mm (the AZ-648 metric), its extrema along up and
    forward over 5 mm, and the raw radius's largest (over the travel). Numbers only."""
    series = [r["x"]["jg"] for r in rows if r.get("x", {}).get("jg")]
    out = {}
    for n in range(max((len(s_) for s_ in series), default=0)):
        offs = [s_[n][:3] for s_ in series if len(s_) > n]
        moves = [math.dist(a, b) for a, b in zip(offs, offs[1:])]
        ext = {}
        for ax, name in ((2, "up"), (1, "fwd")):
            v = [o[ax] for o in offs]
            ext[name] = [round(v[i], 1) for i in range(1, len(v) - 1)
                         if (v[i] - v[i - 1]) * (v[i + 1] - v[i]) < 0 and abs(v[i]) > 5.0]
        out[n] = {"ticks": len(offs), "peak_mm": round(max((math.sqrt(sum(c * c for c in o)) for o in offs), default=0.0), 1),
                  "peak_axes_mm": [round(max((abs(o[i]) for o in offs), default=0.0), 1) for i in range(3)],
                  "largest_tick_mm": round(max(moves, default=0.0), 1), "ticks_over_10mm": sum(d > 10.0 for d in moves),
                  "extrema": ext, "raw_max": round(max((s_[n][5] for s_ in series if len(s_) > n), default=0.0), 2)}
    return out


def _png_rows(raw: bytes, w: int, h: int, bpp: int) -> list[bytearray]:
    """A PNG's scanlines unfiltered (types 0-4)."""
    out, prev, stride, at = [], bytearray(w * bpp), w * bpp, 0
    for _ in range(h):
        f, line = raw[at], bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif f == 4:
                pa, pb, pc_ = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc_ else b if pb <= pc_ else c)) & 0xFF
        out.append(line)
        prev = line
    return out


def read_png(path: Path) -> tuple[int, int, list[bytearray]]:
    """An 8-bit RGB or RGBA PNG (xemu's screendumps) as its width, height and RGB scanlines."""
    data, at, idat, w = path.read_bytes(), 8, b"", 0
    while at < len(data):
        n, kind = struct.unpack_from(">I4s", data, at)
        body = data[at + 8:at + 8 + n]
        if kind == b"IHDR":
            w, h, depth, colour = struct.unpack_from(">IIBB", body)
            if depth != 8 or colour not in (2, 6):
                raise ValueError(f"{path.name}: an 8-bit RGB(A) PNG is read, not depth {depth} colour {colour}")
            bpp = 3 if colour == 2 else 4
        elif kind == b"IDAT":
            idat += body
        at += 12 + n
    lines = _png_rows(__import__("zlib").decompress(idat), w, h, bpp)
    return w, h, [line if bpp == 3 else bytearray(b for i, b in enumerate(line) if i % 4 != 3) for line in lines]


def write_png(path: Path, w: int, h: int, lines: list[bytearray]) -> None:
    """RGB scanlines as an 8-bit PNG (filter 0)."""
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + bytes(line) for line in lines)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def contact_sheet(out: Path, frames: list[Path], series: list[list[float]] | None = None, plot_h: int = 96,
                  beside: list[Path] | None = None) -> dict:
    """``frames`` (the same size) side by side in one PNG, ``beside``'s under them (the control's, MB beside RT), and
    under both ``series`` (per curve its values a frame, mm) plotted against 0 at the plot's middle, its scale the
    largest |value|; returns the sheet's size and the plot's scale (mm a pixel). Pictures of the game: evidence only."""
    rows_of = [list(frames)] + ([list(beside)] if beside else [])
    imgs = [[read_png(p) for p in r] for r in rows_of]
    w, h = imgs[0][0][0], imgs[0][0][1]
    gap = 4
    W = len(frames) * w + (len(frames) - 1) * gap
    lines: list[bytearray] = []
    for r in imgs:
        for y in range(h):
            line = bytearray()
            for i, (_, _, ls) in enumerate(r):
                line += ls[y] + (bytes([255] * 3 * gap) if i < len(r) - 1 else b"")
            line += bytes([255] * 3 * (W - len(line) // 3))
            lines.append(line)
        lines += [bytearray([255] * 3 * W) for _ in range(gap)]
    scale = 0.0
    if series:
        top = max((abs(v) for c in series for v in c), default=0.0) or 1.0
        scale = top / (plot_h / 2 - 2)
        plot = [bytearray([255] * 3 * W) for _ in range(plot_h)]
        for x in range(W):
            plot[plot_h // 2][3 * x:3 * x + 3] = b"\xc0\xc0\xc0"
        colours = (b"\xd0\x30\x30", b"\x30\x60\xd0", b"\x20\x90\x40")
        for ci, curve in enumerate(series):
            for i, v in enumerate(curve):
                x = min(W - 1, int((i + 0.5) * (w + gap)) if len(curve) == len(frames) else int(i * (W - 1) / max(1, len(curve) - 1)))
                y = max(0, min(plot_h - 1, plot_h // 2 - int(round(v / scale))))
                for dy in (-1, 0, 1):
                    yy = min(plot_h - 1, max(0, y + dy))
                    plot[yy][3 * x:3 * x + 3] = colours[ci % 3]
        lines += plot
    write_png(out, W, len(lines), lines)
    return {"sheet": out.name, "frames": len(frames), "beside": len(beside or []), "size": [W, len(lines)],
            "mm_per_px": round(scale, 3)}


_KITS: dict[int, "Kit"] = {}


def phase_lines(phase: str, n: int = COST_N, a: int | None = None) -> list[str]:
    """A cost phase's pipe lines over ``n`` vblanks, each ``+k`` from its start (Step 2.173; ``play_recording``'s), the
    pad let go at its last vblank: idle none (the body's idle clip and jiggle); turn the left stick swept -1..1 across
    (a line every 10 vblanks: the camera sees every side of the body); run_stop the stick forward 60 vblanks, let go
    90, twice in 300 (the stop's jiggle, D584); attack A (scancode ``a``) held 4 vblanks in every 12 (row_combo's A
    every 6 ticks: the body's attack chain, its spin or weapon, D592)."""
    if phase == "idle":
        return []
    if phase == "turn":
        body = [f"+{k} axis lx {xo.pipe_axis(-1 + 2 * k / n):.6f}" for k in range(0, n - 1, 10)]
    elif phase == "run_stop":
        body = [f"+{k + d} axis ly {xo.pipe_axis(v):.6f}" for k in range(0, n - 1, 150)
                for d, v in ((0, 1.0), (60, 0.0)) if k + d < n - 1]
    elif phase == "attack":
        if a is None:
            raise ValueError("phase_lines: attack needs A's scancode (sb.code('a'))")
        body = [ln for k in range(0, n - 5, 12) for ln in (f"+{k} down {a}", f"+{k + 4} up {a}")]
    else:
        raise ValueError(f"phase_lines: {phase!r} is none of {COST_PHASES}")
    return body + [f"+{n - 1} clear"]


def cost_scenes(x) -> list[dict]:
    """A control for ``xo.frame_warning``: a ``row_cost`` row (its ``frame_cost``), a ``frame_cost`` dict, its
    ``scenes`` or a list of any of them (several boots), as a list of ``{label: frame_cost}``: only its scenes (a row
    whose boot failed has no ``frame_cost``, so none)."""
    if isinstance(x, list):
        return [sc for y in x for sc in cost_scenes(y)]
    x = x.get("frame_cost", x)
    sc = x.get("scenes", x)
    return [{k: v for k, v in sc.items() if isinstance(v, dict) and "kinds" in v}]


def boot_load(sb, tag: str, res: dict) -> str:
    """How ``Kit.boot`` loaded a row (the fork's item 7, Step X.68): the state, its drive and the guest RAM
    (``[sys] mem_limit``), and boot_build's reset into the disc, or its warm state saved in this sandbox."""
    st = sb.st
    drive = f"a private drive ({Path(st['hdd']).name})" if st.get("hdd") else "a clone of the D98 drive"
    try:
        mem = (tomllib.loads((Path(sb.w) / "xemu.toml").read_text(encoding="utf-8")).get("sys") or {}).get("mem_limit")
    except (AttributeError, TypeError, OSError, tomllib.TOMLDecodeError):
        mem = None
    at = f" at {mem} MiB" if mem else ""
    if res.get("warm_drive"):   # Step X.81d: another sandbox of the sitting booted it cold and shared it
        return (f"state b-{res.get('iso_sha12')}-{tag} on the sitting's warm drive {res['warm_drive']}{at}: the "
                f"build's own, saved at its first boot_build from {tag} in a sandbox of this sitting")
    if res.get("warm"):
        return (f"state b-{res.get('iso_sha12')}-{tag} on {drive}{at}: the build's own, saved at its first "
                f"boot_build from {tag} in this sandbox")
    return f"state {tag} on {drive}{at}, then boot_build: a reset into the disc, SaveGame #1, its first steady tick"


def run_how(row: dict, scene: str) -> dict:
    """How ``row`` (a ``Kit.row``) reached ``scene`` (the fork's item 7, Step X.68): ``{binary, load, reached}``, the
    xemu binary's sha256[:12] and the load (its boot's: ``boot_load``, or a driver's own boot's ``load``, its cold
    boot's recipe), ``xo.NOT_RECORDED`` in an older row (its draft refused); ``reached`` "warp levels/..." where the
    row warped to the scene's level, else "state" (the loaded save's own level)."""
    boot, lv = row.get("boot") or {}, scene.split("/")[0]
    return {"binary": boot.get("binary") or xo.NOT_RECORDED, "load": boot.get("load") or xo.NOT_RECORDED,
            "reached": f"warp {LEVELS.get(lv, lv)}" if f"warp_{lv}" in row
            else f"state ({lv}, the loaded save's level; no warp)"}


def kit(s) -> "Kit":
    """The sitting's kit (one per ``Sitting``: its pictures' hashes and spots carry across driver requests)."""
    return _KITS.setdefault(id(s), Kit(s))


def _f1(sb, va: int) -> float:
    return struct.unpack("<f", sb.read(va, 4))[0]


def _v3(sb, va: int) -> tuple:
    return struct.unpack("<3f", sb.read(va, 12))


def _rel(a, b, n: int = 4) -> list:
    return [round(x - y, n) for x, y in zip(a, b)]


def _cam_yaw(sb) -> float:
    """The camera's yaw at the player tick (the input state EAX points at, +0x10)."""
    return struct.unpack("<f", sb.read(sb.g.regs()["eax"] + 0x10, 4))[0]


def steer(a: float, plan):
    """An on_tick: the stick, camera-relative, so the body heads along game angle ``a`` on the ground or in the air;
    ``plan(k, state)`` -> None (rest), "steer", or (lx, ly) given straight (on a ladder)."""
    def f(sb, row, rows):
        want = plan(row["k"], row["state"])
        if want is None:
            lx, ly = 0.0, 0.0
        elif want == "steer":
            d = a - _cam_yaw(sb)
            lx, ly = -math.sin(d), math.cos(d)
        else:
            lx, ly = want
        return [f"axis lx {lx:.3f}", f"axis ly {ly:.3f}"]
    return f


def runs(rows: list[dict]) -> list[dict]:
    """Run-length phases: (k0, ticks, state, anim, the anim slot's clip handle index, baked)."""
    out = []
    for r in rows:
        x = r.get("x") or {}
        k = (r.get("state"), x.get("anim"), x.get("slot_h"))
        if out and out[-1]["key"] == k:
            out[-1]["ticks"] += 1
        else:
            out.append({"key": k, "k0": r["k"], "ticks": 1})
    return [{"k0": o["k0"], "ticks": o["ticks"], "state": hex(o["key"][0] or 0), "anim": o["key"][1],
             "slot_i": (o["key"][2] - 0x100000) if o["key"][2] and o["key"][2] >= 0x100000 else o["key"][2],
             "baked": _baked(o["key"][2])} for o in out]


def _baked(h) -> bool:
    return bool(h) and 0x100000 <= h < 0x110000 and (h - 0x100000) >= 3394   # past vanilla's characters.xbr TOC


def _phases(rows: list[dict], n: int) -> list:
    return [(p["state"], p["anim"], p["ticks"]) for p in runs(rows)][:n]


def i_letgo(rows: list[dict]) -> int | None:
    """The first row out of the ride (state 5)."""
    return next((j for j in range(1, len(rows)) if rows[j - 1]["state"] == 5 and rows[j]["state"] != 5), None)


def steps_from(rows: list[dict], i0: int, n: int = 26) -> dict:
    """From row ``i0`` on: the drawn origin's offset against the centre (``od``, else +0x1B0) per tick and its step
    between ticks; the largest step; the ticks until the offset holds within 0.01 m of the last airborne one (the
    stance)."""
    seq = [(rows[j]["k"], rows[j]["state"], rows[j]["x"].get("od", rows[j]["x"]["o0"]))
           for j in range(i0, min(i0 + n, len(rows)))]
    st = [round(math.dist(a[2], b[2]), 3) for a, b in zip(seq, seq[1:])]
    air = [q for q in seq[1:] if q[1] == 2]
    fin = air[-1][2] if air else seq[-1][2]
    j_st = next((j for j, q in enumerate(seq[1:], 1) if math.dist(q[2], fin) < 0.01), None)
    return {"o0_dz": [round(q[2][2], 3) for q in seq], "states": [hex(q[1]) for q in seq], "steps": st,
            "max_step": max(st) if st else None, "stance_ticks": j_st, "stance_dz": round(fin[2], 3)}


def zip_summary(rows: list[dict]) -> dict:
    """The zipline's phases from the cable point (PC+0x44): hang_start's ticks and anims, where its glide ends against
    the cable, then the ride's first 30 ticks (origin against the cable, the step across hang_start -> ride)."""
    st = [r["state"] for r in rows]
    i0 = next((i for i, x in enumerate(st) if x == 0x105), None)
    if i0 is None:
        return {"hang": False, "states": sorted({hex(x) for x in st})}
    j = i0
    while j < len(st) and st[j] == 0x105:
        j += 1
    last = rows[j - 1]["x"]
    out = {"hang": True, "hang_start_ticks": j - i0, "after": hex(st[j]) if j < len(st) else None,
           "hang_anims": sorted({r["x"]["anim"] for r in rows[i0:j]}),
           "end_dz": round(last["o1"][2] - last["cab"][2], 3),
           "end_dxy": round(math.hypot(last["o1"][0] - last["cab"][0], last["o1"][1] - last["cab"][1]), 3),
           "o0_end_dz": round(last["o0"][2] - last["cab"][2], 3)}
    ride = [r for r in rows[j:] if r["state"] == 5][:30]
    if ride:
        dz = [r["x"]["o0"][2] - r["x"]["cab"][2] for r in ride]
        dxy = [math.hypot(r["x"]["o0"][0] - r["x"]["cab"][0], r["x"]["o0"][1] - r["x"]["cab"][1]) for r in ride]
        c_a, c_b = rows[j - 1]["c"], ride[0]["c"]   # the origin's world step: (o0 - centre) + centre, the centres' change
        step_z = (ride[0]["x"]["o0"][2] + c_b[2]) - (last["o1"][2] + c_a[2])
        out.update(ride_ticks=len([r for r in rows[j:] if r["state"] == 5]), ride_anims=sorted({r["x"]["anim"] for r in ride}),
                   ride_modes=sorted({r["x"]["mode"] for r in ride}),
                   ride_dz=[round(min(dz), 3), round(max(dz), 3)], ride_dz_first=round(dz[0], 3),
                   ride_dxy=[round(min(dxy), 3), round(max(dxy), 3)], step_z=round(step_z, 3),
                   o0_ride_vs_centre_dz=[round(min(r["x"]["o0"][2] for r in ride), 3),
                                         round(max(r["x"]["o0"][2] for r in ride), 3)])
    return out


def reversals(ds: list[float], tol: float = 0.01) -> int:
    """The camera distance's reversals over ``ds`` (per tick): a move counts once it runs ``tol`` m from the last
    extreme, so the regrow's sub-centimetre creep against a wall's face (X25's NOP at rest) isn't one (Step 2.107)."""
    n, d, ext = 0, 0, None
    for v in ds:
        if ext is None or d and (v - ext) * d > 0:   # the first, or on in the same direction: the new extreme
            ext = v
        elif abs(v - ext) >= tol:                    # a move of tol from the extreme: the first one or a turn
            n, d, ext = n + (d != 0), (1 if v > ext else -1), v
    return n


def cam_judge(per_tick: list[dict], rows: list[dict], sel) -> dict:
    """Over the ticks ``sel(k)`` picks: the point's height over the centre after X20 (min, max, ticks under it), the
    ticks X20 raised it, the camera's distance (min, max, ticks under 1.5 m) and pitch, the sweep ticks with AL set
    at 0x81066, 0x810F8 (the player's), 0x80D71, 0x80C3A, and the glide end o1's height."""
    byk = {r["k"]: r for r in rows}
    L = [o for o in per_tick if sel(o["k"]) and o.get("act2_dist") is not None]
    if not L:
        return {"n": 0}

    def mm(f):
        return [round(min(f(o) for o in L), 3), round(max(f(o) for o in L), 3)]
    return {"n": len(L), "aim2_dc": mm(lambda o: o["aim2_min"]), "under_centre": sum(1 for o in L if o["aim2_min"] < -0.001),
            "x20_raised": sum(1 for o in L if o.get("aim_dc") is not None and o["aim2_dc"] > o["aim_dc"] + 0.001),
            "act2_dist": mm(lambda o: o["act2_min"]), "collapsed": sum(1 for o in L if o["act2_min"] < 1.5),
            "act2_pitch": mm(lambda o: o["act2_pitch"]),
            "sw_ticks": {"81066": sum(1 for o in L if any(o.get("sw1") or [])),
                         "810F8": sum(1 for o in L if any(a for a, _f, mine in (o.get("sw2") or []) if mine)),
                         "80D71": sum(1 for o in L if any(o.get("d71") or [])),
                         "80C3A": sum(1 for o in L if any(o.get("c3a") or []))},
            "o1_dz": mm(lambda o: (byk[o["k"]]["x"].get("o1") or [0, 0, 0])[2])}


def segs(rows: list[dict]) -> list[dict]:
    """State-0x100 runs split where the column or anim changes or the clip restarts (its fraction falls by > 0.2: a
    replay of the same move), so a basic1 that replays basic1 shows as two swings."""
    out, cur, prev = [], None, None
    for r in rows:
        x = r["x"]
        if r["state"] != 0x100:
            cur, prev = None, None
            continue
        restart = prev is not None and x["frac"] < prev - 0.2
        if cur is None or (x["col"], x["anim"]) != cur["key"] or restart:
            cur = {"key": (x["col"], x["anim"]), "k0": r["k"], "ticks": 0, "contig": cur is not None}
            out.append(cur)
        cur["ticks"] += 1
        prev = x["frac"]
    return out


def stun_runs(rows: list[dict], cands: dict) -> dict:
    """Per candidate: its stun bit's runs (ticks) over the capture."""
    out = {}
    for t, sp in cands.items():
        runs_, cur = [], 0
        for r in rows:
            v = (r["x"].get("tg") or {}).get(hex(t))
            if v and v[0]:
                cur += 1
            elif cur:
                runs_.append(cur)
                cur = 0
        if cur:
            runs_.append(cur)
        if runs_:
            out[f"{sp}@{hex(t)[-4:]}"] = runs_
    return out


def judge_swings(sw: list[dict], finds: dict) -> list[dict]:
    """Per swing: +0xFC, its first damage tick, its chain tick, the last search inside it (its count, distance less
    radius, features, the row), the stun bit (0x8000) in that result, 0x7EBB0's calls then."""
    out = []
    for w in sw:
        srch = w.get("search") or []
        last = srch[-1] if srch else None
        s_ = (last[1].get("s") or {}) if last else {}
        feat = int(s_["feat"], 16) if isinstance(s_.get("feat"), str) else None
        kk = (w["k0"] + last[0]) if last else None
        out.append({"k0": w["k0"], "name": w["name"], "ticks": w["ticks"], "fc": w.get("fc"), "rate": w.get("rate"),
                    "dmg_k": w["drops"][0][0] if w.get("drops") else None, "chain": w.get("chain_tick"),
                    "next": w.get("next"), "srch_rel": last[0] if last else None, "n": s_.get("n"), "dr": s_.get("dr"),
                    "feat": s_.get("feat"), "stun": bool(feat & 0x8000) if feat is not None else None,
                    "row": last[1].get("row") if last else None, "calls": finds.get(kk) if kk is not None else None,
                    "levels": [(lv[0], lv[1], lv[2]) for lv in (w.get("levels") or [])][:4]})
    return out


# --- the frame's score (Step 2.107, D280; its SITTING-PLAN section 3, from workflow A's drivers/framing_score.py) -------
def _m44(raw: bytes) -> list[tuple]:
    """A row-major 4x4 of f32 (D3D's row vectors: p' = p . M)."""
    f = struct.unpack("<16f", raw)
    return [f[4 * i:4 * i + 4] for i in range(4)]


def _mul(v, m) -> tuple:
    return tuple(sum(v[k] * m[k][j] for k in range(4)) for j in range(4))


def view_eye(view, proj=None) -> tuple[tuple, tuple]:
    """The eye and its forward from a rigid view matrix (row vectors): the rotation's columns are the camera's axes,
    the eye -t . R^T; the forward is the axis the projection's w grows along: the game's camera pass looks down view
    -z (its projection's w is -z, G0's calibration: a right-handed view), D3D's (w +z, or no ``proj``) down +z."""
    r, t = [row[:3] for row in view[:3]], view[3][:3]
    sign = -1.0 if proj is not None and proj[2][3] < 0.0 else 1.0
    return (tuple(-sum(t[k] * r[j][k] for k in range(3)) for j in range(3)), tuple(sign * r[j][2] for j in range(3)))


def perspective(proj) -> bool:
    """A perspective projection (w from the view depth): the camera's pass; the player's shadow pass at 0x3E887 draws
    it through an orthographic one (w 1: G0's calibration)."""
    return proj[3][3] == 0.0 and proj[2][3] != 0.0


def ndc(p, view, proj) -> tuple:
    """A world point's NDC x and y (None behind the eye) and its view depth (the clip w: the distance along the
    view's forward, either handedness)."""
    v = _mul((*p, 1.0), view)
    c = _mul(v, proj)
    return (None, None, c[3]) if c[3] <= 0.0 else (c[0] / c[3], c[1] / c[3], c[3])


def frame_score(view, proj, world, bones, pad, point, surface_z=None, prev=None, edge: float = 0.95) -> dict:
    """One frame's metrics: the drawn silhouette, the posed ``bones`` (model units) as points, the top and lowest
    raised and lowered by ``pad``'s z ((low, high), the bind mesh box less the bind bone box: ``frame_body``; the mesh
    past them), under ``world``, seen through ``view`` and ``proj``: its top and bottom in NDC y, the height it fills,
    whether it is whole inside ``edge`` and past the near plane (G0's calibration against the pictures [viewed]:
    garret4 at x1 -0.011 / -0.604, his drawn rows about 0.02 / -0.615; town_male_6 at garret4's height x2 and x0.37
    0.018 / -0.608, drawn about 0.02 / -0.62; the box of the bones widened by ``pad`` overstates a deep pose, its
    corners 0.12 / -0.68 on garret4, and the points clipped into it understate a body whose bind bones reach past its
    mesh, -0.53 for town_male_6's feet: ``box`` keeps the corners' top and bottom); with ``surface_z`` (swimming) the
    same for the points over the surface (``above_n``, ``above_in_frame``: what the water doesn't hide, G2 in the
    water); whether the eye is inside the padded box; the camera ``point``'s height as a fraction of the box and its NDC, the eye's distance to it and the
    angle between the view and the line to it; the eye over ``surface_z``; with ``prev`` (the last frame's ``_eye``,
    ``_forward``) the eye's step and the view's turn. ``_eye``/``_forward`` are positions: memory only."""
    lo = [min(b[k] for b in bones) + pad[0][k] for k in range(3)]
    hi = [max(b[k] for b in bones) + pad[1][k] for k in range(3)]
    corners = [_mul((x, y, z, 1.0), world)[:3] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    tb, lb = max(bones, key=lambda b: b[2]), min(bones, key=lambda b: b[2])
    pts = [*bones, (tb[0], tb[1], tb[2] + pad[1][2]), (lb[0], lb[1], lb[2] + pad[0][2])]
    wpts = [_mul((*q, 1.0), world)[:3] for q in pts]
    seen = [ndc(q, view, proj) for q in wpts]
    xs, ys = [x for x, _, _ in seen if x is not None], [y for _, y, _ in seen if y is not None]
    behind = sum(1 for _, _, d in seen if d < NEAR)
    up = [n for q, n in zip(wpts, seen) if surface_z is not None and q[2] >= surface_z]   # what the water doesn't hide
    top, bottom = (max(ys), min(ys)) if ys else (None, None)
    bys = [y for _, y, _ in (ndc(c, view, proj) for c in corners) if y is not None]
    eye, fwd = view_eye(view, proj)
    w_top, w_feet = max(c[2] for c in corners), min(c[2] for c in corners)
    to = [p - e for p, e in zip(point, eye)]
    eye_aim = math.sqrt(sum(d * d for d in to))
    along = [d / eye_aim for d in to] if eye_aim > 0 else [0.0, 0.0, 0.0]
    out = {"top": top, "bottom": bottom, "box": [max(bys), min(bys)] if bys else None,
           "fill_h": None if top is None else (min(top, 1.0) - max(bottom, -1.0)) / 2.0,
           "box_in_frame": behind == 0 and all(abs(x) <= edge for x in xs) and all(abs(y) <= edge for y in ys),
           "behind_near": behind,
           "eye_in_body": all(min(c[k] for c in corners) <= eye[k] <= max(c[k] for c in corners) for k in range(3)),
           "aim_frac": (point[2] - w_feet) / (w_top - w_feet) if w_top > w_feet else None,
           "aim_ndc": list(ndc(point, view, proj)[:2]), "eye_aim_m": eye_aim,
           "eye_view_err": math.degrees(math.acos(max(-1.0, min(1.0, sum(a * f for a, f in zip(along, fwd)))))),
           "eye_over_surf_m": None if surface_z is None else eye[2] - surface_z, "d_eye_m": None, "d_fwd_deg": None,
           "above_n": None if surface_z is None else len(up),
           "above_in_frame": None if surface_z is None else all(x is not None and abs(x) <= edge and abs(y) <= edge
                                                                and d >= NEAR for x, y, d in up),
           "_eye": eye, "_forward": fwd}
    if prev is not None:
        out["d_eye_m"] = math.dist(eye, prev[0])
        out["d_fwd_deg"] = math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(fwd, prev[1]))))))
    return out


def no_snap(m: dict, d_point: float, s: float, dt: float = 1 / 30, c0_fwd_max: float | None = None) -> bool:
    """G6 on one frame: the eye's step at most the point's step + 10s dt + 0.05s, the view's turn at most C0's
    same-state largest + 2 degrees."""
    if m.get("d_eye_m") is None:
        return True
    return m["d_eye_m"] <= d_point + 10.0 * s * dt + 0.05 * s and (c0_fwd_max is None or m["d_fwd_deg"] <= c0_fwd_max + 2)


def no_collapse(eye_aim: float, s: float, c0_holds: bool = True) -> bool:
    """G5's floor: the eye at least 0.6 x 5.11s from the point wherever C0 holds 3 m or more."""
    return not c0_holds or eye_aim >= 0.6 * 5.11 * s


def swim_judge(over: list, band: float = 0.4) -> dict:
    """The camera (or eye) over the surface per tick (m; None skipped): its range, the side changes (a crossing of
    the surface) and the ticks inside 0x81E10's push band (G7)."""
    v = [x for x in over if x is not None]
    return {"n": len(v), "range": [round(min(v), 3), round(max(v), 3)] if v else None,
            "side_changes": sum(1 for a, b in zip(v, v[1:]) if (a > 0) != (b > 0)),
            "band_ticks": sum(1 for x in v if abs(x) < band)}


def frame_body(characters_xbr: bytes, body: str) -> dict:
    """What the frame's score needs of a build's body (its ``characters.xbr``, model units): the posed bones to read
    (its rig's count) and the pad, its bind mesh box less its bind bone box per side (no mesh: none)."""
    from azurkit.tools.characters.characters import mesh_bounds, read_body
    b = read_body(characters_xbr, body)
    pos = [p for _n, p in b.bones] or [(0.0, 0.0, 0.0)]
    blo, bhi = ([min(p[k] for p in pos) for k in range(3)], [max(p[k] for p in pos) for k in range(3)])
    mesh = mesh_bounds(characters_xbr, body) or (blo, bhi)
    return {"bones": len(b.bones), "pad": (tuple(mesh[0][k] - blo[k] for k in range(3)),
                                           tuple(mesh[1][k] - bhi[k] for k in range(3)))}


class Kit:
    """The rows on one sitting ``s`` (``kit(s)``)."""

    def __init__(self, s):
        self.s = s
        self.pics: dict[str, dict] = {}   # this sitting's pictures by name: sha12, retakes, the earlier one it equals
        self.shas: dict[str, str] = {}    # sha12 -> the first picture with those bytes (a stale retake's test)
        self.bones: int | None = BONES_N["usa"]
        self.cands: dict[int, str] = {}   # the combo's candidate targets: critter -> species
        self.floor: dict[int, dict] = {}  # the floor cast per tick (row 5)
        self.camabs: dict[int, tuple] = {}   # the camera's place and point per target: memory only (positions)
        self.ent: int | None = None       # the last PlayerControl entity seen (the picture's clock)
        self.k1: float | None = None      # 0x42070's wrap threshold (GLIDE_WRAP), read once
        self.floor_len = 8.0              # the floor cast's length (floor_tick)
        self.frame: dict | None = None    # the frame's score on cap_cam's captures (frame_on): the body's pad, the rig's s
        self._fk, self._fr, self._fP = -1, {}, None   # the capture's frame index, its reads by index (memory), the player
        self.frame_sums: dict[str, dict] = {}   # this row's framing summaries by capture label
        self._case: str | None = None
        self._last_cam: dict = {}         # the last 0x81277 reading for the player (the swim input's pitch)
        self.quiet: bool | None = None    # the boots' quiet (Sitting.boot's: None its default, False the popups as saved)
        self.words: dict[str, int] = {}   # the booted build's shim words (shim_words), read per tick by xz
        self.jiggle: tuple[int, int] | None = None   # X41's shown words' VA and row count (jiggle_at; Step 2.156)
        self.sets: tuple[int, int] | None = None   # X36's state VA and set count (sets_at; Step 2.189a)
        self._seen: tuple | None = None   # the process the last row ran in: (pid, its bugchecks then) (Step X.96)

    @property
    def sb(self):
        return self.s.sb

    def va(self, usa_va: int) -> int:
        return self.s._va(usa_va)

    def species(self, t: int) -> str:
        """Critter ``t``'s species name (its def's +0), a known name or a sha12."""
        return self.s.guest_str(self.sb.read_u32(self.sb.read_u32(t + 0x178)))

    # -- the row ------------------------------------------------------------------------------------------------------
    def row(self, rid: str, iso, sha: str | None, tag: str, run, *, spots=(), body="usa", fresh: str | None = None,
            **note) -> dict:
        """One row: the spots it places onto recorded (``record_spot``, memory only; where the last row's xemu died
        or hung, in a fresh process instead), its xemu process (``fresh``: the last row's, relaunched only when one
        is due or ``fresh`` gives a reason), ``iso`` booted at ``tag`` (its sha12 checked against ``sha``), ``run(R)``'s steps, watched: a lost
        player tick ends the row with its census and one EIP sample (``R["hold"]``). One results row, its pictures
        in it."""
        name = iso if iso in ("usa", "europe") else Path(iso).stem
        R = {"case": f"{self.s.step}-{rid}" if self.s.step else rid, "row": rid, "name": name, "want_sha12": sha,
             "release": self.s.sb.st.get("release", "usa"), **note}
        self.bones = body if isinstance(body, int) else BONES_N.get(body)
        t0, pics0 = time.monotonic(), set(self.pics)
        self._case, self.frame_sums = R["case"], {}
        try:
            with self.s.watch():   # a failed set-up (no spot, no relaunch, no boot) is the row's record, its steps not run
                levels = lambda: {t: self.spot(t)["level"] for t in spots}  # noqa: E731
                ok = "err" not in self.step(R, "spots", levels) or (   # the last row's xemu died or hung
                    "err" not in self.step(R, "fresh_spots", self.fresh, f"{rid}'s spots",
                                           force="the spots failed there")
                    and "err" not in self.step(R, "spots_again", levels))
                ok = ok and "err" not in self.step(R, "fresh", self.fresh, rid, force=fresh)
                if ok and "err" not in self.step(R, "boot", self.boot, R, iso, tag, sha):
                    run(R)
        except self.s.Hold as h:
            R["hold"] = h.info
        R["wall_s"] = round(time.monotonic() - t0, 1)
        R["pics"] = {k: v for k, v in self.pics.items() if k not in pics0}
        if self.frame_sums:   # each framed capture's summary (its per-tick metrics in results/frames.jsonl)
            R["frames"] = self.frame_sums
        self.s.result(R)
        print(f"  ROW {R['case']} done in {R['wall_s']} s" + (f"; HELD at {R['hold']['where']}: "
                                                               f"{R['hold']['census'].get('class')}" if "hold" in R else ""))
        return R

    def step(self, R: dict, key: str, f, *a, **kw):
        """One check: its result into ``R[key]``; an error is recorded and the row goes on (a hold, ``Sitting.Hold``,
        ends it; a signal tears down)."""
        t0 = time.monotonic()
        try:
            R[key] = f(*a, **kw)
        except (Exception, SystemExit) as e:  # noqa: BLE001  (a check's failure is its result)
            if self.s.signalled is not None:
                raise self.s.after_signal(e) or e
            R[key] = {"err": f"{type(e).__name__}: {str(e)[:200]}"}
            print(f"  {key} ERROR {R[key]['err']}")
        R.setdefault("_s", {})[key] = round(time.monotonic() - t0, 1)
        return R[key]

    def relaunch_due(self) -> str | None:
        """Why the next row can't run in the last row's xemu process (Step X.96, the xemu fork session's advice:
        a row's boot then restores its state from the process's in-memory checkpoint, 2-10 ms, or loads it, where a
        relaunch took seconds), or None: the process lost; a guest bugcheck or dead halt, or a hung advance's probe,
        since the last row began; a sandbox whose boots walk the wall clock (real time, ``frame_boot`` false: a
        second boot in one process bugchecked there, AZ-628); a build without v0.15's load fix (D200's guard:
        repeated loads in one offscreen process diverged)."""
        sb, pid = self.sb, self.sb.st.get("pid")
        if not sb.alive():
            return "the process is gone"
        if not (sb.frame_boot() and sb.st.get("load_fix")):
            return "its boots walk the wall clock (AZ-628) or its build predates v0.15's load fix (D200)"
        if any(f"hang-{pid}-" in Path(q).name for q in sb.st.get("hang_probes", [])):
            return "a hung advance"
        seen = self._seen[1] if self._seen and self._seen[0] == pid else 0
        if new := sb.bugchecks()[seen:]:
            return f"a guest bugcheck or dead halt: {xo.bugcheck_list(new)}"
        return None

    def fresh(self, why: str, *, force: str | None = None) -> dict:
        """The xemu process for the next row: the last row's (Step X.96), unless ``relaunch_due`` or ``force`` (the
        spots failed there; a rate row times its own process) names a reason: then QMP quit and a relaunch on the
        same W keeping its slot."""
        t0 = time.monotonic()
        due = force or self.relaunch_due()
        out = {"why": why, "relaunched": due is not None}
        if due is not None:
            out.update(due=due, quit=self.sb._quit(relaunch=True))   # an owner demo keeps its lease (AZ-601)
            self.sb.relaunch()
        out.update(pid=self.sb.st.get("pid"), launches=self.sb.st.get("launches"), s=round(time.monotonic() - t0, 1))
        self._seen = (out["pid"], len(self.sb.bugchecks()))
        self.s.log(f"{'fresh process' if due else 'same process'} for {why}: pid {out['pid']}"
                   + (f" ({due})" if due else ""))
        print("  PROCESS", out)
        return out

    def boot(self, R: dict, iso, tag: str, sha: str | None) -> dict:
        """``iso`` ("usa", "europe": the vanilla discs, a control; else a build's ISO) booted at ``tag``'s save
        (``Sitting.boot``: quiet), its ISO's sha12 checked; a build's boot with its DVD and HDD bytes read."""
        disc = (None if iso == "usa" else xo.vanilla_iso(xo.region_named("europe")) if iso == "europe" else Path(iso))
        b0 = self._blocks() if disc is not None and iso != "europe" else None
        res = self.s.boot(disc, tag, **({} if self.quiet is None else {"quiet": self.quiet}))
        out = {k: res.get(k) for k in ("iso_sha12", "xbe_sha256", "level", "s", "tries", "warm", "warm_drive",
                                        "incidents", "host_profile")}
        out.update(binary=self.sb.st.get("xemu_sha12"), load=boot_load(self.sb, tag, res))   # a fork request's
        try:
            xbe = xo.read_file(disc, "default.xbe") if disc is not None else None
            self.words = shim_words(xbe) if xbe is not None else {}
            self.jiggle = jiggle_at(xbe) if xbe is not None else None
            self.sets = sets_at(xbe) if xbe is not None else None
        except (OSError, ValueError, KeyError) as e:   # not a build the tools can place: no words
            self.words, self.jiggle, self.sets, out["words_err"] = {}, None, None, str(e)[:60]
        out["words"] = sorted(self.words)
        out["x41_rows"] = self.jiggle[1] if self.jiggle else 0
        if b0 is not None:
            with _suppressed():
                out["io"] = {k: {x: v[x] - b0.get(k, {}).get(x, 0) for x in ("rd", "wr")}
                             for k, v in self._blocks().items()}
        R["iso_ok"] = (out.get("iso_sha12") == sha) if sha else None
        print(R["row"], "boot", out)
        return out

    def _blocks(self) -> dict:
        try:
            return self.sb.blockstats()
        except (OSError, EOFError, KeyError) as e:
            return {"err": str(e)[:80]}

    def warp(self, level: str, tries: int = 3) -> dict:
        """The debug menu's level warp (``Sitting.warp``), retried (a hit reaction holding the cheat tick)."""
        last = None
        for i in range(tries):
            try:
                self.ensure_tick()
                self.s.capture(30, {}, label=None, body=False, hold_hp=200)
                w = self.s.warp(level)
                return {**{k: w.get(k) for k in ("ok", "level", "s")}, "try": i + 1, "last_err": last}
            except (Exception, SystemExit) as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:100]}"
                print("  warp failed:", last)
        raise SystemExit(f"warp {level}: {tries} failures ({last})")

    # -- the player, spots and placements -----------------------------------------------------------------------------
    def player(self) -> tuple[int, int]:
        """(entity, critter) at a player tick (halted there); a few ticks tried."""
        for _ in range(6):
            r = self.sb.g.regs()
            if r["eip"] == xo.PLAYER_TICK and (e := self.sb.g.u32(r["esp"] + 4)):
                self.ent = e
                return e, self.sb.read_u32(e + 0x20)
            if self.s.tick() is None:
                self.s.clear_dialog()
        raise SystemExit("no player tick with an entity")

    def ensure_tick(self) -> bool:
        """Halted at a player tick (run to the next one if not)."""
        if self.sb.g.regs()["eip"] == xo.PLAYER_TICK or self.s.tick(4.0) is not None:
            return True
        return self.s.clear_dialog()

    def spot(self, tag: str) -> dict:
        """A D98 state's spot (``Sitting.record_spot``: its body centre, facing, cell, level: memory only) and its
        camera yaw at the state's first tick (the steer's start), recorded once a sitting."""
        if "cam" not in self.s.spots.get(tag, {}):
            self.s.record_spot(tag)
            self.s.spots[tag]["cam"] = _cam_yaw(self.sb)
        return self.s.spots[tag]

    def free(self, limit: int = 2400) -> int:
        """Player ticks until the input builder takes the stick (input+0x30 clear: no level-start sequence or exit
        field moves the player; after a place in a1 230-810 ticks, AZ-422); the ticks it took."""
        def f(sb, row, rows):
            if sb.read(sb.g.regs()["eax"] + 0x30, 1)[0] == 0:
                return ["stop"]
        return self.s.capture(limit, {}, label=None, on_tick=f, body=False, chain=False)["meta"]["rows"]

    def cam_back(self, a: float, n: int = 300) -> int:
        """Player ticks until the camera's yaw is back within 0.05 rad of ``a`` (the state's: the steer's start)."""
        def f(sb, row, rows):
            if abs((_cam_yaw(sb) - a + math.pi) % (2 * math.pi) - math.pi) < 0.05:
                return ["stop"]
        return self.s.capture(n, {}, label=None, on_tick=f, body=False, chain=False)["meta"]["rows"]

    def placed(self, spot: str, tries: int = 4, wait: int = 900, **kw) -> dict:
        """R6 onto a recorded spot [placed], re-placed while it settles more than 0.3 m off (AZ-409), then the stick
        free and the camera back at the state's yaw (AZ-422: a1 holds both after a place); three attempts."""
        last = None
        for _ in range(3):
            try:
                self.ensure_tick()
                self.s.clear_dialog()
                pl = None
                for t in range(tries):
                    pl = self.s.place(spot=spot, **kw)
                    pl["try"] = t + 1
                    if pl["off_m"] <= 0.3:
                        break
                    self.s.capture(20, {}, label=None, body=False)
                pl["free_after"] = self.free(wait)
                if (a := self.s.spots[spot].get("cam")) is not None:
                    pl["cam_after"] = self.cam_back(a)
                e, c = self.player()
                pl["off_after_wait_m"] = round(math.dist(_v3(self.sb, c + 0x15C), self.s.spots[spot]["centre"]), 3)
                return pl
            except (OSError, SystemExit) as e:
                last = str(e)[:80]
                print("  placement failed:", last)
        raise SystemExit(f"placed {spot}: three failures ({last})")

    def place_feet(self, sp: dict, back_m: float = 0.0, lift: float = 0.1) -> None:
        """R6 at a spot's feet (``back_m`` behind it along its facing) with its facing and cell [placed]."""
        q4 = sp["quat"]
        yaw = 2 * math.atan2(q4[2], q4[3])
        fx, fy = -math.sin(yaw), math.cos(yaw)
        cen = sp["centre"]
        feet = (cen[0] - back_m * fx, cen[1] - back_m * fy, cen[2] - recipes.LIFT + lift)
        self.s.apply(recipes.place(self.sb.read_u32, feet, 0.0, quat=q4, cell=sp["cell"], entity=self.player()[0],
                                   va=self.s._va))

    # -- pictures -----------------------------------------------------------------------------------------------------
    def pic(self, name: str, adv: int = 4) -> str:
        """A picture of the present: ``adv`` frames advanced first (a halted screendump is stale, AZ-422), retaken 4
        frames on while its bytes equal any earlier picture of the sitting (AZ-452), 3 times at most, then named
        SAME-AS; the frames advanced and the player ticks they ran (the event clock) recorded, the frames counting
        those each screenshot advanced itself (v0.16.1's picture-stale and null-RAM draws, ``last_picture``)."""
        rec = {"adv": adv}
        try:
            c0 = self._clock()
            self.sb.frame_advance(adv)
            frames, tries = adv, 0
            p = self.s.screenshot(name)
            frames += self._shot_frames()
            h = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
            while h in self.shas and tries < 3:
                tries += 1
                self.sb.frame_advance(4)
                frames += 4
                p = self.s.screenshot(name)
                frames += self._shot_frames()
                h = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
            c1, stale = self._clock(), h in self.shas
            rec.update(sha12=h, frames=frames, retakes=tries, same_as=self.shas.get(h) if stale else None,
                       ticks=round((c1 - c0) * 30) if c0 is not None and c1 is not None else None)
            self.pics[name] = rec
            self.shas.setdefault(h, name)
            return p.name + (f" (retaken {tries})" if tries else "") + (f" SAME-AS {self.shas[h]}" if stale else "")
        except (Exception, SystemExit) as e:  # noqa: BLE001  (a failed picture is its result)
            rec["err"] = str(e)[:80]
            self.pics[name] = rec
            return f"failed: {str(e)[:80]}"

    def _shot_frames(self) -> int:
        """The vblanks the last screenshot ran itself (Step X.61): advanced past a stale picture, drawn by
        ``xemu-render-next``."""
        lp = getattr(self.sb, "last_picture", None) or {}
        return lp.get("advanced", 0) + lp.get("render_frames", 0)

    def _clock(self) -> float | None:
        """The player's event clock (PlayerControl+0x18, a double): the entity halted at, else the last one seen."""
        try:
            if self.sb._g is not None and self.sb._halted and (r := self.sb.g.regs())["eip"] == xo.PLAYER_TICK:
                self.ent = self.sb.g.u32(r["esp"] + 4)
            return struct.unpack("<d", self.sb.read(self.ent + 0x18, 8))[0] if self.ent else None
        except (OSError, EOFError):
            return None

    # -- per-tick fields ------------------------------------------------------------------------------------------------
    def glide_t(self, sb, c: int) -> float:
        """0x42070's blend of the drawn origin from +0x1B0 to +0x1BC (Step 2.106): glide mode +0x19C 1, the clock
        [critter+0xE4]+0x10 less +0x1A8 over +0x1A0; 2 (an aligned move: hang_start, climb_up_edge), the playing layer's
        clip fraction (layer [+0x10]+1 of +0x17C's 0x40-byte layers: its time +0x18 over its clip's length +0x10) less
        +0x1A8, plus 1 under 0x1A26C8's value, over +0x1A0; each clamped to [0, 1] (NaN 0); else 0 (the origin)."""
        mode = sb.read_i32(c + 0x19C)
        if mode not in (1, 2):
            return 0.0
        win, t0 = _f1(sb, c + 0x1A0), struct.unpack("<d", sb.read(c + 0x1A8, 8))[0]
        if mode == 1:
            f = struct.unpack("<d", sb.read(sb.read_u32(c + 0xE4) + 0x10, 8))[0] - t0
        else:
            lay = sb.read_u32(c + 0x17C)
            e = lay + (sb.read_i32(lay + 0x10) + 1) * 0x40
            clip = sb.read_u32(e + 4)
            f = (_f1(sb, e + 0x18) / _f1(sb, clip + 0x10) if clip else 0.0) - t0
            if self.k1 is None:
                try:
                    self.k1 = _f1(sb, self.va(GLIDE_WRAP))
                except (OSError, ValueError, KeyError):
                    self.k1 = 0.0
            if f < self.k1:
                f += 1.0
        t = f / win if win else (math.inf if f > 0 else 0.0)
        return 0.0 if math.isnan(t) else min(max(t, 0.0), 1.0)

    def xz443(self, sb, ent: int) -> dict:
        """Offsets only: the cable point PC+0x44 and the glide ends +0x1B0/+0x1BC against the body centre +0x15C, and
        the origin the model is drawn from (``od``: their blend by ``glide_t``, ``gt``; +0x1B0 outside a glide)."""
        c = sb.read_u32(ent + 0x20)
        cen = _v3(sb, c + 0x15C)
        anim = sb.read_i32(c + 0x200)
        o0, o1 = _v3(sb, c + 0x1B0), _v3(sb, c + 0x1BC)
        try:
            t = self.glide_t(sb, c)
        except (OSError, ValueError, ZeroDivisionError, struct.error):
            t = 0.0
        od = tuple(a + (b - a) * t for a, b in zip(o0, o1))
        return {"anim": anim, "mode": sb.read_i32(c + 0x19C), "cab": _rel(_v3(sb, ent + 0x44), cen),
                "o0": _rel(o0, cen), "o1": _rel(o1, cen), "od": _rel(od, cen), "gt": round(t, 4),
                "sc": round(_f1(sb, c + 0x188), 4),
                "slot_h": sb.read_u32(sb.read_u32(c + 0x178) + 0x124 + 4 * anim) if 0 <= anim < 104 else None}

    def words_now(self, sb) -> dict:
        """The booted build's shim words this tick (:data:`WORDS`: X29's swap count, X8's swim side, B2's holds, R1's
        hold)."""
        out = {}
        for key, va in self.words.items():
            with _suppressed():
                out[key] = struct.unpack("<i", sb.read(va, 4))[0]
        return out

    def jiggle_now(self, sb) -> list[list[float]]:
        """X41's shown words this tick, per row: the offset (mm as drawn: side, forward, up), roll and yaw (rad), the
        raw radius over the travel, the clock it stepped at (s, unrounded) and the squash's three scales (Step 2.156,
        D481); [] without X41."""
        from azurkit.tools.characters.jiggle_rt import SHOWN_SIZE
        if not self.jiggle:
            return []
        va, n = self.jiggle
        out = []
        with _suppressed():
            raw = sb.read(va, SHOWN_SIZE * n)
            for i in range(n):
                *six, now, s0, s1, s2 = struct.unpack_from("<6fd3f", raw, SHOWN_SIZE * i)
                out.append([round(v, 4) for v in six] + [now] + [round(v, 5) for v in (s0, s1, s2)])
        return out

    def jiggle_trace(self, label: str, rows: list[dict]) -> dict:
        """X41's shown offsets, steps and resets, the state and the centre's speed (m/s over X41's clock, so at 30 or 60
        Hz) per tick of capture ``rows`` (each tick's ``x``: ``xz``'s, which reads ``jiggle_now``) into the sitting's
        private folder only (0600), and the rows' ``jiggle_metric`` (the AZ-648 metric, peaks and extrema: numbers
        only)."""
        p = self.s.private / f"trace-jiggle-{label}.json"
        L, last = [], None
        for r in rows:
            x = r.get("x", {})
            c, now = r.get("c"), x["jg"][0][6] if x.get("jg") else None
            speed = round(math.dist(c, last[0]) / (now - last[1]), 3) if c and now and last and now > last[1] else None
            last = (c, now) if c and now else last
            L.append({"k": r.get("k"), "state": r.get("state"), "speed": speed, "steps": x.get("x41_steps"),
                      "resets": x.get("x41_resets"), "jg": x.get("jg")})
        p.write_text(json.dumps(L), encoding="utf-8")
        os.chmod(p, 0o600)
        return {"trace": p.name, "metric": jiggle_metric(rows)}

    def jiggle_sheet(self, label: str, names: list[str], rows: list[dict] | None = None,
                     beside: list[str] | None = None, row: int = 0) -> dict:
        """An offscreen motion sheet (Step 2.156): this sitting's pictures ``names`` (``pic``'s, in order, e.g. the side
        and three-quarter views a few ticks apart) side by side, a control's ``beside`` (MB's, under RT's), and under
        them X41 row ``row``'s offset per tick of ``rows`` (side, forward, up in mm, ``jiggle_now``'s) plotted, into
        the sitting's screens folder as ``sheet-<label>.png``. Pictures of the game: evidence only, never committed."""
        folder = self.s.ev / "screens"
        paths = [folder / f"{n}.png" for n in names]
        series = None
        if rows:
            jg = [r["x"]["jg"][row] for r in rows if r.get("x", {}).get("jg") and len(r["x"]["jg"]) > row]
            series = [[o[i] for o in jg] for i in range(3)]
        return contact_sheet(folder / f"sheet-{label}.png", paths, series,
                             beside=[folder / f"{n}.png" for n in beside] if beside else None)

    def xz(self, sb, ent: int) -> dict:
        """xz443, the top and lowest bone (model z x scale + the drawn origin ``od``) against the cable and the centre
        (the body's ``bones``), the fall reference PlayerControl+0x168 against the centre, the state time +0x9C, the
        flaps and the build's shim words (``words_now``, Step 2.116b). Two limits sitting 2.118 measured (score a drawn
        body on the frame there, ``frame_on``'s draw hook): in ``hang_start`` (glide mode 2) ``od`` is up to 0.98 m off
        the origin the frame is drawn from [cause unread], and a one-bone rig's top and lowest are its bone's, not its
        mesh's (key_fire1's mesh rides 1.03 over it)."""
        d = self.xz443(sb, ent) | self.words_now(sb)
        if self.jiggle:
            d["jg"] = self.jiggle_now(sb)
        if self.bones:
            try:
                c = sb.read_u32(ent + 0x20)
                raw = sb.read(sb.read_u32(sb.read_u32(c + 0x17C) + 8), 0xB0 * self.bones)
                zs = [struct.unpack_from("<f", raw, 0xB0 * i + 0xA8)[0] for i in range(self.bones)]
                zs = [z for z in zs if math.isfinite(z) and abs(z) < 1e4]
                top, low = max(zs) * d["sc"] + d["od"][2], min(zs) * d["sc"] + d["od"][2]
                d.update(top_vs_cab=round(top - d["cab"][2], 3), top_vs_cen=round(top, 3), low_vs_cen=round(low, 3))
            except (OSError, ValueError):
                pass
        try:
            c = sb.read_u32(ent + 0x20)
            d["f168_dc"] = round(_f1(sb, ent + 0x168) - _f1(sb, c + 0x164), 4)
            d["st_t"] = round(_f1(sb, ent + 0x9C), 4)
            d["flapc"] = sb.read_i32(ent + 0xD8)
        except OSError:
            pass
        return d

    def xcombo(self, sb, ent: int) -> dict:
        """The player's attack per tick (column +0x134, Move end1 +0xFC, end2 +0x100, the clip fraction +0x178, the
        press time +0xA0, the row's multiplier +0xEC and Rate +0x104, the clip handle), the live search radius, and
        each candidate target's stun and freeze bits (+0x168 & 0x8000 / 0x10000), distance, HP and bearing."""
        c = sb.read_u32(ent + 0x20)
        d = {"anim": sb.read_i32(c + 0x200), "col": sb.read_i32(ent + 0x134), "fc": round(_f1(sb, ent + 0xFC), 4),
             "frac": round(_f1(sb, ent + 0x178), 4), "pa": round(_f1(sb, ent + 0xA0), 4), "hp": sb.read_i32(c + 0x210),
             "clip": sb.read_u32(c + 0x204), "slot_h": None, "tg": {}}
        try:
            p = _v3(sb, c + 0x15C)
            q4 = struct.unpack("<4f", sb.read(c + 0x18C, 16))
            yaw = 2 * math.atan2(q4[2], q4[3])
            fx, fy = -math.sin(yaw), math.cos(yaw)
            for t in self.cands:
                with _suppressed():
                    fl, q = sb.read_u32(t + 0x168), _v3(sb, t + 0x15C)
                    dx, dy = q[0] - p[0], q[1] - p[1]
                    dist = math.hypot(dx, dy)
                    brg = math.degrees(math.atan2(fx * dy - fy * dx, fx * dx + fy * dy)) if dist > 1e-3 else 0.0
                    d["tg"][hex(t)] = [bool(fl & 0x8000), bool(fl & 0x10000), round(dist, 3), sb.read_i32(t + 0x210),
                                       round(brg, 1)]
        except OSError:
            pass
        d.update(mult=round(_f1(sb, ent + 0xEC), 4), rate=round(_f1(sb, ent + 0x104), 4),
                 end2=round(_f1(sb, ent + 0x100), 4), rad=self.radius(sb))
        return d

    def radius(self, sb) -> float | None:
        """attack_target_find's live radius: the float its instruction at 0x7EDA4 names (+2: the operand)."""
        try:
            return round(_f1(sb, sb.read_u32(self.va(RAD_OP) + 2)), 4)
        except (OSError, ValueError):
            return None

    # -- the camera readers ---------------------------------------------------------------------------------------------
    def rd_cam(self, sb, r) -> dict:
        """At 0x81277 (before X20): the camera [esp+0x10], its target +0x190, the point the target gave [esp+0x50],
        the camera's place +0x15C, its pitch and distance (+0x198), the wanted ones (+0x1A0): offsets from the
        target's centre, the camera's actual distance and pitch to the point (the place and point in memory only)."""
        try:
            esp = r["esp"]
            cam = sb.read_u32(esp + 0x10)
            t = sb.read_u32(cam + 0x190)
            a, cp, c = _v3(sb, esp + 0x50), _v3(sb, cam + 0x15C), _v3(sb, t + 0x15C)
            pitch, dist = struct.unpack("<2f", sb.read(cam + 0x198, 8))
            self.camabs[t] = (cp, a)
            o = {"tgt": t, "aim_dc": round(a[2] - c[2], 4), "aim_dxy": round(math.hypot(a[0] - c[0], a[1] - c[1]), 4),
                 "cam_dc": round(cp[2] - c[2], 4), "cam_dxy": round(math.hypot(cp[0] - c[0], cp[1] - c[1]), 4),
                 "cam_aim_m": round(math.dist(cp, a), 4), "pitch_deg": round(math.degrees(pitch), 2),
                 "dist": round(dist, 3), "depth": round(_f1(sb, t + 0x27C), 3)}
        except (OSError, ValueError) as e:
            return {"err": str(e)[:60]}
        try:
            o["want_a0"], o["want_a4"] = [round(v, 4) for v in struct.unpack("<2f", sb.read(cam + 0x1A0, 8))]
            h = math.hypot(a[0] - cp[0], a[1] - cp[1])
            o["act_dist"] = round(math.dist(cp, a), 3)
            o["act_pitch"] = round(math.degrees(math.atan2(a[2] - cp[2], h)), 2)
        except (OSError, ValueError):
            pass
        self._last_cam[t] = o
        return o

    def rd_pt2(self, sb, r) -> dict:
        """At 0x8129C (where X20's CALL returns; vanilla: after the two loads it replaces): EDI the camera; the point
        it aims at ([esp+0x50]) as the update goes on, its height over the target's centre, the camera's distance and
        pitch to it."""
        try:
            cam = r["edi"]
            t = sb.read_u32(cam + 0x190)
            a, c, cp = _v3(sb, r["esp"] + 0x50), _v3(sb, t + 0x15C), _v3(sb, cam + 0x15C)
            h = math.hypot(a[0] - cp[0], a[1] - cp[1])
            if self.frame is not None and t == self._fP:   # the frame's point and the camera's state (memory)
                f = self._fr.setdefault(self._fk, {})
                f["P"] = a
                f["cam"] = [round(v, 4) for v in struct.unpack("<5f", sb.read(cam + 0x194, 20))] + [
                    round(_f1(sb, cam + 0x1B4), 4)]
            return {"tgt": t, "aim2_dc": round(a[2] - c[2], 4), "act2_dist": round(math.dist(cp, a), 3),
                    "act2_pitch": round(math.degrees(math.atan2(a[2] - cp[2], h)), 2)}
        except (OSError, ValueError) as e:
            return {"err": str(e)[:60]}

    @staticmethod
    def rd_al(sb, r) -> dict:
        return {"al": r["eax"] & 0xFF}

    @staticmethod
    def rd_sw2(sb, r) -> dict:
        """0x810F8: AL after the camera's point -> place sweep, the hit fraction [esp+0x48], the camera's target."""
        try:
            return {"al": r["eax"] & 0xFF, "frac": round(_f1(sb, r["esp"] + 0x48), 4), "tgt": sb.read_u32(r["esi"] + 0x190)}
        except (OSError, ValueError) as e:
            return {"al": r["eax"] & 0xFF, "err": str(e)[:40]}

    @staticmethod
    def rd_sight(sb, r) -> dict:
        """0x80C3A: AL after the line-of-sight sweep (X19's answer where it is installed), the game's hit fraction
        [esp+0x94] (its record, 0x81B7C's lea, from the camera end), the hit's distance from the point (1 - it) x the
        line's length (0x80C10's two arguments: the camera's +0x15C and the point) and the blocked timer +0x1B4 of the
        camera ([esp+0x1C], the caller's [esp+0x10]) as the sweep left it (Step 2.116: X19 sets 1.0 to pull now)."""
        try:
            frac = _f1(sb, r["esp"] + 0x94)
            ends = [struct.unpack("<3f", sb.read(sb.read_u32(r["esp"] + k), 12)) for k in (4, 8)]
            return {"al": r["eax"] & 0xFF, "frac": round(frac, 4), "near_m": round((1.0 - frac) * math.dist(*ends), 3),
                    "blocked": round(_f1(sb, sb.read_u32(r["esp"] + 0x1C) + 0x1B4), 4)}
        except (OSError, ValueError) as e:
            return {"al": r["eax"] & 0xFF, "err": str(e)[:40]}

    @staticmethod
    def rd_stick(sb, r) -> dict:
        """0x81952: the stick sum [esp+0x20] the camera grows its distance by, its distance and wanted one."""
        try:
            return {"stick": round(_f1(sb, r["esp"] + 0x20), 4), "d": round(_f1(sb, r["ecx"] + 0x19C), 3),
                    "want": round(_f1(sb, r["ecx"] + 0x1A4), 3)}
        except (OSError, ValueError) as e:
            return {"err": str(e)[:40]}

    def cam_bps(self) -> tuple[list[int], dict]:
        """The camera's breakpoints and readers: its update (0x81277), the sweeps' ALs, the stick, X20's return."""
        v = self.va
        rd = {v(CAM_UPD): self.rd_cam, v(SW1): self.rd_al, v(SW2): self.rd_sw2, v(SW_D71): self.rd_al,
              v(SW_C3A): self.rd_sight, v(STICK_AT): self.rd_stick, v(PT2_AT): self.rd_pt2}
        return list(rd), rd

    def cam_ticks(self, c: dict, rows: list[dict], P: int) -> dict:
        """Per tick (k): the camera's reading for the player (distance +0x19C, the wanted pitch/distance, the actual
        distance and pitch to its point, the point over the centre), after X20 the point's height over the centre (the
        tick's last update and its lowest) and the camera's distance and pitch to it (last and smallest), AL after
        each sweep, the stick sum; summarized per state."""
        v = self.va
        cam, sw1, sw2, d71, c3a, stick, pt2 = (v(x) for x in (CAM_UPD, SW1, SW2, SW_D71, SW_C3A, STICK_AT, PT2_AT))
        byk, by2 = {}, {}
        for h in c["hits"]:
            if (k := h.get("k")) is None:
                continue
            b = byk.setdefault(k, {"sw1": [], "sw2": [], "d71": [], "c3a": [], "c3a_hit": [], "stick": []})
            va = int(h["va"], 16)
            if va == cam and h.get("tgt") == P and "aim_dc" in h:
                b.update({x: h.get(x) for x in ("aim_dc", "dist", "pitch_deg", "want_a0", "want_a4", "act_dist",
                                               "act_pitch")})
            elif va == pt2 and h.get("tgt") == P and "aim2_dc" in h:
                by2.setdefault(k, []).append(h)
            elif va in (sw1, d71, c3a):
                b[{sw1: "sw1", d71: "d71", c3a: "c3a"}[va]].append(h.get("al"))
                if va == c3a:   # the sight's hit: its fraction, its distance from the point, the blocked timer
                    b["c3a_hit"].append((h.get("frac"), h.get("near_m"), h.get("blocked")))
            elif va == sw2:
                b["sw2"].append((h.get("al"), h.get("frac"), h.get("tgt") == P))
            elif va == stick:
                b["stick"].append(h.get("stick"))
        out = []
        for r in rows:
            b, x = byk.get(r["k"], {}), r.get("x") or {}
            o = {"k": r["k"], "st": hex(r["state"]), "dist": b.get("dist"), "act_dist": b.get("act_dist"),
                 "act_pitch": b.get("act_pitch"), "pitch": b.get("pitch_deg"), "want": [b.get("want_a0"), b.get("want_a4")],
                 "aim_dc": b.get("aim_dc"), "sw1": b.get("sw1"), "sw2": b.get("sw2"), "d71": b.get("d71"),
                 "c3a": b.get("c3a"), "c3a_hit": b.get("c3a_hit"), "stick": b.get("stick"),
                 "top_vs_cab": x.get("top_vs_cab"),
                 "o1_dz": (x.get("o1") or [None] * 3)[2]}
            if L := by2.get(r["k"]):
                o.update(aim2_dc=L[-1]["aim2_dc"], aim2_min=min(h["aim2_dc"] for h in L), act2_dist=L[-1]["act2_dist"],
                         act2_min=min(h["act2_dist"] for h in L), act2_pitch=L[-1]["act2_pitch"], n_upd=len(L))
            out.append(o)
        summ = {}
        for st in sorted({o["st"] for o in out}):
            L = [o for o in out if o["st"] == st and o["act_dist"] is not None]
            if not L:
                continue

            def mm(f, L=L):
                return [min(f(o) for o in L), max(f(o) for o in L)]
            summ[st] = {"n": len(L), "act_dist": mm(lambda o: o["act_dist"]), "dist": mm(lambda o: o["dist"]),
                        "act_pitch": mm(lambda o: o["act_pitch"]), "aim_dc": mm(lambda o: o["aim_dc"]),
                        "want": sorted({tuple(o["want"]) for o in L})[:3],
                        "sw2_hit_ticks": sum(1 for o in L if any(a for a, _f, mine in (o["sw2"] or []) if mine)),
                        "sw2_frac_hits": sorted({f_ for o in L for a, f_, mine in (o["sw2"] or []) if a and mine})[:6],
                        "sw1_hit_ticks": sum(1 for o in L if any(o["sw1"] or [])),
                        "d71_hit_ticks": sum(1 for o in L if any(o["d71"] or [])),
                        "c3a_hit_ticks": sum(1 for o in L if any(o["c3a"] or [])),
                        "stick_nonzero_ticks": sum(1 for o in L if any(v for v in (o["stick"] or []) if v)),
                        "collapsed_ticks": sum(1 for o in L if o["act_dist"] < 1.5)}
        first_drop = next((o for o in out if o["act_dist"] is not None and o["act_dist"] < 1.5), None)
        return {"per_tick": out, "by_state": summ, "first_drop": first_drop}

    def cap_cam(self, n: int, sched: dict, label: str | None, *, extra: dict | None = None,
                **kw) -> tuple[dict, dict]:
        """A capture with the per-tick fields (``xz``) and the camera's breakpoints, ``extra`` ({USA VA: a reader or
        None}) beside them: (capture, ``cam_ticks``, with the frame's score per tick under ``frame`` while
        ``frame_on``)."""
        _e, P = self.player()
        b, rd = self.cam_bps()
        for va, f in (extra or {}).items():
            b.append(self.va(va))
            if f is not None:
                rd[self.va(va)] = f
        fields, hooks = {"x": self.xz}, {}
        if self.frame is not None:
            self._fk, self._fr, self._fP = -1, {}, P
            fields["fk"] = self._frame_tick
            hooks = {self.va(va): self._hk_draw for va in DRAW_AT}
        c = self.s.capture(n, sched, label=label, fields=fields, bps=b, bp_readers=rd, hooks=hooks, **kw)
        cz = self.cam_ticks(c, c["rows"], P)
        if self.frame is not None:
            cz["frame"] = self.frames(c["rows"], label, cz["per_tick"])
        return c, cz

    # -- the frame's score (Step 2.107, D280) --------------------------------------------------------------------------
    def frame_on(self, pad=None, s: float = 1.0) -> None:
        """Score the player's frame on every ``cap_cam`` capture from here on (``frame_score``, one row of
        ``results/frames.jsonl`` a capture, its summary in the row's ``frames``): ``pad`` the body's (``frame_body``),
        ``s`` the build's rig scale (G5's and G6's bounds; 1 with no rig). ``None``: off."""
        self.frame = None if pad is None else {"pad": pad, "s": s}

    def _frame_tick(self, sb, ent) -> int:
        """A field: the row's index (the key the render's reads after it file under) and the surface (the centre's
        z plus its depth, memory only)."""
        self._fk += 1
        with _suppressed():
            c = sb.read_u32(ent + 0x20)
            self._fr.setdefault(self._fk, {})["surf"] = _f1(sb, c + 0x164) + _f1(sb, c + 0x27C)
        return self._fk

    def _hk_draw(self, sb, r) -> None:
        """A hook at a critter's draw (``DRAW_AT``): at the player's first this frame through the camera (a perspective
        projection: its shadow pass, 0x3E887's orthographic one, skipped) its world, view and projection matrices and
        its posed bones' translations (model units), in memory; every draw of it counted."""
        off = next((o for va, o in DRAW_AT.items() if self.va(va) == r["eip"]), None)
        if off is None or sb.read_u32(r["esp"] + off) != self._fP:
            return
        f = self._fr.setdefault(self._fk, {})
        f["draws"] = f.get("draws", 0) + 1
        if "w" in f:
            return
        with _suppressed():
            p = _m44(sb.read(self.va(PROJ_M), 64))
            if not perspective(p):
                return
            f["w"], f["v"], f["p"] = _m44(sb.read(self.va(WORLD_M), 64)), _m44(sb.read(self.va(VIEW_M), 64)), p
            f["site"] = hex(r["eip"])
            if self.bones:
                raw = sb.read(sb.read_u32(sb.read_u32(self._fP + 0x17C) + 8), 0xB0 * self.bones)
                vs = (struct.unpack_from("<3f", raw, 0xB0 * i + 0xA0) for i in range(self.bones))
                f["b"] = [v for v in vs if all(math.isfinite(x) and abs(x) < 1e4 for x in v)]

    def frames(self, rows: list[dict], label: str | None, cams: list[dict] | None = None) -> dict:
        """The frame's score per tick of a capture (``frame_score`` on the reads ``_hk_draw`` and ``rd_pt2`` kept),
        the eye's step against the point's, G5's and G6's bounds at the rig's s, whether a camera sweep hit for the
        player that tick (``cams``: ``cam_ticks``' per tick; ``sw``, the pull-in's cause G2, G4 and G5 exempt); its
        per-tick metrics as one
        ``results/frames.jsonl`` row (numbers only: no position), its summary by state returned and kept in the row's
        ``frames``."""
        pad, s_ = self.frame["pad"], self.frame["s"]
        out, prev, p0, w0 = [], None, None, None
        swk = {c["k"]: int(any(c.get("sw1") or []) or any(c.get("d71") or []) or any(c.get("c3a") or [])
                           or any(a for a, _f, mine in (c.get("sw2") or []) if mine)) for c in (cams or [])}
        for r in rows:
            f = self._fr.get(r["k"], {})
            o = {"k": r["k"], "st": hex(r["state"]), "draws": f.get("draws", 0), "cam": f.get("cam"),
                 "sw": swk.get(r["k"])}
            if all(x in f for x in ("w", "v", "p", "b", "P")) and f["b"]:
                m = frame_score(f["v"], f["p"], f["w"], f["b"], pad, f["P"],
                                f.get("surf") if r["state"] == 6 else None, prev)
                prev = (m.pop("_eye"), m.pop("_forward"))
                d_p = math.dist(f["P"], p0) if p0 is not None else 0.0
                d_o = math.dist(f["w"][3][:3], w0) if w0 is not None else 0.0   # the drawn origin's step (Step 2.116)
                p0, w0 = f["P"], f["w"][3][:3]
                o.update({k: (round(v, 4) if isinstance(v, float) else
                              [None if x is None else round(x, 4) for x in v] if isinstance(v, list) else v)
                          for k, v in m.items()},
                         d_point_m=round(d_p, 4), d_origin_m=round(d_o, 4), snap=not no_snap(m, d_p, s_),
                         collapsed=not no_collapse(m["eye_aim_m"], s_))
            else:
                o["missing"] = sorted({"w", "v", "p", "b", "P"} - set(f))
            out.append(o)
        by = {}
        for st in sorted({o["st"] for o in out}):
            L = [o for o in out if o["st"] == st and "missing" not in o]
            if not L:
                continue

            def mm(key, L=L):
                v = [o[key] for o in L if o.get(key) is not None]
                return [min(v), max(v)] if v else None
            by[st] = {"n": len(L), "whole": sum(o["box_in_frame"] for o in L), "fill_h": mm("fill_h"), "top": mm("top"),
                      "bottom": mm("bottom"), "aim_frac": mm("aim_frac"), "eye_aim_m": mm("eye_aim_m"),
                      "eye_view_err": mm("eye_view_err"), "eye_in_body": sum(o["eye_in_body"] for o in L),
                      "behind_near": sum(1 for o in L if o["behind_near"]), "d_eye_max": mm("d_eye_m"),
                      "d_fwd_max": mm("d_fwd_deg"), "d_origin_max": mm("d_origin_m"),
                      "snaps": sum(o["snap"] for o in L),
                      "collapsed": sum(o["collapsed"] for o in L),
                      "surface": swim_judge([o.get("eye_over_surf_m") for o in L])}
        summ = {"s": s_, "ticks": len(out), "scored": sum("missing" not in o for o in out), "by_state": by}
        import fcntl   # POSIX's own (tests/test_contracts.py)
        with (self.s.ev / "results" / "frames.jsonl").open("a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(json.dumps({"case": self._case, "label": label, "sandbox": self.s.name, **summ,
                                 "per_tick": out}) + "\n")
        self.frame_sums[label or f"capture-{len(self.frame_sums)}"] = summ
        return summ

    def priv_trace(self, label: str, rows: list[dict]) -> str:
        """The centre and the fall reference per tick, into the sitting's private folder only (0600): the
        lane-against-main check (``trace_cmp``)."""
        p = self.s.private / f"trace-{label}.json"
        L = [(r["k"], r["state"], list(r["c"]), (r["x"].get("f168_dc") or 0.0) + r["c"][2]) for r in rows if r.get("c")]
        p.write_text(json.dumps(L), encoding="utf-8")
        os.chmod(p, 0o600)
        return p.name

    def trace_cmp(self, lane: str, main: str) -> dict:
        """The lane-against-main check (2.105's trace_cmp.py) on two of this sitting's traces (``priv_trace``'s labels,
        e.g. ``<rid>-T``: both rows on one serve, whose private folder teardown deletes): per tick both have, the
        ticks whose state differs, the centre's and the fall reference's (+0x168) largest difference and the ticks
        over 1 mm. Differences only, never a position."""
        A, B = ({k: (st, c, f) for k, st, c, f in json.loads((self.s.private / f"trace-{x}.json").read_text(
            encoding="utf-8"))} for x in (lane, main))
        ks = sorted(set(A) & set(B))
        dc, df = [math.dist(A[k][1], B[k][1]) for k in ks], [abs(A[k][2] - B[k][2]) for k in ks]
        return {"ticks": len(ks), "lane": len(A), "main": len(B), "state_differs": sum(A[k][0] != B[k][0] for k in ks),
                "centre_max_m": round(max(dc, default=0.0), 6), "f168_max_m": round(max(df, default=0.0), 6),
                "over_1mm": {"centre": sum(v > 0.001 for v in dc), "f168": sum(v > 0.001 for v in df)}}

    # -- f3's zipline -------------------------------------------------------------------------------------------------
    def zip_teleport(self, label: str, letgo_at: int = 50) -> dict:
        """The teleport start: R6 onto the zipline spot [placed], 60 ticks from the teleport with the camera; the
        stick free and the camera back; one capture: Y at k3 (hang_start, the ride), Y at ``letgo_at`` (the let-go), to
        k100; per tick the offsets, the camera, the sweeps."""
        sp = self.spot(ZIP)
        self.player()
        self.ensure_tick()
        self.place_feet(sp)
        c1, arr = self.cap_cam(60, {}, f"{label}-T-arrive")
        fr = self.free(900)
        if (a := sp.get("cam")) is not None:
            self.cam_back(a)
        c2, cz = self.cap_cam(100, {3: "down y", 6: "up y", letgo_at: "down y", letgo_at + 2: "up y"}, f"{label}-T-zip")
        rows = c2["rows"]
        i = i_letgo(rows)
        kl = rows[i]["k"] if i else None
        out = {"free": fr, "arrive": cam_judge(arr["per_tick"], c1["rows"], lambda k: k >= 5),
               "zip": zip_summary(rows), "phases": _phases(rows, 12),
               "hang_cam": cam_judge(cz["per_tick"], rows, lambda k: rows[k]["state"] == 0x105),
               "ride_cam": cam_judge(cz["per_tick"], rows, lambda k: rows[k]["state"] == 5),
               "letgo": steps_from(rows, i - 1) if i else None,
               "after_letgo_cam": cam_judge(cz["per_tick"], rows, lambda k: kl is not None and kl <= k < kl + 4),
               "s2_eased_cam": cam_judge(cz["per_tick"], rows, lambda k: rows[k]["state"] == 2
                                         and (rows[k]["x"].get("o1") or [0, 0, 0])[2] < -1.25),
               "trace": self.priv_trace(label + "-T", rows)}
        print(f"  {label} T arrive {out['arrive']}\n  {label} T zip {out['zip']}\n  {label} T ride cam {out['ride_cam']}")
        print(f"  {label} T let-go {out['letgo']} after {out['after_letgo_cam']} eased-s2 {out['s2_eased_cam']}")
        return out

    def walkin(self, label: str, back_m: float = 4.0, rest: int = 30) -> dict:
        """The walk-in start: R6 ``back_m`` behind the zipline spot facing it [placed], the stick free and the camera
        back at the state's yaw; then real input: the stick forward until 0.4 m from the spot, ``rest`` ticks at rest;
        the camera at rest judged."""
        self.placed(ZIP)
        _e, P = self.player()
        sp = self.spot(ZIP)
        yaw = 2 * math.atan2(sp["quat"][2], sp["quat"][3])
        fx, fy, cen = -math.sin(yaw), math.cos(yaw), sp["centre"]
        self.place_feet(sp, back_m)
        for _ in range(15):
            self.s.tick()
        fr = self.free(900)
        yw = self.cam_back(sp["cam"]) if sp.get("cam") is not None else None
        st = {"arr": None}

        def on(sb, row, rows):
            c = _v3(sb, P + 0x15C)
            left = (cen[0] - c[0]) * fx + (cen[1] - c[1]) * fy
            if st["arr"] is None and row["k"] >= 1 and left <= 0.4:
                st["arr"] = row["k"]
                return ["axis ly 0"]
            if (st["arr"] is not None and row["k"] >= st["arr"] + rest) or row["k"] > 150:
                return ["stop"]
        c, cz = self.cap_cam(200, {1: f"axis ly {xo.pipe_axis(1.0):.6f}"}, f"{label}-walkin", on_tick=on)
        out = {"free": fr, "yaw_wait": yw, "arr": st["arr"],
               "rest_cam": cam_judge(cz["per_tick"], c["rows"], lambda k: st["arr"] is not None and k >= st["arr"] + 5)}
        print(f"  {label} walk-in: arrived k{st['arr']}, rest cam {out['rest_cam']}")
        return out

    def _ride(self, on_state: dict, ride_n: int, after: int):
        """An on_tick for a ride from Y: ``ride_n`` ride ticks with no stick, then Y lets go, ``after`` ticks on."""
        def on(sb, row, rows):
            acts = []
            if row["state"] == 5:
                on_state["r"] += 1
                if on_state["r"] == ride_n and on_state["go"] is None:
                    on_state["go"] = row["k"]
                    acts.append("down y")
            if on_state["go"] is not None and row["k"] == on_state["go"] + 2:
                acts.append("up y")
            if on_state["go"] is not None and row["k"] >= on_state["go"] + after:
                acts.append("stop")
            return acts or None
        return on

    def _ride_cams(self, cz: dict, rows: list[dict]) -> dict:
        i = i_letgo(rows)
        kl = rows[i]["k"] if i else None
        return {"hang_cam": cam_judge(cz["per_tick"], rows, lambda k: rows[k]["state"] == 0x105),
                "ride_cam": cam_judge(cz["per_tick"], rows, lambda k: rows[k]["state"] == 5),
                "after_letgo_cam": cam_judge(cz["per_tick"], rows, lambda k: kl is not None and kl <= k < kl + 4),
                "s2_eased_cam": cam_judge(cz["per_tick"], rows, lambda k: rows[k]["state"] == 2
                                          and (rows[k]["x"].get("o1") or [0, 0, 0])[2] < -1.25)}

    def zip_walkin(self, label: str, back_m: float = 4.0, rest: int = 30, ride_n: int = 102, after: int = 10) -> dict:
        """Row 1's ride: the walk-in start, then Y, the ride for ``ride_n`` ticks with no stick, Y lets go, ``after``
        ticks on; the camera per tick."""
        wk = self.walkin(label + "-W", back_m, rest)
        st = {"r": 0, "go": None}
        c, cz = self.cap_cam(400, {2: "down y", 5: "up y"}, f"{label}-W-zip", on_tick=self._ride(st, ride_n, after))
        rows = c["rows"]
        i = i_letgo(rows)
        out = {"walkin": wk, "marks": dict(st, y=2), "zip": zip_summary(rows), "rest_cam": wk["rest_cam"],
               **self._ride_cams(cz, rows), "letgo": steps_from(rows, i - 1, 12) if i else None,
               "ride_seq": [(o["k"], o.get("act2_min"), o.get("act2_pitch"), o.get("aim2_min"), o.get("aim_dc"))
                            for o in cz["per_tick"] if rows[o["k"]]["state"] == 5][::5]}
        print(f"  {label} W marks {out['marks']} rest {out['rest_cam']}")
        print(f"  {label} W hang {out['hang_cam']} ride {out['ride_cam']} after let-go {out['after_letgo_cam']}")
        return out

    def zip_placed(self, label: str, ride_n: int = 102, after: int = 24) -> dict:
        """The ride with the camera per tick from the zipline spot [placed]: Y at k3, ``ride_n`` ride ticks with no
        stick, then Y lets go, ``after`` ticks on."""
        pl = self.placed(ZIP)
        st = {"r": 0, "go": None}
        c, cz = self.cap_cam(ride_n + after + 40, {3: "down y", 6: "up y"}, f"{label}-ridecam",
                             on_tick=self._ride(st, ride_n, after))
        rows = c["rows"]
        i = i_letgo(rows)
        ride = [o for o in cz["per_tick"] if rows[o["k"]]["state"] == 5]
        r0 = ride[0]["k"] if ride else 0
        out = {"place": {k: pl.get(k) for k in ("off_m", "try")}, "ride_ticks": st["r"],
               "rest_cam": cam_judge(cz["per_tick"], rows, lambda k: k < 4), **self._ride_cams(cz, rows),
               "ride_seq": [(o["k"] - r0, o.get("act2_min"), o.get("act2_pitch"), o.get("aim2_min"), o.get("aim_dc"))
                            for o in ride][::5],
               "letgo": steps_from(rows, i - 1) if i else None,
               "s2_cam": cam_judge(cz["per_tick"], rows, lambda k: rows[k]["state"] == 2)}
        print(f"  {label} ride cam: rest {out['rest_cam']} hang {out['hang_cam']} ride {out['ride_cam']}")
        print(f"  {label} let-go {out['letgo']} after {out['after_letgo_cam']} eased-s2 {out['s2_eased_cam']}")
        return out

    def zip_to_end(self, label: str, n: int = 600, after: int = 0) -> dict:
        """The ride to the cable's end (no let-go) from the walk-in start, the camera per tick: the phases, the origin
        against the centre and its steps from the end on, the camera on the ride and in the 4 ticks after its end;
        with ``after``, on ``after`` ticks past the dismount's landing (its third tick at rest) at rest, the camera
        over them (``rest_cam``)."""
        wk = self.walkin(label + "-E")
        st = {"rest": None}

        def at_rest(sb, row, rows):
            if st["rest"] is None and row["k"] > 40 and row["state"] == 0 and len(rows) > 3 \
                    and all(r["state"] == 0 for r in rows[-3:]):
                st["rest"] = row["k"]
            return ["stop"] if st["rest"] is not None and row["k"] >= st["rest"] + after else None
        c, cz = self.cap_cam(n + after, {2: "down y", 5: "up y"}, f"{label}-zip-toend", on_tick=at_rest)
        rows = c["rows"]
        i = i_letgo(rows)
        cams = self._ride_cams(cz, rows)
        out = {"phases": _phases(rows, 14), "ride_ticks": sum(1 for r in rows if r["state"] == 5),
               "end": steps_from(rows, i - 1, 30) if i else None, "walkin": wk,
               "rest_cam": cam_judge(cz["per_tick"], rows, lambda k: k < 4), "hang_cam": cams["hang_cam"],
               "ride_cam": cams["ride_cam"], "after_end_cam": cams["after_letgo_cam"],
               "s2_eased_cam": cams["s2_eased_cam"], "trace": self.priv_trace(label + "-E", rows)}
        if after:
            out.update(rest_k=st["rest"], after_ticks=sum(1 for r in rows if st["rest"] is not None
                                                          and r["k"] > st["rest"]),
                       landed_cam=cam_judge(cz["per_tick"], rows, lambda k: st["rest"] is not None and k > st["rest"]))
        print(f"  {label} ride to the end: "
              f"{({k: v for k, v in out.items() if k not in ('ride_cam', 'rest_cam', 'hang_cam')})}")
        print(f"  {label} ride cam: rest {out['rest_cam']} hang {out['hang_cam']} ride {out['ride_cam']}")
        return out

    def zip_land(self, label: str, ride_n: int = 262, after: int = 90, fall: int = 150) -> dict:
        """A let-go that lands (Step 2.107, the skeptic's R1): the walk-in start, Y, ``ride_n`` ride ticks with no stick
        (the cable's end is about 277 on): Y lets go over the end's floor, then until its landing's third tick at rest
        (state 0) and ``after`` more, or a death (state 7: the fall missed the floor), or ``fall`` airborne ticks; the
        camera per tick: from the let-go, and from the landing on (``landed_cam``)."""
        wk = self.walkin(label + "-L")
        st = {"r": 0, "go": None, "rest": None, "dead": None, "air": 0}

        def on(sb, row, rows):
            acts = []
            if row["state"] == 5 and st["go"] is None:
                st["r"] += 1
                if st["r"] == ride_n:
                    st["go"] = row["k"]
                    acts.append("down y")
            if st["go"] is not None and row["k"] == st["go"] + 2:
                acts.append("up y")
            if st["go"] is not None and row["k"] > st["go"]:
                st["air"] += row["state"] == 2
                if st["rest"] is None and row["state"] == 0 and len(rows) > 3 and all(r["state"] == 0 for r in rows[-3:]):
                    st["rest"] = row["k"]
                if st["dead"] is None and row["state"] == 7:
                    st["dead"] = row["k"]
                if (st["rest"] is not None and row["k"] >= st["rest"] + after) or st["air"] > fall or (
                        st["dead"] is not None and row["k"] >= st["dead"] + 5):
                    acts.append("stop")
            return acts or None
        was, self.s.watching = self.s.watching, False   # a death's popup holds the tick (the row then ends there)
        try:
            c, cz = self.cap_cam(ride_n + 200 + after, {2: "down y", 5: "up y"}, f"{label}-zip-land", on_tick=on)
        finally:
            self.s.watching = was
        rows = c["rows"]
        i = i_letgo(rows)
        kl = rows[i]["k"] if i else None
        out = {"walkin": wk, "ride_n": ride_n, "letgo_k": kl, "rest_k": st["rest"], "dead_k": st["dead"],
               "air_ticks": st["air"], "phases": _phases(rows, 16), "stop": c["meta"]["stop"],
               "letgo": steps_from(rows, i - 1, 30) if i else None,
               "after_letgo_cam": cam_judge(cz["per_tick"], rows, lambda k: kl is not None and k >= kl),
               "landed_cam": cam_judge(cz["per_tick"], rows, lambda k: st["rest"] is not None and k > st["rest"])}
        print(f"  {label} let-go at ride {ride_n}: letgo k{kl} rest k{st['rest']} dead k{st['dead']} "
              f"air {st['air']} landed cam {out['landed_cam']}")
        if st["dead"] is not None:
            self.s.clear_dialog(12)
        return out

    def worn(self) -> dict:
        """The worn armor slot: its name, level and flaps."""
        sl = self.sb.read_u32(self.s.chain()["armor_mgr"] + 0x20)
        return {"slot": self.s.guest_str(self.sb.read_u32(sl), 24) if sl else None,
                "level": self.sb.read_i32(sl + 8) if sl else None, "flaps": self.sb.read_i32(sl + 0x38) if sl else None}

    def cast_air(self, level: int = 3) -> dict:
        """R2: air at ``level``, the other elements 1, each fuel to its cap [placed]; then the cast by real input: LT
        held, Y, LT released; the worn slot read back."""
        self.ensure_tick()
        self.s.kit(air=level, earth=1, fire=1, water=1)
        inv = self.s.chain()["inv"]
        for i in range(4):
            self.sb.write_i32(inv + 0x1C + 0xC * i, max(self.sb.read_i32(inv + 0x20 + 0xC * i), 100))
        w0 = self.worn()
        self.s.capture(40, {2: "trigger lt 1", 8: "down y", 10: "up y", 16: "trigger lt 0"}, label=None, body=False,
                       hold_hp=200)
        return {"before": w0, "after": self.worn()}

    def zip_flap(self, label: str, letgo_at: int = 50, flap_after: int = 2) -> dict:
        """The let-go then a wing flap ``flap_after`` ticks into state 2, with the air armor (cast at the spot after
        R2's kit [placed]): the origin against the centre per tick, its steps, the camera."""
        self.placed(ZIP)
        out = {"cast": self.cast_air(3)}
        self.placed(ZIP)
        st = {"s2": None}

        def on(sb, row, rows):
            if st["s2"] is None and row["k"] > letgo_at and row["state"] == 2:
                st["s2"] = row["k"]
            if st["s2"] is not None and row["k"] == st["s2"] + flap_after:
                return ["down y"]
            if st["s2"] is not None and row["k"] == st["s2"] + flap_after + 3:
                return ["up y"]
            if st["s2"] is not None and row["k"] >= st["s2"] + 30:
                return ["stop"]
        c, cz = self.cap_cam(130, {3: "down y", 6: "up y", letgo_at: "down y", letgo_at + 2: "up y"}, f"{label}-flap",
                             on_tick=on, hold_hp=200)
        rows = c["rows"]
        i = i_letgo(rows)
        out.update(phases=_phases(rows, 14), s2_k=st["s2"], flaps_used=[r.get("flaps_used") for r in rows[-1:]],
                   steps=steps_from(rows, i - 1, 34) if i else None,
                   cam=cam_judge(cz["per_tick"], rows, lambda k: i is not None and k >= rows[i]["k"]))
        print(f"  {label} let-go + flap: {out}")
        return out

    def zip_pics(self, label: str, marks=(1, 5, 30, 60), s2=(1, 4)) -> dict:
        """Pictures (a run of their own: the numbers come from the uninterrupted runs): the ride's ticks ``marks`` (by
        the state time +0x9C), Y lets go and the let-go's state-2 ticks 1 and 4, then the cable's end from a walk-in."""
        self.placed(ZIP)
        out = {}

        def until(pred, n, sched=None):
            return self.s.capture(n, sched or {}, label=None, fields={"x": self.xz443},
                                  on_tick=lambda sb, row, rows: ["stop"] if pred(sb, row) else None)
        for j, m in enumerate(marks):
            until(lambda sb, row, m=m: row["state"] == 5 and round(_f1(sb, row["ent"] + 0x9C) * 30) + 1 >= m, 400,
                  {2: "down y", 5: "up y"} if j == 0 else None)
            out[f"ride{m}"] = self.pic(f"{label}-ride{m}", 2)
        self.s.capture(3, {0: "down y", 2: "up y"}, label=None, body=False)
        n2 = {"n": 0}

        def in_s2(sb, row):
            n2["n"] += row["state"] == 2
            return n2["n"] >= 1
        until(in_s2, 20)
        out["letgo_s2_1"] = self.pic(f"{label}-letgo-s2-1", 2)
        self.s.capture(2, {}, label=None, body=False)
        out["letgo_s2_4"] = self.pic(f"{label}-letgo-s2-4", 2)
        self.s.capture(30, {}, label=None, body=False)
        out["walkin_end"] = self.walkin(label + "-P2")
        st = {"r": False}

        def ended(sb, row):
            st["r"] = st["r"] or row["state"] == 5
            return st["r"] and row["state"] != 5
        until(ended, 600, {2: "down y", 5: "up y"})
        out["end"] = self.pic(f"{label}-cable-end", 2)
        self.s.capture(30, {}, label=None, body=False)
        print(f"  {label} pictures {out}")
        return out

    # -- the floor under the centre (a guest call per tick) -----------------------------------------------------------
    def sweep_down(self, sb, crit: int, length: float = 8.0) -> dict:
        """collision_sweep (0x60870, stdcall 36) called at the halted player tick as 0x8AE10 calls it (the world's
        tree [[critter+0x154]+0xAC], the critter as self, 0, radii 0, mask 0x10, its hit record pre-set as 0x8AE10's)
        from the critter's centre +0x15C straight down ``length`` m, returning to the tick's own breakpoint; every
        register put back (the whole 'g' packet). Returns AL and the hit's fraction +0x18, or an error."""
        g = sb.g
        raw0 = g.cmd("g")
        r0 = g.regs()
        esp0, eip0 = r0["esp"], r0["eip"]
        rec, frm, top = (esp0 - 0x200) & ~0xF, (esp0 - 0x80) & ~0xF, (esp0 - 0x300) & ~0xF
        to = frm + 0x10
        cen = _v3(sb, crit + 0x15C)
        tree = sb.read_u32(sb.read_u32(crit + 0x154) + 0xAC)
        rb = bytearray(0x100)
        rb[0x20:0x24] = bytes([0x00, 0x80, 0x00, 0xCC])
        g.write(rec, bytes(rb))
        g.write(frm, struct.pack("<3f", *cen))
        g.write(to, struct.pack("<3f", cen[0], cen[1], cen[2] - length))
        g.write(top, struct.pack("<10I", eip0, tree, crit, 0, frm, to, 0, 0, 0x10, rec))
        le = lambda v: struct.pack("<I", v & 0xFFFFFFFF).hex()  # noqa: E731
        if not (g.cmd(f"P4={le(top)}") == b"OK" and g.cmd(f"P8={le(self.va(SWEEP_FN))}") == b"OK"):
            raw = bytearray(bytes.fromhex(raw0.decode()))   # no 'P': the whole packet with ESP and EIP changed
            raw[16:20], raw[32:36] = struct.pack("<I", top), struct.pack("<I", self.va(SWEEP_FN))
            if g.cmd(b"G" + raw.hex().encode()) != b"OK":
                return {"err": "no register write"}
        res = {"err": "no return"}
        try:
            for _ in range(12):
                g.cont()
                g.wait_stop(10.0)
                r1 = g.regs()
                if r1["eip"] == eip0 and r1["esp"] == top + 4 + 36:
                    res = {"al": r1["eax"] & 0xFF, "frac": round(_f1(sb, rec + 0x18), 5),
                           "nz": round(_f1(sb, rec + 0x14), 4), "fl": sb.read(rec + 0x20, 1)[0]}
                    break
        finally:
            if g.cmd(b"G" + raw0) != b"OK":
                raise RuntimeError("sweep_down: the registers were not put back (G refused)")
            r2 = g.regs()
            if (r2["eip"], r2["esp"]) != (eip0, esp0):
                raise RuntimeError("sweep_down: the registers differ after the restore")
        return res

    def floor_tick(self, length: float = 8.0):
        """An on_tick: per tick the cast ``length`` m down and the clock [critter+0xE4]+0x10 (a double), kept by k."""
        self.floor, self.floor_len = {}, length

        def f(sb, row, rows):
            c = sb.read_u32(row["ent"] + 0x20)
            o = self.sweep_down(sb, c, length)
            with _suppressed():
                o["clk"] = round(struct.unpack("<d", sb.read(sb.read_u32(c + 0xE4) + 0x10, 8))[0], 4)
            self.floor[row["k"]] = o
        return f

    def floor_rows(self, rows: list[dict]) -> list[dict]:
        """Per tick: state, the floor's depth under the centre (fraction x the cast's length; None: no floor within it),
        the hit's normal z and flags, the drawn lowest bone against the floor, the origin's offsets (o0 z, the drawn od z)
        from the centre, the clock."""
        out = []
        for r in rows:
            o = self.floor.get(r["k"], {})
            d = round(o["frac"] * self.floor_len, 3) if o.get("al") else None
            low = r["x"].get("low_vs_cen")
            out.append({"k": r["k"], "st": hex(r["state"]), "floor_below_c": d,
                        "low_vs_floor": round(low + d, 3) if (d is not None and low is not None) else None,
                        "nz": o.get("nz"), "fl": o.get("fl"), "o0_dz": r["x"]["o0"][2],
                        "od_dz": (r["x"].get("od") or r["x"]["o0"])[2], "clk": o.get("clk"), "err": o.get("err")})
        return out

    def zip_cast(self, label: str, length: float = 8.0) -> dict:
        """The floor cast on f3's whole ride [placed at the spot]: Y at k3, to the cable's end and 10 ticks after (only
        the player-tick breakpoint armed)."""
        self.placed(ZIP)
        c = self.s.capture(400, {3: "down y", 6: "up y"}, label=f"{label}-ridecast", fields={"x": self.xz},
                           on_tick=self.s.both(self.floor_tick(length), lambda sb, row, rows: ["stop"] if row["k"] > 40
                                               and len(rows) > 10 and all(r["state"] == 0 for r in rows[-10:]) else None))
        fr = self.floor_rows(c["rows"])
        out = {"n": len(fr), "phases": _phases(c["rows"], 14), "per_tick": fr, "errors": sum(1 for x in fr if x["err"])}
        print(f"  {label} ride cast: {len(fr)} ticks, errors {out['errors']}; every 10th: {fr[::10]}")
        return out

    # -- a1's ladder ----------------------------------------------------------------------------------------------------
    def setter_hits(self, c: dict) -> list[dict]:
        at = hex(self.va(SETTER))
        return [{"k": h["k"], "state": h["regs"]["ecx"], "anim": int(h["stack_u32"][1], 16), "caller": h["stack_u32"][0]}
                for h in c["hits"] if h["va"] == at]

    def ladder(self, label: str, jump_at: int | None = None, pics=()) -> dict:
        """a1's ladder [placed at the spot], the stick up (2.75a's run A): with ``jump_at``, Y at that climb tick (the
        stick let go), else on over the top; per tick the offsets (steps), the camera (X20 must not act); with
        ``pics`` (capture ticks), a second run of the same plan [placed] stopped at each for a picture."""
        a = self.spot(LADDER)["cam"]
        out = self._ladder(label, a, jump_at)
        if pics:
            out["pics"] = self._ladder(label, a, jump_at, pics)
        return out

    def _ladder(self, label: str, a: float, jump_at: int | None, pics=()) -> dict:
        st = {"climb": 0, "jk": None, "base": 0}

        def plan(k, s_):
            if k < 2 or k >= 330 or st["jk"] is not None:
                return None
            return (0.0, 1.0) if s_ in (1, 0x101) else "steer"
        stick = steer(a, lambda k, s_: plan(k + st["base"], s_))

        def on(sb, row, rows):
            k = row["k"] + st["base"]
            acts = stick(sb, row, rows) or []
            if row["state"] in (1, 0x101):
                st["climb"] += 1
            if jump_at is not None and st["jk"] is None and st["climb"] >= jump_at:
                st["jk"] = k
                acts = ["axis lx 0.000", "axis ly 0.000", "down y"]
            if st["jk"] is not None and k == st["jk"] + 3:
                acts.append("up y")
            if st["jk"] is not None and k >= st["jk"] + 60 or st.get("mark") is not None and k >= st["mark"]:
                acts.append("stop")
            return acts or None
        self.placed(LADDER)
        if pics:   # the pictures' run: stopped at each mark (its ticks counted on across the stops), a picture
            got = {}
            for m in sorted(pics):
                st["mark"] = m
                c = self.s.capture(m - st["base"] + 1, {}, label=None, fields={"x": self.xz}, on_tick=on)
                if not c["rows"]:
                    break
                last = c["rows"][-1]
                k_last, name = last["k"] + st["base"], f"{label}-ladder{'J' if jump_at else 'T'}-k{m}"
                got[m] = {"k": k_last, "state": hex(last["state"]), "pic": self.pic(name, 2)}
                st["base"] = k_last + 1 + ((self.pics.get(name) or {}).get("ticks") or 0)   # the picture's ticks ran too
                if k_last < m:
                    break   # the capture ended early (a hold, or the plan's own stop)
            print(f"  {label} ladder pictures: {got}")
            return got
        c, cz = self.cap_cam(360 if jump_at is None else 260, {}, f"{label}-ladder{'J' if jump_at else 'T'}",
                             extra={SETTER: None}, on_tick=on)
        rows = c["rows"]
        if jump_at is not None:
            i0 = next((j for j, r in enumerate(rows) if r["k"] == st["jk"]), None)
        else:
            i0 = max((j for j, r in enumerate(rows) if r["state"] in (1, 0x101)), default=None)
        allst = [round(math.dist(a_["x"].get("od", a_["x"]["o0"]), b_["x"].get("od", b_["x"]["o0"])), 3)
                 for a_, b_ in zip(rows, rows[1:])]
        out = {"phases": _phases(rows, 16), "climb_ticks": st["climb"], "jk": st["jk"], "setter": self.setter_hits(c)[:8],
               "leave": steps_from(rows, i0, 40) if i0 is not None else None, "max_step_all": max(allst) if allst else None,
               "big_steps": [(rows[j + 1]["k"], hex(rows[j + 1]["state"]), v) for j, v in enumerate(allst) if v > 0.85][:12],
               "cam": cam_judge(cz["per_tick"], rows, lambda k: True),
               "cam_after_leave": cam_judge(cz["per_tick"], rows, lambda k: i0 is not None and k >= rows[i0]["k"]),
               "pic": self.pic(f"{label}-ladder{'J' if jump_at else 'T'}-end", 2)}
        print(f"  {label} ladder {'jump at ' + str(jump_at) if jump_at else 'top'}: "
              f"{({k: v for k, v in out.items() if k != 'setter'})}")
        return out

    def ladder_cast(self, label: str, rest: int = 20) -> dict:
        """The floor cast at a1's ladder [placed at the spot]: ``rest`` ticks at its foot, then the stick up (run A)."""
        a = self.spot(LADDER)["cam"]

        def plan(k, s_):
            if k < rest or k >= 330:
                return None
            return (0.0, 1.0) if s_ in (1, 0x101) else "steer"
        self.placed(LADDER)
        c = self.s.capture(360, {}, label=f"{label}-laddercast", fields={"x": self.xz}, bps=[self.va(SETTER)],
                           on_tick=self.s.both(self.floor_tick(), steer(a, plan)))
        fr = self.floor_rows(c["rows"])
        out = {"n": len(fr), "phases": _phases(c["rows"], 14), "per_tick": fr, "setter": self.setter_hits(c),
               "errors": sum(1 for x in fr if x["err"])}
        print(f"  {label} ladder cast: {len(fr)} ticks, errors {out['errors']}; every 10th: {fr[::10]}")
        return out

    # -- fights: the critters near, the combo's readers -----------------------------------------------------------------
    def rd_t3(self, sb, r) -> dict:
        """0x4323C: a hit's target (EDX), attacker (the record EBX +4: its species, or "platform"), the target's HP and
        hit timer ``ht`` (+0x1E0: positive, the hit deals nothing) and ``ht4`` (+0x1E4, the window the last hit set)."""
        try:
            t, at = r["edx"], sb.read_u32(r["ebx"] + 4)
            o = {"target": t, "attacker": at, "target_hp": sb.read_i32(t + 0x210), "target_species": self.species(t),
                 "ht": round(_f1(sb, t + 0x1E0), 4), "ht4": round(_f1(sb, t + 0x1E4), 4)}
        except (OSError, ValueError) as e:
            return {"read_err": str(e)[:60]}
        if at:
            try:
                o["att_vt"] = hex(vt := sb.read_u32(at))
                o["att_sp"] = "platform" if vt == self.va(PLATFORM_VT) else self.species(at)
            except (OSError, ValueError):
                o["att_sp"] = "?"
        return o

    def rd_apply(self, sb, r) -> dict:
        """apply_damage's entry: the critter, its new HP and HP, its species."""
        try:
            t = sb.read_u32(r["esp"] + 4)
            return {"critter": t, "new_hp": sb.read_i32(r["esp"] + 8), "hp": sb.read_i32(t + 0x210),
                    "species": self.species(t)}
        except (OSError, ValueError) as e:
            return {"read_err": str(e)[:60]}

    @staticmethod
    def rd_q(sb, r) -> dict:
        try:
            m = sb.read_u32(r["esp"] + 8)
            return {"attacker": sb.read_u32(m + 4) if m else 0}
        except OSError as e:
            return {"read_err": str(e)[:60]}

    def rd_level(self, sb, r) -> dict:
        """0x30BD0's entry: the damage, the record's multiplier, the target's thresholds, species and HP."""
        try:
            t = sb.read_u32(r["edx"] + 0x20)
            spe = sb.read_u32(t + 0x178)
            return {"dmg": r["eax"], "rec_c": round(_f1(sb, r["ecx"] + 0xC), 4), "thr48": sb.read_i32(spe + 0x48),
                    "thr4c": sb.read_i32(spe + 0x4C), "t_species": self.s.guest_str(sb.read_u32(spe)),
                    "t_hp": sb.read_i32(t + 0x210), "target": t}
        except (OSError, ValueError) as ex:
            return {"read_err": str(ex)[:60]}

    def rd_lvl(self, sb, r) -> dict:
        """0x30C26 (after the light-hit compare, X18): the level EBX the chooser picked, ECX the hit record, EDI the
        target: whether the attacker is the world's player (+0xBC), the multiplier against the player critter's
        +0x224, the column PlayerControl+0x134 plays."""
        try:
            rec, t = r["ecx"], r["edi"]
            att = sb.read_u32(rec + 4)
            w = sb.read_u32(t + 0x154)
            wp = sb.read_u32(w + 0xBC) if w else 0
            o = {"lvl": r["ebx"], "att": att, "target": t, "mult": round(_f1(sb, rec + 0xC), 4),
                 "player_hit": bool(wp) and att == wp, "on_player": bool(wp) and t == wp, "t_sp": self.species(t)}
            if wp:
                o["mult_eq"] = sb.read_u32(rec + 0xC) == sb.read_u32(wp + 0x224)
                pc = sb.read_u32(wp + 0x180)
                o["col"] = sb.read_i32(pc + 0x134) if pc else None
            return o
        except (OSError, ValueError) as ex:
            return {"err": str(ex)[:60]}

    @staticmethod
    def rd_search(sb, r) -> dict:
        """0x7EF85, after 0x7EBB0: its result at [esp+0x18]: the count, the bearing, the angle, distance less radius,
        the target's features."""
        try:
            raw = sb.read(r["esp"] + 0x18, 0x20)
            return {"n": struct.unpack_from("<I", raw, 0)[0], "brg": round(struct.unpack_from("<f", raw, 0x10)[0], 3),
                    "ang": round(struct.unpack_from("<f", raw, 0x14)[0], 3),
                    "dr": round(struct.unpack_from("<f", raw, 0x18)[0], 3),
                    "feat": hex(struct.unpack_from("<I", raw, 0x1C)[0])}
        except OSError as ex:
            return {"err": str(ex)[:60]}

    @staticmethod
    def rd_row(sb, r) -> dict:
        """0x7F1A8: the row the search matched (ESI) and the column it leads to (its byte at EAX - 0xB)."""
        try:
            return {"row": r["esi"], "to_col": struct.unpack("<b", sb.read(r["eax"] - 0xB, 1))[0]}
        except OSError as ex:
            return {"row": r["esi"], "err": str(ex)[:40]}

    def rd_find(self, sb, r) -> dict:
        """0x7EBB0's entry (attack_target_find, stdcall: the critter [esp+4]): the live radius, its VA,
        PlayerControl+0x134 (the last move)."""
        try:
            crit = sb.read_u32(r["esp"] + 4)
            rv = sb.read_u32(self.va(RAD_OP) + 2)
            pc = sb.read_u32(crit + 0x180)
            return {"rad": round(_f1(sb, rv), 4), "rad_va": hex(rv), "col134": sb.read_i32(pc + 0x134) if pc else None,
                    "crit": crit}
        except (OSError, ValueError) as ex:
            return {"err": str(ex)[:60]}

    def combo_bps(self) -> tuple[list[int], dict]:
        """The combo's breakpoints and readers: hits, damage, the hit level, the transition search and its row, the
        target finder's entry, the staff's clank on a wall."""
        v = self.va
        rd = {v(HIT_T3): self.rd_t3, v(APPLY_DAMAGE): self.rd_apply, v(LEVEL_FN): self.rd_level, v(LVL_AT): self.rd_lvl,
              v(SEARCH_AT): self.rd_search, v(ROW_AT): self.rd_row, v(ROW_NONE): lambda sb, r: {"row": None},
              v(FIND_AT): self.rd_find, v(STAFF_CLANK): lambda sb, r: {"clank": True}}
        return list(rd), rd

    def watch_bps(self) -> tuple[list[int], dict]:
        """The hits and damage queries that name the critters near (an arena's)."""
        v = self.va
        rd = {v(DMG_QUERY): self.rd_q, v(HIT_T3): self.rd_t3, v(APPLY_DAMAGE): self.rd_apply}
        return list(rd), rd

    def rd_store(self, sb, r) -> dict:
        """0x43584 (X31's CALL where the build carries it, else the game's FLD/FST): the hit's target (EDX), the
        record's Delay [EAX+0x10] (f32, exact), the message's source ([EBP], 0x43266's &message.source) and whether its
        species carries the player flag (+0x64 bit 0x20, X8's and X31's test) or is the target."""
        try:
            t, src = r["edx"], sb.read_u32(r["ebp"])
            o = {"s_target": t, "s_rec": _f1(sb, r["eax"] + 0x10), "s_src_is_target": src == t, "s_src_player": None}
            if src:
                with _suppressed():
                    o["s_src_player"] = bool(sb.read(sb.read_u32(src + 0x178) + 0x64, 1)[0] & 0x20)
            return o
        except (OSError, ValueError) as e:
            return {"err": str(e)[:60]}

    @staticmethod
    def rd_wset(sb, r) -> dict:
        """0x43591 (the FSTP of the target's window): the target (EDX), the record's Delay (``ht_time``) and the
        target's +0x1E4, which the store (the game's FST, or X31's) wrote with the value the FSTP stores (f32, exact)."""
        try:
            return {"ht_target": r["edx"], "ht_time": _f1(sb, r["eax"] + 0x10), "w_1e4": _f1(sb, r["edx"] + 0x1E4)}
        except (OSError, ValueError) as e:
            return {"err": str(e)[:60]}

    @staticmethod
    def rd_wdone(sb, r) -> dict:
        """0x43597 (after the FSTP): the target (EDX) and its window +0x1E0 and +0x1E4 as stored (f32, exact)."""
        try:
            return {"w_target": r["edx"], "w_1e0": _f1(sb, r["edx"] + 0x1E0), "w_1e4": _f1(sb, r["edx"] + 0x1E4)}
        except (OSError, ValueError) as e:
            return {"err": str(e)[:60]}

    def window_bps(self) -> tuple[list[int], dict]:
        """X31's reads (Step 2.126; USA VAs, Europe unmapped): the Delay store, the window's FSTP and after it."""
        v = self.va
        rd = {v(HIT_STORE): self.rd_store, v(HT_SET): self.rd_wset, v(HT_DONE): self.rd_wdone}
        return list(rd), rd

    def rd_staff(self, sb, r) -> dict:
        """0x8CB52: player_staff_wall_check with this tick's two sampled ends stored (``STAFF_TIP``, ``STAFF_BUTT``),
        built from the staff node's pose times the critter's matrix at [esp+0x120], whose rows 0-2 0xA3860 scaled by
        +0x188 (X30: by 1.0): that matrix's scale (|row 0|), the critter's +0x188, the staff's length, and each end's
        offset (forward, side, up; m) in the critter's facing frame (+0x18C) from its body centre +0x15C and from the
        matrix's row 3 (the drawn origin), and the drawn origin's from the centre. Offsets only (Step 2.126)."""
        try:
            crit = r["edi"]
            M = struct.unpack("<16f", sb.read(r["esp"] + 0x120, 64))
            tip, butt, cen = _v3(sb, self.va(STAFF_TIP)), _v3(sb, self.va(STAFF_BUTT)), _v3(sb, crit + 0x15C)
            q4 = struct.unpack("<4f", sb.read(crit + 0x18C, 16))
            yaw = 2 * math.atan2(q4[2], q4[3])
            fx, fy = -math.sin(yaw), math.cos(yaw)
            org = M[12:15]

            def loc(p, o):
                dx, dy, dz = (p[i] - o[i] for i in range(3))
                return [round(dx * fx + dy * fy, 4), round(dx * fy - dy * fx, 4), round(dz, 4)]
            return {"crit": crit, "staff_sc": round(math.sqrt(M[0] ** 2 + M[1] ** 2 + M[2] ** 2), 4),
                    "sc188": round(_f1(sb, crit + 0x188), 4), "len": round(math.dist(tip, butt), 4),
                    "tip_c": loc(tip, cen), "butt_c": loc(butt, cen), "tip_o": loc(tip, org), "butt_o": loc(butt, org),
                    "org_c": loc(org, cen)}
        except (OSError, ValueError, struct.error) as e:
            return {"err": str(e)[:60]}

    def staff_bps(self) -> tuple[list[int], dict]:
        """X30's reads (Step 2.126; USA VAs): the staff check's sampled ends each tick it runs, and its clank."""
        v = self.va
        rd = {v(STAFF_ENDS): self.rd_staff, v(STAFF_CLANK): lambda sb, r: {"clank": True}}
        return list(rd), rd

    def critters(self, n: int = 6) -> dict[int, str]:
        """The critters drawn over ``n`` player ticks, by species: {critter: species}."""
        cmm = self.va(CMM)
        c = self.s.capture(n, {}, label=None, body=False, bps=[cmm],
                           bp_readers={cmm: lambda sb, r: {"critter": sb.read_u32(r["esp"] + 4)}}, chain=False)
        seen = {}
        for h in c["hits"]:
            if (t := h.get("critter")) and t not in seen:
                try:
                    seen[t] = self.species(t)
                except OSError:
                    pass
        return seen

    def find(self, want, n: int = 8, exact: bool = False) -> list[tuple]:
        """The drawn critters of the wanted species, nearest first: [(dist m, critter, species)]."""
        cr = self.critters(n)
        _e, P = self.player()
        cen = _v3(self.sb, P + 0x15C)
        out = []
        for t, sp in cr.items():
            if t == P or not sp or not ((sp in want) if exact else any(sp.startswith(w) for w in want)):
                continue
            with _suppressed():
                q = _v3(self.sb, t + 0x15C)
                if all(math.isfinite(v) for v in q):
                    out.append((round(math.dist(q, cen), 2), t, sp))
        return sorted(out)

    def place_exact(self, t: int, d_centre: float, turn: float = 0.0) -> float:
        """R6: the player ``d_centre`` m from critter ``t`` (horizontal, centre to centre), facing it [placed]; the
        distance after 3 ticks."""
        _e, P = self.player()
        p, q = _v3(self.sb, P + 0x15C), _v3(self.sb, t + 0x15C)
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        ux, uy = ((q[0] - p[0]) / d, (q[1] - p[1]) / d) if d > 1e-3 else (0.0, 1.0)
        face = math.atan2(uy, ux) - math.pi / 2
        self.ensure_tick()
        self.s.apply(recipes.place(self.sb.read_u32, (q[0] - d_centre * ux, q[1] - d_centre * uy, p[2] - 1.0 + 0.05),
                                   face + turn, entity=self.player()[0], va=self.s._va))
        for _ in range(3):
            if self.s.tick() is None:
                self.s.clear_dialog()
        p2, q2 = _v3(self.sb, P + 0x15C), _v3(self.sb, t + 0x15C)
        return round(math.hypot(q2[0] - p2[0], q2[1] - p2[1]), 3)

    def ground(self, limit: int = 30) -> int:
        """Player ticks until two in state 0 (a placement that left the body in the air lands first)."""
        st = {"n": 0}

        def f(sb, row, rows):
            st["n"] = st["n"] + 1 if row["state"] == 0 else 0
            if st["n"] >= 2:
                return ["stop"]
        return self.s.capture(limit, {}, label=None, on_tick=f, body=False, chain=False)["meta"]["rows"]

    def cheat_nodmg(self) -> dict:
        """The game's own no-damage code (``Sitting.cheat``, real pad input at the cheat tick) [placed by input]; its
        code holds a WHITE press, which X36 takes as a set press, so the build's set goes back to its first
        (``attack_set``; Step 2.189a: sitting 2.175a's beam557 row and 2.189a's town_male_6 rows played set 2)."""
        try:
            self.ensure_tick()
            out = self.s.cheat("no_damage")
            if self.sets:
                out["set"] = self.attack_set(0)
            return out
        except (Exception, SystemExit) as e:  # noqa: BLE001
            return {"err": f"{type(e).__name__}: {str(e)[:120]}"}

    def attack_set(self, want: int, tries: int = 8) -> dict:
        """X36's set to ``want`` (0 the game's combo) by WHITE presses while the player idles, each read back from the
        search landing's state (``sets_at``); the sets, the set it ends on and each read, and ``err`` when ``tries``
        presses didn't reach it (Step 2.189a: a row in the wrong set is no row; ``combo`` stops on it)."""
        va, n = self.sets
        seen = [self.sb.read_i32(va)]
        while seen[-1] != want and len(seen) <= tries:
            self.ensure_tick()
            self.s.capture(12, {2: "down white", 5: "up white"}, label=None, body=False, hold_hp=200)
            seen.append(self.sb.read_i32(va))
        out = {"sets": n, "set": seen[-1], "seen": seen}
        if seen[-1] != want:
            out["err"] = f"attack set {want} not reached in {tries} WHITE presses (read {seen})"
        return out

    def swings(self, rows: list[dict], hits: list[dict], P: int) -> list[dict]:
        """Per swing (``segs``): column, ticks, +0xFC/+0xEC/+0x104/+0x100 and clip at its start, its first damage tick
        and drops (the player's hits), the next swing when it follows at once (the chain, or a replay) and its chain
        tick, each critter it hit at its last tick (stun, distance less radius, bearing), the stunned candidates
        within 3 m, and the hit levels and searches inside it; ``blocked``, its hits that met a target's running hit
        timer (no damage: 0x4323C's gate), and ``clank``, the tick the staff hit a wall (the move ends undamaging).
        A swing's hits are those over its ticks and the tick after its last; a hit at the tick one swing ends and the
        next (contiguous) one starts is the ending swing's only, so a sum over swings counts each hit once (Step
        2.132's record: both swings held it, and main's guard_air on a sleeth read 19.20 HP/s for 14.40)."""
        hit_t3, apply_, lvl_fn, lvl_at = (hex(self.va(x)) for x in (HIT_T3, APPLY_DAMAGE, LEVEL_FN, LVL_AT))
        clanks = sorted(h["k"] for h in hits if h["va"] == hex(self.va(STAFF_CLANK)))
        cands, byk = self.cands, {r["k"]: r for r in rows}

        def dr(t, info):
            return round(info[2] - RADIUS.get(cands.get(int(t, 16)), 0.7), 3)
        t3 = [h for h in hits if h["va"] == hit_t3 and h.get("attacker") == P]
        ap = {(h["k"], h.get("critter")): h["hp"] - max(h["new_hp"], 0) for h in hits
              if h["va"] == apply_ and h.get("critter") != P and "hp" in h}
        dmg = {}
        for h in hits:
            if h["va"] == lvl_fn and "dmg" in h:
                dmg.setdefault((h["k"], h["target"]), h["dmg"])
        lv = []
        for h in hits:
            if h["va"] != lvl_at or "lvl" not in h:
                continue
            later = (byk.get(h["k"] + 3) or {}).get("x", {}).get("tg", {}).get(hex(h["target"]))
            lv.append({"k": h["k"], "lvl": h["lvl"], "sp": h.get("t_sp"), "mult": h.get("mult"), "mult_eq": h.get("mult_eq"),
                       "col": h.get("col"), "player_hit": h.get("player_hit"), "dmg": dmg.get((h["k"], h["target"])),
                       "stun3": later[0] if later else None})
        se = self.searches(hits)
        sw, out = segs(rows), []
        for i, w in enumerate(sw):
            k0, k1 = w["k0"], w["k0"] + w["ticks"]
            xe, x0 = byk[k1 - 1]["x"], byk[k0]["x"]
            nxt = sw[i + 1] if i + 1 < len(sw) and sw[i + 1]["contig"] and sw[i + 1]["k0"] == k1 else None
            lo = k0 + 1 if i and w["contig"] and sw[i - 1]["k0"] + sw[i - 1]["ticks"] == k0 else k0
            mine = [h for h in t3 if lo <= h["k"] <= k1]
            tg, col = xe.get("tg", {}), w["key"][0]
            first = (mine[0]["k"] - k0) if mine else None
            out.append({"k0": k0, "col": col, "name": COLS[col] if 0 <= col < len(COLS) else None, "ticks": w["ticks"],
                        "fc": x0["fc"], "first_hit_tick": first,
                        "drops": [(h["k"] - k0, ap[(h["k"], h["target"])], cands.get(h["target"]) or h.get("target_species"))
                                  for h in mine if (h["k"], h["target"]) in ap],
                        "end_frac": xe.get("frac"), "next": nxt["key"][0] if nxt else None, "chained": bool(nxt),
                        "hit_at_end": {cands.get(int(t, 16), "?"): {"stun": tg[t][0], "d_minus_r": dr(t, tg[t]),
                                                                    "bearing": tg[t][4]}
                                       for t in sorted({hex(h["target"]) for h in mine}) if t in tg},
                        "stunned_within_3m": sorted((cands.get(int(t, 16), "?"), dr(t, v), v[4]) for t, v in tg.items()
                                                    if v[0] and dr(t, v) <= 3.0),
                        "mult": x0.get("mult"), "rate": x0.get("rate"), "end2": x0.get("end2"),
                        "clip": hex(x0.get("clip") or 0), "chain_tick": w["ticks"] if nxt else None,
                        "gap": (w["ticks"] - first) if nxt and first is not None else None,
                        "levels": [(lv_["k"] - k0, lv_["lvl"], lv_["sp"], lv_["mult"], lv_["mult_eq"], lv_["col"],
                                    lv_["dmg"], lv_["stun3"]) for lv_ in lv if lv_["player_hit"] and lo <= lv_["k"] <= k1],
                        "search": [(k - k0, v) for k, v in sorted(se.items()) if k0 <= k <= k1 + 1],
                        "blocked": [(h["k"] - k0, cands.get(h["target"]) or h.get("target_species"), h["ht"])
                                    for h in mine if (h.get("ht") or 0) > 0],
                        "clank": next((k - k0 for k in clanks if k0 <= k < k1), None)})
        return out

    def searches(self, hits: list[dict]) -> dict:
        """Per tick k: the search's result (0x7EF85) and the row it matched (0x7F1A8; "none": the last row)."""
        search, row_at, row_none = (hex(self.va(x)) for x in (SEARCH_AT, ROW_AT, ROW_NONE))
        out = {}
        for h in hits:
            if h["va"] == search:
                out.setdefault(h["k"], {}).update(s={x: h.get(x) for x in ("n", "brg", "ang", "dr", "feat")})
            elif h["va"] == row_at:
                out.setdefault(h["k"], {}).update(row=h.get("row"), to_col=h.get("to_col"))
            elif h["va"] == row_none:
                out.setdefault(h["k"], {}).update(row="none")
        return out

    def finds(self, hits: list[dict], P: int) -> dict:
        """Per tick k: 0x7EBB0's calls by the player (radius, +0x134 each)."""
        at, out = hex(self.va(FIND_AT)), {}
        for h in hits:
            if h.get("va") == at and h.get("crit") == P:
                out.setdefault(h["k"], []).append((h.get("rad"), h.get("col134")))
        return out

    def hp_up(self, cands) -> dict[int, int]:
        """Each candidate's HP to its max (at least 100) [placed]: {critter: the HP held}."""
        hp0 = {}
        for t in cands:
            with _suppressed():
                hm = self.sb.read_i32(t + 0x214)
                hp0[t] = max(self.sb.read_i32(t + 0x210), hm if 0 < hm < 10000 else 100)
                self.sb.write_i32(t + 0x210, hp0[t])
        return hp0

    # -- e7's combo -----------------------------------------------------------------------------------------------------
    def arena_for(self, want) -> tuple:
        """e7's keylord arena (``Arena``: placed, the approach) and the nearest live critter of ``want`` (the arena's
        and the drawn ones, within 10 m, waiting in 40-tick idles); none near: R6 beside a spawn of the first
        (``NodeArena``)."""
        A = Arena(self)
        if (near := self.nearest_of(A, want)) is None:
            A = NodeArena(self, "levels/earth/e7", want[0])
            near = self.nearest_of(A, want, waits=3)
        return A, near

    def nearest_of(self, A, want, waits: int = 10):
        for _ in range(waits):
            p = A.my_pos()
            es = [(math.hypot(q[0] - p[0], q[1] - p[1]), t, sp, hp, q) for t, sp, hp, q in A.enemies() if sp in want]
            with _suppressed():
                for _d, t, sp in self.find(want, n=8, exact=True):
                    hp, q = self.sb.read_i32(t + 0x210), _v3(self.sb, t + 0x15C)
                    if hp > 0 and all(math.isfinite(v) for v in q) and abs(q[2] - p[2]) < 3.0:
                        es.append((math.hypot(q[0] - p[0], q[1] - p[1]), t, sp, hp, q))
                        A.seen.add(t)
            for w in want:
                if cand := sorted(e for e in es if e[2] == w and e[0] <= 10.0):   # a far one: a stale or wrong cell
                    return cand[0]
            b, rd = self.watch_bps()
            A.collect(self.s.capture(40, {}, label=None, body=False, hold_hp=200, bps=b, bp_readers=rd))
        return None

    def combo_setup(self, want, d_centre: float, dr: float | None) -> dict | None:
        """A run's set-up: the arena, the nearest live target, R6 ``d_centre`` from it facing it (or its radius plus
        ``dr``) [placed], ground; the candidates' HP to their max [placed] and their checked hold (AZ-530)."""
        A, near = self.arena_for(want)
        if near is None:
            return None
        d, t, sp, hp, q = near
        dc = (dr + RADIUS.get(sp, 0.7)) if dr is not None else d_centre
        d_after = self.place_exact(t, dc)
        self.ground()
        _e, P = self.player()
        cands = {t_: sp_ for t_, sp_, _h, _q in A.enemies() if _SPECIES.fullmatch(sp_)}
        with _suppressed():
            cands.update({t_: sp_ for t_, sp_ in self.critters(6).items() if t_ != P and sp_ in RADIUS})
        self.cands = cands
        log: list = []
        hp0 = self.hp_up(cands)
        return {"P": P, "t": t, "sp": sp, "hp": hp, "d": d, "dc": dc, "d_after": d_after, "cands": cands, "log": log,
                "hold": self.s.hold_targets(hp0, log)}

    def combo_run(self, label: str, ri: int, ctx: dict, n: int, every: int, first: int = 2) -> dict:
        """The run's combo (A every ``every`` ticks from tick ``first`` for ``n`` ticks; the combo's breakpoints),
        the candidates' HP held (checked), then 40 ticks to rest."""
        sched = {}
        for k in range(first, n - 4, every):
            sched[k], sched[k + 2] = "down a", "up a"
        b, rd = self.combo_bps()
        c = self.s.capture(n, sched, label=f"{label}-combo-{ri}", fields={"x": self.xcombo}, bps=b, bp_readers=rd,
                           hold_hp=200, on_tick=ctx["hold"])
        self.s.capture(40, {}, label=None, body=False, hold_hp=200,
                       on_tick=lambda sb, row, rows: ["stop"] if row["state"] in (0, 3) and row["k"] > 2 else None)
        return c

    def combo(self, label: str, runs_n: int = 8, n: int = 150, every: int = 6, d_centre: float = 1.4,
              want=("keylord", "overlord"), dr: float | None = None, nodmg: bool = True,
              same_state: bool = False) -> dict:
        """Rows 2 and 6 (e7, the keylord arena): ``runs_n`` runs of ``combo_run``; per run each swing judged
        (``judge_swings``), the stun runs, the radius, the finder's calls, the HP writes skipped; a lost tick ends the
        row (the watcher), its runs so far in the hold. Each run carries the world on from the one before, unless
        ``same_state`` (Step 2.189a, AZ-712): then each starts from the row's own state after the cheat (an in-memory
        checkpoint, restored), its first press ``ri`` ticks later than run 0's, so a lane's run and main's start
        alike."""
        out = {"cheat": self.cheat_nodmg() if nodmg else None, "runs": []}
        if (err := ((out["cheat"] or {}).get("set") or {}).get("err")):
            out["err"] = err   # the wrong attack set: no runs (Step 2.189a)
            return out
        if same_state:
            self.ensure_tick()
            out["same_state"] = {"save": self.sb.checkpoint_save(SAME_STATE), "ram": self.sb.ram_digest()}
        try:
            ri, ctx = 0, None
            while ri < runs_n:
                if same_state and ri:
                    self.sb.checkpoint_restore(SAME_STATE)
                    self.ensure_tick()
                if ctx is None:
                    ctx = self.combo_setup(want, d_centre, dr)
                if ctx is None:
                    out["runs"].append({"run": ri, "note": f"no live {want} seen"})
                    break
                c = self.combo_run(label, ri, ctx, n, every, 2 + ri if same_state else 2)
                P = ctx["P"]
                sw, fi = self.swings(c["rows"], c["hits"], P), self.finds(c["hits"], P)
                rads = sorted({r["x"].get("rad") for r in c["rows"]} - {None})
                o = {"run": ri, "first_press": 2 + ri if same_state else 2, "target": ctx["sp"],
                     "d_centre_set": round(ctx["dc"], 3), "d_after": ctx["d_after"],
                     "cands": sorted(ctx["cands"].values()), "swings": sw, "judge": judge_swings(sw, fi),
                     "stun_runs": stun_runs(c["rows"], self.cands), "rad_ticks": rads, "hp_log": ctx["log"][:20],
                     "finds": sorted(Counter(len(v) for v in fi.values()).items()),
                     "far_unstunned": [(k, v) for k, v in self.searches(c["hits"]).items()
                                       if (v.get("s") or {}).get("n") and ((v["s"].get("dr") or 0) > 3.0)
                                       and not (int(v["s"]["feat"], 16) & 0x18000)][:6]}
                out["runs"].append(o)
                print(f"  {label} run {ri} vs {ctx['sp']} (set {ctx['dc']:.2f}, after {ctx['d_after']}): rad {rads} "
                      f"finds {o['finds']} hp_log {ctx['log'][:4]} far_unstunned {o['far_unstunned']}")
                for w in o["judge"]:
                    print("     ", w)
                self.cands = {}
                ri, ctx = ri + 1, None
                if ri < runs_n and not same_state:
                    ctx = self.combo_setup(want, d_centre, dr)
        except self.s.Hold as h:
            h.info["runs"] = out["runs"]
            raise
        finally:
            self.cands = {}
        out["pic"] = self.pic(f"{label}-combo-end", 2)
        return out

    # -- f6's lone blaze sentinel ---------------------------------------------------------------------------------------
    def sentinel(self) -> tuple:
        """f6's vanilla-enemy arena (``SpotArena``) and its live blaze sentinel (the nearest, else a drawn one)."""
        A = SpotArena(self, SENTINEL)
        near = A.nearest()
        if near is None or "blaze_sentinel" not in str(near[2]):
            p = A.my_pos()
            for _d, t, sp in self.find(("blaze_sentinel",), n=8):
                if (hp := self.sb.read_i32(t + 0x210)) > 0:
                    q = _v3(self.sb, t + 0x15C)
                    near = (math.hypot(q[0] - p[0], q[1] - p[1]), t, sp, hp, q)
                    break
        return A, near

    def sentinel_runs(self, label: str, dr: float = 3.6, runs_n: int = 4, n: int = 120, every: int = 6) -> dict:
        """Row 3 at f6's lone blaze sentinel (the cheat on): the player placed so its distance less radius (1.0) is
        ``dr``, facing it [placed]; A every ``every`` ticks for ``n`` ticks; per search 0x7EBB0's calls, the result
        and the row; the HP held (the target's checked)."""
        out = {"runs": []}
        for ri in range(runs_n):
            try:
                _A, near = self.sentinel()
                if near is None:
                    out["runs"].append({"note": "no sentinel"})
                    continue
                t = near[1]
                d_after = self.place_exact(t, dr + 1.0)
                self.ground()
                _e, P = self.player()
                self.cands, log = {t: "blaze_sentinel"}, []
                hold = self.s.hold_targets(self.hp_up([t]), log)
                sched = {}
                for k in range(2, n - 4, every):
                    sched[k], sched[k + 2] = "down a", "up a"
                b, rd = self.combo_bps()
                c = self.s.capture(n, sched, label=f"{label}-sent-dr{dr}-{ri}", fields={"x": self.xcombo}, bps=b,
                                   bp_readers=rd, hold_hp=200, on_tick=hold)
                sw, fi = self.swings(c["rows"], c["hits"], P), self.finds(c["hits"], P)
                o = {"run": ri, "dr": dr, "d_after": d_after, "judge": judge_swings(sw, fi),
                     "stun_runs": stun_runs(c["rows"], self.cands), "finds": sorted(fi.items())[:40],
                     "rad_ticks": sorted({r["x"].get("rad") for r in c["rows"]} - {None}), "hp_log": log[:10]}
                out["runs"].append(o)
                print(f"  {label} sentinel dr {dr} run {ri} (after {d_after}): rad {o['rad_ticks']} stun {o['stun_runs']}")
                for w in o["judge"]:
                    print("     ", w)
                self.cands = {}
                self.s.capture(40, {}, label=None, body=False, hold_hp=200)
            except Exception as ex:  # noqa: BLE001  (a run's failure is its record; a hold ends the row)
                out["runs"].append({"run": ri, "err": f"{type(ex).__name__}: {str(ex)[:120]}"})
                self.cands = {}
        return out

    def sentinel_press(self, label: str, dr: float = 3.6, fwd: bool = False) -> dict:
        """The break row: a fresh press at ``dr`` on the sentinel still stunned from a combo that ended without its
        finisher (one A: basic1 hits and stuns it; back to rest), then A again while it is stunned (with ``fwd`` the
        stick forward from 2 ticks before the press to its search): the calls, +0x134, the result and the row."""
        near = None
        for _ in range(3):   # the sentinel back in reach of the spot's arena (a finisher pushes it away)
            _A, near = self.sentinel()
            if near is not None:
                break
            self.s.capture(60, {}, label=None, body=False, hold_hp=200)
        if near is None:
            return {"note": "no sentinel"}
        t = near[1]
        d_after = self.place_exact(t, dr + 1.0)
        self.ground()
        _e, P = self.player()
        self.cands, log = {t: "blaze_sentinel"}, []
        hold = self.s.hold_targets(self.hp_up([t]), log)
        st = {"rest": None, "press": None}

        def on(sb, row, rows):
            acts = []
            hold(sb, row, rows)
            stun = bool(sb.read_u32(t + 0x168) & 0x8000)
            if st["rest"] is None and row["k"] > 6 and row["state"] == 0:
                st["rest"] = row["k"]
            if st["rest"] is not None and st["press"] is None and row["k"] >= st["rest"] + 2:
                if fwd and row["k"] == st["rest"] + 2:
                    acts += ["axis ly 1.000"]
                if row["k"] >= st["rest"] + (4 if fwd else 2):
                    st["press"], st["stun_at_press"] = row["k"], stun
                    acts += ["down a"]
            if st["press"] is not None and row["k"] == st["press"] + 2:
                acts += ["up a", "axis ly 0.000"]
            if st["press"] is not None and row["k"] >= st["press"] + 40:
                acts += ["stop"]
            return acts or None
        b, rd = self.combo_bps()
        c = self.s.capture(200, {2: "down a", 4: "up a"}, label=f"{label}-fresh{'F' if fwd else ''}",
                           fields={"x": self.xcombo}, bps=b, bp_readers=rd, hold_hp=200, on_tick=on)
        fi, se, kp = self.finds(c["hits"], P), self.searches(c["hits"]), st["press"]
        after = {k: v for k, v in se.items() if kp is not None and k >= kp}
        first = min(after) if after else None
        out = {"d_after": d_after, "rest_k": st["rest"], "press_k": kp, "stun_at_press": st.get("stun_at_press"),
               "first_combo": [(k, v.get("row"), (v.get("s") or {}).get("n")) for k, v in sorted(se.items())
                               if kp is None or k < kp][:6],
               "fresh_search": (first, after.get(first)) if first is not None else None,
               "fresh_calls": fi.get(first) if first is not None else None,
               "col134_at": [(k, v) for k, v in sorted(fi.items()) if kp is not None and k >= kp][:4],
               "swings": [(w["name"], w["ticks"]) for w in self.swings(c["rows"], c["hits"], P)],
               "stun_runs": stun_runs(c["rows"], self.cands), "hp_log": log[:6]}
        print(f"  {label} fresh press{' (stick forward)' if fwd else ''}: {out}")
        self.cands = {}
        return out

    # -- f6's ground, a1's pit and wall, w1's water (2.104's and 2.105's break rows; Step 2.107's grid) ------------------
    def ground_cam(self, label: str, spot: str = FLAT_SPOT, n: int = 40, stick: float = 0.0) -> dict:
        """Open ground [placed at ``spot``]: ``n`` ticks with the camera per tick, at rest, or with ``stick`` (a
        ControllerState magnitude: 0.5 a walk, 1.0 a run) along the state's camera yaw from k2; then a picture
        (2.104's ground_cam104)."""
        pl = self.placed(spot)
        a = self.spot(spot).get("cam")

        def on(sb, row, rows):
            if not stick or a is None or row["k"] < 2:
                return None
            d = a - _cam_yaw(sb)
            return [f"axis lx {xo.pipe_axis(-math.sin(d) * stick):.6f}", f"axis ly {xo.pipe_axis(math.cos(d) * stick):.6f}"]
        tag = "rest" if not stick else f"stick{stick:g}"
        c, cz = self.cap_cam(n, {}, f"{label}-{spot}-{tag}", on_tick=on)
        out = {"place": {k: pl.get(k) for k in ("off_m", "try")}, "by_state": cz["by_state"],
               "speed": round(math.hypot(c["rows"][-1].get("vx") or 0.0, c["rows"][-1].get("vy") or 0.0), 3),
               "pic": self.pic(f"{label}-{spot}-{tag}", 2)}
        print(f"  {label} ground cam at {spot} ({tag}): {out}")
        return out

    def jump(self, label: str, spot: str = FLAT_SPOT, sched: dict | None = None, n: int = 60, tag: str = "jump",
             flap: bool = False) -> dict:
        """A jump at rest on open ground [placed] (Y at k2; with ``flap`` the air armor cast first and Y again at
        k10): per tick the origin against the centre (o1 at -1.0 in state 2: X20 not acting), its steps, the camera
        (2.105's jump105)."""
        out = {}
        if flap:
            self.placed(spot)
            out["cast"] = self.cast_air(3)
        self.placed(spot)
        sc = sched or ({2: "down y", 5: "up y", 10: "down y", 13: "up y"} if flap else {2: "down y", 5: "up y"})
        c, cz = self.cap_cam(n, sc, f"{label}-{tag}", hold_hp=200, on_tick=lambda sb, row, rows: ["stop"] if row["k"] > 12
                             and row["state"] == 0 and rows[-2]["state"] == 0 else None)
        rows = c["rows"]
        allst = [round(math.dist(a_["x"]["o0"], b_["x"]["o0"]), 3) for a_, b_ in zip(rows, rows[1:])]
        s2 = [r["x"]["o1"][2] for r in rows if r["state"] == 2]
        out.update(phases=_phases(rows, 12), max_step=max(allst) if allst else None,
                   o1_dz_s2=[round(min(s2), 3), round(max(s2), 3)] if s2 else None,
                   cam=cam_judge(cz["per_tick"], rows, lambda k: True), by_state=cz["by_state"])
        print(f"  {label} {tag}: {out}")
        return out

    def runoff(self, label: str, jk: int = 29, watch: bool = False) -> dict:
        """A run off a ledge: f6's vanilla-wall [placed], a running jump onto its 1.26 m ledge (the stick along the
        state's camera yaw, Y at k``jk``), then the stick back (the body turns and runs off it); per tick the state,
        the origin against the centre, the camera (2.105's runoff105); with ``watch`` each hit on the player (tick,
        attacker's species, hit timer) and the damage it took (Step 2.123: f6's sentinels hit some runs' run-up)."""
        self.placed(WALL_SPOT)
        _e, P = self.player()
        a = self.spot(WALL_SPOT)["cam"]
        st = {"top": None}

        def on(sb, row, rows):
            k = row["k"]
            if st["top"] is None and k > jk + 5 and row["state"] == 0 and rows[-2]["state"] == 0:
                st["top"] = k
            if st["top"] is not None and k >= st["top"] + 8:
                d = (a + math.pi) - _cam_yaw(sb)
                return [f"axis lx {-math.sin(d):.3f}", f"axis ly {math.cos(d):.3f}"] + (
                    ["stop"] if k >= st["top"] + 50 else [])
            if k >= 5:
                d = a - _cam_yaw(sb)
                return [f"axis lx {-math.sin(d):.3f}", f"axis ly {math.cos(d):.3f}"]
        extra = {HIT_T3: self.rd_t3, APPLY_DAMAGE: self.rd_apply, HIT_STORE: self.rd_store, HT_DONE: self.rd_wdone
                 } if watch else None
        c, cz = self.cap_cam(170, {jk: "down y", jk + 1: "up y"}, f"{label}-runoff", on_tick=on, hold_hp=200,
                             extra=extra)
        rows = c["rows"]
        i = next((j for j in range(1, len(rows)) if st["top"] is not None and rows[j]["k"] > st["top"]
                  and rows[j - 1]["state"] == 0 and rows[j]["state"] == 2), None)   # the walk-off: 0 -> 2, no Y
        allst = [round(math.dist(a_["x"]["o0"], b_["x"]["o0"]), 3) for a_, b_ in zip(rows, rows[1:])]
        out = {"phases": _phases(rows, 16), "top_k": st["top"], "walkoff_k": rows[i]["k"] if i else None,
               "off": steps_from(rows, i - 1, 30) if i else None, "max_step_all": max(allst) if allst else None,
               "o1_dz_s2_after_top": sorted({round(r["x"]["o1"][2], 3) for r in rows if st["top"] is not None
                                             and r["k"] > st["top"] and r["state"] == 2})[:6],
               "cam": cam_judge(cz["per_tick"], rows, lambda k: True), "by_state": cz["by_state"]}
        if watch:
            out["hits_on_player"] = [(h["k"], h.get("att_sp"), h.get("ht"), h.get("ht4")) for h in c["hits"]
                                     if h["va"] == hex(self.va(HIT_T3)) and h.get("target") == P]
            out["stores_on_player"] = [(h["k"], h.get("s_rec")) for h in c["hits"]   # the window store (X31's site)
                                       if h["va"] == hex(self.va(HIT_STORE)) and h.get("s_target") == P]
            out["windows_on_player"] = [(h["k"], h.get("w_1e0"), h.get("w_1e4")) for h in c["hits"]
                                        if h["va"] == hex(self.va(HT_DONE)) and h.get("w_target") == P]
            out["damage_on_player"] = [(h["k"], h["hp"] - h["new_hp"]) for h in c["hits"]
                                       if h["va"] == hex(self.va(APPLY_DAMAGE)) and h.get("critter") == P and "hp" in h]
        print(f"  {label} run off a ledge: {out}")
        return out

    def pit(self, label: str) -> dict:
        """a1's 6 m drop over the ladder spot [placed there first, the camera settled behind the body, then 6 m up]:
        70 ticks with the camera per tick, the hard landing's state 0x100 ticks, a picture (2.104's pit520)."""
        self.placed(LADDER)
        sp = self.spot(LADDER)
        feet = (sp["centre"][0], sp["centre"][1], sp["centre"][2] - recipes.LIFT + 0.1 + 6.0)
        self.s.apply(recipes.place(self.sb.read_u32, feet, 0.0, quat=sp["quat"], cell=sp["cell"],
                                   entity=self.player()[0], va=self.s._va))
        c, cz = self.cap_cam(70, {}, f"{label}-pit")
        rows = c["rows"]
        land = next((r["k"] for r in rows if r["state"] == 0x100), None)
        lock = 0
        for r in rows[land:] if land is not None else ():
            if r["state"] != 0x100:
                break
            lock += 1
        out = {"land_k": land, "lock_0x100": lock, "by_state": cz["by_state"], "pic": self.pic(f"{label}-pit-after", 2)}
        print(f"  {label} pit: land {land} lock {lock} by state {out['by_state']}")
        return out

    def wall_rest(self, label: str, spot: str = LADDER, yaw_deg: float = 180.0, n: int = 90) -> dict:
        """A spot turned ``yaw_deg`` [placed], so its wall is behind the body (a1's ladder spot turned 180: K6; a
        spot whose back faces a wall: K5): ``n`` ticks at rest from the placement's tick with the camera per tick, its
        distance's reversals, a picture (2.104's wall_rest104, one turn)."""
        self.placed(spot)
        sp = self.spot(spot)
        cen = sp["centre"]
        yaw0 = 2 * math.atan2(sp["quat"][2], sp["quat"][3])
        self.s.apply(recipes.place(self.sb.read_u32, (cen[0], cen[1], cen[2] - recipes.LIFT + 0.1),
                                   yaw0 + math.radians(yaw_deg), cell=sp["cell"], entity=self.player()[0],
                                   va=self.s._va))
        c, cz = self.cap_cam(n, {}, f"{label}-wall-{yaw_deg:g}")
        ds = [o["act_dist"] for o in cz["per_tick"] if o["act_dist"] is not None]
        out = {"yaw_deg": yaw_deg, "by_state": cz["by_state"], "first_drop": cz["first_drop"],
               "dist_seq": ds[:30], "dist_end": ds[-1] if ds else None, "reversals": reversals(ds),
               "pic": self.pic(f"{label}-wall-{yaw_deg:g}", 2)}
        print(f"  {label} wall rest {yaw_deg:g}: {out}")
        return out

    def rd_xpt(self, sb, r) -> dict:
        """0x41F6C, X8's point back from 0x41F40: EDI the critter, the point [esp+0x18] (model units) and its depth."""
        return {"critter": r["edi"], "pt": [round(v, 4) for v in _v3(sb, r["esp"] + 0x18)],
                "depth": round(_f1(sb, r["edi"] + 0x27C), 3)}

    @staticmethod
    def rd_push(sb, r) -> dict:
        """0x81EC0, the water push: EBP the camera, its target, and the camera's depth under the surface less the band
        (``cam_under_m``: [esp+8] - 0.4; None out of the water)."""
        a0 = _f1(sb, r["esp"] + 8)
        return {"push_target": sb.read_u32(r["ebp"] + 0x190), "a0": round(a0, 4),
                "cam_under_m": round(a0 - 0.4, 3) if a0 > -49 else None}

    def _swim_cap(self, n: int, sched: dict, label: str, **kw) -> dict:
        """A capture in the water: ``cap_cam``'s with X8's point and the push read; per tick the camera over the
        surface (0x81277's place against the centre less the depth), X8's point (m over the origin) and the push;
        the switches of X8's point (a step over 1 m) and the side changes (``swim_judge``)."""
        _e, P = self.player()
        c, cz = self.cap_cam(n, sched, label, extra={CAM_PT_RET: self.rd_xpt, CAM_PUSH_RET: self.rd_push}, **kw)
        cam, xpt, push = hex(self.va(CAM_UPD)), hex(self.va(CAM_PT_RET)), hex(self.va(CAM_PUSH_RET))
        sc = _f1(self.sb, P + 0x188)
        over = [h["cam_dc"] - h["depth"] for h in c["hits"] if h["va"] == cam and h.get("tgt") == P and "cam_dc" in h]
        pts = [(h["k"], h["pt"][2] * sc, h["depth"]) for h in c["hits"] if h["va"] == xpt and h.get("critter") == P]
        under = [h["cam_under_m"] for h in c["hits"] if h["va"] == push and h.get("push_target") == P
                 and h.get("cam_under_m") is not None]
        return {"rows": c["rows"], "cz": cz, "states": sorted({hex(r["state"]) for r in c["rows"]}),
                "cam_over_surface": swim_judge(over),
                "x8_switches": [(b[0], round(a[1], 2), round(b[1], 2), round(b[2], 2)) for a, b in zip(pts, pts[1:])
                                if abs(b[1] - a[1]) > 1.0],
                "push": {"ticks": len(under), "range": [min(under), max(under)] if under else None,
                         "band_ticks": sum(1 for x in under if abs(x) < 0.4)},
                "depth_end": round(_f1(self.sb, P + 0x27C), 3)}

    @staticmethod
    def _summ(w: dict) -> dict:
        return {k: v for k, v in w.items() if k not in ("rows", "cz")}

    def swim_rest(self, label: str, rest: int = 60) -> dict:
        """vanilla-ocean at rest [placed] (floating): ``rest`` ticks with the camera per tick (a crossing of the
        surface shows as a side change), then a picture (2.104's surface520)."""
        pl = self.placed(OCEAN)
        w = self._swim_cap(rest, {}, f"{label}-swim-rest")
        out = {"place": {k: pl.get(k) for k in ("off_m", "try")}, **self._summ(w), "by_state": w["cz"]["by_state"],
               "pic": self.pic(f"{label}-swim-rest", 3)}
        print(f"  {label} swim rest: {out}")
        return out

    def _top_under(self, sb, row) -> float | None:
        """The drawn top's depth under the surface (m): the centre's depth less the top bone over the centre."""
        top = (row.get("x") or {}).get("top_vs_cen")
        ent = int(row["ent"], 16) if isinstance(row["ent"], str) else row["ent"]   # a capture's kept row holds it as hex
        return None if top is None else _f1(sb, sb.read_u32(ent + 0x20) + 0x27C) - top

    def swim_sink(self, label: str, under_m: float | None = None, n: int = 400) -> dict:
        """vanilla-ocean [placed], A held until the drawn top is ``under_m`` under the surface (None: 40 ticks; the
        plan's 2 x m1 for the build), then a picture deep; then Y held until the body is back at the surface (depth
        under 1.6 m) and 20 ticks on (2.104's sink520): X8's switches, the camera's side changes and band ticks."""
        self.placed(OCEAN)
        self._swim_cap(20, {}, f"{label}-sink-rest")

        def down(sb, row, rows):
            if under_m is None:
                return ["stop"] if row["k"] >= 40 else None
            u = self._top_under(sb, row)
            return ["stop"] if u is not None and u >= under_m else None
        w1 = self._swim_cap(n, {1: "down a"}, f"{label}-sink", on_tick=down)
        deep = {"pic": self.pic(f"{label}-sink-deep", 2), "ticks": len(w1["rows"]),
                "top_under_m": round(self._top_under(self.sb, w1["rows"][-1]) or 0.0, 3) if w1["rows"] else None}
        st = {"back": None}

        def up(sb, row, rows):
            dep = _f1(sb, sb.read_u32(row["ent"] + 0x20) + 0x27C)
            if st["back"] is None and row["k"] > 5 and dep < 1.6:
                st["back"] = row["k"]
            return ["stop"] if st["back"] is not None and row["k"] >= st["back"] + 20 else None
        w2 = self._swim_cap(260, {0: "up a", 2: "down y"}, f"{label}-rise", on_tick=up)
        self.s.capture(4, {0: "up y"}, label=None, body=False)
        out = {"sink": self._summ(w1), "deep": deep, "rise": self._summ(w2), "rise_back_k": st["back"],
               "by_state": {"sink": w1["cz"]["by_state"], "rise": w2["cz"]["by_state"]},
               "pic_end": self.pic(f"{label}-rise-end", 2)}
        print(f"  {label} sink and rise: {out}")
        return out

    def swim_input(self, label: str, under_m: float = 1.0, pitches=(-4.0, -8.0), hold: int = 30, rt: int = 45,
                   n: int = 600) -> dict:
        """G7b and K17 (Step 2.107): vanilla-ocean [placed], the drawn top held ``under_m`` under the surface (A while
        it is shallower), then the right stick pitching the camera to each of ``pitches`` (degrees off the pitch to
        the point at the start: down negative; the stick's sign found from the first ticks) held ``hold`` ticks, then
        RT ``rt`` ticks; the camera's side changes and band ticks over it all."""
        self.placed(OCEAN)
        _e, P = self.player()
        st = {"phase": "sink", "i": 0, "p0": None, "sign": 1.0, "t": 0, "tried": None, "a": False}
        self._last_cam.pop(P, None)   # a reading from this capture only (Step 2.123: the last one's flipped the sign)

        def on(sb, row, rows):
            u = self._top_under(sb, row)
            acts = []
            if (want_a := u is not None and u < under_m) != st["a"]:   # A while the top is shallower than under_m
                st["a"] = want_a
                acts.append("down a" if want_a else "up a")
            pitch = self._last_cam.get(P, {}).get("act_pitch")
            st["t"] += 1
            if st["phase"] == "sink" and u is not None and u >= under_m and pitch is not None:
                st.update(phase="pitch", p0=pitch, t=0, tried=pitch)
            elif st["phase"] == "pitch" and pitch is not None:
                want = st["p0"] + pitches[st["i"]]
                if st["t"] == 4 and st["i"] == 0 and (pitch - st["tried"]) * pitches[0] < 0:
                    st["sign"] = -st["sign"]   # the stick moved the pitch the other way
                if (pitch - want) * pitches[st["i"]] >= 0:
                    st.update(phase="hold", t=0)
                    acts.append("axis ry 0")
                else:
                    acts.append(f"axis ry {st['sign'] * (1.0 if pitches[st['i']] < 0 else -1.0) * 0.6:.3f}")
            elif st["phase"] == "hold" and st["t"] >= hold:
                st["i"] += 1
                if st["i"] < len(pitches):
                    st.update(phase="pitch", t=0)
                else:
                    st.update(phase="rt", t=0)
                    acts.append("trigger rt 1")
            elif st["phase"] == "rt" and st["t"] >= rt:
                acts += ["trigger rt 0", "stop"]
            return acts
        w = self._swim_cap(n, {}, f"{label}-swim-input", on_tick=on)
        out = {**self._summ(w), "end_phase": st["phase"], "pitches_done": st["i"], "stick_sign": st["sign"],
               "by_state": w["cz"]["by_state"], "pic": self.pic(f"{label}-swim-input", 2)}
        print(f"  {label} swim under input: {out}")
        return out

    def swim_leave(self, label: str, n: int = 400) -> dict:
        """Out of the water onto the beach: vanilla-ocean [placed], the stick toward the beach (vanilla-beach-shield5's
        spot, its direction from the ocean's) until 20 ticks out of the swim state."""
        self.placed(OCEAN)
        o, b = self.spot(OCEAN)["centre"], self.spot(BEACH)["centre"]
        a = math.atan2(-(b[0] - o[0]), b[1] - o[1])   # the game angle of that direction: forward is (-sin, cos)
        st = {"out": None}

        def on(sb, row, rows):
            if st["out"] is None and row["k"] > 5 and row["state"] != 6:
                st["out"] = row["k"]
            if st["out"] is not None and row["k"] >= st["out"] + 20:
                return ["axis lx 0", "axis ly 0", "stop"]
            if row["k"] >= 2:
                d = a - _cam_yaw(sb)
                return [f"axis lx {-math.sin(d):.3f}", f"axis ly {math.cos(d):.3f}"]
        w = self._swim_cap(n, {}, f"{label}-swim-leave", on_tick=on)
        out = {**self._summ(w), "out_k": st["out"], "phases": _phases(w["rows"], 10), "by_state": w["cz"]["by_state"],
               "pic": self.pic(f"{label}-swim-leave", 2)}
        print(f"  {label} out of the water: {out}")
        return out

    def waterjump(self, label: str) -> dict:
        """vanilla-ocean at rest [placed] (floating), Y at k5: out of the water; per tick the state, the origin against
        the centre and its steps (a slide shows as 0.847 m steps), the camera (2.105's waterjump105)."""
        self.placed(OCEAN)
        c, cz = self.cap_cam(70, {5: "down y", 8: "up y"}, f"{label}-waterjump", hold_hp=200)
        rows = c["rows"]
        allst = [round(math.dist(a_["x"]["o0"], b_["x"]["o0"]), 3) for a_, b_ in zip(rows, rows[1:])]
        out = {"phases": _phases(rows, 14), "steps": allst, "max_step": max(allst) if allst else None,
               "eased_steps": sum(1 for v in allst if abs(v - 0.847) < 0.002),
               "o0_dz": [round(r["x"]["o0"][2], 3) for r in rows][:40],
               "cam": cam_judge(cz["per_tick"], rows, lambda k: True), "by_state": cz["by_state"]}
        print(f"  {label} out of the water: {out}")
        return out

    # -- the rows (2.105's, by family) ------------------------------------------------------------------------------------
    def row_zip(self, rid: str, iso, sha: str | None = None, *, body="usa", pics: bool = True, flap: bool = True,
                cast: bool = False, ridecam: bool = True, ride_end: bool = True, **note) -> dict:
        """f3's zipline set (2.105's rows 1, 4 and 5's ride): vanilla-ig-a1, the warp to f3, the teleport start (Y k3,
        the let-go k50), [the walk-in ride and its let-go, the placed ride], [the ride to the cable's end], [the floor
        cast on the ride], [the pictures], [the let-go with a flap: the air armor cast last]."""
        def run(R):
            self.step(R, "warp_f3", self.warp, "levels/fire/f3")
            self.step(R, "zipT", self.zip_teleport, rid)
            if ridecam:
                self.step(R, "zipW", self.zip_walkin, rid)
                self.step(R, "ridecam", self.zip_placed, rid)
            if ride_end:
                self.step(R, "ride_end", self.zip_to_end, rid)
            if cast:
                self.step(R, "ride_cast", self.zip_cast, rid)
            if pics:
                self.step(R, "pics", self.zip_pics, rid)
            if flap:
                self.step(R, "flap", self.zip_flap, rid)
        return self.row(rid, iso, sha, "vanilla-ig-a1", run, spots=(ZIP,), body=body, **note)

    def row_ladder(self, rid: str, iso, sha: str | None = None, *, body="usa", cast: bool = False, **note) -> dict:
        """a1's ladder (2.105's break row, its ladder part): over the top, a jump off at climb tick ``LADDER_JUMP``,
        [the floor cast at its foot]."""
        def run(R):
            self.step(R, "ladder_top", self.ladder, rid)
            self.step(R, "ladder_jump", self.ladder, rid, LADDER_JUMP)
            if cast:
                self.step(R, "ladder_cast", self.ladder_cast, rid)
        return self.row(rid, iso, sha, "vanilla-ig-a1", run, spots=(LADDER,), body=body, **note)

    def row_combo(self, rid: str, iso, sha: str | None = None, *, runs_n: int = 8, quiet: bool | None = False,
                  **kw) -> dict:
        """e7's combo (2.105's rows 2 and 6, its HP writes checked: AZ-530): vanilla-ig-e7, ``combo``. Booted loud by
        default (``quiet``: Step 2.107's sitting C, the popups as the save holds them, gave 2.105's first run: settled
        1.4 m from its keylord, five unchained basic1s; a quiet boot settled it 2.025 m off among rock shards)."""
        note = {k: kw.pop(k) for k in list(kw) if k not in ("n", "every", "d_centre", "want", "dr", "nodmg")}
        was, self.quiet = self.quiet, quiet
        try:
            return self.row(rid, iso, sha, "vanilla-ig-e7",
                            lambda R: self.step(R, "combo", self.combo, rid, runs_n, **kw), spots=(KEYLORD,), **note)
        finally:
            self.quiet = was

    def row_sentinel(self, rid: str, iso, sha: str | None = None, *, drs=((3.6, 4),), press: bool = True,
                     **note) -> dict:
        """f6's lone blaze sentinel (2.105's row 3, the 3 m rule): vanilla-ig-f6, the cheat, the runs at each (dr,
        runs), [the fresh press on the stunned sentinel, still and stick forward]. Not yet matched to 2.105's row: on
        v0.16 Step 2.107's sittings placed it as 2.105 did (4.98-5.04 m) but 0x7EBB0 found n 0 on 9-10 of its 10
        searches, quiet or loud, where 2.105's found 1-3 at 2.94-3.00 m [cause open]."""
        def run(R):
            self.step(R, "cheat", self.cheat_nodmg)
            for dr, nr in drs:
                self.step(R, f"sent{dr}", self.sentinel_runs, rid, dr, nr)
            if press:
                self.step(R, "fresh", self.sentinel_press, rid, 3.6, False)
                self.step(R, "freshF", self.sentinel_press, rid, 3.6, True)
        return self.row(rid, iso, sha, "vanilla-ig-f6", run, spots=(SENTINEL,), **note)

    def _swim_steps(self, R: dict, rid: str, *, rest: int, sink_m: float | None, under_input: bool, leave: bool,
                    jump: bool) -> None:
        self.step(R, "swim_rest", self.swim_rest, rid, rest)
        self.step(R, "swim_sink", self.swim_sink, rid, sink_m)
        if under_input:
            self.step(R, "swim_input", self.swim_input, rid)
        if leave:
            self.step(R, "swim_leave", self.swim_leave, rid)
        if jump:
            self.step(R, "waterjump", self.waterjump, rid)

    def row_swim(self, rid: str, iso, sha: str | None = None, *, body=None, frame: dict | None = None, s: float = 1.0,
                 rest: int = 60, sink_m: float | None = None, under_input: bool = True, leave: bool = True,
                 jump: bool = True, **note) -> dict:
        """w1's ocean (Step 2.107: AZ-311, AZ-414, AZ-446; G7, G7b, K7, K17): vanilla-ig-w1, at the recorded
        vanilla-ocean spot each part: at rest ``rest`` ticks, sunk (A) until the drawn top is ``sink_m`` under (the
        plan's 2 x m1) and risen (Y), [the top held 1 m under with the stick's pitch and RT], [out onto the beach],
        [the jump out of the water]; the camera per tick, and with ``frame`` (``frame_body``'s: its ``pad``, and its
        ``bones`` unless ``body`` names them) the frame's score at the rig's ``s``."""
        def run(R):
            self.frame_on(frame and frame["pad"], s)
            try:
                self._swim_steps(R, rid, rest=rest, sink_m=sink_m, under_input=under_input, leave=leave, jump=jump)
            finally:
                self.frame_on(None)
        bones = body if body is not None else frame["bones"] if frame else "usa"
        return self.row(rid, iso, sha, "vanilla-ig-w1", run, spots=(OCEAN, BEACH), body=bones, **note)

    def row_frame(self, rid: str, iso, sha: str | None = None, *, frame: dict, s: float = 1.0, body=None,
                  levels=("f6", "a1", "f3", "w1"), sink_m: float | None = None, **note) -> dict:
        """The frame at the grid's spots (Step 2.107, D280: SITTING-PLAN section 4), every capture scored per tick
        (``frame_on``: ``frame`` is ``frame_body``'s for the build's body, ``s`` its rig scale; the bones read are
        ``frame["bones"]`` unless ``body`` names them): the build booted at the first of ``levels``' save, the others
        by the warp: f6 still, walk, run, a jump, a flap, a run off the ledge; a1 the pit's landing, the ladder over
        the top and off it at climb tick ``LADDER_JUMP``, its spot turned 180 against the wall (K6); f3 the zipline's teleport and
        walk-in starts, its placed ride and the ride to the cable's end; w1 ``row_swim``'s parts."""
        first = levels[0]

        def run(R):
            self.frame_on(frame["pad"], s)
            try:
                for lv in levels:
                    if lv != first:
                        self.step(R, f"warp_{lv}", self.warp, LEVELS[lv])
                    if lv == "f6":
                        self.step(R, "f6_rest", self.ground_cam, rid)
                        self.step(R, "f6_walk", self.ground_cam, rid, FLAT_SPOT, 45, 0.5)
                        self.step(R, "f6_run", self.ground_cam, rid, FLAT_SPOT, 45, 1.0)
                        self.step(R, "f6_jump", self.jump, rid)
                        self.step(R, "f6_flap", self.jump, rid, FLAT_SPOT, None, 70, "flap", True)
                        self.step(R, "f6_runoff", self.runoff, rid)
                    elif lv == "a1":
                        self.step(R, "a1_pit", self.pit, rid)
                        self.step(R, "a1_ladder_top", self.ladder, rid)
                        self.step(R, "a1_ladder_jump", self.ladder, rid, LADDER_JUMP)
                        self.step(R, "a1_wall", self.wall_rest, rid)
                    elif lv == "f3":
                        self.step(R, "f3_zipT", self.zip_teleport, rid)
                        self.step(R, "f3_zipW", self.zip_walkin, rid)
                        self.step(R, "f3_ridecam", self.zip_placed, rid)
                        self.step(R, "f3_ride_end", self.zip_to_end, rid)
                    elif lv == "w1":
                        self._swim_steps(R, rid, rest=60, sink_m=sink_m, under_input=True, leave=True, jump=True)
            finally:
                self.frame_on(None)
        spots = {"f6": (FLAT_SPOT, WALL_SPOT), "a1": (LADDER,), "f3": (ZIP,), "w1": (OCEAN, BEACH)}
        bones = frame["bones"] if body is None else body
        return self.row(rid, iso, sha, f"vanilla-ig-{first}", run, spots=tuple(t for lv in levels for t in spots[lv]),
                        body=bones, **note)

    # -- the frame's cost (Step 2.173: D603 warns, never refuses; D604 drafts a fork request) --------------------------
    def settle(self, n: int = COST_SETTLE) -> dict:
        """``n`` player ticks with no input, the HP held, then until the input builder takes the stick (``free``):
        the load's window and the level-start sequence past (Step 2.173's smoke: a1's save holds the stick 496 ticks,
        its flips 400,112 triangles at p95 there and 56,611-65,300 in play after it, so a phase before it measures the
        level's opening camera, not the body, and its stick does nothing). The ticks each took."""
        self.ensure_tick()
        ticks = self.s.capture(n, {}, label=None, body=False, hold_hp=200)["meta"]["rows"]
        return {"ticks": ticks, "free_ticks": self.free()}

    def cost_phase(self, phase: str, n: int = COST_N, gpu: bool | str = "per-flip") -> dict:
        """One phase from a player tick: ``phase_lines`` played over ``n`` vblanks with NV2A counters, timed
        (``xo.timed_advance``), then a player tick (the body still playing; watched, its loss ends the row). Its
        ``xo.frame_cost`` (per flip: steady max, p95, median by kind) with ``times`` and ``ticks``."""
        self.ensure_tick()
        lines = phase_lines(phase, n, self.sb.code("a") if phase == "attack" else None)
        r, t = xo.timed_advance(self.sb, n, gpu=gpu, play=lines)
        return {**xo.frame_cost(r.get("gpu-counters") or {}, n), "times": t, "ticks": self.s.tick(5.0) is not None}

    def row_cost(self, rid: str, iso, sha: str | None = None, *, control=None, ceiling: dict | None = None,
                 levels=COST_LEVELS, phases=COST_PHASES, n: int = COST_N, realtime: bool = False, body="usa",
                 **note) -> dict:
        """The frame's cost (Step 2.173, D603): the build booted at the first of ``levels``' save (vanilla-ig-a1), the
        others by the warp, each settled (``settle``: ``COST_SETTLE`` ticks, then until the stick is the player's),
        then each of ``phases`` (``phase_lines``) for ``n`` vblanks with per-flip counters (deterministic null: exact
        counts) and its host and guest times; every scene's ``frame_cost`` in ``R["frame_cost"]["scenes"]`` ("a1/idle" ...). Run it on the vanilla disc ("usa") as the
        control, then on the build with ``control=`` that row (or a list of boots); with a control or a ``ceiling``,
        ``xo.frame_warning``'s lines: ``R["warn"]`` (L1, which ``Sitting.header`` lists under WARNINGS) and
        ``frame_cost``'s ``notes``, ``heaviest`` and ``realtime_due`` (L1 fired, or ``realtime``: run ``rate_pairs``
        on ``heaviest``'s scene in a real-time sitting). Never a refusal."""
        first = levels[0]

        def run(R):
            fc = R["frame_cost"] = {"scenes": {}, "n": n}

            def phase(lv: str, ph: str) -> dict:
                got = fc["scenes"][f"{lv}/{ph}"] = self.cost_phase(ph, n)
                return {k: got.get(k) for k in ("steady", "per_vblank", "ticks")}
            try:
                for lv in levels:
                    if lv != first and "err" in self.step(R, f"warp_{lv}", self.warp, LEVELS[lv]):
                        continue
                    self.step(R, f"settle_{lv}", self.settle)
                    for ph in phases:
                        self.step(R, f"{lv}_{ph}", phase, lv, ph)
            finally:   # a lost tick (Sitting.Hold) keeps the scenes so far, judged
                if control is not None or ceiling is not None:
                    w = xo.frame_warning(fc["scenes"], None if control is None else cost_scenes(control),
                                         ceiling=ceiling)
                    R["warn"] = w["warn"]
                    fc.update(notes=w["notes"], heaviest=w["heaviest"], ceiling=w["ceiling"])
                    fc["realtime_due"] = realtime or bool(w["warn"])
        return self.row(rid, iso, sha, f"vanilla-ig-{first}", run, body=body, **note)

    def rate_phase(self, phase: str, n: int = RATE_N) -> dict:
        """One phase's rate in this sitting's mode: ``n`` vblanks of its lines timed with the NV2A counters off, its
        flips counted without them (``xo.flip_count``: the fork's reply on FRAME-8bffffeb0243, Step X.68), the host's
        load average before it."""
        load = os.getloadavg()[0]
        self.ensure_tick()
        lines = phase_lines(phase, n, self.sb.code("a") if phase == "attack" else None)
        _, t = xo.timed_advance(self.sb, n, gpu=False, play=lines)
        st = self.sb.st
        return {**t, "load1": round(load, 1), "mode": "deterministic" if st.get("deterministic") else "real time",
                "headless": st.get("headless")}

    def row_rate(self, rid: str, iso, sha: str | None = None, *, scene: str = "a1/idle", n: int = RATE_N,
                 body="usa", **note) -> dict:
        """One scene's rate (Step 2.173, D604), a fresh process: booted at vanilla-ig-a1's save, the warp to the
        scene's level, ``settle``, then ``rate_phase``. In a real-time offscreen sitting (``Sitting(headless="1",
        deterministic=False)``) its ``per_vblank`` is the frame rate the owner sees; in a deterministic one its
        ``wall_ms_vblank`` is the host's time a vblank (null, or offscreen Vulkan with ``headless="1"``)."""
        lv, ph = scene.split("/")

        def run(R):
            if lv != "a1" and "err" in self.step(R, f"warp_{lv}", self.warp, LEVELS[lv]):
                return
            self.step(R, "settle", self.settle)
            self.step(R, "rate", self.rate_phase, ph, n)
        return self.row(rid, iso, sha, "vanilla-ig-a1", run, body=body, scene=scene,
                        fresh="a rate row times a process of its own (D604)", **note)

    def rate_pairs(self, rid: str, iso, sha: str | None = None, *, scene: str, control="usa",
                   control_sha: str | None = None, pairs: int = xo.RT_PAIRS, n: int = RATE_N) -> dict:
        """L3's pairs (Step 2.173, D604): ``pairs`` times the control's ``row_rate``, then the build's, each its own
        fresh process (no second boot in one, AZ-628), alternated so the host's load drifts over both. ``{scene,
        pairs: [{control, build, load, ms}], n, start, settle, run, load, mode, flips_by, vblank_ns}`` for
        ``xo.frame_warning(rt=)`` (``ms``: each row's host ms a vblank, control then build; ``settle`` and ``run``: the
        build's last ``settle`` and ``run_how``; ``flips_by``: how the arms counted flips, "+"-joined); a pair a row
        of which found no rate is left out (fewer than ``RT_PAIRS``: inconclusive). With the control as ``iso`` too,
        ``xo.rate_spread`` of it is the vanilla-vs-vanilla noise."""
        out: dict = {"scene": scene, "pairs": [], "n": n}
        by: set[str] = set()
        for i in range(pairs):
            c = self.row_rate(f"{rid}-c{i + 1}", control, control_sha, scene=scene, n=n).get("rate") or {}
            B = self.row_rate(f"{rid}-b{i + 1}", iso, sha, scene=scene, n=n)
            b = B.get("rate") or {}
            if c.get("per_vblank") is not None and b.get("per_vblank") is not None:
                out["pairs"].append({"control": c["per_vblank"], "build": b["per_vblank"],
                                     "load": [c.get("load1"), b.get("load1")],
                                     "ms": [c.get("wall_ms_vblank"), b.get("wall_ms_vblank")]})
                out["start"], out["settle"], out["run"] = b.get("start_frame"), B.get("settle"), run_how(B, scene)
                by.update((c.get("flips_by", "gpu-counters"), b.get("flips_by", "gpu-counters")))
        out["mode"] = "deterministic" if self.sb.st.get("deterministic") else "real time"
        if by:
            out["flips_by"] = "+".join(sorted(by))
        loads = [x for p in out["pairs"] for x in p["load"] if x is not None]
        out["load"] = round(sum(loads) / len(loads), 1) if loads else None
        out["vblank_ns"] = self.sb.st.get("vblank_ns", xo.VBLANK_NS)
        return out

    def frame_request(self, build: dict, control: dict, rt: dict, warning: dict, *, recipe: str, iso,
                      out: Path | None = None, offscreen: dict | None = None) -> Path | None:
        """D604's draft, only where ``warning`` (``xo.frame_warning(..., rt=rt)``'s) says the real-time rate fell:
        ``xo.fork_request`` from the build's and the control's ``row_cost`` rows at ``rt``'s scene, into ``out``
        (default ``xemu-fork-requests-<date>/`` in ``$EV``) as ``FRAME-<build sha12>-<level>-<phase>.txt``, for the
        orchestrator to fold into the fork's next prompt for the owner to relay. ``recipe``: the build's
        ``azurkit build`` arguments; ``iso``: its path; ``offscreen``: ``rate_pairs`` of the scene in a deterministic
        offscreen sitting (the host's ms a vblank there, build / vanilla). None, nothing written, otherwise (D604's "if
        framerate decreases": an L1 warning alone writes no request)."""
        if not warning.get("request"):
            return None
        from devkit.xemu import sitting as xs
        scene, st = rt["scene"], self.sb.st
        lv, ph = scene.split("/")
        b, c = (row.get("frame_cost", {}).get("scenes", {}).get(scene, {}) for row in (build, control))
        boot = build.get("boot") or {}
        sha = build.get("want_sha12") or boot.get("iso_sha12") or "unknown"
        n, se = rt.get("n", RATE_N), rt.get("settle") or {}
        ms = [p["ms"] for p in (offscreen or {}).get("pairs") or [] if None not in p.get("ms", [None])]
        off = (" / ".join(f"{sum(m[i] for m in ms) / len(ms):.2f}" for i in (1, 0)) + f" ({len(ms)} pairs)") if ms \
            else None
        settle = (f"{se.get('ticks', COST_SETTLE)} player ticks with no input, then {se['free_ticks']} more until the "
                  "input builder took the stick (input+0x30 clear)") if "free_ticks" in se else \
            f"{COST_SETTLE} player ticks, then until the input builder takes the stick (input+0x30 clear)"
        r = {"step": self.s.step, "scene": scene, "xemu": st.get("xemu_version"),   # run: an older rt's isn't kept
             "run": rt.get("run") or dict.fromkeys(("binary", "load", "reached"), xo.NOT_RECORDED),
             "counts": run_how(build, scene), "load": rt.get("load"), "rt": rt, "disc": boot.get("iso_sha12"),
             "xbe": (boot.get("xbe_sha256") or "")[:12] or None, "recipe": recipe, "iso": str(iso), "settle": settle,
             "start": rt.get("start"), "frames": n,
             "lines": phase_lines(ph, n, self.sb.code("a") if ph == "attack" else None),
             "build": b, "control": c, "host_build": b.get("times"), "host_control": c.get("times"),
             "off_ms": off, "files": str(self.s.ev / "results")}
        d = Path(out) if out is not None else xs.EV / f"xemu-fork-requests-{time.strftime('%Y-%m-%d')}"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"FRAME-{sha}-{lv}-{ph}.txt"
        p.write_text(xo.fork_request(r), encoding="utf-8")
        self.s.log(f"D604 fork request drafted: {p}")
        return p

    def rate_verdict(self, rid: str, build: dict, control: dict, rt: dict, *, recipe: str, iso,
                     noise: float | None = None, out: Path | None = None, offscreen: dict | None = None) -> dict:
        """L3 (Step 2.173, D604) on ``rate_pairs``' ``rt`` for the ``row_cost`` rows ``build`` and ``control``
        (``noise``: FC0's vanilla-vs-vanilla ``xo.rate_spread``; ``offscreen``: ``frame_request``'s): one results row
        with the verdict, the frame-rate line in its ``warn`` (``Sitting.header``'s WARNINGS) and, where it fell,
        ``frame_request``'s draft."""
        w = xo.frame_warning(cost_scenes(build)[0], cost_scenes(control), rt=rt, noise=noise)
        R = {"case": f"{self.s.step}-{rid}" if self.s.step else rid, "row": rid, "scene": rt.get("scene"), "rt": rt,
             "fps": w["fps"], "warn": [x for x in w["warn"] if x.startswith("frame rate:")], "notes": w["notes"],
             "request": None}
        p = self.frame_request(build, control, rt, w, recipe=recipe, iso=iso, out=out, offscreen=offscreen)
        R["request"] = str(p) if p else None
        self.s.result(R)
        return R


class _suppressed:
    """A guest read's failures suppressed (OSError, ValueError, KeyError, ZeroDivisionError, struct.error), as the
    drivers' ``except Exception: pass`` did; a hold (``Sitting.Hold``) and a signal go on."""

    def __enter__(self):
        return self

    def __exit__(self, et, e, tb) -> bool:
        return et is not None and issubclass(et, (OSError, ValueError, KeyError, ZeroDivisionError, struct.error))


class Arena:
    """e7's keylord spot [placed]: the player critter, the enemies its hits and queries name, the approach (the stick
    toward the spot's facing until one is within 3.5 m)."""

    def __init__(self, k: Kit, spot: str = KEYLORD, hold: int = 200, approach: bool = True):
        self.k, self.hold, self.pl, self.seen = k, hold, {}, set()
        if approach:
            for _ in range(3):
                try:
                    self.pl = k.placed(spot)
                    break
                except (OSError, SystemExit) as e:
                    print("  placement failed:", str(e)[:80])
                    self.pl = {"err": str(e)[:80]}
        self.a = k.spot(spot)["cam"]
        k.s.tick()
        self.P = k.sb.read_u32(k.sb.g.u32(k.sb.g.regs()["esp"] + 4) + 0x20)
        if approach:
            self.approach()

    def approach(self) -> None:
        b, rd = self.k.watch_bps()
        for _ in range(3):
            c = self.k.s.capture(60, {}, label=None, body=False, bps=b, bp_readers=rd, hold_hp=self.hold,
                                 on_tick=self.k.s.both(steer(self.a, lambda k, st: "steer"), self.on_app))
            self.collect(c)
            if c["meta"]["stop"] and "stop action" in c["meta"]["stop"]:
                break

    def enemies(self) -> list[tuple]:
        out = []
        for t in list(self.seen):
            try:
                sp, hp, q = self.k.species(t), self.k.sb.read_i32(t + 0x210), _v3(self.k.sb, t + 0x15C)
            except (OSError, ValueError):
                continue
            if sp and sp[0].isalpha() and hp > 0 and all(math.isfinite(v) for v in q):
                out.append((t, sp, hp, q))
        return out

    def my_pos(self) -> tuple:
        return _v3(self.k.sb, self.P + 0x15C)

    def on_app(self, sb, row, rows):
        if es := self.enemies():
            p = self.my_pos()
            if min(math.hypot(q[0] - p[0], q[1] - p[1]) for _, _, _, q in es) < 3.5:
                return ["stop"]

    def collect(self, c: dict) -> None:
        for h in c["hits"]:
            for key in ("attacker", "target", "critter"):
                if (v := h.get(key)) and v != self.P and isinstance(v, int):
                    self.seen.add(v)

    def nearest(self):
        if not (es := self.enemies()):
            b, rd = self.k.watch_bps()
            self.collect(self.k.s.capture(40, {}, label=None, body=False, bps=b, bp_readers=rd, hold_hp=self.hold))
            if not (es := self.enemies()):
                return None
        p = self.my_pos()
        return min((math.hypot(q[0] - p[0], q[1] - p[1]), t, sp, hp, q) for t, sp, hp, q in es)


class SpotArena(Arena):
    """The arena at another recorded spot (f6's vanilla-enemy: a blaze sentinel straight ahead)."""

    def __init__(self, k: Kit, spot: str, hold: int = 200):
        self.k, self.hold, self.seen = k, hold, set()
        self.pl = k.placed(spot)
        self.a = k.spot(spot)["cam"]
        k.s.tick()
        self.P = k.sb.read_u32(k.sb.g.u32(k.sb.g.regs()["esp"] + 4) + 0x20)
        self.approach()


class NodeArena(Arena):
    """Beside a spawn of ``species`` in ``level``: R6 ``back_m`` from its critterGenerator toward the nearest
    playerLocation, facing it [placed] (the level file's nodes, read at run time: positions in memory only), then
    idle captures (HP held) until a live one has queried or hit."""

    _NODES: dict[str, dict] = {}

    def __init__(self, k: Kit, level: str, species: str, back_m: float = 4.0, hold: int = 200, tries: int = 4):
        self.k, self.hold, self.seen, self.a = k, hold, set(), 0.0
        ln = self.nodes(level)
        n = len({g[1] for g in ln["gens"] if g[0].split(":")[0] == species})
        self.pl = {"spawns": n, "tries": []}
        b, rd = k.watch_bps()
        for j in range(min(n, tries)):
            pl = self.place_near(ln, species, j, back_m)
            k.s.tick()
            self.P = k.sb.read_u32(k.sb.g.u32(k.sb.g.regs()["esp"] + 4) + 0x20)
            for _ in range(5):
                self.collect(k.s.capture(60, {}, label=None, body=False, bps=b, bp_readers=rd, hold_hp=hold))
                if any(species in sp for _, sp, _, _ in self.enemies()):
                    break
            self.pl["tries"].append({"k": j, "spawn": pl.get("spawn"), "settled": pl.get("settled"),
                                     "seen": sorted({sp for _, sp, _, _ in self.enemies()})})
            if any(species in sp for _, sp, _, _ in self.enemies()):
                break
        print("  NodeArena", self.pl)

    def nodes(self, level: str) -> dict:
        """{'spots': {name: pos}, 'gens': [(species, generator name, pos)]} of the release's vanilla level file."""
        from azurkit.core import iso as xiso
        from azurkit.core.xbr import graph as _nodes
        lv, release = level.rsplit("/", 1)[-1], self.k.sb.st.get("release", "usa")
        if (lv, release) in self._NODES:
            return self._NODES[(lv, release)]
        with xiso.Reader(xo.vanilla_iso(xo.region_named(release))) as r:
            xbe, data = r.read("default.xbe"), r.read(f"gamedata/{lv}.xbr")
        schema, out = _nodes.Schema(xbe), {"spots": {}, "gens": []}
        for g in _nodes.graphs(data, schema):
            sizes = g.record_sizes()
            order = sorted((ro, i) for i, ro in enumerate(g.recs) if ro is not None)
            ros = [ro for ro, _ in order]

            def rec_of(p, ros=ros, order=order, sizes=sizes):
                j = bisect.bisect_right(ros, p) - 1
                if j < 0:
                    return None
                ro, i = order[j]
                return i if p < ro + sizes.get(i, 64) else None
            strs = {m.start(): g.s[m.start():m.end() - 1].decode("latin-1")
                    for m in re.finditer(rb"([a-z0-9_]+(:[a-z0-9_]+)?)\x00", g.s.lower())}
            for i, t in enumerate(g.types):
                if t == "playerLocation":
                    out["spots"][g.pstr(g.recs[i], 0x1C)] = _nodes.apply(g.world(i)[0], (0.0, 0.0, 0.0))
            for p in range(0, len(g.s) - 8, 4):
                if (tgt := struct.unpack_from("<i", g.s, p + 4)[0] + p + 4) in strs:
                    if (i := rec_of(p)) is not None and g.types[i] == "critterGenerator":
                        out["gens"].append((strs[tgt], g.names[i], _nodes.apply(g.world(i)[0], (0.0, 0.0, 0.0))))
        self._NODES[(lv, release)] = out
        return out

    def place_near(self, ln: dict, species: str, j: int = 0, back_m: float = 4.0) -> dict:
        """R6 beside the ``j``-th spawn of ``species``: ``back_m`` from it toward the nearest playerLocation, facing
        it [placed]; names and distances only."""
        gens = []
        for g in ln["gens"]:   # an archetype is "species" or "species:path"; each generator once
            if (g[0] == species or g[0].split(":")[0] == species) and all(g[1] != h[1] for h in gens):
                gens.append(g)
        if not gens:
            return {"err": f"no {species} spawn"}
        _sp, gname, gp = gens[min(j, len(gens) - 1)]
        tp = min(ln["spots"].values(), key=lambda v: math.dist(v, gp))
        d = math.hypot(tp[0] - gp[0], tp[1] - gp[1]) or 1.0
        fx, fy = gp[0] + back_m * (tp[0] - gp[0]) / d, gp[1] + back_m * (tp[1] - gp[1]) / d
        self.k.ensure_tick()
        self.k.s.apply(recipes.place(self.k.sb.read_u32, (fx, fy, gp[2] + 0.3),
                                     math.atan2(gp[1] - fy, gp[0] - fx) - math.pi / 2, entity=self.k.player()[0],
                                     va=self.k.s._va))
        ok = all(self.k.s.tick(6.0) is not None for _ in range(20))
        _e, c = self.k.player()
        cen = _v3(self.k.sb, c + 0x15C)
        return {"spawn": gname, "spawns": len(gens), "settled": ok,
                "from_spawn_m": round(math.hypot(cen[0] - gp[0], cen[1] - gp[1]), 2), "dz_from_spawn": round(cen[2] - gp[2], 2)}


# --- selftest (offline: no xemu, no fixtures) -------------------------------------------------------------------------

def selftest() -> int:
    """One fake row on a stand-in sitting: the row's fresh process, boot and steps, an error kept as its step's
    result, a lost tick (``Sitting.Hold``) ending it with its runs so far, one tagged results row; and the zipline's
    and the camera's judges on a made-up ride."""
    import tempfile
    import types

    from devkit.xemu import sitting as xs
    ok = True

    def check(name: str, cond, detail: str = "") -> None:
        nonlocal ok
        ok &= bool(cond)
        xo.log(f"{'ok  ' if cond else 'FAIL'} {name}{f' ({detail})' if detail else ''}")

    tmp = Path(tempfile.mkdtemp(prefix="azx-model-kit-selftest.", dir="/tmp"))
    try:
        s = xs.Sitting("mk", step="X.45", ev=tmp / "ev")
        for sub in ("results", "captures", "logs"):
            (s.ev / sub).mkdir(parents=True)
        calls, checks = [], []   # checks: the run log's bugchecks in the current process (Step X.96)
        s.sb = types.SimpleNamespace(st={"pid": 7, "launches": 1, "release": "usa", "load_fix": True},
                                     _quit=lambda relaunch=False: calls.append("quit") or {"quit": "qmp"},
                                     relaunch=lambda: (calls.append("relaunch"), checks.clear(),
                                                       s.sb.st.update(pid=s.sb.st["pid"] + 1, launches=2)),
                                     alive=lambda: True, frame_boot=lambda: True, bugchecks=lambda: list(checks))
        s.boot = lambda disc, tag: calls.append(f"boot {disc} {tag}") or {"iso_sha12": "6989c84e96eb", "s": 3.0}
        k = kit(s)

        def runs(label):
            k.cands = {0x1000: "keylord"}
            out = {"runs": [{"run": 0, "target": "keylord"}]}
            try:
                calls.append("run 0")
                s.held("tick", "no player tick within 4.0 s", {"class": "hold", "census": ["none"], "bits": None})
            except s.Hold as h:
                h.info["runs"] = out["runs"]
                raise
            finally:
                k.cands = {}
        s.eip_sample = lambda: {"eip": "0x800151ef", "IF": False, "stack": []}
        R = k.row("C0-fake", "usa", "6989c84e96eb", "vanilla-ig-e7",
                  lambda R: (k.step(R, "warp", lambda: 1 / 0), k.step(R, "combo", runs, "C0-fake"),
                             calls.append("never")))
        rows = [json.loads(ln) for ln in (s.ev / "results/runs.jsonl").read_text(encoding="utf-8").splitlines()]
        check("row (Step X.45): the boot with its sha12 checked in the process it found (Step X.96), a step's error "
              "kept as its result, a lost tick ending the row with its census, EIP sample and runs so far; one "
              "results row, tagged",
              calls == ["boot None vanilla-ig-e7", "run 0"] and R["iso_ok"] is True
              and R["fresh"] == {**R["fresh"], "relaunched": False, "pid": 7}
              and R["warp"] == {"err": "ZeroDivisionError: division by zero"}
              and R["hold"]["census"]["class"] == "hold" and R["hold"]["eip"]["eip"] == "0x800151ef"
              and R["hold"]["runs"] == [{"run": 0, "target": "keylord"}] and "combo" not in R and not k.cands
              and not s.watching and len(rows) == 1 and rows[0]["case"] == "X.45-C0-fake" and rows[0]["sandbox"] == "mk",
              f"{calls} {R}")
        # Step X.96: the next row reuses the process while it runs clean, and relaunches after a guest bugcheck in it,
        # a real-time sandbox's boots (the wall clock's, AZ-628) or a lost process
        why = []
        for setup in (lambda: None, lambda: checks.extend(xo.bugchecks("xemu: guest bugcheck 0x0000001e (0xc0000005, "
                                                         "0x000af173, 0x00000000, 0x00000000) from 0x8001ca36\n")),
                      lambda: setattr(s.sb, "frame_boot", lambda: False),
                      lambda: setattr(s.sb, "alive", lambda: "relaunch" in calls)):
            setup()
            calls.clear()
            r = k.row("C0-again", "usa", "6989c84e96eb", "vanilla-ig-e7", lambda R: calls.append("run"))
            why.append((r["fresh"]["relaunched"], r["fresh"].get("due", "")[:12], calls[:2]))
            s.sb.frame_boot, s.sb.alive = (lambda: True), (lambda: True)
        check("row process (Step X.96): the last row's process again while it runs clean; a relaunch after a guest "
              "bugcheck in it, on a sandbox whose boots walk the wall clock, and after a lost process",
              why == [(False, "", ["boot None vanilla-ig-e7", "run"]),
                      (True, "a guest bugc", ["quit", "relaunch"]), (True, "its boots wa", ["quit", "relaunch"]),
                      (True, "the process ", ["quit", "relaunch"])], f"{why}")
        # a row after the last row's xemu died: its spot's load fails there, so a fresh process records it, and the
        # row runs in it (2.105's d00 recorded the spots once; the kit's first try skipped the relaunch)
        dead = [True]

        def rec(tag, disc=None):
            calls.append(f"record_spot {tag}")
            if dead[0]:
                raise ConnectionRefusedError(61, "Connection refused")
            s.spots[tag] = {"level": "levels/earth/e7"}
        s.record_spot, s.sb.read = rec, (lambda va, n: struct.pack("<f", 0.5))
        s.sb.g = types.SimpleNamespace(regs=lambda: {"eax": 0x7000})
        s.sb.relaunch = lambda: calls.append("relaunch") or dead.__setitem__(0, False)
        calls.clear()
        R2 = k.row("C0-dead", "usa", "6989c84e96eb", "vanilla-ig-e7", lambda R: calls.append("run"), spots=(KEYLORD,))
        check("row after a death: the spots fail in the dead process, a fresh one records them, then the row "
              "boots and runs in it",
              calls == [f"record_spot {KEYLORD}", "quit", "relaunch", f"record_spot {KEYLORD}",
                        "boot None vanilla-ig-e7", "run"]
              and R2["spots"]["err"].startswith("ConnectionRefusedError")
              and R2["spots_again"] == {KEYLORD: "levels/earth/e7"} and R2["iso_ok"] is True, f"{calls} {R2}")
        # AZ-422: a placement waits for the stick (input+0x30 clear: here from the 3rd tick on) and the camera's yaw
        # (back within 0.05 rad from the 6th), and a picture advances frames first and is retaken while its bytes equal
        # an earlier picture's
        seen, shots, tick, own = [], [b"A", b"A", b"B"], [0], [0, 3, 0]   # own: the vblanks each screenshot ran

        def cap(n, sched=None, *, label=None, on_tick=None, **_kw):
            rows = []
            for i in range(n):
                tick[0] += 1
                rows.append(row := {"k": i, "state": 0})
                if "stop" in ((on_tick(fake, row, rows) if on_tick else None) or []):
                    break
            seen.append(f"capture {len(rows)}")
            return {"meta": {"rows": len(rows), "stop": None}, "rows": rows, "hits": []}

        def read(va, n):
            if va == 0x7000 + 0x30:
                return bytes([tick[0] < 3])
            if va == 0x7000 + 0x10:
                return struct.pack("<f", 0.5 if tick[0] >= 6 else 2.0)
            return struct.pack("<3f", 1.0, 2.0, 3.0)[:n]

        def shot(name):
            (p := tmp / f"{name}.png").write_bytes(shots.pop(0))
            fake.last_picture = {"advanced": own.pop(0)}
            seen.append(f"shot {name}")
            return p
        fake = types.SimpleNamespace(st={"release": "usa"}, _g=None, _halted=False, read=read,
                                     read_u32=lambda va: 0x500000, frame_advance=lambda n: seen.append(f"advance {n}"),
                                     g=types.SimpleNamespace(regs=lambda: {"eip": xo.PLAYER_TICK, "esp": 0x9000,
                                                                           "eax": 0x7000}, u32=lambda va: 0x481C60))
        p = xs.Sitting("mk2", ev=tmp / "ev2")
        p.sb, p.capture, p.screenshot, p.tick = fake, cap, shot, (lambda timeout=10.0: 0x481C60)
        p.clear_dialog = lambda tries=4: seen.append("clear") or True
        p.place = lambda spot=None, **_kw: seen.append(f"place {spot}") or {"placed": spot, "settled": True, "off_m": 0.1}
        p.spots = {LADDER: {"centre": (1.0, 2.0, 3.0), "cam": 0.5}}
        k2 = kit(p)
        pl = k2.placed(LADDER)
        pics = [k2.pic("p1", 2), k2.pic("p2", 2)]
        check("placed and pic (AZ-422): an R6 place, then the stick's wait and the camera's; a picture advances frames "
              "before its screendump, and one equal to an earlier picture is retaken 4 frames on; its frames count "
              "those the screenshot ran itself (Step X.61)",
              seen == ["clear", f"place {LADDER}", "capture 3", "capture 3", "advance 2", "shot p1", "advance 2",
                       "shot p2", "advance 4", "shot p2"]
              and (pl["free_after"], pl["cam_after"], pl["off_after_wait_m"]) == (3, 3, 0.0)
              and pics == ["p1.png", "p2.png (retaken 1)"] and k2.pics["p1"]["frames"] == 2
              and k2.pics["p2"]["frames"] == 9, f"{seen} {pl} {pics} {k2.pics}")
        # the zipline's and the camera's judges on a made-up ride: hang_start 2 ticks, the ride 4, the let-go
        ride = [(0, 0x105, -1.0), (1, 0x105, -1.0), (2, 5, -1.2), (3, 5, -1.3), (4, 5, -1.3), (5, 5, -1.4), (6, 2, -1.6),
                (7, 2, -1.0), (8, 0, -1.0)]
        rows = [{"k": k_, "state": st, "c": (0.0, 0.0, 10.0), "x": {"anim": 9, "mode": 1, "cab": [0.0, 0.0, 1.5],
                                                                  "o0": [0.0, 0.0, z], "o1": [0.0, 0.0, z]}}
                for k_, st, z in ride]
        per = [{"k": r["k"], "act2_dist": 5.0 - 0.5 * r["k"], "act2_min": 5.0 - 0.5 * r["k"], "act2_pitch": -30.0,
                "aim2_dc": 0.0, "aim2_min": -0.1 if r["k"] == 3 else 0.0, "aim_dc": -1.0, "sw1": [1] if r["k"] == 2 else []}
               for r in rows]
        z, cj, lg = zip_summary(rows), cam_judge(per, rows, lambda k_: rows[k_]["state"] == 5), steps_from(rows, 5, 4)
        p.private = tmp / "priv"
        p.private.mkdir()
        k2.priv_trace("lane-T", rows)
        k2.priv_trace("main-T", [{**r, "c": (0.0, 0.002 * (r["k"] == 4), 10.0)} for r in rows[:-1]])
        tc = k2.trace_cmp("lane-T", "main-T")
        check("judges: the zipline's hang_start and ride against the cable, the camera on the ride (its point under "
              "the centre, X20's raise, collapsed ticks, sweeps), the let-go's steps to its stance, and a lane trace "
              "against main's (differences only)",
              z["hang_start_ticks"] == 2 and z["ride_ticks"] == 4 and z["ride_dz"] == [-2.9, -2.7] and z["step_z"] == -0.2
              and cj["n"] == 4 and cj["under_centre"] == 1 and cj["x20_raised"] == 4 and cj["act2_dist"] == [2.5, 4.0]
              and cj["collapsed"] == 0 and cj["sw_ticks"]["81066"] == 1 and lg["max_step"] == 0.6
              and lg["stance_ticks"] == 2 and i_letgo(rows) == 6
              and tc == {"ticks": 8, "lane": 9, "main": 8, "state_differs": 0, "centre_max_m": 0.002,
                         "f168_max_m": 0.0, "over_1mm": {"centre": 1, "f168": 0}}, f"{z} {cj} {lg} {tc}")
        # Step 2.107: the frame's score on a made-up camera (the game's camera pass, G0's calibration: a right-handed
        # look-at down view -z, w = -z, 70 degrees across at 4:3, near 0.11, no far plane), the garret4 x1 rest: the
        # eye 5.11 m back at -30 degrees from the point at his eye height; the same picture at x2 with the rig doubled
        # (what X25 builds on); a 1 m eye step is a snap, a 2 m eye a collapse
        def look(eye, at):
            zz = [e - a for a, e in zip(at, eye)]   # the view's +z points back from the point to the eye
            zz = [v / math.sqrt(sum(u * u for u in zz)) for v in zz]
            xx = [-zz[1], zz[0], 0.0]   # cross((0, 0, 1), z)
            xx = [v / math.hypot(*xx) for v in xx]
            yy = [zz[1] * xx[2] - zz[2] * xx[1], zz[2] * xx[0] - zz[0] * xx[2], zz[0] * xx[1] - zz[1] * xx[0]]
            return [(xx[0], yy[0], zz[0], 0.0), (xx[1], yy[1], zz[1], 0.0), (xx[2], yy[2], zz[2], 0.0),
                    (-sum(a * b for a, b in zip(xx, eye)), -sum(a * b for a, b in zip(yy, eye)),
                     -sum(a * b for a, b in zip(zz, eye)), 1.0)]
        xs_ = 1 / math.tan(math.radians(35.0))
        proj = [(xs_, 0.0, 0.0, 0.0), (0.0, xs_ / 0.75, 0.0, 0.0), (0.0, 0.0, -1.0, -1.0), (0.0, 0.0, -0.11, 0.0)]
        ortho = [(0.8, 0.0, 0.0, 0.0), (0.0, 0.8, 0.0, 0.0), (0.0, 0.0, -0.2, 0.0), (0.0, 0.0, -1.3333, 1.0)]
        ident = [(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)]
        c30, s30 = math.cos(math.radians(30.0)), math.sin(math.radians(30.0))

        def rest(x):
            pt = (0.0, 0.0, 1.9925 * x)
            return pt, (0.0, -5.11 * x * c30, pt[2] + 5.11 * x * s30)
        bones2 = [(-0.3, 0.0, 0.0), (0.3, 0.0, 2.0018)]   # on the axis: workflow A's -0.538 bottom
        pt1, eye1 = rest(1.0)
        m1 = frame_score(look(eye1, pt1), proj, ident, bones2, ((0.0,) * 3, (0.0,) * 3), pt1)
        pt2, eye2 = rest(2.0)
        m2 = frame_score(look(eye2, pt2), proj, ident, [tuple(2 * v for v in b) for b in bones2],
                         ((0.0,) * 3, (0.0,) * 3), pt2, prev=(m1["_eye"], m1["_forward"]))
        step = frame_score(look((1.0, eye1[1], eye1[2]), pt1), proj, ident, bones2, ((0.0,) * 3, (0.0,) * 3), pt1,
                           prev=(m1["_eye"], m1["_forward"]))
        check("frame score (Step 2.107): garret4's x1 rest framed (the point at the frame's centre 5.11 m from the eye "
              "along its view, the box whole, its feet low in the frame), the same picture at x2 with the rig doubled, "
              "a 1 m eye step a snap, an eye 2 m from the point a collapse",
              max(abs(v) for v in m1["aim_ndc"]) < 1e-6 and abs(m1["eye_aim_m"] - 5.11) < 1e-6
              and m1["eye_view_err"] < 1e-4 and m1["box_in_frame"] and not m1["eye_in_body"] and m1["behind_near"] == 0
              and abs(m1["bottom"] + 0.538) < 0.001 and abs(m1["aim_frac"] - 1.9925 / 2.0018) < 1e-6
              and abs(m2["bottom"] - m1["bottom"]) < 1e-9 and abs(m2["top"] - m1["top"]) < 1e-9
              and abs(m2["eye_aim_m"] - 10.22) < 1e-6 and no_snap(m1, 0.0, 1.0) and not no_snap(step, 0.0, 1.0)
              and no_collapse(5.11, 1.0) and not no_collapse(2.0, 1.0), f"{m1} {m2} {step}")
        # the reads behind it: per frame the player's draw through the camera (its shadow pass's orthographic one,
        # another critter's and a second draw of it ignored), X8's point after X20, the surface; one
        # results/frames.jsonl row of numbers (no position), the row's summary
        mem: dict[int, int] = {}

        def put(va, b):
            mem.update(zip(range(va, va + len(b)), b))
        P_, cam_, dsp, osp, psp, xsp = 0x500000, 0x600000, 0x9000, 0x9800, 0xA000, 0xA800

        def m44(m):
            return struct.pack("<16f", *(v for row in m for v in row))
        put(dsp + 0x18, struct.pack("<I", P_))
        put(osp + 0x8, struct.pack("<I", P_))
        put(xsp + 0x18, struct.pack("<I", 0x510000))
        put(P_ + 0x17C, struct.pack("<I", 0x700000))
        put(0x700008, struct.pack("<I", 0x710000))
        for i_, b_ in enumerate(bones2):
            put(0x710000 + 0xB0 * i_ + 0xA0, struct.pack("<3f", *b_))
        put(WORLD_M, m44(ident))
        put(PROJ_M, m44(proj))
        put(cam_ + 0x190, struct.pack("<I", P_))
        put(psp + 0x50, struct.pack("<3f", *pt1))
        put(cam_ + 0x194, struct.pack("<5f", 0.1, -0.5236, 5.0, -0.5236, 5.0))
        fm = types.SimpleNamespace(st={"release": "usa"}, read=lambda va, n: bytes(mem.get(a, 0) for a in range(va, va + n)))
        fm.read_u32 = lambda va: struct.unpack("<I", fm.read(va, 4))[0]
        f3 = xs.Sitting("mk3", ev=tmp / "ev3")
        (f3.ev / "results").mkdir(parents=True)
        f3.sb = fm
        k3 = kit(f3)
        k3.bones, k3._case = 2, "X.45-F"
        k3.frame_on(((0.0,) * 3, (0.0,) * 3), 1.0)
        k3._fk, k3._fr, k3._fP = -1, {}, P_
        rows3 = []
        for i_, eye_ in enumerate((eye1, eye1, (1.0, eye1[1], eye1[2]))):
            put(VIEW_M, m44(look(eye_, pt1)))
            put(WORLD_M, m44(ident[:3] + [(0.0, 0.0, 0.05 * (i_ == 2), 1.0)]))   # tick 2's drawn origin 5 cm up
            k3._frame_tick(fm, 0x400000)
            rows3.append({"k": i_, "state": 0})
            put(PROJ_M, m44(ortho))
            k3._hk_draw(fm, {"eip": 0x3E887, "esp": osp})
            put(PROJ_M, m44(proj))
            k3._hk_draw(fm, {"eip": 0x3F075, "esp": xsp})
            k3._hk_draw(fm, {"eip": 0x3F075, "esp": dsp})
            k3._hk_draw(fm, {"eip": 0x3F075, "esp": dsp})
            k3.rd_pt2(fm, {"edi": cam_, "esp": psp})
        k3._frame_tick(fm, 0x400000)
        rows3.append({"k": 3, "state": 0})
        sm = k3.frames(rows3, "F-test")
        fr = [json.loads(ln) for ln in (f3.ev / "results/frames.jsonl").read_text(encoding="utf-8").splitlines()]
        pt3 = fr[0]["per_tick"] if fr else []
        keys = {k_ for o in pt3 for k_ in o}
        check("frame reads (Step 2.107): the player's first draw a frame through the camera (its shadow pass skipped "
              "and counted, another critter's ignored, a second counted), "
              "X8's point after X20 and the camera's state, the eye's step a snap; one frames.jsonl row of numbers "
              "with no position, its summary by state in the row's frames",
              len(fr) == 1 and fr[0]["case"] == "X.45-F" and len(pt3) == 4 and pt3[0]["draws"] == 3
              and abs(pt3[0]["eye_aim_m"] - 5.11) < 1e-3 and pt3[0]["box_in_frame"] and pt3[1]["d_eye_m"] == 0.0
              and pt3[2]["snap"] and not pt3[1]["snap"] and pt3[3]["missing"] == ["P", "b", "p", "v", "w"]
              and pt3[0]["cam"][:3] == [0.1, -0.5236, 5.0] and not keys & {"P", "w", "v", "p", "b", "surf", "_eye"}
              and [o.get("d_origin_m") for o in pt3[:3]] == [0.0, 0.0, 0.05]
              and sm["by_state"]["0x0"]["d_origin_max"] == [0.0, 0.05]
              and sm["by_state"]["0x0"]["n"] == 3 and sm["by_state"]["0x0"]["whole"] == 3
              and sm["by_state"]["0x0"]["snaps"] == 1 and k3.frame_sums["F-test"] is sm, f"{fr} {sm}")
        csp = 0xB000   # 0x80C3A: the sight sweep's frame (Step 2.116)
        put(csp + 4, struct.pack("<I", 0xB800))
        put(csp + 8, struct.pack("<I", 0xB810))
        put(0xB800, struct.pack("<3f", 0.0, -3.0, 4.0))
        put(0xB810, struct.pack("<3f", 0.0, 0.0, 0.0))
        put(csp + 0x1C, struct.pack("<I", cam_))
        put(cam_ + 0x1B4, struct.pack("<f", 1.0))
        put(csp + 0x94, struct.pack("<f", 0.4))
        sr = k3.rd_sight(fm, {"eax": 0x101, "esp": csp})
        check("sight read (Step 2.116): AL, the game's hit fraction from the camera end, its 3 m from the point on a "
              "5 m line, the blocked timer X19 may set", sr == {"al": 1, "frac": 0.4, "near_m": 3.0, "blocked": 1.0},
              f"{sr}")
        k3.words = {"x29_swaps": 0xB900, "x8_under": 0xB904, "b2_holds": 0xB908, "r1_base_p": 0xB90C,
                    "r1_off": 0xB910, "r1_acts": 0xB914}   # the build's words
        put(0xB900, struct.pack("<3if2i", 3, 1, 2, -0.5235988, 1, 12))
        wn = k3.words_now(fm)
        check("shim words (Steps 2.116b, 2.116d, 2.116e): X29's swap count, X8's swim side, B2's holds and R1's base "
              "pitch (its bits), off and acts read per tick at the build's VAs",
              wn == {"x29_swaps": 3, "x8_under": 1, "b2_holds": 2, "r1_base_p": -1090123118, "r1_off": 1,
                     "r1_acts": 12}, f"{wn}")
        sj = swim_judge([2.1, 2.0, 0.3, -0.9, -1.0, None, -1.1, 0.8])
        check("swim judge (G7): the side changes and the push band's ticks over the camera's height over the surface",
              sj == {"n": 7, "range": [-1.1, 2.1], "side_changes": 2, "band_ticks": 1}, f"{sj}")
        rv = (reversals([10.19, 2.207, 2.215, 2.223, 2.206] + [2.206 + 0.0004 * i for i in range(25)]),
              reversals([5.09, 2.209, 2.222, 2.203, 2.203]), reversals([7.4, 7.39, 2.21, 7.4, 2.21, 7.4]))
        check("reversals (K5): a pull-in, a 1.6 cm rebound and back, then the regrow's creep at the wall: 2, as the "
              "game's own; a sawtooth counts each turn", rv == (2, 2, 3), f"{rv}")
        k.cands, x = {0x1000: "sleeth"}, lambda c, f: {"frac": f, "col": c, "anim": c + 1, "fc": 0, "tg": {}}
        srows = [{"k": i, "state": 0x100 if i < 8 else 0, "x": x(i // 4, (i % 4) / 4)} for i in range(10)]
        shits = [{"k": kk, "va": hex(HIT_T3), "attacker": 0x2000, "target": 0x1000, "ht": 0} for kk in (2, 4)]
        shits += [{"k": kk, "va": hex(APPLY_DAMAGE), "critter": 0x1000, "hp": 100, "new_hp": 90} for kk in (2, 4)]
        sw = k.swings(srows, shits, 0x2000)
        k.cands = {}
        check("swings (Step 2.132's record): a hit at the tick one swing ends and the next starts is the ending swing's "
              "only", [[d[0] for d in w["drops"]] for w in sw] == [[2, 4], []], f"{[w['drops'] for w in sw]}")
        k3.jiggle = (0xC000, 2)   # X41's shown words (Step 2.156): two rows
        put(0xC000, struct.pack("<6fd3f4x6fd3f4x", 1.0, -2.0, 30.0, 0.1, -0.05, 0.4, 1.5, 0.9, 1.0, 1.25, 3.0, 12.0,
                                0.0, 0.0, 0.0, 0.0, 1.5, 1.0, 1.0, 1.0))
        jn = k3.jiggle_now(fm)
        jt = k2.jiggle_trace("j60", [{"c": (0.0, 0.1 * i, 0.0), "x": {"jg": [[0.0] * 6 + [1.0 + i / 60]]}} for i in range(3)])
        jt = [r["speed"] for r in json.loads((p.private / jt["trace"]).read_text(encoding="utf-8"))]
        jrows = [{"x": {"jg": [[0.0, 0.0, z, 0, 0, 0.2], [0.0, f, 0.0, 0, 0, 0.1]]}}
                 for z, f in ((0.0, 0.0), (12.0, 3.0), (25.0, 9.0), (6.0, -7.0), (-8.0, -2.0), (1.0, 0.0))]
        jm = jiggle_metric(jrows)
        check("X41 words (Step 2.156): both rows' offset, roll, yaw, raw, clock and squash scales read per tick; the "
              "AZ-648 metric (largest tick, ticks over 10 mm), peaks and extrema over 5 mm; the trace's speed over X41's "
              "clock (60 Hz)",
              jn == [[1.0, -2.0, 30.0, 0.1, -0.05, 0.4, 1.5, 0.9, 1.0, 1.25], [3.0, 12.0, 0.0, 0.0, 0.0, 0.0, 1.5, 1.0, 1.0,
                                                                              1.0]] and jt == [None, 6.0, 6.0]
              and jm[0]["largest_tick_mm"] == 19.0 and jm[0]["ticks_over_10mm"] == 4 and jm[0]["peak_mm"] == 25.0
              and jm[0]["extrema"]["up"] == [25.0, -8.0] and jm[1]["extrema"]["fwd"] == [9.0, -7.0]
              and jm[1]["raw_max"] == 0.1, f"{jn} {jm} {jt}")
        pics = []
        for n_, col in enumerate((b"\x10\x20\x30", b"\x40\x50\x60")):
            p_ = tmp / f"f{n_}.png"
            write_png(p_, 4, 3, [bytearray(col * 4) for _ in range(3)])
            pics.append(p_)
        cs = contact_sheet(tmp / "sheet.png", pics, [[1.0, -2.0], [0.5, 0.5]], plot_h=10, beside=pics[::-1])
        sw_, sh_, sl_ = read_png(tmp / "sheet.png")
        check("contact sheet (Step 2.156): two 4x3 frames side by side, the control's under them, the offsets plotted "
              "under both; the PNG reads back with each frame's pixels",
              (sw_, sh_) == (12, 3 + 4 + 3 + 4 + 10) and cs["size"] == [12, 24] and sl_[0][:3] == b"\x10\x20\x30"
              and sl_[0][24:27] == b"\x40\x50\x60" and sl_[7][:3] == b"\x40\x50\x60", f"{cs} {(sw_, sh_)}")
        # Step 2.173 (D603, D604): the frame's cost on a stand-in sitting: the vanilla control's row and the build's
        # (its attack 3x the control's triangles), each scene its phase's lines played with per-flip counters and
        # timed; the build's L1 lines in its results row and under the report's WARNINGS; three alternated real-time
        # pairs where the build flips less, judged fell, drafting the fork request
        fcs = xs.Sitting("mk4", step="2.173", ev=tmp / "ev4")
        for sub in ("results", "captures", "logs"):
            (fcs.ev / sub).mkdir(parents=True)
        disc, played, idle, gpus, presents = [None], [], [0], [], [0]

        def advance(n, lines=None, gpu=False):   # a rate arm (counters off, Step X.68): the build flips less
            played.append(list(lines or []))
            gpus.append(gpu)
            heavy = disc[0] is not None and any(" down " in ln for ln in lines or [])
            nf = int(n * (0.4 if disc[0] is not None and not gpu else 0.5))
            presents[0] += nf
            per = [{"triangles": 5, "begin-end": 2}] + [{"triangles": (300_000 if heavy else 100_000) + i,
                                                         "begin-end": 30} for i in range(nf - 1)]
            fsb.st["frame"] += n
            return {"frame": fsb.st["frame"], "windows": 1, **({"gpu-counters": {"flips": nf, **(
                {"per-flip": per} if gpu == "per-flip" else {})}} if gpu else {})}

        def prof():
            idle[0] += 10**8
            return {"launch": 1, "idle-ns": idle[0]}
        fsb = types.SimpleNamespace(st={"pid": None, "launches": 1, "release": "usa", "deterministic": True,
                                        "vblank_ns": 16_666_666, "xemu_version": "0.16.2", "frame": 0,
                                        "xemu_sha12": "b1b1b1b1b1b1"},
                                    _quit=lambda relaunch=False: {"quit": "qmp"}, relaunch=lambda: None,
                                    alive=lambda: True, frame_boot=lambda: False, bugchecks=lambda: [],
                                    code=lambda b: 232 if b == "a" else 233, blockstats=lambda: {}, host_profile=prof,
                                    frame_advance=lambda n, gpu=False: advance(n, None, gpu),
                                    play_recording=lambda lines, frames, gpu=False: advance(frames, lines, gpu),
                                    read_u32=lambda va: presents[0] if va == xo.PRESENT_COUNT else 0,
                                    g=types.SimpleNamespace(regs=lambda: {"eip": xo.PLAYER_TICK, "esp": 0x9000}))
        fcs.sb, fcs.tick = fsb, (lambda timeout=10.0: 0x481C60)
        fcs.boot = lambda d, tag, **_: disc.__setitem__(0, d) or {
            "iso_sha12": "6989c84e96eb" if d is None else "b0b0b0b0b0b0", "xbe_sha256": "c0" * 32, "level": tag}
        fcs.capture = lambda n, sched=None, **_: {"meta": {"rows": n}}
        fcs.warp = lambda level, **_: {"ok": True, "level": level, "s": 1.0}
        (bi := tmp / "b.iso").write_bytes(b"x")
        k4, kw4 = kit(fcs), {"levels": ("a1", "w1"), "phases": ("idle", "attack"), "n": 12}
        Rc = k4.row_cost("FC-ctl", "usa", "6989c84e96eb", **kw4)
        Rb = k4.row_cost("FC-b", str(bi), "b0b0b0b0b0b0", control=Rc, **kw4)
        fails = cost_scenes([Rc, {"row": "FC-x", "boot": {"err": "SystemExit: boot hung"}}])   # a boot that failed
        w_fail = xo.frame_warning(cost_scenes(Rb)[0], fails)
        off4 = k4.rate_pairs("FC-off", str(bi), "b0b0b0b0b0b0", scene="a1/attack", control_sha="6989c84e96eb", n=12)
        fsb.st["deterministic"] = False   # the pairs' sitting: real time
        rt4 = k4.rate_pairs("FC-rt", str(bi), "b0b0b0b0b0b0", scene=Rb["frame_cost"]["heaviest"]["scene"],
                            control_sha="6989c84e96eb", n=12)
        V = k4.rate_verdict("FC-v", Rb, Rc, rt4, recipe="build", iso=bi, out=tmp / "req",
                            offscreen=off4)
        req4 = Path(V["request"] or tmp / "none")
        txt4 = req4.read_text(encoding="utf-8") if req4.exists() else ""
        rows4 = [json.loads(ln) for ln in (fcs.ev / "results/runs.jsonl").read_text(encoding="utf-8").splitlines()]
        head4 = fcs.header()
        l1 = ["frame cost: a1/attack triangles 300,004 a flip, 1.41x vanilla's heaviest (213,262, pack-03)",
              "frame cost: w1/attack triangles 300,004 a flip, 1.41x vanilla's heaviest (213,262, pack-03)"]
        check("frame cost (Step 2.173, D603, D604): the control's and the build's rows (a1's save, the warp, each "
              "scene's phase lines played with per-flip counters, timed); the build's L1 lines in its results row and "
              "the report's WARNINGS, its heaviest scene timed in 3 alternated pairs with the counters off and the "
              "flips by the game's present counter (Step X.68), a real-time drop drafting the fork request (the det "
              "offscreen pairs' host ms in it, each arm's binary, load and a1 by state, the settle as run); a "
              "control row whose boot failed adds no scene and breaks no warning",
              fails[1] == {} and w_fail["warn"] == l1 and len(off4["pairs"]) == 3
              and all(len(p["ms"]) == 2 and None not in p["ms"] for p in off4["pairs"] + rt4["pairs"])
              and re.search(r"det offscreen: [0-9.]+ / [0-9.]+ \(3 pairs\) ms a vblank", txt4) is not None
              and "In the scene: settle 30 player ticks with no input, then 2400 more" in txt4
              and "rates (real time): binary b1b1b1b1b1b1; loaded from state vanilla-ig-a1 on a clone of the D98 "
                  "drive, then boot_build: a reset into the disc, SaveGame #1, its first steady tick; a1/attack "
                  "reached by state (a1, the loaded save's level; no warp)." in txt4
              and "counts (det null): binary b1b1b1b1b1b1; loaded from state vanilla-ig-a1" in txt4
              and "flips counted by the game's present counter, the NV2A counters off." in txt4
              and rt4["flips_by"] == off4["flips_by"] == "guest" and gpus.count(False) == 12
              and set(gpus) == {False, "per-flip"} and Rb["boot"]["binary"] == "b1b1b1b1b1b1"
              and list(Rc["frame_cost"]["scenes"]) == ["a1/idle", "a1/attack", "w1/idle", "w1/attack"]
              and "warn" not in Rc
              and Rc["frame_cost"]["scenes"]["a1/idle"]["steady"] == 5
              and Rc["frame_cost"]["scenes"]["a1/idle"]["times"]["busy_ns_flip"] == 16_666_665
              and ["+0 down 232", "+4 up 232", "+11 clear"] in played and [] in played
              and Rb["warn"] == l1 and Rb["frame_cost"]["heaviest"]["scene"] == "a1/attack"
              and Rb["frame_cost"]["realtime_due"] and len(rt4["pairs"]) == 3 and rt4["mode"] == "real time"
              and {(p["control"], p["build"]) for p in rt4["pairs"]} == {(0.5, 0.3333)}
              and V["fps"]["verdict"] == "fell" and len(V["warn"]) == 1
              and V["warn"][0].startswith("frame rate: a1/attack")
              and req4.name == "FRAME-b0b0b0b0b0b0-a1-attack.txt" and "WHAT DROPS: a1/attack." in txt4
              and "+0 down 232" in txt4 and len(rows4) == 15 and rows4[1]["warn"] == l1
              and "WARNINGS (D603, D604" in head4 and all(x in head4 for x in l1 + V["warn"]),
              f"{Rb.get('warn')} {rt4} {V} {played[:6]}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)   # its own scratch, deleted directly (D147)
    xo.log("selftest: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1:] != ["selftest"]:
        sys.exit("usage: python -m devkit.xemu.sittings.model_kit selftest   (the kit itself is imported by a "
                 "sitting's driver)")
    sys.exit(selftest())

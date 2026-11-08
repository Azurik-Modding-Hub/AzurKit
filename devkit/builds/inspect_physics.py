"""``python -m devkit builds inspect-physics (--iso IMAGE | --xbe XBE)``: what
each player_physics slider site of any build holds (Modkit's
``inspect-physics``, ported in Step 4.6l), each at its release's own
address; run it first when a build "does nothing" in game: it shows
whether the bytes landed.

Each row is ``VANILLA`` (the release's vanilla bytes), ``PATCHED`` (with the
value it holds, and where the code now reads it) or ``DRIFTED`` (neither:
the length and sha256[:12] of what is there, never the bytes):

- gravity, the two fuel costs and the seven air-control speeds: the float
  the slider overwrites in place (``vanilla``, its vanilla value);
- swim, jump, flap and the far-descent flap: the 6-byte x87 load or
  multiply the slider points at a float of its own in the shim room (jump
  and flap hold gravity x k^2, swim and the far-descent flap their vanilla
  x k);
- roll distance, roll speed, climb speed and the flap ceiling: the hook
  the slider writes, a CALL into the shim room to its hand-written shim,
  and the k in the shim's data block there;
- the speed toggle: the PlayerControl tick's hook, a CALL into the shim room;
- walk: garret4's ``runSpeed`` in the image's config.xbr (``NOT READ`` for a
  raw XBE), against the vanilla 7.0.

A build it can't read, of neither release or with no vanilla XBE to compare
with is one ``inspect-physics:`` line and exit 2.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys

from azurkit.core import xbe
from azurkit.tools.mods.packs import player_physics as pp
from devkit.builds import source
from devkit.builds.verify_patches import digest, in_room, lands, read_at

HAND = {   # a hand shim's hook (USA), its size and where its body holds k's address
    "roll": (pp.ROLL_HOOK, 5, 11),
    "roll_time": (pp.ROLL_TIME_HOOK, 6, 17),
    "climb": (pp.CLIMB_HOOKS[0][0], pp.CLIMB_HOOKS[0][1], 8),
    "ceiling": (pp.CEILING_HOOK, 6, 8),
}
LOADS = {"swim": pp.SWIM, "jump": pp.JUMP, "flap": pp.FLAP, "flap_below_peak": pp.BELOW_PEAK}
IMMEDIATES = {"gravity": pp.GRAVITY.va, "descent_fuel": pp.DESCENT_FUEL, "entry_fuel": pp.ENTRY_FUEL}


def _f32(data: bytes) -> float:
    return struct.unpack("<f", data)[0]


def _float_at(build: source.Build, va: int) -> float | None:
    """The float a build carved at ``va`` (in the shim room), else ``None``."""
    at = xbe.resolve_va_to_file(build.xbe, va) if in_room(build, va) else None
    return None if at is None or at + 4 > len(build.xbe) else _f32(build.xbe[at:at + 4])


def immediate(build: source.Build, usa_va: int) -> dict:
    va, _, got, was = read_at(build, usa_va, 4)
    return {"site_va": va, "state": "VANILLA" if got == was else "PATCHED", "value": _f32(got), "vanilla": _f32(was)}


def load(build: source.Build, usa_va: int) -> dict:
    """A 6-byte ``op dword [abs32]`` the slider points at a carved float."""
    va, _, got, was = read_at(build, usa_va, 6)
    if got == was:
        return {"site_va": va, "state": "VANILLA"}
    inject = struct.unpack_from("<I", got, 2)[0]
    value = _float_at(build, inject) if got[:2] == was[:2] else None
    if value is None:
        return {"site_va": va, "state": "DRIFTED", "got": digest(got)}
    return {"site_va": va, "state": "PATCHED", "inject_va": inject, "value": value}


def hand(build: source.Build, usa_va: int, size: int, k_at: int) -> dict:
    """A hook's CALL to a hand shim whose body reads k at the address ``k_at`` into it."""
    va, at, got, was = read_at(build, usa_va, size)
    if got == was:
        return {"site_va": va, "state": "VANILLA"}
    body = (va + 5 + struct.unpack_from("<i", got, 1)[0]) & 0xFFFFFFFF
    data_at = xbe.resolve_va_to_file(build.xbe, body + k_at)
    inject = (struct.unpack_from("<I", build.xbe, data_at)[0]
              if data_at is not None and data_at + 4 <= len(build.xbe) else None)
    value = _float_at(build, inject) if inject is not None and lands(build, at, "call") else None
    if value is None:
        return {"site_va": va, "state": "DRIFTED", "got": digest(got)}
    return {"site_va": va, "state": "PATCHED", "inject_va": inject, "value": value}


def toggle(build: source.Build) -> dict:
    hook, size = pp.TOGGLE_HOOKS[0]
    va, at, got, was = read_at(build, hook.va, size)
    if got == was:
        return {"site_va": va, "state": "VANILLA"}
    if not lands(build, at, "call"):
        return {"site_va": va, "state": "DRIFTED", "got": digest(got)}
    return {"site_va": va, "state": "PATCHED", "inject_va": (va + 5 + struct.unpack_from("<i", got, 1)[0]) & 0xFFFFFFFF}


def walk(build: source.Build) -> dict:
    """garret4's runSpeed (D53), the cell the walk slider scales."""
    w = pp.WALK
    row = {"cell": f"{w.file} {w.table}/garret4/runSpeed"}
    vanilla = source.vanilla_tables()[w.table].number("garret4", "runSpeed")
    if (tables := build.tables) is None:
        return row | {"state": "NOT READ"}
    try:
        value = tables[w.table].number("garret4", "runSpeed")
    except (KeyError, LookupError, ValueError):   # not the game's config.xbr
        return row | {"state": "DRIFTED"}
    return row | {"state": "VANILLA" if value == vanilla else "PATCHED", "value": value, "vanilla": vanilla}


def inspect_player_physics(build: source.Build) -> dict:
    """``{"xbe_size", "release", "sliders": {name: row}, "air_control": [row] * 7}``."""
    sliders = {"walk": walk(build), "gravity": immediate(build, IMMEDIATES["gravity"])}
    sliders |= {name: load(build, va) for name, va in LOADS.items()}
    sliders |= {name: hand(build, *args) for name, args in HAND.items()}
    sliders |= {name: immediate(build, IMMEDIATES[name]) for name in ("descent_fuel", "entry_fuel")}
    sliders["speed_toggle"] = toggle(build)
    return {"xbe_size": len(build.xbe), "release": build.release.name, "sliders": sliders,
            "air_control": [immediate(build, va) for va in pp.AIR_CONTROL]}


def line(label: str, row: dict) -> str:
    text = f"  {label:16s} [{row['state']}]  {row.get('cell') or f'VA 0x{row['site_va']:X}'}"
    if "got" in row:
        return f"{text}  got {row['got']}"
    if "inject_va" in row:
        text += f" -> 0x{row['inject_va']:X}"
    if "value" in row:
        text += f" = {row['value']:.4f}"
    if row["state"] == "PATCHED" and row.get("vanilla"):
        text += f"  ({row['value'] / row['vanilla']:.3f}x vanilla)"
    return text


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit builds inspect-physics",
                                description="What each player_physics slider site of a build holds.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--iso", help="a built image (its default.xbe and gamedata/config.xbr are read in place)")
    src.add_argument("--xbe", help="a built default.xbe (walk's config.xbr cell isn't read)")
    p.add_argument("--original", help="the vanilla image or default.xbe of the build's release (default: the "
                                      "player's image, found as AZURKIT_ISO or AZURKIT_ISO_EUROPE names it)")
    p.add_argument("--json", action="store_true", help="the report as one JSON object")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        build = source.load(args.iso or args.xbe, args.original)
        report = inspect_player_physics(build)
    except (OSError, ValueError) as exc:
        print(f"inspect-physics: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"Inspecting: {build.path}\n  XBE size: {report['xbe_size']:,} bytes, the {build.release.label} release\n")
    print("Player physics sliders:")
    for name, row in report["sliders"].items():
        print(line(name.replace("_", " "), row))
    print("Air-control sites:")
    for row in report["air_control"]:
        print(line("air control", row))
    return 0

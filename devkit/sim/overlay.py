"""Parametric L3 (Step X.11, D173's T6): a modded build laid over a vanilla snapshot.

A snapshot holds the code and the config cells of the build that ran when it was taken.  An :class:`Overlay` is
what another build changes, so :class:`~devkit.sim.l3.L3` can run that build's movement from any vanilla
snapshot (``L3(snap, vanilla_xbe, overlay=...)``), at any slider value, without a sitting:

- **the XBE's changes** (:func:`code_writes`): every byte of a section the build changes (code, ``.rdata``
  constants, a section grown into its padding by the carve allocator), and each section the build appends
  (``SHIMS``), mapped where the XBE loader would put it.  A byte is written only where the snapshot holds what
  vanilla's loader put there: a changed byte of a writable section the game has since rewritten (live data) is
  refused by name, as is an appended section over a page the snapshot holds.  The XBE header (the section table,
  which the kernel's loader reads, not the game's step) is left as the snapshot holds it.
- **the config cells** (:data:`CELLS`): config.xbr is read at boot into the game's own structures, so a build's
  cell is poked there: garret4's ``runSpeed`` into its CritterData (+0x40, f32, the player's species
  ``[critter+0x178]``) and each air shield's ``Flaps`` into its row of the armor slot vector 0x38C4D4 (+0x38, the
  int32 the loader 0xF5A40 truncates to).  Any other cell is refused by name.
- **the copies** (:data:`COPIES`): a constant the game copied out when the world was built is rewritten where it
  went, if the snapshot holds vanilla's value there: the world clock's quantum (0x198410, copied into the player's
  scheduler [entity+0xC]+0xC at 0x51BFB; fps_unlock sets it to 1/F, and an event time quantized to vanilla's 1/30
  at 60 Hz left a ledge mount's state 0x100 running forever in Step X.11's measurements).

Any other copy goes unseen; Step X.11's sitting compares runs on an overlaid vanilla snapshot with the real builds
(docs/SIMULATOR.md § "Overlays").  Level files are the snapshot's own.  Dev tooling (Unicorn is a dev dependency);
prints no game bytes.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from typing import Callable, NamedTuple

from devkit.sim.ports import parse_xbe_sections

CR_SPECIES, SPECIES_RUN_SPEED = 0x178, 0x40   # critter -> its CritterData (the species); runSpeed, f32
ARMOR_SLOTS, SLOT_SIZE, SLOT_FLAPS = 0x38C4D4, 0x40, 0x38   # std::vector<slot> begin, end; a slot's Flaps (int32)
SHIELDS = ("air_shield_1", "air_shield_2", "air_shield_3")
# constant VA -> (where the game copied it: from the player entity, why)
COPIES = {0x198410: (lambda u32, entity: u32(entity + 0xC) + 0xC,
                     "the world clock's quantum: [scheduler+0xC], which 0xAB830 snaps event times to (0x51BFB)")}
# (table, entity, property) -> how the loaded value is held: the config.xbr cells a movement slider writes
CELLS = {("critters_critter_data", "garret4", "runSpeed"): "f32",
         **{("armor_properties", s, "Flaps"): "trunc" for s in SHIELDS}}
# a multiplier slider's cell (AzurKit's picks it from the vanilla tables) -> that vanilla value: garret4's runSpeed
BASES = {("critters_critter_data", "garret4", "runSpeed"): 7.0}   # m/s (xemu 7.000, lldb CritterData+0x40)


class Overlay(NamedTuple):
    """A build as L3 lays it over a vanilla snapshot: its ``default.xbe`` and the config cells it changes
    (``((table, entity, property, value), ...)``, value as config.xbr stores it), and a label."""
    xbe: bytes
    cells: tuple = ()
    name: str = ""

    @property
    def sha12(self) -> str:
        """sha256[:12] of the XBE and the cells: the overlay's identity."""
        h = hashlib.sha256(self.xbe)
        h.update(json.dumps(sorted(map(list, self.cells))).encode())
        return h.hexdigest()[:12]


def build(vanilla_xbe: bytes, params: dict, name: str = "") -> Overlay:
    """The overlay of ``vanilla_xbe`` built with the packs ``params`` names (``{pack: {slider: value}}``, applied
    once each in registry order, as every build applies them), in memory: the XBE's sites as AzurKit's build plans
    them (:func:`devkit.sim.ports.build`), a config.xbr slider as the cell it writes (its value; a multiplier's
    times the vanilla cell :data:`BASES` holds).  A config slider whose cell isn't in :data:`CELLS` is refused by
    name."""
    from azurkit.tools.mods.engine import XbrParametricEdit
    from devkit.sim.ports import build as build_xbe
    from devkit.sim.ports import ordered_packs

    xbe_params, cells = {}, []
    for pack in ordered_packs(params):
        given = dict(params.get(pack.name, {}))
        for edit in pack.sites:
            if not isinstance(edit, XbrParametricEdit) or edit.name not in given:
                continue
            value = float(given.pop(edit.name))
            key = (edit.table, edit.entity, edit.prop)
            if key not in CELLS:
                raise ValueError(f"{pack.name}.{edit.name}: config.xbr {'/'.join(key)} is not a cell an L3 overlay "
                                 f"pokes ({', '.join('/'.join(k) for k in CELLS)})")
            cells.append((*key, value * BASES[key] if edit.cells is not None else value))
        if pack.custom_apply or any(not isinstance(s, XbrParametricEdit) for s in pack.sites):
            xbe_params[pack.name] = given
    return Overlay(build_xbe(vanilla_xbe, xbe_params) if xbe_params else bytes(vanilla_xbe), tuple(cells), name)


class Write(NamedTuple):
    va: int
    new: bytes          # the build's bytes
    old: bytes          # what vanilla's loader put there (zeros past a section's raw data)
    section: str
    writable: bool


def code_writes(vanilla_xbe: bytes, build_xbe: bytes, keep_out=()) -> tuple[list[Write], list[tuple]]:
    """(the runs of bytes the build changes in vanilla's sections, the sections it appends as ``(va, size,
    bytes, name)``).  A section moved or dropped, or a change inside ``keep_out`` (``(va, n)`` ranges: code L3
    hooks by address), is refused by name."""
    vsec = {s["name"]: s for s in parse_xbe_sections(vanilla_xbe)[1]}
    out, new = [], []
    for s in parse_xbe_sections(build_xbe)[1]:
        data = build_xbe[s["raw_addr"]:s["raw_addr"] + min(s["raw_size"], s["vsize"])]
        v = vsec.pop(s["name"], None)
        if v is None:
            new.append((s["vaddr"], max(s["vsize"], len(data)), data, s["name"]))
            continue
        if v["vaddr"] != s["vaddr"] or s["vsize"] < v["vsize"]:
            raise ValueError(f"the build moved or shrank {s['name']}: an L3 overlay writes sections in place")
        old = vanilla_xbe[v["raw_addr"]:v["raw_addr"] + min(v["raw_size"], v["vsize"])]
        old = old + bytes(max(len(data) - len(old), 0))
        i = 0
        while i < len(data):
            if data[i] == old[i]:
                i += 1
                continue
            j = i
            while j < len(data) and data[j] != old[j]:
                j += 1
            out.append(Write(s["vaddr"] + i, data[i:j], old[i:j], s["name"], bool(s["flags"] & 1)))
            i = j
    if vsec:
        raise ValueError(f"the build drops {', '.join(sorted(vsec))}: an L3 overlay writes sections in place")
    for w in out:
        for va, n in keep_out:
            if w.va < va + n and va < w.va + len(w.new):
                raise ValueError(f"the build changes {w.section} at {va:#x}, where L3 hooks the game's code")
    return out, new


def copies(u32: Callable[[int], int], read: Callable[[int, int], bytes], entity: int, vanilla_xbe: bytes,
           build_xbe: bytes) -> list[tuple]:
    """The writes that put the build's value of each :data:`COPIES` constant where the game copied it, where the
    snapshot holds vanilla's value there (a snapshot of another build, or a copy made later, is left alone)."""
    out = []
    for va, (where, _why) in COPIES.items():
        old, new = (_at(x, va, 4) for x in (vanilla_xbe, build_xbe))
        if old is None or new is None or old == new:
            continue
        dst = where(u32, entity)
        if read(dst, 4) == old:
            out.append((dst, new))
    return out


def _at(xbe: bytes, va: int, n: int) -> bytes | None:
    """``n`` bytes at ``va`` in the XBE file (None: not in a section's raw data)."""
    for s in parse_xbe_sections(xbe)[1]:
        if s["vaddr"] <= va and va + n <= s["vaddr"] + min(s["raw_size"], s["vsize"]):
            return xbe[s["raw_addr"] + va - s["vaddr"]:s["raw_addr"] + va - s["vaddr"] + n]
    return None


def pokes(u32: Callable[[int], int], read: Callable[[int, int], bytes], entity: int, cells) -> list[tuple]:
    """The writes that put ``cells`` where the game holds them after its load (:data:`CELLS`), read through the
    running game's ``u32``/``read`` from the player ``entity``."""
    out = []
    for table, ent, prop, value in cells:
        if (table, ent, prop) not in CELLS:
            raise ValueError(f"config.xbr {table}/{ent}/{prop} is not a cell an L3 overlay pokes")
        if not math.isfinite(value):
            raise ValueError(f"{table}/{ent}/{prop}: {value!r} isn't finite")
        if prop == "runSpeed":
            out.append((u32(u32(entity + 0x20) + CR_SPECIES) + SPECIES_RUN_SPEED, struct.pack("<f", value)))
            continue
        begin, end = u32(ARMOR_SLOTS), u32(ARMOR_SLOTS + 4)
        slot = next((a for a in range(begin, end, SLOT_SIZE)
                     if read(u32(a), 32).split(b"\0")[0] == ent.encode()), None)
        if slot is None:
            raise ValueError(f"the armor slot vector has no row {ent!r}")
        n = math.trunc(value)
        if not -2**31 <= n < 2**31:
            raise ValueError(f"{ent}/Flaps: {value!r} doesn't fit the game's int32")
        out.append((slot + SLOT_FLAPS, struct.pack("<i", n)))
    return out


__all__ = ["CELLS", "COPIES", "Overlay", "Write", "build", "code_writes", "copies", "pokes"]

"""A build's layers and how they stack (D28).

A tool plans each layer against the vanilla files: its :class:`Change` s,
each bytes a file gets at an offset, in a **group** that must land whole (one
per site or cell, or per operation of an ``xbr`` recipe). :func:`compose`
lays the layers over the vanilla files in their canonical order, each
layer's groups in its order. Where a later group (of a later layer, or later
in the same one) gives a byte an earlier group wrote another value, the later
wins and the build goes on (D28): the earlier group is dropped whole, each
of its other bytes back to vanilla unless another group wrote the same value
there, so a site never lands half, and a :class:`Conflict` names both layers
and both groups (a config.xbr cell's group names the cell, AZ-130). A later
group that writes the value a byte already holds overwrites nothing.

A change can also be a whole file (``whole``, §12.2's ``file.put``): the
file a layer wrote, at any size, planned against the whole vanilla file
(``before`` its sha256). The character layer writes ``characters.xbr``,
``fx.xbr`` and ``index.xbr`` so, one group of them (a swap grows each:
``core.xbr.append``). It shadows every earlier group in its file: a group
whose bytes it doesn't hold is dropped whole, and listed as a conflict. A
later range in the file is planned against its vanilla bytes as any change,
and lands over the whole file's only where they still hold those bytes (or
its own); where the whole file changed them (a grown body moves every later
resource), the range would land in another resource and is refused (D35),
as Modkit refuses an edit whose file holds neither its expected bytes nor
its new ones (AZ-096). Only one group may write a file whole.

The layers' canonical order is Modkit's ``mod_apply`` order (a file's bytes
then match Modkit's, file for file): the generator (the randomizer), the
packs, the character layer, then the ``xbr`` operations (the Data tool).

A layer's :class:`Claim` s are the room the carve allocator gave it in a
file (``core.xbe.Carver``: a shim's bytes, which its changes then write);
the manifest keeps them, and no two layers' claims meet. The header state
they derive (``.text``'s sizes, an appended section: ``core.xbe.grown``) is
laid down first, never written by a layer, so a layer's changes are planned
against the vanilla file with it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from azurkit.core import xbe

DERIVED = {"default.xbe": xbe.grown}   # a file a layer may claim room in -> its derived header state


@dataclass(frozen=True)
class Change:
    file: str       # its path in the image, e.g. "default.xbe"
    offset: int     # 0 for a whole file
    before: str     # sha256 of the vanilla bytes it replaces (a whole file's: the whole vanilla file's)
    after: bytes = field(repr=False)
    group: str      # the unit it lands with, e.g. "fps_unlock 0x001983E8 (timestep)"
    whole: bool = False   # the file whole, at any size (the module's docstring)


@dataclass(frozen=True)
class Claim:
    file: str
    offset: int
    size: int
    owner: str      # e.g. "shim:qol_skip_logo"
    writable: bool = False


@dataclass(frozen=True)
class Layer:
    id: str         # e.g. "pack fps_unlock"
    tool: str       # e.g. "mods"
    kind: str       # e.g. "packs"
    recipe: Mapping   # what the tool planned it from (JSON)
    changes: tuple[Change, ...]
    claims: tuple[Claim, ...] = ()
    notes: tuple[str, ...] = ()   # what its plan tells the player (a slider past float32's range, Q110)


@dataclass(frozen=True)
class Conflict:
    file: str
    offset: int
    size: int       # the bytes the later layer gave another value
    layer: str
    group: str
    overwrote: str  # the earlier layer
    dropped: str    # its group, dropped whole

    def __str__(self) -> str:
        return (f"{self.file} 0x{self.offset:X} ({self.size} B): {self.layer} ({self.group}) overwrote "
                f"{self.overwrote}, whose group {self.dropped} is dropped whole")


def claimed(base: Mapping[str, bytes], layers: Sequence[Layer]) -> dict[str, bytes]:
    """Each file the layers claim room in, its derived header state laid
    over ``base``; ``ValueError`` names two layers' claims that meet, or a
    claim in a file nothing derives."""
    out = {}
    for file in sorted({c.file for la in layers for c in la.claims}):
        if file not in DERIVED or file not in base:
            raise ValueError(f"a claim in {file}, where nothing is carved")
        claims = sorted((c for la in layers for c in la.claims if c.file == file), key=lambda c: c.offset)
        for a, b in zip(claims, claims[1:]):
            if b.offset < a.offset + a.size:
                raise ValueError(f"{file}: {b.owner}'s claim at 0x{b.offset:X} meets {a.owner}'s at 0x{a.offset:X}")
        out[file] = DERIVED[file](base[file], [(c.offset, c.size, c.writable) for c in claims])
    return out


def compose(base: Mapping[str, bytes], layers: Sequence[Layer]) -> tuple[dict[str, bytearray], list[Conflict]]:
    """Each file a change or claim names, as ``layers`` leave it over
    ``base`` (its vanilla bytes) with the claims' derived state
    (:func:`claimed`), and every conflict. ``ValueError`` names a change
    outside its file or planned against other bytes, a range over a whole
    file that holds neither its vanilla bytes there nor its own, a second
    group writing a file whole, a group of a whole file and ranges, or a
    whole file a claim derives (D35)."""
    base = {**base, **claimed(base, layers)}
    files: dict[str, bytearray] = {file: bytearray(base[file]) for file in {c.file for la in layers for c in la.claims}}
    writers: dict[tuple[str, int], list[tuple[int, str]]] = {}   # a byte -> the range groups holding its value
    members: dict[tuple[int, str], list[Change]] = {}
    whole: dict[str, tuple[int, str]] = {}   # a file written whole -> its group
    put: dict[str, bytes] = {}               # -> its bytes, under every range group's
    conflicts: list[Conflict] = []

    def drop(group: tuple[int, str]) -> None:   # a range group: each byte back to the whole file's, else vanilla
        for c in members.pop(group):
            for at in range(c.offset, c.offset + len(c.after)):
                held = writers[c.file, at]
                held.remove(group)
                if not held:
                    del writers[c.file, at]
                    files[c.file][at] = (put[c.file] if c.file in put else base[c.file])[at]

    for i, layer in enumerate(layers):
        for c in layer.changes:
            what = f"{layer.id} ({c.group})"
            if c.file not in base:
                raise ValueError(f"{what}: no file {c.file} in the base")
            if any(m.whole != c.whole for m in members.get((i, c.group), ())):
                raise ValueError(f"{what}: one group writes {c.file} whole and another file in ranges")
            if c.whole:
                if c.offset or hashlib.sha256(base[c.file]).hexdigest() != c.before:
                    raise ValueError(f"{what}: written whole against another {c.file}")
                if c.file in whole or c.file in DERIVED:
                    by = layers[whole[c.file][0]].id if c.file in whole else "the claims' derived state"
                    raise ValueError(f"{what}: {c.file} is written whole by {by} already")
                for group in [g for g, cs in members.items() if any(m.file == c.file for m in cs)]:
                    ats = [at for m in members[group] if m.file == c.file
                           for at, value in enumerate(m.after, m.offset) if at >= len(c.after) or c.after[at] != value]
                    if ats:
                        drop(group)
                        conflicts.append(Conflict(c.file, ats[0], len(ats), layer.id, c.group, layers[group[0]].id,
                                                  group[1]))
                whole[c.file], put[c.file] = (i, c.group), c.after
                files[c.file] = bytearray(c.after)
                members.setdefault((i, c.group), []).append(c)
                continue
            buf = files.setdefault(c.file, bytearray(base[c.file]))
            end = c.offset + len(c.after)
            if c.offset < 0 or end > min(len(buf), len(base[c.file])):
                raise ValueError(f"{what}: 0x{c.offset:X}+{len(c.after)} is outside {c.file}")
            if hashlib.sha256(base[c.file][c.offset:end]).hexdigest() != c.before:
                raise ValueError(f"{what}: planned against other bytes of {c.file} at 0x{c.offset:X}")
            under = whole.get(c.file)
            if under and put[c.file][c.offset:end] not in (base[c.file][c.offset:end], c.after):
                raise ValueError(f"{what}: {layers[under[0]].id} ({under[1]}) wrote {c.file} whole with other bytes "
                                 f"at 0x{c.offset:X}")
            hit: dict[tuple[int, str], list[int]] = {}
            for at, value in enumerate(c.after, c.offset):
                for group in writers.get((c.file, at), ()):
                    if group != (i, c.group) and buf[at] != value:
                        hit.setdefault(group, []).append(at)
            for group, ats in hit.items():
                drop(group)
                conflicts.append(Conflict(c.file, ats[0], len(ats), layer.id, c.group, layers[group[0]].id, group[1]))
            buf[c.offset:end] = c.after
            for at in range(c.offset, end):
                writers.setdefault((c.file, at), []).append((i, c.group))
            members.setdefault((i, c.group), []).append(c)
    return files, conflicts

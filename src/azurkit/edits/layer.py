"""A build's layers and how they stack (D28).

A tool plans each layer against the vanilla files: its :class:`Change` s,
each bytes a file gets at an offset, in a **group** that must land whole (one
per site). :func:`compose` lays the layers over the vanilla files in their
canonical order. Where a later layer gives a byte an earlier group wrote
another value, the later layer wins and the build goes on (D28): the earlier
group is dropped whole, each of its other bytes back to vanilla unless another
group wrote the same value there, so a site never lands half, and a
:class:`Conflict` names both layers and the dropped group. A later layer that
writes the value a byte already holds overwrites nothing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Change:
    file: str       # its path in the image, e.g. "default.xbe"
    offset: int
    before: str     # sha256 of the vanilla bytes it replaces
    after: bytes = field(repr=False)
    group: str      # the unit it lands with, e.g. "fps_unlock 0x001983E8 (timestep)"


@dataclass(frozen=True)
class Layer:
    id: str         # e.g. "pack fps_unlock"
    tool: str       # e.g. "mods"
    kind: str       # e.g. "packs"
    recipe: Mapping   # what the tool planned it from (JSON)
    changes: tuple[Change, ...]


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


def compose(base: Mapping[str, bytes], layers: Sequence[Layer]) -> tuple[dict[str, bytearray], list[Conflict]]:
    """Each file a change names, as ``layers`` leave it over ``base`` (its
    vanilla bytes), and every conflict. ``ValueError`` names a change
    outside its file or planned against other bytes (D35)."""
    files: dict[str, bytearray] = {}
    writers: dict[tuple[str, int], list[tuple[int, str]]] = {}   # a byte -> the groups holding its value
    members: dict[tuple[int, str], list[Change]] = {}
    conflicts: list[Conflict] = []

    def drop(group: tuple[int, str]) -> None:
        for c in members.pop(group):
            for at in range(c.offset, c.offset + len(c.after)):
                held = writers[c.file, at]
                held.remove(group)
                if not held:
                    del writers[c.file, at]
                    files[c.file][at] = base[c.file][at]

    for i, layer in enumerate(layers):
        for c in layer.changes:
            if c.file not in base:
                raise ValueError(f"{layer.id} ({c.group}): no file {c.file} in the base")
            buf = files.setdefault(c.file, bytearray(base[c.file]))
            end = c.offset + len(c.after)
            if c.offset < 0 or end > len(buf):
                raise ValueError(f"{layer.id} ({c.group}): 0x{c.offset:X}+{len(c.after)} is outside {c.file}")
            if hashlib.sha256(base[c.file][c.offset:end]).hexdigest() != c.before:
                raise ValueError(f"{layer.id} ({c.group}): planned against other bytes of {c.file} at 0x{c.offset:X}")
            hit: dict[tuple[int, str], list[int]] = {}
            for at, value in enumerate(c.after, c.offset):
                for group in writers.get((c.file, at), ()):
                    if group[0] != i and buf[at] != value:
                        hit.setdefault(group, []).append(at)
            for group, ats in hit.items():
                drop(group)
                conflicts.append(Conflict(c.file, ats[0], len(ats), layer.id, c.group, layers[group[0]].id, group[1]))
            buf[c.offset:end] = c.after
            for at in range(c.offset, end):
                writers.setdefault((c.file, at), []).append((i, c.group))
            members.setdefault((i, c.group), []).append(c)
    return files, conflicts

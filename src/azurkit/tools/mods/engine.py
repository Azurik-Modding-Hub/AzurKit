"""The pack engine: a pack's sites, as data, planned into a layer of changes.

A site (:class:`PatchSpec`) is the bytes a pack writes at an address. It is
a USA address (the canonical ones), which another release's address map
moves (``core.facts``), with the absolute addresses at the patch's ``abs32``
offsets and the targets of its rel32 branches at its ``rel32`` offsets moved
along; a site that names releases without USA is that release's own, at its
own address. The facts give each site's size and the sha256 of its vanilla
bytes, which the input must hold there (D27). A pack holds only what it
writes.

A pack's parameters are its sliders (:class:`ParametricPatch`): any finite
number (D23), its track's ends display hints only; a slider at a site writes
its value there, a virtual one hands it to the pack's ``custom_apply``.
:meth:`Pack.values` takes a pack's parameters or names each it refuses.

A slider over config.xbr (:class:`XbrParametricEdit`) writes keyed cells
there (``core.xbr``): its value into one number cell, or as a multiplier of
the cells its pack picks from the vanilla tables.

A trampoline (:class:`TrampolinePatch`) hooks a site with a CALL or JMP
rel32 into a C shim: the pack's prebuilt object (``shims/<name>.o``, which
``shimkit`` builds from ``<name>.c`` beside it, so no host needs a compiler,
AZ-045), laid out by ``core.coff`` where the carve allocator
(``core.xbe.Carver``) gives it room, past every claim of the layers before
it; its placements are the layer's claims (one group with the hook). Each
hook lands its own copy of the object. A shim's calls of the game's
functions go to their addresses in the facts, a kernel function's to a
6-byte stub that jumps through the game's thunk slot for it (one a pack),
or, for one the game doesn't import, to a stub that asks the shared
kernel-export resolver for it once (:func:`resolving_stub`), and a kernel
variable is read through its slot; its parameters
(:class:`FloatParam`, :class:`BytesParam`) are written into its landed
``.rdata``.

A pack writes its sites in order, or its ``custom_apply(xbe, **values)``
writes through the :class:`Xbe` it is given, only inside the ``footprint``
it declares (AZ-097): a facts site, or a span the footprint gives with its
size (``Place.size``), which the facts may cover only in part (theirs are
the bytes Modkit's cases changed). It may also carve bytes of its own
(:meth:`Xbe.carve`: a float a rewritten instruction reads, a hand-written
shim) and hook a site to them (:class:`Hook`). :func:`plan` makes a pack's layer (one group per
site or cell), planned against the release's vanilla files, or raises
:class:`PackError` naming every site that failed and why: by its label and
address or cell, never its bytes (D35).
"""

from __future__ import annotations

import functools
import hashlib
import importlib.resources
import inspect
import math
import struct
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from azurkit.core import coff
from azurkit.core import facts as facts_
from azurkit.core import xbe as xbe_
from azurkit.core.gate import Release
from azurkit.core.xbr import Document, edits
from azurkit.core.xbr.keyed import Table
from azurkit.edits.layer import Change, Claim, Layer

XBE = "default.xbe"
CONFIG = "gamedata/config.xbr"
INT32 = (-2**31, 2**31 - 1)
#: Each pack's category (:attr:`Pack.category`), with its title and line, in the order a UI shows them: Modkit's
#: (``azurik_mod/patching/category.py``, its GUI's tabs; the player's model is the Characters tab's here).
CATEGORIES = {"player": ("Player", "Player movement, physics and stats."),
              "enemies": ("Enemies", "Enemies' health, damage, speed and size, and the damage they take."),
              "qol": ("Quality of Life", "Frame rate, the boot logo, popups and other conveniences.")}


class PackError(ValueError):
    """A pack that can't be planned, with every reason by name (D35)."""


@dataclass(frozen=True, kw_only=True)
class Place:
    """An address a pack may write: a USA one, or (``releases`` without USA)
    those releases' own. ``releases`` empty: every release the pack lists.
    In a footprint, ``size`` makes it a span a ``custom_apply`` may write
    whole, whether or not the facts list a site there."""
    va: int
    releases: tuple[str, ...] = ()
    size: int = 0

    def on(self, release: str) -> bool:
        return not self.releases or release in self.releases

    def own(self, facts: facts_.Facts) -> int:
        """Its address in the release of ``facts``; ``LookupError`` says why there is none."""
        return self.va if self.releases and "usa" not in self.releases else facts.va(self.va)


@dataclass(frozen=True, kw_only=True)
class PatchSpec(Place):
    """``patch`` written at the site :attr:`va`."""
    label: str
    patch: bytes
    abs32: tuple[int, ...] = ()   # offsets in patch of each absolute address it holds
    rel32: tuple[int, ...] = ()   # offsets in patch of each rel32 branch displacement

    def placed(self, facts: facts_.Facts, va: int) -> bytes:
        """The patch at ``va``, its address in the release of ``facts``."""
        if self.releases and "usa" not in self.releases:
            return self.patch
        return moved(facts, self.patch, self.va, va, self.abs32, self.rel32)


def moved(facts: facts_.Facts, data: bytes, usa_at: int, at: int, abs32=(), rel32=()) -> bytes:
    """``data``, written for USA at ``usa_at``, at ``at`` in the release of
    ``facts``: the USA address at each ``abs32`` offset, and the target of
    the rel32 branch at each ``rel32`` offset, moved to the release's."""
    if facts.addresses is None:
        return data
    out = bytearray(data)
    for k in abs32:
        struct.pack_into("<I", out, k, facts.va(struct.unpack_from("<I", out, k)[0]))
    for k in rel32:
        target = (usa_at + k + 4 + struct.unpack_from("<i", out, k)[0]) & 0xFFFFFFFF
        struct.pack_into("<i", out, k, facts.va(target) - (at + k + 4))
    return bytes(out)


@dataclass(frozen=True)
class FloatParam:
    """A shim's float the build writes from the value named :attr:`name`
    (a slider's): its symbol :attr:`symbol` (``AZURIK_FLOAT_PARAM``)."""
    name: str
    symbol: str


@dataclass(frozen=True)
class BytesParam:
    """A shim's table of :attr:`size` bytes the build writes from the bytes
    named :attr:`name`, zero-filled (``AZURIK_BYTES_PARAM``); none: zeros."""
    name: str
    symbol: str
    size: int


@dataclass(frozen=True, kw_only=True)
class TrampolinePatch(Place):
    """A CALL (``mode`` ``call``) or JMP rel32 at the site :attr:`va` to the
    symbol :attr:`symbol` of the prebuilt shim :attr:`shim`, the rest of the
    site's bytes no-ops; its parameters written into its landing."""
    label: str
    shim: str      # its object: shims/<shim>.o
    symbol: str    # its entry, as C mangles it ("_c_skip_logo")
    mode: Literal["call", "jmp"] = "call"
    floats: tuple[FloatParam, ...] = ()
    tables: tuple[BytesParam, ...] = ()


@dataclass(frozen=True, kw_only=True)
class Hook(Place):
    """A CALL or JMP rel32 at the site :attr:`va` to :attr:`target`, an
    address the pack carved in this build (:meth:`Xbe.carve`), the rest of
    the site's bytes no-ops."""
    label: str
    target: int
    mode: Literal["call", "jmp"] = "call"


def jump(mode: str, va: int, target: int, size: int) -> bytes:
    """A CALL (``mode`` ``call``) or JMP rel32 at ``va`` to ``target``, NOPs
    to ``size`` bytes; ``ValueError`` when ``size`` is under 5."""
    if size < 5:
        raise ValueError(f"the site is {size} B, too small for a rel32 {mode}")
    return bytes([0xE8 if mode == "call" else 0xE9]) + struct.pack("<i", target - (va + 5)) + b"\x90" * (size - 5)


RESOLVER = ("xboxkrnl_resolver", "_xboxkrnl_resolve_by_ordinal")   # the shared kernel-export resolver's shim, entry
RESOLVING_STUB = 0x25   # bytes: 0x21 of code, then the 4-byte cache it keeps the export's address in


def resolving_stub(at: int, ordinal: int, resolver: int) -> bytes:
    """The :data:`RESOLVING_STUB` bytes at ``at`` that call the kernel
    export ``ordinal``, which the game doesn't import (Modkit's D1-extend):
    while its cache (its last 4 bytes) is 0 it asks the resolver at
    ``resolver`` (cdecl) for the export's address, ECX and EDX kept for a
    fastcall's arguments (AZ-041), and keeps it there; it then jumps to it.
    It writes its cache, so it lands writable (AZ-281)."""
    cache = struct.pack("<I", at + 0x21)
    return (b"\xA1" + cache + b"\x85\xC0\x75\x16"   # mov eax, [cache]; test eax, eax; jnz +0x16 (the jmp)
            + b"\x51\x52\x68" + struct.pack("<I", ordinal)   # push ecx; push edx; push ordinal
            + b"\xE8" + struct.pack("<i", resolver - (at + 0x15))   # call the resolver
            + b"\x83\xC4\x04\x5A\x59\xA3" + cache   # add esp, 4; pop edx; pop ecx; mov [cache], eax
            + b"\xFF\xE0" + bytes(4))   # jmp eax; the cache


@functools.cache
def shim(name: str) -> coff.Coff:
    """The prebuilt shim object ``shims/<name>.o``, parsed."""
    return coff.parse(importlib.resources.files(__package__).joinpath("shims", f"{name}.o").read_bytes())


def f32(value: float) -> bytes:
    """``value`` as a little-endian float32; past its range, the infinity a
    C ``(float)`` cast gives (D23, Q110: saturated, never refused; a plan
    notes it, :meth:`Xbe.f32`)."""
    try:
        return struct.pack("<f", value)
    except OverflowError:
        return struct.pack("<f", math.copysign(math.inf, value))


def saturated(value: float, data: bytes) -> str | None:
    """Q110's note when the finite ``value`` became an infinity as ``data``, its float32."""
    if math.isfinite(value) and math.isinf(from_f32(data)):
        return f"{value:g} is past float32's range: written as {from_f32(data):g} (Q110)"
    return None


def from_f32(data: bytes) -> float:
    return struct.unpack("<f", data)[0]


@dataclass(frozen=True, kw_only=True)
class Slider:
    """A pack's parameter :attr:`name`: any finite number (D23).
    ``slider_min`` and ``slider_max`` are its track's ends, display hints
    that never clamp, and the track holds :attr:`default` and the vanilla
    value (D42). :attr:`whole` takes only whole numbers in that range, its
    encoding's limit (D45, named by :attr:`why`), never a cap."""
    name: str
    label: str
    default: float
    slider_min: float
    slider_max: float
    slider_step: float
    unit: str = ""
    description: str = ""
    vanilla: float | None = None
    whole: tuple[int, int] | None = None
    why: str = ""
    logic_floor: str | None = None   # "min" or "max": the side of default where the randomizer's logic no longer
                                     # holds and a build's logic_verified is false (D83(c)); never a limit

    def value(self, given: object) -> float | int:
        """``given`` as this slider takes it; ``ValueError`` (naming the
        slider) for anything but a finite number, or, for a :attr:`whole`
        one, a whole number its encoding holds. Never clamped."""
        value = edits.finite(given, self.name)
        if self.whole is None:
            return value
        low, high = self.whole
        if given != int(given) or not low <= given <= high:
            raise ValueError(f"{self.name}: {given:g} is not a whole number from {low} to {high} ({self.why})")
        return int(given)

    def catalog(self) -> dict:
        return {"name": self.name, "label": self.label, "default": self.default, "min": self.slider_min,
                "max": self.slider_max, "step": self.slider_step, "unit": self.unit,
                "description": self.description, "vanilla": self.vanilla,
                "whole": list(self.whole) if self.whole else None, "logic_floor": self.logic_floor}


@dataclass(frozen=True, kw_only=True)
class ParametricPatch(Place, Slider):
    """A slider in default.xbe. One at a site (:attr:`va` not 0) writes
    ``encode(value)`` there, the facts' site's size, and its vanilla value
    is the image's own (``decode``, read there: Q174, ``sdk.vanilla``); a
    virtual one (:attr:`va` 0) hands its value to the pack's
    ``custom_apply``, or to a shim's :class:`FloatParam` of its name, and
    names :attr:`vanilla`."""
    va: int = 0
    encode: Callable[[float], bytes] = f32
    decode: Callable[[bytes], float] = from_f32

    @property
    def virtual(self) -> bool:
        return self.va == 0


_TO_INT32 = {"round": round, "trunc": math.trunc, "ceil": math.ceil}   # an x87 FISTP rounds half to even;
                                                                          # 0xF5A40 truncates; a pack rounds up


@dataclass(frozen=True, kw_only=True)
class XbrParametricEdit(Slider):
    """A slider in config.xbr's keyed table :attr:`table` (``core.xbr``).
    Without :attr:`cells` its value goes into the number cell
    :attr:`entity`/:attr:`prop`. With them it is a multiplier k: each cell
    ``cells(tables)`` picks from the vanilla tables, ``(entity, column,
    prop, base)`` in :attr:`table` or ``(entity, column, prop, base,
    table)`` in another, becomes k x base (an empty one filled), and at its
    default it writes nothing; :attr:`entity` and :attr:`prop` then only
    say what the cells are. Where the game reads the cell as an int32
    (:attr:`int32`: it rounds or truncates; a pack may round up), a value it can't hold is
    refused, by the slider or by the cell (D45), and a multiplied cell is
    written as the game keeps it. The vanilla value is the default, which
    writes what vanilla holds (``tests/test_packs.py`` reads it from the
    image)."""
    table: str
    entity: str
    prop: str
    file: str = CONFIG
    int32: Literal["round", "trunc", "ceil"] | None = None
    cells: Callable[[Mapping[str, Table]], Iterable[tuple]] | None = None

    virtual = False   # its pack writes it; a custom_apply is handed its value too

    def _int32(self, value: float, what: str) -> int:
        how = {"round": "rounded", "trunc": "truncated", "ceil": "rounded up"}[self.int32]
        whole = _TO_INT32[self.int32](value) if math.isfinite(value) else None
        if whole is None or not INT32[0] <= whole <= INT32[1]:
            raise ValueError(f"{what}: {value:g} doesn't fit the game's 32-bit integer once {how} "
                             f"({INT32[0]}..{INT32[1]})")
        return whole

    def value(self, given: object) -> float:
        value = super().value(given)
        if self.int32 is not None and self.cells is None:
            self._int32(value, self.name)
        return value

    def catalog(self) -> dict:
        return super().catalog() | {"vanilla": self.default}

    def writes(self, tables: Mapping[str, Table], value: float) -> list[tuple[str, int, bytes]]:
        """Each cell the slider at ``value`` writes, ``(table/entity/prop,
        file offset, bytes)``; ``LookupError`` or ``ValueError`` names a
        cell it can't write and why."""
        if self.table not in tables:
            raise LookupError(f"{self.file} has no keyed table {self.table!r}")
        if self.cells is None:
            picked = [(self.entity, tables[self.table].column(self.entity), self.prop, value, self.table)]
        elif value == self.default:
            return []
        else:
            picked = []
            for entity, col, prop, base, *other in self.cells(tables):
                name = other[0] if other else self.table
                written = value * base
                if self.int32 is not None:
                    written = float(self._int32(written, f"{name} {entity}/{prop}"))
                picked.append((entity, col, prop, written, name))
        return [(f"{name}/{entity}/{prop}" + (f" (column {col})" if tables[name].cols.count(entity) > 1 else ""),
                 at, data) for entity, col, prop, written, name in picked
                for at, data in edits.set_number(tables[name], entity, prop, written, col=col,
                                                 fill=self.cells is not None)]


@dataclass(frozen=True)
class Pack:
    name: str
    description: str
    sites: tuple[PatchSpec | ParametricPatch | TrampolinePatch | XbrParametricEdit, ...] = ()
    custom_apply: Callable[..., None] | None = None   # (xbe: Xbe, **values); it writes only by Xbe.patch
    footprint: tuple[Place, ...] = ()                   # every place custom_apply may write
    default_on: bool = False                            # every build applies it unless told not to (D528)
    category: str = "qol"
    releases: tuple[str, ...] = ("usa", "europe")
    requires: tuple[str, ...] = ()                      # the packs a build must apply with it (mods.missing)
    requires_why: str = ""                              # why, finishing "<pack> ...": a moved box's line (mods.settle)
    inputs: tuple[str, ...] = ()                        # what a build, never a recipe, hands custom_apply (plan)

    def __post_init__(self) -> None:
        """A ``custom_apply`` takes the pack's sliders (it writes their XBE
        sites itself; a config.xbr one's cells are the engine's, its value
        handed over too), then its :attr:`inputs`. Without one, a virtual
        slider is a shim's :class:`FloatParam` of its name. Its category is
        one of :data:`CATEGORIES`."""
        if self.category not in CATEGORIES:
            raise TypeError(f"pack {self.name!r}: no category {self.category!r} (the categories: "
                            f"{', '.join(CATEGORIES)})")
        if self.custom_apply is not None:
            takes = list(inspect.signature(self.custom_apply).parameters)[1:]
            if takes != [s.name for s in self.sliders()] + list(self.inputs):
                raise TypeError(f"pack {self.name!r}: custom_apply takes {takes}, not its sliders and inputs")
            return
        floats = {f.name for s in self.sites if isinstance(s, TrampolinePatch) for f in s.floats}
        if loose := [s.name for s in self.sliders() if s.virtual and s.name not in floats]:
            raise TypeError(f"pack {self.name!r}: no custom_apply or shim takes its virtual sliders {loose}")

    def sliders(self) -> tuple[ParametricPatch | XbrParametricEdit, ...]:
        return tuple(s for s in self.sites if isinstance(s, Slider))

    def files(self) -> tuple[str, ...]:
        """The image's files the pack writes (and reads to plan)."""
        xbe = self.custom_apply is not None or any(not isinstance(s, XbrParametricEdit) for s in self.sites)
        return tuple(dict.fromkeys([XBE] * xbe + [s.file for s in self.sites if isinstance(s, XbrParametricEdit)]))

    def values(self, params: Mapping[str, object]) -> dict[str, float | int]:
        """Every slider's value: ``params``' (:meth:`ParametricPatch.value`),
        else its default; :class:`PackError` names each parameter it doesn't
        take and each value refused."""
        sliders = {s.name: s for s in self.sliders()}
        failures = [f"no parameter {name!r}" for name in params if name not in sliders]
        values = {}
        for name, slider in sliders.items():
            try:
                values[name] = slider.value(params.get(name, slider.default))
            except ValueError as exc:
                failures.append(str(exc))
        if failures:
            raise PackError(f"pack {self.name!r}: {'; '.join(failures)} "
                            f"(its parameters: {', '.join(sliders) or 'none'})")
        return values


def digest(data: bytes) -> str:
    """``data`` as messages name it: its size and sha256, never its bytes."""
    return f"<{len(data)} B, sha256 {hashlib.sha256(data).hexdigest()[:12]}>"


class Xbe:
    """A release's vanilla ``default.xbe`` as a pack plans against it: what
    it reads there, and the sites it writes."""

    def __init__(self, facts: facts_.Facts, vanilla: bytes, pack: Pack, occupied: Sequence[Claim] = ()):
        self.release = facts.release.name
        self._facts, self._vanilla, self._pack = facts, vanilla, pack
        self._occupied = [(c.offset, c.size) for c in occupied if c.file == XBE]
        self._carver: xbe_.Carver | None = None
        self._stubs: dict[str, int] = {}   # a kernel import's mangled name -> its stub, one a pack (the resolver's too)
        self._kernel = {k.mangled: k for k in facts.kernel.values()}
        self.changes: list[Change] = []
        self.claims: list[Claim] = []
        self.failures: list[str] = []
        self.notes: list[str] = []
        self.landed: dict[str, dict[str, int]] = {}   # a trampoline's label -> its shim's symbols' addresses
        self.tables: Mapping[str, Table] = {}           # config.xbr's vanilla keyed tables, for a pack that reads it
        self._written: set[int] = set()
        self._allowed: set[int] | None = None
        self._spans: dict[int, int] = {}
        if pack.custom_apply is not None:
            self._allowed = set()
            for place in pack.footprint:
                if place.on(self.release):
                    try:
                        self._allowed.add(own := place.own(facts))
                    except LookupError as exc:
                        self.failures.append(f"its footprint at 0x{place.va:08X}: {exc}")
                        continue
                    if place.size:
                        self._spans[own] = place.size

    def va(self, usa_va: int) -> int:
        """``usa_va``'s address in this release (``LookupError`` says why there is none)."""
        return self._facts.va(usa_va)

    def read(self, usa_va: int, size: int, *, own: bool = False) -> bytes:
        """The vanilla bytes at ``usa_va`` in this release (``own``: at this release's own address)."""
        offset = self._facts.offset(usa_va if own else self._facts.va(usa_va), size)
        return self._vanilla[offset:offset + size]

    def moved(self, data: bytes, at: int, abs32=(), rel32=()) -> bytes:
        """``data`` (code written for USA at ``at``, an address in this
        build) with the USA addresses at its ``abs32`` offsets and the
        targets of its ``rel32`` branches moved to this release's."""
        return moved(self._facts, data, at, at, abs32, rel32)

    def f32(self, value: float, what: str) -> bytes:
        """:func:`f32`, noting a value past float32's range (Q110)."""
        data = f32(value)
        if note := saturated(value, data):
            self.notes.append(f"{self._pack.name} {what}: {note}")
        return data

    def _place(self, size: int, align: int, writable: bool) -> tuple[int, int]:
        """Room for ``size`` bytes from the carve allocator, claimed: ``(file offset, address)``."""
        if self._carver is None:
            self._carver = xbe_.Carver(self._vanilla, self._occupied)
        at, held, offset, address = self._carver.place(size, align, writable)
        self.claims.append(Claim(XBE, at, held, f"shim:{self._pack.name}", writable))
        return offset, address

    def carve(self, data: bytes | Callable[[int], bytes], label: str, *, size: int = 0,
              writable: bool = False) -> int:
        """Land ``data`` (or ``data(address)``, ``size`` bytes) where the
        carve allocator gives room, writable if asked; its address."""
        size = len(data) if isinstance(data, bytes) else size
        offset, address = self._place(size, 1, writable)
        body = data if isinstance(data, bytes) else data(address)
        if len(body) != size:
            raise ValueError(f"{label}: {len(body)} B, not the {size} B carved")
        self.changes.append(Change(XBE, offset, hashlib.sha256(bytes(size)).hexdigest(), body,
                                   f"{self._pack.name} {label}"))
        return address

    def write(self, usa_va: int, label: str, data: bytes) -> None:
        """Write ``data`` at ``usa_va``'s site or span as it is (an address in
        it is this build's own): :meth:`patch` of a :class:`PatchSpec`."""
        self.patch(PatchSpec(label=label, va=usa_va, patch=data))

    def _extern(self, landed: list[Change]) -> coff.Extern:
        """A shim's kernel imports: a variable's slot, or a function's stub,
        one a pack, its changes added to ``landed``: ``jmp [slot]``, or for
        a function the game doesn't import (no slot) a :func:`resolving_stub`,
        with the shared resolver landed once a pack. A variable with no slot
        is refused by name: only a function can be resolved at run time."""
        def resolve(name: str) -> int | None:
            if (k := self._kernel.get(name)) is None:
                return None
            if name not in self._stubs:
                if k.convention == "data":
                    if k.slot is None:
                        raise LookupError(f"the shim's kernel variable {k.name!r} has no slot in the "
                                          f"{self._facts.release.label} XBE's thunk table (only a function is "
                                          f"resolved at run time)")
                    return k.slot
                if k.slot is None:
                    if RESOLVER[1] not in self._stubs:
                        placed, entry = coff.layout(shim(RESOLVER[0]), RESOLVER[1], self._place, {})
                        landed.extend(Change(XBE, p.offset, hashlib.sha256(bytes(len(p.data))).hexdigest(), p.data,
                                             "") for p in placed)
                        self._stubs[RESOLVER[1]] = entry
                    offset, address = self._place(RESOLVING_STUB, 1, True)
                    data = resolving_stub(address, k.ordinal, self._stubs[RESOLVER[1]])
                else:
                    offset, address = self._place(6, 1, False)
                    data = b"\xFF\x25" + struct.pack("<I", k.slot)
                landed.append(Change(XBE, offset, hashlib.sha256(bytes(len(data))).hexdigest(), data, ""))
                self._stubs[name] = address
            return self._stubs[name]
        return resolve

    def _shim(self, spec: TrampolinePatch, va: int, size: int, group: str,
              params: Mapping[str, object]) -> tuple[bytes, list[Change]]:
        """The hook at ``va`` (``size`` bytes) and the changes that land
        its shim, its parameters written, each placement claimed;
        ``LookupError`` or ``ValueError`` says why it can't land, its
        claims and stubs given back."""
        if size < 5:
            raise ValueError(f"the facts' site is {size} B, too small for a rel32 {spec.mode}")
        if self._carver is None:
            self._carver = xbe_.Carver(self._vanilla, self._occupied)
        taken, claimed, stubs, notes = len(self._carver.taken), len(self.claims), dict(self._stubs), len(self.notes)
        obj, landed = shim(spec.shim), []
        try:
            placed, entry = coff.layout(obj, spec.symbol, self._place, self._facts.mangled(), self._extern(landed))
            text = next((s for s in obj.sections if s.name == ".text"), None)   # its code reads a slot by a relocation
            if (spec.tables or spec.floats) and not (text and text.relocations):   # AZ-172
                raise ValueError("it declares parameters, but the shim's .text has no relocations, so it reads "
                                 "none of them")
            data = {p.index: bytearray(p.data) for p in placed}
            for param in (*spec.tables, *spec.floats):
                symbol = obj.symbol(param.symbol)
                if symbol.section - 1 not in data:
                    raise ValueError(f"its parameter {param.name!r} ({param.symbol}) is in no section it lands")
                if isinstance(param, FloatParam):
                    if param.name not in params:
                        raise ValueError(f"no value for its parameter {param.name!r}")
                    value = self.f32(params[param.name], param.name)
                else:
                    value = params.get(param.name, b"")
                    if not isinstance(value, bytes) or len(value) > param.size:
                        raise ValueError(f"its parameter {param.name!r} takes bytes, at most {param.size}")
                    value = value.ljust(param.size, b"\0")
                if symbol.value + len(value) > len(data[symbol.section - 1]):
                    raise ValueError(f"its parameter {param.name!r} runs past its landed section")
                data[symbol.section - 1][symbol.value:symbol.value + len(value)] = value
            hook = jump(spec.mode, va, entry, size)
        except (LookupError, ValueError, struct.error) as exc:
            del self._carver.taken[taken:], self.claims[claimed:], self.notes[notes:]
            self._stubs = stubs
            raise ValueError(f"its shim {spec.shim!r}: {exc}") from None
        at = {p.index: p.va for p in placed}
        self.landed[spec.label] = {s.name: at[s.section - 1] + s.value for s in obj.symbols
                                   if s.storage == coff.EXTERNAL and s.section - 1 in at}
        return hook, [Change(XBE, p.offset, hashlib.sha256(bytes(len(p.data))).hexdigest(), bytes(data[p.index]),
                             group) for p in placed] + [c.__class__(c.file, c.offset, c.before, c.after, group)
                                                        for c in landed]

    def _site(self, va: int) -> tuple[int, list[facts_.Site]]:
        """The size of what a pack writes at this release's ``va`` and the
        facts' sites that hold it: a footprint's span, with every facts
        site wholly inside it, or the facts' site there."""
        if (size := self._spans.get(va)) is not None:
            return size, [s for s in self._facts.sites.values() if va <= s.va and s.va + s.size <= va + size]
        site = self._facts.site(va)
        return site.size, [site]

    def patch(self, spec: PatchSpec | ParametricPatch | TrampolinePatch | Hook, value: float | int | None = None,
              params: Mapping[str, object] | None = None) -> None:
        """Write ``spec`` (a slider: ``value`` encoded; a trampoline: its
        shim, with ``params``, the values its parameters take; nothing when
        it isn't one of this release's), or record why it can't be written."""
        if not spec.on(self.release):
            return
        where = f"{spec.label} at 0x{spec.va:08X}"
        try:
            va = spec.own(self._facts)
            where += f" ({self._facts.release.label} 0x{va:08X})" if va != spec.va else ""
            size, sites = self._site(va)
            offset = self._facts.offset(va, size)
            if isinstance(spec, ParametricPatch):
                data = spec.encode(value)
                if spec.encode is f32 and (note := saturated(value, data)):
                    self.notes.append(f"{self._pack.name} {spec.name}: {note}")
            elif isinstance(spec, Hook):
                data = jump(spec.mode, va, spec.target, size)
            else:
                data = b"" if isinstance(spec, TrampolinePatch) else spec.placed(self._facts, va)
        except (LookupError, ValueError, struct.error) as exc:
            self.failures.append(f"{where}: {exc}")
            return
        group = f"{self._pack.name} 0x{va:08X} ({spec.label})"
        held = next((s for s in sites if hashlib.sha256(self._vanilla[(o := self._facts.offset(s.va, s.size)):
                                                                      o + s.size]).hexdigest() != s.sha256), None)
        if self._allowed is not None and va not in self._allowed:
            why = "it is outside the pack's declared footprint"
        elif va in self._written:
            why = "the pack writes it twice"
        elif not isinstance(spec, TrampolinePatch) and len(data) != size:
            why = f"the patch is {len(data)} B, the {'span' if va in self._spans else "facts' site"} {size} B"
        elif held is not None:
            at = self._facts.offset(held.va, held.size)
            there = "there" if held.va == va else f"at 0x{held.va:08X}"
            why = (f"default.xbe holds {digest(self._vanilla[at:at + held.size])} {there}, "
                   f"not the facts' <{held.size} B, sha256 {held.sha256[:12]}>")
        else:
            try:
                data, landed = (self._shim(spec, va, size, group, params or {}) if isinstance(spec, TrampolinePatch)
                                else (data, []))
            except ValueError as exc:
                why = str(exc)
            else:
                self._written.add(va)
                self.changes += [*landed, Change(XBE, offset, hashlib.sha256(self._vanilla[offset:offset + size])
                                                 .hexdigest(), data, group)]
                return
        self.failures.append(f"{where}: {why}")


def plan(pack: Pack, release: Release, base: Mapping[str, bytes], params: Mapping[str, object] | None = None,
         occupied: Sequence[Claim] = (), inputs: Mapping[str, float] | None = None) -> Layer:
    """``pack``'s layer on ``release``, planned against its vanilla files
    (``base``: each of :meth:`Pack.files`, by its path in the image) with
    ``params``, its shims placed past every claim in ``occupied`` (the
    layers before it), and ``inputs``, what the build hands its
    ``custom_apply`` beside them (:attr:`Pack.inputs`: a worn body's
    ``size_fold``, one unset ``None``); :class:`PackError` names each
    reason it can't be (D35)."""
    params, inputs = dict(params or {}), dict(inputs or {})
    if loose := sorted(set(inputs) - set(pack.inputs)):
        raise PackError(f"pack {pack.name!r}: no input {', '.join(map(repr, loose))}")
    if release.name not in pack.releases:
        raise PackError(f"pack {pack.name!r} is not available on the {release.label} release "
                        f"(it supports {', '.join(pack.releases)})")
    values = pack.values(params)
    for name in pack.files():
        data = base[name]
        size, sha256 = (facts_.of(release).size, facts_.of(release).sha256) if name == XBE else release.files[name]
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
            raise PackError(f"pack {pack.name!r}: {name} {digest(data)} is not the vanilla {release.label} one")
    changes, failures, claims, notes = [], [], [], []
    documents: dict[str, Document] = {}
    if XBE in pack.files():
        xbe = Xbe(facts_.of(release), base[XBE], pack, occupied)
        if CONFIG in pack.files():
            try:
                xbe.tables = (documents := {CONFIG: Document(base[CONFIG])})[CONFIG].tables
            except ValueError as exc:
                raise PackError(f"pack {pack.name!r}: {CONFIG}: {exc}") from None
        if pack.custom_apply is None:
            for spec in pack.sites:
                if isinstance(spec, ParametricPatch) and spec.virtual:
                    continue   # a shim's FloatParam takes it
                if not isinstance(spec, XbrParametricEdit):
                    xbe.patch(spec, values.get(spec.name) if isinstance(spec, ParametricPatch) else None, values)
        else:
            try:
                pack.custom_apply(xbe, **values, **{name: inputs.get(name) for name in pack.inputs})
            except (LookupError, ValueError) as exc:
                raise PackError(f"pack {pack.name!r}: {exc}") from None
        changes, failures, claims, notes = xbe.changes, xbe.failures, xbe.claims, xbe.notes
    for spec in pack.sites:
        if isinstance(spec, XbrParametricEdit):
            data = base[spec.file]
            try:
                if spec.file not in documents:
                    documents[spec.file] = Document(data)
                for what, at, after in spec.writes(documents[spec.file].tables, values[spec.name]):
                    before = hashlib.sha256(data[at:at + len(after)]).hexdigest()
                    changes.append(Change(spec.file, at, before, after, f"{pack.name} {what}"))
            except (LookupError, ValueError) as exc:
                failures.append(f"{spec.label}: {exc}")
    if failures:
        raise PackError(f"pack {pack.name!r}: {len(failures)} site(s) failed: " + "; ".join(failures))
    return Layer(f"pack {pack.name}", "mods", "packs", {"pack": pack.name, "params": params}, tuple(changes),
                 tuple(claims), tuple(dict.fromkeys(notes)))

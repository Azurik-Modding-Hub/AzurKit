"""The pack engine: a pack's sites, as data, planned into a layer of changes.

A site (:class:`PatchSpec`) is the bytes a pack writes at an address. It is
a USA address (the canonical ones), which another release's address map
moves (``core.facts``), with the absolute addresses at the patch's ``abs32``
offsets and the targets of its rel32 branches at its ``rel32`` offsets moved
along; a site that names releases without USA is that release's own, at its
own address. The facts give each site's size and the sha256 of its vanilla
bytes, which the input must hold there (D27). A pack holds only what it
writes, never vanilla bytes (D3).

A pack's parameters are its sliders (:class:`ParametricPatch`): any finite
number (D23), its track's ends display hints only; a slider at a site writes
its value there, a virtual one hands it to the pack's ``custom_apply``.
:meth:`Pack.values` takes a pack's parameters or names each it refuses.

A slider over config.xbr (:class:`XbrParametricEdit`) writes keyed cells
there (``core.xbr``): its value into one number cell, or as a multiplier of
the cells its pack picks from the vanilla tables.

A pack writes its sites in order, or its ``custom_apply(xbe, **values)``
writes through the :class:`Xbe` it is given, only inside the ``footprint``
it declares (AZ-097). :func:`plan` makes a pack's layer (one group per
site or cell), planned against the release's vanilla files, or raises
:class:`PackError` naming every site that failed and why: by its label and
address or cell, never its bytes (D35).
"""

from __future__ import annotations

import hashlib
import inspect
import math
import struct
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from azurkit.core import facts as facts_
from azurkit.core.gate import Release
from azurkit.core.xbr import Document, edits
from azurkit.core.xbr.keyed import Table
from azurkit.edits.layer import Change, Layer

XBE = "default.xbe"
CONFIG = "gamedata/config.xbr"
INT32 = (-2**31, 2**31 - 1)


class PackError(ValueError):
    """A pack that can't be planned, with every reason by name (D35)."""


@dataclass(frozen=True, kw_only=True)
class Place:
    """An address a pack may write: a USA one, or (``releases`` without USA)
    those releases' own. ``releases`` empty: every release the pack lists."""
    va: int
    releases: tuple[str, ...] = ()

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
        if facts.addresses is None or (self.releases and "usa" not in self.releases):
            return self.patch
        out = bytearray(self.patch)
        for k in self.abs32:
            struct.pack_into("<I", out, k, facts.va(struct.unpack_from("<I", out, k)[0]))
        for k in self.rel32:
            target = (self.va + k + 4 + struct.unpack_from("<i", out, k)[0]) & 0xFFFFFFFF
            struct.pack_into("<i", out, k, facts.va(target) - (va + k + 4))
        return bytes(out)


def f32(value: float) -> bytes:
    """``value`` as a little-endian float32; past its range, the infinity a
    C ``(float)`` cast gives (D23, Q110: saturated, never refused)."""
    try:
        return struct.pack("<f", value)
    except OverflowError:
        return struct.pack("<f", math.copysign(math.inf, value))


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
                "whole": list(self.whole) if self.whole else None}


@dataclass(frozen=True, kw_only=True)
class ParametricPatch(Place, Slider):
    """A slider in default.xbe. One at a site (:attr:`va` not 0) writes
    ``encode(value)`` there, the facts' site's size, and its vanilla value
    is the image's own (``decode``, read there: Q174); a virtual one
    (:attr:`va` 0) hands its value to the pack's ``custom_apply`` and names
    :attr:`vanilla`."""
    va: int = 0
    encode: Callable[[float], bytes] = f32
    decode: Callable[[bytes], float] = from_f32

    @property
    def virtual(self) -> bool:
        return self.va == 0


_TO_INT32 = {"round": round, "trunc": math.trunc}   # an x87 FISTP rounds half to even; 0xF5A40 truncates


@dataclass(frozen=True, kw_only=True)
class XbrParametricEdit(Slider):
    """A slider in config.xbr's keyed table :attr:`table` (``core.xbr``).
    Without :attr:`cells` its value goes into the number cell
    :attr:`entity`/:attr:`prop`. With them it is a multiplier k: each cell
    ``cells(tables)`` picks from the vanilla tables, ``(entity, column,
    prop, base)``, becomes k x base (an empty one filled), and at its
    default it writes nothing; :attr:`entity` and :attr:`prop` then only
    say what the cells are. Where the game reads the cell as an int32
    (:attr:`int32`: it rounds or truncates), a value it can't hold is
    refused, by the slider or by the cell (D45), and a multiplied cell is
    written as the game keeps it. The vanilla value is the default, which
    writes what vanilla holds (``tests/test_packs.py`` reads it from the
    image)."""
    table: str
    entity: str
    prop: str
    file: str = CONFIG
    int32: Literal["round", "trunc"] | None = None
    cells: Callable[[Mapping[str, Table]], Iterable[tuple[str, int, str, float]]] | None = None

    virtual = False   # its pack writes it; a custom_apply never takes it

    def _int32(self, value: float, what: str) -> int:
        whole = _TO_INT32[self.int32](value)
        if not INT32[0] <= whole <= INT32[1]:
            raise ValueError(f"{what}: {value:g} doesn't fit the game's 32-bit integer once "
                             f"{'rounded' if self.int32 == 'round' else 'truncated'} ({INT32[0]}..{INT32[1]})")
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
        if (table := tables.get(self.table)) is None:
            raise LookupError(f"{self.file} has no keyed table {self.table!r}")
        if self.cells is None:
            picked = [(self.entity, table.column(self.entity), self.prop, value)]
        elif value == self.default:
            return []
        else:
            picked = []
            for entity, col, prop, base in self.cells(tables):
                written = value * base
                if self.int32 is not None:
                    written = float(self._int32(written, f"{self.table} {entity}/{prop}"))
                picked.append((entity, col, prop, written))
        return [(f"{self.table}/{entity}/{prop}" + (f" (column {col})" if table.cols.count(entity) > 1 else ""),
                 at, data) for entity, col, prop, written in picked
                for at, data in edits.set_number(table, entity, prop, written, col=col, fill=self.cells is not None)]


@dataclass(frozen=True)
class Pack:
    name: str
    description: str
    sites: tuple[PatchSpec | ParametricPatch | XbrParametricEdit, ...] = ()
    custom_apply: Callable[..., None] | None = None   # (xbe: Xbe, **values); it writes only by Xbe.patch
    footprint: tuple[Place, ...] = ()                   # every place custom_apply may write
    default_on: bool = False                            # every build applies it unless told not to (D528)
    category: str = "qol"
    releases: tuple[str, ...] = ("usa", "europe")

    def __post_init__(self) -> None:
        """A ``custom_apply`` takes the pack's sliders, every one virtual (it writes their sites itself)."""
        if self.custom_apply is not None:
            takes = list(inspect.signature(self.custom_apply).parameters)[1:]
            if takes != [s.name for s in self.sliders()] or not all(s.virtual for s in self.sliders()):
                raise TypeError(f"pack {self.name!r}: custom_apply takes {takes}, not its sliders, all virtual")

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

    def __init__(self, facts: facts_.Facts, vanilla: bytes, pack: Pack):
        self.release = facts.release.name
        self._facts, self._vanilla, self._pack = facts, vanilla, pack
        self.changes: list[Change] = []
        self.failures: list[str] = []
        self._written: set[int] = set()
        self._allowed: set[int] | None = None
        if pack.custom_apply is not None:
            self._allowed = set()
            for place in pack.footprint:
                if place.on(self.release):
                    try:
                        self._allowed.add(place.own(facts))
                    except LookupError as exc:
                        self.failures.append(f"its footprint at 0x{place.va:08X}: {exc}")

    def read(self, usa_va: int, size: int) -> bytes:
        """The vanilla bytes at ``usa_va`` in this release."""
        offset = self._facts.offset(self._facts.va(usa_va), size)
        return self._vanilla[offset:offset + size]

    def patch(self, spec: PatchSpec | ParametricPatch, value: float | int | None = None) -> None:
        """Write ``spec`` (a slider: ``value`` encoded; nothing when it isn't
        one of this release's), or record why it can't be written."""
        if not spec.on(self.release):
            return
        where = f"{spec.label} at 0x{spec.va:08X}"
        try:
            va = spec.own(self._facts)
            where += f" ({self._facts.release.label} 0x{va:08X})" if va != spec.va else ""
            site = self._facts.site(va)
            data = spec.encode(value) if isinstance(spec, ParametricPatch) else spec.placed(self._facts, va)
            offset = self._facts.offset(va, site.size)
        except (LookupError, ValueError, struct.error) as exc:
            self.failures.append(f"{where}: {exc}")
            return
        held = self._vanilla[offset:offset + site.size]
        if self._allowed is not None and va not in self._allowed:
            why = "it is outside the pack's declared footprint"
        elif va in self._written:
            why = "the pack writes it twice"
        elif len(data) != site.size:
            why = f"the patch is {len(data)} B, the facts' site {site.size} B"
        elif hashlib.sha256(held).hexdigest() != site.sha256:
            why = f"default.xbe holds {digest(held)} there, not the facts' <{site.size} B, sha256 {site.sha256[:12]}>"
        else:
            self._written.add(va)
            self.changes.append(Change(XBE, offset, site.sha256, data, f"{self._pack.name} 0x{va:08X} ({spec.label})"))
            return
        self.failures.append(f"{where}: {why}")


def plan(pack: Pack, release: Release, base: Mapping[str, bytes], params: Mapping[str, object] | None = None
         ) -> Layer:
    """``pack``'s layer on ``release``, planned against its vanilla files
    (``base``: each of :meth:`Pack.files`, by its path in the image) with
    ``params``; :class:`PackError` names each reason it can't be (D35)."""
    params = dict(params or {})
    if release.name not in pack.releases:
        raise PackError(f"pack {pack.name!r} is not available on the {release.label} release "
                        f"(it supports {', '.join(pack.releases)})")
    values = pack.values(params)
    for name in pack.files():
        data = base[name]
        size, sha256 = (facts_.of(release).size, facts_.of(release).sha256) if name == XBE else release.files[name]
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
            raise PackError(f"pack {pack.name!r}: {name} {digest(data)} is not the vanilla {release.label} one")
    changes, failures = [], []
    if XBE in pack.files():
        xbe = Xbe(facts_.of(release), base[XBE], pack)
        if pack.custom_apply is None:
            for spec in pack.sites:
                if not isinstance(spec, XbrParametricEdit):
                    xbe.patch(spec, values.get(spec.name) if isinstance(spec, ParametricPatch) else None)
        else:
            try:
                pack.custom_apply(xbe, **values)
            except (LookupError, ValueError) as exc:
                raise PackError(f"pack {pack.name!r}: {exc}") from None
        changes, failures = xbe.changes, xbe.failures
    documents: dict[str, Document] = {}
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
    return Layer(f"pack {pack.name}", "mods", "packs", {"pack": pack.name, "params": params}, tuple(changes))

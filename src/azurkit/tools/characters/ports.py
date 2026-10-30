"""What the player-model swap's modules (Modkit's, which the oracle sync
installs: ``scripts/oracle_sync.py``'s ``SOURCES`` and ``FAMILY_REWRITES``)
call of Modkit's engine, on AzurKit's. Ours, never the sync's.

**The build** (:class:`Build`, :func:`building`): a swap runs inside one,
which holds the release's vanilla files (:class:`Vanilla`), its facts and the
claims of the layers before the character layer. Modkit's swap edits its
staged files in place (:class:`IsoStaging`): ``default.xbe`` after the packs,
``characters.xbr``, ``fx.xbr``, ``index.xbr`` and ``config.xbr``.

**default.xbe**: a hook's vanilla bytes are the image's own, which
:func:`xbe_site` reads from the vanilla ``default.xbe`` (checked against the
facts' swap site where the facts hold one), never a literal; a shim is
the prebuilt object beside its source (``player_model/<stem>.o``, shimkit's),
laid out by ``core.coff`` where the carve allocator (``core.xbe.Carver``)
gives room past every claim before it, its header state laid down from the
claims (``core.xbe.grown``), as Modkit's ``carve_shim_landing`` grows
``.text`` and appends ``SHIMS``.

**config.xbr's keyed tables** (:class:`KeyedSection`, the edits below,
:func:`load_all_tables`): a cell is read from the file's live bytes each
time, as Modkit's swap reads a cell after it wrote another.

A refusal is a ``ValueError`` naming what and why, never the bytes (D35);
where Modkit's engine prints a line and returns ``False``, this raises.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import math
import struct
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from azurkit.core import coff, gate, iso
from azurkit.core import facts as facts_
from azurkit.core import xbe as xbe_
from azurkit.core.facts import xbe_layout as _facts_of
from azurkit.core.xbe import resolve_va_to_file
from azurkit.core.xbr.document import Document
from azurkit.core.xbr.keyed import EMPTY, NUMBER, SIZE, STRING
from azurkit.core.xbr.nodes import XbrStructuralError

__all__ = ["BytesParam", "CHECKOUT", "FloatParam", "IsoStaging", "KeyedSection", "PatchConflictError", "PatchSpec",
           "Region", "ShimSource", "TrampolinePatch", "UnmappedAddressError", "Vanilla", "XbrDocument",
           "XbrStructuralError", "XisoReader", "HELD", "apply_trampoline_patch", "restored", "building", "carve_shim_landing",
           "clear_keyed_cell", "finite_slider_value", "get_pack", "link_curve", "link_value", "load_all_tables",
           "pack_f32", "patch_spec_site", "point_at_string", "point_keyed_string", "read_file", "release_session",
           "replace_bytes_at", "resolve_va_to_file", "set_keyed_double", "set_keyed_string",
           "string_sharer_counts", "trampoline_shim_data", "trampoline_symbol_va", "va_to_file",
           "verify_trampoline_patch", "xbe_layout", "xbe_site", "_load_doc_for_edit"]

XBE = "default.xbe"
CHECKOUT = Path(__file__).resolve().parent
"""Where Modkit's build finds its shim objects; ours sit beside their sources (:meth:`ShimSource.object_path`)."""
_CALL, _JMP, _NOP = 0xE8, 0xE9, 0x90


class UnmappedAddressError(ValueError):
    """A USA address has no address in the release asked for."""


class PatchConflictError(ValueError):
    """A hook already installed whose parameters can't be compared (D27)."""


# --------------------------------------------------------------------------- the vanilla files and the build


class Vanilla:
    """A vanilla image's files, read on demand and each checked against its
    release's manifest (D27): ``source`` is the image (a path or an
    ``iso.Image``) or ``{path: bytes}`` of files already read and checked."""

    def __init__(self, release: gate.Release, source):
        self.release = release
        self._source = source
        self._cache: dict[str, bytes] = {}
        if isinstance(source, Mapping):
            self._cache.update(source)
            self.paths = tuple(sorted(source))
        else:
            with iso.Reader(source) as r:
                self.paths = tuple(e.path for e in r.entries() if not e.is_dir)

    def read(self, path: str) -> bytes:
        if path not in self._cache:
            if isinstance(self._source, Mapping):
                raise KeyError(f"{path}: not one of the files read from the image")
            with iso.Reader(self._source) as r:
                data = r.read(path)
            size, sha256 = self.release.files.get(path, (None, None))
            if (len(data), hashlib.sha256(data).hexdigest()) != (size, sha256):
                raise ValueError(f"{path}: not the vanilla {self.release.label} file (D27)")
            self._cache[path] = data
        return self._cache[path]


@dataclass
class Build:
    """One swap's state: the release's vanilla files and facts, the claims
    the layers before it hold in ``default.xbe`` (``(offset, size, writable)``), and
    those its own shims take (``(offset, size, writable)``)."""
    vanilla: Vanilla
    taken: list[tuple[int, int, bool]] = field(default_factory=list)
    claims: list[tuple[int, int, bool]] = field(default_factory=list)
    packs: Mapping[str, object] = field(default_factory=dict)   # get_pack's: what the swap reads of a pack
    carver: xbe_.Carver | None = None

    @property
    def facts(self) -> facts_.Facts:
        return facts_.of(self.vanilla.release)

    def xbe(self) -> bytes:
        return self.vanilla.read(XBE)


_BUILD: contextvars.ContextVar[Build | None] = contextvars.ContextVar("azurkit_characters_build", default=None)


@contextlib.contextmanager
def building(build: Build) -> Iterator[Build]:
    """Run the swap inside ``build`` (its vanilla files, facts and claims)."""
    token = _BUILD.set(build)
    try:
        yield build
    finally:
        _BUILD.reset(token)


def _build() -> Build:
    if (b := _BUILD.get()) is None:
        raise RuntimeError("the swap runs only inside ports.building(...)")
    return b


class IsoStaging:
    """Modkit's staged files: ``{name: bytearray}``, each read on first use,
    from ``current`` (the files the layers before left) or the vanilla
    ``source`` (:class:`Vanilla`), found as Modkit's are (``gamedata/<name>``,
    ``gamedata/index/<name>``, then the root; case-insensitively), one
    buffer a file whatever name reached it. :meth:`stored` is the vanilla
    file; :attr:`root` the vanilla files (:class:`XisoReader` reads them)."""

    def __init__(self, source: Vanilla, current: Mapping[str, bytes] | None = None):
        self.root = source
        self._current = dict(current or {})
        self._paths: dict[str, str] = {}
        self._cache: dict[str, bytearray] = {}
        self._files = {iso.key(p): p for p in source.paths}

    def _resolve(self, filename: str) -> str:
        if filename not in self._paths:
            found = next((self._files[k] for k in (iso.key(f"gamedata/{filename}"),
                                                    iso.key(f"gamedata/index/{filename}"), iso.key(filename))
                          if k in self._files), None)
            if found is None:
                raise KeyError(f"{filename!r} isn't in the image (looked in gamedata/, gamedata/index/ and the root)")
            self._paths[filename] = found
        return self._paths[filename]

    def __contains__(self, filename: object) -> bool:
        try:
            self._resolve(filename)   # type: ignore[arg-type]
        except (KeyError, TypeError):
            return False
        return True

    def __getitem__(self, filename: str) -> bytearray:
        path = self._resolve(filename)
        if path not in self._cache:
            self._cache[path] = bytearray(self._current[path] if path in self._current else self.root.read(path))
        return self._cache[path]

    def __setitem__(self, filename: str, value: bytearray) -> None:
        self._cache[self._resolve(filename)] = value

    def get(self, filename: str, default=None):
        try:
            return self[filename]
        except KeyError:
            return default

    def keys(self) -> Iterator[str]:
        return iter(self)

    def __iter__(self) -> Iterator[str]:
        return iter(Path(p).name for p in self._cache)

    def loaded(self) -> dict[str, bytearray]:
        return dict(self._cache)

    def stored(self, filename: str) -> bytes:
        return self.root.read(self._resolve(filename))

    def changed(self) -> dict[str, bytearray]:
        """Each file whose buffer isn't what the layers before left (or the vanilla file)."""
        return {p: buf for p, buf in self._cache.items()
                if buf != (self._current[p] if p in self._current else self.root.read(p))}

    @contextlib.contextmanager
    def first_reads(self) -> Iterator[dict]:
        yield {}


class _Walked(NamedTuple):
    is_dir: bool


class XisoReader:
    """The vanilla files (:class:`Vanilla`) as Modkit's ``XisoReader`` reads an image."""

    def __init__(self, source: Vanilla):
        self._source = source

    def __enter__(self) -> XisoReader:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read_file(self, path: str) -> bytes:
        return self._source.read(path)

    def walk(self) -> Iterator[tuple[str, _Walked]]:
        for path in self._source.paths:
            yield path, _Walked(False)


def read_file(source: Vanilla, path: str) -> bytes:
    return source.read(path)


# --------------------------------------------------------------------------- what a pack site is to the swap


class ShimSource(NamedTuple):
    """A shim's C source, ``folder/<stem>.c``, and its prebuilt object beside it."""
    folder: Path
    stem: str = "shim"

    def source_path(self) -> Path:
        return Path(self.folder) / f"{self.stem}.c"

    def object_path(self, pack_name: str, repo_root: Path | None = None) -> Path:
        return Path(self.folder) / f"{self.stem}.o"


class PatchSpec(NamedTuple):
    label: str
    va: int
    original: bytes
    patch: bytes
    is_data: bool = False
    safety_critical: bool = False
    abs32: tuple[int, ...] = ()
    rel32: tuple[int, ...] = ()
    regions: tuple[str, ...] = ()


class FloatParam(NamedTuple):
    name: str
    symbol: str
    default: float
    label: str = ""
    description: str = ""


class BytesParam(NamedTuple):
    name: str
    symbol: str
    size: int
    label: str = ""


class TrampolinePatch(NamedTuple):
    name: str
    label: str
    va: int
    replaced_bytes: bytes   # its size counts; its bytes are the image's (xbe_site)
    shim_object: Path
    shim_symbol: str
    mode: str = "call"
    safety_critical: bool = False
    float_params: tuple[FloatParam, ...] = ()
    bytes_params: tuple[BytesParam, ...] = ()


class ParametricPatch(NamedTuple):
    """What the swap reads of a pack's slider (:func:`get_pack`): its name, USA address, vanilla bytes and default."""
    name: str
    va: int
    original: bytes
    default: float


@dataclass(frozen=True)
class PackView:
    """A pack as the swap reads it (:func:`get_pack`): whether it is on by
    default, its sliders and its hooks (the sdk makes these from the packs'
    catalog: the three tools never import each other)."""
    name: str
    default_on: bool
    sliders: tuple[ParametricPatch, ...] = ()
    hooks: tuple[TrampolinePatch, ...] = ()

    def parametric_sites(self) -> tuple[ParametricPatch, ...]:
        return self.sliders

    def trampoline_sites(self) -> tuple[TrampolinePatch, ...]:
        return self.hooks


def get_pack(name: str) -> PackView:
    try:
        return _build().packs[name]
    except KeyError:
        raise ValueError(f"the swap reads pack {name!r}, which the build doesn't describe") from None


def finite_slider_value(label: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label}: value {value} is not finite; a slider takes any finite number, never NaN or inf")
    return value


def pack_f32(value: float) -> bytes:
    """``value`` as a float32; past its range, the infinity a C cast gives (D23, Q110)."""
    try:
        if not math.isinf(value):
            return struct.pack("<f", value)
    except OverflowError:
        pass
    return struct.pack("<f", math.copysign(math.inf, value))


def release_session(xbe_data: bytearray) -> None:
    """Modkit's shim session holds kernel stubs a buffer's shims share; the player model's shims call none."""


# --------------------------------------------------------------------------- default.xbe


@dataclass(frozen=True)
class Region:
    """A release as the swap names it: its addresses (:meth:`va`)."""
    facts: facts_.Facts

    @property
    def name(self) -> str:
        return self.facts.release.name

    @property
    def label(self) -> str:
        return self.facts.release.label

    def va(self, usa_va: int) -> int:
        try:
            return self.facts.va(usa_va)
        except LookupError as exc:
            raise UnmappedAddressError(str(exc)) from None

    def symbols(self) -> dict[str, int]:
        return self.facts.mangled()


def xbe_layout(xbe: bytes) -> Region:
    """The release whose addresses ``xbe`` has, by its kernel thunk table's (``core.facts.xbe_layout``)."""
    return Region(_facts_of(xbe))


def va_to_file(va: int) -> int:
    """``va``'s file offset in USA's section table as Modkit's static map has it (the section it is past)."""
    for s in sorted(facts_.of(gate.USA).sections, key=lambda s: s.va, reverse=True):
        if va >= s.va:
            return s.raw + va - s.va
    raise ValueError(f"VA 0x{va:X} is below all known sections")


def _offset(region: Region, xbe: bytes, va: int) -> int:
    if region.facts.release is gate.USA:
        return va_to_file(va)
    if (at := resolve_va_to_file(xbe, va)) is None:
        raise UnmappedAddressError(f"0x{va:08X} has no file bytes in this {region.label} XBE")
    return at


def _vanilla_at(region: Region, va: int, size: int) -> bytes:
    """The ``size`` vanilla bytes at the release's ``va``, read from the
    player's vanilla ``default.xbe``; the facts' swap or patch site there,
    when they hold one of that size, must hold their sha256 (D27)."""
    b = _build()
    if region.facts.release is not b.vanilla.release:
        raise ValueError(f"default.xbe is a {region.label} XBE, and this build reads the "
                         f"{b.vanilla.release.label} image")
    vanilla = b.xbe()
    at = _offset(region, vanilla, va)
    data = vanilla[at:at + size]
    for site in (region.facts.swap.get(va), region.facts.sites.get(va)):
        if site is not None and site.size == size and hashlib.sha256(data).hexdigest() != site.sha256:
            raise ValueError(f"default.xbe at 0x{va:08X} isn't the facts' vanilla <{size} B, sha256 {site.sha256[:12]}>")
    return data


def _moved(region: Region, data: bytes, usa_va: int, va: int, abs32=(), rel32=()) -> bytes:
    if region.facts.addresses is None:
        return data
    out = bytearray(data)
    for k in abs32:
        struct.pack_into("<I", out, k, region.va(struct.unpack_from("<I", out, k)[0]))
    for k in rel32:
        target = (usa_va + k + 4 + struct.unpack_from("<i", out, k)[0]) & 0xFFFFFFFF
        struct.pack_into("<i", out, k, region.va(target) - (va + k + 4))
    return bytes(out)


def xbe_site(xbe: bytes, usa_va: int, original: bytes) -> tuple[int, int, bytes]:
    """The USA patch site ``usa_va`` in ``xbe``'s release: its address, its
    file offset in ``xbe`` and the ``len(original)`` vanilla bytes there,
    the player's own (:func:`_vanilla_at`): ``original`` gives the size."""
    region = xbe_layout(xbe)
    va = region.va(usa_va)
    return va, _offset(region, xbe, va), _vanilla_at(region, va, len(original))


def patch_spec_site(xbe_data: bytes, spec: PatchSpec) -> tuple[int, bytes, bytes]:
    """``spec``'s file offset in ``xbe_data``, the vanilla bytes there and its patch, moved to the release."""
    region = xbe_layout(xbe_data)
    if spec.regions and region.name not in spec.regions:
        raise UnmappedAddressError(f"{spec.label}: not a {region.label} site (it is {', '.join(spec.regions)} only)")
    if spec.regions and "usa" not in spec.regions:
        return _offset(region, xbe_data, spec.va), _vanilla_at(region, spec.va, len(spec.original)), spec.patch
    va = region.va(spec.va)
    return (_offset(region, xbe_data, va), _vanilla_at(region, va, len(spec.original)),
            _moved(region, spec.patch, spec.va, va, spec.abs32, spec.rel32))


def _regrow(xbe_data: bytearray, b: Build) -> None:
    """``xbe_data``'s header state laid down from every claim (``core.xbe.grown``)."""
    vanilla = b.xbe()
    grown = xbe_.grown(vanilla, [*b.taken, *b.claims])
    first = min(s.raw for s in xbe_.sections(vanilla) if s.raw)
    xbe_data[:first] = grown[:first]
    if len(grown) > len(xbe_data):
        xbe_data.extend(bytes(len(grown) - len(xbe_data)))


def carve_shim_landing(xbe_data: bytearray, shim_bytes: bytes, align: int = 1,
                       writable: bool = False) -> tuple[int, int]:
    """Land ``shim_bytes`` where the carve allocator gives room past every
    claim (the layers' before, then the swap's): ``(file offset, address)``."""
    b = _build()
    if b.carver is None:
        b.carver = xbe_.Carver(b.xbe(), [(o, n) for o, n, _ in b.taken])
    at, held, offset, va = b.carver.place(len(shim_bytes), align, writable)
    b.claims.append((at, held, writable))
    _regrow(xbe_data, b)
    xbe_data[offset:offset + len(shim_bytes)] = shim_bytes
    return offset, va


def _shape(window: bytes, opcode: int) -> bool:
    return window[0] == opcode and all(x == _NOP for x in window[5:])


def _g4_roll(vanilla: Vanilla) -> bytes:
    """roll.c's ``g4_roll`` table, garret4's roll_forward ``m_feet`` track
    (its marker, component 1: forward): each key's time, value and in- and
    out-tangent as float32, read from the player's characters.xbr."""
    from azurkit.tools.characters import characters, retarget

    data = vanilla.read("gamedata/characters.xbr")
    feet = [name for name, _ in characters.marker_records(data, "garret4")].index("m_feet")
    track = next(t for t in retarget.named_clip(data, "garret4", "roll_forward").markers
                 if (t.target, t.comp) == (feet, 1))
    return b"".join(struct.pack("<4f", *key) for key in track.keys)


HELD = {   # a shim's object (its stem) -> each symbol whose bytes the committed object holds as zeros -> its bytes
    # garret4's roll motion (game data): read from the player's image at each build
    "roll": {"_g4_roll": _g4_roll},
    # Modkit's own constants, held because their bytes meet a vanilla file's by chance, longer than the leak
    # guard's object rule took before D961 (16 B in a data section, 32 in the file; kept as D961's default): the
    # range param's default and the aim's sides and reach beside the zeros around them (fx.xbr, d1.xbr); half the
    # projectile's gravity, in its name
    "drain": {"_player_model_drain_range": struct.pack("<f", 16.0),
              "_aim_node.side": struct.pack("<3f", -1.0, 1.0, 0.0),
              "_aim_node.ahead": struct.pack("<3f", 0.8, 0.8, 1.0)},
    "throw": {"__real@409ccccd": (0x409CCCCD).to_bytes(4, "little")},
}
"""The bytes Modkit's build of a player-model shim holds that ours holds as
zeros (shimkit zeroes them after compiling, ``shimkit.hold``) and every
build writes back into the object as it lands it (:func:`restored`): Modkit's
object byte for byte, its G2 hash (``tests/test_shims.py``)."""


def restored(stem: str, obj: coff.Coff, vanilla: Vanilla | None = None) -> coff.Coff:
    """``obj``, the committed object ``player_model/<stem>.o``, with each of
    its :data:`HELD` symbols' bytes written back (garret4's roll table read
    from ``vanilla``)."""
    held = HELD.get(stem)
    if not held:
        return obj
    sections = list(obj.sections)
    for name, value in held.items():
        data = value(vanilla) if callable(value) else value
        sym = obj.symbol(name)
        s = sections[sym.section - 1]
        body = bytearray(s.data)
        if any(body[sym.value:sym.value + len(data)]) or sym.value + len(data) > len(body):
            raise ValueError(f"player_model/{stem}.o: {name} isn't {len(data)} zero bytes in its section")
        body[sym.value:sym.value + len(data)] = data
        sections[sym.section - 1] = coff.Section(s.name, s.flags, bytes(body), s.relocations)
    return coff.Coff(obj.machine, tuple(sections), obj.symbols)


def apply_trampoline_patch(xbe_data: bytearray, patch: TrampolinePatch, repo_root: Path | None = None, *,
                           params: Mapping[str, float | bytes] | None = None,
                           shim_source: Path | None = None) -> bool:
    """Hook ``patch``'s site with a CALL or JMP rel32 into its shim (the
    prebuilt object), its float and bytes parameters written into its
    landing; ``True``, also when the site holds the hook already (one with
    parameters raises :class:`PatchConflictError`). ``ValueError`` names
    why it can't (a site holding other than its vanilla bytes, an object
    that doesn't lay out), the buffer and claims left as they were."""
    size = len(patch.replaced_bytes)
    if size < 5:
        raise ValueError(f"{patch.label}: replaced_bytes must be >= 5 B (got {size}) to fit a rel32 jump")
    if patch.mode not in ("call", "jmp"):
        raise ValueError(f"{patch.label}: unknown mode {patch.mode!r}, expected 'call' or 'jmp'")
    region = xbe_layout(xbe_data)
    site_va, at, vanilla = xbe_site(xbe_data, patch.va, patch.replaced_bytes)
    opcode = _CALL if patch.mode == "call" else _JMP
    current = bytes(xbe_data[at:at + size])
    if current != vanilla:
        if _shape(current, opcode):
            if patch.float_params or patch.bytes_params:
                raise PatchConflictError(f"{patch.label}: a shim is already installed at VA 0x{patch.va:X} and its "
                                         "params can't be compared; rebuild from vanilla")
            return True
        raise ValueError(f"{patch.label}: default.xbe at VA 0x{site_va:X} holds neither its vanilla bytes nor a hook")
    obj = restored(Path(patch.shim_object).stem, coff.parse(Path(patch.shim_object).read_bytes()), _build().vanilla)
    floats = {p.name: finite_slider_value(p.name, (params or {}).get(p.name, p.default)) for p in patch.float_params}
    tables = {}
    for p in patch.bytes_params:
        value = (params or {}).get(p.name, b"")
        if not isinstance(value, (bytes, bytearray)) or len(value) > p.size:
            raise ValueError(f"{patch.label}: bytes_param {p.name!r} takes bytes, at most {p.size}")
        tables[p.name] = bytes(value).ljust(p.size, b"\0")
    b = _build()
    snapshot, claims = bytes(xbe_data), len(b.claims)
    try:
        text = next((s for s in obj.sections if s.name == ".text"), None)
        if (patch.float_params or patch.bytes_params) and (text is None or not text.relocations):
            raise ValueError("params declared but the shim has no relocations, so it reads none of them")

        def allocate(n: int, align: int, writable: bool) -> tuple[int, int]:
            return carve_shim_landing(xbe_data, bytes(n), align, writable)

        def extern(name: str) -> int | None:
            if any(k.mangled == name for k in region.facts.kernel.values()):
                raise ValueError(f"its kernel import {name!r}: the swap's shims call none (not ported)")
            return None

        placed, entry = coff.layout(obj, patch.shim_symbol, allocate, region.symbols(), extern)
        data = {p.index: bytearray(p.data) for p in placed}
        offsets = {p.index: p.offset for p in placed}
        for p in (*patch.bytes_params, *patch.float_params):
            symbol = obj.symbol(p.symbol)
            if symbol.section - 1 not in data:
                raise ValueError(f"param {p.name!r} (symbol {p.symbol!r}) is not in the landed shim sections")
            value = tables[p.name] if isinstance(p, BytesParam) else pack_f32(floats[p.name])
            if symbol.value + len(value) > len(data[symbol.section - 1]):
                raise ValueError(f"param {p.name!r} runs past its landed section")
            data[symbol.section - 1][symbol.value:symbol.value + len(value)] = value
        for index, body in data.items():
            xbe_data[offsets[index]:offsets[index] + len(body)] = body
        rel32 = entry - (site_va + 5)
        if not -0x80000000 <= rel32 <= 0x7FFFFFFF:
            raise ValueError(f"shim too far for rel32 (delta 0x{rel32:X})")
        xbe_data[at:at + size] = bytes([opcode]) + struct.pack("<i", rel32) + bytes([_NOP] * (size - 5))
    except (LookupError, ValueError, struct.error) as exc:
        xbe_data[:] = snapshot
        del b.claims[claims:]
        if b.carver is not None:
            del b.carver.taken[len(b.taken) + claims:]
        raise ValueError(f"{patch.label}: {exc}") from None
    return True


def verify_trampoline_patch(xbe_data: bytes, patch: TrampolinePatch) -> str:
    """``"applied"``, ``"original"``, ``"mismatch"`` or ``"out-of-range"``: what ``patch``'s site holds."""
    _, at, vanilla = xbe_site(xbe_data, patch.va, patch.replaced_bytes)
    if at + len(vanilla) > len(xbe_data):
        return "out-of-range"
    current = bytes(xbe_data[at:at + len(vanilla)])
    if current == vanilla:
        return "original"
    return "applied" if _shape(current, _CALL if patch.mode == "call" else _JMP) else "mismatch"


def _landed_text(xbe_data: bytes, patch: TrampolinePatch):
    """``(object, its .text, the address it landed at, the landed bytes)``,
    read from the build, or ``None`` when the hook isn't applied."""
    if verify_trampoline_patch(xbe_data, patch) != "applied":
        return None
    obj = restored(Path(patch.shim_object).stem, coff.parse(Path(patch.shim_object).read_bytes()), _build().vanilla)
    entry = obj.symbol(patch.shim_symbol)
    text = obj.sections[entry.section - 1]
    site_va, at, _ = xbe_site(xbe_data, patch.va, patch.replaced_bytes)
    text_va = site_va + 5 + struct.unpack_from("<i", xbe_data, at + 1)[0] - entry.value
    off = resolve_va_to_file(xbe_data, text_va)
    landed = b"" if off is None else bytes(xbe_data[off:off + len(text.data)])
    fields = {r.offset + i for r in text.relocations for i in range(4)}
    if len(landed) != len(text.data) or any(landed[i] != v for i, v in enumerate(text.data) if i not in fields):
        raise ValueError(f"{patch.label}: the code at VA 0x{text_va:X} isn't its shim's .text")
    return obj, text, text_va, landed


def _placed(obj: coff.Coff, text: coff.Section, text_va: int, landed: bytes) -> dict[int, set[int]]:
    placed: dict[int, set[int]] = {}
    for r in text.relocations:
        sym = obj.symbols[r.symbol]
        if sym.section <= 0:
            continue
        target = struct.unpack_from("<I", landed, r.offset)[0]
        if r.type == coff.REL32:
            target += text_va + r.offset + 4
        addend = struct.unpack_from("<i", text.data, r.offset)[0]
        placed.setdefault(sym.section - 1, set()).add((target - addend - sym.value) & 0xFFFFFFFF)
    return placed


def trampoline_shim_data(xbe_data: bytes, patch: TrampolinePatch, repo_root: Path | None = None, *,
                         shim_source: Path | None = None) -> list[tuple[int, int]]:
    """The ``[start, end)`` addresses of the landed ``.data`` and ``.bss`` of ``patch``'s shim."""
    found = _landed_text(xbe_data, patch)
    if found is None:
        return []
    obj, text, text_va, landed = found
    if not text.relocations:
        return []
    placed, out = _placed(obj, text, text_va, landed), []
    for index, section in enumerate(obj.sections):
        if not (section.writable and section.data):
            continue
        vas = placed.get(index, set())
        if len(vas) != 1:
            raise ValueError(f"{patch.label}: {len(vas)} VAs for {section.name} (section {index}) in the .text "
                             "relocations, not 1")
        va = vas.pop()
        out.append((va, va + len(section.data)))
    return sorted(out)


def trampoline_symbol_va(xbe_data: bytes, patch: TrampolinePatch, symbol: str, repo_root: Path | None = None, *,
                         shim_source: Path | None = None) -> int:
    """Where ``symbol`` of ``patch``'s shim landed."""
    found = _landed_text(xbe_data, patch)
    if found is None:
        raise ValueError(f"{patch.label}: no shim at VA 0x{patch.va:X}")
    obj, text, text_va, landed = found
    try:
        sym = obj.symbol(symbol)
    except LookupError:
        raise ValueError(f"{patch.label}: the shim has no symbol {symbol!r}") from None
    if sym.section >= 1 and obj.sections[sym.section - 1] is text:
        return text_va + sym.value
    vas = _placed(obj, text, text_va, landed).get(sym.section - 1, set())
    if len(vas) != 1:
        raise ValueError(f"{patch.label}: {len(vas)} VAs for {symbol!r}'s section in the .text relocations, not 1")
    return vas.pop() + sym.value


# --------------------------------------------------------------------------- XBR archives and keyed tables


class _Entry(NamedTuple):
    tag: str
    file_offset: int


@dataclass
class Cell:
    """A keyed cell as the file holds it now: its 16 bytes' offset, its kind
    (0 empty, 1 a double, 2 a string) and its value."""
    file_offset: int
    type_code: int
    double_value: float | None = None
    string_value: str | None = None
    string_length: int | None = None
    string_file_offset: int | None = None


def _cstring(buf, at: int, limit: int = 512) -> str:
    end = at
    while end < len(buf) and end - at < limit and buf[end] != 0:
        end += 1
    return bytes(buf[at:end]).decode("latin-1")


class KeyedSection:
    """A keyed table (``core.xbr.keyed``'s layout) of :attr:`document`'s
    live bytes: its rows and grid where the parse found them, each cell read
    when asked."""

    def __init__(self, document: XbrDocument, name: str, start: int, words: tuple[int, ...], rows: tuple[str, ...]):
        self.document, self.name = document, name
        self.entry = _Entry("tabl", start)
        self.num_rows, self.num_cols = words[0], words[2]
        self._rows_at, self._grid = start + 4 + words[1], start + 0x10 + words[4]
        self._row_names = list(rows)

    def row_names(self):
        """Each row's name, in order."""
        return [*self._row_names]

    def read_cell(self, col: int, row: int) -> Cell:
        at = self._grid + SIZE * (col * self.num_rows + row)
        buf = self.document.raw
        if at < 0 or at + SIZE > len(buf):
            raise XbrStructuralError(f"keyed cell ({col}, {row}) of {self.name} at 0x{at:08X} runs past the file")
        kind = struct.unpack_from("<I", buf, at)[0]
        cell = Cell(at, kind)
        if kind == NUMBER:
            cell.double_value = struct.unpack_from("<d", buf, at + 8)[0]
        elif kind == STRING:
            cell.string_length = struct.unpack_from("<I", buf, at + 8)[0]
            cell.string_file_offset = at + 12 + struct.unpack_from("<I", buf, at + 12)[0]
            cell.string_value = _cstring(buf, cell.string_file_offset)
        return cell

    def col_names(self):
        """Each column's name, its first row's string (``col_<i>`` where it holds none)."""
        heads = [self.read_cell(k, 0) for k in range(self.num_cols)]
        return [h.string_value if h.type_code == STRING else f"col_{k}" for k, h in enumerate(heads)]

    def find_cell(self, entity: str, prop: str, col: int | None = None) -> Cell | None:
        """The cell of column ``entity`` (its last, or ``col`` when that one
        has the name) and row ``prop``; ``None`` when there is none."""
        if prop not in self._row_names:
            return None
        row, cols = self._row_names.index(prop), self.col_names()
        if col is not None:
            return self.read_cell(col, row) if 0 <= col < len(cols) and cols[col] == entity else None
        found = [i for i, name in enumerate(cols) if name == entity]
        return self.read_cell(found[-1], row) if found else None

    def refs(self) -> Iterator[tuple[int, int]]:
        """Each reference to a string, ``(its field, the string's offset)``, in the live bytes."""
        buf = self.document.raw
        fields = [self._rows_at + 8 * k + 4 for k in range(self.num_rows)]
        yield from ((f, (f + struct.unpack_from("<I", buf, f)[0]) & 0xFFFFFFFF) for f in fields)
        for k in range(self.num_rows * self.num_cols):
            at = self._grid + SIZE * k
            if struct.unpack_from("<I", buf, at)[0] == STRING:
                yield at + 12, (at + 12 + struct.unpack_from("<I", buf, at + 12)[0]) & 0xFFFFFFFF


class XbrDocument:
    """An archive's bytes, :attr:`raw` (edited in place), and its keyed tables by name."""

    def __init__(self, raw: bytearray):
        self.raw = raw
        self._tables: dict[str, KeyedSection] | None = None

    @classmethod
    def from_bytes(cls, data) -> XbrDocument:
        return cls(bytearray(data))

    def _keyed(self) -> dict[str, KeyedSection]:
        if self._tables is None:
            parsed = Document(bytes(self.raw)).tables
            self._tables = {name: KeyedSection(self, name, t.start, t.words, t.rows) for name, t in parsed.items()}
        return self._tables

    def keyed_section(self, name: str) -> KeyedSection:
        if name not in self._keyed():
            raise ValueError(f"no keyed table {name!r} (the file's: {', '.join(sorted(self._keyed()))})")
        return self._keyed()[name]

    def sections(self) -> list[KeyedSection]:
        return list(self._keyed().values())


def _load_doc_for_edit(xbr_files, filename: str) -> XbrDocument:
    """The :class:`XbrDocument` whose :attr:`~XbrDocument.raw` is the staged
    file ``filename``'s buffer, one a buffer however it is named."""
    buf = xbr_files.get(filename)
    if buf is None:
        raise ValueError(f"XBR buffer {filename!r} not provided")
    cache = getattr(xbr_files, "_xbr_doc_cache", None)
    if cache is None:
        cache = {}
        with contextlib.suppress(AttributeError, TypeError):
            xbr_files._xbr_doc_cache = cache
    if (doc := cache.get(id(buf))) is None:
        doc = XbrDocument.from_bytes(buf)
        xbr_files[filename] = doc.raw
        cache[id(doc.raw)] = doc
    return doc


def _where(section: KeyedSection, entity: str, prop: str) -> str:
    return f"cell {entity!r}/{prop!r} of {section.name}"


def _cell(section: KeyedSection, entity: str, prop: str, col: int | None) -> Cell:
    cell = section.find_cell(entity, prop, col)
    if cell is None:
        raise XbrStructuralError(f"{_where(section, entity, prop)}: not found")
    return cell


def _blank(section: KeyedSection, cell: Cell) -> bool:
    return cell.type_code == EMPTY and not any(section.document.raw[cell.file_offset:cell.file_offset + SIZE])


def _fillable(section: KeyedSection, entity: str, prop: str, kind: int) -> None:
    """An empty cell takes ``kind`` unless its row holds only the other kind."""
    row = section.row_names().index(prop)
    held = {section.read_cell(k, row).type_code for k in range(section.num_cols)}
    if NUMBER + STRING - kind in held and kind not in held:
        raise XbrStructuralError(f"{_where(section, entity, prop)} is empty and its row holds "
                                 f"{'numbers' if kind == STRING else 'strings'}, so it can't be filled with "
                                 f"{'a string' if kind == STRING else 'a number'}")


def set_keyed_double(section: KeyedSection, entity: str, prop: str, value: float, col: int | None = None,
                     fill_empty: bool = False) -> int:
    """Write the double ``value`` (finite, D23) into a number cell (an empty
    one too with ``fill_empty``); the double's file offset."""
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        raise XbrStructuralError(f"{_where(section, entity, prop)}: {value} is not finite")
    cell, buf = _cell(section, entity, prop, col), section.document.raw
    if fill_empty and _blank(section, cell):
        _fillable(section, entity, prop, NUMBER)
        struct.pack_into("<II", buf, cell.file_offset, NUMBER, 0)
    elif cell.type_code != NUMBER:
        raise XbrStructuralError(f"{_where(section, entity, prop)} holds kind {cell.type_code}, not a number")
    struct.pack_into("<d", buf, cell.file_offset + 8, value)
    return cell.file_offset + 8


def _slot(buf, cell: Cell) -> int:
    """A string's room in place: its length and the NULs after it, at least its length and one NUL."""
    end = cell.string_file_offset + cell.string_length
    while end < len(buf) and buf[end] == 0:
        end += 1
    return max(cell.string_length + 1, end - cell.string_file_offset)


def string_sharer_counts(section: KeyedSection, cells) -> list[int]:
    """For each string cell of ``cells``, how many references besides its
    own point into its string's room (:func:`_slot`), over every keyed table."""
    buf = section.document.raw
    targets = sorted((target, src) for s in section.document.sections() for src, target in s.refs())
    keys = [t for t, _ in targets]
    out = []
    for cell in cells:
        lo = _bisect(keys, cell.string_file_offset)
        hi = _bisect(keys, cell.string_file_offset + _slot(buf, cell))
        out.append(sum(src != cell.file_offset + 12 for _, src in targets[lo:hi]))
    return out


def _bisect(keys: list[int], value: int) -> int:
    lo, hi = 0, len(keys)
    while lo < hi:
        mid = (lo + hi) // 2
        if keys[mid] < value:
            lo = mid + 1
        else:
            hi = mid
    return lo


def set_keyed_string(section: KeyedSection, entity: str, prop: str, new: str, col: int | None = None) -> int:
    """Rewrite a string cell's string in place, NUL-padded to its room, when
    it fits and no other reference shares it; its string's file offset."""
    if not new.isascii():
        raise XbrStructuralError(f"{_where(section, entity, prop)}: {new!r} isn't ASCII")
    cell, buf = _cell(section, entity, prop, col), section.document.raw
    if cell.type_code != STRING:
        raise XbrStructuralError(f"{_where(section, entity, prop)} holds kind {cell.type_code}, not a string")
    start = cell.string_file_offset
    if start < 0 or start + cell.string_length + 1 > len(buf):
        raise XbrStructuralError(f"{_where(section, entity, prop)}: its string runs past the file")
    room, raw = _slot(buf, cell), new.encode("ascii")
    if len(raw) + 1 > room:
        raise XbrStructuralError(f"{_where(section, entity, prop)}: {new!r} needs {len(raw) + 1} B, its string's "
                                 f"room is {room} B (a longer string needs the table to grow)")
    if shared := string_sharer_counts(section, [cell])[0]:
        raise XbrStructuralError(f"{_where(section, entity, prop)}: its string is shared with {shared} other "
                                 "reference(s)")
    buf[start:start + room] = raw + bytes(room - len(raw))
    struct.pack_into("<I", buf, cell.file_offset + 8, len(raw))
    return start


def point_keyed_string(section: KeyedSection, entity: str, prop: str, src_entity: str, src_prop: str,
                       col: int | None = None, src_col: int | None = None, fill_empty: bool = False,
                       src_cell: Cell | None = None) -> None:
    """Point the string cell ``entity``/``prop`` (an empty one too with
    ``fill_empty``) at the string the cell ``src_entity``/``src_prop`` holds
    (or held: ``src_cell``, read before)."""
    buf = section.document.raw
    dst = section.find_cell(entity, prop, col)
    src = section.find_cell(src_entity, src_prop, src_col)
    for c, (e, p) in ((dst, (entity, prop)), (src, (src_entity, src_prop))):
        if c is None:
            raise XbrStructuralError(f"{_where(section, e, p)}: not found")
    fill = fill_empty and _blank(section, dst)
    if not fill and dst.type_code != STRING:
        raise XbrStructuralError(f"{_where(section, entity, prop)} holds kind {dst.type_code}, not a string")
    if src.type_code != STRING:
        raise XbrStructuralError(f"{_where(section, src_entity, src_prop)} holds kind {src.type_code}, not a string")
    src = src if src_cell is None else src_cell
    if fill:
        _fillable(section, entity, prop, STRING)
        struct.pack_into("<I", buf, dst.file_offset, STRING)
    struct.pack_into("<II", buf, dst.file_offset + 8, src.string_length,
                     (src.string_file_offset - (dst.file_offset + 12)) & 0xFFFFFFFF)


def point_at_string(section: KeyedSection, entity: str, prop: str, value: str, col: int | None = None,
                    fill_empty: bool = False) -> None:
    """Point the cell at ``value``: the string the table's first cell holding it (column by column) holds."""
    for k in range(section.num_cols * section.num_rows):   # column by column
        c, r = divmod(k, section.num_rows)
        held = section.read_cell(c, r)
        if held.type_code == STRING and held.string_value == value:
            return point_keyed_string(section, entity, prop, section.col_names()[c], section.row_names()[r],
                                      col, c, fill_empty)
    raise XbrStructuralError(f"{_where(section, entity, prop)}: no cell of {section.name} holds {value!r} (a new "
                             "string needs the table to grow)")


def clear_keyed_cell(section: KeyedSection, entity: str, prop: str, col: int | None = None) -> None:
    """Empty the cell: its 16 bytes zeros (its string stays, unreferenced by it)."""
    cell = _cell(section, entity, prop, col)
    section.document.raw[cell.file_offset:cell.file_offset + SIZE] = bytes(SIZE)


def replace_bytes_at(doc: XbrDocument, offset: int, new: bytes, expected: bytes | None = None) -> None:
    """Write ``new`` at ``offset``, where the file holds ``expected`` (or ``new`` already) when given."""
    end = offset + len(new)
    if offset < 0 or end > len(doc.raw):
        raise XbrStructuralError(f"replace_bytes out of range at 0x{offset:08X} ({len(new)} B)")
    if expected is not None and bytes(doc.raw[offset:end]) not in (bytes(expected), bytes(new)):
        raise XbrStructuralError(f"at 0x{offset:08X} the file holds neither the expected original nor the new value")
    doc.raw[offset:end] = new


class KeyedTable:
    """A keyed table read whole, as Modkit's ``load_all_tables`` gives one:
    its column names (``col_<i>`` for one with no name), row names, each
    name's last column and each cell's ``(kind, value, offset)``."""

    def __init__(self, section: KeyedSection):
        self.col_names, self.row_names = section.col_names(), section.row_names()
        self.entity_index = dict(zip(self.col_names, range(len(self.col_names))))   # a repeated name: its last
        self._section = section

    def read_cell(self, col: int, row: int) -> tuple[str, float | str | None, int]:
        cell = self._section.read_cell(col, row)
        kind = {NUMBER: "double", STRING: "string"}.get(cell.type_code, "empty")
        return kind, cell.double_value if cell.type_code == NUMBER else cell.string_value, cell.file_offset

    def get_value(self, entity: str, prop: str):
        col = self.entity_index.get(entity)
        if col is None or prop not in self.row_names:
            return None
        return self.read_cell(col, self.row_names.index(prop))


def load_all_tables(config, sections=None) -> dict[str, KeyedTable]:
    """config.xbr's keyed tables (only ``sections``, when named), by name."""
    doc = XbrDocument.from_bytes(config)
    want = None if sections is None else set(sections)
    return {name: KeyedTable(s) for name, s in doc._keyed().items() if want is None or name in want}


# --------------------------------------------------------------------------- the staff fx ring's link curves
# (Modkit's ``randomizer/levels.py``: Curve, link_curve, link_value; the plan's cut of _player_fx_ring's import)

FLT_MAX = 3.4028234663852886e38


class Curve:
    """The link curve a link's curve field (at section offset ``field_off``) points at."""

    def __init__(self, s: bytes, field_off: int):
        h = field_off + struct.unpack_from("<i", s, field_off)[0]
        kind, n, kref = struct.unpack_from("<IIi", s, h)
        self.pre, self.post = kind & 0xFFFF, kind >> 16
        self.n = n & 0x0FFFFFFF
        keys_at = h + 8 + kref
        self.keys = [struct.unpack_from("<4f", s, keys_at + 16 * k) for k in range(self.n)]

    def __call__(self, x: float) -> float:
        ks = self.keys
        x0, xl = ks[0][0], ks[-1][0]
        if x < x0:
            if self.pre in (0, 1):
                return ks[0][1] if self.pre == 0 else (x - x0) * ks[0][2] + ks[0][1]
            raise ValueError(f"pre-infinity mode {self.pre} is not modelled")
        if x >= xl:
            if self.post in (0, 1):
                slope = ks[-1][3] if math.isfinite(ks[-1][3]) else 0.0
                return ks[-1][1] if self.post == 0 else (x - xl) * slope + ks[-1][1]
            raise ValueError(f"post-infinity mode {self.post} is not modelled")
        i = max((k for k in range(len(ks) - 1) if ks[k][0] <= x), default=0)
        (xa, ya, _, outa), (xb, yb, inb, _) = ks[i], ks[i + 1]
        if outa > FLT_MAX:
            return ya
        dx = xb - xa
        t = (x - xa) / dx
        m0 = dx * outa
        m1 = dx * inb if math.isfinite(dx * inb) else 0.0
        return (((2 * (ya - yb) + m1 + m0) * t + (3 * (yb - ya) - 2 * m0 - m1)) * t + m0) * t + ya


def link_curve(g, i: int, k: int) -> Curve | None:
    """The curve of record ``i``'s k-th link, or ``None`` (curve word 1)."""
    st, _ = g.list_at(i, 0x10)
    lo = st + 24 * k
    return None if struct.unpack_from("<I", g.s, lo + 4)[0] == 1 else Curve(g.s, lo + 4)


def link_value(cv: Curve | None, x: float, weight: float, factor: float) -> float:
    """The value a link delivers for source value x (0x663B0)."""
    return (cv(x * weight) if cv is not None else x * weight) * factor


"""What the simulator's modules ported from Modkit (Step 4.13a, AGENTS.md's Porting from Modkit) import from
Modkit's shared engine, on AzurKit's: a port points those imports here, so each module's code stays Modkit's
(``azurkit.tools.randomizer.ports`` is the randomizer's like table).

- the XBE: :func:`parse_xbe_sections` (Modkit's ``patching.xbe``, on :func:`azurkit.core.xbe.sections`) and
  :func:`parse_kernel_thunks` (``patching.kernel_imports``, its names from ``data/kernel.toml``);
- the game's functions a shim may call, :func:`all_entries` (``patching.vanilla_symbols``: the USA facts');
- the packs: :func:`get_pack`, :func:`ordered_packs`, :func:`build` and :func:`apply_pack` (``patching.registry``
  and ``.apply``, on :mod:`azurkit.tools.mods`);
- the image: :data:`VANILLA_ISO_SHA256`, :func:`resolve_vanilla_iso` and :func:`vanilla_iso` (``assets.vanilla``:
  :data:`azurkit.core.gate.USA`'s),
  :class:`XisoReader` and :func:`read_file` (``iso.xiso``, on :class:`azurkit.core.iso.Reader`).
"""

from __future__ import annotations

import functools
import json
import os
import struct
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from azurkit.core import facts, gate, iso, xbe
from azurkit.tools.randomizer import ports

KERNEL = Path(__file__).resolve().parent / "data" / "kernel.toml"
VANILLA_ISO_SHA256 = gate.USA.iso_sha256
_THUNK_KEYS = (0x5B6D40B6, 0xEFB1F152, 0x2290059D)   # the header's thunk table address is XORed with one: retail,
                                                    # debug, Chihiro


def parse_xbe_sections(data: bytes) -> tuple[int, list[dict]]:
    """The XBE's base address and its sections, each ``{name, vaddr, vsize, raw_addr, raw_size, flags}``;
    ``ValueError`` when ``data`` isn't an XBE or its table runs off it."""
    table = xbe.sections(data)
    return struct.unpack_from("<I", data, 0x104)[0], [
        {"name": s.name, "vaddr": s.va, "vsize": s.vsize, "raw_addr": s.raw, "raw_size": s.raw_size,
         "flags": s.flags} for s in table]


@dataclass(frozen=True)
class ThunkEntry:
    """A slot of the kernel thunk table: its address, the export's ordinal and its name (None: unknown)."""
    thunk_va: int
    ordinal: int
    name: str | None


@functools.cache
def _kernel() -> dict:
    return tomllib.loads(KERNEL.read_text(encoding="utf-8"))


def parse_kernel_thunks(data: bytes) -> list[ThunkEntry]:
    """Every slot of the XBE's kernel thunk table, up to its zero terminator: each holds 0x80000000 | the
    export's ordinal (the loader indexes the export table with the low 31 bits). ``ValueError`` for a header
    whose thunk address no key puts in the image, a slot without the high bit or a table past 1000 slots."""
    if bytes(data[:4]) != xbe.MAGIC:
        raise ValueError("not an XBE: no XBEH at 0")
    base, size, raw = (struct.unpack_from("<I", data, at)[0] for at in (0x104, 0x10C, 0x158))
    va = next((raw ^ k for k in _THUNK_KEYS if base <= raw ^ k < base + size), None)
    if va is None:
        raise ValueError(f"the kernel thunk address 0x{raw:08X} is in the image under no key")
    at = xbe.offset(xbe.sections(data), va, 4)
    names = _kernel()["names"]
    out = []
    for i in range(1000):
        slot = struct.unpack_from("<I", data, at + 4 * i)[0]
        if slot == 0:
            return out
        if not slot & 0x80000000:
            raise ValueError(f"kernel thunk slot {i} at 0x{va + 4 * i:X} is 0x{slot:08X}, not by ordinal")
        out.append(ThunkEntry(va + 4 * i, slot & 0x7FFFFFFF, names.get(str(slot & 0x7FFFFFFF))))
    raise ValueError("the kernel thunk table runs past 1000 slots with no terminator")


def all_entries() -> list[facts.Function]:
    """The game's functions a shim may call (the USA facts'), each with its ``va``."""
    return list(facts.of(gate.USA).functions.values())


def get_pack(name: str):
    """The pack ``name``; ``KeyError`` for an unknown one."""
    from azurkit.tools.mods import PACKS
    return PACKS[name]


def ordered_packs(names: Iterable[str]) -> list:
    """The packs ``names`` asks for, each once, in the order every build applies them; ``KeyError`` names an
    unknown one."""
    from azurkit.tools.mods import PACKS
    wanted = {get_pack(name).name for name in names}
    return [pack for pack in PACKS.values() if pack.name in wanted]


@functools.cache
def _vanilla_file(name: str) -> bytes:
    if (path := gate.find(gate.USA)) is None:
        raise ValueError(gate.missing(gate.USA))
    with iso.Reader(path) as r:
        return bytes(r.read(name))


def build(vanilla: bytes, params: Mapping[str, Mapping[str, object]]) -> bytes:
    """The USA release's vanilla XBE ``vanilla`` built with the packs ``params`` names (``{pack: {slider:
    value}}``), each once in the order every build applies them, as AzurKit's build plans and lays them
    (:func:`azurkit.tools.mods.plan`, :func:`azurkit.edits.layer.compose`; a pack that reads config.xbr reads the
    USA image's, :func:`azurkit.core.gate.find`'s). Only the XBE is built: a config.xbr slider away from its
    default is refused (``ValueError``), as is any other XBE than vanilla's (the engine's ``PackError``)."""
    from azurkit.edits import layer
    from azurkit.tools.mods import engine
    base, layers = {engine.XBE: bytes(vanilla)}, []
    for pack in ordered_packs(params):
        given = params[pack.name]
        if cells := [s.name for s in pack.sliders() if isinstance(s, engine.XbrParametricEdit)
                     and s.name in given and float(given[s.name]) != s.default]:
            raise ValueError(f"pack {pack.name!r}: {', '.join(cells)} write config.xbr, which this build has none of")
        base |= {name: _vanilla_file(name) for name in pack.files() if name not in base}
        layers.append(engine.plan(pack, gate.USA, base, given, [c for la in layers for c in la.claims]))
    files, _ = layer.compose(base, layers)
    return bytes(files.get(engine.XBE, base[engine.XBE]))


def apply_pack(pack, xbe_: bytearray, params: Mapping[str, object]) -> None:
    """``pack`` at ``params`` written into the USA release's vanilla XBE ``xbe_``, in place (:func:`build`)."""
    xbe_[:] = build(bytes(xbe_), {pack.name: params})


class XisoReader(ports.XisoReader):
    """An image read file by file, as Modkit's ``iso.xiso.XisoReader``: :meth:`find` a file's entry and
    :meth:`read_at` part of it, besides :meth:`read_file`."""

    def find(self, path: str) -> iso.Entry:
        return self._reader.find(path)

    def read_at(self, entry: iso.Entry, off: int, n: int) -> bytes:
        """Up to ``n`` bytes of the file ``entry`` from ``off`` (fewer at its end)."""
        n = max(0, min(n, entry.size - off))
        return self._reader.range(entry, off, n) if n else b""


def resolve_vanilla_iso() -> Path:
    """Where the USA image is (:func:`azurkit.core.gate.find`), unverified: ``FileNotFoundError`` where it looked."""
    if (path := gate.find(gate.USA)) is None:
        raise FileNotFoundError(gate.missing(gate.USA))
    return path


class _Stamps:
    """:data:`azurkit.core.gate.STAMPS` for :func:`vanilla_iso`: the images it passed, ``{key: release}`` in the
    user cache's ``AzurKit/devkit-iso-stamps.json`` (Modkit's ``vanilla-iso-stamps.json``), so a process hashes no
    image as it was when another passed it (an L3 pool's worker reads the disc first inside a step: a whole check
    there ran past L3's watchdog, Step 4.13d1)."""

    def __init__(self, file: Path) -> None:
        self.file = file

    def _read(self) -> dict:
        try:
            kept = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return kept if isinstance(kept, dict) else {}

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def put(self, key: str, name: str) -> None:
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_name(f".{self.file.name}.{os.getpid()}.part")
            tmp.write_text(json.dumps(self._read() | {key: name}), encoding="utf-8")
            os.replace(tmp, self.file)
        except OSError:
            pass                                    # a stamp that can't be kept is only slower


@functools.cache
def vanilla_iso() -> Path:
    """The USA image, through the identity gate (every file of it, once a process, and not again while the image
    is as a process before found it: :class:`_Stamps`): ``FileNotFoundError`` where it looked, else
    :class:`azurkit.core.gate.NotVanillaError` (a ``ValueError``) naming what differs."""
    from platformdirs import user_cache_path
    if (path := gate.find(gate.USA)) is None:
        raise FileNotFoundError(gate.missing(gate.USA))
    host, gate.STAMPS = gate.STAMPS, gate.STAMPS or _Stamps(user_cache_path("AzurKit", appauthor=False)
                                                            / "devkit-iso-stamps.json")
    try:
        gate.verify(path, releases=(gate.USA,))
    finally:
        gate.STAMPS = host
    return path


def read_file(image, path: str) -> bytes:
    """The bytes of the file ``path`` (``"default.xbe"``) in ``image``."""
    with XisoReader(image) as r:
        return r.read_file(path)

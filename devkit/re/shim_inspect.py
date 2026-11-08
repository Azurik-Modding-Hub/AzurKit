"""``python -m devkit re shim-inspect TARGET``: preview what a compiled
shim object will land (Modkit's ``azurik-mod shim-inspect``, ported in Step
4.11e).

It reads a ``.o`` with :mod:`azurkit.core.coff`, the parser the engine lands
shims with, and summarises it without a build, to check that:

- the section sizes line up with the trampoline's budget;
- the relocations target the game functions expected;
- the calling-convention decorations (``@N`` stdcall, ``@name@N``
  fastcall) are the ones the facts' functions mangle to;
- a static-assert trap fired (or didn't) at compile time.

``TARGET`` is a ``.o`` (or its ``.c``, whose object is beside it), or a
shim's name (``<name>.o`` in ``shimkit.FOLDERS``: the packs', each named
after its pack, and the player-model swap's).
Each external the facts know as a game function is listed with its address
in the release asked for (USA's by default), or as having none there (a
function Europe's facts don't list, such as its rebuilt D3D's). A section's
first bytes are the shim's own code, never the game's.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import shimkit
from azurkit.core import coff, facts
from azurkit.core.gate import RELEASES, USA, Release

# IMAGE_REL_I386_* -> human name.  The subset core.coff relocates
# (layout refuses anything else).
_RELOC_TYPE_NAMES = {
    0x0000: "ABSOLUTE",
    0x0006: "DIR32",
    0x0007: "DIR32NB",
    0x0014: "REL32",
}

# Storage-class codes we see in practice (clang-cl + nxdk LLD).
_STORAGE_CLASS_NAMES = {
    2: "EXTERNAL",
    3: "STATIC",
    6: "LABEL",
    101: "FUNCTION",
    105: "FILE",
    103: "END_OF_STRUCT",
}


@dataclass(frozen=True)
class ShimSectionSummary:
    name: str
    raw_size: int
    flags: int
    reloc_count: int
    reloc_types: tuple[str, ...]  # unique, sorted
    first_bytes: str              # hex, up to first 32 bytes


@dataclass(frozen=True)
class ShimSymbolSummary:
    name: str
    section_number: int
    value: int
    storage_class: int
    storage_class_name: str
    is_external: bool


@dataclass(frozen=True)
class ShimRelocationSummary:
    section_name: str      # which section the reloc lives in
    offset: int            # offset within that section
    type_code: int
    type_name: str
    symbol_name: str


@dataclass
class ShimInspection:
    """Full inspection report for one compiled shim object."""

    path: str
    machine: int
    total_section_bytes: int
    sections: list[ShimSectionSummary] = field(default_factory=list)
    symbols: list[ShimSymbolSummary] = field(default_factory=list)
    relocations: list[ShimRelocationSummary] = field(default_factory=list)
    region: str = "usa"
    vanilla_vas: dict[str, int | None] = field(default_factory=dict)
    """Each external the facts know as a game function: its address in
    :attr:`region`, or ``None`` when that release has none."""

    @property
    def externals(self) -> list[ShimSymbolSummary]:
        """Every external (undefined) symbol, i.e. callouts to vanilla
        functions that the COFF loader will need to resolve."""
        return [s for s in self.symbols if s.is_external]

    def to_json_dict(self) -> dict:
        return {
            "path": self.path,
            "region": self.region,
            "vanilla_vas": self.vanilla_vas,
            "machine": self.machine,
            "total_section_bytes": self.total_section_bytes,
            "sections": [
                {"name": s.name, "raw_size": s.raw_size,
                 "flags": s.flags, "reloc_count": s.reloc_count,
                 "reloc_types": list(s.reloc_types),
                 "first_bytes": s.first_bytes}
                for s in self.sections],
            "symbols": [
                {"name": s.name, "section_number": s.section_number,
                 "value": s.value, "storage_class": s.storage_class,
                 "storage_class_name": s.storage_class_name,
                 "is_external": s.is_external}
                for s in self.symbols],
            "relocations": [
                {"section": r.section_name, "offset": r.offset,
                 "type_code": r.type_code, "type_name": r.type_name,
                 "symbol": r.symbol_name}
                for r in self.relocations],
        }


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def vanilla_vas(names, release: Release) -> dict[str, int | None]:
    """``{name: its address in release, or None}`` for each of ``names``
    (mangled) that is a game function the facts know (USA's list them all)."""
    known, here = facts.of(USA).mangled(), facts.of(release).mangled()
    return {n: here.get(n) for n in names if n in known}


def inspect_object(target: Path | str, release: Release = USA) -> ShimInspection:
    """Inspect a ``.o`` file, its ``.c``, or a shim's name (:func:`resolve`).

    Raises
    ------
    FileNotFoundError
        No matching .o is found (bad path or name, or an unbuilt shim).
    ValueError
        The file exists but doesn't parse as PE-COFF (a stray .xbe or
        raw binary passed by mistake); the message names its size and
        the parser's reason, never its bytes.

    ``release`` is the one whose addresses :attr:`ShimInspection.vanilla_vas`
    gives.
    """
    obj_path = resolve(target)
    raw = obj_path.read_bytes()
    try:
        parsed = coff.parse(raw)
    except ValueError as exc:
        raise ValueError(
            f"{obj_path} is not a parseable PE-COFF .o file "
            f"({len(raw)} B): {exc}") from exc
    result = _summarise(obj_path, parsed)
    result.region = release.name
    result.vanilla_vas = vanilla_vas([s.name for s in result.externals], release)
    return result


def resolve(target: Path | str) -> Path:
    """Turn a target into a concrete ``.o`` file: a file (a ``.c``'s object
    beside it), else a shim's name in one of ``shimkit.FOLDERS`` (a pack's
    shim is named after it)."""
    path = Path(target)
    if path.is_file():
        obj = path.with_suffix(".o") if path.suffix == ".c" else path
        if not obj.is_file():
            raise FileNotFoundError(f"{path} has no object beside it ({obj.name}); "
                                    f"`uv run --locked python -m shimkit` builds it")
        return obj
    for folder in shimkit.FOLDERS:
        if (obj := folder / f"{target}.o").is_file():
            return obj
    raise FileNotFoundError(f"no file or shim {str(target)!r}")


def _summarise(path: Path, obj: coff.Coff) -> ShimInspection:
    """Render a parsed :class:`coff.Coff` as a :class:`ShimInspection`."""
    sec_summaries = []
    reloc_summaries = []
    total_bytes = 0

    for section in obj.sections:
        total_bytes += len(section.data)
        reloc_types = sorted({
            _RELOC_TYPE_NAMES.get(r.type, f"UNKNOWN(0x{r.type:X})")
            for r in section.relocations})
        sec_summaries.append(ShimSectionSummary(
            name=section.name,
            raw_size=len(section.data),
            flags=section.flags,
            reloc_count=len(section.relocations),
            reloc_types=tuple(reloc_types),
            first_bytes=(section.data[:32].hex() if section.data else ""),
        ))
        for reloc in section.relocations:
            sym = _safe_symbol(obj.symbols, reloc.symbol)
            reloc_summaries.append(ShimRelocationSummary(
                section_name=section.name,
                offset=reloc.offset,
                type_code=reloc.type,
                type_name=_RELOC_TYPE_NAMES.get(
                    reloc.type, f"UNKNOWN(0x{reloc.type:X})"),
                symbol_name=sym.name if sym else "(unknown)",
            ))

    sym_summaries = []
    for sym in obj.symbols:
        if not sym.name:
            continue  # skip placeholder aux entries (empty name)
        sym_summaries.append(ShimSymbolSummary(
            name=sym.name,
            section_number=sym.section,
            value=sym.value,
            storage_class=sym.storage,
            storage_class_name=_STORAGE_CLASS_NAMES.get(
                sym.storage,
                f"CLASS_{sym.storage}"),
            is_external=(sym.section == 0 and
                         sym.storage == coff.EXTERNAL),
        ))

    return ShimInspection(
        path=str(path),
        machine=obj.machine,
        total_section_bytes=total_bytes,
        sections=sec_summaries,
        symbols=sym_summaries,
        relocations=reloc_summaries,
    )


def _safe_symbol(symbols: tuple[coff.Symbol, ...],
                 index: int) -> coff.Symbol | None:
    if 0 <= index < len(symbols):
        return symbols[index]
    return None


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def format_inspection(r: ShimInspection) -> str:
    lines = [
        f"=== Shim inspection: {r.path} ===",
        f"  release:              {r.region}",
        f"  machine:              0x{r.machine:04X}",
        f"  total section bytes:  {r.total_section_bytes}",
        "",
        "Sections:",
    ]
    for s in r.sections:
        rtypes = ", ".join(s.reloc_types) or "(none)"
        lines.append(
            f"  {s.name:<12s}  size={s.raw_size:5d}   "
            f"flags=0x{s.flags:08X}   relocs={s.reloc_count:2d}  "
            f"[{rtypes}]")
        if s.first_bytes:
            preview = s.first_bytes[:64]
            more = "..." if len(s.first_bytes) > 64 else ""
            lines.append(f"    bytes[0:32] = {preview}{more}")

    lines.append("")
    lines.append(f"Symbols ({len(r.symbols)}):")
    ext = r.externals
    if ext:
        lines.append(f"  {len(ext)} external (resolved against "
                     f"the facts' functions at layout time):")
        for s in ext:
            va = r.vanilla_vas.get(s.name, 0)
            where = ("" if s.name not in r.vanilla_vas
                     else f"  0x{va:X}" if va is not None else f"  (no {r.region} address)")
            lines.append(
                f"    {s.name:<40s}  {s.storage_class_name}{where}")
    internals = [s for s in r.symbols if not s.is_external]
    if internals:
        lines.append(f"  {len(internals)} internal / section / local:")
        for s in internals[:20]:
            lines.append(
                f"    {s.name:<40s}  sect={s.section_number}  "
                f"val=0x{s.value:X}  {s.storage_class_name}")
        if len(internals) > 20:
            lines.append(f"    ... and {len(internals) - 20} more")

    lines.append("")
    lines.append(f"Relocations ({len(r.relocations)}):")
    for reloc in r.relocations:
        lines.append(
            f"  {reloc.section_name:<12s}  off=0x{reloc.offset:04X}  "
            f"{reloc.type_name:<10s}  -> {reloc.symbol_name}")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """A target with no object, or a file that isn't one, is one
    ``shim-inspect: ...`` line and exit 1 (Modkit's), not a traceback."""
    p = argparse.ArgumentParser(
        prog="python -m devkit re shim-inspect",
        description="Summarise a compiled shim object (PE-COFF .o): its sections and their sizes, its symbols "
                    "and every relocation, the game functions it calls at the release's addresses, before any "
                    "build.")
    p.add_argument("target", help="a .o (or its .c), or a shim's name (a pack's shim is named after it)")
    p.add_argument("--region", choices=[r.name for r in RELEASES], default=USA.name,
                   help="the release whose addresses the game functions it calls resolve to (default usa)")
    p.add_argument("--json", action="store_true", help="JSON instead of the report")
    args = p.parse_args(argv)
    try:
        result = inspect_object(args.target, next(r for r in RELEASES if r.name == args.region))
    except (FileNotFoundError, ValueError) as exc:
        print(f"shim-inspect: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.to_json_dict(), indent=2) if args.json else format_inspection(result))
    return 0


__all__ = [
    "ShimInspection",
    "ShimRelocationSummary",
    "ShimSectionSummary",
    "ShimSymbolSummary",
    "format_inspection",
    "inspect_object",
]

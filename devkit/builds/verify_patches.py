"""``python -m devkit builds verify-patches (--iso IMAGE | --xbe XBE)``: what
each pack's sites hold in any build's ``default.xbe`` (Modkit's
``verify-patches``, ported in Step 4.6l): an AzurKit build, a Modkit one or
another, of either release, each site at that release's own address.

- **Fixed patches** (``PatchSpec``): applied (the pack's bytes), original
  (vanilla's) or mismatch (neither: the length and sha256[:12] of each, and
  the first offset where they part, never the bytes).
- **Sliders at a site** (``ParametricPatch``): default (vanilla's bytes, the
  value they hold), custom (the value) or mismatch (no finite value); a
  virtual one has no site of its own and is listed as such.
- **Trampolines** (``TrampolinePatch``): applied (a CALL or JMP rel32, as
  the patch says, into the shim room, the rest of the site NOPs), original
  or mismatch.
- **A pack that writes its own sites** (a ``custom_apply``): how many of its
  footprint's places the build changed, and which.
- **The player-model swap's sites** (the facts' ``swap``): how many it changed.
- **Bytes outside them all:** the build against its release's vanilla XBE
  (``--original``, else the player's image), every byte that differs
  outside every pack's sites and footprint, the swap's sites and the shim
  room (``.text``'s growth and the appended ``SHIMS`` section), with the
  header held to the state those derive (``core.xbe.grown``): each run's
  file offset, VA and section and its length.

- **The frame-rate guard** (Modkit's safety-critical guard, which pinned
  fps_unlock's step cap): the frame rate the main loop's rate holds, and
  each place fps_unlock writes at that rate holding its bytes.

It exits 1 on a mismatch or a failed guard, or with ``--strict`` on a byte
outside, else 0;
a build it can't read, of neither release or with no vanilla XBE to compare
with is one ``verify-patches:`` line and exit 2. Modkit allowed each swap hook
only where it calls into the room; each swap site is allowed whole here.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import struct
import sys
from collections.abc import Iterator

import numpy as np

from azurkit.core import xbe
from azurkit.tools import mods
from azurkit.tools.mods import PACKS
from azurkit.tools.mods.engine import XBE, PackError, PatchSpec, ParametricPatch, Place, TrampolinePatch
from azurkit.tools.mods.packs import fps_unlock
from devkit.builds import source

NOP = 0x90
SHOWN = 8   # the places or runs listed by address before "... and N more"


def digest(data: bytes) -> str:
    return f"<{len(data)} B, sha256 {hashlib.sha256(data).hexdigest()[:12]}>"


def first_difference(a: bytes, b: bytes) -> int:
    return next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


def span(build: source.Build, place: Place) -> tuple[int, int, int]:
    """``(va, file offset, size)`` of a place at the build's release's own
    address; ``LookupError`` when the release has none."""
    va = place.own(build.facts)
    size = place.size or build.facts.site(va).size
    return va, build.facts.offset(va, size), size


def room(build: source.Build) -> list[tuple[int, int, int, int]]:
    """The shim room the build holds: ``(file offset, size, va, vsize)`` of
    ``.text``'s growth past vanilla's and of an appended ``SHIMS``."""
    old = {s.name: s for s in build.facts.sections}
    out = []
    for s in xbe.sections(build.xbe):
        if s.name == ".text" and s.raw_size > old[".text"].raw_size:   # mapped as the carver maps it: VA = file
            grow = s.raw_size - old[".text"].raw_size                    # offset's distance into .text
            out.append((s.raw + old[".text"].raw_size, grow, s.va + old[".text"].raw_size, grow))
        elif s.name == xbe.SHIMS and s.name not in old:
            out.append((s.raw, s.raw_size, s.va, s.vsize))
    return out


def in_room(build: source.Build, va: int) -> bool:
    return any(lo <= va < lo + n for _, _, lo, n in room(build))


def lands(build: source.Build, at: int, mode: str) -> bool:
    """Whether the 5 bytes at ``at`` are a ``mode`` rel32 into the shim room."""
    code = build.xbe[at:at + 5]
    if len(code) < 5 or code[0] != (0xE8 if mode == "call" else 0xE9):
        return False
    va = next((s.va + at - s.raw for s in xbe.sections(build.xbe) if s.raw <= at < s.raw + s.raw_size), None)
    return va is not None and in_room(build, (va + 5 + int.from_bytes(code[1:], "little", signed=True)) & 0xFFFFFFFF)


def _packs(build: source.Build):
    return [p for p in PACKS.values() if build.release.name in p.releases]


def _sites(build: source.Build, kind) -> Iterator[tuple[str, object, int, int, int]]:
    """``(pack, site, va, offset, size)`` of each ``kind`` site of the packs on the release."""
    for pack in _packs(build):
        for s in pack.sites:
            if isinstance(s, kind) and s.on(build.release.name) and not (isinstance(s, ParametricPatch) and s.virtual):
                try:
                    yield (pack.name, s, *span(build, s))
                except LookupError:
                    continue


def allowed(build: source.Build) -> list[tuple[int, int]]:
    """The file spans a build may change: every pack's sites and footprint
    places, the swap's sites and the shim room."""
    out = [(at, at + n) for _, _, _, at, n in _sites(build, (PatchSpec, ParametricPatch, TrampolinePatch))]
    for pack in _packs(build):
        for place in pack.footprint:
            if place.on(build.release.name):
                try:
                    _, at, n = span(build, place)
                except LookupError:
                    continue
                out.append((at, at + n))
    out += [(build.facts.offset(s.va, s.size), build.facts.offset(s.va, s.size) + s.size)
            for s in build.facts.swap.values()]
    return out + [(at, at + n) for at, n, _, _ in room(build)]


def strays(build: source.Build) -> list[tuple[int, int]]:
    """``(file offset, length)`` of each run of the build's bytes that
    differs from its vanilla XBE with the header state its shim room
    derives, outside :func:`allowed`; a build longer or shorter than that
    is a run at its end."""
    old = {s.name: s for s in build.facts.sections}
    base = xbe.room(build.vanilla)
    claims = []
    for s in xbe.sections(build.xbe):
        if s.name == ".text" and s.raw_size > old[".text"].raw_size:
            claims.append((base.gap, s.raw_size - old[".text"].raw_size, False))
        elif s.name == xbe.SHIMS and s.name not in old:
            claims.append((s.raw, s.raw_size, bool(s.flags & xbe.WRITABLE)))
    try:
        want = xbe.grown(build.vanilla, claims)
    except ValueError:   # a room the allocator couldn't have given: every byte is compared with vanilla's
        want = build.vanilla
    got, n = build.xbe, max(len(want), len(build.xbe))
    bad = np.frombuffer(got.ljust(n, b"\0"), np.uint8) != np.frombuffer(want.ljust(n, b"\0"), np.uint8)
    bad[min(len(got), len(want)):] = True
    for lo, hi in allowed(build):
        bad[lo:hi] = False
    edges = np.flatnonzero(np.diff(np.concatenate(([0], bad.view(np.int8), [0]))))
    return [(int(lo), int(hi - lo)) for lo, hi in zip(edges[::2], edges[1::2])]


def frame_rate(build: source.Build) -> tuple[list[str], bool]:
    """The frame-rate guard (Modkit's safety-critical one, which pinned
    fps_unlock's step cap): the frame rate F the main loop's rate holds,
    and each place fps_unlock writes at F holding its bytes, the step cap
    ceil(F/15) among them; 30 (vanilla's) writes none."""
    _, at, got, was = read_at(build, fps_unlock.RATE, 8)
    rate = struct.unpack("<d", got)[0]
    if got == was:
        return [f"  the main loop runs at {rate:g} fps, vanilla's: fps_unlock writes nothing"], True
    if not (rate.is_integer() and 1 <= rate <= fps_unlock.MAX_FPS):
        return [f"  [FAIL] the main loop's rate holds {rate:g}, no frame rate fps_unlock writes"], False
    try:
        layer = mods.plan(PACKS["fps_unlock"], build.release, {XBE: build.vanilla}, {"target_fps": int(rate)})
    except PackError as exc:
        return [f"  [FAIL] fps_unlock at {rate:g} fps: {exc}"], False
    off = [c.group for c in layer.changes if build.xbe[c.offset:c.offset + len(c.after)] != c.after]
    if not off:
        return [f"  [OK ] fps_unlock at {rate:g} fps: its {len(layer.changes)} places hold its bytes"], True
    return [f"  [FAIL] fps_unlock at {rate:g} fps: {len(off)} of its {len(layer.changes)} places don't hold its "
            "bytes:", *(f"         {group}" for group in off)], False


def read_at(build: source.Build, usa_va: int, size: int) -> tuple[int, int, bytes, bytes]:
    """``(va, offset, the build's bytes, vanilla's)`` of ``size`` bytes at the release's own ``usa_va``."""
    va = build.facts.va(usa_va)
    at = build.facts.offset(va, size)
    return va, at, build.xbe[at:at + size], build.vanilla[at:at + size]


def where(build: source.Build, at: int) -> str:
    for s in xbe.sections(build.xbe):
        if s.raw <= at < s.raw + s.raw_size:
            return f"file 0x{at:06X}  VA 0x{s.va + at - s.raw:08X}  {s.name}"
    return f"file 0x{at:06X}  (the header)" if at < min(s.raw for s in xbe.sections(build.xbe) if s.raw) else \
        f"file 0x{at:06X}  (no section)"


def report(build: source.Build, strict: bool = False) -> tuple[list[str], bool]:
    """The report's lines and whether the build passes."""
    b, v, ok = build.xbe, build.vanilla, True
    lines = [f"Reading patched XBE from {build.path}...", f"  {len(b)} bytes, the {build.release.label} release",
             f"  vanilla: {build.vanilla_from}"]
    if elsewhere := [p.name for p in PACKS.values() if build.release.name not in p.releases]:
        lines.append(f"  Not checked (not available on the {build.release.label} release): {', '.join(elsewhere)}")

    specs = list(_sites(build, PatchSpec))
    counts = dict.fromkeys(("applied", "original", "mismatch", "out-of-range"), 0)
    unapplied, mismatched = [], []
    for pack, spec, va, at, n in specs:
        got, patch = b[at:at + n], spec.placed(build.facts, va)
        status = ("out-of-range" if at + n > len(b) else "applied" if got == patch else
                  "original" if got == v[at:at + n] else "mismatch")
        counts[status] += 1
        if status == "original":
            unapplied.append(f"  VA=0x{va:06X}  {pack}: {spec.label}")
        elif status != "applied":
            mismatched += [f"  [{status}] VA=0x{va:06X}  {pack}: {spec.label}", f"             got:      {digest(got)}"]
            mismatched += [f"             {name + ':':<9s} {digest(want)}, first differing offset "
                           f"{first_difference(got, want):#x}" for name, want in (("original", v[at:at + n]),
                                                                                  ("patch", patch))]
    lines += ["", f"PatchSpec status ({len(specs)} sites):", f"  applied:      {counts['applied']}",
              f"  original:     {counts['original']}  (patch NOT applied)",
              f"  mismatch:     {counts['mismatch']}  (bytes unrecognised)",
              f"  out-of-range: {counts['out-of-range']}"]
    if unapplied:
        lines += ["", "Sites still at original bytes (expected if a pack wasn't requested):", *unapplied]
    if mismatched:
        lines += ["", "*** MISMATCHES: bytes match neither the original nor the patch ***", *mismatched]
        ok = False

    sliders = [(pack.name, s) for pack in _packs(build) for s in pack.sites
               if isinstance(s, ParametricPatch) and s.on(build.release.name)]
    if sliders:
        lines += ["", f"Parametric sliders ({len(sliders)} sites):"]
        for pack, s in sliders:
            if s.virtual:
                lines.append(f"  [virtual ]  {pack}.{s.name}  (no XBE footprint; default {s.default:g} {s.unit})")
                continue
            try:
                va, at, n = span(build, s)
            except LookupError as exc:
                lines.append(f"  [absent  ]  {pack}.{s.name}  ({exc})")
                continue
            value = s.decode(b[at:at + n])
            if b[at:at + n] == v[at:at + n]:
                lines.append(f"  [default ]  {pack}.{s.name}  = {value:g} {s.unit}")
            elif isinstance(value, (int, float)) and math.isfinite(value):
                lines.append(f"  [custom  ]  {pack}.{s.name}  = {value:g} {s.unit}  (default {s.default:g})")
            else:
                lines.append(f"  [mismatch]  {pack}.{s.name}  VA 0x{va:X}: its bytes hold no finite value")
                ok = False

    hooks = list(_sites(build, TrampolinePatch))
    if hooks:
        lines += ["", f"Trampoline sites ({len(hooks)} sites):"]
        for pack, t, va, at, n in hooks:
            status = ("out-of-range" if at + n > len(b) else "original" if b[at:at + n] == v[at:at + n] else
                      "applied" if lands(build, at, t.mode) and set(b[at + 5:at + n]) <= {NOP} else "mismatch")
            lines.append(f"  [{status:<8s}]  {pack}: {t.label}  VA=0x{va:X}  shim={t.symbol}")
            ok = ok and status in ("applied", "original")

    custom = [p for p in _packs(build) if p.custom_apply is not None]
    if custom:
        lines += ["", "Packs that write their own sites (their footprint's places):"]
        for pack in custom:
            places = []
            for place in pack.footprint:
                if place.on(build.release.name):
                    try:
                        places.append(span(build, place))
                    except LookupError:
                        continue
            written = [(va, n) for va, at, n in places if b[at:at + n] != v[at:at + n]]
            shown = ", ".join(f"0x{va:X} ({n} B)" for va, n in written[:SHOWN])
            more = f" ... and {len(written) - SHOWN} more" if len(written) > SHOWN else ""
            lines.append(f"  {pack.name}: {len(written)} of {len(places)} written" + (f": {shown}{more}" if written
                                                                                       else ""))
    if "fps_unlock" in {p.name for p in _packs(build)}:
        guard, passed = frame_rate(build)
        lines += ["", "Frame-rate guard:", *guard]
        ok = ok and passed
    swap = [s for s in build.facts.swap.values()
            if b[(at := build.facts.offset(s.va, s.size)):at + s.size] != v[at:at + s.size]]
    lines += ["", f"Player-model swap sites: {len(swap)} of {len(build.facts.swap)} written"]

    runs = strays(build)
    lines += ["", f"Bytes outside every site, footprint, swap site and the shim room, against {build.vanilla_from}:"]
    if runs:
        lines += [f"  {where(build, at)}: {n} B" for at, n in runs[:SHOWN]]
        if len(runs) > SHOWN:
            lines.append(f"  ... and {len(runs) - SHOWN} more")
        lines.append(f"  {len(runs)} run(s), {sum(n for _, n in runs)} B" + (": a failure (--strict)" if strict else
                                                                             " (--strict fails on them)"))
        ok = ok and not strict
    else:
        lines.append("  none")
    return lines, ok


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m devkit builds verify-patches",
                                description="What each pack's sites hold in a build's default.xbe.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--iso", help="a built image (its default.xbe is read in place)")
    src.add_argument("--xbe", help="a built default.xbe")
    p.add_argument("--original", help="the vanilla image or default.xbe of the build's release (default: the "
                                      "player's image, found as AZURKIT_ISO or AZURKIT_ISO_EUROPE names it)")
    p.add_argument("--strict", action="store_true", help="fail on a byte changed outside every site")
    return p


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        build = source.load(args.iso or args.xbe, args.original)
        lines, ok = report(build, strict=args.strict)
    except (OSError, ValueError) as exc:
        print(f"verify-patches: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0 if ok else 1

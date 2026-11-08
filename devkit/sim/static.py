"""Simulator Level 0: is a build's structure sound?

Modkit's Step 2.5 (behavior test 3; ported in Step 4.13a).  Identity is
not this module's job: a build starts from the vanilla image the identity
gate passed (:mod:`azurkit.core.gate`), and the goldens pin what it
writes.  :func:`check`
looks at what a build wrote, the ``default.xbe`` and the XBRs it
touched (untouched ones are vanilla, so they are not re-read):

- every section's file bytes lie inside the file and within its virtual
  size, and no two sections, or a section and the image headers,
  overlap in memory or in the file;
- the entry point lies in ``.text``, and ``size_of_image`` covers every
  section;
- the kernel thunk table lies in a section and ends in a zero, and each
  entry imports a kernel export by ordinal (1..378);
- the TLS directory, if there is one, lies in a section;
- a touched XBR parses (:class:`azurkit.core.xbr.Document`): its header,
  table of contents and trailer's tables lie inside the file, and each
  keyed table's rows, cells and strings inside its payload, every cell of
  a kind the game reads (empty, double, string).  Modkit's check of every
  self-relative pointer its pointer graph models has no AzurKit home.

Section digests are not checked (Q54, N6): the owner's setup boots
stale digests, and AzurKit recomputes them (Step 4.5).
"""

from __future__ import annotations

import struct
from collections.abc import Mapping

from azurkit.core.xbr import Document
from devkit.sim.ports import parse_kernel_thunks, parse_xbe_sections

ENTRY_KEY_RETAIL = 0xA8FC57AB   # the header's entry point is XOR-ed with it
KERNEL_ORDINALS = range(1, 379)  # xboxkrnl.exe's exports


def check(xbe: bytes, xbrs: Mapping[str, bytes] | None = None) -> list[str]:
    """Every structural problem in a built ``default.xbe`` and the XBRs
    the build touched (``{"config.xbr": bytes}``); empty = sound."""
    return _check_xbe(xbe) + [f"{name}: {problem}" for name, data in (xbrs or {}).items()
                              for problem in _check_xbr(data)]


def _check_xbe(xbe: bytes) -> list[str]:
    try:
        base, secs = parse_xbe_sections(xbe)
    except ValueError as exc:
        return [str(exc)]
    headers, image, entry, tls = struct.unpack_from("<2I24xII", xbe, 0x108)  # 0x108, 0x10C, 0x128, 0x12C
    bad = []
    for s in secs:
        if s["raw_addr"] + s["raw_size"] > len(xbe):
            bad.append(f"{s['name']}: its file bytes run past the end of the file")
        if s["raw_size"] > s["vsize"]:
            bad.append(f"{s['name']}: 0x{s['raw_size']:X} file bytes exceed "
                       f"its virtual size 0x{s['vsize']:X}")
    spans = [{"name": "headers", "vaddr": base, "vsize": headers,
              "raw_addr": 0, "raw_size": headers}] + secs
    for start, size, where in (("vaddr", "vsize", "memory"), ("raw_addr", "raw_size", "the file")):
        spans.sort(key=lambda s: s[start])
        for a, b in zip(spans, spans[1:]):
            if a[size] and a[start] + a[size] > b[start]:
                bad.append(f"{a['name']} overlaps {b['name']} in {where}")
    if max((s["vaddr"] + s["vsize"] for s in secs), default=base) - base > image:
        bad.append(f"size_of_image 0x{image:X} does not cover every section")

    def section(va: int) -> str | None:  # the section whose file bytes hold va
        return next((s["name"] for s in secs
                     if s["vaddr"] <= va < s["vaddr"] + s["raw_size"]), None)

    entry ^= ENTRY_KEY_RETAIL
    if section(entry) != ".text":
        bad.append(f"entry point 0x{entry:X} is not in .text")
    if tls and section(tls) is None:
        bad.append(f"TLS directory 0x{tls:X} is in no section")
    try:
        bad += [f"kernel thunk 0x{t.thunk_va:X} imports ordinal {t.ordinal}, not 1..378"
                for t in parse_kernel_thunks(xbe) if t.ordinal not in KERNEL_ORDINALS]
    except (ValueError, struct.error) as exc:  # in no section, no terminator, past the end
        bad.append(f"kernel thunk table: {exc}")
    return bad


def _check_xbr(data: bytes) -> list[str]:
    try:
        Document(data).tables   # parsed on first read: each keyed table's rows, cells (their kinds) and strings
    except ValueError as exc:   # bad magic; a structure off the file; a cell of another kind
        return [f"does not parse: {exc}"]
    return []

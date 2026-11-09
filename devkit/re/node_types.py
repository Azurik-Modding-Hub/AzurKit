"""``python -m devkit re node-types [--update]``: the node-type names table the package ships,
``node_types.json`` (a copy beside each of its readers, ``src/azurkit/core/xbr/graph.py`` and
``src/azurkit/tools/randomizer/art/nodes.py``), checked against what capstone reads from both releases' vanilla
``default.xbe``, or written (Modkit's ``scripts/gen_node_types.py`` with its ``nodes.scan_types``, ported in Step
4.24c).

Builds read the node types from the table, so none needs capstone. :func:`scan` reads them from the static
initialisers that register them (``graph.py``'s docstring): each type's base type and its attribute names in index
order, no addresses, defaults or other game bytes. The two releases must agree, as the table holds one. It prints
counts and ``sha256[:12]`` only. Exit 0 up to date (or written), 1 a copy differs (``--update`` writes both; read
``git diff`` before committing), 2 no image or an XBE whose registrations aren't where it reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys

from azurkit.core.facts import xbe_layout
from azurkit.core.gate import RELEASES
from azurkit.core.xbe import resolve_va_to_file
from azurkit.core.xbr import graph
from azurkit.tools.randomizer.art import nodes
from devkit.re.xbe import load

COPIES = (graph.NODE_TYPES_FILE, nodes.NODE_TYPES_FILE)


def scan(xbe: bytes) -> dict[str, dict]:
    """The node types ``xbe`` registers, read from its static initialisers with capstone: name -> ``{"parent": its
    base type's name (``None`` for ``node``), "attrs": its attribute names by index, its ancestors' included}``, in
    registration order, at the XBE's own release's addresses. ``ValueError`` when the registrations aren't where
    ``graph.REGISTER_FN`` says (AZ-315)."""
    import capstone

    register = xbe_layout(xbe).va(graph.REGISTER_FN)
    lo, hi = graph.INIT_RANGE
    o = resolve_va_to_file(xbe, lo)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    ins = list(md.disasm(bytes(xbe[o:o + (hi - lo)]), lo))
    found = {}    # name -> (count, descriptor, base descriptor, [(index, name)] of its own chunk)
    for k, i in enumerate(ins):
        if i.mnemonic != "call" or i.op_str != hex(register):
            continue
        regs, chunk = {}, None
        for w in ins[max(0, k - 6):k]:
            dst, _, src = w.op_str.partition(", ")
            if w.mnemonic == "mov" and dst in ("eax", "ecx", "edx", "esi"):
                try:
                    regs[dst] = int(src, 0)
                except ValueError:
                    pass
            elif w.mnemonic == "push" and w.op_str.startswith("0x"):
                chunk = int(w.op_str, 16)
        name = nodes.xbe_cstr(xbe, regs.get("ecx", 0))
        if not name or chunk is None:
            raise ValueError(f"unparsed node-type initialiser at {i.address:#x}")
        own = []      # the chunk: 16-byte {u32 index, char *name, u32 kind, f32 default} up to a NULL name
        while (rec := struct.unpack_from("<II", xbe, resolve_va_to_file(xbe, chunk)))[1]:
            own.append((rec[0], nodes.xbe_cstr(xbe, rec[1])))
            chunk += 16
        # edx is no immediate for `node`: no count, no attributes
        found[name] = (regs.get("edx"), regs["esi"], regs.get("eax", 0), own)
    if len(found) != graph.NODE_TYPES:   # AZ-315: another release's XBE reads 0
        raise ValueError(f"{len(found)} node types registered through {register:#x}, "
                         f"not {graph.NODE_TYPES}: is this a vanilla default.xbe?")
    by_desc = {desc: name for name, (_, desc, _, _) in found.items()}
    out = {}
    for name, (count, _, parent_desc, _) in found.items():
        chain, d = [], name
        while d is not None:
            chain.append(d)
            d = by_desc.get(found[d][2])
            if len(chain) > 16:
                raise ValueError(f"cyclic type chain at {name}")
        names = [None] * (count or 0)
        for c in reversed(chain):
            for idx, nm in found[c][3]:
                if idx >= len(names) or names[idx] is not None:
                    raise ValueError(f"{name}: attribute index {idx} ({nm}) is out of range or doubled")
                names[idx] = nm
        if any(x is None for x in names):
            raise ValueError(f"{name}: attribute indexes leave a gap")
        out[name] = {"parent": by_desc.get(parent_desc), "attrs": names}
    return out


def table(xbes: dict[str, bytes]) -> dict:
    """The table the releases' ``default.xbe`` (``{release name: its bytes}``) give; ``ValueError`` when they
    differ."""
    scans = {name: scan(data) for name, data in xbes.items()}
    first = next(iter(scans.values()))
    if differ := [name for name, types in scans.items() if list(types.items()) != list(first.items())]:
        raise ValueError(f"the releases register different node types ({', '.join(differ)}): "
                         f"node_types.json holds one table")
    return {"releases": sorted(scans), "types": first}


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=1) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit re node-types", description=__doc__.split("\n\n")[0])
    ap.add_argument("--update", action="store_true", help="write both copies of the table")
    args = ap.parse_args(argv)
    try:
        text = dumps(table({r.name: load(region=r.name)[0] for r in RELEASES}))
    except (OSError, ValueError) as exc:
        print(f"node-types: {exc}", file=sys.stderr)
        return 2
    sha = hashlib.sha256(text.encode()).hexdigest()[:12]
    stale = [p for p in COPIES if not p.is_file() or p.read_text(encoding="utf-8") != text]
    if not stale:
        print(f"node_types.json up to date ({sha}, {len(json.loads(text)['types'])} types)")
        return 0
    if args.update:
        for p in stale:
            p.write_text(text, encoding="utf-8")
        print(f"node_types.json written ({sha}): {', '.join(str(p.parent.name) for p in stale)}")
        return 0
    print(f"node_types.json differs from capstone's read (want {sha}) in "
          f"{', '.join(p.parent.name for p in stale)}; run with --update", file=sys.stderr)
    return 1

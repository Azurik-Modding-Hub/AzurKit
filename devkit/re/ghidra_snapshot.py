"""``python -m devkit re ghidra-snapshot PATH``: a live Ghidra's function
and label state, dumped to JSON (Modkit's, ported in Step 4.11d2).

It pulls every function name and symbol / label from a live Ghidra
instance and writes the result to a JSON file the rest of the toolchain
reads offline: ``devkit/re/data/ghidra_snapshot.json``, whose only writer
this verb is (``devkit/re/xbe.py`` names the listings' addresses from it).

## Why

1. **Diff over time** — "did auto-analyze overwrite my nice
   names?" becomes a two-file diff instead of a memory game.
2. **Source of truth under version control** — docs and tests can
   cite specific VA→name mappings in the committed snapshot.

## Scope

The snapshot holds the program info and these top-level lists:

- ``functions``: ``[{"address": "0x00085700", "name": "..."}, ...]``
- ``labels``:    ``[{"address": "...", "name": "...", "namespace": "...",
  "type": "..."}, ...]``
- ``structs``:   the struct layouts ``ghidra-sync --push-structs`` creates,
  i.e. those in Ghidra's root category ``/`` (``include_structs=False``
  skips them)

Names are bare; a label's namespace is its parent namespace's name or
``Global`` (stock Ghydra sends ``ns::name``; see ``ghidra_client``).

Names Ghidra made up itself are EXCLUDED by default, so the snapshot
holds functions, *named* labels and structs (REORG_PLAN §6a.4): the
default ``FUN_`` / ``LAB_`` / ``DAT_`` / ``SUB_`` / ``PTR_`` names,
the switch labels (``switchD``, ``caseD_*``, ``default``,
``switchdataD_*``), string labels (``s_…_<addr>``, ``u_…_<addr>``),
``thunk_FUN_*``, labels named by their bare address, and any of these
with an offcut ``+N`` suffix (``s_ICookie/_001a07dc+1``).  Pass
``include_default_names=True`` to keep them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .ghidra_client import GhidraClient, Refused, connect, require_usa


_AUTO_NAME = re.compile(
    r"(?:(?:thunk_)?(?:FUN|LAB|DAT|SUB|PTR|caseD|switchdataD)_.*"
    r"|[su]_.*_[0-9a-fA-F]{8}|switchD|default|[0-9a-fA-F]{8})"
    r"(?:\+\d+)?")


def is_auto_name(name: str | None) -> bool:
    """A name Ghidra made up itself: no information beyond the address."""
    return not name or _AUTO_NAME.fullmatch(name) is not None


@dataclass
class SnapshotStats:
    """Summary of what :func:`dump_snapshot` actually wrote."""

    total_functions: int = 0
    named_functions: int = 0
    total_labels: int = 0
    named_labels: int = 0
    total_structs: int = 0
    captured_structs: int = 0
    program_name: str = ""


def _format_address(addr: int | str) -> str:
    """Return an ``0xHHHHHHHH`` string; accepts either an int or
    a string (for EXTERNAL-namespaced addresses like
    ``EXTERNAL:00000001``)."""
    if isinstance(addr, int):
        return f"0x{addr:08X}"
    return str(addr)


def dump_snapshot(client: GhidraClient, *,
                  include_default_names: bool = False,
                  include_labels: bool = True,
                  include_structs: bool = True,
                  ) -> tuple[dict, SnapshotStats]:
    """Pull a snapshot off ``client``.

    Parameters
    ----------
    client: GhidraClient
        Live Ghidra instance to query.
    include_default_names: bool
        When ``True``, keep the names Ghidra made up itself
        (``FUN_*``, ``caseD_*``, ``s_…``; see the module docstring).
        Default ``False`` — the snapshot keeps assigned names only.
    include_labels: bool
        When ``True`` (default), page through ``GET /symbols``
        (~45 k rows in Azurik); ``False`` skips the labels.

    Returns a ``(snapshot_dict, stats)`` pair.
    """
    info = client.program_info()
    stats = SnapshotStats(program_name=info.name)

    functions: list[dict] = []
    for fn in client.iter_functions():
        stats.total_functions += 1
        if not include_default_names and is_auto_name(fn.name):
            continue
        stats.named_functions += 1
        functions.append({"address": _format_address(fn.address),
                          "name": fn.name})

    structs: list[dict] = []
    if include_structs:
        # ``ghidra-sync --push-structs`` creates the azurik.h structs in
        # the root category; the rest of the DTM is SDK headers (kernel
        # noise) and stray imports such as the AZ-036 smoke-test debris
        # under /AzurikSmokeTest (deleted from the owner's project by D94's
        # plan, 2026-10-11).
        for summary in client.iter_structs():
            stats.total_structs += 1
            if summary.get("category") != "/":
                continue
            full = client.get_struct(summary["name"])
            structs.append({
                "name": full.name,
                "size": full.size,
                "category": full.category,
                "description": full.description,
                "fields": [
                    {"name": f.name, "type": f.data_type,
                     "offset": f.offset, "length": f.length,
                     **({"comment": f.comment} if f.comment else {})}
                    for f in full.fields
                ],
            })
            stats.captured_structs += 1

    labels: list[dict] = []
    if include_labels:
        for lbl in client.iter_labels():
            stats.total_labels += 1
            if not include_default_names and is_auto_name(lbl.name):
                continue
            stats.named_labels += 1
            labels.append({
                "address": _format_address(lbl.address),
                "name": lbl.name,
                "namespace": lbl.namespace,
                "type": lbl.symbol_type,
            })

    snapshot = {
        "schema": 1,
        "program": {
            "name": info.name,
            "image_base": f"0x{info.image_base:08X}",
        },
        "functions": functions,
        "labels": labels,
        "structs": structs,
    }
    return snapshot, stats


def write_snapshot(path: str | Path, client: GhidraClient, *,
                   include_default_names: bool = False,
                   include_labels: bool = True,
                   include_structs: bool = True,
                   indent: int = 2,
                   before_write: Callable[[], None] | None = None) -> SnapshotStats:
    """Dump a snapshot to ``path``.  Returns the stats struct.
    ``before_write`` runs between the dump and the write; if it raises,
    nothing is written."""
    snapshot, stats = dump_snapshot(
        client,
        include_default_names=include_default_names,
        include_labels=include_labels,
        include_structs=include_structs)
    if before_write is not None:
        before_write()
    Path(path).expanduser().write_text(
        json.dumps(snapshot, indent=indent),
        encoding="utf-8")
    return stats


def main(argv: list[str]) -> int:
    """Write the snapshot. Refuses (exit 2, nothing written) when nothing
    answers on the port, a program that isn't the USA XBE (AZ-326) and a
    ``ghidra-serve`` on the port that is dirty or stale, before the dump and
    again before the write, so an edit made during the dump refuses too
    (Step 2.13c)."""
    from .ghidra_serve import unfit_for_snapshot

    p = argparse.ArgumentParser(
        prog="python -m devkit re ghidra-snapshot",
        description="Pull every function and symbol from a running Ghidra and write them to a JSON snapshot "
                    "(the only writer of devkit/re/data/ghidra_snapshot.json). Names Ghidra made up itself "
                    "(FUN_*, LAB_*, DAT_*, caseD_* and the other switch labels, s_* string labels, ...) are left "
                    "out: the snapshot keeps functions, named labels and structs. A ghidra-serve on the port that "
                    "is dirty or stale is refused.")
    p.add_argument("path", help="the JSON file to write")
    p.add_argument("--port", type=int, default=None, help="Ghidra's port (default 8193)")
    p.add_argument("--keep-default-names", action="store_true",
                   help="keep the names Ghidra made up (FUN_*, caseD_*, s_*, ...; default: drop them)")
    p.add_argument("--no-labels", action="store_true", help="skip the labels (a functions-only snapshot)")
    p.add_argument("--no-structs", action="store_true",
                   help="skip the structs (by default the snapshot keeps those ghidra-sync --push-structs "
                        "creates: Ghidra's root category /)")
    args = p.parse_args(argv)

    def refuse_an_unfit_serve() -> None:
        if why := unfit_for_snapshot(client.port):
            raise Refused(why)

    try:
        client = connect(args.port)
        refuse_an_unfit_serve()
        require_usa(client, "ghidra-snapshot")
        stats = write_snapshot(Path(args.path).expanduser(), client,
                               include_default_names=args.keep_default_names,
                               include_labels=not args.no_labels, include_structs=not args.no_structs,
                               before_write=refuse_an_unfit_serve)
    except Refused as exc:
        print(f"ghidra-snapshot: {exc}", file=sys.stderr)
        return exc.code
    print(f"Snapshot written to {args.path}")
    print(f"  program:         {stats.program_name}")
    print(f"  functions:       {stats.named_functions} named / {stats.total_functions} total")
    print(f"  labels:          {stats.named_labels} named / {stats.total_labels} total")
    if stats.total_structs:
        print(f"  structs:         {stats.captured_structs} captured / {stats.total_structs} total")
    return 0


__all__ = [
    "SnapshotStats",
    "dump_snapshot",
    "is_auto_name",
    "write_snapshot",
]

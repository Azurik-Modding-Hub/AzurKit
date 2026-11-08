"""``python -m devkit re ghidra-query decompile|disasm|xrefs-to VA``:
questions to a ``ghidra-serve`` copy (``AzurikServe:/default.xbe``) only;
any other program on the port refuses before a query (Modkit's Step 2.20g,
ported in Step 4.11d2). It reads only: its client names no target, so it
can't write (AZ-197), and ``disasm`` never prints an instruction's bytes
(D87)."""

from __future__ import annotations

import argparse
import sys

from .ghidra_client import GhidraClientError, Refused, connect, emit
from .ghidra_serve import COPY, SERVE_PORT


def main(argv: list[str]) -> int:
    """Exit 0 answered, 1 the query failed (no function starts at VA), 2
    refused (a bad VA, nothing on the port, or not a serve's copy)."""
    p = argparse.ArgumentParser(
        prog="python -m devkit re ghidra-query",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Asks a ghidra-serve copy of the project (AzurikServe:/default.xbe; any other program on the\n"
            "port refuses before a query) and never writes:\n"
            "  decompile VA   the C text of the function that starts at VA\n"
            "  disasm VA      its instructions (address, mnemonic, operands; never bytes)\n"
            "  xrefs-to VA    every reference to VA, its type and function\n"
            "Exit 0 answered, 1 the query failed (no function starts at VA), 2 refused."),
        epilog=(
            "Examples:\n"
            "  python -m devkit re ghidra-serve start --project '<folder>/Azurik Ghidra.gpr'\n"
            "  python -m devkit re ghidra-query decompile 0x85700\n"
            "  python -m devkit re ghidra-query xrefs-to 0x19C1AC --port 8213"))
    p.add_argument("action", choices=["decompile", "disasm", "xrefs-to"])
    p.add_argument("va", help="the VA (hex 0x... or decimal)")
    p.add_argument("--port", type=int, default=SERVE_PORT, help=f"the serve's port (default {SERVE_PORT})")
    p.add_argument("--json", action="store_true", help="JSON instead of text")
    args = p.parse_args(argv)
    try:
        try:
            va = int(args.va, 0)
        except ValueError:
            raise Refused(f"bad VA {args.va!r}") from None
        client = connect(args.port, timeout=120.0)   # a big decompile
        served, serve = client.program_info().program_id, f"{COPY}:/default.xbe"
        if served != serve:
            raise Refused(f"{client.base_url} serves {served!r}; it reads only a ghidra-serve copy ({serve!r}): "
                          "python -m devkit re ghidra-serve start --port N, then --port N")
        if args.action == "decompile":
            code = client.decompile(va)
            emit({"va": va, "decompilation": code} if args.json else code.rstrip("\n"), args.json)
        elif args.action == "disasm":
            rows = client.disassemble(va)
            emit(rows if args.json else [f"0x{r['address']:08X}  {r['mnemonic']} {r['operands']}".rstrip()
                                         for r in rows], args.json)
        else:
            rows = client.xrefs_to(va)
            emit(rows if args.json else [
                f"0x{r['from']:08X}  {r['type']}" + (f"  in {r['function']}" if r["function"] else "")
                for r in rows] + [f"({len(rows)} found)"], args.json)
    except GhidraClientError as exc:
        print(f"ghidra-query: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"ghidra-query: {exc}", file=sys.stderr)
        return exc.code
    return 0

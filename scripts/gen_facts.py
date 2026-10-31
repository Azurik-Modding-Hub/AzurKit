"""Write AzurKit's facts, ``src/azurkit/core/facts.<release>.json``: their
XBE half from the player's images, the rest as each file holds it.

The XBE half is each release's vanilla ``default.xbe`` as its image holds
it: its sha256, size, base and kernel thunk table's address (Live tells the
release a running xemu booted by it), its section table with each section's
sha256, every patch site's vanilla sha256 (the site's address and size are
the file's), and the slot of each kernel export a shim may use
(:data:`KERNEL`: its ordinal, its convention and argument bytes or that it
is data) in the release's thunk table, read from the image, and the
vanilla sha256 of each span the player-model swap's XBE hooks write
(``swap``'s sites).

Each file holds the rest, edited by hand: a patch site's address and size
(a new one needs only those; this fills in its sha256), the game's functions
a shim may call (each one's address, calling convention and argument bytes),
the swap's hooks (each span's address, size and what writes it, and each
address its shims call by name or are handed, at the release's own
addresses; since Step 4.12c, before it Modkit's facts) and Europe's address
map (each USA address the packs name, at its Europe address, or why it has
none). Hashes, sizes, names and addresses only: facts, not dumps.

    uv run --locked python scripts/gen_facts.py [--check]

Each image is the one the gate finds (``AZURKIT_ISO``, ``AZURKIT_ISO_EUROPE``,
else the user data folder), checked whole against its release's manifest.
``--check`` writes nothing and exits 1 when a file isn't what this derives;
``tests/test_packs.py`` checks the same.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from azurkit.core import facts, gate, iso, xbe

ROOT = Path(__file__).resolve().parent.parent

ABOUT = ("The XBE half (the xbe's sha256, size, base and thunk table, the sections, each site's and each swap "
         "site's sha256 and each kernel slot) is written by scripts/gen_facts.py from the player's image; a site's "
         "address and size, the functions, the swap's sites and refs and Europe's address map are edited by hand. "
         "Hashes, sizes, names and addresses only.")
# The kernel exports AzurKit's shims use: name -> (ordinal, convention, argument bytes), or (ordinal, "data") for
# a variable (read through its slot). Xbox kernel ordinals are the kernel's own export numbers; a shim reaches
# one only through the game's thunk table, slot by slot, which ends at a zero word.
KERNEL = {"KeTickCount": (156, "data", 0), "MmFreeContiguousMemory": (171, "stdcall", 4)}
_hex = "0x{:08X}".format


def vanilla_xbe(release: gate.Release, image: Path) -> bytes:
    """The release's ``default.xbe`` from ``image``, which the gate checks whole."""
    stamp = gate.verify(image, releases=(release,))
    with iso.Reader(stamp.path) as r:
        return r.read("default.xbe")


def thunk_ordinals(data: bytes, table: tuple[xbe.Section, ...], at: int) -> list[int]:
    """The kernel ordinal of each slot of the thunk table at ``at``, up to its zero word."""
    out, offset = [], xbe.offset(table, at, 4)
    while word := struct.unpack_from("<I", data, offset + 4 * len(out))[0]:
        out.append(word & 0x7FFFFFFF)
    return out


def derive(release: gate.Release, data: bytes) -> dict:
    """The facts file of ``release`` with its XBE half from ``data``, its vanilla ``default.xbe``."""
    held = json.loads(facts.path(release).read_text(encoding="utf-8"))
    table = xbe.sections(data)
    base = struct.unpack_from("<I", data, 0x104)[0]
    thunks = struct.unpack_from("<I", data, 0x158)[0] ^ facts.THUNK_KEY
    ordinals = thunk_ordinals(data, table, thunks)

    def site(va: int, size: int) -> str:
        """A site's vanilla sha256: in its section's file bytes, or in the slack past them (USA's ``.text``)."""
        s = max((s for s in table if s.va <= va), key=lambda s: s.va)
        at = s.raw + va - s.va
        return hashlib.sha256(data[at:at + size]).hexdigest()

    out = {
        "_about": ABOUT,
        "release": release.name,
        "xbe": {"base": _hex(base), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                "thunks": _hex(thunks)},
        "sections": [{"name": s.name, "va": _hex(s.va), "vsize": _hex(s.vsize), "raw": _hex(s.raw),
                      "raw_size": _hex(s.raw_size), "flags": _hex(s.flags),
                      "sha256": hashlib.sha256(data[s.raw:s.raw + s.raw_size]).hexdigest()} for s in table],
        "sites": {va: {"size": s["size"], "sha256": site(int(va, 16), s["size"])} for va, s in held["sites"].items()},
        "functions": held["functions"],
        "kernel": {name: {"ordinal": ordinal, "convention": convention, "arg_bytes": arg_bytes}
                   | ({"slot": _hex(thunks + 4 * ordinals.index(ordinal))} if ordinal in ordinals else {})
                   for name, (ordinal, convention, arg_bytes) in KERNEL.items()},
    }
    out["swap"] = {"sites": {va: s | {"sha256": site(int(va, 16), s["size"])} for va, s in held["swap"]["sites"].items()},
                   "refs": held["swap"]["refs"]}
    for key in ("addresses", "absent"):   # Europe's address map
        if key in held:
            out[key] = held[key]
    return out


def text(release: gate.Release, data: bytes) -> str:
    return json.dumps(derive(release, data), indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when a file differs")
    args = ap.parse_args(argv)
    stale = []
    for release in gate.RELEASES:
        if (image := gate.find(release)) is None:
            raise SystemExit(f"gen_facts needs the {release.label} image: {gate.missing(release)}")
        path, want = facts.path(release), text(release, vanilla_xbe(release, image))
        if path.read_text(encoding="utf-8") == want:
            continue
        stale.append(path)
        if not args.check:
            path.write_text(want, encoding="utf-8")
    for path in stale:
        print(f"{'stale' if args.check else 'wrote'}: {path.relative_to(ROOT)}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())

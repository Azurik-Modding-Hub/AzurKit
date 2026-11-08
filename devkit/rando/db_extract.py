"""``python -m devkit rando db-extract --out DIR [--iso IMAGE]``: the randomizer's generated level data, read from
the vanilla image (Modkit's ``rando db-extract``; Step 4.13b).

It writes ``DIR/<level>.json`` for the 22 playable levels and ``training_room``, or nothing (D35): each level's
JSON text as :mod:`azurkit.tools.randomizer.levels`' rules decode it (:func:`extract`), which the randomizer ships as
``src/azurkit/tools/randomizer/data/generated``. Where it writes is checked before the image is read: each file it
writes, not just the folder, goes through :func:`~devkit.rando.ports.require_new_output` (D36), so the vanilla
image's folder is refused as ``--out``. Either release's image gives the same files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from azurkit.tools.randomizer.art import nodes
from azurkit.tools.randomizer.levels import CHARACTER_SLOTS, LEVELS, _Level, extract_level
from devkit.rando.ports import default_region, require_new_output, resolve_vanilla_iso, verify_vanilla_iso


def extract(iso: Path) -> dict[str, str]:
    """level -> the JSON text of its generated data, read from ``iso``, which
    the caller has checked is the vanilla ISO."""
    from devkit.rando.ports import XisoReader, load_all_tables

    with XisoReader(iso) as rd:
        xbe = bytes(rd.read_file("default.xbe"))
        schema = nodes.Schema(xbe)
        on_disc = {p.lower()[len("gamedata/"):-len(".xbr")] for p, e in rd.walk()
                   if not e.is_dir and re.fullmatch(r"gamedata/[^/]+\.xbr", p.lower())}
        cfg = load_all_tables(rd.read_file("gamedata/config.xbr"))
        mg = cfg["magic"]
        combo_of = {}
        for n, cc in mg.entity_index.items():
            for r, rn in enumerate(mg.row_names):
                if rn == "Damage":
                    kind, v = mg.read_cell(cc, r)[:2]
                    if kind != "empty" and v and n != "none":
                        combo_of[v] = n
        items = cfg["critters_item_data"]
        key_codes = {items.get_value(n, "invType")[1]: n for n in items.col_names if n.startswith("key_")}
        chars = _Level("characters", bytes(rd.read_file("gamedata/characters.xbr")), schema)
        char_ctxs = {gi: chars.ctxs[gi] for gi, _ in CHARACTER_SLOTS.values()}
        levels = {lvl: _Level(lvl, bytes(rd.read_file(f"gamedata/{lvl}.xbr")), schema) for lvl in LEVELS}
    # The spot table per level: the playerLocations' +0x1C strings in record order (0x6EB15 copies it to
    # node+0x20, which 0x5FF70 compares).  One graph per level holds playerLocations; in the multi-graph
    # levels (town, w3, training_room) that graph is taken to be the main graph [pd+0xDC], so
    # `arrival_graph_known` is false there.
    spots = {}
    for lvl, lv in levels.items():
        locs = [(c.gid(i), c.g.pstr(c.g.recs[i], 0x1C) or "")
                for c in lv.ctxs for i, t in enumerate(c.g.types) if t == "playerLocation"]
        if len({x.split("/")[1] for x, _ in locs}) > 1:
            raise ValueError(f"{lvl}: playerLocations in more than one graph")
        spots[lvl] = {"graphs": len(lv.ctxs), "locs": locs}
    return {lvl: json.dumps(extract_level(lv, combo_of, key_codes, char_ctxs, spots, on_disc),
                            indent=1, sort_keys=True) + "\n"
            for lvl, lv in levels.items()}


def write_generated(out: Path, texts: dict[str, str]) -> None:
    """Write ``out/<level>.json`` for each level's text, creating ``out``
    when it is missing.  Every file is written into a temporary folder
    inside ``out`` before any target is replaced, so a failed write
    (a full disk, a folder it can't write) leaves ``out``'s files as they
    were (D35)."""
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=out, prefix=".db-extract-"))
    try:
        for lvl, text in texts.items():
            (tmp / f"{lvl}.json").write_text(text, encoding="utf-8", newline="\n")
        for lvl in texts:
            os.replace(tmp / f"{lvl}.json", out / f"{lvl}.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str]) -> int:
    """Write ``--out``'s 23 files, or nothing (D35); 1 with an ``ERROR:`` line naming why."""
    ap = argparse.ArgumentParser(prog="python -m devkit rando db-extract", description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="the folder for <level>.json (created when missing)")
    ap.add_argument("--iso", help="the vanilla image (default: the USA one AZURKIT_ISO or the user data folder "
                                  "names, else Europe's)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    try:
        iso = Path(args.iso) if args.iso else resolve_vanilla_iso(default_region())
        if out.exists() and not out.is_dir():
            raise ValueError(f"--out {out} is not a folder")
        for lvl in LEVELS:
            require_new_output(out / f"{lvl}.json", iso)
        verify_vanilla_iso(iso)
        texts = extract(iso)
        write_generated(out, texts)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{len(texts)} levels written to {out}")
    return 0

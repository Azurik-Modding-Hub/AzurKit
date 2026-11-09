"""The ``azurkit`` command, a thin shell over :mod:`azurkit.sdk`: each verb
turns its flags into the sdk's JSON and prints what comes back.

    azurkit verify [--iso PATH ...]       is each image a release's vanilla one, every file of it?
    azurkit packs                         the packs: on by default or not, the releases, what each does, its sliders
    azurkit build --iso PATH --out PATH [--mods FILE ...] [--pack NAME ...] [--no-pack NAME ...] [--no-defaults]
                  [--pack-param PACK.SLIDER=VALUE ...]
                  [--seed SEED [--settings FILE | --share STRING] | --plan FILE] [--obsidian-cost N]
                  [--spoiler FILE] [--save-settings FILE] [--character JSON]
    azurkit open BUILD                    an AzurKit build's recipe, as a mods file (JSON on stdout)
    azurkit files IMAGE [--extract PATH --out FILE]
                                          an image's files (each size and path), or one of them written to FILE
    azurkit data [--iso PATH [--files | --file FILE] | --input FILE] [TABLE [ENTITY]]
                                          config.xbr's tables (or FILE's), a table's entities, or an entity's cells
    azurkit diff MODS [MODS ...] [--input FILE | --iso PATH]
                                          each edit of mods files (Modkit's too), as a build makes it of config.xbr
    azurkit mod-template TABLE [TABLE ...] [--entity NAME] [--name NAME] [--out FILE]
                                          a mods file of config.xbr's vanilla values, to edit (JSON)
    azurkit entity diff A B [--all] [--json] [--config FILE | --iso PATH]
                                          two config.xbr entities side by side, table by table
    azurkit plan --seed SEED [--settings FILE | --share STRING] [--out FILE]
                                          a randomizer plan file (JSON on stdout, or written to FILE)
    azurkit spoiler PLAN                  a plan file's spoiler
    azurkit content [list | install ID | update ID] [--source URL|DIR]
                                          Azurik-Custom-Content's entries, and Install or Update one
    azurkit content check DIR [--write]   a content repository's manifest and files (--write fills in their sha256)

``build`` applies the packs on by default (D528) and each ``--pack`` with
those it requires, less each ``--no-pack`` and those that require it (D588:
``--no-pack qol_memory_upper64`` leaves out ``qol_memory_upper64_gpu`` too),
printing a line for each it moved (``mods.settle``); ``--no-defaults`` starts
from none (no packs at all is the identity build). ``--mods FILE`` (Q268: a preset, an AzurKit build's manifest or a
share link; what ``open`` prints) adds its xbr operations, and when it has
a packs layer the build starts from its packs in place of those on by
default; several apply in their order (Modkit's ``patch --mod``): their
packs joined, their edits one after another, and a later file's change to
what an earlier one set (a slider, an edit's bytes, the randomizer, the
character) wins and is said, D28's report. ``--pack-param`` sets a slider of a pack it applies, to
any finite number (D23: never clamped). ``--seed`` randomizes the build:
the plan (the seed under the default settings, a settings file's or a share
string's, at the movement tier the build's movement sliders pick) is
written first, the built image is read back against it before anything is
written, and the build prints whether its logic still holds (and why not);
``--plan FILE`` builds that plan file (``plan``'s) exactly, in the seed's
place: it carries its own seed and settings, and one from another database,
edited, or not beatable under its settings is refused by name.
``--spoiler FILE`` and ``--save-settings FILE`` write a randomized build's
spoiler and its settings as a settings file (the app's Save spoiler and Save
settings; Modkit's ``randomize-full``'s), each checked before the build (not
the output, an input or a vanilla image) and written after it, or the image
isn't kept either (D35).
``--obsidian-cost`` sets the obsidian locks' cost (vanilla 10). ``--character``
dresses the player in a species' body (a recipe's character as JSON,
``{"species": "keylord"}`` and any of its options: ``tools.characters``;
a variant by name, a built-in, one of yours (a folder in ``variants`` in
the user data folder, or ``$AZURKIT_VARIANTS``: ``tools.characters.library``)
or one of a recipe file's, ``{"species": "mine", "variant_file": "recipes.json"}``),
its size folded into the walk and roll first (with ``--seed``, the plan's
too, and what the body leaves unmodelled leaves its logic unverified). A mods file
of a randomized build (``open``) replays its seed and share string, and one with a character
wears it (``--character`` in its place). ``plan`` fills the randomizer's
authored levels for the seed under the default settings (D144), a settings
file's (TOML) or a share string's, and ``spoiler`` reads a plan file back.
``files`` lists every file of an image, each with its size, in path order,
and ``--extract`` writes one of them to ``--out`` (never over the image or a
vanilla image, D36). ``data`` reads config.xbr as the Data tab does (the vanilla file AzurKit
ships; no image): its tables by category, a table's entities, or each cell
of an entity by its property's name (a repeated entity, each column).
``--iso`` reads any image's config.xbr instead (a build's too, read-only and
never gated; Modkit's ``list`` and ``dump --iso``), ``--files`` lists every
.xbr of it with how many keyed tables each holds, and ``--file FILE`` reads
that file's tables from it (only config.xbr holds any in a vanilla image);
``--input FILE`` reads a loose .xbr (Modkit's ``--input``). ``diff --input
FILE`` or ``--iso PATH`` and ``entity diff --config FILE`` or ``--iso PATH``
read that config.xbr in the vanilla one's place.
``diff`` previews mods files before a build (Modkit's ``diff``): each edit
numbered, ``~`` a cell or bytes it changes (its vanilla value -> its new
one), ``=`` one that changes nothing, ``?`` a byte edit of a file only a
build reads, and ``ERROR`` one a build refuses, then the counts; exit 1
when any edit would fail the build. ``mod-template`` writes (or prints) a
mods file of the vanilla values of every number cell of the named tables,
or of one entity there (Modkit's mod file, ``_keyed_patches``): edit it,
then build with ``build --mods``; a table without the entity is left out
with a line saying so. ``entity diff`` sets two entities' cells side by
side in each table that holds either: ``~`` a property they hold
differently, ``-`` one only A holds, ``+`` one only B holds (``=`` alike,
with ``--all``), or the rows as JSON.
``content`` lists Azurik-Custom-Content's entries (its source: the hub's,
``--source`` or ``$AZURKIT_CONTENT_SOURCE``, a URL or a folder) and what the
content folder holds of each; ``install`` and ``update`` copy one in, every
file's sha256 checked first (a build reads a variant's files from there);
``check`` checks a clone's ``manifest.json`` and every file it lists, and
``--write`` first fills in each listed file's sha256 and size.
A refusal or failure is one ``azurkit: ...`` line on stderr and exit 1.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from azurkit import __version__, sdk
from azurkit.core import gate
from azurkit.core.xbr import Document
from azurkit.edits import files as replaced
from azurkit.tools.mods import settle


def _verify(args: argparse.Namespace) -> int:
    images, failed = list(args.iso), 0
    if not images:
        for release in gate.RELEASES:
            if (found := gate.find(release)) is None:
                print(f"azurkit: no {release.label} image: {gate.missing(release)}", file=sys.stderr)
                failed = 1
            else:
                images.append(str(found))
    for image in images:
        try:
            checked = sdk.verify(image)
        except (OSError, ValueError) as exc:
            print(f"azurkit: {exc}", file=sys.stderr)
            failed = 1
            continue
        print(f"{image}: the vanilla {checked['label']} image, every file as its manifest has it")
    return failed


def _packs(args: argparse.Namespace) -> int:
    for pack in sdk.catalog()["packs"]:
        params = "".join(f" [{s['name']}={s['default']:g}]" for s in pack["sliders"])
        print(f"{pack['name']:<18} {'on ' if pack['default_on'] else 'off'}  "
              f"{'/'.join(pack['releases'])}  {pack['description']}{params}")
    return 0


def recipe(iso: str, packs: list[str], no_packs: list[str], defaults: bool, params: list[str] = (),
           mods: dict | None = None, randomizer: dict | None = None, community: list[str] = ()) -> dict:
    """``build``'s flags as the sdk's recipe, from ``mods`` (a mods file,
    ``sdk.read_mods``, its character too) when given, with ``randomizer``
    (the randomizer's flags, in place of the mods file's) and each of
    ``community`` (ids, after the mods file's); ``ValueError`` names a pack no pack
    has, one both added and taken away (no flag cancels another), one added
    that needs one taken away, and a ``--pack-param`` that isn't
    ``PACK.SLIDER=NUMBER`` of a pack the build applies (the sdk names a slider
    or value it refuses). Prints what the flags and the mods file moved."""
    catalog = {p["name"]: p for p in sdk.catalog()["packs"]}
    if unknown := sorted({*packs, *no_packs} - catalog.keys()):
        raise ValueError(f"no pack {', '.join(map(repr, unknown))} (the packs: {', '.join(catalog)})")
    if both := sorted(set(packs) & set(no_packs)):
        raise ValueError(f"packs both added and taken away: {', '.join(both)}")
    given = (mods or {}).get("packs")
    start = set(given) if given is not None else {name for name, p in catalog.items() if defaults and p["default_on"]}
    chosen, moved = settle(start, packs, no_packs)
    for line in [*(mods or {}).get("settled", ()), *moved]:
        print(line)
    built = {name: dict((given or {}).get(name, {})) for name in catalog if name in chosen}
    for given in params:
        target, _, value = given.partition("=")
        pack, _, slider = target.partition(".")
        try:
            number = float(value)
        except ValueError:
            number = None
        if not slider or number is None:
            raise ValueError(f"--pack-param {given}: not PACK.SLIDER=NUMBER")
        if pack not in built:
            raise ValueError(f"--pack-param {given}: the build doesn't apply {pack!r} (add --pack {pack})")
        built[pack][slider] = number
    randomizer = randomizer or (mods or {}).get("randomizer")
    pins = [*(mods or {}).get("community", []), *({"id": name} for name in community)]
    return ({"community": pins} if pins else {}) | {"iso": iso, "packs": built} | ({"xbr": mods["xbr"]} if mods and mods.get("xbr") else {}) | (
        {"randomizer": randomizer} if randomizer else {}) | (
        {"character": mods["character"]} if mods and mods.get("character") else {})


def merged(given: list[tuple[str, dict]]) -> tuple[dict, list[str]]:
    """Several mods files (each ``(path, sdk.read_mods'``) as one, applied in
    their order (Modkit's ``patch --mod`` repeated): their packs joined, their
    ``xbr`` operations one after another (a later one's write over an earlier
    one's is the build's conflict, D28), their community packs and replaced
    files joined by id and path, and a later file's slider value, randomizer,
    character, community pin or replaced file in place of an earlier one's,
    each such overwrite a line (D28's report: the later file wins)."""
    out: dict = {}
    said: list[str] = []
    setter: dict[str, str] = {}

    def take(what: str, path: str, old, new) -> None:
        if what in setter and old != new:
            said.append(f"{path}'s {what} replaces {setter[what]}'s: the later mods file wins")
        setter[what] = path

    for path, mods in given:
        for name, params in mods.get("packs", {}).items():
            held = out.setdefault("packs", {}).setdefault(name, {})
            for slider, value in params.items():
                take(f"{name}.{slider}", path, held.get(slider), value)
                held[slider] = value
        if "packs" in mods:
            out.setdefault("packs", {})
        for key in ("settled", "xbr"):
            out[key] = [*out.get(key, []), *mods.get(key, [])]
        for key in ("randomizer", "character"):
            if key in mods:
                take(key, path, out.get(key), mods[key])
                out[key] = mods[key]
        for key, field, what in (("community", "id", "community pack"), ("files", "path", "replaced file")):
            for item in mods.get(key, []):
                held = out.setdefault(key, [])
                old = next((x for x in held if x[field] == item[field]), None)
                take(f"{what} {item[field]}", path, old, item)
                out[key] = [x for x in held if x[field] != item[field]] + [item]
    return {key: value for key, value in out.items() if value or key == "packs"}, said


def _randomizer(args: argparse.Namespace) -> dict | None:
    """The randomizer's flags as the sdk's recipe (``None`` without ``--seed``
    or ``--plan``, whose plan carries its own seed and settings: the sdk
    refuses either beside it)."""
    if args.seed is None and args.plan is None:
        if args.settings or args.share or args.obsidian_cost is not None:
            raise ValueError("--settings, --share and --obsidian-cost randomize the build: give --seed or --plan")
        return None
    given = {"seed": args.seed} if args.seed is not None else {}
    if args.plan is not None:
        try:
            given["plan"] = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"--plan {args.plan}: not a plan file (not JSON: {exc})") from None
    if args.settings:
        given["settings"] = tomllib.loads(Path(args.settings).read_text(encoding="utf-8"))
    elif args.share:
        given["share"] = args.share
    return given | ({"obsidian_cost": args.obsidian_cost} if args.obsidian_cost is not None else {})


def _replacing(flags: list[str], listed: list[dict]) -> tuple[list[dict], dict[str, bytes]]:
    """``--file PATH=FILE``: the recipe's ``files`` (``listed``, a mods file's,
    then each new path's entry) and the bytes each flag picked; ``ValueError``
    names a flag that isn't one, or a file no host reads (a network share, a
    device path: ``edits.files.source``)."""
    picked = {}
    for flag in flags:
        path, sep, file = flag.partition("=")
        if not sep or not path or not file:
            raise ValueError(f"--file {flag}: not PATH=FILE")
        picked[path] = Path(replaced.source(file)).read_bytes()
    known = {entry["path"] for entry in listed}
    return [*listed, *(replaced.entry(path, data) for path, data in picked.items() if path not in known)], picked


def _outputs(args: argparse.Namespace, made: dict) -> dict[str, Path]:
    """``--spoiler`` and ``--save-settings``' files (Modkit's ``randomize-full``'s),
    checked before the build: a randomized build's (``--seed``, ``--plan`` or
    a mods file's randomizer), each in a folder that is there, not a folder,
    the output, an input, a vanilla image or the other's file; ``ValueError``
    names every refusal (D35, D36)."""
    asked = {flag: Path(value) for flag, value in (("--spoiler", args.spoiler), ("--save-settings", args.save_settings))
             if value is not None}
    if not asked:
        return {}
    if "randomizer" not in made:
        raise ValueError(f"{' and '.join(asked)}: a randomized build's files: give --seed or --plan")
    inputs = [("the image it writes (--out)", args.out), ("the image it reads (--iso)", args.iso),
              ("the plan file it reads (--plan)", args.plan),
              ("the settings file it reads (--settings)", args.settings),
              *(("a mods file it reads (--mods)", path) for path in args.mods),
              *(("a file it reads (--file)", flag.partition("=")[2]) for flag in args.file),
              *((f"the vanilla {r.label} image", found) for r in gate.RELEASES if (found := gate.find(r)))]

    def same(a: Path, b: Path) -> bool:
        return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))
    failed = []
    for flag, path in asked.items():
        if path.is_dir():
            failed.append(f"{flag} {path}: a folder, not a file")
        elif not path.resolve().parent.is_dir():
            failed.append(f"{flag} {path}: no folder {path.resolve().parent}")
        failed += [f"{flag} {path}: it is {what}" for what, given in inputs if given and same(path, Path(given))]
    if len(asked) == 2 and same(*asked.values()):
        failed.append(f"--spoiler and --save-settings name the same file ({args.spoiler})")
    if failed:
        raise ValueError("; ".join(failed))
    return asked


def _write_outputs(outputs: dict[str, Path], built: dict) -> None:
    """The build's spoiler and its settings file (the app's ``spoiler`` and
    ``settings_file``: ``tools.randomizer.settings_file``) to ``outputs``,
    each a part file renamed into place, all or none."""
    from azurkit.tools import randomizer

    settings = built["randomizer"]["settings"]
    texts = {flag: built["spoiler"] if flag == "--spoiler" else randomizer.settings_file(settings) for flag in outputs}
    parts, placed = [], []
    try:
        for flag, path in outputs.items():
            parts.append(part := path.with_name(f"{path.name}.part"))
            part.write_bytes(texts[flag].encode("utf-8"))
        for part, path in zip(parts, outputs.values()):
            part.replace(path)
            placed.append(path)
    except BaseException:
        for path in placed:
            path.unlink(missing_ok=True)
        raise
    finally:
        for part in parts:
            part.unlink(missing_ok=True)


def _build(args: argparse.Namespace) -> int:
    try:
        files = []
        for path in args.mods:
            try:
                files.append((path, sdk.read_mods(Path(path).read_bytes())))
            except ValueError as exc:
                raise ValueError(f"{path}: {exc}" if len(args.mods) > 1 else str(exc)) from None
        given, replaced_by = merged(files) if files else (None, [])
        if len(files) > 1:   # the data edits' numbers each file's are, as a conflict names them
            n = 0
            for path, mods in files:
                if k := len(mods.get("xbr", [])):
                    print(f"mods {path}: data edits #{n + 1}-#{n + k}" if k > 1 else f"mods {path}: data edit #{n + 1}")
                n += k
        made = recipe(args.iso, args.pack, args.no_pack, not args.no_defaults, args.pack_param, given,
                      _randomizer(args), args.community)
        entries, picked = _replacing(args.file, (given or {}).get("files", []))
        outputs = _outputs(args, made)
        built = sdk.build(made | ({"character": json.loads(args.character)} if args.character else {})
                          | ({"files": entries} if entries else {}), args.out, picked=picked)
        try:
            _write_outputs(outputs, built)
        except (OSError, ValueError):
            Path(built["out"]).unlink(missing_ok=True)   # D35: a spoiler or settings file not written keeps no image
            raise
    except (OSError, ValueError) as exc:    # tomllib.TOMLDecodeError is a ValueError
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    for layer in built["layers"]:
        print(f"{layer['id']}: {layer['sites']} sites, {layer['bytes']} B")
    for conflict in [*built["conflicts"], *replaced_by]:
        print(f"conflict: {conflict}")
    if (plan := built.get("randomizer")) is not None:
        print(f"randomizer: seed {plan['seed']!r}, share {plan['share']}, plan {plan['plan'][:12]}; the image "
              f"holds the plan; logic_verified: {str(plan['logic_verified']).lower()}")
        for line in plan["conflicts"] + plan["why_not"]:
            print(f"  {line}")
    print(f"{Path(built['out'])}: {built['label']}, {built['size']:,} B, sha256 {built['sha256']}")
    for flag, path in outputs.items():
        print(f"{'spoiler' if flag == '--spoiler' else 'settings file'}: {path}")
    return 0


def _open(args: argparse.Namespace) -> int:
    try:
        found = sdk.open_build(args.build)
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(found, indent=1, sort_keys=True))
    return 0


def _files(args: argparse.Namespace) -> int:
    try:
        if (args.extract is None) != (args.out is None):
            raise ValueError("files: --extract PATH and --out FILE go together")
        if args.extract is not None:
            done = sdk.extract(args.image, args.extract, args.out)
            print(f"{args.extract}: {done['size']:,} B written to {done['out']} (sha256 {done['sha256'][:12]})")
            return 0
        listed = sdk.files(args.image)["files"]
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    for path, _, size in listed:
        print(f"{size:>13,}  {path}")
    return 0


def _xbr_file(path: str, flag: str) -> bytes:
    """The .xbr file ``flag`` names, read whole; ``ValueError`` names one that isn't an XBR."""
    data = Path(replaced.source(path)).read_bytes()
    if data[:4] != b"xobx":
        raise ValueError(f"{flag} {path}: not an XBR file (no xobx header)")
    return data


def _config(given: str | None, image: str | None, flag: str) -> bytes | None:
    """The config.xbr ``diff`` and ``entity diff`` read in place of the vanilla
    one AzurKit ships (Modkit's ``--input``, ``--config`` and ``--iso``): the
    file ``flag`` names, else ``image``'s, any image's (a build's too),
    read-only; ``None`` with neither."""
    from azurkit.tools import data as datatool

    if given is not None:
        return _xbr_file(given, flag)
    if image is None:
        return None
    if (data := datatool.image_file(replaced.source(image), datatool.FILE)) is None:
        raise ValueError(f"{image}: its {datatool.FILE} holds no keyed table")
    return data


def _data(args: argparse.Namespace) -> int:
    from azurkit.tools import data as datatool

    try:
        if args.input is not None and (args.iso or args.files or args.file):
            raise ValueError("data: --input reads one .xbr file: give no --iso, --files or --file")
        if args.files:
            if args.file or args.table:
                raise ValueError("data: --files lists the image's files: give no --file or TABLE")
            if args.iso is None:
                raise ValueError("data: --files lists an image's files: give --iso")
            for f in datatool.image_files(replaced.source(args.iso)):
                n = len(f["tables"])
                print(f"{n:>3} keyed table{' ' if n == 1 else 's'}  {f['file']}")
            return 0
        file = args.file or datatool.FILE
        if args.input is not None or args.iso is not None:   # a file's, or any image's: read-only, never gated
            where = args.input if args.input is not None else file
            data = (_xbr_file(args.input, "--input") if args.input is not None
                    else datatool.image_file(replaced.source(args.iso), file))
            tables = Document(data).tables if data is not None else {}
            if args.table is None:
                print("\n".join(f"{name:<26} {len(t.cols):>4} x {len(t.rows)}" for name, t in tables.items())
                      or "(no keyed tables)")
                return 0
            if args.table not in tables:
                raise ValueError(f"{where} has no keyed table {args.table!r}")
            t = tables[args.table]
            grid = {"cols": list(t.cols), "rows": list(t.rows),
                    "cells": [[t.cell(c, r).value for r in range(len(t.rows))] for c in range(len(t.cols))]}
        else:   # the vanilla config.xbr AzurKit ships
            if file != datatool.FILE:
                raise ValueError(f"data: --file {file} is an image's: give --iso")
            where = "config"
            if args.table is None and args.file:
                listed = sdk.data({"what": "tables"})["tables"]
                print("\n".join(f"{t['name']:<26} {t['cols']:>4} x {t['rows']}" for t in listed))
                return 0
            if args.table is None:
                for t in sdk.data({"what": "index"})["tables"]:
                    print(f"{t['category']:<9} {t['name']:<26} {t['cols']:>4} x {t['rows']:<4} {t['label']}")
                return 0
            grid = sdk.data({"what": "table", "table": args.table})
        cols = [c for c, name in enumerate(grid["cols"]) if args.entity in (None, name)]
        if args.entity is not None and not cols:
            raise ValueError(f"{where} table {args.table} has no entity {args.entity!r}")
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    if args.entity is None:
        print("\n".join(name or "(no name)" for name in grid["cols"]))
        return 0
    for c in cols:
        if len(cols) > 1:
            print(f"{args.entity} (column {c})")
        for r, prop in enumerate(grid["rows"][1:], 1):
            value = grid["cells"][c][r]
            print(f"{prop or '(no name)'}: {'(empty)' if value is None else json.dumps(value)}")
    return 0


def _diff(args: argparse.Namespace) -> int:
    tally, n = {"changed": 0, "errors": 0, "unchanged": 0}, 0
    try:
        config = _config(args.input, args.iso, "--input")
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    for path in args.mods:
        try:
            found = sdk.mods_diff({"text": Path(path).read_text(encoding="utf-8")}
                                  | ({"config": config} if config is not None else {}))
        except (OSError, ValueError) as exc:     # json.JSONDecodeError is a ValueError
            print(f"azurkit: {path}: {exc}", file=sys.stderr)
            return 1
        print(f"{path}" + (f": {found['name']}" if found.get("name") else ""))
        if found.get("description"):
            print(f"  {found['description']}")
        for row in found["edits"]:
            n += 1
            if "refused" in row:
                tally["errors"] += 1
                print(f"  [{n}] ERROR {row['edit']}: {row['refused']}")
                continue
            tally["changed" if row["changed"] else "unchanged"] += 1
            what = row.get("what", row["edit"])
            if "vanilla" in row:
                print(f"  [{n}] {'~' if row['changed'] else '='} {what}: {row['vanilla']} -> {row['value']}")
            elif row.get("checked") is False:
                print(f"  [{n}] ? {what}: a build checks it, on your image")
            else:
                print(f"  [{n}] {'~' if row['changed'] else '='} {what}"
                      + (f" ({row['size']} B)" if "size" in row else ": nothing to do"))
    print(f"{tally['changed']} changed, {tally['errors']} errors, {tally['unchanged']} unchanged")
    return 1 if tally["errors"] else 0


def _template(args: argparse.Namespace) -> int:
    try:
        made = sdk.mod_template({"tables": args.tables, "name": args.name}
                                | ({"entity": args.entity} if args.entity is not None else {}))
        for table in made["left_out"]:
            print(f"azurkit: {table} has no number cell of {args.entity!r}: left out", file=sys.stderr)
        if args.out is None:
            sys.stdout.write(made["text"])
            return 0
        Path(args.out).write_text(made["text"], encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    print(f"{args.out}: {made['cells']} values of {made['entities']} entities in {made['tables']} tables; edit them, "
          f"then: azurkit build --iso PATH --out PATH --mods {args.out}")
    return 0


def _entity(args: argparse.Namespace) -> int:
    try:
        config = _config(args.config, args.iso, "--config")
        found = sdk.entity_diff({"a": args.a, "b": args.b, "all": args.all}
                                | ({"config": config} if config is not None else {}))
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(found, indent=1))
        return 0
    tables = list(dict.fromkeys(row["table"] for row in found["rows"]))
    print(f"{args.a!r} vs {args.b!r}: {len(tables)} tables with differences ({len(found['rows'])} rows)")
    for key, who in (("only_in_a", args.a), ("only_in_b", args.b)):
        if found[key]:
            print(f"  tables only {who!r} is in: {', '.join(found[key])}")
    marks = {"different": "~", "a_only": "-", "b_only": "+", "equal": "="}
    for table in sorted(tables):
        print(f"\n[{table}]")
        for row in (r for r in found["rows"] if r["table"] == table):
            a, b = (f"{row[f'{x}_type']} {json.dumps(row[f'{x}_value'])}" for x in "ab")
            print(f"  {marks[row['kind']]} {row['property']:<28}  "
                  + {"different": f"A {a:<20}  B {b}", "a_only": f"A {a:<20}  (B has none)",
                     "b_only": f"{'(A has none)':<22}  B {b}", "equal": a}[row["kind"]])
    return 0


def _plan(args: argparse.Namespace) -> int:
    try:
        given = {"seed": args.seed}
        if args.settings:
            given["settings"] = tomllib.loads(Path(args.settings).read_text(encoding="utf-8"))
        elif args.share:
            given["share"] = args.share
        doc = sdk.plan(given)
    except (OSError, ValueError) as exc:     # tomllib.TOMLDecodeError is a ValueError
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"    # Modkit's plan file, byte for byte
    if args.out is None:
        sys.stdout.write(text)
        return 0
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"plan {doc['sha256'][:12]} written to {args.out}: {len(doc['placement'])} locations "
          f"(attempt {doc['attempt']}, share {doc['share']})")
    return 0


def _spoiler(args: argparse.Namespace) -> int:
    try:
        lines = sdk.spoiler(json.loads(Path(args.plan).read_text(encoding="utf-8")))["lines"]
    except (OSError, ValueError) as exc:     # json.JSONDecodeError is a ValueError
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


def _save(args: argparse.Namespace) -> int:
    from azurkit.tools import saves

    try:
        target = Path(replaced.source(args.target))
        slots = [saves.Slot.read(target)] if target.is_dir() else saves.slots(target)
        if args.action == "inspect":
            if not slots:
                print(f"{target}: no Azurik save")
            for slot in slots:
                print(f"{slot.id}: {len(slot.files)} files, {len(slot.folders)} folders")
                for file in saves.decode(slot):
                    print(f"  {file['path']}: {file['kind']}, {file['size']:,} B"
                          + "".join(f"\n    {n} {line}" for n, line in enumerate(file.get("lines", []))))
            return 0
        if not args.out or not args.flash or not args.iso:
            raise ValueError("save edit: give --out, --flash and --iso: an edited save is signed again for your console")
        slot = next((s for s in slots if s.id == args.slot), None) if args.slot else slots[0] if len(slots) == 1 else None
        if slot is None:
            raise ValueError(f"save edit: name a slot with --slot (there: {', '.join(s.id for s in slots)})")
        sdk.saves({"do": "open", "id": slot.id, "files": slot.files, "folders": list(slot.folders)})
        for given in args.set:
            file, _, rest = given.partition(":")
            line, sep, value = rest.partition("=")
            if not sep or not line.isdecimal():
                raise ValueError(f"--set {given}: not FILE:LINE=VALUE")
            sdk.saves({"do": "edit", "id": slot.id, "edits": [{"file": file, "line": int(line), "value": value}]})
        sdk.saves({"do": "sign", "id": slot.id, "iso": args.iso, "flash": Path(replaced.source(args.flash)).read_bytes(),
                   "mcpx": Path(replaced.source(args.mcpx)).read_bytes() if args.mcpx else None})
        print(sdk.saves({"do": "save", "id": slot.id, "out": args.out})["out"])
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    return 0


def _content(args: argparse.Namespace) -> int:
    from azurkit.tools.characters import content

    try:
        if args.action == "check":
            folder = Path(args.target or ".")
            raw = json.loads((folder / content.MANIFEST).read_text(encoding="utf-8"))
            manifest = content.filled(raw, lambda path: (folder / path).read_bytes()) if args.write else content.check(raw)
            for entry in manifest["entries"]:
                content.verify(manifest, entry["id"], {f["path"]: (folder / f["path"]).read_bytes()
                                                       for e in manifest["entries"] for f in e["files"]},
                               sdk.content_refusal)
            if args.write:
                (folder / content.MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
            print(f"{folder / content.MANIFEST}: {len(manifest['entries'])} entries, every file as it lists it"
                  + (" (written)" if args.write else ""))
            return 0
        if args.action in ("install", "update"):
            if not args.target:
                raise ValueError(f"content {args.action}: name the entry")
            view = sdk.content_install({"id": args.target, "source": args.source})
        else:
            view = sdk.content({"source": args.source})
    except (OSError, ValueError) as exc:     # json.JSONDecodeError is a ValueError
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    if view["why"]:
        print(f"azurkit: {view['why']}", file=sys.stderr)
    for e in view["entries"]:
        state = {"install": "not installed", "installed": f"installed v{e['installed']}",
                 "update": f"installed v{e['installed']}, update to v{e['version']}"}[e["state"]]
        print(f"{e['id']:<18} {e['kind']:<8} {state:<28} {e['title']} ({e['author']}, {e['licence']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="azurkit", description="Mods for Azurik: Rise of Perathia.")
    parser.add_argument("--version", action="version", version=f"azurkit {__version__}")
    verbs = parser.add_subparsers(dest="verb")
    verify = verbs.add_parser("verify", help="check that each image is a release's vanilla image, every file of it",
                              description="Check each --iso image, else each release's own (AZURKIT_ISO, "
                                          "AZURKIT_ISO_EUROPE, else the user data folder's usa.iso and europe.iso), "
                                          "against that release's manifest, and name the first file that differs.")
    verify.add_argument("--iso", action="append", default=[], metavar="PATH", help="an image to check (repeatable)")
    verify.set_defaults(run=_verify)
    packs = verbs.add_parser("packs", help="list the packs", description="List the packs in the order a build "
                             "applies them: on by default or off, the releases each supports, what it does, and "
                             "its parameters with their defaults.")
    packs.set_defaults(run=_packs)
    build = verbs.add_parser("build", help="build an image with packs",
                             description="Check that --iso is a vanilla image (the files a build reads), apply the "
                                         "packs on by default and each --pack, less each --no-pack, and write the "
                                         "image to --out. Nothing is written if any pack fails.")
    build.add_argument("--iso", required=True, metavar="PATH", help="the vanilla image")
    build.add_argument("--mods", action="append", default=[], metavar="FILE",
                       help="a mods file: a preset, an AzurKit build's manifest or a share link (azurkit open prints "
                            "one); its packs, when it has them, replace those on by default (repeatable: applied in "
                            "order, a later file's change to what an earlier one set wins and is said)")
    build.add_argument("--out", required=True, metavar="PATH", help="where to write the build (never the input)")
    build.add_argument("--pack", action="append", default=[], metavar="NAME", help="a pack to apply (repeatable)")
    build.add_argument("--no-pack", action="append", default=[], metavar="NAME",
                       help="a pack on by default to leave out (repeatable)")
    build.add_argument("--no-defaults", action="store_true", help="leave out every pack on by default")
    build.add_argument("--pack-param", action="append", default=[], metavar="PACK.SLIDER=VALUE",
                       help="set a slider of a pack the build applies: any finite number, never clamped "
                            "(repeatable; azurkit packs lists them)")
    build.add_argument("--seed", help="randomize the build: the plan of this seed (any string), written first")
    settled = build.add_mutually_exclusive_group()
    settled.add_argument("--settings", metavar="FILE", help="the randomizer's settings as a settings file (TOML)")
    settled.add_argument("--share", metavar="STRING", help="the randomizer's settings as a share string (AZR-...)")
    build.add_argument("--plan", metavar="FILE", help="randomize the build with this plan file (azurkit plan's), "
                       "exactly: it carries its own seed and settings")
    build.add_argument("--spoiler", metavar="FILE", help="write the randomized build's spoiler here: its settings, "
                       "spheres and each progression item's paths")
    build.add_argument("--save-settings", metavar="FILE", help="write the randomized build's settings here, as a "
                       "settings file (--settings loads it back)")
    build.add_argument("--obsidian-cost", type=float, metavar="N",
                       help="the obsidian each lock costs (vanilla 10; any number, never clamped)")
    build.add_argument("--character", metavar="JSON", help='dress the player in a species\' body: a recipe\'s '
                       'character, e.g. \'{"species": "keylord", "mode": "garret4"}\'')
    build.add_argument("--community", action="append", default=[], metavar="ID",
                       help="a community pack installed with `azurkit content install` (repeatable): its packs and "
                            "game-data edits join the build")
    build.add_argument("--file", action="append", default=[], metavar="PATH=FILE",
                       help="replace the image's file PATH with your FILE, whole, after every other change (repeatable; "
                            "not default.xbe or filelist.txt; a mods file names one and needs this flag to build)")
    build.set_defaults(run=_build)
    opened = verbs.add_parser("open", help="print an AzurKit build's recipe as a mods file",
                              description="Read BUILD's /azurkit.json, check every file of the image against it, "
                                          "and print its recipe as a mods file (JSON), which build --mods takes.")
    opened.add_argument("build", metavar="BUILD", help="an image AzurKit built")
    opened.set_defaults(run=_open)
    listed = verbs.add_parser("files", help="list an image's files, or write one of them to a file",
                              description="List every file of IMAGE in path order, each with its size, or with "
                                          "--extract write that file of it to --out (never over IMAGE or a vanilla "
                                          "image).")
    listed.add_argument("image", metavar="IMAGE", help="a disc image (vanilla, an AzurKit build or another)")
    listed.add_argument("--extract", metavar="PATH", help="the image's file to write, as the list names it")
    listed.add_argument("--out", metavar="FILE", help="where --extract writes it (a part file renamed into place)")
    listed.set_defaults(run=_files)
    read = verbs.add_parser("data", help="read config.xbr's tables (or any .xbr's), as the Data tab shows them",
                            description="List config.xbr's tables by category (each entities x properties), "
                                        "TABLE's entities, or each cell of ENTITY in TABLE by its property's name. "
                                        "It reads the vanilla config.xbr AzurKit ships (both releases hold it), or "
                                        "read-only the config.xbr of the image at --iso (any image: a build's too) "
                                        "or the .xbr file at --input; --files lists every .xbr of the image with its "
                                        "keyed tables, and --file reads one's from the image (All files).")
    read.add_argument("table", nargs="?", metavar="TABLE", help="a table (azurkit data lists them)")
    read.add_argument("entity", nargs="?", metavar="ENTITY", help="an entity of TABLE (a column)")
    source = read.add_mutually_exclusive_group()
    source.add_argument("--iso", metavar="PATH", help="an image (vanilla, a build or another) whose config.xbr (or "
                        "--file) to read, read-only")
    source.add_argument("--input", metavar="FILE", help="an .xbr file to read (a config.xbr of any image, or "
                        "another), read-only")
    read.add_argument("--files", action="store_true", help="every .xbr of the image and how many keyed tables each holds")
    read.add_argument("--file", metavar="FILE", help="an .xbr of the image, as --files names it (default config.xbr)")
    read.set_defaults(run=_data)
    diffed = verbs.add_parser("diff", help="preview what mods files change, before a build",
                              description="Read each mods file (a preset, a build's mods file, a share link or one "
                                          "of Modkit's mod files) and print each of its edits as a build makes it of "
                                          "the vanilla config.xbr (or --input's, or --iso's image's): ~ changed (its "
                                          "value -> new), = unchanged, ? a byte "
                                          "edit of a file only a build reads, ERROR one a build refuses; exit 1 "
                                          "if any would fail the build.")
    diffed.add_argument("mods", nargs="+", metavar="MODS", help="a mods file")
    against = diffed.add_mutually_exclusive_group()
    against.add_argument("--input", metavar="FILE", help="a config.xbr file to diff against, in vanilla's place")
    against.add_argument("--iso", metavar="PATH", help="an image (a build or another) whose config.xbr to diff "
                         "against, in vanilla's place")
    diffed.set_defaults(run=_diff)
    templated = verbs.add_parser("mod-template", help="write a mods file of config.xbr's vanilla values to edit",
                                 description="Write (or print) a mods file holding the vanilla value of every number "
                                             "cell of each TABLE (or of --entity there), by config.xbr's own names, "
                                             "as Modkit's mod files hold them (_keyed_patches): edit the values, then "
                                             "build with build --mods. It reads the config.xbr AzurKit ships.")
    templated.add_argument("tables", nargs="+", metavar="TABLE", help="a table (azurkit data lists them)")
    templated.add_argument("--entity", metavar="NAME", help="only this entity (a table without it is left out)")
    templated.add_argument("--name", default="my-mod", help="the mod's name (default: my-mod)")
    templated.add_argument("--out", metavar="FILE", help="write it here (default: print it)")
    templated.set_defaults(run=_template)
    entity = verbs.add_parser("entity", help="compare two config.xbr entities",
                              description="Compare two config.xbr entities (each its column, by its exact name).")
    compared = entity.add_subparsers(dest="action", required=True).add_parser(
        "diff", help="two entities side by side", description="Set two entities' cells side by side in each table "
                                                              "that holds either: what they hold differently, what "
                                                              "only one holds, and the tables only one is in. It "
                                                              "reads the config.xbr AzurKit ships, or --config's or "
                                                              "--iso's image's.")
    compared.add_argument("a", metavar="A", help="an entity (azurkit data TABLE lists a table's)")
    compared.add_argument("b", metavar="B", help="another entity")
    compared.add_argument("--all", action="store_true", help="the properties they hold alike too")
    compared.add_argument("--json", action="store_true", help="the rows as JSON")
    held = compared.add_mutually_exclusive_group()
    held.add_argument("--config", metavar="FILE", help="a config.xbr file to read, in the shipped one's place")
    held.add_argument("--iso", metavar="PATH", help="an image (a build or another) whose config.xbr to read")
    compared.set_defaults(run=_entity)
    planned = verbs.add_parser("plan", help="fill the randomizer for a seed and print (or write) the plan file",
                               description="Fill the randomizer's authored levels for --seed under the default "
                                           "settings (D144), a settings file's or a share string's, and print the "
                                           "plan file (JSON), or write it to --out. The same seed and settings "
                                           "give the same plan.")
    planned.add_argument("--seed", required=True, help="the seed: any string")
    given = planned.add_mutually_exclusive_group()
    given.add_argument("--settings", metavar="FILE", help="the settings as a settings file (TOML)")
    given.add_argument("--share", metavar="STRING", help="the settings as a share string (AZR-...)")
    planned.add_argument("--out", metavar="FILE", help="write the plan file here (default: print it)")
    planned.set_defaults(run=_plan)
    spoiled = verbs.add_parser("spoiler", help="print a plan file's spoiler",
                               description="Print PLAN's settings, its spheres with each progression item's "
                                           "obtain and return paths, the traps and the rest.")
    spoiled.add_argument("plan", metavar="PLAN", help="a plan file (azurkit plan --out)")
    spoiled.set_defaults(run=_spoiler)
    saved = verbs.add_parser("save", help="read an Azurik save slot, or edit one and sign it again",
                             description="inspect: what a slot's folder or an xemu HDD image's slots hold (read-only). "
                                         "edit: change a text save's lines (--set), sign the slot again with your own "
                                         "BIOS files (read in memory, never kept) and write it to --out, a new folder.")
    saved.add_argument("action", choices=("inspect", "edit"))
    saved.add_argument("target", metavar="FOLDER|HDD", help="a slot's folder, or an xemu HDD image")
    saved.add_argument("--slot", metavar="ID", help="edit: which slot of an HDD image")
    saved.add_argument("--set", action="append", default=[], metavar="FILE:LINE=VALUE", help="edit: a line (repeatable)")
    saved.add_argument("--flash", metavar="PATH", help="edit: your flash image")
    saved.add_argument("--mcpx", metavar="PATH", help="edit: your MCPX boot ROM")
    saved.add_argument("--iso", metavar="PATH", help="edit: your game image (the game's key is in its XBE)")
    saved.add_argument("--out", metavar="DIR", help="edit: a new folder to write the slot to")
    saved.set_defaults(run=_save)
    contented = verbs.add_parser("content", help="list, install or update Azurik-Custom-Content's entries",
                                 description="List Azurik-Custom-Content's entries (from --source, else "
                                             "$AZURKIT_CONTENT_SOURCE, else the hub's) and what the content folder "
                                             "holds of each; install or update one, every file's sha256 checked "
                                             "before anything is written; or check a content repository's "
                                             "manifest and files.")
    contented.add_argument("action", nargs="?", default="list", choices=("list", "install", "update", "check"))
    contented.add_argument("target", nargs="?", metavar="ID|DIR", help="the entry to install or update; check's folder")
    contented.add_argument("--source", metavar="URL|DIR", help="where Azurik-Custom-Content is read from")
    contented.add_argument("--write", action="store_true", help="check: fill in each listed file's sha256 and size")
    contented.set_defaults(run=_content)
    args = parser.parse_args(argv)
    if args.verb is None:
        parser.print_help()
        return 0
    return args.run(args)

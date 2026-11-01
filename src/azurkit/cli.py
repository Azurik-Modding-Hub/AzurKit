"""The ``azurkit`` command, a thin shell over :mod:`azurkit.sdk`: each verb
turns its flags into the sdk's JSON and prints what comes back.

    azurkit verify [--iso PATH ...]       is each image a release's vanilla one, every file of it?
    azurkit packs                         the packs: on by default or not, the releases, what each does, its sliders
    azurkit build --iso PATH --out PATH [--mods FILE] [--pack NAME ...] [--no-pack NAME ...] [--no-defaults]
                  [--pack-param PACK.SLIDER=VALUE ...]
                  [--seed SEED [--settings FILE | --share STRING] [--obsidian-cost N]] [--character JSON]
    azurkit open BUILD                    an AzurKit build's recipe, as a mods file (JSON on stdout)
    azurkit files IMAGE [--extract PATH --out FILE]
                                          an image's files (each size and path), or one of them written to FILE
    azurkit data [TABLE [ENTITY]]         config.xbr's tables, a table's entities, or an entity's cells
    azurkit plan --seed SEED [--settings FILE | --share STRING] [--out FILE]
                                          a randomizer plan file (JSON on stdout, or written to FILE)
    azurkit spoiler PLAN                  a plan file's spoiler
    azurkit content [list | install ID | update ID] [--source URL|DIR]
                                          Azurik-Custom-Content's entries, and Install or Update one
    azurkit content check DIR [--write]   a content repository's manifest and files (--write fills in their sha256)

``build`` applies the packs on by default (D528) and each ``--pack``, less
each ``--no-pack`` and each pack on by default that requires one left out
(D588: ``--no-pack qol_memory_upper64`` leaves out ``qol_memory_upper64_gpu``
too); ``--no-defaults`` starts from none (no packs at all is the identity
build). ``--mods FILE`` (Q268: a preset, an AzurKit build's manifest or a
share link; what ``open`` prints) adds its xbr operations, and when it has
a packs layer the build starts from its packs in place of those on by
default. ``--pack-param`` sets a slider of a pack it applies, to
any finite number (D23: never clamped). ``--seed`` randomizes the build:
the plan (the seed under the default settings, a settings file's or a share
string's, on the logic re-checked under the build's movement sliders) is
written first, the built image is read back against it before anything is
written, and the build prints whether its logic still holds (and why not);
``--obsidian-cost`` sets the obsidian locks' cost (vanilla 10). ``--character``
dresses the player in a species' body (a recipe's character as JSON,
``{"species": "keylord"}`` and any of its options: ``tools.characters``;
a variant by name, a built-in or one of a recipe file's,
``{"species": "mine", "variant_file": "recipes.json"}``),
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
           mods: dict | None = None, randomizer: dict | None = None) -> dict:
    """``build``'s flags as the sdk's recipe, from ``mods`` (a mods file,
    ``sdk.read_mods``, its character too) when given, with ``randomizer``
    (the randomizer's flags, in place of the mods file's); ``ValueError`` names a pack no pack
    has, one both added and taken away (no flag cancels another), and a
    ``--pack-param`` that isn't ``PACK.SLIDER=NUMBER`` of a pack the build
    applies (the sdk names a slider or value it refuses)."""
    catalog = {p["name"]: p for p in sdk.catalog()["packs"]}
    if unknown := sorted({*packs, *no_packs} - catalog.keys()):
        raise ValueError(f"no pack {', '.join(map(repr, unknown))} (the packs: {', '.join(catalog)})")
    if both := sorted(set(packs) & set(no_packs)):
        raise ValueError(f"packs both added and taken away: {', '.join(both)}")
    given = (mods or {}).get("packs")
    start = set(given) if given is not None else {name for name, p in catalog.items() if defaults and p["default_on"]}
    chosen = (start | set(packs)) - set(no_packs)
    while gone := {name for name in chosen - set(packs) if not set(catalog[name]["requires"]) <= chosen}:
        chosen -= gone   # a default pack goes with one it requires (D588); a named one the sdk refuses
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
    return {"iso": iso, "packs": built} | ({"xbr": mods["xbr"]} if mods and mods.get("xbr") else {}) | (
        {"randomizer": randomizer} if randomizer else {}) | (
        {"character": mods["character"]} if mods and mods.get("character") else {})


def _randomizer(args: argparse.Namespace) -> dict | None:
    """The randomizer's flags as the sdk's recipe (``None`` without ``--seed``)."""
    if args.seed is None:
        if args.settings or args.share or args.obsidian_cost is not None:
            raise ValueError("--settings, --share and --obsidian-cost randomize the build: give --seed")
        return None
    given = {"seed": args.seed}
    if args.settings:
        given["settings"] = tomllib.loads(Path(args.settings).read_text(encoding="utf-8"))
    elif args.share:
        given["share"] = args.share
    return given | ({"obsidian_cost": args.obsidian_cost} if args.obsidian_cost is not None else {})


def _build(args: argparse.Namespace) -> int:
    try:
        given = sdk.read_mods(Path(args.mods).read_bytes()) if args.mods else None
        made = recipe(args.iso, args.pack, args.no_pack, not args.no_defaults, args.pack_param, given,
                      _randomizer(args))
        built = sdk.build(made | ({"character": json.loads(args.character)} if args.character else {}), args.out)
    except (OSError, ValueError) as exc:    # tomllib.TOMLDecodeError is a ValueError
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    for layer in built["layers"]:
        print(f"{layer['id']}: {layer['sites']} sites, {layer['bytes']} B")
    for conflict in built["conflicts"]:
        print(f"conflict: {conflict}")
    if (plan := built.get("randomizer")) is not None:
        print(f"randomizer: seed {plan['seed']!r}, share {plan['share']}, plan {plan['plan'][:12]}; the image "
              f"holds the plan; logic_verified: {str(plan['logic_verified']).lower()}")
        for line in plan["conflicts"] + plan["why_not"]:
            print(f"  {line}")
    print(f"{Path(built['out'])}: {built['label']}, {built['size']:,} B, sha256 {built['sha256']}")
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


def _data(args: argparse.Namespace) -> int:
    try:
        if args.table is None:
            for t in sdk.data({"what": "index"})["tables"]:
                print(f"{t['category']:<9} {t['name']:<26} {t['cols']:>4} x {t['rows']:<4} {t['label']}")
            return 0
        grid = sdk.data({"what": "table", "table": args.table})
        cols = [c for c, name in enumerate(grid["cols"]) if args.entity in (None, name)]
        if args.entity is not None and not cols:
            raise ValueError(f"config table {args.table} has no entity {args.entity!r}")
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


def _content(args: argparse.Namespace) -> int:
    from azurkit.tools.characters import content

    try:
        if args.action == "check":
            folder = Path(args.target or ".")
            raw = json.loads((folder / content.MANIFEST).read_text(encoding="utf-8"))
            manifest = content.filled(raw, lambda path: (folder / path).read_bytes()) if args.write else content.check(raw)
            for entry in manifest["entries"]:
                content.verify(manifest, entry["id"], {f["path"]: (folder / f["path"]).read_bytes()
                                                       for e in manifest["entries"] for f in e["files"]})
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
    build.add_argument("--mods", metavar="FILE", help="a mods file: a preset, an AzurKit build's manifest or a "
                       "share link (azurkit open prints one); its packs, when it has them, replace those on by default")
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
    build.add_argument("--obsidian-cost", type=float, metavar="N",
                       help="the obsidian each lock costs (vanilla 10; any number, never clamped)")
    build.add_argument("--character", metavar="JSON", help='dress the player in a species\' body: a recipe\'s '
                       'character, e.g. \'{"species": "keylord", "mode": "garret4"}\'')
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
    read = verbs.add_parser("data", help="read config.xbr's tables, as the Data tab shows them",
                            description="List config.xbr's tables by category (each entities x properties), "
                                        "TABLE's entities, or each cell of ENTITY in TABLE by its property's name. "
                                        "It reads the vanilla config.xbr AzurKit ships (both releases hold it).")
    read.add_argument("table", nargs="?", metavar="TABLE", help="a table (azurkit data lists them)")
    read.add_argument("entity", nargs="?", metavar="ENTITY", help="an entity of TABLE (a column)")
    read.set_defaults(run=_data)
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

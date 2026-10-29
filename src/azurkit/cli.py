"""The ``azurkit`` command, a thin shell over :mod:`azurkit.sdk`: each verb
turns its flags into the sdk's JSON and prints what comes back.

    azurkit verify [--iso PATH ...]       is each image a release's vanilla one, every file of it?
    azurkit packs                         the packs: on by default or not, the releases, what each does, its sliders
    azurkit build --iso PATH --out PATH [--pack NAME ...] [--no-pack NAME ...] [--no-defaults]
                  [--pack-param PACK.SLIDER=VALUE ...]

``build`` applies the packs on by default (D528) and each ``--pack``, less
each ``--no-pack`` and each pack on by default that requires one left out
(D588: ``--no-pack qol_memory_upper64`` leaves out ``qol_memory_upper64_gpu``
too); ``--no-defaults`` starts from none (no packs at all is the identity
build). ``--pack-param`` sets a slider of a pack it applies, to
any finite number (D23: never clamped). A refusal or failure is one
``azurkit: ...`` line on stderr and exit 1.
"""

from __future__ import annotations

import argparse
import sys
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


def recipe(iso: str, packs: list[str], no_packs: list[str], defaults: bool, params: list[str] = ()) -> dict:
    """``build``'s flags as the sdk's recipe; ``ValueError`` names a pack no
    pack has, one both added and taken away (no flag cancels another), and a
    ``--pack-param`` that isn't ``PACK.SLIDER=NUMBER`` of a pack the build
    applies (the sdk names a slider or value it refuses)."""
    catalog = {p["name"]: p for p in sdk.catalog()["packs"]}
    if unknown := sorted({*packs, *no_packs} - catalog.keys()):
        raise ValueError(f"no pack {', '.join(map(repr, unknown))} (the packs: {', '.join(catalog)})")
    if both := sorted(set(packs) & set(no_packs)):
        raise ValueError(f"packs both added and taken away: {', '.join(both)}")
    chosen = {name for name, p in catalog.items() if defaults and p["default_on"]} | set(packs)
    chosen -= set(no_packs)
    while gone := {name for name in chosen - set(packs) if not set(catalog[name]["requires"]) <= chosen}:
        chosen -= gone   # a default pack goes with one it requires (D588); a named one the sdk refuses
    built = {name: {} for name in catalog if name in chosen}
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
    return {"iso": iso, "packs": built}


def _build(args: argparse.Namespace) -> int:
    try:
        built = sdk.build(recipe(args.iso, args.pack, args.no_pack, not args.no_defaults, args.pack_param), args.out)
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    for layer in built["layers"]:
        print(f"{layer['id']}: {layer['sites']} sites, {layer['bytes']} B")
    for conflict in built["conflicts"]:
        print(f"conflict: {conflict}")
    print(f"{Path(built['out'])}: {built['label']}, {built['size']:,} B, sha256 {built['sha256']}")
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
    build.add_argument("--out", required=True, metavar="PATH", help="where to write the build (never the input)")
    build.add_argument("--pack", action="append", default=[], metavar="NAME", help="a pack to apply (repeatable)")
    build.add_argument("--no-pack", action="append", default=[], metavar="NAME",
                       help="a pack on by default to leave out (repeatable)")
    build.add_argument("--no-defaults", action="store_true", help="leave out every pack on by default")
    build.add_argument("--pack-param", action="append", default=[], metavar="PACK.SLIDER=VALUE",
                       help="set a slider of a pack the build applies: any finite number, never clamped "
                            "(repeatable; azurkit packs lists them)")
    build.set_defaults(run=_build)
    args = parser.parse_args(argv)
    if args.verb is None:
        parser.print_help()
        return 0
    return args.run(args)

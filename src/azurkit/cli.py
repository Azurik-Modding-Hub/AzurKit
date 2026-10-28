"""The ``azurkit`` command.

    azurkit verify [--iso PATH ...]       is each image a release's vanilla one, every file of it?
    azurkit build --iso PATH --out PATH   the identity build: the image packed with no edits

A refusal or failure is one ``azurkit: ...`` line on stderr and exit 1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from azurkit import __version__
from azurkit.core import gate, iso


def _verify(args: argparse.Namespace) -> int:
    images, failed = [Path(p) for p in args.iso], 0
    if not images:
        for release in gate.RELEASES:
            if (found := gate.find(release)) is None:
                print(f"azurkit: no {release.label} image: {gate.missing(release)}", file=sys.stderr)
                failed = 1
            else:
                images.append(found)
    for image in images:
        try:
            stamp = gate.verify(image)
        except (OSError, ValueError) as exc:
            print(f"azurkit: {exc}", file=sys.stderr)
            failed = 1
            continue
        print(f"{image}: the vanilla {stamp.release.label} image, every file as its manifest has it")
    return failed


def _build(args: argparse.Namespace) -> int:
    source, out = Path(args.iso), Path(args.out)
    try:
        stamp = gate.verify(source, whole=False)              # D27: a build starts from vanilla
        for release in gate.RELEASES:                             # D36
            if (vanilla := gate.find(release)) and out.exists() and out.samefile(vanilla):
                raise ValueError(f"{out}: it is the vanilla {release.label} image, which a build never writes over")
        sha256 = iso.pack(iso.read(source), out)
    except (OSError, ValueError) as exc:
        print(f"azurkit: {exc}", file=sys.stderr)
        return 1
    print(f"{out}: {stamp.release.label}, {out.stat().st_size:,} B, sha256 {sha256}")
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
    build = verbs.add_parser("build", help="pack an image with no edits (the identity build)",
                             description="Check that --iso is a vanilla image (the files a build reads), then write "
                                         "it to --out with no edits: the same bytes.")
    build.add_argument("--iso", required=True, metavar="PATH", help="the vanilla image")
    build.add_argument("--out", required=True, metavar="PATH", help="where to write the build (never the input)")
    build.set_defaults(run=_build)
    args = parser.parse_args(argv)
    if args.verb is None:
        parser.print_help()
        return 0
    return args.run(args)

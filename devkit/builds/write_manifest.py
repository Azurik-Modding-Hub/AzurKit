"""``python -m devkit builds write-manifest [--iso IMAGE ...] [--out FILE]``:
a release's manifest (``src/azurkit/core/manifests/<release>.json``: each
folder of its image, and each file's size and sha256, what the gate checks
an image against, ``azurkit.core.gate``) written from that release's exact
vanilla image (Modkit's ``iso-verify --write-manifest``, ported in Step
4.24a).

The image must be one the gate's releases name by the whole image: its size
and sha256 a release's (``gate.Release.iso_size`` and ``iso_sha256``, which
no manifest gives); another is refused by name and nothing is written. With
no ``--iso`` it writes each release's image the resolver finds
(``AZURKIT_ISO``, ``AZURKIT_ISO_EUROPE``, else the user data folder's), noting
one it doesn't; ``--out`` writes one image's elsewhere. The file is Modkit's
layout, byte for byte, written whole (a part file renamed into place); it
prints counts and paths, never a byte. A refusal is one ``write-manifest:``
line on stderr and exit 1. A manifest is a protected path: the commit that
changes one names it and why."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from azurkit.core import gate, iso


def release_of(path: Path) -> gate.Release:
    """The release whose whole vanilla image ``path`` is, by its size, then
    its sha256; ``ValueError`` names an image of neither."""
    size = path.stat().st_size
    sized = [r for r in gate.RELEASES if r.iso_size == size]
    if not sized:
        raise ValueError(f"{path} is no release's vanilla image: {size:,} B, where "
                         + " and ".join(f"{r.label}'s is {r.iso_size:,} B" for r in gate.RELEASES))
    with open(path, "rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    if (found := next((r for r in sized if r.iso_sha256 == sha), None)) is None:
        raise ValueError(f"{path} is no release's vanilla image: {size:,} B, {sized[0].label}'s size, but its "
                         f"sha256 is {sha[:12]}, not {sized[0].iso_sha256[:12]}")
    return found


def manifest(path: Path) -> tuple[str, int]:
    """The manifest of the image at ``path`` (every folder, sorted, and every
    file's ``[size, sha256]``, by path), in Modkit's layout, and its count of
    entries."""
    dirs, files = [], {}
    with iso.Reader(path) as r:
        for entry in r.entries():
            if entry.is_dir:
                dirs.append(entry.path)
                continue
            digest = hashlib.sha256()
            for data in r.chunks(entry):
                digest.update(data)
            files[entry.path] = [entry.size, digest.hexdigest()]
    rows = ",\n".join(f"  {json.dumps(p)}: {json.dumps(files[p])}" for p in sorted(files))
    return f'{{\n "dirs": {json.dumps(sorted(dirs))},\n "files": {{\n{rows}\n }}\n}}\n', len(dirs) + len(files)


def write(image: Path, out: Path | None = None) -> tuple[gate.Release, Path, int]:
    """Write the manifest of ``image``'s release from it to ``out`` (its
    release's own by default): the release, where, and how many entries."""
    release = release_of(image)
    out = out or release.manifest
    if out.exists() and out.samefile(image):
        raise ValueError(f"{out}: the image itself")
    text, n = manifest(image)
    part = out.with_name(f"{out.name}.part")
    try:
        part.write_bytes(text.encode("utf-8"))
        part.replace(out)
    finally:
        part.unlink(missing_ok=True)
    return release, out, n


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m devkit builds write-manifest",
                                 description="Write each release's manifest (src/azurkit/core/manifests/"
                                             "<release>.json) from its exact vanilla image; any other is refused.")
    ap.add_argument("--iso", action="append", default=[], metavar="IMAGE",
                    help="an image to write its release's manifest from (repeatable; default: each release's the "
                         "resolver finds)")
    ap.add_argument("--out", metavar="FILE", help="write it here, not over the release's own (one image)")
    args = ap.parse_args(argv)
    images = [Path(p) for p in args.iso]
    if not images:
        for release in gate.RELEASES:
            if (found := gate.find(release)) is None:
                print(f"write-manifest: no {release.label} image: {gate.missing(release)}", file=sys.stderr)
            else:
                images.append(found)
    if not images or (args.out and len(images) != 1):
        print("write-manifest: " + ("no image to write a manifest from" if not images
                                    else "--out writes one image's manifest: give one --iso"), file=sys.stderr)
        return 1
    failed = 0
    for image in images:
        try:
            release, out, n = write(image, Path(args.out) if args.out else None)
        except (OSError, ValueError) as exc:
            print(f"write-manifest: {exc}", file=sys.stderr)
            failed = 1
            continue
        print(f"{image}: the vanilla {release.label} image; wrote its {n} entries to {out}")
    return failed

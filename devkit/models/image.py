"""The image a model verb reads and the folder it writes (D27, D36): Modkit's
resolver, identity gate and output guard as its ``model`` verbs used them.

:func:`find` is ``--iso``'s image, else the one AzurKit finds
(``core.gate.find``: USA's, else Europe's). :func:`stamp` checks it as a
build's input, every file a build reads its release's (D27, ``gate.verify``
through the sdk's kept check). :func:`read` reads any image's files, a
build's too. :func:`swap` gives the swap's modules (``tools.characters``)
what they read of the packs and of a release's vanilla ``default.xbe``
outside a build. :func:`output` refuses a folder a verb may not write."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path

from azurkit.core import gate, iso

CHECKOUT = Path(__file__).resolve().parents[2]
"""This checkout (a lane's tree in a lane): what a verb writes is a game asset, never in it."""


def find(given: str | None = None) -> Path:
    """``given`` (``--iso``), else the first release's image ``gate.find``
    finds; ``ValueError`` says where it looked."""
    if given:
        return Path(given)
    if found := next((path for release in gate.RELEASES if (path := gate.find(release))), None):
        return found
    raise ValueError(f"no image: {gate.missing(gate.USA)}, or pass --iso PATH")


def stamp(path: Path) -> gate.Stamp:
    """``path``'s ``gate.Stamp`` once every file a build reads is its
    release's (D27); ``gate.NotVanillaError`` (a ``ValueError``) names the
    first that isn't."""
    from azurkit import sdk

    return sdk._stamp(str(path))


def read(path: Path, *names: str) -> list[bytes]:
    """The files ``names`` (``gamedata/config.xbr``) of the image at ``path``,
    any image's."""
    with iso.Reader(path) as r:
        return [r.read(name) for name in names]


@contextlib.contextmanager
def swap(built: bytes | None = None) -> Iterator[None]:
    """Inside it, the swap's modules read the packs as a build describes them
    (``ports.get_pack``: ``model_inspect``'s budget lines) and, for
    ``built`` (a built ``default.xbe``), a site's vanilla bytes from its
    release's image AzurKit finds, each file checked (D27); ``ValueError``
    when that image isn't found."""
    from azurkit.tools import characters, mods
    from azurkit.tools.characters import ports

    release, vanilla = gate.USA, None
    if built is not None:
        release = ports.xbe_layout(built).facts.release
        if (path := gate.find(release)) is None:
            raise ValueError(f"a built image is read against its release's vanilla one: {gate.missing(release)}")
        vanilla = ports.Vanilla(release, path)
    with ports.building(ports.Build(vanilla or ports.Vanilla(release, {}),
                                    packs=characters.packs_view(release, mods.PACKS))):
        yield


def output(out: str | Path, *inputs: Path, file: bool = False) -> Path:
    """``out`` as an absolute path, once it may be written (D36): a new or
    empty folder (``file``: a file, which may replace one there, as
    ``fx texture --png``'s and the Blender batch's MP4 do), outside this
    checkout, none of ``inputs``
    (the files a verb reads) and inside none, and outside the folder of each
    image read (an input named ``*.iso``) or found (whatever its name, as
    ``AZURKIT_ISO`` may name ``Azurik.xiso``), each folder compared by file
    identity (Modkit's ``require_new_output``), so another letter case can't
    slip through; ``ValueError`` names why not."""
    out = Path(out).absolute()
    real = out.resolve()
    above = [d for d in (real, *real.parents) if d.exists()]

    def inside(folder: Path) -> bool:
        return folder.exists() and any(os.path.samefile(d, folder) for d in above)

    if inside(CHECKOUT):
        raise ValueError(f"--out {out} is inside the checkout {CHECKOUT}: what it writes is a game asset")
    images = [p for p in inputs if p.suffix.lower() == ".iso"] + [p for p in map(gate.find, gate.RELEASES) if p]
    for folder in {d for p in images for d in (p.absolute().parent, p.resolve().parent)}:
        if inside(folder):
            raise ValueError(f"--out {out} is inside {folder}, an image's folder")
    for p in inputs:
        if p.exists() and real.exists() and real.samefile(p):
            raise ValueError(f"--out {out} is the same file as {p}, which it reads")
    if not file and out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"--out {out} already holds something; give a new or empty folder")
    return out

"""What the database tools ported from Modkit (Step 4.13b, AGENTS.md's Porting from Modkit) import from Modkit's
shared engine, on AzurKit's: a port points those imports here, so each module's code stays Modkit's
(``devkit/sim/ports.py`` is the simulator's like table).

- the image: :class:`XisoReader` (Modkit's ``iso.xiso``: :meth:`~XisoReader.read_file` and
  :meth:`~XisoReader.walk`, on :class:`azurkit.core.iso.Reader`), :func:`default_region`,
  :func:`resolve_vanilla_iso` and :func:`verify_vanilla_iso` (``assets.vanilla``, on :mod:`azurkit.core.gate`)
  and :func:`require_new_output` (``assets.vanilla``'s D36 check, less Modkit's checkout ``iso/`` folder,
  which AzurKit hasn't);
- config.xbr's keyed tables: :func:`load_all_tables` (``config.keyed_tables``, as the characters' ports read
  them).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from azurkit.core import gate, iso
from azurkit.tools.characters.ports import load_all_tables
from devkit.sim import ports

__all__ = ["XisoReader", "default_region", "load_all_tables", "require_new_output", "resolve_vanilla_iso",
           "verify_vanilla_iso"]

_ISO_NAMES = ("usa.iso", "europe.iso")   # the names a vanilla image has in a checkout's iso/


class XisoReader(ports.XisoReader):
    """An image read file by file, as Modkit's ``iso.xiso.XisoReader``: :meth:`walk` its entries too."""

    def walk(self) -> Iterator[tuple[str, iso.Entry]]:
        """``(posix_path, entry)`` for every file and folder, parents first."""
        for entry in self._reader.entries():
            yield entry.path, entry


def resolve_vanilla_iso(release: gate.Release = gate.USA) -> Path:
    """``release``'s image (``gate.find``); ``FileNotFoundError`` names where it looked."""
    if (path := gate.find(release)) is None:
        raise FileNotFoundError(gate.missing(release))
    return path


def default_region() -> gate.Release:
    """The release a verb given no image reads: USA when its image is found, else the only one found; USA when
    none is, so its resolver says where it looked."""
    return next((r for r in gate.RELEASES if gate.find(r) is not None), gate.USA)


def verify_vanilla_iso(path: Path) -> gate.Release:
    """The release ``path`` is the vanilla image of, every file checked; :class:`azurkit.core.gate.NotVanillaError`
    (a ``ValueError``) names the first file that differs."""
    return gate.verify(path).release


def require_new_output(out: Path, *inputs: Path) -> None:
    """D36: raise ``ValueError`` unless ``out`` may be written: it is none of ``inputs`` and inside none that is a
    folder, not a found vanilla image (either release), not directly in the folder of one or of an input named
    ``usa.iso`` or ``europe.iso`` (any case), or in the folder such a link resolves into, and nowhere inside such
    a folder named ``iso``. Both sides are resolved (``..`` and symlinks, dangling ones too) and then compared by
    file identity, so a link, a hardlink or another letter case can't slip through either; an output that is
    itself a link counts where it sits too, as a write's rename replaces it there."""
    def same(a: Path, b: Path) -> bool:
        return a.exists() and b.exists() and os.path.samefile(a, b)

    out = Path(out)
    real = out.resolve()
    homes = (real.parent, out.parent.resolve())   # an output link's own folder too
    above = [real, *(d for h in homes for d in (h, *h.parents))]
    protected = [Path(p) for p in inputs]
    images = [p for p in protected if any(n.lower() in _ISO_NAMES for n in (p.name, p.resolve().name))]
    for release in gate.RELEASES:
        if (found := gate.find(release)) is not None:
            protected.append(found)
            images.append(found)
    folders = [d for p in images for d in (p.parent, p.resolve().parent)]
    for p in protected:
        if same(real, p):
            raise ValueError(f"output {out} is the same file as {p}; nothing is ever written over an input or "
                             f"a vanilla image")
        if p.is_dir() and any(same(d, p) for d in above):
            raise ValueError(f"output {out} is inside the input folder {p}; nothing is ever written into an input")
    for iso_dir in (d for d in folders if d.name.lower() == "iso"):
        if any(same(d, iso_dir) for d in above):
            raise ValueError(f"output {out} is inside {iso_dir}, which holds only the vanilla image")
    for folder in folders:
        if any(same(h, folder) for h in homes):
            raise ValueError(f"output {out} is inside {folder}, the vanilla ISO's folder")

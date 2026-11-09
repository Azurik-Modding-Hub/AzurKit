"""What the database tools ported from Modkit (Step 4.13b, AGENTS.md's Porting from Modkit) import from Modkit's
shared engine, on AzurKit's: a port points those imports here, so each module's code stays Modkit's
(``devkit/sim/ports.py`` is the simulator's like table).

- the image: :class:`XisoReader` (Modkit's ``iso.xiso``: :meth:`~XisoReader.read_file` and
  :meth:`~XisoReader.walk`, on :class:`azurkit.core.iso.Reader`), :func:`default_region`,
  :func:`resolve_vanilla_iso` and :func:`verify_vanilla_iso` (``assets.vanilla``, on :mod:`azurkit.core.gate`)
  and :func:`require_new_output` (``assets.vanilla``'s D36 check, less Modkit's checkout ``iso/`` folder,
  which AzurKit hasn't: the engine's, :func:`azurkit.core.gate.require_new_output`);
- config.xbr's keyed tables: :func:`load_all_tables` (``config.keyed_tables``, as the characters' ports read
  them).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from azurkit.core import gate, iso
from azurkit.core.gate import require_new_output
from azurkit.tools.characters.ports import load_all_tables
from devkit.sim import ports

__all__ = ["XisoReader", "default_region", "load_all_tables", "require_new_output", "resolve_vanilla_iso",
           "verify_vanilla_iso"]


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

"""Character swaps and variants; the only package that may import numpy.

Step 4.3a1 holds what a swap writes with, ported from Modkit by
``scripts/oracle_sync.py`` (the models family: never edit them by hand):
``characters.py`` reads a body and its clips from ``characters.xbr``,
``body_codec.py`` decodes a body whole and writes it back with any topology,
and ``index_xbr.py`` reads ``index.xbr`` and adds records to it; each grows
its archive through ``core.xbr.append`` (new resources, their relocations,
grown payloads).

**The character layer** (§12.2, the plan's character group): a swap grows
``characters.xbr``, ``fx.xbr`` and ``index.xbr``, so the layer writes each
it changes whole (:data:`FILES`), all of them one group (:func:`whole_files`),
and the rest (config.xbr's cells, default.xbe's hooks) as ranges. It stacks
after the packs and before the Data tool's ``xbr`` operations
(``edits.layer``'s canonical order, Modkit's ``mod_apply``'s).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from azurkit.edits.layer import Change

TOOL = KIND = "characters"
FILES = ("gamedata/characters.xbr", "gamedata/fx.xbr", "gamedata/index/index.xbr")
"""The files the character layer writes whole, one group."""


def whole_files(base: Mapping[str, bytes], built: Mapping[str, bytes], group: str) -> tuple[Change, ...]:
    """The character layer's whole-file group ``group``: each of
    :data:`FILES` that ``built`` holds and that differs from its vanilla
    bytes in ``base``, as one whole change, in :data:`FILES`' order.
    ``ValueError`` names a file ``built`` holds that isn't one of them."""
    if strays := sorted(set(built) - set(FILES)):
        raise ValueError(f"{group}: {', '.join(strays)} isn't a file the character layer writes whole "
                         f"({', '.join(FILES)})")
    return tuple(Change(file, 0, hashlib.sha256(base[file]).hexdigest(), bytes(built[file]), group, whole=True)
                 for file in FILES if file in built and bytes(built[file]) != base[file])

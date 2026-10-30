"""The content folder: the files a swap reads that Azurik-Custom-Content
carries, not this repository or the wheel (D869: our own work, made in
Blender on the game's rigs; the Characters pickers install them, D913).

- ``clips/townsfolk/``: the weaponless townsfolk's bare-hands kit, a weapon
  any body may pick (``bare_hands``; ``_player_kit.KIT``);
- ``fx/air_elemental/``: the worn air elemental's funnel mesh and its
  swirl (``_player_variants.FX_ASSETS``);
- ``clips/booblord/``, ``sounds/booblord/``: booblord's own clips and
  voice (the built-in variants', ``_player_variants.CLIPS`` and ``SOUNDS``).

The swap's modules (the models family's sync installs them) read these
below :data:`ROOT`: the folder ``AZURKIT_CONTENT`` names, else ``content``
in the user data folder (beside the images' links, where the app keeps
what it installs). Until Azurik-Custom-Content is published (Step 4.4),
``scripts/oracle_sync.py``'s models sync installs Modkit's files there, at
the family's commit, and ORACLE.toml's ``models.content`` keeps each one's
sha256. A build that needs one the folder lacks fails naming the file."""

from __future__ import annotations

import os
from pathlib import Path

ENV = "AZURKIT_CONTENT"


def root() -> Path:
    """The folder ``AZURKIT_CONTENT`` names, else ``content`` in the user
    data folder; the site's worker (the wheel without its dependencies, so
    no user data folder) reads ``content`` in its working folder."""
    if named := os.environ.get(ENV):
        return Path(named)
    try:
        from platformdirs import user_data_path
    except ImportError:
        return Path("content")
    return user_data_path("AzurKit", appauthor=False) / "content"


ROOT = root()
"""The content folder of this process (:func:`root`, read once)."""

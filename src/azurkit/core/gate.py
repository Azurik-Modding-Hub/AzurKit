"""The two releases AzurKit builds from, USA and Europe: what each vanilla
image is, and where the player keeps it.

Each image is the file its release's variable names (``AZURKIT_ISO``,
``AZURKIT_ISO_EUROPE``), or when that is unset, ``usa.iso`` or
``europe.iso`` in the user data folder (``platformdirs``'
``user_data_dir("AzurKit")``). The identity check that gives a stamp comes
with the ISO reader's step; until then the tests check an image by its
size and sha256.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class Release:
    name: str        # "usa" or "europe": its image's file name and its pytest marker
    label: str       # how messages name it
    iso_sha256: str  # the whole vanilla image
    iso_size: int
    env: str         # the variable that names its image


USA = Release("usa", "USA", "6989c84e96ebcb5d668ccdd9942f737d2e36843e7db459996ed077e6161d84be",
              2_747_006_976, "AZURKIT_ISO")
EUROPE = Release("europe", "Europe", "77fb736e5656333080733ba894ceb1c505a83e53339441c8ac563fcccbc37e99",
                 2_313_027_584, "AZURKIT_ISO_EUROPE")
RELEASES = (USA, EUROPE)


def data_path(release: Release) -> Path:
    """Where the user data folder keeps the release's image."""
    return user_data_path("AzurKit", appauthor=False) / f"{release.name}.iso"


def find(release: Release) -> Path | None:
    """The file the release's variable names (when it is set), else its image
    in the user data folder; ``None`` when that isn't a file."""
    path = Path(os.environ.get(release.env) or data_path(release))
    return path if path.is_file() else None

"""The pack engine (:mod:`.engine`) and the packs.

:data:`PACKS` holds them in their canonical order, Modkit's registry order,
which every build applies them in (AZ-024); a pack ported later takes its
place there."""

from azurkit.tools.mods.engine import Pack, PackError, plan
from azurkit.tools.mods.packs import fps_unlock, qol_alloc_race, qol_pickup_anims, qol_popups

PACKS: dict[str, Pack] = {pack.name: pack for pack in (
    fps_unlock.PACK, qol_popups.GEM_POPUPS, qol_popups.OTHER_POPUPS, qol_pickup_anims.PACK, qol_alloc_race.PACK)}

__all__ = ["PACKS", "Pack", "PackError", "plan"]

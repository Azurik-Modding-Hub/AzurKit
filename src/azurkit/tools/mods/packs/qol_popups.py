"""qol_gem_popups and qol_other_popups: hide first-time popups.

A popup's message is looked up by its resource key in ``.rdata``
(``loc/english/popups/<name>``). Each site nulls the key's first byte, so
the key is empty, the lookup finds nothing, and no popup shows. Each key is
named by its USA address, which Europe's address map moves.

qol_other_popups leaves the game-over message alone (the death screen would
send the player to the menu unexplained) and the 6keys one (D105): it is the
message a key pickup gives when no key slot is free, and the pickup is refused
(AZ-272).
"""

from __future__ import annotations

from azurkit.tools.mods.engine import Pack, PatchSpec

GEMS = {"emeralds": 0x19EBF8, "diamonds": 0x19EBDC, "rubies": 0x19EBC0, "sapphires": 0x19EBA0,
        "collect_obsidians": 0x19EB78}
OTHERS = {"swim": 0x19BE18, "key": 0x19EB1C, "chromatic_powerup": 0x19EB34, "health": 0x19EB5C,
          "water_powerup": 0x19EC14, "fire_powerup": 0x19EC38, "air_powerup": 0x19EC58, "earth_powerup": 0x19EC78}


def _keys(keys: dict[str, int]) -> tuple[PatchSpec, ...]:
    return tuple(PatchSpec(label=f"the {name} popup's key emptied", va=va, patch=b"\0") for name, va in keys.items())


GEM_POPUPS = Pack(name="qol_gem_popups", description="Hides first-time gem-collect popups (all 5 gem types).",
                  sites=_keys(GEMS))
OTHER_POPUPS = Pack(name="qol_other_popups",
                    description="Hides first-time tutorial, key, health and power-up popups.", sites=_keys(OTHERS))

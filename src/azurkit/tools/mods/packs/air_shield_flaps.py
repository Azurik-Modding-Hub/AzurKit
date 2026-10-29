"""air_shield_flaps: the wing flaps each air shield tier grants, the
``Flaps`` cells of ``air_shield_1`` to ``air_shield_3`` in config.xbr's
``armor_properties`` (the table the game loads as
``config/armor_properties``); no XBE byte.

The armor loader truncates each to an int32 (0xF5A40: 2.7 gives 2) and
wraps a value no int32 holds (3e9 gave -1294967296 flaps), so such a value
is refused (D45, D73). The track, 0 to 20, is a hint (D23).

Ported from Modkit's ``azurik_mod/patches/air_shield_flaps`` at the packs
oracle's tag.
"""

from __future__ import annotations

from azurkit.tools.mods.engine import Pack, XbrParametricEdit


def _tier(tier: int, default: float) -> XbrParametricEdit:
    return XbrParametricEdit(
        name=f"air_shield_{tier}_flaps", label=f"Air Shield {tier} flaps", table="armor_properties",
        entity=f"air_shield_{tier}", prop="Flaps", default=default, slider_min=0.0, slider_max=20.0,
        slider_step=1.0, unit="flaps", int32="trunc", logic_floor="min",
        description=f"Wing flaps Air Shield {tier} grants (config.xbr armor_properties).")


PACK = Pack(name="air_shield_flaps", description="Wing flaps each air-shield tier grants.",
            sites=(_tier(1, 1.0), _tier(2, 2.0), _tier(3, 5.0)), category="player")

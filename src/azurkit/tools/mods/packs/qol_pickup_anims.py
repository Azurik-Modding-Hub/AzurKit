"""qol_pickup_anims: skip the celebration after a pickup.

One site: the start of the non-gem pickup handler's "play the celebration"
block becomes a 5-byte JMP rel32 to its epilog (0x4146F). The save list and
the collected flags are still written, so a pickup stays collected.
"""

from __future__ import annotations

from azurkit.tools.mods.engine import Pack, PatchSpec

PACK = Pack(
    name="qol_pickup_anims",
    description="Skips the post-pickup celebration animation.",
    sites=(PatchSpec(label="skip the pickup celebration", va=0x000413EE, patch=b"\xE9\x7C\x00\x00\x00", rel32=(1,)),),
)

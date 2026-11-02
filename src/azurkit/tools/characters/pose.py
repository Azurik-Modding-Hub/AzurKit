"""The pose a body's pictures are drawn in (D1042): the first frame of its idle.

:func:`idle_clip` names a body's idle as the build's slot 1 plays it: its own ``idle``, else the slot's pick among its
own clips (``idle_1``, town_female_4's ``vaseidle``, a townsman's ``listen_1``, a flier's ``fly``); a body with no clips
has none and stays in its bind pose. :func:`group_positions` skins the most detailed LOD's groups into a clip's first frame as the
game draws them (:func:`~azurkit.tools.characters.gltf._engine`'s bone worlds, its scales too, times the inverse
binds, by each vertex's weights), so a prop stands where its clip keys it: town_female_4's vase on her head, the
others' at their 1e-12 out of sight, garret4's staff in his hand.
"""

from __future__ import annotations

import struct

import numpy as np

from azurkit.core.xbr.nodes import TocEntry
from azurkit.tools.characters import gltf, render
from azurkit.tools.characters._player_slots import closest_own
from azurkit.tools.characters.body_codec import VERTEX_SIZE, slot_entry
from azurkit.tools.characters.characters import bone_records, inverse_binds, read_body
from azurkit.tools.characters.retarget import named_clip

_VERTEX = np.dtype({"names": ("position", "weights", "slots"), "formats": ("<3f4", "<4f4", "4u1"),
                    "offsets": (0, 12, 56), "itemsize": VERTEX_SIZE})
_ENTRY = np.array([-1 if (e := slot_entry(byte)) is None else e for byte in range(256)])
"""Each slot byte's palette entry (-1: none)."""


def idle_clip(characters_xbr: bytes, body: str) -> str | None:
    """``body``'s idle under its own clips (module docstring), or ``None``: it has none, or no clip at all."""
    found = read_body(characters_xbr, body)
    if found is None:
        return None
    return next((c for c in found.clips if c.casefold() == "idle"), None) or closest_own("idle", found)


def group_positions(characters_xbr: bytes, toc: list[TocEntry], index: int, body: str, clip: str) -> list[np.ndarray]:
    """Each LOD-0 group's positions (n, 3) of the body at TOC ``index`` (``body``'s, or its player's copy, which has
    her bones) in the first frame of ``characters/<body>/<clip>``. :class:`ValueError` for a live weight on a slot
    outside its group's palette (:meth:`~azurkit.tools.characters.body_codec.Vertex.skin`'s)."""
    rig = gltf._Body(body, 0, bone_records(characters_xbr, body), inverse_binds(characters_xbr, body), (), ())
    worlds = np.array(gltf._engine(rig, named_clip(characters_xbr, body, clip), 0.0))
    skin = (worlds @ np.array(rig.binds, np.float64).reshape(-1, 4, 4).transpose(0, 2, 1))[:, :3]
    base = toc[index].file_offset
    bmsh = toc[struct.unpack_from("<I", characters_xbr, render._rel(characters_xbr, base + 12))[0]].file_offset
    groups = render._rel(characters_xbr, bmsh + 4)
    out = []
    for k in range(struct.unpack_from("<I", characters_xbr, bmsh)[0]):
        at = groups + 40 * k
        npal = struct.unpack_from("<i", characters_xbr, at + 4)[0]
        palette = np.array(struct.unpack_from(f"<{npal}i", characters_xbr, render._rel(characters_xbr, at + 8)), np.int64)
        v = np.frombuffer(characters_xbr, _VERTEX, struct.unpack_from("<I", characters_xbr, at + 24)[0],
                          render._rel(characters_xbr, at + 28))
        entries = _ENTRY[v["slots"]]
        weights = v["weights"].astype(np.float64)
        if ((weights > 0) & ((entries < 0) | (entries >= len(palette)))).any():
            raise ValueError(f"{body}: a weight's slot is outside group {k}'s {len(palette)}-entry palette")
        points = np.concatenate((v["position"].astype(np.float64), np.ones((len(v), 1))), axis=1)
        out.append(np.einsum("ni,nijk,nk->nj", weights, skin[palette[np.clip(entries, 0, len(palette) - 1)]], points))
    return out

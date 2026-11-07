"""The Variants editor's engine (Step 4.6b; Modkit's Variants page's
engine half, ``authoring/colour_preview.py`` and ``variant_library.py``'s
calls past the library's rules): the colour views (``tools/characters/colour_preview.py``)."""

from __future__ import annotations

import hashlib
import json

import numpy as np

from azurkit.core import iso
from azurkit.tools import characters
from azurkit.tools.characters import _player_variants, colour_preview
from azurkit.tools.randomizer import art
from tests import _hosts

#: booblord_human's colours (W38: her skin's reds warmed, her purples turned green), which the views draw on her base
#: species' own body here.
HUMAN = json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))["booblord_human"]["colours"]


def _sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _game(usa_iso) -> tuple[bytes, bytes]:
    with iso.Reader(usa_iso) as r:
        return r.read(characters.CONFIG), r.read(characters.FILES[0])


def test_the_colour_views_draw_a_bodys_rows_recoloured_as_its_build_recolours_them(usa_iso):
    """``colour_preview`` (Modkit's, in the package since Step 4.6b) draws town_female_2's own body, booblord's
    base, in booblord_human's colours from the front and from behind, 160 px, by sha256 on the recording host (off
    it, D1016, close enough: each view's size, its drawn pixels' count within 1 % and their mean colour within 2 of
    each channel's), the colours changing both; and her rows' textures whole as the Export's PNGs, each recoloured
    row's pixels by sha256 on every host (the recolour's maths is fdlibm's and numpy's correctly rounded operations,
    AZ-830; a PNG's own bytes are each zlib's, so its pixels are held)."""
    config, bodies = _game(usa_iso)
    base = colour_preview.vanilla(config, bodies, "town_female_2")
    colours = colour_preview.specs(HUMAN)
    drawn, plain = colour_preview.pictures(colour_preview.recoloured(base, colours)), colour_preview.pictures(base.parts)
    assert (base.body, sorted(base.sizes.items())) == ("townspeople/female_2", [(r, (128, 128)) for r in range(3)])
    assert all(drawn[view] != plain[view] for view in ("front", "back"))
    seen = {}
    for view, png in drawn.items():
        px = art.unpng(png)
        drawn_at = px[..., 3] > 0
        seen[view] = (px.shape, int(drawn_at.sum()), px[drawn_at][:, :3].mean(0))
    if _hosts.recording():
        assert {view: _sha12(png) for view, png in drawn.items()} == {"front": "f8afb06f3a7b", "back": "70c65104331e"}
    want = {"front": ((160, 160, 4), 5364, (114.22, 78.1, 54.16)),
            "back": ((160, 160, 4), 5435, (113.85, 81.2, 57.31))}
    for view, (shape, count, mean) in seen.items():
        assert shape == want[view][0] and abs(count - want[view][1]) <= want[view][1] // 100, view
        assert np.abs(mean - np.array(want[view][2])).max() <= 2, view
    rows = colour_preview.rows(bodies, base.body, colours)
    files = colour_preview.pngs("mine", rows)
    assert {name: _sha12(art.unpng(png).tobytes()) for name, png in files.items()} == {
        "mine_row0.png": "546ff8107223", "mine_row1.png": "de321e106c9a", "mine_row2.png": "11a3e26a824f",
        "mine_row3.png": "819befadd5c2"}

"""The reach model's first stage, as the maps read it (Step 4.2c3).

Modkit's map drawer (``scripts/render_level_maps.py``, installed as
:mod:`.maps`) builds ``draft.reach.Reach(level, flights=False)`` with no
database and reads only its level, its solid spans, the logic profile's
walkable floors and regions, the water and damage volumes and the damage
there at load. This is that stage of ``Reach.__init__``, line for line
(Modkit's ``azurik_mod/randomizer/draft/reach.py``): the wiring decides
which driven solids and volumes are there at load and which toggled solids
crumble under the player's own touch, then the spans, the volumes and the
logic profile's :class:`~..draft.floors.Walk`. The rest of the model (the
flights, the moves, the gates, the zones) draws nothing on a map, so it
isn't ported; the sync's rewrite points the drawer's import here.
"""

from __future__ import annotations

import numpy as np

from azurkit.tools.randomizer.draft.floors import PROFILES, Walk
from azurkit.tools.randomizer.draft.geometry import (
    CAT_DAMAGE, CAT_PUSH, CAT_TOGGLE, CAT_WATER, SOLID_CATS, Obstacles, Spans, Volumes, raster)
from azurkit.tools.randomizer.draft.wiring import Wiring

#: What a level's derive reads beyond its generated file with no database (Modkit's ``export.derive_inputs``'s
#: ``level`` for empty inputs): no hand-authored node, button or barrier.
NO_HAND = {"node": [], "button": [], "barrier": []}


class Reach:
    """A level's spans, volumes and logic floors (Modkit's ``Reach`` with
    ``flights=False`` and no ``db``, up to its logic profile's walk)."""

    def __init__(self, lv, flights: bool = False):
        if flights:
            raise ValueError("the maps' reach model stops at the floors (flights=False)")
        self.lv, self.name = lv, lv.name
        self.gen, self.toml = {}, NO_HAND
        self.wire = Wiring(lv, self.gen, self.toml)
        # A driven gameSolid, damage or pushEnable is there at load when its first frame's value is non-zero
        self.init_changed = []
        for o in lv.owners:
            plug = {CAT_TOGGLE: "gameSolid", CAT_DAMAGE: "damage", CAT_PUSH: "pushEnable"}.get(o["cat"])
            if o["kind"] != "platform" or plug is None or plug not in o["driven"]:
                continue
            sg = self.wire.plug(o["oi"], plug)
            o["present_stored"] = o["present"]
            if sg.init is not None and (sg.init != 0.0) != o["present"]:
                o["present"] = sg.init != 0.0
                self.init_changed.append(o["oi"])
        self.present = np.array([o["present"] for o in lv.owners], dtype=bool)
        # a toggled solid that only its own touch removes is a floor the logic walk stands on
        self.crumble = set()
        for o in lv.owners:
            if o["kind"] == "platform" and o["cat"] == CAT_TOGGLE and o["present"] and "gameSolid" in o["driven"]:
                t_ = self.wire.terms(self.wire.plug(o["oi"], "gameSolid").off)
                if t_ == [(frozenset([f"touch:{o['G']}:{o['R']}"]), frozenset())]:
                    self.crumble.add(o["oi"])
        self.pairs = raster(lv, np.nonzero(np.isin(lv.tri_cat, SOLID_CATS))[0])
        self.pmask = self.present[lv.tri_owner[self.pairs[3]]]
        self.spans = Spans(lv, *(x[self.pmask] for x in self.pairs))
        self.water_oids = [o["oi"] for o in lv.owners if o["cat"] == CAT_WATER]
        self.damage_oids = [o["oi"] for o in lv.owners if o["cat"] == CAT_DAMAGE]
        # drag currents: a push volume switched by the same driver as a link-driven damage volume counts as part of it
        dmg_drv = {tuple(lv.driver_of(oi, ("damage",))) for oi in self.damage_oids
                   if "damage" in lv.owners[oi]["driven"]} - {()}
        self.drag_oids = [o["oi"] for o in lv.owners if o["cat"] == CAT_PUSH and "pushEnable" in o["driven"]
                          and tuple(lv.driver_of(o["oi"], ("pushEnable",))) in dmg_drv]
        self.damage_oids += self.drag_oids
        self.water_vol = Volumes(lv, self.water_oids)
        self.damage_vol = Volumes(lv, self.damage_oids)
        self.dmg_present = {oi for oi in self.damage_oids if lv.owners[oi]["present"]}
        obst = Obstacles(lv, self.pairs, self.pmask, PROFILES["logic"]["floor_nz"])
        self.W = {"logic": Walk(lv, self.spans, "logic", self.water_vol, self.dmg_present, self.damage_vol, obst,
                                self.crumble)}

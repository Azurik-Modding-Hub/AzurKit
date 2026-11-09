"""A variant's recipe (``tools/characters/_player_variants.py``, Modkit's
Step 2.137 on): what it loads, what it refuses by name and what a build of
it wears. Modkit's ``test_player_variants.py``, its rows no other AzurKit
test, golden or facts entry pinned; a build goes through the product's
dress (``sdk._plan``, or ``characters.dressed`` where Modkit read the swap's
log, logic or plans)."""

from __future__ import annotations

import dataclasses
import json
import math
import re
import struct
import sys
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.core.xbr.nodes import named_resources
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_variants, mesh_edit, ports
from azurkit.tools.characters._player_variants import builtins, load_variants, recipe_sha

CHARACTERS, CONFIG = "gamedata/characters.xbr", "gamedata/config.xbr"

SPIN = {"generator": "t_spin", "length": 0.4, "turns": 2, "active": [0.1, 0.9],
        "box": {"centre": [0.0, 0.0, 0.8], "half": [0.78, 0.78, 0.8]}}
RECIPE = {"base": "town_female_2", "attacks": {"balance": False}, "markers": ["m_damage"],
          "clips": {"spin": SPIN}, "columns": {"basic1": "spin"}, "carry": ["basic1"]}
OP = {"op": "scale", "bone": "spine_2", "radius": [0.2, 0.2, 0.2], "factors": [1.5, 1.5, 1.5]}
SUB = {"op": "subdivide", "bone": "spine_2", "radius": [0.1, 0.1, 0.1], "edge": 0.01}
PUSH = {"op": "push", "bone": "spine_2", "dir": [0, 1, 0], "height": 0.1, "depth": 0.1,
        "radius": {"in": 0.1, "out": 0.1, "up": 0.1, "down": 0.1}}
TAPER = {"op": "taper", "bone": "root_joint", "factors": [0.9, 0.9], "plateau": 0.05, "half": 0.1, "reach": [0.2, 0.3]}
TUCK = {"op": "tuck", "groups": [1], "under": [4], "dir": [0, 1, 0], "margin": 0.003}
NAMED = {**PUSH, "name": "bust", "offset": [0.07, 0.15, 0.05], "mirror": True}
JIGGLE = {"frees": [{"group": 1, "bone": "joint19", "into": "left_foot_2"},
                    {"group": 4, "bone": "left_hand", "drop": True}],
          "bones": [{"role": "bust", "bone": "joint32", "parent": "spine_2", "shape": ["bust"], "groups": [1],
                     "takes": ["spine_2"], "weight": 0.5, "freq": 2, "damping": 0.1, "travel": 0.04, "turn": 0.3}]}
STAND = {"key": "characters/balthazar_spider/fx/fx_default", "trigger": "m_whirlwind_trigger", "hold": 1.5}
GLTF = {"file": "nowhere.glb", "sha256": "0" * 64}
HSPIN = {"generator": "hand_spin", "length": 1.4, "turns": 2, "tilt_deg": 85, "hand": "right_hand_endnode",
         "hand_z": 0.05, "plant": [0.15, 0.85], "active": [0.15, 0.85],
         "box": {"centre": [0.0, 0.0, 0.75], "half": [1.5, 1.5, 0.75]}}
BEAM = {"generator": "beam", "source": "attack_3", "length": 0.9, "switch": "m_balth_lightningswitch",
        "aim": "m_balth_lightning", "level_deg": 20.1, "box": {"from": 0.0, "to": 14.0, "half_width": 0.5, "z": [0, 2]}}
WHOOSH = {"generator": "whoosh", "length": 0.4, "swells": 4, "seed": 1, "columns": ["basic1"]}
JAB = {"generator": "gltf", "file": "jab.glb", "sha256": "0" * 64, "animation": "jab"}
HUE = {"op": "hsv", "hue": 120}


def _with(**changes) -> dict:
    """:data:`RECIPE` with ``changes`` laid over it (``None`` drops a field)."""
    recipe = json.loads(json.dumps(RECIPE))
    for key, value in changes.items():
        if value is None:
            recipe.pop(key)
        else:
            recipe[key] = value
    return recipe


def _id(said: str) -> str:
    return re.sub(r"\W+", "-", said).strip("-")[:60]


BLAST, NOVA = (builtins()["beamlord"].clips[c] for c in ("blast", "nova"))

# a recipe file's refusals at load: (its recipes, its source, the built-in names taken, said)
_LOAD_REFUSALS = [({n: r}, "test", taken, said) for r, n, taken, said in (
    (_with(colour=1), "booblord", (), "unknown key 'colour'"),
    (_with(base=None), "booblord", (), "missing 'base'"),
    (RECIPE, "Booblord", (), "lower-case letters"),
    (_with(mode="full"), "booblord", (), "full is retired"),
    (_with(size="huge"), "booblord", (), "size 'huge' is not one of"),
    (_with(attacks={"damage": float("nan")}), "booblord", (), "attacks.damage: nan is not a finite number"),
    (_with(attacks={"balance": "no"}), "booblord", (), "attacks.balance 'no' is not true or false"),
    (_with(clips={"spin": {**SPIN, "generator": "laser"}}), "booblord", (), "generator 'laser' is not one of"),
    (_with(clips={"spin": {k: v for k, v in SPIN.items() if k != "turns"}}), "booblord", (),
     "clips.spin: missing 'turns'"),
    (_with(clips={"spin": {**SPIN, "speed": 2}}), "booblord", (), "clips.spin: unknown key 'speed'"),
    (_with(clips={"spin": {**SPIN, "seek": "yes"}}), "booblord", (), "clips.spin.seek: 'yes' is not true or false"),
    (_with(clips={"spin": {"generator": "bake", "body": "barnacle", "clip": "walk"}}), "booblord", (),
     "clips.spin.body: 'barnacle' is no humanoid body the bake serves"),
    (_with(clips={"spin": {**SPIN, "length": 0}}), "booblord", (), "clips.spin.length: 0 must be above 0"),
    (_with(clips={"spin": {**HSPIN, "tilt_deg": 120}}), "booblord", (), "tilt_deg: 120 is outside (0, 90]"),
    (_with(clips={"spin": {**HSPIN, "plant": [0.9, 0.1]}}), "booblord", (), "plant: 0.9, 0.1 are not in order"),
    (_with(clips={"spin": {k: v for k, v in NOVA.items() if k != "switch_ramp"}}), "booblord", (),
     "switch_fade fades switch_ramp's switch out: give switch_ramp too"),
    (_with(clips={"spin": {**BLAST, "blast": {**BLAST["blast"], "dome_unit": 0}}}), "booblord", (),
     "clips.spin.blast.dome_unit: 0 must be above 0"),
    (_with(clips={"spin": {**BLAST, "blast": {**BLAST["blast"], "spin_deg": 360}}}), "booblord", (),
     "clips.spin.blast: unknown key 'spin_deg'"),
    (_with(columns={"roll forward": "spin"}), "booblord", (), "the roll keeps garret4's roll"),
    (_with(carry=["roll forward"]), "booblord", (), "the roll never moves with the stick"),
    (_with(held=["roll forward"]), "booblord", (), "held[0]: the roll never chains while held"),
    (_with(mode="garret4"), "booblord", (), "mode garret4 gives every column garret4's box and time"),
    (_with(fx=[{"record": 21, "name": "blastdome", "type": "transform", "inherit": 5}]), "booblord", (),
     "fx[0].inherit: 5 is not one of the decoded inherit modes 0, 1, 2, 3, 6"),
    (_with(fx=[{"record": 21, "name": "blastdome", "type": "transform", "anchor": "m root"}]), "booblord", (),
     "fx[0].anchor: 'm root' is not a marker name"),
    (_with(fx=[{"record": 22, "name": "blastdomeShape", "type": "platform", "material": {"blend": 1.5}}]),
     "booblord", (), "fx[0].material.blend: 1.5 is not a blend type"),
    (_with(fx=[{"record": 35, "name": "pRendererB2", "type": "pRendererB",
                "texture": {"recolor": {"ramp": [[0, 0, 0]]}}}]), "booblord", (),
     "fx[0].texture.recolor.ramp [[0, 0, 0]]: at least two colours"),
    (_with(fx_grafts=[{"template": "laser_wall", "parent": 5}]), "booblord", (),
     "fx_grafts[0].template: 'laser_wall' is not one of electric_shield, holder, force_field"),
    (RECIPE, "booblord", ("booblord",), "a built-in variant has that name"),
    (_with(voice="quiet"), "booblord", (), "voice 'quiet' is not one of own, silent"),
    (_with(sfx={"spin": {**WHOOSH, "generator": "laser"}}), "booblord", (),
     "sfx.spin: generator 'laser' is not one of whoosh"),
    (_with(sfx={"spin": {**WHOOSH, "columns": ["roll forward"]}}), "booblord", (),
     "the roll takes its first attack column's sound (D328)"),
    (_with(sfx={"spin": WHOOSH, "twirl": WHOOSH}), "booblord", (), "'basic1' plays sfx.spin already"),
    (_with(sfx={"spin": {**WHOOSH, "takes": 0}}), "booblord", (), "takes: 0 is not a whole number from 1 to 20"),
    (_with(sfx={"spin": {**WHOOSH, "takes": 21}}), "booblord", (), "takes: 21 is not a whole number from 1 to 20"),
    (_with(sfx={"spin": {**WHOOSH, "swells": 0}}), "booblord", (), "swells: 0 is not a whole number from 1"),
    (_with(sfx={"spin": {**WHOOSH, "length": 1e-6}}), "booblord", (), "sfx.spin.length: 1e-06 s makes no sample"),
    (_with(sfx={"hurt": WHOOSH}), "booblord", (), "'hurt' is a drop-in role"),
    (_with(sfx={"spin_a": WHOOSH}), "booblord", (), "not ending in _a .. _s"),
    (_with(sfx={"spin": WHOOSH}), "b" * 240, (), "is past the 255 characters 0x4B680 formats"),
    (_with(shouts={"files": ["hit.wav"]}), "b" * 240, (), "shouts: its key fx/sound/v/" + "b" * 240
     + "/shout_s is past the 255 characters 0x4B680 formats"),
    (_with(sounds="garret4", voice="silent"), "booblord", (), "voice, sfx, wavs and shouts need sounds own"),
    (_with(wavs={"wow": ["hit.wav"]}), "booblord", (), "wavs.wow: not a role; one of hurt"),
    (_with(wavs={"hurt": ["../hit.wav"]}), "booblord", (), "wavs.hurt[0]: '../hit.wav' is not a .wav file's name"),
    (_with(sfx={"fin": {"generator": "wav", "files": [], "columns": ["basic1"]}}), "booblord", (),
     "sfx.fin.files: [] is not a list of 1 to 20 WAV files"),
    (_with(mesh={"ops": [OP], "warp": 1}), "booblord", (), "mesh: unknown key 'warp'"),
    (_with(mesh={"ops": [{**OP, "op": "warp"}]}), "booblord", (), "mesh.ops[0].op 'warp' is not one of scale"),
    (_with(mesh={"ops": [{**OP, "factors": [2, 2]}]}), "booblord", (),
     "mesh.ops[0].factors: [2, 2] is not a list of 3 numbers"),
    (_with(mesh={"ops": [{**OP, "radius": [0, 1, 1]}]}), "booblord", (), "mesh.ops[0].radius[0]: 0 must be above 0"),
    (_with(mesh={"ops": [{**OP, "offset": [0, float("nan"), 0]}]}), "booblord", (),
     "mesh.ops[0].offset[1]: nan is not a finite number"),
    (_with(mesh={"gltf": {**GLTF, "sha256": "abc"}}), "booblord", (),
     "mesh.gltf.sha256: 'abc' is not 64 lower-case hex digits"),
    (_with(mesh={"ops": [{**PUSH, "dir": [0, 0, 0]}]}), "booblord", (), "mesh.ops[0]: dir is zero"),
    (_with(mesh={"ops": [{**PUSH, "dir": [0, 0, 1]}]}), "booblord", (), "dir is straight up or down"),
    (_with(mesh={"ops": [{**PUSH, "radius": {"in": 0.1, "out": 0.1, "up": 0.1}}]}), "booblord", (),
     "mesh.ops[0].radius: missing 'down'"),
    (_with(mesh={"ops": [{**PUSH, "fold": 2}]}), "booblord", (), "mesh.ops[0].fold: 2 must be from 0"),
    (_with(mesh={"ops": [TAPER | {"factors": [1.2, 0.9]}]}), "booblord", (),
     "mesh.ops[0].factors[0]: 1.2 must be above 0 and at most 1 (a taper narrows"),
    (_with(mesh={"ops": [TUCK | {"margin": -1}]}), "booblord", (), "mesh.ops[0].margin: -1 must be at least 0"),
    (_with(shapes={"bust": {"title": "Bust size", "ops": ["bust"]}}), "booblord", (),
     "shapes: a shape sizes the recipe's mesh ops, and it has no mesh"),
    (_with(mesh={"ops": [NAMED]}, shapes={"bust": {"title": "Bust size", "ops": ["chest"], "value": 1.2}}),
     "booblord", (), "shapes.bust.ops: the recipe's mesh has no op named 'chest' to size"),
    (_with(mesh={"ops": [NAMED]}, shapes={"bust": {"title": "Bust size", "ops": ["bust"], "value": 0.9}}),
     "booblord", (),
     "shapes.bust.ops: 'bust' is a push op, which has no size a shape scales (only round and scale ops)"),
    (_with(mesh={"ops": [{**OP, "name": "bust"}]},
           shapes={"bust": {"title": "Bust size", "ops": ["bust"], "value": float("nan")}}), "booblord", (),
     "shapes.bust.value: nan is not a finite number"),
    (_with(mesh={"ops": [{"op": "round", "bone": "spine_2", "origin": 0.05, "blend": 0.02, "radius": {
        "across": 0.1, "along": 0.1, "up": 0.1, "down": 0.1, "taper_low": [1, 0]}}]}), "booblord", (),
     "mesh.ops[0].radius.taper_low: [1, 0] must be [the share of across lost"),
    (_with(mesh={"ops": [{"op": "round", "bone": "spine_2", "origin": 0.05, "blend": 0.02, "radius": {
        "across": 0.1, "along": 0.1, "up": 0.1, "down": 0.1}, "behind": {"y": [0.02, 0.02]}}]}), "booblord", (),
     "mesh.ops[0].behind: y [0.02, 0.02] must be [full, none] apart"),
    (_with(mesh={"ops": [TUCK | {"band": [1.3, 1.2]}]}), "booblord", (), "mesh.ops[0].band: [1.3, 1.2] must rise"),
    (_with(mesh={"ops": [SUB | {"normals": "flat"}]}), "booblord", (),
     "mesh.ops[0].normals 'flat' is not area, angle or nearer"),
    (_with(mesh={"ops": [{"op": "thicken", "bone": "root_joint", "radius": [1, 1, 1], "depth": 0}]}),
     "booblord", (), "mesh.ops[0].depth: 0 must be above 0"),
    (_with(mesh={"ops": [{"op": "thicken", "bone": "root_joint", "radius": [1, 1, 1], "depth": 0.006,
                          "taper": -0.01}]}), "booblord", (), "mesh.ops[0].taper: -0.01 must be 0 or above"),
    (_with(mesh={"ops": [TUCK | {"under": []}]}), "booblord", (),
     "mesh.ops[0].under: [] is not a list of mesh group indices"),
    (_with(arms={"out_deg": "4"}), "booblord", (), "arms.out_deg: '4' is not a finite number"),
    (_with(jiggle=JIGGLE), "booblord", (), "jiggle: its shapes are mesh ops by name, and the recipe has no mesh"),
    (_with(lods={"shadow": True}), "booblord", (), "lods.shadow: a shadow LOD is cut from the recipe's mesh"),
    (_with(lods={"shadow": -1}, mesh={"ops": [OP]}), "booblord", (), "lods.shadow -1.0 is no share of LOD 0's"),
    (_with(lods={"ratio": [0.3], "at": [9]}), "booblord", (),
     "lods.ratio: LODs are cut from the recipe's mesh, and it has none (they would grow a vanilla body"),
    (_with(lods={"ratio": [0.5, 0.4, 0.3, 0.2, 0.1], "at": [1, 2, 3, 4, 5]}, mesh={"ops": [OP]}), "booblord", (),
     "lods.ratio: 5 LODs past LOD 0, and the game switches among at most 4 (lodThreshold1-4, 0x3EE73)"),
    (_with(lods={"ratio": [1.5], "at": [9]}, mesh={"ops": [OP]}), "booblord", (),
     "lods.ratio[0] 1.5 is no share of LOD 0's triangles (above 0, at most 1)"),
    (_with(lods={"ratio": [0.3, 0.1], "at": [9]}, mesh={"ops": [OP]}), "booblord", (),
     "lods.at [9] is not a list of 2 switch distances (m), one a LOD of lods.ratio"),
    (_with(lods={"ratio": [0.3], "at": [float("inf")]}, mesh={"ops": [OP]}), "booblord", (),
     "lods.at[0]: inf is not a finite number"),
    (_with(lods={"ratio": [0.3], "at": [9], "shadow": True}, mesh={"ops": [OP]}), "booblord", (),
     "lods.shadow: with LODs of its own the realtime shadow draws their LOD 1 (0x3E8B1)"),
    (_with(mesh={"ops": [PUSH]}, jiggle={**JIGGLE, "frees": [{"group": 1, "bone": "joint19"}]}), "booblord", (),
     "jiggle.frees[0]: either into (its parent) or drop: true"),
    (_with(mesh={"ops": [PUSH]}, jiggle={**JIGGLE, "bones": [{**JIGGLE["bones"][0], "damping": -1}]}),
     "booblord", (), "jiggle.bones[0].damping: -1 must be at least 0"),
    (_with(fx_ring={"slots": 0}), "booblord", (), "fx_ring.slots: 0 is not a count of 1 to 12"),
    (_with(fx_ring={"stand": {**STAND, "rise": 0.8}}), "booblord", (), "fx_ring.stand: unknown key 'rise'"),
    (_with(fx_ring={"stand": {**STAND, "hold": -1}}), "booblord", (),
     "fx_ring.stand.hold: -1 s is not from 0 to 65.535 s"),
    (_with(fx_ring={"stand": {**STAND, "fx": [{"record": 217, "name": "x", "type": "pRendererB"}]}}),
     "booblord", (), "fx_ring.stand.fx[0]: neither set, links"),
    (_with(clips={"spin": {**JAB, "active": [0.3, 0.45]}}), "booblord", (),
     "clips.spin: active and box come together"),
    (_with(clips={"spin": {**JAB, "rate": 0}}), "booblord", (), "clips.spin.rate: 0 must be above 0"),
    (_with(weapon="Big Stick"), "booblord", (), "weapon 'Big Stick' is not a weapon's name"),
    (_with(weapon="farmers_hoe"), "booblord", (),
     "weapon farmers_hoe plays every attack column, so the recipe names no clips or columns or carry"),
    (_with(effects=[{"template": "comet", "columns": ["basic1"]}]), "booblord", (),
     "effects[0].template: 'comet' is not one of fireball, ice_shard, arrow"),
    (_with(effects=[{"template": t, "columns": [c]} for t, c in
                    (("bubble", "basic1"), ("dome", "basic2"), ("laser", "basic3"), ("bolts", "finish"))]),
     "booblord", (), "effects[3]: a 4th shield or beam row: X38's table holds 3 bound keys"),
    (_with(effects=[{"template": "fireball", "columns": ["basic1"], "spin": 2}]), "booblord", (),
     "effects[0]: unknown key 'spin'"),
    (_with(effects=[{"template": "fireball", "columns": ["basic1"], "seek": 1}]), "booblord", (),
     "effects[0].seek: 1 is not true or false"),
    (_with(effects=[{"template": "bubble", "columns": ["basic1"], "seek": True}]), "booblord", (),
     "effects[0].seek: a shield plays on the body; only a projectile row's throw seeks"),
    (_with(effects=[{"template": "fireball", "columns": ["basic1"], "speed": float("inf")}]), "booblord", (),
     "effects[0].speed: inf is not a finite number"),
    (_with(effects=[{"template": "fireball", "columns": ["roll forward"]}]), "booblord", (),
     "effects[0].columns[0]: the roll throws nothing"),
    (_with(effects=[{"template": "fireball", "columns": ["basic1"]},
                    {"template": "arrow", "columns": ["basic2"]}]), "booblord", (),
     "effects[1]: a second projectile row: X42 throws one species a build, debug (W30)"),
    (_with(idles={"idle": "spin", "idle_7": "spin"}), "booblord", (), "idles.idle_7: no idle slot"),
    (_with(idles={"idle": "spin", "idle_3": "talk"}), "booblord", (), "idles.idle_3 without idle_2"),
    (_with(idles={"idle": "spin", "wait": [30, 21]}), "booblord", (), "idles.wait: 30, 21 are not low <= high"),
    (_with(idles={"idle": "spin", "wait": [float("nan"), 1]}), "booblord", (),
     "idles.wait[0]: nan is not a finite number"),
    (_with(idles={"idle": "spin", "wait": [21, 1e39]}), "booblord", (), "idles.wait[1]: 1e+39 is outside a float32"),
    (_with(idles={"wait": [21, 30]}), "booblord", (), "idles: names no slot"),
    (_with(mode="garret4", clips=None, columns=None, carry=None, markers=None, idles={"idle": "idle"}),
     "booblord", (), "idles: mode garret4 plays garret4's slots"),
    (_with(texture_scale=3), "booblord", (), "texture_scale 3 is not a power of two of at least 1"),
    (_with(texture_scale=2), "booblord", (), "texture_scale: a texture is baked through the recipe's mesh"),
    (_with(colours=[{"row": 1, "size": 128, "ops": [HUE]}]), "booblord", (),
     "colours[0]: size: a colour keeps its texture's size and format"),
    (_with(colours=[{"ops": [{"op": "skin", "hue": [0, 30]}]}]), "booblord", (),
     "colours[0].ops[0].op 'skin' is a textures op, baked through a mesh: colours are hsv and swap"),
    (_with(colours=[{"ops": [HUE | {"bone": "head"}]}]), "booblord", (),
     "colours[0].ops[0]: bone: a colour has no region (no mesh to select by)"),
    (_with(colours=[{"ops": [{"op": "swap", "from": [0.5, 0.5, 0.5], "to": [1, 0, 0]}]}]), "booblord", (),
     "colours[0].ops[0].from: [0.5, 0.5, 0.5] is a grey, which has no hue to swap"),
    (_with(colours=[{"ops": [HUE | {"sat": float("nan")}]}]), "booblord", (),
     "colours[0].ops[0].sat: nan is not a finite number"),
    (_with(colours=[{"ops": [HUE | {"spread": 0.3}]}]), "booblord", (),
     "colours[0].ops[0].spread: a hue spread is about a window's middle: give the window"),
    (_with(colours=[{"row": 1, "ops": [HUE]}, {"row": 1, "ops": [HUE]}]), "booblord", (),
     "colours[1].row 1 is not a material row (each once"),
    (_with(victory_cancel="soon"), "tossy", (), "victory_cancel: 'soon' is not a finite number"),
    (_with(slots={"hover": "walk"}), "tspin", (), "slots.hover: not a slot a recipe fills (walk, run, walk_backwards"),
    (_with(slots={"idle": "walk"}), "tspin", (), "slots.idle: an idle slot; idles names those"),
    (_with(slots={"walk": "walk"}), "tspin", (), "slots.walk_backwards: missing; walk_backwards plays at walk's cell"),
    (_with(mode="garret4", clips=None, columns=None, carry=None, markers=None, slots={"victory_1": "talk"}), "tspin",
     (), "slots: mode garret4 plays garret4's slots"))] + [(doc, "test", (), said) for doc, said in (
    ({"high": {"from": "nobody"}}, "from 'nobody' names no other recipe of its file nor a built-in"),
    ({"higher": {"from": "booblord_high"}}, "from 'booblord_high', which is from 'booblord': a recipe is from one that "
     "is from none"),
    ({"low": RECIPE, "mid": {"from": "low"}, "high": {"from": "mid"}},
     "from 'mid', which is from 'low': a recipe is from one that is from none"),
    ({"low": RECIPE, "high": {"from": "low", "scale": 2}},
     "scale: a recipe from another lays over only its title, notes, texture_scale"),
    ({"low": RECIPE, "high": {"from": "low", "mesh_ops": [SUB]}}, "mesh_ops: 'low' has no mesh to add them to"),
    ({"low": RECIPE | {"mesh": {"ops": [OP]}}, "high": {"from": "low", "mesh_ops": []}},
     "mesh_ops [] is not a list of mesh ops"),
    ({"low": RECIPE | {"mesh": {"ops": [OP]}}, "high": {"from": "low", "mesh_ops": [SUB, OP]}},
     "mesh_ops[1].op 'scale': a recipe from another adds only subdivide and thicken ops (its shape"),
    ({"low": RECIPE | {"mesh": {"ops": [OP]}}, "high": {"from": "low", "mesh_ops": [{"over": "x"}]}},
     "mesh_ops[0].over 'x': lays only sides, rings over the one tube of 'low''s mesh"),
    ({"low": RECIPE | {"mesh": {"ops": [OP]}}, "high": {"from": "low", "texture_ops": [{"row": 1, "ops": []}]}},
     "texture_ops[0]: a {row, ops} adding paint ops to a row 'low''s"),
    ({"low": RECIPE, "high": {"from": "low", "shapes": {"bust": {"value": 1.2}}}},
     "shapes.bust: a recipe from 'low' lays only a value over a shape it declares (none)"))] + [
    ({"booblord": _with(mesh={"gltf": GLTF})}, "built-in", (), "mesh.gltf: a built-in takes no glTF")]


@pytest.mark.parametrize("recipes, source, taken, said", _LOAD_REFUSALS,
                         ids=[_id(said) for *_, said in _LOAD_REFUSALS])
def test_a_recipe_that_cant_build_fails_by_name(recipes, source, taken, said):
    """D35 (Modkit's Step 2.137 on): a recipe file fails by name at load,
    before any image is read: a key no recipe has, a missing base, a name
    the CLI can't take, a retired mode or unknown size, a number that isn't
    finite (D23: never clamped), a switch that isn't true or false, an
    unknown generator or a parameter of it missing, unknown or 0, a hand
    spin's tilt or plant out of range, the roll in its columns, carry or
    held, mode garret4 with authored clips, a user's name a built-in has;
    an fx edit's inherit, anchor, blend or ramp; its sounds, WAVs, mesh ops,
    shapes, jiggle, LODs, fx ring, weapon, effects rows, idles, slots,
    texture scale, colours and victory cancel each out of what they hold;
    and a ``from`` that names no recipe, chains, lays over more than its
    labels, or adds what its parent can't take. A built-in (``built-in``)
    takes no glTF."""
    with pytest.raises(ValueError) as caught:
        load_variants(json.dumps(recipes), source, taken)
    assert said in str(caught.value)


def _planned(usa_iso, folder: Path, recipe: dict, name: str = "tspin", packs: dict | None = None, **given):
    """``recipe`` as ``name`` in a recipe file in ``folder``, worn (``given``: the character's other fields) in a
    build of the USA image planned through ``sdk._plan`` (``packs``: its packs, none by default): its plan."""
    file = folder / f"{name}.json"
    file.write_text(json.dumps({name: recipe}), encoding="utf-8")
    return sdk._plan({"iso": str(usa_iso), "packs": packs or {},
                      "character": {"species": name, "variant_file": str(file), **given}})


# a recipe's refusals at build: (the recipe, its name, the character's other fields, said)
_BUILD_REFUSALS = (
    (_with(base="jellyfish"), "tspin", {}, "'jellyfish': it has no body"),
    (_with(mesh={"ops": [{**OP, "name": "chest"}]}, shapes={"chest": {"title": "Chest size", "ops": ["chest"],
                                                                    "value": 3}}), "tspin", {},
     "(a variant of town_female_2) at Chest size 3: mesh.ops fold the surface"),
    (RECIPE, "keylord", {}, "a species has that name ('keylord')"),
    (_with(columns={"basic9": "spin"}), "tspin", {}, "columns.basic9: no such attacks_anims column"),
    (_with(held=["basic9"]), "tspin", {}, "held: 'basic9' is no attacks_anims column"),
    (_with(columns={"basic1": "attack_7"}), "tspin", {}, "'attack_7' is neither a clip of the recipe"),
    (_with(markers=["m_feet", "m_damage"]), "tspin", {}, "markers: 'm_feet' is one of townspeople/female_2's"),
    (_with(markers=["m_wing"]), "tspin", {}, "markers: garret4 has no 'm_wing' to grow"),
    (_with(marker_source="nobody"), "tspin", {}, "marker_source: characters.xbr has no body 'nobody'"),
    (_with(markers=None), "tspin", {}, "t_spin: townspeople/female_2 has no m_damage"),
    (_with(clips={"spin": {**HSPIN, "hand": "tail"}}), "tspin", {}, "rig has no bone 'tail'"),
    (_with(clips={"spin": BEAM}), "tspin", {}, "beam: townspeople/female_2 has no marker 'm_balth_lightning"),
    (_with(base="balthazar", markers=None, carry=None, clips={"spin": {**BEAM, "switch": "m_lifedrainswitch"}}),
     "tspin", {}, "beam: attack_3's m_lifedrainswitch never reaches 0.5"),
    (_with(base="balthazar", markers=None, carry=None, clips={"spin": BEAM}, fx=[
        {"record": 17, "name": "pSinkShape1", "type": "pSink", "set": {"maxAge": 1.0}}]), "tspin", {},
     "fx[0]: record 17 of characters/balthazar_airship/fx/fx_default is 'pEmitterShape1' (pEmitter)"),
    (_with(base="balthazar", markers=None, carry=None, clips={"spin": BEAM}, fx=[
        {"record": 17, "name": "pEmitterShape1", "type": "pEmitter", "set": {"glow": 1.0}}]), "tspin", {},
     "fx[0]: a pEmitter has no attribute 'glow'"),
    (_with(base="balthazar", markers=None, carry=None, clips={"spin": BEAM}, fx=[
        {"record": 16, "name": "m_balth_lightningswitch", "type": "transform",
         "links": [{"index": 3, "weight": 1.0}]}]), "tspin", {},
     "fx[0].links[0]: record 16 (m_balth_lightningswitch) has 3 links"),
    (_with(base="balthazar", markers=None, carry=None, clips={"spin": BEAM}, fx=[
        {"record": 16, "name": "m_balth_lightningswitch", "type": "transform",
         "links": [{"index": 0, "dst_plug": "glow"}]}]), "tspin", {},
     "fx[0].links[0].dst_plug: a pEmitter has no attribute 'glow'"),
    (_with(base="balthazar", markers=None, carry=None, clips={"spin": BEAM}, fx=[
        {"record": 21, "name": "blastdome", "type": "transform", "material": {"opacity": 1.0}}]), "tspin", {},
     "fx[0].material: a transform isn't a platform"),
    (RECIPE, "tspin", {"mode": "garret4"}, "--player-character-mode garret4: the variant 'tspin' is mode own"),
    (RECIPE, "tspin", {"size": "garret4"}, "--player-character-size garret4: the variant 'tspin' is size own"),
    (RECIPE, "tspin", {"attack_balance": True},
     "--player-attack-balance on: the variant 'tspin' is balance off"),
    (_with(sfx={"spin": {**WHOOSH, "columns": ["basic9"]}}), "tspin", {},
     "sfx.spin.columns: 'basic9' is no attacks_anims column"),
    (_with(base="balthazar", markers=None, carry=None, clips={}, columns={}, voice="silent"), "tspin", {},
     "its base balthazar has sounds of its own"),
    (_with(wavs={"hurt": ["nowhere.wav"]}), "tspin", {}, "wavs.hurt[0]: no such file nowhere.wav"),
    (_with(mesh={"ops": [{**OP, "bone": "chest"}]}), "tspin", {},
     "mesh.ops[0].bone: townspeople/female_2 has no bone 'chest'"),
    (_with(mesh={"keep": ["sash"], "ops": [OP]}), "tspin", {}, "mesh.keep: townspeople/female_2 has no bone 'sash'"),
    (_with(base="balthazar", markers=None, carry=None, clips={}, columns={"basic1": "attack_3"}, fx_ring={
        "arm": [{"record": 24, "name": "pEmitterShape1", "set": {"emitRate": 1.0}}]}), "tspin", {},
     "fx_ring.arm[0]: record 24 of characters/balthazar_airship/fx/fx_default is 'pBurstEmitterShape1', not"),
    (_with(base="balthazar", markers=None, carry=None, clips={}, columns={"basic1": "attack_3"},
           fx_ring={"stand": STAND}), "tspin", {},
     "fx_ring.stand.trigger: characters/balthazar_spider/fx/fx_default binds no marker 'm_whirlwind_trigger' "
     "of balthazar_airship"),
    (_with(fx_ring={"stand": {**STAND, "fx": [{"record": 217, "name": "funnel", "type": "pRendererB",
                                               "set": {"alpha1": 1.0}}]}}), "tspin", {},
     "fx_ring.stand.fx[0]: record 217 of characters/balthazar_spider/fx/fx_default is "
     "'single_tornado2_pRendererB1' (pRendererB), not 'funnel'"),
    (_with(mesh={"ops": [{**OP, "mirror": True}]}), "tspin", {}, "mesh.ops[0].mirror: its centre is on x = 0"),
    (_with(mesh={"ops": [{**OP, "factors": [9, 9, 9]}]}), "tspin", {}, "mesh.ops fold the surface at"),
    (_with(mesh={"gltf": GLTF}), "tspin", {}, "mesh.gltf.file 'nowhere.glb': no such file"),
    (_with(mesh={"ops": [{**PUSH, "groups": [9]}]}), "tspin", {},
     "mesh.ops[0].groups: townspeople/female_2 has no LOD-0 group 9"),
    (_with(mesh={"ops": [OP, TUCK | {"under": [1]}]}), "tspin", {}, "a layer can't tuck behind itself"),
    (_with(mesh={"ops": [NAMED]}, jiggle={**JIGGLE, "bones": [{**JIGGLE["bones"][0], "bone": "spine_3"}]}),
     "tspin", {}, "jiggle.bones[0].bone 'spine_3' has a child or weights a vertex"),
    (_with(mesh={"ops": [NAMED]}, jiggle={**JIGGLE, "loops": ["swim_9"]}), "tspin", {},
     "jiggle.loops: townspeople/female_2 has no clip 'swim_9'"),
    (_with(mesh={"ops": [NAMED]}, jiggle={**JIGGLE, "loops": ["touchdown"],
                                         "still": ["idle", "listen", "sit", "talk"]}), "tspin", {},
     "g4/touchdown: jiggle.loops names it, but it doesn't end where it starts"),
    (_with(clips={"spin": JAB}), "tspin", {}, "columns.basic1: clips.spin has no box, and its animation 'jab' is "
     "no clip of townspeople/female_2's"),
    (_with(weapon="sword", clips=None, columns=None, carry=None), "tspin", {},
     "the recipe's weapon sword: no such weapon (one of default, own, "),
    (_with(effects=[{"template": "fireball", "columns": ["basic2"]}]), "tspin", {},
     "its fireball row and the bare-hands kit's vase throw: X42 throws one species a build (debug, W30)"),
    (_with(effects=[{"template": "arrow", "columns": ["basic9"]}], base="keylord", markers=None, clips=None,
           columns=None, carry=None), "tspin", {}, "its arrow row: columns: 'basic9' is no attacks_anims column"),
    (_with(effects=[{"template": "arrow", "columns": ["basic1"], "size": 0}], base="keylord", markers=None, clips=None,
           columns=None, carry=None), "tspin", {}, "its arrow row: size 0 draws nothing (debug's scale would be 0)"),
    (_with(effects=[{"template": "bubble", "columns": ["basic1"]}], fx_ring=False, base="keylord", markers=None,
           clips=None, columns=None, carry=None), "tspin", {},
     "its bubble row plays on X38's ring, which its recipe's fx_ring false turns off"),
    (_with(effects=[{"template": "dome", "columns": ["basic1"], "fade": 70}], base="keylord", markers=None,
           clips=None, columns=None, carry=None), "tspin", {},
     "fade 70 s is not from 0 to 65.535 s (the table holds ms in 16 bits)"),
    (_with(idles={"idle": "nap"}), "tspin", {},
     "idles.idle: 'nap' is neither a clip of the recipe nor one of townspeople/female_2's"),
    (_with(clips={"spin": SPIN, "turn": {**SPIN, "turns": 0.25}}, idles={"idle": "turn"}), "tspin", {},
     "idles.idle: v/turn doesn't end where it starts"),
    (_with(clips={"spin": SPIN, "bow": {"generator": "bake", "body": "townspeople/male_1", "clip": "jump"}}), "tspin",
     {}, "body 'townspeople/male_1' has no clip 'jump'"),
    ({"base": "catalisk", "clips": {"jump": {"generator": "bake", "body": "garret4", "clip": "jump"}}}, "tspin", {},
     "bake: catalisk is no humanoid body the bake serves"),
    (_with(slots={"jump": "spin"}), "tspin", {}, "slots.jump: v/spin keys m_damage above 0, which a jump never does"),
    (_with(slots={"victory_1": "strut"}), "tspin", {},
     "slots.victory_1: 'strut' is neither a clip of the recipe nor one of townspeople/female_2's"),
    (_with(clips={"spin": SPIN, "turn": {**SPIN, "turns": 0.25}}, slots={"run": "turn", "run_backwards": "turn"}),
     "tspin", {}, "slots.run: v/turn doesn't end where it starts"),
    (_with(slots={"run": "idle", "run_backwards": "idle"}), "tspin", {},
     "slots.run: idle plants no foot that moves back (at least 0.05 of its height a second)"),
    (_with(slots={"victory_1": "spin"}), "tspin", {},
     "slots.victory_1: v/spin keys m_damage above 0, which a victory never"))


@pytest.mark.parametrize("recipe, name, given, said", _BUILD_REFUSALS, ids=[_id(said) for *_, said in _BUILD_REFUSALS])
def test_a_recipe_that_cant_build_fails_by_name_at_build(usa_iso, tmp_path, recipe, name, given, said):
    """D35 (Modkit's Step 2.137 on): a recipe that loads but can't be
    worn fails by name before any image is written: a base the swap can't
    wear, a name a species has, a column, held column or sound column
    attacks_anims lacks, a clip neither the recipe's nor the base's, a
    marker the body has or garret4 lacks, a marker source the archive
    lacks, a spin with no m_damage, a hand spin on a bone the rig lacks, a
    beam on a body without its markers or on a switch its clip never turns
    on, an fx edit whose record has another name or type or an attribute,
    link or plug it lacks, a material on what isn't a platform, a mode,
    size or balance given beside a variant that isn't its recipe's, voice
    on a base with sounds of its own, a WAV or glTF that isn't there, a
    mesh op on a bone or group the body lacks, a mirror on x = 0, ops that
    fold it (a shape's value too), a tuck behind its own layer, a jiggle
    bone with a child or a loop the body lacks or that doesn't end where it
    starts, a ring edit or stand trigger its graph lacks, a weapon that
    isn't one, an effects row beside the kit's throw, on no column, of size
    0, on a ring turned off or fading past 16 bits of ms, an idle, gait or
    victory clip that doesn't loop, plant or stay harmless, and a bake from
    a clip its body lacks or onto a body it doesn't serve."""
    with pytest.raises(ValueError) as caught:
        _planned(usa_iso, tmp_path, recipe, name, **given)
    assert said in str(caught.value)


def test_a_bodys_own_load_runs_past_the_budgets_line_fail_naming_its_mib(usa_iso, tmp_path, monkeypatch):
    """D491 (Modkit's Step 2.158; 2.162b, D515): a body whose own load runs
    pass the budget's line fails naming its MiB, the line moved by the
    budget the built default.xbe holds (qol_memory_budget at 41 MiB, a layer
    before the character's): 1 MiB up at 41, under the one 42 MiB gives."""
    from azurkit.tools.characters import model_inspect

    monkeypatch.setattr(model_inspect, "OWN_ERROR", 1 << 20)
    with pytest.raises(ValueError) as caught:
        _planned(usa_iso, tmp_path, RECIPE, packs={"qol_memory_budget": {"budget_mib": 41.0}})
    assert re.search(r"--player-character 'tspin': its own load runs, 2\.\d\d MiB \(banm .*\), pass the 2 MiB the "
                     r"game's 41 MiB budget .*; make its mesh or clips smaller, or set qol_memory_budget to 42 MiB "
                     r"\(line 3 MiB\)", str(caught.value))


def test_a_recipe_from_several_takes_the_first_with_each_others_fields_laid_over_it():
    """D751 (Modkit's Step 2.170d): ``from`` a list of recipes each from
    the same one takes the first as it builds with each other's own fields
    laid over it in turn, then its own, so each look stays defined once; it
    is from their one (its files, fit and jiggle places); a list that can't
    say where a field comes from fails by name. From one (Steps 2.170b,
    2.177b, 2.177d): its colours load with no mesh and lay over that one's,
    its ``mesh_ops`` follow that one's ops (a thicken too, a tube's rings laid
    over its own) and its ``texture_ops`` follow its row's paint ops."""
    low = RECIPE | {"mesh": {"ops": [OP]}}
    high = {"from": "low", "title": "High", "texture_scale": 2, "mesh_ops": [SUB]}
    human = {"from": "low", "title": "Human", "colours": [{"row": 1, "ops": [HUE]}]}
    doc = {"low": low, "high": high, "human": human, "both": {"from": ["high", "human"], "title": "Both"}}
    got, parent = _player_variants.recipe_of(doc, "both", "test")
    assert parent == "low" and got == _player_variants.recipe_of(doc, "high", "test")[0] | {
        "title": "Both", "colours": human["colours"]}
    loaded = load_variants(json.dumps(doc), "test")
    both = loaded["both"]
    assert (both.files, both.texture_scale, both.mesh, both.colours) == (
        "low", 2, loaded["high"].mesh, loaded["human"].colours) and both.sha not in (loaded["high"].sha,
                                                                                    loaded["human"].sha)
    for extra, said in (({"both": {"from": ["high"]}}, "from ['high']: a recipe from several names two or more"),
                        ({"both": {"from": ["high", "high"]}}, "names two or more other recipes, each once"),
                        ({"both": {"from": ["high", "both"]}}, "names two or more other recipes, each once"),
                        ({"both": {"from": ["high", "nobody"]}}, "from 'nobody' names no other recipe of its file"),
                        ({"both": {"from": ["high", "low"]}},
                         "from 'low', which is from None: a recipe from several is from recipes each from one"),
                        ({"low2": RECIPE, "other": {"from": "low2"}, "both": {"from": ["high", "other"]}},
                         "which are from ['low', 'low2']: a recipe from several is from recipes each from the same"),
                        ({"mid": {"from": "high"}, "both": {"from": ["human", "mid"]}},
                         "from 'high', which is from 'low': a recipe is from one that is from none"),
                        ({"wide": {"from": "low", "texture_scale": 4}, "both": {"from": ["high", "wide"]}},
                         "texture_scale: laid over 'low''s by both 'high' and 'wide': a recipe from several takes "
                         "each field from one of them"),
                        ({"one": {"from": "both"}}, "from 'both', which is from ['high', 'human']: a recipe is from "
                         "one that is from none"),
                        ({"both": {"from": ["high", "human"], "scale": 2}},
                         "scale: a recipe from another lays over only")):
        with pytest.raises(ValueError, match=re.escape(said)):
            load_variants(json.dumps(doc | extra), "test")
    high, human, both = (builtins()[n] for n in ("booblord_high", "booblord_human", "booblord_high_human"))
    assert [f.name for f in dataclasses.fields(both) if getattr(both, f.name) != getattr(high, f.name)] == [
        "name", "title", "notes", "sha", "colours"] and both.colours == human.colours and both.files == "booblord"
    # from one: colours with no mesh, laid over that one's
    plain = load_variants(json.dumps({"low": _with(colours=[{"ops": [HUE]}]), "high": {
        "from": "low", "colours": [{"row": 1, "ops": [HUE | {"window": [200, 240]}]}]}}), "test")
    assert plain["low"].mesh is None and [(c.row, [o.op for o in c.ops]) for c in plain["low"].colours] == [
        (None, ["hsv"])]
    assert plain["high"].colours[0].row == 1 and plain["high"].colours[0].ops[0].numbers["window"] == (200.0, 240.0)
    low = RECIPE | {"mesh": {"keep": ["vase_joint"], "ops": [OP]}}
    got, _ = _player_variants.recipe_of({"low": low, "high": {"from": "low", "mesh_ops": [SUB]}}, "high", "test")
    assert got["mesh"] == {"keep": ["vase_joint"], "ops": [OP, SUB]} and "mesh_ops" not in got
    tube, thick = {"op": "tube", "name": "tail", "sides": 32}, {"op": "thicken", "depth": 0.006}
    paint = {"row": 1, "size": 512, "ops": [{"op": "fill"}]}
    got, _ = _player_variants.recipe_of({"low": low | {"mesh": {"ops": [OP, tube]}, "textures": [paint]}, "high": {
        "from": "low", "mesh_ops": [thick, {"over": "tail", "sides": 64}], "texture_ops": [
            {"row": 1, "ops": [{"op": "sharpen"}]}]}}, "high", "test")
    assert got["mesh"]["ops"] == [OP, tube | {"sides": 64}, thick]
    assert got["textures"] == [paint | {"ops": [{"op": "fill"}, {"op": "sharpen"}]}] and "texture_ops" not in got


def test_a_recipes_sha_is_what_it_builds_with_its_weapon_and_no_built_in_is_a_species(usa_iso):
    """Modkit's Steps 2.137 and 2.161b: a label edit and the sounds keep a
    recipe's sha (its grade), a scale changes it; its weapon is played, so it
    is in the sha and loads by name, and a weapon ``default`` or ``own`` is
    the recipe's own moveset, keeping its clips; no built-in is named as a
    species (config.xbr's critters_engine columns)."""
    assert (recipe_sha(_with(title="Spinner", notes="any", voice="silent", sfx={"spin": WHOOSH}))
            == recipe_sha(RECIPE) != recipe_sha(_with(scale=1.1)))
    hoe = load_variants(json.dumps({"tspin": _with(weapon="farmers_hoe", clips=None, columns=None, carry=None)}),
                        "test")["tspin"]
    assert hoe.weapon == "farmers_hoe" and len({recipe_sha(RECIPE), hoe.sha,
                                                recipe_sha(_with(weapon="bare_hands"))}) == 3
    assert all(load_variants(json.dumps({"tspin": _with(weapon=w)}), "test")["tspin"].clips for w in ("default", "own"))
    with iso.Reader(usa_iso) as r:
        engine = ports.XbrDocument.from_bytes(r.read(CONFIG)).keyed_section("critters_engine")
    assert not set(builtins()) & set(engine.col_names())


def test_a_shape_at_one_keeps_a_recipes_mesh_and_sha_and_another_value_sizes_only_the_ops_it_names():
    """D455 (Modkit's Step 2.164b): booblord declares Bust size, Hip width
    and Butt size (booblord_high takes them from her), each at 1.0: her sha
    is her recipe's without them, her mesh as written, and at 1.0 the
    shape is her. Another value sizes only the ops its shape names: a
    round's across and along half axes and origin times the value (up and
    down kept; a pair's origin on x = 0, only its height moving), a scale's
    factors on the axes it scales; above 1 her Butt size turns her back sash
    flaps out; below 1 her Hip width sizes her pelvis's scale too; the build
    is another (another sha) whose arm fit and jiggle places are her
    unshaped build's (``fit_sha``, ``plain``)."""
    from azurkit.tools.characters._player_variants import BUILTIN, fit_sha, reshaped

    her = builtins()["booblord"]
    written = json.loads(BUILTIN.read_text(encoding="utf-8"))["booblord"]
    assert recipe_sha({k: v for k, v in written.items() if k != "shapes"}) == her.sha and her.plain is None
    assert [(s.name, s.title, s.value) for s in builtins()["booblord_high"].shapes] == [
        ("bust", "Bust size", 1.0), ("hips", "Hip width", 1.0), ("butt", "Butt size", 1.0)]
    assert reshaped(her, {"bust": 1.0, "butt": 1.0}) is her
    sized = reshaped(her, {"bust": 1.3, "hips": 0.8})
    assert (sized.sha != her.sha, sized.unshaped, fit_sha(sized), sized.plain) == (True, her.sha, her.sha, her.mesh)
    changed = [(a, b) for a, b in zip(her.mesh.ops, sized.mesh.ops) if a != b]
    assert sorted(a.name for a, _ in changed) == ["breast right", "breast right", "hip bone right", "hip right",
                                                  "pelvis"]
    (pelvis, narrowed), = [(a, b) for a, b in changed if a.name == "pelvis"]
    assert narrowed.factors == pytest.approx((pelvis.factors[0] * 0.8, 1.0, 1.0))
    wider = reshaped(her, {"hips": 1.2}).mesh.ops
    assert sorted(a.name for a, b in zip(her.mesh.ops, wider) if a != b) == ["hip bone right", "hip right"]
    changed = [(a, b) for a, b in changed if a.name != "pelvis"]

    def origin(op):   # its rays' origin less the bone's
        n = mesh_edit.push_frame(op.direction)[0]
        return tuple(o - op.origin * k for o, k in zip(op.offset, n))
    for a, b in changed:
        x = 1.3 if a.name == "breast right" else 0.8
        kept, fall = origin(a), mesh_edit.push_frame(a.direction)[0][2]
        assert (*b.radius, b.origin, b.inward, *origin(b)) == pytest.approx((
            a.radius[0] * x, a.radius[1] * x, a.radius[2], a.radius[3], a.origin * x, a.inward,
            kept[0] * x if a.pair else kept[0], kept[1], kept[2] - (x - 1) * a.origin * fall))
    turns = {v: [(p.clip, p.bone, p.axis, p.window) for p in reshaped(her, {"butt": v}).poses if p.clip == ""]
             for v in (1.0, 0.8, 1.3)}
    (turn,) = [p for p in reshaped(her, {"butt": 1.3}).poses if p.clip == ""]
    per = written["shapes"]["butt"]["turns"][0]["deg"]
    assert (turns[1.0], turns[0.8], turns[1.3], turn.deg) == (
        [], [], [("", "loincloth_back_1", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))], pytest.approx(per * 0.3))


def _vanilla_characters(usa_iso) -> bytes:
    with iso.Reader(usa_iso) as r:
        return r.read(CHARACTERS)


def test_a_pose_turns_its_bone_over_its_window_only(usa_iso):
    """D438 (Modkit's Step 2.154; a recipe's ``poses``): ``turned_over``
    turns one bone about a model-frame axis by its angle inside its window,
    eased in and out over ``ease`` (female_2's front sash in her walk, -25
    degrees about x over 30-60 %): within the window its rotation is the
    turn times the clip's, outside the eased margins the clip's own, every
    other track kept, its key times rising from 0 in float32. An ease of 0
    turns it at the window's edges with no margin."""
    from azurkit.tools.characters.retarget import Rig, evaluate, named_clip, qangle, turned_over

    data, body = _vanilla_characters(usa_iso), "townspeople/female_2"
    walk, rig = named_clip(data, body, "walk"), Rig.read(data, body)
    k = next(j for j, b in enumerate(rig.bones) if b.name == "loincloth_front_1")
    out = turned_over(rig, walk, k, (1.0, 0.0, 0.0), -25.0, (0.3, 0.6, 0.1))

    def rotation(clip, t):
        keyed = {tr.comp - 3: tr.keys for tr in clip.bones if tr.target == k and 3 <= tr.comp <= 6}
        return tuple(evaluate(keyed[c], t) if c in keyed else rig.bones[k].q[c] for c in range(4))
    for j in range(41):
        angle = qangle(rotation(out, walk.length * j / 40), rotation(walk, walk.length * j / 40))
        if 0.3 <= j / 40 <= 0.6:
            assert abs(angle - 25.0) < 0.5, j
        elif j / 40 < 0.2 or j / 40 > 0.7:
            assert angle < 1e-3, j
    assert [tr for tr in out.bones if tr.target != k] == [tr for tr in walk.bones if tr.target != k]
    assert out.markers == walk.markers and out.length == walk.length
    for tr in out.bones:
        times = [struct.unpack("<f", struct.pack("<f", key[0]))[0] for key in tr.keys]
        assert times[0] == 0.0 and all(b > a for a, b in zip(times, times[1:]))
    hard = turned_over(rig, walk, k, (1.0, 0.0, 0.0), -25.0, (0.3, 0.6, 0.0))
    for j in (4, 10, 20, 30):
        t = walk.length * j / 40
        assert abs(qangle(rotation(hard, t), rotation(walk, t)) - (25.0 if j == 20 else 0.0)) < 0.5, j


def test_booblords_sash_hangs_at_each_spins_ends_and_swings_out_mid_spin(usa_iso):
    """D371 (Modkit's Steps 2.134a, 2.134b; AZ-619, AZ-636): each loincloth
    bone her idle keys starts and ends booblord's spin, twirl, stomp and
    hand spin on her idle's t 0 rotation, its hang, and each chain's first
    bone swings out from it: 66.5 degrees off the hang mid-spin, mid-twirl
    and mid-hand-spin, a 25-degree lift in the stomp's fall (0.525)."""
    from azurkit.tools.characters._player_variants import hand_spin, t_spin
    from azurkit.tools.characters.characters import read_body
    from azurkit.tools.characters.retarget import Rig, evaluate, named_clip, qangle

    data, variant = _vanilla_characters(usa_iso), builtins()["booblord"]
    body = read_body(data, "townspeople/female_2")
    markers = {m: i for i, m in enumerate([*body.markers, "m_damage"])}
    idle, rig = named_clip(data, body.name, "idle"), Rig.read(data, body.name)
    names = {k: b.name for k, b in enumerate(rig.bones)}
    keyed = {(tr.target, tr.comp): tr.keys for tr in idle.bones if 3 <= tr.comp <= 6}
    sash = sorted({k for k, _ in keyed if names[k].startswith("loincloth_")})
    assert [names[k] for k in sash] == [f"loincloth_{s}_{n}" for s in ("front", "back") for n in range(1, 5)]
    hang = {k: tuple(evaluate(keyed[k, 3 + r], 0.0) if (k, 3 + r) in keyed else rig.bones[k].q[r] for r in range(4))
            for k in sash}
    for name, (mid, off) in {"spin": (0.5, 66.5), "twirl": (0.5, 66.5), "stomp": (0.525, 25.0),
                             "hspin": (0.5, 66.5)}.items():
        made = (hand_spin if name == "hspin" else t_spin)(data, body, variant.clips[name], markers)
        tracks = {(tr.target, tr.comp): tr.keys for tr in made.bones}

        def turned(k: int, t: float) -> float:
            return qangle(tuple(evaluate(tracks[k, 3 + r], t) for r in range(4)), hang[k])
        assert max(turned(k, t) for k in sash for t in (0.0, made.length)) < 1e-3, name
        assert {names[k]: round(turned(k, mid * made.length), 1) for k in sash if names[k].endswith("_1")} == {
            "loincloth_front_1": pytest.approx(off, abs=1.0), "loincloth_back_1": pytest.approx(off, abs=1.0)}, name


def test_booblords_b_spins_chain_planted_and_she_rises_only_when_the_chain_ends(usa_iso):
    """D701 (Modkit's Step 2.180, W37): for a hand spin both B columns play
    that rests on its hand after its turns (booblord's hspin, booblord_high's;
    not beamlord's, nor one with no ``hold``), W37 chains both at the rest's
    start (0.67 of her clip), starts sweep2 one turn before it (0.335) and
    ends it at the clip's end; row 33 (B near a cliff) becomes sweep2's B ->
    sweep2 and row 27 (B from a run) plays sweep1; no other byte of
    config.xbr changes. Every pose the chain plays (sweep2 through one turn,
    and the cut's crossfade into the next) keeps her root within 2.5 cm of
    the planted pose's and her hand under 7 cm; every pose of her rest is
    the pose sweep2 starts at; she stands only at the clip's ends."""
    from azurkit.tools.characters._player_character import planted_chain
    from azurkit.tools.characters._player_variants import hand_spin
    from azurkit.tools.characters.characters import read_body
    from azurkit.tools.characters.retarget import Rig, origins, pose, qangle

    variant = builtins()["booblord"]
    p = variant.loop()
    assert p is variant.clips["hspin"] and builtins()["booblord_high"].loop() == p
    assert builtins()["beamlord"].loop() is None
    assert dataclasses.replace(variant, clips={**variant.clips, "hspin": {k: v for k, v in p.items() if k != "hold"}}
                               ).loop() is None
    cells = ("Move start", "Move end1", "Move end2")
    s, e = 0.335, 0.67
    with iso.Reader(usa_iso) as r:
        config, data = r.read(CONFIG), r.read(CHARACTERS)
    doc = ports.XbrDocument.from_bytes(bytearray(config))
    anims, rows = doc.keyed_section("attacks_anims"), doc.keyed_section("attacks_transitions")
    names, cols = anims.col_names(), rows.col_names()
    one, two = names.index("sweep1"), names.index("sweep2")
    ports.set_keyed_double(anims, "sweep1", "Move end1", 19.3048, col=one)   # W19's 0.2952 of its clip
    before = bytes(doc.raw)

    def table(section) -> list[dict]:
        return [{r: (c.string_value if c.type_code == 2 else c.double_value) for r in section.row_names()
                 if (c := section.find_cell(name, r, i)) is not None and c.type_code}
                for i, name in enumerate(section.col_names())]
    was = (table(anims), table(rows))
    got = planted_chain(anims, rows, tuple(p["plant"]), float(p["turns"]), float(p["hold"]))
    assert (round(got[0], 4), round(got[1], 4), got[2]) == (s, e, True)
    now = (table(anims), table(rows))
    assert now[0][two] == was[0][two] | dict(zip(cells, (pytest.approx(s, abs=1e-4), pytest.approx(e, abs=1e-4), 1.0)))
    assert now[0][one]["Move end1"] == pytest.approx(1 + e * 62, abs=1e-3)
    assert {i for i in range(len(names)) if now[0][i] != was[0][i]} == {one, two}
    assert {i: now[1][i] for i in range(len(cols)) if now[1][i] != was[1][i]} == {
        27: was[1][27] | {"next move": "sweep1"},
        33: {"search order": "a", "last move": "sweep2", "button": 2.0, "next move": "sweep2"}}
    touched = [c.file_offset for i, col in ((one, "sweep1"), (two, "sweep2"))
               for c in (anims.find_cell(col, r, i) for r in cells)] + [
        rows.find_cell(cols[c], r, c).file_offset for c, r in ((27, "next move"), (33, "last move"),
                                                              (33, "next move"), (33, "near cliff"))]
    assert all(any(at <= k < at + 16 for at in touched) for k, (x, y) in enumerate(zip(before, doc.raw)) if x != y)
    body = read_body(data, "townspeople/female_2")
    clip = hand_spin(data, body, p, {m: i for i, m in enumerate([*body.markers, "m_damage"])})
    rig = Rig.read(data, body.name)
    bones = [b.name for b in rig.bones]
    root, hand = bones.index("root_joint"), bones.index("right_hand_endnode")
    rate, rest, length = was[0][two]["Rate"], p["plant"][1], clip.length

    def at(f: float) -> tuple:
        o, q = origins(rig, clip, f * length), pose(rig, clip, f * length)
        return o[root], o[hand], q[root]
    low = at(0.5)[0][2]
    tick = rate / 30 / length
    for k in range(61):   # sweep2 from s through one turn, then the cut's 3-tick crossfade into the next
        r, h, _ = at(s + (e - s) * k / 60)
        assert abs(r[2] - low) < 0.025 and h[2] < 0.07, k
    for j in range(4):
        (ro, ho, _), (rn, hn, _) = at(e + j * tick), at(s + j * tick)
        w = j / 3
        assert abs((1 - w) * ro[2] + w * rn[2] - low) < 0.025 and (1 - w) * ho[2] + w * hn[2] < 0.07, j
    r0, h0, q0 = at(s)
    for k in range(21):   # her rest: the pose sweep2 starts at, whichever tick a press chains her on
        r1, h1, q1 = at(e + (rest - e) * k / 20)
        assert math.dist(r0, r1) < 1e-3 and math.dist(h0, h1) < 1e-3 and qangle(q0, q1) < 0.1, k
    assert at(1.0)[0][2] - low > 0.3 and at(0.0)[0][2] - low > 0.3


def test_booblords_ponytail_swings_live_walled_off_her_back_from_a_root_that_rides_her():
    """D734, D737 (Modkit's Step 2.169c): her ponytail swings on X41 as well
    as its bake: five spring rows on ponytail_1-5, each chained to the one
    above, walled 3 mm toward her back, no gravity of their own, the swing
    faded in from the root (its travel the least) as it softens (frequency
    falling, damping rising root to tip), its drive capped at 1.2 m/s^2 and
    smoothed over 0.08 s; the links stay baked bones, ``jiggle.clear``
    keeping their hang out of her skin and forearms (and at a ladder's edges
    her skin alone), and booblord_high's jiggle is hers."""
    v = builtins()["booblord"]
    rows = [b for b in v.jiggle.springs if b.bone.startswith("ponytail")]
    assert [(b.role, b.bone, b.parent) for b in rows] == [
        (f"pony{k}", f"ponytail_{k}", "head" if k == 1 else f"ponytail_{k - 1}") for k in range(1, 6)]
    assert all((b.spring.wall, b.spring.gravity, b.spring.rot_share, b.spring.pivot) == ((0.0, 1.0, 0.0, 0.003), 0.0,
                                                                                         1.0, "origin") for b in rows)
    assert {(b.spring.accel, b.spring.give) for b in rows} == {(1.2, 0.08)}
    swing = [math.hypot(*b.spring.travel[:2]) for b in rows]
    assert swing.index(min(swing)) == 0 and swing[0] < 0.5 * max(swing)
    assert [b.spring.freq for b in rows] == sorted((b.spring.freq for b in rows), reverse=True)
    assert [b.spring.damping for b in rows] == sorted(b.spring.damping for b in rows)
    baked = [b for b in v.jiggle.bones if b.bone.startswith("ponytail")]
    assert [b.bone for b in baked] == [f"ponytail_{k}" for k in range(1, 6)] and all(b.spring is None for b in baked)
    assert (v.jiggle.clear.links, v.jiggle.clear.groups, v.jiggle.clear.clips) == (
        tuple(b.bone for b in baked), (1, 2), (("climb_up_edge", (1,)), ("climb_down_edge", (1,))))
    assert builtins()["booblord_high"].jiggle == v.jiggle


def test_a_kept_body_is_not_reused_for_specs_that_differ_only_in_a_zeros_sign():
    """Modkit's Step 2.176 review (4): 0.0 == -0.0 while a zero's sign
    reaches the bytes, so a variant body's kept parts are keyed by the specs'
    ``repr``: a mesh that moves a vertex by -0.0 is dressed again, never
    handed the +0.0 one's body."""
    from types import SimpleNamespace

    from azurkit.tools.characters._player_character import _body_keys

    plus, minus = (SimpleNamespace(mesh=("move", z), jiggle=None, textures=None, texture_scale=1) for z in (0.0, -0.0))
    assert plus.mesh == minus.mesh
    keys = [_body_keys(b"x", b"x", "townspeople/female_2", v, None) for v in (plus, minus, plus)]
    assert keys[0] != keys[1] and keys[0] == keys[2]


def test_booblord_high_is_booblord_with_finer_forms_and_each_texture_at_twice_its_size(usa_iso):
    """D593, D680, D691, D698, D721, D724 (Modkit's Step 2.177 on):
    booblord_high is ``from`` booblord with ``texture_scale`` 2 and her
    ``mesh_ops`` (her bust, glutes and thighs subdivided once more, each
    feathered; her sash thickened, tapered at its top), her ponytail's rings
    laid over booblord's tube and her face's sharpen and shade after her
    skin row's paint ops; every other field a build reads is booblord's and
    her sha her own; she reads booblord's sounds and clips and swings the
    Axion staff with booblord's arm fit, which a field laid over her drops;
    her rows bake at twice their size, a size past 4,096 failing by name."""
    from azurkit.tools.characters import _player_weapons as pw
    from azurkit.tools.characters import paint
    from azurkit.tools.characters.characters import read_body

    high, boob = builtins()["booblord_high"], builtins()["booblord"]
    own = ("name", "title", "notes", "sha", "texture_scale", "files", "mesh", "textures")
    assert [f.name for f in dataclasses.fields(high) if f.name not in own
            and getattr(high, f.name) != getattr(boob, f.name)] == []
    n = len(boob.mesh.ops)
    added, laid = high.mesh.ops[n:], [k for k in range(n) if high.mesh.ops[k] != boob.mesh.ops[k]]
    assert [(boob.mesh.ops[k].name, boob.mesh.ops[k].sides, boob.mesh.ops[k].rings, high.mesh.ops[k].rings)
            for k in laid] == [("ponytail", 32, 72, 144)]
    assert dataclasses.replace(high.mesh.ops[laid[0]], rings=72) == boob.mesh.ops[laid[0]]
    assert dataclasses.replace(high.mesh, ops=boob.mesh.ops) == boob.mesh
    assert [(op.name, op.edge, op.apart is not None, op.normals) for op in added[:-1]] == [
        ("bust high", 0.0065, True, "nearer"), ("bust high feather", 0.0092, True, "nearer"),
        ("glutes high", 0.0055, False, "area"), ("glutes high feather", 0.0078, False, "area"),
        ("thighs high", 0.011, False, "area"), ("thighs high feather", 0.0156, False, "area")]
    assert (added[-1].name, added[-1].depth, added[-1].only, added[-1].taper) == (
        "sash thick", 0.006, ("loincloth_front_1", "loincloth_back_1"), 0.03)
    assert [dataclasses.replace(t, ops=t.ops[:len(b.ops)]) for t, b in zip(high.textures, boob.textures)] == list(
        boob.textures) and len(high.textures) == len(boob.textures)
    assert [[op.op for op in t.ops[len(b.ops):]] for t, b in zip(high.textures, boob.textures)] == [
        ["sharpen", "shade"], []]
    assert (high.texture_scale, high.files, high.sha != boob.sha) == (2, "booblord", True)
    assert [f(high) for f in (_player_variants.sound_folder, _player_variants.clip_folder)] == [
        f(boob) for f in (_player_variants.sound_folder, _player_variants.clip_folder)]
    staff, body = pw.weapons()["axion_staff"], "townspeople/female_2"
    assert pw.fit_turns(body, high, staff) == pw.fit_turns(body, boob, staff) != {}
    assert pw.fit_turns(body, _player_variants.laid_over(high, {"arms": None}), staff) == {}
    data = _vanilla_characters(usa_iso)
    assert pw.default_weapon(data, read_body(data, body), high).name == "booblord_spin"
    assert pw.attack_recipe(high, "booblord_spin", "booblord_spin") is high
    assert [(s.row, s.size, s.format, len(s.ops)) for s in paint.scaled(data, body, high.textures, 2)] == [
        (1, 1024, "dxt1", 6), (0, 512, "dxt1", 4), (2, 256, "dxt1", 0), (3, 128, "dxt1", 0)]
    with pytest.raises(ValueError, match="row 1 at 32768x32768 is past the 4096"):
        paint.scaled(data, body, boob.textures, 64)


def test_a_recipe_file_may_be_from_a_built_in_with_effects_rows_laid_over(usa_iso, tmp_path):
    """D687 (Modkit's Step X.73): a user's recipe may be ``from`` a built-in
    and lay ``effects`` over it: every field a build reads is booblord's but
    its rows; it reads her sounds, clips and fx, takes her W29 places and
    wears her spins as its default weapon."""
    from azurkit.tools.characters import _player_weapons as pw
    from azurkit.tools.characters.characters import read_body

    rows = [{"template": "bubble", "columns": ["basic1"]}, {"template": "laser", "columns": ["finish", "finish2"]}]
    (tmp_path / "e3.json").write_text(json.dumps({"e3": {"from": "booblord", "title": "E3", "effects": rows}}),
                                      encoding="utf-8")
    e3, boob = _player_variants.resolve("e3", tmp_path / "e3.json"), builtins()["booblord"]
    own = ("name", "source", "title", "notes", "sha", "effects", "files")
    assert [f.name for f in dataclasses.fields(e3) if f.name not in own
            and getattr(e3, f.name) != getattr(boob, f.name)] == []
    assert (e3.files, [(e.template.name, e.columns) for e in e3.effects], e3.sha != boob.sha) == (
        "booblord", [("bubble", ("basic1",)), ("laser", ("finish", "finish2"))], True)
    folders = (_player_variants.sound_folder, _player_variants.clip_folder, _player_variants.fx_folder)
    assert [f(e3) for f in folders] == [f(boob) for f in folders]
    assert _player_variants.parent_of(e3) is boob
    data, body = _vanilla_characters(usa_iso), "townspeople/female_2"
    assert pw.default_weapon(data, read_body(data, body), e3).name == "booblord_spin"
    assert pw.attack_recipe(e3, "booblord_spin", "booblord_spin") is e3


def test_a_plain_balthazar_build_draws_beamlords_bolts():
    """D427, D442, D452 (Modkit's Steps 2.146, 2.153b, 2.197b): plain
    Balthazar's own build (his overlay, no variant worn) edits his fx clone
    at beamlord's bolt records ([24] the burst emitter, [35] its renderer,
    [39] its sink) and drain box [45], his stream's renderer [11] bright
    for 1 s and pool [14] at 30 Hz, and his bolts' targets [58], [60], [62]
    at inherit mode 7; the bytes his build writes are G3's
    (``randomize-full:player-character=balthazar``)."""
    bolts = _player_variants.overlay("balthazar").fx
    assert bolts[:4] == tuple(e for e in builtins()["beamlord"].fx if e["record"] in (24, 35, 39, 45))
    stream = {e["record"]: e["set"] for e in bolts[4:6]}
    assert [(e["record"], e["inherit"]) for e in bolts[6:]] == [(58, 7), (60, 7), (62, 7)]
    assert len(bolts) == 9 and stream[14] == {"updateRate": 30.0} and (
        stream[11]["colorAge2"], stream[11]["alphaAge2"], stream[11]["sizeAge2"], stream[11]["size2"]) == (
        1.0, 1.0, 1.0, 0.24)


def test_the_variants_pages_own_sounds_are_the_roles_its_build_binds_with_w3s_picks(usa_iso):
    """Modkit's Step 2.164d: the Variants editor greys a recipe's voice and
    WAVs on a base whose own sounds its build binds, read as the build reads
    them (W3's picks), not the vanilla Anim cells: boulder's roll binds its
    own roll sound."""
    assert sdk.own_sounds({"iso": str(usa_iso), "species": "boulder"})["roles"] == ["death", "footstep", "roll"]


# --- a build of a recipe, read back -----------------------------------------------------------------------------------
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]
XBE = "default.xbe"


def _files(image, folder: Path, recipe: dict, name: str = "tspin", **given) -> dict[str, bytes]:
    """``recipe`` as ``name`` in a recipe file in ``folder`` (its files beside it), worn (``given``: the character's
    other fields) in a build of ``image`` through ``sdk.image``, no pack on: each file the build changed (but
    filelist.txt) and its bytes."""
    file = folder / f"{name}.json"
    file.write_text(json.dumps({name: recipe}), encoding="utf-8")
    made, report = sdk.image({"iso": str(image), "packs": {},
                              "character": {"species": name, "variant_file": str(file), **given}})
    with iso.Reader(made) as r:
        return {f: r.read(f) for f in report["result"] if f != "filelist.txt"}


def _building(image):
    """The context the swap's hook and shim readers run in (``ports.building``): ``image``'s vanilla files."""
    stamp = gate.verify(str(image), whole=False)
    return ports.building(ports.Build(ports.Vanilla(stamp.release, stamp.path, stamped=stamp), taken=[],
                                      packs=characters.packs_view(stamp.release, mods.PACKS)))


def _at(xbe: bytes, hook, symbol: str) -> int:
    """The file offset in ``xbe`` of ``symbol`` of ``hook``'s shim (inside :func:`_building`)."""
    return ports.resolve_va_to_file(xbe, ports.trampoline_symbol_va(xbe, hook, symbol))


def _slots(xbe: bytes, slots) -> tuple[list[str], list[float]]:
    """X11's table in the built ``xbe``: the clip each of ``slots`` plays and its timed length."""
    from azurkit.tools.characters._player_slots import HOOK

    table = _at(xbe, HOOK, "_player_model_slots")
    offsets, lengths = struct.unpack_from("<82H", xbe, table), struct.unpack_from("<82f", xbe, table + 82 * 2)
    names = table + 82 * 6
    return ([xbe[names + offsets[k] - 1:xbe.index(b"\0", names + offsets[k] - 1)].decode() for k in slots],
            [lengths[k] for k in slots])


def _clip_only(data: bytes, body: str, clips) -> bytes:
    """``clips`` ((name, clip) pairs) of ``body`` as a ``.glb`` of its bone nodes and those animations alone, as
    ``model export`` writes them (Modkit's ``townsfolk_kit.clip_only``, a retired authoring script's, D955)."""
    from azurkit.tools.characters import gltf

    doc, blob, _, _ = gltf._document(data, gltf._read(data, body), list(clips), True)
    used = sorted({s[k] for a in doc["animations"] for s in a["samplers"] for k in ("input", "output")})
    out, accessors, views = bytearray(), [], []
    for i in used:
        acc = dict(doc["accessors"][i])
        view = doc["bufferViews"][acc["bufferView"]]
        out += bytes(-len(out) % 4)
        views.append({"buffer": 0, "byteOffset": len(out), "byteLength": view["byteLength"]})
        out += blob[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
        acc["bufferView"] = len(views) - 1
        accessors.append(acc)
    remap = {old: new for new, old in enumerate(used)}
    for a in doc["animations"]:
        for s in a["samplers"]:
            s["input"], s["output"] = remap[s["input"]], remap[s["output"]]
    lean = {"asset": doc["asset"], "scene": 0, "scenes": [{"name": doc["scenes"][0]["name"],
                                                           "nodes": [len(doc["nodes"]) - 2]}],
            "nodes": doc["nodes"][:-1], "animations": doc["animations"], "accessors": accessors,
            "bufferViews": views, "buffers": [{"byteLength": len(out)}]}
    text = json.dumps(lean, separators=(",", ":"), allow_nan=False).encode()
    text += b" " * (-len(text) % 4)
    out += bytes(-len(out) % 4)
    return (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(out))
            + struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(out), 0x004E4942) + out)


def _played_back(clip):
    """``clip`` run back in time: each key at the length less its time, its tangents swapped and negated."""
    from azurkit.tools.characters.retarget import Clip, Track

    return Clip(clip.length, tuple(Track(tr.target, tr.comp, tuple((clip.length - t, v, -o, -i)
                                                                   for (t, v, i, o) in reversed(tr.keys)),
                                         (tr.modes[1], tr.modes[0])) for tr in clip.bones), ())


def test_a_recipe_clip_from_gltf_plays_in_its_columns_at_its_rate_with_its_box(usa_iso, tmp_path):
    """D465, D491 (Modkit's Step 2.158): a user recipe's ``gltf`` clip
    (female_2's exported idle renamed ``jab``) plays in its column as
    ``v/jab`` at the recipe's rate times the speed slider, its ``m_damage``
    box on over its ``active`` seconds, and W19's chain point the one for
    that Rate; a wrong sha256 fails by name (by its first 12 digits, AzurKit's)."""
    from azurkit.tools.characters._player_character import chain_point, contact, move_window
    from azurkit.tools.characters.characters import damage_windows
    from azurkit.tools.characters.gltf import export_body
    from azurkit.tools.characters.retarget import named_clip

    body = "townspeople/female_2"
    gltf = export_body(_vanilla_characters(usa_iso), body, tmp_path / "export", ["idle"]).gltf
    doc = json.loads(gltf.read_text(encoding="utf-8"))
    doc["animations"][0]["name"] = "jab"
    gltf.write_text(json.dumps(doc), encoding="utf-8")
    jab = {"generator": "gltf", "file": f"export/{gltf.name}", "sha256": mesh_edit.file_sha256(gltf),
           "animation": "jab", "active": [0.30, 0.45], "box": {"centre": [0.0, 0.5, 1.1], "half": [0.35, 0.35, 0.35]},
           "rate": 1.25}
    recipe = {"base": "town_female_2", "attacks": {"balance": False, "speed": 1.2}, "markers": ["m_damage"],
              "clips": {"jab": jab}, "columns": {"basic1": "jab"}}
    built = _files(usa_iso, tmp_path, recipe, "jabber")
    data = built[CHARACTERS]
    anims = ports.XbrDocument.from_bytes(built[CONFIG]).keyed_section("attacks_anims")
    i = anims.col_names().index("basic1")
    assert anims.find_cell("basic1", "Anim", i).string_value == "v/jab"
    assert anims.find_cell("basic1", "Rate", i).double_value == pytest.approx(1.25 * 1.2)
    (w,) = damage_windows(data, body, "v/jab", 1.15)
    assert (w.on, w.off) == pytest.approx((0.30, 0.45), abs=0.02)
    length = named_clip(data, body, "v/jab").length
    met = contact(data, body, "v/jab", 1.15, length, move_window(anims, i))
    assert chain_point(anims, i, length, (w,), met) is None
    with pytest.raises(ValueError, match="its sha256 is [0-9a-f]{12}, not the recipe's 0{12} "):
        _files(usa_iso, tmp_path, {**recipe, "clips": {"jab": {**jab, "sha256": "0" * 64}}}, "jabber")


FIDGETY = {"base": "town_female_2", "idles": {"idle": "idle", "idle_1": "idle", "idle_2": "listen", "idle_3": "talk",
                                              "idle_4": "sit", "wait": [21, 30]}}
"""A recipe of town_female_2's own clips as idles: her idle the base (slots 1 and 2), listen, talk and sit the
fidgets (slots 3-5)."""


@pytest.mark.parametrize("release", RELEASES)
def test_a_recipes_idles_fill_the_idle_slots_and_play_a_fidget_after_its_wait_never_twice(release, request, tmp_path):
    """D553, D331 (Modkit's Step 2.168): a recipe's ``idles`` name the
    clips X11 plays in the idle slots, and X45 takes the standing picker's
    CALL of the fidget pick at 0x85CD7 with its table: the fidget slots 3-5,
    the wait [21, 30] and the standing timer's address read from the image
    (USA 0x38DC50, Europe 0x38FBF8). L2 (USA, from 0x85C60): under the
    drawn wait it returns 1, past it a fidget the species fills, never the
    one before, the next wait drawn; a slot the species lacks is never
    picked; ESI, EDI, EBX and EBP are kept and the x87 stack left empty.
    Idles that name no wait, and booblord's, wait [10, 10] (Step 2.190)."""
    from unicorn.x86_const import UC_X86_REG_FPSW

    from azurkit.tools.characters._player_slots import BASE_CLIPS, IDLE_HOOK, IDLE_TABLE, idle_table
    from devkit.sim import l2

    image, europe = request.getfixturevalue(f"{release.name}_iso"), release is gate.EUROPE
    xbe = _files(image, tmp_path, FIDGETY, "fidgety")[XBE]
    with _building(image):
        assert ports.verify_trampoline_patch(xbe, IDLE_HOOK) == "applied"
        at = _at(xbe, IDLE_HOOK, IDLE_TABLE.symbol)
        assert xbe[at:at + 16] == idle_table(0b111000, (21.0, 30.0), 0x38FBF8 if europe else 0x38DC50)
        assert _slots(xbe, range(1, 6))[0] == ["idle", "idle", "listen", "talk", "sit"]
        words = {w: ports.trampoline_symbol_va(xbe, IDLE_HOOK, w)
                 for w in ("_player_model_idle_wait", "_player_model_idle_last")}
    assert BASE_CLIPS[1:6] == ("idle", "idle_1", "idle_2", "idle_3", "idle_4")
    if europe:
        return
    calm = {**FIDGETY, "idles": {k: v for k, v in FIDGETY["idles"].items() if k != "wait"}}
    assert load_variants(json.dumps({"calm": calm}), "test")["calm"].idle_wait == (10.0, 10.0) == builtins()[
        "booblord"].idle_wait
    base = 0x20000000
    control, critter, species, given = (base + 0x400 * k for k in range(4))
    sim = l2.Sim(xbe)
    sim.uc.mem_map(base, 0x2000)
    for at_, value in ((control + 0x20, critter), (critter + 0x200, 1), (critter + 0x178, species),
                       *((species + 0x124 + 4 * k, k) for k in range(1, 8))):
        sim.uc.mem_write(at_, struct.pack("<I", value))
    sim.uc.mem_write(species + 0x124 + 4 * 6, struct.pack("<i", -1))   # slot 6 empty
    kept = {"ebx": 0x11, "esi": 0x22, "ebp": 0x33}

    def standing(timer: float) -> int:
        sim.uc.mem_write(0x38DC50, struct.pack("<f", timer - 1 / 30))   # the picker adds the tick first
        got = sim.call(0x85C60, regs={"edi": control, "ecx": given, **kept})
        assert {r: sim.reg(r) for r in (*kept, "edi")} == {**kept, "edi": control}
        assert (sim.uc.reg_read(UC_X86_REG_FPSW) >> 11) & 7 == 0
        return got
    assert standing(10.5) == 1
    wait = sim.f32(words["_player_model_idle_wait"])
    assert 21.0 <= wait <= 30.0
    assert standing(wait - 0.01) == 1
    played = []
    for _ in range(60):
        played.append(standing(sim.f32(words["_player_model_idle_wait"]) + 0.01))
        assert sim.u32(words["_player_model_idle_last"]) == played[-1]
        assert 21.0 <= sim.f32(words["_player_model_idle_wait"]) <= 30.0
    assert set(played) == {3, 4, 5} and all(a != b for a, b in zip(played, played[1:]))
    sim.uc.mem_write(species + 0x124 + 4 * 4, struct.pack("<i", -1))   # talk's slot gone: listen and sit alone
    rest = [standing(sim.f32(words["_player_model_idle_wait"]) + 0.01) for _ in range(10)]
    assert set(rest) == {3, 5} and all(a != b for a, b in zip(rest, rest[1:]))


GAITED = {"base": "town_female_2", "slots": {"walk": "walk", "run": "walk", "walk_backwards": "walk_back",
                                             "run_backwards": "walk_back",
                                             **{f"victory_{v}": "talk" for v in range(1, 7)}}}
"""town_female_2's clips in its slots: her walk in the forward gait slots, its keys run back in time (``walk_back``,
a glTF clip the test writes) in the backward ones, her talk in the six victories."""


def test_a_recipes_slots_play_its_gait_and_victories_untimed_and_a_wrong_one_is_refused_by_name(usa_iso, tmp_path):
    """D440, D487, D534, D535 (Modkit's Step 2.171): a recipe's ``slots``
    name the clips X11 plays in the gait slots 8, 9, 13 and 14 and the
    victories 75-80 (none timed); W7 writes ``walkAnimSpeed`` and
    ``runAnimSpeed`` as the planted feet's speed of the walk and run slots'
    clips, and no baked garret4 victory is left in characters.xbr. A
    backward twin whose planted feet don't move forward at its forward
    twin's speed is refused by name (the other slot refusals are
    :data:`_LOAD_REFUSALS`' and :data:`_BUILD_REFUSALS`')."""
    from azurkit.tools.characters._player_character import planted
    from azurkit.tools.characters.retarget import named_clip

    vanilla, body = _vanilla_characters(usa_iso), "townspeople/female_2"
    (tmp_path / "back.glb").write_bytes(_clip_only(vanilla, body, [("walk_back", _played_back(
        named_clip(vanilla, body, "walk")))]))
    recipe = {**GAITED, "clips": {"walk_back": {"generator": "gltf", "file": "back.glb", "animation": "walk_back",
                                                "sha256": mesh_edit.file_sha256(tmp_path / "back.glb")}}}
    built = _files(usa_iso, tmp_path, recipe, "gaited")
    xbe, data = built[XBE], built[CHARACTERS]
    with _building(usa_iso):
        assert _slots(xbe, (8, 9, 13, 14, *range(75, 81))) == (["walk"] * 2 + ["v/walk_back"] * 2 + ["talk"] * 6,
                                                                [0.0] * 10)
    critters = ports.XbrDocument.from_bytes(built[CONFIG]).keyed_section("critters_critter_data")
    i = critters.col_names().index("garret4")
    speed = planted(data, body, "walk")
    assert speed > 0 and planted(data, body, "v/walk_back") == pytest.approx(-speed, rel=0.05)
    assert [critters.find_cell("garret4", p, i).double_value for p in ("walkAnimSpeed", "runAnimSpeed")] == \
        pytest.approx([speed, speed], rel=1e-6)
    assert not [n for n in named_resources(data).values() if "/g4/victory" in n.casefold()]
    stills = {"spin": SPIN, "still": {**SPIN, "turns": 0}}
    for slots, said in (({"walk": "walk", "walk_backwards": "still"},
                         f"slots.walk_backwards: v/still's planted feet move +0.000 model units a second (+ back), not "
                         f"{-speed:+.3f} within 5% (slots.walk's walk, run backwards): one cell times both"),
                        ({"walk": "walk", "walk_backwards": "walk"},
                         f"slots.walk_backwards: walk's planted feet move {speed:+.3f} model units a second (+ back), "
                         f"not {-speed:+.3f} within 5%")):
        with pytest.raises(ValueError) as caught:
            _planned(usa_iso, tmp_path, _with(clips=stills, slots=slots))
        assert said in str(caught.value)


@pytest.fixture(scope="module")
def _booblord_installed(tmp_path_factory) -> Path:
    """A content folder with booblord installed from Azurik-Custom-Content (``sdk.content_install``, every file checked
    against its manifest), once a module."""
    from azurkit.tools.characters import content
    from tests.test_characters import _content_source

    folder = tmp_path_factory.mktemp("content")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(content, "ROOT", folder)
        mp.setenv(content.ENV, str(folder))
        try:
            sdk.content_install({"id": "booblord", "source": _content_source()})
        except (OSError, ValueError) as exc:
            pytest.fail(f"Azurik-Custom-Content's booblord can't be installed from {_content_source()} (set "
                        f"{sdk.SOURCE_ENV}, or clone it beside the main checkout): {exc}", pytrace=False)
    return folder


@pytest.fixture
def booblord(_booblord_installed, monkeypatch) -> Path:
    """Booblord's files where the swap reads them: each name a characters module binds to a folder of
    ``content.ROOT`` rebound to that folder of :func:`_booblord_installed`'s, and ``AZURKIT_CONTENT`` naming it."""
    from azurkit.tools.characters import content

    root = content.ROOT
    monkeypatch.setattr(content, "ROOT", _booblord_installed)
    monkeypatch.setenv(content.ENV, str(_booblord_installed))
    for name, module in list(sys.modules.items()):
        if name == characters.__name__ or name.startswith(f"{characters.__name__}."):
            for attr, value in list(vars(module).items()):
                if isinstance(value, Path) and value.is_relative_to(root):
                    monkeypatch.setattr(module, attr, _booblord_installed / value.relative_to(root))
    return _booblord_installed


LENT = {"base": "town_female_3", "clips": {
    "g4_jump": {"generator": "bake", "body": "garret4", "clip": "jump"},
    "male_1_bow": {"generator": "bake", "body": "townspeople/male_1", "clip": "bow"},
    "booblord_hip_idle": {"generator": "bake", "body": "townspeople/female_2", "variant": "booblord", "clip": "hip_idle"},
    "g4_kick": {"generator": "bake", "body": "garret4", "clip": "attack_back_kick"}},
    "idles": {"idle": "booblord_hip_idle"}, "slots": {"jump": "g4_jump", "superjump": "g4_jump", "victory_1": "male_1_bow"},
    "columns": {"basic1": "g4_kick"}}
"""A townswoman's recipe of other humanoid bodies' clips through the bake: garret4's jump in her jump and superjump
and his back kick in basic1, town_male_1's bow in her first victory and booblord's Blender hip_idle as her idle."""


def test_a_recipe_clip_baked_from_another_humanoid_body_plays_in_its_slots_the_jump_family_too(usa_iso, tmp_path,
                                                                                               booblord):
    """D785, D768 (Modkit's Step 2.164c): a ``bake`` clip is another
    humanoid body's clip (garret4's, a townsman's, or with ``variant`` a
    built-in's Blender clip read on that body) retargeted onto the recipe's
    body, stored under ``v/`` so its idles and slots play it; ``slots``
    takes the jump family (jump 15, superjump 17) untimed, and a column plays
    one as ``v/<clip>``, X13's fill taking it as a base clip (no box of its
    own). garret4's jump lent so is the clip B bakes of it, and each lent
    clip keeps its lender's length."""
    from azurkit.tools.characters.clip_import import read_clips
    from azurkit.tools.characters.retarget import Retarget, bake_clip, named_clip, read_clip, write_clip

    built = _files(usa_iso, tmp_path, LENT, "lent")
    xbe, data = built[XBE], built[CHARACTERS]
    with _building(usa_iso):
        assert _slots(xbe, (1, 15, 17, 75)) == (["v/booblord_hip_idle", "v/g4_jump", "v/g4_jump", "v/male_1_bow"],
                                                 [0.0] * 4)
    anims = ports.XbrDocument.from_bytes(built[CONFIG]).keyed_section("attacks_anims")
    assert anims.find_cell("basic1", "Anim", anims.col_names().index("basic1")).string_value == "v/g4_kick"
    variant = load_variants(json.dumps({"lent": LENT}), "test")["lent"]
    assert _player_variants.authored(variant, anims.col_names()) == 0
    vanilla, body = _vanilla_characters(usa_iso), "townspeople/female_3"
    jump = named_clip(vanilla, "garret4", "jump")
    assert named_clip(data, body, "v/g4_jump") == read_clip(write_clip(bake_clip(Retarget(vanilla, body), jump)), 0)
    hip = read_clips(vanilla, "townspeople/female_2", _player_variants.CLIPS / "booblord" / "idles.glb", ["hip_idle"],
                     bones_only=True)[0].clip
    assert [named_clip(data, body, f"v/{c}").length for c in ("g4_jump", "male_1_bow", "booblord_hip_idle")] == \
        [jump.length, named_clip(vanilla, "townspeople/male_1", "bow").length, hip.length]


@pytest.mark.parametrize("release", RELEASES)
def test_a_recipes_victory_cancel_ends_a_victory_at_a_push_of_the_stick_after_its_minimum(release, request,
                                                                                          tmp_path):
    """D702 (Modkit's Step 2.181): a recipe's ``victory_cancel`` (s)
    installs X46 at the state machine's end check of a 0x1xx move, 0x8CF84
    (Europe 0x8CF34), with its minimum. L2 (USA, from 0x8CF50 to the
    dispatch at 0x8CFA0, on this build and on vanilla): a victory (slot
    75-80) still playing ends (state 0, its hit timer zeroed) once its own
    clock reaches 0.5 with the stick past 0.1 and input +0x30 clear, whatever
    the state timer; under the minimum, at rest, a light touch, a script's
    hold, an attack or the use it holds, and a layer that ended or stopped
    end it as vanilla does, ECX, EDX, EBX, EDI and EBP as vanilla's and the
    x87 stack untouched."""
    from unicorn.x86_const import UC_X86_REG_FPSW

    from azurkit.tools.characters._player_victory import CANCEL_AFTER, CANCEL_HOOK
    from devkit.sim import l2

    image = request.getfixturevalue(f"{release.name}_iso")
    recipe = {"base": "town_female_2", "slots": {f"victory_{v}": "talk" for v in range(1, 7)}, "victory_cancel": 0.5}
    xbe = _files(image, tmp_path, recipe, "tossy")[XBE]
    with _building(image):
        assert ports.verify_trampoline_patch(xbe, CANCEL_HOOK) == "applied"
        assert struct.unpack_from("<f", xbe, _at(xbe, CANCEL_HOOK, CANCEL_AFTER.symbol))[0] == 0.5
    if release is gate.EUROPE:
        return
    base = 0x20000000
    control, critter, anim, inp = (base + 0x400 * k for k in range(4))

    def run(data: bytes, slot: int, t: float, st: float, stick: float, held: int, flags: int) -> tuple:
        sim = l2.Sim(data)
        sim.uc.mem_map(base, 0x2000)
        for va, fmt, value in ((control + 0x94, "<I", 0x100), (control + 0x9C, "<f", st), (control + 0x20, "<I", critter),
                               (critter + 0x17C, "<I", anim), (critter + 0x200, "<i", slot), (critter + 0x1E4, "<f", 4.0),
                               (critter + 0x1E0, "<f", 4.0 - t), (anim + 0x10, "<i", 0), (anim + 0x48, "<I", flags),
                               (inp + 0x1C, "<f", stick), (inp + 0x30, "<B", held)):
            sim.uc.mem_write(va, struct.pack(fmt, value))
        top = (sim.uc.reg_read(UC_X86_REG_FPSW) >> 11) & 7
        sim.call(0x8CF50, regs={"ebp": control, "edi": inp, "ebx": critter}, until=0x8CFA0)
        assert (sim.uc.reg_read(UC_X86_REG_FPSW) >> 11) & 7 == top
        return (sim.u32(control + 0x94), sim.f32(critter + 0x1E0),
                tuple(sim.reg(r) for r in ("ecx", "edx", "ebx", "edi", "ebp")))
    with iso.Reader(image) as r:
        vanilla = r.read(XBE)
    for row in ((76, 0.5, 0.0, 1.0, 0, 0x4D, True), (75, 3.9, 3.9, 0.11, 0, 0x4D, True),
                (80, 0.5, 0.5, 1.0, 0, 0x4D, True), (76, 14 / 30, 2.0, 1.0, 0, 0x4D, False),
                (76, 0.5, 0.5, 0.0, 0, 0x4D, False), (76, 0.5, 0.5, 0.1, 0, 0x4D, False),
                (76, 0.5, 0.5, 1.0, 1, 0x4D, False), (20, 2.0, 2.0, 1.0, 0, 0x4D, False),
                (81, 2.0, 2.0, 1.0, 0, 0x4D, False), (74, 2.0, 2.0, 1.0, 0, 0x4D, False),
                (76, 0.1, 0.1, 0.0, 0, 0xED, False), (76, 0.1, 0.1, 0.0, 0, 0x4C, False)):
        got, was = run(xbe, *row[:-1]), run(vanilla, *row[:-1])
        assert got[2] == was[2], row
        assert got[:2] == ((0, 0.0) if row[-1] else was[:2]), (row, got, was)
        assert was[0] == (0 if row[5] != 0x4D else 0x100)

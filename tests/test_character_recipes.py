"""A variant's recipe (``tools/characters/_player_variants.py``, Modkit's
Step 2.137 on): what it loads, what it refuses by name and what a build of
it wears. Modkit's ``test_player_variants.py``, its rows no other AzurKit
test, golden or facts entry pinned; a build goes through the product's
dress (``sdk._plan``, or ``characters.dressed`` where Modkit read the swap's
log, logic or plans)."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
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

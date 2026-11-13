"""A variant's recipe (``tools/characters/_player_variants.py``, Modkit's
Step 2.137 on): what it loads, what it refuses by name and what a build of
it wears. Modkit's ``test_player_variants.py``, its rows no other AzurKit
test, golden or facts entry pinned; a build goes through the product's
dress (``sdk._plan``, or ``characters.dressed`` where Modkit read the swap's
log, logic or plans)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.core.xbr.nodes import named_resources
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_variants, mesh_edit, ports, reasons
from azurkit.core.xbr.append import relocations
from azurkit.core.xbr.clone import closure, refs_in
from azurkit.core.xbr.graph import Graph, Schema, apply, bind_name, list_at, local_matrix
from azurkit.core.xbr.nodes import parse_toc
from azurkit.tools.characters import fx_edit, fx_templates, render, textures
from azurkit.tools.characters._player_character import (ATTACK_BOX_HOOK, CARRY_HOOK, JIGGLE_HOOK, ROTATE_HOOK,
                                                        SEARCH_HOOK, AttackLogic)
from azurkit.tools.characters._player_damage_marker import DAMAGE_MARKER
from azurkit.tools.characters._player_variants import (RAMP, VARIANT_DIR, _rx, _rz, builtins, load_variants, options,
                                                       overlay, recipe_sha)
from azurkit.tools.characters.characters import damage_windows, marker_records, mesh_groups, read_body
from azurkit.tools.characters.retarget import Rig, _turn, evaluate, named_clip, origins, pose, qmul, read_clip

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


def _counted(name: str, key: str | dict, value: int | None) -> dict:
    """booblord's recipe with its mesh op ``name``'s count ``key`` at ``value`` (or each of a dict ``key``'s)."""
    recipe = json.loads(_player_variants.BUILTIN.read_text(encoding="utf-8"))["booblord"]
    counts = {key: value} if isinstance(key, str) else key
    recipe["mesh"]["ops"] = [op | counts if op.get("name") == name else op for op in recipe["mesh"]["ops"]]
    return recipe

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
    (_with(sfx={"spin": {**WHOOSH, "length": 40}, "jab": {**WHOOSH, "length": 10, "takes": 3, "columns": ["basic2"]}}),
     "booblord", (), "sfx: 70 s of whooshes (length x takes) is past the 60 s a recipe may make"),
    (_with(sfx={"hurt": WHOOSH}), "booblord", (), "'hurt' is a wavs role"),
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
    ({"booblord": _with(mesh={"gltf": GLTF})}, "built-in", (), "mesh.gltf: a built-in takes no glTF")] + [
    ({"mine": _counted(name, key, value)}, "test", (), said) for name, key, value, said in (
        ("upper chest", "passes", 10 ** 12, "passes 1,000,000,000,000 is past the 100 passes an op may run"),
        ("top hem 2", "relax", 10 ** 12, "relax 1,000,000,000,000 is past the 100 passes an op may run"),
        ("ponytail", "rings", 10 ** 6, "rings 1,000,000 is past the 512 a tube may have"),
        ("ponytail", "sides", 2 ** 20, "sides 1,048,576 is past the 256 a tube may have"),
        ("ponytail", "segments", 10 ** 9, "segments 1,000,000,000 is past the 40 its rings"),
        ("necklace", {"sides": 256, "rings": 192}, None,
         "256 sides and 192 rings are past the 32,768 points ((sides + 1) x rings)"))] + [
    ({"mine": {"from": "booblord", "mesh_ops": [{"over": "ponytail", "rings": 10 ** 6}]}}, "test", (),
     "rings 1,000,000 is past the 512 a tube may have")]


@pytest.mark.parametrize("recipes, source, taken, said", _LOAD_REFUSALS,
                         ids=[_id(said) for *_, said in _LOAD_REFUSALS])
def test_a_recipe_that_cant_build_fails_by_name(recipes, source, taken, said):
    """D35 (Modkit's Step 2.137 on): a recipe file fails by name at load,
    before any image is read: a key no recipe has, a missing base, a name
    the CLI can't take, a retired mode or unknown size, a number that isn't
    finite (D23: never clamped), a switch that isn't true or false, an
    unknown generator or a parameter of it missing, unknown, 0 or past its
    cap (whooshes past 60 s in all, length x takes summed over the sfx,
    each sample made in turn; a mesh op's
    passes, a tube's sides, rings, points or segments), a hand
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


def test_a_shapes_quick_preview_moves_each_drawn_vertex_where_the_builds_positions_put_it(monkeypatch):
    """Modkit's Step 2.164d: the Shape tab's quick preview (``editor.moved``)
    moves each drawn vertex found among the prepared mesh's to where
    ``mesh_edit.positions`` puts it at the recipe's shape values, and one the
    dress made beyond them (a finer triangle's, found nowhere) by its
    neighbours' mean move. The preparation stood in for (no game data); a
    found vertex drawn by a real dress, and the refusal of a mesh changed
    beyond its shapes, are test_variant_editor's quick preview test's."""
    import numpy as np

    from azurkit.tools.characters import editor
    from azurkit.tools.characters._player_variants import reshaped

    at = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
    moves = np.array([[0, 0, 0.1], [0, 0, 0.2], [0, 0, 0.3]], np.float32)
    calls = []
    monkeypatch.setattr(mesh_edit, "positions", lambda prepared, spec: calls.append(spec) or tuple(at + moves))
    drawn = [(np.array([[0, 1, 0], [0.5, 0.5, 0], [0, 0, 0], [1, 0, 0]]), np.array([[2, 3, 1], [3, 0, 1]]))]
    sized = reshaped(builtins()["booblord"], {"bust": 1.3})
    got = editor.moved(("prepared", at, [np.array([2, -1, 0, 1])]), sized, drawn)
    assert got[0] == pytest.approx(np.array([[0, 1, 0.3], [0.5, 0.5, 0.2], [0, 0, 0.1], [1, 0, 0.2]]))
    assert calls == [reshaped(builtins()["booblord"], {"bust": 1.3}).mesh]


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
    from azurkit.tools.characters.retarget import qangle, turned_over

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
    from azurkit.tools.characters.retarget import qangle

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
    from azurkit.tools.characters.retarget import qangle

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


def test_booblord_high_is_booblord_with_a_thicker_sash_and_each_texture_at_twice_its_size(usa_iso):
    """D593, D680, D691, D698, D721, D724 (Modkit's Step 2.177 on), and
    the booblord pass's carry-over (D1241): booblord_high is ``from``
    booblord with ``texture_scale`` 2 and one ``mesh_ops`` row (her sash
    thickened, tapered at its top), her mesh booblord's before it and her
    paint booblord's; every other field a build reads is booblord's and
    her sha her own; she reads booblord's sounds and clips and swings the
    Axion staff with booblord's arm fit, which a field laid over her drops;
    her rows bake at twice their size, a size past 4,096 failing by name."""
    from azurkit.tools.characters import _player_weapons as pw
    from azurkit.tools.characters import paint

    high, boob = builtins()["booblord_high"], builtins()["booblord"]
    own = ("name", "title", "notes", "sha", "texture_scale", "files", "mesh")
    assert [f.name for f in dataclasses.fields(high) if f.name not in own
            and getattr(high, f.name) != getattr(boob, f.name)] == []
    n = len(boob.mesh.ops)
    assert high.mesh.ops[:n] == boob.mesh.ops and dataclasses.replace(high.mesh, ops=boob.mesh.ops) == boob.mesh
    assert [(op.name, op.depth, op.only, op.taper) for op in high.mesh.ops[n:]] == [
        ("sash thick", 0.006, ("loincloth_front_1", "loincloth_back_1"), 0.03)]
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
        (1, 1024, "dxt1", 13), (0, 512, "dxt1", 3), (2, 256, "dxt1", 0), (3, 128, "dxt1", 0)]
    with pytest.raises(ValueError, match="row 1 at 32768x32768 is past the 4096"):
        paint.scaled(data, body, boob.textures, 64)


def test_a_recipe_file_may_be_from_a_built_in_with_effects_rows_laid_over(usa_iso, tmp_path):
    """D687 (Modkit's Step X.73): a user's recipe may be ``from`` a built-in
    and lay ``effects`` over it: every field a build reads is booblord's but
    its rows; it reads her sounds, clips and fx, takes her W29 places and
    wears her spins as its default weapon."""
    from azurkit.tools.characters import _player_weapons as pw

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


def test_a_plain_balthazar_build_draws_beamlords_bolts(usa_iso):
    """D427, D442, D452, D446 (Modkit's Steps 2.146, 2.153b, 2.197b): plain
    Balthazar's own build (his overlay, no variant worn) draws his attack_3's
    bolts as beamlord's: the player's clone of his fx_default changed only at
    beamlord's bolt records ([24] the burst emitter, [35] its renderer and
    texture, [39] its sink), his drain box [45], his stream's renderer [11]
    bright for 1 s and pool [14] at 30 Hz, and his bolts' targets [58], [60],
    [62] at inherit mode 7, the airship boss's graph vanilla's; his
    garret4-mode build adds no clone."""
    bolts = overlay("balthazar").fx
    assert bolts[:4] == tuple(e for e in builtins()["beamlord"].fx if e["record"] in (24, 35, 39, 45))
    stream = {e["record"]: e["set"] for e in bolts[4:6]}
    assert [(e["record"], e["inherit"]) for e in bolts[6:]] == [(58, 7), (60, 7), (62, 7)]
    assert len(bolts) == 9 and stream[14] == {"updateRate": 30.0} and (
        stream[11]["colorAge2"], stream[11]["alphaAge2"], stream[11]["sizeAge2"], stream[11]["size2"]) == (
        1.0, 1.0, 1.0, 0.24)
    vanilla, schema = _vanilla_characters(usa_iso), Schema(_vanilla_file(usa_iso, XBE))
    own, plain = (bytes(_engine(usa_iso, "balthazar", mode=mode)["characters.xbr"]) for mode in ("own", "garret4"))
    _cloned_only(schema, vanilla, own, "balthazar_airship", bolts)
    key = fx_edit.default_key("balthazar_airship")
    assert _payloads(plain, key) == _payloads(vanilla, key)
    assert fx_edit.clone_key("balthazar_airship") not in _payloads(plain, "characters/balthazar_airship/v/")


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


def _worn(image, character: dict) -> dict[str, bytes]:
    """``character`` worn in a build of ``image`` through ``sdk.image``, no pack on: each file the build changed (but
    filelist.txt) and its bytes."""
    made, report = sdk.image({"iso": str(image), "packs": {}, "character": character})
    with iso.Reader(made) as r:
        return {f: r.read(f) for f in report["result"] if f != "filelist.txt"}


def _files(image, folder: Path, recipe: dict, name: str = "tspin", **given) -> dict[str, bytes]:
    """``recipe`` as ``name`` in a recipe file in ``folder`` (its files beside it), worn (``given``: the character's
    other fields) as :func:`_worn` wears it."""
    file = folder / f"{name}.json"
    file.write_text(json.dumps({name: recipe}), encoding="utf-8")
    return _worn(image, {"species": name, "variant_file": str(file), **given})


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
    from azurkit.tools.characters.gltf import export_body

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


def _content_source() -> str:
    """Azurik-Custom-Content's source: ``$AZURKIT_CONTENT_SOURCE``, else its clone beside the main checkout."""
    if env := os.environ.get(sdk.SOURCE_ENV):
        return env
    common = subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
    return str(Path(common).parent.parent / "Azurik-Custom-Content")


@pytest.fixture(scope="module")
def _booblord_installed(tmp_path_factory) -> Path:
    """A content folder with booblord installed from Azurik-Custom-Content (``sdk.content_install``, every file checked
    against its manifest), once a module."""
    from azurkit.tools.characters import content

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
    from azurkit.tools.characters.retarget import Retarget, bake_clip, write_clip

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


def test_the_guis_movement_hint_measures_a_variant_at_the_player_pages_shape_values(usa_iso, monkeypatch):
    """Modkit's Step 2.164d: the worn body's size folded into the walk and
    roll (``characters.size``, the sdk's fold before a plan) measures a
    variant as its build sizes it at the character's shape values: booblord
    with her Bust size at 1.3 reshaped, at 1.0 her own body."""
    from azurkit.tools.characters._player_variants import reshaped

    measured, swap = [], characters._swap()
    monkeypatch.setattr(swap, "size_shape", lambda *args: measured.append(args[5].sha) or "her shape")
    monkeypatch.setattr(swap, "movement_size", lambda _shape, _scale: 2.0)
    stamp = gate.verify(str(usa_iso), whole=False)
    vanilla, her = ports.Vanilla(stamp.release, stamp.path, stamped=stamp), builtins()["booblord"]
    sizes = [characters.size(characters.normalize({"species": "booblord", "shapes": {"bust": v}}), vanilla)
             for v in (1.3, 1.0)]
    assert (sizes, measured) == ([2.0, 2.0], [reshaped(her, {"bust": 1.3}).sha, her.sha])


def test_beamlords_beams_turn_to_their_target_in_the_cone_at_the_attacks_start(usa_iso):
    """D762 (Modkit's Step 2.194b): beamlord's ``beam`` and ``sweep`` clips
    seek, so X49 lands at player_attack_enter's load of the swing's yaw
    (0x88A3A) for every column playing them (not the nova's), at the kit
    throw's 14 m and 45 degrees, with X21's radius. L2 on the vanilla XBE
    with X21 and X49 at his mask (attack_target_find stubbed): a beam or
    sweep whose own slot plays asks the finder from the yaw plus its Aim
    with the radius at 14 m (3 m after) and, a target 40 degrees off, takes
    its bearing less the Aim as the yaw (EAX, PC+0x138 and PC+0x90); 50
    degrees off or none counted, the yaw stays the game's, and a slot not
    playing or the nova asks nothing. EBX, ECX, EDX, ESI, EDI and EBP are
    kept."""
    from unicorn import UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP

    from azurkit.tools.characters._player_character import (SEARCH_RADIUS_SYMBOL, SEEK_HOOK, install_search_shim,
                                                             install_seek_shim)
    from devkit.sim import l2

    variant = builtins()["beamlord"]
    built = _worn(usa_iso, {"species": "beamlord"})
    xbe = built[XBE]
    columns = ports.XbrDocument.from_bytes(built[CONFIG]).keyed_section("attacks_anims").col_names()
    seeking = sum(1 << i for i, c in enumerate(columns) if variant.columns.get(c) in ("beam", "sweep"))
    with iso.Reader(usa_iso) as r:
        probe = bytearray(r.read(XBE))
    with _building(usa_iso):
        assert [struct.unpack_from("<f", xbe, _at(xbe, SEEK_HOOK, f"_player_model_seek_{k}"))[0]
                for k in ("columns", "range", "cone")] == [seeking, 14.0, 45.0]

        def radius_at(data: bytes) -> tuple[int, int]:   # X21's radius, and the VA X49's bytes param holds
            return (ports.trampoline_symbol_va(data, SEARCH_HOOK, SEARCH_RADIUS_SYMBOL),
                    struct.unpack_from("<I", data, _at(data, SEEK_HOOK, "_player_model_seek_radius_at"))[0])
        assert len(set(radius_at(xbe))) == 1
        install_search_shim(probe, 3.0)
        radius = ports.trampoline_symbol_va(probe, SEARCH_HOOK, SEARCH_RADIUS_SYMBOL)
        install_seek_shim(probe, seeking, radius)
        assert radius_at(probe) == (radius, radius)
    site = ports.resolve_va_to_file(probe, SEEK_HOOK.va)
    entry = SEEK_HOOK.va + 5 + struct.unpack_from("<i", probe, site + 1)[0]
    sim = l2.Sim(bytes(probe))
    pc, critter = 0x20000000, 0x20001000
    sim.uc.mem_map(pc, 0x2000)
    sim.uc.mem_write(pc + 0x20, struct.pack("<I", critter))
    log, answer = [], {}

    def find(uc, *_):   # attack_target_find(critter, facing, out): RET 0xC
        esp = sim.reg("esp")
        who, facing, out = struct.unpack("<IfI", uc.mem_read(esp + 4, 12))
        log.append((who, facing, sim.f32(radius)))
        uc.mem_write(out, struct.pack("<i5f", answer["count"], 0.0, 0.0, 0.0, answer["bearing"], answer["off"]))
        uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
        uc.reg_write(UC_X86_REG_ESP, esp + 16)
    sim.uc.hook_add(UC_HOOK_CODE, find, begin=0x7EBB0, end=0x7EBB0)

    def enter(column: str, yaw: float, *, aim: float = 1e5, playing: bool = True, **found) -> float:
        k = columns.index(column)
        answer.update({"count": 1, "bearing": 1.0, "off": math.radians(40)} | found)
        for va, data in ((pc + 0xE8, struct.pack("<f", aim)), (pc + 0x134, struct.pack("<i", k)),
                         (pc + 0x138, struct.pack("<f", yaw)), (pc + 0x90, struct.pack("<f", yaw)),
                         (critter + 0x200, struct.pack("<i", 0x52 + k if playing else 37))):
            sim.uc.mem_write(va, data)
        kept = {"ebx": 0x11, "ecx": 0x33, "edx": 0x100, "esi": 0x22, "ebp": 0x44, "edi": pc}
        eax = sim.call(entry, regs=kept, until=l2._RETURN)
        assert {r: sim.reg(r) for r in kept} == kept and sim.reg("esp") == l2._STACK_TOP - 0x100
        assert struct.pack("<I", eax) == bytes(sim.uc.mem_read(pc + 0x138, 4)) == bytes(sim.uc.mem_read(pc + 0x90, 4))
        return sim.f32(pc + 0x138)
    beam, sweep, nova = (next(c for c in columns if variant.columns.get(c) == n) for n in ("beam", "sweep", "nova"))
    yaw = pytest.approx(0.3)
    assert (enter(beam, 0.3), log) == (1.0, [(critter, yaw, 14.0)]) and sim.f32(radius) == 3.0
    assert (enter(sweep, 0.3, aim=10.0, bearing=1.2), log[-1]) == (
        pytest.approx(1.2 - math.radians(10)), (critter, pytest.approx(0.3 + math.radians(10)), 14.0))
    assert (enter(beam, 0.3, off=math.radians(50)), enter(beam, 0.3, count=0), len(log)) == (yaw, yaw, 4)
    assert (enter(beam, 0.3, playing=False), enter(nova, 0.3), len(log)) == (yaw, yaw, 4)


def test_booblords_own_landing_keeps_her_feet_over_x48s_hold_line_and_her_sash_off_the_floor_into_her_idle(
        usa_iso, booblord):
    """AZ-752, AZ-728, AZ-770, AZ-772, AZ-825 (Modkit's Steps 2.193 on):
    slot 11 plays booblord's own landing (``v/touchdown``, garret4's 13
    ticks), and from every phase of her fall a hard landing comes from, of
    her jumps and of her long fall, in the game's crossfade, her
    weight-bearing lowest point stays over X48's hold line through the
    landing and over her idle's own (less 2 cm) into her idle; her sash's
    lowest bone stays over the floor; each foot is planted (its ball moves at
    most 5 cm while its lowest joint is within 3 cm of the floor); every soft
    landing into her idle, walk or run and every takeoff from them keeps her
    over the line; her right ankle flexes at most 25 degrees in her fall and
    jumps. A recipe's touchdown that doesn't last 13 ticks fails by name."""
    import numpy as np

    from azurkit.tools.characters import _player_crossfade as cf
    from azurkit.tools.characters._player_character import FADE_HOOK, FADE_LOW, FADE_SOLE, loose_bones, move_checks
    from azurkit.tools.characters._player_slots import TOUCHDOWN_TICKS

    variant, body = builtins()["booblord"], "townspeople/female_2"
    built = _worn(usa_iso, {"species": "booblord"})
    xbe, data = built[XBE], built[CHARACTERS]
    with _building(usa_iso):
        assert _slots(xbe, (11,))[0] == ["v/touchdown"]
        low, sole = (struct.unpack_from("<f", xbe, _at(xbe, FADE_HOOK, p.symbol))[0] for p in (FADE_LOW, FADE_SOLE))
    rig = Rig.read(data, body)
    skip = loose_bones(rig)
    sash = frozenset(range(len(rig.bones))) - {k for k, b in enumerate(rig.bones) if b.name.startswith("loincloth")}
    td, idle = named_clip(data, body, "v/touchdown"), named_clip(data, body, "v/hip_idle")
    assert round(td.length * 30.0) == TOUCHDOWN_TICKS == 13
    rest = float(cf.lowest(rig, cf.sample(rig, idle, np.arange(0.0, idle.length, 1 / 30)), skip=skip).min())
    ks = np.arange(TOUCHDOWN_TICKS + 13)
    feet_ = {side: [next(k for k, b in enumerate(rig.bones) if b.name == n) for n in names]
             for side, names in (("right", ("right_ankle", "right_foot_2", "joint10")),
                                 ("left", ("left_ankle", "left_foot_2", "joint19")))}

    def at(pose, bone):   # a bone's model position per time (its chain's turns and offsets)
        q, t = pose
        q = q / np.linalg.norm(q, axis=-1, keepdims=True)
        chain = [bone]
        while rig.bones[chain[-1]].parent >= 0:
            chain.append(rig.bones[chain[-1]].parent)
        turn, here = None, None
        for k in reversed(chain):
            b = rig.bones[k]
            local = cf._qmul(cf._qmul(np.asarray(b.jo), q[k]), np.asarray(b.ra))
            here = t[k] if turn is None else here + cf._turn(turn, t[k])
            turn = local if turn is None else cf._qmul(turn, local)
        return here

    for name, first in (("g4/fall", 0.77), ("g4/fall_big", 0.0), ("g4/jump", 0.77), ("g4/jump_standing", 0.77)):
        src = named_clip(data, body, name)
        for p in np.arange(first, src.length, 1 / 30):
            t = p + ks / 30
            pose = cf.sample(rig, src, t % src.length if name == "g4/fall_big" else np.minimum(t, src.length))
            w = np.array([cf.fade_weight(k) for k in ks])[None, :, None]
            pose = cf.blend(pose, cf.sample(rig, td, np.minimum(ks / 30, td.length)), w)
            j = np.maximum(ks - TOUCHDOWN_TICKS, 0)
            w = np.array([cf.fade_weight(x) if k >= TOUCHDOWN_TICKS else 0.0 for k, x in zip(ks, j)])[None, :, None]
            pose = cf.blend(pose, cf.sample(rig, idle, j / 30), w)
            feet = cf.lowest(rig, pose, skip=skip)
            assert (feet[:TOUCHDOWN_TICKS] * 1.15 - sole).min() >= low, (name, p)
            assert feet[TOUCHDOWN_TICKS:].min() >= rest - 0.02 / 1.15, (name, p)
            assert cf.lowest(rig, pose, skip=sash).min() > 0.0, (name, p)
            for side, foot in feet_.items():
                ankle_, ball, tip = (at(pose, k) * 1.15 for k in foot)
                down = np.minimum(np.minimum(ankle_[:, 2], ball[:, 2]), tip[:, 2]) < 0.03
                step = np.r_[0.0, np.linalg.norm(np.diff(ball[:, :2], axis=0), axis=1)]
                assert (step * down).sum() <= 0.05, (name, p, side)
    air, ground = ("g4/fall", "g4/fall_big", "g4/jump", "g4/jump_standing"), ("v/hip_idle", "v/sway_walk", "v/sway_run")
    for name, into in [*((a, g) for a in air for g in ground), *((g, a) for g in ground for a in air)]:
        src, new = named_clip(data, body, name), named_clip(data, body, into)
        phases = np.arange(0.0, src.length, 1 / 30)
        for k in range(12):
            t = phases + k / 30
            was = cf.sample(rig, src, t % src.length if name not in air or name == "g4/fall_big" else
                            np.minimum(t, src.length))
            on = cf.sample(rig, new, [min(k / 30, new.length)])
            pose = cf.blend(was, on, cf.fade_weight(k)) if k < cf.FADE_TICKS else on
            assert (cf.lowest(rig, pose, skip=skip) * 1.15 - sole).min() >= low, (name, into, k)
    ankle = next(k for k, b in enumerate(rig.bones) if b.name == "right_ankle")
    jx, jy, jz, jw = qmul(rig.world[rig.bones[ankle].parent], rig.bones[ankle].jo)
    axis = np.array(_turn((-jx, -jy, -jz, jw), (1.0, 0.0, 0.0)))
    bx, by, bz, bw = rig.bones[ankle].q
    for name in ("g4/fall", "g4/jump", "g4/jump_standing"):
        clip = named_clip(data, body, name)
        for q in cf.sample(rig, clip, np.arange(0.0, clip.length, 1 / 30))[0][ankle]:
            d = np.array(qmul(tuple(q / np.linalg.norm(q)), (-bx, -by, -bz, bw)))
            d = -d if d[3] < 0 else d
            assert math.degrees(2.0 * math.atan2(d[:3] @ axis / np.linalg.norm(axis), d[3])) <= 25.0, name
    long = dataclasses.replace(variant, slots={**variant.slots, "touchdown": "hip_idle"})
    with pytest.raises(ValueError, match=r"slots\.touchdown: v/hip_idle lasts 4\.000 s, not garret4's 13 ticks"):
        move_checks(data, read_body(data, body, dirs=(VARIANT_DIR,)), long, "booblord")


# --- booblord v3 (Modkit's tests/_variant_fixtures.py): her shipped recipe with v3's shape, arms and jiggle --------
BOOBLORD_V3 = {
    "mesh": {
        "keep": ["loincloth_front_1", "loincloth_back_1", "vase_joint"],
        "ops": [
            {"op": "push", "name": "bust", "bone": "spine_2", "offset": [0.0719, 0.1257, 0.0575],
             "dir": [0.048, 1.0, -0.209], "height": 0.1378,
             "radius": {"in": 0.092, "out": 0.0675, "up": 0.1383, "down": 0.0917}, "depth": 0.157,
             "fold": 0.062, "groups": [4], "mirror": True},
            {"op": "push", "name": "bust", "bone": "spine_2", "offset": [0.0719, 0.0564, 0.0575],
             "dir": [0.048, 1.0, -0.209], "height": 0.1047,
             "radius": {"in": 0.0659, "out": 0.075, "up": 0.1286, "down": 0.1013}, "depth": 0.0462,
             "fold": 0.131, "groups": [1], "mirror": True},
            {"op": "push", "name": "bust low", "bone": "spine_2", "offset": [0.0719, 0.1257, -0.0416],
             "dir": [0.048, 1.0, -0.08], "height": 0.0752,
             "radius": {"in": 0.0815, "out": 0.0617, "up": 0.0653, "down": 0.0511}, "depth": 0.1596,
             "fold": 0.0, "groups": [4], "mirror": True},
            {"op": "push", "name": "bust low", "bone": "spine_2", "offset": [0.0719, 0.0564, -0.0416],
             "dir": [0.048, 1.0, -0.08], "height": 0.0344,
             "radius": {"in": 0.0664, "out": 0.0606, "up": 0.0658, "down": 0.0499}, "depth": 0.0462,
             "fold": 0.0, "groups": [1], "mirror": True},
            {"op": "push", "name": "bust fill", "bone": "spine_2", "offset": [0.0928, 0.0233, -0.0439],
             "dir": [0.048, 1.0, -0.09], "height": 0.0274,
             "radius": {"in": 0.0519, "out": 0.0709, "up": 0.0335, "down": 0.0421}, "depth": 0.064,
             "fold": 0.0, "groups": [1], "mirror": True},
            {"op": "push", "name": "glutes", "bone": "root_joint", "offset": [0.071, -0.105, -0.09],
             "dir": [0.04, -1.0, 0.0], "height": 0.115,
             "radius": {"in": 0.075, "out": 0.077, "up": 0.13, "down": 0.118}, "depth": 0.1, "fold": 0.48,
             "mirror": True},
            {"op": "scale", "name": "pelvis", "profile": "smooth", "bone": "root_joint",
             "offset": [0.0, -0.0331, -0.09], "radius": [0.4624, 0.1534, 0.17],
             "factors": [1.1578, 1.0, 1.0]},
            {"op": "push", "name": "hips", "bone": "root_joint", "offset": [0.1505, -0.021, -0.1195],
             "dir": [1.0, -0.433, 0.0], "height": 0.0155,
             "radius": {"in": 0.1132, "out": 0.1278, "up": 0.1223, "down": 0.0417}, "depth": 0.08,
             "fold": 0.0, "mirror": True},
            {"op": "taper", "name": "waist", "bone": "root_joint", "offset": [0.0, 0.015, 0.11],
             "factors": [0.86, 0.92], "plateau": 0.05, "half": 0.09, "reach": [0.2, 0.3]},
            {"op": "scale", "name": "thighs", "profile": "smooth", "bone": "left_leg_1",
             "offset": [0.0, -0.014, -0.1515], "radius": [0.112, 0.125, 0.169],
             "factors": [1.02, 1.2195, 1.0], "mirror": True},
            {"op": "push", "name": "hamstring", "bone": "left_leg_1", "offset": [0.0, -0.1, -0.17],
             "dir": [0.0, -1.0, 0.0], "height": 0.026,
             "radius": {"in": 0.07, "out": 0.08, "up": 0.09, "down": 0.1}, "depth": 0.08, "fold": 0.0,
             "mirror": True},
            {"op": "push", "name": "drape", "bone": "loincloth_back_1", "offset": [0.0, -0.2, -0.03],
             "dir": [0.0, -0.05, 1.0], "height": 0.11,
             "radius": {"in": 0.15, "out": 0.15, "up": 0.188, "down": 0.9}, "depth": 0.05, "fold": 1.0,
             "only": ["loincloth_back_1"]},
            {"op": "tuck", "name": "tuck", "groups": [1], "under": [4],
             "skip": ["loincloth_front_1", "loincloth_back_1"], "dir": [0.0, 1.0, 0.0], "margin": 0.003,
             "strict": True, "band": [1.225, 1.28], "faces": True},
            {"op": "tuck", "name": "tuck", "groups": [1], "under": [4],
             "skip": ["loincloth_front_1", "loincloth_back_1"], "dir": [0.0, 1.0, 0.0], "margin": 0.0066,
             "band": [1.28, 9.0], "strict": True, "faces": True}
        ]
    },
    "arms": {"out_deg": 4.0},
    "jiggle": {
        "frees": [
            {"group": 1, "bone": "joint19", "into": "left_foot_2"},
            {"group": 1, "bone": "joint10", "into": "right_foot_2"},
            {"group": 4, "bone": "left_hand", "drop": True}
        ],
        "bones": [
            {"role": "bust", "bone": "joint32", "parent": "spine_2", "shape": ["bust", "bust low", "bust fill"],
             "groups": [1, 4], "takes": ["spine_1", "spine_2", "spine_3", "spine_endnode"], "weight": 0.9,
             "spring": {"freq": 2.6, "damping": 0.1, "mass": 2.4, "travel": [0.05, 0.06, 0.3],
                        "weights": [0.65, 0.42, 1.0], "gain": 3.6, "give": 0.04, "accel": 3.5,
                        "gravity": 0.4, "turn": 0.3, "rot_share": 0.65, "sides": "auto",
                        "centre": "auto", "pivot": [0.0, -0.07, 0.0], "swim": [0.15, 3.0],
                        "pace": 3.0, "squash": [0.0, -0.1, 0.35], "kick": 0.5, "kick_hold": 2.0,
                        "kick_time": 1.5, "impact": 0.125}},
            {"role": "glutes", "bone": "joint39", "parent": "root_joint", "shape": ["glutes"], "groups": [1],
             "takes": ["root_joint", "left_hip", "right_hip"], "weight": 0.75,
             "spring": {"freq": 3.1, "damping": 0.15, "mass": 3.0, "travel": [0.03, 0.045, 0.12],
                        "weights": [0.15, 0.4, 1.0], "gain": 4.3, "give": 0.05, "accel": 3.0,
                        "gravity": 0.4, "turn": 0.25, "rot_share": 0.5, "sides": "auto",
                        "centre": "auto", "pivot": [0.0, 0.06, 0.0], "swim": [0.15, 3.0],
                        "pace": 2.0, "squash": [0.0, -0.08, 0.17], "kick": 0.3, "kick_hold": 2.0,
                        "kick_time": 1.5, "impact": 0.1}}
        ],
        "springs": [
            {"role": "hair1", "bone": "hair_1", "parent": "head",
             "spring": {"freq": 2.0, "damping": 0.2, "travel": 0.06, "gain": 1.0, "gravity": 0.0, "accel": 3.0,
                        "give": 0.04, "rot_share": 1.0, "pivot": "origin", "pace": 2.0}},
            {"role": "hair2", "bone": "hair_2", "parent": "hair_1",
             "spring": {"freq": 2.0, "damping": 0.2, "travel": 0.06, "gain": 1.0, "gravity": 0.0, "accel": 3.0,
                        "give": 0.04, "rot_share": 1.0, "pivot": "origin", "pace": 2.0}},
            {"role": "hair3", "bone": "hair_3", "parent": "hair_2",
             "spring": {"freq": 2.0, "damping": 0.2, "travel": 0.06, "gain": 1.0, "gravity": 0.0, "accel": 3.0,
                        "give": 0.04, "rot_share": 1.0, "pivot": "origin", "pace": 2.0,
                        "centre": [0.0, -0.3169, 1.6447]}}
        ]
    }
}
"""v3's ``mesh``, ``arms`` and ``jiggle`` (``variants.json`` at Step 2.174's bdaf620c: her landing's impact)."""
V3_SHA = "12ee3e6638f4"


def booblord_v3_recipe(sash: bool = False) -> dict:
    """Her shipped recipe with v3's shape, arms and jiggle (a build of a minute, her shipped one's many), and no
    poses, textures, moves, idles, victory_cancel, lods or weapon; with ``sash`` her shipped ``jiggle.springs`` (her
    hair chain and her sash's two chains; not her ponytail's: v3 has no ponytail bones) in place of v3's."""
    from azurkit.tools.characters._player_variants import BUILTIN

    recipe = json.loads(BUILTIN.read_text(encoding="utf-8"))["booblord"]
    springs = recipe["jiggle"]["springs"]
    for key in ("poses", "textures", "slots", "victory_cancel", "lods", "weapon", "idles"):
        recipe.pop(key, None)
    moves = {k for k, clip in recipe["clips"].items() if clip.get("file") in ("moves.glb", "idles.glb")}
    recipe["clips"] = {k: clip for k, clip in recipe["clips"].items() if k not in moves}
    recipe["columns"] = {c: clip for c, clip in recipe["columns"].items() if clip not in moves}
    recipe["carry"] = [c for c in recipe["carry"] if c in recipe["columns"]]
    recipe |= json.loads(json.dumps(BOOBLORD_V3))
    if sash:
        recipe["jiggle"]["springs"] = [r for r in springs if not r["bone"].startswith("ponytail")]
    return recipe


def booblord_v3(sash: bool = False):
    """:func:`booblord_v3_recipe` as the built-in ``booblord`` (without ``sash`` its sha :data:`V3_SHA`)."""
    variant = _player_variants._variant("booblord", booblord_v3_recipe(sash), "built-in")
    assert sash or variant.sha == V3_SHA, variant.sha
    return variant


def _dress(image, worn, **heard) -> tuple[object, list[str]]:
    """``worn`` (a ``Variant``) dressed on ``image``'s vanilla files as a build dresses it (``characters.dressed``,
    the model tools' path, at the variant's own options; ``heard``: ``logic``, ``springs_out``, ``plans``): the
    staging it wrote and the swap's log lines."""
    stamp = gate.verify(str(image), whole=False)
    vanilla = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    staging, _, _, lines = characters.dressed({"species": worn.name}, vanilla, (),
                                              characters.packs_view(stamp.release, mods.PACKS), worn=worn, **heard)
    return staging, lines


def _clips(data: bytes, body: str) -> dict:
    """Every ``banm`` under ``body`` in ``data``: key -> (its bytes, the clip)."""
    toc, prefix = parse_toc(data), f"characters/{body}/".casefold()
    return {k: (data[toc[i].file_offset:toc[i].file_offset + toc[i].size], read_clip(data, toc[i].file_offset))
            for i, name in named_resources(data).items()
            if (k := name.casefold()).startswith(prefix) and toc[i].tag == "banm"}


def test_a_variants_arms_hang_wider_in_every_clip_but_its_own(usa_iso, booblord):
    """D428 (Modkit's Step 2.143): a variant's ``arms`` turns each
    ``*_arm_1`` out by ``out_deg`` about the body's forward axis in every
    clip the build gives its body, her own clips in place, the bakes and
    copies alike, each once (q = r x q of the same build without it, at every
    time) but its recipe's own ``v/`` clips, which pose the arms themselves
    (byte for byte); every other track stays, and her hands hang farther from
    her sides in her idle and walk."""
    from azurkit.tools.characters.retarget import qangle

    variant, body = booblord_v3(), "townspeople/female_2"
    built, plain = (_dress(usa_iso, v)[0] for v in (variant, dataclasses.replace(variant, arms=0.0)))
    mine, theirs = (_clips(bytes(g["characters.xbr"]), body) for g in (built, plain))
    rig = Rig.read(bytes(built["characters.xbr"]), body)
    turns = _player_variants.arm_turns(rig, variant.arms)
    assert variant.arms == 4.0 and len(turns) == 2 and set(mine) == set(theirs)

    def rotation(clip, k, t):
        keyed = {tr.comp - 3: tr.keys for tr in clip.bones if tr.target == k and 3 <= tr.comp <= 6}
        return tuple(evaluate(keyed[c], t) if c in keyed else rig.bones[k].q[c] for c in range(4))
    turned = 0
    for key, (data, clip) in mine.items():
        if key.startswith(f"characters/{body}/{VARIANT_DIR}"):
            assert data == theirs[key][0], key
            continue
        other = theirs[key][1]
        assert [tr for tr in clip.bones if not (tr.target in turns and 3 <= tr.comp <= 6)] == [
            tr for tr in other.bones if not (tr.target in turns and 3 <= tr.comp <= 6)] and clip.markers == other.markers
        for k, r in turns.items():
            for j in range(9):
                t = clip.length * j / 8
                assert qangle(rotation(clip, k, t), qmul(r, rotation(other, k, t))) < 1e-3, (key, j)
        turned += 1
    assert turned == 54   # v3's 54: the kit's one shove, no run slots' copy of her walk
    for clip in ("idle", "walk"):
        hands = [next(k for k, b in enumerate(rig.bones) if b.name == f"{side}_hand") for side in ("left", "right")]
        for j in range(4):
            t = mine[f"characters/{body}/{clip}"][1].length * j / 4
            wide, narrow = (origins(rig, c[f"characters/{body}/{clip}"][1], t) for c in (mine, theirs))
            assert all(abs(wide[h][0]) > abs(narrow[h][0]) + 0.02 for h in hands), (clip, j)


def test_a_variant_with_a_ring_the_balance_and_its_own_sounds_builds(usa_iso, tmp_path, booblord):
    """AZ-635 (Modkit's Step 2.145): a user's variant with X10's ring
    (rotate), the attack balance and sounds of its own (booblord v3's recipe,
    her WAVs and clips beside the file) builds: its log names the ring, the
    balance and her sounds, and the build writes default.xbe, fx.xbr,
    index.xbr, config.xbr and characters.xbr."""
    import shutil

    recipe = booblord_v3_recipe()
    recipe |= {"rotate": True, "attacks": {**recipe["attacks"], "balance": True}}
    for file in (*(_player_variants.SOUNDS / "booblord").glob("*.wav"),
                 *(_player_variants.CLIPS / "booblord").glob("*.glb")):
        shutil.copy(file, tmp_path)
    path = tmp_path / "ringlord.json"
    path.write_text(json.dumps({"ringlord": recipe}), encoding="utf-8")
    staging, log = _dress(usa_iso, load_variants(path.read_text(encoding="utf-8"), str(path))["ringlord"])
    assert any("(X10)" in line and "the attack balance (W14)" in line for line in log)
    assert any(line.startswith("    sounds: 17 waves") for line in log)
    assert sorted(staging.changed()) == [XBE, CHARACTERS, CONFIG, "gamedata/fx.xbr", "gamedata/index/index.xbr"]


def test_a_recipe_from_another_with_finer_triangles_keeps_that_ones_jiggle_bones(usa_iso, tmp_path, monkeypatch,
                                                                                 booblord):
    """Modkit's Step 2.177b (its judge's F2): W29 places a jiggle bone at the
    centroid of the vertices it takes, so a recipe ``from`` another whose
    ``mesh_ops`` subdivide her bust would move its bone: booblord v3 in a
    recipe file and one from it with a finer bust take v3's very origins and
    sides, though its bust bone takes some 30 times the vertices; placed by
    its own centroid the bone sits over 10 mm off."""
    from azurkit.tools.characters._player_character import _variant_body

    op = {"op": "subdivide", "name": "bust finer", "bone": "spine_2", "offset": [0.07, 0.09, 0.0],
          "radius": [0.1, 0.12, 0.14], "edge": 0.012, "groups": [1, 4], "mirror": True}
    path = tmp_path / "variants.json"
    path.write_text(json.dumps({"low": booblord_v3_recipe(), "high": {"from": "low", "mesh_ops": [op]}}),
                    encoding="utf-8")
    got = load_variants(path.read_text(encoding="utf-8"), str(path))
    vanilla, body = _vanilla_characters(usa_iso), "townspeople/female_2"
    with _building(usa_iso):
        low, high = (_variant_body(vanilla, vanilla, body, got[name])[2].bones for name in ("low", "high"))
        assert [(b.bone.role, b.origin, b.sides) for b in high] == [(b.bone.role, b.origin, b.sides) for b in low]
        assert sum(high[0].reach.values()) > 20 * sum(low[0].reach.values())
        monkeypatch.setattr(_player_variants, "parent_of", lambda variant: None)
        own = _variant_body(vanilla, vanilla, body, got["high"])[2].bones
    assert math.dist(own[0].origin, low[0].origin) > 0.01


def test_a_subdivided_variant_builds_with_its_jiggle_on_new_bones_new_geometry_and_its_textures(usa_iso, tmp_path,
                                                                                                booblord):
    """D438, D443, D444, D456, D482, D485, D582 (Modkit's Step 2.154):
    booblord v3 with a mirrored ``subdivide`` over her bust first, a ``tube``
    tail of two segments from her head, a pendant ``tube`` riding her top
    (``follow``, ``reach``), its jiggle bones two new bones and a chain of two
    more on the tail's segments, and a texture (row 1 at 256) builds: the body
    grows by over 3,000 vertices, written whole (every group within 31 bones
    and vanilla's largest push buffer), its four new bones last under
    spine_2, root_joint, head and the first link, every weight summing to 1,
    the bust bone weighing more vertices than v3's 303, its log counting the
    palette entries it added and naming W30's texture, the material row's
    stage naming a new 256 x 256 ``surf``, and the export's checks pass on
    the built file. The pendant swings with the bust, the tail none of it."""
    from azurkit.tools.characters import body_codec, paint
    from azurkit.tools.characters.gltf import export_body

    variant = booblord_v3()
    fine = mesh_edit.SubdivideOp("spine_2", (0.13, 0.17, 0.16), 0.02, (0.0719, 0.09, 0.02), True, groups=(1, 4),
                                 name="bust fine")
    tail = mesh_edit.TubeOp("head", ((0.0, -0.1, 0.08), (0.0, -0.2, 0.0), (0.0, -0.22, -0.2)), (0.02, 0.03, 0.01),
                            0, (0.02, 0.01, 0.28, 0.14), sides=8, rings=12, segments=2, name="tail")
    pendant = mesh_edit.TubeOp("spine_2", ((0.0719, 0.27, 0.07), (0.0719, 0.275, 0.05)), (0.005, 0.005), 0,
                               (0.02, 0.3, 0.05, 0.32), sides=8, rings=4, follow=(1, 4), reach=0.04, name="pendant")
    renamed = {"bust": "jiggle_bust", "glutes": "jiggle_glutes"}
    bones = tuple(dataclasses.replace(jb, bone=renamed[jb.role]) for jb in variant.jiggle.bones)
    links = tuple(dataclasses.replace(bones[0], role=f"tail_{n}", bone=f"tail_{n}", parent=parent, shape=(f"tail {n}",),
                                      groups=(0,), takes=("head",), weight=1.0)
                  for n, parent in ((1, "head"), (2, "tail_1")))
    skin = paint.PaintOp("skin", paint.Region(groups=(1,)), {"hue": (250.0, 30.0), "sat": 0.1, "value": 0.04},
                         paint.Region("spine_2", (0.3, 0.12, 0.1), (0.0, -0.02, 0.17)))
    blender = {k for k, c in variant.clips.items() if c["generator"] == "gltf"}
    worn = dataclasses.replace(   # her Blender idles and moves key her own rig's bones: not this one's
        variant, mesh=dataclasses.replace(variant.mesh, ops=(fine, *variant.mesh.ops, tail, pendant)),
        jiggle=dataclasses.replace(variant.jiggle, frees=(), bones=(*bones, *links), loops=()),
        textures=(paint.TextureSpec(1, 256, ops=(skin,)),), idles={}, slots={},
        clips={k: c for k, c in variant.clips.items() if k not in blender},
        columns={col: c for col, c in variant.columns.items() if c not in blender})
    staging, lines = _dress(usa_iso, worn)
    log = "\n".join(lines)
    assert re.search(r"; 0 palette entries freed, [1-9]\d* added, ", log)
    assert "its textures (W30): row 1 (3 groups): a 256x256 dxt1 texture, 1 paint ops" in log
    body, data = "townspeople/female_2", bytes(staging["characters.xbr"])
    asset = body_codec.read_asset(data, body)
    groups = asset.lods[0].groups
    assert sum(len(g.vertices) for g in groups) > 3427 + 3000 and len(groups) > 6
    assert all(len(g.palette) <= body_codec.PALETTE_MAX and len(g.stored[1]) <= body_codec.PUSH_MAX for g in groups)
    names = asset.bone_names
    assert names[-4:] == ["jiggle_bust", "jiggle_glutes", "tail_1", "tail_2"] and len(names) == 97
    assert [names[asset.bones[k].parent] for k in (93, 94, 95, 96)] == ["spine_2", "root_joint", "head", "tail_1"]
    assert all(abs(sum(v.weights) - 1.0) < 1e-6 for g in groups for v in g.vertices)
    bust = sum(1 for g in groups for v in g.vertices
               if any(w > 0 and g.palette[body_codec.code_entry(b)] == 93 for w, b in zip(v.weights, v.slots)))
    assert bust > 303
    vanilla = _vanilla_characters(usa_iso)
    own = body_codec.read_asset(vanilla, body).lods[0].groups[0]
    riders = [v.position for g in groups if g.material == own.material for v in g.vertices
              if any(w > 0 and g.palette[body_codec.code_entry(b)] == 93 for w, b in zip(v.weights, v.slots))]
    assert len(riders) >= 8 * 4 and all(p[1] > 0.1 for p in riders)
    toc = parse_toc(data)
    stage = render.material(data, toc, 2955, 1)["textures"][0]
    assert stage >= len(parse_toc(vanilla))
    assert render.surf_image(data, toc, stage).shape == (256, 256, 4)
    export = export_body(data, body, tmp_path / "out", ["walk"], source_vanilla=False)
    assert export.bones == 97 and export.checks.rest_m < 1e-5 and export.checks.clip_matrix < 1e-5


def _x14(xbe: bytes) -> tuple[str, dict[int, str]]:
    """X14's table in the built ``xbe``: its dir and each slot it names (a miss left out; inside :func:`_building`)."""
    from azurkit.tools.characters._player_sounds import SOUND_HOOKS, SOUNDS_TABLE, TABLE_SIZE

    at = _at(xbe, SOUND_HOOKS[0], SOUNDS_TABLE.symbol)
    table = bytes(xbe[at:at + TABLE_SIZE])
    dir_at, count = struct.unpack_from("<HH", table)

    def name(off: int) -> str:
        return table[off:table.index(b"\0", off)].decode()
    return name(dir_at), {slot: name(off) for slot, off in enumerate(struct.unpack_from(f"<{count}H", table, 4)) if off}


def _loads(xbe: bytes, site) -> str | bytes:
    """What an X15 site loads in ``xbe`` (either release): the path its imm32 points at, or its bytes when it holds
    its vanilla ones (inside :func:`_building`)."""
    _, off, vanilla = ports.xbe_site(xbe, site.va, site.original)
    if bytes(xbe[off:off + 5]) == vanilla:
        return vanilla
    at = ports.resolve_va_to_file(xbe, struct.unpack_from("<I", xbe, off + 1)[0])
    return bytes(xbe[at:xbe.index(b"\0", at)]).decode()


OWNERS = {"hurt": "hit.wav", "hurt_a": "attack1.wav", "roll": "roll.wav", "jump": "hup.wav", "fall": "fall.wav",
          "climb": "grunt.wav"}
"""Booblord's waves that are the owner's WAVs (leaf -> file)."""


@pytest.mark.parametrize("release", RELEASES)
def test_booblords_attacks_only_whoosh_and_her_other_sounds_are_the_owners_wavs(release, request, booblord):
    """D386, D405-D408, D418, D699 (Modkit's Steps 2.141, 2.144, 2.180):
    booblord's sounds are the owner's WAVs and her whooshes. X14's table
    names her dir fx/sound/v/booblord and binds "hurt" (two takes) in the 6
    hurt slots and "climb" in hoist and climb_up_edge, "" in the other voice
    slots, and leaves Garret's 9 effect slots to his dir; every attack
    column binds one of her whooshes (her finishers "twirl", the roll
    "roll", her hand spin's columns "hspin", her casts the whip's, every
    other the spin's or stomp's), no column a shout; X15 points a jump at
    .../jump, a long fall's landing at .../fall and the falling scream at
    .../death, a name no index.xbr record has (silent), and leaves the step
    and landing paths Garret's. fx.xbr gains her 17 waves (the 11 whooshes as
    made, the 6 WAVs as read), each named, with its index.xbr record; every
    other entry is her build's without her sounds. The log names each WAV's
    sha256. On USA a rebuild is identical and L1 is clean. X41 hooks her
    pose on both releases; her shipped recipe's sha is her graded one. A
    variant with no fall WAV plays its hurt at the ouch."""
    from azurkit.tools.characters._player_slots import BASE_CLIPS
    from azurkit.tools.characters._player_sounds import (ATTACK_SLOT, ROLE_SLOTS, SHOUT_ROWS, VOICE_SLOTS,
                                                         XBE_SOUND_SITES, variant_roles)
    from azurkit.tools.characters._player_variants import SOUNDS, UNGRADED, sound_dir, waves
    from azurkit.tools.characters.index_xbr import parse_index_xbr
    from azurkit.tools.characters.xbox_adpcm import read_wav, wave_entry
    from devkit.sim import l1

    image = request.getfixturevalue(f"{release.name}_iso")
    variant = booblord_v3()
    game, log = _dress(image, variant)
    recipe = booblord_v3_recipe()
    unvoiced, _ = _dress(image, load_variants(json.dumps(   # her clip file beside it
        {"booblord": {k: v for k, v in recipe.items() if k not in UNGRADED}}),
        str(_player_variants.CLIPS / "booblord" / "unvoiced.json"))["booblord"])
    with iso.Reader(image) as r:
        vanilla_xbe, config = r.read(XBE), r.read(CONFIG)
    xbe = bytes(game["default.xbe"])
    with _building(image):
        folder, binds = _x14(xbe)
        assert ports.verify_trampoline_patch(xbe, JIGGLE_HOOK) == "applied"   # X41 at USA 0xCB5CB, Europe 0xCB74B
    columns = ports.XbrDocument.from_bytes(config).keyed_section("attacks_anims").col_names()
    effects = ("touchdown", "step_up", "step_down", "slide", "climb_down_edge", "climb_up", "climb_down",
               "climb_left", "climb_right")
    heard = {BASE_CLIPS.index(slot): "hurt" for slot in ROLE_SLOTS["hurt"]} | {
        BASE_CLIPS.index(slot): "climb" for slot in ("hoist", "climb_up_edge")}
    sfx = {col: name for name, p in variant.sfx.items() for col in p["columns"]} | {"roll forward": "roll"}
    assert folder == sound_dir(variant) == "fx/sound/v/booblord" and len(VOICE_SLOTS) == 30
    assert {slot: binds.get(slot) for slot in VOICE_SLOTS} == dict.fromkeys(VOICE_SLOTS, "") | heard
    assert not {BASE_CLIPS.index(clip) for clip in effects} & set(binds)
    assert {col: binds.get(ATTACK_SLOT + k) for k, col in enumerate(columns)} == sfx and len(sfx) == 24
    assert {col: sfx[col] for col in ("finish", "finish2", "finish3", "sweep1", "sweep2", "sweep ledge", "basic3",
                                      "down", "elemental1", "hose_attack_3")} == {
        "finish": "twirl", "finish2": "twirl", "finish3": "twirl", "sweep1": "hspin", "sweep2": "hspin",
        "sweep ledge": "hspin", "basic3": "spin", "down": "stomp", "elemental1": "whip", "hose_attack_3": "spin"}
    anims = ports.XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
    assert not any(anims.find_cell(col, row, c).type_code for c, col in enumerate(columns) for row in SHOUT_ROWS)
    index, old = parse_index_xbr(bytes(game["index.xbr"])), parse_index_xbr(bytes(unvoiced["index.xbr"]))
    keys = {r.key for r in index.records}
    loaded = {"ouch": "fall", "fallingdeath": "death", "jump": "jump"}
    with _building(image):
        sites = {site: _loads(xbe, site) for site in XBE_SOUND_SITES}
    for site, loads in sites.items():
        if site.sound in loaded:
            assert loads == f"{folder}/{loaded[site.sound]}" and (loads in keys) == (site.sound != "fallingdeath"), (
                hex(site.va))
        else:   # the wing flap, the steps and the landings
            assert isinstance(loads, bytes), hex(site.va)
    made = {f"{folder}/{leaf}": wave_entry(samples) for leaf, samples in waves(variant).items()} | {
        f"{folder}/{leaf}": wave_entry(read_wav(SOUNDS / "booblord" / file)[0]) for leaf, file in OWNERS.items()}
    fx, plain = bytes(game["fx.xbr"]), bytes(unvoiced["fx.xbr"])
    toc, before = parse_toc(fx), parse_toc(plain)
    named = {key: i for i, key in named_resources(fx).items()}
    assert len(made) == 17 and len(toc) == len(before) + 17
    assert {p["generator"] for p in variant.sfx.values()} == {"whoosh"} and set(sfx.values()) - set(variant.sfx) == {
        "roll"}
    assert {leaf: len(s) for leaf, s in waves(variant).items() if leaf.startswith("hspin")} == {
        "hspin": 30870, "hspin_a": 30870}   # 1.4 s at 22050 Hz
    assert {key: (toc[named[key]].tag, fx[toc[named[key]].file_offset:][:toc[named[key]].size]) for key in made} == {
        key: ("wave", entry) for key, entry in made.items()}
    assert all(fx[e.file_offset:e.file_offset + e.size] == plain[o.file_offset:o.file_offset + o.size]
               and (e.tag, e.size) == (o.tag, o.size) for e, o in zip(toc, before))
    assert {(r.key, r.archive, r.fourcc) for r in set(index.records) - set(old.records)} == {
        (key, "fx.xbr", "wave") for key in made} and len(index.records) == len(old.records) + 17
    for leaf, file in OWNERS.items():
        sha = hashlib.sha256((SOUNDS / "booblord" / file).read_bytes()).hexdigest()[:12]
        assert any(f"recipe {file}: {leaf} (sha256 {sha})" in line for line in log), file
    assert [variant_roles("t", "d", ["basic1", "roll forward"], {}, True, frozenset(r)).xbe["ouch"]
            for r in ((), {"hurt"}, {"hurt", "fall"})] == ["d/hurt", "d/hurt", "d/fall"]
    if release is gate.USA:   # the simulator runs USA's
        again, _ = _dress(image, variant)
        assert {k: bytes(v) for k, v in again.changed().items()} == {k: bytes(v) for k, v in game.changed().items()}
        assert l1.check(vanilla_xbe, xbe) == []
    assert builtins()["booblord"].sha == "75d89c537286"   # the booblord pass's rework, places kept (Step 4.48b)


def _vanilla_file(image, path: str) -> bytes:
    with iso.Reader(image) as r:
        return r.read(path)


def _engine(image, species: str, **options):
    """``species`` dressed on a fresh staging of ``image``'s vanilla files by the swap's own entry
    (``apply_player_model``, which ``characters.dressed`` calls for both hosts) with ``options`` as given: the staging."""
    stamp = gate.verify(str(image), whole=False)
    vanilla = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    staging = ports.IsoStaging(vanilla)
    with ports.building(ports.Build(vanilla, taken=[], packs=characters.packs_view(stamp.release, mods.PACKS))):
        characters._swap().apply_player_model(staging, species, **options)
    return staging


# --- a built-in variant's build (Modkit's test_a_variant_plays_its_recipes_clips_and_spares_the_npcs) -------------
def _param(xbe: bytes, hook, symbol: str) -> float:
    """A shim's float param in the built ``xbe`` (inside :func:`_building`)."""
    return struct.unpack_from("<f", xbe, _at(xbe, hook, symbol))[0]


def _payloads(characters: bytes, prefix: str) -> dict[str, str]:
    """sha256[:12] of each ``characters.xbr`` resource named under ``prefix``."""
    toc = parse_toc(characters)
    return {name.casefold(): hashlib.sha256(characters[toc[i].file_offset:toc[i].file_offset + toc[i].size])
            .hexdigest()[:12] for i, name in named_resources(characters).items()
            if name.casefold().startswith(prefix)}


def _yaw(rig: Rig, clip, bone: int) -> float:
    """How far (degrees) ``bone`` turns about z over ``clip``."""
    total, prev = 0.0, pose(rig, clip, 0.0)[bone]
    for k in range(1, 401):
        q = pose(rig, clip, clip.length * k / 400)[bone]
        step = 2 * math.atan2(q[2], q[3]) - 2 * math.atan2(prev[2], prev[3])
        total, prev = total + (step + math.pi) % (2 * math.pi) - math.pi, q
    return math.degrees(total)



def _cloned_only(schema, vanilla: bytes, characters: bytes, body: str, fx, grafts=(), keys=None) -> None:
    """D385, D446 (Steps 2.140, 2.157): ``body``'s default fx in
    ``characters`` and everything it reaches are vanilla's byte for byte
    (every NPC of the body plays its own), and the player's clone
    (``characters/<body>/v/fx/fx_default``; ``keys``: another graph and
    its clone, the stand's of Step 2.155b) is vanilla's graph but at
    ``fx``'s attributes, links (Step 2.145), inherit modes and material
    rows (Step 2.146), the same length; each of its relocated fields names
    the vanilla texture it named or a new copy of its target, each copy
    vanilla's bytes but at its own relocated fields (and a material's
    edited fields), so nothing it reaches is shared but the textures; a
    ``texture`` edit's field names a new texture of the same format and
    size (Step 2.157), a platform's on its material stage (a new list
    the size of the one it drew); a ``mesh`` edit's copies are new
    meshes (``tests/test_fx_mesh.py`` reads them) at the descriptor's
    bounds and fourcc, and a ``parent`` edit's DAG parent the edit's
    (Step 2.155e); a template's ``grafts`` add its records at the
    end (their own reading is ``tests/test_xbr_clone.py``'s), the clone
    and its ndbg vanilla's in front but for their counts and tables, and
    an edit of a grafted record reads back on it."""
    toc, built_toc = parse_toc(vanilla), parse_toc(characters)
    src_key, clone_key = keys or (fx_edit.default_key(body), fx_edit.clone_key(body))
    src = next(i for i, n in named_resources(vanilla).items() if n.casefold() == src_key)
    clone = next(i for i, n in named_resources(characters).items() if n.casefold() == clone_key)
    for i in closure(vanilla, [src]):   # the NPCs' graph and its closure, vanilla's
        assert characters[built_toc[i].file_offset:][:built_toc[i].size] == vanilla[toc[i].file_offset:][:toc[i].size]
    graphs = [Graph(vanilla, toc, toc[src], schema), Graph(characters, built_toc, built_toc[clone], schema)]
    own = len(graphs[0].recs)
    added = [(n, kind) for g in grafts for _, n, kind in fx_templates.GRAFTS[g["template"]].records]
    assert list(zip(graphs[1].names[own:], graphs[1].types[own:])) == added
    reverts: dict[int, list[tuple[int, int]]] = {src: []}   # vanilla entry -> (offset, length) the edits change
    grown = {src: [(0, 8), (0x14, 8)], graphs[0].ndbg_index: [(8, 8)]} if added else {}   # counts and tables
    recoloured = set()   # the clone's fields naming a new texture (Step 2.157)
    restaged: set[tuple[int, int]] = set()   # (vanilla gshd, its stage field) naming a new texture (Step 2.155e)
    remeshed: set[int] = set()   # the vanilla rdms and push buffers a mesh edit's copies replace (Step 2.155e)
    for edit in fx:
        if edit["record"] >= own:   # a grafted record's edit, on it
            r = edit["record"]
            assert {k: graphs[1].attr_named(r, k) for k in edit.get("set", {})} == pytest.approx(
                edit.get("set", {}), rel=1e-6)
            for rdms, _ in render.platform_bindings(graphs[1], r, every=True) if "material" in edit else ():
                gshd, row = struct.unpack_from("<II", characters, built_toc[rdms].file_offset + 4)
                assert {k: render.material(characters, built_toc, gshd, row)[k] for k in edit["material"]} == (
                    pytest.approx(edit["material"], rel=1e-6))
            continue
        rec = graphs[0].recs[edit["record"]]
        if "texture" in edit and edit["type"] != "platform":   # a renderer's: a new one, the one it drew's format, size
            recoloured.add(rec + 0x18)
        binds = render.platform_bindings(graphs[0], edit["record"], every=True) if edit["type"] == "platform" else []
        if "texture" in edit and binds:   # a platform's material stage (Step 2.155e)
            gshd, row = struct.unpack_from("<II", vanilla, toc[binds[0][0]].file_offset + 4)
            stage = render.material_row(vanilla, toc, gshd, row) - toc[gshd].file_offset + 100 + 124 * edit[
                "texture"].get("stage", 0)
            restaged.add((gshd, stage))
        if "mesh" in edit:   # Step 2.155e: its copies new; the descriptor's bounds, sub-bounds and fourcc the mesh's
            remeshed |= set(binds[0])
            d = list_at(graphs[0].s, rec + 0x1C)[0]
            sub, n = list_at(graphs[0].s, d + 48)
            reverts[src] += [(d + 4, 24), (sub, 24 * n), (list_at(graphs[0].s, d + 64)[0] + 8, 4)]
        if "parent" in edit:
            assert graphs[1].parent(edit["record"]) == edit["parent"]
            reverts[src].append((rec + 0x18, 4))
        start, _ = list_at(graphs[0].s, rec + 8)
        for attr, value in edit.get("set", {}).items():
            at = start + 4 * schema.types[edit["type"]].attrs.index(attr)
            assert struct.unpack_from("<f", graphs[1].s, at)[0] == pytest.approx(value, rel=1e-6), attr
            reverts[src].append((at, 4))
        links, _ = list_at(graphs[0].s, rec + 0x10)
        for link in edit.get("links", []):   # D416: the dome keyed by the nova's switch
            old, new = (g.links(edit["record"])[link["index"]] for g in graphs)
            assert (new.src_plug, new.curve, new.dst, graphs[1].plug_name(new.dst, new.dst_plug)) == (
                old.src_plug, old.curve, link.get("dst", old.dst),
                link.get("dst_plug", graphs[0].plug_name(old.dst, old.dst_plug)))
            assert (new.weight, new.factor) == pytest.approx(
                (link.get("weight", old.weight), link.get("factor", old.factor)), rel=1e-6)
            reverts[src].append((links + 24 * link["index"], 24))
        if "inherit" in edit:
            assert struct.unpack_from("<I", graphs[1].s, rec + 0x28)[0] == edit["inherit"]
            reverts[src].append((rec + 0x28, 4))
        if "material" in edit:   # Step 2.146: the dome's material row, on the clone's copy alone
            (rdms, _), = render.platform_bindings(graphs[0], edit["record"], every=True)
            gshd, row = struct.unpack_from("<II", vanilla, toc[rdms].file_offset + 4)
            at = render.material_row(vanilla, toc, gshd, row) - toc[gshd].file_offset
            reverts.setdefault(gshd, []).extend((at + render.MATERIAL_FIELDS[k][0], 4) for k in edit["material"])
            materials = {k: v for k, v in edit["material"].items()}
    rows, built_rows = sorted(relocations(vanilla)), sorted(relocations(characters))
    pairs, seen = [(src, clone)], set()
    while pairs:
        i, j = pairs.pop()
        if (i, j) in seen:
            continue
        seen.add((i, j))
        assert j >= len(toc) and (built_toc[j].tag in ("pbrc", "pbrw") if i in remeshed and toc[i].tag in ("pbrc", "pbrw")
                                  else built_toc[j].tag == toc[i].tag)   # a new copy; only a remeshed pb retags
        refs = refs_in(vanilla, toc, i, rows)
        got = [(off, u) for off, u in refs_in(characters, built_toc, j, built_rows) if off < toc[i].size]
        assert [off for off, _ in got] == [off for off, _ in refs]
        if i in remeshed:   # a mesh edit's: its own bytes, its material the copy's
            pairs += [(t, u) for (_, t), (_, u) in zip(refs, got)]
            continue
        assert (built_toc[j].size > toc[i].size) if i in grown else built_toc[j].size == toc[i].size
        restored = bytearray(characters[built_toc[j].file_offset:][:toc[i].size])
        for at, n in grown.get(i, ()):
            restored[at:at + n] = vanilla[toc[i].file_offset + at:][:n]
        for (off, t), (_, u) in zip(refs, got):
            if (i == src and off in recoloured) or (i, off) in restaged:
                assert (u >= len(toc), built_toc[u].tag, built_toc[u].size) == (True, "surf", toc[t].size)
                new, old = (textures.info(d[e.file_offset:][:e.size]) for d, e in ((characters, built_toc[u]),
                                                                                    (vanilla, toc[t])))
                assert {**new, "list": len(new.get("list", ()))} == {**old, "list": len(old.get("list", ()))}
            elif toc[t].tag == "surf":
                assert u == t
            else:
                pairs.append((t, u))
            restored[off:off + 4] = vanilla[toc[i].file_offset + off:][:4]
        if toc[i].tag == "gshd" and i in reverts:
            assert {k: render.material(characters, built_toc, j, row)[k] for k in materials} == pytest.approx(
                materials, rel=1e-6)
        for at, n in reverts.get(i, ()):
            restored[at:at + n] = vanilla[toc[i].file_offset + at:][:n]
        assert hashlib.sha256(restored).digest() == hashlib.sha256(
            vanilla[toc[i].file_offset:][:toc[i].size]).digest(), (i, toc[i].tag)


# Each built-in's authored clips (on, off, forward, corner, low z, high z at its drawn scale; root yaw
# degrees, None: its source clip's own), its logic (reach, damage), X21's reach (None: no X21), how
# many columns X33 carries, X33's held mask and its mesh (W24: vertices and normals written, the chest's
# forward depth over vanilla's, the hips' half-width, the butt's back; None: none).
# air_elemental is its own build's overlay (W23), not a variant.
BUILT = {
    "air_elemental": ({"gust": (0.36, 0.947, 13.138, 13.193, 0.0, 2.4, None)}, (2.465, 0.738), 13.19, 20, 0x1C0,
                      None),
    "beamlord": ({"beam": (0.373, 0.657, 14.0, 14.036, -1.0, 3.0, None),
                  "sweep": (0.373, 0.657, 14.035, 16.511, -1.0, 3.0, None),
                  "nova": (0.373, 0.657, 2.80, 3.96, 0.0, 2.4, None),
                  "blast": (0.3, 2.697, 2.80, 3.96, -2.5, 2.0, None)},
                 (2.80, 1.0), 3.96, 0, 0xEFFFFF, None),
    "booblord": ({"spin": (0.04, 0.36, 0.897, 1.269, 0.0, 1.84, 720.0),
                  "twirl": (0.10, 0.90, 0.897, 1.269, 0.0, 1.84, 1440.0),
                  "stomp": (0.42, 0.57, 1.035, 1.464, 0.0, 1.38, 0.0),
                  "hspin": (0.21, 1.407, 1.725, 2.44, 0.0, 1.725, 720.0)},
                 (1.725, 0.6), None, 19, 0, (768, 882, 1.854, 0.183, -0.203)),
}



@pytest.mark.parametrize("name", sorted(BUILT))
def test_a_variant_plays_its_recipes_clips_and_spares_the_npcs(usa_iso, name, monkeypatch, booblord):
    """D332, D359-D361 (Step 2.137): a built-in variant's recipe columns
    play its own clips (W3's Anims ``v/<clip>``), every other column what
    the base's own build plays there (booblord's hose_attack_3 the
    bare-hands kit's shove, as her townswoman base swings it since Step
    2.159a, its X3 box her farthest reach, D237; her three casts her whip
    since Step 2.171), and neither X3 nor X13's fill touches them (the
    sweep's bar turns: filled, it would be its bounds);
    X10 is off; each clip's box opens and closes when its recipe says, as far
    ahead and as high as it says at the body's drawn scale, the spin's
    root turning its turns; the bake's hidden props stay hidden and no
    authored clip keys ``m_feet`` (no lunge); the grown ``m_damage`` rests
    off and no baked clip keys it (C5); the logic reads its recipe's
    damage and the reach of its idle swings (basic1 and the sweeps,
    AZ-566, D719), and a plan wearing it reads verified though booblord's
    hand spin reaches 1.725 m ahead (her shove's X3 box, hose_attack_3, no
    longer counts) and the air elemental's basic1 2.47 m, short of
    garret4's 2.76 m (D726: reach never flags); X21 searches no farther than its melee
    boxes; X33 carries its ``carry`` columns and chains its ``held`` ones
    while held (beamlord's every column but the roll, planted: Step 2.153,
    D450; at D449's speed 2.0 and damage 1.0 his logic reads 1.0); X41
    hooks the pose for booblord, whose jiggle has real-time springs
    (Step 2.156), and for beamlord, whose balthazar_airship's locks
    ``chains.json`` swings (Step 2.169f), not the air elemental's overlay;
    and the base's NPCs keep
    their own clips (and Balthazar his fx) byte for byte, but where the
    variant's ``arms`` restyle them (W28, Step 2.143).  booblord's
    spins are 0.897 m ahead of her (1.27 m to the corner), each turning
    its turns, her jump attack the spin; her B (sweep1, sweep2, sweep
    ledge) the hand spin (D378): two turns over 1.4 s with her right
    hand's end node planted within 0.02 model units of (0, 0, 0.05) at
    every root key of the plant, no bone deeper than the planted pose's
    lowest as she leans in and out, its box 1.725 m all round;
    beamlord's beam and sweep run 14 m ahead (ranged: the sweep's corner
    16.51 m) over his lightning's switch window, 1 m to
    either side and -1 to 3 m high, his nova 2.80 m ahead and 3.96 m to
    its corner (melee, so the logic's anchor and X21's 3.96 m), his jump
    attack's blast (Step 2.153, D451) a bolt column under him from 0.3 s,
    then a box round him growing to 2.8 m half, on to 2.7 s, -2.5 to 2 m
    high (the same 2.80 m and 3.96 m), and (Step 2.153b) its bolt's
    emitter [23] within 0.03 model units of his two hand endnodes' mean
    at every time of the bolt phase, then the switch 0 and the aim unturned at his
    feet, its extents the box's x half over blast.dome_unit (the grafted
    floor dome's rim on the box's edge) and 1 outside the blast, and
    (AZ-669, Step 2.153c) the origin of the fx transform it drives
    ([12], scaling about its pivot) within 1 mm of his feet at the
    blast's start, its grow_until and either side of its until; and
    (D385, Step 2.140) the beams' switch keyed to its switch_z (0.02 since
    Step 2.145: the bolts on, the dome unseen) from the clip's start to
    the window's end, the beams' aim pitched up 10.1 degrees and the
    nova's down 30 under its whirl, the player's clone of his
    ``fx/fx_default`` changed only at the recipe's attributes, links and
    inherit modes, the same length, and every NPC's graph vanilla's
    (Step 2.157, D446),
    and garret4's hitsThroughWalls 1.0 in his build (0.0 in booblord's);
    (D416, Step 2.145) the nova's switch ramps 0.02 to 1.0 by the box's
    grow_until of the window and holds it to the window's end, then
    (AZ-658, D479, Step 2.153b) falls straight to 0 over beamlord's
    switch_fade (0.24 s) with the aim turning on through it, his box
    still closing at the window's end; (D433,
    D442, Step 2.157) the game's electric shield grafted under his
    spine_2 (records 64-67), keyed by it: the switch's stream link
    weighs 0 (the stream off), its gameVisible link goes to the shield's
    platform at weight 1 (opacity z), the shield at scale 1.25, its
    shader's ShaderAlpha and its material's opacity 0.45 and both its
    textures recoloured, on the clone's copies; the old dome undriven.  W24 (Step 2.142, D370, D376; v3
    Step 2.143, D403; booblord here her v3, ``tests/_variant_fixtures.py``,
    Step 2.154): her mesh moves 768 vertices and rewrites 882
    normals, her chest 1.85 times as deep, her hips 0.183 half-wide and
    her butt 0.203 behind, her front sash and vase where they were, and
    nothing else of any mesh changes;
    beamlord's mesh is vanilla's.  D374 (Step 2.140, W23): the air elemental's own build
    (no variant worn) throws its wind on B (sweep1, sweep2, sweep ledge):
    a 2.4 m box 1.2 m up whose centre travels from 1 to 12 m ahead over
    0.36-0.95 s (ranged), its wind puff m_turbulence on the same path at
    3 times its size, the three columns out of X33's carry and X13's fill
    (0xEFFE3F) and W14's balance (garret4's multiplier: a thrown box
    passes a target once); its grade and logic are its own build's.
    D414, D415 (Step 2.145): held, B throws again as each box arrives (the
    three columns X33's held mask 0x1C0, their Move end1 arrive / length,
    0.8636) and its hits skip the wall test (hitsThroughWalls 1.0); the
    plain build has neither. Step 2.135 (X36, the critique's C2): its
    second attack set plays the gust in basic1-3, so its X21 searches out
    to the gust's 13.19 m. D434 (Step 2.155): the body grows
    spideyzar's 14 fx bind names at his own records, the gust keys
    m_projectile on the box's path at the floor (extents 1.5, on over the
    travel) and nothing keys m_whirlwind_trigger; no clip of the body keys
    the drain switch, the projectile and death-beam triggers, the iceball
    or the trigger (AZ-453's class); spideyzar's body and fx are
    vanilla's, and (D501, Step 2.155b) the player's clone of his graph
    the ring stands (``characters/air_elemental/v/fx/fx_stand``) is his
    but at the recipe's ``fx_ring.stand.fx``."""
    with _building(usa_iso):
        _plays(usa_iso, name, monkeypatch, Schema(_vanilla_file(usa_iso, XBE)))


def _plays(usa_iso, name: str, monkeypatch, schema) -> None:
    """:func:`test_a_variant_plays_its_recipes_clips_and_spares_the_npcs`' checks of ``name``'s build."""
    variant = (booblord_v3() if name == "booblord" else builtins().get(name)) or overlay(name)
    overlaid = variant.source == "overlay"
    clips, (reach, damage), search, carried, held_mask, reshaped = BUILT[name]
    logic = AttackLogic()
    built = _engine(usa_iso, variant.base, variant=None if overlaid else variant, logic=logic, **options(variant))
    kept = {k: v for k, v in options(variant).items() if k in ("mode", "size", "sounds", "attack_balance",
                                                                "attack_ground")}
    monkeypatch.delitem(_player_variants.OVERLAYS, name, raising=False)   # the base's own build, without its overlay
    plain = _engine(usa_iso, variant.base, **kept)
    anims = [ports.XbrDocument.from_bytes(bytes(g["config.xbr"])).keyed_section("attacks_anims") for g in (built, plain)]
    columns = anims[0].col_names()
    played = [[a.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)] for a in anims]
    recipe = sum(1 << i for i, col in enumerate(columns) if col in variant.columns)
    vanilla = _vanilla_characters(usa_iso)
    base = read_body(vanilla, ports.XbrDocument.from_bytes(bytes(built["config.xbr"])).keyed_section(
        "critters_engine").find_cell(variant.base, "body", None).string_value)
    # every other column what the base's own build plays (D421: a townswoman's, Balthazar's attacks)
    assert played[0] == [variant.clip_of(col) or played[1][i] for i, col in enumerate(columns)]
    xbe, base_xbe = bytes(built["default.xbe"]), bytes(plain["default.xbe"])
    x3 = [round(_param(x, DAMAGE_MARKER, "_player_model_x3_columns"))
          if ports.verify_trampoline_patch(x, DAMAGE_MARKER) == "applied" else 0 for x in (xbe, base_xbe)]
    site = ports.resolve_va_to_file(xbe, ROTATE_HOOK.va)   # X10's site keeps vanilla's CALL of anim_change
    assert x3[0] == x3[1] & ~recipe and xbe[site:site + len(ROTATE_HOOK.replaced_bytes)] == ROTATE_HOOK.replaced_bytes
    fill = [round(_param(x, ATTACK_BOX_HOOK, "_player_attack_ground_mask")) for x in (xbe, base_xbe)]
    assert fill[0] == fill[1] & ~recipe != fill[1]   # X13 leaves a recipe's own boxes as keyed (the sweep's bar)

    characters, body_name = bytes(built["characters.xbr"]), base.name
    body, rig = read_body(characters, body_name, dirs=(VARIANT_DIR,)), Rig.read(characters, body_name)
    scale = 1.15 if variant.base.startswith("town_female") else 1.0
    root = next(k for k, b in enumerate(rig.bones) if b.parent < 0)
    hidden = {k for k, b in enumerate(rig.bones) if b.name == "vase_joint"}
    feet = body.markers.index("m_feet")
    for clip, (on, off, ahead, corner, low, high, turned) in clips.items():
        (w,) = damage_windows(characters, body_name, VARIANT_DIR + clip, scale)
        assert ((w.on, w.off, w.forward, w.reach, w.low[2], w.high[2])
                == pytest.approx((on, off, ahead, corner, low, high), abs=6e-3)), clip
        made = named_clip(characters, body_name, VARIANT_DIR + clip)
        assert turned is None or _yaw(rig, made, root) == pytest.approx(turned, abs=0.5), clip
        params = variant.clips[clip]
        if "switch_z" in params or "switch_ramp" in params:   # D385: the switch from switch_from to the window's
            keyed = {(tr.target, tr.comp): tr.keys for tr in made.markers}   # end, the aim's pitch
            switch, aim = (body.markers.index(params[k]) for k in ("switch", "aim"))
            if "switch_z" in params:
                assert [round(evaluate(keyed[switch, 2], t), 3) for t in (
                    params.get("switch_from", w.on) + 0.01, (w.on + w.off) / 2, w.off + 0.01)] == [
                        params["switch_z"]] * 2 + [0.0]
            else:   # D416: the nova's ramp, 0.02 at the window's start to 1.0 as the box is grown; AZ-658 (D479):
                # a fade to 0 switch_fade after the window, the whirl turning on through it, the box closing on time
                values = [round(k[1], 4) for k in keyed[switch, 2]]   # the last (0 at the clip's end) unless the fade ends it
                assert values[:6] == [0.0, 0.0, 0.02, 1.0, 1.0, 0.0] and values[6:] in ([], [0.0])
                assert keyed[switch, 2][3][0] == pytest.approx(
                    w.on + params["box"]["grow_until"] * (w.off - w.on), abs=0.01)
                fade = params.get("switch_fade", 0.0)
                assert [keyed[switch, 2][5][0], keyed[aim, 3][-1][0]] == pytest.approx(
                    [w.off + (fade or RAMP / 2), w.off + fade], abs=0.01)
                assert evaluate(keyed[switch, 2], w.off + (fade / 2 if fade else 2 * RAMP)) == pytest.approx(
                    0.5 if fade else 0.0, abs=0.03)   # halfway down a fade, else past the step
            pitch = _rx(math.radians(params.get("level_deg", params.get("pitch_deg", 0.0))))
            first = keyed[aim, 3][0][0]   # the aim's first key: W's start for a turning aim
            assert [evaluate(keyed[aim, c], first) for c in range(3, 7)] == pytest.approx(
                qmul(_rz(-math.radians(params.get("sweep_deg", 0.0))), pitch), abs=1e-4), clip
        assert {(tr.target, tr.comp) for tr in made.bones if tr.target in hidden} >= {
            (k, c) for k in hidden for c in (7, 8, 9)} and not any(tr.target == feet for tr in made.markers)
        if params.get("generator") == "gust":   # D374: the box and the wind puff on one path, the puff x3
            keyed = {(tr.target, tr.comp): tr.keys for tr in made.markers}
            box, cloud = body.markers.index("m_damage"), body.markers.index(params["cloud"])
            assert [round(evaluate(keyed[box, 1], t), 3) for t in (params["release"], params["arrive"])] == [
                params["from"], params["to"]]
            assert [keyed[cloud, c] for c in range(3)] == [keyed[box, c] for c in range(3)]
            assert [evaluate(keyed[cloud, c], w.on) for c in (7, 8, 9)] == pytest.approx(
                [params["cloud_scale"] * v for v in dict(marker_records(characters, body_name))[params["cloud"]][7:10]])
            funnel = body.markers.index(params["funnel"]["marker"])   # D434: his tornado's frame on the same path
            mid = (params["release"] + params["arrive"]) / 2
            assert keyed[funnel, 1] == keyed[box, 1] and [evaluate(keyed[funnel, c], mid) for c in (0, 2, 7, 8, 9, 11)
                                                       ] == pytest.approx([0.0, 0.0, *[params["funnel"]["size"]] * 3, 1.0])
        if params.get("generator") == "air_blast":   # D451 (Step 2.153b): one bolt from his hands, then a floor dome
            keyed = {(tr.target, tr.comp): tr.keys for tr in made.markers}
            switch, aim = (body.markers.index(params[k]) for k in ("switch", "aim"))
            bolt, blast, impact = params["bolt"], params["blast"], params["impact"]
            start, unit, top = impact + RAMP / 2, blast["dome_unit"], blast["half"][0]
            for t, extents in ((bolt["from"], 1.0), (impact - 0.02, 1.0), (start, blast["grow_from"] / unit),
                               ((start + blast["grow_until"]) / 2, (blast["grow_from"] + top) / 2 / unit),
                               (blast["grow_until"], top / unit), (blast["until"] - 0.01, top / unit),
                               (blast["until"] + 0.02, 1.0)):   # the aim's extents: the dome's rim on the box's edge
                assert [evaluate(keyed[aim, c], t) for c in (7, 8, 9)] == pytest.approx([extents] * 3, rel=1e-4), t
            for t in (start + (blast["until"] - start) * k / 8 for k in range(9)):   # no bolts, no shield, no whirl
                assert evaluate(keyed[switch, 2], t) == 0.0 and [evaluate(keyed[aim, c], t) for c in range(3, 7)] == (
                    pytest.approx([0.0, 0.0, 0.0, 1.0], abs=1e-6)), t
            vtoc, schema = parse_toc(vanilla), schema
            src = next(i for i, n in named_resources(vanilla).items() if n.casefold() == fx_edit.default_key(body_name))
            graph = Graph(vanilla, vtoc, vtoc[src], schema)   # AZ-669: the transform the aim drives scales about its
            bound = next(r for r, ro in enumerate(graph.recs) if ro is not None   # pivot, so its origin, the dome's,
                         and schema.is_a(graph.types[r], "transform")             # stays at his feet as it grows
                         and (bind_name(graph.s, ro) or "").casefold() == params["aim"].casefold())
            for t in (start, blast["grow_until"], blast["until"] - 0.01, blast["until"] + 0.01):
                x = dict(graph.xform_fields(bound), t=tuple(evaluate(keyed[aim, c], t) for c in range(3)),
                         r=(0.0, 0.0, 0.0), s=tuple(evaluate(keyed[aim, c], t) for c in (7, 8, 9)))
                assert [evaluate(keyed[aim, c], t) for c in range(3, 7)] == pytest.approx([0.0, 0.0, 0.0, 1.0], abs=1e-6)
                assert apply(local_matrix(schema, x), (0.0, 0.0, 0.0)) == pytest.approx([0.0] * 3, abs=1e-3), t
            e23 = [Graph(vanilla, vtoc, vtoc[src], schema).attr_named(23, k) for k in ("translateX", "translateY",
                                                                                     "translateZ")]
            assert bolt["emitter"] == pytest.approx(e23, abs=1e-4)   # the recipe's emitter is the graph's [23]
            turned = _turn(_rx(math.radians(bolt["pitch_deg"])), e23)
            hands = [k for k, b in enumerate(rig.bones) if b.name in bolt["hands"]]
            for t in (impact * k / 36 for k in range(36)):   # F1: [23] rides his hands' mean through the bolt phase
                mean = [sum(origins(rig, made, t)[k][c] for k in hands) / len(hands) for c in range(3)]
                assert math.dist([evaluate(keyed[aim, c], t) + turned[c] for c in range(3)], mean) < 0.03, t
        if "hand" in params:   # D378: the hand planted, the feet never sinking
            hand = next(k for k, b in enumerate(rig.bones) if b.name == params["hand"])
            p0, p1 = (made.length * f for f in params["plant"])
            keyed = {k[0] for tr in made.bones if tr.target == root for k in tr.keys}
            assert max(math.dist(origins(rig, made, t)[hand], (0.0, 0.0, params["hand_z"]))
                       for t in keyed if p0 <= t <= p1) < 0.02, clip

            def lowest(t: float) -> float:
                return min(o[2] for k, o in enumerate(origins(rig, made, t)) if k not in hidden)
            assert min(lowest(made.length * k / 140) for k in range(141)) >= lowest((p0 + p1) / 2) - 1e-3, clip
    if overlaid:   # W23: the thrown box travels in her frame (no carry), and passes a target once (no balance)
        carry = [round(_param(x, CARRY_HOOK, "_player_model_carry_columns")) for x in (xbe, base_xbe)]
        assert carry[0] == carry[1] & ~recipe == fill[0] == 0xEFFE3F
        held = [round(_param(x, CARRY_HOOK, "_player_model_held_columns")) for x in (xbe, base_xbe)]
        assert held == [recipe, 0] and recipe == 0x1C0   # D414: held, the gust throws again as each box arrives
        gust = variant.clips["gust"]

        def fraction(col: str, i: int) -> float:   # Move end1 as 0x7E2E0 reads it (Anim start, end: 0, 1 if empty)
            a0, a1, e1 = (c.double_value if (c := anims[0].find_cell(col, row, i)).type_code == 1 else empty
                          for row, empty in (("Anim start", 0.0), ("Anim end", 1.0), ("Move end1", 1.0)))
            return (e1 - a0) / (a1 - a0)
        assert [fraction(col, i) for i, col in enumerate(columns) if recipe >> i & 1] == pytest.approx(
            [gust["arrive"] / gust["length"]] * 3)
        assert ports.XbrDocument.from_bytes(bytes(plain["config.xbr"])).keyed_section("critters_critter_data").find_cell(
            "garret4", "hitsThroughWalls", None).double_value == 0.0   # D415: the overlay's alone
        # D434: spideyzar's bind names at his records, never keyed where they hurt, show or switch his tornado on
        spider = dict(marker_records(vanilla, variant.marker_source))
        assert {m: v for m, v in marker_records(characters, body_name) if m in variant.markers} == {
            m: spider[m] for m in variant.markers} and len(variant.markers) == 14
        quiet = {body.markers.index(m) for m in ("m_lifedrainswitch", "m_projectile_trigger", "m_deathbeam_trigger",
                                                 "m_ice_telltale", "m_whirlwind_trigger")}
        assert not any(tr.target in quiet for clip in body.clips
                       for tr in named_clip(characters, body_name, clip).markers)
        assert _payloads(characters, "characters/balthazar_spider/") == _payloads(vanilla, "characters/balthazar_spider/")
        stand = variant.fx_ring["stand"]   # D501 (Step 2.155b): his graph retuned on the player's clone X38 spawns
        _cloned_only(schema, vanilla, characters, body_name, stand["fx"], keys=(stand["key"], fx_edit.stand_key(body_name)))
        vanilla_anims = ports.XbrDocument.from_bytes(_vanilla_file(usa_iso, CONFIG)).keyed_section(
            "attacks_anims")
        for i, col in enumerate(columns):
            if recipe >> i & 1:
                cell = vanilla_anims.find_cell(col, "Damage multiplier", i)
                assert anims[0].find_cell(col, "Damage multiplier", i).double_value == (
                    cell.double_value if cell is not None and cell.type_code == 1 else 1.0), col
    if "m_damage" in variant.markers:   # grown after B: at rest off, and no baked clip keys it (C5)
        marker, toc = body.markers.index("m_damage"), parse_toc(characters)
        assert dict(marker_records(characters, body_name))["m_damage"][10:12] == (0.0, 0.0)
        assert not any(tr.target == marker for i, key in named_resources(characters).items()
                       if key.casefold().startswith(f"characters/{body_name}/g4/".casefold())
                       for tr in read_clip(characters, toc[i].file_offset).markers)
    assert (logic.reach, logic.damage) == pytest.approx((reach, damage), abs=5e-3)
    assert reasons(name, logic, variant.base) == []
    assert (round(_param(xbe, SEARCH_HOOK, "_player_model_search_reach"), 2)
            if ports.verify_trampoline_patch(xbe, SEARCH_HOOK) == "applied" else None) == search
    assert (bin(round(_param(xbe, CARRY_HOOK, "_player_model_carry_columns"))).count("1")
            if ports.verify_trampoline_patch(xbe, CARRY_HOOK) == "applied" else 0) == carried
    assert (round(_param(xbe, CARRY_HOOK, "_player_model_held_columns"))
            if ports.verify_trampoline_patch(xbe, CARRY_HOOK) == "applied" else 0) == held_mask
    assert ports.verify_trampoline_patch(xbe, JIGGLE_HOOK) == (   # X41: her springs, his locks (chains.json, Step 2.169f)
        "applied" if name in ("booblord", "beamlord") else "original")
    npc = f"characters/{body_name}/".casefold()
    own = (set() if variant.arms else {npc + c.casefold() for c in read_body(vanilla, body_name).clips}) | {
        fx_edit.default_key(body_name)}   # W28 restyles her own clips (no level places her, D361)
    assert {k: v for k, v in _payloads(characters, npc).items() if k in own} == {
        k: v for k, v in _payloads(vanilla, npc).items() if k in own}
    if variant.fx_edits:   # D385, D446: the recipe's edits on the player's clone alone
        _cloned_only(schema, vanilla, characters, body_name, variant.fx, variant.fx_grafts)
    else:
        assert fx_edit.clone_key(body_name) not in _payloads(characters, npc)
    walls = ports.XbrDocument.from_bytes(bytes(built["config.xbr"])).keyed_section("critters_critter_data").find_cell(
        "garret4", "hitsThroughWalls", None)
    assert walls.double_value == (1.0 if variant.through_walls else 0.0)
    # W24: the mesh's written fields alone (positions +0, normals +28 of LOD 0), every other mesh vanilla's;
    # W29 (Step 2.143): a jiggle's weights +12, slot bytes +56 and palette entries too
    groups = [g for g in mesh_groups(characters, body_name) if g.lod == 0]
    cells = [g.vertices + 60 * j for g in groups for j in range(g.count)]
    restored = bytearray(characters)
    fields = ((0, 12), (28, 40)) + (((12, 28), (56, 60)) if variant.jiggle else ())
    for at in cells:
        for a, b in fields:
            restored[at + a:at + b] = vanilla[at + a:at + b]
    for g in groups if variant.jiggle else ():
        restored[g.bones_at:g.bones_at + 4 * len(g.bones)] = vanilla[g.bones_at:g.bones_at + 4 * len(g.bones)]
    toc = parse_toc(vanilla)
    assert all(restored[e.file_offset:e.file_offset + e.size] == vanilla[e.file_offset:e.file_offset + e.size]
               for e in toc if e.tag == "bmsh")
    if reshaped is None:
        assert variant.mesh is None and restored == bytearray(characters)
        return
    moved = [at for at in cells if characters[at:at + 12] != vanilla[at:at + 12]]
    normals = [at for at in cells if characters[at + 28:at + 40] != vanilla[at + 28:at + 40]]
    before, after = (mesh_edit._read_mesh(x, body_name) for x in (vanilla, characters))
    tops = [before.names[b] for b in before.heaviest]
    flesh = [not (n.startswith("loincloth") or n == "vase_joint") for n in tops]

    def band(points, z0, z1, half):
        return [p for p, f in zip(points, flesh) if f and abs(p[0]) <= half and z0 <= p[2] <= z1]
    spine = dict(read_body(vanilla, body_name).bones)["spine_2"][1]
    depth = [max(p[1] for p in band(m.positions, 1.25, 1.47, 0.2)) - spine for m in (before, after)]
    hips = band(after.positions, 0.95, 1.20, 0.3)
    assert ((len(moved), len(normals), depth[1] / depth[0], max(abs(p[0]) for p in hips), min(p[1] for p in hips))
            == pytest.approx(reshaped, abs=2e-3))
    assert not any(characters[at:at + 12] != vanilla[at:at + 12] for at, n in zip(cells, tops)
                   if n.startswith("loincloth_front") or n == "vase_joint")



def _over_packs(image, packs: dict, worn, **fields):
    """``worn`` (a ``Variant``) dressed by ``characters.dressed`` over the layers ``packs`` plan on ``image``
    (``sdk._plan``'s: the swap reads the files they leave), ``fields`` the character's other fields
    (``springs_out``: the spring rows' preview data): the staging."""
    stamp, _, layers, _, _ = sdk._plan({"iso": str(image), "packs": packs})
    springs = fields.pop("springs_out", None)
    vanilla = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    staging, _, _, _ = characters.dressed({"species": worn.name, **fields}, vanilla, layers,
                                          characters.packs_view(stamp.release, mods.PACKS), worn=worn,
                                          springs_out=springs)
    return staging


BAKED_JIGGLE = {
    "bones": [
        {"role": "bust", "bone": "joint32", "parent": "spine_2", "shape": ["bust", "bust low", "bust fill"],
         "groups": [1, 4], "takes": ["spine_1", "spine_2", "spine_3", "spine_endnode"], "weight": 0.9, "freq": 1.6,
         "damping": 0.3, "travel": 0.045, "turn": 0.35, "hang": 0.5, "gain": 2.2, "drive": 6.5},
        {"role": "glutes", "bone": "joint39", "parent": "root_joint", "shape": ["glutes"], "groups": [1],
         "takes": ["root_joint", "left_hip", "right_hip"], "weight": 0.75, "freq": 2.2, "damping": 0.3,
         "travel": 0.03, "turn": 0.3, "hang": 0.5, "gain": 2.2, "drive": 6.5}],
    "keys": 15, "still": ["idle", "listen", "sit", "talk"],
    "loops": ["walk", "climb_idle", "climb_up", "climb_down", "climb_left", "climb_right", "fall", "fall_big", "hover",
              "hang", "slide", "swim_idle", "swim_idle_up", "swim_idle_down", "swim_2", "spin"]}
"""Step 2.143's booblord jiggle, baked (W28): her bones without a real-time
spring, so the bake stays pinned until Step 2.156's sitting retires it."""


def test_a_variants_jiggle_bones_swing_on_real_time_springs_or_baked_keys(usa_iso, monkeypatch, tmp_path, booblord):
    """Step 2.156 (D444, D445; X41): booblord's jiggle bones have real-time
    springs: her build hooks the pose's per-bone CALL (0xCB5CB) with X41,
    whose table is her rows as ``jiggle_rt.table`` packs them (the bust,
    the glutes, her hair chain, D485: hair_2 chained to hair_1, hair_3
    to hair_2, and her sash's two chains, Step 2.169b: the tabard's
    loincloth_front_1-4 and the tails' loincloth_back_1-4, each link
    chained to the one above and walled off the clip's pose along its bind
    -up, 5 mm on the tabard's top two links and the tails' first, 15 mm
    below; the scene global's address read from the image, X26's latch
    words), every clip under her body keying both sash chains'
    first links (their hang: X41 swings each about what the clip keys),
    and no clip under her body but her recipe's own keys either bone and
    no ``r/`` copy is made (her clips are the baked build's with its jiggle
    tracks off); at
    strength 0 the site holds vanilla's CALL and nothing else in her
    characters.xbr differs.
    Step 2.143 (D403, D428; W29, W28), on her bones baked (the same rows
    without springs, :data:`BAKED_JIGGLE`): the jiggle rewrites the
    leaf bones joint32 and joint39 in place under spine_2 and root_joint,
    their rest world against their new inverse bind the identity (at rest
    they skin as their parents do); group 1's palette entries 14 and 17
    (joint19, joint10, merged into the feet they ride) and group 4's 13
    (left_hand, dropped) re-aimed at them, no vertex left on a freed bone,
    every vertex's weights summing to 1 with the heaviest in slot 0; every
    clip the build gives her body keys both bones (three translation
    components, q's y and z) but her still ones (idle, listen, sit, talk),
    which key neither, and only adds those tracks to the same build
    with real-time springs; every keyed offset stays within its bone's travel,
    each clip her ``loops`` names (by its name's last part: her walk, the
    climbs, swims and falls, the spin) has its keys meet at its seam and
    every other clip, a one-shot, starts at rest and ends there (the
    judge's D2: a hit that ends in its start pose is no loop; D1: it eases
    out, k after the limit), and her landing and hit (g4/touchdown,
    g4/ouch_1) throw the bust over a centimetre with no key a travel from
    the one before (D3: the drive capped, so it rings, not bangs between
    the limit's stops).  AZ-648 (the sitting: her walk baked at the run
    slot's 1.217 shook in the walk slot, which plays it at 4.7-6.6, and
    the climbs baked at 1 jerked at 1.5 and 2): each clip is keyed at the
    rate the game plays it, her walk at the walk slot's 0.8 x walkSpeed
    over (1.15 x walkAnimSpeed), the run slots' copy ``r/walk`` (the only
    clip she gains, its other tracks her walk's) at garret4's runSpeed
    over runAnimSpeed, which the walk slider scales (here x 2, as
    randomize-full applies player_physics before the model: 14 m/s, not
    1.4 x walkSpeed; the review's D1), the climb loop at 2, its latch 1.5,
    step_up 3, her hit at its length over 0.4 s, the roll at its column's
    Rate and the hand spin at the geometric middle of sweep1's and
    sweep2's.
    Step 2.168 (D553): a recipe's own clip may key a jiggle bone (her
    ``v/press``, made in Blender, lifts the bust bone 1 cm): with
    real-time springs it
    plays its keys, which X41 swings about; baked, the bone it keys keeps
    its keys unbaked and the bones it leaves are baked as in any clip.
    (Her ``slots`` are left out here, Step 2.171: her walk plays in the
    walk and run slots as before, which AZ-648's copy is about.)"""
    with _building(usa_iso):
        _springs(usa_iso, monkeypatch, tmp_path)


def _springs(usa_iso, monkeypatch, tmp_path) -> None:
    """:func:`test_a_variants_jiggle_bones_swing_on_real_time_springs_or_baked_keys`' builds and checks."""
    from azurkit.tools.characters import jiggle, jiggle_rt, model_chains
    from azurkit.tools.characters._player_character import STANCE_HOOK
    from azurkit.tools.characters.characters import bone_records, inverse_binds
    from azurkit.tools.characters.retarget import Clip, Track, write_clip

    body = "townspeople/female_2"
    booblord = booblord_v3(sash=True)
    recipe = booblord_v3_recipe()
    vanilla = _vanilla_characters(usa_iso)
    dressed = bytearray(vanilla)   # W24 and W29 as the build makes them, for the Blender clip's rig
    mesh_edit.write(dressed, mesh_edit.plan(vanilla, body, booblord.mesh), vanilla)
    jiggle.rig(dressed, vanilla, body, booblord.jiggle, booblord.mesh)
    bust = [b.name for b in bone_records(bytes(dressed), body)].index("joint32")
    idle = named_clip(bytes(dressed), body, "idle")
    lift = Track(bust, 1, tuple((t, Rig.read(bytes(dressed), body).bones[bust].t[1] + d, 0.0, 0.0)
                                for t, d in ((0.0, 0.0), (2.0, 0.01), (idle.length, 0.0))))
    (tmp_path / "booblord").mkdir()
    (tmp_path / "booblord" / "press.glb").write_bytes(
        _clip_only(bytes(dressed), body, [("press", Clip(idle.length, (*idle.bones, lift), ()))]))
    monkeypatch.setattr(_player_variants, "CLIPS", tmp_path)
    springy = dataclasses.replace(booblord, slots={}, clips={**booblord.clips, "press": {   # her walk in both gaits
        "generator": "gltf", "file": "press.glb", "sha256": mesh_edit.file_sha256(tmp_path / "booblord" / "press.glb"),
        "animation": "press"}})
    variant = dataclasses.replace(springy, jiggle=_player_variants._jiggle(
        "test", {"frees": recipe["jiggle"]["frees"]} | BAKED_JIGGLE))
    springs = {}
    built, plain, zero = (_over_packs(usa_iso, {"player_physics": {"walk_speed_scale": 2.0}}, worn, **extra)
                          for worn, extra in ((variant, {}), (springy, {"springs_out": springs}),
                                              (springy, {"jiggle_strength": 0.0})))
    characters = bytes(built["characters.xbr"])
    # X41: the springy build's hook and table; at strength 0, nothing
    xbe = bytes(plain["default.xbe"])
    assert ports.verify_trampoline_patch(xbe, JIGGLE_HOOK) == "applied"
    assert ports.verify_trampoline_patch(bytes(zero["default.xbe"]), JIGGLE_HOOK) == "original"
    assert ports.verify_trampoline_patch(bytes(built["default.xbe"]), JIGGLE_HOOK) == "original"
    assert bytes(zero["characters.xbr"]) == bytes(plain["characters.xbr"])

    def word(symbol: str, size: int) -> bytes:
        at = _at(xbe, JIGGLE_HOOK, symbol)
        return xbe[at:at + size]
    bones_n = len(bone_records(bytes(plain["characters.xbr"]), body))
    assert [(r.role, r.bone, r.parent, r.chain) for r in springs["rows"]] == [
        ("bust", 22, 16, -1), ("glutes", 24, 0, -1), ("hair1", 27, 20, -1), ("hair2", 28, 27, 2), ("hair3", 29, 28, 3),
        *((f"loincloth_{side}_{k}", at + k, at + k - 1 if k > 1 else 0, first + k - 1 if k > 1 else -1)
          for side, at, first in (("front", 81, 4), ("back", 86, 8)) for k in range(1, 5))]
    assert [r.spring.wall[3] for r in springs["rows"][5:]] == [0.005, 0.005, 0.015, 0.015, 0.005, 0.015, 0.015, 0.015]
    assert [r.spring.wall and r.spring.wall[:3] for r in springs["rows"]] == [None] * 5 + [(0.0, 0.0, -1.0)] * 8
    assert jiggle_rt.kinds(springs) == {"bust": "bust", "glutes": "glutes", "hair1": "", "hair2": "", "hair3": ""} | {
        f"loincloth_{side}_{k}": "hem" if k == 4 else "cloth" for side in ("front", "back") for k in range(1, 5)}
    sash = {c["root"]: c for c in model_chains.chains(bytes(plain["characters.xbr"]), "townspeople/female_2")["chains"]}
    assert [(sash[f"loincloth_{side}_1"]["keyed"], sash[f"loincloth_{side}_1"]["unkeyed"]) for side in ("front", "back")
            ] == [(59, [])] * 2   # her v3 stand-in's 58 clips and the test's press (idle's keys and the lift)
    assert word("_player_model_jiggle_bones", jiggle_rt.TABLE_SIZE) == jiggle_rt.table(
        springs["rows"], bones_n, 1.0, springs["drawn"])
    assert word("_player_model_jiggle_scene", 4) == struct.pack("<I", 0x1BF63C)
    assert word("_player_model_jiggle_x26", 8) == struct.pack("<II", *(
        ports.trampoline_symbol_va(xbe, STANCE_HOOK, f"_player_model_stance_{w}") for w in ("held", "edge")))
    assert struct.unpack("<f", word("_player_model_jiggle_strength", 4)) == (1.0,)
    rig, records = Rig.read(characters, body), bone_records(characters, body)
    names = [b.name for b in records]
    bones = {jb.role: (names.index(jb.bone), jb) for jb in variant.jiggle.bones}
    assert {r: rig.bones[k].parent for r, (k, _) in bones.items()} == {
        "bust": names.index("spine_2"), "glutes": names.index("root_joint")}
    binds = inverse_binds(characters, body)
    home = []
    for b in rig.bones:
        home.append(tuple(b.t) if b.parent < 0 else
                    tuple(p + d for p, d in zip(home[b.parent], _turn(rig.world[b.parent], b.t))))
    for k, _ in bones.values():   # rest world x inverse bind = I: rotation and origin
        m = binds[k]
        assert max(abs(m[4 * i + j] - _turn(qmul((-rig.world[k][0], -rig.world[k][1], -rig.world[k][2],
                                                       rig.world[k][3]), (0.0, 0.0, 0.0, 1.0)), axis)[j])
                   for i, axis in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))) for j in range(3)) < 1e-5
        assert max(abs(sum(home[k][i] * m[4 * i + j] for i in range(3)) + m[12 + j]) for j in range(3)) < 1e-5
    groups = {g.index: g for g in mesh_groups(characters, body) if g.lod == 0}
    assert ([groups[1].bones[e] for e in (14, 17)], groups[4].bones[13]) == (
        [bones["bust"][0], bones["glutes"][0]], bones["bust"][0])
    gone = {1: {names.index("joint19"), names.index("joint10")}, 4: {names.index("left_hand")}}
    for g in groups.values():
        for j in range(g.count):
            at = g.vertices + 60 * j
            w = struct.unpack_from("<4f", characters, at + 12)
            used = [g.bones[b - 1 if b <= 12 else b - 2] for b, x in zip(characters[at + 56:at + 60], w) if x > 0]
            assert abs(sum(w) - 1.0) < 1e-6 and w[0] == max(w) and not set(used) & gone.get(g.index, set())
    mine, theirs = (_clips(bytes(x["characters.xbr"]), body) for x in (built, plain))
    still = {f"characters/{body}/{c}" for c in variant.jiggle.still}
    cycled = set(variant.jiggle.loops)
    run = f"characters/{body}/r/walk"
    assert set(mine) == set(theirs) | {run} and len(mine) == 60 and len(still) == 4
    jig = {k for k, _ in bones.values()}   # Step 2.168: a recipe's own clip plays its keys on a jiggle bone
    own = {key for key, (_, clip) in theirs.items() if any(tr.target in jig for tr in clip.bones)}
    assert {key.rsplit("/", 1)[-1] for key in own} == {"press"}
    for key in own:
        (_, made), (_, sprung) = mine.pop(key), theirs[key]
        keyed = {tr.target for tr in sprung.bones if tr.target in jig}
        assert [tr for tr in made.bones if tr.target in keyed] == [tr for tr in sprung.bones if tr.target in keyed]
        for k in jig - keyed:
            assert {tr.comp for tr in made.bones if tr.target == k} == {0, 1, 2, 4, 5}, key
    lifted = {tr.comp: tr.keys for tr in theirs[f"characters/{body}/v/press"][1].bones if tr.target == bones["bust"][0]}
    assert evaluate(lifted[1], 2.0) == pytest.approx(rig.bones[bones["bust"][0]].t[1] + 0.01, abs=1e-3)
    assert b"r/walk\0" in bytes(built["default.xbe"]) and b"r/walk\0" not in bytes(plain["default.xbe"])   # X11's
    for key, (data, clip) in mine.items():
        added = [tr for tr in clip.bones if tr.target in {k for k, _ in bones.values()}]
        source = theirs[f"characters/{body}/walk" if key == run else key][1]
        assert [tr for tr in clip.bones if tr not in added] == list(source.bones), key
        if key in still:
            assert data == theirs[key][0], key
            continue
        assert sorted((tr.target, tr.comp) for tr in added) == sorted(
            (k, c) for k, _ in bones.values() for c in (0, 1, 2, 4, 5)), key
        for k, jb in bones.values():
            keyed = {tr.comp: tr.keys for tr in added if tr.target == k}
            off = [math.dist([evaluate(keyed[c], clip.length * i / 60) for c in range(3)], rig.bones[k].t)
                   for i in range(61)]
            assert max(off) <= jb.travel * 1.1, (key, jb.role)
            if key.rsplit("/", 1)[-1] in cycled:
                assert all(keys[0][1] == keys[-1][1] for keys in keyed.values()), key
            else:
                assert off[0] < 1e-3 and off[-1] < 1e-3, (key, jb.role)
            if key.endswith(("/g4/touchdown", "/g4/ouch_1")):
                at = [[k[1] for k in keyed[c]] for c in range(3)]
                assert jb.role != "bust" or max(off) > 0.01
                assert max(math.dist([a[j] for a in at], [a[j + 1] for a in at])
                           for j in range(len(at[0]) - 1)) < jb.travel, (key, jb.role)
    # AZ-648: each clip's springs are the ones its slot's rate keys, on W29's rig as the dress makes it
    edited = bytearray(vanilla)
    mesh_edit.write(edited, mesh_edit.plan(vanilla, body, variant.mesh), vanilla)
    rigged = jiggle.rig(edited, vanilla, body, variant.jiggle, variant.mesh)
    config = ports.XbrDocument.from_bytes(bytes(built["config.xbr"]))
    data, anims = config.keyed_section("critters_critter_data"), config.keyed_section("attacks_anims")
    cell = {p: data.find_cell("garret4", p, None).double_value
            for p in ("walkSpeed", "runSpeed", "walkAnimSpeed", "runAnimSpeed")}
    drawn = config.keyed_section("critters_engine").find_cell("garret4", "scale", None).double_value
    rate = {c: anims.find_cell(c, "Rate", i).double_value for i, c in enumerate(anims.col_names())}
    assert (cell["walkSpeed"], cell["runSpeed"], round(drawn, 6)) == (5.0, 14.0, 1.15)
    for name, at in (("walk", 0.8 * 5.0 / (drawn * cell["walkAnimSpeed"])),
                     ("r/walk", cell["runSpeed"] / (drawn * cell["runAnimSpeed"])), ("g4/climb_up", 2.0),
                     ("g4/climb_start", 1.5), ("g4/step_up", 3.0),
                     ("g4/ouch_1", mine[f"characters/{body}/g4/ouch_1"][1].length / 0.4),
                     ("g4/roll_forward", rate["roll forward"]),
                     ("v/hspin", math.sqrt(rate["sweep1"] * rate["sweep2"]))):
        data, clip = mine[f"characters/{body}/{name}"]
        rest = Clip(clip.length, tuple(tr for tr in clip.bones if tr.target not in {k for k, _ in bones.values()}),
                    clip.markers)
        again, _ = jiggle.keyed(rig, rest, rigged.bones, variant.jiggle.keys, at, drawn,
                                name.rsplit("/", 1)[-1] in cycled)
        assert write_clip(again) == data, (name, at)
    assert rate["sweep1"] != rate["sweep2"]


"""The weaponless townsfolk's throw (Step 2.159b; D473, D474) and an
effects template's projectile (Step 2.167b, D538's E2): W30, the
projectile as data, and X42's table.

D473 (the owner: "Vase + rock (Recommended)"): townswomen throw the vase
they carry (it reappears in the hand after), townsmen and children a rock;
a real travelling projectile that hits enemies, as a second WHITE set
(D325).  D474: the randomizer's logic stays on the melee reach.

- **W30** (characters.xbr, index.xbr and config.xbr, a kit build with a
  throw): the spare species ``debug`` (placed in no level) becomes the
  projectile.  Its rows in :data:`SECTIONS` take the boulder's (numbers as
  numbers, strings pointed at the boulder's, its empty cells emptied: no
  drops), its ``body`` the string ``debug`` (its own name cell: no pool
  growth) and its ``scale`` the kind's (:func:`projectile_scale`).
  ``characters/debug`` is a copy of the earth guardian's boulder (a rock),
  or of female_0_base cut to its LOD0 vase on ``vase_joint``
  (:func:`~azurik_mod.assets.body_codec.subset`, its LOD1 vase rides
  ``root_joint``) with the boulder's ``m_alpha`` marker added (a vase);
  ``idle``, ``run`` and ``die`` are the boulder's.  Its default fx is a
  clone of the boulder's whose ``breakEffectShape`` loads
  ``characters/debug/fx/fx_break``, a clone of the boulder's break with
  its damage field's damage 0 by value and by its timer's link, so the
  shards hurt no one; a vase's shards and dust take the vase's own colour
  and the rock's size.  The die clip keys m_alpha, whose link loads the
  break where the projectile dies, as the guardian's boulders break.
  The boulder, its fx and every NPC graph stay vanilla.
- **X42's table** (:meth:`Plan.table`, ``player_model/throw.c``'s ``Table``):
  the throwing columns, each one's spawn and release fractions and
  multiplier (:class:`Shot`), the hand bone, the aim, the flight (its
  speed and its ``arc``: the share of gravity it falls with, the kit's
  1.0) and the hit, :class:`Plan` per build.  A throw flies straight
  along the thrower's facing to the aim's ``miss`` point, ``miss_z``
  over his point (D761, Step 2.194b: no current ranged attack seeks;
  the kit's about the floor, so a throw dead ahead comes down through a
  critter's height); only a plan with ``seek`` (an
  ``effects`` row's opt-in) aims at the critter the target finder gives
  within the aim's range and cone.
- **A template's projectile** (Step 2.167b, D538: "create new effects ...
  without replacing assets", projectiles first; a recipe's or a weapon
  style's ``effects`` row, :func:`~azurik_mod.assets.fx_templates.effects`):
  :func:`template_plan` throws it from each column the row names, at the
  column clip's first damage tick (else :data:`RELEASE_SHARE` of it),
  held from :data:`SPAWN_LEAD` ticks before, at the row's speed, arc,
  life and radius, the kit's aim (``kit.json``'s range, miss, miss_z, cone, pad
  and landing; the row's ``seek``, off unless given); :func:`write_template` makes ``debug`` (W30's species)
  wear the template's body at its ``size`` (a copy of the game's body:
  the boulder's recoloured in the row's colour, another its own texture,
  its mesh baked into its template's ``pose`` (:func:`posed`) and held
  still; or our own :func:`arrow` on the boulder's bone), its
  default fx a clone of the boulder's with the template's sets grafted
  at its origin (their shows, colour and params written), its break the
  template's impact graph copied (refused if it deals damage: X42's hit
  is the projectile's only one) or none.  Every graph it plays is a copy
  (the clone invariant): the game's bodies, clips and graphs stay
  vanilla.
- **A carrier's vase** (:func:`take_tick`, :func:`throw_carry`): in the
  throw clip her head's vase rides her head until the tick her hand
  passes nearest it (X42 spawns the thrown vase in the hand then),
  is hidden until the clip's ``back`` tick, where it shows at the palm,
  and is carried back to her head by the clip's end (each step half a
  tick early, :data:`HALF`).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

import numpy as np

from azurkit.core import fdlibm
from azurkit.tools.characters import body_codec, fx_edit, textures
from azurkit.tools.characters.characters import Body, height, marker_records
from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records
from azurkit.tools.characters.retarget import Clip, Rig, Track, grow_markers, origins, read_clip, write_clip
from azurkit.tools.characters._player_kit import Throw
from azurkit.tools.characters import render
from azurkit.core.xbr.append import append_resources
from azurkit.core.xbr.clone import Batch, Copier
from azurkit.tools.characters.ports import clear_keyed_cell, point_at_string, point_keyed_string, set_keyed_double
from azurkit.core.xbr.nodes import named_resources, parse_toc

SPECIES = "debug"
"""The species W30 makes the projectile: unplaced in every level (38 scanned), so no NPC wears it."""
SOURCE = "boulder"
"""The species whose rows it takes: the earth guardian's thrown boulder."""
BOULDER = "bosses/boulder"
BODY = f"characters/{SPECIES}"
FX_DEFAULT = f"{BODY}/fx/fx_default"
FX_BREAK = f"{BODY}/fx/fx_break"
SECTIONS = ("critters_engine", "critters_critter_data", "critters_damage", "critters_walking")
CLIPS = ("idle", "run", "die")
BREAK_EFFECT = (3, "breakEffectShape", "effect")
"""fx_default's record that loads the break (its m_alpha link)."""
FIELD = (19, "damageFieldShape", "platform")
"""fx_boulder_break's damage field: the shards' rock_shard box."""
TIMER = (1, "timer1", "timer")
"""Its timer, whose link writes the field's damage."""
SHARDS = tuple((2 * k + 2, f"shard{k + 1}", "transform") for k in range(7))
SHARD_SHAPES = tuple((2 * k + 3, f"shardShape{k + 1}", "platform") for k in range(7))
DUST = (20, "pRendererB1", "pRendererB")
HAND = "right_hand"
HALF = 0.5
"""The throw's steps fall half a tick before their tick (X42's spawn and
release fractions, a carried vase's hide and return), so the game's tick
nearest each takes it on both sides alike, whatever its float rounding."""
HIDDEN = 1e-12
"""A hidden prop's scale: the game's own (town_female_1's vase in her clips), so no bone matrix is singular."""
TABLE_SIZE = 0x184
"""``player_model/throw.c``'s ``Table``."""
HAND_LOW = -1e9
"""The kit's ``low``: its rock or vase held and thrown from the hand wherever it is."""
TEMPLATE_LOW = 0.0
"""A template's ``low`` (m over the player's point, about 1 m up): no
lower is it held or thrown (AZ-705, Step 2.167c's sitting: the catalisk's
paw held its arrow 0.17-0.45 m over the sand, and flying straight at its
target's centre, 0.2-0.6 m up, every arrow ended on state 23's contact,
on the sand or a sleeth in the line) [D115: his point, the chest the
design names]."""
COLUMNS = 24
"""The columns its per-column rows hold (``attacks_anims`` has 23)."""
PLAYER = "garret4"
TICK = 30.0
SPAWN_LEAD = 6
"""Ticks a template's projectile sits in the hand before its release
[D115: 0.2 s, about the kit's 8 at a quicker swing]."""
RELEASE_SHARE = 0.4
"""Where in a clip with no damage window a template's projectile leaves
the hand [D115]."""
STILL = 1.0
"""The length (s) of a projectile's idle and run that hold its pose (an arrow's, an ice shard's)."""
ARROW_LENGTH = 1.0
"""The authored arrow's length in model units (:func:`arrow`): its ``size`` is its length."""


@dataclass(frozen=True)
class Shot:
    """One throwing column: its ``attacks_anims`` index, its clip's ticks
    at 30 Hz, the ticks it spawns at and leaves the hand at, and its
    written ``Damage multiplier``."""

    column: int
    ticks: int
    spawn: int
    release: int
    mult: float


@dataclass(frozen=True)
class Plan:
    """A build's throw: its columns (:class:`Shot`), the projectile's
    scale and radius (m), the push-out from the thrower's axis (m), the
    hand bone (-1: ahead of the chest), its horizontal speed (m/s), arc,
    the aim's range, miss and cone (m, m, degrees), the flight time's
    clamp, the hit box's pad (m), its life (s), message 10's clip slot and
    landing state, what it throws: the kit's :class:`Throw` or a
    template's :class:`~azurik_mod.assets.fx_templates.Effect`, the
    lowest it is held at over the player's point (m), whether it seeks
    (D761: aimed at the critter the target finder gives within the range
    and cone; off, straight along the facing to the miss point) and the
    miss point's height over the player's point (m; the kit's
    ``miss_z``, about the floor)."""

    shots: tuple[Shot, ...]
    scale: float
    radius: float
    pushout: float
    bone: int
    speed: float
    arc: float
    range: float
    miss: float
    cone: float
    flight: tuple[float, float]
    pad: float
    life: float
    anim: int
    landing: int
    throw: Throw | None = None
    effect: object = None
    low: float = HAND_LOW
    seek: bool = False
    miss_z: float = 0.0

    @property
    def column(self) -> int:
        """The first throwing column (the kit's one)."""
        return self.shots[0].column

    @property
    def spawn(self) -> int:
        return self.shots[0].spawn

    @property
    def mult(self) -> float:
        return self.shots[0].mult

    def table(self) -> bytes:
        """X42's table (``player_model/throw.c``'s ``Table``): each shot's
        fractions half a tick early (:data:`HALF`)."""
        spawn, release, mult = [0.0] * COLUMNS, [0.0] * COLUMNS, [0.0] * COLUMNS
        for s in self.shots:
            spawn[s.column], release[s.column] = (s.spawn - HALF) / s.ticks, (s.release - HALF) / s.ticks
            mult[s.column] = s.mult
        name = SPECIES.encode("ascii")
        out = struct.pack("<ii3f10fiif16s", sum(1 << s.column for s in self.shots), self.bone, 0.0, 0.0, 0.0,
                          self.speed, self.arc, self.range, self.miss, fdlibm.cos(math.radians(self.cone)),
                          *self.flight, self.pad, self.life, self.pushout, self.anim, self.landing, self.radius,
                          name + bytes(16 - len(name)))
        out += struct.pack(f"<{3 * COLUMNS}f", *spawn, *release, *mult) + struct.pack("<fif", self.low, self.seek, self.miss_z)
        assert len(out) == TABLE_SIZE
        return out


def _cell(doc, section: str, entity: str, prop: str) -> float | None:
    c = doc.keyed_section(section).find_cell(entity, prop)
    return c.double_value if c is not None and c.type_code == 1 else None


def projectile_scale(throw: Throw, characters_xbr: bytes, body: Body, drawn: float, config) -> float:
    """The projectile's drawn scale on ``body`` drawn ``drawn`` times:
    a rock's the kind's scale at the ``reference`` townsman's drawn height
    (town_male_6's config scale x its mesh's height), times the wearer's
    drawn height over it (a child's smaller); a vase the kind's scale x
    the wearer's drawn scale (her head's vase, x0.4 on her bone)."""
    p = throw.projectile
    if "reference" not in p:
        return p["scale"] * drawn
    engine = config.keyed_section("critters_engine")
    ref = engine.find_cell(p["reference"], "body").string_value
    from azurkit.tools.characters.characters import read_body
    ref_height = _cell(config, "critters_engine", p["reference"], "scale") * height(
        characters_xbr, read_body(characters_xbr, ref))
    return p["scale"] * drawn * height(characters_xbr, body) / ref_height


def plan(throw: Throw, characters_xbr: bytes, body: Body, columns: list[str], picks: list[str], dirs: str,
         drawn: float, vanilla_config, written_config, take: int | None, hand: str = HAND) -> Plan:
    """The build's :class:`Plan`: the column playing the throw clip
    (``dirs`` + its clip), the projectile's scale, its radius (the
    boulder's collisionRadius x the scale), the push-out (the player's
    collisionRadius x ``drawn`` + that radius + the throw's ``clear``),
    the ``hand`` bone's index (a body of no townsfolk family wearing bare
    hands throws from its bone playing garret4's right hand, Step 2.161b),
    the spawn tick (``take`` for a carrier) and the throw column's written
    ``Damage multiplier``.  :class:`ValueError` when no column plays the
    clip, two do, or the body has no such hand."""
    played = [i for i, p in enumerate(picks) if p == dirs + throw.clip]
    if len(played) != 1:
        raise ValueError(f"the throw: {len(played)} attacks_anims columns play {dirs + throw.clip}, not 1")
    bones = [b.name for b in Rig.read(characters_xbr, body.name).bones]
    if hand not in bones:
        raise ValueError(f"the throw: {body.name} has no {hand} bone to throw from")
    scale = projectile_scale(throw, characters_xbr, body, drawn, vanilla_config)
    radius = _cell(vanilla_config, "critters_engine", SOURCE, "collisionRadius") * scale
    own = _cell(written_config, "critters_engine", PLAYER, "collisionRadius") * drawn
    anims = written_config.keyed_section("attacks_anims")
    mult = anims.find_cell(columns[played[0]], "Damage multiplier", played[0]).double_value
    p = throw.projectile
    shot = Shot(played[0], throw.ticks, throw.spawn if take is None else take, throw.release, mult)
    return Plan((shot,), scale, radius, own + radius + throw.clear, bones.index(hand), p["speed"], 1.0, throw.range,
                throw.miss, throw.cone, throw.flight, throw.pad, throw.life, p["anim"], throw.landing, throw=throw,
                miss_z=throw.miss_z)


def source_body(template) -> str:
    """The body a template's projectile copies (``characters/<it>``): its
    ``body.key``'s, or the boulder's for one we author (its one bone)."""
    if "authored" in template.body:
        return BOULDER
    key = template.body["key"]
    if not key.startswith("characters/"):
        raise ValueError(f"{template.name}'s body {key!r} is no characters/ key")
    return key[len("characters/"):]


def template_scale(characters_xbr: bytes, template, size: float) -> float:
    """``debug``'s scale wearing ``template``'s body ``size`` m across: its
    mesh's longest span (model units; an authored arrow's length) drawn
    ``size`` long.  A size whose scale is 0 draws nothing, and its
    contact sphere (radius / scale) is no number: refused by name (D35)."""
    from azurkit.tools.characters.characters import mesh_bounds
    if "authored" in template.body:
        scale = size / ARROW_LENGTH
    else:
        if "pose" in template.body:   # the mesh as drawn: in its pose
            points = [v.position for g in posed(characters_xbr, template).lods[0].groups for v in g.vertices]
            bounds = (tuple(map(min, zip(*points))), tuple(map(max, zip(*points)))) if points else None
        else:
            bounds = mesh_bounds(characters_xbr, source_body(template))
        if bounds is None:
            raise ValueError(f"{template.name}: {source_body(template)} has no mesh to size")
        scale = size / max(h - lo for lo, h in zip(*bounds))
    if scale == 0:
        raise ValueError(f"its {template.name} row: size {size:g} draws nothing (debug's scale would be 0)")
    return scale


def posed(characters_xbr: bytes, template, asset: body_codec.BodyAsset | None = None) -> body_codec.BodyAsset:
    """``template``'s body (``asset``, a copy of it, else its own) with
    each LOD's vertices skinned into the first frame of its ``pose`` clip
    as the game draws them (each bone's world in that frame times its
    inverse bind, by the vertex's weights; the normals turned alike), so
    drawn in its bind pose (its still clips: a thrown critter plays its
    clip, Step 2.167c's sitting) it shows that pose.  AZ-704: the ice
    shard's own ``ball`` keys no bone (its 22 bones at rest: the T-pose
    it flew in), the rock shard's, on the same bones, curls it.
    :class:`ValueError` names a pose that is no clip, or one whose body's
    bones aren't the body's (D35)."""
    from dataclasses import replace

    from azurkit.tools.characters import gltf
    from azurkit.tools.characters.characters import bone_records, inverse_binds
    source, key = source_body(template), template.body["pose"]
    owner = key[len("characters/"):].rpartition("/")[0] if key.casefold().startswith("characters/") else ""
    at = _named(characters_xbr).get(key.casefold())
    toc = parse_toc(characters_xbr)
    if not owner or at is None or toc[at].tag != "banm":
        raise ValueError(f"{template.name}'s pose {key!r} is no characters/<body>/<clip> clip in characters.xbr")
    bones = bone_records(characters_xbr, source)
    if [b.name for b in bone_records(characters_xbr, owner)] != [b.name for b in bones]:
        raise ValueError(f"{template.name}'s pose {key!r}: {owner}'s bones aren't {source}'s")
    rig = gltf._Body(source, 0, tuple(bones), inverse_binds(characters_xbr, source), (), ())
    skin = np.array(gltf._engine(rig, read_clip(characters_xbr, toc[at].file_offset), 0.0)) @ np.array(
        [np.array(m, float).reshape(4, 4).T for m in rig.binds])
    asset = asset or body_codec.read_asset(characters_xbr, source)
    for lod in asset.lods:
        for group in lod.groups:
            out = []
            for k, v in enumerate(group.vertices):
                m = sum(w * skin[b] for b, w in group.skin(k).items())
                p = m @ np.array([*v.position, 1.0])
                n = m[:3, :3] @ np.array(v.normal)
                n = n / (np.linalg.norm(n) or 1.0)
                out.append(replace(v, position=tuple(float(x) for x in np.float32(p[:3])),
                                   normal=tuple(float(x) for x in np.float32(n))))
            group.vertices = out
    return asset


def template_plan(effect, characters_xbr: bytes, columns: list[str], timing: dict[int, tuple[int, int | None]],
                  written_config, drawn: float, bone: int) -> Plan:
    """The :class:`Plan` of an ``effects`` row's projectile (module
    docstring): each of its columns (``timing``: column index -> its
    clip's ticks and first damage tick, ``None`` for none) released at
    that tick (else :data:`RELEASE_SHARE` of the clip) and spawned
    :data:`SPAWN_LEAD` ticks before, at its written ``Damage multiplier``;
    the row's speed, arc and life, its radius the hit's, the push-out the
    player's collisionRadius x ``drawn`` + that radius + the kit's clear,
    from ``bone``; the kit's aim, seeking with the row's ``seek``;
    message 10's clip the body's run (none for one we author).  :class:`ValueError` names a column
    ``attacks_anims`` lacks."""
    from azurkit.tools.characters._player_kit import kit_document
    t, v = effect.template, effect.values
    shots = []
    anims = written_config.keyed_section("attacks_anims")
    for name in effect.columns:
        if name not in columns:
            raise ValueError(f"its {t.name} row: columns: {name!r} is no attacks_anims column")
        i = columns.index(name)
        ticks, hit = timing[i]
        release = min(max(round(RELEASE_SHARE * ticks) if hit is None else hit, 1), ticks)
        cell = anims.find_cell(name, "Damage multiplier", i)
        mult = cell.double_value if cell is not None and cell.type_code == 1 else 1.0
        shots.append(Shot(i, ticks, max(1, release - SPAWN_LEAD), release, mult))
    kit = kit_document()["throw"]
    own = _cell(written_config, "critters_engine", PLAYER, "collisionRadius") * drawn
    radius = float(v["radius"])
    return Plan(tuple(sorted(shots, key=lambda s: s.column)), template_scale(characters_xbr, t, float(v["size"])),
                radius, own + radius + kit["clear"], bone, float(v["speed"]), float(v["arc"]), kit["range"],
                kit["miss"], kit["cone"], (1.0 / TICK, float(v["life"])), kit["pad"], float(v["life"]),
                -1 if "authored" in t.body else 9, kit["landing"], effect=effect, low=TEMPLATE_LOW, seek=effect.seek,
                miss_z=kit["miss_z"])


def write_species(doc, scale: float, contact: float | None = None) -> list[str]:
    """W30's config rows (module docstring) in ``doc``: the rows of
    :data:`SPECIES` it changed; with ``contact`` (a template's
    projectile, m: the smaller of its hit radius and half its size) its
    ``collisionRadius`` so the engine's contact sphere is that at its
    ``scale``."""
    done = []
    for name in SECTIONS:
        k = doc.keyed_section(name)
        for prop in k.row_names():
            if prop in ("name", ""):
                continue
            src, dst = k.find_cell(SOURCE, prop), k.find_cell(SPECIES, prop)
            if src is None or dst is None:
                continue
            if name == "critters_engine" and prop == "body":
                point_at_string(k, SPECIES, "body", SPECIES, fill_empty=True)
            elif name == "critters_engine" and prop == "scale":
                set_keyed_double(k, SPECIES, "scale", scale, fill_empty=True)
            elif name == "critters_engine" and prop == "collisionRadius" and contact is not None:
                set_keyed_double(k, SPECIES, prop, contact / scale, fill_empty=True)
            elif src.type_code == 1:
                if dst.type_code == 1 and dst.double_value == src.double_value:
                    continue
                set_keyed_double(k, SPECIES, prop, src.double_value, fill_empty=True)
            elif src.type_code == 2:
                if dst.type_code == 2 and dst.string_value == src.string_value:
                    continue
                point_keyed_string(k, SPECIES, prop, SOURCE, prop, fill_empty=True)
            elif src.type_code == 0 and dst.type_code != 0:
                clear_keyed_cell(k, SPECIES, prop)
            else:
                continue
            done.append(f"{name}/{prop}")
    return done


def _vase_ramp(characters_xbr: bytes, group: body_codec.Group) -> list[list[float]]:
    """A recolour ramp in the vase's own colour: its texture's mean, from
    black through half of it to halfway to white."""
    toc = parse_toc(characters_xbr)
    tex = render.material(characters_xbr, toc, *group.material)["textures"][0]
    e = toc[tex]
    rgb = textures.levels(bytes(characters_xbr[e.file_offset:e.file_offset + e.size]))[0][..., :3]
    mean = [float(x) / 255.0 for x in np.asarray(rgb, dtype=np.float64).reshape(-1, 3).mean(0)]
    return [[0.0, 0.0, 0.0], [m / 2 for m in mean], mean, [(1.0 + m) / 2 for m in mean]]


def _named(data: bytes) -> dict[str, int]:
    return {n.casefold(): i for i, n in named_resources(data).items()}


def write_projectile(characters_xbr: bytes, index_xbr: bytes, xbe: bytes, throw: Throw) -> tuple[bytes, bytes, dict]:
    """W30's characters.xbr and index.xbr (module docstring) for
    ``throw``'s kind; with what it added (``named``, the break's link
    index, a vase's group and ramp).  :class:`ValueError` names a record
    or group the files lack (D35)."""
    p = throw.projectile
    idx = _named(characters_xbr)
    if BODY in idx:
        raise ValueError(f"the throw: characters.xbr already holds {BODY}; build from vanilla")
    toc = parse_toc(characters_xbr)
    batch = Batch(characters_xbr)
    copier = Copier(characters_xbr, batch, same=True, label="characters.xbr")
    source = f"characters/{p['source']}".casefold()
    batch[copier.copy(idx[source])].name = BODY
    for clip in CLIPS:
        batch[copier.copy(idx[f"characters/{BOULDER}/{clip}"])].name = f"{BODY}/{clip}"
    new = batch.resources()
    default = fx_edit.Clone(characters_xbr, f"characters/{BOULDER}/fx/fx_default", xbe, base=len(toc) + len(new))
    r, name, kind = BREAK_EFFECT
    default.apply([{"record": r, "name": name, "type": kind, "graph": FX_BREAK}])
    new += default.build(FX_DEFAULT)
    brk = fx_edit.Clone(characters_xbr, f"characters/{BOULDER}/fx/fx_boulder_break", xbe, base=len(toc) + len(new))
    plug = brk.attrs_of(FIELD[0]).index("damage")
    links = [j for j, lk in enumerate(brk.source.links(TIMER[0])) if lk.dst == FIELD[0] and lk.dst_plug == plug]
    if len(links) != 1:
        raise ValueError(f"the throw: fx_boulder_break's timer drives the field's damage through {len(links)} links")
    edits = [{"record": FIELD[0], "name": FIELD[1], "type": FIELD[2], "set": {"damage": 0.0}},
             {"record": TIMER[0], "name": TIMER[1], "type": TIMER[2], "links": [{"index": links[0], "factor": 0.0}]}]
    info: dict = {"kind": throw.kind, "source": p["source"], "break_link": links[0]}
    group = None
    if "bone" in p:   # a vase: one group on one bone, its shards in its colour at the rock's size
        asset = body_codec.read_asset(characters_xbr, p["source"])
        vb = asset.bone(p["bone"])
        on = [g for g, grp in enumerate(asset.lods[0].groups) if grp.palette == [vb]]
        if len(on) != 1:
            raise ValueError(f"the throw: {p['source']}'s LOD0 has {len(on)} groups on {p['bone']} alone, not 1")
        group = on[0]
        ramp = _vase_ramp(characters_xbr, asset.lods[0].groups[group])
        recolor = {"recolor": {"ramp": ramp}}
        r, name, kind = SHARD_SHAPES[0]
        edits.append({"record": r, "name": name, "type": kind, "texture": {**recolor, "shared": True}})
        r, name, kind = DUST
        edits.append({"record": r, "name": name, "type": kind, "texture": recolor})
        k = p["shards"]
        edits += [{"record": r, "name": name, "type": kind, "set": {"scaleX": k, "scaleY": k, "scaleZ": k}}
                  for r, name, kind in SHARDS]
        info |= {"group": group, "ramp": ramp}
    brk.apply(edits)
    new += brk.build(FX_BREAK)
    grown = append_resources(characters_xbr, new)
    if group is not None:
        cut = body_codec.subset(body_codec.read_asset(grown, SPECIES), {0: [group]})
        grown = body_codec.write_asset(grown, cut)
        at = _named(grown)[BODY]
        e = parse_toc(grown)[at]
        alpha = dict(marker_records(characters_xbr, BOULDER))["m_alpha"]
        grown = append_resources(grown, rewrite={at: grow_markers(bytes(grown[e.file_offset:e.file_offset + e.size]),
                                                                  [("m_alpha", alpha)])})
    named = [x.name for x in new if x.name]
    info["named"] = named
    index = add_index_records(index_xbr, [IndexRecord(x.name, "characters.xbr", x.tag) for x in new if x.name])
    return grown, index, info


def colour_ramp(colour) -> list[list[float]]:
    """A recolour ramp in ``colour``: from black through half of it and
    it to halfway to white (the vase's shards' shape, :func:`_vase_ramp`)."""
    c = [float(x) for x in colour]
    return [[0.0, 0.0, 0.0], [x / 2 for x in c], c, [(1.0 + x) / 2 for x in c]]


def arrow(centre, palette: list[int], material: tuple[int, int], like: body_codec.Group) -> body_codec.Group:
    """Our own arrow (Step 2.167b; D538's template ``arrow``: no game
    data): :data:`ARROW_LENGTH` along +y (the body's forward) about
    ``centre``, a square shaft, a four-sided head and two crossed vanes
    at its tail, every face drawn from both sides (its own vertices, the
    face's normal), its UVs a strip of the texture, skinned whole to bone
    0; ``like``'s FVF and D3D fields, ``material``'s row."""
    cx, cy, cz = centre
    half = ARROW_LENGTH / 2
    tail, neck, tip = cy - half, cy + half - 0.12, cy + half
    shaft, head, vane = 0.012, 0.035, 0.05
    faces: list[tuple[tuple[float, float, float], ...]] = []

    def quad(a, b, c, d):
        faces.extend([(a, b, c), (a, c, d)])
    ring = [(shaft, shaft), (-shaft, shaft), (-shaft, -shaft), (shaft, -shaft)]
    for k in range(4):   # the shaft's four sides
        (x0, z0), (x1, z1) = ring[k], ring[(k + 1) % 4]
        quad((cx + x0, tail, cz + z0), (cx + x1, tail, cz + z1), (cx + x1, neck, cz + z1), (cx + x0, neck, cz + z0))
    base = [(head, head), (-head, head), (-head, -head), (head, -head)]
    for k in range(4):   # the head
        (x0, z0), (x1, z1) = base[k], base[(k + 1) % 4]
        faces.append(((cx + x0, neck, cz + z0), (cx + x1, neck, cz + z1), (cx, tip, cz)))
    quad(*[(cx + x, neck, cz + z) for x, z in base])
    for dx, dz in ((vane, 0.0), (0.0, vane)):   # the vanes
        quad((cx - dx, tail, cz - dz), (cx + dx, tail, cz + dz), (cx + dx, tail + 0.15, cz + dz),
             (cx - dx, tail + 0.15, cz - dz))
    group = body_codec.Group(list(palette), [], [], material, like.fvf, like.vb, like.pb)
    for face in faces:
        u = [b - a for a, b in zip(face[0], face[1])]
        w = [b - a for a, b in zip(face[0], face[2])]
        n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        size = math.sqrt(sum(c * c for c in n)) or 1.0
        n = tuple(c / size for c in n)
        for sign in (1.0, -1.0):   # both sides
            corners = face if sign > 0 else face[::-1]
            ids = tuple(group.add(c, tuple(sign * x for x in n), (0.5 + (c[0] - cx) * 4, (c[1] - tail) / ARROW_LENGTH),
                                  {0: 1.0}) for c in corners)
            group.triangles.append(ids)
    return group


def _harmless(data: bytes, toc, index: int, schema, key: str) -> None:
    """Refuse an impact graph that deals damage: a platform whose
    ``damage`` is set or that a link writes (X42's hit is the projectile's
    only one; W30 zeroes the rock's break's)."""
    from azurkit.core.xbr.graph import Graph
    g = Graph(data, toc, toc[index], schema)
    for r, kind in enumerate(g.types):
        if g.recs[r] is None:
            continue
        attrs = schema.types[kind].attrs if kind in schema.types else []
        if schema.is_a(kind, "platform") and "damage" in attrs and g.attrs(r)[attrs.index("damage")]:
            raise ValueError(f"its impact {key} deals damage ([{r}] {g.names[r]}): only X42's hit may")
        for lk in g.links(r):
            dst = g.types[lk.dst]
            if schema.is_a(dst, "platform") and schema.types[dst].attrs[lk.dst_plug] == "damage":
                raise ValueError(f"its impact {key} deals damage ([{r}] {g.names[r]}'s link to "
                                 f"[{lk.dst}] {g.names[lk.dst]}): only X42's hit may")


def _recolour_body(characters_xbr: bytes, batch: Batch, copier: Copier, source: str, ramp) -> int:
    """Each texture ``source``'s body draws (stage 0 of each LOD group's
    material row) recoloured through ``ramp`` in the copy's own material
    (a new ``surf`` each; the vanilla one stays the body's); how many."""
    toc = parse_toc(characters_xbr)
    made: dict[int, int] = {}
    done = set()
    for lod in body_codec.read_asset(characters_xbr, source).lods:
        for group in lod.groups:
            gshd, row = group.material
            if (gshd, row) in done or gshd not in copier.copies:
                continue
            done.add((gshd, row))
            entry = batch[copier.copies[gshd]]
            start = fx_edit.material_row_at(entry.payload, row)
            if start is None or struct.unpack_from("<I", entry.payload, start + 96)[0] < 1:
                continue
            off = start + 100
            src = entry.refs.get(off)
            if src is None or src >= len(toc) or toc[src].tag != "surf":
                continue
            if src not in made:
                payload = bytes(characters_xbr[toc[src].file_offset:toc[src].file_offset + toc[src].size])
                info = textures.info(payload)
                if "list" in info:
                    continue
                img = textures.recolor(textures.levels(payload)[0], ramp)
                made[src] = batch.add("surf", textures.surf(img, info["format"]),
                                      source=f"debug's body (recoloured from surf {src})")
            entry.point(off, made[src])
    return len(made)


def write_template(characters_xbr: bytes, index_xbr: bytes, xbe: bytes, fx_xbr: bytes, effect, scale: float
                   ) -> tuple[bytes, bytes, dict]:
    """W30 for an ``effects`` row's projectile (module docstring): the
    characters.xbr and index.xbr with ``debug`` wearing the template's
    body (at ``scale``: :func:`template_scale`), its clips, its fx and its
    break; with what it added.  :class:`ValueError` names a record, graph
    or body the files lack, or an impact that deals damage (D35)."""
    from azurkit.tools.characters.fx_templates import GRAFTS
    from azurkit.core.xbr.graph import Schema
    t = effect.template
    idx = _named(characters_xbr)
    if BODY in idx:
        raise ValueError(f"the throw: characters.xbr already holds {BODY}; build from vanilla")
    source = source_body(t)
    if f"characters/{source}".casefold() not in idx:
        raise ValueError(f"its {t.name} row: characters.xbr has no body characters/{source}")
    toc = parse_toc(characters_xbr)
    batch = Batch(characters_xbr)
    copier = Copier(characters_xbr, batch, same=True, label="characters.xbr")
    batch[copier.copy(idx[f"characters/{source}".casefold()])].name = BODY
    die = read_clip(characters_xbr, toc[idx[f"characters/{BOULDER}/die"]].file_offset)
    marks = [n for n, _ in marker_records(characters_xbr, source)]
    alpha = None if "m_alpha" in marks else len(marks)   # the marker the die keys, grown where the body lacks it
    held = Clip(STILL, tuple(Track(tr.target, tr.comp, ((0.0, tr.keys[0][1], 0.0, 0.0), (STILL, tr.keys[0][1], 0.0, 0.0)))
                             for tr in die.bones), ())
    for clip in CLIPS:
        if source == BOULDER and "authored" not in t.body:   # the boulder's own, byte for byte (as the rock's)
            batch[copier.copy(idx[f"characters/{BOULDER}/{clip}"])].name = f"{BODY}/{clip}"
        elif clip == "die":   # the boulder's: m_alpha keyed (its link loads the break), its pose held
            keyed = Clip(die.length, () if alpha is not None else die.bones,
                         tuple(Track(alpha if alpha is not None else tr.target, tr.comp, tr.keys, tr.modes)
                               for tr in die.markers))
            batch.add("banm", write_clip(keyed), name=f"{BODY}/die", source=f"{BOULDER}'s die, m_alpha keyed")
        else:   # the arrow: the boulder's bone where its clips hold it (another body: its bind pose, its mesh posed)
            batch.add("banm", write_clip(held if source == BOULDER else Clip(STILL, (), ())), name=f"{BODY}/{clip}",
                      source="a still pose")
    recoloured = _recolour_body(characters_xbr, batch, copier, source, colour_ramp(effect.colour)) \
        if effect.colour is not None and source == BOULDER and "authored" not in t.body else 0   # the fireball's rock
    new = batch.resources()
    default = fx_edit.Clone(characters_xbr, f"characters/{BOULDER}/fx/fx_default", xbe, base=len(toc) + len(new),
                            fx_xbr=fx_xbr)
    at: dict[str, tuple[int, str]] = {}   # a grafted record's name -> its index in the clone, its type
    kept = grafted = len(default.recs)
    for g in t.sets:
        for _, name, kind in GRAFTS[g].records:
            at.setdefault(name, (grafted, kind))
            grafted += 1
    grafts = [{"template": g, "parent": 0} for g in t.sets]
    edits = []

    def edit(name: str, **change) -> None:
        r, kind = at[name]
        edits.append({"record": r, "name": name, "type": kind, **change})
    if t.impact is not None:
        r, name, kind = BREAK_EFFECT
        edits.append({"record": r, "name": name, "type": kind, "graph": FX_BREAK})
    else:   # no impact: m_alpha's link loads nothing
        edits.append({"record": 2, "name": "m_alpha", "type": "transform", "links": [{"index": 0, "factor": 0.0}]})
    for e in t.edits:
        edit(e["record"], **{k: v for k, v in e.items() if k != "record"})
    for s in t.show:
        edit(s["record"], set={s["attr"]: float(s["value"])})
    for pname, param in t.params.items():
        for w in param["writes"]:
            if "record" in w and effect.values[pname] != "auto":
                edit(w["record"], set={w["attr"]: float(effect.values[pname]) * w.get("factor", 1.0)})
    if t.colour is not None and effect.colour is not None:
        for w in t.colour.get("writes", []):
            edit(w["record"], set=dict(zip(w["attrs"], effect.colour)))
        for rc in t.colour.get("recolor", []):
            edit(rc["record"], texture={**({"stage": rc["stage"]} if "stage" in rc else {}),
                                        "recolor": {"ramp": colour_ramp(effect.colour)}})
    try:
        default.apply(edits, grafts)
    except ValueError as exc:
        raise ValueError(f"its {t.name} row: {FX_DEFAULT}: {exc}") from None
    new += default.build(FX_DEFAULT)
    impact = None
    if t.impact is not None:
        src = fx_xbr if t.impact["archive"] == "fx" else characters_xbr
        named = _named(src)
        key = t.impact["key"].casefold()
        if key not in named:
            raise ValueError(f"its {t.name} row: {t.impact['archive']}.xbr has no graph {key}")
        _harmless(src, parse_toc(src), named[key], Schema(xbe), key)
        extra = Batch(characters_xbr, len(toc) + len(new))
        cop = Copier(src, extra, same=src is characters_xbr, label=f"{t.impact['archive']}.xbr")
        extra[cop.copy(named[key])].name = FX_BREAK
        new += extra.resources()
        impact = key
    grown = append_resources(characters_xbr, new)
    body_at = _named(grown)[BODY]
    if "authored" in t.body:   # our arrow in the boulder's mesh's place, on its bone, in its material
        from azurkit.tools.characters.characters import mesh_bounds
        asset = body_codec.read_asset(grown, SPECIES)
        low, high = mesh_bounds(characters_xbr, source)
        like = asset.lods[0].groups[0]
        asset.lods = [body_codec.Lod(asset.lods[0].bmsh, [arrow(tuple((a + b) / 2 for a, b in zip(low, high)), [],
                                                               like.material, like)])]
        grown = body_codec.write_asset(grown, asset)
    elif "pose" in t.body:   # the copy's mesh in its pose (AZ-704)
        grown = body_codec.write_asset(grown, posed(characters_xbr, t, body_codec.read_asset(grown, SPECIES)))
    if alpha is not None:   # the die keys m_alpha: the boulder's, grown on the body
        e = parse_toc(grown)[body_at]
        defaults = dict(marker_records(characters_xbr, BOULDER))["m_alpha"]
        grown = append_resources(grown, rewrite={body_at: grow_markers(bytes(grown[e.file_offset:e.file_offset + e.size]),
                                                                       [("m_alpha", defaults)])})
    named_new = [x.name for x in new if x.name]
    index = add_index_records(index_xbr, [IndexRecord(x.name, "characters.xbr", x.tag) for x in new if x.name])
    return grown, index, {"template": t.name, "source": source, "named": named_new, "recoloured": recoloured,
                          "impact": impact, "sets": list(t.sets), "grafted": grafted - kept,
                          "bytes": sum(len(x.payload) for x in new)}


def take_tick(rig: Rig, clip: Clip, props: dict, throw: Throw) -> tuple[int, float]:
    """A carrier's take (module docstring): the tick in the throw's
    ``take`` range at which the right hand's origin passes nearest the
    carried prop's place (its ride bone plus its offset), and that
    distance (model units)."""
    hand = [b.name for b in rig.bones].index(HAND)
    best = None
    for tick in range(throw.take[0], throw.take[1] + 1):
        at = origins(rig, clip, min(tick / 30.0, clip.length))
        for ride, offset, _ in props.values():
            d = math.dist(at[hand], tuple(a + b for a, b in zip(at[ride], offset)))
            if best is None or d < best[1]:
                best = (tick, d)
    return best


def throw_carry(rig: Rig, clip: Clip, props: dict, take: int, back: int, hz: float = 30.0) -> Clip:
    """The throw ``clip`` with each carried prop (:func:`~azurik_mod.patches._player_kit.carried`)
    on its ride bone to ``take``, hidden from there to ``back`` (waiting
    at the right hand's origin), shown there at ``back`` and carried back
    to its ride by the clip's end, keyed every tick (its own tracks
    replaced; each step :data:`HALF` a tick early)."""
    hand = [b.name for b in rig.bones].index(HAND)
    times = [i / hz for i in range(int(clip.length * hz + 1e-6) + 1) if i / hz < clip.length - 1e-4] + [clip.length]
    where = [origins(rig, clip, t) for t in times]
    last = len(times) - 1
    t_take, t_back = (take - HALF) / hz, (back - HALF) / hz
    tracks = [tr for tr in clip.bones if tr.target not in props]
    for k, (ride, offset, scale) in sorted(props.items()):
        def place(i: int) -> tuple[float, float, float]:   # hidden, it waits in the hand
            head = tuple(where[i][ride][c] + offset[c] for c in range(3))
            if times[i] < t_take:
                return head
            u = max(0.0, min(1.0, (times[i] - back / hz) / max(clip.length - back / hz, 1e-6)))
            u = u * u * (3 - 2 * u)
            return tuple(where[i][hand][c] + (head[c] - where[i][hand][c]) * u for c in range(3))
        values = [place(i) for i in range(len(times))]
        for c in range(3):
            keys = []
            for i, t in enumerate(times):
                lo, hi = max(0, i - 1), min(last, i + 1)
                slope = (values[hi][c] - values[lo][c]) / (times[hi] - times[lo]) if times[hi] > times[lo] else 0.0
                keys.append((t, values[i][c], slope, slope))
            tracks.append(Track(k, c, tuple(keys)))
        shown = tuple((t, scale if not t_take <= t < t_back else HIDDEN, 0.0, 0.0) for t in times)
        tracks += [Track(k, 7 + c, shown) for c in range(3)]
    return Clip(clip.length, tuple(sorted(tracks, key=lambda tr: (tr.target, tr.comp))), clip.markers)


__all__ = ["ARROW_LENGTH", "BODY", "COLUMNS", "FX_BREAK", "FX_DEFAULT", "HAND_LOW", "Plan", "RELEASE_SHARE",
           "SECTIONS", "SPAWN_LEAD", "SPECIES", "Shot", "TABLE_SIZE", "TEMPLATE_LOW", "arrow", "colour_ramp", "plan", "posed", "projectile_scale",
           "source_body", "take_tick", "template_plan", "template_scale", "throw_carry", "write_projectile",
           "write_species", "write_template"]

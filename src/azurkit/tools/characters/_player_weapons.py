"""Weapons as data (Step 2.161a; D492-D495): what a body holds and how it
attacks, read from ``assets/weapons.json`` (:data:`WEAPONS_FILE`) through
one resolver, :func:`loadout`, which the build
(:func:`~azurik_mod.patches._player_character.apply_player_model`) and the
attack listing (:func:`~azurik_mod.patches._player_character.attacks`)
share.

D492-D495 (the owner): weapons as their own thing, separate from the
body, each a prop and an attack style; every body keeps a default
weapon, and a build with its default is today's build, byte for byte.

- **The data** (:func:`weapons`): ``props`` (what a body holds:
  garret4's Axion staff, the farmers' hoe), ``styles`` (how it attacks:
  garret4's staff moves, the townsfolk's bare-hands kit,
  :mod:`~azurik_mod.patches._player_kit`, Balthazar's own build) and
  ``weapons`` (a title, a prop or none, and a style).  A key or value it
  doesn't know is refused by name (D35), as a variant recipe's is.
- **The default** (:func:`default_weapon`), derived from the body, in
  order: a body that holds a prop as its own (``own_on`` its name:
  garret4's Axion staff); a prop-less style's own source rig
  (Balthazar's magic on balthazar_airship); a body holding a loose prop
  in its own mesh (W26, :func:`loose_props`: the six townsmen farmers'
  hoe); any other body the bake maps
  (:data:`~azurik_mod.assets.retarget.MAPS`) with clips but no attack
  clip (:func:`attack_clips`: the 23 other townspeople, bare hands);
  else ``own``, its own attacks.
- **The loadout** (:class:`Loadout`): how much of the default a build
  applies.  A loose prop is carried in place in every mode (W26).  A
  style applies only in Balanced on a body the bake serves with clips but
  no attack clip (L4): garret4's staff style there swings his own attack
  for each column baked onto the rig (``g4/``, his window, with a
  carried prop X3's box around it: Step 2.195b), never in a variant's columns (L6: a variant
  of a farmer keeps its base's own picks); the kit bakes its family's
  clips (``t/``), a variant (booblord) in the columns its recipe leaves.
- **W26** (Step 2.134b; D337-D339; W20's place, Step 2.106): a loose
  prop rides the style's held channel (garret4's staff) on two carrier
  bones of the wearer (:func:`carry_props`, :func:`carried`), its fx at
  its ends (W6, :attr:`Loadout.fx_ends`), Balanced X3's borrowed rows the
  box around it in garret4's windows (:func:`held_window`, Step 2.195b,
  D767: the staff medium, the hoe long), and the measures of the body's own
  pose leave its carriers out (:func:`carriers`).
- **A picked weapon** (Step 2.161b; D492-D495, D543: the owner picks a
  weapon at build time, ``--player-weapon``, the GUI's "Weapon:" box, a
  recipe's ``weapon``): on a body the bake maps (:data:`MAPS`; the
  creatures and tokens: below) its style applies
  in Balanced whatever the anims rule (L5), a variant's recipe columns
  first (L6), and its prop applies in every mode (L3: Skin takes a prop
  only, so a prop-less weapon there is the default).  The prop is copied
  (W32, :func:`copy_prop`: the donor's group with its material, its row
  and textures copied into new entries, in every LOD the wearer draws,
  skinned to its tip carrier, :attr:`Loadout.k` its size) onto two
  carriers appended under the wearer's bone playing garret4's right hand
  (W31, :func:`add_carriers`; the farmers keep their own ``joint74`` and
  ``joint97`` for their own hoe), which each baked clip keys in the
  wearer's own hand frame (:func:`carried_copy`, the twin of :func:`carried`),
  X3's rows the box around it there (:func:`held_window`'s twin); a body
  holding a loose prop of its own wearing another hides it (W33,
  :func:`hide_own`).  Where a level places a critter wearing the body,
  the prop is the player's alone (P2, Step 2.203, D543): W38's copy of
  the body holds it and X47 binds the copy for the player, every NPC
  keeping vanilla's body.  :func:`offers` lists what each body takes and how
  it fits; :data:`WEAPON_GRADES` holds the sittings' grades.
- **Balthazar's magic** (Step 2.161c; D494): a style that plays a source
  rig's own build (:func:`source_style`: ``clips`` ``source_build``, X3's
  windows ``source_markers``, D421's lent picks and windows restored as
  the generic shape's options), baked onto a mapped body as ``b/<clip>``
  with X3's box his own for the clip at the body's size (Step 2.195b,
  D767: his blast ahead of his hand, his lightning's 7 m beam), and W34 (:func:`magic`): the markers his
  graph binds grown on the body before the bake (M1), those his graph
  hangs effects under ridden on its grip at k x his offset from his own
  (S6, :func:`ride`; k the body's height over his, AZ-691), and the player's clone of his default fx with his
  own build's retune, binds to a bone the body lacks renamed to the bone
  of its role (:func:`magic_graph`), which X40 binds to the player alone
  (a body with no default fx of its own, every townsperson, loads it:
  0x43700 asks nothing of the body, ``docs/RE_XBE.md``); W17's field,
  X37's drain and X38's copies read that clone.
- **garret4's other weapons** (Step 2.161d; :func:`_armed`): his staff
  cut from his mesh (W33, :func:`cut_staff`); the hoe on his own staff
  chain (:data:`ON_CHAIN`), swung with his own attacks; bare hands or
  Balthazar's magic baked onto his own rig in Balanced
  (:data:`~azurik_mod.assets.retarget.TARGETS_EXTRA`), X17 forced.
- **Creatures and tokens** (Step 2.161e; D493: every body offered, odd
  looks accepted; :func:`_held`): a body the bake doesn't map keeps its
  own clips; a prop rides its grip rigidly (:data:`RIGID`, ``grips``:
  :class:`Grip`, else a token's root), W31's carriers appended after
  every measure of its pose, X3's box at the prop's tip in Balanced
  (:attr:`Loadout.tip`, the logic its measured reach), or on a clipless
  body floats along garret4's staff (:data:`FLOAT`, :func:`float_clips`),
  X3's box around it; Balthazar's magic casts from a creature's
  grip in its own attack clips (:attr:`Loadout.cast`, :func:`cast_clips`).
- **A weapon is a whole moveset** (Step 2.161g; D585, the owner: "for
  weapons, booblord's spin would be a type of weapon, whereas if she has
  the axion she would have garret's moveset"; D592 "Every body"): a
  style may name a variant's recipe (``variant``: booblord's spins,
  :func:`moveset`), the variant's default weapon (:func:`default_weapon`)
  built as its recipe always was; any other weapon a variant picks drops
  its recipe's moveset (:func:`~azurik_mod.patches._player_variants.unarmed`,
  :attr:`Loadout.recipe`), so the weapon's style plays every column; and
  any other body with clips takes the moveset weapon (:func:`lent`): the
  recipe's spins generated on its own rig, their boxes x its height over
  the recipe's body's, the columns it leaves the bare-hands kit's on a
  body the bake serves, else its own picks; its attack sliders the
  recipe's (:func:`attack_recipe`).
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import re
import statistics
import struct
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from azurkit.tools.characters import fx_edit, fx_templates
from azurkit.tools.characters.characters import (
    VERTEX_SIZE,
    Body,
    DamageWindow,
    MeshGroup,
    body_at,
    bone_records,
    damage_windows,
    height,
    inverse_binds,
    marker_default,
    marker_records,
    mesh_groups,
    near,
    read_body,
)
from azurkit.tools.characters.grades import load_grades
from azurkit.tools.characters.retarget import (
    LIFTS,
    MAPS,
    SAMPLE_HZ,
    TARGETS,
    Clip,
    Retarget,
    Rig,
    Track,
    _turn,
    bake_clip,
    evaluate,
    named_clip,
    origins,
    qinv,
    qmul,
    qnorm,
    role_map,
    turned,
)
from azurkit.tools.characters._player_damage_marker import garret4_window
from azurkit.tools.characters._player_kit import CARRY_HZ, KIT, Style, kit_style
from azurkit.core.xbr.append import NewResource
from azurkit.core.xbr.graph import Graph, Schema, bind_name
from azurkit.core.xbr.nodes import named_resources, parse_toc

WEAPONS_FILE = Path(__file__).resolve().parent / "weapons.json"
"""The built-in weapons (module docstring)."""
PLAYER = "garret4"
"""The player's species, whose clips B bakes onto a mapped body (``g4/``)."""
OWN = "own"
"""A body's own attacks: the default of a body no other rule gives a weapon."""
LOOSE = "loose"
"""A prop's ``own_on`` for one a body holds loose in its own mesh (W26)."""
ENDS = ("native", "carriers")
"""Where a prop's staff fx bind (W6): its own rig's staff ends, or its carriers."""
DEFAULT = "default"
"""``--player-weapon``'s name for the body's own default weapon."""
IN_PLACE, COPY, ON_CHAIN = "in_place", "copy", "on_chain"
"""How a :class:`Loadout` carries its prop: a loose prop in the holder's
own mesh on its own end joints (W26), a copy on carriers appended to
the wearer (W31, W32), or a copy skinned to the style source's own held
channel (garret4's staff chain, Step 2.161d: the hoe on his
``m_stafftop``, which his own clips move)."""
RIGID, FLOAT = "rigid", "floating"
"""Step 2.161e (D493): a copy on carriers appended under a creature's or a
token's grip, which its own clips carry rigidly (no clip keys them); a
copy on a carrier of its own at the model's root, keyed along garret4's
staff in each of his clips baked onto a clipless body as timers."""
LOOK, TIP_HITS = "look", "look + tip hits"
"""A creature's fits (the 2.161 design's 2.5): its prop a look on its own
clips, and with X3's box at the prop's tip (Balanced: :attr:`Loadout.tip`)."""
TIP_BOX = 1.3889
"""The side (m, at garret4's size) of the cube X3's box is at a rigid
prop's tip (:attr:`Loadout.tip`; D115's default, unmeasured: garret4's
attack box's height, ``GARRET4_EXTENT``'s z), x :attr:`Loadout.k` and the
drawn scale."""
CAST_SWITCH = "m_balth_lightningswitch"
"""Balthazar's switch a creature's cast keys (Step 2.161e,
:func:`cast_clips`): his lightning's, on while its translateZ is 0.5 or
more, so his stream and bolts leave the creature's grip."""
SIZE_BAND = (0.9, 1.1)
"""A copied prop's size is the wearer's height over garret4's, but 1
inside this band (the townsmen, Balthazar and the fire and water
elementals hold it at garret4's size, as the farmers hold the hoe)."""
CARRIER_MAX = 7
"""The longest carrier name W6's binds hold (its 10- and 13-character
strings: :func:`~azurik_mod.patches._player_character.follow_hands`)."""
ODD: dict[str, str] = {"golem": "its long arms swing it wide"}
"""The mapped bodies a picked weapon fits oddly (the 2.161 design's
2.5), by body (case-folded): the fit the picker and the listing show."""
GOOD = "good"
SOURCE_BUILD, SOURCE_MARKERS = "source_build", "source_markers"
"""A style's ``clips`` and ``windows`` that play its source rig's own build
(Step 2.161c, :func:`source_style`): each column the clip that build plays,
X3's window on each clip from the source's own damage markers."""
_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
_BODY = re.compile(r"[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)*\Z")
_DIR = re.compile(r"[a-z]{1,2}/\Z")
_FIELDS = {"props": (("title", "own_on", "carriers", "ends"), ("clip", "hand", "over", "own_carriers", "mesh")),
           "styles": (("title",), ("source", "hand", "held", "kit", "dir", "clips", "windows", "fx", "variant", "body",
                                   "effects", "drain")),
           "weapons": (("title", "prop", "style"), ())}


@dataclass(frozen=True)
class PropMesh:
    """Where a copied prop's mesh comes from (a prop's ``mesh``): the
    ``body``'s LOD 0 groups skinned to ``bones`` alone (garret4's staff),
    or its :func:`loose_props` (``loose``: the farmer's hoe)."""

    body: str
    bones: tuple[str, ...] | None = None
    loose: bool = False


@dataclass(frozen=True)
class Prop:
    """What a body holds (``weapons.json``'s ``props``)."""

    name: str
    title: str
    own_on: str
    """The body that holds it as its own (garret4), or :data:`LOOSE`: any
    body holding it loose in its own mesh (:func:`loose_props`)."""
    carriers: tuple[str, str]
    """Its top and bottom end bones on a wearer it is copied onto (W31,
    Step 2.161b): garret4's staff ends' names, so the staff fx graphs
    bind them natively; else two names of at most :data:`CARRIER_MAX`
    characters (``wpn_tip``, ``wpn_end``), so W6's binds fit both."""
    ends: str
    """Where W6 binds the staff fx (:data:`ENDS`)."""
    clip: str | None = None
    """A loose prop: the clip whose body holds it (the farmers' own hoeing,
    identical on all six)."""
    hand: str | None = None
    """A loose prop: the bone its first carrier hangs from."""
    own_carriers: tuple[str, str] | None = None
    """A loose prop: the holder's two free end joints W26 carries it on in
    place, the first re-parented to :attr:`hand` at the prop's blade tip,
    the second under it at the handle's end (the farmers' end nodes of
    ``right_thumb_3`` and ``right_pinkyfgr_3``: no vertex, no clip key,
    no role, identical on all six; 7 characters, so W6's binds fit both
    strings)."""
    mesh: PropMesh | None = None
    """Where a copy's mesh comes from (W32)."""
    over: float = 0.0
    """How far (model units) past the style's held top along its axis the
    prop's blade tip rides: the hoe's 0.735 is :data:`PROP_GRIP` - (1 -
    0.442) x 1.55, so its grip point sits at garret4's right hand's mean
    grip on his staff over his 19 melee windows (0.442 of the way bottom
    to top, 220 samples: Step 2.134b's read,
    ``results/hoe_reach_D1.2.15_g4class``) and the handle's end 0.407
    inside ``m_staffbottom``."""


@dataclass(frozen=True)
class WeaponStyle:
    """How a weapon attacks (``weapons.json``'s ``styles``)."""

    name: str
    title: str
    source: str | None = None
    """The rig whose own attacks it is (garret4's staff, Balthazar's build)."""
    hand: str | None = None
    """The source's bone holding its prop (garret4's right hand)."""
    held: tuple[str, str] | None = None
    """The source's held channel, its prop's top and bottom bones: a held
    prop's tip rides along them (W26)."""
    kit: str | None = None
    """A clip kit's folder (:mod:`~azurik_mod.patches._player_kit`): the
    townsfolk's."""
    dir: str | None = None
    """Where a source's own clips go on the wearer (``b/``: ``characters/<body>/b/<clip>``, Step 2.161c)."""
    clips: str | None = None
    """:data:`SOURCE_BUILD`: each column plays the clip the source's own build plays there (Step 2.161c)."""
    windows: str | None = None
    """:data:`SOURCE_MARKERS`: X3's window on each clip from the source's own damage markers (Step 2.161c)."""
    fx: str | None = None
    """The species whose own-build graph the player's clone takes (W34, Step 2.161c: Balthazar's, with his
    W23 retune)."""
    variant: str | None = None
    """A built-in variant whose recipe's moveset it plays (Step 2.161g, D585: booblord's spins, :func:`moveset`)."""
    body: str | None = None
    """That recipe's body, whose height its boxes are authored at (:func:`lent` scales them to a wearer's)."""
    effects: tuple | None = None
    """Its ``effects`` rows (Step 2.167b, D538's E2: :func:`~azurik_mod.assets.fx_templates.effects`, a
    recipe's shape), played on every body wearing it beside a recipe's own; ``None``: none."""
    drain: str | None = None
    """``drain.targets`` (Step 2.196, D765, a recipe's shape: :func:`~azurik_mod.patches._player_variants.
    drain_targets`): whom the life drain it plays takes life from, its target alone (``nearest``; ``None``, the
    default, the same) or (``all``) every critter its box touches."""


@dataclass(frozen=True)
class Weapon:
    """A weapon (``weapons.json``'s ``weapons``): a prop (or none) and a style."""

    name: str
    title: str
    prop: Prop | None
    style: WeaponStyle

    @property
    def sha(self) -> str:
        """sha256[:12] of its prop and style records without their titles,
        as a variant recipe's (``recipe_sha``)."""
        doc = {"prop": None if self.prop is None else _fields(self.prop), "style": _fields(self.style)}
        if self.style.effects is not None:   # Step 2.167b: each template as built, as a recipe's sha folds it
            from azurkit.tools.characters._player_variants import templated
            doc["style"]["effects"] = templated([{"template": e.template.name, "columns": list(e.columns),
                                                  "colour": e.colour, **e.values, **({"seek": True} if e.seek else {})}
                                                 for e in self.style.effects])
        return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Grip:
    """A creature's grip (``weapons.json``'s ``grips``, Step 2.161e; the
    2.161 design's L7, read off each body's bone tree, Step 2.161's read
    of the bodies: a claw, pincer, jaw, tentacle or tail tip): the bone a
    picked prop rides rigidly (:data:`RIGID`), and the prop's ``turn``
    (degrees about the model's x, y and z in turn, about the grip) and
    ``offset`` (model units) from garret4's idle hold there, for a look
    the pictures call for."""

    body: str
    bone: str
    turn: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Fit:
    """W35's arm fit for a body or a built-in variant wearing Garret's
    staff moves (``weapons.json``'s ``fits``, Step 2.161g, AZ-696; written
    by ``scripts/weapon_fit.py``): both ``*_arm_1`` turned ``clips[clip]``
    = (out, forward) degrees in each of his clips so its prop clears its
    chest; a variant's ``sha`` its recipe's when fitted."""

    name: str
    clips: dict
    sha: str | None = None


_LATER = ("dir", "clips", "windows", "fx", "variant", "body", "effects", "drain")
"""A style's keys from Step 2.161c, hashed only where a record has them (as a recipe's are), so the shas
WEAPON_GRADES and the recipes hold for the weapons before them stay theirs."""


def _fields(record) -> dict:
    return {k: v for k, v in asdict(record).items() if k not in ("name", "title") and not (k in _LATER and v is None)}


def _keys(where: str, given, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> None:
    if not isinstance(given, dict):
        raise ValueError(f"{where}: {given!r} is not an object")
    unknown = sorted(set(given) - set(required) - set(optional))
    missing = [k for k in required if k not in given]
    if unknown:
        raise ValueError(f"{where}: unknown key {', '.join(map(repr, unknown))}")
    if missing:
        raise ValueError(f"{where}: missing {', '.join(map(repr, missing))}")


def _name(where: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: {value!r} is not a name")
    return value


def _pair(where: str, value) -> tuple[str, str]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{where}: {value!r} is not a list of two bone names")
    return _name(f"{where}[0]", value[0]), _name(f"{where}[1]", value[1])


def load_weapons(text: str, where: str = "weapons.json") -> dict[str, Weapon]:
    """The weapons of a ``weapons.json`` document (module docstring),
    by name; :class:`ValueError` names an unknown or missing key, a value
    of the wrong kind or a name no record has (D35), its ``grips`` too
    (:func:`_load`)."""
    return _load(text, where)[0]


def _vec3(where: str, value) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3 or any(
            isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) for c in value):
        raise ValueError(f"{where}: {value!r} is not a list of three finite numbers")
    return tuple(float(c) for c in value)


def _load(text: str, where: str) -> tuple[dict[str, Weapon], dict[str, Grip], dict[str, Fit]]:
    """A ``weapons.json`` document's weapons (:func:`load_weapons`), its
    creature grips by body, case-folded (:class:`Grip`: a body's name,
    its ``bone``, and ``turn`` and ``offset`` three numbers each) and its
    arm fits (:class:`Fit`, W35: a body's or a built-in variant's name,
    ``clips`` {clip: [out, forward] degrees} and a variant's ``sha``)."""
    doc = json.loads(text)
    _keys(where, doc, (*_FIELDS, "grips"), ("fits",))
    fitted = {}
    if not isinstance(doc.get("fits", {}), dict):
        raise ValueError(f"{where}: fits {doc['fits']!r} is not an object")
    for name, row in doc.get("fits", {}).items():
        at = f"{where}: fits.{name}"
        if not _BODY.match(name):
            raise ValueError(f"{at}: a body's or a variant's name is lower-case letters, digits, _ and /")
        _keys(at, row, ("clips",), ("sha",))
        if not isinstance(row["clips"], dict) or not row["clips"]:
            raise ValueError(f"{at}.clips: {row['clips']!r} is not an object of clips")
        turns = {}
        for clip, turn in row["clips"].items():
            if not isinstance(turn, list) or len(turn) != 2 or any(
                    isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) for c in turn):
                raise ValueError(f"{at}.clips.{clip}: {turn!r} is not two finite numbers (out, forward degrees)")
            turns[_name(f"{at}.clips", clip)] = (float(turn[0]), float(turn[1]))
        fitted[name] = Fit(name, turns, _name(f"{at}.sha", row["sha"]) if "sha" in row else None)
    if not isinstance(doc["grips"], dict):
        raise ValueError(f"{where}: grips {doc['grips']!r} is not an object")
    held = {}
    for body, g in doc["grips"].items():
        at = f"{where}: grips.{body}"
        if not _BODY.match(body):
            raise ValueError(f"{at}: a body's name is lower-case letters, digits, _ and /")
        _keys(at, g, ("bone",), ("turn", "offset"))
        held[body] = Grip(body, _name(f"{at}.bone", g["bone"]), *(
            _vec3(f"{at}.{k}", g[k]) if k in g else (0.0, 0.0, 0.0) for k in ("turn", "offset")))
    records: dict[str, dict] = {}
    for section, (required, optional) in _FIELDS.items():
        if not isinstance(doc[section], dict):
            raise ValueError(f"{where}: {section} {doc[section]!r} is not an object")
        for name, rec in doc[section].items():
            at = f"{where}: {section}.{name}"
            if not _NAME.match(name):
                raise ValueError(f"{at}: a name is lower-case letters, digits and _, starting with a letter")
            _keys(at, rec, required, optional)
            _name(f"{at}.title", rec["title"])
        records[section] = doc[section]
    props = {}
    for name, p in records["props"].items():
        at = f"{where}: props.{name}"
        own_on = _name(f"{at}.own_on", p["own_on"])
        if p["ends"] not in ENDS:
            raise ValueError(f"{at}.ends: {p['ends']!r} is not one of {', '.join(ENDS)}")
        if own_on == LOOSE and not ("clip" in p and "hand" in p and "own_carriers" in p):
            raise ValueError(f"{at}: a loose prop names the clip its holder holds it in, its hand and its "
                             "own_carriers")
        over = p.get("over", 0.0)
        if isinstance(over, bool) or not isinstance(over, (int, float)) or not math.isfinite(over):
            raise ValueError(f"{at}.over: {over!r} is not a finite number")
        carriers = _pair(f"{at}.carriers", p["carriers"])
        own = _pair(f"{at}.own_carriers", p["own_carriers"]) if "own_carriers" in p else None
        if p["ends"] == "carriers" and any(len(n) > CARRIER_MAX for n in (*carriers, *(own or ()))):
            raise ValueError(f"{at}: a carrier W6 binds the staff fx to is at most {CARRIER_MAX} characters")
        mesh = None
        if "mesh" in p:
            m = p["mesh"]
            _keys(f"{at}.mesh", m, ("body",), ("bones", "rule"))
            if ("bones" in m) == ("rule" in m):
                raise ValueError(f"{at}.mesh: it names the donor's bones or its rule, one of them")
            if "rule" in m and m["rule"] != LOOSE:
                raise ValueError(f"{at}.mesh.rule: {m['rule']!r} is not {LOOSE!r}")
            if "bones" in m and (not isinstance(m["bones"], list) or not m["bones"]):
                raise ValueError(f"{at}.mesh.bones: {m['bones']!r} is not a list of bone names")
            mesh = PropMesh(_name(f"{at}.mesh.body", m["body"]),
                            tuple(_name(f"{at}.mesh.bones", b) for b in m["bones"]) if "bones" in m else None,
                            "rule" in m)
        props[name] = Prop(name, p["title"], own_on, carriers, p["ends"],
                           _name(f"{at}.clip", p["clip"]) if "clip" in p else None,
                           _name(f"{at}.hand", p["hand"]) if "hand" in p else None, own, mesh, float(over))
    from azurkit.tools.characters._player_variants import drain_targets
    styles = {}
    for name, s in records["styles"].items():
        at = f"{where}: styles.{name}"
        if sum(k in s for k in ("source", "kit", "variant")) != 1:
            raise ValueError(f"{at}: a style names its source rig, its kit or a variant's recipe, one of them")
        if "variant" in s:   # Step 2.161g (D585): a recipe's moveset, read by name at build time
            from azurkit.tools.characters._player_variants import builtins
            if ("body" not in s) or any(k in s for k in ("hand", "held", "dir", "clips", "windows", "fx")):
                raise ValueError(f"{at}: a variant's moveset names its recipe's body, and no held channel, dir, "
                                 "clips, windows or fx")
            if s["variant"] not in builtins():
                raise ValueError(f"{at}.variant: {s['variant']!r} is no built-in variant (the built-ins: "
                                 f"{', '.join(builtins())})")
        elif "body" in s:
            raise ValueError(f"{at}.body: only a variant's moveset names its recipe's body")
        if "kit" in s and s["kit"] != KIT.name:
            raise ValueError(f"{at}.kit: {s['kit']!r} is no kit (the kits: {KIT.name})")
        if ("held" in s) != ("hand" in s):
            raise ValueError(f"{at}: a held channel names its hand, and a hand its held channel")
        if "clips" in s and s["clips"] != SOURCE_BUILD:
            raise ValueError(f"{at}.clips: {s['clips']!r} is not {SOURCE_BUILD!r}")
        if "windows" in s and s["windows"] != SOURCE_MARKERS:
            raise ValueError(f"{at}.windows: {s['windows']!r} is not {SOURCE_MARKERS!r}")
        own = ("dir", "clips", "windows")
        if any(k in s for k in (*own, "fx")) and not ("source" in s and "held" not in s and all(k in s for k in own)):
            raise ValueError(f"{at}: a source's own build names its source, its dir, clips and windows, and no "
                             "held channel")
        if "dir" in s and (not isinstance(s["dir"], str) or not _DIR.match(s["dir"])):
            raise ValueError(f"{at}.dir: {s['dir']!r} is not one or two lower-case letters and a /")
        styles[name] = WeaponStyle(name, s["title"], _name(f"{at}.source", s["source"]) if "source" in s else None,
                                   _name(f"{at}.hand", s["hand"]) if "hand" in s else None,
                                   _pair(f"{at}.held", s["held"]) if "held" in s else None, s.get("kit"),
                                   s.get("dir"), s.get("clips"), s.get("windows"),
                                   _name(f"{at}.fx", s["fx"]) if "fx" in s else None,
                                   s.get("variant"), _name(f"{at}.body", s["body"]) if "body" in s else None,
                                   fx_templates.effects(f"{at}.effects", s["effects"]) if "effects" in s else None,
                                   drain_targets(f"{at}.drain", s["drain"]) if "drain" in s else None)
    out = {}
    for name, w in records["weapons"].items():
        at = f"{where}: weapons.{name}"
        if name == OWN:
            raise ValueError(f"{at}: {OWN!r} is a body's own attacks, not a weapon")
        if w["prop"] is not None and w["prop"] not in props:
            raise ValueError(f"{at}.prop: {w['prop']!r} is no prop of {where}")
        if w["style"] not in styles:
            raise ValueError(f"{at}.style: {w['style']!r} is no style of {where}")
        if w["prop"] is not None and props[w["prop"]].own_on == LOOSE and styles[w["style"]].held is None:
            raise ValueError(f"{at}: a loose prop rides its style's held channel, and {w['style']!r} has none")
        out[name] = Weapon(name, w["title"], None if w["prop"] is None else props[w["prop"]], styles[w["style"]])
    return out, held, fitted


@functools.cache
def _built_in() -> tuple[dict[str, Weapon], dict[str, Grip], dict[str, Fit]]:
    return _load(WEAPONS_FILE.read_text(encoding="utf-8"), "weapons.json")


def weapons() -> dict[str, Weapon]:
    """The built-in weapons (:data:`WEAPONS_FILE`)."""
    return _built_in()[0]


def grips() -> dict[str, Grip]:
    """The built-in creature grips (:data:`WEAPONS_FILE`'s ``grips``), by body."""
    return _built_in()[1]


def fits() -> dict[str, Fit]:
    """The built-in arm fits (:data:`WEAPONS_FILE`'s ``fits``, W35), by body or variant."""
    return _built_in()[2]


def fit_turns(body: str | None, variant=None, w: Weapon | None = None) -> dict[str, tuple[float, float]]:
    """W35's turns (Step 2.161g, AZ-696) for ``body`` (``variant`` the
    recipe it wears) swinging ``w``'s prop on Garret's staff moves, by his
    clip: a built-in variant's own row while its sha is the recipe's (a
    variant with a mesh or arms of its own: else none; one ``from``
    another, as shipped, that one's row: Step 2.177,
    :func:`~azurik_mod.patches._player_variants.fit_sha`), else the body's
    row; none for any other weapon (:func:`fits`)."""
    if body is None or w is None or w.prop is None or w.style.held is None:
        return {}
    row = fits().get(getattr(variant, "files", "") or getattr(variant, "name", None)) if variant is not None else None
    if variant is not None and (row is not None or getattr(variant, "mesh", None) is not None
                                or getattr(variant, "arms", 0.0)):
        if row is None or getattr(variant, "source", None) != "built-in":
            return {}
        from azurkit.tools.characters._player_variants import fit_sha
        return dict(row.clips) if row.sha == fit_sha(variant) else {}
    row = fits().get(body.casefold())
    return dict(row.clips) if row is not None else {}


def attack_clips(body: Body) -> tuple[str, ...]:
    """The clips ``body`` can attack with, sorted by name: those that
    switch its damage marker on, and every ``attack*`` clip, which X3
    gives a hit box when it switches none on (Step 2.64)."""
    return tuple(sorted(set(body.damage_clips) | {c for c in body.clips if c.startswith("attack")}))


def default_weapon(characters_xbr: bytes, body: Body, variant=None) -> Weapon | None:
    """``body``'s default weapon (module docstring: a ``variant``'s own
    moveset, Step 2.161g; garret4's Axion staff,
    Balthazar's magic on his own rig, a loose prop's, the kit's bare
    hands on a mapped body with clips but no attack clip), or ``None``:
    its own attacks (:data:`OWN`)."""
    found = weapons().values()
    mine = getattr(variant, "files", "") or getattr(variant, "name", None)   # Step 2.177: ``from``'s moveset
    own = next((w for w in found if w.style.variant is not None and w.style.variant == mine), None)
    if own is not None:
        return own
    for rule in (lambda w: w.prop is not None and w.prop.own_on == body.name,
                 lambda w: w.prop is None and w.style.source == body.name,
                 lambda w: w.prop is not None and w.prop.own_on == LOOSE
                 and bool(loose_props(characters_xbr, body, w.prop)),
                 lambda w: w.prop is None and w.style.kit is not None and body.name.casefold() in MAPS
                 and bool(body.clips) and not attack_clips(body)):
        for w in found:
            if rule(w):
                return w
    return None


@dataclass(frozen=True)
class Carriers:
    """The bones a carried prop rides (W26): ``bones`` hung from ``hand`` (``None``: a floating carrier's root)."""

    hand: str | None
    bones: tuple[str, ...]


@dataclass(frozen=True)
class Loadout:
    """What a build of a body makes of its weapon (:func:`loadout`)."""

    weapon: Weapon | None
    """The weapon it wears: the body's default (:func:`default_weapon`) or the one picked, ``None`` its own
    attacks."""
    prop: Prop | None
    """The prop it carries, every mode (W26's in place: the farmers' hoe; W31-W32's copy), else ``None``."""
    borrowing: bool
    """Every attack column swings the style source's own attack for it baked onto the rig (``g4/``,
    Step 2.134a): garret4's staff moves, his box and window for the column (X3)."""
    kit: Style | None
    """A clip kit it swings (Step 2.159a: the bare-hands kit baked as ``t/``), else ``None``."""
    carry: str | None = None
    """How it carries :attr:`prop`: :data:`IN_PLACE` (W26), :data:`COPY` (W31, W32), :data:`ON_CHAIN`,
    :data:`RIGID` or :data:`FLOAT`, else ``None``."""
    grip: str | None = None
    """A picked weapon's grip: the wearer's bone playing garret4's right hand, the copy's carriers' parent (a
    creature's :class:`Grip`, Step 2.161e; ``None`` on a floating carrier)."""
    k: float = 1.0
    """A copied prop's size on the wearer (:data:`SIZE_BAND`); a moveset weapon's box scale there (:func:`lent`)."""
    hide: bool = False
    """W33: the body's own loose prop hidden (a farmer wearing another weapon)."""
    default: Weapon | None = None
    """The body's own default weapon (:func:`default_weapon`)."""
    picked: bool = False
    """A weapon other than the body's default (``--player-weapon``, a recipe's ``weapon``)."""
    fit: str = GOOD
    """How a picked weapon fits the body: ``good`` or ``odd`` (:data:`ODD`)."""
    body: str | None = None
    """The body it was resolved for."""
    lift: float = 0.0
    """The baked clips' root lift on the body (``Retarget.lift``), which the copy's tips read (:func:`held_window`)."""
    tip: bool = False
    """X3's box at a rigid prop's tip on every attack column, in the windows of the body's own clips (Step
    2.161e; the 2.161 design's 2.6, S3, S4: Balanced, ``_player_character.tip_plan``), in place of its own boxes."""
    cast: Style | None = None
    """A style whose graph a creature casts from its grip on its own attack clips (Step 2.161e: Balthazar's
    magic, :func:`cast_clips`), else ``None``."""
    tips: dict = field(default_factory=dict, compare=False, repr=False)
    """A copy's point samples by clip and point (:func:`_worn_tips`), filled as they are read."""
    recipe: object = None
    """The recipe its attack columns play (Step 2.161g; D585, D592): a variant's with its moveset dropped
    (another weapon picked, :func:`~azurik_mod.patches._player_variants.unarmed`), or a moveset weapon's laid
    over the wearer (:func:`lent`); ``None``: the variant's own, or none (W23's overlay)."""
    left: tuple[str, ...] = ()
    """The moveset weapon's columns the wearer can't make (:func:`lent`), which keep its other picks."""
    turns: dict = field(default_factory=dict, compare=False)
    """W35's arm turns in Garret's clips baked onto the body (:func:`fit_turns`), by clip."""
    size: tuple[float, float] | None = None
    """Its prop's length and pad (:func:`prop_size`, X3's box around it: :func:`held_window`), read from the
    ``characters.xbr`` :func:`loadout` resolves it on, before W26 re-skins a farmer's own hoe; ``None``: no prop."""

    @property
    def lent(self) -> bool:
        """A moveset weapon's recipe laid over a body not its own (:func:`lent`)."""
        return self.recipe is not None and self.weapon is not None and self.weapon.style.variant is not None

    @property
    def name(self) -> str:
        return OWN if self.weapon is None else self.weapon.name

    @property
    def copied(self) -> bool:
        """Its prop is a copy on carriers appended to the wearer (W31, W32): on a mapped body's grip, a
        creature's (rigid) or a clipless body's root (floating)."""
        return self.carry in (COPY, RIGID, FLOAT)

    @property
    def cut(self) -> bool:
        """W33 on garret4 (Step 2.161d): a weapon other than his own Axion
        staff cuts his staff from his mesh (:func:`cut_staff`)."""
        return self.picked and self.body == PLAYER

    @property
    def walls_off(self) -> bool:
        """X17 forced (Step 2.161d): garret4 with no prop on his staff chain
        keeps its ``staff_center2slide``, which the game checks against the
        walls, though his staff is cut; the hoe riding the chain keeps his
        wall check."""
        return self.cut and self.prop is None

    @property
    def carriers(self) -> Carriers | None:
        """The bones its carried prop rides, which the measures of the
        body's own pose leave out (:func:`carriers`), else ``None``: the
        holder's own end joints under its hand (in place), else the copy's
        carriers under its grip (the 2.161 design's L8); on garret4's staff
        chain (:data:`ON_CHAIN`, Step 2.161g, D618) the prop's under his
        ``m_stafftop``, which no measure reads."""
        if self.carry == IN_PLACE:
            return Carriers(self.prop.hand, self.prop.own_carriers)
        if self.carry == ON_CHAIN:
            return Carriers(self.weapon.style.held[0], self.prop.carriers)
        return Carriers(self.grip, self.prop.carriers) if self.copied else None

    @property
    def reaching(self) -> bool:
        """Whether X3's borrowed rows grow to its carried prop's tip (W26, D339)."""
        return self.prop is not None and self.borrowing

    @property
    def fx_ends(self) -> tuple[str, str] | None:
        """The bones W6 binds the staff fx's two ends to: its carried prop's
        carriers (D338), else ``None`` (the action point's hands or point;
        a copied Axion staff's own ends, :attr:`native`)."""
        if self.prop is None or self.prop.ends != "carriers" or self.carriers is None:
            return None
        return self.carriers.bones

    @property
    def native(self) -> bool:
        """A copied prop whose carriers are garret4's staff ends by name:
        the staff fx bind them as on him, so W4 and W6 are left out (the
        2.161 design's F-E)."""
        return self.copied and self.prop.ends == "native"


def loadout(characters_xbr: bytes, body: Body, mode: str, baked: bool, variant=None,
            weapon: str | None = None) -> Loadout:
    """What a build of ``body`` in gameplay ``mode`` makes of its weapon,
    ``baked`` whether the build bakes garret4's clips onto it (B),
    ``variant`` the recipe it wears, if any, ``weapon`` the one picked
    (a name of :func:`weapons`, :data:`OWN` or :data:`DEFAULT`; ``None``
    or :data:`DEFAULT`, the recipe's ``weapon``, else the body's default).  The default (module
    docstring): a loose prop carried in every mode; a style only in
    Balanced on a baked body with clips but no attack clip, garret4's
    staff never in a variant's columns.  A picked one: :func:`_picked`.
    :class:`ValueError` names a body the kit's rigs don't fit and a weapon
    the body can't take (D35).  Step 2.161g (D585): a variant's default is
    its own moveset, its recipe's columns, the rest its base's default's;
    another weapon picked over its recipe's (``weapon``) drops its moveset
    (:attr:`Loadout.recipe`)."""
    default = default_weapon(characters_xbr, body, variant)
    name = getattr(variant, "weapon", None) if weapon in (None, DEFAULT) else weapon   # a recipe's is its default
    if name not in (None, DEFAULT, default.name if default is not None else OWN) and not (
            name == OWN and (body.name == PLAYER or default is not None and default.style.source == body.name)):
        where = f"--player-weapon {name}" if weapon not in (None, DEFAULT) else f"the recipe's weapon {name}"
        lo = _picked(characters_xbr, body, mode, baked, name, default, variant, where)
        if variant is not None and lo.picked and lo.recipe is None and name != variant.weapon:
            from azurkit.tools.characters._player_variants import unarmed
            lo = replace(lo, recipe=unarmed(variant))   # D585: the weapon's style in every column
    elif default is not None and default.style.variant is not None:   # D585: the variant's own moveset, as built
        lo = replace(_own(characters_xbr, body, mode, baked, variant, default_weapon(characters_xbr, body)),
                     weapon=default, default=default)
    else:
        lo = _own(characters_xbr, body, mode, baked, variant, default)
    return lo if lo.prop is None else replace(lo, size=prop_size(characters_xbr, lo.prop))


def _own(characters_xbr: bytes, body: Body, mode: str, baked: bool, variant, default: Weapon | None) -> Loadout:
    """:func:`loadout`'s body's ``default`` (module docstring)."""
    if default is None:
        return Loadout(None, None, False, None, body=body.name)
    prop = default.prop if default.prop is not None and default.prop.own_on == LOOSE else None
    style = default.style
    serves = mode == "own" and baked and bool(body.clips) and not attack_clips(body)
    kit = None
    if serves and style.kit is not None:
        kit = kit_style(characters_xbr, body)
        if kit is None:
            raise ValueError(f"{body.name}: no rig of the {style.kit} kit has its bones ({default.title})")
    return Loadout(default, prop, serves and style.source == PLAYER and variant is None, kit,
                   IN_PLACE if prop is not None else None, default=default, body=body.name)


def grip(characters_xbr: bytes, body: Body) -> str:
    """The bone of ``body`` a picked weapon's carriers hang from (the 2.161
    design's L7): the one the role map gives garret4's right hand
    (keylord's ``right_hand``, Balthazar's ``left_w``: his arms are
    mirrored, the elementals' ``r_wrist``, the golem's ``hand_right_1``),
    else its nearest ancestor whose bind and every bind above it is rigid
    (rest scale 1: :func:`~azurik_mod.assets.skeleton.add_bone` refuses a
    scaled parent).  A body the bake doesn't map (Step 2.161e): its
    :func:`grips` row's bone, else its first root (a token's, a speck's).
    :class:`ValueError` names a body with no such bone."""
    target = Rig.read(characters_xbr, body.name)
    names = [b.name for b in target.bones]
    if body.name.casefold() in TARGETS:
        g4 = Rig.read(characters_xbr, PLAYER)
        roles = role_map(target, g4, TARGETS[body.name.casefold()])
        hand = [b.name for b in g4.bones].index("right_hand")
        k = next((t for t, g in roles.items() if g == hand), None)
        if k is None:
            raise ValueError(f"{body.name}: no bone plays garret4's right hand to hold a weapon in")
    elif (row := grips().get(body.name.casefold())) is not None:
        if row.bone not in names:
            raise ValueError(f"{body.name}: no bone {row.bone!r} (weapons.json's grips) to hold a weapon in")
        k = names.index(row.bone)
    else:
        k = next((j for j, b in enumerate(target.bones) if b.parent < 0), None)
        if k is None:
            raise ValueError(f"{body.name}: no bone to hold a weapon on")
    chain = [k, *target.ancestors(k)]
    for j, bone in enumerate(chain):
        if all(max(abs(s - 1.0) for s in target.bones[a].s) <= 1e-5 for a in chain[j:]):
            return target.bones[bone].name
    raise ValueError(f"{body.name}: every bone from {target.bones[k].name} up carries a scale, so no carrier "
                     "can hang rigidly from its hand")


def size_of(characters_xbr: bytes, body: Body) -> float:
    """A copied prop's size on ``body`` (:data:`SIZE_BAND`): its height
    over garret4's (keylord's 0.55, a child's 0.67-0.71), 1 inside the
    band."""
    k = height(characters_xbr, body) / height(characters_xbr, read_body(characters_xbr, PLAYER))
    return 1.0 if SIZE_BAND[0] <= k <= SIZE_BAND[1] else k


def _picked(characters_xbr: bytes, body: Body, mode: str, baked: bool, name: str, default: Weapon | None,
            variant, where: str) -> Loadout:
    """A weapon other than ``body``'s default (module docstring, the 2.161
    design's L3-L12 for the mapped bodies and garret4, :func:`_armed`),
    ``where`` who named it.
    :class:`ValueError` names the weapon, the body and why it can't take
    it (D35)."""
    if name == OWN:
        raise ValueError(f"{where}: {body.name} has no attack clip of its own to swing")
    found = weapons()
    if name not in found:
        raise ValueError(f"{where}: no such weapon (one of {DEFAULT}, {OWN}, {', '.join(found)})")
    w = found[name]
    where = f"{where} on {body.name}"
    if w.style.variant is not None:   # Step 2.161g (D585, D592): a recipe's moveset, on any body with clips
        return _moveset(characters_xbr, body, mode, baked, w, default, variant, where)
    if w.style.kit is None and w.style.source != PLAYER and w.style.clips is None:
        raise ValueError(f"{where}: {w.style.title} name no clips another body could swing (weapons.json: a "
                         f"kit, or {SOURCE_BUILD})")
    if w.style.clips is not None and w.style.source.casefold() not in MAPS:   # L5: the lender's rig mapped too
        raise ValueError(f"{where}: the bake doesn't map {w.style.source}'s rig (retarget.MAPS), whose own build "
                         f"{w.style.title} bake")
    if body.name == PLAYER:
        return _armed(characters_xbr, body, mode, baked, w, default, where)
    if body.name.casefold() not in MAPS:   # Step 2.161e: a creature or a token
        return _held(characters_xbr, body, mode, baked, w, default, variant, where)
    if mode == "garret4" and w.prop is None:   # Skin takes only a weapon's prop (S7): this one is the default's
        return loadout(characters_xbr, body, mode, baked, variant, default.name if default is not None else OWN)
    if w.prop is not None and w.prop.mesh is None:
        raise ValueError(f"{where}: its prop {w.prop.name} names no mesh to copy")
    hold = grip(characters_xbr, body)
    serves = mode == "own"   # L4, L5: a picked style in any Balanced build, whatever the anims rule
    kit = None
    if serves and w.style.kit is not None:
        kit = kit_style(characters_xbr, body, lend=True)
    elif serves and w.style.clips is not None:   # Step 2.161c: a source's own build (Balthazar's magic)
        kit = source_style(characters_xbr, w.style)
    hide = default is not None and default.prop is not None and default.prop.own_on == LOOSE
    return Loadout(w, w.prop, serves and w.style.source == PLAYER, kit, COPY if w.prop is not None else None, hold,
                   size_of(characters_xbr, body) if w.prop is not None else 1.0, hide, default, True,
                   "odd" if body.name.casefold() in ODD else GOOD, body.name,
                   LIFTS.get(body.name.casefold(), 0.0) if baked else 0.0,
                   turns=fit_turns(body.name, variant, w))   # W35 in Skin too: its copy rides the same g4/ clips


def _armed(characters_xbr: bytes, body: Body, mode: str, baked: bool, w: Weapon, default: Weapon,
           where: str) -> Loadout:
    """A weapon other than his Axion staff on garret4's own body (Step
    2.161d; the 2.161 design's 2.5 row garret4): his staff cut from his
    mesh in every mode (W33, :attr:`Loadout.cut`); a prop riding his
    staff chain (:data:`ON_CHAIN`: the hoe on his ``m_stafftop`` at its
    ``over``, his own clips moving it, X3's rows his own grown to its
    tip); in Balanced a prop-less weapon's style baked onto his own rig
    (bare hands' kit ``t/``, Balthazar's build ``b/``:
    :data:`~azurik_mod.assets.retarget.TARGETS_EXTRA`) with X17 forced
    (:attr:`Loadout.walls_off`); in Skin a prop-less weapon is his
    default (L3, S7).  :class:`ValueError` names a prop whose style isn't
    his own staff moves (its tip rides his held channel)."""
    if mode == "garret4" and w.prop is None:   # Skin takes only a weapon's prop (S7): this one is the default's
        return loadout(characters_xbr, body, mode, baked, None, default.name)
    if w.prop is not None and (w.prop.mesh is None or w.style.source != PLAYER or w.style.held is None):
        raise ValueError(f"{where}: its {w.prop.title} would ride his staff chain, so it needs a mesh to copy and "
                         "his own staff moves")
    kit = None
    if mode == "own" and w.style.kit is not None:
        kit = kit_style(characters_xbr, body, lend=True)
    elif mode == "own" and w.style.clips is not None:   # Step 2.161c's source build (Balthazar's magic)
        kit = source_style(characters_xbr, w.style)
    return Loadout(w, w.prop, False, kit, ON_CHAIN if w.prop is not None else None,
                   w.style.hand if w.prop is not None else None, 1.0, False, default, True, GOOD, body.name)


def _held(characters_xbr: bytes, body: Body, mode: str, baked: bool, w: Weapon, default: Weapon | None, variant,
          where: str) -> Loadout:
    """A weapon on a body the bake doesn't map (Step 2.161e; D493: every
    body offered, odd looks accepted; the 2.161 design's 2.5 rows
    creatures and tokens), which keeps its own clips: a prop copied onto
    two carriers appended under its grip (:func:`grip`: a creature's
    :func:`grips` row, else a token's or speck's root), which its clips
    carry rigidly (:data:`RIGID`), X3's box at the prop's tip in Balanced
    (:attr:`Loadout.tip`); on a clipless body, whose clips are garret4's
    as timers, the prop on a carrier of its own keyed along his staff
    (:data:`FLOAT`), X3's box around it; Balthazar's magic cast
    from a creature's grip in its own attack clips (:attr:`Loadout.cast`,
    Balanced; in Skin a prop-less weapon is the default, S7).  Step 2.204
    (D810): bare hands are a creature's own attacks, the default's build
    (the kit's clips bake only onto a rig the bake maps); the magic casts
    from a body's root where :func:`grips` has no row (an odd fit), and on
    a body with no attack clip in the clips its attack columns play
    (:func:`cast_clips`' copies, a clipless body's ``g4/`` timers).
    :class:`ValueError` names a weapon the body can't take: a prop with no
    mesh, a prop on a ``variant`` whose recipe has jiggle bones (W31
    appends the carriers after X41 reads the body's bones)."""
    if w.prop is None and (mode == "garret4" or w.style.kit is not None):   # Skin takes only a weapon's prop
        # (S7), and a creature's bare hands are its own attacks (D810): the default's build
        return loadout(characters_xbr, body, mode, baked, None, default.name if default is not None else OWN)
    if w.prop is None:
        rooted = grips().get(body.name.casefold()) is None or not attack_clips(body)   # D810: its root, its columns
        return Loadout(w, None, False, None, None, grip(characters_xbr, body), 1.0, False, default, True,
                       "odd" if rooted else LOOK, body.name, cast=source_style(characters_xbr, w.style))
    if w.prop.mesh is None:
        raise ValueError(f"{where}: its prop {w.prop.name} names no mesh to copy")
    if getattr(variant, "jiggle", None) is not None:
        raise ValueError(f"{where}: its {w.prop.title} is carried on bones appended after X41 reads the body's, and "
                         "the recipe's jiggle bones spring there: one or the other")
    k = size_of(characters_xbr, body)
    if not body.clips:
        return Loadout(w, w.prop, False, None, FLOAT, None, k, False, default, True, "odd", body.name)
    tip, hold = mode == "own", grip(characters_xbr, body)
    rig = Rig.read(characters_xbr, body.name)
    rooted = rig.bones[[b.name for b in rig.bones].index(hold)].parent < 0   # a token's or speck's: an odd fit
    return Loadout(w, w.prop, False, None, RIGID, hold, k, False, default, True,
                   "odd" if rooted else TIP_HITS if tip else LOOK, body.name, tip=tip)


def _moveset(characters_xbr: bytes, body: Body, mode: str, baked: bool, w: Weapon, default: Weapon | None,
             variant, where: str) -> Loadout:
    """A moveset weapon on a body not its recipe's own (Step 2.161g; D592,
    the owner: "Every body"; D493: odd looks accepted; the re-cut design's
    1.3): in Balanced its recipe's moveset laid over the body
    (:func:`lent`), the columns it leaves the bare-hands kit's on a body
    the bake serves (garret4's own rig too: his staff cut, X17 forced),
    else its own picks, a farmer's own hoe hidden (W33), a fit ``odd`` on
    a body the bake doesn't map and on :data:`ODD`'s; in Skin the
    default (S7: no prop), and the default on a body with no clips of its
    own too (Step 2.204, D810: a statue or token, whose every column plays
    garret4's timers; the spins on its one bone are a feature not built)."""
    if mode == "garret4" or not body.clips:   # Skin takes only a weapon's prop (S7); a clipless body's columns
        # play garret4's timers (D810): this one is the default's
        return loadout(characters_xbr, body, mode, baked, None if body.name == PLAYER else variant,
                       default.name if default is not None else OWN)
    recipe, left, s = lent(characters_xbr, body, w, variant)
    mapped = body.name.casefold() in TARGETS
    kit = kit_style(characters_xbr, body, lend=True) if mapped else None
    hide = default is not None and default.prop is not None and default.prop.own_on == LOOSE
    return Loadout(w, None, False, kit, None, None if body.name == PLAYER else _grip_or_none(characters_xbr, body),
                   s, hide, default, True, GOOD if mapped and body.name.casefold() not in ODD else "odd", body.name,
                   recipe=recipe, left=left)


def _grip_or_none(characters_xbr: bytes, body: Body) -> str | None:
    try:
        return grip(characters_xbr, body)
    except ValueError:
        return None


PORTABLE = ("t_spin", "hand_spin")
"""The generators a moveset weapon's clips play on another body (Step
2.161g, D592): each poses that body's own bind (every humanoid bind a
T-pose, its grip 0.34-0.39 of its height out: the re-cut design's M1),
so the spins keep their look; a clip of another (2.171's Blender clips,
a base clip) keeps the wearer's other pick in its columns."""


def moveset(w: Weapon | None):
    """The built-in recipe ``w``'s style plays (Step 2.161g: booblord's,
    read by name at build time, so a new recipe of hers is the weapon's
    too), else ``None``."""
    if w is None or w.style.variant is None:
        return None
    from azurkit.tools.characters._player_variants import builtins
    return builtins()[w.style.variant]


def lent(characters_xbr: bytes, body: Body, w: Weapon, variant=None) -> tuple[object, tuple[str, ...], float]:
    """D592's moveset view (Step 2.161g; the re-cut design's 1.3):
    ``w``'s recipe's moveset (:func:`moveset`) on ``body`` (``variant``
    the recipe it wears, else none), as
    :func:`~azurik_mod.patches._player_variants.lend` lays it, each of its
    :data:`PORTABLE` clips generated on the body's own rig: its box's
    centre and half extents, a hop and a planted hand's height x s, the
    body's model height over the recipe's body's (``style.body``:
    booblord's 1.739, so town_male_6's x1.081), its hand spin planted on
    the recipe's hand where the body has a bone of that name (garret4's,
    the townsfolk's, Balthazar's), else on its grip (:func:`grip`), and
    the columns playing any other clip (the wearer's other picks there).
    Returns the recipe, those columns and s."""
    from azurkit.tools.characters._player_variants import lend
    m = moveset(w)
    s = height(characters_xbr, body) / height(characters_xbr, read_body(characters_xbr, w.style.body))
    names = {n.casefold(): n for n, _ in body.bones}
    hold = _grip_or_none(characters_xbr, body)
    clips = {}
    for name, p in m.clips.items():
        if p["generator"] not in PORTABLE:
            continue
        p = {**p, "box": {k: [s * c for c in p["box"][k]] for k in ("centre", "half")}}
        if "hop" in p:
            p["hop"] = s * p["hop"]
        if p["generator"] == "hand_spin":
            hand = names.get(p["hand"].casefold(), hold)
            if hand is None:
                continue
            p.update(hand=hand, hand_z=s * p["hand_z"])
        clips[name] = p
    return lend(m, variant, body.name, clips), tuple(c for c, clip in m.columns.items() if clip not in clips), s


def attack_recipe(variant, weapon: str | None, default: str | None = None):
    """The recipe whose attack sliders and on/off rules a build of
    ``variant`` (``None``: a species) wearing ``weapon`` takes (Step
    2.161g; D585, D592: "A moveset brings its own sliders"), as
    :func:`loadout` wears it: the variant's own with its default
    (``None``, :data:`DEFAULT`, :data:`OWN`, its recipe's weapon,
    ``default``: its :func:`default_weapon`'s name, :func:`default_name`)
    or its own moveset; a moveset weapon's recipe (booblord spin's damage
    0.6, balance off, ground on); a variant's with its moveset dropped
    under any other (:func:`~azurik_mod.patches._player_variants.unarmed`:
    1.0 and the mode's rules); ``None``: a species' own."""
    from azurkit.tools.characters._player_variants import unarmed
    own = getattr(variant, "weapon", None)
    name = own if weapon in (None, DEFAULT) else weapon
    lender = moveset(weapons().get(name))
    if lender is not None:
        return variant if variant is not None and lender.name == (variant.files or variant.name) else lender
    return variant if variant is None or name in (None, DEFAULT, OWN, own, default) else unarmed(variant)


def default_name(iso, variant) -> str | None:
    """The name of ``variant``'s :func:`default_weapon` on its base's body
    in the image ``iso`` (``None``: its own attacks), the pick
    :func:`attack_recipe` takes as no pick (the 2.161g review's 1:
    ``--player-weapon balthazar_magic`` on beamlord builds his default)."""
    from azurkit.tools.characters.gltf import resolve_body
    from azurkit.tools.characters.ports import IsoStaging

    game = IsoStaging(Path(iso))
    characters = game.stored("characters.xbr")
    body, _ = resolve_body(characters, game.stored("config.xbr"), variant.base)
    w = default_weapon(characters, read_body(characters, body), variant)
    return None if w is None else w.name


def offers(characters_xbr: bytes, body: Body, mode: str = "own", variant=None) -> dict[str, tuple[str, str]]:
    """What ``body`` (wearing ``variant``, if any) takes in gameplay ``mode`` (the GUI's "Weapon:" box,
    ``player-models --weapons``): each weapon name -> (``default``, a
    fit (:data:`FIT_COLOURS`), ``refused`` or ``same``: it builds the
    default) and why, :data:`OWN` first where the body has attacks of its
    own, a variant's own moveset first (Step 2.161g).  Since Step 2.204
    (D809, D810) every weapon builds on every body the census read, a
    ``same`` naming why it builds the default (:func:`same_why`)."""
    out = {}
    own = default_weapon(characters_xbr, body, variant) if variant is not None else None
    first = [own.name] if own is not None and own.style.variant is not None else []
    names = ([OWN] if attack_clips(body) and body.name != PLAYER else []) + first + [
        n for n in weapons() if n not in first]
    for name in names:
        try:
            lo = loadout(characters_xbr, body, mode, True, variant, name)
        except ValueError as exc:
            out[name] = ("refused", str(exc))
            continue
        if not lo.picked:
            out[name] = (DEFAULT, describe(lo, body)) if lo.name == name else ("same", same_why(body, mode, name))
        else:
            out[name] = (lo.fit, ODD.get(body.name.casefold(), describe(lo, body)))
    return out


def same_why(body: Body, mode: str, name: str) -> str:
    """Why weapon ``name`` builds ``body``'s default in ``mode`` (an offer
    ``same``, Step 2.204): Skin takes only a weapon's prop (S7); bare hands
    on a body the bake doesn't map are its own attacks; a body with no
    clips plays garret4's timers in every column; its own attacks are its
    default (Balthazar's own build)."""
    w = weapons().get(name)
    if w is None:
        return "the default's build: its default is its own attacks"
    if mode == "garret4" and w.prop is None:
        return "the default's build: Skin takes only a weapon's prop"
    if not body.clips:
        return "the default's build: a body with no clips plays garret4's moves in every column"
    if w.style.kit is not None and body.name.casefold() not in MAPS:
        return "the default's build: its own attacks are its bare hands"
    return "the default's build"


FIT_COLOURS = {GOOD: "green", "odd": "yellow", TIP_HITS: "yellow", LOOK: "yellow"}
"""An unseen pick's colour by its offline fit (Step 2.204; D809, the owner:
"we can use green yellow red, and it is fine to not test them"; D810):
green for a weapon a mapped body swings as designed, yellow for an odd
look, a creature's prop or cast; no better than the body's own grade
(:func:`pick_grade`'s ``own``)."""
NOT_SEEN = "not seen in game"
"""How :func:`pick_grade` names an unseen pick coloured by its fit (D810)."""
_RANK = ("green", "yellow", "red")


WEAPON_GRADES: dict[tuple[str, str, str, str], tuple[str, str]] = load_grades(
    WEAPONS_FILE.parent / "weapon_grades.json", ("name", "mode", "weapon", "sha"))
"""Each picked weapon's grade by (species or variant, mode, weapon, its
:func:`pick_sha`), from the xemu sittings (the 2.161 design's 2.7; sitting W-A's
eight, 2.161b2's X44 rows and its air elemental, 2.161c's magic on
town_male_6, the fire elemental and keylord, 2.161d's garret4 with the
hoe, bare hands and the magic, 2.161e's eight creatures and tokens,
2.161g's W-G: booblord with the Axion staff and the hoe, town_male_6 with
the Axion staff (in Skin too) and Booblord spin, garret4 with the hoe and
Booblord spin, the catalisk with Booblord spin; Balanced at the body's
own size, x1, unless the key says Skin; Step 2.161g's W35 rebuilt
keylord's Axion staff and Balthazar's, town_child_1's and
town_female_1's hoe, whose grades are gone until a sitting sees them;
booblord's two, 7f7dd50780e6 and 8eb490316891, went with her v3 shape:
her v4 with a weapon is unseen, Step 2.154, D631; her v4's recipe sha
moved Booblord spin's on town_male_6, the catalisk and garret4, whose
builds are byte for byte main's, so their grades moved with it, and so
did her sash's springs, Step 2.169b: a moveset lends no jiggle, and the
G3 cases of town_male_6 and the catalisk stayed main's; 2.204's
Balthazar's magic on seven bodies main refused it on, frag_fire_1's red
its model's own).
A default build keeps the
species' or variant's own grade; a grade colours the build's status line,
the GUI's picker and its Weapon box (:func:`pick_grade`) and never gates
the logic.  One grade a line in ``assets/weapon_grades.json`` (Step X.85;
:mod:`azurik_mod.assets.grades`)."""


def seen(size: str, model_scale: float, variant=None, sliders: tuple[float, float, float] | None = None) -> bool:
    """Whether a build is one a weapon's sitting built (D242): a species
    at its own ``size`` (``own``) drawn x1; a ``variant`` built in, at its
    recipe's scale and attack sliders (``model_scale`` and ``sliders``,
    reach, damage and speed, as the build takes them; ``None`` the
    recipe's), as ``variants.status`` grades one."""
    if variant is None:
        return size == "own" and model_scale == 1.0
    own = (variant.scale, variant.reach, variant.damage, variant.speed)
    return variant.source == "built-in" and (model_scale, *(sliders or own[1:])) == own


def pick_sha(w: Weapon, body: str | None = None, turns: dict | None = None) -> str:
    """The sha a grade of ``w`` worn by ``body`` is keyed by
    (:data:`WEAPON_GRADES`): :attr:`Weapon.sha`; on a body with a
    :func:`grips` row (Step 2.161e: its bone, turn and offset place a
    rigid prop, so its tip's box and reach, and a cast's origin) sha256[:12]
    of that and the row, so a retuned grip is a build no sitting saw; a
    moveset weapon's (Step 2.161g) with its recipe's sha too, so a new
    recipe of hers is a build no sitting saw (D242), and with W35's
    ``turns`` (:func:`fit_turns`) a refit one."""
    row = grips().get(body.casefold()) if body else None
    lender = moveset(w)
    if row is None and lender is None and not turns:
        return w.sha
    doc = [w.sha] + ([row.bone, list(row.turn), list(row.offset)] if row is not None else []) + (
        [lender.sha] if lender is not None else []) + ([sorted([c, list(t)] for c, t in turns.items())]
                                                       if turns else [])
    return hashlib.sha256(json.dumps(doc, separators=(",", ":")).encode()).hexdigest()[:12]


def pick_grade(name: str, mode: str, weapon: str | None, built: bool = True, body: str | None = None,
               fit: str | None = None, own: tuple[str, str] | None = None) -> tuple[str, str] | None:
    """A picked ``weapon``'s grade (:data:`WEAPON_GRADES`) on ``name``, a
    species or a variant, wearing ``body``, in ``mode``: the one lookup the
    build's status line (:func:`grade`) and the GUI's picker and Weapon box
    read; where no sitting has graded it or the build isn't the one its
    sitting built (``built`` false, :func:`seen`; its grip retuned,
    :func:`pick_sha`) its ``fit``'s colour (:data:`FIT_COLOURS`, Step
    2.204, D810), no better than ``own`` (the model's own status, its
    colour and note, where a sitting gave it one), its note
    :data:`NOT_SEEN`, else ``unseen`` (no fit given); on an untested model
    (``_player_character.UNTESTED``, red "untested") ``unseen`` noted
    :data:`NOT_SEEN`, grey as the picker shows the model (AZ-807, D830);
    ``None`` for no pick (``None``, :data:`DEFAULT`)."""
    if weapon in (None, DEFAULT):
        return None
    from azurkit.tools.characters._player_character import UNTESTED
    from azurkit.tools.characters._player_variants import builtins
    w = weapons().get(weapon)
    turns = fit_turns(body, builtins().get(name), w)   # W35, every mode's
    sha, title = (pick_sha(w, body, turns), w.title) if w is not None else (OWN, weapon)
    graded = WEAPON_GRADES.get((name, mode, weapon, sha)) if built else None
    if graded is not None:
        return graded
    why = (f"no sitting has graded {name} with {title} at another size or scale (D242)" if not built else
           f"no sitting has graded {name} with {title} (weapon {sha}, D242)")
    if own == UNTESTED:   # AZ-807: as unseen as the model it's on
        return "unseen", f"{NOT_SEEN}: {why}; the model untested"
    if fit not in FIT_COLOURS:
        return "unseen", why
    own = own[0] if own else None
    colour = max(FIT_COLOURS[fit], own if own in _RANK else "green", key=_RANK.index)
    return colour, f"{NOT_SEEN}: {why}; its fit {fit}" + (f", the model {own}" if colour == own != FIT_COLOURS[fit]
                                                           else "")


def grade(species: str, mode: str, lo: Loadout, built: bool = True,
          own: tuple[str, str] | None = None) -> tuple[str, str] | None:
    """``lo``'s grade on ``species`` (or a variant) in ``mode``
    (:func:`pick_grade`, by its fit, no better than ``own``; ``built``:
    :func:`seen`); ``None`` for a default."""
    return pick_grade(species, mode, lo.name, built, lo.body, lo.fit, own) if lo.picked else None


def describe(lo: Loadout, body: Body) -> str:
    """What a build of ``body`` makes of ``lo``'s weapon, in words
    (``player-models --weapons``): its own attacks; its own (garret4's
    staff, Balthazar's build); the prop it carries and the style it
    swings; or none of it (a style a mode doesn't apply, L4)."""
    w = lo.weapon
    if w is None:
        return "its own attacks"
    if not lo.picked and body.name in (w.style.source, w.prop.own_on if w.prop else None):
        return "its own"
    parts = []
    if w.style.variant is not None:   # Step 2.161g (D585, D592)
        parts.append(f"{w.style.title} in {len(lo.recipe.columns)} columns, generated on its own rig (W22)"
                     + (f", its {', '.join(lo.left)} its other picks" if lo.left else "") if lo.lent
                     else f"{w.style.title} in its recipe's columns (W22)")
    if lo.carry == IN_PLACE:
        parts.append(f"its {lo.prop.clip} carried along {lo.weapon.style.source}'s staff")
    elif lo.carry == ON_CHAIN:   # Step 2.161d: garret4's own staff chain
        parts.append(f"the {lo.prop.title} on his staff chain ({lo.weapon.style.held[0]}), swung with his own "
                     "attacks, X3's box around it")
    elif lo.carry == COPY:
        parts.append(f"the {lo.prop.title} copied into its {lo.grip} (W31, W32{f', x{lo.k:.2f}' if lo.k != 1 else ''})"
                     + (", its own hoe hidden (W33)" if lo.hide else ""))
    elif lo.carry == RIGID:   # Step 2.161e
        parts.append(f"the {lo.prop.title} copied rigidly into its {lo.grip} (W31, W32"
                     f"{f', x{lo.k:.2f}' if lo.k != 1 else ''}), swung with its own attacks"
                     + (", X3's box at its tip in place of its own" if lo.tip else ", a look only"))
    elif lo.carry == FLOAT:   # Step 2.161e
        parts.append(f"the {lo.prop.title} on a floating carrier swung along garret4's staff beside it (W31, W32"
                     f"{f', x{lo.k:.2f}' if lo.k != 1 else ''}), X3's box around it")
    elif lo.hide:
        parts.append("its own hoe hidden (W33)")
    if lo.cast is not None:   # Step 2.161e; Step 2.204 (D810): a body with no attack clip, in its columns' clips
        parts.append(f"{lo.cast.source}'s lightning cast from its {lo.grip} in "
                     + ("its own attack clips' damage windows" if attack_clips(body) else
                        "copies of the clips its attack columns play, X3's windows" if body.clips else
                        "garret4's timers its attack columns play, his windows")
                     + ", his graph the player's clone (W34), its own hits")
    if lo.borrowing:
        parts.append(f"{lo.weapon.style.source}'s own attacks baked onto its rig (g4/)"
                     + (", X3's box around its prop" if lo.reaching else ""))
    if lo.kit is not None and lo.kit.own is not None:   # Step 2.161c
        parts.append(f"{lo.kit.source}'s own attacks baked onto its rig ({lo.kit.dir}), X3 his own boxes (Step 2.195b)"
                     + (", his graph the player's clone of it, his markers grown and ridden on its hand (W34)"
                        if lo.kit.fx is not None else ""))
    elif lo.kit is not None:
        parts.append(f"the kit's clips baked onto its rig ({lo.kit.dir}), X3 at the fist or foot each strikes with "
                     "(Step 2.195)")
    if lo.cut:
        parts.append("his staff cut from his mesh (W33)" + (", X17 off its wall check" if lo.walls_off else ""))
    if lo.recipe is not None and not lo.lent:   # D585
        parts.append("its recipe's own moves dropped")
    return "; ".join(parts) or "not in this build: its style is Balanced's, on a body the bake serves"


# --- W26: a held prop rides garret4's staff (Step 2.134b; D337-D339; W20's place, Step 2.106) ---
PROP_FAR = 1.0
"""How far (m, the median of its vertices) from the body's root bone a
group skinned to that bone alone lies to be a loose prop (W26): the
farmers' hoe 1.25 m; the root-skinned parts of every other body that
has the prop's clip none."""
PROP_GRIP = 1.6
"""How far (m) along the prop from its blade end the right hand holds it
(D115's default, Step 2.106): the hoe's ``over`` puts that point at the
right hand's mean grip on garret4's staff."""
PROP_HANDLE = 0.45
"""How far (m) from its blade end the prop's handle starts: its centre
line is its vertices' mean x and z beyond that."""
HELD_SAMPLES = 40
"""How many steps W26 samples an attack window in for the prop's tip
(:func:`held_window`)."""
FLOOR_CLEAR = 0.02
"""How far over the floor (model units, metres at x1) W41 keeps a held
prop's lowest point (Step 2.207, AZ-784; D115's default: under the 7 cm
garret4's own staff keeps in his 360_ledge)."""
FLOORLESS = ("climb", "hoist", "hang", "jump", "superjump", "step_up", "swim", "drowning", "dive")
"""The clips W41 leaves as they are, by name: those garret4 plays off the
floor, his ladder, ledge, hang and jump moves (every clip of his keying
``m_feet``'s height, whose floor is a ledge's top or none) and the
water's (Step 2.207)."""
LIFT_STEP = 1.0
"""W41's search step (degrees), refined by halving (:func:`_floor_lift`)."""

SLIDE_RAMP = 0.3
"""How far under the floor (drawn metres, as :data:`FLOOR_CLEAR`) the
higher of a held prop's hand and arm (:data:`ARM_UP`) takes W41's slide
from whole to none (Step 2.207b, the review's F2: a hard gate 1 mm under
dropped the golem's hoe 0.40 m in a tick; offline at 0.3 its cast's step
is 0.02 m past main's, and keylord's roll never takes the whole hoe under,
main's 3 ticks)."""
ARM_UP = 2
"""How many bones up from a held prop's grip the point is whose height
gates W41's slide (Step 2.207c, AZ-800): a humanoid's upper arm, its
shoulder.  Gated by the hand itself (Step 2.207b), a hoe stayed with a
hand the bake puts into the floor while the body stands over it (the
golem's long arms in garret4's casts, keylord's roll, the catalisk's
claw); a body that sinks (magmar, the water tentacles) takes its
shoulder under too, and the prop with it.  The higher of the two gates
it (the skeptic's sitting): a tentacle's chain hangs its point 2 up
under its hand (water_tentacle1's attack_lr 36 -> 64 ticks under, magmar's
die 44 -> 46, with the arm alone)."""


def loose_props(characters_xbr: bytes, body: Body, prop: Prop) -> tuple[MeshGroup, ...]:
    """W26's groups (Step 2.106, AZ-491; W20's until Step 2.134b): on a body with
    ``prop``'s clip, every mesh group of every LOD skinned to its root
    bone alone whose vertices lie a median of more than :data:`PROP_FAR`
    from it: the six townsmen farmers' hoe (and ``male_farmer_0_base``'s,
    which no species wears), a group of 276 vertices on ``root_joint``
    that every clip carries rigidly with the pelvis, 1.16 m to the right
    of the model."""
    if prop.clip not in body.clips or not body.bones:
        return ()
    root = body.bones[0][1]
    out = []
    for group in mesh_groups(characters_xbr, body.name):
        if group.bones != (0,) or not group.count:
            continue
        far = statistics.median(math.dist(struct.unpack_from("<3f", characters_xbr, group.vertices + VERTEX_SIZE * j),
                                          root) for j in range(group.count))
        if far > PROP_FAR:
            out.append(group)
    return tuple(out)


def carriers(rig: Rig, held: Carriers | None) -> frozenset[int]:
    """The bones of ``rig`` a carried prop rides (``held``, the
    :class:`Loadout`'s: its carrier bones hung from its hand): they draw
    a prop, so the measures of the body's own pose (``hang_top``,
    ``pose_top``, ``hold_plan``) leave them out, as before W26, when its
    tip was no bone; none for ``None``.  A floating carrier (``hand``
    ``None``, Step 2.161e) is a root."""
    out: set[int] = set()
    if held is None:
        return frozenset()
    for k, b in enumerate(rig.bones):
        if b.name in held.bones and (b.parent in out or (rig.bones[b.parent].name == held.hand if b.parent >= 0
                                                         else held.hand is None)):
            out.add(k)
    return frozenset(out)


def _frames(rig: Rig, keyed: dict[tuple[int, int], tuple], targets, t: float) -> tuple[dict, dict]:
    """The engine model (:func:`~azurik_mod.assets.retarget.pose`,
    :func:`~azurik_mod.assets.retarget.origins`) on ``targets``' chains
    alone: each chain bone's world rotation and origin when a clip whose
    tracks are ``keyed`` ({(bone, comp): keys}) plays on ``rig`` at ``t``."""
    rot: dict[int, tuple] = {}
    at: dict[int, tuple] = {}
    for j in sorted({k for b in targets for k in (b, *rig.ancestors(b))}):
        b = rig.bones[j]
        q = qnorm(tuple(evaluate(keyed[j, 3 + c], t) if (j, 3 + c) in keyed else b.q[c] for c in range(4)))
        local = tuple(evaluate(keyed[j, c], t) if (j, c) in keyed else b.t[c] for c in range(3))
        r = qmul(qmul(b.jo, q), b.ra)
        if b.parent < 0:
            rot[j], at[j] = r, local
        else:
            rot[j] = qmul(rot[b.parent], r)
            at[j] = tuple(p + d for p, d in zip(at[b.parent], _turn(rot[b.parent], local)))
    return rot, at


def _keyed(clip: Clip) -> dict[tuple[int, int], tuple]:
    return {(tr.target, tr.comp): tr.keys for tr in clip.bones}


def _tip(rot: dict, at: dict, top: int, bottom: int, over: float) -> tuple[tuple[float, float, float], tuple]:
    """The style's held channel in a pose (:func:`_frames`): the prop's
    blade tip, ``over`` past the channel's top along its axis, and the
    top's world rotation."""
    axis = [a - b for a, b in zip(at[top], at[bottom])]
    n = math.sqrt(sum(c * c for c in axis))
    return tuple(a + over * c / n for a, c in zip(at[top], axis)), rot[top]


def _staff_hold(characters_xbr: bytes, style: WeaponStyle, over: float) -> tuple[Rig, int, int, tuple, tuple]:
    """The style source's rig (garret4's), its held channel's top and
    bottom bones, K (his idle's t 0 ``m_stafftop`` turn to his right
    hand's: a W26 carrier at its rest turn there turns with the staff as
    K after it) and the carrier's rest translation, the prop's tip
    (``over`` past the top) in his right hand's frame at that t 0."""
    g4 = Rig.read(characters_xbr, style.source)
    names = [b.name for b in g4.bones]
    top, bottom, hand = (names.index(n) for n in (*style.held, style.hand))
    rot, at = _frames(g4, _keyed(named_clip(characters_xbr, style.source, "idle")), (top, bottom, hand), 0.0)
    tip, staff = _tip(rot, at, top, bottom, over)
    return (g4, top, bottom, qmul(qinv(staff), rot[hand]),
            _turn(qinv(rot[hand]), [a - b for a, b in zip(tip, at[hand])]))


def carried(characters_xbr: bytes, body: Body, lo: Loadout):
    """W26's tracks (Step 2.134b; D337, the owner on the farmers' hoe:
    "would it be possible to make it look like they are using it
    visually, like how garret uses his axion?"): for
    :func:`~azurik_mod.assets.retarget.bake_body`'s ``post``, garret4's
    clip baked onto ``body`` with ``lo``'s prop's first carrier keyed so
    that, under its new parent (the prop's hand), it sits where the
    prop's blade tip rides garret4's staff (:func:`_tip`) and turns as his
    ``m_stafftop`` does after K (:func:`_staff_hold`): local q = H^-1 S K,
    local T = H^-1 (tip - hand), H and hand garret4's right hand (the
    body's baked hand turns as his within 0.054 degrees, so the prop rides
    the hand wherever the bake puts it: a roll centred at drawn != 1 moves
    the body's hand by (1 - 1/D) x his m_feet, not his tip; the judge's
    A1) and S his staff top's turn (the frame, not an aim at the axis,
    which turns end over end in attack_10, 14 and 15), sampled at
    :data:`~azurik_mod.assets.retarget.SAMPLE_HZ` and at the key times of
    his staff and hand chains, one-sided slopes, the quaternion's sign
    kept continuous (as the bake's folded bones)."""
    style, prop = lo.weapon.style, lo.prop
    g4, top, bottom, k_turn, _ = _staff_hold(characters_xbr, style, prop.over)
    hand = [b.name for b in g4.bones].index(style.hand)
    carrier = [n for n, _ in body.bones].index(prop.own_carriers[0])
    chain = {top, bottom, hand, *g4.ancestors(top), *g4.ancestors(bottom), *g4.ancestors(hand)}
    rig = Rig.read(characters_xbr, body.name)
    held = [b.name for b in rig.bones].index(prop.hand)
    hull, long = _prop_hull(characters_xbr, prop)

    def post(name: str, source: Clip, baked: Clip) -> Clip:
        his, mine, length = _keyed(source), _keyed(baked), baked.length
        floored = floor_kept(name)

        def at(t: float, ref: tuple | None) -> tuple[tuple, tuple]:
            rot, pos = _frames(g4, his, (top, bottom, hand), t)
            tip, staff = _tip(rot, pos, top, bottom, prop.over)
            turn = qmul(staff, k_turn)
            if floored:   # W41 (Step 2.207): the body's hand holds his hand's point as it turns
                w_rot, w_pos = _frames(rig, mine, (held,), t)
                up, floor = _up_and_floor(pos[hand], 1.0, w_pos[held], qmul(w_rot[held], qinv(rot[hand])))
                tip, turn = _lifted(_floor_lift(tip, turn, pos[hand], hull, long, up, floor), tip, turn)
            h = qinv(rot[hand])
            q = qnorm(qmul(h, turn))
            if ref is not None and sum(x * y for x, y in zip(q, ref)) < 0:
                q = tuple(-x for x in q)
            return _turn(h, [a - b for a, b in zip(tip, pos[hand])]), q
        known = {0.0, length} | {key[0] for (b, _), keys in his.items() if b in chain for key in keys
                                 if 0.0 <= key[0] <= length}
        tracks = _sampled_track(carrier, length, known, at)
        return replace(baked, bones=tuple(sorted((*baked.bones, *tracks), key=lambda tr: (tr.target, tr.comp))))
    return post


def carry_props(characters: bytearray, body: Body, lo: Loadout) -> int:
    """W26 on ``body``'s rig and mesh in ``characters`` (``characters.xbr``,
    edited in place; Step 2.134b, superseding W20's two-handed grip, which
    turned the prop 132-144 degrees in the hand at every cut between the
    body's own idle and a baked clip): ``lo``'s prop's first carrier
    becomes a child of the prop's hand at its rest the prop's tip in
    garret4's right hand at his idle's t 0 (:func:`_staff_hold`; joint
    orient, rotate axis and rotation the identity), its second a child of
    it at the prop's handle end (its length along the carrier's -y), each
    inverse bind (+0x60) its new bind's; each of its :func:`loose_props`
    (the hoe, along the model's y, its blade end the lowest) is skinned to
    the carrier (its one bone entry) and turned a half turn about x and
    moved, its positions and normals, so its blade tip (the handle's
    centre line, its vertices' mean x and z past :data:`PROP_HANDLE`, at
    the blade end) is the carrier's origin and its handle runs down the
    carrier's -y.  The body's own clips key neither bone, so there the
    prop rides the hand as garret4 holds his staff at rest; each baked
    clip keys the carrier along his staff (:func:`carried`).  Its blend
    weights and every other group are kept.  Returns how many groups it
    rewrote.  :class:`ValueError` names why one can't be carried (D35): a
    bone it needs missing or out of order, or a prop whose longest side
    isn't along y."""
    prop = lo.prop
    props = loose_props(bytes(characters), body, prop)
    if not props:
        return 0
    names = [name for name, _ in body.bones]
    missing = [n for n in (prop.hand, *prop.own_carriers) if n not in names]
    if missing:
        raise ValueError(f"W26: body {body.name!r} has no {', '.join(missing)} to carry its prop on")
    hand, carrier, end = (names.index(n) for n in (prop.hand, *prop.own_carriers))
    if not hand < carrier < end:
        raise ValueError(f"W26: body {body.name!r}'s {prop.hand}, {prop.own_carriers[0]} and {prop.own_carriers[1]} "
                         "aren't in parent-first order")
    first = props[0]
    points = [struct.unpack_from("<3f", characters, first.vertices + VERTEX_SIZE * j) for j in range(first.count)]
    length = max(p[1] for p in points) - min(p[1] for p in points)
    rest = _staff_hold(bytes(characters), lo.weapon.style, prop.over)[4]
    _, table = body_at(bytes(characters), body.name)
    table += 4 + struct.unpack_from("<i", characters, table + 4)[0]
    hand_bind = struct.unpack_from("<16f", characters, table + 160 * hand + 0x60)
    turn = [[hand_bind[4 * i + j] for j in range(3)] for i in range(3)]   # v = o + R x local
    origin = dict(body.bones)[prop.hand]
    placed = []
    for bone, parent, t in ((carrier, hand, rest), (end, carrier, (0.0, -length, 0.0))):
        rec = table + 160 * bone
        struct.pack_into("<h", characters, rec + 8, parent)
        struct.pack_into("<4f4f3f4f3f", characters, rec + 0x10, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, *t,
                         0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0)
        origin = tuple(o + sum(turn[i][j] * t[j] for j in range(3)) for i, o in enumerate(origin))
        bind = list(hand_bind)
        bind[12:15] = (-sum(origin[i] * turn[i][j] for i in range(3)) for j in range(3))
        struct.pack_into("<16f", characters, rec + 0x60, *bind)
        placed.append(origin)
    tip_at = placed[0]
    for group in props:
        cells = [group.vertices + VERTEX_SIZE * j for j in range(group.count)]
        points = [struct.unpack_from("<3f", characters, c) for c in cells]
        spans = [max(p[k] for p in points) - min(p[k] for p in points) for k in range(3)]
        if spans[1] < max(spans[0], spans[2]):
            raise ValueError(f"W26: body {body.name!r}'s prop (LOD {group.lod}, group {group.index}) "
                             "doesn't lie along the model's y")
        blade = min(p[1] for p in points)
        handle = [p for p in points if p[1] > blade + PROP_HANDLE]
        tip = (statistics.fmean(p[0] for p in handle), blade, statistics.fmean(p[2] for p in handle))

        def model(v) -> tuple[float, float, float]:   # carrier-local v (a half turn about x) into the model
            return tuple(sum(turn[i][j] * v[j] for j in range(3)) for i in range(3))
        for c, p in zip(cells, points):
            local = (p[0] - tip[0], tip[1] - p[1], tip[2] - p[2])
            struct.pack_into("<3f", characters, c, *(a + b for a, b in zip(tip_at, model(local))))
            n = struct.unpack_from("<3f", characters, c + 28)
            struct.pack_into("<3f", characters, c + 28, *model((n[0], -n[1], -n[2])))
        struct.pack_into("<i", characters, group.bones_at, carrier)
    return len(props)


def held_window(characters_xbr: bytes, clip: str, drawn: float, lo: Loadout) -> DamageWindow | None:
    """X3's row for a column swinging garret4's ``clip`` with ``lo``'s
    held prop (W26, Step 2.134b; the 2.195b design, D767, the owner:
    "tune each weapon": the Axion staff medium, the farmer's hoe long; D339:
    "as long reach as it looks like the hoe should have"): garret4's own
    window for ``clip``
    (:func:`~azurik_mod.patches._player_damage_marker.garret4_window`), its
    box the one bounding the prop through it, its blade tip and its
    handle's end (:func:`_prop_points`, :data:`HELD_SAMPLES` steps) grown
    its pad every way (:attr:`Loadout.size`: its mesh's farthest vertex
    from that line, x :attr:`Loadout.k`), drawn ``drawn`` times, metres from the
    feet: the staff strikes with either end, the hoe out to its blade; its
    handle's end taken at least as far down his staff as the Axion staff's
    bottom end, his ``m_staffbottom`` (the hoe's stops 0.41 short of it, so
    its basic2, attack_9's butt stroke, fell short of the staff's: Step
    2.195b's skeptic 2; D767: the hoe long);
    its height his box's (at the prop's size, x k and drawn) and the prop's
    both (his waist-high thrust's box reaches the floor, so the prop's
    meets a small enemy as his does, X13's fill or not); its reach that box's corner, its near the nearest any
    one sample's box comes.  In his back kick (:data:`PROP_KICKS`: his
    foot strikes, behind him, not the prop) and on his own staff chain
    (:data:`ON_CHAIN`: garret4 holding another prop, never short of his own
    staff's reach) also his own box x k x drawn.  In his three elemental casts (:data:`PROP_CASTS`, magic) his own
    box grown to hold the tip, his near (Step 2.134b's row).  ``None``
    where he has none (the roll).  A copied prop's points are where the
    wearer's own baked hand carries it (:func:`_worn_tips`, Step 2.161b:
    the twin, F-C)."""
    w = garret4_window(characters_xbr, read_body(characters_xbr, lo.weapon.style.source), clip)
    if w is None:
        return None
    tips = _prop_points(characters_xbr, clip, w, lo, drawn, 0.0)
    if clip in PROP_CASTS:
        low, high = list(w.low), list(w.high)
        for tip in tips:
            low = [min(a, drawn * b) for a, b in zip(low, tip)]
            high = [max(a, drawn * b) for a, b in zip(high, tip)]
        return DamageWindow(w.marker, w.on, w.off, tuple(low), tuple(high),
                            max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1])), w.near)
    length, pad = lo.size
    g4, top, bottom, _, _ = _staff_hold(characters_xbr, lo.weapon.style, lo.prop.over)
    staff = math.dist(g4.positions[top], g4.positions[bottom])   # the Axion staff's: his top to his bottom
    ends = _prop_points(characters_xbr, clip, w, lo, drawn, max(length, lo.prop.over + staff))
    boxes = [tuple(tuple(drawn * (f(a[c], b[c]) + s * pad * lo.k) for c in range(3)) for f, s in ((min, -1), (max, 1)))
             for a, b in zip(tips, ends)]
    near_m = min(near(*box) for box in boxes)
    if clip in PROP_KICKS or lo.carry == ON_CHAIN:
        boxes.append((tuple(drawn * lo.k * c for c in w.low), tuple(drawn * lo.k * c for c in w.high)))
        near_m = min(near_m, drawn * lo.k * w.near)
    low = (*(min(box[0][c] for box in boxes) for c in range(2)),
           min(drawn * lo.k * w.low[2], *(box[0][2] for box in boxes)))
    high = (*(max(box[1][c] for box in boxes) for c in range(2)),
            max(drawn * lo.k * w.high[2], *(box[1][2] for box in boxes)))
    return DamageWindow(w.marker, w.on, w.off, low, high,
                        max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1])), near_m)


PROP_CASTS = frozenset({"elemental_attack", "elemental_attack_2", "elemental_attack_3"})
"""garret4's elemental casts, the vanilla clips of the ``attacks_anims``
columns elemental1-3 (``_player_character.CASTS``): magic his staff casts,
not a hit with it, so a held prop leaves their boxes his own, grown to its
tip (:func:`held_window`)."""
PROP_KICKS = frozenset({"attack_back_kick"})
"""garret4's back kick, the vanilla clip of the ``attacks_anims`` column
back2: his foot strikes behind him, not the prop, so a held prop's box
there is his own x k x drawn as well (Step 2.195b's review 1: the prop's
alone reached 0.25-0.42 m behind the feet, short of W19's contact front,
where his own reaches 1.38: :func:`held_window`)."""


def prop_size(characters_xbr: bytes, prop: Prop) -> tuple[float, float]:
    """``prop``'s length, its blade tip to its handle's end (:func:`_donor`),
    and its pad, how far its mesh's farthest vertex lies from that line
    (model units at garret4's size; Step 2.195b): the Axion staff 1.55 and
    0.03 (a thin shaft), the hoe 1.88 and 0.14 (its blade)."""
    verts, _, _, length = _donor(characters_xbr, prop)
    if prop.mesh.loose:   # the tip the origin, the handle down -y (W26's turn)
        axis = (0.0, -1.0, 0.0)
    else:   # the staff in his m_stafftop's frame, toward m_staffbottom
        g4 = Rig.read(characters_xbr, prop.mesh.body)
        names = [b.name for b in g4.bones]
        top, bottom = (names.index(n) for n in prop.carriers)
        axis = _turn(qinv(g4.world[top]), [b - a for a, b in zip(g4.positions[top], g4.positions[bottom])])
    n = math.sqrt(sum(c * c for c in axis))
    axis = tuple(c / n for c in axis)
    return length, max(math.dist(p, tuple(min(max(sum(a * b for a, b in zip(p, axis)), 0.0), length) * c
                                          for c in axis)) for p, *_ in verts)


def _prop_points(characters_xbr: bytes, clip: str, w: DamageWindow, lo: Loadout, drawn: float,
                 back: float) -> tuple[tuple, ...]:
    """The point ``back`` model units along ``lo``'s prop from its blade tip
    (0: the tip; its length: its handle's end), :data:`HELD_SAMPLES` steps
    over ``w`` in garret4's ``clip``, where the build carries it (model
    units): a copy in the wearer's baked hand (:func:`_worn_tips`), else (W26
    in place, his staff chain) along his staff (:func:`_tip`), each less
    (1 - 1/D) x his horizontal ``m_feet`` there in a lunge the build draws
    about the centre at ``drawn`` (:func:`~azurik_mod.assets.retarget.centred`,
    Step 2.175, AZ-623: up to 0.14 m at x1.15); a floating carrier where
    :func:`float_clips` keys it."""
    style, over = lo.weapon.style, lo.prop.over - back
    g4, top, bottom, _, _ = _staff_hold(characters_xbr, style, lo.prop.over)
    source = named_clip(characters_xbr, style.source, clip)
    keyed = _keyed(source)
    times = [w.on + (w.off - w.on) * s / HELD_SAMPLES for s in range(HELD_SAMPLES + 1)]
    if lo.carry == FLOAT:   # Step 2.161e: where the floating carrier is keyed (:func:`float_clips`)
        feet = _feet(g4, source)
        return tuple(_floated_at(g4, keyed, feet, top, bottom, over, lo.k, drawn, t)[0] for t in times)
    points = (_worn_tips(characters_xbr, clip, w, lo, back) if lo.carry == COPY
              else [_tip(*_frames(g4, keyed, (top, bottom), t), top, bottom, over)[0] for t in times])
    at = next((i for i, m in enumerate(g4.markers) if m.casefold() == "m_feet"), -1)
    lead = {tr.comp: tr.keys for tr in source.markers if tr.target == at and tr.comp in (0, 1)}
    lunge = any(key[1] != keys[0][1] for keys in lead.values() for key in keys)   # moves_root's test
    c = 1.0 - 1.0 / drawn if lunge and drawn and math.isfinite(drawn) else 0.0
    return tuple(tuple(p[i] - c * evaluate(lead[i], t) if i in lead else p[i] for i in range(3))
                 for p, t in zip(points, times))


# --- W31-W33: a picked weapon's prop copied onto the wearer (Step 2.161b; D492-D495) ---
def _worn_tips(characters_xbr: bytes, clip: str, w: DamageWindow, lo: Loadout, back: float = 0.0
               ) -> tuple[tuple, ...]:
    """A copied prop's blade tip, or the point ``back`` model units along
    it from there (:func:`_prop_points`), over ``w`` (:data:`HELD_SAMPLES`
    steps) in garret4's ``clip`` baked onto ``lo``'s body (model units):
    the wearer's grip in the bake (``Retarget`` at :attr:`Loadout.lift`, as
    :func:`~azurik_mod.assets.retarget.bake_body` bakes it) plus garret4's
    hand-to-point offset times :attr:`Loadout.k`, where :func:`carried_copy` keys
    the tip carrier, carried rigidly with its arm by W35's turn in a fitted
    clip (:attr:`Loadout.turns`); each clip and point once a build (:attr:`Loadout.tips`)."""
    from azurkit.tools.characters._player_variants import ARMS, arm_turns

    if (clip, back) not in lo.tips:
        style, over = lo.weapon.style, lo.prop.over
        if "" not in lo.tips:
            lo.tips[""] = Retarget(characters_xbr, lo.body, grow=False, lift=lo.lift)
        rt = lo.tips[""]
        g4, top, bottom, _, _ = _staff_hold(characters_xbr, style, over)
        hand = [b.name for b in g4.bones].index(style.hand)
        source = named_clip(characters_xbr, style.source, clip)
        baked = bake_clip(rt, source)
        his, mine = _keyed(source), _keyed(baked)
        names = [b.name for b in rt.target.bones]
        at = names.index(lo.grip)
        arm = next((k for k in rt.target.ancestors(at) if names[k] in dict(ARMS)), None) if clip in lo.turns else None
        moved = _keyed(turned(rt.target, baked, arm_turns(rt.target, *lo.turns[clip]))) if arm is not None else None
        out = []
        for s in range(HELD_SAMPLES + 1):
            t = w.on + (w.off - w.on) * s / HELD_SAMPLES
            rot, pos = _frames(g4, his, (top, bottom, hand), t)
            tip, _ = _tip(rot, pos, top, bottom, over - back)
            _, there = _frames(rt.target, mine, (at,), t)
            point = tuple(p + lo.k * (a - b) for p, a, b in zip(there[at], tip, pos[hand]))
            if moved is not None:   # W35: rigid with its arm, turned (the hand below it unkeyed by the turn)
                (r0, p0), (r1, p1) = ((f[0][arm], f[1][arm]) for f in (_frames(rt.target, mine, (arm,), t),
                                                                     _frames(rt.target, moved, (arm,), t)))
                point = tuple(a + b for a, b in zip(p1, _turn(qmul(r1, qinv(r0)), [c - d for c, d in zip(point, p0)])))
            out.append(point)
        lo.tips[clip, back] = tuple(out)
    return lo.tips[clip, back]


def _sampled_track(carrier: int, length: float, known: set[float], at, grid=None) -> list[Track]:
    """W26's tracks for ``carrier`` (:func:`carried`, :func:`carried_copy`): its
    translation and rotation at ``at(t, ref)`` sampled at :data:`SAMPLE_HZ`
    (or at ``grid``'s times, W41: :func:`chain_lifted`) and at the
    ``known`` key times, one-sided slopes at those, the quaternion's sign
    kept continuous."""
    known = sorted(known)
    n = max(2, math.ceil(length * SAMPLE_HZ) + 1)
    times = sorted(set(known) | {u for u in (grid if grid is not None else (length * i / (n - 1) for i in range(n)))
                                 if min(abs(u - v) for v in known) > 2e-3})
    h, rows, prev, kinks = 1e-5, [], None, set(known)
    for t in times:
        v, q = at(t, prev)
        lo_t, hi = max(0.0, t - h), min(length, t + h)
        here, right = (*v, *q), sum(at(hi, q), ())
        out = [(y - x) / (hi - t) if hi > t else 0.0 for x, y in zip(here, right)]
        if t in kinks:   # a key time: its own slope on each side (between keys the curve is smooth)
            left = sum(at(lo_t, q), ())
            rows.append((t, here, [(x - y) / (t - lo_t) if t > lo_t else 0.0 for x, y in zip(here, left)], out))
        else:
            rows.append((t, here, out, out))
        prev = q
    return [Track(carrier, c, tuple((t, v[c], i[c], o[c]) for t, v, i, o in rows)) for c in range(7)]


# --- W41: a held prop kept over the floor (Step 2.207, AZ-784) ---
def floor_kept(clip: str) -> bool:
    """Whether W41 keeps a held prop over the floor in garret4's ``clip``
    (in any folder: ``g4/``, ``p/``; :data:`FLOORLESS`)."""
    return not clip.rsplit("/", 1)[-1].startswith(FLOORLESS)


def _rows(q: tuple) -> tuple[tuple[float, float, float], ...]:
    """The rotation matrix of the unit quaternion ``q`` (x, y, z, w): ``_turn(q, v)`` is its rows times ``v``."""
    x, y, z, w = q
    return ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
            (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
            (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))


def _extremes(points) -> tuple[tuple[float, float, float], ...]:
    """The points of ``points`` lowest along one of 256 directions spread
    over the sphere: those a rigid prop's lowest point can be along any
    way up (its hull, near enough), so W41 reads a few dozen vertices."""
    n, keep = 256, set()
    for i in range(n):
        z = 1.0 - (2 * i + 1) / n
        r, a = math.sqrt(1.0 - z * z), i * math.pi * (3.0 - math.sqrt(5.0))
        d = (r * math.cos(a), r * math.sin(a), z)
        keep.add(min(range(len(points)), key=lambda j: sum(c * p for c, p in zip(d, points[j]))))
    return tuple(tuple(points[j]) for j in sorted(keep))


def _arm(rig: Rig, grip: int) -> int:
    """The bone :data:`ARM_UP` up from ``grip`` (fewer where its chain is shorter: a token's root is its own)."""
    up = rig.ancestors(grip)[:ARM_UP]
    return up[-1] if up else grip


def _floor_lift(tip, turn, hand, hull, length: float, up, floor: float, ground: float | None = None,
                either: bool = False, arm=None) -> tuple[tuple, tuple, tuple] | None:
    """W41 (Step 2.207, AZ-784): the turn L about the point P of a held
    prop's handle nearest ``hand`` (the prop's frame ``turn``, its tip
    ``tip``; ``hull`` its points in that frame, :func:`_extremes`, the tip
    the origin and the handle ``length`` down -y) that brings every point
    to ``floor`` or over along the unit ``up``: the least one, in steps of
    :data:`LIFT_STEP` degrees halved to 0.001 degree, in the plane of the
    tip's way from P and ``up``, the tip rising about the grip, up to 90
    degrees, or where none does (Step 2.207b, AZ-785: a handle end under
    the floor, a creature's upright hold) sinking; with ``either`` (a
    wearer's own clips and a floating carrier, which 2.207 never turned)
    the least turn either way.  (L, P, S), S (0, 0, 0), or ``None`` where
    every point is there already.  Where no turn does it, the one that
    raises the lowest point most (the tip up only, as Step 2.207's, unless
    ``either``), and S slides the prop the rest of the way along ``up``
    where ``hand`` or ``arm`` (the point :data:`ARM_UP` bones up from the
    grip; Step 2.207c, AZ-800), the higher, is on the floor or over it
    (``ground``, by default ``floor`` less :data:`FLOOR_CLEAR`; Step 2.207b:
    the grip itself near the floor, his roll's 0.088 m, a token's root on
    it, a long arm's hand in it: the prop leaves the hand by its own depth
    there), less and less over its next :data:`SLIDE_RAMP` under it,
    after which (a body sinking into its water) the prop keeps that
    turn."""
    m = _rows(turn)

    def along(u) -> tuple[float, float, float]:   # u . (M p) = (M^T u) . p
        return tuple(sum(m[i][c] * u[i] for i in range(3)) for c in range(3))

    def dot(a, b) -> float:
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    w = along(up)
    if dot(up, tip) + min(dot(w, p) for p in hull) >= floor:
        return None
    handle = _turn(turn, (0.0, -1.0, 0.0))
    s = min(max(dot([h - t for h, t in zip(hand, tip)], handle), 0.0), length)
    pivot = tuple(t + s * c for t, c in zip(tip, handle))
    rel = [t - p for t, p in zip(tip, pivot)]
    axis = (rel[1] * up[2] - rel[2] * up[1], rel[2] * up[0] - rel[0] * up[2], rel[0] * up[1] - rel[1] * up[0])
    if dot(axis, axis) < 1e-18:   # the tip straight under the grip: any axis square to up
        axis = (up[1], -up[0], 0.0) if abs(up[2]) < 0.9 else (0.0, up[2], -up[1])
    n = math.sqrt(dot(axis, axis))
    axis = tuple(c / n for c in axis)   # rel x up: a turn about it raises the tip
    side = (up[1] * axis[2] - up[2] * axis[1], up[2] * axis[0] - up[0] * axis[2], up[0] * axis[1] - up[1] * axis[0])
    wc, ws = along(up), along(side)
    cs = [(dot(up, rel) + dot(wc, p), dot(side, rel) + dot(ws, p)) for p in hull]
    need = floor - dot(up, pivot)

    def low(a: float) -> float:
        c, s_ = math.cos(a), math.sin(a)
        return min(x * c + y * s_ for x, y in cs) - need
    best, at, cleared = low(0.0), 0.0, False
    steps = range(1, int(round(90.0 / LIFT_STEP)) + 1)   # Step 2.207's turns kept unless ``either``
    for sign, k in ([(s_, k) for k in steps for s_ in (1.0, -1.0)] if either
                    else [(s_, k) for s_ in (1.0, -1.0) for k in steps]):
        a = math.radians(sign * k * LIFT_STEP)
        v = low(a)
        if v >= 0.0:
            near, far = math.radians(sign * (k - 1) * LIFT_STEP), a
            while abs(far - near) > math.radians(0.001):
                mid = (near + far) / 2
                near, far = (near, mid) if low(mid) >= 0.0 else (mid, far)
            at, cleared = far, True
            break
        if v > best and (either or sign > 0.0):
            best, at = v, a
    ground = floor - FLOOR_CLEAR if ground is None else ground
    ramp = (floor - ground) * SLIDE_RAMP / FLOOR_CLEAR   # in the caller's units, as its clearance
    gate = dot(up, hand) if arm is None else max(dot(up, hand), dot(up, arm))
    fade = min(max((gate - ground + 1e-3 + ramp) / ramp, 0.0), 1.0)   # a token's root: at it
    slide = 0.0 if cleared else -best * fade
    h = at / 2
    return ((axis[0] * math.sin(h), axis[1] * math.sin(h), axis[2] * math.sin(h), math.cos(h)), pivot,
            tuple(slide * c for c in up))


def _lifted(lift, tip: tuple, turn: tuple) -> tuple[tuple, tuple]:
    """A tip and frame turned by :func:`_floor_lift`'s (L, P, S) and slid by S, unchanged for ``None``."""
    if lift is None:
        return tip, turn
    q, pivot, slide = lift
    return (tuple(p + c + s for p, c, s in zip(pivot, _turn(q, [t - p for t, p in zip(tip, pivot)]), slide)),
            qnorm(qmul(q, turn)))


def _up_and_floor(hand: tuple, k: float, o: tuple, q: tuple) -> tuple[tuple, float]:
    """W41's floor in garret4's frame for a wearer that holds his point x
    at ``o`` + Q k (x - ``hand``) (``q`` Q; ``k`` :attr:`Loadout.k`): the
    unit ``up`` and height n . x at its floor plus :data:`FLOOR_CLEAR`."""
    up = _turn(qinv(q), (0.0, 0.0, 1.0))
    return up, (FLOOR_CLEAR - o[2]) / k + sum(a * b for a, b in zip(up, hand))


def _prop_hull(characters_xbr: bytes, prop: Prop) -> tuple[tuple, float]:
    """A loose prop's :func:`_extremes` in its tip carrier's frame (W26's
    turn: the tip the origin, the handle down -y; :func:`_donor`, at
    garret4's size), the tip itself among them (the handle's centre line
    at the blade end, which the blade's vertices don't hold), and its
    length, for W41."""
    verts, _, _, length = _donor(characters_xbr, prop)
    return _extremes([(0.0, 0.0, 0.0), *(v[0] for v in verts)]), length


def _copy_turn(prop: Prop, k_turn: tuple) -> tuple:
    """C, the turn a copy's tip carrier takes after the style's held top
    (W31): K (:func:`_staff_hold`) for a loose prop (the hoe, in W26's
    frame: its handle down -y), the identity for garret4's own staff, whose
    carriers then turn as his ``m_stafftop`` and ``m_staffbottom``, so the
    fx blades bound to them by name (``docs/RE_DATA.md`` "The staff") lie
    along the shaft as on him, not across it (AZ-693: K is 90.1 degrees,
    a hoe)."""
    return k_turn if prop.mesh.loose else (0.0, 0.0, 0.0, 1.0)


def _rest(characters_xbr: bytes, rt: Retarget, lo: Loadout) -> tuple[tuple, tuple]:
    """The tip carrier's rest under the grip (W31): where :func:`carried_copy`
    keys it in garret4's idle at t 0 baked onto the wearer, so the body's
    own clips, which key no carrier, hold the prop as his idle holds his
    staff: (translation, rotation) in the grip's frame."""
    style, prop = lo.weapon.style, lo.prop
    g4, top, bottom, k_turn, _ = _staff_hold(characters_xbr, style, prop.over)
    k_turn = _copy_turn(prop, k_turn)
    hand = [b.name for b in g4.bones].index(style.hand)
    idle = named_clip(characters_xbr, style.source, "idle")
    rot, pos = _frames(g4, _keyed(idle), (top, bottom, hand), 0.0)
    tip, staff = _tip(rot, pos, top, bottom, prop.over)
    at = [b.name for b in rt.target.bones].index(lo.grip)
    w_rot, _ = _frames(rt.target, _keyed(bake_clip(rt, idle)), (at,), 0.0)
    hw = qinv(w_rot[at])
    return (tuple(lo.k * c for c in _turn(hw, [a - b for a, b in zip(tip, pos[hand])])),
            qnorm(qmul(qmul(hw, staff), k_turn)))


def _donor(characters_xbr: bytes, prop: Prop) -> tuple[list, list, tuple[int, int], float]:
    """A prop's mesh in its tip carrier's frame (W32, model units at
    garret4's size): its vertices ((position, normal, uv, extra) each),
    triangles, material and length (its tip to its handle's end).  The
    staff (a ``bones`` mesh) is garret4's LOD 0 group on those bones in
    his ``m_stafftop``'s bind frame, so it rides the carrier as it rides
    his staff top (:func:`_copy_turn`); the hoe (a ``loose``
    mesh) is W26's turn of the farmer's: a half turn about x, its blade tip
    the origin and its handle down -y (:func:`carry_props`)."""
    from azurkit.tools.characters.body_codec import read_asset

    m = prop.mesh
    asset = read_asset(characters_xbr, m.body)
    if m.loose:
        donor = read_body(characters_xbr, m.body)
        loose = {(g.lod, g.index) for g in loose_props(characters_xbr, donor, prop)}
        groups = [g for n, g in enumerate(asset.lods[0].groups) if (0, n) in loose]
    else:
        wanted = {asset.bone(b) for b in m.bones}
        groups = [g for g in asset.lods[0].groups if g.palette and set(g.palette) <= wanted]
    if len(groups) != 1:
        raise ValueError(f"the {prop.title}: {m.body}'s LOD 0 has {len(groups)} groups of it, not 1")
    g = groups[0]
    points = [v.position for v in g.vertices]
    if m.loose:
        blade = min(p[1] for p in points)
        handle = [p for p in points if p[1] > blade + PROP_HANDLE]
        tip = (statistics.fmean(p[0] for p in handle), blade, statistics.fmean(p[2] for p in handle))
        verts = [((p[0] - tip[0], tip[1] - p[1], tip[2] - p[2]), (v.normal[0], -v.normal[1], -v.normal[2]),
                  v.uv, v.extra) for p, v in zip(points, g.vertices)]
        length = max(p[1] for p in points) - blade
    else:
        g4 = Rig.read(characters_xbr, m.body)
        names = [b.name for b in g4.bones]
        top, bottom = names.index(prop.carriers[0]), names.index(prop.carriers[1])
        frame = qinv(g4.world[top])
        verts = [(_turn(frame, [a - b for a, b in zip(p, g4.positions[top])]), _turn(frame, v.normal), v.uv, v.extra)
                 for p, v in zip(points, g.vertices)]
        length = math.dist(g4.positions[top], g4.positions[bottom])
    return verts, list(g.triangles), g.material, length


# --- Step 2.161e: a prop on a creature's grip or floating on a clipless body (D493) ---
def _euler(degrees: tuple[float, float, float]) -> tuple:
    """The turn of :attr:`Grip.turn`: about the model's x, then y, then z."""
    q = (0.0, 0.0, 0.0, 1.0)
    for axis, d in enumerate(degrees):
        half = math.radians(d) / 2
        q = qmul(tuple(math.sin(half) if c == axis else 0.0 for c in range(3)) + (math.cos(half),), q)
    return q


def _idle_hold(characters_xbr: bytes, lo: Loadout) -> tuple[tuple, tuple, tuple]:
    """garret4's idle at t 0 in his model's frame for ``lo``'s prop: his
    right hand's offset to the prop's tip x :attr:`Loadout.k`, the tip x
    k, and the tip carrier's turn there (his staff top's after
    :func:`_copy_turn`'s C, as :func:`carried_copy` turns it)."""
    style, prop = lo.weapon.style, lo.prop
    g4, top, bottom, k_turn, _ = _staff_hold(characters_xbr, style, prop.over)
    k_turn = _copy_turn(prop, k_turn)
    hand = [b.name for b in g4.bones].index(style.hand)
    rot, at = _frames(g4, _keyed(named_clip(characters_xbr, style.source, "idle")), (top, bottom, hand), 0.0)
    tip, staff = _tip(rot, at, top, bottom, prop.over)
    return (tuple(lo.k * (a - h) for a, h in zip(tip, at[hand])), tuple(lo.k * a for a in tip),
            qnorm(qmul(staff, k_turn)))


def _feet(g4: Rig, clip: Clip) -> dict[int, tuple]:
    """garret4's ``m_feet`` keys in ``clip`` by component, those some key
    of which leaves 1 mm (as the timer bake rides them: ``bake_clip``)."""
    feet = next((i for i, m in enumerate(g4.markers) if m.casefold() == "m_feet"), -1)
    return {tr.comp: tr.keys for tr in clip.markers if tr.target == feet and tr.comp <= 2
            and any(abs(key[1]) > 1e-3 for key in tr.keys)}


def _floated_at(g4: Rig, keyed: dict, feet: dict[int, tuple], top: int, bottom: int, over: float, k: float,
                drawn: float, t: float, kept: tuple | None = None) -> tuple[tuple, tuple]:
    """A floating carrier at ``t`` of garret4's clip (``keyed``, ``feet``:
    :func:`_feet`) on a clipless body drawn ``drawn`` times: model units
    k x his tip + (1 / D - k) x his ``m_feet``, so, the game drawing the
    model at its entity less ``m_feet`` and the bones x D, the drawn tip is
    D x k x (his tip - his ``m_feet``) from the entity, his staff's path at
    the prop's size; and his staff top's turn.  With ``kept`` (W41, Step
    2.207b, AZ-785: his hand, the prop's hull and length and C,
    :func:`_copy_turn`) the tip and turn are first turned over the floor
    about his grip (:func:`_floor_lift`), its D x k x clear over his
    ``m_feet``."""
    rot, pos = _frames(g4, keyed, (top, bottom) if kept is None else (top, bottom, kept[0]), t)
    tip, staff = _tip(rot, pos, top, bottom, over)
    inv = 1.0 / drawn if drawn and math.isfinite(drawn) else 0.0
    under = [evaluate(feet[c], t) if c in feet else 0.0 for c in range(3)]
    if kept is not None and inv:
        hand, hull, length, c_turn = kept
        turn = qmul(staff, c_turn)
        tip, turn = _lifted(_floor_lift(tip, turn, pos[hand], hull, length, (0.0, 0.0, 1.0),
                                        under[2] + FLOOR_CLEAR * inv / k, under[2], either=True), tip, turn)
        staff = qmul(turn, qinv(c_turn))
    return tuple(k * a + (inv - k) * f for a, f in zip(tip, under)), staff


def float_clips(characters_xbr: bytes, body: Body, lo: Loadout, drawn: float) -> bytes:
    """The floating carrier's tracks (:data:`FLOAT`, Step 2.161e; the 2.161
    design's S5): ``characters.xbr`` with each of garret4's clips baked onto
    the clipless ``body`` (its every clip, ``g4/<clip>``: B's timers, his
    victories among them; its carriers added, :func:`add_carriers`)
    rewritten with the tip carrier, a root, keyed where :func:`_floated_at`
    puts it and turned as his staff top after :func:`_copy_turn`'s C;
    sampled as :func:`carried`
    (his chain's and ``m_feet``'s key times, one-sided slopes there).  The
    timer bake rode every root on ``m_feet`` before the carriers were
    there, so the body's own bone keeps that ride."""
    from azurkit.tools.characters.retarget import BAKED_DIR, read_clip, write_clip
    from azurkit.core.xbr.append import append_resources

    style, prop = lo.weapon.style, lo.prop
    g4, top, bottom, k_turn, _ = _staff_hold(characters_xbr, style, prop.over)
    k_turn = _copy_turn(prop, k_turn)
    rig = Rig.read(characters_xbr, body.name)
    carrier = [b.name for b in rig.bones].index(prop.carriers[0])
    back = qinv(rig.bones[carrier].jo)
    chain = {top, bottom, *g4.ancestors(top), *g4.ancestors(bottom)}
    hull = _prop_hull(characters_xbr, prop) if prop.over > 0.0 else None   # W41 (Step 2.207b): past his staff
    hand = [b.name for b in g4.bones].index(style.hand)
    toc, names = parse_toc(characters_xbr), named_resources(characters_xbr)
    prefix = f"characters/{body.name}/{BAKED_DIR}".casefold()
    rewrite = {}
    for i, name in sorted(names.items()):
        if not name.casefold().startswith(prefix) or toc[i].tag != "banm":
            continue
        baked = read_clip(characters_xbr, toc[i].file_offset)
        source = named_clip(characters_xbr, style.source, name[len(prefix):])
        his, feet, length = _keyed(source), _feet(g4, source), baked.length
        kept = (hand, *hull, k_turn) if hull is not None and floor_kept(name) else None

        def place(t: float, ref: tuple | None, his=his, feet=feet, kept=kept) -> tuple[tuple, tuple]:
            at, staff = _floated_at(g4, his, feet, top, bottom, prop.over, lo.k, drawn, t, kept)
            q = qnorm(qmul(back, qmul(staff, k_turn)))
            if ref is not None and sum(x * y for x, y in zip(q, ref)) < 0:
                q = tuple(-x for x in q)
            return at, q
        known = {0.0, length} | {key[0] for (b, _), keys in his.items() if b in chain for key in keys
                                 if 0.0 <= key[0] <= length} | {key[0] for keys in feet.values() for key in keys
                                                                if 0.0 <= key[0] <= length}
        tracks = [tr for tr in baked.bones if tr.target != carrier] + _sampled_track(carrier, length, known, place)
        rewrite[i] = write_clip(replace(baked, bones=tuple(sorted(tracks, key=lambda tr: (tr.target, tr.comp)))))
    if not rewrite:
        raise ValueError(f"W31: {body.name} has no clip of garret4's baked onto it to key its floating carrier in")
    return append_resources(characters_xbr, rewrite=rewrite)


def add_carriers(characters_xbr: bytes, body: Body, lo: Loadout, rt: Retarget | None = None) -> bytes:
    """W31 (Step 2.161b; the 2.161 design's L8): ``characters.xbr`` with
    ``lo``'s copied prop's two carriers appended to ``body`` after every
    other bone (:func:`~azurik_mod.assets.skeleton.add_bone`, so W24's,
    W29's and X41's indices hold): the tip under :attr:`Loadout.grip` at
    its :func:`_rest` (garret4's idle-t0 tip in the wearer's baked grip
    frame, x :attr:`Loadout.k`; its joint orient that turn), the end under
    the tip at the prop's other end (the hoe's handle end down -y, the
    staff's ``m_staffbottom``), its joint orient the identity.  Retarget
    keeps both (a mapped bone above them), and no clip but a baked one
    keys them, so the body's own clips hold the prop at rest.  Step
    2.161e: on a creature or a token (:data:`RIGID`, no ``rt``) the tip
    sits at its grip's bind as garret4's idle at t 0 holds it in the
    model's frame, his hand-to-tip offset x k, its turn his staff top's
    after C (:func:`_idle_hold`), then its :class:`Grip`'s turn and
    offset; on a clipless body (:data:`FLOAT`) it is a root there, at his
    tip x k.  Step 2.161g (D618): on garret4's staff chain (:data:`ON_CHAIN`)
    both under his ``m_stafftop``, the tip at the prop's blade tip
    (:func:`_on_chain`), the end at its handle's end, each turned as that
    bone (C the identity, as his staff's: AZ-693), so his staff's fx bind
    the prop's ends.  :class:`ValueError` names a carrier the body already has
    (D35)."""
    from azurkit.tools.characters import body_codec, skeleton

    prop = lo.prop
    asset = body_codec.read_asset(characters_xbr, body.name)
    taken = [n for n in prop.carriers if n in asset.bone_names]
    if taken:
        raise ValueError(f"W31: {body.name} has a bone {taken[0]!r} already, so the {prop.title}'s carrier can't "
                         "take its name")
    worlds = skeleton.rest_worlds(asset)
    if lo.carry == ON_CHAIN:   # Step 2.161g (D618): rigid on his chain, at the prop's ends
        origin, placed = _on_chain(characters_xbr, lo)
        turn = Rig.read(characters_xbr, PLAYER).world[asset.bone(lo.weapon.style.held[0])]
        length = _donor(characters_xbr, prop)[3]
        skeleton.add_bone(asset, prop.carriers[0], lo.weapon.style.held[0], origin, turn)
        skeleton.add_bone(asset, prop.carriers[1], prop.carriers[0],
                          tuple(o + c for o, c in zip(origin, _turn(placed, (0.0, -length, 0.0)))), turn)
        return body_codec.write_asset(characters_xbr, asset)
    if lo.carry == COPY:
        t, q = _rest(characters_xbr, rt, lo)
        p = asset.bone(lo.grip)
        pq = skeleton._world_rotation(asset, p)
        origin = tuple(worlds[p][i][3] + sum(worlds[p][i][j] * t[j] for j in range(3)) for i in range(3))
        turn = qnorm(qmul(pq, q))
    else:   # Step 2.161e: garret4's idle hold in the model's frame, on a creature's grip or floating at the root
        hold, tip, staff = _idle_hold(characters_xbr, lo)
        if lo.carry == FLOAT:
            origin, turn = tip, staff
        else:
            row = grips().get(body.name.casefold()) or Grip(body.name, lo.grip)
            spin, p = _euler(row.turn), asset.bone(lo.grip)
            origin = tuple(worlds[p][i][3] + h + o for i, (h, o) in enumerate(zip(_turn(spin, hold), row.offset)))
            turn = qnorm(qmul(spin, staff))
    skeleton.add_bone(asset, prop.carriers[0], lo.grip, origin, turn)
    verts, _, _, length = _donor(characters_xbr, prop)
    if prop.mesh.loose:
        end = (0.0, -length * lo.k, 0.0)
    else:
        g4 = Rig.read(characters_xbr, prop.mesh.body)
        names = [b.name for b in g4.bones]
        top, bottom = names.index(prop.carriers[0]), names.index(prop.carriers[1])
        end = tuple(lo.k * c for c in _turn(qinv(g4.world[top]),
                                            [a - b for a, b in zip(g4.positions[bottom], g4.positions[top])]))
    skeleton.add_bone(asset, prop.carriers[1], prop.carriers[0],
                      tuple(o + c for o, c in zip(origin, _turn(turn, end))), turn)
    return body_codec.write_asset(characters_xbr, asset)


def carried_copy(characters_xbr: bytes, body: Body, lo: Loadout, variant=None):
    """The twin of :func:`carried` for a copied prop (Step 2.161b; the
    2.161 design's F-C, L9): garret4's clip baked onto ``body`` (its
    carriers added, :func:`add_carriers`) with the tip carrier keyed so
    it sits where the prop's tip rides garret4's staff, his hand-to-tip
    offset x :attr:`Loadout.k`, and turns as his ``m_stafftop`` after
    :func:`_copy_turn`'s C, in the wearer's own baked grip frame Hw: local
    q = JO^-1 Hw^-1 S C (JO the carrier's rest turn, W31), local
    T = Hw^-1 (tip - hand) x k;
    sampled as :func:`carried` (the bake keys the grip at his chain's key
    times or on its own grid); then W35 (Step 2.161g, AZ-696) turns both
    ``*_arm_1`` by :attr:`Loadout.turns` in a fitted clip, the prop riding
    the turned hand.  W41 keeps the prop over the floor where the grip
    ends up once W35 and ``variant``'s W28 (its arms and poses, which the
    build makes later: :func:`~azurik_mod.patches._player_variants.
    arms_posed`; Step 2.207b, AZ-785) have turned the clip."""
    from azurkit.tools.characters._player_variants import arm_turns, arms_posed
    style, prop = lo.weapon.style, lo.prop
    g4, top, bottom, k_turn, _ = _staff_hold(characters_xbr, style, prop.over)
    k_turn = _copy_turn(prop, k_turn)
    hand = [b.name for b in g4.bones].index(style.hand)
    rig = Rig.read(characters_xbr, body.name)
    names = [b.name for b in rig.bones]
    carrier, at = names.index(prop.carriers[0]), names.index(lo.grip)
    arm = _arm(rig, at)
    back = qinv(rig.bones[carrier].jo)
    chain = {top, bottom, hand, *g4.ancestors(top), *g4.ancestors(bottom), *g4.ancestors(hand)}
    hull, long = _prop_hull(characters_xbr, prop) if prop.over > 0.0 else (None, 0.0)   # W41: past his staff
    later = arms_posed(rig, variant) if variant is not None and hull is not None else None   # W28's, Step 2.207b

    def post(name: str, source: Clip, baked: Clip) -> Clip:
        his, mine, length = _keyed(source), _keyed(baked), baked.length
        fitted = turned(rig, baked, arm_turns(rig, *lo.turns[name])) if name in lo.turns and hull is not None else baked
        final = later(name, fitted) if later is not None else fitted
        moved = _keyed(final) if hull is not None and final is not baked else None
        floored = hull is not None and floor_kept(name)

        def place(t: float, ref: tuple | None) -> tuple[tuple, tuple]:
            rot, pos = _frames(g4, his, (top, bottom, hand), t)
            tip, staff = _tip(rot, pos, top, bottom, prop.over)
            w_rot, w_pos = _frames(rig, mine, (at,), t)   # the grip's chain: its arm too
            hw = qinv(w_rot[at])
            turn = qmul(staff, k_turn)
            if floored:   # W41 (Step 2.207): his point x at grip + k (x - hand), then the grip as W35 and W28 turn it
                o, q_, a_ = w_pos[at], (0.0, 0.0, 0.0, 1.0), w_pos[arm]
                if moved is not None:
                    r1, p1 = _frames(rig, moved, (at,), t)
                    o, q_, a_ = p1[at], qmul(r1[at], hw), p1[arm]
                up, floor = _up_and_floor(pos[hand], lo.k, o, q_)
                arm_at = tuple(h + c / lo.k for h, c in zip(pos[hand], _turn(qinv(q_), [a - b for a, b in zip(a_, o)])))
                tip, turn = _lifted(_floor_lift(tip, turn, pos[hand], hull, long, up, floor,
                                                floor - FLOOR_CLEAR / lo.k, arm=arm_at), tip, turn)
            q = qnorm(qmul(back, qmul(hw, turn)))
            if ref is not None and sum(x * y for x, y in zip(q, ref)) < 0:
                q = tuple(-x for x in q)
            return tuple(lo.k * c for c in _turn(hw, [a - b for a, b in zip(tip, pos[hand])])), q
        known = {0.0, length} | {key[0] for (b, _), keys in his.items() if b in chain for key in keys
                                 if 0.0 <= key[0] <= length}   # the grip's keys are his chain's or the bake's grid
        tracks = [tr for tr in baked.bones if tr.target != carrier] + _sampled_track(carrier, length, known, place)
        clip = replace(baked, bones=tuple(sorted(tracks, key=lambda tr: (tr.target, tr.comp))))
        return turned(rig, clip, arm_turns(rig, *lo.turns[name])) if name in lo.turns else clip
    return post


def _on_chain(characters_xbr: bytes, lo: Loadout) -> tuple[tuple, tuple]:
    """Where a prop on garret4's staff chain (:data:`ON_CHAIN`, Step
    2.161d) sits at his bind: its tip carrier's frame as W26's carrier
    would ride his staff (:func:`carried`: turned as his ``m_stafftop``
    after K, its origin the tip ``over`` past the top along the staff),
    (origin, turn) in his model.  His staff's axis is fixed in his
    ``m_stafftop``'s frame in every one of his 95 clips (0.0 degrees,
    Step 2.161d's probe), so a mesh skinned to that bone alone rides
    exactly there in each."""
    style, prop = lo.weapon.style, lo.prop
    g4, top, bottom, k_turn, _ = _staff_hold(characters_xbr, style, prop.over)
    axis = [a - b for a, b in zip(g4.positions[top], g4.positions[bottom])]
    n = math.sqrt(sum(c * c for c in axis))
    return (tuple(a + prop.over * c / n for a, c in zip(g4.positions[top], axis)),
            qnorm(qmul(g4.world[top], k_turn)))


def copy_prop(characters_xbr: bytes, body: Body, lo: Loadout) -> tuple[bytes, int]:
    """W32 (Step 2.161b): ``characters.xbr`` with ``lo``'s prop's mesh
    (:func:`_donor`) x :attr:`Loadout.k` appended as a group to every LOD
    ``body`` draws, skinned to its tip carrier alone (W31's bind: at rest
    it skins as the identity; on garret4's staff chain, Step 2.161d, placed
    as his ``m_stafftop`` carries it, :func:`_on_chain`, on the carrier
    W31 hangs rigidly under that bone since Step 2.207, so W41 can key
    it: :func:`chain_lifted`), its material a copy: the donor's row as a
    one-row ``gshd`` of its own and the row's textures and shader
    programs copied (``xbr.clone.Copier``), each a new unnamed entry
    reached only through the relocated field that names it (the 2.161
    design's 3.2: no foreign index); and how many groups it added."""
    from azurkit.tools.characters import body_codec
    from azurkit.core.xbr.append import append_resources
    from azurkit.core.xbr.clone import Batch, Copier, refs_in
    from azurkit.core.xbr.nodes import parse_toc

    verts, triangles, (gshd, row), _ = _donor(characters_xbr, lo.prop)
    toc = parse_toc(characters_xbr)
    e = toc[gshd]
    src = bytes(characters_xbr[e.file_offset:e.file_offset + e.size])
    table = 4 + struct.unpack_from("<i", src, 4)[0]
    start = table + 4 * row + struct.unpack_from("<i", src, table + 4 * row)[0]
    size = 100 + 124 * struct.unpack_from("<I", src, start + 96)[0]
    batch = Batch(characters_xbr)
    copier = Copier(characters_xbr, batch, same=False, label="characters.xbr")
    refs = {}
    for off, target in refs_in(characters_xbr, toc, gshd):
        if off == 8 or start <= off < start + size:
            refs[off if off == 8 else 12 + off - start] = copier.target(target)
    payload = struct.pack("<Ii", 1, 12 + size - 4) + src[8:12] + src[start:start + size] + struct.pack("<i", -size)
    material = batch.add("gshd", payload, refs, source=("characters.xbr", gshd))
    grown = append_resources(characters_xbr, batch.resources())
    asset = body_codec.read_asset(grown, body.name)
    if lo.carry == ON_CHAIN:   # Step 2.161d: where W26's carrier would ride his m_stafftop, on its tip carrier
        tip = asset.bone(lo.prop.carriers[0])   # under it (W31), which W41 keys where it would go under the floor
        origin, q = _on_chain(characters_xbr, lo)

        def model(v, offset=(0.0, 0.0, 0.0)) -> tuple:
            return tuple(o + c for o, c in zip(offset, _turn(q, v)))
    else:
        tip = asset.bone(lo.prop.carriers[0])
        bind = struct.unpack_from("<16f", asset.bones[tip].record, 0x60)
        turn = [[bind[4 * i + j] for j in range(3)] for i in range(3)]   # the bind's rows: model = o + R^T local
        origin = [-sum(bind[12 + j] * turn[i][j] for j in range(3)) for i in range(3)]

        def model(v, offset=(0.0, 0.0, 0.0)) -> tuple:
            return tuple(o + sum(turn[i][j] * v[j] for j in range(3)) for i, o in enumerate(offset))
    for lod in asset.lods:
        group = body_codec.Group([], [], list(triangles), (material, 0))
        for p, n, uv, extra in verts:
            group.add(model([lo.k * c for c in p], origin), model(n), uv, {tip: 1.0}, extra)
        lod.groups.append(group)
    return body_codec.write_asset(grown, asset), len(asset.lods)


def chain_lifted(characters_xbr: bytes, lo: Loadout) -> tuple[bytes, tuple[str, ...]]:
    """W41 on garret4's staff chain (:data:`ON_CHAIN`; Step 2.207, AZ-784:
    in his 360_ledge the hoe's tip went 0.358 m under the floor in game,
    0.366 offline, where his own staff's lowest point stays 0.07 m over
    it): ``characters.xbr`` (W31's carriers in, W32's mesh on the tip one)
    with each clip of his :func:`floor_kept` names in which the prop's
    lowest point goes under :data:`FLOOR_CLEAR` keying its tip carrier
    there, turned up about his grip by :func:`_floor_lift` (its rest, as
    his ``m_stafftop`` carries it, elsewhere), and those clips' names.
    Only where it is turned (and a 60 Hz step either side) are keys
    sampled (:data:`~azurik_mod.assets.retarget.SAMPLE_HZ` and his
    chain's key times); a prop that reaches no farther than his staff's
    top (the Axion staff's ``over`` 0) is left alone."""
    from azurkit.tools.characters.retarget import read_clip, write_clip
    from azurkit.core.xbr.append import append_resources

    style, prop = lo.weapon.style, lo.prop
    if prop.over <= 0.0:
        return characters_xbr, ()
    g4, top, bottom, k_turn, _ = _staff_hold(characters_xbr, style, prop.over)
    k_turn = _copy_turn(prop, k_turn)
    names = [b.name for b in g4.bones]
    hand, carrier = names.index(style.hand), names.index(prop.carriers[0])
    arm = _arm(g4, hand)
    b = g4.bones[carrier]
    rest = qmul(qmul(b.jo, b.q), b.ra)
    hull, long = _prop_hull(characters_xbr, prop)
    up = (0.0, 0.0, 1.0)
    chain = {top, bottom, hand, *g4.ancestors(top), *g4.ancestors(bottom), *g4.ancestors(hand)}
    toc, found = parse_toc(characters_xbr), named_resources(characters_xbr)
    prefix = f"characters/{PLAYER}/".casefold()
    rewrite, lifted = {}, []
    for i, name in sorted(found.items()):
        clip_name = name[len(prefix):]
        if not name.casefold().startswith(prefix) or toc[i].tag != "banm" or not floor_kept(clip_name):
            continue
        source = read_clip(characters_xbr, toc[i].file_offset)
        his, length = _keyed(source), source.length

        def lift(t: float, his=his) -> tuple:
            rot, pos = _frames(g4, his, (top, bottom, hand), t)
            tip, staff = _tip(rot, pos, top, bottom, prop.over)
            turn = qmul(staff, k_turn)
            return _floor_lift(tip, turn, pos[hand], hull, long, up, FLOOR_CLEAR, arm=pos[arm]), rot, pos, tip
        n = max(2, math.ceil(length * SAMPLE_HZ) + 1)
        grid = [length * j / (n - 1) for j in range(n)]
        hits = [j for j, t in enumerate(grid) if lift(t)[0] is not None]
        if not hits:
            continue
        near = sorted({j + d for j in hits for d in (-1, 0, 1) if 0 <= j + d < n})
        spans = [(grid[j], grid[j + 1]) for j in near if j + 1 in near]
        known = {0.0, length} | {key[0] for (c, _), keys in his.items() if c in chain for key in keys
                                 if any(a < key[0] < z for a, z in spans)}

        def place(t: float, ref: tuple | None, lift=lift) -> tuple[tuple, tuple]:
            found_lift, rot, pos, tip = lift(t)
            local, q = b.t, b.q
            if found_lift is not None:
                staff = rot[top]
                tip, _ = _lifted(found_lift, tip, staff)
                inv = qinv(staff)   # his m_stafftop's frame: r' = S^-1 L S r0, q = JO^-1 r' RA^-1
                r = qmul(qmul(inv, qmul(found_lift[0], staff)), rest)
                q = qnorm(qmul(qmul(qinv(b.jo), r), qinv(b.ra)))
                local = _turn(inv, [a - c for a, c in zip(tip, pos[top])])
            if ref is not None and sum(x * y for x, y in zip(q, ref)) < 0:
                q = tuple(-x for x in q)
            return tuple(local), q
        tracks = _sampled_track(carrier, length, known, place, grid=[grid[j] for j in near])
        rewrite[i] = write_clip(replace(source, bones=tuple(sorted((*source.bones, *tracks),
                                                                   key=lambda tr: (tr.target, tr.comp)))))
        lifted.append(clip_name)
    return (append_resources(characters_xbr, rewrite=rewrite) if rewrite else characters_xbr), tuple(lifted)


OWN_CARRIES = (IN_PLACE, COPY, RIGID)
"""The carries whose wearer's own clips :func:`own_lifted` keys (Step 2.207b)."""


def own_lifted(characters_xbr: bytes, body: str, lo: Loadout, donor: bytes) -> tuple[bytes, tuple[str, ...]]:
    """W41 in a wearer's own clips (Step 2.207b, AZ-785: keylord's die_2 and
    ouch_3 took a picked hoe 0.47 m under the floor, the golem's ouch_3
    1.80 m, the catalisk's every clip, its idles too): ``characters.xbr``
    with each clip under ``body`` that keys no tip carrier (``lo``'s:
    W26's under a farmer's hand, W31's under a picked prop's grip or a
    creature's, which ride it at their rest) and isn't :data:`FLOORLESS`,
    in which the prop's lowest point (:func:`_prop_hull` of ``donor``'s
    prop, x :attr:`Loadout.k`) goes under :data:`FLOOR_CLEAR` over the
    floor (``m_feet``'s height there, keyed or its rest: the game draws the
    model at its entity less it, 0x42E40), keying the tip carrier where it
    does, turned about the grip (:func:`_floor_lift`; its rest elsewhere),
    sampled as :func:`chain_lifted` samples; and those clips' names.  A
    prop that reaches no farther than his staff's top, and the other
    carries (his own chain, a floating carrier, keyed in every clip), are
    left alone."""
    from azurkit.tools.characters.retarget import read_clip, write_clip
    from azurkit.core.xbr.append import append_resources

    prop = lo.prop
    if prop is None or prop.over <= 0.0 or lo.carry not in OWN_CARRIES:
        return characters_xbr, ()
    rig = Rig.read(characters_xbr, body)
    carrier = [b.name for b in rig.bones].index((prop.own_carriers if lo.carry == IN_PLACE else prop.carriers)[0])
    b = rig.bones[carrier]
    hand, chain = b.parent, {carrier, *rig.ancestors(carrier)}
    arm = _arm(rig, hand)
    hull, long = _prop_hull(donor, prop)
    hull, long = tuple(tuple(lo.k * c for c in p) for p in hull), lo.k * long
    feet = next((i for i, m in enumerate(rig.markers) if m.casefold() == "m_feet"), -1)
    rest = (marker_default(characters_xbr, body, "m_feet") or (0.0, 0.0, 0.0))[2]
    up = (0.0, 0.0, 1.0)
    toc, found = parse_toc(characters_xbr), named_resources(characters_xbr)
    prefix = f"characters/{body}/".casefold()
    rewrite, lifted = {}, []
    for i, name in sorted(found.items()):
        clip_name = name[len(prefix):]
        if not name.casefold().startswith(prefix) or toc[i].tag != "banm" or not floor_kept(clip_name):
            continue
        source = read_clip(characters_xbr, toc[i].file_offset)
        if any(tr.target == carrier for tr in source.bones):   # garret4's clips baked on: W26's or W31's keys
            continue
        mine, length = _keyed(source), source.length
        fz = next((tr.keys for tr in source.markers if tr.target == feet and tr.comp == 2), None)

        def lift(t: float, mine=mine, fz=fz) -> tuple:
            rot, at = _frames(rig, mine, (carrier,), t)
            floor = (evaluate(fz, t) if fz else rest) + FLOOR_CLEAR
            return (_floor_lift(at[carrier], rot[carrier], at[hand], hull, long, up, floor, either=True, arm=at[arm]),
                    rot, at)
        n = max(2, math.ceil(length * SAMPLE_HZ) + 1)
        grid = [length * j / (n - 1) for j in range(n)]
        hits = [j for j, t in enumerate(grid) if lift(t)[0] is not None]
        if not hits:
            continue
        near = sorted({j + d for j in hits for d in (-1, 0, 1) if 0 <= j + d < n})
        spans = [(grid[j], grid[j + 1]) for j in near if j + 1 in near]
        known = {0.0, length} | {key[0] for (c, _), keys in mine.items() if c in chain for key in keys
                                 if any(a < key[0] < z for a, z in spans)}

        def place(t: float, ref: tuple | None, lift=lift) -> tuple[tuple, tuple]:
            found_lift, rot, at = lift(t)
            local, q = b.t, b.q
            if found_lift is not None:   # its world frame turned and slid, in its grip's: q = JO^-1 H^-1 T' RA^-1
                tip, turn = _lifted(found_lift, at[carrier], rot[carrier])
                inv = qinv(rot[hand])
                q = qnorm(qmul(qmul(qinv(b.jo), qmul(inv, turn)), qinv(b.ra)))
                local = _turn(inv, [a - c for a, c in zip(tip, at[hand])])
            if ref is not None and sum(x * y for x, y in zip(q, ref)) < 0:
                q = tuple(-x for x in q)
            return tuple(local), q
        tracks = _sampled_track(carrier, length, known, place, grid=[grid[j] for j in near])
        rewrite[i] = write_clip(replace(source, bones=tuple(sorted((*source.bones, *tracks),
                                                                   key=lambda tr: (tr.target, tr.comp)))))
        lifted.append(clip_name)
    return (append_resources(characters_xbr, rewrite=rewrite) if rewrite else characters_xbr), tuple(lifted)


# --- W41 through the crossfade (Step 2.207c, AZ-806) ---
FADE_TIMES = (0.25, 0.1)
"""The anim layers' crossfades (s, anim+0x14, ``docs/RE_XBE.md``): a clip change's 0.25 s (0xCAD40, 0x197564),
which :func:`faded_lifted` lifts a clip's start against, and an attack's 0.1 s (``player_attack_enter`` stores it
at 0x88A33 from 0x1980A4), for a clip :data:`ATTACKING` names."""
ATTACKING = ("attack", "360_")
"""The clips played as attacks, by a name in any folder holding the first or starting with the second
(``player_attack_enter``'s 0.1 s crossfade: garret4's attack rows and a body's own attack clips)."""
LOOPS = ("idle", "run", "walk")
"""The clips a body plays looping, by name in any folder: :func:`faded_lifted` lifts a clip that plays once
against the crossfade from them into its start and from its end into them, and never keys a loop (its first tick
is also its wrap's)."""
DEATHS = ("die", "death")
"""The clips, by name in any folder, whose end no loop fades in from (the player's death holds its last pose)."""
FADE_PHASE = 0.1
"""How far apart (s) the times of each loop are that a clip's start is lifted against."""
FADE_STEP = 5.0
""":func:`faded_lifted`'s search step (degrees, either way up to 90), refined by halving to under 0.1."""
FADE_SLEW = 10.0
"""How far (degrees) a crossfade lift's turn moves a tick at most, its turns raised where a neighbour's needs
more (the ease into and out of a clip's fade-in, and the end's ramp at least 0.25 s)."""
_TICK = 1.0 / 30.0


def _share(n: int, fade: float) -> float:
    """The new layer's share of the pose ``n`` ticks into a crossfade of ``fade`` s (0xCAD40 starts it at weight
    0.01; each tick moves both weights by dt / ``fade``: :func:`~azurik_mod.patches._player_crossfade.fade_weight`'s
    rule at any fade), 1 once it is over."""
    x = n * _TICK / fade
    if x >= 1.0:
        return 1.0
    return (0.01 + x) / (1.01)


def faded_lifted(characters_xbr: bytes, body: str, lo: Loadout, donor: bytes | None = None
                 ) -> tuple[bytes, tuple[str, ...]]:
    """W41 through the crossfade (Step 2.207c, AZ-806: keylord + hoe's
    attack end into idle_1 took the hoe 0.349 m under the floor in game,
    idle_1 into die_2 0.197 m, though each clip alone keeps it over):
    ``characters.xbr`` with each :func:`floor_kept` clip under ``body``
    that plays once (not :data:`LOOPS`) keying ``lo``'s tip carrier, after
    every other write of it, turned about the grip where a crossfade with a
    loop takes the prop's lowest point under :data:`FLOOR_CLEAR` over the
    floor (or under either clip's own, where that is lower): over its first
    ticks against each loop at each :data:`FADE_PHASE` (0.25 s, an
    attack's 0.1 s: :data:`FADE_TIMES`, :data:`ATTACKING`), easing out
    at :data:`FADE_SLEW`, and over its last 0.25 s or more (no death's,
    :data:`DEATHS`) to the least turn its end needs held while each loop
    fades in from its start, each cut where it would take the clip's own
    pose under; and those clips' names.  The blend is the
    game's (``docs/RE_XBE.md``, "The anim layers' crossfade"): each
    layer's rotations normalised and turned to w >= 0 (0xCBB6D-0xCBB7C),
    summed by the layers' shares and normalised, translations and
    ``m_feet``'s height lerped.  The turn is about the point of the prop's
    long axis (its hull's farthest pair) nearest the hand, in the plane of
    its far end's way from there and up, the least either way that clears
    every case in steps of :data:`FADE_STEP`.  A floating carrier (a
    root, :data:`FLOAT`) and a prop that reaches no farther than his staff's
    top are left alone.  The prop is the body's mesh group on the carrier
    alone, or before W32 adds it (``tip_plan``) ``donor``'s prop x
    :attr:`Loadout.k` (:func:`_prop_hull`, as :func:`own_lifted` reads it;
    none: left alone)."""
    import numpy as np

    from azurkit.tools.characters.body_codec import read_asset
    from azurkit.tools.characters.retarget import read_clip, write_clip
    from azurkit.tools.characters._player_crossfade import _curve, _qmul, _turn as _vturn, sample
    from azurkit.core.xbr.append import append_resources

    prop = lo.prop
    if prop is None or prop.over <= 0.0 or lo.carry == FLOAT:
        return characters_xbr, ()
    rig = Rig.read(characters_xbr, body)
    names = [b.name for b in rig.bones]
    carrier = names.index((prop.own_carriers if lo.carry == IN_PLACE else prop.carriers)[0])
    b = rig.bones[carrier]
    parent = b.parent
    hand = names.index(lo.weapon.style.hand) if lo.carry == ON_CHAIN else parent
    points = [_turn(qinv(rig.world[carrier]), [a - c for a, c in zip(v.position, rig.positions[carrier])])
              for g in read_asset(characters_xbr, body).lods[0].groups if list(g.palette) == [carrier]
              for v in g.vertices]
    if not points and donor is not None and lo.carry in OWN_CARRIES:
        points = [tuple(lo.k * c for c in p) for p in _prop_hull(donor, prop)[0]]
    if not points:
        return characters_xbr, ()
    hull = np.array(_extremes(points))
    e1, e2 = max(((p, q) for p in hull for q in hull), key=lambda pq: float(np.sum((pq[0] - pq[1]) ** 2)))
    chain = sorted({carrier, *rig.ancestors(carrier)}, key=lambda k: len(rig.ancestors(k)))
    row = {k: r for r, k in enumerate(chain)}
    jo = {k: np.array(rig.bones[k].jo) for k in chain}
    ra = {k: np.array(rig.bones[k].ra) for k in chain}
    feet = next((i for i, m in enumerate(rig.markers) if m.casefold() == "m_feet"), -1)
    rest = (marker_default(characters_xbr, body, "m_feet") or (0.0, 0.0, 0.0))[2]
    toc, found = parse_toc(characters_xbr), named_resources(characters_xbr)
    prefix = f"characters/{body}/".casefold()
    clips: dict[str, tuple[int, Clip]] = {}
    for i, name in sorted(found.items()):
        if name.casefold().startswith(prefix) and toc[i].tag == "banm" and floor_kept(name[len(prefix):]):
            clips[name[len(prefix):]] = (i, read_clip(characters_xbr, toc[i].file_offset))
    loops = [n for n in clips if n.rsplit("/", 1)[-1].startswith(LOOPS)]
    once = [n for n in clips if n not in loops]
    if not loops or not once:
        return characters_xbr, ()

    def canon(q):   # each layer's rotation normalised, w >= 0 (0xCBB6D-0xCBB7C)
        q = q / np.linalg.norm(q, axis=-1, keepdims=True)
        return np.where(q[..., 3:4] < 0.0, -q, q)

    def posed(clip: Clip, ts) -> tuple:   # the chain's raw q and t (rows of ``chain``), m_feet's height, its low
        q, t = sample(rig, clip, ts)
        fz = next((tr.keys for tr in clip.markers if tr.target == feet and tr.comp == 2), None)
        f = _curve(fz, np.asarray(ts, dtype=float)) if fz else np.full(len(ts), rest)
        q, t = canon(q[chain]), t[chain]
        return q, t, f, low(*parent_frame(q, t), q[row[carrier]], t[row[carrier]]) - f

    def parent_frame(q, t):   # the carrier's parent's world rotation and origin (FK of the chain above it)
        world, at = {}, {}
        for k in chain:
            if k == carrier:
                continue
            loc = _qmul(_qmul(jo[k], q[row[k]] / np.linalg.norm(q[row[k]], axis=-1, keepdims=True)), ra[k])
            p = rig.bones[k].parent
            world[k], at[k] = (loc, t[row[k]]) if p < 0 else (_qmul(world[p], loc), at[p] + _vturn(world[p], t[row[k]]))
        return world[parent], at[parent]

    def low(w_par, a_par, qc, tc):   # the prop's lowest point (model z) with the carrier's local q, t
        wc = _qmul(w_par, _qmul(_qmul(jo[carrier], qc / np.linalg.norm(qc, axis=-1, keepdims=True)), ra[carrier]))
        ac = a_par + _vturn(w_par, tc)
        x, y, z, w = np.moveaxis(wc, -1, 0)
        r3 = np.stack((2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)), axis=-1)
        return ac[..., 2] + (r3 @ hull.T).min(axis=-1)

    # the loops: each at its phases, n ticks on (wrapping), for the fade-ins; from its start for the fade-outs
    pq, pt, pf, pl, fq, ft, ff, fl = [], [], [], [], [], [], [], []
    for name in loops:
        clip = clips[name][1]
        phases = [j * FADE_PHASE for j in range(int(clip.length / FADE_PHASE) + 1) if j * FADE_PHASE < clip.length]
        ts = [(ph + n * _TICK) % clip.length if clip.length > 0 else 0.0 for ph in phases for n in range(8)]
        q, t, f, lw = posed(clip, ts)
        pq.append(q.reshape(len(chain), len(phases), 8, 4))
        pt.append(t.reshape(len(chain), len(phases), 8, 3))
        pf.append(f.reshape(len(phases), 8))
        pl.append(lw.reshape(len(phases), 8))
        fq.append(pq[-1][:, :1]), ft.append(pt[-1][:, :1]), ff.append(pf[-1][:1]), fl.append(pl[-1][:1])
    pq, pt, pf, pl = (np.concatenate(a, axis=1 if a[0].ndim == 4 else 0) for a in (pq, pt, pf, pl))
    fq, ft, ff, fl = (np.concatenate(a, axis=1 if a[0].ndim == 4 else 0) for a in (fq, ft, ff, fl))
    up = np.array((0.0, 0.0, 1.0))

    def frame(keyed: dict, t: float) -> tuple:   # the clip's carrier, its parent and the turn's pivot and axis at t
        rot, at = _frames(rig, keyed, (carrier, hand), t)
        a1 = np.array(at[carrier]) + np.array(_turn(rot[carrier], e1))
        a2 = np.array(at[carrier]) + np.array(_turn(rot[carrier], e2))
        u = a2 - a1
        length = float(np.linalg.norm(u))
        u = u / length if length > 0.0 else up
        pivot = a1 + min(max(float(np.dot(np.array(at[hand]) - a1, u)), 0.0), length) * u
        far = a1 if np.linalg.norm(a1 - pivot) > np.linalg.norm(a2 - pivot) else a2
        axis = np.cross(far - pivot, up)
        n_ = float(np.linalg.norm(axis))
        return rot, at, pivot, (axis / n_ if n_ > 1e-9 else np.array((1.0, 0.0, 0.0)))

    def turned(rot, at, pivot, axis, degrees) -> tuple:   # the carrier's local q, t (arrays over ``degrees``)
        h = np.radians(np.atleast_1d(degrees)) / 2
        r = np.concatenate((axis[None] * np.sin(h)[:, None], np.cos(h)[:, None]), axis=1)
        wc = _qmul(r, np.array(rot[carrier]))
        ac = pivot + _vturn(r, np.array(at[carrier]) - pivot)
        inv = np.array(qinv(rot[parent]))
        q = _qmul(_qmul(_qmul(np.array(qinv(b.jo)), inv), wc), np.array(qinv(b.ra)))
        return canon(q), _vturn(np.broadcast_to(inv, (len(h), 4)), ac - np.array(at[parent]))

    def least(cases, own, fr, sign: float = 0.0) -> float:
        """The least turn (degrees) of the clip's carrier (its chain ``own``, its frame ``fr``) that keeps each
        case's blend over its targets: (the other layer's chain q and t, the new layer's share, the floors, the
        targets, whether the clip is the new layer); with ``sign``, that way only."""
        own_q, own_t = own
        rot, at, pivot, axis = fr

        def worst(degrees) -> np.ndarray:
            qc, tc = turned(rot, at, pivot, axis, degrees)
            out = np.full(len(qc), np.inf)
            for oq, ot, s, floor, target, mine in cases:
                w = s if mine else 1.0 - s   # the clip's weight in the blend
                bq = w * qc[:, None] + (1.0 - w) * oq[row[carrier]][None]
                bt = w * tc[:, None] + (1.0 - w) * ot[row[carrier]][None]
                w_par, a_par = parent_frame(w * own_q + (1.0 - w) * oq, w * own_t + (1.0 - w) * ot)
                out = np.minimum(out, (low(w_par[None], a_par[None], bq, bt) - floor - target).min(axis=-1))
            return out
        if worst(0.0)[0] >= 0.0:
            return 0.0
        grid = [0.0] + [d * FADE_STEP * g for d in range(1, int(90 / FADE_STEP) + 1) for g in (1.0, -1.0)
                        if not sign or g == sign]
        v = worst(np.array(grid))
        hit = [i for i in range(len(grid)) if v[i] >= 0.0]
        if not hit:
            return grid[int(np.argmax(v))]
        far = grid[hit[0]]
        near = far - math.copysign(FADE_STEP, far)
        while abs(far - near) > 0.1:
            mid = (near + far) / 2
            near, far = (near, mid) if worst(mid)[0] >= 0.0 else (mid, far)
        return far

    rewrite, lifted = {}, []
    for name in once:
        i, clip = clips[name]
        keyed, length = _keyed(clip), clip.length
        last = name.rsplit("/", 1)[-1]
        fade = FADE_TIMES[1] if ATTACKING[0] in last or last.startswith(ATTACKING[1]) else FADE_TIMES[0]
        n_in = [n for n in range(1, 8) if n * _TICK <= length and _share(n, fade) < 1.0]
        ts = [min(n * _TICK, length) for n in range(8)] + [length]
        cq, ct, cf, cl = posed(clip, ts)
        starts = {}
        for n in n_in:   # each loop's phase fading out as the clip fades in, and the clip alone
            s = _share(n, fade)
            cases = [(pq[:, :, n], pt[:, :, n], s, (1 - s) * pf[:, n] + s * cf[n],
                      np.minimum(np.minimum(pl[:, n], cl[n]), FLOOR_CLEAR), True),
                     (cq[:, n:n + 1], ct[:, n:n + 1], 1.0, cf[n:n + 1], np.minimum(cl[n:n + 1], FLOOR_CLEAR), True)]
            fr = frame(keyed, ts[n])
            starts[n] = (cases, fr, least(cases, (cq[:, n:n + 1], ct[:, n:n + 1]), fr))
        sign = 1.0
        if any(v[2] for v in starts.values()):   # one way through the fade-in
            sign = math.copysign(1.0, max((v[2] for v in starts.values()), key=abs))
            for n, (cases, fr, d) in starts.items():
                if d and math.copysign(1.0, d) != sign:
                    starts[n] = (cases, fr, least(cases, (cq[:, n:n + 1], ct[:, n:n + 1]), fr, sign=sign))
        s_out = [_share(n, FADE_TIMES[0]) for n in range(1, 8)]
        cases = [(fq[:, :, n], ft[:, :, n], s, (1 - s) * cf[8] + s * ff[:, n],
                  np.minimum(np.minimum(fl[:, n], cl[8]), FLOOR_CLEAR), False) for n, s in zip(range(1, 8), s_out)]
        cases.append((cq[:, 8:9], ct[:, 8:9], 1.0, cf[8:9], np.minimum(cl[8:9], FLOOR_CLEAR), True))
        end = 0.0 if last.startswith(DEATHS) else least(   # held at its end as each loop fades in
            cases, (cq[:, 8:9], ct[:, 8:9]), frame(keyed, length))
        ticks = {n: v[2] for n, v in starts.items() if v[2]}
        if not ticks and not end:
            continue
        mags = [abs(ticks.get(max(n, 1), 0.0)) for n in range(8)]   # held to one side, at most FADE_SLEW a tick
        mags += [0.0] * (int(max(mags) / FADE_SLEW) + 2)
        for n in range(1, len(mags)):
            mags[n] = max(mags[n], mags[n - 1] - FADE_SLEW)
        for n in range(len(mags) - 2, -1, -1):
            mags[n] = max(mags[n], mags[n + 1] - FADE_SLEW)
        curve = [math.copysign(m, sign) for m in mags]
        ease_in = max(length - max(FADE_TIMES[0], 1.5 * abs(end) * _TICK / FADE_SLEW), 0.0)   # smoothstep's slope
        scale = [1.0, 1.0]   # the start's and the end's, cut where the clip's own pose would go under

        def angle(t: float) -> float:
            a = scale[0] * float(np.interp(t, [n * _TICK for n in range(len(curve))], curve)) if ticks else 0.0
            if end and t > ease_in:
                x = (t - ease_in) / (length - ease_in) if length > ease_in else 1.0
                a += scale[1] * end * x * x * (3.0 - 2.0 * x)
            return a

        def own_low(t: float, degrees: float) -> float:   # the clip's own lowest point over its floor, turned
            rot, at, pivot, axis = frame(keyed, t)
            qc, tc = turned(rot, at, pivot, axis, degrees)
            fz = next((tr.keys for tr in clip.markers if tr.target == feet and tr.comp == 2), None)
            return float(low(np.array(rot[parent]), np.array(at[parent]), qc, tc)[0]) - (evaluate(fz, t) if fz else rest)

        for side, (lo_t, hi_t) in enumerate(((0.0, min((len(curve) - 1) * _TICK, length)), (ease_in, length))):
            if not (ticks if side == 0 else end):
                continue
            checks = [(t, min(own_low(t, 0.0), FLOOR_CLEAR)) for t in sorted(
                {lo_t, hi_t} | {j * _TICK / 2 for j in range(int(length / (_TICK / 2)) + 1) if lo_t <= j * _TICK / 2 <= hi_t})]
            if any(own_low(t, angle(t)) < floor_ - 1e-4 for t, floor_ in checks):
                cut, keep = 1.0, 0.0   # the largest share of the turn that keeps every tick over (halving)
                for _ in range(10):
                    scale[side] = (cut + keep) / 2
                    if any(own_low(t, angle(t)) < floor_ - 1e-4 for t, floor_ in checks):
                        cut = scale[side]
                    else:
                        keep = scale[side]
                scale[side] = keep
        if not scale[0]:
            ticks = {}
        if not scale[1]:
            end = 0.0
        if not ticks and not end:
            continue
        old = {tr.comp: tr for tr in clip.bones if tr.target == carrier}
        rest_v = (*b.t, *b.q)

        def value(t: float) -> tuple:
            return tuple(evaluate(old[c].keys, t) if c in old else rest_v[c] for c in range(7))

        def place(t: float, ref: tuple | None) -> tuple[tuple, tuple]:
            rot, at, pivot, axis = frame(keyed, t)
            q, tr = turned(rot, at, pivot, axis, angle(t))
            q, tr = tuple(float(c) for c in q[0]), tuple(float(c) for c in tr[0])
            ref = ref if ref is not None else value(t)[3:]
            if sum(x * y for x, y in zip(q, ref)) < 0:
                q = tuple(-x for x in q)
            return tr, q
        spans = ([(0.0, min((len(curve) - 1) * _TICK, length))] if ticks else []) + (
            [(ease_in, length)] if end else [])
        if len(spans) == 2 and spans[1][0] <= spans[0][1]:
            spans = [(0.0, length)]
        new: dict[int, list] = {c: [] for c in range(7)}
        for lo_t, hi_t in spans:
            times = {lo_t, hi_t} | {k[0] for tr in old.values() for k in tr.keys if lo_t < k[0] < hi_t} | {
                t for t in (lo_t + j * _TICK / 2 for j in range(int((hi_t - lo_t) / (_TICK / 2)) + 1)) if t < hi_t}
            for tr in _sampled_track(carrier, length, times, place, grid=[]):
                new[tr.comp] += [k for k in tr.keys if lo_t <= k[0] <= hi_t]
        tracks = [tr for tr in clip.bones if tr.target != carrier]
        for c in range(7):
            kept = [k for k in (old[c].keys if c in old else ())
                    if not any(lo_t <= k[0] <= hi_t for lo_t, hi_t in spans)]
            keys = sorted(new[c] + kept)
            if c not in old and all(abs(k[1] - rest_v[c]) < 1e-7 and not k[2] and not k[3] for k in keys):
                continue
            tracks.append(Track(carrier, c, tuple(keys), old[c].modes if c in old else (0, 0)))
        rewrite[i] = write_clip(replace(clip, bones=tuple(sorted(tracks, key=lambda tr: (tr.target, tr.comp)))))
        lifted.append(name)
    return (append_resources(characters_xbr, rewrite=rewrite) if rewrite else characters_xbr), tuple(lifted)


STAFF_CUT = 0.5
"""How much of a vertex's weight on garret4's staff bones makes it his
staff's (W33, Step 2.161d): LOD 1's staff, 22 vertices on
``staff_center2slide`` in a group of 1,871, weighs on it alone."""


def cut_staff(characters_xbr: bytes, lo: Loadout) -> tuple[bytes, tuple[int, ...]]:
    """W33 on garret4 (Step 2.161d; the 2.161 design's S1: a scale on his
    staff chain would hide a hoe riding it too): ``characters.xbr`` with
    his staff cut from his mesh in every LOD, and how many triangles it
    cut in each: a group skinned to his Axion staff's bones alone
    (``weapons.json``'s mesh bones: LOD 0's group 7, 152 triangles)
    dropped whole, and in any other group each triangle whose every
    vertex weighs more than :data:`STAFF_CUT` on them (LOD 1's 18 on
    ``staff_center2slide``), with the vertices only those used.  His
    bones stay: his clips key the chain, the hoe rides it and the game
    checks ``staff_center2slide`` against the walls (X17).
    :class:`ValueError` names a LOD with no staff to cut (D35)."""
    from azurkit.tools.characters import body_codec

    asset = body_codec.read_asset(characters_xbr, PLAYER)
    staff = {asset.bone(b) for b in lo.default.prop.mesh.bones}
    cut = []
    for n, lod in enumerate(asset.lods):
        before = sum(len(g.triangles) for g in lod.groups)
        lod.groups = [g for g in lod.groups if not set(g.palette) <= staff]
        for g in lod.groups:
            held = {v for v in range(len(g.vertices))
                    if sum(w for b, w in g.skin(v).items() if b in staff) > STAFF_CUT}
            g.triangles = [t for t in g.triangles if not held.issuperset(t)]
            used = {v for t in g.triangles for v in t}
            if held - used:
                g.remove(held - used)
        cut.append(before - sum(len(g.triangles) for g in lod.groups))
        if not cut[-1]:
            raise ValueError(f"W33: {PLAYER}'s LOD {n} has no triangle on his staff "
                             f"({', '.join(lo.default.prop.mesh.bones)}) to cut")
    return body_codec.write_asset(characters_xbr, asset), tuple(cut)


def hide_own(characters: bytearray, body: Body, lo: Loadout) -> int:
    """W33 (Step 2.161b): a body wearing a weapon other than its own loose
    prop's (a farmer with the Axion staff or bare hands) has that prop
    (:func:`loose_props`) skinned to its first own carrier, whose rest
    scale becomes 0, in ``characters`` (edited in place): no clip keys it
    (a mapped bone above it, so the bake keeps no track of it), so the
    prop draws as a point everywhere.  Returns how many groups it hid."""
    prop = lo.default.prop
    groups = loose_props(bytes(characters), body, prop)
    if not groups:
        return 0
    names = [name for name, _ in body.bones]
    if prop.own_carriers[0] not in names:
        raise ValueError(f"W33: body {body.name!r} has no {prop.own_carriers[0]} to hide its {prop.clip} on")
    k = names.index(prop.own_carriers[0])
    _, table = body_at(bytes(characters), body.name)
    table += 4 + struct.unpack_from("<i", characters, table + 4)[0]
    struct.pack_into("<3f", characters, table + 160 * k + 0x4C, 0.0, 0.0, 0.0)
    for group in groups:
        struct.pack_into("<i", characters, group.bones_at, k)
    return len(groups)


# --- W35: Garret's staff moves turn the wearer's arms clear of its chest (Step 2.161g, AZ-696) ---
CHEST_NEAR, CHEST_DEEP, CHEST_HZ = 0.04, 0.01, 30.0
""":class:`Chest`'s test (the re-cut design's probes): a prop vertex
within ``CHEST_NEAR`` (model units) of the body's nearest torso vertex
and deeper than ``CHEST_DEEP`` behind it along that vertex's normal is
inside the body, on a tick of ``CHEST_HZ``."""
CHEST_RUN = 64
"""Prop vertices :meth:`Chest.ticks` measures at once, each run against only
the region's vertices in its box grown by ``CHEST_NEAR`` (Step 2.154:
booblord v4's 47,338 vertices took 1.6 s a tick against them all)."""
_LIMBS = ("arm_", "hand", "fgr", "thumb", "forearm")
_HEAD = ("head", "jaw", "neck", "left_brow", "right_brow")
BUST = (0.029, 0.661, 0.863, 0.0115)
"""A townswoman's bust, of her torso, by her bind (fractions of her height):
in front past y, between two heights, and off the centre line (the probes'
town_female_2 box: y > 0.05, 1.15 < z < 1.50, |x| > 0.02, over 1.739); a
tick counts where a prop vertex is inside the torso or the bust alone."""
BUST_BODIES = "townspeople/female_"
"""The bodies :data:`BUST` tests (the townswomen, booblord's base among them)."""


class Chest:
    """A body's LOD 0 mesh in ``characters_xbr`` posed by the engine model
    (``gltf._engine``, the inverse binds), its torso (each vertex whose
    heaviest bone is no arm, hand, finger, head, neck, hair, sash or vase
    bone, a mapped body's bone by the garret4 bone its role, or its
    nearest mapped ancestor's, plays: the elementals' ``r_arm03``, keylord's
    ``joint38``), a townswoman's bust (:data:`BUST`) and the vertices of its
    ``prop`` (those whose heaviest bone is one of its bones): :meth:`ticks`."""

    def __init__(self, characters_xbr: bytes, body: str, prop):
        import numpy as np

        from azurkit.tools.characters import gltf
        from azurkit.tools.characters.body_codec import read_asset

        asset = read_asset(characters_xbr, body)
        index, _ = body_at(characters_xbr, body)
        self.rig = gltf._Body(body, index, tuple(bone_records(characters_xbr, body)), inverse_binds(characters_xbr, body),
                              (), ())   # its bones and binds alone: _engine reads no clip of the body's
        rig = Rig.read(characters_xbr, body)
        names = [n.casefold() for n in asset.bone_names]
        if body.casefold() in MAPS:   # a limb by its role (garret4's bone names)
            g4 = Rig.read(characters_xbr, PLAYER)
            roles = role_map(rig, g4, TARGETS[body.casefold()])
            plays = [next((g4.bones[roles[a]].name.casefold() for a in (k, *rig.ancestors(k)) if a in roles), n)
                     for k, n in enumerate(names)]
        else:
            plays = names
        rows = []
        for g in asset.lods[0].groups:
            for k, v in enumerate(g.vertices):
                skin = sorted(g.skin(k).items(), key=lambda bw: (-bw[1], bw[0]))[:4]
                skin += [(0, 0.0)] * (4 - len(skin))
                rows.append((v.position, v.normal, [b for b, _ in skin], [w for _, w in skin]))
        self.P = np.array([r[0] for r in rows], float)
        self.N = np.array([r[1] for r in rows], float)
        self.J = np.array([r[2] for r in rows], int)
        self.W = np.array([r[3] for r in rows], float)
        held = {n.casefold() for n in prop}
        self.prop = np.array([names[j] in held for j in self.J[:, 0]])
        other = np.array([names[j] in held or names[j].startswith(("loincloth", "vase", "hair"))
                          or any(a in plays[j] for a in _LIMBS) or plays[j] in _HEAD for j in self.J[:, 0]])
        self.torso = ~other
        tall = height(characters_xbr, read_body(characters_xbr, body)) or 1.0
        y, z0, z1, x = (f * tall for f in BUST)
        P = self.P
        self.bust = self.torso & (P[:, 1] > y) & (P[:, 2] > z0) & (P[:, 2] < z1) & (np.abs(P[:, 0]) > x) & (
            body.casefold().startswith(BUST_BODIES))
        self.G = np.array([np.array(m, float).reshape(4, 4).T for m in self.rig.binds])

    def _posed(self, M, mask):
        import numpy as np

        P, J, W, N = self.P[mask], self.J[mask], self.W[mask], self.N[mask]
        ph = np.c_[P, np.ones(len(P))]
        X = sum(W[:, s, None] * np.einsum("nij,nj->ni", M[J[:, s]], ph)[:, :3] for s in range(4))
        Y = sum(W[:, s, None] * np.einsum("nij,nj->ni", M[J[:, s], :3, :3], N) for s in range(4))
        return X, Y / np.maximum(np.linalg.norm(Y, axis=1), 1e-12)[:, None]

    def ticks(self, clip) -> tuple[int, float]:
        """How many of ``clip``'s ticks (:data:`CHEST_HZ`) put a prop vertex
        inside the torso or the bust (:data:`CHEST_DEEP`), and the prop's
        lowest model z over them (``inf`` with no prop)."""
        import numpy as np

        from azurkit.tools.characters import gltf

        bad, low = 0, math.inf
        if not self.prop.any():
            return 0, low
        regions = [r for r in (self.torso, self.bust) if r.any()]
        for i in range(int(clip.length * CHEST_HZ + 1e-6) + 1):
            M = np.array(gltf._engine(self.rig, clip, min(i / CHEST_HZ, clip.length))) @ self.G
            Q, _ = self._posed(M, self.prop)
            low = min(low, float(Q[:, 2].min()))
            inside = False
            for region in regions:
                B, NB = self._posed(M, region)
                for a in range(0, len(Q), CHEST_RUN):   # a run of prop vertices against the region's vertices
                    q = Q[a:a + CHEST_RUN]              # in its box grown by CHEST_NEAR, where any nearest vertex
                    near = np.nonzero(((B >= q.min(0) - CHEST_NEAR) & (B <= q.max(0) + CHEST_NEAR)).all(1))[0]
                    if not len(near):                   # within CHEST_NEAR lies: each row's answer the full scan's
                        continue
                    diff = q[:, None, :] - B[near][None, :, :]
                    dist = np.sqrt((diff ** 2).sum(-1))
                    j = dist.argmin(1)
                    rows = np.arange(len(q))
                    depth = -(diff[rows, j] * NB[near][j]).sum(-1)
                    inside = inside or bool(((dist[rows, j] < CHEST_NEAR) & (depth > CHEST_DEEP)).any())
            bad += inside
        return bad, low


# --- W34: Balthazar's magic on a mapped body (Step 2.161c; D494; the 2.161 design's M1, S6, W34) ---
def source_style(characters_xbr: bytes, ws: WeaponStyle) -> Style:
    """``ws`` (``clips`` :data:`SOURCE_BUILD`) as a
    :class:`~azurik_mod.patches._player_kit.Style` (Step 2.161c; the 2.161
    design's 3.4: D421's lent picks and windows, which Step 2.159a deleted,
    restored as the generic shape's options): each column the clip
    ``ws.source``'s own build plays there (:attr:`Style.own`,
    :func:`~azurik_mod.patches._player_character.substitutes` on his body:
    Balthazar's attack_1, attack_2 and attack_3 in turn, the jump attack
    his attack_1), baked from his rig under ``ws.dir`` at his length, each
    column at its own Rate; X3's window on a clip (``windows``
    :data:`SOURCE_MARKERS`) from his first damage window's start to his
    last's end (his attack_1 0.463-0.860 of 1.133 s, attack_3 0.930-1.593
    of 2.267; his attack_2 switches none: X3's own 20-50 % of the move);
    ``ws.fx`` the species whose own-build graph W34 clones for the player
    (:func:`magic`)."""
    his = read_body(characters_xbr, ws.source)
    windows = {}
    for clip in his.clips:
        found = damage_windows(characters_xbr, ws.source, clip)
        if found:
            windows[clip] = (min(w.on for w in found), max(w.off for w in found))
    return Style(source=ws.source, dir=ws.dir, picks={}, windows=windows,
                 lengths={c: his.length(c) for c in his.clips}, rate=None,
                 load=functools.partial(_own_clips, ws.source, his.clips), own=his, fx=ws.fx)


def _own_clips(source: str, clips: tuple[str, ...], characters_xbr: bytes) -> dict[str, Clip]:
    return {clip: named_clip(characters_xbr, source, clip) for clip in clips}


@dataclass(frozen=True)
class Magic:
    """What W34 makes of a style's graph on a wearer (:func:`magic`)."""

    key: str
    """The source's default fx, which the player's clone copies."""
    grown: tuple[tuple[str, tuple[float, ...]], ...]
    """M1: the markers that graph binds and the wearer lacks, each with the source's record (its rest), grown on
    the wearer before the bake, so the bake keeps the source clips' tracks on them (``Retarget.markers``)."""
    ridden: tuple[str, ...]
    """S6: the bound markers the graph hangs effects under (their transform some record's DAG parent: Balthazar's
    m_lifedrain, m_balth_lightning and m_activateFireStaff), by name; its switches (m_lifedrainswitch ...) keep
    the source's keys."""
    renames: tuple[tuple[int, str, str], ...]
    """Each transform bound to a bone of the source's the wearer lacks: (its record, its name, the wearer's bone
    playing that bone's role, else its nearest mapped ancestor's): Balthazar's spine_2 on an elemental."""
    grip: str
    """The wearer's bone the ridden markers ride (:func:`grip`)."""
    source_grip: str
    """The source's bone of the same role (Balthazar's ``left_w``)."""
    replaced: bool
    """The wearer has a default fx of its own, which the player's clone replaces (its NPCs keep it)."""
    pivots: tuple[tuple[str, tuple[float, float, float]], ...] = ()
    """Each of :attr:`ridden`'s scale pivot: the record +0x2C of the transform the graph binds to it and hangs its
    effects under (Balthazar's m_balth_lightning (0.155, 0.015, 0.271), the others 0), about which the marker's
    extents scale those effects (``docs/RE_DATA.md``, the bind's T, R and S); :func:`ride` reads it (AZ-691)."""


def magic(characters_xbr: bytes, body: Body, style: Style, xbe: bytes) -> Magic:
    """W34's plan (Step 2.161c) for ``body`` (read after B's bake) playing
    ``style``'s own build with its graph (``style.fx``): the source's
    default fx read on ``xbe``'s node schema, the markers it binds that
    the wearer lacks (M1), those it hangs effects under (S6), the binds to
    a bone of the source's the wearer lacks renamed (to the bone of its
    role, else of its nearest mapped ancestor's: a bind no bone takes
    stays, as on the source a bind to no node of its own does), the
    grips.  :class:`ValueError` names a source without a default fx."""
    source = style.source
    key = fx_edit.default_key(source)
    toc = parse_toc(characters_xbr)
    names = {n.casefold(): i for i, n in named_resources(characters_xbr).items()}
    if key not in names:
        raise ValueError(f"W34: characters.xbr has no {key} to clone")
    graph = Graph(characters_xbr, toc, toc[names[key]], Schema(xbe))
    binds: dict[int, str] = {}
    parents: set[int] = set()
    for r, ro in enumerate(graph.recs):
        if ro is None:
            continue
        if graph.types[r] == "transform" and (n := bind_name(graph.s, ro)):
            binds[r] = n
        if graph.schema.is_a(graph.types[r], "dag") and (p := struct.unpack_from("<i", graph.s, ro + 0x18)[0]) >= 0:
            parents.add(p)
    records = marker_records(characters_xbr, source)
    have = {m.casefold() for m in body.markers}
    grown = tuple((n, rec) for n, rec in records if n in binds.values() and n.casefold() not in have)
    ridden = tuple(n for n, _ in records if any(b == n and r in parents for r, b in binds.items()))
    pivots = tuple((n, next(graph.xform_fields(r)["sp"] for r, b in sorted(binds.items()) if b == n and r in parents))
                   for n in ridden)
    his, mine, g4 = (Rig.read(characters_xbr, n) for n in (source, body.name, PLAYER))
    his_bones, my_bones = [b.name for b in his.bones], {b.name for b in mine.bones}
    held = grip(characters_xbr, body)
    renames = []
    if body.name.casefold() not in TARGETS:   # Step 2.161e: a creature casts from its grip, every such bind there
        renames = [(r, graph.names[r], held) for r, n in sorted(binds.items()) if n in his_bones and n not in my_bones]
    else:
        his_roles = role_map(his, g4, MAPS[source.casefold()])
        by_role = {g: k for k, g in role_map(mine, g4, TARGETS[body.name.casefold()]).items()}
        for r, n in sorted(binds.items()):
            if n in his_bones and n not in my_bones:
                k = his_bones.index(n)
                to = next((mine.bones[by_role[his_roles[a]]].name for a in (k, *his.ancestors(k))
                           if his_roles.get(a) in by_role), None)
                if to is not None:
                    renames.append((r, graph.names[r], to))
    return Magic(key, grown, ridden, tuple(renames), held,
                 grip(characters_xbr, read_body(characters_xbr, source)), fx_edit.default_key(body.name) in names,
                 pivots)


def ride(characters_xbr: bytes, body: Body, style: Style, m: Magic):
    """S6 (Step 2.161c; the 2.161 design's S6): the post hook of the bake of
    ``style``'s clips onto ``body`` (read with M1's markers grown) that keys
    each of ``m.ridden`` in every baked clip, every :data:`CARRY_HZ` tick,
    so an effect born at Balthazar's hand is born at the wearer's: on
    keylord, whose hands hang 0.44 of his height lower, a bolt leaves his
    claw, not the air where Balthazar's hand would be.  Since AZ-691 (Step
    2.202) at the wearer's grip plus k times the marker's offset from the
    source's grip in the source clip (its rest where the clip doesn't key
    it: Balthazar's m_balth_lightning, his stream's and bolts' origin), k
    the wearer's height over the source's (:func:`height`, model units:
    keylord 0.519, town_male_6 0.887, the golem 1.596), its extents
    (components 7-9, which the bind makes the transform's scale,
    ``docs/RE_DATA.md``) k times his, so every effect his graph hangs under
    it (``m.pivots``: the scale about the bound transform's pivot, the
    position less (1 - k) x the pivot) is born k times his gap from the
    hand: keylord's stream 0.49-0.53 m and bolts 1.0-1.8 m off his claw at
    x1 (Step 2.161c's B2), Balthazar's own 0.09-0.25 and 0.42-0.80.  His
    graph's own offsets under the marker are model units of the wearer
    (an fx node's authored point scales with the critter), so scaling the
    marker's offset alone (the 2.161 design's x k) would leave a bolt
    (1 - k) x his hand-to-marker offset off the hand.  Its switches keep
    his keys.  ``None`` with none to ride."""
    if not m.ridden:
        return None
    his, mine = Rig.read(characters_xbr, style.source), Rig.read(characters_xbr, body.name)
    hg, mg = [b.name for b in his.bones].index(m.source_grip), [b.name for b in mine.bones].index(m.grip)
    his_at = {n.casefold(): i for i, n in enumerate(his.markers)}
    my_at = {n.casefold(): i for i, n in enumerate(mine.markers)}
    rest = {n.casefold(): rec for n, rec in marker_records(characters_xbr, style.source)}
    pivot = {n.casefold(): sp for n, sp in m.pivots}
    k = height(characters_xbr, body) / height(characters_xbr, read_body(characters_xbr, style.source))
    marks = [(his_at[n.casefold()], my_at[n.casefold()], rest[n.casefold()], pivot.get(n.casefold(), (0.0,) * 3))
             for n in m.ridden if n.casefold() in my_at]

    def post(_name: str, source: Clip, baked: Clip) -> Clip:
        times = [i / CARRY_HZ for i in range(int(baked.length * CARRY_HZ + 1e-6) + 1)
                 if i / CARRY_HZ < baked.length - 1e-4] + [baked.length]   # as the kit's carry
        last = len(times) - 1
        theirs = [origins(his, source, t)[hg] for t in times]
        ours = [origins(mine, baked, t)[mg] for t in times]
        keyed = {(tr.target, tr.comp): tr.keys for tr in source.markers}
        moved = {k_ for _, k_, _, _ in marks}
        tracks = [tr for tr in baked.markers if not (tr.target in moved and (tr.comp <= 2 or 7 <= tr.comp <= 9))]

        def at(h, rec, c, t):
            return evaluate(keyed[h, c], t) if (h, c) in keyed else rec[c]
        for h, mk, rec, sp in marks:
            for c in (0, 1, 2, 7, 8, 9):
                v = ([ours[i][c] + k * (at(h, rec, c, t) - theirs[i][c]) - (1.0 - k) * sp[c]
                      for i, t in enumerate(times)] if c <= 2 else [k * at(h, rec, c, t) for t in times])
                keys = []
                for i, t in enumerate(times):
                    lo, hi = max(0, i - 1), min(last, i + 1)
                    slope = (v[hi] - v[lo]) / (times[hi] - times[lo]) if times[hi] > times[lo] else 0.0
                    keys.append((t, v[i], slope, slope))
                tracks.append(Track(mk, c, tuple(keys)))
        return Clip(baked.length, baked.bones, tuple(sorted(tracks, key=lambda tr: (tr.target, tr.comp))))

    return post


def _caster(characters_xbr: bytes, body: Body, style: Style, m: Magic):
    """:func:`cast_clips`' keying of one clip of ``body``: a function of a
    clip and its damage windows giving it keyed (``m.ridden`` at its grip,
    :data:`CAST_SWITCH` on over those windows, else X3's)."""
    from azurkit.tools.characters._player_variants import _active, _const

    his, mine = Rig.read(characters_xbr, style.source), Rig.read(characters_xbr, body.name)
    hg, mg = [b.name for b in his.bones].index(m.source_grip), [b.name for b in mine.bones].index(m.grip)
    rest = {n.casefold(): rec for n, rec in marker_records(characters_xbr, style.source)}
    switch = [n.casefold() for n in his.markers].index(CAST_SWITCH.casefold())
    ref = None
    for clip in sorted(read_body(characters_xbr, style.source).clips):
        source = named_clip(characters_xbr, style.source, clip)
        keyed = next((tr.keys for tr in source.markers if tr.target == switch and tr.comp == 2), None)
        on = next((s / CARRY_HZ for s in range(int(source.length * CARRY_HZ) + 1)
                   if keyed is not None and evaluate(keyed, s / CARRY_HZ) >= 0.5), None)
        if on is not None:
            ref = origins(his, source, on)[hg]
            break
    if ref is None:
        raise ValueError(f"W34: {style.source} keys no {CAST_SWITCH} on in a clip of his, so no cast starts there")
    mark = {n.casefold(): i for i, n in enumerate(mine.markers)}
    if CAST_SWITCH.casefold() not in mark:
        raise ValueError(f"W34: {body.name} has no {CAST_SWITCH} grown to cast with")
    rides = [(mark[n.casefold()], rest[n.casefold()]) for n in m.ridden if n.casefold() in mark]

    def cast(motion: Clip, own: tuple[DamageWindow, ...]) -> Clip:
        length = motion.length
        on, off = ((min(w.on for w in own), max(w.off for w in own)) if own
                   else (0.2 * length, 0.5 * length))   # X3's own window (X3_OPENS, X3_CLOSES)
        times = [t / CARRY_HZ for t in range(int(length * CARRY_HZ + 1e-6) + 1)
                 if t / CARRY_HZ < length - 1e-4] + [length]
        at = [origins(mine, motion, t)[mg] for t in times]
        moved = {k for k, _ in rides} | {mark[CAST_SWITCH.casefold()]}
        tracks = [tr for tr in motion.markers if tr.target not in moved]
        for k, rec in rides:
            for c in range(3):
                v = [a[c] + rec[c] - ref[c] for a in at]
                keys = []
                for j, t in enumerate(times):
                    lo_, hi = max(0, j - 1), min(len(times) - 1, j + 1)
                    slope = (v[hi] - v[lo_]) / (times[hi] - times[lo_]) if times[hi] > times[lo_] else 0.0
                    keys.append((t, v[j], slope, slope))
                tracks.append(Track(k, c, tuple(keys)))
        s = mark[CAST_SWITCH.casefold()]
        tracks += [_active(s, on, off, length, 2, 1.0), _const(s, 11, 1.0, length)]
        return Clip(length, motion.bones, tuple(sorted(tracks, key=lambda tr: (tr.target, tr.comp))))

    return cast


def cast_clips(characters_xbr: bytes, body: Body, style: Style, m: Magic,
               clips: tuple[str, ...] | None = None) -> tuple[bytes, tuple[str, ...]]:
    """W34's cast on a creature (Step 2.161e; the 2.161 design's 2.5
    creatures row and sitting row D2: "bolts from its jaw at its bites'
    windows"): ``characters.xbr`` with each of ``body``'s attack clips
    (:func:`attack_clips`; read with M1's markers grown; ``clips``, names
    under the body, in their place: Step 2.204's ``g4/`` timers of a
    clipless body's attack columns, D810) rewritten in
    place, as W22's beam generator keys Balthazar's switch on a clip of
    his: ``m.ridden`` keyed every :data:`CARRY_HZ` tick at its grip plus
    the marker's rest less his grip where his lightning starts (his clip
    that keys :data:`CAST_SWITCH` on, at its first tick on: x1, as S6 was
    before AZ-691), and :data:`CAST_SWITCH`'s translateZ keyed 1 over the clip's own
    damage windows (the first start to the last end), else X3's
    :data:`~azurik_mod.patches._player_character.X3_OPENS` to
    ``X3_CLOSES`` of the clip, its active part 1, so his stream and bolts
    leave the grip at its bites' windows and the creature's own boxes
    hit.  Every NPC wearing the body plays the same clips, and no graph
    of theirs binds those markers.  Returns the clips it rewrote too."""
    from azurkit.tools.characters.retarget import read_clip, write_clip
    from azurkit.core.xbr.append import append_resources

    cast_one = _caster(characters_xbr, body, style, m)
    toc, names = parse_toc(characters_xbr), {n.casefold(): i for i, n in named_resources(characters_xbr).items()}
    rewrite, cast = {}, []
    for clip in attack_clips(body) if clips is None else clips:
        i = names.get(f"characters/{body.name}/{clip}".casefold())
        if i is None or toc[i].tag != "banm":
            continue
        rewrite[i] = write_clip(cast_one(read_clip(characters_xbr, toc[i].file_offset),
                                         damage_windows(characters_xbr, body.name, clip)))
        cast.append(clip)
    if not rewrite:
        raise ValueError(f"W34: {body.name} has no attack clip to cast in")
    return append_resources(characters_xbr, rewrite=rewrite), tuple(cast)


def cast_copies(characters_xbr: bytes, body: Body, style: Style, m: Magic,
                copies: dict[str, tuple[str, Clip]], picks) -> dict[str, tuple[str, Clip]]:
    """W34's cast on a body with no attack clip of its own (Step 2.204,
    D810): ``copies`` (W3's, a pick -> its copy's name and clip,
    :func:`~azurik_mod.patches._player_character.attack_copies` and
    :data:`~azurik_mod.patches._player_character.CAST_DIR`'s) with each
    copy of one of ``picks`` (the clips its attack columns play: a
    flicken's ``ouch_1``, a gem's ``idle``) keyed as :func:`cast_clips`
    keys an attack clip, in the pick's own damage windows, else X3's; the
    pick itself, which its other slots play, stays as it was."""
    cast_one = _caster(characters_xbr, body, style, m)
    return {pick: (name, cast_one(clip, damage_windows(characters_xbr, body.name, pick)) if pick in picks else clip)
            for pick, (name, clip) in copies.items()}


def magic_graph(characters_xbr: bytes, body: Body, style: Style, m: Magic, xbe: bytes,
                fx_xbr: bytes | None = None) -> list[NewResource]:
    """W34's clone (Step 2.161c): the source's default fx (``m.key``) copied
    as the player's clone of ``body``'s, ``characters/<body>/v/fx/
    fx_default`` (:func:`~azurik_mod.assets.fx_edit.clone_key`, which X40
    binds to the player alone), with ``style.fx``'s own-build retune (its W23
    overlay's ``fx`` and ``fx_grafts``: Balthazar's bolts, his drain's box
    and his stream, as his own build plays them) and ``m.renames``'
    binds (an ``anchor`` edit each, Step 2.167a), as
    :func:`~azurik_mod.xbr.append.append_resources` values."""
    from azurkit.tools.characters import _player_variants as variants

    own = variants.overlay(style.fx) if style.fx is not None else None
    clone = fx_edit.Clone(characters_xbr, m.key, xbe, fx_xbr=fx_xbr)
    clone.apply([*(own.fx if own is not None else ()),
                 *({"record": r, "name": n, "type": "transform", "anchor": to} for r, n, to in m.renames)],
                own.fx_grafts if own is not None else ())
    return clone.build(fx_edit.clone_key(body.name))


__all__ = ["BUST", "BUST_BODIES", "CARRIER_MAX", "CAST_SWITCH", "CHEST_DEEP", "CHEST_HZ", "CHEST_NEAR", "COPY", "DEFAULT", "ENDS", "FLOAT", "GOOD", "HELD_SAMPLES", "IN_PLACE",
           "LOOK", "LOOSE", "ODD", "ON_CHAIN", "OWN", "PORTABLE", "PROP_CASTS", "PROP_FAR", "PROP_KICKS", "PROP_GRIP", "PROP_HANDLE", "RIGID",
           "SIZE_BAND",
           "SOURCE_BUILD", "SOURCE_MARKERS", "STAFF_CUT", "TIP_BOX", "TIP_HITS", "WEAPONS_FILE", "WEAPON_GRADES",
           "FIT_COLOURS", "NOT_SEEN",
           "Carriers", "Chest", "Fit", "Grip", "Loadout", "Magic", "Prop", "PropMesh", "Weapon", "WeaponStyle", "add_carriers",
           "attack_clips", "attack_recipe", "carried", "carried_copy", "carriers", "carry_props", "copy_prop", "cut_staff",
           "default_name", "default_weapon", "describe", "fit_turns", "fits", "float_clips", "grade", "grip", "grips", "held_window", "hide_own",
           "lent", "load_weapons", "loadout", "loose_props", "magic", "magic_graph", "moveset", "offers", "pick_sha", "prop_size", "ride", "same_why", "size_of",
           "source_style", "weapons"]

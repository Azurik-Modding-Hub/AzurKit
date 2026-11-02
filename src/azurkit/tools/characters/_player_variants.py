"""Player-model variants: named recipes over a base species' swap (Step
2.137; D332, D354, D359-D361).

A variant is data, not a species, a pack or a layer: a JSON recipe that
names a base species (a usable ``critters_engine`` one), the swap's own
choices for it (its mode, size, scale and sounds, its attack sliders), the
clips it authors (each made by a built-in generator, a pure function of
the vanilla bytes and the recipe's numbers), the ``attacks_anims`` columns
that play them, and the columns X33 carries along the stick.
:func:`~azurik_mod.patches._player_character.apply_player_model` builds
it inside the one ``player model <name>`` layer (``variant=``), so every
check after it (X3, W5, W19, X13, X21, the logic) measures the built
variant as it measures any build.

- **The recipe** (:data:`FIELDS`; :func:`load_variants`, unknown keys and
  values refused by name): ``title``, ``notes`` (the picker's label and
  info), ``base``, ``mode`` (``own`` or ``garret4``; a recipe with
  ``clips``, ``markers``, ``carry`` or ``held`` is own only, since garret4's exact
  gives every column X3's box and garret4's time), ``size``, ``scale``,
  ``sounds``, ``attacks`` (``reach``, ``damage``, ``speed``: any finite
  number, D23; ``balance``, ``ground``, ``through_walls``: true or false,
  the last garret4's ``hitsThroughWalls``, so the player's hits skip the
  game's wall test 0x46070: Step 2.140), ``markers`` (grown
  on the body after B with garret4's record defaults, so no baked clip
  gains a box: the 2.130 critique's C5), ``clips`` ({name: {"generator":
  ..., its parameters}}, stored as ``characters/<body>/v/<name>``,
  :data:`VARIANT_DIR`: a ``/`` name takes a string no pick plays, W3's
  third rule, so the kept columns' clips keep theirs; the ``gltf``
  generator reads a clip made in Blender, with its own hit window and
  Rate: :func:`gltf_clip`, Step 2.158; the ``bake`` generator another
  humanoid body's clip or a built-in's Blender clip retargeted onto the
  body: :func:`baked_clip`, Step 2.164c, D785; any clip's ``seek``, true
  or false, turns the columns playing it to their target at the attack's
  start, X49: :func:`seeking`, Step 2.194b, D762), ``columns``
  ({column: a recipe clip or a base clip}; the roll never; the rest keep
  W3's picks), ``carry`` (X33's columns, with the base's own), ``held`` (columns
  that chain while A or B is held, never carried: X33's held mask, Step 2.153,
  D450), ``rotate`` (X10's ring over
  the recipe's clips; off by default), ``fx`` (edits of the body's
  ``fx/fx_default``, each naming a record by its index, name and type
  and what it changes, Step 2.140; since Step 2.157 made on the player's
  clone, ``characters/<body>/v/fx/fx_default``, which X40 binds to the
  player alone: :mod:`azurik_mod.assets.fx_edit`), ``voice`` (``own``, the base's or
  Garret's as today, or ``silent``: D386, Step 2.141), ``sfx`` ({name:
  {"generator": "whoosh", ...}}, sounds made at build time, or
  {"generator": "wav", "files": [...]}, a WAV a take, bound to the
  ``columns`` it lists, :data:`SFX_GENERATORS`), ``shouts``
  ({"files": [...]}, a WAV a take: its voice under another weapon, Step
  2.183, D705: :func:`unarmed`), ``marker_source`` (the
  body whose marker records ``markers`` grow with: garret4's by default,
  or another's, e.g. spideyzar's ``balthazar_spider`` for the bind names
  of his fx: Steps 2.145, 2.155), ``wavs`` ({role: [WAV,
  ...]}: a :data:`DROP_ROLES` role's sounds, a file a take, Step 2.144;
  both read from :func:`sound_folder`) and ``mesh`` (W24,
  Step 2.142: ``gltf`` {``file``, ``sha256``, ``import``: ``positions``
  by default, or ``topology`` or ``weights``, Step 2.154}, an edited glTF of the
  base's body, user recipes only; ``keep``, bones whose vertices the ops
  leave; ``drop``, bones whose vertices leave the mesh, Step 4.3; ``ops``,
  deform ops: :mod:`azurik_mod.assets.mesh_edit`) and
  ``arms`` ({``out_deg``}: both ``*_arm_1`` turned out in every clip the
  body plays but the recipe's own, W28, Step 2.143: :func:`restyled`)
  and ``jiggle`` (leaf bones on springs baked into every clip but its
  ``still`` ones, cycling in its ``loops``, W29 and W28:
  :mod:`azurik_mod.assets.jiggle`; a recipe's own ``v/`` clips may key a
  jiggle bone, Step 2.168: a real-time spring's swings about its keys, a
  baked one isn't baked in that clip) and ``idles`` (the idle slots' clips,
  ``idle`` the base and ``idle_1``-``idle_6`` the fidgets, each a recipe clip or
  a base clip, filled from ``idle`` on, and ``wait``, the range a fidget's
  wait is drawn from: X11 and X45, Step 2.168, D553;
  :func:`_idles`) and ``slots`` (the clips of its gait and victories,
  ``walk``, ``run``, ``walk_backwards``, ``run_backwards`` and
  ``victory_1``-``victory_6``, since Step 2.164c its jump family,
  ``jump``, ``jump_standing``, ``superjump`` and ``climb_drop``, and since
  Step 2.193 its landing, ``touchdown``, each a recipe clip or a base clip:
  X11 plays them, and W7 times a gait it names by its planted feet, Step
  2.171; a touchdown lasts garret4's 13 ticks, Step 2.193;
  :func:`_slots`) and ``victory_cancel`` (s: a victory ends at the first
  tick that long in with the stick pushed, X46, Step 2.181, D702;
  :mod:`~azurik_mod.patches._player_victory`) and ``fx_ring`` (X38's ring, Step
  2.149: ``false`` off, or its ``slots``, ``arm`` and ``stand``:
  :func:`check_fx_ring`) and ``effects`` (Step 2.167b, D538's E2: effects
  templates by name and the columns that play them, a projectile row
  thrown from the hand by X42: :func:`~azurik_mod.assets.fx_templates.effects`,
  :mod:`~azurik_mod.patches._player_throw`; Step 2.167c, E3: a shield or
  beam row its own graph on X38's bound keys, :mod:`~azurik_mod.patches._player_fx_ring`). No offsets, no game bytes; a downloaded
  recipe is data and never runs code.
- **Its sha** (:func:`recipe_sha`): sha256[:12] of the canonical JSON of
  every field but ``title``, ``notes``, ``voice``, ``sfx``, ``wavs`` and ``shouts`` (and the
  glTF's file path: its sha256 stands for it), so a label edit keeps its
  grade (:data:`VARIANT_GRADES`), and so do its sounds
  (Step 2.72's rule: a body's own sounds aren't on the grading
  checklist); the build log names it, and the sounds' own sha
  (:func:`sounds_sha`) and each WAV's sha256.
- **Its sounds** (Step 2.141; D384, D386): with ``voice`` ``silent`` the
  voice roles bind nothing, ``sfx`` and ``wavs`` add their waves to
  ``fx.xbr`` under ``fx/sound/v/<variant>/`` (:data:`VARIANT_SOUND_DIR`),
  and a drop-in folder (``--player-variant-sounds``, :func:`drop_ins`)
  lays the owner's WAVs over them by role (:data:`DROP_ROLES`,
  :func:`variant_sounds`); the binding is
  :func:`~azurik_mod.patches._player_sounds.variant_roles`.  A base with
  sounds of its own can't take them (X14 binds every slot from one dir).
- **The built-ins** are ``azurik_mod/assets/variants.json``; a user's are
  a file of the same shape (``--player-variant-file``), none named as a
  built-in.
- **A recipe from another** (Step 2.177, D593: booblord_high): ``from``
  names another recipe of its file (itself from none), whose fields it
  takes but its labels, laying over them only :data:`FROM_FIELDS` (its
  ``title``, ``notes``, ``texture_scale`` and ``effects``) and adding its
  ``mesh_ops`` (Step 2.177b, D691: subdivide ops; Step 2.177d, D698: thicken
  ops, and ``{"over": NAME, ...}`` a tube's sides and rings laid over
  that one's) after that one's ``mesh`` ops and its ``texture_ops``
  (Step 2.177d: paint ops after that one's row's), and its ``shapes``
  values over that one's (Step 2.164b: ``{name: {"value": v}}``, a
  shape that one declares) and a ``jiggle`` in place of that one's (Step
  2.164b: its springs tuned), so it follows that one's
  changes; its shape, moves and sounds being that one's, it reads that one's files
  (:attr:`Variant.files`) and, as shipped, takes its W35 fit
  (:func:`fit_sha`), and where its mesh differs its jiggle bones sit where
  that one's build puts them (:func:`parent_of`; finer triangles would
  pull W29's centroids, and with them her springs and her clips' rests).
  Its sha is its whole recipe's.  A user's file may name a built-in there
  (Step X.73, D687: booblord with one effects row a column, a test variant
  that follows her), whose folders it then reads (:func:`files_shipped`).
  ``from`` may list several recipes each from the same one (Step 2.170d, D751:
  booblord_high_human from booblord_high and booblord_human, her body and
  look the one's and her colours the other's, each defined once): it is
  from that one, takes the first as it builds and lays each other's own
  fields over it in turn, then its own; a field two of them lay fails by
  name (:func:`_from_several`).
- **On garret4's own body** (Step 2.170c, D748; Step 2.206, D813): a
  recipe whose base is garret4 takes every field his own body can take,
  made on his own build (``_player_character._apply_garret4``): its
  scale and attack numbers his own sliders', its look, moves, sounds and
  colours on his body in place (only he wears it); what has no meaning
  on him is refused by name (:data:`GARRET4_REFUSED`); none ships.
- **Overlays** (W23, Step 2.140; :data:`OVERLAYS`): a species' own-build
  recipe of clips and columns, built the same way whenever its own-mode
  build wears no variant (the air elemental's thrown wind, D374); not a
  variant, so it has no name, sha or grade of its own.
- **Hair chains** (Step 2.169f, D536's cloth D; :data:`CHAINS`,
  :func:`chain_springs`): ``assets/chains.json`` lists the bodies whose
  hair X41 swings (the girls' ponytails, the townswomen's tails,
  balthazar_airship's five locks) with their ``jiggle.springs`` rows, which
  any build wearing that body with no ``jiggle`` of its own takes, a plain
  species swap and a variant alike (beamlord); not a recipe field, so no
  recipe's sha moves.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass, field, replace
from pathlib import Path

from azurkit.core import fdlibm
from azurkit.tools.characters import fx_edit, fx_templates
from azurkit.tools.characters import jiggle as jiggles
from azurkit.tools.characters import jiggle_rt
from azurkit.tools.characters import synth, textures
from azurkit.tools.characters.characters import Body, body_at, bone_records, marker_records, read_body, track_value
from azurkit.tools.characters.grades import load_grades
from azurkit.tools.characters.mesh_edit import (OPS, PROFILES, SIZES, AtlasOp, BindOp, CutOp, HemOp, IslandOp, MeshSpec,
                                         PushOp, RelaxOp, ReweightOp, RoundOp, ScaleOp, TubeOp,
                                         SubdivideOp, TaperOp, ThickenOp, TuckOp, UnwrapOp, push_frame, shaped)
from azurkit.tools.characters.index_xbr import IndexRecord, add_index_records
from azurkit.tools.characters.retarget import (
    FLT_MAX, MAPS, Clip, Retarget, Rig, Track, _turn, evaluate, grow_markers, named_clip, origins, qinv, qmul, qnorm,
    read_clip, stretched, turned, turned_over, write_clip)
from azurkit.tools.characters.xbox_adpcm import RATE
from azurkit.tools.characters._player_slots import GAIT_TWINS, IDLE_SLOTS, IDLE_WAIT, RECIPE_SLOTS
from azurkit.tools.characters import render
from azurkit.core.xbr.append import NewResource, append_resources, appended
from azurkit.core.xbr.graph import bind_name, lstr, record_offsets
from azurkit.core.xbr.nodes import named_resources, parse_toc

PLAYER = "garret4"
VARIANT_DIR = "v/"
"""Where a variant's clips live under its body: ``characters/<body>/v/<clip>``."""
BUILTIN = Path(__file__).resolve().parent / "variants.json"
"""The built-in recipes."""
LABELS = ("title", "notes")
"""The recipe's fields no build reads, left out of its sha."""
UNGRADED = ("voice", "sfx", "wavs", "shouts")
"""The recipe's sound fields, left out of its sha too (Step 2.72's
rule: a body's own sounds aren't on the grading checklist); the build
log names their own (:func:`sounds_sha`)."""
FIELDS = (*LABELS, "base", "mode", "size", "scale", "sounds", "attacks", "markers", "marker_source", "clips",
          "columns", "carry", "held", "rotate", "fx", "fx_ring", "fx_grafts", "mesh", "arms", "poses", "jiggle",
          "weapon", "effects", "textures", "texture_scale", "colours", "lods", "idles", "slots", "victory_cancel",
          "drain", "shapes", *UNGRADED)
"""A recipe's fields; any other key fails by name.  ``weapon`` (Step
2.161b; D492-D495): the weapon it wears (``_player_weapons``: a name,
``own`` or ``default``), its syntax checked here and its name by the
build; in the sha as ``<name>@<the weapon's sha>``; a recipe naming one
plays it in every column, so it names no clips, columns, carry or held
(Step 2.161g, D585), unless they are a moveset weapon's
(:func:`moveset_moves`: booblord's, Step 2.209, D939: her default the
Axion staff, her spins the pick Booblord spin).  ``effects`` (Step 2.167b, D538's E2): rows of an
effects template and the columns that play it
(:func:`~azurik_mod.assets.fx_templates.effects`: a projectile thrown
from the hand by X42, W30's ``debug`` wearing the template's body; a
shield or beam, Step 2.167c, its own graph on X38's bound keys), each
template in the sha as ``<name>@<the template's sha>``; they stay under
another weapon (they name columns, not clips).  ``lods`` (D537's
field): ``{"shadow": ...}`` (Step 2.166c), the body's shadow LOD (W36):
``false`` none, ``true`` one at
:data:`~azurik_mod.assets.decimate.SHADOW_RATIO`, or a share of LOD 0's
triangles; left out, a one-LOD body past
:data:`~azurik_mod.assets.decimate.SHADOW_MIN` triangles takes one.
``{"ratio": [...], "at": [...], "error_px": p}`` (Step 2.166d, W39):
the body's LODs past LOD 0 cut anew from its final LOD 0, LOD k at most
``ratio[k-1]`` of its triangles (each above 0 and at most 1; at most
:data:`~azurik_mod.assets.lods.PICKED`, the game's four switch cells),
switching at ``at[k-1]`` m (garret4's ``lodThreshold``, any finite
number, D23), and with ``error_px`` each kept within that many screen
lines of the LOD before at its switch distance; ``"ratio": []`` drops
the body's LODs past LOD 0.  The realtime shadow then draws their LOD 1,
so a recipe naming both ``ratio`` and ``shadow`` is refused (:class:`Lods`).
A recipe without a ``mesh`` asks for no LODs (they would grow or cut a
vanilla body every NPC wearing it loads).  ``texture_scale`` (Step 2.177, D680): a power
of two, every material row of the body baked at that many times its
width and height, a row the recipe's ``textures`` paint at its size and
every other from its vanilla texture
(:func:`~azurik_mod.assets.paint.scaled`); 1 by default.  ``colours``
(Step 2.170b, D539, D734: W38 and X47): ``hsv`` and ``swap`` ops on the
textures of the body's material rows (and ``png``, Step 2.203: a row's
texture an edited PNG beside the recipe, :func:`colour_folder`) (an entry with no ``row`` every
row's), made in the player's copy of the body
(:func:`~azurik_mod.assets.paint.write_colours`), so the NPCs wearing it
keep theirs; with or without a mesh, after every other write of the body
(:func:`_colours`).  ``drain`` (Step 2.196, D765, AZ-758):
``{"targets": "nearest" | "all"}``, whom its life drain (X37) takes
life from: the critter its pick lands on (the default) or every critter
its box touches (:func:`drain_targets`).  ``shapes`` (Step 2.164b,
D455): ``{name: {"title": T, "ops": [mesh op names], "value": v}}``, its
shape sliders, each sizing the ``round`` and ``scale`` ops it names (and
its ``below`` ones at a value under 1, Step 2.164d) by
``value`` (1 by default; :func:`~azurik_mod.assets.mesh_edit.sized`) and
times ``--player-shape NAME=X`` (:func:`reshaped`); a shape at 1.0 is
left out of the sha, so a recipe declaring its shapes keeps its grade
(:func:`_shapes`)."""
FROM_FIELDS = (*LABELS, "texture_scale", "effects", "mesh_ops", "texture_ops", "colours", "shapes", "jiggle")
"""What a recipe ``from`` another lays over that one's fields (the module
docstring): its look's resolution, its effects rows (Step X.73: they name
columns, not clips), its ``colours`` (Step 2.170b: the player's copy
recoloured), its ``mesh_ops``, subdivide ops added after that
one's (Step 2.177b: finer triangles where her forms curve) and since Step
2.177d thicken ops and a tube's resolution laid over (:data:`FROM_OPS`,
:data:`OVER_FIELDS`), its ``texture_ops``, paint ops added to that
one's rows (Step 2.177d), and its ``shapes``, the values of the shape
sliders that one declares (Step 2.164b, D455: ``{name: {"value": v}}``,
its titles and ops that one's), and its ``jiggle``, in place of that
one's whole (Step 2.164b, its skeptic's G4: her springs tuned in the
Variants page's Jiggle tab, which copies that one's at the first edit;
its bones' shapes name that one's mesh ops), not its shape, moves or
sounds."""
GARRET4_REFUSED = {"mode": ("garret4", "garret4's exact is his own build already"),
                   "size": ("garret4", "he stands at garret4's height already"),
                   "sounds": ("garret4", "his own sounds are Garret's already")}
"""What a recipe on garret4's own body can't ask (Step 2.206, D813, which
opened every other field; Step 2.170c, D748 took only its colours): each
field's value with no meaning on him, and why.  So is ``fx_ring``
(:data:`G4_NO_RING`)."""
G4_NO_RING = ("X38's ring copies a swapped body's own ranged attacks' effects; his are his staff's, which his own "
              "build plays")
FROM_OPS = ("subdivide", "thicken")
"""The mesh ops a recipe ``from`` another adds (its shape is that one's:
finer triangles, a cloth's thickness)."""
OVER_FIELDS = ("sides", "rings")
"""What a recipe ``from`` another's ``mesh_ops`` entry ``{"over": NAME,
...}`` lays over that one's tube of that name (Step 2.177d, D698: her
ponytail rounder; its path, radii and weights that one's)."""
ATTACK_FIELDS = ("clips", "columns", "carry", "held", "rotate", "markers", "attacks")
"""A recipe's moveset (Step 2.161g; D585, D592): the fields a weapon other
than its own drops (:func:`unarmed`) and its moveset weapon lends another
body (:func:`lend`, ``weapons.json``'s ``variant`` style).  Its look
(mesh, jiggle, arms, size, scale), voice and ``wavs`` stay with it; its
``sfx`` (its moves' whooshes) go under another weapon (:func:`unarmed`),
its ``shouts`` playing there instead, and stay its own body's under a lent
one (X14 binds one dir)."""
MOVES = ("clips", "columns", "carry", "held")
"""The fields that play a recipe's own moves, which a recipe naming a
weapon leaves out (Step 2.161g, D585) unless they are a moveset weapon's
(:func:`moveset_moves`)."""
MOVESET = (*ATTACK_FIELDS, "sfx")
"""A recipe's whole moveset, as :func:`unarmed` drops it under another
weapon: its moves, attack numbers and switches, and its moves' whooshes."""


def moveset_moves(recipe: dict, of: str = "") -> bool:
    """Whether ``recipe`` may keep its :data:`MOVES` beside a ``weapon`` it
    names, the moveset weapon's pick playing them (Step 2.209, D939:
    booblord's default the Axion staff, her spins Booblord spin): it is a
    moveset weapon's built-in recipe or one ``from`` it (``of``, that
    recipe's name; ``weapons.json``'s ``variant`` styles, read raw: the
    weapons' loader reads the built-ins), else it holds such a recipe's
    whole :data:`MOVESET` as it builds (a copy of her recipe: ModelKit's
    shape base, a pasted one), so an edit of them is refused under a weapon
    (2.209's review, 2: it would build in no pick).  New from this and
    ``model edit --from`` leave the weapon out (:func:`own_recipe`)."""
    from azurkit.tools.characters._player_weapons import WEAPONS_FILE

    styles = json.loads(WEAPONS_FILE.read_text(encoding="utf-8")).get("styles", {})
    names = {s.get("variant") for s in styles.values() if isinstance(s, dict)}
    if of in names:
        return True
    doc = json.loads(BUILTIN.read_text(encoding="utf-8"))
    return any(isinstance(n, str) and isinstance(doc.get(n), dict) and all(
        recipe.get(k) == recipe_of(doc, n, "built-in")[0].get(k) for k in MOVESET) for n in names)


def own_recipe(recipe: dict) -> dict:
    """``recipe`` (a built-in's as it builds) made a recipe of one's own (New
    from this's own copy, ``model edit --from``): a ``weapon`` over its
    :data:`MOVES` left out, so they and its attack numbers play as its
    default, its own to edit, and no later change of the built-in's moves
    refuses it (2.209's review: under booblord's Axion staff a copy's moves
    and attack numbers built in no pick but a Bare hands its Weapon box
    called one), and its ``notes`` with it (Step 2.209's looks, 3: hers
    say she carries the staff; no sha reads them; New from this keeps a
    user's own, :func:`~azurik_mod.authoring.variant_library.own_copy`)."""
    if recipe.get("weapon") in (None, "default", "own") or not any(recipe.get(k) for k in MOVES):
        return recipe
    return {k: v for k, v in recipe.items() if k not in ("weapon", "notes")}


SHOUT = "shout"
"""The name a recipe's ``shouts`` play under (``<dir>/shout``, ``shout_a``
..., a WAV a take), so no ``sfx`` takes it."""
VOICES = ("own", "silent")
"""``voice``: the base's sounds as the swap binds them (Garret's where it
has none, D232), or none in the voice roles (D386)."""
VARIANT_SOUND_DIR = "fx/sound/v/"
"""Where a variant's sounds live in ``fx.xbr``: ``fx/sound/v/<variant>/<name>``
(no vanilla key starts so, in any archive or either index.xbr)."""
DROP_ROLES = ("hurt", "death", "idle", "taunt", "land", "roll", "jump", "footstep", "fall", "climb")
"""The roles a recipe's ``wavs`` or a drop-in WAV may name besides a
recipe's ``sfx`` (:func:`~azurik_mod.patches._player_sounds.variant_roles`
binds them; ``fall``, a long fall's landing, and ``climb``, the ledge
hoist and the climb over a ladder's top: Step 2.144, D406, D408)."""
from azurkit.tools.characters.content import ROOT as CONTENT_ROOT
SOUNDS = CONTENT_ROOT / "sounds"
"""The built-ins' WAVs, ``sounds/<variant>/`` (their origin and licence in
its ``README.md``)."""
_WAV_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.wav\Z", re.IGNORECASE)
TAKES = 20
"""A name's takes the binder tries: ``<name>`` and ``<name>_a`` ..
``_s`` (0x4B680, ``cmp ebx, 0x14`` at 0x4B71F)."""
KEY_MAX = 255
"""The longest key 0x4B680 formats (``%s/%s_%c`` into a 256-byte stack
buffer: ``sub esp, 0x118`` at 0x4B686, ``lea esi, [esp + 0x18]``
[inferred: its exact size])."""
_TAKE = re.compile(r"(?P<name>[a-z][a-z0-9_]*?)(?:_(?P<take>[a-s]))?\Z")
ATTACKS = ("reach", "damage", "speed", "balance", "ground", "through_walls")
"""The recipe's ``attacks`` fields: the swap's attack sliders and switches
(``through_walls``: garret4's ``hitsThroughWalls``, Step 2.140)."""
FX_FIELDS = ("record", "name", "type", "set", "links", "inherit", "material", "parent", "texture", "anchor", "mesh")
"""An ``fx`` edit's fields (Step 2.140, D385): the body's ``fx/fx_default``
record by its index, name and type (both checked, so an index alone never
retunes another record: the airship's two pEmitterShape1s) and what it
changes, one or more of: ``set``, the attributes it sets by the type's own
names; ``links`` (Step 2.145, D416), edits of the record's own link list
(:data:`LINK_FIELDS`), each naming a link by its ``index`` (a link writes
its destination's plug ``curve(source x weight) x factor`` each update,
0x663B0); ``inherit``, a transform's inherit mode (record +0x28, one of
:data:`~azurik_mod.assets.fx_edit.INHERIT_MODES`: 1 keeps only the parent's
carriage of its anchor, so the child stands upright and unscaled; 3
faces the camera, Step 2.157); ``anchor`` (Step 2.167a, D538), a
transform bound to the wearer's marker of that name (and renamed so), the
holder an effect template hangs under; ``material`` (Step 2.146, D416), a
platform's material rows (:data:`~azurik_mod.xbr.render.MATERIAL_FIELDS`:
``opacity``, ``alpha_ref``, ``blend``), the rows its meshes name and no
other mesh of the graph does (the material's opacity caps gameVisible's,
a float opacity scale: AZ-631).  Since Step 2.157 (D446) every edit is
made on the player's clone of the graph and its copies
(:class:`~azurik_mod.assets.fx_edit.Clone`), so the body's NPCs keep
theirs, and an edit may also set a DAG record's ``parent`` (a record
before it) and a ``texture`` (:data:`TEXTURE_FIELDS`: a renderer's, or a
platform material's ``stage``, made new by a ``recolor`` of the one it
draws or a ``png``, in its ``format``), and a recipe's
``fx_grafts`` (:data:`GRAFT_FIELDS`) add another graph's records to the
clone: a named graft (:data:`~azurik_mod.assets.fx_templates.GRAFTS`)
or records ``from`` a graph, each set's roots under its ``parent``; a
grafted record's index is the graph's record count plus its place.
Since Step 2.155e (D525) a platform's ``mesh`` ({``gltf``: {``file``,
``sha256``}}, a ``.glb``) draws a static glTF's mesh in place of its
own (:mod:`~azurik_mod.assets.fx_mesh`); a ``png`` or ``gltf`` file is
in :func:`fx_folder`."""
TEXTURE_FIELDS = ("recolor", "png", "stage", "format")
"""An ``fx`` edit's ``texture`` fields (Step 2.157): one of ``recolor``
({``ramp``: [[r, g, b] ...] or [[t, r, g, b] ...], ``gamma``, ``gain``})
and ``png`` ({``file``, ``sha256``}, in :func:`fx_folder`), and
``stage`` (a platform's material stage, 0 by default) and ``format``
(``dxt1``, ``dxt3`` or ``bgra8``; the source texture's by default)."""
GRAFT_FIELDS = ("template", "from", "parent")
"""A ``fx_grafts`` entry's fields: ``template`` (a name) or ``from``
({``archive``: characters or fx, ``key``, ``records``}), and ``parent``."""
LINK_FIELDS = ("index", "dst", "dst_plug", "weight", "factor")
MATERIAL_FIELDS = tuple(render.MATERIAL_FIELDS)
"""An ``fx`` edit's ``material`` fields (Step 2.146): ``opacity`` and
``alpha_ref`` (any finite number, D23) and ``blend`` (a whole number)."""
"""An ``fx`` edit's link edit: the link's ``index`` in the record's list,
and one or more of its destination record ``dst``, the destination's
attribute ``dst_plug`` (by name), its ``weight`` and its ``factor``; its
source plug and curve stay."""
ROLL = "roll forward"
_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
VARIANT_GRADES: dict[tuple[str, str], tuple[str, str]] = load_grades(BUILTIN.parent / "variant_grades.json",
                                                                     ("variant", "sha"))
"""Each built-in variant's grade by (name, recipe sha12), from the xemu
sitting of that recipe's build (D242: a grade belongs to a build).  Step
2.137's (beamlord 085f9443029d green, booblord c692eadc1dda yellow) went
with their v1 recipes, and Step 2.140's beamlord 184d0d37f5f6 (yellow:
his beams through, but no dome on the nova, AZ-631) with his v2; Step
2.145's v3 (the dome keyed) stays yellow, its dome still not drawn.  Step
2.134b's sitting saw booblord 3706a604000b's sash swing in all five spins
(green, D425); that grade went with her v2 shape, and Step 2.143's
sittings saw her v3 119336410952 (its springs since AZ-648): yellow,
its skeptic's R1-R3 unseen; Step 2.156's sittings saw her v3 on X41's
springs at D508, 50de4082d29a: yellow, her run starts (AZ-678) and the
owner's look to come; Step 2.156b's sitting saw the run-start kick on
a3404eea2d92: yellow, the owner's look to come; Step 2.174's saw her
landings grow with the fall on 28e6b20cafa1: yellow, the same; Step
2.168's saw her idles on 6f79a8b0b730: yellow, those and look_back's arm
by her bust (D551); its fix re-authored look_back, bust_bounce's reach
under her bust and sash_fix's way back to her hip so no arm or hand
passes into her bust or hips, unseen until their re-sit; Step 2.171's
sitting and its reach re-run saw her moves (her gait, whip and victory
in her slots and casts) and those idles on 75b112a9a92e: yellow,
50de4082d29a's reasons and her moves' look still the owner's; its
second sitting, skeptic and re-run saw the owner's D583 and D584 (her
clips and springs retuned) on c73690f2c0cf: yellow, her whip's short
tail in her build, her hand spin's and whip's small gain and a 6 m
landing's crouch; Step 2.169b's sitting saw her sash's walled springs
on e3611ddbb8ae: yellow, her steady run, her stops at 60 fps and in
Europe and a long idle unseen, the sash's depth into her legs past the
design's, the owner's look to come.  Those grades went with her v3
shape, and her v4 (Step 2.154, D631: round 13b's R13j, the owner's
slider set refined1 with its last refinements) was green: Step 2.154's
land sittings saw 85c4cc0d7a39, and Step 2.166c's saw its build with
W36's shadow LOD (the recipe unchanged); Step 2.171's re-fit sitting saw
her moves on it, 13c01e172027, green, on the bytes before W36 (ISO
4601e5b565fb; by 2.166c's precedent the grade carried to W36's bytes).
Step 2.169b's re-fit sitting saw her sash's springs on her v4 without
those moves, 1b4dd48d5f16: green.  The combine sitting saw her v4
with both, the moves and the sash, 55dbca8fef44, against the moves
alone: green, her sash crossing her thighs in her own gaits open (its
skeptic: the sash's never-inside-her-legs row fails as written there);
Step 2.169b's gait fix keys the sash's first links out over her thighs
in her walk and run clips: 584ed2eeaedc, green by its sitting.
Step 2.177's sitting saw booblord_high 4391ad5d69fe (hers at
texture_scale 2, on her 85c4cc0d7a39): green; she follows booblord's
recipe, so a change of hers leaves her unseen (D242): on 584ed2eeaedc
she is 9e027ed6c2e4, green by its re-sit.  Step 2.177b's sitting saw her
smoother forms on it (round 2's pick with its judge's F1 and F2),
0c0e4e11d3d8: green.  Step 2.177c's sitting saw her bust's normals
weighed by angle (the owner's D695: dark specks on her bust's side),
10fbe068dccf: yellow, one crack notch by her top's edge darker in game.
Step 2.181's victory_cancel (X46: her victory ends at a push of the
stick 0.5 s in): booblord df3deaddaab8, unseen until its sitting, and
booblord_high with both, unseen until its sitting.
Step 2.180's rest on her hand (W37) and its recheck sitting: booblord
f16ddfab9731, green.  Step 2.177d's sitting and its recheck saw
booblord_high's round 3 on it (D721: her ponytail's rings, her sash's
thickness, her face's paint), e928d4f4a860: yellow, a step in the sash's
edge below her belt (AZ-735) and 10fbe068dccf's notch still open.
Step 2.168r re-fits her idles on v4 with three more keyed bones, rounds
3-8's clips, and turns her sash out of her legs in the hit and fall
clips she borrows (AZ-727), on Step 2.180's rest on her hand, her pendant
hung as one piece: 663c2532b172, green by its sitting and recheck (the
recheck on the rebased bytes); booblord_high with it, 5a357b40c2e2,
yellow: she boots and fidgets, her look e928d4f4a860's.
Step 2.146's beamlord 4f76bd7e62c4 (v3 with the dome's material at
opacity 1.0) was green: its sitting saw the dome draw; Step 2.135's
sitting saw X36's sets and X37's drain on v3's 222fcdaf631d (yellow
then for the dome alone); X36 and X37 change no recipe field, so its
lines joined his green note.  Step 2.157's sitting saw beamlord v4
(the electric-blue bolts and the electric shield on the nova, on the
player's clone) fail the look as first tuned (a1daf7365cdb: a dotted
beam, a faint disc at his feet) and pass it retuned: 25d6b762f282 is
green, its skeptic's corrections and R-CAM in its note.  Step 2.153's
sitting and record saw v5 95deba405c89 (speed 2.0, damage 1.0, held,
the air blast, the drain at 100 %): yellow, its drain's misses
(AZ-663).  Step 2.153b's sitting and record saw v6
36c9d143c3de (the bolt from his hands, the blast held to the floor
where he lands, the nova's fade, the 24 m drain box): yellow, its
floor dome not drawn (AZ-669).  Step 2.153c's sitting and record saw
the same recipe's builds with the blast's aim keyed about its pivot
(the generator's, not the recipe's): the floor dome round his feet;
still yellow, for the drain's halt on a deleted target (AZ-682).
Step 2.153d's sitting and record saw them with X37's identity check
(the generator's again): no halt in 7 deletions, green.  Step 2.196's
sitting saw D782's ``drain`` (``targets`` ``all``: his area drain kept,
a red stream from each enemy it drains), 3d8a492822a6: green (it
landed; with Step 2.194b's seeking beams it is 628f6d09ad7b, below).
Step 2.170b's sitting saw booblord_human 8db2978324cb, her colours in
the player's copy of her body: her daylight eyeshadow white (its
skeptic's F1); its record's re-run saw the fix, 7ccd281aec80: green.
Step 2.169c's rebase sitting saw her on booblord's ponytail,
86157db7fcb6: her bones booblord's tick for tick, her colours as
before: green.
Step 2.190's sitting saw them with her idles' wait [10, 10], the game's
rhythm: booblord a61353495e47 and booblord_human 3b242581ba4d green,
booblord_high 6b39ae17a288 yellow (505a7cc1b7fd's open items).
Step 2.170d's sitting saw booblord_high_human (booblord_high's body,
booblord_human's colours) as a2deb7556d0f, her characters.xbr the same
as ac1b0ec2b57e's on Step 2.190's idle wait: yellow (booblord_high's
open items).
Step 2.188's record sitting saw booblord's sash and finger poses and
booblord_high's notch normals on recipes before Step 2.190's rhythm,
booblord 7d99519d1344 and booblord_high 3bdaf4113e47: green (her
landing's back flap clear of her legs, her front flap 36 mm in her
thighs, sit_cross's flap over her crossed legs, three fingertips at the
pinch, the lower notch's shade back); neither recipe landed, so their
keys went with the step's rebase onto Step 2.190.  Its second rebase's
sitting saw the rebased recipes (its poses and notch normals on Step
2.190's rhythm): booblord 16b2c0a85a7f, booblord_high 71ababada355 and
booblord_human 1e885f8583be green.  Its third rebase's sitting saw
booblord_high_human b5b700149553 (those normals and poses with
booblord_human's colours): green.
Step 2.191's sitting and its record re-run saw booblord's V-sign
victory (D750) on recipes before Step 2.188's poses, booblord
30563e4d3ac1, booblord_high a9d039886f8b, booblord_human f833b25444d4
and booblord_high_human c1ec1b37c1f2: yellow (AZ-753, AZ-754, AZ-755);
none landed, so their keys went with the step's rebase onto Step 2.188.
Its rebase's sitting saw the rebased recipes (the V-sign on Step 2.188's
poses): booblord a64e506b5376, booblord_high 2bde646d4745,
booblord_human 0c1a625c0d71 and booblord_high_human c3a4c8c07abe yellow
(AZ-754, AZ-755; AZ-753 accepted by the owner, D753).
Step 2.166d's sitting saw its LODs (W39: a LOD 1 at 0.3 within a pixel at
9 m, which her shadow draws too) on recipes before Step 2.191's victory,
booblord 802333cd54ea, booblord_high 04ecf15b37f8, booblord_human
fa9324ecbab7 and booblord_high_human 7d5a971ef0ad: the switch at 9 m and
LOD 1 read as her; none landed, so their keys went with the step's
rebase onto Step 2.191, whose rows saw booblord f58679be4e2a,
booblord_high 57521e6f7d6f, booblord_human 8d6f54bb1b33 and
booblord_high_human 7b0fd8fda453 switch as before (and the switch as
played, no pop): yellow, for Step 2.191's AZ-754 and AZ-755.
Step 2.169d's sitting saw her ponytail out of her arms (her whip's
tail, her climb's drop, lying dead in die_2) on recipes before Step
2.191's V sign, booblord f70bebd15ce1, booblord_high 241068a6fb6a,
booblord_human 9cea0c0408aa and booblord_high_human 604cc5f1b074 (none
landed); its record re-run saw them on Step 2.191 (957ba9544721,
510a3266564c, a4bb2aba5cf0, c401a01086d1, none landed either) and its
rebase rows on Step 2.166d's LODs, booblord 0d4132ceb337, booblord_high
822de5670d68, booblord_human 75a1190acc97 and booblord_high_human
01551784dc36: yellow, her tail standing 30 deg up off the floor as she
lies dead (AZ-762) and AZ-749.
Step 2.194b's sitting and its record pass saw beamlord's beam and sweep
seek (D762, X49) on 72d7d398adfc, his recipe before Step 2.196's drain:
green; it never landed, so its key went with the stack onto Step 2.196,
whose re-grade sitting saw both, the seeking beams and the drain with
its streams, on 628f6d09ad7b: green.  One grade a line in
``assets/variant_grades.json`` (Step X.85; :mod:`azurik_mod.assets.grades`)."""


def _num(where: str, value) -> float:
    """``value`` as a finite number (D23: never clamped; NaN and inf
    refused as :func:`~azurik_mod.patching.spec.finite_slider_value`
    refuses them)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where}: {value!r} is not a finite number")
    return float(value)


def _positive(where: str, value) -> float:
    """A length or count that divides: above 0 (its encoding can't hold
    a clip of no length)."""
    value = _num(where, value)
    if value <= 0:
        raise ValueError(f"{where}: {value:g} must be above 0")
    return value


def _vec(where: str, value, n: int) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != n:
        raise ValueError(f"{where}: {value!r} is not a list of {n} numbers")
    return tuple(_num(f"{where}[{i}]", v) for i, v in enumerate(value))


def _keys(where: str, given: dict, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> None:
    if not isinstance(given, dict):
        raise ValueError(f"{where}: {given!r} is not an object")
    unknown = sorted(set(given) - set(required) - set(optional))
    missing = [k for k in required if k not in given]
    if unknown:
        raise ValueError(f"{where}: unknown key {', '.join(map(repr, unknown))}")
    if missing:
        raise ValueError(f"{where}: missing {', '.join(map(repr, missing))}")


def _index(where: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{where}: {value!r} is not a record index")
    return value


def _string(where: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: {value!r} is not a name")
    return value


def _file(where: str, value) -> str:
    """A recipe's file field: a file in the recipe's folder (or one below
    it), as ``mesh_edit._buffer`` holds a glTF's buffers beside it, so a
    recipe someone hands you reads nothing outside its folder (D992's
    SEC-14): a relative POSIX path, no empty, ``.`` or ``..`` part, no
    ``\\``, ``:`` (a drive, a URL's scheme) or NUL."""
    name = _string(where, value)
    if name.startswith("/") or any(c in name for c in "\\:\0") or {"", ".", ".."} & set(name.split("/")):
        raise ValueError(f"{where}: {name!r} is not a file in the recipe's folder (a relative path, no '..')")
    return name


# --- the generators -------------------------------------------------------
@dataclass(frozen=True)
class Generator:
    """A built-in clip generator: ``check(where, params)`` refuses a
    parameter by name (no game data), ``make(characters, body, params,
    markers)`` returns the clip for ``body`` (its marker indices
    ``markers``, the grown ones included), :class:`ValueError` naming
    what of the body it lacks."""

    check: object
    make: object


RAMP = 0.01
"""How long (s) an authored box takes to open or close: its active part
crosses 0.5 at the recipe's time, a smooth step with finite tangents
(no vanilla clip holds a held, non-finite tangent, so none is written)."""


def _const(target: int, comp: int, value: float, length: float) -> Track:
    return Track(target, comp, ((0.0, value, 0.0, 0.0), (length, value, 0.0, 0.0)))


def _active(target: int, on: float, off: float, length: float, comp: int = 11, value: float = 1.0) -> Track:
    """``target``'s active part (or component ``comp``): 0, ``value``
    from ``on`` to ``off`` (s), 0."""
    h = RAMP / 2
    keys = [(0.0, 0.0), (max(on - h, 0.0), 0.0), (on + h, value), (off - h, value), (min(off + h, length), 0.0),
            (length, 0.0)]
    out = []
    for t, v in keys:
        if out and t <= out[-1][0]:
            continue
        out.append((t, v, 0.0, 0.0))
    return Track(target, comp, tuple(out))


def _box_tracks(target: int, length: float, on: float, off: float, centre, extents, q=(0.0, 0.0, 0.0, 1.0)
                ) -> list[Track]:
    """A marker keyed as a constant box (``centre``, ``extents`` with
    length 0.5, rotation ``q``), on from ``on`` to ``off``: every part
    keyed, so the marker's defaults (garret4's, when grown) play no part."""
    return ([_const(target, c, v, length) for c, v in enumerate(centre)]
            + [_const(target, 3 + c, v, length) for c, v in enumerate(q)]
            + [_const(target, 7 + c, v, length) for c, v in enumerate(extents)]
            + [_const(target, 10, 0.5, length), _active(target, on, off, length)])


def _rz(a: float) -> tuple[float, float, float, float]:
    return (0.0, 0.0, fdlibm.sin(a / 2), fdlibm.cos(a / 2))


def _drz(a: float) -> tuple[float, float, float, float]:
    """d Rz(a) / da."""
    return (0.0, 0.0, 0.5 * fdlibm.cos(a / 2), -0.5 * fdlibm.sin(a / 2))


def _rx(a: float) -> tuple[float, float, float, float]:
    return (fdlibm.sin(a / 2), 0.0, 0.0, fdlibm.cos(a / 2))


def _ry(a: float) -> tuple[float, float, float, float]:
    return (0.0, fdlibm.sin(a / 2), 0.0, fdlibm.cos(a / 2))


def _dry(a: float) -> tuple[float, float, float, float]:
    """d Ry(a) / da."""
    return (0.0, 0.5 * fdlibm.cos(a / 2), 0.0, -0.5 * fdlibm.sin(a / 2))


def _turning(target: int, comps: tuple[int, int, int, int], times: list[float], angle, rate: float,
             value, slope) -> list[Track]:
    """Four tracks (``comps``) of a quaternion ``value(angle)`` keyed at
    ``times`` with its exact tangents (``slope(angle)`` x ``rate``, the
    angle's change a second): the Hermite 0xD8300 scales them by the
    keys' spacing, and the pose normalises the result."""
    keys = [[] for _ in range(4)]
    for t in times:
        a = angle(t)
        q, dq = value(a), slope(a)
        for r in range(4):
            keys[r].append((t, q[r], dq[r] * rate, dq[r] * rate))
    return [Track(target, comps[r], tuple(keys[r])) for r in range(4)]


def _check_t_spin(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "length", "turns", "active", "box"), ("hop",))
    _positive(f"{where}.length", p["length"])
    _num(f"{where}.turns", p["turns"])
    _vec(f"{where}.active", p["active"], 2)
    _keys(f"{where}.box", p["box"], ("centre", "half"))
    _vec(f"{where}.box.centre", p["box"]["centre"], 3)
    _vec(f"{where}.box.half", p["box"]["half"], 3)
    if "hop" in p:
        _num(f"{where}.hop", p["hop"])


SASH = "loincloth_"
"""The sash's bones (town_female_2's ``loincloth_front_1``-``5`` and
``loincloth_back_1``-``5``), which :func:`t_spin` and :func:`hand_spin`
hang and swing."""
SASH_FLARE = math.radians(60.0)
"""How far (rad) each sash chain's first bone swings out along its own
side mid-spin (the front chain forward, the back chain back): a strip at
two turns in 0.4 s would fly almost level (D371, Step 2.134a's defaults,
kept out of the recipe so its sha holds)."""
SASH_LAG = math.radians(30.0)
"""How far (rad) the chains trail against the spin's turn mid-spin."""
SASH_LIFT = math.radians(25.0)
"""How far (rad) the chains lift in a stomp's fall (no turns)."""


def _sash(characters: bytes, body: Body, bones, length: float, turns: float) -> list[Track]:
    """The sash's tracks in a :func:`t_spin` or :func:`hand_spin` clip
    (Step 2.134a, AZ-636; D371, the owner: "swing with her"; AZ-619: at
    its bind it stuck out stiff about 1 m ahead of and behind her hips):
    each :data:`SASH` bone the body's
    ``idle`` keys holds its ``idle``'s t 0 rotation (its hang), and each
    chain's first bone (``*_1``) swings from it by R = Rz(-lag e)
    Rx(+-flare e) in the body's frame, q = (P JO)^-1 R (P JO) q_hang with
    P its parent's bind world, so the swing turns with her: with
    ``turns``, e eases 0 -> 1 over the clip's first quarter and back over
    its last (zero tangents), :data:`SASH_FLARE` out along its side and
    :data:`SASH_LAG` against the turn; without, a :data:`SASH_LIFT` lift
    from 0.35 to 0.7 of the clip, the hop's fall.  Each clip so starts
    and ends on the hang.  None on a body with no idle or no sash."""
    if "idle" not in body.clips:
        return []
    keyed: dict[int, dict[int, tuple]] = {}
    for tr in named_clip(characters, body.name, "idle").bones:
        if 3 <= tr.comp <= 6:
            keyed.setdefault(tr.target, {})[tr.comp - 3] = tr.keys
    sash = [k for k, b in enumerate(bones) if b.name.casefold().startswith(SASH) and k in keyed]
    if not sash:
        return []
    world = Rig.read(characters, body.name).world
    spin = (turns > 0) - (turns < 0)
    ease = (((0.0, 0.0), (0.25, 1.0), (0.75, 1.0), (1.0, 0.0)) if turns
            else ((0.0, 0.0), (0.35, 0.0), (0.525, 1.0), (0.7, 0.0), (1.0, 0.0)))
    out: list[Track] = []
    for k in sash:
        b = bones[k]
        hang = tuple(evaluate(keyed[k][r], 0.0) if r in keyed[k] else b.q[r] for r in range(4))
        if not b.name.endswith("_1"):
            out += [_const(k, 3 + r, hang[r], length) for r in range(4)]
            continue
        frame = qmul(world[b.parent], b.jo)
        side = 1.0 if "front" in b.name.casefold() else -1.0
        keys = []
        for f, e in ease:
            swing = qmul(_rz(-SASH_LAG * e * spin), _rx(side * (SASH_FLARE if turns else SASH_LIFT) * e))
            keys.append((f * length, qnorm(qmul(qmul(qmul(qinv(frame), swing), frame), hang))))
        out += [Track(k, 3 + r, tuple((t, q[r], 0.0, 0.0) for t, q in keys)) for r in range(4)]
    return out


def _root(bones) -> int | None:
    """The bone :func:`t_spin` and :func:`hand_spin` turn: ``root_joint``,
    else the rig's first root (Step 2.161g, D592: the air elemental's
    ``tail``, a statue's one bone, on a body wearing booblord's spins)."""
    roots = [k for k, b in enumerate(bones) if b.parent < 0]
    return next((k for k in roots if bones[k].name.casefold() == "root_joint"), roots[0] if roots else None)


def t_spin(characters: bytes, body: Body, p: dict, markers: dict[str, int]) -> Clip:
    """A spin on the bind pose (booblord's T-pose spin): ``turns`` turns of
    the root (``root_joint``, else the rig's first root: :func:`_root`) about z over ``length`` s, q(t) = JO^-1
    Rz(theta) JO q_rest keyed every 45 degrees with its exact tangents,
    the sash hung and swung (:func:`_sash`, Step 2.134a), every other bone
    at its bind (unkeyed); with ``hop`` the root rises
    that much (model units) by 0.35 of the clip and lands at 0.7; the
    bake's hidden props (the vase) scaled to 0; ``m_damage`` a box
    centred at ``box.centre`` with half extents ``box.half`` (model
    units), on from ``active[0]`` to ``active[1]`` of the clip. No
    ``m_feet`` track, so the clip moves the body nowhere (X33 moves it)."""
    length, turns = float(p["length"]), float(p["turns"])
    bones = bone_records(characters, body.name)
    root = _root(bones)
    if root is None:
        raise ValueError(f"t_spin: {body.name}'s rig has no root bone")
    if "m_damage" not in markers:
        raise ValueError(f"t_spin: {body.name} has no m_damage (grow it: \"markers\": [\"m_damage\"])")
    b = bones[root]
    out: list[Track] = []
    if turns:
        steps = max(1, math.ceil(abs(turns) * 8))
        rate = 2 * math.pi * turns / length
        out += _turning(root, (3, 4, 5, 6), [length * k / steps for k in range(steps + 1)],
                        lambda t: rate * t, rate,
                        lambda a: qmul(qmul(qmul(qinv(b.jo), _rz(a)), b.jo), b.q),
                        lambda a: qmul(qmul(qmul(qinv(b.jo), _drz(a)), b.jo), b.q))
    hop = float(p.get("hop", 0.0))
    if hop:
        z = b.t[2]
        out.append(Track(root, 2, tuple((t * length, z + h, 0.0, 0.0) for t, h in
                                        ((0.0, 0.0), (0.35, hop), (0.7, 0.0), (1.0, 0.0)))))
    out += _sash(characters, body, bones, length, turns)
    props = Retarget(characters, body.name, grow=False).props if body.name.casefold() in MAPS else ()
    out += [_const(k, comp, 0.0, length) for k in props for comp in (7, 8, 9)]
    on, off = (length * f for f in p["active"])
    box = _box_tracks(markers["m_damage"], length, on, off, p["box"]["centre"],
                      [2.0 * h for h in p["box"]["half"]])
    return Clip(length, tuple(sorted(out, key=lambda tr: (tr.target, tr.comp))),
                tuple(sorted(box, key=lambda tr: (tr.target, tr.comp))))


def _ordered(where: str, value) -> tuple[float, float]:
    """Two fractions of a clip, in order, within [0, 1]."""
    a, b = _vec(where, value, 2)
    if not 0.0 <= a < b <= 1.0:
        raise ValueError(f"{where}: {a:g}, {b:g} are not in order within [0, 1]")
    return a, b


def _check_hand_spin(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "length", "turns", "tilt_deg", "hand", "hand_z", "plant", "active", "box"),
          ("hold",))
    _positive(f"{where}.length", p["length"])
    _num(f"{where}.turns", p["turns"])
    tilt = _num(f"{where}.tilt_deg", p["tilt_deg"])
    if not 0.0 < tilt <= 90.0:
        raise ValueError(f"{where}.tilt_deg: {tilt:g} is outside (0, 90]")
    _string(f"{where}.hand", p["hand"])
    _num(f"{where}.hand_z", p["hand_z"])
    on, off = _ordered(f"{where}.plant", p["plant"])
    if "hold" in p and not 0.0 <= _num(f"{where}.hold", p["hold"]) < off - on:
        raise ValueError(f"{where}.hold: {p['hold']:g} is outside [0, {off - on:g}), the plant's span")
    _ordered(f"{where}.active", p["active"])
    _keys(f"{where}.box", p["box"], ("centre", "half"))
    _vec(f"{where}.box.centre", p["box"]["centre"], 3)
    _vec(f"{where}.box.half", p["box"]["half"], 3)


def _ease(u: float) -> tuple[float, float]:
    """A Hermite step with flat ends over u in [0, 1] and its slope."""
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u), 6.0 * u * (1.0 - u)


def hand_spin(characters: bytes, body: Body, p: dict, markers: dict[str, int]) -> Clip:
    """A spin on one planted hand (booblord's B, D378): the whole bind pose
    turns rigidly about its root (``root_joint``, else :func:`_root`'s) by R(t) = Rz(theta)
    Ry(tilt), theta turning ``turns`` turns over ``length`` s and the tilt
    rolling her onto her side (``tilt_deg``, +z towards +x: the right arm
    down) while she plants, and the root moves so that the ``hand`` bone's
    origin stays at (0, 0, ``hand_z``) (model units) under her origin: t =
    P - R (hand - root), the body swinging round the hand.  Over the first
    ``plant[0]`` of the clip the tilt and the root's place ease from her
    rest to the planted ones (a Hermite step with flat ends) and over the
    last 1 - ``plant[1]`` back, raised where a bone would dip under the
    floor the rest and planted poses stand on (their lowest bones' depths,
    eased the same way), so the feet don't sink as she leans onto the
    hand.  With ``hold`` (a fraction of the clip, Step 2.180, D701: W37's
    chain window) theta turns its ``turns`` by ``plant[1]`` - ``hold``
    and stays there, so she rests planted and still for ``hold``, then
    rises without turning.  Both tracks are keyed every 22.5 degrees of theta, at the
    plant's ends, the hold's start and 12 times over each ease, with their exact tangents
    (the raise's by a central difference); the sash hung and swung as in
    :func:`t_spin` (:func:`_sash`, Step 2.134b, AZ-636), every other bone
    at its bind (unkeyed); the bake's hidden props scaled to 0; ``m_damage`` a box centred at ``box.centre`` with half extents
    ``box.half``, on from ``active[0]`` to ``active[1]`` of the clip; no
    ``m_feet`` track, so X33 moves the body."""
    length, turns = float(p["length"]), float(p["turns"])
    bones = bone_records(characters, body.name)
    root = _root(bones)
    if root is None:
        raise ValueError(f"hand_spin: {body.name}'s rig has no root bone")
    hand = next((k for k, b in enumerate(bones) if b.name.casefold() == p["hand"].casefold()), None)
    if hand is None:
        raise ValueError(f"hand_spin: {body.name}'s rig has no bone {p['hand']!r}")
    if "m_damage" not in markers:
        raise ValueError(f"hand_spin: {body.name} has no m_damage (grow it: \"markers\": [\"m_damage\"])")
    rest = origins(Rig.read(characters, body.name), Clip(length, (), ()), 0.0)
    reach = tuple(h - r for h, r in zip(rest[hand], rest[root]))
    props = Retarget(characters, body.name, grow=False).props if body.name.casefold() in MAPS else ()
    drawn = [tuple(v - r for v, r in zip(o, rest[root])) for k, o in enumerate(rest) if k not in props]
    b, at = bones[root], (0.0, 0.0, float(p["hand_z"]))
    p0, p1 = (length * f for f in p["plant"])
    hold = float(p.get("hold", 0.0))
    stop = p1 - hold * length if hold else length   # the turn's end (her rest on the hand: W37's window)
    tilt, rate = math.radians(float(p["tilt_deg"])), 2 * math.pi * turns / stop

    def planted(t: float) -> tuple[float, float]:
        """How far planted (0 her rest, 1 on the hand) and its rate."""
        if t < p0:
            w, dw = _ease(t / p0)
            return w, dw / p0
        if t > p1:
            w, dw = _ease((length - t) / (length - p1))
            return w, -dw / (length - p1)
        return 1.0, 0.0

    def turned(t: float, side: int = -1) -> tuple[tuple, tuple]:
        """R(t) and dR/dt (``side`` +1: after ``t``, where the hold stops the turn)."""
        w, dw = planted(t)
        spin = rate if not hold or t < stop - 1e-7 or (t <= stop + 1e-7 and side < 0) else 0.0   # keys are rounded
        theta, phi = rate * (min(t, stop) if hold else t), tilt * w
        r = qmul(_rz(theta), _ry(phi))
        dr = tuple(spin * a + tilt * dw * c for a, c in zip(qmul(_drz(theta), _ry(phi)), qmul(_rz(theta), _dry(phi))))
        return r, dr

    def local(q) -> tuple:
        return qmul(qmul(qmul(qinv(b.jo), q), b.jo), b.q)

    def placed(t: float) -> tuple[tuple, float]:
        """The root's eased place at ``t`` (before the raise) and its lowest
        bone's height there."""
        w = planted(t)[0]
        r = turned(t)[0]
        arm = _turn(r, reach)
        place = tuple((1 - w) * b.t[c] + w * (at[c] - arm[c]) for c in range(3))
        return place, place[2] + min(_turn(r, v)[2] for v in drawn)
    floors = (placed(0.0)[1], placed((p0 + p1) / 2)[1])   # the rest pose's lowest bone, the planted one's

    def raised(t: float) -> float:
        w = planted(t)[0]
        return max(0.0, (1 - w) * floors[0] + w * floors[1] - placed(t)[1]) if 0.0 < w < 1.0 else 0.0

    steps, h = max(1, math.ceil(abs(turns) * 16)), 1e-4
    times = sorted({round(stop * k / steps, 9) for k in range(steps + 1)}
                   | {round(a + (z - a) * k / 12, 9) for a, z in ((0.0, p0), (p1, length)) for k in range(13)})
    rot: list[list] = [[] for _ in range(4)]
    move: list[list] = [[] for _ in range(3)]
    for t in times:
        r, dr = turned(t)
        dr2 = turned(t, 1)[1]
        q, dq, dq2 = local(r), local(dr), local(dr2)
        for c in range(4):
            rot[c].append((t, q[c], dq[c], dq2[c]))
        w, dw = planted(t)
        arm = _turn(r, reach)
        darm, darm2 = (tuple(x + y for x, y in zip(qmul(qmul(d, (*reach, 0.0)), qinv(r))[:3],
                                                   qmul(qmul(r, (*reach, 0.0)), qinv(d))[:3])) for d in (dr, dr2))
        lift = (raised(t), (raised(min(t + h, length)) - raised(max(t - h, 0.0))) / (min(t + h, length) - max(t - h, 0.0)))
        for c in range(3):
            on = at[c] - arm[c]
            value = (1 - w) * b.t[c] + w * on + (lift[0] if c == 2 else 0.0)
            slope, slope2 = (dw * (on - b.t[c]) - w * da[c] + (lift[1] if c == 2 else 0.0) for da in (darm, darm2))
            move[c].append((t, value, slope, slope2))
    out = [Track(root, 3 + c, tuple(rot[c])) for c in range(4)] + [Track(root, c, tuple(move[c])) for c in range(3)]
    out += _sash(characters, body, bones, length, turns)
    out += [_const(k, comp, 0.0, length) for k in props for comp in (7, 8, 9)]
    on, off = (length * f for f in p["active"])
    box = _box_tracks(markers["m_damage"], length, on, off, p["box"]["centre"],
                      [2.0 * h for h in p["box"]["half"]])
    return Clip(length, tuple(sorted(out, key=lambda tr: (tr.target, tr.comp))),
                tuple(sorted(box, key=lambda tr: (tr.target, tr.comp))))


def _check_lightning(where: str, p: dict, box: tuple[str, ...], extra: tuple[str, ...],
                     optional: tuple[str, ...] = ()) -> None:
    optional = ("sweep_deg", "switch_z", "switch_from", *optional)
    _keys(where, p, ("generator", "source", "length", "switch", "aim", "box", *extra), optional)
    for k in ("source", "switch", "aim"):
        _string(f"{where}.{k}", p[k])
    _positive(f"{where}.length", p["length"])
    for k in (*extra, *(k for k in optional if k in p and k != "switch_ramp")):
        _num(f"{where}.{k}", p[k])
    if "switch_ramp" in p:
        _vec(f"{where}.switch_ramp", p["switch_ramp"], 2)
    _keys(f"{where}.box", p["box"], box)


def _check_beam(where: str, p: dict) -> None:
    _check_lightning(where, p, ("from", "to", "half_width", "z"), ("level_deg",))
    _num(f"{where}.box.from", p["box"]["from"])
    _num(f"{where}.box.to", p["box"]["to"])
    _num(f"{where}.box.half_width", p["box"]["half_width"])
    _vec(f"{where}.box.z", p["box"]["z"], 2)


def _check_nova(where: str, p: dict) -> None:
    _check_lightning(where, p, ("half", "centre_z", "grow_from", "grow_until"), ("spin_deg",),
                     ("pitch_deg", "switch_ramp", "switch_fade"))
    if "switch_ramp" in p:
        if "switch_z" in p:
            raise ValueError(f"{where}: switch_ramp and switch_z both key the switch: give one")
    if "switch_fade" in p:
        if "switch_ramp" not in p:
            raise ValueError(f"{where}: switch_fade fades switch_ramp's switch out: give switch_ramp too")
        _positive(f"{where}.switch_fade", p["switch_fade"])
    _vec(f"{where}.box.half", p["box"]["half"], 3)
    _num(f"{where}.box.centre_z", p["box"]["centre_z"])
    _num(f"{where}.box.grow_from", p["box"]["grow_from"])
    _positive(f"{where}.box.grow_until", p["box"]["grow_until"])


def _lightning(characters: bytes, body: Body, p: dict, markers: dict[str, int], what: str
               ) -> tuple[Clip, int, int, float, float, list[Track]]:
    """``p``'s source clip stretched to its length (every key, bone and
    marker, at that share of its time: :func:`~azurik_mod.assets.retarget.stretched`)
    without its ``m_damage`` and aim-marker tracks, the indices of
    ``m_damage`` and the aim marker, and the window W (s) its switch's
    translateZ holds 0.5 or more (the stream, the dome and the bolts it
    drives are on).  With ``switch_z`` the switch's translateZ is keyed
    to that from ``switch_from`` (s; default W's start) to W's end and 0
    elsewhere instead (its stream's emitRate is 100 x z, unclamped; the
    dome and bolts are on from 0.25: Step 2.140's R6); W stays the
    source's."""
    found = {name.casefold(): i for name, i in markers.items()}
    for key in ("switch", "aim"):
        if p[key].casefold() not in found:
            raise ValueError(f"{what}: {body.name} has no marker {p[key]!r}")
    if "m_damage" not in found:
        raise ValueError(f"{what}: {body.name} has no m_damage")
    if p["source"] not in body.clips:
        raise ValueError(f"{what}: {body.name} has no clip {p['source']!r}")
    length = float(p["length"])
    clip = stretched(named_clip(characters, body.name, p["source"]), length)
    switch, aim, damage = found[p["switch"].casefold()], found[p["aim"].casefold()], found["m_damage"]
    keyed = next((tr for tr in clip.markers if tr.target == switch and tr.comp == 2), None)
    on = [] if keyed is None else [
        s / 300.0 for s in range(int(length * 300) + 1)
        if track_value(*keyed.modes, keyed.keys, s / 300.0) >= 0.5]
    if not on:
        raise ValueError(f"{what}: {p['source']}'s {p['switch']} never reaches 0.5, so its stream never shows")
    kept = [tr for tr in clip.markers if tr.target not in (damage, aim)]
    if "switch_z" in p:
        kept = [tr for tr in kept if (tr.target, tr.comp) != (switch, 2)]
        kept.append(_active(switch, float(p.get("switch_from", on[0])), on[-1], length, 2, float(p["switch_z"])))
    return clip, damage, aim, on[0], on[-1], kept


def beam(characters: bytes, body: Body, p: dict, markers: dict[str, int]) -> Clip:
    """Balthazar's lightning (his ``source``, attack_3) as a long level
    beam: the clip stretched to ``length`` s, its switch's window W kept;
    ``m_damage`` a bar from ``box.from`` to ``box.to`` ahead (m, model
    units), ``box.half_width`` to either side, ``box.z`` high, on over W;
    with ``sweep_deg`` the bar pivots at the feet from -sweep_deg to
    +sweep_deg across W (keyed at five points with exact tangents); the
    aim marker turned the same way and pitched up ``level_deg`` (the
    stream's emitters are pitched down 20.1 degrees under it), so the
    stream leaves level and fans with the bar."""
    clip, damage, aim, w0, w1, kept = _lightning(characters, body, p, markers, "beam")
    box, length = p["box"], clip.length
    sweep = math.radians(float(p.get("sweep_deg", 0.0)))
    level = _rx(math.radians(float(p["level_deg"])))
    cy, cz = (box["from"] + box["to"]) / 2, sum(box["z"]) / 2
    extents = (2.0 * box["half_width"], box["to"] - box["from"], box["z"][1] - box["z"][0])
    times = [w0 + (w1 - w0) * j / 4 for j in range(5)]
    rate = 2 * sweep / (w1 - w0)

    def psi(t: float) -> float:
        return -sweep + rate * (t - w0)
    tracks = [_const(damage, 2, cz, length), *(_const(damage, 7 + c, e, length) for c, e in enumerate(extents)),
              _const(damage, 10, 0.5, length), _active(damage, w0, w1, length)]
    if sweep:
        tracks += [Track(damage, 0, tuple((t, -fdlibm.sin(psi(t)) * cy, -fdlibm.cos(psi(t)) * cy * rate,
                                           -fdlibm.cos(psi(t)) * cy * rate) for t in times)),
                   Track(damage, 1, tuple((t, fdlibm.cos(psi(t)) * cy, -fdlibm.sin(psi(t)) * cy * rate,
                                           -fdlibm.sin(psi(t)) * cy * rate) for t in times))]
        tracks += _turning(damage, (3, 4, 5, 6), times, psi, rate, _rz, _drz)
        tracks += _turning(aim, (3, 4, 5, 6), times, psi, rate, lambda a: qmul(_rz(a), level),
                           lambda a: qmul(_drz(a), level))
    else:
        tracks += [_const(damage, 0, 0.0, length), _const(damage, 1, cy, length),
                   *(_const(damage, 3 + c, v, length) for c, v in enumerate((0.0, 0.0, 0.0, 1.0))),
                   *(_const(aim, 3 + c, v, length) for c, v in enumerate(level))]
    return Clip(length, clip.bones, tuple(sorted((*kept, *tracks), key=lambda tr: (tr.target, tr.comp))))


def nova(characters: bytes, body: Body, p: dict, markers: dict[str, int]) -> Clip:
    """Balthazar's lightning (his ``source``, attack_3) as a ring round
    him: the clip stretched to ``length`` s, its switch's window W kept;
    ``m_damage`` a box centred on him ``box.centre_z`` up, ``box.half``
    its half extents, its x and y growing from ``box.grow_from`` at W's
    start to ``box.half`` by ``box.grow_until`` of W, on over W; the aim
    marker turned ``spin_deg`` about z across W (a key every 45 degrees)
    over a pitch of ``pitch_deg`` (Rx, negative down; default 0), so the
    stream and bolts whirl round him and the dome (the same marker's
    child) turns with them.  With ``switch_ramp`` [z0, z1] (Step 2.145,
    D416) the switch's translateZ steps to z0 at ``switch_from`` (default
    W's start), rises straight to z1 by the box's ``grow_until`` of W,
    holds it to W's end and is 0 after, so a dome keyed on it grows with
    the box; with ``switch_fade`` (clip s; Step 2.153b, AZ-658, D479) it
    falls straight from z1 at W's end to 0 that long after, the aim
    turning on at the same rate, so what the switch shows (beamlord's
    shield) fades out turning; the box still closes at W's end (a look
    only).  A fade past the clip's end is refused."""
    clip, damage, aim, w0, w1, kept = _lightning(characters, body, p, markers, "nova")
    box, length = p["box"], clip.length
    grown = w0 + (w1 - w0) * min(float(box["grow_until"]), 1.0)
    fade = float(p.get("switch_fade", 0.0))
    if w1 + fade > length + 1e-6:
        raise ValueError(f"nova: switch_fade {fade:g} s runs past the clip's end ({length:g} s; W ends {w1:.3f})")
    if "switch_ramp" in p:
        switch = {name.casefold(): i for name, i in markers.items()}[p["switch"].casefold()]
        z0, z1 = (float(z) for z in p["switch_ramp"])
        s0, h = float(p.get("switch_from", w0)), RAMP / 2
        slope = (z1 - z0) / (grown - (s0 + h)) if grown > s0 + h else 0.0
        out = -z1 / (fade + h) if fade else 0.0   # the fade's straight fall, W's end to fade after it
        keys = [(0.0, 0.0, 0.0, 0.0), (max(s0 - h, 0.0), 0.0, 0.0, 0.0), (s0 + h, z0, 0.0, slope),
                (grown, z1, slope, 0.0), (w1 - h, z1, 0.0, out), (min(w1 + (fade or h), length), 0.0, out, 0.0),
                (length, 0.0, 0.0, 0.0)]
        kept = [tr for tr in kept if (tr.target, tr.comp) != (switch, 2)] + [Track(switch, 2, tuple(
            k for j, k in enumerate(keys) if j == 0 or k[0] > keys[j - 1][0]))]
    tracks = [_const(damage, 0, 0.0, length), _const(damage, 1, 0.0, length),
              _const(damage, 2, box["centre_z"], length),
              *(_const(damage, 3 + c, v, length) for c, v in enumerate((0.0, 0.0, 0.0, 1.0))),
              _const(damage, 9, 2.0 * box["half"][2], length), _const(damage, 10, 0.5, length),
              _active(damage, w0, w1, length)]
    for c in (0, 1):
        e0, e1 = 2.0 * box["grow_from"], 2.0 * box["half"][c]
        slope = (e1 - e0) / (grown - w0) if grown > w0 else 0.0
        tracks.append(Track(damage, 7 + c, ((w0, e0, slope, slope), (grown, e1, slope, slope))))
    spin = math.radians(float(p["spin_deg"]))
    rate, end = spin / (w1 - w0), min(w1 + fade, length)   # the whirl turns on through the fade
    steps = max(1, math.ceil(abs(float(p["spin_deg"])) * (end - w0) / (w1 - w0) / 45))
    pitch = _rx(math.radians(float(p.get("pitch_deg", 0.0))))
    tracks += _turning(aim, (3, 4, 5, 6), [w0 + (end - w0) * k / steps for k in range(steps + 1)],
                       lambda t: rate * (t - w0), rate, lambda a: qmul(_rz(a), pitch), lambda a: qmul(_drz(a), pitch))
    return Clip(length, clip.bones, tuple(sorted((*kept, *tracks), key=lambda tr: (tr.target, tr.comp))))


def _check_gust(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "source", "length", "release", "arrive", "from", "to", "half", "centre_z", "cloud",
                     "cloud_scale"), ("funnel",))
    if "funnel" in p:
        _keys(f"{where}.funnel", p["funnel"], ("marker", "size"))
        _string(f"{where}.funnel.marker", p["funnel"]["marker"])
        _positive(f"{where}.funnel.size", p["funnel"]["size"])
    for k in ("source", "cloud"):
        _string(f"{where}.{k}", p[k])
    length = _positive(f"{where}.length", p["length"])
    release, arrive = (_num(f"{where}.{k}", p[k]) for k in ("release", "arrive"))
    if not 0.0 <= release < arrive <= length:
        raise ValueError(f"{where}: release {release:g} and arrive {arrive:g} are not in order within the clip")
    for k in ("from", "to", "centre_z", "cloud_scale"):
        _num(f"{where}.{k}", p[k])
    _vec(f"{where}.half", p["half"], 3)


def gust(characters: bytes, body: Body, p: dict, markers: dict[str, int]) -> Clip:
    """The air elemental's thrown wind (D374, build 1; Step 2.140): its
    ``source`` (attack_1) stretched to ``length`` s, its ``m_damage``
    tracks replaced by a box of half extents ``half`` whose centre,
    ``centre_z`` up, travels straight ahead (model units) from ``from`` at
    ``release`` s to ``to`` at ``arrive`` s, on over that travel; the
    ``cloud`` marker (its body's wind puff, m_turbulence) keyed on the
    same path with its extents ``cloud_scale`` times its rest's (a marker's
    extents scale the fx bound to it: Step 2.140's R8); and no ``m_feet``
    track (no lunge).  The box travels in the body's frame, so its
    columns stay out of X33's carry (W23).  With ``funnel`` (D434, Step
    2.155) its ``marker`` (spideyzar's m_projectile, the frame of his
    tornado in his fx) rides the box's path at the floor (x 0, z 0),
    upright, its extents ``size``, on over the travel; nothing keys his
    trigger, so X38's stand copy of his fx stays dark while it rides and
    stands where the gust ends (:mod:`~azurik_mod.patches._player_fx_ring`)."""
    found = {name.casefold(): i for name, i in markers.items()}
    funnel = p.get("funnel")
    for name in ("m_damage", p["cloud"], *((funnel["marker"],) if funnel else ())):
        if name.casefold() not in found:
            raise ValueError(f"gust: {body.name} has no marker {name!r}")
    if p["source"] not in body.clips:
        raise ValueError(f"gust: {body.name} has no clip {p['source']!r}")
    length, release, arrive = float(p["length"]), float(p["release"]), float(p["arrive"])
    clip = stretched(named_clip(characters, body.name, p["source"]), length)
    damage, cloud, feet = found["m_damage"], found[p["cloud"].casefold()], found.get("m_feet")
    rest = dict(marker_records(characters, body.name))[next(n for n, i in markers.items() if i == cloud)]
    start, end = float(p["from"]), float(p["to"])
    rate = (end - start) / (arrive - release)
    tracks: list[Track] = []
    for target in (damage, cloud):
        path = ((0.0, start, 0.0, 0.0), (release, start, 0.0, rate), (arrive, end, rate, 0.0), (length, end, 0.0, 0.0))
        tracks += [_const(target, 0, 0.0, length), Track(target, 1, path), _const(target, 2, float(p["centre_z"]), length)]
    tracks += [*(_const(damage, 3 + c, v, length) for c, v in enumerate((0.0, 0.0, 0.0, 1.0))),
               *(_const(damage, 7 + c, 2.0 * h, length) for c, h in enumerate(p["half"])),
               _const(damage, 10, 0.5, length), _active(damage, release, arrive, length)]
    tracks += [_const(cloud, 7 + c, float(p["cloud_scale"]) * rest[7 + c], length) for c in range(3)]
    at = found[funnel["marker"].casefold()] if funnel else None
    if funnel:
        path = ((0.0, start, 0.0, 0.0), (release, start, 0.0, rate), (arrive, end, rate, 0.0), (length, end, 0.0, 0.0))
        tracks += [_const(at, 0, 0.0, length), Track(at, 1, path), _const(at, 2, 0.0, length),
                   *(_const(at, 3 + c, v, length) for c, v in enumerate((0.0, 0.0, 0.0, 1.0))),
                   *(_const(at, 7 + c, float(funnel["size"]), length) for c in range(3)),
                   _active(at, release, arrive, length)]
    kept = [tr for tr in clip.markers if tr.target not in (damage, cloud, feet, at)]
    return Clip(length, clip.bones, tuple(sorted((*kept, *tracks), key=lambda tr: (tr.target, tr.comp))))


def _check_air_blast(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "source", "length", "switch", "aim", "impact", "bolt", "blast"))
    for k in ("source", "switch", "aim"):
        _string(f"{where}.{k}", p[k])
    length, impact = _positive(f"{where}.length", p["length"]), _num(f"{where}.impact", p["impact"])
    bolt, blast = p["bolt"], p["blast"]
    _keys(f"{where}.bolt", bolt, ("from", "half", "centre_z", "switch_z", "hands", "emitter", "pitch_deg"))
    _keys(f"{where}.blast", blast, ("half", "centre_z", "grow_from", "grow_until", "until", "dome_unit"))
    for k in ("from", "centre_z", "switch_z", "pitch_deg"):
        _num(f"{where}.bolt.{k}", bolt[k])
    for k in ("centre_z", "grow_from", "grow_until", "until"):
        _num(f"{where}.blast.{k}", blast[k])
    _positive(f"{where}.blast.dome_unit", blast["dome_unit"])
    for part, k, n in (("bolt", "half", 3), ("bolt", "emitter", 3), ("blast", "half", 3)):
        _vec(f"{where}.{part}.{k}", p[part][k], n)
    if not isinstance(bolt["hands"], list) or not bolt["hands"]:
        raise ValueError(f"{where}.bolt.hands: {bolt['hands']!r} is not a list of bone names")
    for i, name in enumerate(bolt["hands"]):
        _string(f"{where}.bolt.hands[{i}]", name)
    times = (bolt["from"], impact, blast["grow_until"], blast["until"])
    if not (0.0 <= times[0] and all(b - a > RAMP for a, b in zip(times, times[1:])) and times[3] <= length):
        raise ValueError(f"{where}: bolt.from {times[0]:g}, impact {impact:g}, blast.grow_until {times[2]:g} and "
                         f"blast.until {times[3]:g} are not in order {RAMP:g} s apart within the clip")


HANDS_STEP = 0.05
"""The spacing (clip s) of the keys that carry :func:`air_blast`'s bolt
emitter along its hands (review F1, Step 2.153b: one place for the whole
bolt phase missed his hands by 1.1 model units on average in a standing
jump's air time; at 0.05 beamlord's keys miss by 0.015 at most, at 0.1
by 0.11 as his arms swing up)."""


def _riding(characters: bytes, body: Body, clip: Clip, aim: int, bolt: dict, turned: tuple, end: float,
            then: list[tuple]) -> list[Track]:
    """The aim's translation tracks (comps 0-2) from 0 to ``end`` (s):
    the mean of ``bolt.hands``' origins as ``clip`` plays, less
    ``turned`` (the emitter under the turned aim), keyed every
    :data:`HANDS_STEP` s with central-difference slopes and flat at
    ``end``; then each component's keys of ``then``."""
    rig = Rig.read(characters, body.name)
    names = {b.name: k for k, b in enumerate(rig.bones)}
    missing = [n for n in bolt["hands"] if n not in names]
    if missing:
        raise ValueError(f"air_blast: {body.name} has no bone {', '.join(map(repr, missing))}")
    hands = [names[n] for n in bolt["hands"]]

    def at(t: float) -> tuple[float, ...]:
        o = origins(rig, clip, t)
        return tuple(sum(o[k][c] for k in hands) / len(hands) - turned[c] for c in range(3))
    steps = max(1, math.ceil(end / HANDS_STEP - 1e-9))
    times = [end * j / steps for j in range(steps + 1)]
    d = 1e-3
    keys: list[list[tuple]] = [[], [], []]
    for j, t in enumerate(times):
        v, lo, hi = at(t), at(max(t - d, 0.0)), at(min(t + d, end))
        for c in range(3):
            slope = (hi[c] - lo[c]) / (min(t + d, end) - max(t - d, 0.0))
            keys[c].append((t, v[c], slope, 0.0 if j == steps else slope))
    return [Track(aim, c, (*keys[c], *then[c])) for c in range(3)]


def scale_pivot(characters: bytes, body: Body, marker: str) -> tuple[float, float, float]:
    """The scale pivot (+0x2C) of the transform of ``body``'s default fx
    (``characters/<body>/fx/fx_default``) bound to ``marker``, the point
    its scale grows about (``nodes.local_matrix``), or (0, 0, 0) when no
    transform there is bound to it.  The game's bind (0x68DE0) writes the
    marker's translation, rotation and extents into the transform's T, R
    and S and leaves the pivots as authored, so at a scale S and no turn
    the transform's origin sits (1 - S) x the pivot from its translation
    (AZ-669, Step 2.153c: balthazar_airship's aim [12] has (0.1551, 0.0154,
    0.2709), 48 m under his feet at S 179)."""
    at = {n.casefold(): i for i, n in named_resources(characters).items()}.get(fx_edit.default_key(body.name))
    if at is None:
        return (0.0, 0.0, 0.0)
    for rec in record_offsets(characters, parse_toc(characters)[at].file_offset):
        if rec is not None and lstr(characters, rec) == "transform" and (
                bind_name(characters, rec) or "").casefold() == marker.casefold():
            return struct.unpack_from("<3f", characters, rec + 0x2C)
    return (0.0, 0.0, 0.0)


def air_blast(characters: bytes, body: Body, p: dict, markers: dict[str, int]) -> Clip:
    """Balthazar's lightning (his ``source``, attack_3) fired straight down,
    then a blast round him (Step 2.153, D451; Step 2.153b): the clip
    stretched to ``length`` s.  Up to ``impact`` (s) the bolt phase: the
    switch at ``bolt.switch_z`` (the bolts on, what the switch shows
    unseen), the aim marker turned ``bolt.pitch_deg`` about x, which
    points the bolts down, and translated so the point ``bolt.emitter``
    under it (beamlord's burst emitter [23]) rides the mean of the
    ``bolt.hands`` bones' origins as the clip plays (keyed every
    :data:`HANDS_STEP` s with the path's own slopes), ``m_damage`` a column of half
    extents ``bolt.half`` centred ``bolt.centre_z`` under his feet, on
    from ``bolt.from``.  From ``impact`` the blast: the switch 0 (no
    bolts, no shield), the aim at his feet, unturned, its extents
    ``blast.half``'s x half over ``blast.dome_unit`` (the floor dome
    grafted under it, a sphere of that radius at extents 1, so its rim is
    the box's edge as it grows; 1 again after ``blast.until``) and its
    translation (E - 1) x the scale pivot of the fx transform bound to it
    (:func:`scale_pivot`), so its origin stays at his feet as E grows
    (AZ-669, Step 2.153c),
    ``m_damage`` centred ``blast.centre_z`` up, its half z ``blast.half``'s
    and its x and y half growing from ``blast.grow_from`` to
    ``blast.half``'s by ``blast.grow_until``, off at ``blast.until``.
    Each phase change is a :data:`RAMP`-wide step.  X39 holds the bolt
    phase while the body is airborne and moves the clip to ``impact``
    when it lands."""
    clip, damage, aim, _, _, kept = _lightning(characters, body, p, markers, "air_blast")
    length, impact, bolt, blast = clip.length, float(p["impact"]), p["bolt"], p["blast"]
    switch = {name.casefold(): i for name, i in markers.items()}[p["switch"].casefold()]
    h, until, grown = RAMP / 2, float(blast["until"]), float(blast["grow_until"])
    start = impact + h

    def phased(target: int, comp: int, before: float, after: tuple) -> Track:
        """``before`` to the impact, then ``after``'s keys (value, slope)."""
        keys = [(0.0, before, 0.0, 0.0), (impact - h, before, 0.0, 0.0), *after]
        return Track(target, comp, tuple(k for j, k in enumerate(keys) if j == 0 or k[0] > keys[j - 1][0]))

    def grows(e0: float, e1: float, t1: float, then: tuple = ()) -> tuple:
        slope = (e1 - e0) / (t1 - start)
        return ((start, e0, 0.0, slope), (t1, e1, slope, 0.0), *then)

    def after(value: float) -> tuple:
        return ((start, value, 0.0, 0.0), (length, value, 0.0, 0.0))
    lit = Track(switch, 2, ((0.0, 0.0, 0.0, 0.0), (h, float(bolt["switch_z"]), 0.0, 0.0)))
    on = phased(switch, 2, float(bolt["switch_z"]), after(0.0))
    kept = [tr for tr in kept if (tr.target, tr.comp) != (switch, 2)] + [Track(switch, 2, lit.keys + on.keys[1:])]
    tracks = [_const(damage, 0, 0.0, length), _const(damage, 1, 0.0, length),
              phased(damage, 2, float(bolt["centre_z"]), after(float(blast["centre_z"]))),
              *(_const(damage, 3 + c, v, length) for c, v in enumerate((0.0, 0.0, 0.0, 1.0))),
              *(phased(damage, 7 + c, 2.0 * bolt["half"][c], grows(2.0 * blast["grow_from"], 2.0 * blast["half"][c],
                                                                   grown, ((length, 2.0 * blast["half"][c], 0.0, 0.0),)))
                for c in (0, 1)),
              phased(damage, 9, 2.0 * bolt["half"][2], after(2.0 * blast["half"][2])),
              _const(damage, 10, 0.5, length), _active(damage, float(bolt["from"]), until, length)]
    down = _rx(math.radians(float(bolt["pitch_deg"])))
    unit = float(blast["dome_unit"])
    dome = grows(blast["grow_from"] / unit, blast["half"][0] / unit, grown, (
        (until - h, blast["half"][0] / unit, 0.0, 0.0), (min(until + h, length), 1.0, 0.0, 0.0), (length, 1.0, 0.0, 0.0)))
    # AZ-669: the aim scales about its pivot sp, its origin at t + (1 - E) sp, so t := (E - 1) sp keeps it at his
    # feet; Hermite keys are linear in their values and slopes, so the mapped keys give (E(t) - 1) sp exactly
    sp = scale_pivot(characters, body, p["aim"])
    dome = tuple(k for j, k in enumerate(dome) if j == 0 or k[0] > dome[j - 1][0])
    feet = [tuple((t, (v - 1.0) * sp[c], a * sp[c], b * sp[c]) for t, v, a, b in dome) for c in range(3)]
    tracks += _riding(characters, body, clip, aim, bolt, _turn(down, bolt["emitter"]), impact - h, feet)
    tracks += [phased(aim, 3 + r, down[r], after((0.0, 0.0, 0.0, 1.0)[r])) for r in range(4)]
    tracks += [phased(aim, 7 + c, 1.0, dome) for c in range(3)]
    return Clip(length, clip.bones, tuple(sorted((*kept, *tracks), key=lambda tr: (tr.target, tr.comp))))


from azurkit.tools.characters.content import ROOT as CONTENT_ROOT
CLIPS = CONTENT_ROOT / "clips"
"""The built-ins' Blender clips, ``clips/<variant>/``: clip-only glTF
files (bones and keys, no mesh or image; game-asset snippets, D153)."""
ROOT_TRAVEL_MAX = 0.10
"""How far a Blender clip's root bone may move from its rest along the
floor, as a share of the body's height: the game moves a body by a marker
track (``m_feet``) that a new clip lacks, so a root that travels draws the
body away from its entity and its hit box (Step 2.158's X3); a drop, as
a sit's, keeps it over its place (Step 2.168, D660)."""


def _check_gltf(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "file", "sha256", "animation"), ("active", "box", "rate"))
    _file(f"{where}.file", p["file"])
    if not isinstance(p["sha256"], str) or not _SHA256.match(p["sha256"]):
        raise ValueError(f"{where}.sha256: {p['sha256']!r} is not 64 lower-case hex digits "
                         "(`azurik-mod model clips` prints it)")
    name = p["animation"]
    if not isinstance(name, str) or not name or not name.isascii() or name != name.lower() or "\0" in name:
        raise ValueError(f"{where}.animation: {name!r} is not a clip's name (lower-case ASCII)")
    if ("active" in p) != ("box" in p):
        raise ValueError(f"{where}: active and box come together (the hit window and its box) or not at all")
    if "active" in p:
        on, off = _vec(f"{where}.active", p["active"], 2)
        if not 0.0 <= on < off:
            raise ValueError(f"{where}.active: {on:g}, {off:g} are not 0 <= on < off (clip seconds)")
        _keys(f"{where}.box", p["box"], ("centre", "half"))
        _vec(f"{where}.box.centre", p["box"]["centre"], 3)
        _vec(f"{where}.box.half", p["box"]["half"], 3)
    if "rate" in p:
        _positive(f"{where}.rate", p["rate"])


FX_ASSETS = BUILTIN.parent / "fx"
"""The built-ins' and overlays' fx files, ``fx/<name>/``: a texture's PNG
and a platform's glTF mesh (Step 2.155e; made by a script, committed)."""


def files_shipped(variant, kinds=("built-in", "overlay")) -> bool:
    """Whether ``variant`` reads its files from the shipped folders: a
    source of ``kinds``, or a user's recipe ``from`` a built-in (Step X.73),
    whose files are that built-in's."""
    return variant.source in kinds or bool(variant.files) and variant.files in builtins()


def fx_folder(variant) -> Path:
    """Where ``variant``'s ``fx`` files are (a texture's ``png``, a
    mesh's ``gltf``): a built-in's or an overlay's :data:`FX_ASSETS`
    ``/<name>`` (:func:`files_shipped`), a user recipe's beside its file."""
    return FX_ASSETS / (variant.files or variant.name) if files_shipped(variant) else Path(variant.source).parent


def colour_folder(variant) -> Path:
    """Where ``variant``'s ``colours`` PNGs are (Step 2.203): beside a user
    recipe's file (one ``from`` a built-in too: the Colours tab's Import
    copies it there), a built-in's or an overlay's :data:`FX_ASSETS`
    ``/<name>``."""
    return FX_ASSETS / variant.name if variant.source in ("built-in", "overlay") else Path(variant.source).parent


def clip_folder(variant) -> Path:
    """Where ``variant``'s ``gltf`` clips' files are: a built-in's
    :data:`CLIPS` ``/<name>`` (:func:`files_shipped`), a user recipe's beside
    its file."""
    return CLIPS / (variant.files or variant.name) if files_shipped(variant) else Path(variant.source).parent


_GLTF_CLIPS: dict[tuple, object] = {}   # gltf_clip's reads by content, the newest _GLTF_CLIPS_KEPT
_GLTF_CLIPS_KEPT = 64


def gltf_clip(characters: bytes, body: Body, p: dict, markers: dict[str, int], *, folder: Path,
              builtin: bool = False, lent: bool = False) -> Clip:
    """A clip made in Blender (Step 2.158, D465): the animation
    ``animation`` of the glTF ``file`` in ``folder``, its sha256 checked,
    read as a clip of ``body`` as the build has it here (after W24 and
    W29, so their bones resolve:
    :func:`~azurik_mod.assets.clip_import.read_clips`, thinned).  With
    ``active`` and ``box``, ``m_damage`` is keyed as a box centred at
    ``box.centre`` with half extents ``box.half`` (model units), on from
    ``active[0]`` to ``active[1]`` (clip seconds); without, the clip keeps
    the marker tracks of the body's clip of the animation's name (none
    for a new one).  A root bone that moves along the floor more than
    :data:`ROOT_TRAVEL_MAX` of the body's height is refused, and so is a
    built-in's file that carries a mesh or an image.  ``lent`` (a clip
    another body's recipe bakes, :func:`baked_clip`): its keys on nodes
    that are no bone of ``body`` dropped.  A read is kept per
    process by its inputs' content (the file's sha256, the animation and
    :func:`~azurik_mod.assets.clip_import.read_key`: what it reads of the
    body, not the clips a build adds; Step X.81c), so a recipe's builds
    read each of its clips once."""
    from azurkit.tools.characters import clip_import, mesh_edit
    from azurkit.tools.characters.characters import height

    path = Path(folder) / _file("gltf: file", p["file"])
    if not path.is_file():
        raise ValueError(f"gltf: file {p['file']!r}: no such file ({path})")
    sha = mesh_edit.file_sha256(path)
    if sha != p["sha256"]:
        raise ValueError(f"gltf: file {p['file']!r}: its sha256 is {sha[:12]}, not the recipe's {p['sha256'][:12]} "
                         "(`azurik-mod model clips` prints the row)")
    if builtin:
        doc = mesh_edit._load(path)[0]
        if doc.get("meshes") or doc.get("images"):
            raise ValueError(f"gltf: file {p['file']!r}: a built-in's clip file holds bones and keys only, no mesh "
                             "or image")
    read = clip_import.read_key(characters, body.name, [p["animation"]])
    key = (read, sha, p["animation"], lent) if read is not None else None
    got = _GLTF_CLIPS.get(key) if key is not None else None
    if got is None:
        got = clip_import.read_clips(characters, body.name, path, [p["animation"]], bones_only=lent)[0]
        if key is not None:
            _GLTF_CLIPS[key] = got
            while len(_GLTF_CLIPS) > _GLTF_CLIPS_KEPT:
                del _GLTF_CLIPS[next(iter(_GLTF_CLIPS))]
    tall = height(characters, body) or 1.0
    if got.root_travel > ROOT_TRAVEL_MAX * tall:
        raise ValueError(f"gltf: animation {p['animation']!r} moves its root bone {got.root_travel:.3f} model units "
                         "along the floor, "
                         f"past {ROOT_TRAVEL_MAX:.0%} of {body.name}'s height {tall:.3f}: the game moves a body by its "
                         "m_feet marker, which a new clip lacks, so the body would be drawn off its place")
    clip = got.clip
    if "box" not in p:
        return clip
    if "m_damage" not in markers:
        raise ValueError(f"gltf: {body.name} has no m_damage (grow it: \"markers\": [\"m_damage\"])")
    on, off = (float(x) for x in p["active"])
    if off > clip.length:
        raise ValueError(f"gltf: active ends at {off:g} s, past animation {p['animation']!r}'s {clip.length:.3f} s")
    damage = markers["m_damage"]
    box = _box_tracks(damage, clip.length, on, off, p["box"]["centre"], [2.0 * h for h in p["box"]["half"]])
    kept = [tr for tr in clip.markers if tr.target != damage]
    return Clip(clip.length, clip.bones, tuple(sorted((*kept, *box), key=lambda tr: (tr.target, tr.comp))))


def _check_bake(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "body", "clip"), ("variant",))
    lender = _string(f"{where}.body", p["body"])
    if lender != PLAYER and lender.casefold() not in MAPS:
        raise ValueError(f"{where}.body: {lender!r} is no humanoid body the bake serves (garret4 or one "
                         "retarget.MAPS lists)")
    _string(f"{where}.clip", p["clip"])
    if "variant" in p and not (isinstance(p["variant"], str) and _NAME.match(p["variant"])):
        raise ValueError(f"{where}.variant: {p['variant']!r} is not a variant's name")


@functools.cache
def _builtin_clips() -> dict:
    """The built-in recipes' own ``clips`` as ``variants.json`` holds them
    (read raw, so the built-ins' own load can fold them)."""
    doc = json.loads(BUILTIN.read_text(encoding="utf-8"))
    return {name: r.get("clips", {}) for name, r in doc.items() if isinstance(r, dict)}


def baked_clip(characters: bytes, body: Body, p: dict, markers: dict[str, int]) -> Clip:
    """Another humanoid body's clip on ``body`` (Step 2.164c; D785, the
    owner: "Any humanoid body's"): ``body`` (garret4 or a body
    :data:`~azurik_mod.assets.retarget.MAPS` lists)'s clip ``clip``, or
    with ``variant`` that built-in's own ``gltf`` clip ``clip`` read on
    ``body`` (its keys on bones the vanilla body lacks, its mesh's,
    dropped: they play no role), retargeted onto ``body``'s rig through
    both role maps as B bakes garret4's (:class:`~azurik_mod.assets.
    retarget.Retarget`, its lift :data:`~azurik_mod.assets.retarget.LIFTS`'),
    its tracks on the markers B grows (:data:`~azurik_mod.assets.retarget.
    ADDED_MARKERS`: root motion, ledge, trail) and the damage markers kept
    on ``body``'s of their names (the recipe's grown ``m_damage`` too), its
    others (the lender's own fx switches; W27's ``m_root``, which no baked
    clip keys) dropped; on ``body`` itself the clip as it is.
    :class:`ValueError` names a body or clip it lacks, a body the bake
    can't map (either one) and a lent Blender clip with a hit box (a box is
    authored on its own body)."""
    from azurkit.tools.characters.characters import DAMAGE_MARKERS
    from azurkit.tools.characters.retarget import ADDED_MARKERS, LIFTS, TARGETS, bake_clip

    lender = p["body"]
    if body.name.casefold() not in TARGETS:
        raise ValueError(f"bake: {body.name} is no humanoid body the bake serves (retarget.MAPS), so it takes no "
                         "other body's clip")
    own = lender.casefold() == body.name.casefold()
    if "variant" in p:
        given = _builtin_clips().get(p["variant"], {}).get(p["clip"])
        if not isinstance(given, dict) or given.get("generator") != "gltf":
            raise ValueError(f"bake: the built-in variant {p['variant']!r} has no Blender (gltf) clip {p['clip']!r}")
        if "box" in given:
            raise ValueError(f"bake: {p['variant']}'s {p['clip']} has a hit box, authored on its own body: a lent "
                             "clip keeps none")
        on = body if own else read_body(characters, lender)
        source = gltf_clip(characters, on, given, {m: i for i, m in enumerate(on.markers)},
                           folder=CLIPS / p["variant"], builtin=True, lent=True)
    else:
        source = named_clip(characters, lender, p["clip"])
    if own:
        return source
    try:
        rt = Retarget(characters, body.name, grow=False, lender=lender, lift=LIFTS.get(body.name.casefold(), 0.0))
    except ValueError as exc:
        raise ValueError(f"bake: {lender}'s clips can't be baked onto {body.name}: {exc}") from None
    named = {m.casefold(): i for m, i in markers.items()
             if m.casefold() in {n.casefold() for n in (*ADDED_MARKERS, *DAMAGE_MARKERS)}}
    rt.markers = {i: named[m.casefold()] for i, m in enumerate(rt.garret4.markers) if m.casefold() in named}
    return bake_clip(rt, source)


GENERATORS = {"t_spin": Generator(_check_t_spin, t_spin), "hand_spin": Generator(_check_hand_spin, hand_spin),
              "beam": Generator(_check_beam, beam), "nova": Generator(_check_nova, nova),
              "gust": Generator(_check_gust, gust), "air_blast": Generator(_check_air_blast, air_blast),
              "gltf": Generator(_check_gltf, gltf_clip), "bake": Generator(_check_bake, baked_clip)}
"""The built-in clip generators, by the name a recipe's ``generator`` gives
(``gltf``'s ``make`` also takes the folder its file is in)."""


def _int(where: str, value, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{where}: {value!r} is not a whole number from {low} to {high}")
    return value


def _check_whoosh(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "length", "swells", "seed", "columns"), ("takes",))
    length = _positive(f"{where}.length", p["length"])
    if round(length * RATE) < 1:
        raise ValueError(f"{where}.length: {length:g} s makes no sample at {RATE} Hz")
    _int(f"{where}.swells", p["swells"], 1, 2 ** 31)
    _int(f"{where}.seed", p["seed"], 0, 2 ** 32 - 1)
    _int(f"{where}.takes", p.get("takes", 1), 1, TAKES)


def _files(where: str, files) -> None:
    if not isinstance(files, list) or not 1 <= len(files) <= TAKES:
        raise ValueError(f"{where}: {files!r} is not a list of 1 to {TAKES} WAV files (a take each)")
    for i, file in enumerate(files):
        if not isinstance(file, str) or not _WAV_FILE.match(file):
            raise ValueError(f"{where}[{i}]: {file!r} is not a .wav file's name (no folder: the variant's "
                             "sounds folder holds it)")


def _check_wav(where: str, p: dict) -> None:
    _keys(where, p, ("generator", "files", "columns"))
    _files(f"{where}.files", p["files"])


SFX_GENERATORS = {"whoosh": Generator(_check_whoosh, lambda p, take: synth.whoosh(
    float(p["length"]), p["swells"], p["seed"], take)), "wav": Generator(_check_wav, None)}
"""The built-in sound generators (``check(where, params)``, ``make(params,
take)`` -> PCM16 at 22050 Hz), by the name an ``sfx``'s ``generator``
gives; ``wav``'s takes are its ``files`` (:func:`recipe_wavs`)."""


def take_name(name: str, take: int) -> str:
    """A sound's ``take``-th name as the binder tries it: ``name``, then
    ``name_a`` .. ``name_s``."""
    return name if take == 0 else f"{name}_{chr(ord('a') + take - 1)}"


# --- the recipe -------------------------------------------------------------
@dataclass(frozen=True)
class Pose:
    """One of a recipe's ``poses`` (Step 2.154, W28): in each clip whose
    name's last part is ``clip``, ``bone`` turned ``deg`` about ``axis``
    (the model's frame at bind: x right, y forward, z up) through
    ``window`` (from, to: shares of the clip; then ``ease``, a share eased
    in before and out after): :func:`~azurik_mod.assets.retarget.turned_over`.
    ``clip`` "" is a shape's turn (:class:`Shape`, Step 2.164b): in every
    clip, the whole clip (:func:`~azurik_mod.assets.retarget.turned`)."""

    clip: str
    bone: str
    axis: tuple[float, float, float]
    deg: float
    window: tuple[float, float, float]


@dataclass(frozen=True)
class Lods:
    """A recipe's screen LODs (``lods.ratio``, ``lods.at``,
    ``lods.error_px``; Step 2.166d, D537, W39): LOD k cut from LOD k-1 to
    at most ``ratio[k-1]`` of LOD 0's triangles (and, with ``error_px``,
    no further than that many screen lines at its switch distance,
    :func:`~azurik_mod.assets.lods.pixel_error`), garret4 switching to it
    past ``at[k-1]`` m; no ratio drops the body's LODs past LOD 0.  One
    LOD 1 serves the screen and the realtime shadow
    (:data:`~azurik_mod.assets.lods.SHADOW_LOD`), so W36 adds none."""

    ratio: tuple[float, ...]
    at: tuple[float, ...] = ()
    error_px: float | None = None


@dataclass(frozen=True)
class Shape:
    """One of a recipe's ``shapes`` (Step 2.164b, D455): a slider ``name``
    (``--player-shape NAME=X``), its ``title`` (the Player page's row),
    the mesh ops it sizes by name and its ``value``."""

    name: str
    title: str
    ops: tuple[str, ...]
    value: float = 1.0
    turns: tuple[tuple[str, tuple[float, float, float], float], ...] = ()
    """(bone, axis, deg): above 1, each bone turned ``deg`` times the
    value less 1 about ``axis`` (the model's frame at bind) in every clip
    she plays (:class:`Pose` "", W28): a cloth hung over the form kept
    out of it as it grows (Step 2.164b, its skeptic's sash: her back flaps
    out over a bigger butt); at or below 1 none."""
    below: tuple[str, ...] = ()
    """More ops it sizes only at a value below 1 (Step 2.164d: her pelvis's
    scale narrows her hips, where her rounds, which push the skin out to
    their forms, take nothing in; above 1 it puffed her shorts' hem)."""

    def sizes(self) -> tuple[str, ...]:
        """The ops it sizes at its value: ``ops``, and ``below`` under 1."""
        return self.ops + (self.below if self.value < 1.0 else ())


@dataclass(frozen=True, eq=False)
class Variant:
    """A parsed recipe (module docstring): its ``name``, where it came
    from (``source``: "built-in" or a file), its fields, and its
    :func:`recipe_sha`."""

    name: str
    source: str
    title: str
    notes: str
    base: str
    mode: str = "own"
    size: str = "own"
    scale: float = 1.0
    sounds: str = "own"
    reach: float = 1.0
    damage: float = 1.0
    speed: float = 1.0
    balance: bool | None = None
    ground: bool | None = None
    markers: tuple[str, ...] = ()
    clips: dict = field(default_factory=dict)
    columns: dict = field(default_factory=dict)
    carry: tuple[str, ...] = ()
    rotate: bool = False
    sha: str = ""
    voice: str = "own"
    sfx: dict = field(default_factory=dict)
    shouts: tuple[str, ...] = ()
    """``shouts.files`` (Step 2.183, D705): its voice's WAVs, a take each,
    which play where Garret shouts under another weapon (:func:`unarmed`)."""
    mesh: MeshSpec | None = None
    through_walls: bool = False
    fx: tuple = ()
    wavs: dict = field(default_factory=dict)
    arms: float = 0.0
    jiggle: jiggles.Spec | None = None
    fx_ring: dict | None = field(default_factory=dict)
    fx_grafts: tuple = ()
    marker_source: str = PLAYER
    held: tuple[str, ...] = ()
    weapon: str | None = None
    """The weapon it wears (``--player-weapon`` over it; ``None``: its base's default)."""
    effects: tuple = ()
    """Its ``effects`` rows (:class:`~azurik_mod.assets.fx_templates.Effect`, Step 2.167b)."""
    arm_clips: tuple[tuple[str, float], ...] = ()
    """``arms.clips``: a clip (by the last part of its name; the recipe's
    own ``v/`` clips too) whose arms turn out this many degrees instead of
    ``arms.out_deg`` (Step 2.154: a jump's arms kept off a bigger bust)."""
    poses: tuple[Pose, ...] = ()
    textures: tuple = ()
    """``textures`` (Step 2.154 round 3, W30): the body's materials
    repainted (:class:`~azurik_mod.assets.paint.TextureSpec`)."""
    shadow: bool | float | None = None
    """``lods.shadow`` (Step 2.166c, W36): ``False`` no shadow LOD, ``True``
    one at the default share, a number one at that share; ``None`` the
    default (:data:`FIELDS`)."""
    lods: Lods | None = None
    """``lods.ratio``, ``lods.at`` and ``lods.error_px`` (Step 2.166d,
    W39); ``None``: the body's own LODs."""
    idles: dict = field(default_factory=dict)
    """``idles``' slots (Step 2.168, D553): {slot name (``idle``,
    ``idle_1``-``idle_6``): a recipe clip or a base clip}."""
    idle_wait: tuple[float, float] = IDLE_WAIT
    """``idles.wait``: the range (s of standing) X45 draws each fidget's
    wait from."""
    slots: dict = field(default_factory=dict)
    """``slots`` (Step 2.171): {slot name (:data:`~azurik_mod.patches.
    _player_slots.RECIPE_SLOTS`): a recipe clip or a base clip}."""
    texture_scale: int = 1
    """``texture_scale`` (Step 2.177, :data:`FIELDS`): every material row baked at this many times its size."""
    colours: tuple = ()
    """``colours`` (Step 2.170b, W38): the player's copy of the body
    recoloured (:class:`~azurik_mod.assets.paint.ColourSpec`)."""
    victory_cancel: float | None = None
    """``victory_cancel`` (Step 2.181, D702): the seconds a victory plays
    before a push of the stick ends it (X46); ``None``: it plays whole."""
    drain: str = "nearest"
    """``drain.targets`` (Step 2.196, D765): whom its life drain takes life
    from (:func:`drain_targets`)."""
    shapes: tuple[Shape, ...] = ()
    """``shapes`` (Step 2.164b, :data:`FIELDS`): its shape sliders, in the recipe's order."""
    unshaped: str = ""
    """Its sha with every shape at 1.0 (:func:`recipe_sha`): its own while no
    shape is sized, else the build its jiggle places and arm fits are
    (:func:`fit_sha`, :attr:`plain`)."""
    plain: MeshSpec | None = None
    """Its ``mesh`` before its shapes sized it (``None`` while none does):
    where its jiggle bones sit (``_player_character._variant_body``), so
    her clips' rests hold."""
    files: str = ""
    """The recipe it is ``from`` (Step 2.177; empty: none), whose files it
    reads (:func:`sound_folder`, :func:`clip_folder`, :func:`fx_folder`; a
    user's recipe from a built-in, that built-in's folders, Step X.73)."""

    @property
    def fx_edits(self) -> bool:
        """Whether the recipe edits its body's default fx (a clone, X40)."""
        return bool(self.fx or self.fx_grafts)

    def idle_clips(self) -> dict[str, str]:
        """``idles``' slots, each by its clip's name under the body (a
        recipe clip under :data:`VARIANT_DIR`)."""
        return {slot: VARIANT_DIR + clip if clip in self.clips else clip for slot, clip in self.idles.items()}

    def slot_clips(self) -> dict[str, str]:
        """``slots``' slots, each by its clip's name under the body (a
        recipe clip under :data:`VARIANT_DIR`)."""
        return {slot: VARIANT_DIR + clip if clip in self.clips else clip for slot, clip in self.slots.items()}

    def loop(self) -> dict | None:
        """The hand spin B's chain loops planted (W37, Step 2.180, D701):
        the :func:`hand_spin` clip both sweep1 and sweep2 play, when it
        rests on its hand (``hold``) after a turn that its plant holds
        whole; else ``None``."""
        clip = self.columns.get("sweep1")
        p = self.clips.get(clip) if clip is not None else None
        if p is None or p.get("generator") != "hand_spin" or self.columns.get("sweep2") != clip:
            return None
        turns, (on, off), hold = abs(float(p["turns"])), p["plant"], float(p.get("hold", 0.0))
        return p if turns and hold and (off - hold) * (1.0 - 1.0 / turns) >= on else None

    def clip_of(self, column: str) -> str | None:
        """The pick the recipe gives ``column``: one of its clips under
        :data:`VARIANT_DIR`, a base clip by its name, or ``None`` (W3's)."""
        clip = self.columns.get(column)
        return None if clip is None else VARIANT_DIR + clip if clip in self.clips else clip


def _sha(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


DRAIN_BOX = {"record": 45, "name": "damageBox", "type": "transform",
             "set": {"scaleX": 12.0, "scaleY": 12.0, "scaleZ": 2.0}}
"""Balthazar's drain box (its ``damageBox`` transform [45], whose one child
is the 2 x 2 x 2 m norm_2 platform [46]) scaled 12, 12, 2: 24 x 24 x 4 m,
12 m to each side (D452: "bigger and wider"; Step 2.153's scale 6, 12 x
12 x 4 m, Step 2.153b's 12: the second sleeth set 2 knocks sat 3.98 and
5.70 m from the pick, AZ-663; the world bounds Step 2.153c's diagnosis
read, 29.8-33.6 m across as it turns, main's 15.5-17.0, give the size),
in his own build's overlay and beamlord's ``fx`` alike: on the player's
clone of his fx (X40, D446), so the airship boss keeps his own 2 x 2 x
2 m box.  A platform's touch has no wall test, so it drains through
walls; X37 zeroes the horizontal knock of a hit it lands (AZ-672)."""

STAND_TEXTURE = {"recolor": {"ramp": [[0.26, 0.27, 0.29], [0.95, 0.96, 0.98]], "gain": 1.1}}
"""The air elemental's standing tornado's puffs (spideyzar's grey surf 297, both its renderers'): their luminance
x 1.1 through a grey-to-off-white ramp, so they draw a light wind grey with their streaks kept (D501, Step 2.155b;
greyer since Step 2.155c, so it reads as wind, not steam)."""
FUNNEL_TEXTURE = {"recolor": {"ramp": [[0.0, 0.2, 0.21, 0.23], [0.38, 0.3, 0.31, 0.33], [0.72, 0.84, 0.85, 0.88],
                                       [1.0, 0.86, 0.87, 0.9]], "gain": 1.1}}
"""The tornado's puffs (Step 2.155d; Step 2.155e its cloud head): STAND_TEXTURE's grey stretched over the puff's own
luminance (0.35-0.74 x 1.1 between its 5th and 95th percentiles) to the funnel's greyer white (AZ-666)."""
FUNNEL_MESH = {"gltf": {"file": "air_funnel.glb",
                        "sha256": "8115cce7de39494f0480e8dab7e1efb424206b945987c726b97dd8646dbc099d"}}
"""The tornado's funnel (Step 2.155e, D525), made in Blender 5.2.2 (D364) and committed under :data:`FX_ASSETS`:
825 vertices, 1,536 triangles, its radius 0.5 + 2.75 (h / 8.5 m)^1.3 m from its foot on its axis at z 0 to 8.5 m,
its spine leaning 0.35 m off the axis with a half turn up the height and three lobes of +-(12 % + 0.3 m) twisting 1.5
turns clockwise up it (the 0.3 m ramped in over the lowest 1.7 m, so its foot is one round tip), so its outline changes
as group1 turns it counter-clockwise and the lobes read as climbing; u twice round, v up."""
FUNNEL_SWIRL = {"png": {"file": "air_funnel_swirl.png",
                        "sha256": "da5ed277189ba7849da73ea51170ed2d032a015fc67c993a4c690676e7c7027d"}, "format": "dxt3"}
"""The funnel's texture (Step 2.155e): diagonal wisps of a neutral grey (0.76, 0.78, 0.81 x 0.75-1.0, AZ-666), alpha
0.1-1.0 by wisp, rising the way the lobes do, faded in over the foot's 12 % and out over the top's 25 %; DXT3 128 x
128, every frame of the blast dome's 5-frame list (its stage's 20 frames a second then draw one still texture)."""
_HEAD = {"positionVarianceX": 0.05, "positionVarianceY": 0.8, "positionVarianceZ": 0.3, "velocityBaseX": 0.06,
         "velocityBaseY": 2.8, "velocityBaseZ": 0.8, "velocityVarianceX": 0.06, "velocityVarianceY": 0.2,
         "velocityVarianceZ": 0.2, "scaleRangeMin": 3.0, "scaleRangeMax": 5.0}
"""The cloud at the funnel's head (Step 2.155e): two of his funnel emitters on its rim, 8 m up and 2.9 m out from
its spine,
their puffs (x 3-5) swirling round at 5.3 m/s, rising 1.5 m/s and drifting out 0.3 m/s."""
FUNNEL_UNIT = 0.5333
"""The funnel holder's scale at full size: group1's units are 1.875 m (its 1.25 x the marker's 1.5), so one mesh
metre is one metre."""
_SKIRT = {"positionVarianceY": 2.0, "velocityBaseX": -1.0, "velocityBaseY": 3.0, "velocityBaseZ": 0.3}
"""The cloud's four emitters (Step 2.155c): a low dust skirt drifting in and swirling round the tornado's foot
(rising 0.3, since Step 2.155e, so it stays low)."""
TURN = {"record": 22, "name": "timer3", "type": "timer", "set": {"rate": 1.5},
        "links": [{"index": 2, "dst": 35, "dst_plug": "rotateZ", "factor": -0.4048}]}
"""The tornado's turn (Step 2.155d): his own timer3 (1.0667 s, repeating; its link 2 took his iceball's rotateZ 0 to
-15.52 rad, the iceball hidden on the clone), its link onto group1 [35]'s rotateZ at -0.4048, so the funnel's
emitters turn one round (2 pi, a seamless wrap) every 1.07 s, 5.89 rad/s the way the swirl turns (since Step 2.155e
at rate 1.5: every 0.71 s, 8.84 rad/s, the funnel mesh with them), as the game spins
its emitter groups (frag_air_1's EffectSpin_timer)."""
ROPE, ROPE_FADE = 0.12, 0.35
"""The tornado's rope (Step 2.155f, D569: "Thin to a rope, then fade"): the funnel's width at its end, of full, and
the trigger level z under which it fades (its opacity min(1, z / 0.35)): as z falls the funnel narrows to
max(ROPE, z^3) of its width, a thin rope by z 0.49, then fades."""
ROPE_LINKS = [
    # z fanned out by his force trigger [31] (bound, never keyed: 0 while bound), the trigger's link 9 writing its
    # translateZ: its link 0 feeds the dust emitter [53] the trigger fed (35 z x 4), links 1-3 three copies of z
    {"record": 31, "name": "m_force_trigger", "type": "transform", "links": [
        {"index": 0, "dst": 53, "dst_plug": "emitRate", "factor": 140.0},
        *({"index": i, "dst": 18, "dst_plug": f"inputs[{i - 1}]", "factor": 1 / 24.5864} for i in (1, 2)),
        {"index": 3, "dst": 19, "dst_plug": "inputs[1]", "factor": 1 / 8.9864}]},
    # z^3 by his iceball's two times combiners, max(ROPE, z^3) by its max combiner, which scales the funnel's holder
    {"record": 18, "name": "emissiveRed_timesCombiner", "type": "combiner",
     "links": [{"index": 0, "dst": 19, "dst_plug": "inputs[0]"}]},
    {"record": 19, "name": "emissiveGreen_timesCombiner", "type": "combiner",
     "links": [{"index": 0, "dst": 17, "dst_plug": "inputs[1]"}]},
    {"record": 17, "name": "Ice_s_emissive_maxCombiner", "type": "combiner", "set": {"inputs[0]": ROPE},
     "links": [{"index": i, "dst": 83, "dst_plug": "scale" + "XY"[i], "factor": FUNNEL_UNIT} for i in (0, 1)]},
    {"record": 16, "name": "fx_magic_timer", "type": "timer",   # its other input's writers parked on the iceball
     "links": [{"index": 1, "dst": 24, "dst_plug": "rotateX"}]},
    {"record": 14, "name": "m_attacklevel_toggle", "type": "switch",
     "links": [{"index": 0, "dst": 24, "dst_plug": "rotateY"}]},
    # g, rising 0 to 1 as z falls: the trigger's link 0 writes 1 + S(z) (0.5 + 0.5 smoothstep, x 2) into his acid
    # timer [93], stopped, whose link 3 is its curve's falling half there, s^3 - 2 s^2 + 1, into his steam trigger
    # [56] (bound, never keyed), whose links take the holder's height to 1 + 0.15 g and the turn's timer to
    # 1.5 (1 + g): the rope a little taller, spinning twice as fast at its end
    {"record": 93, "name": "acid_effect_fx_magic_timer", "type": "timer", "set": {"enable": 0.0},
     "links": [{"index": 3, "dst": 56, "dst_plug": "translateZ"}]},
    {"record": 56, "name": "m_steam_trigger", "type": "transform", "links": [
        {"index": 0, "dst": 83, "dst_plug": "scaleZ", "weight": 0.25, "factor": FUNNEL_UNIT / 50},
        {"index": 1, "dst": 22, "dst_plug": "rate", "weight": 2 / 3, "factor": 0.75}]}]
"""The rope's links (Step 2.155f, D569), all from the trigger's level z: the graph's links write curve(source x
weight) x factor (0x663B0) and only his trigger [34] is written, so its spare nodes give the shapes its two curves
(0.5 + 0.5 smoothstep, 0 to 35) can't: width max(ROPE, z^3), height 1 + 0.15 g, spin x (1 + g), g = d(S(z)).
A stopped timer's update writes nothing (0x6BAD0: enable 0 returns), so a linked currentTime holds."""

OVERLAYS = {
    "air_elemental": {
        "clips": {"gust": {"generator": "gust", "source": "attack_1", "length": 1.1, "release": 0.36, "arrive": 0.95,
                           "from": 1.0, "to": 12.0, "half": [1.2, 1.2, 1.2], "centre_z": 1.2,
                           "cloud": "m_turbulence", "cloud_scale": 3.0,
                           "funnel": {"marker": "m_projectile", "size": 1.5}}},
        "columns": {"sweep1": "gust", "sweep2": "gust", "sweep ledge": "gust"},
        "attacks": {"through_walls": True},
        "marker_source": "balthazar_spider",
        "markers": ["m_projectile", "m_projectile_trigger", "m_deathbeam_trigger", "m_balth_blast",
                    "m_lifedrainswitch", "m_force_trigger", "m_whirlwind_trigger", "m_steam_trigger",
                    "m_acid_trigger", "m_right_fang", "m_left_fang", "m_ice_telltale", "m_fire_telltale",
                    "m_steam_telltale"],
        "fx_ring": {"arm": [{"record": 7, "name": "CompressedAir_EmitterShape", "set": {"emitRate": 117.0}}],
                    "stand": {"key": "characters/balthazar_spider/fx/fx_default", "trigger": "m_whirlwind_trigger",
                              "hold": 2.0, "fx": [   # D501 (Step 2.155b): big, dense; Step 2.155c: a tornado; 2.155e: held 2 s
                                  # Step 2.155e: the trigger is the funnel's opacity (link 6, its curve 0 to 35:
                                  # since Step 2.155f min(1, z / ROPE_FADE)), feeds the head cloud x 2.5 and the dust
                                  # x 4; group1's scale held at 1.25 (below), so the vortex's axis stays 1 m long
                                  # (Step 2.155d); since Step 2.155f (D569) its links 0 and 9 drive ROPE_LINKS,
                                  # which narrow the funnel's holder to a rope as it fades, not into its foot
                                  {"record": 34, "name": "m_whirlwind_trigger", "type": "transform",
                                   "set": {"translateZ": 0.0}, "links": [
                                      {"index": 0, "dst": 93, "dst_plug": "currentTime", "factor": 2.0},
                                      *({"index": i, "dst": 24, "dst_plug": "rotate" + "XY"[i - 1]} for i in (1, 2)),
                                      *({"index": i, "factor": 2.5 if i in (3, 5) else 4.0} for i in (3, 4, 5, 7, 8)),
                                      {"index": 6, "dst": 84, "dst_plug": "gameVisible", "weight": 1 / ROPE_FADE,
                                       "factor": 1 / 35},
                                      {"index": 9, "dst": 31, "dst_plug": "translateZ", "factor": 1 / 35}]},
                                  *({"record": r, "name": n, "type": "pEmitter", "set": _HEAD} for r, n in (
                                      (37, "funnel_emitterShape"), (45, "funnel_emitter5Shape"))),
                                  {"record": 47, "name": "funnel_emitter6Shape", "type": "pEmitter",
                                   "set": {"emitRate": 0.0}},   # its link is the funnel's opacity now
                                  *({"record": r, "name": n, "type": "transform", "set": {
                                      "translateX": x, "translateY": y, **({"translateZ": z} if z else {})}}
                                    for r, n, x, y, z in (   # the head cloud on the rim (place155e)
                                        (36, "funnel_emitter", 0.5459, 0.0319, -0.1759),
                                        (44, "funnel_emitter5", 0.2209, 0.2195, -0.1759),
                                        # the dust: the cloud's 0.6 x as far, round the foot
                                        (40, "cloud_emitter", 7.393, 0.004, 0), (48, "cloud_emitter1", 8.545, -1.148, 0),
                                        (50, "cloud_emitter2", -7.393, 0.004, 0),
                                        (52, "cloud_emitter3", 0.0, -7.389, 0))),
                                  *({"record": r, "name": n, "type": "pEmitter", "set": _SKIRT} for r, n in (
                                      (41, "cloud_emitterShape"), (49, "cloud_emitter1Shape"),
                                      (51, "cloud_emitter2Shape"), (53, "cloud_emitter3Shape"))),
                                  {"record": 217, "name": "single_tornado2_pRendererB1", "type": "pRendererB",
                                   "set": {"alpha1": 0.9, "alphaAge1": 0.25, "alphaAge2": 1.4, "size1": 0.5,
                                           "size2": 0.5, "sizeAge2": 1.4, "color1R": 0.8, "color1G": 0.81,
                                           "color1B": 0.84, "color2R": 0.72, "color2G": 0.72, "color2B": 0.74,
                                           # Step 2.155d: depth-sorted (0xDE000 tests the renderer's useDepthSort
                                           # bit and sorts its pool by view depth, 0xDDD00), so one face draws on
                                           # top and its flow round the funnel shows; small puffs
                                           # (a pixel holds the near side's, not the whole orbit's), the old ones
                                           # held at half (alpha2) for D501's density
                                           "useDepthSort": 1.0, "alpha2": 0.5},
                                   "texture": FUNNEL_TEXTURE},
                                  {"record": 223, "name": "single_tornado2_pRendererB2", "type": "pRendererB",
                                   # the dust skirt's puffs (Step 2.155e): 0.6 to 1.2 m, a grey haze round the
                                   # funnel's foot (Step 2.155d halved them so its particle foot showed)
                                   "set": {"alpha1": 0.7, "alphaAge1": 0.2, "size1": 0.6, "size2": 1.2,
                                           "color1R": 0.6, "color1G": 0.59, "color1B": 0.57, "color2R": 0.48,
                                           "color2G": 0.47, "color2B": 0.46},
                                   "texture": STAND_TEXTURE},
                                  # Step 2.155d: his vortex's axis 1 m long at full size, on the funnel's axis, so it
                                  # holds every stream on its orbit (a cone, no waist, no arms flung off)
                                  {"record": 38, "name": "pVortex1", "type": "transform",
                                   "set": {"scaleX": 0.533, "scaleY": 0.533, "scaleZ": 0.533, "translateX": 0.0}},
                                  TURN,   # group1 turns with the swirl
                                  # the funnel's particles gone once drawn out (1.4 s), so its pool feeds the foot
                                  {"record": 222, "name": "pSinkShape1", "type": "pSink", "set": {"maxAge": 1.4}},
                                  {"record": 35, "name": "group1", "type": "transform",
                                   "set": {"scaleX": 1.25, "scaleY": 1.25, "scaleZ": 1.25}},
                                  # Step 2.155e (D525): his blast dome re-meshed as the funnel, its holder hung on
                                  # group1's axis at the floor, so TURN spins it; dark until let go (its
                                  # gameVisible 0, the deathbeam's link and timer2's off it, the iceball hidden)
                                  {"record": 83, "name": "blastdome", "type": "transform", "parent": 35,
                                   "set": {"translateX": 0.0, "translateY": 0.0, "translateZ": -4.4423,
                                           "rotateX": 0.0, "rotateY": 0.0, "rotateZ": 0.0,
                                           "scaleX": FUNNEL_UNIT * ROPE, "scaleY": FUNNEL_UNIT * ROPE,
                                           "scaleZ": FUNNEL_UNIT}},
                                  {"record": 84, "name": "blastdomeShape", "type": "platform", "mesh": FUNNEL_MESH,
                                   "set": {"gameVisible": 0.0},
                                   # its row 2 on blend 4 (SRCALPHA, INVSRCALPHA), not 5's additive, so it greys
                                   # what it covers (AZ-666's greyer white)
                                   "material": {"opacity": 0.85, "alpha_ref": 0.02, "blend": 4},
                                   "texture": FUNNEL_SWIRL},
                                  {"record": 12, "name": "m_deathbeam_trigger", "type": "transform",
                                   "links": [{"index": 2, "dst": 24, "dst_plug": "rotateX"}]},
                                  {"record": 82, "name": "timer2", "type": "timer",
                                   "links": [{"index": 0, "dst": 24, "dst_plug": "rotateX"},
                                             {"index": 1, "dst": 24, "dst_plug": "rotateY"}]},
                                  {"record": 25, "name": "IceballShape", "type": "platform",
                                   "set": {"gameVisible": 0.0}},
                                  *ROPE_LINKS]}}},   # Step 2.155f (D569): the rope's links, last
    "balthazar": {   # D427's fallback (Step 2.146): beamlord's bolts (v4's since Step 2.157, D442) on his attack_3
        "fx": [{"record": 24, "name": "pBurstEmitterShape1", "type": "pBurstEmitter",
                "set": {"emitRate": 80.0, "spacing": 0.05, "maxCount": 400.0, "kinkRadialOffsetMin": 0.05,
                        "kinkRadialOffsetMax": 0.2, "splitCountMin": 2.0, "splitCountMax": 4.0}},
               {"record": 35, "name": "pRendererB2", "type": "pRendererB",
                "set": {"color1R": 0.35, "color1G": 0.65, "color1B": 1.0, "alpha1": 0.6, "color2R": 0.15,
                        "color2G": 0.35, "color2B": 1.0, "alpha2": 0.3, "colorAge2": 0.15, "alphaAge2": 0.15,
                        "size1": 0.25, "size2": 0.16},
                "texture": {"recolor": {"ramp": [[0.0, 0.0, 0.0], [0.05, 0.15, 0.55], [0.3, 0.6, 1.0],
                                                 [0.6, 0.82, 1.0]], "gamma": 1.15}}},
               {"record": 39, "name": "pSinkShape2", "type": "pSink", "set": {"maxAge": 0.12}},
               DRAIN_BOX,   # D452 (Steps 2.153, 2.153b): the drain's box 24 x 24 x 4 m
               # AZ-643 (Step 2.153b): his violet stream's renderer bright for 1 s, its sprites 0.3-0.6 m, its
               # pool updated at 30 Hz
               {"record": 11, "name": "balthblast_pRendererB1", "type": "pRendererB",
                "set": {"color1R": 0.85, "color1G": 0.65, "color1B": 1.0, "color2R": 0.6, "color2G": 0.3,
                        "color2B": 1.0, "colorAge2": 1.0, "alpha1": 0.85, "alpha2": 0.7, "alphaAge2": 1.0,
                        "size1": 0.12, "size2": 0.24, "sizeAge2": 1.0}},
               {"record": 14, "name": "pSystemShape1", "type": "pSystem", "set": {"updateRate": 30.0}},
               # AZ-769 (Step 2.197b, D797): his bolts' three targets inherit mode 7, so X37's anchor puts them on
               # the beam's target's chest, else straight ahead to its reach (X37 writes their translate each tick;
               # these hold until its first)
               *({"record": r, "name": n, "type": "transform", "inherit": 7,
                  "set": {"translateX": x, "translateY": y, "translateZ": 1.2}}
                 for r, n, x, y in ((58, "locator1", -0.4, 4.8), (60, "locator2", 0.4, 4.8), (62, "locator3", 0.0, 6.0)))]},
}
"""W23 (Step 2.140): each species' own-build overlay, a recipe of clips and
columns (no name, title, base or grade of its own) its own-mode build plays
whenever no variant is worn: the air elemental's B throws its wind (D374,
build 1; the d336 read's sweep1, sweep2 for a moving B, sweep ledge at a
cliff) 1 to 12 m ahead at 18.6 m/s (sweep1's Rate 1.0), its wind puff
riding the box; held, B throws again as each box arrives (X33's held
columns, Move end1 arrive / length: Step 2.145, D414) and its hits skip
the wall test (``through_walls``, D415); since Step 2.149 (D429, D430)
her puff rides out in X38's copy of her graph kept bound at rest, its
emitter at 117 a second once a throw arms it (``fx_ring.arm``), and stays
where the next clip leaves it; and since Step 2.155 (D434: "Standing
funnel at the end") each gust ends in spideyzar's tornado standing where
it ends for about 1.5 s, as his own does: the 14 bind names of his
fx/fx_default the body lacks are grown at his own rest records
(``marker_source``; every switch of his graph at z 0 there, so nothing
of it shows at rest or in another clip), the gust keys m_projectile on
the box's path at the floor (``funnel``, extents 1.5: his species scale)
and nothing keys his trigger, and X38's ``fx_ring.stand`` spawns a dark
bound copy of his graph at each throw, detaches it where the gust ends
and writes its m_whirlwind_trigger up to 1, held 1.5 s and back to 0
(the graph's own links grow the funnel and feed its seven emitters);
since Step 2.155b (D501: "Big and dramatic") it spawns the player's
clone of his graph, ``characters/air_elemental/v/fx/fx_stand``
(``fx_ring.stand.fx``), its three funnel emitters fed at 3.5 times his
rate and four cloud emitters at 3 times (the trigger's links' factor),
its puffs white (:data:`STAND_TEXTURE`), opaque, larger and fading by
2.2 s; his NPC keeps his graph; since Step 2.155e a spinning mesh funnel
(:data:`FUNNEL_MESH`), which since Step 2.155f (D569) ends as a rope
(:data:`ROPE_LINKS`).
NPC air elementals wear the same body and bind none of the grown names.
Balthazar's (Step
2.146, D427: "Stream, bolts as fallback") is ``fx`` alone: his attack_3's
violet stream ([17] -> [14]) shows in no picture of a worn body since
Step 2.137, so his own build brightens the lightning bolts that draw his
beam as beamlord's do ([24], [35], [39] of his fx_default: since Step
2.157 v4's translucent electric-blue bolts on a recoloured copy of
their texture, D442, on the player's clone: the airship boss keeps his);
and since Step 2.153b (AZ-643) his stream itself reads as a band: born
about 2.4 m up at his levitating hands and pitched down 20 degrees, its
sprites dimmed to (0.22, 0.04, 0.28) by 0.4 s while they swelled to
about 1.9 m, so only its first metre or two showed; its renderer [11]
now keeps them bright violet (alpha 0.85 to 0.7) and 0.3-0.6 m across
(x 2.5) for 1 s, and its pool [14] updates at 30 Hz (15); its pitch
stays vanilla's.  attack_2 is Step 2.135's (D324).  A species' grade
stays its own (MODE_GRADES)."""


def overlay(species: str) -> Variant | None:
    """``species``' own-build overlay (:data:`OVERLAYS`) as a
    :class:`Variant` named for it, from source ``overlay``, or ``None``."""
    recipe = OVERLAYS.get(species)
    return None if recipe is None else _variant(species, {"base": species, **recipe}, "overlay")


def recipe_sha(recipe: dict) -> str:
    """sha256[:12] of ``recipe``'s canonical JSON (sorted keys, compact)
    without its labels and sounds (:data:`LABELS`, :data:`UNGRADED`), its
    shapes at 1.0 (Step 2.164b: they build no other byte) and
    its glTF's, its Blender clips' and its textures' PNG file paths (each
    sha256 stands for it): what a sitting grades of a build of it."""
    played = {k: v for k, v in recipe.items() if k not in LABELS + UNGRADED}
    if isinstance(played.get("shapes"), dict):   # Step 2.164b: a shape at 1.0 builds no other byte
        played["shapes"] = {n: s for n, s in played["shapes"].items()
                            if not (isinstance(s, dict) and s.get("value", 1.0) == 1.0)}
        if not played["shapes"]:
            del played["shapes"]
    if isinstance(played.get("weapon"), str):   # Step 2.161b: the weapon it names, as built (its record's sha)
        from azurkit.tools.characters._player_weapons import weapons
        found = weapons().get(played["weapon"])
        played["weapon"] = played["weapon"] + (f"@{found.sha}" if found is not None else "")
    if isinstance(played.get("effects"), list):   # Step 2.167b: each template as built (its record's sha)
        played["effects"] = templated(played["effects"])
    mesh = played.get("mesh")
    if isinstance(mesh, dict) and isinstance(mesh.get("gltf"), dict):
        played["mesh"] = {**mesh, "gltf": {k: v for k, v in mesh["gltf"].items() if k != "file"}}
    if isinstance(played.get("clips"), dict):   # a Blender clip's file by its sha256 too (Step 2.158), and a
        played["clips"] = {name: {k: v for k, v in c.items() if k != "file"}   # built-in's one a bake lends by
                           if isinstance(c, dict) and c.get("generator") == "gltf" else _lent(c)   # its own (2.164c)
                           for name, c in played["clips"].items()}
    if isinstance(played.get("fx"), list):   # a texture's PNG (Step 2.157) and a mesh's glTF by its sha256 too
        played["fx"] = _file_shas(played["fx"])
    if isinstance(played.get("colours"), list):   # a colours png's by its sha256 too (Step 2.203)
        played["colours"] = [{**e, "ops": [{k: v for k, v in o.items() if k != "file"}
                                           if isinstance(o, dict) and o.get("op") == "png" else o for o in e["ops"]]}
                             if isinstance(e, dict) and isinstance(e.get("ops"), list) else e
                             for e in played["colours"]]
    ring = played.get("fx_ring")
    if isinstance(ring, dict) and isinstance(ring.get("stand"), dict) and isinstance(ring["stand"].get("fx"), list):
        played["fx_ring"] = {**ring, "stand": {**ring["stand"], "fx": _file_shas(ring["stand"]["fx"])}}
    return _sha(played)


def _lent(clip):
    """A ``bake`` clip from a built-in's Blender clip with ``variant``
    named ``<name>@<that clip's sha256>``, so its sha follows the file."""
    if not (isinstance(clip, dict) and clip.get("generator") == "bake" and isinstance(clip.get("variant"), str)):
        return clip
    given = _builtin_clips().get(clip["variant"], {}).get(clip.get("clip"))
    sha = given.get("sha256") if isinstance(given, dict) else None
    return {**clip, "variant": clip["variant"] + (f"@{sha}" if isinstance(sha, str) else "")}


def templated(rows: list) -> list:
    """``effects`` rows with each known template named ``<name>@<its sha>``
    (:func:`~azurik_mod.assets.fx_templates.template_sha`), as a recipe's
    and a weapon's shas fold them."""
    return [{**r, "template": f"{r['template']}@{fx_templates.template_sha(r['template'])}"}
            if isinstance(r, dict) and r.get("template") in fx_templates.TEMPLATES else r for r in rows]


def _file_shas(fx: list) -> list:
    """``fx`` edits with each texture's PNG and mesh's glTF named by its sha256 alone."""
    def bare(e: dict, field: str, ref: str) -> dict:
        if not isinstance(e.get(field), dict) or not isinstance(e[field].get(ref), dict):
            return e
        return {**e, field: {**e[field], ref: {k: v for k, v in e[field][ref].items() if k != "file"}}}
    return [bare(bare(e, "texture", "png"), "mesh", "gltf") if isinstance(e, dict) else e for e in fx]


def sounds_sha(variant: Variant, drop: dict | None = None) -> str:
    """sha256[:12] of ``variant``'s ``voice``, ``sfx`` and ``wavs`` and
    each WAV file's sha256 (:func:`variant_sounds`): what its sounds are
    built from."""
    return _sha({"voice": variant.voice, "sfx": variant.sfx, "wavs": variant.wavs,
                 "drop": {leaf: d.sha256 for leaf, d in sorted((drop or {}).items())}})


def sound_dir(variant: Variant) -> str:
    """``variant``'s dir in ``fx.xbr``, as X14 binds from it."""
    return VARIANT_SOUND_DIR + variant.name


def sound_folder(variant: Variant) -> Path:
    """Where ``variant``'s ``wavs`` and ``wav`` sounds' files are: a
    built-in's :data:`SOUNDS` ``/<name>`` (:func:`files_shipped`), a user recipe's beside its file."""
    return SOUNDS / (variant.files or variant.name) if files_shipped(variant, ("built-in",)) \
        else Path(variant.source).parent


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _names(where: str, value) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{where}: {value!r} is not a list of bone names")
    return tuple(_string(f"{where}[{i}]", v) for i, v in enumerate(value))


def _mesh(where: str, mesh, builtin: bool) -> MeshSpec:
    """The recipe's ``mesh`` (W24, Step 2.142), checked with no game data:
    the body's bones, the glTF and the folds are the build's to check."""
    where = f"{where}: mesh"
    _keys(where, mesh, (), ("gltf", "keep", "ops", "drop"))
    gltf = None
    if "gltf" in mesh:
        if builtin:
            raise ValueError(f"{where}.gltf: a built-in takes no glTF (no exported game data is committed)")
        _keys(f"{where}.gltf", mesh["gltf"], ("file", "sha256"), ("import",))
        sha = mesh["gltf"]["sha256"]
        if not isinstance(sha, str) or not _SHA256.match(sha):
            raise ValueError(f"{where}.gltf.sha256: {sha!r} is not 64 lower-case hex digits "
                             "(`azurik-mod model check` prints it)")
        gltf = (_file(f"{where}.gltf.file", mesh["gltf"]["file"]), sha)
        how = mesh["gltf"].get("import", "positions")
        if how not in ("positions", "topology", "weights"):
            raise ValueError(f"{where}.gltf.import {how!r} is not positions, topology or weights")
    ops = mesh.get("ops", [])
    if not isinstance(ops, list):
        raise ValueError(f"{where}.ops: {ops!r} is not a list")
    parsed = []
    for i, op in enumerate(ops):
        parsed.append(_mesh_op(f"{where}.ops[{i}]", op))
    drop = _names(f"{where}.drop", mesh.get("drop", []))
    if gltf is None and not parsed and not drop:
        raise ValueError(f"{where}: neither a gltf, ops nor a drop")
    return MeshSpec(gltf, _names(f"{where}.keep", mesh.get("keep", [])), tuple(parsed),
                    mesh["gltf"].get("import", "positions") if gltf else "positions", drop)


_OP_KEYS = {
    "scale": (("bone", "radius", "factors"), ("offset", "mirror", "only", "groups", "profile", "name", "late")),
    "push": (("bone", "dir", "height", "radius", "depth"), ("offset", "mirror", "only", "groups", "fold", "name",
                                                            "region")),
    "taper": (("bone", "factors", "plateau", "half", "reach"), ("offset", "only", "groups", "name")),
    "tuck": (("groups", "under", "dir", "margin"), ("window", "skip", "only", "name", "strict", "band", "faces")),
    "subdivide": (("bone", "radius", "edge"), ("offset", "mirror", "only", "groups", "smooth", "name", "apart",
                                              "normals")),
    "round": (("bone", "radius", "origin", "blend"), ("offset", "dir", "gate", "mirror", "only", "groups", "name",
                                                       "drape", "bridge", "beneath", "pair", "midline", "behind",
                                                       "window")),
    "unwrap": (("bone", "radius"), ("offset", "mirror", "only", "groups", "shrink", "name")),
    "hem": (("bone", "radius", "edge", "groups"), ("offset", "mirror", "only", "relax", "inset", "width", "name")),
    "bind": (("bone", "radius", "groups", "to"), ("offset", "mirror", "only", "name", "reach", "fade", "near")),
    "reweight": (("bone", "radius", "take", "into", "share"), ("z", "x", "offset", "mirror", "only", "groups", "name")),
    "relax": (("bone", "radius", "passes"), ("offset", "mirror", "only", "groups", "open", "name")),
    "island": (("bone", "radius", "rects", "groups"), ("offset", "mirror", "only", "name", "uv")),
    "atlas": (("groups", "rect"), ("name",)),
    "tube": (("bone", "path", "radius", "group", "rect"), ("sides", "rings", "flat", "across", "closed", "follow",
                                                            "segments", "name", "fade", "reach", "facets", "smooth",
                                                            "under", "skip", "hang")),
    "cut": (("bone", "normal", "radius", "groups"), ("offset", "only", "name", "under", "press", "trim", "uv", "snap",
                                                      "corner")),
    "thicken": (("bone", "radius", "depth"), ("offset", "mirror", "only", "groups", "name", "taper")),
}


def _group_list(where: str, groups) -> tuple[int, ...]:
    if not isinstance(groups, list) or not groups or not all(
            isinstance(g, int) and not isinstance(g, bool) and g >= 0 for g in groups):
        raise ValueError(f"{where}: {groups!r} is not a list of mesh group indices")
    return tuple(groups)


def _mesh_op(at: str, op):
    """One of ``mesh.ops`` (:mod:`azurik_mod.assets.mesh_edit`'s rules)."""
    if not isinstance(op, dict) or op.get("op") not in OPS:
        raise ValueError(f"{at}.op {op.get('op') if isinstance(op, dict) else op!r} is not one of {', '.join(OPS)}")
    kind = op["op"]
    required, optional = _OP_KEYS[kind]
    _keys(at, op, ("op", *required), optional)
    if kind == "tuck":
        direction = _vec(f"{at}.dir", op["dir"], 3)
        try:
            push_frame(direction)
        except ValueError as exc:
            raise ValueError(f"{at}: {exc}") from None
        margin = _num(f"{at}.margin", op["margin"])
        if margin < 0:
            raise ValueError(f"{at}.margin: {margin:g} must be at least 0")
        strict, faces = op.get("strict", False), op.get("faces", False)
        for key, flag in (("strict", strict), ("faces", faces)):
            if not isinstance(flag, bool):
                raise ValueError(f"{at}.{key} {flag!r} is not true or false")
        band = None
        if "band" in op:
            band = _vec(f"{at}.band", op["band"], 2)
            if not band[0] < band[1]:
                raise ValueError(f"{at}.band: {list(band)} must rise")
        return TuckOp(_group_list(f"{at}.groups", op["groups"]), _group_list(f"{at}.under", op["under"]), direction,
                      margin, _positive(f"{at}.window", op.get("window", 0.05)), _names(f"{at}.skip", op.get("skip", [])),
                      _names(f"{at}.only", op.get("only", [])),
                      _string(f"{at}.name", op["name"]) if "name" in op else "", strict, band, faces)
    if kind == "tube":
        path = op["path"]
        if not isinstance(path, list) or len(path) < 2:
            raise ValueError(f"{at}.path: a list of 2 or more [x, y, z] offsets from the bone")
        pts = tuple(_vec(f"{at}.path[{k}]", q, 3) for k, q in enumerate(path))
        radius = op["radius"]
        if not isinstance(radius, list) or len(radius) != len(pts):
            raise ValueError(f"{at}.radius: one radius a path point ({len(pts)})")
        radii = tuple(_positive(f"{at}.radius[{k}]", r) for k, r in enumerate(radius))
        rect = _vec(f"{at}.rect", op["rect"], 4)
        counts = {}
        for key, default in (("sides", 16), ("rings", 32), ("segments", 0)):
            v = op.get(key, default)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"{at}.{key} {v!r} is not a count")
            counts[key] = v
        group = op["group"]
        if not isinstance(group, int) or isinstance(group, bool) or group < 0:
            raise ValueError(f"{at}.group {group!r} is not a mesh group index")
        closed = op.get("closed", False)
        if not isinstance(closed, bool):
            raise ValueError(f"{at}.closed {closed!r} is not true or false")
        fade = None
        if "fade" in op:
            _keys(f"{at}.fade", op["fade"], ("bone", "from", "to"))
            fade = (_string(f"{at}.fade.bone", op["fade"]["bone"]), _num(f"{at}.fade.from", op["fade"]["from"]),
                    _num(f"{at}.fade.to", op["fade"]["to"]))
            if not 0.0 <= fade[1] < fade[2] <= 1.0 or "follow" in op:
                raise ValueError(f"{at}.fade: from and to rise within 0..1 (shares of its length), on a tube with no "
                                 "follow")
        reach = op.get("reach", 0.0)
        if isinstance(reach, list):
            if len(reach) != len(pts):
                raise ValueError(f"{at}.reach: {len(reach)} numbers for {len(pts)} path points (one a point, or one)")
            reach = tuple(_num(f"{at}.reach[{j}]", r) for j, r in enumerate(reach))
        else:
            reach = _num(f"{at}.reach", reach)
        most = max(reach) if isinstance(reach, tuple) else reach
        least = min(reach) if isinstance(reach, tuple) else reach
        if least < 0 or (most > 0 and "follow" not in op):
            raise ValueError(f"{at}.reach: at least 0, and above 0 only with follow")
        facets = op.get("facets", False)
        if not isinstance(facets, bool):
            raise ValueError(f"{at}.facets {facets!r} is not true or false")
        smooth = op.get("smooth", 0.0)
        if isinstance(smooth, list):
            if len(smooth) != len(pts):
                raise ValueError(f"{at}.smooth: {len(smooth)} numbers for {len(pts)} path points (one a point, or one)")
            smooth = tuple(_num(f"{at}.smooth[{j}]", s) for j, s in enumerate(smooth))
        else:
            smooth = _num(f"{at}.smooth", smooth)
        if (min(smooth) if isinstance(smooth, tuple) else smooth) < 0 or (
                (max(smooth) if isinstance(smooth, tuple) else smooth) > 0 and (most <= 0 or facets)):
            raise ValueError(f"{at}.smooth: at least 0, and above 0 only with a reach and no facets")
        under = op.get("under", 0.0)
        if isinstance(under, list):
            if len(under) != len(pts):
                raise ValueError(f"{at}.under: {len(under)} numbers for {len(pts)} path points (one a point, or one)")
            under = tuple(_num(f"{at}.under[{j}]", u) for j, u in enumerate(under))
        else:
            under = _num(f"{at}.under", under)
        lo_u, hi_u = (min(under), max(under)) if isinstance(under, tuple) else (under, under)
        if lo_u < 0 or hi_u > 1 or (hi_u > 0 and (most <= 0 or facets)):
            raise ValueError(f"{at}.under: from 0 to 1, and above 0 only with a reach and no facets")
        hang = _string(f"{at}.hang", op["hang"]) if "hang" in op else ""
        if hang and most <= 0:
            raise ValueError(f"{at}.hang: W29 hangs a tube that rides the skin as one piece: only with a reach")
        return TubeOp(bone=_string(f"{at}.bone", op["bone"]), path=pts, radius=radii, group=group, rect=rect,
                      fade=fade, reach=reach, facets=facets, smooth=smooth, under=under, hang=hang,
                      skip=_names(f"{at}.skip", op["skip"]) if "skip" in op else (),
                      flat=_positive(f"{at}.flat", op.get("flat", 1.0)),
                      across=_vec(f"{at}.across", op.get("across", [1.0, 0.0, 0.0]), 3), closed=closed,
                      follow=_group_list(f"{at}.follow", op["follow"]) if "follow" in op else (),
                      name=_string(f"{at}.name", op["name"]) if "name" in op else "", **counts)
    if kind == "cut":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        normal = _vec(f"{at}.normal", op["normal"], 3)
        if not any(normal):
            raise ValueError(f"{at}.normal is zero")
        press = trim = foot = None
        if "press" in op:
            _keys(f"{at}.press", op["press"], ("depth", "width"), ("swell", "thick", "origin"))
            depth, width = _num(f"{at}.press.depth", op["press"]["depth"]), _positive(f"{at}.press.width",
                                                                                    op["press"]["width"])
            swell, thick = (_num(f"{at}.press.{k}", op["press"].get(k, 0.0)) for k in ("swell", "thick"))
            if depth < 0 or swell < 0 or thick < 0:
                raise ValueError(f"{at}.press: depth, swell and thick are at least 0")
            press = (depth, width, swell, thick, _vec(f"{at}.press.origin", op["press"].get("origin", [0, 0, 0]), 3))
        if "trim" in op:
            _keys(f"{at}.trim", op["trim"], ("radius", "rect"), ("flat", "sides", "foot"))
            sides = op["trim"].get("sides", 8)
            if not isinstance(sides, int) or isinstance(sides, bool):
                raise ValueError(f"{at}.trim.sides {sides!r} is not a count")
            rect = _vec(f"{at}.trim.rect", op["trim"]["rect"], 4)
            trim = (_positive(f"{at}.trim.radius", op["trim"]["radius"]),
                    _positive(f"{at}.trim.flat", op["trim"].get("flat", 1.0)), sides, rect)
            if "foot" in op["trim"]:
                length, lift = _vec(f"{at}.trim.foot", op["trim"]["foot"], 2)
                if not (length > 0 and lift >= 0) or not op.get("snap"):
                    raise ValueError(f"{at}.trim.foot: [length (above 0), lift (at least 0)] on a snapped cut's cord")
                foot = (length, lift)
        snap = op.get("snap", False)
        if not isinstance(snap, bool):
            raise ValueError(f"{at}.snap {snap!r} is not true or false")
        corner = None
        if "corner" in op:
            _keys(f"{at}.corner", op["corner"], ("normal", "offset", "radius"))
            n2 = _vec(f"{at}.corner.normal", op["corner"]["normal"], 3)
            if not any(n2):
                raise ValueError(f"{at}.corner.normal is zero")
            corner = (n2, _vec(f"{at}.corner.offset", op["corner"]["offset"], 3),
                      _positive(f"{at}.corner.radius", op["corner"]["radius"]))
        return CutOp(bone=_string(f"{at}.bone", op["bone"]), normal=normal, radius=radius, snap=snap, corner=corner,
                     groups=_group_list(f"{at}.groups", op["groups"]),
                     offset=_vec(f"{at}.offset", op.get("offset", [0.0, 0.0, 0.0]), 3),
                     only=_names(f"{at}.only", op.get("only", [])),
                     name=_string(f"{at}.name", op["name"]) if "name" in op else "",
                     under=_group_list(f"{at}.under", op["under"]) if "under" in op else (), press=press, trim=trim,
                     uv=_vec(f"{at}.uv", op["uv"], 4) if "uv" in op else None, foot=foot)
    if kind == "atlas":
        rect = _vec(f"{at}.rect", op["rect"], 4)
        if not (0 <= rect[0] < rect[2] <= 1 and 0 <= rect[1] < rect[3] <= 1):
            raise ValueError(f"{at}.rect: {list(rect)} is not a rect inside 0..1 (u0, v0, u1, v1)")
        return AtlasOp(_group_list(f"{at}.groups", op["groups"]), rect,
                       _string(f"{at}.name", op["name"]) if "name" in op else "")
    common = {"bone": _string(f"{at}.bone", op["bone"]),
              "offset": _vec(f"{at}.offset", op.get("offset", [0.0, 0.0, 0.0]), 3),
              "only": _names(f"{at}.only", op.get("only", []))}
    if "name" in op:
        common["name"] = _string(f"{at}.name", op["name"])
    if "groups" in op:
        common["groups"] = _group_list(f"{at}.groups", op["groups"])
    if kind != "taper":
        mirror = op.get("mirror", False)
        if not isinstance(mirror, bool):
            raise ValueError(f"{at}.mirror {mirror!r} is not true or false")
        common["mirror"] = mirror
    if kind == "thicken":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        taper = _num(f"{at}.taper", op.get("taper", 0.0))
        if taper < 0:
            raise ValueError(f"{at}.taper: {taper:g} must be 0 or above (a length; 0: none)")
        return ThickenOp(radius=radius, depth=_positive(f"{at}.depth", op["depth"]), taper=taper, **common)
    if kind == "round":
        direction = _vec(f"{at}.dir", op.get("dir", [0.0, 1.0, 0.0]), 3)
        try:
            push_frame(direction)
        except ValueError as exc:
            raise ValueError(f"{at}: {exc}") from None
        _keys(f"{at}.radius", op["radius"], ("across", "along", "up", "down"),
              ("inner", "back", "taper", "taper_in", "taper_back", "taper_low"))
        radius = tuple(_positive(f"{at}.radius.{k}", op["radius"][k]) for k in ("across", "along", "up", "down"))
        inner = _positive(f"{at}.radius.inner", op["radius"]["inner"]) if "inner" in op["radius"] else 0.0
        back = _positive(f"{at}.radius.back", op["radius"]["back"]) if "back" in op["radius"] else 0.0
        if back and not op.get("pair"):
            raise ValueError(f"{at}.radius.back: a pair's (its one origin may sit behind the centre)")
        taper = _num(f"{at}.radius.taper", op["radius"].get("taper", 0.0))
        taper_in = _num(f"{at}.radius.taper_in", op["radius"].get("taper_in", 0.0))
        if not (0 <= taper < 1 and 0 <= taper_in < 1):
            raise ValueError(f"{at}.radius.taper / taper_in: {taper:g}, {taper_in:g} must be at least 0 and under 1 "
                             "(the share of across the top loses)")
        tapers = {}
        for key in ("taper_back", "taper_low"):
            if key in op["radius"]:
                share, reach = _vec(f"{at}.radius.{key}", op["radius"][key], 2)
                if not (0 <= share < 1 and reach >= 0):
                    raise ValueError(f"{at}.radius.{key}: [{share:g}, {reach:g}] must be [the share of across lost, "
                                     "at least 0 and under 1; its reach, at least 0 (0: the back or down half axis)]")
                tapers[key] = (share, reach)
        midline = None
        if "midline" in op:
            midline = _vec(f"{at}.midline", op["midline"],
                           len(op["midline"]) if isinstance(op["midline"], list) and len(op["midline"]) in (4, 5) else 3)
            if not (midline[0] < midline[1] and midline[2] > 0 and (len(midline) < 5 or midline[4] > 0)):
                raise ValueError(f"{at}.midline: {list(midline)} must be [z from, z to (above it), width (above 0)"
                                 "[, behind (y)[, span (above 0)]]]")
        origin, inward = op["origin"], 0.0
        if isinstance(origin, dict):
            _keys(f"{at}.origin", origin, ("back",), ("in",))
            origin, inward = _num(f"{at}.origin.back", origin["back"]), _num(f"{at}.origin.in", origin.get("in", 0.0))
        else:
            origin = _num(f"{at}.origin", origin)
        if not 0 <= origin or (not op.get("pair") and (
                origin >= radius[1] or fdlibm.sq(origin / radius[1]) + fdlibm.sq(inward / (inner or radius[0])) >= 1)):
            raise ValueError(f"{at}.origin: back {origin:g}, in {inward:g} must put the rays' start inside the "
                             "ellipsoid (a pair's may start behind it), back at least 0")
        blend, inner_blend = op["blend"], None
        if isinstance(blend, dict):
            _keys(f"{at}.blend", blend, ("up", "down"), ("inner",))
            if "inner" in blend:
                inner_blend = _vec(f"{at}.blend.inner", blend["inner"], 3)
                if not (inner_blend[0] > 0 and 0 <= inner_blend[1] < inner_blend[2]):
                    raise ValueError(f"{at}.blend.inner: {list(inner_blend)} must be [down (above 0), x full, x none "
                                     "(above x full, at least 0)]")
            blend = (_positive(f"{at}.blend.up", blend["up"]), _positive(f"{at}.blend.down", blend["down"]))
        else:
            blend = (_positive(f"{at}.blend", blend),) * 2
        gate = None
        if "gate" in op:
            gate = _vec(f"{at}.gate", op["gate"], 2)
            if not -1 <= gate[0] < gate[1] <= 1:
                raise ValueError(f"{at}.gate: {list(gate)} must rise within -1 to 1 (the ray's cosine to dir)")
        drape, ease = None, 0.0
        if "drape" in op:
            _keys(f"{at}.drape", op["drape"], ("anchor",), ("fade", "tilt", "ease"))
            ease = _num(f"{at}.drape.ease", op["drape"].get("ease", 0.0))
            if ease < 0:
                raise ValueError(f"{at}.drape.ease: {ease:g} must be at least 0")
            anchor = _vec(f"{at}.drape.anchor", op["drape"]["anchor"], 2)
            fade = _vec(f"{at}.drape.fade", op["drape"].get("fade", [0.5, 1.0]), 2)
            if not 0 <= fade[0] < fade[1] <= 1:
                raise ValueError(f"{at}.drape.fade: {list(fade)} must rise within 0 to 1 "
                                 "(a share of the across half axis)")
            drape = (*anchor, *fade, _num(f"{at}.drape.tilt", op["drape"].get("tilt", 0.0)))
        bridge = _num(f"{at}.bridge", op.get("bridge", 0.0))
        if bridge < 0 or (bridge > 0 and not common["mirror"]):
            raise ValueError(f"{at}.bridge: {bridge:g} is a mirrored op's smooth union across x = 0, at least 0")
        beneath = None
        if "beneath" in op:
            _keys(f"{at}.beneath", op["beneath"], ("groups", "gap"))
            gap = _num(f"{at}.beneath.gap", op["beneath"]["gap"])
            if gap < 0:
                raise ValueError(f"{at}.beneath.gap: {gap:g} must be at least 0")
            beneath = (_group_list(f"{at}.beneath.groups", op["beneath"]["groups"]), gap)
        pair = op.get("pair", False)
        if not isinstance(pair, bool) or (pair and not common["mirror"]):
            raise ValueError(f"{at}.pair {pair!r}: true or false, true for a mirrored op only")
        behind = window = None
        if "behind" in op:
            _keys(f"{at}.behind", op["behind"], ("y",), ("share", "line"))
            y_full, y_none = _vec(f"{at}.behind.y", op["behind"]["y"], 2)
            share = _num(f"{at}.behind.share", op["behind"].get("share", 1.0))
            if not (y_full != y_none and 0 < share <= 1):
                raise ValueError(f"{at}.behind: y {[y_full, y_none]} must be [full, none] apart and share "
                                 f"{share:g} above 0 and at most 1")
            line = op["behind"].get("line", [])
            if not isinstance(line, list):
                raise ValueError(f"{at}.behind.line: {line!r} is not a list of [z, y] points")
            line = tuple(_vec(f"{at}.behind.line[{j}]", q, 2) for j, q in enumerate(line))
            if any(b[0] <= a[0] for a, b in zip(line, line[1:])):
                raise ValueError(f"{at}.behind.line: its points' z must rise")
            behind = (y_full, y_none, share, line)
        if "window" in op:
            window = _vec(f"{at}.window", op["window"], 4)
            if not window[0] < window[1] <= window[2] < window[3]:
                raise ValueError(f"{at}.window: {list(window)} must be [z0, z1, z2, z3] rising (none below z0 and "
                                 "above z3, full from z1 to z2)")
        return RoundOp(radius=radius, origin=origin, blend=blend, direction=direction, gate=gate, drape=drape,
                       bridge=bridge, inward=inward, beneath=beneath, pair=pair, inner=inner, ease=ease, back=back,
                       taper=taper, taper_in=taper_in, midline=midline, inner_blend=inner_blend, behind=behind,
                       window=window, **tapers, **common)
    if kind == "reweight":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        share = _num(f"{at}.share", op["share"])
        if not 0 < share <= 1:
            raise ValueError(f"{at}.share: {share:g} must be above 0 and at most 1 (of the weight on take)")
        bands = {}
        for key in ("z", "x"):
            if key in op:
                bands[key] = _vec(f"{at}.{key}", op[key], 2)
                if not bands[key][0] < bands[key][1]:
                    raise ValueError(f"{at}.{key}: {list(bands[key])} must rise")
        return ReweightOp(radius=radius, take=_names(f"{at}.take", op["take"]), into=_string(f"{at}.into", op["into"]),
                          share=share, z=bands.get("z"), x=bands.get("x"), **common)
    if kind == "island":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        rects = op["rects"]
        if not isinstance(rects, list) or len(rects) != (2 if common["mirror"] else 1):
            raise ValueError(f"{at}.rects: one rect a side ({2 if common['mirror'] else 1}), each [u0, v0, u1, v1]")
        parsed = []
        for k, rect in enumerate(rects):
            rect = _vec(f"{at}.rects[{k}]", rect, 4)
            if not (0 <= rect[0] < rect[2] <= 1 and 0 <= rect[1] < rect[3] <= 1):
                raise ValueError(f"{at}.rects[{k}]: {list(rect)} is not a rect inside 0..1 (u0, v0, u1, v1)")
            parsed.append(rect)
        box = None
        if "uv" in op:
            box = _vec(f"{at}.uv", op["uv"], 4)
            if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                raise ValueError(f"{at}.uv: {list(box)} is not a box inside 0..1 (u0, v0, u1, v1)")
        return IslandOp(radius=radius, rects=tuple(parsed), uv=box, **common)
    if kind == "relax":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        passes, open_ = op["passes"], op.get("open", False)
        if not isinstance(passes, int) or isinstance(passes, bool) or passes < 0:
            raise ValueError(f"{at}.passes {passes!r} is not a count of passes")
        if not isinstance(open_, bool):
            raise ValueError(f"{at}.open {open_!r} is not true or false")
        return RelaxOp(radius=radius, passes=passes, open=open_, **common)
    if kind == "bind":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        to = _group_list(f"{at}.to", op["to"])
        reach, fade = _num(f"{at}.reach", op.get("reach", 0.0)), op.get("fade", False)
        if reach < 0:
            raise ValueError(f"{at}.reach: {reach:g} must be at least 0 (0: the nearest skin vertex's weights)")
        if set(to) & set(common["groups"]) and not reach > 0:
            raise ValueError(f"{at}: a layer binds to its own group only with a reach (its weights mixed within it)")
        if not isinstance(fade, bool):
            raise ValueError(f"{at}.fade {fade!r} is not true or false")
        near = None
        if "near" in op:
            near = _vec(f"{at}.near", op["near"], 2)
            if not 0.0 <= near[0] < near[1]:
                raise ValueError(f"{at}.near: {list(near)} must rise from 0 (full, none)")
        return BindOp(radius=radius, to=to, reach=reach, fade=fade, near=near, **common)
    if kind == "hem":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        relax = op.get("relax", 0)
        if not isinstance(relax, int) or isinstance(relax, bool) or relax < 0:
            raise ValueError(f"{at}.relax {relax!r} is not a count of passes")
        inset, width = _num(f"{at}.inset", op.get("inset", 0.0)), _num(f"{at}.width", op.get("width", 0.0))
        if inset < 0 or width < 0 or (inset > 0) != (width > 0):
            raise ValueError(f"{at}: inset {inset:g} and width {width:g} are both above 0 or both 0")
        return HemOp(radius=radius, edge=_positive(f"{at}.edge", op["edge"]), relax=relax, inset=inset, width=width,
                     **common)
    if kind == "unwrap":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        shrink = _num(f"{at}.shrink", op.get("shrink", 0.0))
        if not 0 <= shrink < 1:
            raise ValueError(f"{at}.shrink: {shrink:g} must be at least 0 and under 1 (the share of the way to an "
                             "island's middle its edge moves)")
        return UnwrapOp(radius=radius, shrink=shrink, **common)
    if kind == "subdivide":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        smooth = op.get("smooth", True)
        if not isinstance(smooth, bool):
            raise ValueError(f"{at}.smooth {smooth!r} is not true or false")
        apart = None
        if "apart" in op:   # Step 2.177b (its judge's F1): a layer's open edges left as the other ops leave them
            _keys(f"{at}.apart", op["apart"], ("edges", "band"))
            apart = (_group_list(f"{at}.apart.edges", op["apart"]["edges"]),
                     _positive(f"{at}.apart.band", op["apart"]["band"]))
        normals = op.get("normals", "area")
        if normals not in ("area", "angle", "nearer"):   # Steps 2.177c, 2.188: how its smooth normals weigh faces
            raise ValueError(f"{at}.normals {normals!r} is not area, angle or nearer")
        return SubdivideOp(radius=radius, edge=_positive(f"{at}.edge", op["edge"]), smooth=smooth, apart=apart,
                           normals=normals, **common)
    if kind == "scale":
        radius = _vec(f"{at}.radius", op["radius"], 3)
        for k, r in enumerate(radius):
            _positive(f"{at}.radius[{k}]", r)
        profile = op.get("profile", "cone")
        if profile not in PROFILES:
            raise ValueError(f"{at}.profile {profile!r} is not one of {', '.join(PROFILES)}")
        late = op.get("late", False)
        if not isinstance(late, bool):
            raise ValueError(f"{at}.late {late!r} is not true or false")
        return ScaleOp(radius=radius, factors=_vec(f"{at}.factors", op["factors"], 3), profile=profile, late=late,
                       **common)
    if kind == "push":
        direction = _vec(f"{at}.dir", op["dir"], 3)
        try:
            push_frame(direction)
        except ValueError as exc:
            raise ValueError(f"{at}: {exc}") from None
        _keys(f"{at}.radius", op["radius"], ("in", "out", "up", "down"))
        radius = tuple(_positive(f"{at}.radius.{k}", op["radius"][k]) for k in ("in", "out", "up", "down"))
        fold = _num(f"{at}.fold", op.get("fold", 1.0))
        if not 0 <= fold <= 1:
            raise ValueError(f"{at}.fold: {fold:g} must be from 0 (the bell) to 1 (the round fold)")
        region = op.get("region", False)
        if not isinstance(region, bool):
            raise ValueError(f"{at}.region {region!r} is not true or false")
        return PushOp(direction=direction, height=_num(f"{at}.height", op["height"]), radius=radius,
                      depth=_positive(f"{at}.depth", op["depth"]), fold=fold, region=region, **common)
    factors = _vec(f"{at}.factors", op["factors"], 2)
    for k, f in enumerate(factors):
        if not 0 < f <= 1:
            raise ValueError(f"{at}.factors[{k}]: {f:g} must be above 0 and at most 1 (a taper narrows; scale widens)")
    plateau = _num(f"{at}.plateau", op["plateau"])
    if plateau < 0:
        raise ValueError(f"{at}.plateau: {plateau:g} must be at least 0")
    reach = _vec(f"{at}.reach", op["reach"], 2)
    if not 0 <= reach[0] < reach[1]:
        raise ValueError(f"{at}.reach: {list(reach)} must rise from at least 0")
    return TaperOp(factors=factors, plateau=plateau, half=_positive(f"{at}.half", op["half"]), reach=reach, **common)


JIGGLE_KEYS = (("frees", "bones"), ("keys", "still", "loops", "springs", "clear"))
JIGGLE_BONE_KEYS = (("role", "bone", "parent", "shape", "groups", "takes", "weight", "freq", "damping", "travel",
                     "turn"), ("hang", "gain", "drive", "grade"))
JIGGLE_BAKE_KEYS = ("freq", "damping", "travel", "turn", "hang", "gain", "drive")
"""A bone's baked-spring keys (W28), which a row with a real-time
``spring`` (X41, Step 2.156) neither needs nor takes."""


def _jiggle(where: str, doc) -> jiggles.Spec:
    """The recipe's ``jiggle`` (:mod:`azurik_mod.assets.jiggle`), checked
    with no game data (the bones, groups and shapes are the build's)."""
    _keys(where, doc, *JIGGLE_KEYS)
    if not isinstance(doc["frees"], list) or not isinstance(doc["bones"], list) or not doc["bones"]:
        raise ValueError(f"{where}: frees and bones are lists, bones not empty")
    frees = []
    for i, f in enumerate(doc["frees"]):
        at = f"{where}.frees[{i}]"
        _keys(at, f, ("group", "bone"), ("into", "drop"))
        if ("into" in f) == ("drop" in f) or f.get("drop", True) is not True:
            raise ValueError(f"{at}: either into (its parent) or drop: true")
        frees.append(jiggles.Free(_group_list(f"{at}.group", [f["group"]])[0], _string(f"{at}.bone", f["bone"]),
                                  _string(f"{at}.into", f["into"]) if "into" in f else None))
    bones = []
    for i, b in enumerate(doc["bones"]):
        at = f"{where}.bones[{i}]"
        grade = None
        if isinstance(b, dict) and "grade" in b:
            _keys(f"{at}.grade", b["grade"], ("z", "floor"))
            z = _vec(f"{at}.grade.z", b["grade"]["z"], 2)
            if not z[0] < z[1]:
                raise ValueError(f"{at}.grade.z: {list(z)} must rise")
            grade = (*z, _num(f"{at}.grade.floor", b["grade"]["floor"]))
        if isinstance(b, dict) and "keyed" in b:    # keyed by its recipe's own clips alone (Step 2.168, D575)
            _keys(at, b, tuple(k for k in JIGGLE_BONE_KEYS[0] if k not in JIGGLE_BAKE_KEYS), ("keyed", "grade"))
            if b["keyed"] is not True:
                raise ValueError(f"{at}.keyed: {b['keyed']!r} is not true (a bone only the recipe's own clips key)")
            if not isinstance(b["role"], str) or not _NAME.match(b["role"]):
                raise ValueError(f"{at}.role {b['role']!r}: lower-case letters, digits and _")
            for key in ("shape", "takes"):
                if not isinstance(b[key], list) or not b[key]:
                    raise ValueError(f"{at}.{key}: {b[key]!r} is not a list of names")
            bones.append(jiggles.Bone(b["role"], _string(f"{at}.bone", b["bone"]), _string(f"{at}.parent", b["parent"]),
                                      tuple(_string(f"{at}.shape[{j}]", n) for j, n in enumerate(b["shape"])),
                                      _group_list(f"{at}.groups", b["groups"]), _names(f"{at}.takes", b["takes"]),
                                      _num(f"{at}.weight", b["weight"]), 0.0, 0.0, 0.0, 0.0, grade=grade, keyed=True))
            continue
        if isinstance(b, dict) and "spring" in b:   # X41's real-time spring (Step 2.156): no baked fields
            _keys(at, b, tuple(k for k in JIGGLE_BONE_KEYS[0] if k not in JIGGLE_BAKE_KEYS), ("spring", "grade"))
            if not isinstance(b["role"], str) or not _NAME.match(b["role"]):
                raise ValueError(f"{at}.role {b['role']!r}: lower-case letters, digits and _")
            for key in ("shape", "takes"):
                if not isinstance(b[key], list) or not b[key]:
                    raise ValueError(f"{at}.{key}: {b[key]!r} is not a list of names")
            bones.append(jiggles.Bone(b["role"], _string(f"{at}.bone", b["bone"]), _string(f"{at}.parent", b["parent"]),
                                      tuple(_string(f"{at}.shape[{j}]", n) for j, n in enumerate(b["shape"])),
                                      _group_list(f"{at}.groups", b["groups"]), _names(f"{at}.takes", b["takes"]),
                                      _num(f"{at}.weight", b["weight"]), 0.0, 0.0, 0.0, 0.0,
                                      spring=jiggle_rt.parse_spring(f"{at}.spring", b["spring"]), grade=grade))
            continue
        _keys(at, b, *JIGGLE_BONE_KEYS)
        if not isinstance(b["role"], str) or not _NAME.match(b["role"]):
            raise ValueError(f"{at}.role {b['role']!r}: lower-case letters, digits and _")
        if not isinstance(b["shape"], list) or not b["shape"]:
            raise ValueError(f"{at}.shape: {b['shape']!r} is not a list of mesh op names")
        if not isinstance(b["takes"], list) or not b["takes"]:
            raise ValueError(f"{at}.takes: {b['takes']!r} is not a list of bone names")
        damping = _num(f"{at}.damping", b["damping"])
        if damping < 0:
            raise ValueError(f"{at}.damping: {damping:g} must be at least 0")
        bones.append(jiggles.Bone(b["role"], _string(f"{at}.bone", b["bone"]), _string(f"{at}.parent", b["parent"]),
                                  tuple(_string(f"{at}.shape[{j}]", n) for j, n in enumerate(b["shape"])),
                                  _group_list(f"{at}.groups", b["groups"]), _names(f"{at}.takes", b["takes"]),
                                  _num(f"{at}.weight", b["weight"]),
                                  _positive(f"{at}.freq", b["freq"]), damping, _positive(f"{at}.travel", b["travel"]),
                                  _positive(f"{at}.turn", b["turn"]), _num(f"{at}.hang", b.get("hang", 1.0)),
                                  _num(f"{at}.gain", b.get("gain", 1.0)),
                                  _positive(f"{at}.drive", b["drive"]) if "drive" in b else None, grade=grade))
    springs = _springs(f"{where}.springs", doc.get("springs", []))
    roles = [b.role for b in (*bones, *springs)]
    if len(set(roles)) < len(roles):
        raise ValueError(f"{where}: two bones or springs take the role "
                         f"{next(r for r in roles if roles.count(r) > 1)!r}")
    lists = {}
    for field in ("still", "loops"):
        names = doc.get(field, [])
        if not isinstance(names, list):
            raise ValueError(f"{where}.{field}: {names!r} is not a list of clip names")
        lists[field] = tuple(_string(f"{where}.{field}[{i}]", c) for i, c in enumerate(names))
    clear = None
    if "clear" in doc:   # a chain kept out of the body (Step 2.154b, D617)
        at = f"{where}.clear"
        _keys(at, doc["clear"], ("links", "group", "bones"), ("standoff", "clips", "held"))
        c = doc["clear"]
        for key in ("links", "bones"):
            if not isinstance(c[key], list) or not c[key]:
                raise ValueError(f"{at}.{key}: {c[key]!r} is not a list of bone names")
        group = c["group"] if isinstance(c["group"], list) else [c["group"]]   # one, or several (Step 2.169c)
        clips = c.get("clips", {})   # a clip kept out of only its own groups (Step 2.169c)
        if not isinstance(clips, dict):
            raise ValueError(f"{at}.clips: {clips!r} is not a map of clip names to mesh groups")
        held = c.get("held", [])   # the clips whose last pose the game holds (Step 2.169d)
        if not isinstance(held, list):
            raise ValueError(f"{at}.held: {held!r} is not a list of clip names")
        clear = jiggles.Clear(_names(f"{at}.links", c["links"]), _group_list(f"{at}.group", group),
                              _names(f"{at}.bones", c["bones"]), _num(f"{at}.standoff", c.get("standoff", 0.004)),
                              tuple((_string(f"{at}.clips", n), _group_list(f"{at}.clips.{n}", g))
                                    for n, g in clips.items()),
                              tuple(_string(f"{at}.held[{i}]", n) for i, n in enumerate(held)))
    return jiggles.Spec(tuple(frees), tuple(bones), _positive(f"{where}.keys", doc.get("keys", 15.0)),
                        lists["still"], lists["loops"], tuple(springs), clear)


def _springs(where: str, rows) -> tuple[jiggles.Bone, ...]:
    """``jiggle.springs`` rows (X41's on the body's own bones, Step 2.156,
    D485; :data:`CHAINS`' too), each ``role``, ``bone``, ``parent`` and
    ``spring``, checked with no game data."""
    if not isinstance(rows, list):
        raise ValueError(f"{where}: {rows!r} is not a list")
    out = []
    for i, b in enumerate(rows):
        at = f"{where}[{i}]"
        _keys(at, b, ("role", "bone", "parent", "spring"), ())
        if not isinstance(b["role"], str) or not _NAME.match(b["role"]):
            raise ValueError(f"{at}.role {b['role']!r}: lower-case letters, digits and _")
        out.append(jiggles.Bone(b["role"], _string(f"{at}.bone", b["bone"]), _string(f"{at}.parent", b["parent"]),
                                (), (), (), 0.0, 0.0, 0.0, 0.0, 0.0,
                                spring=jiggle_rt.parse_spring(f"{at}.spring", b["spring"])))
    return tuple(out)


CHAINS = BUILTIN.parent / "chains.json"
"""The hair catalogue (Step 2.169f, D536's cloth D, its B9): ``bodies``
maps a body (``characters/<body>``) to a chain of ``chains``, each a list
of ``jiggle.springs`` rows (:func:`_springs`) X41 swings on any build that
wears that body with no jiggle of its own (:func:`chain_springs`)."""


@functools.cache
def chain_springs(body: str) -> tuple[jiggles.Bone, ...]:
    """The :data:`CHAINS` rows of ``body`` (``()`` for a body it doesn't
    list); :class:`ValueError` names a catalogue that isn't one (D35)."""
    doc = json.loads(CHAINS.read_text(encoding="utf-8"))
    _keys("chains.json", doc, ("bodies", "chains"))
    chain = doc["bodies"].get(body)
    if chain is None:
        return ()
    if chain not in doc["chains"]:
        raise ValueError(f"chains.json: {body} names no chain {chain!r}")
    return _springs(f"chains.json chains.{chain}", doc["chains"][chain])


def _idles(where: str, idles) -> tuple[dict[str, str], tuple[float, float]]:
    """``idles``' slots and wait (Step 2.168, D553): keys
    :data:`~azurik_mod.patches._player_slots.IDLE_SLOTS` and ``wait``,
    the slots filled from ``idle`` on with no gap (the game's pick plays
    the run of filled slots from slot 1), the wait two finite numbers a
    float32 holds (X45's table), low first (never clamped, D23; under 10 s
    it acts as 10, the game's own check first)."""
    if not isinstance(idles, dict):
        raise ValueError(f"{where}: {idles!r} is not an object")
    for key in idles:
        if key != "wait" and key not in IDLE_SLOTS:
            raise ValueError(f"{where}.{key}: no idle slot ({', '.join(IDLE_SLOTS[:2])}-{IDLE_SLOTS[-1]}, wait)")
    slots = {k: _string(f"{where}.{k}", idles[k]) for k in IDLE_SLOTS if k in idles}
    if not slots:
        raise ValueError(f"{where}: names no slot (idle, the base, first)")
    for before, k in zip(IDLE_SLOTS, IDLE_SLOTS[1:]):
        if k in slots and before not in slots:
            raise ValueError(f"{where}.{k} without {before}: the game plays the run of filled slots from idle")
    wait = _vec(f"{where}.wait", idles.get("wait", list(IDLE_WAIT)), 2)
    for i, w in enumerate(wait):
        if abs(w) > FLT_MAX:
            raise ValueError(f"{where}.wait[{i}]: {w:g} is outside a float32 (X45's table holds it as one)")
    if wait[0] > wait[1]:
        raise ValueError(f"{where}.wait: {wait[0]:g}, {wait[1]:g} are not low <= high (s of standing)")
    return slots, (wait[0], wait[1])


def _slots(where: str, slots) -> dict[str, str]:
    """``slots`` (Step 2.171): keys :data:`~azurik_mod.patches._player_slots.
    RECIPE_SLOTS` (an idle slot is ``idles``'), each a clip's name; a
    backward gait slot and its forward twin named together, since its
    rate shares the twin's cell (:data:`~azurik_mod.patches._player_slots.
    GAIT_TWINS`)."""
    if not isinstance(slots, dict):
        raise ValueError(f"{where}: {slots!r} is not an object")
    for key in slots:
        if key in IDLE_SLOTS:
            raise ValueError(f"{where}.{key}: an idle slot; idles names those")
        if key not in RECIPE_SLOTS:
            raise ValueError(f"{where}.{key}: not a slot a recipe fills (walk, run, walk_backwards, run_backwards, "
                             "victory_1-6, jump, jump_standing, superjump, climb_drop, touchdown)")
    named = {k: _string(f"{where}.{k}", slots[k]) for k in RECIPE_SLOTS if k in slots}
    for back, forward in GAIT_TWINS.items():
        if (back in named) != (forward in named):
            raise ValueError(f"{where}.{forward if back in named else back}: missing; {back} plays at {forward}'s "
                             "cell, so a recipe names both or neither")
    return named


def drain_targets(where: str, doc) -> str:
    """A recipe's or weapon style's ``drain`` (AZ-758, Step 2.196, D765):
    ``{"targets": T}``, T one of
    :data:`~azurik_mod.patches._player_character.DRAIN_TARGETS`
    (``nearest``: the life drain takes life from its target alone, the
    critter attack_target_find picks; ``all``: from every critter its box
    touches: beamlord's, D782); any other value or key fails by
    name."""
    from azurkit.tools.characters._player_character import DRAIN_TARGETS

    _keys(where, doc, ("targets",))
    if doc["targets"] not in DRAIN_TARGETS:
        raise ValueError(f"{where}.targets: {doc['targets']!r} is not one of {', '.join(DRAIN_TARGETS)}")
    return doc["targets"]


def _variant(name: str, recipe, source: str, files: str = "") -> Variant:
    from azurkit.tools.characters._player_character import MODES, RETIRED_MODES, SIZES
    from azurkit.tools.characters._player_sounds import SOUND_MODES

    where = f"variant {name!r} ({source})"
    if not _NAME.match(name):
        raise ValueError(f"{where}: a variant's name is lower-case letters, digits and _, starting with a letter")
    _keys(where, recipe, ("base",), tuple(k for k in FIELDS if k != "base"))
    base = _string(f"{where}: base", recipe["base"])
    if base == PLAYER:   # Step 2.206 (D813): what has no meaning on his own body
        for key, (value, why) in GARRET4_REFUSED.items():
            if recipe.get(key) == value:
                raise ValueError(f"{where}: {key} {value}: a recipe on garret4's own body can't ask it: {why}")
        if "fx_ring" in recipe:
            raise ValueError(f"{where}: fx_ring: a recipe on garret4's own body can't ask it: {G4_NO_RING}")
    mode = recipe.get("mode", "own")
    if mode in RETIRED_MODES:
        raise ValueError(f"{where}: mode {RETIRED_MODES[mode]}")
    for key, value, allowed in (("mode", mode, MODES), ("size", recipe.get("size", "own"), SIZES),
                                ("sounds", recipe.get("sounds", "own"), SOUND_MODES)):
        if value not in allowed:
            raise ValueError(f"{where}: {key} {value!r} is not one of {', '.join(allowed)}")
    for key in LABELS:
        if key in recipe and not isinstance(recipe[key], str):
            raise ValueError(f"{where}: {key} {recipe[key]!r} is not text")
    attacks = recipe.get("attacks", {})
    _keys(f"{where}: attacks", attacks, (), ATTACKS)
    numbers = {k: _num(f"{where}: attacks.{k}", attacks[k]) for k in ("reach", "damage", "speed") if k in attacks}
    for k in ("balance", "ground", "through_walls"):
        if k in attacks and not isinstance(attacks[k], bool):
            raise ValueError(f"{where}: attacks.{k} {attacks[k]!r} is not true or false")
    fx = _fx_edits(f"{where}: fx", recipe.get("fx", []))
    grafts = recipe.get("fx_grafts", [])
    if not isinstance(grafts, list):
        raise ValueError(f"{where}: fx_grafts {grafts!r} is not a list")
    for i, graft in enumerate(grafts):
        _graft(f"{where}: fx_grafts[{i}]", graft)
    markers = recipe.get("markers", [])
    if not isinstance(markers, list):
        raise ValueError(f"{where}: markers {markers!r} is not a list")
    for i, m in enumerate(markers):
        _string(f"{where}: markers[{i}]", m)
    marker_source = _string(f"{where}: marker_source", recipe.get("marker_source", PLAYER))
    clips = recipe.get("clips", {})
    if not isinstance(clips, dict):
        raise ValueError(f"{where}: clips {clips!r} is not an object")
    for clip, params in clips.items():
        at = f"{where}: clips.{clip}"
        if not _NAME.match(clip):
            raise ValueError(f"{at}: a clip's name is lower-case letters, digits and _")
        if not isinstance(params, dict) or params.get("generator") not in GENERATORS:
            raise ValueError(f"{at}: generator {params.get('generator') if isinstance(params, dict) else params!r} "
                             f"is not one of {', '.join(GENERATORS)}")
        if not isinstance(params.get("seek", False), bool):
            raise ValueError(f"{at}.seek: {params['seek']!r} is not true or false")
        GENERATORS[params["generator"]].check(at, {k: v for k, v in params.items() if k != "seek"})
    columns = recipe.get("columns", {})
    if not isinstance(columns, dict):
        raise ValueError(f"{where}: columns {columns!r} is not an object")
    for column, clip in columns.items():
        _string(f"{where}: columns.{column}", clip)
        if column == ROLL:
            raise ValueError(f"{where}: columns.{column}: the roll keeps garret4's roll")
    carry, held = recipe.get("carry", []), recipe.get("held", [])
    for key, names, why in (("carry", carry, "moves with the stick"), ("held", held, "chains while held")):
        if not isinstance(names, list):
            raise ValueError(f"{where}: {key} {names!r} is not a list")
        for i, column in enumerate(names):
            _string(f"{where}: {key}[{i}]", column)
            if column == ROLL:
                raise ValueError(f"{where}: {key}[{i}]: the roll never {why} (X33)")
    rotate = recipe.get("rotate", False)
    if not isinstance(rotate, bool):
        raise ValueError(f"{where}: rotate {rotate!r} is not true or false")
    if mode == "garret4" and (clips or markers or carry or held):
        raise ValueError(f"{where}: mode garret4 gives every column garret4's box and time (X3, W5), so its "
                         "clips, markers, carry and held would play no part: use mode own")
    idles, idle_wait = _idles(f"{where}: idles", recipe["idles"]) if "idles" in recipe else ({}, IDLE_WAIT)
    if mode == "garret4" and idles:
        raise ValueError(f"{where}: idles: mode garret4 plays garret4's slots; use mode own")
    slots = _slots(f"{where}: slots", recipe["slots"]) if "slots" in recipe else {}
    if mode == "garret4" and slots:
        raise ValueError(f"{where}: slots: mode garret4 plays garret4's slots; use mode own")
    cancel = recipe.get("victory_cancel")
    if cancel is not None:
        cancel = _num(f"{where}: victory_cancel", cancel)
        if abs(cancel) > FLT_MAX:
            raise ValueError(f"{where}: victory_cancel {cancel:g} is outside a float32 (X46 holds it as one)")
    voice, sfx, wavs = recipe.get("voice", "own"), recipe.get("sfx", {}), recipe.get("wavs", {})
    _sound_fields(where, name, voice, sfx, wavs)
    shouts = recipe.get("shouts")
    if shouts is not None:
        _keys(f"{where}: shouts", shouts, ("files",))
        _files(f"{where}: shouts.files", shouts["files"])
        if len(f"{VARIANT_SOUND_DIR}{name}/{SHOUT}_s") > KEY_MAX:
            raise ValueError(f"{where}: shouts: its key {VARIANT_SOUND_DIR}{name}/{SHOUT}_s is past the {KEY_MAX} "
                             "characters 0x4B680 formats")
    if (voice != "own" or sfx or wavs or shouts) and recipe.get("sounds", "own") != "own":
        raise ValueError(f"{where}: voice, sfx, wavs and shouts need sounds own; with sounds garret4 Garret's play "
                         "and they would play no part")
    mesh = _mesh(where, recipe["mesh"], source == "built-in") if "mesh" in recipe else None
    shapes = _shapes(f"{where}: shapes", recipe["shapes"], mesh) if "shapes" in recipe else ()
    plain = None
    if any(s.value != 1.0 for s in shapes):   # Step 2.164b: its ops sized as the build writes them
        plain, mesh = mesh, shaped(mesh, {op: s.value for s in shapes for op in s.sizes()})
    arms = recipe.get("arms")
    arm_clips = ()
    if arms is not None:
        _keys(f"{where}: arms", arms, ("out_deg",), ("clips",))
        if not isinstance(arms.get("clips", {}), dict):
            raise ValueError(f"{where}: arms.clips {arms['clips']!r} is not an object")
        arm_clips = tuple(sorted((_string(f"{where}: arms.clips", c).casefold(), _num(f"{where}: arms.clips.{c}", d))
                                 for c, d in arms.get("clips", {}).items()))
    poses = recipe.get("poses", [])
    if not isinstance(poses, list):
        raise ValueError(f"{where}: poses {poses!r} is not a list")
    parsed_poses = []
    for i, pz in enumerate(poses):
        at = f"{where}: poses[{i}]"
        _keys(at, pz, ("clip", "bone", "axis", "deg", "window"), ("ease",))
        axis = _vec(f"{at}.axis", pz["axis"], 3)
        if not any(axis):
            raise ValueError(f"{at}.axis is zero")
        window = _vec(f"{at}.window", pz["window"], 2)
        ease = _num(f"{at}.ease", pz.get("ease", 0.1))
        if not (0 <= window[0] <= window[1] <= 1 and ease >= 0):
            raise ValueError(f"{at}: window {list(window)} must rise within 0 to 1, ease at least 0")
        parsed_poses.append(Pose(_string(f"{at}.clip", pz["clip"]).casefold(), _string(f"{at}.bone", pz["bone"]), axis,
                                 _num(f"{at}.deg", pz["deg"]), (*window, ease)))
    parsed_poses += [Pose("", bone, axis, deg * (s.value - 1.0), (0.0, 1.0, 0.0))   # a shape's turns (Step 2.164b)
                     for s in shapes if s.value > 1.0 for bone, axis, deg in s.turns]
    jiggle = _jiggle(f"{where}: jiggle", recipe["jiggle"]) if "jiggle" in recipe else None
    if jiggle is not None and mesh is None:
        raise ValueError(f"{where}: jiggle: its shapes are mesh ops by name, and the recipe has no mesh")
    ring = check_fx_ring(f"{where}: fx_ring", recipe.get("fx_ring", {}))
    weapon = recipe.get("weapon")
    if weapon is not None and not (isinstance(weapon, str) and _NAME.match(weapon)):
        raise ValueError(f"{where}: weapon {weapon!r} is not a weapon's name (lower-case letters, digits and _)")
    effects = fx_templates.effects(f"{where}: effects", recipe.get("effects", []))
    played = [k for k in MOVES if recipe.get(k)]
    if weapon not in (None, "default", "own") and played and not moveset_moves(
            recipe, files or (name if source == "built-in" else "")):   # Step 2.161g (D585): a weapon is a whole
        # moveset; Step 2.209 (D939): a moveset weapon's moves stay, that weapon's pick
        raise ValueError(f"{where}: weapon {weapon} plays every attack column, so the recipe names no "
                         f"{' or '.join(played)}")
    painted = _textures(f"{where}: textures", recipe.get("textures", []))
    if painted and mesh is None:
        raise ValueError(f"{where}: textures: a texture is baked through the recipe's mesh, and it has none")
    scale = recipe.get("texture_scale", 1)
    if isinstance(scale, bool) or not isinstance(scale, int) or scale < 1 or scale & (scale - 1):
        raise ValueError(f"{where}: texture_scale {scale!r} is not a power of two of at least 1 (a texture's size "
                         "stays one)")
    if scale != 1 and mesh is None:
        raise ValueError(f"{where}: texture_scale: a texture is baked through the recipe's mesh, and it has none")
    colours = _colours(f"{where}: colours", recipe.get("colours", []))
    drain = drain_targets(f"{where}: drain", recipe["drain"]) if "drain" in recipe else "nearest"
    lods = recipe.get("lods", {})
    _keys(f"{where}: lods", lods, (), ("shadow", "ratio", "at", "error_px"))
    shadow = lods.get("shadow")
    if shadow is not None and not isinstance(shadow, bool):
        shadow = _num(f"{where}: lods.shadow", shadow)
        if shadow < 0:
            raise ValueError(f"{where}: lods.shadow {shadow!r} is no share of LOD 0's triangles (true, false or a "
                             "number of at least 0)")
    if shadow is not None and shadow is not False and mesh is None:
        raise ValueError(f"{where}: lods.shadow: a shadow LOD is cut from the recipe's mesh, and it has none (it "
                         "would grow a vanilla body every NPC wearing it loads)")
    screen = _lods(f"{where}: lods", lods, shadow, mesh is not None)
    return Variant(name, source, recipe.get("title", name), recipe.get("notes", ""), base, mode,
                   recipe.get("size", "own"), _num(f"{where}: scale", recipe.get("scale", 1.0)),
                   recipe.get("sounds", "own"), numbers.get("reach", 1.0), numbers.get("damage", 1.0),
                   numbers.get("speed", 1.0), attacks.get("balance"), attacks.get("ground"), tuple(markers),
                   dict(clips), dict(columns), tuple(carry), rotate, recipe_sha(recipe), voice, dict(sfx),
                   tuple(shouts["files"]) if shouts else (), mesh, attacks.get("through_walls", False), tuple(fx),
                   wavs=dict(wavs),
                   arms=0.0 if arms is None else _num(f"{where}: arms.out_deg", arms["out_deg"]), jiggle=jiggle,
                   fx_ring=ring, fx_grafts=tuple(grafts), marker_source=marker_source, held=tuple(held),
                   weapon=weapon, effects=effects, arm_clips=arm_clips, poses=tuple(parsed_poses), textures=painted,
                   shadow=shadow, lods=screen, idles=idles, idle_wait=idle_wait, slots=slots, texture_scale=scale,
                   victory_cancel=cancel, colours=colours, drain=drain, shapes=shapes,
                   unshaped=recipe_sha({k: v for k, v in recipe.items() if k != "shapes"}) if plain else "",
                   plain=plain, files=files)


def _shapes(where: str, doc, mesh: MeshSpec | None) -> tuple[Shape, ...]:
    """A recipe's ``shapes`` (Step 2.164b, D455) on its ``mesh``: each a
    name ``--player-shape`` takes, a title, the ``round`` and ``scale`` ops
    it sizes by name (an op sized by one shape) and a value above 0 (1 by
    default; finite, never clamped: D23, D45); :class:`ValueError` names a
    shape on a recipe with no mesh and, at a value other than 1, an op its
    mesh lacks or of a kind with no size (the 2.164 critique's B16; at 1.0
    a shape sizes nothing, so a mesh laid over the recipe's, a sculpt
    round's or a test's, needn't hold its ops)."""
    if not isinstance(doc, dict):
        raise ValueError(f"{where}: {doc!r} is not an object of shapes")
    if mesh is None:
        raise ValueError(f"{where}: a shape sizes the recipe's mesh ops, and it has no mesh")
    kinds: dict[str, set[type]] = {}
    for op in mesh.ops:
        if getattr(op, "name", ""):
            kinds.setdefault(op.name, set()).add(type(op))
    out, taken = [], {}
    for name, shape in doc.items():
        at = f"{where}.{name}"
        if not _NAME.match(name):
            raise ValueError(f"{at}: a shape's name is lower-case letters, digits and _, starting with a letter")
        _keys(at, shape, ("title", "ops"), ("value", "turns", "below"))
        ops = _names(f"{at}.ops", shape["ops"])
        below = _names(f"{at}.below", shape.get("below", []))
        value = _positive(f"{at}.value", shape.get("value", 1.0))
        turns = shape.get("turns", [])
        if not isinstance(turns, list):
            raise ValueError(f"{at}.turns: {turns!r} is not a list of turns")
        turned = []
        for j, turn in enumerate(turns):
            _keys(f"{at}.turns[{j}]", turn, ("bone", "axis", "deg"))
            axis = _vec(f"{at}.turns[{j}].axis", turn["axis"], 3)
            if not any(axis):
                raise ValueError(f"{at}.turns[{j}].axis is zero")
            turned.append((_string(f"{at}.turns[{j}].bone", turn["bone"]), axis,
                           _num(f"{at}.turns[{j}].deg", turn["deg"])))
        if not ops:
            raise ValueError(f"{at}.ops: it names no mesh op to size")
        for key, names, sizing in (("ops", ops, value != 1.0), ("below", below, value < 1.0)):
            for op in names:
                if not sizing and op not in kinds:   # it sizes nothing (another mesh laid over: a sculpt round's)
                    continue
                if op not in kinds:
                    raise ValueError(f"{at}.{key}: the recipe's mesh has no op named {op!r} to size")
                if (other := sorted(k.__name__[:-2].lower() for k in kinds[op] if k not in SIZES)) and sizing:
                    raise ValueError(f"{at}.{key}: {op!r} is a {other[0]} op, which has no size a shape scales (only "
                                     f"{' and '.join(SIZES.values())} ops)")
                if op in taken:
                    raise ValueError(f"{at}.{key}: {op!r} is sized by shape {taken[op]!r} too (an op by one shape)")
                taken[op] = name
        out.append(Shape(name, _string(f"{at}.title", shape["title"]), ops, value, tuple(turned), below))
    return tuple(out)


def _lods(where: str, lods: dict, shadow, mesh: bool) -> Lods | None:
    """A recipe's ``lods.ratio``, ``at`` and ``error_px`` (:class:`Lods`),
    ``None`` for none; :class:`ValueError` names a ratio list past the
    game's four switch cells, a share outside (0, 1], an ``at`` not one a
    LOD, NaN or inf, a negative ``error_px``, a ``shadow`` beside them
    and LODs on a recipe with no mesh."""
    from azurkit.tools.characters.lods import PICKED, SHADOW_LOD

    if not {"ratio", "at", "error_px"} & set(lods):
        return None
    ratio = lods.get("ratio")
    if not isinstance(ratio, list):
        raise ValueError(f"{where}.ratio {ratio!r} is not a list of shares of LOD 0's triangles, one a LOD past LOD 0 "
                         "([] drops them)")
    if len(ratio) > PICKED:
        raise ValueError(f"{where}.ratio: {len(ratio)} LODs past LOD 0, and the game switches among at most {PICKED} "
                         f"(lodThreshold1-{PICKED}, 0x3EE73)")
    shares = tuple(_num(f"{where}.ratio[{i}]", r) for i, r in enumerate(ratio))
    for i, r in enumerate(shares):
        if not 0 < r <= 1:
            raise ValueError(f"{where}.ratio[{i}] {r:g} is no share of LOD 0's triangles (above 0, at most 1)")
    at = lods.get("at", [])
    if not isinstance(at, list) or len(at) != len(shares):
        raise ValueError(f"{where}.at {at!r} is not a list of {len(shares)} switch distances (m), one a LOD of "
                         "lods.ratio")
    px = lods.get("error_px")
    if px is not None:
        px = _num(f"{where}.error_px", px)
        if px < 0:
            raise ValueError(f"{where}.error_px {px:g} is not a count of screen lines of at least 0")
        if not shares:
            raise ValueError(f"{where}.error_px: no LOD to stop the cut of (lods.ratio [] drops them)")
    if not mesh:
        raise ValueError(f"{where}.ratio: LODs are cut from the recipe's mesh, and it has none (they would "
                         f"{'grow' if shares else 'cut'} a vanilla body every NPC wearing it loads)")
    if shares and shadow is not None:
        raise ValueError(f"{where}.shadow: with LODs of its own the realtime shadow draws their LOD {SHADOW_LOD} "
                         "(0x3E8B1), so it takes no shadow LOD (W36) beside them")
    return Lods(shares, tuple(_num(f"{where}.at[{i}]", d) for i, d in enumerate(at)), px)


PAINT_REGION = ("bone", "offset", "radius", "mirror", "only", "groups", "z", "feather", "uv")
PAINT_NUMBERS = {
    "skin": (("hue", "from"), ("sat", "value", "detail", "lift", "match")),
    "shade": ((), ("ao", "reach", "light", "warm", "from", "skip")),
    "metal": (("hue",), ("sat", "value", "clean", "contrast", "gain", "chroma")),
    "strands": ((), ("below", "count", "seed", "value", "sheen", "from", "tint", "dark")),
    "fill": (("colour",), ("mix",)),
    "sharpen": (("amount",), ("texels",)),
}
"""A paint op's numbers (:mod:`azurik_mod.assets.paint`), required and optional."""


def _paint_region(at: str, spec) -> "paint.Region":
    from azurkit.tools.characters import paint
    if not isinstance(spec, dict):
        raise ValueError(f"{at}: {spec!r} is not an object")
    kw = {}
    if "bone" in spec:
        kw["bone"] = _string(f"{at}.bone", spec["bone"])
        kw["radius"] = _vec(f"{at}.radius", spec.get("radius", [1.0, 1.0, 1.0]), 3)
        for k, r in enumerate(kw["radius"]):
            _positive(f"{at}.radius[{k}]", r)
        kw["offset"] = _vec(f"{at}.offset", spec.get("offset", [0.0, 0.0, 0.0]), 3)
        mirror = spec.get("mirror", False)
        if not isinstance(mirror, bool):
            raise ValueError(f"{at}.mirror {mirror!r} is not true or false")
        kw["mirror"] = mirror
        kw["only"] = _names(f"{at}.only", spec.get("only", []))
    elif any(k in spec for k in ("radius", "offset", "mirror", "only")):
        raise ValueError(f"{at}: radius, offset, mirror and only need a bone")
    if "groups" in spec:
        kw["groups"] = _group_list(f"{at}.groups", spec["groups"])
    if "z" in spec:
        kw["z"] = _vec(f"{at}.z", spec["z"], 2)
        if not kw["z"][0] < kw["z"][1]:
            raise ValueError(f"{at}.z: {list(kw['z'])} must rise")
    if "feather" in spec:
        kw["feather"] = _num(f"{at}.feather", spec["feather"])
        if kw["feather"] < 0:
            raise ValueError(f"{at}.feather: {kw['feather']:g} must be at least 0")
    if "uv" in spec:
        kw["uv"] = _vec(f"{at}.uv", spec["uv"], 4)
        if not (kw["uv"][0] < kw["uv"][2] and kw["uv"][1] < kw["uv"][3]):
            raise ValueError(f"{at}.uv: {list(kw['uv'])} is not a rect (u0, v0, u1, v1)")
    return paint.Region(**kw)


def _textures(where: str, spec) -> tuple:
    """The recipe's ``textures`` (W30, Step 2.154 round 3), checked with no
    game data: each a material ``row``, a power-of-two ``size``, a format
    and paint ops."""
    from azurkit.tools.characters import paint
    if not isinstance(spec, list):
        raise ValueError(f"{where}: {spec!r} is not a list")
    out, rows = [], set()
    for i, t in enumerate(spec):
        at = f"{where}[{i}]"
        _keys(at, t, ("row", "size"), ("format", "ops"))
        row, size = t["row"], t["size"]
        if not isinstance(row, int) or isinstance(row, bool) or row < 0 or row in rows:
            raise ValueError(f"{at}.row {row!r} is not a material row (each once)")
        if not isinstance(size, int) or isinstance(size, bool) or size < 4 or size > 4096 or size & (size - 1):
            raise ValueError(f"{at}.size {size!r} is not a power of two from 4 to 4096")
        fmt = t.get("format", "dxt1")
        if fmt not in textures.FORMATS:
            raise ValueError(f"{at}.format {fmt!r} is not one of {', '.join(textures.FORMATS)}")
        ops = []
        for j, op in enumerate(t.get("ops", [])):
            oat = f"{at}.ops[{j}]"
            if not isinstance(op, dict) or op.get("op") not in PAINT_NUMBERS:
                raise ValueError(f"{oat}.op is not one of {', '.join(PAINT_NUMBERS)}")
            required, optional = PAINT_NUMBERS[op["op"]]
            _keys(oat, op, ("op", *required), (*optional, *PAINT_REGION))
            numbers, source = {}, None
            for key in (*required, *optional):
                if key not in op:
                    continue
                if key == "from" and op["op"] == "skin":
                    source = _paint_region(f"{oat}.from", op["from"])
                elif key in ("hue", "from", "match", "tint", "colour"):
                    numbers[key] = _vec(f"{oat}.{key}", op[key], 3 if key in ("from", "tint", "colour") else 2)
                    if key == "colour" and not all(0.0 <= c <= 1.0 for c in numbers[key]):
                        raise ValueError(f"{oat}.colour: {list(numbers[key])} is RGB within 0..1")
                elif key == "skip":
                    numbers[key] = _group_list(f"{oat}.skip", op[key])
                else:
                    numbers[key] = _num(f"{oat}.{key}", op[key])
                    if key == "mix" and not 0.0 <= numbers[key] <= 1.0:
                        raise ValueError(f"{oat}.mix: {numbers[key]} is a share within 0..1")
            ops.append(paint.PaintOp(op["op"], _paint_region(oat, {k: op[k] for k in PAINT_REGION if k in op}),
                                     numbers, source))
        rows.add(row)
        out.append(paint.TextureSpec(row, size, fmt, tuple(ops)))
    return tuple(out)


COLOUR_NUMBERS = {
    "hsv": ((), ("hue", "sat", "value", "window", "soft", "spread", "sat_min", "value_min")),
    "swap": (("from", "to"), ("reach",)),
    "png": (("file", "sha256"), ()),
}
"""A ``colours`` op's numbers (:mod:`azurik_mod.assets.paint`), required and optional (a ``png`` op's: its
file, beside the recipe, :func:`colour_folder`)."""


def _colours(where: str, spec) -> tuple:
    """The recipe's ``colours`` (W38, Step 2.170b), checked with no game
    data: each entry ``ops`` and an optional material ``row`` (each row
    once, and one entry with none); a ``textures`` entry's ``size`` and
    ``format``, W30's bake ops and a region's keys are refused by name (a
    colour has no mesh to bake through or select by), as is a ``swap``
    from a grey, which has no hue, and a ``png`` op (Step 2.203: a file
    and its sha256, no file read here) but first in a named row's entry
    (it replaces the texture the ops before it would recolour)."""
    from azurkit.tools.characters import paint
    if not isinstance(spec, list):
        raise ValueError(f"{where}: {spec!r} is not a list")
    out, rows = [], set()
    for i, t in enumerate(spec):
        at = f"{where}[{i}]"
        if isinstance(t, dict) and {"size", "format"} & set(t):
            raise ValueError(f"{at}: {', '.join(sorted({'size', 'format'} & set(t)))}: a colour keeps its texture's "
                             "size and format (a size is a textures entry's, baked through a mesh)")
        _keys(at, t, ("ops",), ("row",))
        row = t.get("row")
        if row is not None and (not isinstance(row, int) or isinstance(row, bool) or row < 0) or row in rows:
            raise ValueError(f"{at}.row {row!r} is not a material row (each once, and one entry for every row)")
        rows.add(row)
        if not isinstance(t["ops"], list) or not t["ops"]:
            raise ValueError(f"{at}.ops {t['ops']!r} is not a list of colour ops")
        ops = []
        for j, op in enumerate(t["ops"]):
            oat = f"{at}.ops[{j}]"
            kind = op.get("op") if isinstance(op, dict) else None
            if kind in PAINT_NUMBERS:
                raise ValueError(f"{oat}.op {kind!r} is a textures op, baked through a mesh: colours are "
                                 f"{' and '.join(COLOUR_NUMBERS)}")
            if kind not in COLOUR_NUMBERS:
                raise ValueError(f"{oat}.op is not one of {', '.join(COLOUR_NUMBERS)}")
            region = sorted(set(op) & set(PAINT_REGION))
            if region:
                raise ValueError(f"{oat}: {', '.join(region)}: a colour has no region (no mesh to select by): "
                                 "name a row, or a window of hues")
            required, optional = COLOUR_NUMBERS[kind]
            _keys(oat, op, ("op", *required), optional)
            if kind == "png":
                if row is None or j:
                    raise ValueError(f"{oat}: a png op is a row's texture: first in an entry naming its row")
                _file_ref(oat, {k: op[k] for k in required})
                ops.append(paint.PaintOp(kind, paint.Region(), {k: op[k] for k in required}))
                continue
            numbers = {}
            for key in (*required, *optional):
                if key in op:
                    numbers[key] = (_vec(f"{oat}.{key}", op[key], 2 if key == "window" else 3)
                                    if key in ("window", "from", "to") else _num(f"{oat}.{key}", op[key]))
            if "spread" in numbers and "window" not in numbers:
                raise ValueError(f"{oat}.spread: a hue spread is about a window's middle: give the window")
            for key in ("from", "to"):
                if key in numbers and not all(0.0 <= c <= 1.0 for c in numbers[key]):
                    raise ValueError(f"{oat}.{key}: {list(numbers[key])} is RGB within 0..1")
            if kind == "swap" and paint.hsv_of(numbers["from"])[1] < paint.GATE:
                raise ValueError(f"{oat}.from: {list(numbers['from'])} is a grey, which has no hue to swap")
            ops.append(paint.PaintOp(kind, paint.Region(), numbers))
        out.append(paint.ColourSpec(row, tuple(ops)))
    return tuple(out)


FX_RING_WRITES = ("record", "name", "set")
STAND_FIELDS = ("key", "trigger", "hold")
"""``fx_ring.stand``'s fields (D434, Step 2.155), and ``slots`` and
``fx`` (Step 2.155b)."""
HOLD_MAX = 65.535
"""s: the most ``fx_ring.stand.hold`` the ring's table holds (u16 ms)."""


def check_fx_ring(where: str, ring) -> dict | None:
    """A recipe's ``fx_ring`` (X38, Step 2.149): ``false`` turns the ring
    off for the build (``None``); else an object of ``slots`` (the copies
    the body's ``fx/fx_default`` keeps, 1-12), ``arm`` (a list of
    {``record``, ``name``, ``set``: {attribute: number}}, written on a copy
    when a throw arms it), each record checked by name at build
    (:func:`~azurik_mod.patches._player_fx_ring.ring_plan`), and
    ``stand`` (D434, Step 2.155: {``key``, another graph spawned dark at
    each throw that carries it; ``trigger``, the bound switch of that
    graph written up to 1 where the throw ends and held ``hold`` s;
    ``slots``, its copies, 1-5, default 5; ``fx``, edits as a recipe's
    ``fx`` made on the player's clone of that graph, which the ring then
    spawns, :func:`~azurik_mod.assets.fx_edit.stand_key`: Step 2.155b,
    D501}).
    :class:`ValueError` names anything else."""
    if ring is False:
        return None
    _keys(where, ring, (), ("slots", "arm", "stand"))
    n = ring.get("slots", 1)   # absent: the kit's own count
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 12:
        raise ValueError(f"{where}.slots: {n!r} is not a count of 1 to 12 copies")
    if "stand" in ring:
        stand = ring["stand"]
        _keys(f"{where}.stand", stand, STAND_FIELDS, ("slots", "fx"))
        for k in ("key", "trigger"):
            _string(f"{where}.stand.{k}", stand[k])
        hold = _num(f"{where}.stand.hold", stand["hold"])
        if not 0.0 <= hold <= HOLD_MAX:
            raise ValueError(f"{where}.stand.hold: {hold:g} s is not from 0 to {HOLD_MAX:g} s (the table holds ms "
                             "in 16 bits)")
        m = stand.get("slots", 5)
        if isinstance(m, bool) or not isinstance(m, int) or not 1 <= m <= 5:
            raise ValueError(f"{where}.stand.slots: {m!r} is not a count of 1 to 5 copies")
        _fx_edits(f"{where}.stand.fx", stand.get("fx", []))
    writes = ring.get("arm", [])
    if not isinstance(writes, list):
        raise ValueError(f"{where}.arm: {writes!r} is not a list")
    for j, w in enumerate(writes):
        at = f"{where}.arm[{j}]"
        _keys(at, w, FX_RING_WRITES)
        _index(f"{at}.record", w["record"])
        _string(f"{at}.name", w["name"])
        if not isinstance(w["set"], dict) or not w["set"]:
            raise ValueError(f"{at}.set: {w['set']!r} is not an object of attributes")
        for k, v in w["set"].items():
            _num(f"{at}.set.{_string(f'{at}.set', k)}", v)
    return json.loads(json.dumps(ring))


def _fx_edits(where: str, fx) -> list:
    """A recipe's ``fx`` edits, or its ``fx_ring.stand.fx`` (Step 2.155b),
    checked with no game data (:data:`FX_FIELDS`): ``where`` names the list."""
    if not isinstance(fx, list):
        raise ValueError(f"{where} {fx!r} is not a list")
    for i, edit in enumerate(fx):
        at = f"{where}[{i}]"
        _keys(at, edit, FX_FIELDS[:3], FX_FIELDS[3:])
        _index(f"{at}.record", edit["record"])
        _string(f"{at}.name", edit["name"])
        _string(f"{at}.type", edit["type"])
        if not any(k in edit for k in FX_FIELDS[3:]):
            raise ValueError(f"{at}: neither set, links, inherit, material, parent, texture, anchor nor mesh")
        if "parent" in edit:
            _index(f"{at}.parent", edit["parent"])
        if "anchor" in edit:
            fx_edit.check_marker(f"{at}.anchor", edit["anchor"])
        if "texture" in edit:
            _texture(f"{at}.texture", edit["texture"])
        if "mesh" in edit:
            _keys(f"{at}.mesh", edit["mesh"], ("gltf",))
            _file_ref(f"{at}.mesh.gltf", edit["mesh"]["gltf"])
        if "set" in edit and (not isinstance(edit["set"], dict) or not edit["set"]):
            raise ValueError(f"{at}.set: {edit['set']!r} is not an object of attributes")
        for k, v in edit.get("set", {}).items():
            _num(f"{at}.set.{_string(f'{at}.set', k)}", v)
        if "links" in edit and (not isinstance(edit["links"], list) or not edit["links"]):
            raise ValueError(f"{at}.links: {edit['links']!r} is not a list of link edits")
        for j, link in enumerate(edit.get("links", [])):
            _keys(f"{at}.links[{j}]", link, LINK_FIELDS[:1], LINK_FIELDS[1:])
            _index(f"{at}.links[{j}].index", link["index"])
            if len(link) < 2:
                raise ValueError(f"{at}.links[{j}]: it changes nothing (dst, dst_plug, weight or factor)")
            if "dst" in link:
                _index(f"{at}.links[{j}].dst", link["dst"])
            if "dst_plug" in link:
                _string(f"{at}.links[{j}].dst_plug", link["dst_plug"])
            for k in ("weight", "factor"):
                if k in link:
                    _num(f"{at}.links[{j}].{k}", link[k])
        if "material" in edit:
            _keys(f"{at}.material", edit["material"], (), tuple(MATERIAL_FIELDS))
            if not edit["material"]:
                raise ValueError(f"{at}.material: it changes nothing (opacity, alpha_ref or blend)")
            for k in ("opacity", "alpha_ref"):
                if k in edit["material"]:
                    _num(f"{at}.material.{k}", edit["material"][k])
            blend = edit["material"].get("blend", 0)
            if isinstance(blend, bool) or not isinstance(blend, int) or not 0 <= blend < 1 << 32:
                raise ValueError(f"{at}.material.blend: {blend!r} is not a blend type (a whole number, u32)")
        inherit = edit.get("inherit", 0)
        if isinstance(inherit, bool) or not isinstance(inherit, int) or inherit not in fx_edit.INHERIT_MODES:
            raise ValueError(f"{at}.inherit: {edit['inherit']!r} is not one of the decoded inherit modes "
                             f"{', '.join(map(str, fx_edit.INHERIT_MODES))}")
    return fx


def _texture(at: str, spec) -> None:
    """An ``fx`` edit's ``texture`` (:data:`TEXTURE_FIELDS`), checked with no game data."""
    _keys(at, spec, (), TEXTURE_FIELDS)
    if ("recolor" in spec) == ("png" in spec):
        raise ValueError(f"{at}: one of recolor and png")
    if "recolor" in spec:
        _keys(f"{at}.recolor", spec["recolor"], ("ramp",), ("gamma", "gain"))
        try:
            textures.ramp_colors(spec["recolor"]["ramp"])
        except ValueError as exc:
            raise ValueError(f"{at}.recolor.{exc}") from None
        for k in ("gamma", "gain"):
            if k in spec["recolor"] and _num(f"{at}.recolor.{k}", spec["recolor"][k]) <= 0:
                raise ValueError(f"{at}.recolor.{k}: {spec['recolor'][k]!r} is not above 0")
    if "png" in spec:
        _file_ref(f"{at}.png", spec["png"])
    if "stage" in spec:
        _index(f"{at}.stage", spec["stage"])
    if "format" in spec and spec["format"] not in textures.FORMATS:
        raise ValueError(f"{at}.format: {spec['format']!r} is not one of {', '.join(textures.FORMATS)}")


def _file_ref(at: str, ref) -> None:
    """A recipe's file ({``file``, ``sha256``}), checked with no file read."""
    _keys(at, ref, ("file", "sha256"))
    _file(f"{at}.file", ref["file"])
    if not isinstance(ref["sha256"], str) or not _SHA256.match(ref["sha256"]):
        raise ValueError(f"{at}.sha256: {ref['sha256']!r} is not 64 lower-case hex digits")


def _graft(at: str, spec) -> None:
    """A ``fx_grafts`` entry (:data:`GRAFT_FIELDS`), checked with no game data."""
    _keys(at, spec, (), GRAFT_FIELDS)
    if ("template" in spec) == ("from" in spec):
        raise ValueError(f"{at}: one of template and from")
    if "template" in spec and spec["template"] not in fx_templates.GRAFTS:
        raise ValueError(f"{at}.template: {spec['template']!r} is not one of {', '.join(fx_templates.GRAFTS)}")
    if "from" in spec:
        _keys(f"{at}.from", spec["from"], ("archive", "key", "records"))
        if spec["from"]["archive"] not in fx_edit.ARCHIVES:
            raise ValueError(f"{at}.from.archive: {spec['from']['archive']!r} is not one of "
                             f"{', '.join(fx_edit.ARCHIVES)}")
        _string(f"{at}.from.key", spec["from"]["key"])
        records = spec["from"]["records"]
        if not isinstance(records, list) or not records:
            raise ValueError(f"{at}.from.records: {records!r} is not a list of record indices")
        for j, r in enumerate(records):
            _index(f"{at}.from.records[{j}]", r)
    if "parent" in spec:
        _index(f"{at}.parent", spec["parent"])


def _sound_fields(where: str, name: str, voice, sfx, wavs) -> None:
    """Refuse a recipe's ``voice``, ``sfx`` or ``wavs`` by name (module
    docstring)."""
    if voice not in VOICES:
        raise ValueError(f"{where}: voice {voice!r} is not one of {', '.join(VOICES)}")
    if not isinstance(wavs, dict):
        raise ValueError(f"{where}: wavs {wavs!r} is not an object")
    for role, files in wavs.items():
        if role not in DROP_ROLES:
            raise ValueError(f"{where}: wavs.{role}: not a role; one of {', '.join(DROP_ROLES)}")
        if len(f"{VARIANT_SOUND_DIR}{name}/{role}_s") > KEY_MAX:
            raise ValueError(f"{where}: wavs.{role}: its key is past the {KEY_MAX} characters 0x4B680 formats")
        _files(f"{where}: wavs.{role}", files)
    if not isinstance(sfx, dict):
        raise ValueError(f"{where}: sfx {sfx!r} is not an object")
    bound: dict[str, str] = {}
    for sound, params in sfx.items():
        at = f"{where}: sfx.{sound}"
        if not _NAME.match(sound) or _TAKE.match(sound)["take"]:
            raise ValueError(f"{at}: a sound's name is lower-case letters, digits and _, not ending in _a .. _s "
                             "(the binder would read it as a take)")
        if sound in (*DROP_ROLES, SHOUT):
            raise ValueError(f"{at}: {sound!r} is a drop-in role (--player-variant-sounds) or the shouts'; name the "
                             "sound otherwise")
        if len(f"{VARIANT_SOUND_DIR}{name}/{sound}_s") > KEY_MAX:
            raise ValueError(f"{at}: its key {VARIANT_SOUND_DIR}{name}/{sound}_s is past the {KEY_MAX} characters "
                             "0x4B680 formats")
        if not isinstance(params, dict) or params.get("generator") not in SFX_GENERATORS:
            raise ValueError(f"{at}: generator {params.get('generator') if isinstance(params, dict) else params!r} "
                             f"is not one of {', '.join(SFX_GENERATORS)}")
        SFX_GENERATORS[params["generator"]].check(at, params)
        if not isinstance(params["columns"], list) or not params["columns"]:
            raise ValueError(f"{at}.columns: {params['columns']!r} is not a list of attacks_anims columns")
        for i, column in enumerate(params["columns"]):
            _string(f"{at}.columns[{i}]", column)
            if column == ROLL:
                raise ValueError(f"{at}.columns[{i}]: the roll takes its first attack column's sound (D328)")
            if column in bound:
                raise ValueError(f"{at}.columns[{i}]: {column!r} plays sfx.{bound[column]} already")
            bound[column] = sound


def load_variants(text: str, source: str, taken: tuple[str, ...] = ()) -> dict[str, Variant]:
    """The recipes of ``text`` (one JSON object, {name: recipe}) from
    ``source`` (named in every refusal); a name in ``taken`` (the
    built-ins, for a user's file) fails by name, as does anything
    :data:`FIELDS` doesn't hold."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"variants ({source}): not JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise ValueError(f"variants ({source}): not an object of recipes")
    out = {}
    for name in doc:
        if name in taken:
            raise ValueError(f"variant {name!r} ({source}): a built-in variant has that name")
        recipe, parent = recipe_of(doc, name, source)
        out[name] = _variant(name, recipe, source, parent)
    return out


def recipe_of(doc: dict, name: str, source: str) -> tuple[dict, str]:
    """Recipe ``name`` of ``doc`` (a file's {name: recipe}, from ``source``)
    as it builds, and the recipe it is ``from`` (the module docstring; ""
    for none): that one's fields but its labels, with :data:`FROM_FIELDS`
    of its own over them; a user's file (``source`` not ``built-in``) may
    name a built-in its file doesn't hold (Step X.73).  A ``from`` list
    (Step 2.170d, D751) names recipes each from the same one, which it is from:
    the first as it builds, each other's own fields laid over in turn,
    then its own (:func:`_from_several`).  :class:`ValueError` names a
    ``from`` that names no other recipe of the file (nor a built-in) or
    one from another, or a field it may not lay over."""
    recipe = doc[name]
    if not isinstance(recipe, dict) or "from" not in recipe:
        return recipe, ""
    where, parent = f"variant {name!r} ({source})", recipe["from"]
    if isinstance(parent, list):
        return _from_several(doc, name, source)
    home = _home(doc, parent, source)
    if not isinstance(parent, str) or parent == name or not isinstance(home.get(parent), dict):
        raise ValueError(f"{where}: from {parent!r} names no other recipe of its file"
                         + ("" if source == "built-in" else " nor a built-in"))
    if "from" in home[parent]:
        raise ValueError(f"{where}: from {parent!r}, which is from {home[parent]['from']!r}: a recipe is from one "
                         "that is from none")
    return _laid(where, home[parent], recipe, parent), parent


def _home(doc: dict, name, source: str) -> dict:
    """The file a ``from`` of ``doc``'s names ``name`` in: ``doc``, or for a
    user's file without it the built-ins' (Step X.73)."""
    if source != "built-in" and isinstance(name, str) and name not in doc:
        return json.loads(BUILTIN.read_text(encoding="utf-8"))
    return doc


def _from_several(doc: dict, name: str, source: str) -> tuple[dict, str]:
    """Recipe ``name`` from a list (Step 2.170d; D751, the owner's "make sure we
    have a booblord-high_human variant also": booblord_high's body and look
    with booblord_human's colours, each still defined once): two or more
    other recipes, each from the same one (itself from none), which it is
    from; the first as it builds, each other's own fields (but its labels)
    laid over it in turn as :func:`recipe_of` lays a recipe's, then its own.
    :class:`ValueError` names a list that isn't two or more other names,
    each once; one naming no recipe, or one from none or from a list; two
    from different ones; and a field two of them lay (each comes from one)."""
    where, names = f"variant {name!r} ({source})", doc[name]["from"]
    if len(names) < 2 or not all(isinstance(n, str) for n in names) or len(set(names)) != len(names) \
            or name in names:
        raise ValueError(f"{where}: from {names!r}: a recipe from several names two or more other recipes, each once")
    homes = [_home(doc, n, source) for n in names]
    for n, home in zip(names, homes):
        if not isinstance(home.get(n), dict):
            raise ValueError(f"{where}: from {n!r} names no other recipe of its file"
                             + ("" if source == "built-in" else " nor a built-in"))
        if not isinstance(home[n].get("from"), str):
            raise ValueError(f"{where}: from {n!r}, which is from {home[n].get('from')!r}: a recipe from several is "
                             "from recipes each from one")
    built = [recipe_of(home, n, source) for n, home in zip(names, homes)]
    roots = [root for _, root in built]
    if len(set(roots)) != 1:
        raise ValueError(f"{where}: from {names!r}, which are from {roots!r}: a recipe from several is from recipes "
                         "each from the same one")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            shared = sorted((set(homes[i][names[i]]) & set(homes[j][names[j]])) - {"from", *LABELS})
            if shared:
                raise ValueError(f"{where}: {', '.join(shared)}: laid over {roots[0]!r}'s by both {names[i]!r} and "
                                 f"{names[j]!r}: a recipe from several takes each field from one of them")
    out = {k: v for k, v in built[0][0].items() if k not in LABELS}
    for n, home in zip(names[1:], homes[1:]):
        out = _laid(where, out, {k: v for k, v in home[n].items() if k not in LABELS}, roots[0])
    return _laid(where, out, doc[name], roots[0]), roots[0]


def _laid(where: str, base: dict, recipe: dict, parent: str) -> dict:
    """``base`` (the recipe ``recipe`` is from, as it builds or as written)
    but its labels, with ``recipe``'s :data:`FROM_FIELDS` over it: its
    ``mesh_ops`` added to (or laid over) ``base``'s mesh ops and its
    ``texture_ops`` to its rows' paint ops; ``parent`` names the recipe
    in a refusal."""
    laid = sorted(set(recipe) - {"from", *FROM_FIELDS})
    if laid:
        raise ValueError(f"{where}: {', '.join(laid)}: a recipe from another lays over only its "
                         f"{', '.join(FROM_FIELDS)} (its shape, moves and sounds are {parent!r}'s)")
    out = {k: v for k, v in base.items() if k not in LABELS} | {
        k: v for k, v in recipe.items() if k not in ("from", "mesh_ops", "texture_ops", "shapes")}
    if "shapes" in recipe:   # Step 2.164b: values over the shapes the one it is from declares
        declared, values = base.get("shapes"), recipe["shapes"]
        if not isinstance(values, dict) or not values:
            raise ValueError(f"{where}: shapes {values!r} is not an object of {{name: {{\"value\": v}}}}")
        shapes = {n: dict(s) if isinstance(s, dict) else s for n, s in declared.items()} \
            if isinstance(declared, dict) else {}
        for name, given in values.items():
            if not isinstance(shapes.get(name), dict) or not isinstance(given, dict) or set(given) - {"value"}:
                raise ValueError(f"{where}: shapes.{name}: a recipe from {parent!r} lays only a value over a shape "
                                 f"it declares ({', '.join(shapes) or 'none'})")
            shapes[name].update(given)
        out["shapes"] = shapes
    if "mesh_ops" in recipe:
        ops, mesh = recipe["mesh_ops"], base.get("mesh")
        if not isinstance(ops, list) or not ops:
            raise ValueError(f"{where}: mesh_ops {ops!r} is not a list of mesh ops")
        for i, op in enumerate(ops):
            kind = op.get("op") if isinstance(op, dict) else op
            if kind not in FROM_OPS and not (isinstance(op, dict) and "over" in op and "op" not in op):
                raise ValueError(f"{where}: mesh_ops[{i}].op {kind!r}: a recipe from another adds only "
                                 f"{' and '.join(FROM_OPS)} ops (its shape is {parent!r}'s)")
        if not isinstance(mesh, dict):
            raise ValueError(f"{where}: mesh_ops: {parent!r} has no mesh to add them to")
        laid, added = list(mesh.get("ops", [])), []
        for i, op in enumerate(ops):
            if "over" not in op:
                added.append(op)
                continue
            at = [j for j, o in enumerate(laid) if isinstance(o, dict) and o.get("name") == op["over"]]
            extra = sorted(set(op) - {"over", *OVER_FIELDS})
            if extra or len(at) != 1 or laid[at[0]].get("op") != "tube":
                raise ValueError(f"{where}: mesh_ops[{i}].over {op['over']!r}: lays only {', '.join(OVER_FIELDS)} "
                                 f"over the one tube of {parent!r}'s mesh that name names"
                                 + (f" (not {', '.join(extra)})" if extra else ""))
            laid[at[0]] = {**laid[at[0]], **{k: v for k, v in op.items() if k != "over"}}
        out["mesh"] = {**mesh, "ops": [*laid, *added]}
    if "texture_ops" in recipe:
        rows, painted = recipe["texture_ops"], list(base.get("textures", []))
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{where}: texture_ops {rows!r} is not a list of {{row, ops}}")
        for i, t in enumerate(rows):
            at = [j for j, p in enumerate(painted) if isinstance(p, dict) and isinstance(t, dict)
                  and p.get("row") == t.get("row")]
            if not isinstance(t, dict) or set(t) != {"row", "ops"} or not isinstance(t["ops"], list) or len(at) != 1:
                raise ValueError(f"{where}: texture_ops[{i}]: a {{row, ops}} adding paint ops to a row {parent!r}'s "
                                 "textures paint")
            painted[at[0]] = {**painted[at[0]], "ops": [*painted[at[0]].get("ops", []), *t["ops"]]}
        out["textures"] = painted
    return out


def fit_sha(variant: Variant) -> str | None:
    """The recipe sha W35's fit row of ``variant`` must hold
    (:func:`~azurik_mod.patches._player_weapons.fit_turns`): its own (at
    its shapes' 1.0, Step 2.164b), or
    for a built-in ``from`` another as shipped, that one's (its geometry and
    moves are that one's: :data:`FROM_FIELDS`); ``None`` for one with
    fields laid over it since."""
    own = variant.unshaped or variant.sha   # Step 2.164b: a shape moves no arm off its fit
    if not variant.files:
        return own
    shipped, parent = builtins().get(variant.name), builtins().get(variant.files)
    return parent.sha if shipped is not None and parent is not None and shipped.sha == own else None


def parent_of(variant: Variant) -> Variant | None:
    """The recipe ``variant`` is ``from`` (Step 2.177b), as its file has it
    (the built-ins for a built-in, or for a user's recipe from one, Step
    X.73: :func:`files_shipped`); ``None`` for one from none."""
    if not variant.files:
        return None
    if files_shipped(variant):
        return builtins()[variant.files]
    return load_variants(Path(variant.source).read_text(encoding="utf-8"), variant.source,
                         tuple(builtins()))[variant.files]


@functools.cache
def builtins() -> dict[str, Variant]:
    """The built-in variants (:data:`BUILTIN`)."""
    return load_variants(BUILTIN.read_text(encoding="utf-8"), "built-in")


def resolve(name: str, user_file: str | Path | None = None) -> Variant | None:
    """The variant ``name`` names (a built-in, else one in ``user_file``),
    or ``None`` (a species, or nothing)."""
    if name in builtins():
        if user_file is not None:
            load_variants(Path(user_file).read_text(encoding="utf-8"), str(user_file), tuple(builtins()))
        return builtins()[name]
    if user_file is None:
        return None
    return load_variants(Path(user_file).read_text(encoding="utf-8"), str(user_file), tuple(builtins())).get(name)


def laid_over(variant: Variant, fields) -> Variant:
    """``variant`` (a built-in, or a recipe file's) with each of ``fields``
    (an object of recipe fields) in place of its recipe's own, ``None``
    dropping one, read as ``variant``'s own, so a built-in's clip, sound
    and texture files stay the built-in's (a sculpt round's candidate:
    ``azurik-mod model dress --recipe``); :class:`ValueError` names a field
    as a recipe's would."""
    if not isinstance(fields, dict):
        raise ValueError(f"variant {variant.name!r}: the fields laid over it are not an object of recipe fields")
    source = BUILTIN if variant.source == "built-in" else Path(variant.source)
    recipe, _ = recipe_of(json.loads(source.read_text(encoding="utf-8")), variant.name, variant.source)
    recipe = dict(recipe)
    for key, value in fields.items():
        if value is None:
            recipe.pop(key, None)
        else:
            recipe[key] = value
    return _variant(variant.name, recipe, variant.source, variant.files)


def reshaped(variant: Variant, values: dict[str, float]) -> Variant:
    """``variant`` with each of its shapes ``values`` names (``--player-shape
    NAME=X``, Step 2.164b, D455) at its recipe's value times X, read as
    :func:`laid_over` reads it (so its sha holds the values the build
    sizes by); every X 1.0 is ``variant`` itself.  :class:`ValueError`
    names a shape it doesn't declare, and an X that isn't a number above
    0 (finite: D23, D45)."""
    declared = {s.name: s for s in variant.shapes}
    for name, x in values.items():
        if name not in declared:
            raise ValueError(f"--player-shape {name}: the variant {variant.name!r} has no shape {name!r} ("
                             + (f"its shapes: {', '.join(declared)})" if declared else "it declares none)"))
        _positive(f"--player-shape {name}", x)
    if all(x == 1.0 for x in values.values()):
        return variant
    return laid_over(variant, {"shapes": {s.name: {"title": s.title, "ops": list(s.ops),
                                                   "value": s.value * values.get(s.name, 1.0),
                                                   **({"turns": [{"bone": b, "axis": list(a), "deg": d}
                                                                 for b, a, d in s.turns]} if s.turns else {}),
                                                   **({"below": list(s.below)} if s.below else {})}
                                          for s in variant.shapes}})


def unarmed(variant: Variant) -> Variant:
    """``variant`` wearing a weapon other than its own moveset (Step
    2.161g; D585, the owner: "if she has the axion she would have garret's
    moveset"): its :data:`ATTACK_FIELDS` dropped, and its ``sfx`` (the
    whooshes its moves bind), so the weapon's style plays every column,
    its look, voice and ``wavs`` its own, and the clips its ``idles`` and
    ``slots`` name (her stance, gait and victories are no attack: Steps
    2.168 and 2.171).  Its ``shouts`` (Step 2.183; D705, the owner: "she
    should use her voice for these attacks") are then its one ``sfx``, a
    take at random at the start of each column Garret shouts in
    (:data:`~azurik_mod.patches._player_sounds.SHOUTED`), as his do, no
    pacing added ("dont worry about pacing")."""
    from azurkit.tools.characters._player_sounds import SHOUTED
    kept = {*variant.idles.values(), *variant.slots.values()}
    voiced = {SHOUT: {"generator": "wav", "files": list(variant.shouts), "columns": list(SHOUTED)}}
    return replace(variant, clips={k: c for k, c in variant.clips.items() if k in kept}, columns={}, carry=(),
                   held=(), rotate=False, markers=(), reach=1.0, damage=1.0, speed=1.0, balance=None, ground=None,
                   through_walls=False, sfx=voiced if variant.shouts else {})


def lend(lender: Variant, wearer: Variant | None, base: str, clips: dict) -> Variant:
    """``lender``'s moveset (Step 2.161g; D592, the owner: "Every body") on
    another body: ``clips`` (its clips as that body makes them) with the
    columns, carry and held columns that play them, its rotate, markers
    and attack sliders, laid over ``wearer``'s recipe (its look and
    sounds kept, and the clips its ``idles`` and ``slots`` name, as
    :func:`unarmed` keeps them), else a recipe of its own on the species
    ``base``."""
    columns = {c: clip for c, clip in lender.columns.items() if clip in clips}
    fields = {"clips": dict(clips), "columns": columns, "carry": tuple(c for c in lender.carry if c in columns),
              "held": tuple(c for c in lender.held if c in columns), "rotate": lender.rotate,
              "markers": lender.markers, "reach": lender.reach, "damage": lender.damage, "speed": lender.speed,
              "balance": lender.balance, "ground": lender.ground, "through_walls": lender.through_walls}
    if wearer is not None:
        return replace(wearer, **{**fields, "clips": {**unarmed(wearer).clips, **clips}})
    return Variant(lender.name, lender.source, lender.title, lender.notes, base, **fields)


def options(variant: Variant, *, mode: str | None = None, size: str | None = None, sounds: str | None = None,
            balance: bool | None = None, ground: bool | None = None, anims: str | None = None,
            scale: float = 1.0, reach: float = 1.0, damage: float = 1.0, speed: float = 1.0,
            jiggle_strength: float | None = None, jiggle_stiffness: float | None = None,
            weapon: str | None = None, default: str | None = None) -> dict:
    """:func:`~azurik_mod.patches._player_character.apply_player_model`'s
    options for ``variant`` under a build's own: a mode, size, sounds,
    balance, ground or anims rule given (not ``None``) must be the
    recipe's (else :class:`ValueError` names it); the scale and the attack
    sliders multiply the recipe's; the jiggle sliders (Step 2.156, D445),
    when given, pass through (they scale its springs at build).  With
    ``weapon`` (``--player-weapon``, Step 2.161g, D585) the attack sliders
    and on/off rules are its moveset's
    (:func:`~azurik_mod.patches._player_weapons.attack_recipe`, ``default``
    the name of the variant's default weapon, which builds as no pick):
    another weapon's the mode's, a moveset weapon's its recipe's."""
    from azurkit.tools.characters._player_character import ATTACK_DEFAULTS, MODE_ANIMS
    from azurkit.tools.characters._player_weapons import attack_recipe

    armed = attack_recipe(variant, weapon, default)
    own_balance, own_ground = ATTACK_DEFAULTS[variant.mode]
    recipe = {"--player-character-mode": (mode, variant.mode), "--player-character-size": (size, variant.size),
              "--player-character-sounds": (sounds, variant.sounds),
              "--player-attack-balance": (balance, own_balance if armed.balance is None else armed.balance),
              "--player-attack-ground": (ground, own_ground if armed.ground is None else armed.ground),
              "--player-character-anims": (anims, MODE_ANIMS[variant.mode])}
    for flag, (given, theirs) in recipe.items():
        if given is not None and given != theirs:
            shown = {True: "on", False: "off"}.get(given, given)
            raise ValueError(f"{flag} {shown}: the variant {variant.name!r} is {flag.rsplit('-', 1)[-1]} "
                             f"{ {True: 'on', False: 'off'}.get(theirs, theirs)} (its recipe's); leave it unset")
    return {"mode": variant.mode, "size": variant.size, "sounds": variant.sounds,
            "model_scale": variant.scale * scale, "attack_reach": armed.reach * reach,
            "attack_damage": armed.damage * damage, "attack_speed": armed.speed * speed,
            "attack_balance": armed.balance, "attack_ground": armed.ground,
            **{k: v for k, v in (("jiggle_strength", jiggle_strength), ("jiggle_stiffness", jiggle_stiffness))
               if v is not None}}


def status(variant: Variant, model_scale: float | None = None, reach: float | None = None,
           damage: float | None = None, speed: float | None = None, shapes: dict | None = None) -> tuple[str, str]:
    """``variant``'s grade (:data:`VARIANT_GRADES`) at the build's own
    scale and attack sliders (the recipe's times a multiplier; ``None``:
    the recipe's own) and ``shapes``' multipliers (Step 2.164b): any other
    than the recipe's is another build, unseen (D242)."""
    own = (variant.scale, variant.reach, variant.damage, variant.speed)
    if tuple(o if v is None else v for v, o in zip((model_scale, reach, damage, speed), own)) != own or any(
            x != 1.0 for x in (shapes or {}).values()):
        return "unseen", "no sitting has graded this variant at other sliders than its recipe's (D242)"
    if variant.source != "built-in":
        return "unseen", f"a recipe of yours ({variant.source}); no sitting graded it"
    return VARIANT_GRADES.get((variant.name, variant.sha),
                              ("unseen", f"no sitting has graded recipe {variant.sha} (D242)"))


# --- the build (W22) --------------------------------------------------------
def refusal(variant: Variant, species: dict, columns: list[str], body: Body) -> str | None:
    """Why ``variant`` can't build on ``body`` (``species``: the
    ``critters_engine`` rows; ``columns``: ``attacks_anims``'), before
    anything is written (D35), or ``None``."""
    if variant.name in species and variant.source != "overlay":
        return f"a species has that name ({variant.name!r}), so --player-character can't name the variant"
    for column, clip in variant.columns.items():
        if column not in columns:
            return f"columns.{column}: no such attacks_anims column"
        if clip not in variant.clips and clip not in body.clips:
            return f"columns.{column}: {clip!r} is neither a clip of the recipe nor one of {body.name}'s"
    for key, names in (("carry", variant.carry), ("held", variant.held)):
        for column in names:
            if column not in columns:
                return f"{key}: {column!r} is no attacks_anims column"
    for key, named in (("idles", variant.idles), ("slots", variant.slots)):
        for slot, clip in named.items():
            if clip not in variant.clips and clip not in body.clips:
                return f"{key}.{slot}: {clip!r} is neither a clip of the recipe nor one of {body.name}'s"
    impacts = {variant.clips[clip]["impact"] for clip in variant.columns.values()
               if variant.clips.get(clip, {}).get("generator") == "air_blast"}
    if len(impacts) > 1:
        return (f"columns: the air blasts they play land at {', '.join(f'{t:g}' for t in sorted(impacts))} s, and X39 "
                "jumps every one to one impact")
    for clip in variant.clips:
        if VARIANT_DIR + clip in body.clips:
            return f"clips.{clip}: {body.name} has a clip {VARIANT_DIR + clip} already"
    for column, clip in variant.columns.items():
        p = variant.clips.get(clip, {})
        if p.get("generator") == "gltf" and "box" not in p and p["animation"] not in body.clips:
            return (f"columns.{column}: clips.{clip} has no box, and its animation {p['animation']!r} is no clip of "
                    f"{body.name}'s to keep a hit box from: give it active and box")
    for sound, params in variant.sfx.items():
        for column in params["columns"]:
            if column not in columns:
                return f"sfx.{sound}.columns: {column!r} is no attacks_anims column"
    return None


# --- the sounds (Step 2.141) -------------------------------------------------
@dataclass(frozen=True)
class DropIn:
    """A WAV of a variant's (:func:`drop_ins`, :func:`recipe_wavs`): its
    file, the role or ``sfx`` name it plays, its sha256, its sound as mono
    PCM16 at 22050 Hz, what the file held and where it came from."""

    path: Path
    role: str
    sha256: str
    samples: tuple[int, ...]
    info: object
    origin: str = "drop-in"
    """``drop-in`` (:func:`drop_ins`) or ``recipe`` (:func:`recipe_wavs`)."""


def drop_ins(folder: str | Path, variant: Variant) -> dict[str, DropIn]:
    """``folder``'s ``*.wav`` files (any case; nothing else is read, so a
    ``.DS_Store`` is ignored) as ``variant``'s sounds, by the leaf each
    becomes (its stem, lower case): ``<name>.wav`` and ``<name>_a.wav`` ..
    ``_s`` for a name of ``variant``'s ``sfx`` or :data:`DROP_ROLES`.  A
    folder with none, a stem that names nothing of these (listing them),
    two files of one leaf, or a WAV :func:`~azurik_mod.assets.xbox_adpcm.read_wav`
    refuses raise :class:`ValueError` (D35)."""
    from azurkit.tools.characters.xbox_adpcm import read_wav

    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"--player-variant-sounds {folder}: not a folder")
    files = sorted(p for p in folder.iterdir() if p.suffix.casefold() == ".wav" and p.is_file())
    if not files:
        raise ValueError(f"--player-variant-sounds {folder}: it holds no .wav file")
    names = (*variant.sfx, *DROP_ROLES)
    out: dict[str, DropIn] = {}
    for path in files:
        leaf = path.stem.casefold()
        m = _TAKE.match(leaf)
        role = leaf if leaf in names else m["name"] if m and m["take"] and m["name"] in names else None
        if role is None:
            raise ValueError(f"--player-variant-sounds: {path.name} names no sound of {variant.name}'s: a file is "
                             f"<name>.wav, or <name>_a.wav .. <name>_s.wav for another take, a name one of "
                             f"{', '.join(names)}")
        if leaf in out:
            raise ValueError(f"--player-variant-sounds: {path.name} and {out[leaf].path.name} are both {leaf}")
        if len(f"{sound_dir(variant)}/{role}_s") > KEY_MAX:
            raise ValueError(f"--player-variant-sounds: {path.name}'s key is past the {KEY_MAX} characters "
                             "0x4B680 formats")
        samples, info = read_wav(path)
        out[leaf] = DropIn(path, role, hashlib.sha256(path.read_bytes()).hexdigest(), tuple(samples), info)
    return out


def recipe_wavs(variant: Variant) -> dict[str, DropIn]:
    """``variant``'s own WAVs, its ``wavs``, its ``wav`` sounds' files and
    its ``shouts`` (as :data:`SHOUT`) from :func:`sound_folder`, by the leaf
    each becomes: a name's n-th file its take n (``<name>``, ``<name>_a``
    ..).  A file that isn't there or that
    :func:`~azurik_mod.assets.xbox_adpcm.read_wav` refuses raises
    :class:`ValueError` (D35)."""
    from azurkit.tools.characters.xbox_adpcm import read_wav

    folder = sound_folder(variant)
    out: dict[str, DropIn] = {}
    for name, (where, files) in _named_wavs(variant).items():
        for take, file in enumerate(files):
            path = folder / file
            if not path.is_file():
                raise ValueError(f"variant {variant.name!r}: {where}[{take}]: no such file {file} in {folder}")
            samples, info = read_wav(path)
            out[take_name(name, take)] = DropIn(path, name, hashlib.sha256(path.read_bytes()).hexdigest(),
                                                tuple(samples), info, "recipe")
    return out


def _named_wavs(variant: Variant) -> dict[str, tuple[str, list[str]]]:
    """``variant``'s own WAVs (:func:`recipe_wavs`) by the name they take: where its recipe names them, their files."""
    return {**{role: (f"wavs.{role}", files) for role, files in variant.wavs.items()},
            **{sound: (f"sfx.{sound}.files", p["files"]) for sound, p in variant.sfx.items() if p["generator"] == "wav"},
            **({SHOUT: ("shouts.files", variant.shouts)} if variant.shouts else {})}


def recipe_wav_files(variant: Variant) -> list[Path]:
    """The files :func:`recipe_wavs` reads, in its order (one that isn't
    there too): a recipe file names them without their sha256."""
    folder = sound_folder(variant)
    return [folder / file for _, files in _named_wavs(variant).values() for file in files]


def variant_sounds(variant: Variant, folder: str | Path | None = None) -> dict[str, DropIn]:
    """``variant``'s WAVs by leaf: :func:`recipe_wavs`, with ``folder``'s
    (:func:`drop_ins`) laid over them, a name the folder fills taking the
    place of all the recipe's files of it."""
    mine = recipe_wavs(variant)
    if folder is None:
        return mine
    dropped = drop_ins(folder, variant)
    filled = {d.role for d in dropped.values()}
    return {leaf: d for leaf, d in mine.items() if d.role not in filled} | dropped


def waves(variant: Variant, drop: dict[str, DropIn] | None = None) -> dict[str, list[int]]:
    """``variant``'s sounds by leaf (``fx/sound/v/<variant>/<leaf>``), in
    the order the build appends them: each ``sfx``'s takes made by its
    generator (``<name>``, ``<name>_a`` ..), then its WAVs (``drop``,
    :func:`variant_sounds`), a WAV of an ``sfx``'s name taking the place
    of all its takes (a ``wav`` sound's takes are its WAVs)."""
    drop = drop or {}
    replaced = {d.role for d in drop.values()}
    out = {take_name(sound, take): SFX_GENERATORS[params["generator"]].make(params, take)
           for sound, params in sorted(variant.sfx.items()) if sound not in replaced and params["generator"] != "wav"
           for take in range(params.get("takes", 1))}
    return out | {leaf: list(d.samples) for leaf, d in sorted(drop.items())}


def carried(variant: Variant, columns: list[str]) -> int:
    """X33's bits (bit i: ``attacks_anims`` column i) for ``variant``'s
    ``carry`` columns, which :func:`refusal` has checked; the build ORs
    them into the base's own (:func:`~azurik_mod.patches._player_character.carry_mask`)."""
    return sum(1 << columns.index(column) for column in variant.carry)


def held(variant: Variant, columns: list[str]) -> int:
    """X33's held bits (bit i: ``attacks_anims`` column i) for ``variant``'s
    ``held`` columns, which :func:`refusal` has checked: a held A or B reads
    as a press in them, so they chain while it is held, never carried
    (Step 2.153, D450: "let beamlord chain attacks while holding the
    button")."""
    return sum(1 << columns.index(column) for column in variant.held)


def blasts(variant: Variant, columns: list[str]) -> tuple[int, float]:
    """X39's columns (bit i: ``attacks_anims`` column i) that play one of
    ``variant``'s ``air_blast`` clips, and their impact (clip s), which
    :func:`refusal` has checked is one; (0, 0.0) for none (Step 2.153)."""
    impacts = {columns.index(column): float(variant.clips[clip]["impact"]) for column, clip in variant.columns.items()
               if variant.clips.get(clip, {}).get("generator") == "air_blast"}
    return sum(1 << i for i in impacts), next(iter(impacts.values()), 0.0)


def seeking(variant: Variant, columns: list[str]) -> int:
    """X49's columns (bit i: ``attacks_anims`` column i) that play one of
    ``variant``'s clips with ``seek`` on (Step 2.194b; D762, the owner:
    "let's make beamlord's beams seek"; D761: seeking is opt-in): each
    turns to its target at the attack's start."""
    return sum(1 << columns.index(column) for column, clip in variant.columns.items()
               if variant.clips.get(clip, {}).get("seek") is True)


def authored(variant: Variant, columns: list[str]) -> int:
    """The bits (bit i: ``attacks_anims`` column i) of the columns that
    play one of ``variant``'s own clips, which X13's fill leaves as keyed:
    a generator puts its box where the attack hits (a centred spin or
    nova, a beam from the feet, all down to the floor, which the fill
    would leave as they are), and the sweep's bar turns ±35°, which the
    fill would make a box of its bounds, about 8.4 x 11.7 m, at either end (Step
    2.137's skeptic).  A ``gltf`` clip counts only with its own ``box``:
    one that keeps a base clip's markers takes the fill as that clip
    does (Step 2.158's X2); a ``bake`` clip never: another body's clip
    takes the fill as a base clip does (Step 2.164c)."""
    return sum(1 << columns.index(column) for column, clip in variant.columns.items()
               if clip in variant.clips and variant.clips[clip]["generator"] != "bake"
               and (variant.clips[clip]["generator"] != "gltf" or "box" in variant.clips[clip]))


def clip_rate(variant: Variant, column: str) -> float | None:
    """The ``rate`` (W5's Rate cell) of the ``gltf`` clip ``variant``
    plays in ``column``, or ``None`` (W5's own rules)."""
    clip = variant.clips.get(variant.columns.get(column))
    return float(clip["rate"]) if clip is not None and "rate" in clip else None


def grow(characters: bytes, index_xbr: bytes | None, body: Body, variant: Variant, xbe: bytes | None = None,
         fx_xbr: bytes | None = None) -> tuple[bytes, bytes | None]:
    """W22: ``characters.xbr`` and ``index.xbr`` with ``variant``'s
    markers grown on ``body`` (after B: each with its ``marker_source``'s
    record defaults, garret4's at rest off, so no clip without a track
    gains a box; C5),
    its clips generated on the grown marker table and added as
    ``characters/<body>/v/<clip>``, and its ``fx`` edits made on a clone
    of the body's ``fx/fx_default`` added as ``characters/<body>/v/fx/
    fx_default`` with its copies, its ``fx_grafts`` (from ``fx_xbr``, the
    vanilla fx.xbr, where they name it) and new textures
    (:class:`~azurik_mod.assets.fx_edit.Clone`, on ``xbe``'s schema; X40
    binds it to the player alone, Step 2.157), and its ``fx_ring.stand.fx``
    made on a clone of the stand's graph added as ``characters/<body>/v/fx/
    fx_stand``, which X38 spawns in its place (Step 2.155b, D501).
    With ``index_xbr`` ``None`` (the attack listing's scratch copy, Step
    2.198) no index.xbr comes back.  :class:`ValueError` names what blocks it."""
    source = variant.marker_source
    try:
        records = {name: values for name, values in marker_records(characters, source)}
    except ValueError:
        raise ValueError(f"marker_source: characters.xbr has no body {source!r}") from None
    have = {m.casefold() for m in body.markers}
    added = []
    for m in variant.markers:
        if m.casefold() in have:
            raise ValueError(f"markers: {m!r} is one of {body.name}'s markers already")
        if m not in records:
            raise ValueError(f"markers: {source} has no {m!r} to grow")
        added.append((m, records[m]))
        have.add(m.casefold())
    markers = {name: i for i, name in enumerate([*body.markers, *(n for n, _ in added)])}
    new = []
    for clip, params in sorted(variant.clips.items()):
        where = {"folder": clip_folder(variant), "builtin": files_shipped(variant)} \
            if params["generator"] == "gltf" else {}
        made = GENERATORS[params["generator"]].make(characters, body, params, markers, **where)
        new.append(NewResource(f"characters/{body.name}/{VARIANT_DIR}{clip}".casefold(), "banm", write_clip(made)))
    index, at = body_at(characters, body.name)
    rewrite = {index: grow_markers(bytes(characters[at:at + parse_toc(characters)[index].size]), added)} if added else {}
    if variant.fx_edits:   # Step 2.157 (D446): on the player's clone, every NPC's graph vanilla
        if xbe is None:
            raise ValueError("fx: the build's default.xbe is needed to name the attributes")
        clone = fx_edit.Clone(characters, fx_edit.default_key(body.name), xbe,
                              base=len(parse_toc(characters)) + len(new), fx_xbr=fx_xbr, folder=fx_folder(variant))
        clone.apply(variant.fx, variant.fx_grafts)
        new += clone.build(fx_edit.clone_key(body.name))
    stand = (variant.fx_ring or {}).get("stand") or {}
    if stand.get("fx"):   # Step 2.155b (D501): the stand's graph retuned on a clone X38 spawns, every NPC's vanilla
        if xbe is None:
            raise ValueError("fx_ring.stand.fx: the build's default.xbe is needed to name the attributes")
        try:
            clone = fx_edit.Clone(characters, stand["key"], xbe, base=len(parse_toc(characters)) + len(new),
                                  folder=fx_folder(variant))
            clone.apply(stand["fx"])
        except ValueError as exc:
            raise ValueError(f"fx_ring.stand.{exc}") from None
        new += clone.build(fx_edit.stand_key(body.name))
    grown = append_resources(characters, new, rewrite=rewrite or None)
    return grown, None if index_xbr is None else add_index_records(
        index_xbr, [IndexRecord(r.name, "characters.xbr", r.tag) for r in new if r.name is not None])


ARMS = (("left_arm_1", 1.0), ("right_arm_1", -1.0))
"""The bones ``arms`` turns, each with the sign of the turn about the
body's forward axis that takes its hand away from her side."""


def arm_turns(rig: Rig, degrees: float, forward: float = 0.0) -> dict[int, tuple[float, float, float, float]]:
    """``arms``' turn of each of :data:`ARMS` (by its index on ``rig``):
    ``degrees`` about the body's forward axis (+y) as the bind pose holds
    it in the bone's joint frame (its parent's bind world rotation times
    its JO, inverted), the r of :func:`~azurik_mod.assets.retarget.turned`;
    with ``forward`` (Step 2.161g, W35) after that many degrees about its
    side axis (+x), the hand forward; the bones ``rig`` lacks left out."""
    out = {}
    names = [b.name for b in rig.bones]
    for name, sign in ARMS:
        if name not in names:
            continue
        k = names.index(name)
        b = rig.bones[k]
        frame = qmul(rig.world[b.parent], b.jo) if b.parent >= 0 else b.jo
        axis = _turn(qinv(frame), (0.0, 1.0, 0.0))
        half = math.radians(sign * degrees) / 2
        out[k] = (*(fdlibm.sin(half) * a for a in axis), fdlibm.cos(half))
        if forward:
            side, half = _turn(qinv(frame), (1.0, 0.0, 0.0)), math.radians(forward) / 2
            out[k] = qmul(out[k], (*(fdlibm.sin(half) * a for a in side), fdlibm.cos(half)))
    return out


def bone_turn(rig: Rig, k: int, axis, degrees: float) -> tuple[float, float, float, float]:
    """The turn of bone ``k`` by ``degrees`` about ``axis`` (the model's
    frame at bind) in its joint frame, as :func:`arm_turns` and
    :func:`~azurik_mod.assets.retarget.turned_over` take one: the r of
    :func:`~azurik_mod.assets.retarget.turned` (Step 2.164b: a shape's
    turn)."""
    b = rig.bones[k]
    frame = qmul(rig.world[b.parent], b.jo) if b.parent >= 0 else b.jo
    ax = _turn(qinv(frame), axis)
    length = math.sqrt(sum(x * x for x in ax))
    half = math.radians(degrees) / 2
    return (*(fdlibm.sin(half) * x / length for x in ax), fdlibm.cos(half))


def restyled(before: bytes, after: bytes, first: int, body: str, variant: Variant,
             rigged: jiggles.Rigged | None = None, rates: dict[str, float] | None = None, drawn: float = 1.0,
             arms: bool = True) -> tuple[bytes, int, dict]:
    """W28 (Step 2.143, D428): ``after`` (the dressed ``characters.xbr``)
    with every clip under ``body`` restyled by ``variant``'s ``arms``
    (with ``arms``; :func:`arm_turns`, :func:`~azurik_mod.assets.retarget.
    turned`) but its own ``v/`` clips, which pose the arms themselves, and
    keyed with its jiggle bones' springs (``rigged``, W29; :func:`~azurik_mod.
    assets.jiggle.keyed`, every clip's at once by :func:`~azurik_mod.assets.
    jiggle.keyed_each`, at the clip's playback rate in ``rates``, by its
    name under the body, else 1, drawn at ``drawn``; as a loop where its
    name's last part is one of the jiggle's ``loops``) but the ``still``
    clips, and a bone with a real-time ``spring`` (X41, Step 2.156) in none; how many it turned, and each keyed clip's peaks (name -> {role:
    (the translation, the angle)}).  The clips this build added (TOC
    entries from ``first``, ``before``'s count) are added again to
    ``before`` in their order, restyled, with their names (or none) and
    relocated fields (:func:`~azurik_mod.xbr.append.appended`: an fx
    clone's copies, Step 2.157), and every older entry the build
    changed or restyles (the body's own clips) is rewritten in place (one
    that outgrows its place moves the payloads after it by whole pages):
    a pass over every clip she plays, each once, whichever step made it
    (the build's two: the arms in the dress, the springs last, AZ-648).
    :class:`ValueError` names a clip (still or not) that keys a freed bone, a
    jiggle bone's parent's scale or, but a recipe's own ``v/`` clip (whose
    keys a real-time spring swings about and a baked one plays instead of
    its bake, Step 2.168), a jiggle bone, a listed loop that doesn't close
    (:func:`~azurik_mod.assets.jiggle.closes`), and a ``still``,
    ``loops``, ``clear.clips`` or ``clear.held`` name no clip under the body has."""
    toc, names, old = parse_toc(after), named_resources(after), parse_toc(before)
    prefix = f"characters/{body}/".casefold()
    rig = Rig.read(after, body)
    turns = arm_turns(rig, variant.arms) if variant.arms and arms else {}
    own_turns = {c: arm_turns(rig, d) for c, d in variant.arm_clips} if arms else {}
    bone_at = {b.name: k for k, b in enumerate(rig.bones)}
    for pz in variant.poses:
        if pz.bone not in bone_at:
            raise ValueError(f"W28: poses: {body} has no bone {pz.bone!r}")
    spec = variant.jiggle if rigged is not None else None
    still, cycled = ({c.casefold() for c in spec.still}, {c.casefold() for c in spec.loops}) if spec else (set(), set())
    own = {c.casefold(): c for c in (*(c for c, _ in spec.clear.clips), *spec.clear.held)} if spec and spec.clear \
        else {}   # Step 2.169c, 2.169d
    have = {names[i].casefold()[len(prefix):].rsplit("/", 1)[-1] for i in names
            if toc[i].tag == "banm" and names[i].casefold().startswith(prefix)}
    for field, wanted in (("still", still), ("loops", cycled),
                          ("clear.clips", {c.casefold() for c, _ in spec.clear.clips} if own else set()),
                          ("clear.held", {c.casefold() for c in spec.clear.held} if own else set())):
        if wanted - have:
            raise ValueError(f"W28: jiggle.{field}: {body} has no clip {sorted(wanted - have)[0]!r}")
    rates = {prefix + k.casefold(): v for k, v in (rates or {}).items()}
    parents = [pl.parent for pl in rigged.bones] if rigged else []
    baked = tuple(pl for pl in rigged.bones if pl.bone.spring is None and not pl.bone.keyed) if rigged else ()
    # X41's rows key nothing, nor a keyed bone (Step 2.168: its recipe's own clips alone)
    from azurkit.tools.characters import pool

    shared = (rig, turns, own_turns, arms, variant.poses, bone_at, prefix,
              (set(rigged.freed), {pl.index for pl in rigged.bones}, parents) if rigged else None, baked, still, cycled,
              rates)
    added = appended(first, after)
    payloads, where, jobs = {}, [], []
    for i in range(first + len(added)):     # every clip under the body in worker processes (Step 2.176)
        e = toc[i]
        key = names.get(i, "").casefold()
        if e.tag != "banm" or not key.startswith(prefix):
            payloads[i] = bytes(after[e.file_offset:e.file_offset + e.size])
        else:
            where.append(i)
            jobs.append((key, read_clip(after, e.file_offset)))
    count, peaks, springs, failed = 0, {}, {}, None   # springs: a clip's left to key (jiggles.keyed_each)
    for i, got in zip(where, pool.each(_styled, shared, jobs, cost=lambda n: jobs[n][1].length)):
        if got[0] == "error":
            failed = ValueError(f"W28: {names[i]}: {got[1]}")    # raised after any earlier clip's springs that fail
            break
        count += got[-1]
        if got[0] == "springs":
            springs[i] = got[1:5]
        else:
            payloads[i] = got[1]
    clears = {"": rigged.clear, **dict(rigged.clip_clears)} if rigged is not None and rigged.clear is not None else {}
    sprung = jiggles.keyed_each(rig, spec.keys, drawn, clears,     # a clip the clear names: its own groups' collider
                                [(*job, own.get(names[i].casefold().rsplit("/", 1)[-1], ""))
                                 for i, job in springs.items()]) if springs else []
    for i, got in zip(springs, sprung):
        if isinstance(got, ValueError):
            raise ValueError(f"W28: {names[i]}: {got}") from None
        payloads[i], peaks[names[i].casefold()[len(prefix):]] = write_clip(got[0]), got[1]
    if failed is not None:
        raise failed
    rewrite = {}
    for i in range(first):    # in place; one that outgrows its place moves the payloads after it (Step 2.154)
        if payloads[i] != bytes(before[old[i].file_offset:old[i].file_offset + old[i].size]):
            rewrite[i] = payloads[i]
    new = [replace(r, payload=payloads[first + j]) for j, r in enumerate(added)]
    return append_resources(before, new, rewrite=rewrite or None), count, peaks


def _styled(shared: tuple, job: tuple) -> tuple:
    """:func:`restyled`'s work on one clip (``job``: its name under the
    characters, casefolded, and the clip), in a worker process: its arms
    turned and its poses, its checks against the jiggle, and then
    ``("clip", payload, turned)``, or ``("springs", clip, the baked bones
    it doesn't key, rate, loop, turned)`` where their springs are left to
    key, or ``("error", the ValueError, turned)``; ``turned`` 1 where it
    was turned."""
    rig, turns, own_turns, arms, poses, bone_at, prefix, jiggled, baked, still, cycled, rates = shared
    key, clip = job
    counted = 0
    try:
        short = key[len(prefix):].rsplit("/", 1)[-1]
        clip, counted = _arms_posed(rig, clip, short, key.startswith(prefix + VARIANT_DIR), turns, own_turns, arms,
                                    poses, bone_at)
        if jiggled is not None:   # a still clip too: the bones it keys skin as the jiggle left them
            freed, placed, parents = jiggled
            keyed = {tr.target for tr in clip.bones}
            if keyed & freed:
                raise ValueError(f"it keys {rig.bones[min(keyed & freed)].name}, whose weights the jiggle merged")
            mine = key.startswith(prefix + VARIANT_DIR)   # a recipe's own clip may key one (Step 2.168)
            if keyed & placed and not mine:
                raise ValueError("it keys a jiggle bone already")
            if any(tr.target in parents and tr.comp >= 7 for tr in clip.bones):
                raise ValueError("it keys a jiggle bone's parent's scale")
        free = tuple(pl for pl in baked if pl.index not in keyed) if jiggled is not None else baked
        if free and short not in still:   # a baked bone the clip keys plays its keys (Step 2.168)
            loop = short in cycled
            if loop:    # each bone loops where its parent's chain closes (a ponytail's head may not: one-shot)
                loop = {pl.index for pl in free if jiggles.closes(rig, clip, [pl.parent])}
                if not loop:
                    raise ValueError("jiggle.loops names it, but it doesn't end where it starts "
                                     f"(within {jiggles.LOOP_TOLERANCE[0]:g} model units)")
            return "springs", clip, free, rates.get(key, 1.0), loop, counted
    except ValueError as exc:
        return "error", exc, counted
    return "clip", write_clip(clip), counted


def _arms_posed(rig: Rig, clip: Clip, short: str, own: bool, turns: dict, own_turns: dict, arms: bool, poses,
                bone_at: dict[str, int]) -> tuple[Clip, int]:
    """W28's arms and poses on one clip (:func:`_styled`, :func:`arms_posed`):
    a clip the recipe names (``short``, its name's last part) its own turn,
    any other but the recipe's own (``own``: its ``v/`` clips) ``turns``,
    then with ``arms`` each pose of it; and 1 where an arm turn was made."""
    counted = 0
    if short in own_turns:      # a clip the recipe names: its own turn, its own v/ clips too
        clip = turned(rig, clip, own_turns[short])
        counted = 1
    elif turns and not own:
        clip = turned(rig, clip, turns)
        counted = 1
    if arms:
        for pz in poses:
            if pz.clip == "":   # a shape's turn (Step 2.164b): the whole clip, exact
                clip = turned(rig, clip, {bone_at[pz.bone]: bone_turn(rig, bone_at[pz.bone], pz.axis, pz.deg)})
            elif pz.clip == short:
                clip = turned_over(rig, clip, bone_at[pz.bone], pz.axis, pz.deg, pz.window)
    return clip, counted


def arms_posed(rig: Rig, variant: Variant):
    """W28's arms and poses (:func:`restyled`'s, ``arms`` on) as one
    clip's function, (its name, the clip) -> the clip as W28 will leave
    it, for W41 (Step 2.207b, AZ-785: :func:`~azurik_mod.patches.
    _player_weapons.carried_copy` lifts a picked hoe over the floor where
    her turned arms put it, booblord's finish 0.374 m under in game);
    ``None`` for a variant that turns nothing.  :class:`ValueError` names a
    pose's bone ``rig`` lacks."""
    if not (variant.arms or variant.arm_clips or variant.poses):
        return None
    bone_at = {b.name: k for k, b in enumerate(rig.bones)}
    for pz in variant.poses:
        if pz.bone not in bone_at:
            raise ValueError(f"W28: poses: {rig.name} has no bone {pz.bone!r}")
    turns = arm_turns(rig, variant.arms) if variant.arms else {}
    own_turns = {c: arm_turns(rig, d) for c, d in variant.arm_clips}
    return lambda name, clip: _arms_posed(rig, clip, name.rsplit("/", 1)[-1], False, turns, own_turns, True,
                                          variant.poses, bone_at)[0]


def reread(characters: bytes, body: Body, dirs: tuple[str, ...] = ()) -> Body:
    """``body`` read again from ``characters`` with its variant's clips
    (:data:`VARIANT_DIR`) among its own, and those of ``dirs`` (the
    style's, Step 2.159a), so every check after W22 reads them."""
    return read_body(characters, body.name, dirs=(VARIANT_DIR, *dirs))


__all__ = ["ARMS", "ATTACKS", "BUILTIN", "CHAINS", "CLIPS", "DRAIN_BOX", "DROP_ROLES", "DropIn", "FIELDS",
           "FROM_FIELDS", "FX_FIELDS",
           "GENERATORS", "GRAFT_FIELDS", "Generator", "TEXTURE_FIELDS",
           "ATTACK_FIELDS", "KEY_MAX", "LABELS", "LINK_FIELDS", "MATERIAL_FIELDS", "MOVES", "MOVESET", "OVERLAYS", "RAMP", "SASH", "SASH_FLARE", "SASH_LAG",
           "SASH_LIFT", "SFX_GENERATORS", "SOUNDS", "TAKES", "UNGRADED", "VARIANT_DIR", "VARIANT_GRADES",
           "VARIANT_SOUND_DIR", "VOICES", "Lods", "Variant", "ROOT_TRAVEL_MAX", "arm_turns", "arms_posed", "beam", "builtins", "check_fx_ring",
           "chain_springs", "clip_folder", "clip_rate", "colour_folder", "drop_ins", "files_shipped", "fit_sha", "fx_folder",
           "gltf_clip", "grow", "gust",
           "hand_spin", "laid_over", "lend", "load_variants", "moveset_moves", "nova", "options", "overlay", "own_recipe", "recipe_of", "recipe_sha",
           "recipe_wav_files", "recipe_wavs",
           "refusal", "reread", "reshaped", "resolve",
           "restyled", "Shape", "sound_dir", "sound_folder", "sounds_sha", "status", "t_spin", "take_name", "templated",
           "unarmed", "variant_sounds", "waves"]

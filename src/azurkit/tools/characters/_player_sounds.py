"""The player model's own sounds (Step 2.71; D224, D231-D233; design:
Step 2.62, ``docs/RE_DATA.md`` § "How a critter's sounds are chosen").

A critter's clip sounds bind by species and slot name, never by body
(0x4B680: ``<sound dir>/<clip>`` and its ``_a`` .. ``_s`` variants per
anim slot), so under the swap (mechanism B, the player stays garret4)
every slot binds Garret's voice bank.  :func:`sound_roles` maps a
species' own sounds onto the player's slots by role:

- **hurt** (``ouch_1`` .. ``ouch_1b``), **death** (``die`` .. ``die_3``),
  **idle** (``idle`` .. ``idle_6``) and **taunt** (``victory_1`` ..
  ``_6``): the species' wave of the slot's own name, else its first
  sound of that role (an alias, e.g. ``ouch`` or ``catalisk_ouch``);
- **jump** (``jump``, ``jump_standing``), **land** (``touchdown``) and
  **footstep** (``walk``, ``run``, ``step_up``, ``step_down``): only a
  wave of the slot's own name;
- **attack** (slot 0x52 + each ``attacks_anims`` column but the roll):
  the wave of the clip the build's ``Anim`` cell names when it is an
  attack sound, else the species' attack sounds in turn; a species with
  none binds nothing where the clip would bind one of Garret's lines
  (AZ-392's ``ouch_1``), which is what garret4's own attacks bind;
- **roll**: the wave of its clip's own name, else (D328, Step 2.141) the
  sound of its first attack column that binds one, so a body rolls with
  one of its own attack sounds rather than Garret's grunt;
- the **townspeople** (D233): their speech dir's lines as hurt and
  attack sounds, the shortest first (hurt the three shortest, attacks
  the next four), a body without a speech dir taking that of another
  species with the same body; never Garret's dialogue.

A role the species has no sound for keeps Garret's (D232): its slots
are left out of the map, so the shim calls 0x4B680 unchanged.  The map
also lists what Step 2.72 writes (:func:`write_sound_cells`,
:func:`install_xbe_sounds`; ``--player-character-sounds own``, D231's
default):

- **W9** ``attacks_anims``: the ``Sound`` .. ``Sound 4`` cells (Garret's
  shouts) of each column the model gives a sound of its own (an attack,
  or the roll its own) become empty, as a vanilla empty cell;
- **W10** garret4's ``critters_sounds`` ``ouch`` (the damage pass's
  per-hit voice) and ``ambient`` := the species' (garret4's are empty:
  filled);
- **W11** garret4's ``critters_sounds`` hit rows := the species', not
  the ``hits/heal`` rows (the player doesn't heal from that element);
- **W12** the townspeople's speech lines as their hurt and attack binds
  (X14's table, D233);
- **X15** (D233) the species' ``jump`` wave, and its ``foot_left`` and
  ``foot_right`` pair (the golem family), carved into ``default.xbe``:
  the ``mov`` that loads ``fx/sound/player/jump`` (the jump and the
  wing flap), ``walkl`` or ``walkr`` (the walk's steps, and 0x8AE10's,
  which plays ``landing`` too) loads the model's instead.  X15's jump
  takes the jump slots' bind, which would play the same wave again.

**X14** (``player_model/sounds.c``) takes the CALLs of 0x4B680 at
0x4B93C (the 82 base clips) and 0x7E3DD (the attack slots) and, for
the player's species, binds :attr:`SoundRoles.binds` from the model's
sound dir through the byte table :func:`sound_table` encodes
(:data:`SOUNDS_TABLE`, late-bound).  Installed by
:func:`~azurik_mod.patches._player_character.apply_player_model` when
``sounds="own"`` and the map is non-empty.

A variant's sounds (Step 2.141; D384, D386) are :func:`variant_roles`':
with ``voice`` ``silent`` every voice slot (:data:`VOICE_SLOTS`) and
attack column binds nothing but its ``sfx``, W9 empties every shout and
X15 points the fall's ``ouch`` and the falling scream at names of its
dir no wave has unless a WAV of the role is one (the recipe's ``wavs``
or a drop-in, Step 2.144); its effects stay Garret's.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import NamedTuple

from azurkit.tools.characters.ports import xbe_site
from azurkit.tools.characters._player_slots import BASE_CLIPS
from azurkit.tools.characters.ports import carve_shim_landing
from azurkit.tools.characters.ports import ShimSource
from azurkit.tools.characters.ports import CHECKOUT
from azurkit.tools.characters.ports import BytesParam, TrampolinePatch
from azurkit.tools.characters.ports import XbrDocument
from azurkit.tools.characters.ports import clear_keyed_cell, point_keyed_string
from azurkit.core.xbr.nodes import named_resources, parse_toc

PLAYER = "garret4"
ROLL = "roll forward"
SOUND_MODES = ("own", "garret4")
"""``--player-character-sounds``: the model's own sounds (D231's
default) or Garret's."""

ATTACK_SLOT = len(BASE_CLIPS)
"""``attacks_anims`` column k binds slot 0x52 + k (0x7E3DD); slot k < 0x52
binds ``BASE_CLIPS[k]`` (0x4B93C)."""

ROLE_SLOTS = {
    "hurt": ("ouch_1", "ouch_2", "ouch_3", "ouch_1r", "ouch_1l", "ouch_1b"),
    "death": ("die", "die_1", "die_2", "die_3"),
    "idle": ("idle", "idle_1", "idle_2", "idle_3", "idle_4", "idle_5", "idle_6"),
    "taunt": ("victory_1", "victory_2", "victory_3", "victory_4", "victory_5", "victory_6"),
    "jump": ("jump", "jump_standing"),
    "land": ("touchdown",),
    "footstep": ("walk", "run", "step_up", "step_down"),
}
"""The base slots of each role a model's sound can take."""
_ALIASES = {
    "hurt": r"ouch(_\d)?",
    "death": r"die(_\d)?|splat",
    "idle": r"idle(_\d)?",
    "taunt": r"laugh|idle_laugh",
    "attack": r"attack(_\w+)?|eat(_\d)?|deathbeam|lifedrain|firewall|metal4attack|ball",
}
"""The wave names (whole, or after a ``<species>_`` prefix) that play a
role in a slot of another name; jump, land and footstep take only a
wave of the slot's own name."""
ROLES = ("attack", "hurt", "death", "idle", "taunt", "jump", "land", "footstep", "roll",
         "ambient", "hit")
"""Every role, in the order the player-models column lists them."""
VOICE_ROLES = ("hurt", "death", "idle", "taunt")
"""The roles that are a voice (D386), with the attack shouts."""
GRUNTS = ("climb_start", "climb_up_edge", "hoist", "hang", "climb_drop", "hoist_waist", "climb_from_jump")
"""Garret's effort grunts in his dir, a voice too (D386): voiced in .56,
.31, .24, .15, .12, .10 and .07 of their loud frames at F0 176-380 Hz,
his effects in .00-.10 (Step 2.141's read, ``voicing.txt``; the last five
voice by inference)."""
VOICE_SLOTS = tuple(BASE_CLIPS.index(slot) for slot in (
    *(slot for role in VOICE_ROLES for slot in ROLE_SLOTS[role]), *GRUNTS))
"""The 30 base slots a silent voice binds nothing in."""
DROP_SITES = {"hurt": ("ouch",), "fall": ("ouch",), "death": ("fallingdeath",), "land": ("landing",),
              "jump": ("jump",), "footstep": ("walkl", "walkr")}
"""A variant's role -> the :data:`XBE_SOUND_SITES` (X15) that load its
``<dir>/<role>`` wave: a WAV's, and hurt's and death's when silent; a
``fall`` WAV takes the fall's ``ouch`` from hurt (Step 2.144, D406), and
the jump's is the jump's alone, the wing flap keeping Garret's."""
CLIMB_SLOTS = ("hoist", "climb_up_edge")
"""The ``climb`` role's slots (Step 2.144, D408): the ledge hoist and the
climb over a ladder's top, two of Garret's effort grunts (:data:`GRUNTS`)."""
DROP_SLOTS = {**{role: ROLE_SLOTS[role] for role in ("hurt", "death", "idle", "taunt", "land")},
              "climb": CLIMB_SLOTS}
"""A variant's roles bound in base slots (X14), and their slots; the roll
binds in its own, fall, jump and footstep at X15's sites alone (a slot
bind would play jump and footstep a second time)."""

FALL_VOICES = frozenset(("balthazar",))
"""The species whose own ``ouch_1`` and ``die`` X15 plays at the fall's
damage (0x8ADC2) and its falling death (0x8BF61) (Step 2.153; D447: "for
beamlord and balthazar, have their fall damage sound use the balthazar
hurt sound", D448: "their fall death should use the death sound for
balthazar"); beamlord's sounds are its base's."""

TOWNSPEOPLE = "townspeople/"
_HURT_LINES, _ATTACK_LINES = 3, 4
_HEAL = "fx/sound/hits/heal"
_NOT_HIT_ROWS = frozenset(("name", "soundMinDist", "soundMaxDist", "ouch", "attack", "idle",
                           "ambient", "ambientCutoffDistance", "foot_left", "foot_right"))
"""``critters_sounds``' rows that aren't hit rows."""


@dataclass(frozen=True)
class SoundRoles:
    """A species' sounds as the player's (:func:`sound_roles`)."""

    species: str
    sound_dir: str | None
    """The dir X14 binds from, as the archive names it; ``None``: none."""
    binds: dict[int, str] = field(default_factory=dict)
    """Slot -> the name X14 binds in :attr:`sound_dir` (``""`` binds
    nothing); a slot left out keeps Garret's."""
    own: tuple[str, ...] = ()
    """The roles the model's own sounds take (in :data:`ROLES` order)."""
    shouts: tuple[str, ...] = ()
    """W9: the ``attacks_anims`` columns whose ``Sound`` .. ``Sound 4``
    cells give way to the model's own sound (an attack's, or the roll's
    own)."""
    ouch: str | None = None
    """W10: ``critters_sounds`` ``ouch`` := this."""
    ambient: str | None = None
    """W10: ``critters_sounds`` ``ambient`` := this."""
    hit_rows: dict[str, str] = field(default_factory=dict)
    """W11: ``critters_sounds`` hit row -> the species' sound."""
    speech: tuple[str, ...] = ()
    """W12: the townspeople's lines (full names) the binds use."""
    xbe: dict[str, str] = field(default_factory=dict)
    """X15: ``jump`` and ``flap``, ``walkl``, ``walkr`` (the XBE's
    ``fx/sound/player/*`` paths, :data:`XBE_SOUND_SITES`) -> the
    species' wave that takes its place, as the archive names it."""
    roll_from: str | None = None
    """D328: the attack column whose sound the roll binds (it has none of
    its own); ``None``: its own, or Garret's."""
    silent: bool = False
    """A variant's ``voice: silent`` (D386, :func:`variant_roles`)."""
    swing: str | None = None
    """The whoosh an attack style's columns bind (:func:`kit_swings`, Step 2.159a)."""


def _waves(files) -> dict[str, dict[str, tuple[str, int]]]:
    """Every named wave of ``fx.xbr`` and ``english.xbr``: ``{dir (case
    folded): {leaf (case folded): (dir/leaf as named, size)}}``."""
    out: dict[str, dict[str, tuple[str, int]]] = {}
    for name in ("fx.xbr", "english.xbr"):
        data = bytes(files[name])
        toc = parse_toc(data)
        for index, key in named_resources(data).items():
            if toc[index].tag == "wave" and "/" in key:
                folder, leaf = key.rsplit("/", 1)
                out.setdefault(folder.casefold(), {})[leaf.casefold()] = (key, toc[index].size)
    return out


def _role_names(names, role: str) -> list[str]:
    """The waves of ``names`` that play ``role``, those named by the role
    alone first."""
    pattern = _ALIASES[role]
    hits = [n for n in names if re.fullmatch(rf"(\w+_)?({pattern})", n) and "not_used" not in n]
    return sorted(hits, key=lambda n: (not re.fullmatch(pattern, n), n))


def sound_roles(game, species: str, anim_picks: dict[str, str] | None = None) -> SoundRoles:
    """``species``' own sounds as the player's, from ``game``'s
    ``config.xbr``, ``fx.xbr`` and ``english.xbr`` (any mapping of those
    names to bytes, e.g. an
    :class:`~azurik_mod.patching.xbr_staging.IsoStaging`): per slot, the
    name X14 binds, and the cells Step 2.72 writes (module docstring).
    ``anim_picks`` (``attacks_anims`` column -> clip) defaults to the
    ``Anim`` cells as the clip names they hold, so the attack sounds
    follow the clips the build names; a W17 copy (``p/<n>``, Step 2.75e),
    a W22 one (``q/<n>``) or a lunge's drawn about the centre (``c/<n>``,
    Step 2.175) names none of the body's, so a build with one passes the
    clips it copies, as the swap does.  garret4's are Garret's: its map is empty."""
    if species == PLAYER:
        return SoundRoles(species, None)
    config = XbrDocument.from_bytes(bytes(game["config.xbr"]))

    def column(table: str, sp: str, rows=None) -> dict[str, str | None]:
        """``sp``'s string cells of ``table`` (of ``rows``, else every
        one) by row; ``{}``: no column."""
        section = config.keyed_section(table)
        if table not in tables:
            tables[table] = (section.row_names(), section.col_names())
        names, cols = tables[table]
        if sp not in cols:
            return {}
        c = cols.index(sp)
        return {row: (got.string_value if (got := section.read_cell(c, names.index(row))).type_code == 2
                      else None) for row in rows or names}

    tables: dict[str, tuple[list[str], list[str]]] = {}
    engine = {sp: column("critters_engine", sp, ("body", "sound dir"))
              for sp in config.keyed_section("critters_engine").col_names()}
    if species not in engine:
        raise ValueError(f"no such species in config.xbr's critters_engine: {species!r}")
    anims = config.keyed_section("attacks_anims")
    columns = anims.col_names()
    if anim_picks is None:
        anim = anims.row_names().index("Anim")
        anim_picks = {col: anims.read_cell(c, anim).string_value for c, col in enumerate(columns)}
    waves = _waves(game)
    garret4 = waves.get((engine[PLAYER]["sound dir"] or "").casefold(), {})
    body = (engine[species]["body"] or "").casefold()
    folder = engine[species]["sound dir"]
    town = body.startswith(TOWNSPEOPLE)
    if town and not folder:   # a body's speech dir is the species' that has one
        folder = next((row["sound dir"] for sp, row in engine.items() if sp != PLAYER
                       and (row["body"] or "").casefold() == body and row["sound dir"]), None)
    mine = waves.get((folder or "").casefold(), {})

    def leaf(key: str) -> str:   # a wave's name as the archive spells it
        return mine[key][0].rsplit("/", 1)[1]

    # X15 (D233): the XBE's jump and footstep paths, where the dir has
    # the wave by name (spideyzar's jump; the golem family's feet, a pair)
    xbe = {path: mine[wave][0] for path, wave in (("jump", "jump"), ("flap", "jump"), ("walkl", "foot_left"),
                                                  ("walkr", "foot_right"))
           if wave in mine and (wave == "jump" or {"foot_left", "foot_right"} <= mine.keys())}
    if species in FALL_VOICES:   # D447, D448 (Step 2.153): a fall's hurt and death in its own voice
        xbe |= {path: mine[wave][0] for path, wave in (("ouch", "ouch_1"), ("fallingdeath", "die")) if wave in mine}
    binds: dict[int, str] = {}
    own: set[str] = {"jump"} if "jump" in xbe else set()
    for role, slots in ROLE_SLOTS.items():
        if role == "jump" and "jump" in xbe:
            continue   # X15 plays it at the jump: a slot bind would play it again
        alias = _role_names(mine, role)[:1] if role in _ALIASES else []
        for slot in slots:
            pick = slot if slot in mine else next(iter(alias), None)
            if pick is not None:
                binds[BASE_CLIPS.index(slot)] = leaf(pick)
                own.add(role)
    speech: list[str] = []
    if town:   # D233: the shortest lines as hurt and attack sounds
        lines = sorted(mine, key=lambda n: (mine[n][1], n))
        hurt, attacks = lines[:_HURT_LINES], lines[_HURT_LINES:_HURT_LINES + _ATTACK_LINES] or lines
        for k, slot in enumerate(ROLE_SLOTS["hurt"] if hurt else ()):
            binds[BASE_CLIPS.index(slot)] = leaf(hurt[k % len(hurt)])
            own.add("hurt")
        speech = [mine[n][0] for n in dict.fromkeys(hurt + attacks)]
    else:
        attacks = _role_names(mine, "attack")
    turn = 0
    for k, col in enumerate(columns):
        clip = (anim_picks.get(col) or "").casefold()
        if col == ROLL:
            if clip in mine and not town:
                binds[ATTACK_SLOT + k] = leaf(clip)
                own.add("roll")
        elif clip in mine and not town and _role_names([clip], "attack"):
            binds[ATTACK_SLOT + k] = leaf(clip)
        elif attacks:
            binds[ATTACK_SLOT + k], turn = leaf(attacks[turn % len(attacks)]), turn + 1
        elif clip in garret4:   # Garret's line on an attack (AZ-392): none, as garret4's own
            binds[ATTACK_SLOT + k] = ""
    roll = ATTACK_SLOT + columns.index(ROLL)
    roll_from = None if roll in binds else next(
        (col for k, col in enumerate(columns) if col != ROLL and binds.get(ATTACK_SLOT + k)), None)
    if roll_from is not None:   # D328: the roll takes its first attack's sound
        binds[roll] = binds[ATTACK_SLOT + columns.index(roll_from)]
        own.add("roll")
    shouts = tuple(col for k, col in enumerate(columns) if binds.get(ATTACK_SLOT + k))
    own |= {"attack"} if set(shouts) - {ROLL} else set()
    own |= {"footstep"} if "walkl" in xbe else set()

    sounds = column("critters_sounds", species)
    hits = {row: value for row, value in sounds.items()
            if row and row not in _NOT_HIT_ROWS and value and value.casefold() != _HEAL}
    own |= {"ambient"} if sounds.get("ambient") else set()
    own |= {"hit"} if hits else set()
    return SoundRoles(
        species=species,
        sound_dir=next(iter(mine.values()))[0].rsplit("/", 1)[0] if mine else None,
        binds=binds, own=tuple(r for r in ROLES if r in own), shouts=shouts,
        ouch=sounds.get("ouch"), ambient=sounds.get("ambient"), hit_rows=hits,
        speech=tuple(speech), xbe=xbe, roll_from=roll_from)


# --- X14: the table and its two hooks ---------------------------------------
TABLE_SIZE = 1024
"""The shim's table, ``TABLE_SIZE`` in ``player_model/sounds.c``."""
SOUNDS_TABLE = BytesParam(name="sounds", symbol="_player_model_sounds", size=TABLE_SIZE,
                          label="Player model sounds (X14)")


def sound_table(roles: SoundRoles) -> bytes:
    """``roles``' binds as X14's table (``player_model/sounds.c``): u16
    the dir's offset, u16 the slots covered, a u16 offset per slot (0: a
    miss), then the NUL-terminated names.  A table past
    :data:`TABLE_SIZE` raises :class:`ValueError` (D35)."""
    count = max(roles.binds, default=-1) + 1
    pool = bytearray()
    at: dict[str, int] = {}
    base = 4 + 2 * count

    def put(name: str) -> int:
        if name not in at:
            at[name] = base + len(pool)
            pool.extend(name.encode("ascii") + b"\0")
        return at[name]

    head = struct.pack("<HH", put(roles.sound_dir or ""), count)
    slots = struct.pack(f"<{count}H", *(put(roles.binds[s]) if s in roles.binds else 0
                                        for s in range(count)))
    table = head + slots + bytes(pool)
    if len(table) > TABLE_SIZE:
        raise ValueError(f"{roles.species}'s sound table takes {len(table)} bytes, "
                         f"past X14's {TABLE_SIZE}")
    return table


BASE_HOOK_VA = 0x4B93C
"""0x4B8E0's CALL of 0x4B680 for the base clips, which X14 replaces."""
ATTACK_HOOK_VA = 0x7E3DD
"""load_attacks_anims_config's CALL of 0x4B680 for each Anim, which X14
replaces."""
SOUNDS_SHIM = ShimSource(folder=Path(__file__).resolve().parent / "player_model", stem="sounds")
SOUNDS_SHIM_NAME = "player_model_sounds"
"""Its object's name: ``player_model_sounds.o`` in the shim build dir."""
SOUND_HOOKS = tuple(TrampolinePatch(
    name=SOUNDS_SHIM_NAME,
    label=f"Player model sounds: the model's own (X14) at VA 0x{va:X}",
    va=va,
    replaced_bytes=vanilla,
    shim_object=SOUNDS_SHIM.object_path(SOUNDS_SHIM_NAME, CHECKOUT),
    shim_symbol="_c_player_model_sounds",
    bytes_params=(SOUNDS_TABLE,),
) for va, vanilla in ((BASE_HOOK_VA, bytes.fromhex("e83ffdffff")),      # CALL 0x4B680
                      (ATTACK_HOOK_VA, bytes.fromhex("e89ed2fcff"))))   # CALL 0x4B680


# --- W9-W11: config.xbr's cells (Step 2.72) ----------------------------------
SHOUT_ROWS = ("Sound", "Sound 2", "Sound 3", "Sound 4")
"""``attacks_anims``' attack shouts: one plays at random as the attack
starts (0x88DD9, 0x88FED); an empty cell is skipped (0xD1630)."""
SHOUTED = ("basic1", "basic2", "basic3", "finish", "finish2", "finish3", "sweep1", "sweep2", "sweep ledge",
           "hose_attack_3", "jump attack", "right1", "right2", "left1", "left2", "back1", "back2", "up1", "up2",
           "down")
"""The columns whose :data:`SHOUT_ROWS` give Garret a shout in vanilla
(both releases), the roll aside: 20 of 24, not his casts (Step 2.183's
trace, one shout made at each of their starts, none at a cast's).  A
variant's ``shouts`` play there under another weapon (D705)."""


def write_sound_cells(config, roles: SoundRoles) -> dict[str, int]:
    """W9-W11 in ``config`` (the staged ``config.xbr``'s
    :class:`XbrDocument`): each :attr:`SoundRoles.shouts` column's
    ``Sound`` cells emptied, garret4's ``critters_sounds`` ``ouch``,
    ``ambient`` and hit rows pointed at the species' strings (an empty
    cell filled).  Returns how many shout cells it emptied per column.
    :class:`~azurik_mod.xbr.edits.XbrStructuralError` names a cell it
    can't write (D35)."""
    anims = config.keyed_section("attacks_anims")
    columns = anims.col_names()
    emptied: dict[str, int] = {}
    for col in roles.shouts:   # W9
        c = columns.index(col)
        for row in SHOUT_ROWS:
            if anims.find_cell(col, row, c).type_code:
                clear_keyed_cell(anims, col, row, c)
                emptied[col] = emptied.get(col, 0) + 1
    sounds = config.keyed_section("critters_sounds")
    cols = sounds.col_names()
    rows = [row for row, value in (("ouch", roles.ouch), ("ambient", roles.ambient)) if value]
    for row in (*rows, *roles.hit_rows):   # W10, W11
        point_keyed_string(sounds, PLAYER, row, roles.species, row, col=cols.index(PLAYER),
                           src_col=cols.index(roles.species), fill_empty=True)
    return emptied


# --- X15: the XBE's jump and footstep paths (Step 2.72, D233) ----------------
class XbeSoundSite(NamedTuple):
    """A ``mov ecx|edi, imm32`` that loads one of the player's
    ``fx/sound/player/*`` paths for 0xA5CA0 (``docs/RE_DATA.md`` § "How a
    critter's sounds are chosen"); X15 points its imm32 at the model's."""

    sound: str
    """The :attr:`SoundRoles.xbe` key: ``jump``, ``flap`` (the wing flap's
    jump sound), ``walkl`` or ``walkr``, or a variant's ``ouch``,
    ``fallingdeath`` or ``landing``."""
    va: int
    original: bytes
    """Its vanilla bytes: the opcode and the path's VA."""


XBE_SOUND_SITES = (
    XbeSoundSite("jump", 0x892AD, bytes.fromhex("b934bf1900")),    # player_jump_init: mov ecx
    XbeSoundSite("flap", 0x89466, bytes.fromhex("b934bf1900")),    # wing_flap: mov ecx
    XbeSoundSite("walkl", 0x8656D, bytes.fromhex("bffcbf1900")),   # player_walk_state: mov edi
    XbeSoundSite("walkr", 0x865C8, bytes.fromhex("bfe4bf1900")),   # player_walk_state: mov edi
    XbeSoundSite("walkl", 0x8B002, bytes.fromhex("b9fcbf1900")),   # 0x8AE10 (landing too): mov ecx
    XbeSoundSite("ouch", 0x8ADC2, bytes.fromhex("b948be1900")),    # fall_damage_dispatch: mov ecx
    XbeSoundSite("fallingdeath", 0x8BF61, bytes.fromhex("b970bd1900")),   # fall_death_dispatch: mov ecx
    XbeSoundSite("landing", 0x8B0DB, bytes.fromhex("b930be1900")),        # 0x8AE10: mov ecx
    XbeSoundSite("landing", 0x8B195, bytes.fromhex("b930be1900")),        # 0x8B100: mov ecx
)
"""X15's sites: ``fx/sound/player/jump`` (0x19BF34; ``flap`` the wing
flap's load of it), ``walkl``
(0x19BFFC) and ``walkr`` (0x19BFE4); for a variant (Step 2.141) also
``ouch`` (0x19BE48, the fall's damage), ``fallingdeath`` (0x19BD70, the
falling scream) and ``landing`` (0x19BE30).  Each caller skips the sound
when 0xA5CA0 finds no wave of the name (``cmp eax, -1`` at 0x8ADCC,
0x8B19F; 0x8D4E0's at 0x8D4EC for 0x8BF61 and 0x8B0DB)."""


def install_xbe_sounds(xbe: bytearray, roles: SoundRoles) -> None:
    """X15 in ``xbe`` (either release): each :attr:`SoundRoles.xbe` wave
    name carved into the image once, and each of its
    :data:`XBE_SOUND_SITES` loading that instead of Garret's path.  A
    site that doesn't hold its vanilla bytes raises :class:`ValueError`
    before anything is written (D27, D35)."""
    sites = []
    for site in XBE_SOUND_SITES:
        if site.sound in roles.xbe:
            _, off, vanilla = xbe_site(xbe, site.va, site.original)
            if bytes(xbe[off:off + len(vanilla)]) != vanilla:
                raise ValueError(f"X15: VA 0x{site.va:X} doesn't hold vanilla's {site.sound} "
                                 f"path; rebuild from vanilla")
            sites.append((off, vanilla[0], roles.xbe[site.sound]))
    carved = {name: carve_shim_landing(xbe, name.encode("ascii") + b"\0")[1]
              for name in dict.fromkeys(name for *_, name in sites)}
    for off, opcode, name in sites:
        xbe[off:off + 5] = struct.pack("<BI", opcode, carved[name])


def variant_roles(species: str, sound_dir: str, columns: list[str], sfx: dict[str, str], silent: bool,
                  dropped: frozenset[str] = frozenset()) -> SoundRoles:
    """A variant's sounds as the player's (Step 2.141; D328, D384, D386),
    on a base with none of its own: ``sfx`` (``attacks_anims`` column ->
    its sound's name) binds each column from ``sound_dir``; with
    ``silent`` the :data:`VOICE_SLOTS` and every other column bind
    nothing and W9 empties every column's shouts; ``dropped`` (the
    :data:`~azurik_mod.patches._player_variants.DROP_ROLES` its WAVs fill:
    the recipe's ``wavs`` and a drop-in folder's) binds each role in its
    slots (:data:`DROP_SLOTS`) and X15's sites (:data:`DROP_SITES`), the
    falls' ``hurt`` (``fall`` when it has one) and ``death`` also when
    silent (a name no wave has: no sound); the roll takes a dropped
    ``roll``, else its first attack column's sound (D328), else nothing
    when silent.  Jump, land and footstep slots, the wing flap and the
    XBE's other paths stay Garret's: effects (D386)."""
    binds = dict.fromkeys(VOICE_SLOTS, "") if silent else {}
    for k, col in enumerate(columns):
        if col in sfx:
            binds[ATTACK_SLOT + k] = sfx[col]
        elif silent and col != ROLL:
            binds[ATTACK_SLOT + k] = ""
    for role, slots in DROP_SLOTS.items():
        if role in dropped:
            binds.update(dict.fromkeys((BASE_CLIPS.index(slot) for slot in slots), role))
    roll, roll_from = ATTACK_SLOT + columns.index(ROLL), None
    if "roll" in dropped:
        binds[roll] = "roll"
    else:
        roll_from = next((col for k, col in enumerate(columns) if col != ROLL and binds.get(ATTACK_SLOT + k)), None)
        if roll_from is not None:   # D328
            binds[roll] = binds[ATTACK_SLOT + columns.index(roll_from)]
        elif silent:
            binds[roll] = ""
    xbe = {path: f"{sound_dir}/{role}" for role, paths in DROP_SITES.items()
           if role in dropped or silent and role in ("hurt", "death") for path in paths}
    shouts = tuple(col for k, col in enumerate(columns) if silent or binds.get(ATTACK_SLOT + k))
    own = {"attack"} if any(binds.get(ATTACK_SLOT + k) for k, col in enumerate(columns) if col != ROLL) else set()
    own |= {"roll"} if binds.get(roll) else set()
    return SoundRoles(species=species, sound_dir=sound_dir, binds=binds,
                      own=tuple(r for r in ROLES if r in own | dropped), shouts=shouts, xbe=xbe,
                      roll_from=roll_from, silent=silent)


def kit_swings(roles: SoundRoles, columns: list[str], swung: set[str], name: str, kit_dir: str) -> SoundRoles:
    """``roles`` with each column of ``swung`` (an attack style's, Step
    2.159a; D502: bare hands' swings whoosh) binding ``name``, a wave the
    build adds under the dir X14 binds from: ``roles``' own (a
    townsperson's speech dir, a variant's) or, with none, ``kit_dir``.
    The roll takes the first attack column's sound where it has none of
    its own (D328), and W9 empties the shouts of every column binding
    one."""
    binds = dict(roles.binds)
    for k, col in enumerate(columns):
        if col in swung and col != ROLL:
            binds[ATTACK_SLOT + k] = name
    roll, roll_from = ATTACK_SLOT + columns.index(ROLL), roles.roll_from
    if roll_from is not None or roll not in binds:
        roll_from = next((col for k, col in enumerate(columns) if col != ROLL and binds.get(ATTACK_SLOT + k)), None)
        if roll_from is not None:
            binds[roll] = binds[ATTACK_SLOT + columns.index(roll_from)]
    shouts = tuple(col for k, col in enumerate(columns) if col in roles.shouts or binds.get(ATTACK_SLOT + k))
    own = set(roles.own) | {"attack"} | ({"roll"} if binds.get(roll) else set())
    return replace(roles, sound_dir=roles.sound_dir or kit_dir, binds=binds, shouts=shouts,
                   own=tuple(r for r in ROLES if r in own), roll_from=roll_from, swing=name)


def describe_variant(roles: SoundRoles, emptied: dict[str, int], columns: list[str],
                     made: dict[str, tuple[int, int]], waves: int, size: int, drops: list[str]) -> list[str]:
    """The build-log lines of a variant's sounds (:func:`variant_roles`;
    ``columns``: ``attacks_anims``'): ``made`` (each ``sfx`` -> its takes
    and columns), ``waves`` and ``size`` (the waves added to ``fx.xbr``
    and their bytes), ``drops`` (a line per WAV file, the recipe's and a
    drop-in folder's)."""
    shouts = sum(emptied.values())
    quiet = ", ".join(r for r in VOICE_ROLES if r not in roles.own)
    grunts = [g for g in GRUNTS if not roles.binds.get(BASE_CLIPS.index(g))]
    climbs = [g for g in GRUNTS if g not in grunts]
    voice = (f"none (D386): {quiet + ' and ' if quiet else ''}{len(grunts)} of Garret's {len(GRUNTS)} effort grunts "
             f"({', '.join(grunts)}) bind nothing (X14)"
             + (f", {' and '.join(climbs)} bind its climb (X14)" if climbs else "")
             + f", his shouts are off in {shouts} cells (W9), and the "
             f"fall's ouch and the falling scream load {roles.xbe['ouch']} and {roles.xbe['fallingdeath']} (X15), "
             "no sound where no WAV of its is that wave" if roles.silent else
             f"Garret's, his shouts off in the {shouts} cells of its own attacks (W9)")
    played = ", ".join(f"{name} x{takes} in {cols} column{'s' * (cols != 1)}" for name, (takes, cols) in made.items())
    roll = roles.binds.get(ATTACK_SLOT + columns.index(ROLL))
    heard = [r for r in VOICE_ROLES if r in roles.own] + (["climb"] if climbs else [])
    lines = ["  Player model sounds: its own attacks, its voice " + (
                 ("silent" + (f" but its {' and '.join(heard)}" if heard else "")) if roles.silent else "Garret's")
             + " (D384, D386)", f"    voice: {voice}"]
    if played:
        lines.append(f"    attack: {played} (X14)")
    lines.append(f"    sounds: {waves} wave{'s' * (waves != 1)}, {size} B, in fx.xbr under {roles.sound_dir} with "
                 "their index.xbr records")
    lines.append(f"    roll: {roll}, its {roles.roll_from} attack's sound (D328)" if roles.roll_from else
                 f"    roll: {roll} (a WAV)" if roll else "    roll: none")
    if "jump" in roles.xbe:
        lines.append(f"    jump: {roles.xbe['jump']} (X15), the wing flap Garret's")
    effects = [r for r in ("jump", "land", "footstep") if r not in roles.own]
    lines.append(f"    {', '.join(effects + ['hits'])}: Garret's (effects)")
    return lines + [f"    {line}" for line in drops]


def describe(roles: SoundRoles, emptied: dict[str, int]) -> list[str]:
    """The build-log lines of a model's own sounds: each role and where
    its sound comes from (X14, W9-W12, X15), or Garret's (D232).
    ``emptied``: :func:`write_sound_cells`' count."""
    where = "its speech lines (X14, W12)" if roles.speech else f"{roles.sound_dir} (X14)"
    silent = sum(1 for k, bind in roles.binds.items() if k >= ATTACK_SLOT and bind == "")
    shouts = sum(n for col, n in emptied.items() if col != ROLL)
    swung = f"bare hands' whoosh, {roles.sound_dir}/{roles.swing} (X14, D502)" if roles.swing else where
    source = {
        "attack": f"{swung}, Garret's shouts off in {shouts} cells (W9)",
        "roll": swung + (f", its {roles.roll_from} attack's sound (D328)" if roles.roll_from else "")
                + (", Garret's grunt off (W9)" if emptied.get(ROLL) else ""),
        "hurt": where + (f", each hit {roles.ouch} (W10)" if roles.ouch else "")
                + (f", a fall's damage {roles.xbe['ouch']} (X15)" if "ouch" in roles.xbe else ""),
        "death": where + (f", a falling death {roles.xbe['fallingdeath']} (X15)"
                          if "fallingdeath" in roles.xbe else ""),
        "jump": f"{roles.xbe['jump']} at the jump and the wing flap (X15)"
                if "jump" in roles.xbe else where,
        "footstep": where + (f", the steps {roles.xbe['walkl']} and {roles.xbe['walkr']} (X15)"
                             if "walkl" in roles.xbe else ""),
        "ambient": f"{roles.ambient} (W10)",
        "hit": f"{roles.species}'s {len(roles.hit_rows)} hit rows (W11)",
    }
    silenced = (f", none on the {silent} attacks whose clip would play his ouch_1 (AZ-392)"
                if silent else "")
    return ["  Player model sounds: its own where it has them, else Garret's (D231, D232)",
            *(f"    {role}: " + (source.get(role, where) if role in roles.own else
                                 "Garret's" + (silenced if role == "attack" else ""))
              for role in ROLES)]


__all__ = [
    "ATTACK_HOOK_VA",
    "CLIMB_SLOTS",
    "DROP_SITES",
    "DROP_SLOTS",
    "FALL_VOICES",
    "GRUNTS",
    "VOICE_ROLES",
    "VOICE_SLOTS",
    "describe_variant",
    "variant_roles",
    "ATTACK_SLOT",
    "BASE_HOOK_VA",
    "ROLES",
    "ROLE_SLOTS",
    "SHOUTED",
    "SHOUT_ROWS",
    "SOUNDS_SHIM",
    "SOUNDS_SHIM_NAME",
    "SOUNDS_TABLE",
    "SOUND_HOOKS",
    "SOUND_MODES",
    "SoundRoles",
    "TABLE_SIZE",
    "XBE_SOUND_SITES",
    "XbeSoundSite",
    "describe",
    "install_xbe_sounds",
    "kit_swings",
    "sound_roles",
    "sound_table",
    "write_sound_cells",
]

"""Weapons and the weaponless townsfolk's throw (Modkit's ``tests/test_player_weapons.py`` and
``test_player_throw.py``, ported lean: Step 4.27d). Weapons are data (``weapons.json``, D492-D495): each body's
default weapon, what a build makes of a picked one (``_player_weapons.loadout``: its prop, style, boxes, reach and
grade) and the moveset weapons (D585); the throw (D473) is W30's projectile ``debug`` and X42, which throws it, the
effects templates' rows (D538) too. Each build is the swap's own dress (``tools.characters.dressed``, which the
plan calls) of the USA image with no pack on, as Modkit's tests dressed a fresh staging; X42's and the attack
state's checks run on ``devkit/sim``'s L2."""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import hashlib
import json
import math
import re
import struct
from collections import OrderedDict
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

from azurkit.core import gate
from azurkit.core.xbr.append import append_resources
from azurkit.core.xbr.clone import closure, refs_in
from azurkit.core.xbr.graph import IDENTITY, Graph, Schema, apply, bind_name, list_at, lstr, mat_mul, record_offsets
from azurkit.core.xbr.nodes import named_resources, parse_toc
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_character as pc
from azurkit.tools.characters import _player_fx_ring as fx_ring
from azurkit.tools.characters import _player_power_fx as power
from azurkit.tools.characters import _player_throw as throws
from azurkit.tools.characters import _player_weapons as pw
from azurkit.tools.characters import fx_edit, fx_templates, model_inspect, paint, picker, ports, render
from azurkit.tools.characters._player_damage_marker import BOX, BOXES_SIZE, DAMAGE_MARKER, GARRET4_FORWARD
from azurkit.tools.characters._player_damage_marker import garret4_window
from azurkit.tools.characters._player_kit import kit_document, kit_style
from azurkit.tools.characters._player_sounds import ATTACK_SLOT, SHOUT_ROWS, SHOUTED
from azurkit.tools.characters._player_variants import arm_turns, builtins, load_variants, options
from azurkit.tools.characters._player_weapons import (GOOD, WEAPON_GRADES, WEAPONS_FILE, _donor, _staff_hold,
                                                      default_weapon, grade, grips, load_weapons, loadout, offers,
                                                      pick_grade, pick_sha, seen, weapons)
from azurkit.tools.characters.body_codec import read_asset
from azurkit.tools.characters.characters import (body_names, damage_windows, forward, height, marker_records,
                                                 mesh_bounds, read_body)
from azurkit.tools.characters.index_xbr import parse_index_xbr
from azurkit.tools.characters.retarget import (BAKED_DIR, MAPS, TARGETS, Retarget, Rig, _turn, bake_clip, evaluate,
                                               named_clip, origins, pose, qinv, qmul, qnorm, turned)
from devkit.sim import l1, l2

XBE, CONFIG, CHARACTERS, FX, INDEX = "default.xbe", "config.xbr", "characters.xbr", "fx.xbr", "index.xbr"
FULL = {XBE: "default.xbe", CONFIG: "gamedata/config.xbr", CHARACTERS: "gamedata/characters.xbr",
        FX: "gamedata/fx.xbr", INDEX: "gamedata/index/index.xbr"}


@functools.cache
def _image(path: str) -> ports.Vanilla:
    """The vanilla files of the image at ``path``, each read checked against its release's manifest."""
    stamp = gate.verify(path, whole=False)
    return ports.Vanilla(stamp.release, stamp.path, stamped=stamp)


def _vanilla(image, name: str) -> bytes:
    """The vanilla file ``name`` (``XBE``, ``CONFIG``, ...) of ``image``."""
    return _image(str(image)).read(FULL[name])


@contextlib.contextmanager
def _building(image):
    """The context the swap's hook and shim readers run in (``ports.building``): ``image``'s vanilla files."""
    v = _image(str(image))
    with ports.building(ports.Build(v, taken=[], packs=characters.packs_view(v.release, mods.PACKS))) as b:
        yield b


_BUILT: OrderedDict = OrderedDict()   # the last few dresses, for the tests that read one twice


def _swap(image, species: str, *, logic: pc.AttackLogic | None = None, worn=None, lines: list | None = None,
          **character) -> dict[str, bytes]:
    """``species`` (or the variant ``worn``) dressed on ``image``'s vanilla files with ``character``'s fields
    (``tools.characters.dressed``, no pack on): each file it reads, by short name; ``logic`` gets the build's
    ``AttackLogic`` and ``lines`` its log."""
    character = {k: v for k, v in character.items() if v is not None}
    key = (str(image), species, json.dumps(character, sort_keys=True), worn and worn.sha)
    if key not in _BUILT:
        v, filled = _image(str(image)), pc.AttackLogic()
        staging, _, _, log = characters.dressed(characters.normalize({"species": species, **character}), v, (),
                                                characters.packs_view(v.release, mods.PACKS), worn=worn, logic=filled)
        _BUILT[key] = ({name: bytes(staging[name]) for name in FULL}, dict(vars(filled)), list(log))
        while len(_BUILT) > 4:
            _BUILT.popitem(last=False)
    files, filled, log = _BUILT[key]
    if logic is not None:
        vars(logic).update(filled)
    if lines is not None:
        lines += log
    return files


@pytest.fixture
def usa(usa_iso):
    """The USA image, inside :func:`_building`."""
    with _building(usa_iso):
        yield usa_iso


def _doc(data: bytes) -> ports.XbrDocument:
    return ports.XbrDocument(bytearray(data))


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _symbol(xbe: bytes, hook, symbol: str) -> int:
    """Where ``symbol`` of ``hook``'s shim landed in the built ``xbe`` (inside :func:`_building`)."""
    return ports.trampoline_symbol_va(xbe, hook, symbol)


def _read(xbe: bytes, va: int, size: int) -> bytes:
    at = ports.resolve_va_to_file(xbe, va)
    return bytes(xbe[at:at + size])


def _param(xbe: bytes, hook, symbol: str) -> float:
    """A shim's float param in the built ``xbe``."""
    return struct.unpack("<f", _read(xbe, _symbol(xbe, hook, symbol), 4))[0]


def _boxes(xbe: bytes) -> int:
    """The file offset of X3's box table's first row in the built ``xbe``."""
    span, = [s for s in ports.trampoline_shim_data(xbe, DAMAGE_MARKER) if s[1] - s[0] == BOXES_SIZE]
    return ports.resolve_va_to_file(xbe, span[0]) + 4


def _played(config: bytes) -> tuple[list[str], list[str]]:
    """``attacks_anims``' columns in ``config`` and the clip each one's Anim names."""
    anims = _doc(config).keyed_section("attacks_anims")
    columns = anims.col_names()
    return columns, [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]


def _drawn(config: bytes) -> float:
    """The player's drawn scale in a built ``config`` (a blank cell: 1)."""
    return _doc(config).keyed_section("critters_engine").find_cell("garret4", "scale", None).double_value or 1.0


def _body(characters_xbr: bytes, config: bytes, species: str) -> str:
    """The body ``species`` wears in ``config``'s critters_engine."""
    return pc._species(_doc(config).keyed_section("critters_engine"))[species]["body"]


# --- weapons as data: each body's default, what a build makes of it (Modkit's Step 2.161a) --------------------------
HOE = (("right_hand", ("joint74", "joint97")), ("joint74", "joint97"))
"""A farmer's carried hoe: its carriers under its hand, and W6's fx ends."""
FARMHAND = {"farmhand": {"title": "a farmer's variant", "base": "town_male_farmer_1", "columns": {"basic1": "walk"}}}


@pytest.mark.parametrize("edit, refused", [
    (lambda d: d["props"]["hoe"].update(colour=1), "props.hoe: unknown key 'colour'"),
    (lambda d: d["props"]["hoe"].pop("hand"), "props.hoe: a loose prop names the clip"),
    (lambda d: d["props"]["axion"].update(ends="tip"), "props.axion.ends: 'tip' is not one of native, carriers"),
    (lambda d: d["styles"]["kit_townsfolk"].update(kit="knights"), "styles.kit_townsfolk.kit: 'knights' is no kit"),
    (lambda d: d["weapons"]["bare_hands"].update(style="fists"), "weapons.bare_hands.style: 'fists' is no style"),
    (lambda d: d["weapons"]["farmers_hoe"].update(style="kit_townsfolk"),
     "weapons.farmers_hoe: a loose prop rides its style's held channel"),
    (lambda d: d["styles"]["balthazar"].update(clips="his_best"), "styles.balthazar.clips: 'his_best' is not "),
    (lambda d: d["styles"]["balthazar"].pop("dir"), "styles.balthazar: a source's own build names its source, its dir"),
    (lambda d: d["grips"]["catalisk"].update(turn=[0, 90]), "grips.catalisk.turn: [0, 90] is not a list of three"),
    (lambda d: d["styles"]["booblord_spins"].update(variant="queenlord"),
     "styles.booblord_spins.variant: 'queenlord' is no built-in variant"),
    (lambda d: d["styles"]["booblord_spins"].update(kit="townsfolk"),
     "styles.booblord_spins: a style names its source rig, its kit or a variant's recipe, one of them"),
    (lambda d: d.setdefault("fits", {}).update(keylord={"clips": {"attack_9": [10]}}),
     "fits.keylord.clips.attack_9: [10] is not two finite numbers"),
    (lambda d: d["styles"]["balthazar"].update(effects=[{"template": "laser", "columns": ["basic1"],
                                                          "turn": [0, 0, 1]}]),
     "styles.balthazar.effects[0]: unknown key 'turn'")])
def test_weapons_json_refuses_a_record_it_cant_read(edit, refused):
    """weapons.json is data only, read as a variant recipe is: a key or value the loader doesn't know, or a
    record naming one that isn't there, fails by name before any build (D35); the built-in file loads, its creature
    grips too (Modkit's Steps 2.161a, 2.161e)."""
    doc = json.loads(WEAPONS_FILE.read_text(encoding="utf-8"))
    assert sorted(load_weapons(json.dumps(doc))) == ["axion_staff", "balthazar_magic", "bare_hands", "booblord_spin",
                                                     "farmers_hoe"]
    edit(doc)
    with pytest.raises(ValueError, match=re.escape(refused)):
        load_weapons(json.dumps(doc))


def test_each_bodys_default_weapon_is_the_build_it_makes_today(usa_iso):
    """Every body keeps a default weapon, derived from the body (D492-D495; the goldens pin its builds' bytes):
    garret4 the Axion staff, balthazar_airship Balthazar's magic, the six townsmen farmers (the only bodies with a
    loose prop) the hoe, carried on joint74 and joint97 under the right hand in every mode with W6's fx at their
    ends, the 23 other bodies the bake maps with no attack clip (the townspeople) bare hands, every other its own; a
    farmer in Balanced on a baked body swings garret4's attacks grown to the hoe's tip, a variant of one keeps its
    base's picks; bare hands bake their family's kit (t/); booblord's recipe names the Axion staff (D939), copied
    into her right hand. The Weapon box (Modkit's ``player-models --weapons``) shows each usable species' default
    so (Modkit's Steps 2.161a, 2.161g, 2.209)."""
    characters_xbr, config = _vanilla(usa_iso, CHARACTERS), _vanilla(usa_iso, CONFIG)
    rows = pc._species(_doc(config).keyed_section("critters_engine"))
    worn = builtins() | load_variants(json.dumps(FARMHAND), "test")
    table = {   # (species or variant, mode, anims): weapon, borrows, kit (source, dir), carriers, its tip, fx ends
        ("garret4", "own", "garret4"): ("axion_staff", False, None, None, False, None),
        ("town_male_farmer_1", "own", "garret4"): ("farmers_hoe", True, None, HOE[0], True, HOE[1]),
        ("town_male_farmer_1", "garret4", "garret4"): ("farmers_hoe", False, None, HOE[0], False, HOE[1]),
        ("town_male_farmer_1", "own", "own"): ("farmers_hoe", False, None, HOE[0], False, HOE[1]),
        ("farmhand", "own", "garret4"): ("farmers_hoe", False, None, HOE[0], False, HOE[1]),
        ("town_male_6", "own", "garret4"): ("bare_hands", False, ("townspeople/male_6", "t/"), None, False, None),
        ("town_child_1", "own", "garret4"): ("bare_hands", False, ("townspeople/child_1", "t/"), None, False, None),
        ("town_child_1", "garret4", "garret4"): ("bare_hands", False, None, None, False, None),
        ("booblord", "own", "garret4"): ("axion_staff", True, None, ("right_hand", ("m_stafftop", "m_staffbottom")),
                                         True, None),
        ("balthazar", "own", "garret4"): ("balthazar_magic", False, None, None, False, None),
        **{(s, "own", "garret4"): ("own", False, None, None, False, None)
           for s in ("keylord", "air_elemental", "gargoylestone", "flicken")},
    }
    got = {}
    for who, mode, anims in table:
        variant = worn.get(who)
        body = read_body(characters_xbr, rows[variant.base if variant else who]["body"])
        lo = loadout(characters_xbr, body, mode, pc.bakes(body, anims), variant)
        got[who, mode, anims] = (lo.name, lo.borrowing, lo.kit and (lo.kit.source, lo.kit.dir),
                                 lo.carriers and (lo.carriers.hand, lo.carriers.bones), lo.reaching, lo.fx_ends)
    assert got == table

    by: dict[str, set[str]] = {}
    for name in body_names(characters_xbr):
        try:
            body = read_body(characters_xbr, name)
        except ValueError:
            continue
        weapon = default_weapon(characters_xbr, body)
        by.setdefault(weapon.name if weapon else "own", set()).add(name)
    farmers = {f"townspeople/male_farmer_{n}" for n in range(1, 7)}
    assert {k: v for k, v in by.items() if k != "own"} == {
        "axion_staff": {"garret4"}, "balthazar_magic": {"balthazar_airship"}, "farmers_hoe": farmers,
        "bare_hands": {b for b in MAPS if b.startswith("townspeople/")} - farmers}

    digest, listed = hashlib.sha256(characters_xbr).hexdigest(), {}
    for m in pc.player_models(config, characters_xbr):
        if m.status != pc.REFUSED:
            box = picker._weapons(picker._offers(characters_xbr, digest, m.body, "own", None), None,
                                  lambda name, fit: (None, "", True))
            listed.setdefault(box[0]["shows"] or "own", set()).add(m.species)
    assert {k: len(v) for k, v in listed.items() if k != "own"} == {
        "axion_staff": 1, "balthazar_magic": 1, "farmers_hoe": 6, "bare_hands": 30}
    assert listed["farmers_hoe"] == {f"town_male_farmer_{n}" for n in range(1, 7)}


def _x3_tick(xbe: bytes, attack: int, done: float, *, scale: float = 1.0) -> tuple[tuple[float, float], tuple]:
    """One tick of the built ``xbe``'s X3 (the hook at 0x8C3B0, L2): attack column ``attack``, ``done`` of the way
    through its move, on a critter drawn ``scale``: the marker X3 hands the damage pass, as (length, active), and
    its centre and extents."""
    entry = DAMAGE_MARKER.va + 5 + struct.unpack_from("<i", xbe, ports.va_to_file(DAMAGE_MARKER.va) + 1)[0]
    pcl, critter = 0x20000000, 0x20001000
    sim = l2.Sim(xbe)
    sim.uc.mem_map(pcl, 0x10000)
    for at, fmt, value in ((pcl + 0x20, "<I", critter), (pcl + 0x94, "<I", 0x100), (pcl + 0xF8, "<f", 0.1),
                           (pcl + 0x100, "<f", 0.9), (pcl + 0x134, "<i", attack), (pcl + 0x178, "<f", 0.1 + 0.8 * done),
                           (critter + 0x188, "<f", scale), (critter + 0x218, "<I", 0), (critter + 0x21C, "<I", 0),
                           (critter + 0x200, "<i", 0x52 + attack)):
        sim.uc.mem_write(at, struct.pack(fmt, value))
    sim.call(entry, args=(pcl,), until=0x8C8A0)
    marker = sim.u32(critter + 0x218)
    assert marker, "X3 handed the damage pass no marker"
    return (struct.unpack("<2f", sim.uc.mem_read(marker + 0x2C, 8)),
            struct.unpack("<3f", sim.uc.mem_read(marker + 4, 12)) + struct.unpack("<3f", sim.uc.mem_read(marker + 0x20, 12)))


@pytest.mark.parametrize("species, weapon", [("town_male_farmer_1", None), ("keylord", "farmers_hoe")])
def test_the_attack_listing_holds_the_boxes_the_build_installs(usa, species, weapon):
    """The attack listing (``_player_character.attacks``) reads the build's loadout (Modkit's Step 2.161a, F1, F2: it
    once re-derived the picks apart from the build): each column lists the clip the build plays (garret4's, baked
    as g4/) and the box and window X3's table holds for it as the game sends it (AZ-766: ``sent_window``), grown to
    the hoe's tip where the farmer's or keylord's own hand carries it (Step 2.161b)."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    rows = pc.attacks(config, characters_xbr, species, weapon=weapon)
    rates = _doc(config).keyed_section("attacks_anims")
    game = _swap(usa, species, sounds="garret4", weapon=weapon)
    xbe, (columns, played) = game[XBE], _played(game[CONFIG])
    assert [r.clip for r in rows] == [BAKED_DIR + p for p in played]
    at, garret4, listed = _boxes(xbe), read_body(characters_xbr, "garret4"), []
    for i, r in enumerate(rows):
        if r.x3:
            (w,), clip = r.windows, r.clip[len(BAKED_DIR):]
            length, row = garret4.length(clip), BOX.unpack_from(xbe, at + BOX.size * i)
            assert (r.borrowed, r.held) == (True, True), r.column
            box = pc.DamageWindow(w.marker, row[0] * length, row[1] * length,
                                  tuple(c - e / 2 for c, e in zip(row[2:5], row[5:8])),
                                  tuple(c + e / 2 for c, e in zip(row[2:5], row[5:8])), 0.0, 0.0)
            sent = pc.sent_window(characters_xbr, "garret4", clip, rates.find_cell(r.column, "Rate", i).double_value,
                                  box)
            listed.append(((sent.on, sent.off, *sent.low, *sent.high),
                           pytest.approx((w.on, w.off, *w.low, *w.high), abs=1e-5)))
    assert len(listed) == len(rows) - 1 and all(built == want for built, want in listed)   # every column but the roll


def test_the_attack_listing_plays_a_lent_movesets_spins_with_their_own_boxes(usa):
    """AZ-763 (Modkit's Step 2.198): the listing of town_male_6 with Booblord spin listed the bare-hands kit in every
    column where the build plays her spins in 19: it reads the recipe the build plays, so each column lists the clip
    the build's Anim cell names and each spin its own box (the damage windows of the clip W22 generated, at the
    build's scale), X13 leaving it as keyed."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    rows = pc.attacks(config, characters_xbr, "town_male_6", weapon="booblord_spin")
    game = _swap(usa, "town_male_6", sounds="garret4", weapon="booblord_spin")
    assert [r.clip for r in rows] == _played(game[CONFIG])[1]
    body, drawn = _body(characters_xbr, config, "town_male_6"), _drawn(game[CONFIG])
    spun = [r for r in rows if r.clip.startswith("v/")]
    assert len(spun) == 19 and {r.clip for r in spun} == {"v/spin", "v/twirl", "v/hspin", "v/stomp"}
    assert [(r.windows, r.x3, r.ground) for r in spun] == [
        (pc.damage_windows(game[CHARACTERS], body, r.clip, drawn), False, False) for r in spun]


def _holds_its_prop(xbe: bytes, built: bytes, body: str, characters_xbr: bytes, columns: list[str], played: list[str],
                    lo, drawn: float, baked: str = BAKED_DIR) -> None:
    """X3's row in each column a held prop swings garret4's clip in is the box around the prop through his window
    (Modkit's Step 2.195b, D767): his window, at least his own box's height (x k and the drawn scale), and the
    prop's tip carrier inside it (1 cm) at each key of its track in the window, his casts aside."""
    at = _boxes(xbe)
    garret4, rig = read_body(characters_xbr, "garret4"), Rig.read(built, body)
    tip = [b.name for b in rig.bones].index((lo.prop.own_carriers if lo.carry == pw.IN_PLACE else lo.prop.carriers)[0])
    held = 0
    for i, (col, clip) in enumerate(zip(columns, played)):
        w = garret4_window(characters_xbr, garret4, clip)
        if col == pc.ROLL or w is None or clip in pw.PROP_CASTS:
            continue
        box = BOX.unpack_from(xbe, at + BOX.size * i)
        low = [c - e / 2 for c, e in zip(box[2:5], box[5:8])]
        high = [c + e / 2 for c, e in zip(box[2:5], box[5:8])]
        assert box[:2] == pytest.approx((w.on / garret4.length(clip), w.off / garret4.length(clip)), abs=1e-6), col
        assert low[2] <= drawn * lo.k * w.low[2] + 1e-5 and high[2] >= drawn * lo.k * w.high[2] - 1e-5, col
        motion = named_clip(built, body, baked + clip)
        times = sorted({key[0] for tr in motion.bones if tr.target == tip for key in tr.keys if w.on <= key[0] <= w.off}
                       ) or [w.on + (w.off - w.on) * s / 8 for s in range(9)]   # on his chain: rigid, exact
        for t in times:
            p = origins(rig, motion, t)[tip]
            assert all(a - 0.01 <= drawn * c <= b + 0.01 for a, b, c in zip(low, high, p)), (col, t)
        held += 1
    assert held


@pytest.mark.parametrize("species, basic1, beam", [("town_male_6", (0.91, 2.13, 3.10, 1.30), 7.19),
                                                   ("town_child_1", (0.74, 1.71, 2.40, 0.87), 4.79),
                                                   ("garret4", (0.79, 2.76, 2.76, 1.13), 6.25)])
def test_each_weapon_reaches_by_what_it_is_bare_hands_short_staff_medium_hoe_long_magic_ranged(usa_iso, species,
                                                                                               basic1, beam):
    """D767 (the owner: "tune each weapon"; D763: range variance): each X3 box is the weapon's own at the body's
    size, the listing's, which the build installs: the staff's and the hoe's the box around the prop through
    garret4's window, the magic's Balthazar's own boxes. Basic1's reaches ahead of the feet (bare hands, staff, hoe,
    magic) and the magic's beam (basic3) are the table's, the beam past any swing of the staff or the hoe; the hoe
    reaches no shorter than the staff in any column, and the back kick (back2) keeps his box past W19's contact
    front behind the feet (Modkit's Step 2.195b)."""
    characters_xbr, config = _vanilla(usa_iso, CHARACTERS), _vanilla(usa_iso, CONFIG)
    far, behind = {}, {}
    rates = _doc(config).keyed_section("attacks_anims")

    def sent(r, i):   # AZ-766: garret4's own staff boxes in the frame the game sends X3's from
        return r.windows if r.x3 or species != "garret4" else tuple(pc.sent_window(
            characters_xbr, "garret4", r.clip, rates.find_cell(r.column, "Rate", i).double_value, w) for w in r.windows)
    for weapon in ("bare_hands", "axion_staff", "farmers_hoe", "balthazar_magic"):
        rows = pc.attacks(config, characters_xbr, species, weapon=weapon)
        far[weapon] = {r.column: max(w.forward for w in sent(r, i)) for i, r in enumerate(rows) if r.windows}
        behind[weapon] = {r.column: -min(w.low[1] for w in r.windows) for r in rows if r.windows}
    assert [far[w]["basic1"] for w in far] == pytest.approx(basic1, abs=0.01)
    assert far["balthazar_magic"]["basic3"] == pytest.approx(beam, abs=0.01)
    assert basic1[0] < basic1[1] <= basic1[2] and max(
        f for w in ("axion_staff", "farmers_hoe") for c, f in far[w].items() if c not in pc.CASTS) < beam
    assert all(far["farmers_hoe"][c] >= f for c, f in far["axion_staff"].items()), species
    drawn = 1.0 if species == "garret4" else 1.15
    assert min(behind[w]["back2"] for w in ("axion_staff", "farmers_hoe")) > pc.PLAYER_RADIUS * drawn


def test_the_attack_listing_and_the_logic_put_a_lunges_box_where_the_game_sends_it(usa_iso):
    """AZ-766 (Modkit's Steps 2.198, 2.197b): the game places a lunge's box from the drawn origin, kept back from
    the body by the clip's m_feet, so the listing's far face straight ahead is the farthest box the game sent at
    Step 2.195b's record sitting (the townsman with the staff and with the hoe, garret4 with the hoe) and at Step
    2.197b's read of garret4's own staff; the logic's melee reach reads them so (his sweep2 a melee box 1.93 m
    ahead, where the 4.13 m its clip holds put it past the melee line)."""
    characters_xbr, config = _vanilla(usa_iso, CHARACTERS), _vanilla(usa_iso, CONFIG)
    seen_far = {("town_male_6", "axion_staff"): {"basic1": 2.131, "basic2": 2.028, "basic3": 2.461, "finish": 2.731,
                                                 "sweep1": 2.113},
                ("town_male_6", "farmers_hoe"): {"basic1": 3.098, "basic2": 2.150, "basic3": 3.407, "finish": 3.696,
                                                 "sweep1": 3.065},
                ("garret4", "farmers_hoe"): {"basic1": 2.759, "basic2": 2.817, "basic3": 2.980, "finish": 3.104,
                                             "sweep1": 2.707},
                ("garret4", None): {"basic1": 2.759, "basic2": 2.737, "basic3": 2.322, "finish": 2.466, "sweep2": 1.930}}
    for (species, weapon), far in seen_far.items():
        rows = {r.column: r for r in pc.attacks(config, characters_xbr, species, weapon=weapon)}
        assert {c: max(w.forward for w in rows[c].windows) for c in far} == pytest.approx(far, abs=0.002), \
            (species, weapon)
    anims = _doc(config).keyed_section("attacks_anims")
    columns = anims.col_names()
    clips = [anims.find_cell(c, "Anim", i).string_value for i, c in enumerate(columns)]
    rates = [anims.find_cell(c, "Rate", i).double_value for i, c in enumerate(columns)]
    garret4 = read_body(characters_xbr, "garret4")
    assert [pc.melee_reach(characters_xbr, garret4, columns, clips, 1.0, 0, 0.0, only=("sweep2",), ahead=True, rates=r)
            for r in (None, rates)] == [None, pytest.approx(1.930, abs=0.002)]


def _bound(fx: bytes, names: tuple[str, ...]) -> int:
    """How many transforms of ``fx``'s graphs bind one of ``names``."""
    return sum(bind_name(fx, rec) in names for e in parse_toc(fx) if e.tag == "node"
               for rec in record_offsets(fx, e.file_offset) if rec is not None)


def _worn(built: bytes, body: str) -> str:
    """The body the player binds in ``built``: P2's copy of ``body`` (Step 2.203), where the build made one."""
    key = paint.skin_key(body)
    return key[len("characters/"):] if any(n.casefold() == key for n in named_resources(built).values()) else body


def _blades(fx: bytes) -> dict:
    """Each staff graph's Blade transforms under its ends, by (graph, end, name): their scale."""
    out = {}
    for g, ends, name in power._graphs(fx):
        kids = power._children(g)
        out |= {(name, bind, g.names[c]): g.xform_fields(c)["s"] for bind, e in ends.items() for c in kids[e]
                if (g.names[c] or "").startswith("Blade")}
    return out


PICKED = [("town_male_6", "axion_staff"), ("keylord", "axion_staff"), ("town_male_farmer_1", "axion_staff"),
          ("town_female_1", "farmers_hoe"), ("balthazar", "farmers_hoe"), ("town_child_1", "farmers_hoe"),
          ("keylord", "bare_hands"), ("balthazar", "bare_hands"), ("town_male_farmer_1", "bare_hands"),
          ("town_male_6", "balthazar_magic"), ("keylord", "balthazar_magic"), ("fire_elemental", "balthazar_magic")]
MAGIC = ("m_lifedrain", "m_lifedrainswitch", "m_balth_lightning", "m_balth_lightningswitch", "m_activateFireStaff",
         "m_activateFireStaffswitch", "m_dying")
"""Balthazar's markers his fx_default binds (M1), the first, third and fifth his effects hang under (S6)."""


@pytest.mark.parametrize("species, weapon", PICKED)
def test_a_picked_weapon_dresses_a_mapped_body_with_its_prop_and_style(usa, species, weapon):
    """A weapon picked for a body the bake maps (Modkit's Steps 2.161b, 2.161c; D492-D495), three bodies each: its
    style plays every attack column (the staff's garret4's attacks baked as g4/, the kit's clips as t/, the magic's
    Balthazar's as b/); its prop rides two carriers appended under the bone playing garret4's right hand, the tip
    keyed where his staff's tip rides, x k from the wearer's hand (the hoe's +y along his staff, the staff's tip
    turned as his m_stafftop, AZ-693), its mesh in every LOD the body draws skinned to the tip alone x k, its
    material a copy; X3's rows the box around the prop in his windows; the staff's fx bind its ends by name,
    unhidden, the hoe's its carriers; X17 off; a farmer's own hoe at scale 0 (W33); the logic's reach a box ahead
    of the feet, bare hands' under half garret4's (their idle swings' boxes). The magic: his markers grown (M1), those
    his effects hang under keyed as his (S6), the player's clone of his graph bound to the body (X40), X37 drains in
    the columns playing b/attack_2."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    body = _body(characters_xbr, config, species)
    lo = loadout(characters_xbr, read_body(characters_xbr, body), "own", True, None, weapon)
    logic = pc.AttackLogic()
    game = _swap(usa, species, sounds="garret4", weapon=weapon, logic=logic)
    built, xbe = game[CHARACTERS], game[XBE]
    columns, played = _played(game[CONFIG])
    rig = Rig.read(built, body)
    names = [b.name for b in rig.bones]
    assert logic.reach < GARRET4_FORWARD / 2 if weapon == "bare_hands" else logic.reach > 0.0
    if weapon == "bare_hands":   # X3's far face in each kit column (L2), m ahead of the feet
        kit, drawn, far = kit_document(), _drawn(game[CONFIG]), {}
        for col in ("basic1", "basic2", "sweep1"):
            clip = kit["clips"][kit["columns"][col]]
            (length, _), box = _x3_tick(xbe, columns.index(col), (sum(clip["hit"]) / 2 / clip["ticks"] - 0.1) / 0.8,
                                        scale=drawn)
            far[col] = drawn * (box[1] + box[4] * length)
        assert logic.reach == pytest.approx(max(far["basic1"], far["sweep1"]), abs=1e-3), far
    if species.startswith("town_male_farmer"):   # W33: its own hoe skinned to joint74, at scale 0
        j74 = names.index("joint74")
        assert rig.bones[j74].s == (0.0, 0.0, 0.0)
        assert sum(g.palette == [j74] for g in read_asset(built, body).lods[0].groups) == 1
    if weapon == "balthazar_magic":
        his = read_body(characters_xbr, "balthazar_airship")
        assert [p for col, p in zip(columns, played) if col != pc.ROLL] == [
            "b/" + c for col, c in zip(columns, pc.substitutes(columns, his, True)) if col != pc.ROLL]
        mine, theirs = read_body(built, body, dirs=("b/",)), Rig.read(characters_xbr, "balthazar_airship")
        assert set(MAGIC) <= set(mine.markers)
        for clip in ("attack_2", "attack_3"):
            built_clip, his_clip = named_clip(built, body, "b/" + clip), named_clip(characters_xbr, "balthazar_airship",
                                                                                     clip)
            for name in MAGIC[1:7:2]:
                assert ({tr.comp: tr.keys for tr in built_clip.markers if tr.target == rig.markers.index(name)}
                        == {tr.comp: tr.keys for tr in his_clip.markers if tr.target == theirs.markers.index(name)})
        key = fx_edit.clone_key(body)
        clone = next(e for e in parse_toc(built) if named_resources(built).get(e.index, "").casefold() == key)
        bound = {bind_name(built, rec) for rec in record_offsets(built, clone.file_offset)
                 if rec is not None and lstr(built, rec) == "transform"} - {None}
        dead = bound - set(his.markers) - {n for n, _ in his.bones}   # binds his own body lacks too
        assert bound - dead <= set(mine.markers) | set(names) and dead
        assert any(r.key.casefold() == key for r in parse_index_xbr(game[INDEX]).records)
        hook = ports.resolve_va_to_file(xbe, pc.FX_DEFAULT_HOOK_VA)
        assert xbe[hook:hook + 5] != pc._FX_DEFAULT_VANILLA   # X40
        assert pc.field_switches(built, body) == {"m_lifedrainswitch"}
        assert pc.drain_columns(columns, played, pc.self_drains(built, mine)) == sum(
            1 << i for i, p in enumerate(played) if p == "b/attack_2") != 0
        assert lo.prop is None and lo.picked
        return
    if lo.kit is not None:
        kit = kit_document()
        assert [p for col, p in zip(columns, played) if col != pc.ROLL] == [
            "t/" + kit["columns"][col] for col in columns if col != pc.ROLL]
        assert lo.prop is None and lo.picked
        return
    vanilla = _doc(config).keyed_section("attacks_anims")
    assert played == [vanilla.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    assert all(named_clip(built, body, BAKED_DIR + clip) for col, clip in zip(columns, played) if col != pc.ROLL)
    prop = weapons()[weapon].prop
    tip, end = (names.index(n) for n in prop.carriers)
    grip = names.index(lo.grip)
    assert (rig.bones[tip].parent, rig.bones[end].parent, tip, end) == (grip, tip, len(names) - 2, len(names) - 1)
    g4, style = Rig.read(characters_xbr, "garret4"), weapons()[weapon].style
    _, top, bottom, _, _ = _staff_hold(characters_xbr, style, prop.over)
    hand = [b.name for b in g4.bones].index(style.hand)
    for clip in ("attack_1", "attack_14"):
        mine, his = named_clip(built, body, BAKED_DIR + clip), named_clip(characters_xbr, "garret4", clip)
        if clip in lo.turns:   # W35 (Step 2.161g): its arms turned after its tip was keyed; turned back here
            mine = turned(rig, mine, {k: qinv(q) for k, q in arm_turns(rig, *lo.turns[clip]).items()})
        assert {tr.comp for tr in mine.bones if tr.target == tip} == set(range(7))
        for t in sorted({key[0] for tr in mine.bones if tr.target == tip for key in tr.keys})[::4]:
            at, theirs = origins(rig, mine, t), origins(g4, his, t)
            axis = [a - b for a, b in zip(theirs[top], theirs[bottom])]
            axis = [c / math.sqrt(sum(a * a for a in axis)) for c in axis]
            want = [lo.k * (a + prop.over * c - h) for a, c, h in zip(theirs[top], axis, theirs[hand])]
            turn = pose(rig, mine, t)[tip]
            if prop.mesh.loose:   # the hoe's +y along his staff
                cos = sum(a * b for a, b in zip(_turn(turn, (0.0, 1.0, 0.0)), axis))
            else:                 # the staff's tip turned as his m_stafftop (AZ-693)
                cos = math.cos(2 * math.acos(min(1.0, abs(sum(a * b for a, b in zip(turn, pose(g4, his, t)[top]))))))
            if math.degrees(math.acos(min(1.0, cos))) >= 0.5 and prop.over > 0.0:   # W41 through a crossfade
                fade = (8 + 90 / pw.FADE_SLEW + 2) / 30   # (Step 2.207c): its turn over a clip's start or end only
                assert t <= fade or t >= mine.length - max(0.25, 1.5 * 90 / pw.FADE_SLEW / 30), (clip, t)
                continue
            assert math.dist([c - h for c, h in zip(at[tip], at[grip])], want) < 2e-3, (clip, t)
            assert math.degrees(math.acos(min(1.0, cos))) < 0.5, (clip, t)
    verts, _, (gshd, _), _ = _donor(characters_xbr, prop)
    toc, old = parse_toc(built), len(parse_toc(characters_xbr))
    m = pc.inverse_binds(built, body)[tip]
    origin = [-sum(m[12 + j] * m[4 * i + j] for j in range(3)) for i in range(3)]   # the tip's bind origin
    longest = max(math.dist(p, (0.0, 0.0, 0.0)) for p, _, _, _ in verts)
    donor = parse_toc(characters_xbr)
    theirs = sorted(hashlib.sha256(characters_xbr[donor[t].file_offset:donor[t].file_offset + donor[t].size]).hexdigest()
                    for o, t in refs_in(characters_xbr, donor, gshd) if donor[t].tag == "surf")
    for lod in read_asset(built, _worn(built, body)).lods:   # W32, every LOD, x k, its material copied
        group = lod.groups[-1]
        assert (group.palette, len(group.vertices)) == ([tip], len(verts))
        assert max(math.dist(v.position, origin) for v in group.vertices) == pytest.approx(lo.k * longest, rel=1e-4)
        copied, copied_row = group.material
        assert (copied >= old, copied_row, toc[copied].tag) == (True, 0, "gshd")
        assert struct.unpack_from("<I", built, toc[copied].file_offset)[0] == 1
        targets = [t for _, t in refs_in(built, toc, copied)]
        assert targets and all(t >= old for t in targets)
        surfs = [t for t in targets if toc[t].tag == "surf"]
        mine = sorted(hashlib.sha256(built[toc[t].file_offset:toc[t].file_offset + toc[t].size]).hexdigest()
                      for t in surfs)
        assert surfs and set(mine) <= set(theirs)
    _holds_its_prop(xbe, built, body, characters_xbr, columns, played, lo, _drawn(game[CONFIG]))
    fx = game[FX]
    staff = pc.staff_scales(fx)
    if prop.ends == "native":
        assert len(staff) == 60 and all(fx[o:o + 12] == pc._SHOWN for o in staff)
    else:
        assert (staff, _bound(fx, prop.carriers) > 0) == ([], True)
    off, _, patch = ports.patch_spec_site(xbe, pc.STAFF_WALLS)
    assert xbe[off:off + len(patch)] == patch


def test_balthazars_magic_on_a_smaller_or_larger_body_births_his_effects_k_times_his_gap_from_its_hand(usa):
    """AZ-691 (Modkit's Step 2.202): S6 kept Balthazar-sized gaps between the grip and his graph's emitters on a
    smaller or larger wearer (keylord's stream 0.5 m, his bolts 1.0-1.8 m off his claw). Each marker his effects
    hang under is keyed every tick at the wearer's grip plus k x its offset from his left_w, less (1 - k) x its bound
    transform's scale pivot, its extents k x his (k the wearer's height over his: keylord 0.519, the golem 1.596),
    so his stream's emitter, his bolts' burst and his drain's pull and box sink are born k x his gap from the hand
    at every tick his switch is on (2 mm)."""
    characters_xbr = _vanilla(usa, CHARACTERS)
    his = Rig.read(characters_xbr, "balthazar_airship")
    hg = [b.name for b in his.bones].index("left_w")
    toc = parse_toc(characters_xbr)
    keys = {n.casefold(): i for i, n in named_resources(characters_xbr).items()}
    g = Graph(characters_xbr, toc, toc[keys["characters/balthazar_airship/fx/fx_default"]], Schema(_vanilla(usa, XBE)))
    rest = dict(marker_records(characters_xbr, "balthazar_airship"))
    for species, body in (("keylord", "keylord"), ("golem", "golem")):
        built = _swap(usa, species, sounds="garret4", weapon="balthazar_magic")[CHARACTERS]
        k = height(characters_xbr, read_body(characters_xbr, body)) / height(characters_xbr, read_body(
            characters_xbr, "balthazar_airship"))
        mine = Rig.read(built, body)
        mg = [b.name for b in mine.bones].index(pw.grip(built, read_body(built, body)))
        mrest = dict(marker_records(built, body))
        for clip, marker, switch, shapes in (("attack_3", "m_balth_lightning", "m_balth_lightningswitch", (17, 24)),
                                             ("attack_2", "m_lifedrain", "m_lifedrainswitch", (8, 10))):
            top = next(r for r, ro in enumerate(g.recs) if ro is not None and g.types[r] == "transform"
                       and bind_name(g.s, ro) == marker)
            sp = g.xform_fields(top)["sp"]
            pts = []
            for rec in shapes:   # each shape's place under the bound transform (its own matrix the marker's)
                m = IDENTITY
                for a in [a for a in reversed(g.ancestors(rec)) if a != top and top in g.ancestors(a)]:
                    m = mat_mul(m, g.local(a)[0])
                pts.append(apply(m, [g.attr_named(rec, f"localPosition{ax}") for ax in "XYZ"]
                                 if rec != 10 else [0.0, 0.0, 0.0]))
            built_clip, his_clip = named_clip(built, body, "b/" + clip), named_clip(characters_xbr, "balthazar_airship",
                                                                                     clip)

            def placed(c, rig, rec, t):   # the marker's T, R, S at t (its rest where unkeyed): each shape's place
                i = rig.markers.index(marker)
                keyed = {tr.comp: tr.keys for tr in c.markers if tr.target == i}
                v = [evaluate(keyed[x], t) if x in keyed else rec[marker][x] for x in range(10)]
                q = qnorm(tuple(v[3:7]))
                return [[v[a] + sp[a] + r for a, r in enumerate(qmul(qmul(q, (*(v[7 + b] * (p[b] - sp[b])
                                                                              for b in range(3)), 0.0)), qinv(q))[:3])]
                        for p in pts]
            on = [i / 30 for i in range(int(his_clip.length * 30) + 1)
                  if evaluate(next(tr.keys for tr in his_clip.markers if tr.target == his.markers.index(switch)
                                   and tr.comp == 2), i / 30) > 0.0]
            assert on
            for t in on:
                ours, theirs = origins(mine, built_clip, t)[mg], origins(his, his_clip, t)[hg]
                for p_mine, p_his in zip(placed(built_clip, mine, mrest, t), placed(his_clip, his, rest, t)):
                    want = [o + k * (x - h) for o, x, h in zip(ours, p_his, theirs)]
                    assert math.dist(p_mine, want) < 2e-3, (species, clip, t)
                    assert math.dist(p_mine, ours) == pytest.approx(k * math.dist(p_his, theirs), abs=2e-3)


@pytest.mark.parametrize("species", ["town_male_6", "keylord"])
def test_a_copied_axion_staff_is_garret4s_staff_on_ends_turned_as_his(usa, species):
    """AZ-693 (Modkit's Steps 2.161f, 2.203): the Axion staff copied onto a body is garret4's: in every LOD one group
    on the copy's m_stafftop, his LOD 0 staff group (its triangles and UVs), its vertices and normals in that
    carrier's bind frame his in his m_stafftop's x k, the copy's m_staffbottom his offset from his top x k at his
    turn (so the fx blades bound to both ends lie along the shaft), every Blade transform under each end x k; its
    material his row (its bytes but the fields the copy relocates, and the textures they name, byte for byte)."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    body = _body(characters_xbr, config, species)
    lo = loadout(characters_xbr, read_body(characters_xbr, body), "own", True, None, "axion_staff")
    game = _swap(usa, species, sounds="garret4", weapon="axion_staff")
    built = game[CHARACTERS]
    his, mine = read_asset(characters_xbr, "garret4"), read_asset(built, _worn(built, body))
    blades, his_blades = _blades(game[FX]), _blades(_vanilla(usa, FX))
    assert len(blades) == len(his_blades) > 0 and all(
        b == pytest.approx(tuple(lo.k * c for c in his_blades[key]), rel=1e-6) for key, b in blades.items())
    own, = [g for g in his.lods[0].groups if g.palette and set(g.palette) <= {his.bone(b) for b in lo.prop.mesh.bones}]
    (top, bottom), (tip, end) = ([a.bone(n) for n in lo.prop.carriers] for a in (his, mine))
    theirs, binds = pc.inverse_binds(characters_xbr, "garret4"), pc.inverse_binds(built, body)

    def local(m, p, w=1.0):   # a model point (w 1) or direction (w 0) in a bone's bind frame (D3D rows)
        return [sum(p[i] * m[4 * i + j] for i in range(3)) + w * m[12 + j] for j in range(3)]

    def origin(m):
        return [-sum(m[12 + j] * m[4 * i + j] for j in range(3)) for i in range(3)]

    def turn(a, b):   # bone b's bind frame in bone a's
        return [sum(a[4 * k + i] * b[4 * k + j] for k in range(3)) for i in range(3) for j in range(3)]

    def faces(g):   # its triangles, each from its least vertex (the write re-strips them)
        return sorted(t[t.index(min(t)):] + t[:t.index(min(t))] for t in g.triangles)
    for lod in mine.lods:
        group, = [g for g in lod.groups if g.palette == [tip]]
        assert (faces(group), [v.uv for v in group.vertices]) == (faces(own), [v.uv for v in own.vertices])
        for v, u in zip(group.vertices, own.vertices):
            assert math.dist([c / lo.k for c in local(binds[tip], v.position)], local(theirs[top], u.position)) < 1e-4
            assert math.dist(local(binds[tip], v.normal, 0.0), local(theirs[top], u.normal, 0.0)) < 1e-3
    assert math.dist([c / lo.k for c in local(binds[tip], origin(binds[end]))],
                     local(theirs[top], origin(theirs[bottom]))) < 1e-4
    assert max(abs(a - b) for a, b in zip(turn(binds[tip], binds[end]), turn(theirs[top], theirs[bottom]))) < 1e-4

    def row(data: bytes, gshd: int, n: int) -> tuple[str, list[str]]:   # a material row's bytes, its fields' targets
        toc = parse_toc(data)
        e = toc[gshd]
        table = e.file_offset + 4 + struct.unpack_from("<i", data, e.file_offset + 4)[0]
        start = table + 4 * n + struct.unpack_from("<i", data, table + 4 * n)[0]
        size = 100 + 124 * struct.unpack_from("<I", data, start + 96)[0]
        cells, named = bytearray(data[start:start + size]), []
        for off, t in sorted(refs_in(data, toc, gshd)):
            if start <= e.file_offset + off < start + size:
                cells[e.file_offset + off - start:e.file_offset + off - start + 4] = bytes(4)
                blob = data[toc[t].file_offset:toc[t].file_offset + toc[t].size]
                named.append(toc[t].tag + " " + hashlib.sha256(blob).hexdigest()[:12])
        return hashlib.sha256(cells).hexdigest()[:12], named
    assert row(built, *group.material) == row(characters_xbr, *own.material)


@pytest.mark.parametrize("species, placed", [("town_male_6", True), ("town_male_farmer_1", False)])
def test_a_picked_prop_is_the_players_alone_where_a_level_places_its_body(usa, species, placed):
    """P2 (Modkit's Step 2.203, D543): a picked prop goes into W38's copy of the body, characters/<body>/v/skin, which
    X47 binds for the player alone, and every entry the vanilla body reaches is vanilla's again but the body's record
    (its LODs and vanilla bones and markers vanilla's, the carriers and B's markers appended): town places
    town_male_6, whose NPCs keep their body while the player's copy holds the staff in every LOD. No level places
    town_male_farmer_1, so its build makes no copy."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    body = _body(characters_xbr, config, species)
    game = _swap(usa, species, sounds="garret4", weapon="axion_staff")
    built, xbe, key = game[CHARACTERS], game[XBE], paint.skin_key(body)
    assert [n.casefold() for n in named_resources(built).values() if n.casefold() == key] == [key] * placed
    assert [r.fourcc for r in parse_index_xbr(game[INDEX]).records if r.key == key] == ["body"] * placed
    assert xbe[ports.resolve_va_to_file(xbe, pc.BODY_KEY_HOOK_VA)] == (0xE8 if placed else 0x68)   # X47, or the push
    vanilla, npc = read_asset(characters_xbr, body), read_asset(built, body)
    mine = read_asset(built, _worn(built, body))
    assert [len(lod.groups) for lod in mine.lods] == [len(lod.groups) + 1 for lod in vanilla.lods]   # W32's staff
    assert ([b.name for b in npc.bones[len(vanilla.bones):]], len(npc.markers) > len(vanilla.markers)) == (
        list(weapons()["axion_staff"].prop.carriers), True)
    if not placed:
        assert npc.index == mine.index
        return
    vtoc, toc = parse_toc(characters_xbr), parse_toc(built)

    def sha(data, t, i) -> str:
        return hashlib.sha256(data[t[i].file_offset:t[i].file_offset + t[i].size]).hexdigest()
    reach = [i for i in closure(characters_xbr, [vanilla.index]) if i != vanilla.index]
    assert [sha(built, toc, i) for i in reach] == [sha(characters_xbr, vtoc, i) for i in reach]
    assert [lod.bmsh for lod in npc.lods] == [lod.bmsh for lod in vanilla.lods]
    assert [(b.name, b.record[8:]) for b in npc.bones[:len(vanilla.bones)]] == [
        (b.name, b.record[8:]) for b in vanilla.bones]
    assert [(m.name, m.record[8:]) for m in npc.markers[:len(vanilla.markers)]] == [
        (m.name, m.record[8:]) for m in vanilla.markers]
    assert ([b.name for b in mine.bones], [m.name for m in mine.markers]) == (
        [b.name for b in npc.bones], [m.name for m in npc.markers])


def test_a_weapon_a_body_cant_take_fails_by_name(usa):
    """A build refuses by name, naming the weapon, the body and why (D35; Modkit's Steps 2.161b, 2.161c, 2.161e,
    2.167b): a name no weapon has; ``own`` on a body with no attack clip; a prop worn by a variant whose recipe has
    jiggle bones (W31 appends the carriers after X41 reads the bones); Balthazar's magic worn by a variant whose
    recipe edits the body's fx (X40 binds one clone). In Skin a weapon with no prop, given or a recipe's, is the
    body's default (S7), no refusal. A recipe's projectile row and its weapon style's are one row a build: two that
    differ are refused, the same one taken once."""
    characters_xbr = _vanilla(usa, CHARACTERS)
    with pytest.raises(ValueError, match=re.escape("--player-weapon sword: no such weapon (one of default, ")):
        _swap(usa, "keylord", weapon="sword")
    for body, weapon, said in (
            ("townspeople/male_6", "own", "--player-weapon own: townspeople/male_6 has no attack clip of its own"),
            ("keylord", "staff", "--player-weapon staff: no such weapon")):
        with pytest.raises(ValueError, match=re.escape(said)):
            loadout(characters_xbr, read_body(characters_xbr, body), "own", True, None, weapon)
    with pytest.raises(ValueError, match=re.escape("on catalisk: its Farmer's hoe is carried on bones appended after "
                                                   "X41 reads the body's")):
        loadout(characters_xbr, read_body(characters_xbr, "catalisk"), "own", True,
                SimpleNamespace(weapon=None, jiggle={"bones": {}}), "farmers_hoe")
    recipe = SimpleNamespace(weapon="bare_hands")
    for body, variant, weapon, built in (("keylord", None, "bare_hands", ("own", False, None)),
                                         ("keylord", recipe, None, ("own", False, None)),
                                         ("townspeople/male_farmer_1", recipe, "bare_hands",
                                          ("farmers_hoe", False, "in_place"))):
        skin = loadout(characters_xbr, read_body(characters_xbr, body), "garret4", True, variant, weapon)
        assert (skin.name, skin.picked, skin.carry) == built, body
    mage, = load_variants(json.dumps({"mage": {"title": "a keylord mage", "base": "keylord", "weapon": "balthazar_magic",
                                               "fx": [{"record": 0, "name": "x", "type": "transform",
                                                       "set": {"scaleX": 1.0}}]}}), "test").values()
    with pytest.raises(ValueError, match=re.escape("its weapon balthazar_magic plays balthazar_airship's graph on the "
                                                   "player's clone (W34), and its recipe's fx edit")):
        _swap(usa, "mage", worn=mage)
    firer, = load_variants(json.dumps({"firer": {"base": "keylord", "effects": [
        {"template": "fireball", "columns": ["basic1"]}]}}), "test").values()
    magic = weapons()["balthazar_magic"]
    arrows = replace(magic.style, effects=fx_templates.effects("x", [{"template": "arrow", "columns": ["basic2"]}]))
    with pytest.raises(ValueError, match=re.escape("its recipe throws fireball on basic1 and its weapon balthazar_magic's "
                                                   "style balthazar arrow on basic2: X42 throws one species")):
        pc.projectile_row(firer, SimpleNamespace(weapon=replace(magic, style=arrows)), "firer")
    same = replace(magic, style=replace(magic.style, effects=firer.effects))
    assert pc.projectile_row(firer, SimpleNamespace(weapon=same), "firer") is firer.effects[0]


def test_every_body_takes_every_weapon_and_one_with_no_attack_clip_casts_and_aims_in_what_its_columns_play(
        usa, tmp_path, monkeypatch):
    """Every weapon is offered on every body in both modes and none refused (Modkit's Step 2.204; D809, D810): a
    prop-less one in Skin, bare hands on a body the bake doesn't map and Booblord spin on a body with no clips build
    the default, each saying why; Balthazar's magic casts from a body's root where weapons.json has no grip row, and
    on a body with no attack clip in what its attack columns play, his switch on over X3's 20-50%: a flicken's k/
    copy of its ouch_1 (its hit plays the clip as it was), a gem's of its idle (its roll the idle as it was), a
    clipless frag's garret4's timers, X37 aiming his beam's bolts in each attack column. A pick no sitting saw is
    coloured by its fit, no better than the model's grade, "not seen in game"; the Weapon box (Modkit's
    ``player-models --weapons``) lists every weapon for the flicken, a default uncoloured."""
    from azurkit import sdk
    from azurkit.tools.characters import content

    characters_xbr = _vanilla(usa, CHARACTERS)
    for body in ("flicken", "diamond", "frag_air_1", "catalisk", "townspeople/male_6", "garret4"):
        for mode in pc.MODES:
            fits = offers(characters_xbr, read_body(characters_xbr, body), mode)
            assert set(weapons()) <= set(fits) and "refused" not in {fit for fit, _ in fits.values()}, (body, mode)
    same = "the default's build: "
    assert [offers(characters_xbr, read_body(characters_xbr, body), mode)[weapon] for body, mode, weapon in (
        ("flicken", "garret4", "balthazar_magic"), ("flicken", "own", "bare_hands"),
        ("frag_air_1", "own", "booblord_spin"))] == [
        ("same", same + "Skin takes only a weapon's prop"), ("same", same + "its own attacks are its bare hands"),
        ("same", same + "a body with no clips plays garret4's moves in every column")]
    gem = loadout(characters_xbr, read_body(characters_xbr, "diamond"), "own", True, None, "balthazar_magic")
    assert (gem.grip, gem.fit, gem.cast is not None) == ("joint1", "odd", True)
    for species, cast in (("flicken", pc.CAST_DIR + "0"), ("diamond", pc.CAST_DIR + "0"),
                          ("frag_air_1", BAKED_DIR + "attack_1")):
        game = _swap(usa, species, weapon="balthazar_magic")
        built = game[CHARACTERS]
        columns, picks = _played(game[CONFIG])
        played = {p for col, p in zip(columns, picks) if col != pc.ROLL}
        assert not picks[columns.index(pc.ROLL)].startswith(pc.CAST_DIR), species   # a roll never casts
        beams = round(_param(game[XBE], pc.DRAIN_HOOKS[1], "_player_model_drain_beams"))
        assert beams == sum(1 << i for i, col in enumerate(columns) if col != pc.ROLL), species
        clip = named_clip(built, species, cast)
        switch = {(tr.target, tr.comp): tr.keys for tr in clip.markers}[
            Rig.read(built, species).markers.index(pc.CAST_SWITCH), 2]
        lit = [t / 100 for t in range(101) if evaluate(switch, t / 100 * clip.length) >= 0.5]
        assert (lit[0], lit[-1]) == (pytest.approx(0.2, abs=0.02), pytest.approx(0.5, abs=0.02)), species
        if species == "flicken":   # its columns play the copy, its hit the clip as it was
            assert played == {cast} and named_clip(built, species, "ouch_1") == named_clip(characters_xbr, species,
                                                                                           "ouch_1")
    for fit, own, colour in (("odd", ("green", ""), "yellow"), ("odd", ("red", ""), "red"),
                             (GOOD, ("unseen", ""), "green")):
        graded = pick_grade("diamond", "own", "balthazar_magic", True, "diamond", fit, own)   # no sitting saw it
        assert (graded[0], graded[1].startswith(pw.NOT_SEEN)) == (colour, True), (fit, own)
    monkeypatch.setattr(content, "ROOT", tmp_path / "content")
    rows = sdk.pickers({"iso": str(usa), "character": {"species": "flicken"}})["chosen"]["weapons"]
    assert {p["name"] for p in rows[1:]} | {rows[0]["shows"]} - {None} == set(weapons())
    assert all((p["colour"] is None) is (p["fit"] in ("default", "same")) and (
        p["colour"] in (None, *picker.STATUS_COLOURS.values())) for p in rows[1:])


def test_a_picked_weapons_grade_is_its_sittings_and_only_for_the_build_it_saw(usa, monkeypatch):
    """Each WEAPON_GRADES key is a pick the build resolves (the species, its mode and the weapon's sha as
    ``loadout`` makes them), so the build's status line reads that grade; the same pick at another size or scale, a
    pick no sitting saw and a body's default don't (D242; Modkit's Steps 2.161b, 2.161b2, 2.161e, 2.161g, 2.204,
    2.209): the status line reads it through ``seen`` (town_child_1's green hoe drawn x2 reads unseen); a variant
    is the build its sitting saw only built in, at its recipe's scale and attack sliders; a creature's grade is
    keyed by its grips row too (a grip retuned after its sitting reads unseen) and a W35-fitted pair's by its
    turns; a pick no sitting saw is coloured by its fit, "not seen in game"; booblord's spins under her default
    Axion staff are a pick graded as one, keyed by her recipe as AzurKit has it (Step 4.3's vase step changed it,
    and its carry of her looks' grades left these keys)."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    species = pc._species(_doc(config).keyed_section("critters_engine"))
    for (name, mode, weapon, sha), graded in WEAPON_GRADES.items():
        v = builtins().get(name)
        lo = loadout(characters_xbr, read_body(characters_xbr, species[v.base if v else name]["body"]), mode, True, v,
                     weapon)
        turns = pw.fit_turns(lo.body, v, lo.weapon)
        assert (lo.name, pick_sha(lo.weapon, lo.body, turns), grade(name, mode, lo)) == (weapon, sha, graded), name
        unseen = grade(name, mode, lo, built=False)   # by its fit, not seen in game
        assert unseen[0] == pw.FIT_COLOURS[lo.fit] and unseen[1].startswith(pw.NOT_SEEN), name
    assert {c for c, _ in WEAPON_GRADES.values()} == {"green", "yellow", "red"}   # red: frag_fire_1's, its model's
    body = read_body(characters_xbr, species["town_male_6"]["body"])
    her = read_body(characters_xbr, species["town_female_1"]["body"])
    assert grade("town_female_1", "own", loadout(characters_xbr, her, "own", True, None, "farmers_hoe"))[0] == "green"
    assert grade("town_male_6", "own", loadout(characters_xbr, body, "own", True, None, "bare_hands")) is None
    catalisk = loadout(characters_xbr, read_body(characters_xbr, "catalisk"), "own", True, None, "farmers_hoe")
    monkeypatch.setitem(WEAPON_GRADES, ("catalisk", "own", "farmers_hoe", pick_sha(catalisk.weapon, "catalisk")),
                        ("green", "seen"))
    assert grade("catalisk", "own", catalisk) == ("green", "seen")
    monkeypatch.setitem(grips(), "catalisk", replace(grips()["catalisk"], offset=(0.0, 0.0, 0.1)))
    assert grade("catalisk", "own", catalisk)[0] == "yellow"   # look + tip hits
    monkeypatch.undo()
    lines = []
    _swap(usa, "town_child_1", weapon="farmers_hoe", scale=2.0, lines=lines)
    assert lines[-1] == ("  Player model status: green "
                         f"({pick_grade('town_child_1', 'own', 'farmers_hoe', False, fit=GOOD)[1]})")
    beamlord = builtins()["beamlord"]
    assert [seen("own", 1.0), seen("garret4", 1.0), seen("own", 2.0)] == [True, False, False]
    assert [seen("own", scale, v, sliders) for v, scale, sliders in (
        (beamlord, beamlord.scale, None), (beamlord, beamlord.scale, (beamlord.reach, beamlord.damage, beamlord.speed)),
        (beamlord, 2 * beamlord.scale, None), (beamlord, beamlord.scale, (2.0, beamlord.damage, beamlord.speed)),
        (replace(beamlord, source="saved/recipe.json"), beamlord.scale, None))] == [True, True, False, False, False]


def _attack_lookup(xbe: bytes, body: str, keys: dict[str, int], name: str, flags: int) -> int:
    """The handle the attacks_anims loader's lookup (its CALL at 0x7E3F0, X12's or X44's hook in ``xbe``) gives a
    column naming ``name`` for a species of ``body`` with ``flags`` (0x20: the player's), the asset registry 0xA5CA0
    stubbed by name with ``keys`` and its formatter 0x178C0 and sound binding 0x4B680, 0xEB1B5 stubbed (L2); -1
    for none."""
    target = 0x7E3F5 + struct.unpack_from("<i", xbe, ports.va_to_file(0x7E3F0) + 1)[0]
    sim, base = l2.Sim(xbe), 0x20000000
    sim.uc.mem_map(base, 0x10000)
    sim.uc.mem_write(base + 0x800, body.encode() + b"\0")
    sim.uc.mem_write(base + 0x900, name.encode() + b"\0")
    sim.uc.mem_write(base + 4, struct.pack("<I", base + 0x800))
    sim.uc.mem_write(base + 0x64, struct.pack("<I", flags))

    def returns(pop: int, eax=None):
        def hook(uc, addr, size, _):
            esp = sim.reg("esp")
            if eax is not None:
                uc.reg_write(UC_X86_REG_EAX, eax(esp) & 0xFFFFFFFF)
            uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
        return hook

    def fmt(esp: int) -> int:   # 0x178C0: ESI := the format with two strings
        text = sim.cstr(sim.u32(esp + 4)) % (sim.cstr(sim.u32(esp + 8)), sim.cstr(sim.u32(esp + 12)))
        sim.uc.mem_write(sim.reg("esi"), text.encode() + b"\0")
        return 0
    for va, hook in ((0xEB1B5, returns(0)), (0x4B680, returns(8)), (0x178C0, returns(0, fmt)),
                     (0xA5CA0, returns(8, lambda esp: keys.get(sim.cstr(sim.reg("ecx")).casefold(), -1)))):
        sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)
    sim.call(target, regs={"eax": base + 0x900, "edi": base + 0xA00}, args=(base,), until=l2._RETURN)
    return struct.unpack("<i", sim.uc.mem_read(base + 0xA00, 4))[0]


@pytest.mark.parametrize("species, weapon", [("keylord", "axion_staff"), ("balthazar", "farmers_hoe")])
def test_a_picked_weapon_swings_garret4s_attack_in_a_column_whose_name_the_body_owns(usa, species, weapon):
    """AZ-688 (Modkit's Step 2.161b2): with a picked weapon keylord swung his own attack_1 and attack_2, Balthazar his
    attack_1-3, since W3 keeps each column's vanilla Anim and X12's lookup borrows only a name the body lacks. Such
    a build lands X44 at that lookup (0x7E3F0): for the player's species g4/<name> before <name>, for a name the
    body owns as for one it lacks, the body's own where garret4's isn't baked, another species' as the game's (L2)."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    body = _body(characters_xbr, config, species)
    names = set(_played(config)[1])
    owned = sorted(names & set(read_body(characters_xbr, body).clips))
    assert owned == {"keylord": ["attack_1", "attack_2"], "balthazar": ["attack_1", "attack_2", "attack_3"]}[species]
    built = _swap(usa, species, sounds="garret4", weapon=weapon)[XBE]
    own = {name: 100 + i for i, name in enumerate([*owned, "idle"])}
    baked = {name: 200 + i for i, name in enumerate([*owned, "attack_9"])}
    keys = {f"characters/{body}/{name}".casefold(): k for name, k in own.items()} | {
        f"characters/{body}/{BAKED_DIR}{name}".casefold(): k for name, k in baked.items()}
    got = {(name, flags): _attack_lookup(built, body, keys, name, flags)
           for name in (*owned, "attack_9", "idle", "no_such_clip") for flags in (0x24, 0x04)}
    assert got == {(name, flags): (baked if flags == 0x24 and name in baked else own).get(name, -1)
                   for name, flags in got}


@pytest.mark.parametrize("weapon", ["farmers_hoe", "bare_hands", "balthazar_magic"])
def test_garret4s_other_weapons_cut_his_staff(usa, weapon):
    """garret4 with a weapon other than his Axion staff (Modkit's Steps 2.161d, 2.161g, 2.182, 2.206b, 2.207;
    D492-D495, D618, D707): the balance and reach-to-ground are taken (refused with his staff, and in Skin with a
    prop-less weapon); his staff is cut from his mesh at both LODs, his bones kept (W33); X17 off for bare hands and
    magic, the hoe on his staff chain keeping it. The hoe is a group in each LOD skinned to its tip carrier alone
    (W41), its blade tip where W26's carrier would ride, its handle down the carrier's -y, X3 his window in every
    column with the box around the hoe; bare hands and magic swing their style's clips in every column but his roll,
    X13 filling what the listing fills; the logic's reach at least his swing (D237), bare hands' under half of it.
    With the hoe his staff's 60 fx transforms bind its two carriers, the power heads laid along it whole, the plain
    staff's head (24 transforms) shrunk with his staff (AZ-782), no staff fx hidden."""
    for staff in [{"weapon": "axion_staff"}] + ([{"weapon": weapon, "mode": "garret4"}] if weapon != "farmers_hoe"
                                               else []):
        with pytest.raises(ValueError, match=re.escape("--player-attack-balance on: garret4 plays his own")):
            _swap(usa, "garret4", attack_balance=True, **staff)
    characters_xbr, hoe = _vanilla(usa, CHARACTERS), weapon == "farmers_hoe"
    logic = pc.AttackLogic()
    on = True if hoe else None   # bare hands and magic: the mode's, both on
    game = _swap(usa, "garret4", weapon=weapon, attack_balance=on, attack_ground=on, logic=logic)
    built, xbe = game[CHARACTERS], game[XBE]
    assert logic.reach < GARRET4_FORWARD / 2 if weapon == "bare_hands" else logic.reach >= GARRET4_FORWARD
    staff = {"staff_center2slide", "m_staffbottom", "m_stafftop"}

    def on_staff(asset) -> list[int]:   # each LOD's triangles whose every vertex weighs mostly on his staff
        bones = {asset.bone(b) for b in staff}
        return [sum(all(sum(w for b, w in g.skin(v).items() if b in bones) > 0.5 for v in t)
                    for g in lod.groups for t in g.triangles) for lod in asset.lods]
    vanilla, mine = read_asset(characters_xbr, "garret4"), read_asset(built, "garret4")
    assert all(on_staff(vanilla)) and mine.bone_names == vanilla.bone_names + (
        list(weapons()[weapon].prop.carriers) if hoe else [])
    off, _, patch = ports.patch_spec_site(xbe, pc.STAFF_WALLS)
    assert (xbe[off:off + len(patch)] == patch) is not hoe   # X17
    columns, played = _played(game[CONFIG])
    if not hoe:
        listed = pc.attacks(_vanilla(usa, CONFIG), characters_xbr, "garret4", weapon=weapon)
        filled = round(_param(xbe, pc.ATTACK_BOX_HOOK, "_player_attack_ground_mask"))
        want = sum(1 << i for i, a in enumerate(listed) if a.ground and a.clip != "t/throw")   # it swings no box
        assert (filled, logic.damage < 1.0) == (want, True) and want   # X13's fill and W14 on, as listed
        assert on_staff(mine) == [0, 0]
        assert {p[:2] for col, p in zip(columns, played) if col != pc.ROLL} == {weapons()[weapon].style.dir or "t/"}
        assert played[columns.index(pc.ROLL)] == "roll_forward"
        return
    top = mine.bone("m_stafftop")
    assert on_staff(mine) == [0, 0]   # the hoe on its tip carrier (W41), none of his staff left
    rig, prop = Rig.read(built, "garret4"), weapons()[weapon].prop
    k_turn = _staff_hold(characters_xbr, weapons()[weapon].style, prop.over)[3]
    verts, _, _, _ = _donor(characters_xbr, prop)
    bottom = mine.bone("m_staffbottom")
    names = [b.name for b in rig.bones]   # D618: the power heads on the hoe's carriers, at its ends
    tip_c, end_c = (names.index(n) for n in prop.carriers)
    for lod in mine.lods:
        group = lod.groups[-1]
        assert (group.palette, len(group.vertices)) == ([tip_c], len(verts))
    ends = [min(range(len(verts)), key=lambda j: f(math.dist(verts[j][0], (0.0,) * 3))) for f in (abs, lambda d: -d)]
    lo = loadout(characters_xbr, read_body(characters_xbr, "garret4"), "own", False, None, weapon)
    origin, placed = pw._on_chain(characters_xbr, lo)
    want = [origin, [o + c for o, c in zip(origin, _turn(placed, (0.0, -_donor(characters_xbr, prop)[3], 0.0)))]]
    assert (rig.bones[tip_c].parent, rig.bones[end_c].parent) == (top, tip_c)
    assert max(math.dist(rig.positions[k], p) for k, p in zip((tip_c, end_c), want)) < 1e-4
    fx, plain = game[FX], _vanilla(usa, FX)
    gone = power.plain(plain)
    heads = [(rec in gone, list_at(plain, rec + 8)[0] + 28) for recs, ends_ in pc._staff_graphs(plain)
             for end in ends_.values() for rec in pc.staff_meshes(plain, recs, end)]   # W6 renames the binds in place
    assert (_bound(fx, prop.carriers), _bound(fx, ("m_stafftop", "m_staffbottom"))) == (60, 0)
    shrunk = [hid for hid, a in heads if all(abs(n) <= 1.01e-3 * abs(o) for n, o in zip(   # x0.001 in f32
        struct.unpack("<3f", fx[a:a + 12]), struct.unpack("<3f", plain[a:a + 12])))]
    assert (len(heads) > 24, shrunk) == (True, [True] * 24)   # the plain head's 24 alone (AZ-782)
    assert all(abs(n) >= 0.1 * abs(o) for hid, a in heads if not hid for n, o in zip(   # no power head shrunk
        struct.unpack("<3f", fx[a:a + 12]), struct.unpack("<3f", plain[a:a + 12])))
    assert all(fx[o:o + 12] == pc._SHOWN for o in pc.staff_scales(fx))   # no W4
    for clip in ("attack_1", "attack_9"):   # two his hoe never takes under the floor (W41 keys none)
        his = named_clip(built, "garret4", clip)
        assert all(tr.target != tip_c for tr in his.bones), clip
        for t in [k / 30 for k in range(0, int(his.length * 30), 3)]:
            at, turn = origins(rig, his, t), pose(rig, his, t)
            axis = [a - b for a, b in zip(at[top], at[bottom])]
            axis = [c / math.sqrt(sum(a * a for a in axis)) for c in axis]
            tip = [a + prop.over * c for a, c in zip(at[top], axis)]
            for j in ends:   # the blade's and the handle's ends, on the tip carrier, in W26's carrier frame
                rest = mine.lods[0].groups[-1].vertices[j].position
                posed = [a + c for a, c in zip(at[tip_c], _turn(qmul(turn[tip_c], qinv(rig.world[tip_c])),
                                                                [r - b for r, b in zip(rest, rig.positions[tip_c])]))]
                want = [a + c for a, c in zip(tip, _turn(qmul(turn[top], k_turn), verts[j][0]))]
                assert math.dist(posed, want) < 2e-3, (clip, t, j)
    _holds_its_prop(xbe, built, "garret4", characters_xbr, columns, played, lo, 1.0, "")


LOW_MOVES = ("360_ledge", "attack_10", "attack_17", "elemental_attack_2", "hose_attack_3", "touchdown", "victory_4",
             "roll_forward")
"""Garret's moves that took a held hoe under the floor (Modkit's Step 2.207's probe; his roll Step 2.207b's)."""


def _hoe_lows(built: bytes, body: str, clip_name: str, tip_name: str, hand_name: str | None
              ) -> list[tuple[float, float | None]]:
    """Each 30 Hz tick of ``clip_name`` under ``body`` in ``built``: its held prop's lowest vertex (the group on
    ``tip_name`` alone, in the body the player binds) over the floor (``m_feet``'s height there, keyed or its rest:
    the game draws the model at its entity less it), and its arm's origin over it (``None``: no ``hand_name``)."""
    rig = Rig.read(built, body)
    names = [b.name for b in rig.bones]
    tip, hand = names.index(tip_name), None if hand_name is None else pw._arm(rig, names.index(hand_name))
    group, = [g for g in read_asset(built, _worn(built, body)).lods[0].groups if g.palette == [tip]]
    local = [_turn(qinv(rig.world[tip]), [a - b for a, b in zip(v.position, rig.positions[tip])]) for v in group.vertices]
    feet = next(i for i, m in enumerate(rig.markers) if m.casefold() == "m_feet")
    rest = next(r for m, r in marker_records(built, body) if m.casefold() == "m_feet")[2]
    clip = named_clip(built, body, clip_name)
    fz = next((tr.keys for tr in clip.markers if tr.target == feet and tr.comp == 2), None)
    out = []
    for k in range(int(clip.length * 30) + 1):
        t = min(k / 30, clip.length)
        rot, at, floor = pose(rig, clip, t), origins(rig, clip, t), evaluate(fz, t) if fz else rest
        out.append((min(at[tip][2] + _turn(rot[tip], p)[2] for p in local) - floor,
                    None if hand is None else at[hand][2] - floor))
    return out


@pytest.mark.parametrize("species, weapon, body, hand, own", [
    ("garret4", "farmers_hoe", "garret4", "right_hand", ()),
    ("town_male_farmer_1", None, "townspeople/male_farmer_1", "right_hand", ()),
    ("keylord", "farmers_hoe", "keylord", "right_hand", ("attack_2", "die_1", "die_2", "ouch_2", "ouch_3")),
    ("gargoylestone", "farmers_hoe", "gargoylestone", None, ())])
def test_a_held_hoe_stays_over_the_floor_wherever_its_arm_is(usa, species, weapon, body, hand, own):
    """AZ-784, AZ-785, AZ-800 (Modkit's Steps 2.207-2.207c, W41): in game Garret's 360_ledge took the hoe's tip
    0.358 m under the floor. Each of his clips but a ladder, ledge, jump or water one turns the hoe about his grip
    where it would go under, on his own staff chain, on a farmer's hand, copied into another body's hand at its size
    with W35's arm turn and on a statue's floating carrier; in the wearer's own clips too, and where no turn clears
    it it slides up while the arm is on the floor or over it: in every move of :data:`LOW_MOVES` and the wearer's
    ``own``, the hoe's lowest vertex is over the floor on every tick its arm is; his ladder and water clips key no
    tip carrier."""
    kw = {"attack_balance": True, "attack_ground": True} if species == "garret4" else {"sounds": "garret4"}
    built = _swap(usa, species, weapon=weapon, **kw)[CHARACTERS]
    hoe, his = weapons()["farmers_hoe"].prop, species == "garret4"
    tip = hoe.carriers[0] if weapon else hoe.own_carriers[0]   # W31's, W26's
    for name in [m if his else BAKED_DIR + m for m in LOW_MOVES] + list(own):
        under = [(k, low) for k, (low, at) in enumerate(_hoe_lows(built, body, name, tip, hand))
                 if low < 0.0 and (at is None or at >= -1e-3)]
        assert not under, (name, len(under))
    if his:
        carrier = [b.name for b in Rig.read(built, body).bones].index(tip)
        assert all(tr.target != carrier for name in ("climb_up_edge", "swim_idle_up")
                   for tr in named_clip(built, body, name).bones)


def _faded_lows(built: bytes, body: str, tip_name: str, old: str, at: float | None, new: str) -> list[float]:
    """Each tick n = 1-7 of the game's 0.25 s crossfade from ``old`` at ``at`` s on (``None``: held at its end) into
    ``new`` from its start (the new layer's share (0.01 + n / 7.5) / 1.01, each layer's rotations normalised and
    turned to w >= 0 (0xCBB6D), summed by share and normalised, the translations and ``m_feet``'s height lerped):
    the held prop's lowest vertex (the group on ``tip_name`` alone) over the blended floor."""
    rig = Rig.read(built, body)
    tip = [b.name for b in rig.bones].index(tip_name)
    group, = [g for g in read_asset(built, _worn(built, body)).lods[0].groups if g.palette == [tip]]
    local = [_turn(qinv(rig.world[tip]), [a - b for a, b in zip(v.position, rig.positions[tip])]) for v in group.vertices]
    feet = next(i for i, m in enumerate(rig.markers) if m.casefold() == "m_feet")
    rest = next(r for m, r in marker_records(built, body) if m.casefold() == "m_feet")[2]
    before, after, out = named_clip(built, body, old), named_clip(built, body, new), []
    for n in range(1, 8):
        share, layers = (0.01 + n / 7.5) / 1.01, []
        for clip, t in ((before, before.length if at is None else at + n / 30), (after, n / 30)):
            keyed = {(tr.target, tr.comp): tr.keys for tr in clip.bones}
            t = min(t, clip.length)
            q = [qnorm(tuple(evaluate(keyed[k, 3 + c], t) if (k, 3 + c) in keyed else b.q[c] for c in range(4)))
                 for k, b in enumerate(rig.bones)]
            fz = next((tr.keys for tr in clip.markers if tr.target == feet and tr.comp == 2), None)
            layers.append(([r if r[3] >= 0 else tuple(-x for x in r) for r in q],
                           [[evaluate(keyed[k, c], t) if (k, c) in keyed else b.t[c] for c in range(3)]
                            for k, b in enumerate(rig.bones)], evaluate(fz, t) if fz else rest))
        world, place = [], []
        for k, b in enumerate(rig.bones):
            q = qnorm(tuple((1 - share) * x + share * y for x, y in zip(layers[0][0][k], layers[1][0][k])))
            t = [(1 - share) * x + share * y for x, y in zip(layers[0][1][k], layers[1][1][k])]
            r = qmul(qmul(b.jo, q), b.ra)
            world.append(r if b.parent < 0 else qmul(world[b.parent], r))
            place.append(t if b.parent < 0 else [p + d for p, d in zip(place[b.parent], _turn(world[b.parent], t))])
        floor = (1 - share) * layers[0][2] + share * layers[1][2]
        out.append(min(place[tip][2] + _turn(world[tip], p)[2] for p in local) - floor)
    return out


def test_a_held_hoe_stays_over_the_floor_through_a_crossfade_with_a_loop(usa):
    """AZ-806 (Modkit's Step 2.207c): at a clip change the game blends the two clips' poses for 0.25 s, and a blend
    of two poses each keeping the hoe over the floor took keylord's under in game (idle_1 into die_2, his sweep's end
    into idle_1). A clip that plays once turns the hoe up over its first ticks against each loop's phases and over
    its last 0.25 s against each loop fading in: through both crossfades its lowest vertex stays over the floor."""
    built = _swap(usa, "keylord", weapon="farmers_hoe", sounds="garret4")[CHARACTERS]
    tip = weapons()["farmers_hoe"].prop.carriers[0]
    for old, at, new in (("idle_1", 1 / 30, "die_2"), (BAKED_DIR + "360_basic_attack", None, "idle_1")):
        lows = _faded_lows(built, "keylord", tip, old, at, new)
        assert min(lows) >= 0.0, (old, new, sum(x < 0.0 for x in lows))


def test_the_floor_lift_keeps_its_turn_up_and_fades_its_slide_as_hand_and_arm_go_under():
    """W41's floor lift (Modkit's Step 2.207b's review, F1 and F2; AZ-800): a point under the grip a little behind it
    clears 30.84 degrees up or 20.84 down: Step 2.207's paths keep the turn up, a wearer's own clips (``either``) the
    least; a rod through a grip under its clearance slides up whole to 1 mm under the floor, half at half SLIDE_RAMP
    more, none past it; the higher of the hand and the arm gates the slide, so a hand 0.4 m under its floor slides
    whole while the arm is over, by the hand's depth, and an arm deep under its hand slides by the hand's."""
    hull, up = ((0.0, 0.0, 0.0), (0.0, -1.0 - 0.5 * math.sin(math.radians(5)), -0.5 * math.cos(math.radians(5)))), (
        0.0, 0.0, 1.0)

    def lifted(either):
        q, _, slide = pw._floor_lift((0.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0), hull, 1.5, up, 0.55,
                                     either=either)
        return round(2 * math.degrees(math.atan2(q[0], q[3])), 2), slide
    assert (lifted(False), lifted(True)) == ((30.84, (0.0, 0.0, 0.0)), (-20.84, (0.0, 0.0, 0.0)))
    rod = ((0.0, 0.0, 0.0), (0.0, -1.5, 0.0))
    for depth, fade in ((-0.01, 1.0), (0.001, 1.0), (0.001 + pw.SLIDE_RAMP / 2, 0.5), (0.001 + pw.SLIDE_RAMP, 0.0),
                        (1.0, 0.0)):
        _, _, slide = pw._floor_lift((0.0, 1.0, -depth), (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, -depth), rod, 1.5, up,
                                     pw.FLOOR_CLEAR, 0.0)
        assert slide == pytest.approx((0.0, 0.0, (pw.FLOOR_CLEAR + depth) * fade), abs=1e-9), depth
        _, _, slide = pw._floor_lift((0.0, 1.0, -0.4), (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, -0.4), rod, 1.5, up,
                                     pw.FLOOR_CLEAR, 0.0, arm=(0.0, -0.3, -depth))
        assert slide == pytest.approx((0.0, 0.0, (pw.FLOOR_CLEAR + 0.4) * fade), abs=1e-9), depth
        _, _, slide = pw._floor_lift((0.0, 1.0, -depth), (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, -depth), rod, 1.5, up,
                                     pw.FLOOR_CLEAR, 0.0, arm=(0.0, -0.3, -1.0))
        assert slide == pytest.approx((0.0, 0.0, (pw.FLOOR_CLEAR + depth) * fade), abs=1e-9), depth


def test_a_copied_hoe_stays_over_the_floor_once_a_recipe_turns_her_arms(usa_iso):
    """AZ-785 (Modkit's Step 2.207b): a recipe's ``arms`` (W28, booblord's 21 degrees) turn her arms after the bake
    keyed the copied hoe's carrier along garret4's staff, so W41's lift, made at her unturned grip, no longer cleared
    the floor (booblord + hoe's finish 0.374 m under in game). W41 lifts it where W28 will put her grip: in each of
    those clips, baked onto her base and W28-turned, its lowest point stays over the floor."""
    characters_xbr = _vanilla(usa_iso, CHARACTERS)
    plain = read_body(characters_xbr, "townspeople/female_2")
    recipe = SimpleNamespace(arms=21.0, arm_clips=(), poses=())
    lo = loadout(characters_xbr, plain, "own", True, builtins()["booblord"], "farmers_hoe")
    worn = pw.add_carriers(characters_xbr, plain, lo, Retarget(characters_xbr, plain.name, grow=False))
    rig, rt = Rig.read(worn, plain.name), Retarget(worn, plain.name, grow=True)
    post = pw.carried_copy(worn, read_body(worn, plain.name), lo, recipe)
    tip = [b.name for b in rig.bones].index(lo.prop.carriers[0])
    hull, _ = pw._prop_hull(characters_xbr, lo.prop)
    for name in ("attack_10", "hose_attack_3"):
        source = named_clip(worn, "garret4", name)
        clip = turned(rig, post(name, source, bake_clip(rt, source)), arm_turns(rig, recipe.arms))   # W28, later
        for k in range(int(clip.length * 30) + 1):
            t = min(k / 30, clip.length)
            m = pw._rows(pose(rig, clip, t)[tip])
            low = origins(rig, clip, t)[tip][2] + min(sum(m[2][c] * lo.k * p[c] for c in range(3)) for p in hull)
            assert low >= 0.0, (name, k)


HELD = [("catalisk", "farmers_hoe"), ("harvester", "axion_staff"), ("boulder", "farmers_hoe"),
        ("gargoylestone", "axion_staff"), ("firedrake", "balthazar_magic")]
"""A creature's hand and pincer, a token's root (rigid), a clipless statue (floating), a jaw (magic)."""


@pytest.mark.parametrize("species, weapon", HELD)
def test_a_creature_or_token_holds_a_weapon_on_its_grip(usa, species, weapon, monkeypatch):
    """A body the bake doesn't map keeps its own clips and takes the prop on two carriers appended last (Modkit's
    Steps 2.161e, 2.195b, 2.204, 2.207b; D493, D810): the tip under its grip (weapons.json's grips; a token its
    root, an odd fit) where garret4's idle at t 0 holds his staff's tip from his right hand, x k (then a grip row's
    turn and offset), no clip keying the end and only W41 the tip, its mesh in every LOD skinned to the tip; X3 in
    exact mode with the tip as its bone on every attack column, each row the window of the body's own clip there
    (else X3's 20-50% of the move), a cube TIP_BOX x k x the drawn scale centred on the tip, as the listing lists
    it; the logic's reach the tip's measured alone. A clipless statue's prop floats on a root carrier keyed in each
    of garret4's clips baked onto it at k x his tip + (1/D - k) x his m_feet, turned as his staff top, X3's box
    around it. Balthazar's magic on a creature: his markers grown, its own attack clips keying his lightning switch
    over their own damage windows and his bolts' marker at its grip (the firedrake's jaw) plus his offset, the
    player's clone of his graph (X40), its own boxes hitting. Bare hands build its default (its own attacks)."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    row = pc._species(_doc(config).keyed_section("critters_engine"))[species]
    body, drawn = row["body"], row["scale"] or 1.0
    mine = read_body(characters_xbr, body)
    lo = loadout(characters_xbr, mine, "own", pc.bakes(mine, "garret4"), None, weapon)
    fits = offers(characters_xbr, mine)
    assert fits["bare_hands"] == ("same", pw.same_why(mine, "own", "bare_hands")) and fits[weapon][0] == lo.fit
    assert fits["balthazar_magic"][0] == ("odd" if species in ("boulder", "gargoylestone") else "look")
    logic = pc.AttackLogic()
    game = _swap(usa, species, sounds="garret4", weapon=weapon, attack_balance=False, logic=logic)
    built, xbe = game[CHARACTERS], game[XBE]
    rig, vanilla = Rig.read(built, body), Rig.read(characters_xbr, body)
    names = [b.name for b in rig.bones]
    if weapon == "balthazar_magic":   # cast from its jaw in its own attack clips, its own boxes hitting
        own = pc.AttackLogic()
        _swap(usa, species, sounds="garret4", attack_balance=False, logic=own)
        assert (lo.grip, lo.fit, names, logic.reach) == ("jaw", "look", [b.name for b in vanilla.bones], own.reach)
        assert set(MAGIC) <= set(rig.markers)
        his = Rig.read(characters_xbr, "balthazar_airship")
        rest = dict(marker_records(characters_xbr, "balthazar_airship"))
        source = named_clip(characters_xbr, "balthazar_airship", "attack_3")
        switch = his.markers.index(pc.CAST_SWITCH)
        on = next(s / 30 for s in range(int(source.length * 30)) if evaluate(next(
            tr.keys for tr in source.markers if tr.target == switch and tr.comp == 2), s / 30) >= 0.5)
        ref = origins(his, source, on)[[b.name for b in his.bones].index("left_w")]
        jaw, cast = names.index("jaw"), 0
        for clip in sorted(pc.attack_clips(read_body(built, body))):
            motion, windows = named_clip(built, body, clip), pc.damage_windows(built, body, clip)
            keyed = {(tr.target, tr.comp): tr.keys for tr in motion.markers}
            w0, w1 = ((min(w.on for w in windows), max(w.off for w in windows)) if windows
                      else (0.2 * motion.length, 0.5 * motion.length))   # X3's own window
            for t in [k / 30 for k in range(int(motion.length * 30))]:
                lit = evaluate(keyed[rig.markers.index(pc.CAST_SWITCH), 2], t) >= 0.5
                assert lit is (w0 <= t <= w1) or min(abs(t - w0), abs(t - w1)) < 0.01, (clip, t)
                at = [evaluate(keyed[rig.markers.index("m_balth_lightning"), c], t) for c in range(3)]
                want = [a + r - h for a, r, h in zip(origins(rig, motion, t)[jaw], rest["m_balth_lightning"], ref)]
                assert math.dist(at, want) < 2e-3, (clip, t)
            cast += 1
        assert cast >= 2
        key = fx_edit.clone_key(body)
        assert any(r.key.casefold() == key for r in parse_index_xbr(game[INDEX]).records)
        hook = ports.resolve_va_to_file(xbe, pc.FX_DEFAULT_HOOK_VA)
        assert xbe[hook:hook + 5] != pc._FX_DEFAULT_VANILLA   # X40
        return
    prop, n = weapons()[weapon].prop, len(vanilla.bones)
    tip, end = names.index(prop.carriers[0]), names.index(prop.carriers[1])
    assert (names[:n], tip, end, rig.bones[end].parent) == ([b.name for b in vanilla.bones], n, n + 1, tip)
    verts, _, _, _ = _donor(characters_xbr, prop)
    m = pc.inverse_binds(built, body)[tip]
    origin = [-sum(m[12 + j] * m[4 * i + j] for j in range(3)) for i in range(3)]   # the tip's bind origin
    longest = max(math.dist(p, (0.0, 0.0, 0.0)) for p, _, _, _ in verts)
    for lod in read_asset(built, _worn(built, body)).lods:   # W32, every LOD, x k
        group = lod.groups[-1]
        assert (group.palette, len(group.vertices)) == ([tip], len(verts))
        assert max(math.dist(v.position, origin) for v in group.vertices) == pytest.approx(lo.k * longest, rel=1e-4)
    g4, style = Rig.read(characters_xbr, "garret4"), weapons()[weapon].style
    _, top, bottom, _, _ = _staff_hold(characters_xbr, style, prop.over)
    hand = [b.name for b in g4.bones].index(style.hand)

    def held(clip: str, t: float) -> tuple[list[float], list[float], list[float]]:   # his tip, hand and staff axis
        at = origins(g4, named_clip(characters_xbr, "garret4", clip), t)
        axis = [a - b for a, b in zip(at[top], at[bottom])]
        axis = [c / math.sqrt(sum(a * a for a in axis)) for c in axis]
        return [a + prop.over * c for a, c in zip(at[top], axis)], list(at[hand]), axis
    at = _boxes(xbe)
    anims = _doc(game[CONFIG]).keyed_section("attacks_anims")
    columns, played = _played(game[CONFIG])
    if not mine.clips:   # floating: a root keyed along his staff in each baked clip, X3's box around it
        assert (lo.carry, lo.fit, rig.bones[tip].parent) == ("floating", "odd", -1)
        feet = g4.markers.index("m_feet")
        # the carrier's frame his staff top's after C (AZ-693): the hoe's handle down its -y, the staff his top's
        rest = (0.0, 1.0, 0.0) if prop.mesh.loose else _turn(qinv(g4.world[top]), [
            a - b for a, b in zip(g4.positions[top], g4.positions[bottom])])
        rest = [c / math.sqrt(sum(a * a for a in rest)) for c in rest]
        for clip in ("attack_1", "attack_14"):
            baked, his = named_clip(built, body, BAKED_DIR + clip), named_clip(characters_xbr, "garret4", clip)
            moved = {tr.comp: tr.keys for tr in his.markers if tr.target == feet and tr.comp <= 2
                     and any(abs(k[1]) > 1e-3 for k in tr.keys)}
            for t in [k / 30 for k in range(0, int(his.length * 30), 4)]:
                tipped, _, axis = held(clip, t)
                want = [lo.k * a + (1 / drawn - lo.k) * (evaluate(moved[c], t) if c in moved else 0.0)
                        for c, a in enumerate(tipped)]
                assert math.dist(origins(rig, baked, t)[tip], want) < 2e-3, (clip, t)
                up = _turn(pose(rig, baked, t)[tip], rest)
                assert math.degrees(math.acos(min(1.0, sum(a * b for a, b in zip(up, axis))))) < 0.5, (clip, t)
        _holds_its_prop(xbe, built, body, characters_xbr, columns, played, lo, drawn)
        assert logic.reach > GARRET4_FORWARD
        return
    grip = names.index(lo.grip)   # rigid: its grip's, its own clips keying neither carrier
    assert (lo.carry, rig.bones[tip].parent, lo.grip) == ("rigid", grip, pw.grips()[body].bone if body in pw.grips()
                                                           else vanilla.bones[0].name)
    assert lo.fit == ("odd" if rig.bones[grip].parent < 0 else "look + tip hits")   # a token's root: odd
    hold, hand_at, _ = held("idle", 0.0)
    shift = pw.grips()[body].offset if body in pw.grips() else (0.0, 0.0, 0.0)   # the boulder's: ahead of it
    assert math.dist([o - g for o, g in zip(origin, rig.positions[grip])],
                     [lo.k * (a - h) + d for a, h, d in zip(hold, hand_at, shift)]) < 2e-3
    keyed = {clip: {tr.target for tr in named_clip(built, body, clip).bones if tr.target >= n} for clip in mine.clips}
    assert {k for ks in keyed.values() for k in ks} <= {tip} and any(keyed.values()) is (weapon == "farmers_hoe")
    monkeypatch.setattr(pw, "grips", lambda: {body: pw.Grip(body, lo.grip, (0.0, 0.0, 90.0), (0.1, 0.0, 0.0))})
    m = pc.inverse_binds(pw.add_carriers(characters_xbr, mine, lo), body)[tip]   # a grip row's turn and offset
    turned_at = [-sum(m[12 + j] * m[4 * i + j] for j in range(3)) for i in range(3)]
    x, y, z = (lo.k * (a - h) for a, h in zip(hold, hand_at))
    assert math.dist(turned_at, [g + d for g, d in zip(rig.positions[grip], (0.1 - y, x, z))]) < 2e-3
    monkeypatch.undo()
    assert round(_param(xbe, DAMAGE_MARKER, "_player_model_x3_bone")) == tip
    assert round(_param(xbe, DAMAGE_MARKER, "_player_model_x3_columns")) == sum(
        1 << i for i, col in enumerate(columns) if col != pc.ROLL)
    listed = pc.attacks(config, characters_xbr, species, weapon=weapon)
    assert [(a.clip, a.tipped) for a in listed] == [(c, col != pc.ROLL) for col, c in zip(columns, played)]
    side, ahead = pw.TIP_BOX * lo.k * drawn, []
    for i, (col, clip) in enumerate(zip(columns, played)):
        box = BOX.unpack_from(xbe, at + BOX.size * i)
        if col == pc.ROLL:
            continue
        windows, length = pc.damage_windows(built, body, clip), mine.length(clip)
        start, stop = pc.move_window(anims, i)
        want = ((min(w.on for w in windows) / length, max(w.off for w in windows) / length) if windows else
                (start + pc.X3_OPENS * (stop - start), start + pc.X3_CLOSES * (stop - start)))
        assert box == pytest.approx((*want, 0.0, 0.0, 0.0, side, side, side), abs=1e-5), col
        motion = named_clip(built, body, clip)
        for s in range(41):
            c = [v * drawn for v in origins(rig, motion, (want[0] + (want[1] - want[0]) * s / 40) * length)[tip]]
            ahead.append(forward([v - side / 2 for v in c], [v + side / 2 for v in c]) if col not in pc.CASTS else 0)
    assert logic.reach == pytest.approx(max(ahead), abs=1e-6)

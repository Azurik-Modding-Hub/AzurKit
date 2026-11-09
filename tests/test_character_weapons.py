"""Weapons and the weaponless townsfolk's throw (Modkit's ``tests/test_player_weapons.py`` and
``test_player_throw.py``, ported lean: Step 4.27d). Weapons are data (``weapons.json``, D492-D495): each body's
default weapon, what a build makes of a picked one (``_player_weapons.loadout``: its prop, style, boxes, reach and
grade) and the moveset weapons (D585); the throw (D473) is W30's projectile ``debug`` and X42, which throws it, the
effects templates' rows (D538) too. Each build is the swap's own dress (``tools.characters.dressed``, which the
plan calls) of the USA image with no pack on, as Modkit's tests dressed a fresh staging; X42's and the attack
state's checks run on ``devkit/sim``'s L2."""

from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import math
import re
import struct
import sys
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
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
from tests.test_characters import booblords  # noqa: F401 (a fixture)

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
    key = (str(image), species, json.dumps(character, sort_keys=True))
    if worn is not None:   # a variant object is built fresh: two may share a sha (``replace``) and differ
        _BUILT.pop(key, None)
    if key not in _BUILT:
        v, filled = _image(str(image)), pc.AttackLogic()
        staging, _, _, log = characters.dressed(characters.normalize({"species": species, **character}), v, (),
                                                characters.packs_view(v.release, mods.PACKS), worn=worn, logic=filled)
        _BUILT[key] = ({name: bytes(staging[name]) for name in FULL}, dict(vars(filled)), list(log))
        while len(_BUILT) > 4:
            _BUILT.popitem(last=False)
    files, filled, log = _BUILT.pop(key) if worn is not None else _BUILT[key]
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


@pytest.fixture
def booblord(booblords, monkeypatch):
    """Booblord installed from Azurik-Custom-Content (``booblords``), and the folders the swap's modules bound to
    the content folder at import (``_player_variants``' ``CLIPS`` and ``SOUNDS``) rebound to that one, so this
    process dresses her."""
    from azurkit.tools.characters import _player_variants, content

    old, new = _player_variants.SOUNDS.parent, content.ROOT
    for name, module in list(sys.modules.items()):
        if name == characters.__name__ or name.startswith(f"{characters.__name__}."):
            for attr, value in list(vars(module).items()):
                if isinstance(value, Path) and value.is_relative_to(old):
                    monkeypatch.setattr(module, attr, new / value.relative_to(old))


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


def test_a_variant_under_another_weapon_keeps_the_clips_its_idles_and_slots_name():
    """Booblord wearing another weapon drops her attack clips and columns but keeps the clips her ``idles`` and
    ``slots`` name (her stance, gait and victory are no attack), each still one of her recipe's; a lent clip joins
    them (Modkit's Steps 2.168, 2.171 on 2.161g's moveset rule, D585)."""
    from azurkit.tools.characters._player_variants import VARIANT_DIR, lend, unarmed

    her = builtins()["booblord"]
    bare = unarmed(her)
    assert set(bare.clips) == {*her.idles.values(), *her.slots.values()} and not bare.columns
    assert all(c.startswith(VARIANT_DIR) for c in (*bare.idle_clips().values(), *bare.slot_clips().values()))
    assert {"spin", "pony_whip"} <= set(her.clips) - set(bare.clips)
    assert set(lend(her, her, her.base, {"spin": her.clips["spin"]}).clips) == {*bare.clips, "spin"}


def test_booblord_shouts_in_her_voice_where_garret_shouts_under_any_other_weapon(usa_iso):
    """D705 (Modkit's Steps 2.183, 2.209): under the Axion staff (her default), the hoe, bare hands or Balthazar's
    magic her one sfx is her shouts (attack1.wav, attack2.wav, shout.wav, a take at random as each attack starts) in
    the 20 columns whose Sound cells give Garret a shout (not his casts; her roll keeps roll.wav), her moves'
    whooshes gone with her moves; her own spins take no such recipe."""
    characters_xbr = _vanilla(usa_iso, CHARACTERS)
    anims = _doc(_vanilla(usa_iso, CONFIG)).keyed_section("attacks_anims")
    shouted = [col for k, col in enumerate(anims.col_names())
               if col != pc.ROLL and any(anims.find_cell(col, row, k).type_code for row in SHOUT_ROWS)]
    assert list(SHOUTED) == shouted and len(shouted) == 20
    her = builtins()["booblord"]
    body = read_body(characters_xbr, "townspeople/female_2")
    voice = {"shout": {"generator": "wav", "files": ["attack1.wav", "attack2.wav", "shout.wav"], "columns": shouted}}
    for weapon in (None, "axion_staff", "farmers_hoe", "bare_hands", "balthazar_magic"):
        assert loadout(characters_xbr, body, "own", True, her, weapon).recipe.sfx == voice, weapon
    assert loadout(characters_xbr, body, "own", True, her, "booblord_spin").recipe is None


def test_a_variants_attack_sliders_are_the_moveset_its_build_wears(usa_iso):
    """A variant's attack sliders and on/off rules are taken from the recipe its build wears (``loadout``'s
    ``recipe``, else its own) where a build reads its options (``tools.characters.variant``; Modkit's
    ``variant_options``, the 2.161g review's 1): beamlord's speed 2.0, balance off and ground on with no pick,
    ``own`` or his default's own name, the mode's under the hoe; booblord's the mode's under the Axion staff, her
    default (Step 2.209), her own under her spin."""
    characters_xbr, vanilla = _vanilla(usa_iso, CHARACTERS), _image(str(usa_iso))
    engine = _doc(_vanilla(usa_iso, CONFIG)).keyed_section("critters_engine")
    for name, weapon, speed in (("beamlord", None, 2.0), ("beamlord", "own", 2.0), ("beamlord", "balthazar_magic", 2.0),
                                ("beamlord", "farmers_hoe", 1.0), ("booblord", None, 1.0),
                                ("booblord", "axion_staff", 1.0), ("booblord", "booblord_spin", 1.0)):
        variant = builtins()[name]
        body = read_body(characters_xbr, pc._species(engine)[variant.base]["body"])
        lo = loadout(characters_xbr, body, variant.mode, pc.bakes(body, pc.MODE_ANIMS[variant.mode]), variant, weapon)
        worn = lo.recipe if lo.recipe is not None else variant
        _, got = characters.variant(characters.normalize({"species": name} | ({"weapon": weapon} if weapon else {})),
                                    vanilla)
        assert (got["attack_speed"], got["attack_damage"], got["attack_balance"], got["attack_ground"]) == (
            speed, worn.damage, worn.balance, worn.ground) and worn.speed == speed, (name, weapon)


def test_booblords_default_weapon_is_the_axion_staff_and_her_spins_a_pick(usa_iso):
    """D939 (Modkit's Step 2.209, the owner: "let's make booblord's default weapon the axion"): her recipe names
    the Axion staff, so a build of her with no pick is the build of the Axion staff on her recipe before (its
    loadout, her shout-only recipe and its options) and Booblord spin builds her spins as her default did; the
    Weapon box offers the Axion staff as her default, first, and her spins as a pick, each graded by a sitting."""
    characters_xbr = _vanilla(usa_iso, CHARACTERS)
    body = read_body(characters_xbr, "townspeople/female_2")
    her = builtins()["booblord"]
    before = replace(her, weapon=None)

    def worn(variant, weapon=None):   # a style's clip reader is a new closure each time, and a recipe equals only
        lo = loadout(characters_xbr, body, "own", True, variant, weapon)   # itself: its fields, its weapon aside
        return replace(lo, kit=lo.kit and (lo.kit.source, lo.kit.dir),
                       recipe=lo.recipe and {k: v for k, v in vars(lo.recipe).items() if k != "weapon"})
    assert (worn(her), options(her)) == (worn(before, "axion_staff"), options(before, weapon="axion_staff"))
    assert (worn(her, "booblord_spin"), options(her, weapon="booblord_spin")) == (worn(before), options(before))
    assert [(name, fit) for name, (fit, _) in offers(characters_xbr, body, "own", her).items()][:2] == [
        ("axion_staff", "default"), ("booblord_spin", GOOD)]
    graded = [grade("booblord", "own", loadout(characters_xbr, body, "own", True, her, w)) for w in (None, "booblord_spin")]
    assert [colour for colour, _ in graded] == ["green", "green"] and not any(pw.NOT_SEEN in why for _, why in graded)


def test_an_own_copy_of_booblord_builds_what_its_weapon_box_says_and_its_edits_build_or_are_refused(
        usa_iso, booblord, tmp_path, monkeypatch):
    """New from this on booblord (``library.own_copy``; Modkit's Step 2.209's review, 1 and 2) and ``devkit models
    edit --from booblord`` (``edit._seed``) leave her Axion staff out, and her notes (your own kept), so the copy's
    default plays its own spins (its Weapon box's one default: its bare hands) and its Attacks numbers reach the
    build; a copy of her recipe with the staff loads, its Bare hands pick builds bare hands with 1.0 hits, and an edit
    of her moveset under the staff is refused (it would play in no build), as moves of its own are (D585); a recipe
    from her keeps the staff."""
    from azurkit.tools.characters import library
    from devkit.models import edit

    monkeypatch.setenv(library.ENV, str(tmp_path / "lib"))
    characters_xbr = _vanilla(usa_iso, CHARACTERS)
    body = read_body(characters_xbr, "townspeople/female_2")
    made = library.own_copy("mine", {"from": "booblord", "notes": builtins()["booblord"].notes})
    recipe = json.loads(made.read_text(encoding="utf-8"))["mine"]
    copy = load_variants(made.read_text(encoding="utf-8"), str(made), tuple(builtins()))["mine"]
    fits = {name: fit for name, (fit, _) in offers(characters_xbr, body, "own", copy).items()}
    assert ({"weapon", "notes"} & recipe.keys(), copy.columns) == (set(), builtins()["booblord"].columns)
    yours = library.own_copy("yours", {"from": "booblord", "notes": "x"})
    assert json.loads(yours.read_text(encoding="utf-8"))["yours"]["notes"] == "x"
    (tmp_path / "work").mkdir()
    assert not {"weapon", "notes"} & edit._seed("mine", "town_female_2", None, "booblord", tmp_path / "work").keys()
    assert [name for name, fit in fits.items() if fit == "default"] == ["bare_hands"] and fits["booblord_spin"] == GOOD
    edited = {**recipe, "attacks": {**recipe["attacks"], "damage": 2.0}}
    assert options(load_variants(json.dumps({"mine": edited}), "test")["mine"])["attack_damage"] == 2.0
    hers = load_variants(json.dumps({"mine": {**recipe, "weapon": "axion_staff"}}), "test")["mine"]
    bare = loadout(characters_xbr, body, "own", True, hers, "bare_hands")
    assert (bare.name, bare.recipe.columns, pw.attack_recipe(hers, "bare_hands", "bare_hands").damage) == (
        "bare_hands", {}, 1.0)
    for field, value in (("attacks", edited["attacks"]), ("columns", {**recipe["columns"], "down": "spin"})):
        with pytest.raises(ValueError, match="weapon axion_staff plays every attack column"):
            load_variants(json.dumps({"mine": {**recipe, "weapon": "axion_staff", field: value}}), "test")
    assert load_variants(json.dumps({"mine": {"from": "booblord"}}), "test")["mine"].weapon == "axion_staff"


def test_garret4s_staff_moves_clear_the_wearers_chest(usa):
    """AZ-696 (Modkit's Step 2.161g, W35): Garret's staff moves swung by another body put the staff through its
    chest (town_male_6's attack_9 on 9 of its 16 ticks); weapons.json's ``fits`` turn both ``*_arm_1`` in each clip
    that clips, the prop riding the turned hand: in town_male_6's built attack_9 the staff is inside his chest on at
    most one tick more than on garret4, and X3's row for the column playing it holds the turned tip on every tick of
    the window. Every built-in variant's fit row is its recipe's."""
    characters_xbr = _vanilla(usa, CHARACTERS)
    body = "townspeople/male_6"
    lo = loadout(characters_xbr, read_body(characters_xbr, body), "own", True, None, "axion_staff")
    assert lo.turns == pw.fits()[body].clips and "attack_9" in lo.turns
    assert loadout(characters_xbr, read_body(characters_xbr, body), "garret4", True, None, "axion_staff").turns == lo.turns
    game = _swap(usa, "town_male_6", sounds="garret4", weapon="axion_staff")
    built, xbe = game[CHARACTERS], game[XBE]
    clip = named_clip(built, body, BAKED_DIR + "attack_9")
    his = pw.Chest(characters_xbr, "garret4", (*weapons()["axion_staff"].prop.mesh.bones, "staff_constraint")).ticks(
        named_clip(characters_xbr, "garret4", "attack_9"))[0]
    assert pw.Chest(built, body, lo.prop.carriers).ticks(clip)[0] <= his + 1
    i = _played(game[CONFIG])[1].index("attack_9")
    box = BOX.unpack_from(xbe, _boxes(xbe) + BOX.size * i)
    drawn, rig = _drawn(game[CONFIG]), Rig.read(built, body)
    tip = [b.name for b in rig.bones].index(lo.prop.carriers[0])
    w = garret4_window(characters_xbr, read_body(characters_xbr, "garret4"), "attack_9")
    for s in range(pw.HELD_SAMPLES + 1):
        at = [drawn * c for c in origins(rig, clip, w.on + (w.off - w.on) * s / pw.HELD_SAMPLES)[tip]]
        assert all(c - e / 2 - 0.01 <= a <= c + e / 2 + 0.01 for a, c, e in zip(at, box[2:5], box[5:8])), s
    assert {n: row.sha for n, row in pw.fits().items() if n in builtins()} == {
        n: builtins()[n].sha for n in pw.fits() if n in builtins()}


def test_an_untested_models_weapon_picks_read_grey_not_seen_in_game_in_its_builds_status_line():
    """AZ-807 (D830): an untested model's red was each pick's cap, so every weapon on one read red; its picks are
    grey, not seen in game, in the build's status line (``pick_grade`` with the model's status), as the Characters
    tab's Weapon box shows them (``test_characters.py``'s species-grades test)."""
    assert pc.mode_status("frag_fire_1", "own", "own") == pc.UNTESTED
    line = pick_grade("frag_fire_1", "own", "farmers_hoe", True, "frag_fire_1", "odd", pc.UNTESTED)
    assert (line[0], line[1].startswith(pw.NOT_SEEN)) == ("unseen", True)


# --- the moveset weapons (Modkit's Step 2.161g; D585, D592) on booblord's v3 -------------------------------------
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

"""Booblord's v3 ``mesh``, ``arms`` and ``jiggle`` (Modkit's ``variants.json`` at its Step 2.174)."""


def _booblord_v3():
    """Booblord's v3 as the built-in ``booblord`` (Modkit's ``tests/_variant_fixtures.py``: her shipped recipe's
    dress takes minutes, v3's seconds): her recipe with v3's mesh, arms and jiggle, and no poses, textures, idles,
    slots, victory_cancel, lods or weapon (her spins her default, as v3's were), her moves.glb and idles.glb clips
    and the columns playing them left out; its recipe ``12ee3e6638f4``, as Modkit's."""
    from azurkit.tools.characters._player_variants import BUILTIN, _variant

    recipe = json.loads(BUILTIN.read_text(encoding="utf-8"))["booblord"]
    for key in ("poses", "textures", "slots", "victory_cancel", "lods", "weapon", "idles"):
        recipe.pop(key, None)
    moves = {k for k, clip in recipe["clips"].items() if clip.get("file") in ("moves.glb", "idles.glb")}
    recipe["clips"] = {k: clip for k, clip in recipe["clips"].items() if k not in moves}
    recipe["columns"] = {c: clip for c, clip in recipe["columns"].items() if clip not in moves}
    recipe["carry"] = [c for c in recipe["carry"] if c in recipe["columns"]]
    recipe |= json.loads(json.dumps(BOOBLORD_V3))
    variant = _variant("booblord", recipe, "built-in")
    assert variant.sha == "12ee3e6638f4", variant.sha
    return variant


def _x14(xbe: bytes) -> tuple[str, dict[int, str]]:
    """X14's table in the built ``xbe``: its dir and each slot it names (a miss left out)."""
    from azurkit.tools.characters._player_sounds import SOUND_HOOKS, SOUNDS_TABLE, TABLE_SIZE

    table = _read(xbe, _symbol(xbe, SOUND_HOOKS[0], SOUNDS_TABLE.symbol), TABLE_SIZE)
    dir_at, count = struct.unpack_from("<HH", table)

    def name(off: int) -> str:
        return table[off:table.index(b"\0", off)].decode()
    return name(dir_at), {slot: name(off) for slot, off in enumerate(struct.unpack_from(f"<{count}H", table, 4))
                          if off}


MOVESETS = [("booblord", None), ("booblord", "axion_staff"), ("booblord", "farmers_hoe"),
            ("town_male_6", "booblord_spin"), ("garret4", "booblord_spin"), ("catalisk", "booblord_spin"),
            ("air_elemental", "booblord_spin")]
"""Booblord's own moveset, Garret's swung by her, and her spins on four other bodies (Modkit's T-G1 rows)."""
SPUN = {"booblord": ("root_joint", "right_hand_endnode"), "town_male_6": ("root_joint", "right_hand_endnode"),
        "garret4": ("root_joint", "right_hand_endnode"), "catalisk": ("root_joint", "right_hand"),
        "air_elemental": ("tail", "r_wrist")}
"""The bone each body's spins turn and the hand its hand spin plants."""


@pytest.mark.parametrize("model, weapon", MOVESETS)
def test_a_bodys_own_moves_are_a_weapon_any_body_can_pick(usa, booblord, model, weapon):
    """D585 (the owner: "for weapons, booblord's spin would be a type of weapon, whereas if she has the axion she
    would have garret's moveset"), D592, AZ-697 (Modkit's Step 2.161g): booblord's (v3's) default is her own
    moveset, her spins in her recipe's columns and the bare-hands kit in the rest; with the Axion staff or the hoe
    she swings Garret's attack in every column, no clip of hers, her look kept (her jiggle's X41), the attack
    sliders the mode's, her shouts where Garret's were (D705). Booblord spin on another body generates her spins on
    its own rig (W22): its root turned (the air elemental's tail), its hand spin planted on her hand where it has
    one, else its grip, each box her recipe's x its height over hers, m_damage grown where it has none, X33 carrying
    her columns, her damage 0.6; its other columns the kit on a body the bake serves (garret4: his staff cut, X17
    forced), else its own (the catalisk, an odd fit). Her whip, a clip of her own rig, is no spin she lends."""
    characters_xbr, config = _vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG)
    variant = _booblord_v3() if model == "booblord" else builtins().get(model)
    species = variant.base if variant is not None else model
    body = _body(characters_xbr, config, species)
    lo = loadout(characters_xbr, read_body(characters_xbr, body), "own", True, variant, weapon)
    logic = pc.AttackLogic()
    game = (_swap(usa, model, worn=variant, weapon=weapon, logic=logic) if variant is not None
            else _swap(usa, model, sounds="garret4", weapon=weapon, logic=logic))
    built, xbe = game[CHARACTERS], game[XBE]
    columns, picks = _played(game[CONFIG])
    played = dict(zip(columns, picks))
    boob = builtins()["booblord"]
    under = f"characters/{body}/v/".casefold()
    if weapon in ("axion_staff", "farmers_hoe"):   # D585: Garret's moves in every column, her look hers
        assert picks == _played(config)[1]
        assert not any(n.casefold().startswith(under) for n in named_resources(built).values())   # AZ-697
        assert ports.verify_trampoline_patch(xbe, pc.JIGGLE_HOOK) == "applied"
        assert {k: options(variant, weapon=weapon)[k] for k in ("attack_damage", "attack_balance", "attack_ground")} \
            == {"attack_damage": 1.0, "attack_balance": None, "attack_ground": None}
        assert (lo.name, lo.picked, lo.recipe.columns) == (weapon, True, {})
        mine = {r.key.rsplit("/", 1)[1].split("_")[0] for r in parse_index_xbr(game[INDEX]).records
                if r.key.startswith("fx/sound/v/booblord/")}
        assert mine == {*variant.wavs, "shout"}   # her WAVs and shouts stay; her moves' whooshes go with her moves
        folder, binds = _x14(xbe)   # D705: her shouts where Garret's were (W9), the roll her roll.wav
        assert folder == "fx/sound/v/booblord" and {col: binds.get(ATTACK_SLOT + k) for k, col in enumerate(columns)} \
            == {col: "shout" if col in SHOUTED else "roll" if col == pc.ROLL else "" for col in columns}
        anims = _doc(game[CONFIG]).keyed_section("attacks_anims")
        assert not any(anims.find_cell(col, row, k).type_code for k, col in enumerate(columns) for row in SHOUT_ROWS)
        return
    lent = {clip for clip, p in boob.clips.items() if p["generator"] in pw.PORTABLE}   # her whip is her rig's
    spins = {col: "v/" + clip for col, clip in boob.columns.items() if clip in lent}
    assert {col: played[col] for col in spins} == spins
    rest = [col for col in columns if col not in spins and col != pc.ROLL]
    kit = kit_document()["columns"]
    if body.casefold() in TARGETS:
        assert {col: played[col] for col in rest} == {col: "t/" + kit[col] for col in rest}
    else:
        assert not any(played[col].startswith(("v/", "t/")) for col in rest)
    carry = round(_param(xbe, pc.CARRY_HOOK, "_player_model_carry_columns"))
    mask = sum(1 << columns.index(col) for col in boob.carry if col in spins)
    assert carry & mask == mask
    s = 1.0 if variant is not None else (height(characters_xbr, read_body(characters_xbr, body))
                                         / height(characters_xbr, read_body(characters_xbr, "townspeople/female_2")))
    mine = read_body(built, body, dirs=("v/",))
    assert mine.markers.count("m_damage") == 1 and (model in ("booblord", "town_male_6")) == (
        "m_damage" not in read_body(characters_xbr, body).markers)
    rig, damage = Rig.read(built, body), mine.markers.index("m_damage")
    root, hand = SPUN[model]
    for clip, p in ((clip, p) for clip, p in boob.clips.items() if clip in lent):
        made = named_clip(built, body, "v/" + clip)
        assert root in {rig.bones[tr.target].name for tr in made.bones if tr.comp <= 6}, clip   # turned or hopped
        extents = [tr.keys[0][1] for tr in sorted(made.markers, key=lambda tr: tr.comp)
                   if tr.target == damage and 7 <= tr.comp <= 9]
        assert extents == pytest.approx([2 * h * s for h in p["box"]["half"]], rel=1e-5), clip
        if p["generator"] == "hand_spin":   # planted on its hand at her hand's height x s
            k = [b.name for b in rig.bones].index(hand)
            p0, p1 = (made.length * f for f in p["plant"])
            keyed = sorted({key[0] for tr in made.bones if rig.bones[tr.target].name == root for key in tr.keys})
            assert max(math.dist(origins(rig, made, t)[k], (0.0, 0.0, s * p["hand_z"]))
                       for t in keyed if p0 <= t <= p1) < 0.02, clip
    assert (lo.name, lo.fit, logic.damage) == ("booblord_spin", "odd" if model == "catalisk" else GOOD, 0.6)
    if model == "garret4":
        off, _, patch = ports.patch_spec_site(xbe, pc.STAFF_WALLS)
        assert (lo.cut, lo.walls_off, xbe[off:off + len(patch)] == patch) == (True, True, True)


# --- the weaponless townsfolk's throw (Modkit's Step 2.159b; D473, D474): the second WHITE set, W30, X42 ----------
MISS, MISS_Z = 9.0, -1.0
"""The kit's miss point (``kit.json``): 9 m on along the facing, 1 m under the thrower's point (about the floor;
D761: a throw dead ahead comes down through a critter's height)."""


def _table(xbe: bytes) -> dict:
    """X42's table as built; ``spawn``, ``release`` and ``mult`` the first throwing column's (the kit's one), each
    column's in ``spawns``, ``releases`` and ``mults``."""
    raw = _read(xbe, _symbol(xbe, pc.THROW_HOOK, "_player_model_throw_table"), throws.TABLE_SIZE)
    v = struct.unpack("<ii3f10fiif16s", raw[:0x58])
    keys = ("columns", "bone", "px", "py", "pz", "vh", "arc", "range", "miss", "cone", "tmin", "tmax", "pad", "life",
            "pushout", "anim", "landing", "radius", "species")
    out = dict(zip(keys, v))
    n = throws.COLUMNS
    per = struct.unpack(f"<{3 * n}f", raw[0x58:0x178])
    out["low"], out["seek"], out["miss_z"] = struct.unpack("<fif", raw[0x178:])
    out["spawns"], out["releases"], out["mults"] = per[:n], per[n:2 * n], per[2 * n:]
    first = (out["columns"] & -out["columns"]).bit_length() - 1
    out["spawn"], out["release"], out["mult"] = out["spawns"][first], out["releases"][first], out["mults"][first]
    return out


@pytest.mark.parametrize("species, kind, carrier", [
    ("town_male_6", "rock", False), ("town_female_4", "vase", True), ("town_female_1", "vase", False)])
def test_a_weaponless_townsperson_throws_in_its_second_white_set(usa, species, kind, carrier):
    """D473 (the owner: "Vase + rock (Recommended)": a real travelling projectile that hits enemies, as a second
    WHITE set): a weaponless townsperson's right1 plays the kit's t/throw, so WHITE cycles "Attack set 1/2 jab cross
    upper shove" and "Attack set 2/2 throw" (right1 in all four slots, X36); right1 throws along the facing (Aim
    angle 0), at Rate 1.0 over the whole clip, chaining at its tick 18 with garret4's damage multiplier 0.5, its X3
    and X13 bits clear (D474: the logic's reach the kick's box, 1.31 m). X42's table: right1, the spawn at tick 3 of
    20 (a carrier's at her take), the release at 11, the right hand, the townsman's rock (x0.25, 0.15 m, out 0.775 m
    at 16 m/s, clip slot 9) or the townswoman's vase (x0.46, 12 m/s, no clip), 14 m and 45 degrees, no seek (D761),
    0.25-1.2 s, a 0.15 m pad, 3 s, landing state 23, ``debug``; its radius X21's. town_female_4's vase rides her head
    until the take, is hidden to tick 15, shows at her right hand x0.4 and is on her head again at the clip's end;
    town_female_1 shows none (Modkit's Step 2.159b)."""
    logic = pc.AttackLogic()
    game = _swap(usa, species, sounds="garret4", logic=logic)
    built = game[XBE]
    anims = _doc(game[CONFIG]).keyed_section("attacks_anims")
    columns, picks = _played(game[CONFIG])
    right1 = columns.index("right1")
    assert picks[right1] == "t/throw" and [c for c, p in zip(columns, picks) if p == "t/throw"] == ["right1"]
    sets = pc.attack_sets(columns, picks)
    assert (sets[1:], pc.set_lines(picks, sets)) == ([[right1] * 4], [
        "Attack set 1/2\njab cross upper shove", "Attack set 2/2\nthrow"])

    def cell(row: str) -> float:
        return anims.find_cell("right1", row, right1).double_value
    a0, a1 = cell("Anim start"), cell("Anim end")
    assert (cell("Aim angle"), cell("Rate"), cell("Move start"), cell("Move end2"), cell("Damage multiplier")) == (
        0.0, 1.0, a0, a1, 0.5)
    assert cell("Move end1") == pytest.approx(a0 + 0.9 * (a1 - a0))
    bit = 1 << right1
    assert not round(_param(built, DAMAGE_MARKER, "_player_model_x3_columns")) & bit
    assert not round(_param(built, pc.ATTACK_BOX_HOOK, "_player_attack_ground_mask")) & bit
    assert logic.reach == pytest.approx(1.31, abs=0.01)
    assert ports.verify_trampoline_patch(built, pc.THROW_HOOK) == "applied"
    t = _table(built)
    radius = struct.unpack("<I", _read(built, _symbol(built, pc.THROW_HOOK, "_player_model_throw_radius_at"), 4))[0]
    assert radius == _symbol(built, pc.SEARCH_HOOK, pc.SEARCH_RADIUS_SYMBOL)
    rig = Rig.read(game[CHARACTERS], f"townspeople/{species[5:]}")
    names = [b.name for b in rig.bones]
    clip = named_clip(game[CHARACTERS], f"townspeople/{species[5:]}", "t/throw")
    take = round(t["spawn"] * 20 + 0.5)
    fixed = {"columns": bit, "release": _f32(10.5 / 20), "bone": names.index("right_hand"), "px": 0.0, "py": 0.0,
             "pz": 0.0, "range": 14.0, "miss": MISS, "miss_z": MISS_Z, "cone": _f32(math.cos(math.radians(45))),
             "tmin": 0.25, "tmax": _f32(1.2), "pad": _f32(0.15), "life": 3.0, "landing": 23, "mult": 0.5, "arc": 1.0,
             "low": throws.HAND_LOW, "seek": 0, "species": b"debug" + bytes(11)}
    assert {k: t[k] for k in fixed} == fixed
    if kind == "rock":
        assert (t["spawn"], t["vh"], t["anim"]) == (_f32(2.5 / 20), 16.0, 9)
        assert (t["radius"], t["pushout"]) == (pytest.approx(0.15, abs=1e-6), pytest.approx(0.775, abs=1e-6))
        return
    assert (t["vh"], t["anim"], t["radius"]) == (12.0, -1, pytest.approx(0.6 * 0.46, abs=1e-6))
    assert t["pushout"] == pytest.approx(0.575 + 0.6 * 0.46 + 0.05, abs=1e-6)
    vase, hand = names.index("vase_joint"), names.index("right_hand")
    scale = {tr.comp: tr.keys for tr in clip.bones if tr.target == vase and tr.comp >= 7}
    if not carrier:
        assert t["spawn"] == _f32(2.5 / 20) and {k[1] for keys in scale.values() for k in keys} == {0.0}
        return
    assert 3 <= take <= 9 and t["spawn"] == _f32((take - 0.5) / 20)
    head = names.index("head")
    before, at = origins(rig, clip, (take - 1) / 30), origins(rig, clip, take / 30)
    assert abs(math.dist(before[vase], before[head]) - 0.125) < 0.002
    offset = [a - b for a, b in zip(before[vase], before[head])]
    assert math.dist(at[hand], [h + o for h, o in zip(at[head], offset)]) < 0.15

    def shown(time: float) -> float:
        return [v for k, v, *_ in scale[7] if k <= time + 1e-6][-1]
    assert [shown(x / 30) for x in (0, take - 1, take, 14, 15, 20)] == [
        _f32(0.4), _f32(0.4), _f32(1e-12), _f32(1e-12), _f32(0.4), _f32(0.4)]
    back = origins(rig, clip, 15 / 30)
    assert math.dist(back[vase], back[hand]) < 1e-3
    end = origins(rig, clip, clip.length)
    assert abs(math.dist(end[vase], end[head]) - 0.125) < 0.002


def test_a_held_a_throws_once_and_waits_for_a_release_and_a_new_press(usa):
    """D566 (Modkit's Step 2.159d; the owner: "One throw per press (Recommended)"): presses are latched edges, so in
    the throw set, as in the melee set, a held A is the one press that started the swing: X33's held stamp no longer
    takes right1. L2 on town_male_6's build, the attack state's stamps (0x8D3D5-0x8D43C) in a right1 swing: A held,
    latched by the press that started the swing, is not stamped, so the chain at Move end1 finds none and the swing
    ends with its one throw; A released stamps nothing; a new press is stamped now and latched."""
    game = _swap(usa, "town_male_6", sounds="garret4")
    built = game[XBE]
    right1 = _played(game[CONFIG])[0].index("right1")
    now = 12.5
    swing = replace(l2.STANDING, state=0x100, move_flags=8, attack=right1, attack_anim=0x52 + right1,
                    anim_slot=0x52 + right1, clock=now)
    for a, latch, stamp in ((1.0, 1, -1.0), (0.0, 0, -1.0), (1.0, 0, now)):   # held, released, pressed again
        sim = l2.PlayerSim(built, replace(swing, attack_buttons=(a, 0.0), attack_latches=(latch, 0)))
        sim.call(0x8D3D5, regs={"ebp": sim.at["entity"], "edi": sim.at["input"]}, until=0x8D43C)
        assert (struct.unpack("<3d", sim.uc.mem_read(sim.at["entity"] + 0xA0, 24)),
                sim.uc.mem_read(sim.at["controller"] + 0x48, 2)) == ((stamp, -1.0, -1.0), bytes((int(a > 0), 0))), (
            a, latch)


@pytest.mark.parametrize("species, kind", [("town_male_6", "rock"), ("town_female_4", "vase")])
def test_the_throws_projectile_is_debug_wearing_a_harmless_clone_of_the_boulder_or_the_vase(usa, species, kind):
    """W30 (Modkit's Step 2.159b; D473): the throw's projectile is the spare species ``debug`` (in no level): its rows
    in critters_engine, critters_critter_data, critters_damage and critters_walking read as the earth guardian's
    boulder's but its body, "debug", and its scale, the throw's (x0.25 a townsman's rock, x0.46 her vase); every
    other species' rows are vanilla but the player's. characters/debug is a copy of bosses/boulder or her LOD0 vase
    alone (one bone, vase_joint; one group of 202 vertices; the boulder's m_alpha), with the boulder's idle, run and
    die byte for byte. Its fx_default's breakEffectShape loads characters/debug/fx/fx_break, whose damage field deals
    0 by value and by timer1's link; the vase's seven shards are x0.54 and they and its dust draw new textures. The
    boulder's body, clips and graphs are vanilla, index.xbr names the six new entries, and a file already holding
    characters/debug is refused."""
    game = _swap(usa, species, sounds="garret4")
    vanilla = {name: _vanilla(usa, name) for name in (CHARACTERS, CONFIG, INDEX)}
    grown, config = game[CHARACTERS], _doc(game[CONFIG])
    old = _doc(vanilla[CONFIG])
    scale = 0.25 if kind == "rock" else 0.4 * 1.15

    def value(cell):
        return None if cell is None else (cell.type_code, cell.double_value if cell.type_code == 1 else
                                          cell.string_value if cell.type_code == 2 else None)
    for section in throws.SECTIONS:
        k, v = config.keyed_section(section), old.keyed_section(section)
        for prop in k.row_names():
            if prop in ("name", ""):
                continue
            want = ((2, "debug") if (section, prop) == ("critters_engine", "body") else
                    (1, pytest.approx(scale)) if (section, prop) == ("critters_engine", "scale") else
                    value(v.find_cell("boulder", prop)))
            assert value(k.find_cell("debug", prop)) == want, (section, prop)
        for c, col in enumerate(k.col_names()):
            if col not in ("garret4", "debug"):
                assert [value(k.read_cell(c, r)) for r in range(len(k.row_names()))] == [
                    value(v.read_cell(c, r)) for r in range(len(v.row_names()))], (section, col)
    toc, old_toc = parse_toc(grown), parse_toc(vanilla[CHARACTERS])
    at = {n.casefold(): i for i, n in named_resources(grown).items()}
    was = {n.casefold(): i for i, n in named_resources(vanilla[CHARACTERS]).items()}

    def payload(data, t, i):
        return bytes(data[t[i].file_offset:t[i].file_offset + t[i].size])
    for key, i in was.items():
        if key == "characters/bosses/boulder" or key.startswith("characters/bosses/boulder/"):
            assert payload(grown, toc, at[key]) == payload(vanilla[CHARACTERS], old_toc, i), key
    for clip in throws.CLIPS:
        assert payload(grown, toc, at[f"characters/debug/{clip}"]) == payload(
            vanilla[CHARACTERS], old_toc, was[f"characters/bosses/boulder/{clip}"]), clip
    assert named_clip(grown, "debug", "die").markers
    body = read_asset(grown, "debug")
    if kind == "rock":
        boulder = read_asset(vanilla[CHARACTERS], "bosses/boulder")
        assert ([b.record[8:] for b in body.bones], [m.record[8:] for m in body.markers]) == (
            [b.record[8:] for b in boulder.bones], [m.record[8:] for m in boulder.markers])
        assert [[(g.palette, g.vertices, g.triangles) for g in lod.groups] for lod in body.lods] == [
            [(g.palette, g.vertices, g.triangles) for g in lod.groups] for lod in boulder.lods]
    else:
        assert ([b.name for b in body.bones], [m.name for m in body.markers], len(body.lods)) == (
            ["vase_joint"], ["m_alpha"], 1)
        assert [(g.palette, len(g.vertices)) for g in body.lods[0].groups] == [([0], 202)]
    schema = Schema(game[XBE])
    default = Graph(grown, toc, toc[at[throws.FX_DEFAULT]], schema)
    assert default.pstr(default.recs[3], 0x1C) == throws.FX_BREAK
    brk = Graph(grown, toc, toc[at[throws.FX_BREAK]], schema)
    src = Graph(vanilla[CHARACTERS], old_toc, old_toc[was["characters/bosses/boulder/fx/fx_boulder_break"]], schema)
    damage = schema.types["platform"].attrs.index("damage")
    assert brk.attrs(19)[damage] == 0.0 and src.attrs(19)[damage] == 1.0
    assert [lk.factor for lk in brk.links(1) if lk.dst == 19 and lk.dst_plug == damage] == [0.0]
    assert [brk.attr_named(r, "scaleX") for r in range(2, 16, 2)] == [_f32(0.54) if kind == "vase" else 1.0] * 7

    def surfaces(data: bytes, t, i: int) -> list[int]:   # the textures a graph's copies draw, by size and tag
        return sorted(t[j].size for j in closure(data, [i]) if t[j].tag == "surf")
    drawn = surfaces(grown, toc, at[throws.FX_BREAK])
    assert len(drawn) == len(surfaces(vanilla[CHARACTERS], old_toc, was["characters/bosses/boulder/fx/fx_boulder_break"]))
    assert all(j < len(old_toc) for j in closure(grown, [at[throws.FX_BREAK]]) if toc[j].tag == "surf") == (
        kind == "rock")
    names = {r.key.casefold() for r in parse_index_xbr(game[INDEX]).records}
    added = {throws.BODY, throws.FX_DEFAULT, throws.FX_BREAK, *(f"{throws.BODY}/{c}" for c in throws.CLIPS)}
    assert {n for n in names if n.startswith(throws.BODY)} == added
    assert not added & {r.key.casefold() for r in parse_index_xbr(vanilla[INDEX]).records}
    data = vanilla[CHARACTERS]
    throw = kit_style(data, read_body(data, "townspeople/male_6" if kind == "rock" else "townspeople/female_4")).throw
    with pytest.raises(ValueError, match="already holds characters/debug"):
        throws.write_projectile(grown, game[INDEX], game[XBE], throw)


def _x42(built: bytes) -> SimpleNamespace:
    """X42 under Unicorn on ``built`` (L2; the game's calls stubbed): the PlayerControl at ``pc``, the player at
    ``player`` (his feet at ``feet``, drawn ``s``, the right hand at ``hand``: its palm ``palm``), nine critter pages,
    each tick's game calls logged (``log``) and the stubs' answers in ``mode``; ``tick`` runs one PlayerControl tick
    of a ``column`` swing at a clip fraction and a clock, ``slot`` reads a ring slot, ``owner`` calls the owner
    interface, ``link``/``unlink`` make the engine's list moves."""
    t = _table(built)
    state = _symbol(built, pc.THROW_HOOK, pc.THROW_STATE)
    radius = _symbol(built, pc.SEARCH_HOOK, pc.SEARCH_RADIUS_SYMBOL)
    entry = pc.THROW_HOOK.va + 5 + struct.unpack_from("<i", built, ports.va_to_file(pc.THROW_HOOK.va) + 1)[0]
    base = 0x20000000
    ctl, clock, player, pvt, anim, bones, species, world, world2, cvt, frame, ours, stubs = (
        base + 0x1000 * k for k in (0, 1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15))
    critters = [base + 0x20000 + 0x1000 * k for k in range(9)]
    centre_stub, message_stub, notify_stub = stubs, stubs + 0x100, stubs + 0x200
    sim = l2.Sim(built)
    sim.uc.mem_map(base, 0x20000)
    for c in critters:
        sim.uc.mem_map(c, 0x1000)
    feet, s = (10.0, 20.0, 0.0), 1.15
    hand = (0.3, 0.2, 1.3)
    palm = tuple(f + s * h for f, h in zip(feet, hand))
    for at, data in ((ctl + 0xC, struct.pack("<I", clock)), (ctl + 0x20, struct.pack("<I", player)),
                     (ctl + 0x138, struct.pack("<f", 0.25)), (player, struct.pack("<I", pvt)),
                     (pvt + 0x80, struct.pack("<I", centre_stub)), (player + 0x154, struct.pack("<II", world, 0x77)),
                     (player + 0x15C, struct.pack("<3f", 10.0, 20.0, 1.0)),
                     (player + 0x178, struct.pack("<II", species, anim)),
                     (player + 0x188, struct.pack("<f5f", s, 0.0, 0.0, 0.0, 1.0, 0.0)), (anim + 8, struct.pack("<I", bones)),
                     (bones + 0xB0 * t["bone"] + 0xA0, struct.pack("<3f", *hand)), (player + 0x210, struct.pack("<i", 100)),
                     (player + 0x220, struct.pack("<I", 0x1234)), (cvt + 0xB4, struct.pack("<I", message_stub))):
        sim.uc.mem_write(at, data)
    # apply_damage's notify as the game makes it (0x446E8): the owner's slot 1 with the critter's slot, RET 0xC
    sim.uc.mem_write(notify_stub, bytes.fromhex("8b4c2404ffb1f40100008b89ec01000083e9048b11ff5204c20c00"))
    log: dict[str, list] = {k: [] for k in ("tail", "spawn", "find", "send", "message", "damage")}
    mode = {"spawn": "now", "next": 0, "count": 1, "offset": (0.0, 6.0, 0.2), "notify": False}

    def ret(uc, eax: int, pop: int) -> None:
        esp = sim.reg("esp")
        uc.reg_write(UC_X86_REG_EAX, eax & 0xFFFFFFFF)
        uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)

    def args(n: int) -> tuple:
        return struct.unpack(f"<{n}I", sim.uc.mem_read(sim.reg("esp") + 4, 4 * n))

    def link(c: int, owner: int, slot: int) -> None:
        sim.uc.mem_write(c, struct.pack("<I", cvt))
        sim.uc.mem_write(c + 0x168, struct.pack("<I", 0x4041))
        sim.uc.mem_write(c + 0x1EC, struct.pack("<II", owner + 4, sim.u32(owner + 4)))
        sim.uc.mem_write(c + 0x1F4, struct.pack("<i", slot))
        sim.uc.mem_write(owner + 4, struct.pack("<I", c + 0x1EC))

    def unlink(c: int) -> None:   # the engine's: the node out of its owner's list
        node, at = c + 0x1EC, state + 4
        while sim.u32(at):
            if sim.u32(at) == node:
                sim.uc.mem_write(at, struct.pack("<I", sim.u32(node + 4)))
                return
            at = sim.u32(at) + 4

    def hook(va: int):
        def wrap(fn):
            sim.uc.hook_add(UC_HOOK_CODE, lambda uc, a, size, _: fn(uc), begin=va, end=va)
            return fn
        return wrap

    @hook(0x8C450)
    def _(uc):   # player_move_fx: EAX the PlayerControl, the frame, RET 4
        log["tail"].append((sim.reg("eax"), args(1)[0]))
        ret(uc, 0, 4)

    @hook(0x42200)
    def _(uc):   # critter_model_matrix: ESI the out, the critter, RET 4
        uc.mem_write(sim.reg("esi"), struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *feet, 1))
        ret(uc, 0, 4)

    @hook(0x45E30)
    def _(uc):   # species_get_by_name: fastcall, plain RET
        assert (sim.cstr(sim.reg("ecx")), sim.reg("edx")) == ("debug", 0)
        ret(uc, ours, 0)

    @hook(0x45C10)
    def _(uc):   # critter_spawn(desc, world, flag): RET 0xC
        desc, w, flag = args(3)
        log["spawn"].append((struct.unpack("<4I3f4fI2i", uc.mem_read(desc, 0x38)), w))
        uc.mem_write(flag, struct.pack("<i", 0 if mode["spawn"] == "fail" else 1))
        if mode["spawn"] != "now":
            ret(uc, 0, 12)
            return
        c = critters[mode["next"]]
        mode["next"] += 1
        link(c, sim.u32(desc), sim.u32(desc + 4))
        ret(uc, c, 12)

    @hook(0x7EBB0)
    def _(uc):   # attack_target_find(critter, facing, out): RET 0xC
        who, facing, out = args(3)
        log["find"].append((who, round(struct.unpack("<f", struct.pack("<I", facing))[0], 6), sim.f32(radius)))
        uc.mem_write(out, struct.pack("<i3f", mode["count"], *mode["offset"]))
        ret(uc, 0, 12)

    @hook(0x460B0)
    def _(uc):   # hit_send(box, message): RET 8
        box, msg = args(2)
        m = struct.unpack("<40f", uc.mem_read(box, 160))
        log["send"].append((m[12:15], m[35:38], struct.unpack("<IIIf", uc.mem_read(msg, 16)),
                            uc.mem_read(species + 0x7C, 1)[0]))
        ret(uc, 0, 8)

    @hook(0x44640)
    def _(uc):   # apply_damage(it, hp, flag): RET 0xC
        log["damage"].append(args(3))
        if not mode["notify"]:
            ret(uc, 0, 12)
            return
        unlink(args(1)[0])
        uc.reg_write(UC_X86_REG_EIP, notify_stub)

    @hook(centre_stub)
    def _(uc):   # the player's vtable +0x80: thiscall(out), RET 4
        out = args(1)[0]
        uc.mem_write(out, struct.pack("<3f", 10.0, 20.0, 1.0))
        ret(uc, out, 4)

    @hook(message_stub)
    def _(uc):   # a critter's vtable +0xB4: thiscall(message), RET 4; a thrown AI's velocity := v (0x38AE4)
        msg = args(1)[0]
        log["message"].append((sim.reg("ecx"), struct.unpack("<II3fii", uc.mem_read(msg, 28)),
                               struct.unpack("<3f", uc.mem_read(sim.reg("ecx") + 0x15C, 12))))
        if ai := sim.u32(sim.reg("ecx") + 0x180):
            uc.mem_write(ai + 0x24, bytes(uc.mem_read(msg + 8, 12)))
        ret(uc, 0, 4)

    def tick(frac: float, now: float, *, on: bool = True, column: int = 14) -> None:
        sim.uc.mem_write(ctl + 0x94, struct.pack("<I", 0x100 if on else 0))
        sim.uc.mem_write(ctl + 0x134, struct.pack("<i", column))
        sim.uc.mem_write(ctl + 0x178, struct.pack("<f", frac))
        sim.uc.mem_write(player + 0x200, struct.pack("<i", 0x52 + column))
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", now))
        kept = {"ebx": 0x11, "esi": 0x22, "ebp": 0x44}
        sim.call(entry, regs={**kept, "edi": ctl, "eax": ctl}, args=(frame,), until=l2._RETURN)
        assert {r: sim.reg(r) for r in (*kept, "edi", "esp")} == {**kept, "edi": ctl, "esp": l2._STACK_TOP - 0x100}

    def slot(k: int) -> tuple:
        return struct.unpack("<Ii", sim.uc.mem_read(state + 0x78 + 0x40 * k, 8))

    def owner(k: int, *a) -> int:   # call the owner's slot k: thiscall on X42's object, popping its arguments
        eax = sim.call(sim.u32(state + 8 + 4 * k), regs={"ecx": state}, args=a, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100
        return eax

    def f3(va: int) -> tuple:
        return struct.unpack("<3f", sim.uc.mem_read(va, 12))
    return SimpleNamespace(**{k: v for k, v in locals().items() if k != "built"})


def test_x42_throws_a_critter_from_the_hand_as_the_players_hit_and_forgets_cut_or_dead_throws(usa):
    """X42 (Modkit's Step 2.159b; D473) at 0x8C3C3 under Unicorn on town_male_6's build (L2; its game calls
    stubbed): each tick it makes the game's call first. A right1 swing reaching its spawn fraction spawns ``debug``
    (its owner X42's object, slot 0, the player's cell, the palm, his quaternion, HP -1/-1) with its no-hit window
    1e9 s and its target kinds cleared; the owner's slots answer held (the palm, his rotation), the clip 1, no
    leash, home his point. At the release it leaves from the palm pushed out to 0.775 m from his axis straight along
    the facing (D761: no target search), with v landing it at the miss point (message 10, clip 9, landing 23).
    Flying, each tick one hit_send of the swept box padded by 0.15 + 0.15 m as the player's hit with his
    hitsThroughWalls set for the call only; after its death notify one last send at its death point, then the slot
    is free. A swing cut while held drops it and sends no hit; past 3 s of game time apply_damage(it, 0, 1) ends it.
    A node gone from the list without a notify is forgotten unread; a queued spawn is adopted from the list; a fifth
    swing ends the oldest flying one (once a swing, none while a life that ran out this tick has its slot ENDED) and
    throws on the next tick, its slot freed by the notify (AZ-686); a new world empties the ring."""
    built = _swap(usa, "town_male_6", sounds="garret4")[XBE]
    assert l1.check(_vanilla(usa, XBE), built) == []
    x = _x42(built)
    (critters, f3, frame, link, log, mode, ours, owner, palm, ctl, player,
     radius, sim, slot, species, state, t, tick, unlink, world, world2) = (
        x.critters, x.f3, x.frame, x.link, x.log, x.mode, x.ours, x.owner,
        x.palm, x.ctl, x.player, x.radius, x.sim, x.slot, x.species, x.state,
        x.t, x.tick, x.unlink, x.world, x.world2)

    # the game's call first, every tick; nothing spawns before the spawn fraction
    tick(0.05, 1.0)
    assert log["tail"] == [(ctl, frame)] and log["spawn"] == []
    # the spawn: in the hand, never a target, immune
    tick(t["spawn"] + 0.01, 1.03)
    (desc, w), = log["spawn"]
    c0 = critters[0]
    assert (desc[:4], w, desc[11:]) == ((state, 0, ours, 0x77), world, (0, -1, -1))
    assert desc[4:7] == pytest.approx(palm) and desc[7:11] == (0.0, 0.0, 0.0, 1.0)
    assert (sim.f32(c0 + 0x1E0), sim.u32(c0 + 0x168), slot(0)) == (1e9, 0x0001, (c0, 1))
    out = frame + 0x100
    assert (owner(4, 0), owner(5, 0), owner(6)) == (1, 1, 0)
    owner(2, 0, out, out + 0x10)
    assert f3(out) == pytest.approx(palm) and struct.unpack("<16f", sim.uc.mem_read(out + 0x10, 64)) == (
        1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    assert owner(3, out, 0) == out and f3(out) == (0.0, 0.0, 0.0)
    assert owner(0, out, 0) == out and f3(out) == (10.0, 20.0, 1.0)
    # the release: pushed out, straight along the facing (+y), solved to land 9 m on, 1 m under his point
    tick(t["release"] + 0.01, 1.4)
    (who, msg, at), = log["message"]
    p0 = (10.0 + 0.775 * 0.345 / math.hypot(0.345, 0.23), 20.0 + 0.775 * 0.23 / math.hypot(0.345, 0.23), palm[2])
    assert (who, msg[:2], msg[5:], log["find"]) == (c0, (10, player), (9, 23), [])
    assert at == pytest.approx(p0, abs=1e-5) and sim.f32(radius) == 3.0
    target, v = (p0[0], p0[1] + MISS, 1.0 + MISS_Z), msg[2:5]
    flight = max(0.25, min(1.2, MISS / 16.0))
    assert [p0[i] + v[i] * flight - (4.9 * flight * flight if i == 2 else 0) for i in range(3)] == pytest.approx(
        target, abs=1e-4)
    # flying: one send a tick as the player's, his walls flag around it, the window re-armed
    sim.uc.mem_write(c0 + 0x15C, struct.pack("<3f", 10.4, 21.0, 1.6))
    sim.uc.mem_write(c0 + 0x1E0, struct.pack("<f", 0.0))
    tick(0.6, 1.433)
    (centre, half, message, walls), = log["send"]
    assert (message, walls, sim.u32(species + 0x7C), sim.f32(c0 + 0x1E0)) == ((3, player, 0x1234, 0.5), 1, 0, 1e9)
    assert centre == pytest.approx(tuple((a + b) / 2 for a, b in zip(p0, (10.4, 21.0, 1.6))), abs=1e-5)
    assert half == pytest.approx(tuple(abs(a - b) + 0.3 for a, b in zip(p0, (10.4, 21.0, 1.6))), abs=1e-5)
    # its death: one last send at the death point, then free
    owner(1, 0)
    unlink(c0)
    tick(0.7, 1.466)
    assert log["send"][-1][:2] == (pytest.approx((10.4, 21.0, 1.6)), pytest.approx((0.6, 0.6, 0.6)))
    assert slot(0) == (0, 0)

    # another throw, straight again; then cut while held: dropped
    for frac, now in ((0.05, 2.0), (t["spawn"] + 0.01, 2.03), (t["release"] + 0.01, 2.06)):
        tick(frac, now)
    c1 = critters[1]
    who, msg, at = log["message"][-1]
    v, flight = msg[2:5], max(0.25, min(1.2, MISS / 16.0))
    assert who == c1 and [at[i] + v[i] * flight - (4.9 * flight * flight if i == 2 else 0) for i in range(3)] == (
        pytest.approx((at[0], at[1] + MISS, 1.0 + MISS_Z), abs=1e-4))
    tick(0.05, 2.1)   # a new swing
    tick(t["spawn"] + 0.01, 2.13)
    c2, sends = critters[2], len(log["send"])
    tick(0.0, 2.16, column=0)   # cut: the jab
    who, msg, at = log["message"][-1]
    assert (who, msg[:5], msg[5:]) == (c2, (10, player, 0.0, 0.0, 0.0), (9, 23)) and at == pytest.approx(p0, abs=1e-5)
    sim.uc.mem_write(c2 + 0x15C, struct.pack("<3f", 10.6, 20.4, 0.6))
    tick(0.1, 2.2, column=0)
    flying = f3(c1 + 0x15C)   # c1 flying sends each tick; the dropped c2 none
    assert [(m[0], m[2][1]) for m in log["send"][sends:]] == [(pytest.approx(flying), player)] * 2
    # past 3 s of game time each ends; c1 gone with no notify and unreadable is forgotten
    unlink(c1)
    sim.uc.mem_unmap(c1, 0x1000)
    tick(0.1, 5.3, column=0)
    assert (log["damage"], slot(0), slot(1)) == ([(c2, 0, 1)], (0, 0), (c2, 4))
    owner(1, 1)
    unlink(c2)
    tick(0.1, 5.33, column=0)
    assert all(slot(k) == (0, 0) for k in range(4))

    # a queued spawn is adopted from the list and thrown
    mode["spawn"], mode["offset"] = "queue", (0.0, 6.0, 0.2)
    tick(0.05, 6.0)
    tick(t["spawn"] + 0.01, 6.03)
    assert slot(0) == (0, 5)
    link(critters[3], state, 0)   # the world builds it
    mode["next"] = 4
    tick(t["spawn"] + 0.05, 6.06)
    assert (slot(0), sim.f32(critters[3] + 0x1E0), sim.u32(critters[3] + 0x168)) == ((critters[3], 1), 1e9, 1)
    tick(t["release"] + 0.01, 6.1)
    assert log["message"][-1][0] == critters[3] and slot(0) == (critters[3], 2)
    # four flying: a fifth swing ends the oldest, once, and throws on the next tick (AZ-686)
    mode["spawn"] = "now"
    for k in range(3):
        now = 6.2 + 0.2 * k
        tick(0.05, now)
        tick(t["spawn"] + 0.01, now + 0.03)
        tick(t["release"] + 0.01, now + 0.06)
    assert [slot(k)[1] for k in range(4)] == [2] * 4
    tick(0.05, 7.0)
    tick(t["spawn"] + 0.01, 7.03)
    tick(t["spawn"] + 0.03, 7.06)   # its notify not yet in: nothing more ended, nothing thrown
    assert (log["damage"][1:], mode["next"]) == ([(critters[3], 0, 1)], 7)
    owner(1, 0)   # apply_damage's notify (0x446E8) and unlink
    unlink(critters[3])
    tick(t["spawn"] + 0.05, 7.09)
    assert (len(log["damage"]), mode["next"], slot(0)) == (2, 8, (critters[7], 1))
    # a life that runs out on a full ring's spawn tick (its notify at once) frees the slot: nothing more ended
    tick(t["release"] + 0.01, 7.12)
    mode["notify"] = True
    tick(0.05, 9.2)
    tick(t["spawn"] + 0.01, 9.27)   # critters[4], released at 6.26, ends past its 3 s
    assert (log["damage"][2:], mode["next"], slot(1)) == ([(critters[4], 0, 1)], 8, (critters[4], 3))
    tick(t["spawn"] + 0.03, 9.3)
    assert (len(log["damage"]), mode["next"], slot(1)) == (3, 9, (critters[8], 1))
    # a new world empties the ring and the list
    sim.uc.mem_write(player + 0x154, struct.pack("<I", world2))
    tick(0.05, 9.33, on=False)
    assert all(slot(k) == (0, 0) for k in range(4)) and sim.u32(state + 4) == 0


def test_x42_throws_straight_along_the_facing_unless_its_table_seeks(usa):
    """AZ-757, D761 (Modkit's Step 2.194b; the owner: "for the current ranged attacks they should not seek towards
    enemies"): with an enemy 27 degrees off the facing 6.7 m out, X42 (L2 on town_male_6's build) searches nothing
    and throws along the facing, landing at the kit's miss point. Its table's ``seek`` (a projectile ``effects``
    row's ``"seek": true``) aims as before: attack_target_find with X21's radius raised to 14 m (3 m after), v
    landing it on his bounds centre plus the result's offset; an enemy 50 degrees off is outside the 45 degree
    cone: the miss point."""
    row, = fx_templates.effects("row", [{"template": "fireball", "columns": ["basic1"], "seek": True}])
    plan = throws.Plan((throws.Shot(0, 20, 3, 11, 0.5),), 0.25, 0.15, 0.775, 0, 16.0, 1.0, 14.0, MISS, 45.0,
                       (0.25, 1.2), 0.15, 3.0, 9, 23, seek=row.seek, miss_z=MISS_Z)
    assert struct.unpack_from("<if", plan.table(), 0x17C) == (1, MISS_Z)
    built = _swap(usa, "town_male_6", sounds="garret4")[XBE]
    x = _x42(built)
    t, log = x.t, x.log
    p0 = (10.0 + 0.775 * 0.345 / math.hypot(0.345, 0.23), 20.0 + 0.775 * 0.23 / math.hypot(0.345, 0.23), x.palm[2])

    def released(now: float) -> tuple:   # one swing's throw: its release velocity
        for frac, dt in ((0.05, 0.0), (t["spawn"] + 0.01, 0.03), (t["release"] + 0.01, 0.06)):
            x.tick(frac, now + dt)
        _, msg, at = log["message"][-1]
        assert at == pytest.approx(p0, abs=1e-5)
        return msg[2:5]
    miss = (p0[0], p0[1] + MISS, 1.0 + MISS_Z)

    def landing(v: tuple, target: tuple) -> list:
        flight = max(0.25, min(1.2, math.dist(target[:2], p0[:2]) / 16.0))
        return [p0[i] + v[i] * flight - (4.9 * flight * flight if i == 2 else 0) for i in range(3)]
    x.mode["offset"] = (3.0, 6.0, 0.2)
    v = released(1.0)
    assert (log["find"], v[0], landing(v, miss)) == ([], 0.0, pytest.approx(miss, abs=1e-4))
    x.sim.uc.mem_write(_symbol(built, pc.THROW_HOOK, "_player_model_throw_table") + 0x17C, struct.pack("<i", 1))
    v = released(1.5)
    assert (log["find"], x.sim.f32(x.radius)) == ([(x.player, 0.25, 14.0)], 3.0)
    assert landing(v, (13.0, 26.0, 1.2)) == pytest.approx((13.0, 26.0, 1.2), abs=1e-4)
    x.mode["offset"] = (6.0, 5.0, 0.2)
    v = released(2.0)
    assert (len(log["find"]), v[0], landing(v, miss)) == (2, 0.0, pytest.approx(miss, abs=1e-4))


# --- the effects templates' rows (Modkit's Steps 2.167b-2.167g; D538): projectiles W30 makes, shields and beams --
EFFECTS = "tests/fixtures/effects.json"
"""G3's firelord case's recipe file (its ``files``, ``tests/goldens/cases.json``): Modkit's fixture of the same name,
a fireball (firelord), an ice shard (icelord), our own arrow (archer) and a bubble, a dome and a laser
(shieldlord)."""


@functools.cache
def _effect_recipes() -> str:
    cases = json.loads((Path(__file__).with_name("goldens") / "cases.json").read_text(encoding="utf-8"))
    return json.dumps(next(case["files"][EFFECTS] for case in cases["pipelines.json"].values()
                           if EFFECTS in case.get("files", {})))


def _effect_variant(name: str, row: bool = True):
    """:data:`EFFECTS`' recipe ``name`` (without its ``effects`` rows unless ``row``)."""
    variant = load_variants(_effect_recipes(), "effects.json")[name]
    return variant if row else replace(variant, effects=())


@functools.lru_cache(maxsize=4)
def _effects(image: str, name: str, row: bool = True) -> dict[str, bytes]:
    """:data:`EFFECTS`' recipe ``name`` built from ``image`` (:func:`_swap`; without its rows unless ``row``)."""
    return _swap(image, name, worn=_effect_variant(name, row))


def _payloads(data: bytes) -> list[bytes]:
    return [bytes(data[e.file_offset:e.file_offset + e.size]) for e in parse_toc(data)]


@pytest.mark.parametrize("name, template", [("firelord", "fireball"), ("icelord", "ice_shard"), ("archer", "arrow")])
def test_an_effects_row_throws_its_template_as_debugs_own_copies_and_edits_no_vanilla_graph(usa, name, template):
    """D538's E2 (Modkit's Steps 2.167b, 2.180; the owner: "create new effects and duplicate effects ... without
    replacing assets"): a recipe's projectile row makes W30's ``debug`` wear its body and graphs as copies, and the
    clone invariant holds: against the recipe built without the row every characters.xbr entry is byte for byte,
    fx.xbr is (but for X32's flash on a body X32 doesn't serve, D700), and the new names are ``characters/debug``
    and under it alone (index.xbr's too, and the flash's). ``debug``'s body is a copy of the template's (the
    boulder's for the fireball, its texture recoloured in a new surf; the ice shard's whole, m_alpha grown after its
    three markers and keyed by its die) or our own arrow (one group of 36 triangles, ARROW_LENGTH along +y); its
    default fx the boulder's clone with the template's sets grafted under effectOrigin, each emitter on at its show
    rate, its break the template's impact copied whole (the arrow's none); its config scale draws the body ``size``
    m across and its collisionRadius x the scale is the smaller of the radius and half the size; model inspect's
    own runs count its runs."""
    t = fx_templates.TEMPLATES[template]
    game, bare = _effects(str(usa), name), _effects(str(usa), name, False)
    variant = _effect_variant(name)
    v = variant.effects[0].values
    flash = [] if ports.verify_trampoline_patch(bare[XBE], pc.HIT_FX_HOOK) == "applied" or t.hit is None else (
        pc.hit_flash(_vanilla(usa, FX), _vanilla(usa, XBE)))
    assert game[FX] == append_resources(bare[FX], flash)
    grown, before = game[CHARACTERS], bare[CHARACTERS]
    kept = _payloads(before)
    assert _payloads(grown)[:len(kept)] == kept
    added = {n.casefold() for i, n in named_resources(grown).items() if i >= len(kept)}
    assert added == {"characters/debug", *(f"characters/debug/{c}" for c in throws.CLIPS), throws.FX_DEFAULT} | (
        {throws.FX_BREAK} if t.impact else set())
    old_index = {r.key.casefold() for r in parse_index_xbr(bare[INDEX]).records}
    assert {r.key.casefold() for r in parse_index_xbr(game[INDEX]).records} - old_index == added | (
        {pc.HIT_FLASH} if flash else set())
    vanilla = _vanilla(usa, CHARACTERS)
    body = read_asset(grown, "debug")
    source = throws.source_body(t)
    if "authored" in t.body:
        group, = body.lods[0].groups
        lo, hi = (min(vx.position[1] for vx in group.vertices), max(vx.position[1] for vx in group.vertices))
        assert (len(body.lods), len(group.triangles), group.palette, [b.name for b in body.bones]) == (
            1, 36, [0], ["root"]) and hi - lo == pytest.approx(throws.ARROW_LENGTH, abs=1e-6)
    else:
        src = read_asset(vanilla, source)
        assert [[(g.palette, len(g.vertices), len(g.triangles)) for g in lod.groups] for lod in body.lods] == [
            [(g.palette, len(g.vertices), len(g.triangles)) for g in lod.groups] for lod in src.lods]
        toc = parse_toc(grown)
        gshd, row = body.lods[0].groups[0].material
        stage = dict(refs_in(grown, toc, gshd))[fx_edit.material_row_at(_payloads(grown)[gshd], row) + 100]
        assert (gshd >= len(kept), stage >= len(kept), toc[stage].tag) == (True, source == throws.BOULDER, "surf")
    markers = [m.name for m in body.markers]
    assert markers[-1] == "m_alpha" and len(markers) == (4 if source == "ice_shard" else 1)
    assert [tr.target for tr in named_clip(grown, "debug", "die").markers] == [len(markers) - 1] * 2
    schema, toc = Schema(game[XBE]), parse_toc(grown)
    at = {n.casefold(): i for i, n in named_resources(grown).items()}
    fx = Graph(grown, toc, toc[at[throws.FX_DEFAULT]], schema)
    names = [rec[1] for g in t.sets for rec in fx_templates.GRAFTS[g].records]
    assert fx.names[4:] == names and all(fx.parent(4 + k) in range(4, 4 + len(names)) or fx.parent(4 + k) == 0
                                         for k in range(len(names)) if fx.is_dag(4 + k))
    for s in t.show:
        assert fx.attr_named(4 + names.index(s["record"]), s["attr"]) == s["value"]
    if t.impact:
        assert fx.pstr(fx.recs[3], 0x1C) == throws.FX_BREAK
        src = vanilla if t.impact["archive"] == "characters" else _vanilla(usa, FX)
        stoc = parse_toc(src)
        donor = Graph(src, stoc, stoc[{n.casefold(): i for i, n in named_resources(src).items()}[t.impact["key"]]],
                      schema)
        copy = Graph(grown, toc, toc[at[throws.FX_BREAK]], schema)
        assert (copy.names, copy.types, [copy.attrs(r) for r in range(len(copy.recs)) if copy.recs[r] is not None]) == (
            donor.names, donor.types, [donor.attrs(r) for r in range(len(donor.recs)) if donor.recs[r] is not None])
    else:
        assert [lk.factor for lk in fx.links(2)] == [0.0]
    engine = _doc(game[CONFIG]).keyed_section("critters_engine")
    scale = engine.find_cell("debug", "scale").double_value
    span = max(h - lo for lo, h in zip(*mesh_bounds(grown, "debug")))
    assert scale * span == pytest.approx(v["size"]) and engine.find_cell(
        "debug", "collisionRadius").double_value * scale == pytest.approx(min(v["radius"], v["size"] / 2))
    worn = _body(vanilla, _vanilla(usa, CONFIG), variant.base)
    with_row, without = (model_inspect.own_runs(g[CHARACTERS], worn) for g in (game, bare))
    assert with_row["bytes"] > without["bytes"]


def test_a_shield_or_beam_row_plays_its_template_as_the_players_own_graph_and_edits_no_vanilla_graph(usa):
    """D538's E3 (Modkit's Step 2.167c): a recipe's shield and beam rows (shieldlord: keylord with a bubble on
    basic1, a dome on the finish, a laser on basic2) each add a graph of their own,
    ``characters/keylord/v/fx/fx_<template>_<k>``, and the clone invariant holds: against the recipe built without
    them every characters.xbr entry is byte for byte, fx.xbr is, and the new names are those three graphs alone
    (index.xbr's too). Each graph is the empty host's clone: its effectOrigin root, the holder under it, the
    template's sets after them; the bubble's holder bound to m_root and renamed so, the dome's unbound at the feet
    sized by keylord's height over garret4's, the laser's unbound at the action point scaled 1 / its drawn scale;
    each show attribute 0 (X38 writes it), each param's write at the row's value (the laser's range ``auto`` its
    basic2 box's reach ahead), every platform's gameSolid and damage 0; model inspect's own runs count them."""
    game, bare = _effects(str(usa), "shieldlord"), _effects(str(usa), "shieldlord", False)
    variant = _effect_variant("shieldlord")
    assert game[FX] == bare[FX]
    grown, before = game[CHARACTERS], bare[CHARACTERS]
    kept = _payloads(before)
    assert _payloads(grown)[:len(kept)] == kept
    keys = [fx_ring.bound_key("keylord", e.template.name, k) for k, e in enumerate(variant.effects)]
    added = {n.casefold() for i, n in named_resources(grown).items() if i >= len(kept)}
    assert added == set(keys)
    old_index = {r.key.casefold() for r in parse_index_xbr(bare[INDEX]).records}
    assert {r.key.casefold() for r in parse_index_xbr(game[INDEX]).records} - old_index == added
    schema, toc = Schema(game[XBE]), parse_toc(grown)
    at = {n.casefold(): i for i, n in named_resources(grown).items()}
    keylord, garret4 = (read_body(grown, b) for b in ("keylord", "garret4"))
    holder = fx_templates.GRAFTS[fx_templates.HOLDER].records[0][1]
    for e, key in zip(variant.effects, keys):
        t, g = e.template, Graph(grown, toc, toc[at[key]], schema)
        names = [rec[1] for name in t.sets for rec in fx_templates.GRAFTS[name].records]
        assert (g.names[2:], g.parent(1)) == (names, 0) and all(
            g.parent(2 + k) in range(1, len(names) + 2) for k in range(len(names)) if g.is_dag(2 + k))
        bound = struct.unpack_from("<I", g.s, g.recs[1] + 0x1C)[0]
        if t.anchor == "centre":
            assert (bound, bind_name(g.s, g.recs[1]), g.names[1]) == (1, "m_root", "m_root")
        else:
            x = g.xform_fields(1)
            assert (bound, g.names[1]) == (0, holder)
            if t.anchor == "feet":
                assert (x["t"], x["s"]) == ((0.0, 0.0, 0.0), (pytest.approx(keylord.top / garret4.top),) * 3)
            else:   # the hand: ahead of the feet and up, its lengths in metres (keylord drawn x2)
                assert x["t"][1] > 0 and x["t"][2] > 0 and x["s"] == (pytest.approx(0.5),) * 3
        for sh in t.show:
            assert g.attr_named(2 + names.index(sh["record"]), sh["attr"]) == 0.0
        for r, kind in enumerate(g.types):
            if kind == "platform":
                assert (g.attr_named(r, "gameSolid"), g.attr_named(r, "damage")) == (0.0, 0.0)
        if t.name == "bubble":
            assert g.attr_named(2 + names.index("StaticFieldBase"), "scaleX") == pytest.approx(1.1)
        if t.name == "laser":
            reach = g.attr_named(2 + names.index("locator3"), "translateY")
            assert 1.0 < reach < 3.0 and g.attr_named(2 + names.index("pBurstEmitterShape1"), "kinkCountMax") == 0
    worn = _body(_vanilla(usa, CHARACTERS), _vanilla(usa, CONFIG), variant.base)
    with_row, without = (model_inspect.own_runs(g[CHARACTERS], worn) for g in (game, bare))
    assert with_row["bytes"] > without["bytes"]


def test_a_shield_or_beam_rows_graph_hangs_under_an_effect_origin_so_the_game_draws_it_on_the_wearer(usa):
    """AZ-709 (Modkit's Step 2.167d): a bound row's copy is drawn on its wearer only under the root the game binds to
    the wearer's model matrix, the transform bound by the name the game's own shields root theirs by
    (fx_shield_force1's [0]). On shieldlord's build each row's graph roots one such transform, bound by that name,
    and every other DAG record hangs under it; a template's edit naming its holder (an inherit mode) writes the
    holder, never the root that shares its donor's name."""
    game = _effects(str(usa), "shieldlord")
    schema, fx = Schema(game[XBE]), _vanilla(usa, FX)
    shield = Graph(fx, parse_toc(fx), parse_toc(fx)[{n.casefold(): i for i, n in named_resources(fx).items()}[
        "fx/magic/fx_shield_force1"]], schema)
    assert (bind_name(shield.s, shield.recs[0]), shield.parent(0), shield.parent(1)) == (fx_ring.ORIGIN, None, 0)
    grown = game[CHARACTERS]
    toc, at = parse_toc(grown), {n.casefold(): i for i, n in named_resources(grown).items()}
    variant = _effect_variant("shieldlord")
    for k, e in enumerate(variant.effects):
        g = Graph(grown, toc, toc[at[fx_ring.bound_key("keylord", e.template.name, k)]], schema)
        assert (struct.unpack_from("<I", g.s, g.recs[0] + 0x1C)[0], bind_name(g.s, g.recs[0]), g.parent(0)) == (
            1, fx_ring.ORIGIN, None), e.template.name

        def top(r: int) -> int:
            while g.parent(r) is not None:
                r = g.parent(r)
            return r
        assert {top(r) for r in range(len(g.recs)) if g.is_dag(r)} == {0}, e.template.name
    bubble = next(e for e in variant.effects if e.template.name == "bubble")
    holder = fx_templates.GRAFTS[fx_templates.HOLDER].records[0][1]
    named = replace(bubble, template=replace(bubble.template, edits=(
        *bubble.template.edits, {"record": holder, "inherit": 2})))
    chars, key = _vanilla(usa, CHARACTERS), "characters/keylord/v/fx/fx_nit_0"
    made, _, _ = fx_ring.bound_graph(chars, game[XBE], fx, named, key, len(parse_toc(chars)), marker=fx_ring.CENTRE)
    out = append_resources(chars, made)
    g = Graph(out, parse_toc(out), parse_toc(out)[{n: i for i, n in named_resources(out).items()}[key]], schema)
    assert [struct.unpack_from("<I", g.s, g.recs[r] + 0x28)[0] for r in (0, 1)] == [0, 2]


def test_a_laser_rows_bolt_keeps_its_splits_so_its_copy_never_double_faults_the_game(usa):
    """AZ-710 (Modkit's Step 2.167d): a burst emitter with a split count of 0 and no kinks or no branches
    double-faults the game the tick after its copy loads, as the laser's did. On shieldlord's build the laser's
    bolt is straight (no kinks, no branches) and keeps the airship's own split counts, as every vanilla burst
    emitter's are at least 2."""
    game = _effects(str(usa), "shieldlord")
    schema, vanilla = Schema(game[XBE]), _vanilla(usa, CHARACTERS)
    donor = Graph(vanilla, parse_toc(vanilla), parse_toc(vanilla)[{
        n.casefold(): i for i, n in named_resources(vanilla).items()}["characters/balthazar_airship/fx/fx_default"]],
        schema)
    grown = game[CHARACTERS]
    toc, at = parse_toc(grown), {n.casefold(): i for i, n in named_resources(grown).items()}
    laser = Graph(grown, toc, toc[at[fx_ring.bound_key("keylord", "laser", 2)]], schema)
    burst = laser.names.index("pBurstEmitterShape1")
    splits = [laser.attr_named(burst, a) for a in ("splitCountMin", "splitCountMax")]
    assert [laser.attr_named(burst, a) for a in ("kinkCountMin", "kinkCountMax", "branchLevelMin",
                                                 "branchLevelMax")] == [0.0] * 4
    assert splits == [donor.attr_named(donor.names.index("pBurstEmitterShape1"), a)
                      for a in ("splitCountMin", "splitCountMax")] and min(splits) >= 1.0


@functools.lru_cache(maxsize=2)
def _bound_row(image: str, template: str, values: tuple = ()) -> tuple[Graph, bytes]:
    """A lone ``template`` row's graph as X38's build makes it (``bound_graph`` on the vanilla archives: a ``centre``
    or ``front`` holder bound to m_root, a placed one at the root's origin) in characters.xbr with it appended."""
    xbe, chars, fx = (_vanilla(image, name) for name in (XBE, CHARACTERS, FX))
    effect, = fx_templates.effects("effects", [{"template": template, "columns": ["basic1"], **dict(values)}])
    key = f"characters/keylord/v/fx/fx_{template}_0"
    made, _, _ = fx_ring.bound_graph(chars, xbe, fx, effect, key, len(parse_toc(chars)), marker=(
        fx_ring.CENTRE if effect.template.anchor in ("centre", "front") else None))
    out = append_resources(chars, made)
    toc = parse_toc(out)
    return Graph(out, toc, toc[{n: i for i, n in named_resources(out).items()}[key]], Schema(xbe)), out


def _platform(g: Graph, out: bytes, platform: str) -> tuple[np.ndarray, bool]:
    """``platform``'s mesh in its graph's root frame, as 0x68BE0 and 0x681E0 compose it (``Graph.world``), and
    whether a node above it has an inherit mode that doesn't compose (3: the camera's axes)."""
    r = g.names.index(platform)
    m, approx = g.world(r)
    rdms, _ = render.platform_bindings(g, r)[0]
    return np.array([apply(m, tuple(v)) for v in render.mesh(out, parse_toc(out), rdms).positions]), approx


def test_a_dome_rows_hemisphere_stands_on_the_feet_its_pole_up_and_its_open_side_on_the_floor(usa_iso):
    """AZ-715 (Modkit's Step 2.167e): the electric shield's hemisphere has its pole on the mesh's -y, which a dome's
    inherit 2 kept ahead (on its side, half under the floor). A dome row's hemisphere stands on the holder's floor
    plane: its rim at the feet, its pole up a radius (1.15 x its size), centred on them."""
    g, out = _bound_row(str(usa_iso), "dome")
    p, approx = _platform(g, out, "StaticFieldBaseShape")
    r = 1.15 * 1.6
    assert not approx and p[:, 2].min() == pytest.approx(0.0, abs=0.01) and p[:, 2].max() == pytest.approx(r, rel=0.01)
    assert [round(float(v), 2) for v in (*p[:, :2].min(0), *p[:, :2].max(0))] == pytest.approx([-r, -r, r, r], abs=0.02)


def test_a_laser_or_bolts_rows_targets_lie_level_ahead_of_the_hand_so_its_line_does_not_slant(usa_iso):
    """AZ-716, AZ-722 (Modkit's Steps 2.167e, 2.167f): the airship's targets sit at translateZ -0.5, so with its
    emitter at the hand a laser's or the bolts' line fell 0.5 m over its range. At any range each of the row's three
    targets lies level with its emitter, ahead of it: the laser's straight ahead at the range, the bolts' middle one
    there and the other two at 0.4 of it, spread to either side."""
    for template, reach in (("laser", 1.99581), ("laser", 15.0), ("bolts", 5.0), ("bolts", 15.0)):
        g, _ = _bound_row(str(usa_iso), template, (("range", reach),))
        hand = apply(g.world(g.names.index("pBurstEmitter1"))[0], (0.0, 0.0, 0.0))
        d = [[q[i] - hand[i] for i in range(3)] for q in (
            apply(g.world(g.names.index(loc))[0], (0.0, 0.0, 0.0)) for loc in ("locator1", "locator2", "locator3"))]
        far = (1.0, 1.0, 1.0) if template == "laser" else (0.4, 0.4, 1.0)
        assert [x for v in d for x in v[1:]] == pytest.approx([x for f in far for x in (f * reach, 0.0)], abs=1e-4), (
            template, reach)
        assert (template == "laser") == all(abs(v[0]) < 1e-4 for v in d), (template, reach)


def test_a_stream_rows_flames_reach_its_range_inside_an_attacks_column_and_keep_their_colour_to_its_end(usa_iso):
    """AZ-717, AZ-724 (Modkit's Steps 2.167e, 2.167g): a stream's reach is its flames' speed times their sink's life
    (magmar's 5 s left them at 1 m/s, under 1 m in an attack's column). At any range a stream row's flames fly for
    under half a second at the range over that flight, its sparks to 0.8 of it, and each renderer reaches its width
    and fades out as its particles die; its flame keeps its colour over 0.7 of its range and its full alpha over
    the first 0.2 (a pRendererB's colour and alpha linear in a particle's age between their two ages, 0x96260), and
    reaches the smoke's colour and alpha 0 as it dies."""
    def share(age, a1, a2):   # how far along its ramp a value is at ``age``
        return 0.0 if age <= a1 else 1.0 if age >= a2 else (age - a1) / (a2 - a1)
    for reach in (5.0, 25.0):
        g, _ = _bound_row(str(usa_iso), "stream", (("range", reach),))
        a = {n: g.attr_named(g.names.index(n), at) for n, at in (
            ("mouth1_EmitterShape1", "velocityBaseX"), ("mouth1_SinkShape1", "maxAge"),
            ("mouth1_EmitterShape2", "velocityBaseX"), ("mouth1_SinkShape2", "maxAge"))}
        life, speed = a["mouth1_SinkShape1"], a["mouth1_EmitterShape1"]
        assert 0.0 < life <= 0.5 and speed * life == pytest.approx(reach, rel=1e-5)
        assert a["mouth1_EmitterShape2"] * a["mouth1_SinkShape2"] == pytest.approx(0.8 * reach, rel=1e-5)
        for renderer, sink in (("pRendererB8", "mouth1_SinkShape1"), ("pRendererB7", "mouth1_SinkShape2")):
            ages = [g.attr_named(g.names.index(renderer), x) for x in ("sizeAge2", "alphaAge2", "colorAge2", "sizeAge1")]
            assert ages[:2] == pytest.approx([a[sink]] * 2) and 0.0 < ages[2] <= a[sink] and ages[3] <= ages[0], renderer
        r = g.names.index("pRendererB8")
        b8 = {k: g.attr_named(r, k) for k in ("colorAge1", "colorAge2", "alpha2", "alphaAge1", "alphaAge2")}
        colour, alpha = (b8["colorAge1"], b8["colorAge2"]), (b8["alphaAge1"], b8["alphaAge2"])
        assert share(0.7 * reach / speed, *colour) == 0.0 and share(life, *colour) == 1.0, b8
        assert share(0.2 * reach / speed, *alpha) == 0.0 and share(life, *alpha) == 1.0 and b8["alpha2"] == 0.0, b8


def test_a_barrier_rows_glow_is_a_panel_facing_ahead_not_a_disc_facing_the_camera(usa_iso):
    """AZ-718 (Modkit's Step 2.167e): the force shield holds its glow in the camera's axes (inherit 3), a disc facing
    the camera. A barrier row's glow composes with the body's axes: a 2.55 m square standing across the line ahead,
    at the row's ``ahead`` (1 m), facing along it."""
    g, out = _bound_row(str(usa_iso), "barrier")
    p, approx = _platform(g, out, "ForceFieldGlowShape")
    span = p.max(0) - p.min(0)
    assert not approx and span[1] == pytest.approx(0.0, abs=1e-4) and p[:, 1].mean() == pytest.approx(1.0, abs=1e-4)
    assert (span[0], span[2]) == (pytest.approx(2.55, rel=1e-3), pytest.approx(2.55, rel=1e-3))


def test_a_bubble_or_dome_rows_opacity_is_its_shaders_alpha_0_7_by_default(usa_iso):
    """AZ-719, AZ-721 (Modkit's Steps 2.167e, 2.167f): the electric shield draws at its shader's ShaderAlpha; its
    material row's opacity changes nothing. Each row's opacity, 0.7 by default, is its shader's ShaderAlpha."""
    for template, values, want in (("bubble", (), 0.7), ("bubble", (("opacity", 0.4),), 0.4), ("dome", (), 0.7)):
        g, _ = _bound_row(str(usa_iso), template, values)
        assert g.attr_named(g.names.index("StaticField_s"), "ShaderAlpha") == pytest.approx(want), (template, values)


def test_a_shield_row_on_a_spring_recipe_builds_and_its_report_keeps_the_bodys_scale_and_x3(usa, booblord):
    """Modkit's Step 2.167c's review: booblord (X41's springs; her v3) with a bubble on basic1 builds (the springs
    once took the rows' holder list's name: a TypeError, not a refusal by name, D35), and its report states the
    body's scale and X3 note as the build without the row does and names the row."""
    bare = _booblord_v3()
    row = replace(bare, effects=fx_templates.effects("effects", [{"template": "bubble", "columns": ["basic1"]}]))
    lines = []
    for v in (row, bare):
        report = []
        _swap(usa, "booblord", worn=v, lines=report)
        lines.append(next(line for line in report if f"Player model: garret4 wears {v.base}'s body" in line))
    got, want = ((re.findall(r", scale ([^;]+); ", line), line.count("(X3)")) for line in lines)
    assert got == want and want[0] and "its bubble row" in lines[0] and "its bubble row" not in lines[1]


def test_a_templates_projectile_is_held_and_thrown_no_lower_than_the_players_point(usa):
    """AZ-705 (Modkit's Step 2.167c's sitting: the catalisk's paw held its arrow 0.17-0.45 m over the sand, and every
    arrow ended on the sand or a sleeth in the line): X42's template rows (``low`` 0) hold their projectile and
    throw it no lower than the player's point; the kit's (``low`` -1e9) where the hand is. Under Unicorn on
    firelord's build (L2: his point 1 m up), a hand 0.23 m up holds and throws at 1 m; with the kit's low, at 0.23 m."""
    built = _effects(str(usa), "firelord")[XBE]
    t, x = _table(built), _x42(built)
    assert t["low"] == throws.TEMPLATE_LOW == 0.0
    col = (t["columns"] & -t["columns"]).bit_length() - 1
    sim, log, tick = x.sim, x.log, x.tick
    sim.uc.mem_write(x.bones + 0xB0 * t["bone"] + 0xA0, struct.pack("<3f", 0.3, 0.2, 0.2))
    for k, (low, held) in enumerate(((throws.TEMPLATE_LOW, 1.0), (throws.HAND_LOW, 1.15 * 0.2))):
        sim.uc.mem_write(_symbol(built, pc.THROW_HOOK, "_player_model_throw_table") + 0x178, struct.pack("<f", low))
        now = 1.0 + k
        tick(0.0, now, on=False, column=col)
        tick(t["spawns"][col] + 1e-3, now + 0.03, column=col)
        assert (len(log["spawn"]), x.f3(x.state + 0x48)[2]) == (k + 1, pytest.approx(held, abs=1e-5))
        tick(t["releases"][col] + 1e-3, now + 0.06, column=col)
        assert (len(log["message"]), log["message"][-1][2][2]) == (k + 1, pytest.approx(held, abs=1e-5))


def test_an_ice_shard_row_flies_curled_in_a_ball_not_in_its_t_pose(usa):
    """AZ-704 (Modkit's Step 2.167c's sitting: the ice shard's own ``ball`` keys none of its 22 bones, so it flew in
    its bind's T-pose): the ice shard template's ``debug`` is its mesh skinned into the rock shard's ``ball`` (the
    same bones) at t 0 as the game skins it and held there by still clips, so it is drawn as a ball ``size`` m
    across (no span past twice another; the T-pose's are 4.8 x 0.9 x 3.6). A pose whose body's bones aren't the
    body's is refused by name."""
    t, vanilla = fx_templates.TEMPLATES["ice_shard"], _vanilla(usa, CHARACTERS)

    def points(asset):   # every LOD's vertices, as an array (no game numbers in a failure's output)
        return np.array([v.position for lod in asset.lods for g in lod.groups for v in g.vertices])
    still = throws.posed(vanilla, replace(t, body={**t.body, "pose": "characters/ice_shard/ball"}))
    assert float(np.abs(points(still) - points(read_asset(vanilla, "ice_shard"))).max()) < 1e-4
    with pytest.raises(ValueError, match="bosses/boulder's bones aren't ice_shard's"):
        throws.posed(vanilla, replace(t, body={**t.body, "pose": "characters/bosses/boulder/idle"}))
    game = _effects(str(usa), "icelord")
    grown = game[CHARACTERS]
    span = [h - lo for lo, h in zip(*mesh_bounds(grown, "debug"))]
    rest = [h - lo for lo, h in zip(*mesh_bounds(vanilla, "ice_shard"))]
    assert max(span) < 2 * min(span) and max(rest) > 4 * min(rest)
    assert not named_clip(grown, "debug", "idle").bones and not named_clip(grown, "debug", "run").bones
    scale = _doc(game[CONFIG]).keyed_section("critters_engine").find_cell("debug", "scale").double_value
    assert scale * max(span) == pytest.approx(t.params["size"]["default"])


def test_x42_throws_a_templates_projectile_from_each_column_at_its_first_hit_falling_by_its_arc(usa):
    """X42's template rows (Modkit's Step 2.167b, D538's E2) under Unicorn on firelord's build (keylord with a
    fireball on basic3 and the finish; L2): its table throws ``debug`` from those two columns, each released half a
    tick before its clip's first damage tick and spawned six ticks before, at its written multiplier, at the row's
    18 m/s, arc 0.2, 2 s life and 0.4 m radius, clip slot 9, the kit's aim, no seek. A basic3 swing spawns at its
    spawn fraction and releases at its own release fraction; v lands it at the miss point under 0.2 of gravity, and
    X42 gives its AI's vertical velocity 0.8 x 9.8 x dt back on the release tick and each flying tick, its hits
    basic3's multiplier; a finish swing waits for the finish's own fractions, and with the arc at 1.5 (any number,
    D23) it is solved under 1.5 g and X42 takes 0.5 x 9.8 x dt off."""
    game = _effects(str(usa), "firelord")
    built = game[XBE]
    t = _table(built)
    anims = _doc(game[CONFIG]).keyed_section("attacks_anims")
    columns = anims.col_names()
    characters_xbr = game[CHARACTERS]
    keylord = read_body(characters_xbr, "keylord", dirs=(pc.CENTRED_DIR,))
    garret4 = read_body(characters_xbr, "garret4")
    want = {}
    for name in ("basic3", "finish"):
        i = columns.index(name)
        owner, clip = pc.source_clip(keylord, garret4, anims.find_cell(name, "Anim", i).string_value)
        ticks = round(owner.length(clip) * 30)
        first = round(min(w.on for w in damage_windows(characters_xbr, owner.name, clip)) * 30)
        want[i] = (_f32((max(1, first - 6) - 0.5) / ticks), _f32((first - 0.5) / ticks),
                   _f32(anims.find_cell(name, "Damage multiplier", i).double_value))
    assert t["columns"] == sum(1 << i for i in want)
    assert {i: (t["spawns"][i], t["releases"][i], t["mults"][i]) for i in range(throws.COLUMNS)
            if t["spawns"][i] or t["releases"][i] or t["mults"][i]} == want
    fixed = {"vh": 18.0, "arc": _f32(0.2), "life": 2.0, "tmin": _f32(1 / 30), "tmax": 2.0, "radius": _f32(0.4),
             "anim": 9, "landing": 23, "range": 14.0, "miss": MISS, "miss_z": MISS_Z, "pad": _f32(0.15),
             "species": b"debug" + bytes(11), "low": throws.TEMPLATE_LOW, "seek": 0}
    assert {k: t[k] for k in fixed} == fixed
    x = _x42(built)
    sim, log, tick = x.sim, x.log, x.tick
    ais = [0x20080000 + 0x1000 * k for k in range(len(x.critters))]
    for c, ai in zip(x.critters, ais):
        sim.uc.mem_map(ai, 0x1000)
        sim.uc.mem_write(c + 0x180, struct.pack("<I", ai))
    basic3, finish = sorted(want)
    tick(0.0, 1.0, column=basic3)
    tick(t["spawns"][basic3] + 1e-3, 1.03, column=basic3)
    tick(t["releases"][basic3] - 1e-3, 1.06, column=basic3)
    assert (len(log["spawn"]), log["message"]) == (1, [])
    tick(t["releases"][basic3] + 1e-3, 1.1, column=basic3)
    (who, msg, p0), = log["message"]
    target, v = (p0[0], p0[1] + MISS, 1.0 + MISS_Z), msg[2:5]
    flight = MISS / 18.0
    assert (who, msg[5:]) == (x.critters[0], (9, 23))
    assert [p0[i] + v[i] * flight - (0.2 * 4.9 * flight * flight if i == 2 else 0) for i in range(3)] == pytest.approx(
        target, abs=1e-4)
    vz = sim.f32(ais[0] + 0x2C)
    assert vz == pytest.approx(v[2] + 0.8 * 9.8 * 0.04, abs=1e-5)
    sim.uc.mem_write(x.critters[0] + 0x15C, struct.pack("<3f", 10.4, 21.0, 1.6))
    tick(0.9, 1.133, column=basic3)
    assert sim.f32(ais[0] + 0x2C) == pytest.approx(vz + 0.8 * 9.8 * 0.033, abs=1e-5)
    assert log["send"][-1][2][3] == want[basic3][2]
    tick(0.0, 1.2, column=finish)
    tick(t["spawns"][finish] + 1e-3, 1.23, column=finish)
    tick(t["releases"][finish] - 1e-3, 1.26, column=finish)
    assert (len(log["spawn"]), len(log["message"])) == (2, 1)
    sim.uc.mem_write(_symbol(built, pc.THROW_HOOK, "_player_model_throw_table") + 0x18, struct.pack("<f", 1.5))
    tick(t["releases"][finish] + 1e-3, 1.3, column=finish)
    who, msg, p0 = log["message"][-1]
    target, v = (p0[0], p0[1] + MISS, 1.0 + MISS_Z), msg[2:5]
    assert who == x.critters[1] and [p0[i] + v[i] * flight - (1.5 * 4.9 * flight * flight if i == 2 else 0)
                                     for i in range(3)] == pytest.approx(target, abs=1e-4)
    assert sim.f32(ais[1] + 0x2C) == pytest.approx(v[2] - 0.5 * 9.8 * 0.04, abs=1e-5)
    sim.uc.mem_write(x.critters[1] + 0x15C, struct.pack("<3f", 10.4, 21.0, 1.6))
    tick(0.95, 1.333, column=finish)
    assert {m[2][3] for m in log["send"][-2:]} == {want[basic3][2], want[finish][2]}


def test_x42_lands_on_europe_with_usas_table(usa, europe_iso):
    """On Europe X42 lands at its own address with the same table as USA's, for the kit's throw (town_male_6) and a
    template's (firelord) (Modkit's Steps 2.159b, 2.167b)."""
    tables = []
    for build in (lambda image: _swap(image, "town_male_6", sounds="garret4"),
                  lambda image: _effects(str(image), "firelord")):
        usa_table = _table(build(usa)[XBE])
        with _building(europe_iso):
            eu = build(europe_iso)[XBE]
            assert ports.verify_trampoline_patch(eu, pc.THROW_HOOK) == "applied"
            tables.append((_table(eu), usa_table))
    assert all(eu == us for eu, us in tables)

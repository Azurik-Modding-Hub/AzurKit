"""What a worn body's attacks, effects, camera, sounds and armor do in game
(Modkit's ``tests/test_player_character.py``, its second half, ported lean,
Step 4.27c): each build dressed as the product dresses one
(``characters.dressed``, the dress ``sdk``'s plan makes, from the recipe's
fields), its shims run under the simulator (``devkit.sim``: L1's checks and
L2's Unicorn runs of the game's code on the built ``default.xbe``), its
config.xbr cells, its archives and the listing it reads from the player's
images. G3's goldens hold the bytes of the builds they make; these hold what
those bytes do and the builds no golden makes."""

from __future__ import annotations

import contextlib
import functools
import json
import math
import re
import statistics
import struct
from collections import Counter
from dataclasses import replace

import pytest
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_FPSW

from azurkit.core import coff, gate
from azurkit.core.xbr.graph import Graph, Schema
from azurkit.core.xbr.nodes import named_resources, parse_toc
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_fx_ring as fx_ring
from azurkit.tools.characters import _player_variants as variants
from azurkit.tools.characters import ports
from azurkit.tools.characters._player_character import (
    ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, BALANCE_CAP, BALANCE_FLOOR, BLAST_HOLD_HOOK, BLAST_HOOK, BLAST_HOOKS,
    BLAST_LAND_HOOKS, BLAST_SHIM, CARRY_HOOK, CARRY_SHIM, CASTS, CENTRED_DIR, CHAIN_AFTER_HIT, CHAIN_GATES, CHAINED,
    DIRECTION_EDITS, DRAIN_HOOKS, DRAIN_SHIM, DRAIN_STATE, EASE_HOOK, EYE_HOOK, FINISH_RANGE, FINISH_RANGE_HOOK,
    FINISH_ROW, FINISHERS, FX_DEFAULT_HOOK, FX_DRAIN_AT, FX_RING_HOOKS, FX_RING_SHIM, FX_RING_STATE, FX_RING_TABLE,
    FX_ROTATION_AT, GARRET4_SIZES, HIT_DELAY_HOOK, HIT_FX_HOOK, HIT_FX_SHIM, HIT_NEAR, LATCH_HOOK, LIGHT,
    LIGHT_HIT_HOOK, LIGHT_HIT_SHIM, MODE_ANIMS, MODE_GRADES, MODE_SHARES, MODES, MULTIPLIER, NEAR_HOOKS, NEAR_SHIM,
    PUSH_HOOK, PUSH_SHIM, REACH_BUMP, RIG_SITES, RING_ENTRY, RING_SIZE, ROTATE_HOOK, SAME_BUILD, SEARCH_HOOK,
    SEARCH_RADIUS_SYMBOL, SEARCH_SHIM, SEARCH_SITES, SETS_HOOKS, SETS_SHIM, SETS_STATE, SHIM_HOOKS, SLOW_BONUS,
    SLOW_RATIO, STAFF_WALLS, STAFF_X1, STUN_LAG, SUPPORT, THUD_HOOK, THUD_SHIM, TOUCH_HOOK, WINGS_POSE, WINGS_SHIM,
    AttackLogic, _armor_frames, aim_records, anim_strings, attack_sets, attacks, bakes, body_height, combo_rate,
    contact, install_air_blast_shim, install_attack_carry_shim, melee_reach, mode_status, move_window, place_anims,
    player_models, reach_misses, search_reach, set_lines, shim_data, source_clip, substitutes, weigh_attacks, windup,
    write_anims)
from azurkit.tools.characters._player_damage_marker import (
    DAMAGE_MARKER, GARRET4_BOX, GARRET4_FORWARD, GARRET4_REACH, SHIM as DAMAGE_MARKER_SHIM)
from azurkit.tools.characters._player_slots import BASE_CLIPS
from azurkit.tools.characters._player_sounds import (
    ATTACK_HOOK_VA, ATTACK_SLOT, BASE_HOOK_VA, SHOUT_ROWS, XBE_SOUND_SITES, sound_roles)
from azurkit.tools.characters._player_variants import DRAIN_BOX, builtins, load_variants, options, overlay
from azurkit.tools.characters._player_weapons import attack_clips, weapons
from azurkit.tools.characters.characters import (
    MELEE_REACH, damage_windows, height, inverse_binds, read_body)
from azurkit.tools.characters.index_xbr import parse_index_xbr
from azurkit.tools.characters.ports import (
    XbrDocument, patch_spec_site, resolve_va_to_file, trampoline_symbol_va, va_to_file, verify_trampoline_patch,
    xbe_site)
from devkit.sim import l1, l2
from devkit.sim.l2 import PlayerSim, Sim
from devkit.sim.ports import parse_xbe_sections
from tests.test_roll import BASIC1, ROLLER

EUROPE = pytest.param("europe", marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")
REGIONS = ["usa", EUROPE]
_FIELD = {kw: field for field, (_, kw) in characters.FIELDS.items() if kw}   # apply_player_model's keyword -> field
_BUILT: dict = {}   # the last few builds, by release and recipe


@functools.cache
def _vanilla(path: str) -> ports.Vanilla:
    stamp = gate.verify(path, whole=False)
    return ports.Vanilla(stamp.release, stamp.path, stamped=stamp)


@pytest.fixture(autouse=True)
def image(request, usa_iso):
    """The image a test reads, its ``region`` parameter's (else USA's), with
    the swap's readers (a site's vanilla bytes, a shim's landed symbols)
    reading that release's files and facts (``ports.building``)."""
    params = getattr(getattr(request.node, "callspec", None), "params", {})
    path = request.getfixturevalue("europe_iso") if params.get("region") == "europe" else usa_iso
    vanilla = _vanilla(str(path))
    with ports.building(ports.Build(vanilla, packs=characters.packs_view(vanilla.release, mods.PACKS))):
        yield path


def _swap(species: str, *, lines: list | None = None, logic: AttackLogic | None = None, variant=None,
          fresh: bool = False, **kw) -> ports.IsoStaging:
    """``species`` (or ``variant``, worn as a recipe file's) dressed on the
    test's image as a build's character layer dresses it
    (``characters.dressed``), ``kw`` ``apply_player_model``'s keywords as
    the recipe's fields: its staged files. ``lines`` hears its build log,
    ``logic`` what it gave the randomizer's logic; the last few builds are
    kept unless ``fresh`` (a test that patched what a build reads)."""
    vanilla = ports._build().vanilla
    recipe = {"species": species if variant is None else variant.name} | {_FIELD[k]: v for k, v in kw.items()}
    key = (vanilla.release.name, json.dumps(recipe, sort_keys=True))
    made = None if fresh or variant is not None else _BUILT.get(key)
    if made is None:
        heard = AttackLogic()
        game, _, _, log = characters.dressed(characters.normalize(recipe), vanilla, [],
                                             characters.packs_view(vanilla.release, mods.PACKS), worn=variant,
                                             logic=heard)
        made = game, dict(vars(heard)), list(log)
        if not fresh and variant is None:
            _BUILT.pop(next(iter(_BUILT)), None) if len(_BUILT) >= 4 else None
            _BUILT[key] = made
    game, heard, log = made
    if lines is not None:
        lines += log
    if logic is not None:
        vars(logic).update(heard)
    return game


def _xbe() -> bytes:
    """The test's image's vanilla ``default.xbe``."""
    return ports._build().xbe()


def _read(path: str) -> bytes:
    """The test's image's vanilla file ``path``."""
    return ports._build().vanilla.read(path)


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _param(built: bytes, hook, shim, symbol: str) -> float:
    """The float param ``symbol`` of the shim ``hook`` installs in ``built``."""
    return struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, hook, symbol, shim_source=shim.source_path())))[0]


def _x3_param(xbe: bytes, name: str) -> int:
    """X3's float param ``_player_model_x3_<name>`` in the built ``xbe``, rounded (its column mask or bone index)."""
    return round(_param(xbe, DAMAGE_MARKER, DAMAGE_MARKER_SHIM, f"_player_model_x3_{name}"))


def _moved(built: bytes) -> set[int]:
    """The USA VAs of the swap's XBE sites (each shim hook, X15's sound
    names, the staff's sites, X21's radius reads, X25's rig) whose bytes in
    ``built`` aren't vanilla's."""
    sites = [*SHIM_HOOKS.items(), *((s.va, s.original) for s in (STAFF_WALLS, STAFF_X1)),
             *((s.va, s.original) for s in (*XBE_SOUND_SITES, *SEARCH_SITES, *RIG_SITES))]
    return {va for va, original in sites
            if (lambda _, off, vanilla: built[off:off + len(vanilla)] != vanilla)(*xbe_site(built, va, original))}


def _clip(characters_xbr: bytes, key: str) -> tuple[int, int]:
    """The file offset and size of ``characters.xbr``'s resource ``key``."""
    toc = parse_toc(characters_xbr)
    index = next(i for i, name in named_resources(characters_xbr).items() if name.casefold() == key)
    return toc[index].file_offset, toc[index].size


def _anims(config: bytes) -> list[str]:
    """The clip each attacks_anims column plays in ``config``."""
    anims = XbrDocument.from_bytes(config).keyed_section("attacks_anims")
    row = anims.row_names().index("Anim")
    return [anims.read_cell(i, row).string_value for i in range(len(anims.col_names()))]


def _cells(config: bytes) -> dict[tuple[str, str, str], tuple]:
    """Every keyed cell of ``config`` by (table, column, row): its type and
    value (a string cell by the string it reads)."""
    out = {}
    for section in XbrDocument.from_bytes(config).sections():
        table, rows, cols = section.name, section.row_names(), section.col_names()
        for c, col in enumerate(cols):
            for r, row in enumerate(rows):
                cell = section.read_cell(c, r)
                out[table, f"{c}:{col}", row] = (cell.type_code, cell.double_value, cell.string_value)
    return out


def _camera_point(built: bytes, flags: int) -> tuple[tuple, bool]:
    """``built``'s CALL at 0x41F67 (the camera point's ``m_head`` lookup,
    X8's hook) under L2 for a critter of a species with ``flags`` (S+0x64)
    whose body has no m_head, out of the water: the camera point it writes,
    and whether it returned as 0xCB2A0 does (RET 4, EAX the out vector)."""
    target = 0x41F6C + struct.unpack_from("<i", built, va_to_file(0x41F67) + 1)[0]
    sim, base = Sim(built), 0x20000000
    critter, species, anim, body, out, name = (base + k * 0x400 for k in range(6))
    sim.uc.mem_map(base, 0x2000 * 4)
    sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
    sim.uc.mem_write(critter + 0x18C, struct.pack("<4f", 0.0, 0.0, 0.0, 1.0))   # unturned
    sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
    sim.uc.mem_write(name, b"m_head\0")
    sim.uc.mem_write(anim, struct.pack("<4I", body, 0, 0, anim + 0x40))
    sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 0.0, 0.0, 10.0))
    sim.uc.mem_write(critter + 0x1B0, struct.pack("<3f", 0.0, 0.0, 10.0))
    sim.uc.mem_write(critter + 0x188, struct.pack("<f", 0.0))
    sim.uc.mem_write(out, struct.pack("<3f", 9.0, 9.0, 9.0))
    eax = sim.call(target, regs={"edi": critter, "ecx": anim, "eax": out}, args=(name,), until=l2._RETURN)
    return struct.unpack("<3f", sim.uc.mem_read(out, 12)), eax == out and sim.reg("esp") == l2._STACK_TOP - 0x100


def _x3_tick(xbe: bytes, attack: int, done: float, *, scale: float = 1.0, state: int = 0x100,
             anim: int | None = None, own: int = 0, bones: dict[int, tuple[float, float, float]] | None = None,
             extents: bool = False, own2: int = 0, slots: dict | None = None
             ) -> tuple[tuple[float, float], int, set[int], tuple[float, ...]]:
    """One tick of ``xbe``'s hook at 0x8C3B0, X3 (L2): attack column
    ``attack``, ``done`` of the way through its move (0.1 to 0.9 of the
    clip), PlayerControl state ``state``, on a critter of ``scale`` playing
    anim ``anim`` (critter+0x200; by default the attack's own, 0x52 + its
    column), whose m_damage critter_init cached at ``own`` (critter+0x218)
    and its m_damage2 at ``own2`` (+0x21C), and whose anim object holds the
    runtime bones ``bones`` (index -> its matrix's translation). The shim
    must end by calling the staff-wall check with the PlayerControl.
    Returns the marker critter+0x218 points at after the tick, as (length,
    active), its VA, every VA the tick wrote, and its centre (with
    ``extents``, followed by its extents); ``slots`` gets what +0x21C points
    at after it and that marker's (length, active)."""
    entry = DAMAGE_MARKER.va + 5 + struct.unpack_from("<i", xbe, va_to_file(DAMAGE_MARKER.va) + 1)[0]
    pc, critter, pose = 0x20000000, 0x20001000, 0x20004000
    sim = Sim(xbe)
    sim.uc.mem_map(pc, 0x10000)
    for at, fmt, value in ((pc + 0x20, "<I", critter), (pc + 0x94, "<I", state),
                           (pc + 0xF8, "<f", 0.1), (pc + 0x100, "<f", 0.9),
                           (pc + 0x134, "<i", attack), (pc + 0x178, "<f", 0.1 + 0.8 * done),
                           (critter + 0x188, "<f", scale), (critter + 0x218, "<I", own),
                           (critter + 0x21C, "<I", own2),
                           (critter + 0x200, "<i", 0x52 + attack if anim is None else anim)):
        sim.uc.mem_write(at, struct.pack(fmt, value))
    if bones:   # the anim object (critter+0x17C): +8 its 0xB0-byte runtime bones, matrix at +0x70
        sim.uc.mem_write(critter + 0x17C, struct.pack("<I", pose))
        sim.uc.mem_write(pose + 8, struct.pack("<I", pose + 0x100))
        for i, origin in bones.items():
            sim.uc.mem_write(pose + 0x100 + 0xB0 * i + 0xA0, struct.pack("<3f", *origin))
    written: set[int] = set()
    sim.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, access, va, size, value, _: written.update(range(va, va + size)))
    sim.call(entry, args=(pc,), until=0x8C8A0)
    assert sim.u32(sim.reg("esp") + 4) == pc
    if slots is not None:
        two = sim.u32(critter + 0x21C)
        slots["m_damage2"] = two, struct.unpack("<2f", sim.uc.mem_read(two + 0x2C, 8)) if two else None
    marker = sim.u32(critter + 0x218)
    if marker == own:
        return (0.0, 0.0), marker, written, (0.0,) * (6 if extents else 3)
    return (struct.unpack("<2f", sim.uc.mem_read(marker + 0x2C, 8)), marker, written,
            struct.unpack("<3f", sim.uc.mem_read(marker + 4, 12))
            + (struct.unpack("<3f", sim.uc.mem_read(marker + 0x20, 12)) if extents else ()))


def _x3_marker(xbe: bytes, attack: int, done: float, **kw) -> tuple[float, float]:
    """X3's marker (length, active) after one tick (:func:`_x3_tick`)."""
    return _x3_tick(xbe, attack, done, **kw)[0]


# --- the attack sliders, the no-hit window, the hit flash and thud, the player's own fx and colours ---------------


@pytest.mark.parametrize("species, kw, chain", [
    ("garret4", {"attack_reach": 1.5}, None),
    ("garret4", {"attack_damage": 2.0}, None),
    ("garret4", {"attack_damage": 0.5}, None),
    ("garret4", {"attack_speed": 2.0}, (0.8250, None, None)),        # basic2-3 keep their own at x2 (AZ-712)
    ("garret4", {"attack_speed": 2.5}, (0.8438, 0.9000, None)),      # basic1's hit on a tick's edge (AZ-712)
    ("garret4", {"attack_speed": 1.5}, (0.8250, None, None)),        # basic2's hit clear of X31's window
    ("garret4", {"attack_speed": 0.5}, (0.5721, 0.5300, 0.6083)),
    ("garret4", {"attack_speed": 1.25}, None),                       # the raw chain is inside the stun
    ("gargoylestone", {"attack_damage": 2.0, "attack_speed": 2.0}, (0.8250, None, None)),   # his (AZ-568)
])
def test_the_attack_sliders_write_garret4s_own_table_and_a_clipless_bodys_and_keep_his_combo_chaining(
        species, kw, chain):
    """D302, D312 (Modkit's Step 2.123): on garret4's own body the reach is
    X13 at that reach with nothing lowered or bumped, and X21's search out
    to 3 m x the reach, nothing else at x1 (no X9, X22, X23 or X25); the
    damage multiplies every attack's Damage multiplier but the roll's (an
    empty cell as 1.0) with X18 once a light hit (0.5) reaches 1.0; the
    speed multiplies every Rate but the roll's, and his basics' Move end1
    moves only where the raw chain would leave the stun: held to the first
    tick the stun shows or later (AZ-712), but 4 ticks where the stun's
    would bring the next basic's hit inside X31's no-hit window, and to its
    x1 gap or less (x0.5), none at x1.25. A body with no clips, whose timers
    play garret4's clips, takes the damage and speed too, and his chain
    rule (AZ-565, AZ-568); the logic reads all three (his reach basic1's
    2.76 m ahead x the reach, AZ-604)."""
    logic = AttackLogic()
    game = _swap(species, sounds="garret4", logic=logic, **kw)
    built = bytes(game["default.xbe"])
    vanilla, anims = (XbrDocument.from_bytes(c).keyed_section("attacks_anims")
                      for c in (game.stored("config.xbr"), bytes(game["config.xbr"])))
    damage, speed, reach = (kw.get(f"attack_{k}", 1.0) for k in ("damage", "speed", "reach"))

    def cell(table, col: str, row: str, i: int) -> float | None:
        c = table.find_cell(col, row, i)
        return c.double_value if c is not None and c.type_code == 1 else None

    def frac(table, col: str, i: int) -> float:
        a0, a1 = cell(table, col, "Anim start", i), cell(table, col, "Anim end", i)
        return (cell(table, col, "Move end1", i) - a0) / (a1 - a0)
    for i, col in enumerate(vanilla.col_names()):
        held = col == "roll forward"
        m = cell(vanilla, col, MULTIPLIER, i)
        assert cell(anims, col, MULTIPLIER, i) == (m if held or damage == 1.0 else pytest.approx((m or 1.0) * damage))
        assert cell(anims, col, "Rate", i) == pytest.approx(cell(vanilla, col, "Rate", i) * (1.0 if held else speed))
        want = (chain or (None,) * 3)[CHAINED.index(col)] if col in CHAINED else None
        assert (cell(anims, col, "Move end1", i) == cell(vanilla, col, "Move end1", i) if want is None
                else frac(anims, col, i) == pytest.approx(want, abs=1e-4)), col
    assert (logic.damage, logic.speed) == (damage, speed)
    if species != "garret4":
        assert verify_trampoline_patch(built, LIGHT_HIT_HOOK) == "applied"
        return
    hooks = ({LIGHT_HIT_HOOK.va} if damage >= 2.0 else {ATTACK_BOX_HOOK.va, SEARCH_HOOK.va} if reach != 1.0 else set()
             ) | ({HIT_DELAY_HOOK.va} if speed > 1.0 else set())
    assert _moved(built) == hooks | ({s.va for s in SEARCH_SITES} if reach != 1.0 else set())
    assert sorted(game.changed()) == ["default.xbe"] * bool(hooks) + ["gamedata/config.xbr"] * (reach == 1.0)
    assert logic.reach == pytest.approx(2.758973 * reach)
    if reach != 1.0:
        assert [_param(built, ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, f"_player_attack_{k}")
                for k in ("reach", "ground_mask", "bump_mask")] == [reach, 0.0, 0.0]
        assert _param(built, SEARCH_HOOK, SEARCH_SHIM, "_player_model_search_reach") == pytest.approx(3.0 * reach)


@pytest.mark.parametrize("species, speed, region", [
    ("garret4", 1.5, "usa"), ("keylord", 1.5, "usa"), ("garret4", 1.0, "usa"), ("garret4", 0.5, "usa"),
    pytest.param("garret4", 1.5, "europe", marks=[pytest.mark.vanilla, pytest.mark.europe])])
def test_a_faster_attack_shortens_the_no_hit_window_its_hits_give_by_the_attack_speed(species, speed, region):
    """AZ-573 (Modkit's Step 2.126, D318): a hit that deals damage sets its
    target's no-hit timer +0x1E0 (and +0x1E4) to the damage record's Delay,
    0.33 s, so from attack speed about 1.3 basic2 met the enemy basic1 had
    just hit inside it. X31 (L2 at 0x43584 to 0x43597) gives the player's
    hit (the source's critter, by the game's vtable +0x74, the player's
    species and not the target) the Delay x f32(1 / speed), and keeps the
    record's for an enemy's hit, a self hit, a platform's and none; ECX,
    EBX, ESI, EDI and EBP kept, the stack balanced. On garret4's own body
    and a swapped one, Europe at the same VA; at speed 1.0 and below the
    game's bytes."""
    built = bytes(_swap(species, sounds="garret4", attack_speed=speed)["default.xbe"])
    assert verify_trampoline_patch(built, HIT_DELAY_HOOK) == ("applied" if speed > 1.0 else "original")
    if region == "europe" or speed <= 1.0:
        return
    base, vtable, platform_of = 0x20000000, 0x19FC08, 0x606A0   # a critter's vtable; a platform's +0x74
    record, target, player, enemy, message, mine, theirs, platform = (base + 0x400 * k for k in range(8))
    kept = {"ecx": 0x1234, "ebx": message, "esi": 0x55, "edi": 0x66, "ebp": message + 4}

    def window(source: int, hit: int = target) -> tuple[float, float]:
        sim = Sim(built)
        sim.uc.mem_map(base, 0x4000)
        for at, fmt, value in ((record + 0x10, "f", 0.33), (player, "I", vtable), (player + 0x178, "I", mine),
                               (mine + 0x64, "B", 0x20), (enemy, "I", vtable), (enemy + 0x178, "I", theirs),
                               (platform, "I", platform + 0x100), (platform + 0x174, "I", platform_of),
                               (message + 4, "I", source)):
            sim.uc.mem_write(at, struct.pack("<" + fmt, value))
        sim.call(HIT_DELAY_HOOK.va, regs={"eax": record, "edx": hit, **kept}, args=(0, 0, 0, hit), until=0x43597)
        assert {r: sim.reg(r) for r in kept} == kept and sim.reg("esp") == l2._STACK_TOP - 0x100 - 0x14
        return sim.f32(hit + 0x1E0), sim.f32(hit + 0x1E4)

    delay = _f32(0.33)
    assert window(player) == (_f32(delay * _f32(1 / speed)),) * 2                  # the player's hit: / the speed
    for source, hit in ((enemy, target), (player, player), (platform, target), (0, target)):
        assert window(source, hit) == (delay, delay), hex(source)


@pytest.mark.parametrize("region", REGIONS)
def test_a_worn_bodys_plain_hits_show_its_own_small_flash_never_an_element_powers(region):
    """D700 (Modkit's Step 2.180, X32): an AI victim's hit handler 0x38C60
    plays a hit's visual by its damage record from the victim species' keys,
    so the worn fire elemental showed its fx_fire_3. X32 (L2, from 0x39003
    to 0x440F0 critter_play_fx) pushes the key its slot holds,
    fx/damage/v/fx_hit_small, on every victim when the attacker is the
    player and the hit's record a plain one (index 0-3); another attacker, a
    power's record, a record outside the table and an empty slot keep the
    key pushed; ECX the victim, the return to 0x3900B; EBX, ESI, EDI and EBP
    kept. The build appends that graph to fx.xbr first, with its index.xbr
    record: fx_norm_1 at half its scale, its timer 1.5 times as fast and its
    gameVisible link at 0.6, every other record and link the source's.
    Installed in both modes, at Europe's same VA; keylord's (its NPC hits
    with a plain record) and garret4's own get neither, their fx.xbr
    unchanged."""
    from azurkit.tools.characters._player_character import HIT_FLASH, HIT_FLASH_SOURCE, hit_flash

    builds = {mode: _swap("fire_elemental", mode=mode, sounds="garret4") for mode in MODES}
    fx, xbe0 = _read("gamedata/fx.xbr"), _xbe()
    old, n = parse_toc(fx), len(hit_flash(fx, xbe0))
    schema = Schema(xbe0)
    for game in builds.values():
        xbe, built = bytes(game["default.xbe"]), bytes(game["fx.xbr"])
        assert verify_trampoline_patch(xbe, HIT_FX_HOOK) == "applied"
        slot = resolve_va_to_file(xbe, trampoline_symbol_va(xbe, HIT_FX_HOOK, "_player_model_hit_fx",
                                                            shim_source=HIT_FX_SHIM.source_path()))
        assert xbe[slot:xbe.index(b"\0", slot)] == HIT_FLASH.encode()
        toc, named = parse_toc(built), named_resources(built)
        assert len(toc) == len(old) + n and named[len(old)] == HIT_FLASH and toc[len(old)].tag == "node"
        assert (HIT_FLASH, "fx.xbr", "node") in {(r.key, r.archive, r.fourcc)
                                                  for r in parse_index_xbr(bytes(game["index.xbr"])).records}
        src = Graph(fx, old, old[next(i for i, k in named_resources(fx).items() if k == HIT_FLASH_SOURCE)], schema)
        got = Graph(built, toc, toc[len(old)], schema)
        assert (got.types, got.names) == (src.types, src.names)
        for i in range(len(src.recs)):
            a, b = (dict(zip(schema.types[g.types[i]].attrs, g.attrs(i))) if g.recs[i] is not None else {}
                    for g in (src, got))
            assert b == (a | {"rate": 1.5} if i == 2 else a), i   # NormalHit_timer: 1.5 times as fast
            factors = [1.0] * len(src.links(i))
            if i == 2:   # Flash.scaleX/Y/Z at half, FlashShape.gameVisible at 0.6, its unload the source's
                factors[:4] = [0.5, 0.5, 0.5, 0.6]
            assert [(k.dst, k.dst_plug, k.weight, k.curve, k.factor) for k in got.links(i)] == [
                (k.dst, k.dst_plug, k.weight, k.curve, pytest.approx(k.factor * f)) for k, f in zip(src.links(i), factors)]
    if region == "europe":
        return
    for species, kw in (("keylord", {}), ("garret4", {"model_scale": 2.0})):
        game = _swap(species, sounds="garret4", **kw)
        assert verify_trampoline_patch(bytes(game["default.xbe"]), HIT_FX_HOOK) == "original", species
        assert len(parse_toc(bytes(game["fx.xbr"]))) == len(old), species
    built = bytes(builds["own"]["default.xbe"])
    base = 0x20000000
    victim, world, player, other, hit, text = (base + 0x400 * k for k in range(6))
    kept = {"ebx": victim, "esi": 0x55, "edi": 0x66, "ebp": 0x77}
    va = trampoline_symbol_va(built, HIT_FX_HOOK, "_player_model_hit_fx", shim_source=HIT_FX_SHIM.source_path())
    at = resolve_va_to_file(built, va)

    def shown(index: int = 1, attacker: int = player, empty: bool = False) -> int:
        xbe = bytearray(built)
        if empty:
            xbe[at] = 0
        sim = Sim(bytes(xbe))
        sim.uc.mem_map(base, 0x4000)
        for where, value in ((victim + 0x154, world), (world + 0xBC, player), (hit + 4, attacker)):
            sim.uc.mem_write(where, struct.pack("<I", value))
        frame = [0] * 34
        frame[4], frame[33] = index & 0xFFFFFFFF, hit            # 0x38C60's [esp+0x14] and [esp+0x88]
        sim.call(0x39003, regs={"eax": text, **kept}, args=tuple(frame), until=0x440F0)
        esp = sim.reg("esp")
        assert (esp, sim.u32(esp), sim.reg("ecx")) == (l2._STACK_TOP - 0x100 - 4 * 34 - 12, 0x3900B, victim)
        assert {r: sim.reg(r) for r in kept} == kept
        return sim.u32(esp + 4)
    assert shown() == va                                     # the player's plain hit: the build's flash
    for kw in ({"attacker": other}, {"index": 5}, {"index": -1}, {"empty": True}):
        assert shown(**kw) == text, kw


@pytest.mark.parametrize("region", REGIONS)
def test_bare_hands_swings_whoosh_and_their_plain_hits_show_sparks_and_thud(region):
    """D502, D467 (Modkit's Step 2.159a): a weaponless townsperson's build
    (town_male_6, whose speech dir X14 binds its hurt lines from) binds the
    kit's whoosh, t_whoosh, in every attack column and the roll (D328), its
    two takes appended to fx.xbr under that dir with the thud,
    fx/sound/t/thud, each with its index.xbr record; X32 shows its small
    flash for its plain hits; and X43 (L2, from 0x38D2B, the hit sound's
    pushes in the AI hit handler, to sound_play_at 0xA2630) plays the
    thud's handle (asset_find 0xA5CA0 by its name) in place of the victim's
    hit-row sound when the attacker is the player and the hit's record a
    plain one; another attacker, a power's record, a record outside the
    table, an asset_find miss and an empty name keep the victim's; the
    point and the return to 0x38D34 as the CALL left them, EAX 0, EBX, ESI,
    EDI and EBP kept. At Europe's same VA. A build with Garret's sounds and
    a farmer's (his hoe) get no X43."""
    from azurkit.tools.characters._player_sounds import SOUND_HOOKS, SOUNDS_SHIM

    game = _swap("town_male_6")
    built = bytes(game["default.xbe"])
    assert verify_trampoline_patch(built, THUD_HOOK) == "applied"
    assert verify_trampoline_patch(built, HIT_FX_HOOK) == "applied"
    name = resolve_va_to_file(built, trampoline_symbol_va(built, THUD_HOOK, "_player_model_thud",
                                                          shim_source=THUD_SHIM.source_path()))
    assert built[name:built.index(b"\0", name)] == b"fx/sound/t/thud"
    speech = "loc/english/speech/male_6"
    waves = {key: parse_toc(bytes(game["fx.xbr"]))[i].tag for i, key in named_resources(bytes(game["fx.xbr"])).items()}
    added = {f"{speech}/t_whoosh", f"{speech}/t_whoosh_a", "fx/sound/t/thud"}
    assert {key: waves.get(key) for key in added} == dict.fromkeys(added, "wave")
    assert added <= {r.key for r in parse_index_xbr(bytes(game["index.xbr"])).records}
    table_at = resolve_va_to_file(built, trampoline_symbol_va(built, SOUND_HOOKS[1], "_player_model_sounds",
                                                              shim_source=SOUNDS_SHIM.source_path()))
    table = built[table_at:table_at + 1024]

    def text(at: int) -> str:
        return table[at:table.index(b"\0", at)].decode()
    count = struct.unpack_from("<H", table, 2)[0]
    binds = {k: text(at) for k in range(count) if (at := struct.unpack_from("<H", table, 4 + 2 * k)[0])}
    columns = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims").col_names()
    assert text(struct.unpack_from("<H", table, 0)[0]) == speech
    assert {binds.get(ATTACK_SLOT + k) for k in range(len(columns))} == {"t_whoosh"}
    assert binds[BASE_CLIPS.index("ouch_1")].startswith("talk_")   # its hurt lines kept
    if region == "europe":
        return
    for species, kw in (("town_male_6", {"sounds": "garret4"}), ("town_male_farmer_1", {})):
        assert verify_trampoline_patch(bytes(_swap(species, **kw)["default.xbe"]), THUD_HOOK) == "original", species
    base = 0x20000000
    victim, world, player, other, hit, point = (base + 0x400 * k for k in range(6))
    kept = {"ebx": victim, "esi": 0x55, "edi": 0x66, "ebp": 0x77}

    def played(index: int = 1, attacker: int = player, found: int = 0x1234, named: bool = True) -> int:
        xbe = bytearray(built)
        if not named:
            xbe[name] = 0
        sim = Sim(bytes(xbe))
        sim.uc.mem_map(base, 0x2000)
        for at, value in ((victim + 0x154, world), (world + 0xBC, player), (hit + 4, attacker)):
            sim.uc.mem_write(at, struct.pack("<I", value))
        frame = [0] * 36
        frame[5], frame[34] = index & 0xFFFFFFFF, hit            # 0x38C60's [esp+0x14] and [esp+0x88]
        sim.call(0x38D2B, regs={"eax": point, **kept, "esi": 0x99}, args=tuple(frame), until=0xA2630,
                 stubs={0xA5CA0: found})
        esp = sim.reg("esp")
        assert (esp, sim.u32(esp), sim.u32(esp + 8), sim.reg("eax")) == (
            l2._STACK_TOP - 0x100 - 4 * 36 - 16, 0x38D34, point, 0)
        assert {r: sim.reg(r) for r in ("ebx", "edi", "ebp")} == {r: kept[r] for r in ("ebx", "edi", "ebp")}
        assert sim.reg("esi") == 0x99
        return sim.u32(esp + 4)
    assert played() == 0x1234                                # the player's plain hit: the thud
    for kw in ({"attacker": other}, {"index": 5}, {"index": -1}, {"found": 0xFFFFFFFF}, {"named": False}):
        assert played(**kw) == 0x99, kw


@pytest.mark.parametrize("region", REGIONS)
def test_the_player_alone_plays_its_bodys_fx_clone(region):
    """D446 (Modkit's Step 2.157, X40): a body's default fx is one graph
    0x43700 builds on every critter of the body, so a variant's fx edits
    changed every NPC. A build with fx edits (plain Balthazar's own) adds
    the player's clone, characters/balthazar_airship/v/fx/fx_default, and
    X40 (L2, from 0x43700 on a fake critter to 0x43727) formats that key
    for a species whose ai class (+0xC) is 'player''s (0x8D750) and the
    vanilla key for any other, the body string and the stack as the vanilla
    push left them; at Europe's same VA, its compare naming Europe's
    factory and both formats its own strings. A build without fx edits (his
    garret4 mode) keeps the vanilla push."""
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM

    built = bytes(_swap("balthazar", sounds="garret4")["default.xbe"])   # his fall voices (X15): an L2 blind spot
    plain = bytes(_swap("balthazar", mode="garret4")["default.xbe"])
    va, off, vanilla = xbe_site(built, FX_DEFAULT_HOOK.va, FX_DEFAULT_HOOK.replaced_bytes)
    assert plain[off:off + 5] == vanilla and built[off] == 0xE8
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    shim = va + 5 + struct.unpack_from("<i", built, off + 1)[0]
    at = resolve_va_to_file(built, shim)
    code = list(md.disasm(built[at:at + 40], shim))[:8]
    assert [i.mnemonic for i in code] == ["pop", "mov", "cmp", "jne", "mov", "push", "push", "ret"]

    def text(insn) -> str:
        o = resolve_va_to_file(built, insn.operands[1].imm)
        return built[o:built.index(b"\0", o)].decode()
    cmp = code[2].operands
    assert (cmp[0].type, cmp[0].mem.disp, cmp[1].type, cmp[1].imm) == (
        X86_OP_MEM, 0xC, X86_OP_IMM, ports.xbe_layout(built).va(0x8D750))
    assert (text(code[1]), text(code[4])) == ("characters/%s/fx/fx_default", "characters/%s/v/fx/fx_default")
    if region == "europe":
        return
    base = 0x20000000
    critter, species, body = base, base + 0x400, base + 0x800
    for ai, key in ((0x8D750, "characters/balthazar_airship/v/fx/fx_default"),
                    (0x3B5A0, "characters/balthazar_airship/fx/fx_default")):
        sim = Sim(built)
        sim.uc.mem_map(base, 0x1000)
        sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
        sim.uc.mem_write(species + 4, struct.pack("<I", body))
        sim.uc.mem_write(species + 0xC, struct.pack("<I", ai))
        sim.uc.mem_write(body, b"balthazar_airship\0")
        sim.call(0x43700, regs={"eax": critter}, until=0x43727)
        esp = sim.reg("esp")
        assert (sim.cstr(sim.reg("esi")), sim.u32(esp + 4), esp) == (key, body, l2._STACK_TOP - 0x100 - 4 - 0x110 - 8)


@pytest.mark.parametrize("region", REGIONS)
def test_a_colour_only_variant_recolours_the_players_copy_alone(region):
    """D539, D734 (Modkit's Step 2.170b, W38 and X47): a recipe's
    ``colours`` are made in the player's copy of its body: town_female_3
    with hue +120 on every row and a swap on row 0 adds
    characters/townspeople/female_3/v/skin to characters.xbr and index.xbr,
    each of its rows drawing its vanilla texture recoloured by its ops
    (every row's, then its own), while the material entry the NPCs' body
    names keeps vanilla's bytes; X47 (L2, 0x4B8E0 on a fake species up to
    its asset_find) formats that key for a species with the player flag
    (0x20 at +0x64) and the vanilla key for any other; at Europe's same VA,
    both formats its own strings."""
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs

    from azurkit.tools.characters import paint, render
    from azurkit.tools.characters._player_character import BODY_KEY_HOOK
    from azurkit.tools.characters.characters import body_at

    hue = {"op": "hsv", "hue": 120}
    swap = {"op": "swap", "from": [0.6, 0.2, 0.1], "to": [0.2, 0.3, 0.8]}
    variant = load_variants(json.dumps({"tinted": {"base": "town_female_3", "colours": [
        {"ops": [hue]}, {"row": 0, "ops": [swap]}]}}), "test")["tinted"]
    game = _swap(variant.base, variant=variant)
    built, stored, xbe = bytes(game["characters.xbr"]), game.stored("characters.xbr"), bytes(game["default.xbe"])
    key, names = "characters/townspeople/female_3/v/skin", named_resources(built)
    assert [n for n in names.values() if n.casefold() == key] == [key]
    assert [r.fourcc for r in parse_index_xbr(bytes(game["index.xbr"])).records if r.key == key] == ["body"]
    vtoc, toc = parse_toc(stored), parse_toc(built)
    body, _ = body_at(stored, "townspeople/female_3")
    copy = next(i for i, n in names.items() if n == key)
    rows, copied = paint.drawn_rows(stored, vtoc, body), paint.drawn_rows(built, toc, copy)
    assert sorted(r for _, r in rows) == sorted(r for _, r in copied) == [0, 1, 2, 3]
    ops = {r: variant.colours[0].ops + (variant.colours[1].ops if r == 0 else ()) for r in range(4)}

    def entry(data, t, i) -> bytes:
        return bytes(data[t[i].file_offset:t[i].file_offset + t[i].size])

    def stage0(data, t, g, r) -> int:
        return struct.unpack_from("<I", data, render.material_row(data, t, g, r) + 100)[0]
    for (g, r), (cg, cr) in zip(sorted(rows), sorted(copied)):
        assert entry(built, toc, g) == entry(stored, vtoc, g)       # the NPCs' material: vanilla's textures
        assert entry(built, toc, stage0(built, toc, cg, cr)) == paint.recolour(entry(stored, vtoc, stage0(
            stored, vtoc, g, r)), ops[r]), r
    va, off, vanilla = xbe_site(xbe, BODY_KEY_HOOK.va, BODY_KEY_HOOK.replaced_bytes)
    shim = va + 5 + struct.unpack_from("<i", xbe, off + 1)[0]
    code = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(xbe[resolve_va_to_file(xbe, shim):][:40], shim))[:8]
    assert xbe[off] == 0xE8 and [i.mnemonic for i in code] == ["pop", "mov", "test", "je", "mov", "push", "push",
                                                                "ret"]
    if region == "europe":
        return
    base = 0x20000000
    species, string = base, base + 0x800
    for flags, want in ((0x20, key), (0, "characters/townspeople/female_3")):
        sim = Sim(xbe)
        sim.uc.mem_map(base, 0x1000)
        sim.uc.mem_write(species + 4, struct.pack("<I", string))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(string, b"townspeople/female_3\0")
        sim.call(0x4B8E0, args=(species,), until=0x4B91A)
        assert sim.cstr(sim.reg("ecx")) == want


def test_a_recoloured_bodys_budget_counts_its_copy_alone_where_no_level_places_the_body(monkeypatch):
    """AZ-761 (Modkit's Step 2.198): the build's own-runs line counted a
    recoloured body and W38's copy both, where the game loads the copy
    alone when no level places a critter wearing the body. No level places
    town_female_2 (D361), the town places town_female_3: a colour-only
    variant of the first counts every own run but what only the body's own
    entry reaches, of the second both."""
    from azurkit.tools.characters import model_inspect as mi

    placed = mi.placed_species(ports._build().vanilla)
    assert "town_female_3" in placed and "town_female_2" not in placed
    monkeypatch.setattr(mi, "lines_for", lambda budget, tier=64: (1 << 40, 0))   # every build prints its line
    for base, body, alone in (("town_female_2", "townspeople/female_2", True),
                              ("town_female_3", "townspeople/female_3", False)):
        variant = load_variants(json.dumps({"tinted": {"base": base, "colours": [
            {"ops": [{"op": "hsv", "hue": 120}]}]}}), "test")["tinted"]
        lines: list[str] = []
        game = _swap(base, variant=variant, lines=lines)
        built, fx = bytes(game["characters.xbr"]), bytes(game["fx.xbr"])   # its sounds' runs, if it added any
        line, = [s for s in lines if s.startswith("  Player model budget: its own load runs ")]
        both, copy = (mi.own_runs(built, body, fx, body_entry=entry)["bytes"] for entry in (True, False))
        assert copy < both and line.startswith(f"  Player model budget: its own load runs "
                                               f"{(copy if alone else both) / mi.MiB:.2f} MiB"), base


GARRET_GREEN = {"garret_green": {
    "title": "Garret recoloured", "base": "garret4",
    "colours": [{"ops": [{"op": "hsv", "hue": -100, "window": [195, 238]}]},
                {"row": 3, "ops": [{"op": "hsv", "hue": 180, "window": [15, 75]}]}]}}
"""Modkit's ``tests/fixtures/garret_colours.json`` (Step 2.170c, D748): his blue skin green and his staff's warm
tones blue (row 3), in his own rows; his purple hair kept (AZ-748)."""


def test_a_colour_recipe_on_garret4_recolours_his_own_rows_in_place():
    """D748 (Modkit's Step 2.170c): a recipe on garret4's own body (his
    blue skin green on every row, his staff's warm tones blue on row 3, his
    256x512 texture) builds his own build with his rows repointed in place:
    each of his four textured rows' stage 0 names a new surf, its vanilla
    texture recoloured by its ops, and every other entry of characters.xbr
    keeps its bytes, his material entry all but those four fields; no copy
    is named, and nothing else of the image changes (no X47); its log has
    no "nothing written" line."""
    from azurkit.tools.characters import paint, render, textures
    from azurkit.tools.characters.characters import body_at

    variant = load_variants(json.dumps(GARRET_GREEN), "garret_colours.json")["garret_green"]
    log: list[str] = []
    game = _swap(variant.base, variant=variant, lines=log)
    assert list(game.changed()) == ["gamedata/characters.xbr"]
    assert not any(line.endswith("nothing written") for line in log) and log[-1].startswith("  Player model status:")
    built, stored = bytes(game["characters.xbr"]), game.stored("characters.xbr")
    vtoc, toc = parse_toc(stored), parse_toc(built)

    def entry(data, t, i) -> bytes:
        return bytes(data[t[i].file_offset:t[i].file_offset + t[i].size])
    stage0 = {}
    for g, r in paint.drawn_rows(stored, vtoc, body_at(stored, "garret4")[0]):
        at = render.material_row(stored, vtoc, g, r)
        if struct.unpack_from("<I", stored, at + 96)[0]:
            stage0[g, r] = (at + 100 - vtoc[g].file_offset, struct.unpack_from("<I", stored, at + 100)[0])
    assert sorted(r for _, r in stage0) == [0, 1, 2, 3] and len(toc) == len(vtoc) + 4
    masked = {g: bytearray(entry(built, toc, g)) for g, _ in stage0}
    for (g, r), (off, old) in stage0.items():
        new = struct.unpack_from("<I", masked[g], off)[0]
        ops = variant.colours[0].ops + (variant.colours[1].ops if r == 3 else ())
        recoloured, info = entry(built, toc, new), textures.info(entry(stored, vtoc, old))
        assert r != 3 or (info["width"], info["height"]) == (256, 512)
        assert new >= len(vtoc) and recoloured == paint.recolour(entry(stored, vtoc, old), ops) != entry(
            stored, vtoc, old), r
        struct.pack_into("<I", masked[g], off, old)
    assert all((bytes(masked[i]) if i in masked else entry(built, toc, i)) == entry(stored, vtoc, i)
               for i in range(len(vtoc)))
    assert named_resources(built) == named_resources(stored)


def test_a_flagged_attack_column_carries_the_stick_and_turns_the_body():
    """D334, D346, D351 (Modkit's Step 2.132, X33): an attack ticks 0x8C7D0
    -> 0x8C630, which hands the move code the clip's root motion alone, so a
    swing neither moved with the stick nor turned. X33 (L2: the real entry
    0x88990 and tick 0x8C7D0 through a basic1, the move code stubbed) at
    0x8C630's CALL 0x307E0: in a column of its mask whose own slot plays
    with the stick off centre, each tick's desired x and y gain garret4's
    runSpeed x the stick's magnitude along its direction, the root motion
    and z kept, and the walk's facing (+0x7C) is copied over +0xD0; an
    unflagged column, the roll, a hit reaction's slot (37) and a centred
    stick are the game's to the bit. The build gives it in own body only:
    every column but the roll for a flyer (the fire elemental), the spin
    clips' columns for another body (sleeth_x's attack_1 in 8 columns),
    nothing for a walker (keylord), in Skin only or on garret4's own body."""
    vanilla = _xbe()

    def carrying(mask: int) -> bytes:
        xbe = bytearray(vanilla)
        install_attack_carry_shim(xbe, mask)
        return bytes(xbe)
    every = 0xEFFFFF
    assert l1.check(vanilla, carrying(every)) == []
    turn = (0.0, 0.0, math.sin(0.3), math.cos(0.3))

    def roll(xbe: bytes, player) -> tuple:
        sim = PlayerSim(xbe, player)
        got = sim.roll()
        return got, struct.unpack("<4f", sim.uc.mem_read(sim.at["input"] + 0xD0, 16))
    base, facing = roll(vanilla, BASIC1)
    got, faced = roll(carrying(every), BASIC1)
    run = [BASIC1.walk_speed * BASIC1.stick * d for d in BASIC1.direction[:2]]
    assert got.ticks == base.ticks > 10 and faced == pytest.approx(BASIC1.walk_facing)
    for g, b in zip(got.desired, base.desired):
        assert g == pytest.approx((b[0] + run[0], b[1] + run[1], b[2]), rel=1e-6), (g, b)
    turned = replace(BASIC1, walk_facing=turn)
    assert roll(carrying(every), turned)[1] == pytest.approx(turn)
    for xbe, player in ((carrying(every & ~1), turned), (carrying(0xFFFFFF), replace(ROLLER, walk_facing=turn)),
                        (carrying(every), replace(turned, anim_slot=37)), (carrying(every), replace(turned, stick=0.0))):
        assert roll(xbe, player) == roll(vanilla, player), player.attack
    for species, kw, mask in (("fire_elemental", {}, every), ("sleeth_x", {}, sum(1 << c for c in (
            0, 3, 6, 9, 12, 16, 19, 23))), ("keylord", {}, None), ("fire_elemental", {"mode": "garret4"}, None),
            ("garret4", {"model_scale": 2.0}, None)):
        built = bytes(_swap(species, sounds="garret4", **kw)["default.xbe"])
        assert (verify_trampoline_patch(built, CARRY_HOOK) == "applied") is (mask is not None), species
        assert mask is None or _param(built, CARRY_HOOK, CARRY_SHIM, "_player_model_carry_columns") == mask

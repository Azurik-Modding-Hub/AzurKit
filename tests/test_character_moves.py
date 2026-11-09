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

import functools
import hashlib
import json
import math
import re
import statistics
import struct
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_FPSW

from azurkit.core import coff, gate
from azurkit.core.xbr.graph import Graph, Schema
from azurkit.core.xbr.nodes import named_resources, parse_toc
from azurkit.tools import characters, mods
from azurkit.tools.characters import _player_character as swapper
from azurkit.tools.characters import _player_fx_ring as fx_ring
from azurkit.tools.characters import _player_variants as variants
from azurkit.tools.characters import ports
from azurkit.tools.characters._player_character import (
    ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, BALANCE_CAP, BALANCE_FLOOR, BLAST_HOLD_HOOK, BLAST_HOOK, BLAST_HOOKS,
    BLAST_LAND_HOOKS, BLAST_SHIM, CARRY_HOOK, CARRY_SHIM, CASTS, CENTRED_DIR, CHAIN_AFTER_HIT, CHAIN_GATES, CHAINED,
    DIRECTION_EDITS, DRAIN_HOOKS, DRAIN_SHIM, DRAIN_STATE, EASE_HOOK, FINISH_RANGE, FINISH_RANGE_HOOK,
    FINISH_ROW, FINISHERS, FX_DEFAULT_HOOK, FX_DRAIN_AT, FX_RING_HOOKS, FX_RING_SHIM, FX_RING_STATE, FX_RING_TABLE,
    FX_ROTATION_AT, GARRET4_SIZES, HIT_DELAY_HOOK, HIT_FX_HOOK, HIT_FX_SHIM, HIT_NEAR, LATCH_HOOK, LIGHT,
    LIGHT_HIT_HOOK, LIGHT_HIT_SHIM, MODE_ANIMS, MODE_GRADES, MODE_SHARES, MODES, MULTIPLIER, NEAR_HOOKS, NEAR_SHIM,
    PUSH_HOOK, PUSH_SHIM, REACH_BUMP, RIG_SITES, RING_ENTRY, RING_SIZE, ROTATE_HOOK, SAME_BUILD, SEARCH_HOOK,
    SEARCH_RADIUS_SYMBOL, SEARCH_SHIM, SEARCH_SITES, SETS_HOOKS, SETS_SHIM, SETS_STATE, SHIM_HOOKS, SLOW_BONUS,
    SLOW_RATIO, STAFF_WALLS, STAFF_X1, STUN_LAG, SUPPORT, THUD_HOOK, THUD_SHIM, TOUCH_HOOK, WINGS_POSE, WINGS_SHIM,
    AttackLogic, _armor_frames, aim_records, anim_strings, attack_sets, attacks, bakes, body_height, combo_rate,
    contact, install_air_blast_shim, install_attack_carry_shim, melee_reach, mode_status, model_sounds, move_window,
    place_anims,
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


def _effects(folder) -> dict:
    """G3's effects recipe file (Modkit's ``tests/fixtures/effects.json``,
    the firelord case's ``variant_file``, which ``tests/goldens/cases.json``
    holds) written in ``folder``: its recipes, as a build reads them."""
    fixture = "tests/fixtures/effects.json"
    cases = json.loads((Path(__file__).with_name("goldens") / "cases.json").read_text(encoding="utf-8"))
    text = json.dumps(next(case["files"][fixture] for case in cases["pipelines.json"].values()
                           if fixture in case.get("files", {})))
    (folder / "effects.json").write_text(text, encoding="utf-8")
    return load_variants(text, str(folder / "effects.json"))


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


def test_a_carried_bodys_held_button_jump_and_landing_keep_it_attacking():
    """D377, D380, D381, D383 (Step 2.140, X33's entries; the owner, of
    booblord: holding attack should chain, a jump should come at once,
    and an air attack had "a long delay" on landing): presses are latched
    edges, so a held button was one press; state 0x100 never calls
    player_jump_init; and the landing classifier 0x85920 turns an air
    attack's 0x102 into 0x100, so its clip played on frozen. L2 on the
    real code at each site (Sim.call to the next callee or the site's
    return; 0x85920, 0x88E70, 0x89060, 0xA30D0 run for real), mask
    0xEFFFFF against the jump attack's column 13 unmasked, column 0
    unmasked and vanilla:
    (a) the attack state's stamps (0x8D3D5-0x8D43C): a held A (B) in a
        carried root-motion swing is stamped 0.25 s back (Step 2.145,
        AZ-633: fresh for the chain's 0.3 s that tick and the next, so a
        tap's tail doesn't chain a second swing), never over a newer stamp,
        its latch kept; else none;
    (b) the airborne state's CALL 0x88E70 (0x8D387): a held A starts the
        air attack (its stamp consumed at 0x88F4D, button 0 at the search
        0x7EF10); unmasked, no press: AL 0, +0x134 := -1;
    (c) the attack state's CALL 0x8C7D0 (0x8D46E): a jump press jumps
        (state 2, v0, the jump's latch) and goes on as the air attack;
        column 13 unmasked, the jump stands with both stamps consumed, so
        the next tick's air start takes none (the critique's C1); an
        uncarried column, and a carried one in the air (PC+0x30 0: the
        attack tick never lands a swing carried off a ledge), ticks
        0x8C7D0 as before;
    (d) the airborne tick's CALL 0x85920 (0x89972-0x89987): a soft landing
        of a carried air attack is state 0 with a held A stamped (0.25 s
        back); else 0x100;
    (e) the air attack's entry tick (0x88990 into 0x102): its desired
        velocity is the root motion plus the jump's, not root alone;
    (a') a column of the held mask alone (Step 2.145, D414: W23's gust,
        sweep1, column 6): a held B is stamped 0.25 s back as in (a); its
        swing's desired velocity is the game's (never carried);
    (f) state 0's CALL 0x89060 (0x8D156-0x8D15F; Step 2.145, D413,
        AZ-630), where a swing carried off a ledge ends (0x8CF8C drops
        0x100 to 0 and dispatches state 0 that tick): a jump press with no
        contact (PC+0x30 0 or 0x150) is AL 0, no jump (state 0, vz and the
        jump's latch as they were); with one, the game's jump (state 2, v0,
        the latch taken); vanilla jumps with none (the bug)."""
    vanilla = _xbe()

    def carrying(mask: int, held: int = 0) -> bytes:
        xbe = bytearray(vanilla)
        install_attack_carry_shim(xbe, mask, held)
        return bytes(xbe)
    every = 0xEFFFFF
    jumpless, columnless = carrying(every & ~(1 << 13)), carrying(every & ~1)
    carried = carrying(every)
    assert l1.check(vanilla, carried) == []
    now, none, held_a = 12.5, (-1.0, -1.0, -1.0), {"attack_buttons": (1.0, 0.0), "attack_latches": (1, 0)}
    swing = replace(BASIC1, state=0x100, move_flags=8, clock=now)
    air = replace(BASIC1, attack=13, attack_anim=0x5F, anim_slot=0x5F, state=0x102, move_flags=8, clock=now)

    def run(xbe: bytes, player, va: int, until: int, args: tuple = (), stubs=None, tick: bool = False) -> PlayerSim:
        """From ``va`` to ``until`` in the state machine 0x8CCC0 (EBP the
        PlayerControl, EDI the input) or, ``tick``, the airborne tick
        0x89480 (the other way round, the hard landing's speed
        sqrt(2 g 2.9) at 0x38B0C4 as 0xFBAC0 sets it at boot)."""
        sim = PlayerSim(xbe, player)
        if tick:
            sim.uc.mem_write(0x38B0C4, struct.pack("<f", math.sqrt(2 * 9.8 * 2.9)))
        pc, inp = sim.at["entity"], sim.at["input"]
        sim.call(va, regs={"ebp": inp, "edi": pc} if tick else {"ebp": pc, "edi": inp}, args=args, until=until,
                 stubs=stubs)
        return sim

    def stamps(sim: PlayerSim) -> tuple:
        return struct.unpack("<3d", sim.uc.mem_read(sim.at["entity"] + 0xA0, 24))

    def latches(sim: PlayerSim) -> bytes:
        return bytes(sim.uc.mem_read(sim.at["controller"] + 0x48, 4))
    # (a) held A and B read as presses
    held = now - 0.25
    for buttons, latch, stamped in (((1.0, 0.0), (1, 0), (held, -1.0, -1.0)), ((0.0, 1.0), (0, 1), (-1.0, held, -1.0))):
        player = replace(swing, attack_buttons=buttons, attack_latches=latch)
        sim = run(carried, player, 0x8D3D5, 0x8D43C)
        assert (stamps(sim), latches(sim)[:2]) == (stamped, bytes(latch)), buttons
        newer = tuple(now - 0.1 if s == held else s for s in stamped)
        assert stamps(run(carried, replace(player, stamps=newer), 0x8D3D5, 0x8D43C)) == newer
        for xbe, other in ((vanilla, player), (columnless, player), (carried, replace(player, anim_slot=37)),
                           (carried, replace(player, move_flags=0))):
            assert stamps(run(xbe, other, 0x8D3D5, 0x8D43C)) == none, buttons
    # (a') a held-only column (the gust's sweep1): stamped, never carried
    gust = replace(swing, attack=6, attack_anim=0x58, anim_slot=0x58, attack_buttons=(0.0, 1.0),
                   attack_latches=(0, 1))
    gusting = carrying(every & ~0x1C0, 0x1C0)
    assert stamps(run(gusting, gust, 0x8D3D5, 0x8D43C)) == (-1.0, held, -1.0)
    assert stamps(run(carrying(every & ~0x1C0), gust, 0x8D3D5, 0x8D43C)) == none
    sweep1 = replace(BASIC1, attack=6, attack_anim=0x58, anim_slot=0x58)
    assert PlayerSim(gusting, sweep1).roll() == PlayerSim(vanilla, sweep1).roll()
    # (b) a held button in the air
    rising = replace(swing, state=2, **held_a)
    sim = run(carried, rising, 0x8D387, 0x7EF10)
    assert (stamps(sim)[0], sim.reg("esi"), sim.u32(sim.at["entity"] + 0x94)) == (-1.0, 0, 2)
    for xbe in (jumpless, vanilla):
        sim = run(xbe, rising, 0x8D387, 0x8D38F)
        assert (sim.reg("eax") & 0xFF, sim.u32(sim.at["entity"] + 0x134)) == (0, 0xFFFFFFFF)
    # (c) a jump press in a swing
    jumping = replace(swing, stamps=(now - 1 / 30, now - 1 / 30, -1.0))
    v0 = math.sqrt(2 * 9.8 * 1.1)
    sim = run(carried, jumping, 0x8D46E, 0x7EF10, stubs=l2.JUMP_STUBS)
    assert (sim.u32(sim.at["entity"] + 0x94), stamps(sim)[0], sim.reg("esi"), latches(sim)[3]) == (2, -1.0, 0, 1)
    assert sim.f32(sim.at["entity"] + 0x2C) == pytest.approx(v0, rel=1e-6)
    sim = run(jumpless, jumping, 0x8D46E, 0x8D474, stubs=l2.JUMP_STUBS)
    assert (sim.u32(sim.at["entity"] + 0x94), stamps(sim)) == (2, none)
    for xbe, player in ((columnless, jumping), (vanilla, jumping), (carried, replace(jumping, object_ptr=0))):
        sim = run(xbe, player, 0x8D46E, 0x8C7D0)
        esp = sim.reg("esp")
        assert (sim.u32(esp), sim.u32(esp + 4), sim.u32(sim.at["entity"] + 0x94), latches(sim)[3]) == (
            0x8D474, sim.at["entity"], 0x100, 0)
    # (d) a carried air attack's soft landing: the classifier's query on the airborne tick's stack
    frame = [0] * 70
    frame[28] = struct.unpack("<I", struct.pack("<f", -4.0))[0]   # the result's vz (S+0x74), S = ESP at 0x89972
    frame[66] = 1                                                 # the query's +0x38 (S+0x10C): a contact
    landing = replace(air, **held_a)
    for xbe, state, stamped in ((carried, 0, held), (jumpless, 0x100, -1.0), (vanilla, 0x100, -1.0)):
        sim = run(xbe, landing, 0x89972, 0x89987, args=tuple(frame), tick=True)
        assert (sim.u32(sim.at["entity"] + 0x94), stamps(sim)[0]) == (state, stamped)
    # (e) the air entry keeps the jump's velocity
    flying = replace(air, state=2, velocity=(3.0, 0.0, v0))
    root = PlayerSim(vanilla, flying).enter(0x102)
    assert PlayerSim(carried, flying).enter(0x102) == pytest.approx(
        tuple(r + v for r, v in zip(root, flying.velocity)), rel=1e-6)
    assert PlayerSim(jumpless, flying).enter(0x102) == root
    # (f) no jump from state 0 without a contact
    for xbe, contact, jumped in ((carried, 0, False), (carried, 0x150, False), (carried, swing.object_ptr, True),
                                 (vanilla, 0, True)):
        sim = run(xbe, replace(swing, state=0, object_ptr=contact), 0x8D156, 0x8D15F, stubs=l2.JUMP_STUBS)
        e = sim.at["entity"]
        assert (sim.reg("eax") & 0xFF, sim.u32(e + 0x94), latches(sim)[3]) == ((1, 2, 1) if jumped else (0, 0, 0))
        assert sim.f32(e + 0x2C) == (pytest.approx(v0, rel=1e-6) if jumped else 0.0), (contact, jumped)


def _ring_table(xbe: bytes) -> dict:
    """X38's table in a built ``xbe`` (``fx_ring.c``'s ``Table``, decoded)."""
    at = resolve_va_to_file(xbe, trampoline_symbol_va(xbe, FX_RING_HOOKS[0], FX_RING_TABLE.symbol,
                                                      shim_source=FX_RING_SHIM.source_path()))
    t = bytes(xbe[at:at + fx_ring.TABLE_SIZE])
    n_keys, n_clips, n_ops, n_wins = struct.unpack_from("<BBHH", t)
    o = 8 + fx_ring.ROWS
    keys = [struct.unpack_from("<BBBBHHHH", t, o + 12 * k) for k in range(n_keys)]
    o += 12 * fx_ring.KEYS
    clips = [[struct.unpack_from("<HHf", t, o + 8 * (fx_ring.KEYS * c + k)) for k in range(n_keys)]
             for c in range(n_clips)]
    o += 8 * fx_ring.KEYS * fx_ring.CLIPS
    names = [t[o + fx_ring.KEY_SIZE * k:o + fx_ring.KEY_SIZE * (k + 1)].split(b"\0")[0].decode() for k in range(n_keys)]
    o += fx_ring.KEY_SIZE * fx_ring.KEYS
    ops = [struct.unpack_from("<HBBf", t, o + 8 * i) for i in range(n_ops)]
    o += 8 * fx_ring.OPS
    wins = [struct.unpack_from("<HHBBHf", t, o + 12 * i) for i in range(n_wins)]
    lists = "spawn", "delay", "arm", "own", "hold", "detach", "show"
    drain_at = [struct.unpack_from("<I", xbe, resolve_va_to_file(xbe, trampoline_symbol_va(
        xbe, hook, FX_DRAIN_AT.symbol, shim_source=FX_RING_SHIM.source_path())))[0] for hook in FX_RING_HOOKS]
    return {"rows": {r: c for r, c in enumerate(t[8:8 + fx_ring.ROWS]) if c != 0xFF},
            "keys": [{"name": name, "mode": "EPSB"[mode], "slots": slots, "delay": delay, "records": records,
                      "hold_ms": hold,
                      "ops": {(lists[op[2]], op[0], op[1]): round(op[3], 4) for op in ops[first:first + n]}}
                     for name, (mode, slots, delay, _, records, first, n, hold) in zip(names, keys)],
            "firsts": [[f for f, _, _ in per] for per in clips],
            "windows": [[{(w[0], w[1], w[2]): (bool(w[3] & fx_ring.WIN_RIG), round(w[5], 4))
                          + ((w[4],) if w[3] & fx_ring.WIN_SWITCH else ()) for w in wins[f:f + n]}
                         for f, n, _ in per] for per in clips],
            "tails": [[round(tail, 2) for _, _, tail in per] for per in clips], "drain_at": drain_at}


@pytest.mark.parametrize("species, kw", [
    ("air_elemental", {}), ("spideyzar", {}), ("beamlord", {}), ("blaze_sentinel", {}), ("guard_fire1", {}),
    ("garret4", {}), ("air_elemental", {"mode": "garret4"}), ("fire_elemental", {}),
    ("air_elemental", {"fx_ring": False})])
def test_a_ranged_bodys_attack_effects_get_their_own_ring(species, kw, monkeypatch):
    """D429, D430 (Step 2.149, X38): a build whose attack clips turn an
    emitter of the body's fx_default on (a switch's link) or carry one
    away (2 model units or more from its rest) hooks player_attack_enter's
    CALL 0x4FF10 at 0x88A5E, the anim step's CALL 0xCBC80 at 0x43A62 and
    the hit handler's CALL 0x44640 at 0x8D6AF (AZ-650, Step 2.155) and
    writes the ring's table: per row (a column, or an X10 entry) its
    clip, per clip each window (the emitter, the record and attribute
    that close it, rig, its end in clip seconds) and the tail (the
    longest sink maxAge + 0.33 s), the key's slots and writes. The air
    elemental's own graph is a P key (its puff [7], on at rest, rides the
    gust's m_turbulence: off 0.95 at the arrival, its sink 5 s), muted on
    the own instance for good, armed at 117 a second (fx_ring.arm,
    AZ-651) and kept in 11 copies (a 10-record graph's 12, capped at the
    ring's 16 less the stand key's 5: her recipe names no slots), and spideyzar's
    graph a STAND key (D434, Step 2.155; since Step 2.155b, D501, the
    player's clone of it, characters/air_elemental/v/fx/fx_stand: 5 copies, dark but for the
    platform rule (since Step 2.155e its funnel mesh [84], which its trigger alone shows, keeps its
    lodVisibility; since Step 2.155g a delay op draws it at gameVisible 1/1024 once the crossfade is
    over, AZ-690), its trigger [34] held 2.0 s (1.5 before Step 2.155e), tail 1.73 s, its carrier
    m_projectile leaving at 0.367 s, no windows); spideyzar's columns
    are his clips' rows (his attack sets keep X10 off, Step 2.135), his
    234-record graph 4 copies, his
    linked iceball [25] and dome [84] hidden on a copy by lodVisibility
    and his attack_3 steam [57] closing through its system [172];
    beamlord's bolts [24] (the player's clone of his graph, X40) close
    at 0.65 by their rate (the enable is linked; the nova's at 0.88, on
    through its shield's fade: AZ-658, Step 2.153b) and the grafted electric
    shield's platform [67] (v4's nova), whose gameVisible a link drives,
    is hidden by its lodVisibility at the spawn, and the air blast's
    grafted floor dome [69] (Step 2.153b) by its gameVisible, whose bolts
    close at its impact, 1.78 (the draw skips gameVisible x
    lodVisibility <= 0, 0xC3128); blaze's waist blast [38], [46] closes on
    the rig and its ambient fires and thrust plates are muted on the copy.
    Balthazar's attack_2 switches his drain's damage [46], so it gets no
    row (the reason logged), and guard_fire's attack_2 its shards' critter
    generator, but since Step 2.175 (AZ-611) guard_fire1's 12 attack_2
    columns play ``q/0``, the clip without that switch, an E key of its
    graph (4 copies; its fire emitters closing at 3.08 and 3.15 s), and a copy spawned in
    the drain's crossfade (Balthazar's beam) has the drain stream's pool
    [2] shut at the spawn (AZ-653, Step 2.155); but with X37 installed
    (AZ-653, Step 2.153c: Balthazar's and beamlord's builds, whose X38
    landings each carry X37's state) the drain, its box [46] under the
    mode-7 'onPlayer', is a row: its stream [44] closes by its switch [42]
    at 2.05 (through [2] on another clip's copy), [46]'s damage goes 0
    at the detach (list DETACH), the own instance's pool [2] is off while
    a copy shows it, and no spawn close is left; garret4's own build,
    the air elemental's Skin build (no gust), the fire elemental (no attack
    keys an fx marker) and a recipe's ``fx_ring: false`` keep vanilla's
    CALLs at the three sites."""
    vanilla = _xbe()
    if kw.get("fx_ring") is False:   # the overlay's knob off
        monkeypatch.setitem(variants.OVERLAYS, species, {**variants.OVERLAYS[species], "fx_ring": False})
        game = _swap(species, fresh=True)
    else:
        game = _swap(species, **kw)
    xbe = bytes(game["default.xbe"])
    hooked = [verify_trampoline_patch(xbe, hook) for hook in FX_RING_HOOKS]
    sites = [xbe[va_to_file(hook.va):va_to_file(hook.va) + 5] for hook in FX_RING_HOOKS]
    if species in ("garret4", "fire_elemental") or kw:
        assert hooked == ["original"] * 3 and sites == [vanilla[va_to_file(h.va):va_to_file(h.va) + 5]
                                                        for h in FX_RING_HOOKS], (species, kw)
        if species == "garret4":   # Balthazar's drain: left out, logged
            bodies = game.stored("characters.xbr")
            plan = fx_ring.ring_plan(bodies, game.stored("default.xbe"), read_body(bodies, "balthazar_airship"),
                                     {0: "attack_2"})
            assert (plan.rows, plan.left_out) == ({}, [
                "attack_2 (it switches characters/balthazar_airship/fx/fx_default [46] damageBoxShape damage, which "
                "a copy would run twice or hit with)"])
            plan = fx_ring.ring_plan(bodies, game.stored("default.xbe"), read_body(bodies, "balthazar_airship"),
                                     {0: "attack_2", 2: "attack_3"})   # AZ-653: the beam copy's drain pool shut
            assert fx_ring.Op(2, 4, 0.0, fx_ring.SPAWN) in plan.keys[0].ops
            plan = fx_ring.ring_plan(bodies, game.stored("default.xbe"), read_body(bodies, "balthazar_airship"),
                                     {0: "attack_2", 2: "attack_3"}, drains=True)   # AZ-653 (2.153c): X37's row
            assert (plan.rows, plan.clips, plan.left_out, plan.windows[0]) == (
                {0: 0, 2: 1}, ["attack_2", "attack_3"], [], [((fx_ring.Window(44, 2, 4, False, 2.05, 42),), 2.33)])
            ops = set(plan.keys[0].ops)
            assert {fx_ring.Op(46, 17, 0.0, fx_ring.DETACH), fx_ring.Op(2, 4, 1.0, fx_ring.OWN)} <= ops and not {
                op for op in ops if (op.record, op.list) == (2, fx_ring.SPAWN)}
        return
    assert hooked == ["applied"] * 3 and l1.check(vanilla, xbe) == []
    table = _ring_table(xbe)
    keys, rows = table["keys"], table["rows"]
    clip = rows[6] if species == "air_elemental" else None
    if species == "air_elemental":
        assert ([(k["name"], k["mode"], k["slots"], k["records"], k["delay"], k["hold_ms"]) for k in keys] == [
            ("characters/air_elemental/fx/fx_default", "P", 11, 10, 1, 0),   # no slots in her recipe: her 12 capped
            ("characters/air_elemental/v/fx/fx_stand", "S", 5, 234, 1, 2000)])   # at 16 less his 5 (D434, D501)
        assert set(rows) == {6, 7, 8} and len(set(rows.values())) == 1 and table["drain_at"] == [0] * 3   # no X37
        assert keys[0]["ops"] == {("delay", 7, 4): 1.0, ("arm", 7, 5): 117.0, ("own", 7, 4): 1.0}
        assert keys[1]["ops"] == {("spawn", 25, 0): 0.0, ("spawn", 149, 17): 0.0, ("delay", 84, 10): 0.001,
                                  **{("spawn", r, 10): 0.0 for r in (68, 70, 72)}, ("hold", 34, 3): 1.0}
        assert (table["windows"][clip], table["tails"][clip], table["firsts"][clip][1]) == (
            [{(7, 7, 4): (False, 0.95)}, {}], [5.33, 1.73], 367)   # the stand copy: its carrier leaves at 0.367 s
    elif species == "spideyzar":
        assert max(rows) < fx_ring.COLUMNS and keys[0]["mode"] == "E" and keys[0]["slots"] == 4   # no X10 rows
        whirl = table["windows"][rows[3]][0]   # finish: whirlwind
        assert whirl == {(e, e, 4): (True, 1.9333) for e in (37, 41, 45, 47, 49, 51, 53)}   # its funnel, cut at 0.34
        assert {k for k in keys[0]["ops"] if k[1] in (25, 84)} == {("spawn", 25, 0), ("spawn", 84, 0)}
        assert (57, 172, 4) in table["windows"][rows[2]][0]   # basic3: attack_3's steam, through [172]
    elif species == "guard_fire1":   # AZ-611: its attack_2 columns' q/0, no shards' generator switched
        assert [(k["name"], k["mode"], k["slots"]) for k in keys] == [
            ("characters/bosses/fire_guardian/fx/fx_default", "E", 4)]
        assert set(rows) == {1, 3, 5, 7, 9, 11, 13, 14, 16, 18, 21, 23} and set(rows.values()) == {0}
        assert {e: end for (e, _, _), (_, end) in table["windows"][0][0].items()} == {
            **dict.fromkeys((113, 115, 117), 3.0833), **dict.fromkeys((126, 128, 130, 132), 3.15)}
    elif species == "beamlord":   # his key is the player's clone (X40, Step 2.157), which his own instance plays;
        # Step 2.153: the air blast carries his bolts down (delayed), on to its impact (Step 2.153b: no bolts in the
        # blast, its floor dome hidden on a copy)
        assert keys[0]["name"] == "characters/balthazar_airship/v/fx/fx_default"
        assert keys[0]["ops"] == {("spawn", 46, 17): 0.0, ("spawn", 67, 0): 0.0,
                                  ("spawn", 69, 10): 0.0,   # the blast's floor dome (Step 2.153b): hidden on a copy
                                  ("detach", 46, 17): 0.0,   # AZ-653 (Step 2.153c): the drain row's box at the detach
                                  ("delay", 24, 5): 80.0,
                                  ("own", 24, 5): 80.0, ("own", 2, 4): 1.0}   # v4's rate; the drain's pool
        assert {w for per in table["windows"] for w in per[0].items()} == {
            ((24, 24, 5), (False, 1.65)), ((24, 24, 5), (False, 0.65)), ((24, 24, 5), (False, 1.7833)),
            ((24, 24, 5), (False, 0.8833)),   # Step 2.153b: the blast's bolt to its impact, the nova's on through its
            ((44, 2, 4), (False, 2.05, 42))}  # shield's fade (AZ-658); AZ-653: elemental2's drain, closed by its switch
        assert table["rows"][10] == 0 and table["drain_at"] == [trampoline_symbol_va(
            xbe, DRAIN_HOOKS[0], DRAIN_STATE, shim_source=DRAIN_SHIM.source_path())] * 3   # X37's state, in each
    else:   # blaze_sentinel
        assert table["windows"] == [[{(38, 38, 4): (True, 3.85), (46, 46, 4): (True, 3.85)}]]
        muted = {(r, a) for (kind, r, a) in keys[0]["ops"] if kind == "spawn"}
        assert muted == {(r, 10) for r in (9, 14, 20, 22)} | {
            (r, 4) for r in (3, 6, 12, 17, 28, 57, 59, 61, 63, 65, 67, 69, 71)}
        assert {k for k in keys[0]["ops"] if k[0] == "own"} == {("own", 38, 4), ("own", 46, 4)}


def test_bound_keys_follow_the_own_and_stand_keys_each_row_its_own_clip_entry(monkeypatch):
    """Step 2.167c (D538's E3; pure): X38's plan puts a build's BOUND keys
    after its own graph's and a stand's: a row whose clip has the own
    key's windows and plays a bound key gets a clip entry of its own (those
    windows and the stand's leave kept), a column only a bound row names
    gets one too, and so does X10's entry row once a listed column is one
    X10 turns; each bound key's first is 1 on the entries that play it;
    the own and stand keys keep their 16 handles (17 refused by name), a
    bound key takes 1 of the ring's 20, and a fade the u16 ms can't hold is
    refused by name."""
    win = fx_ring.Window(7, 7, 4, False, 0.95)
    base = fx_ring.Plan([fx_ring.Key("own", fx_ring.P, 11, 10, 1, ()),
                         fx_ring.Key("stand", fx_ring.STAND, 5, 234, 1, (), 2000)],
                        {6: 0, 7: 0, 24: 0}, ["sweep1"], [[((win,), 5.33), ((), 1.73)]], [], {(0, 1): 367})
    monkeypatch.setattr(fx_ring, "own_plan", lambda *a, **k: base)
    bubble = fx_ring.Bound("v/fx/fx_bubble_0", 5, (6, 2), ((4, 10, 1.0),), 0.3, 0.0)
    plan = fx_ring.ring_plan(b"", b"", None, {2: "attack_3", 6: "sweep1", 7: "sweep1"}, ["sweep1"],
                             bound=(bubble,), turns=1 << 6)
    assert (plan.rows, plan.clips) == ({2: 0, 6: 1, 7: 2, 24: 1},
                                       ["attack_3 +fx_bubble_0", "sweep1 +fx_bubble_0", "sweep1"])
    assert plan.windows == [[((), 0.0), ((), 0.0), ((), 0.0)], [((win,), 5.33), ((), 1.73), ((), 0.0)],
                            [((win,), 5.33), ((), 1.73), ((), 0.0)]]
    assert plan.leaves == {(0, 2): 1, (1, 1): 367, (1, 2): 1, (2, 1): 367, (2, 2): 0}
    assert plan.keys[2] == fx_ring.Key("v/fx/fx_bubble_0", fx_ring.BOUND, 1, 5, 0,
                                       (fx_ring.Op(4, 10, 1.0, fx_ring.SHOW),), 300)
    assert len(plan.pack()) == fx_ring.TABLE_SIZE
    base.keys[0] = replace(base.keys[0], slots=12)
    with pytest.raises(ValueError, match="the fx ring holds 16 copies of the body's own and stand keys"):
        fx_ring.ring_plan(b"", b"", None, {6: "sweep1"}, bound=(bubble,)).pack()
    with pytest.raises(ValueError, match="fx_bubble_0's fade 70 s is not from 0 to 65.535 s"):
        fx_ring.ring_plan(b"", b"", None, {6: "sweep1"}, bound=(replace(bubble, fade=70.0),))




def test_the_fx_ring_shows_a_bound_effects_rows_copy_while_its_column_plays_then_fades_it(tmp_path):
    """D538's E3 (Step 2.167c; L2, :class:`_RingSim`): a shield or beam
    ``effects`` row is a BOUND key of X38's table, its own graph in one
    handle (shieldlord's build, G3's effects recipe file, :func:`_effects`: keylord,
    whose own graph gets no key, so its bubble, dome and laser are keys 0-2,
    the own instance never written), each row's column its clip entry, its
    show write its key's one op, its fade its hold_ms.  At rest nothing
    spawns; basic1's entry spawns the bubble's graph bound (the bind
    interface critter+0x170) with its show [4].gameVisible at 1 (dirty
    0x400), and the attack's own change lets nothing go; the idle's change
    lets it go on the body (no detach): 1 there, 0.5 at 0.15 s; basic1
    again while it fades re-arms it (no spawn, back at 1); an unlisted
    column's entry lets it go and spawns nothing, and it is 0 and dead
    0.3 s on (its tail 0); once the engine has deleted it the finish's
    entry spawns the dome; basic2's lets the dome go and spawns the laser
    (its burst's enable [2] 1), which a hit lets go (0.5 at 0.15 s); at
    HP 0 basic1 spawns nothing, and once HP is back it spawns the bubble
    again.  ESP, EBX, ESI, EDI and EBP as the CALLs left them, the x87
    stack empty; L1 clean."""
    variant = _effects(tmp_path)["shieldlord"]
    built = bytes(_swap(variant.base, variant=variant)["default.xbe"])
    assert l1.check(_xbe(), built) == []
    columns = XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section("attacks_anims").col_names()
    b1, b2, fin, other = (columns.index(c) for c in ("basic1", "basic2", "finish", "basic3"))
    table = _ring_table(built)
    bubble, dome, laser = (fx_ring.bound_key("keylord", t, k) for k, t in enumerate(("bubble", "dome", "laser")))
    assert [(k["name"], k["mode"], k["slots"], k["records"], k["hold_ms"], k["ops"]) for k in table["keys"]] == [
        (bubble, "B", 1, 6, 300, {("show", 5, 10): 1.0}), (dome, "B", 1, 6, 300, {("show", 5, 10): 1.0}),
        (laser, "B", 1, 15, 300, {("show", 3, 4): 1.0})]
    order = sorted((b1, fin, b2))
    assert table["rows"] == {c: order.index(c) for c in order}   # a clip entry per row: each plays its own key
    assert [table["firsts"][table["rows"][c]] for c in (b1, fin, b2)] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert table["tails"][table["rows"][b2]][2] == 0.38 and table["windows"] == [[{}, {}, {}]] * 3
    r = _RingSim(built, ("characters/keylord/fx/fx_default", 1, {}), {bubble: (6, {}), dome: (6, {}), laser: (15, {})})
    tick, enter, attr, dirty = r.tick, r.enter, r.attr, r.dirty
    r.layers(0, c0=(r.IDLE, 0.5))
    assert tick(10.0) == []                                               # at rest: nothing
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    ((_, name, wd, _, flags, bind, shield, handle),) = enter(b1, 11.0)
    assert (name, wd, flags, bind) == (bubble, r.world, 0, r.critter + 0x170)
    assert (attr(shield, 5, 10), dirty(shield, 5) & 0x400) == (1.0, 0x400)
    assert tick(11.05) == [] and attr(shield, 5, 10) == 1.0              # the attack's own change
    r.layers(0, 0.25, c0=(r.IDLE, 0.0))
    assert tick(11.5) == [] and attr(shield, 5, 10) == 1.0                # let go on the body: no detach
    tick(11.65)
    assert attr(shield, 5, 10) == pytest.approx(0.5, abs=1e-5)
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    assert enter(b1, 11.7) == [] and attr(shield, 5, 10) == 1.0           # re-armed while it fades
    r.layers(2, 0.1, c2=(r.SWING, 0.0))
    assert enter(other, 12.0) == [] and attr(shield, 5, 10) == 1.0        # an unlisted column: let go
    tick(12.15)
    assert (attr(shield, 5, 10), r.dead(shield)) == (pytest.approx(0.5, abs=1e-5), 0)
    tick(12.31)
    assert (attr(shield, 5, 10), r.dead(shield)) == (0.0, 1)              # its fade and its 0 s tail over
    r.w(handle, struct.pack("<I", 0))                                    # the engine deletes it, zeroing the handle
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    assert [c[1] for c in enter(fin, 13.0)] == [dome]
    r.layers(2, 0.1, c2=(r.SWING, 0.0))
    ((_, name, *_, beam, _),) = enter(b2, 13.2)
    assert name == laser and attr(beam, 3, 4) == 1.0
    r.layers(0, 0.25, c0=(r.OUCH, 0.0), c2=(r.SWING, 0.2))               # X7's reaction, then the hit
    assert r.hit(13.4, 90) == []                                          # lets the laser go
    tick(13.55)
    assert attr(beam, 3, 4) == pytest.approx(0.5, abs=1e-5)
    r.w(r.critter + 0x210, struct.pack("<i", 0))                          # HP 0: nothing spawns
    tick(13.9)
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    assert enter(b1, 14.0) == []
    r.w(r.critter + 0x210, struct.pack("<i", 100))
    tick(14.1)
    r.layers(2, 0.1, c2=(r.ATTACK, 0.0))
    assert [c[1] for c in enter(b1, 14.2)] == [bubble]


class _RingSim:
    """X38's three landings of a built ``xbe`` under L2, the engine's five calls emulated (quat_from_euler
    0x4FF10, the sampler 0xCBC80, fx_instantiate 0x649E0, fx_instance_detach 0x634B0, apply_damage 0x44640:
    its HP written) and the critter, world, anim, instances and records fake: ``looks`` is the key's (resource,
    records, authored values per record and attribute), every instance's nodes 40 attributes, the own one
    (critter+0x230) loaded with them too, a node with a damage value a platform (its world object at node+0x20,
    its level byte +0x27E that damage); ``links`` the key's links (source -> (target, attribute), factor 1, at
    node+0xC); ``more`` another key's (resource -> records, values: a stand key's)."""

    NODE, ATTRS = 0xC8, 0x28

    def __init__(self, built: bytes, looks: tuple, more: dict | None = None, links: dict | None = None):
        self.built, self.key, self.records, self.values = built, *looks
        self.more, self.links = more or {}, links or {}
        self.sim = sim = Sim(built)
        base = 0x20000000
        sim.uc.mem_map(base, 0x800000)
        (self.critter, self.other, self.world, cellobj, self.anim, self.clock, self.pc, self.out,
         self.ring10) = (base + 0x1000 * k for k in range(9))
        self.own, self.objects, self.heap = base + 0x10000, base + 0x20000, base + 0x30000
        self.IDLE, self.ATTACK, self.SWING, self.OUCH = (base + 0x9000 + 0x100 * k for k in range(4))
        w = self.w = sim.uc.mem_write
        w(self.critter + 0x154, struct.pack("<2I", self.world, base + 0x4000 + 4 * 0xB4))
        w(self.critter + 0x17C, struct.pack("<I", self.anim))
        w(self.critter + 0x210, struct.pack("<i", 100))
        w(self.critter + 0x230, struct.pack("<I", self.own + 0x20))
        w(self.other + 0x154, struct.pack("<I", self.world))
        w(self.world + 0xBC, struct.pack("<I", self.critter))
        w(self.world + 0xD4, struct.pack("<I", cellobj))
        w(cellobj + 0x28, struct.pack("<I", base + 0x4000))
        w(self.anim + 4, struct.pack("<I", self.clock))
        w(self.pc + 0x20, struct.pack("<I", self.critter))
        self.instance(self.own)
        self.calls: list = []
        for va, hook in ((0x4FF10, self._quat), (0xCBC80, self._sample), (0x649E0, self._spawn),
                         (0x634B0, self._detach), (0x44640, self._damage)):
            sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)
        self.ring = trampoline_symbol_va(built, FX_RING_HOOKS[0], FX_RING_STATE, shim_source=FX_RING_SHIM.source_path())

    def instance(self, at: int, key: str | None = None) -> int:
        w = self.w
        records, values = self.more.get(key, (self.records, self.values))
        w(at + 0x24, struct.pack("<2I", at + 0x200, at + 0x200 + 4 * records))
        w(at + 0xA0, struct.pack("<I", 2))
        w(at + 0x1C0 + 0xC, struct.pack("<I", 40))
        nodes = at + 0x200 + 4 * records
        for j in range(records):
            node = nodes + self.NODE * j
            w(at + 0x200 + 4 * j, struct.pack("<I", node))
            w(node + 8, struct.pack("<I", node + self.ATTRS))
            w(node + 0x14, struct.pack("<I", at + 0x1C0))
            for a, v in values.get(j, {}).items():
                w(node + self.ATTRS + 4 * a, struct.pack("<f", v))
            if 17 in values.get(j, {}):                                   # a platform: its object at its level
                w(node + 0x20, struct.pack("<I", self.objects))
                w(self.objects + 0x27E, bytes([int(values[j][17])]))
                self.objects += 0x300
        for src, outs in (self.links if key in (None, self.key) else {}).items():
            for dst, a in outs:                                           # {next, plug, target, weight, curve, factor}
                w(self.objects, struct.pack("<IHHIfIf", self.sim.u32(nodes + self.NODE * src + 0xC), 0, a,
                                            nodes + self.NODE * dst, 1.0, 0, 1.0))
                w(nodes + self.NODE * src + 0xC, struct.pack("<I", self.objects))
                self.objects += 0x18
        return at

    def node(self, inst: int, rec: int) -> int:
        return self.sim.u32(inst + 0x200 + 4 * rec)

    def attr(self, inst: int, rec: int, a: int) -> float:
        return self.sim.f32(self.node(inst, rec) + self.ATTRS + 4 * a)

    def put(self, inst: int, rec: int, a: int, v: float) -> None:
        self.w(self.node(inst, rec) + self.ATTRS + 4 * a, struct.pack("<f", v))

    def level(self, inst: int, rec: int) -> int:
        """A platform's level byte (its world object's +0x27E: what a touch tests)."""
        return self.sim.uc.mem_read(self.sim.u32(self.node(inst, rec) + 0x20) + 0x27E, 1)[0]

    def factors(self, inst: int, src: int) -> dict:
        """Each link of record ``src``: (its target record, attribute) -> its factor."""
        out, lk, nodes = {}, self.sim.u32(self.node(inst, src) + 0xC), self.node(inst, 0)
        while lk:
            nxt, _, a, dst = struct.unpack("<IHHI", self.sim.uc.mem_read(lk, 12))
            out[((dst - nodes) // self.NODE, a)] = self.sim.f32(lk + 0x14)
            lk = nxt
        return out

    def dirty(self, inst: int, rec: int) -> int:
        return self.sim.u32(self.node(inst, rec) + 0x10)

    def dead(self, inst: int) -> int:
        return self.sim.u32(inst + 0x2C) & 1

    def _back(self, uc, pop: int) -> None:
        esp = self.sim.reg("esp")
        uc.reg_write(UC_X86_REG_EIP, self.sim.u32(esp))
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)

    def _quat(self, uc, addr, size, _):
        self.calls.append(("quat", self.sim.reg("esi")))
        self._back(uc, 12)

    def _sample(self, uc, addr, size, _):
        self.calls.append(("sample", *struct.unpack("<2I", uc.mem_read(self.sim.reg("esp") + 4, 8))))
        self._back(uc, 8)

    def _spawn(self, uc, addr, size, _):
        handle, key, wd, cell, flags, bind, *zeros = struct.unpack("<9I", uc.mem_read(self.sim.reg("esp") + 4, 36))
        inst = self.instance(self.heap, self.sim.cstr(key))
        self.heap += 0x40000
        self.w(handle, struct.pack("<I", inst + 0x20))
        self.calls.append(("spawn", self.sim.cstr(key), wd, cell & 0xFFFF, flags, bind, inst, handle))
        self._back(uc, 36)

    def _detach(self, uc, addr, size, _):
        self.calls.append(("detach", self.sim.reg("esi")))
        self._back(uc, 0)

    def _damage(self, uc, addr, size, _):
        critter, hp, flag = struct.unpack("<IiI", uc.mem_read(self.sim.reg("esp") + 4, 12))
        self.w(critter + 0x210, struct.pack("<i", hp))
        self.calls.append(("damage", critter, hp, flag))
        self._back(uc, 12)

    def layers(self, live: int, fade: float = 0.25, **clips) -> None:
        self.w(self.anim + 0x10, struct.pack("<if", live, fade))
        for i, (clip, t) in clips.items():
            layer = self.anim + 0x40 + 0x40 * int(i[1])
            self.w(layer + 4, struct.pack("<I", clip))
            self.w(layer + 0x18, struct.pack("<f", t))
            self.w(layer + 0x20, struct.pack("<f", 1.0))

    def _run(self, hook, now: float, regs: dict, args: tuple, first) -> list:
        kept = {"ebx": 0x11, "ebp": 0x22}
        self.w(self.clock + 0x10, struct.pack("<d", now))
        del self.calls[:]
        self.sim.call(hook.va + 5 + struct.unpack_from("<i", self.built, va_to_file(hook.va) + 1)[0],
                      regs={**regs, **kept}, args=args, until=l2._RETURN)
        sim = self.sim
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and {r: sim.reg(r) for r in (*regs, *kept)} == {**regs, **kept}
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0 and self.calls[0] == first
        return self.calls[1:]

    def tick(self, now: float, who: int | None = None) -> list:
        return self._run(FX_RING_HOOKS[1], now, {"esi": who or self.critter}, (self.anim, 0x1AA800),
                         ("sample", self.anim, 0x1AA800))

    def enter(self, column: int, now: float) -> list:
        self.w(self.pc + 0x134, struct.pack("<i", column))
        return self._run(FX_RING_HOOKS[0], now, {"edi": self.pc, "esi": self.out}, (0, 0, 0), ("quat", self.out))

    def hit(self, now: float, hp: int) -> list:
        """The hit handler's CALL of apply_damage (ESI the PlayerControl) leaving the player at ``hp``."""
        return self._run(FX_RING_HOOKS[2], now, {"esi": self.pc, "edi": 0x33}, (self.critter, hp, 0),
                         ("damage", self.critter, hp, 0))

    def rotation(self, at: int) -> None:
        """Every landing's bytes param ``player_model_fx_rotation_at`` := ``at``."""
        for hook in FX_RING_HOOKS:
            self.w(trampoline_symbol_va(self.built, hook, FX_ROTATION_AT.symbol,
                                        shim_source=FX_RING_SHIM.source_path()), struct.pack("<I", at))


def test_the_fx_ring_spawns_arms_detaches_and_ends_an_attacks_copy(monkeypatch):
    """D429, D430 (Step 2.149, X38; L2, :class:`_RingSim`). The air
    elemental's own build (her graph a P key): the anim step's landing
    calls the sampler with its two arguments for every critter and returns
    at once for one that isn't the world's player; the player's first tick
    writes the own instance's puff enable 0 (dirty 0x10, once: a second
    run that tick writes nothing) and spawns the resting copy (the key, the
    world, the cell's index, flags 0, the bind interface critter+0x170, a
    handle in the ring), its puff off until the crossfade (anim+0x14) and
    a tick are over, then back on. A gust's entry (sweep1) arms it (rate
    117, dirty 0x20: AZ-651) and spawns nothing; the next tick sees no change. The
    held re-throw at the arrival detaches it (its puff, a window, left on)
    before it spawns and arms the next; the detached copy's puff fades its
    rate over 10 ticks from its 0.95 end and closes (enable 0), and the copy
    is dead (instance+0x2C bit 0) past its 5.33 s tail; a copy that isn't
    loaded (state 1) gets no write and counts as guarded; a clip change the
    tick sees (the live layer another) detaches the armed copy and spawns a
    resting one, which the next gust arms; a melee swing's entry (basic1, no
    row) detaches it and arms nothing; at HP 0 every bound copy is detached,
    a resting one's pending delay with it (its puff stays off), and none
    spawned until HP is back; a column X10 rotates takes its entry's row
    (none here: nothing armed); (l) a hit mid-gust (AZ-650, Step 2.155:
    the hit handler's CALL of apply_damage, X7's reaction already the
    live layer) writes the HP, detaches the armed copy in the call and
    spawns nothing, the next tick sees no change and spawns a resting
    one; a lethal hit detaches it the same and no resting copy follows.
    (m) D434 (Step 2.155), her build with the stand key held 1.5 s
    ((a)-(l) run without it): at rest her own copy alone; a gust's entry also spawns
    spideyzar's graph (the player's clone of it, Step 2.155b: bound, its platforms hidden, its damage 0;
    AZ-690, Step 2.155g: its funnel mesh [84], which its trigger alone shows, at gameVisible 0 until the
    crossfade and a tick are over, then 1/1024, so the game loads its mesh's and textures' runs while
    it is bound and its first presents at the let-go are textured, not black); a
    re-throw 1.55 s on detaches both and spawns both again; the detached
    stand copy's trigger [34].translateZ follows his own curve (0.75 at
    0.4 s, 1.0 at 1.0 s), holds 1.0 (no write), falls over 1.2 s, 0.5 at
    2.1 s and 0 by 2.7 s (dirty 0x8 on each change), and the copy is dead
    past 1.5 + 1.2 + its 1.73 s tail; (n) one detached at clip 0.2 s (before its
    carrier left at 0.367 s) is dead at once, its trigger never written;
    (o) every gust spawns its copy (AZ-671); in a held chain (AZ-664) one
    let go by the next gust's entry under 1.5 s after the last standing
    one was let go is dead at once, one let go 1.6 s after stands (a dead
    one counts for none), and a chain's last gust, let go by the idle,
    stands; AZ-689: one while five of his stand, the oldest's trigger back
    at 0 (faded), ends that one and takes its handle; AZ-661: one while
    five stand with every funnel still up spawns none, and once the oldest
    has ended the next gust takes its handle; a gust let go by a melee
    swing's entry (column 0, no row) 0.8 s after the last standing one was
    let go stands: only a gust chains it. (q) AZ-689 on the ring's own
    2.0 s hold: TAPN's taps, one every 1.2 s, each gust let go by the idle
    1.1 s in, stand every gust's funnel, the sixth's entry ending the
    first (faded since 3.2 s, its trigger 0) a tick before its own end.
    Spideyzar's own build (E, X10 off):
    attack_3's entry (column 2) spawns its copy, its linked iceball [25]
    and dome [84] hidden by lodVisibility (dirty 1, gameVisible left to the
    switch), its drain damage [149] 0, another clip's window (the
    whirlwind's [37]) closed by its enable at the arm and its own [8] left
    as authored (AZ-652, Step 2.155), and the own instance's attack_3
    emitters ([8], [10], the steam's system [172]) off while it is bound;
    a hit's clip change at 0.5 s detaches it, the own ones stay off for the
    crossfade and a tick (the slide home) and come back; the copy's rig
    windows fade from 0.33 s past the detach, [8] closes by its enable and
    the steam [57] by its rate alone (its system's enable stays 1: its
    particles age out), and the copy is dead past its 1.33 s tail.
    (p) AZ-653 (Step 2.153c), Balthazar's own build (X37's state in the
    landings): basic2's drain spawns its copy, its pool [2] on (no spawn
    close), the own pool off while it shows it; basic3 at the drain's
    1.5 clip s detaches it, its box [46]'s damage the link left goes 0
    (dirty), {the copy, X37's target} goes into X37's held list, and the
    beam's copy has the drain's pool [2] off (others_off) and (AZ-683,
    Step 2.175d) none of the box's damage: the switch's link into it at
    factor 0 (its link into the stream, the drain's copy's and the own
    instance's as they were), and each copy's box object at level 0 from
    its load (the own one at its authored 2); a held entry no
    slot plays out is pruned at the tick; the drain's window ends at 2.05
    clip s (0.55 s on): its switch [42].translateZ := 0 (dirty 0x8; the
    rate and the pool's enable untouched: its particles age out) and the
    copy leaves the list; dead past its 2.33 s tail; (AZ-684, Step
    2.153d) a second drain's held copy whose entry X37 left with no
    target (dead or deleted) has its switch 0 at the next tick, 0.45 s
    before its window's end, and leaves the list, dead past the same
    tail; a third, detached while X37 holds no target, is listed without
    one and closed at the next tick the same; (D567, Step 2.153e) inside
    a fourth, bound: X37's target left from an earlier window counts for
    nothing until X37 evaluates the drain (its seen stamp moves), a drain
    that never held one plays on (no detach, the switch untouched), and
    once it held one and holds none (dead, none in reach) the next tick
    detaches the copy, its box's damage 0, its switch 0 at once (dirty
    0x8) and its held entry left; the own pool stays off while the clip
    plays on, past the detach's crossfade, and for the idle's crossfade
    and a tick, then back on. ESP,
    EBX, ESI, EDI and EBP as the CALLs left them, the x87 stack empty; L1
    clean (no SSE2, the callees' RET N kept)."""
    taps = bytes(_swap("air_elemental")["default.xbe"])                    # (q): the ring's own stand, held 2.0 s
    ring = variants.OVERLAYS["air_elemental"]["fx_ring"]                  # (m)-(o) on a stand held 1.5 s (2.0 since
    monkeypatch.setitem(variants.OVERLAYS, "air_elemental", {**variants.OVERLAYS["air_elemental"], "fx_ring": {
        **ring, "stand": {**ring["stand"], "hold": 1.5}}})                 # Step 2.155e: the timing's the ring's)
    stood = bytes(_swap("air_elemental", fresh=True)["default.xbe"])                   # D434's stand key, for (m) and (n)
    ring = variants.OVERLAYS["air_elemental"]["fx_ring"]
    monkeypatch.setitem(variants.OVERLAYS, "air_elemental", {**variants.OVERLAYS["air_elemental"], "fx_ring": {
        k: v for k, v in ring.items() if k != "stand"}})                  # (a)-(l): her own key alone
    built = bytes(_swap("air_elemental", fresh=True)["default.xbe"])
    assert l1.check(_xbe(), built) == [] and l1.check(_xbe(), stood) == []
    r = _RingSim(built, ("characters/air_elemental/fx/fx_default", 10, {7: {4: 1.0, 5: 15.0}}))
    tick, enter, attr, dirty, own = r.tick, r.enter, r.attr, r.dirty, r.own
    r.layers(0, c0=(r.IDLE, 0.5))
    assert tick(10.0, r.other) == [] and r.sim.u32(r.ring + 4) == 0       # (d) another critter: the sampler alone
    (made,) = tick(10.0)                                                  # (e) the player's first tick
    _, name, wd, cell, flags, bind, rest, handle = made
    assert (name, wd, cell, flags, bind) == (r.key, r.world, 4, 0, r.critter + 0x170)
    assert r.ring <= handle < r.ring + 0x800 and r.sim.u32(handle) == rest + 0x20
    assert (attr(own, 7, 4), dirty(own, 7), attr(rest, 7, 4)) == (0.0, 0x10, 0.0)
    r.w(r.node(own, 7) + 0x10, struct.pack("<I", 0))
    assert tick(10.0) == [] and dirty(own, 7) == 0                        # once, by value
    tick(10.27)
    assert attr(rest, 7, 4) == 0.0
    tick(10.3)                                                            # (f) after 0.25 s and a tick
    assert attr(rest, 7, 4) == 1.0
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))                                  # (a) sweep1's gust arms it
    assert enter(6, 11.0) == [] and (attr(rest, 7, 5), dirty(rest, 7) & 0x20) == (117.0, 0x20)
    assert tick(11.05) == []                                              # the attack's own change: none
    r.layers(2, 0.1, c1=(r.ATTACK, 0.95), c2=(r.ATTACK, 0.0))             # (b) the held re-throw
    got = enter(7, 11.95)
    assert [c[:2] for c in got] == [("detach", rest), ("spawn", r.key)]
    rest2 = got[1][6]
    assert (attr(rest, 7, 4), attr(rest2, 7, 4), attr(rest2, 7, 5)) == (1.0, 0.0, 117.0)
    tick(12.0)                                                            # (h) the window fades, then closes
    assert attr(rest, 7, 5) == pytest.approx(117.0 * (1 - 0.05 * 3), rel=1e-5)
    tick(12.3)
    assert (attr(rest, 7, 5), attr(rest, 7, 4), attr(rest2, 7, 4)) == (0.0, 0.0, 1.0)
    tick(17.6)                                                            # (i) past its 5.33 s tail
    assert r.dead(rest) == 0
    tick(17.7)
    assert r.dead(rest) == 1
    r.w(rest2 + 0xA0, struct.pack("<I", 1))                               # (j) not loaded: no write
    before, was = r.sim.u32(r.ring + 8), dirty(rest2, 7)
    tick(17.8)
    assert r.sim.u32(r.ring + 8) == before + 1 and dirty(rest2, 7) == was
    r.w(rest2 + 0xA0, struct.pack("<I", 2))
    r.layers(0, 0.25, c0=(r.IDLE, 0.0))                                   # (g) the idle after the throw
    got = tick(18.0)
    assert [c[:2] for c in got] == [("detach", rest2), ("spawn", r.key)]
    rest3 = got[1][6]
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    assert enter(6, 18.5) == [] and attr(rest3, 7, 5) == 117.0
    r.layers(2, 0.1, c2=(r.SWING, 0.0))                                   # (c) a melee swing: no row
    assert enter(0, 19.0) == [("detach", rest3)]
    rest4 = tick(19.1)[0][6]                                              # its change noted: a resting copy
    r.w(r.critter + 0x210, struct.pack("<i", 0))                          # (k) HP 0, the copy's delay pending
    assert tick(19.2) == [("detach", rest4)] and tick(19.6) == [] and enter(6, 19.6) == []
    assert attr(rest4, 7, 4) == 0.0
    r.w(r.critter + 0x210, struct.pack("<i", 100))
    rest5 = tick(19.7)[0][6]
    r.rotation(r.ring10)                                                  # X10's ring rotating sweep1
    r.w(r.ring10, struct.pack("<3I", 3, 1, 1 << 6))                       # its entry's row (24) has no copy
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    assert enter(6, 20.0) == [] and attr(rest5, 7, 5) == 15.0
    r.w(r.ring10, struct.pack("<3I", 0, 0, 0))                            # (l) a hit mid-gust (AZ-650)
    assert enter(6, 20.5) == [] and attr(rest5, 7, 5) == 117.0
    r.layers(2, 0.25, c1=(r.ATTACK, 0.3), c2=(r.OUCH, 0.0))               # X7's reaction, before any re-sample
    assert r.hit(20.8, 90) == [("detach", rest5)] and r.sim.u32(r.critter + 0x210) == 90
    (made,) = tick(20.85)                                                 # the change noted: a resting copy
    rest6 = made[6]
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    assert enter(6, 21.0) == [] and attr(rest6, 7, 5) == 117.0
    r.layers(0, 0.25, c0=(r.OUCH, 0.0), c1=(r.ATTACK, 0.2))
    assert r.hit(21.2, 0) == [("detach", rest6)]                          # lethal: out where it was
    assert tick(21.25) == [] and tick(21.3) == []                         # no resting copy at HP 0

    spider = "characters/air_elemental/v/fx/fx_stand"                      # (m) D434: his tornado (D501's clone) stands
    r = _RingSim(stood, (r.key, 10, {7: {4: 1.0, 5: 15.0}}), {spider: (234, {25: {0: 1.0, 10: 1.0}, 149: {17: 2.0}})})
    tick, enter, attr, dirty = r.tick, r.enter, r.attr, r.dirty
    r.layers(0, c0=(r.IDLE, 0.5))
    rest = tick(10.0)[0][6]                                               # at rest her own copy alone
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    ((_, name, *_, funnel, _),) = enter(6, 11.0)                          # the gust: his graph, bound and dark
    assert name == spider and (attr(funnel, 25, 0), attr(funnel, 149, 17), attr(funnel, 84, 10)) == (0.0, 0.0, 0.0)
    tick(11.1)                                                            # AZ-690: its funnel mesh [84] dark for the
    assert attr(funnel, 84, 10) == 0.0                                    # crossfade (0.1 s) and a tick, then drawn
    tick(11.14)                                                           # at 1/1024, too faint to show, so its runs
    assert (attr(funnel, 84, 10), dirty(funnel, 84) & 0x400) == (1 / 1024, 0x400)   # load before the let-go
    r.layers(2, 0.1, c1=(r.ATTACK, 0.95), c2=(r.ATTACK, 0.0))             # a re-throw 1.55 s on (AZ-664)
    got = enter(7, 12.55)
    assert [c[:2] for c in got] == [("detach", rest), ("detach", funnel), ("spawn", r.key), ("spawn", spider)]
    rest2, funnel2 = got[2][6], got[3][6]
    for now, z, wrote in ((12.95, 0.75, 0x8), (13.55, 1.0, 0x8), (13.9, 1.0, 0), (14.65, 0.5, 0x8),
                          (15.35, 0.0, 0x8), (15.5, 0.0, 0)):              # his rise, the hold, the fall
        r.w(r.node(funnel, 34) + 0x10, struct.pack("<I", 0))
        tick(now)
        assert (attr(funnel, 34, 3), dirty(funnel, 34)) == (pytest.approx(z, abs=1e-3), wrote), now
    tick(16.9)
    assert r.dead(funnel) == 0
    tick(17.0)                                                            # past 1.5 + 1.2 + its 1.73 s tail
    assert r.dead(funnel) == 1
    r.layers(0, 0.25, c0=(r.IDLE, 0.0), c2=(r.ATTACK, 0.2))               # (n) cut before its carrier left
    assert [c[:2] for c in tick(17.9)][:2] == [("detach", rest2), ("detach", funnel2)]
    assert (r.dead(funnel2), attr(funnel2, 34, 3), dirty(funnel2, 34)) == (1, 0.0, 0)
    stands, gust = [], [0]                                                # (o) AZ-671, AZ-664, AZ-661

    def throw(now):
        live, done = (1, 2) if gust[0] % 2 == 0 else (2, 1)
        r.layers(live, 0.1, **{f"c{live}": (r.ATTACK, 0.0), f"c{done}": (r.ATTACK, 0.95)})
        got = [c[6] for c in enter(6 + gust[0] % 2, now) if c[:2] == ("spawn", spider)]
        gust[0] += 1
        stands.extend(got)
        return len(got)

    def idle(now):                                                        # the last gust's clip left for the idle
        r.layers(0, 0.25, c0=(r.IDLE, 0.0), **{f"c{2 - gust[0] % 2}": (r.ATTACK, 0.95)})
        tick(now)
    assert [throw(now) for now in (18.0, 18.8, 19.6, 20.4)] == [1] * 4    # every gust spawns its copy
    assert [r.dead(f) for f in stands] == [0, 1, 0, 0]                    # let go 0.8 s after the first: dead;
    idle(21.35)                                                           # 1.6 s: stands; the last, 0.95 s: stands
    throw(21.5), idle(22.0), throw(22.1), idle(22.6)                      # two taps: each stands
    assert [r.dead(f) for f in stands] == [0, 1, 0, 0, 0, 0] and throw(22.7) == 1   # five stand, the oldest
    assert r.dead(stands[0]) == 1 and attr(stands[0], 34, 3) == 0.0       # faded: it ends, its handle the gust's
    idle(22.75)
    assert throw(22.8) == 0                                               # five, every funnel up: none (AZ-661)
    tick(24.9)                                                            # the third has ended: its handle
    assert throw(25.0) == 1 and r.dead(stands[-2]) == 0
    r.layers(2, 0.1, c1=(r.ATTACK, 0.8), c2=(r.SWING, 0.0))               # a swing 0.8 s on lets the gust go
    assert [c[:2] for c in enter(0, 25.8)][-1] == ("detach", stands[-1])
    assert [r.dead(f) for f in stands[-2:]] == [0, 0]                     # not chained: it stands
    r = _RingSim(taps, (r.key, 10, {7: {4: 1.0, 5: 15.0}}), {spider: (234, {25: {0: 1.0, 10: 1.0}, 149: {17: 2.0}})})
    tick, enter, attr = r.tick, r.enter, r.attr                           # (q) AZ-689 on the ring's own 2.0 s hold
    r.layers(0, c0=(r.IDLE, 0.5))
    tick(30.0)
    stands[:] = []
    for i in range(6):                                                    # TAPN: a tap every 1.2 s, each gust let
        assert throw(31.0 + 1.2 * i) == 1                                 # go by the idle 1.1 s in; the sixth's
        idle(32.1 + 1.2 * i)                                              # entry ends the first, faded since 3.2 s
    assert [r.dead(f) for f in stands] == [1, 0, 0, 0, 0, 0] and attr(stands[0], 34, 3) == 0.0

    built = bytes(_swap("spideyzar")["default.xbe"])                      # E: spideyzar's attack_3
    r = _RingSim(built, ("characters/balthazar_spider/fx/fx_default", 234, {
        8: {4: 1.0, 5: 20.0}, 10: {4: 1.0, 5: 20.0}, 57: {4: 1.0, 5: 30.0}, 172: {4: 1.0},
        25: {0: 1.0, 10: 1.0}, 84: {0: 1.0, 10: 1.0}, 149: {17: 2.0}, 37: {4: 1.0}}))
    tick, enter, attr, dirty, own = r.tick, r.enter, r.attr, r.dirty, r.own
    r.rotation(0)
    r.layers(0, c0=(r.IDLE, 0.5))
    assert tick(10.0) == [] and dirty(own, 172) == 0                      # no copy at rest, the own as authored
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    ((_, name, *_, copy, _),) = enter(2, 11.0)
    assert name == r.key
    assert [(attr(copy, p, 0), dirty(copy, p), attr(copy, p, 10)) for p in (25, 84)] == [(0.0, 1, 1.0)] * 2
    assert attr(copy, 149, 17) == 0.0
    assert (attr(copy, 37, 4), dirty(copy, 37), attr(copy, 8, 4)) == (0.0, 0x10, 1.0)   # AZ-652: whirlwind's shut
    tick(11.05)
    assert [attr(own, rec, 4) for rec in (8, 10, 172)] == [0.0] * 3
    r.layers(0, 0.25, c0=(r.IDLE, 0.0), c1=(r.ATTACK, 0.5))               # a hit cuts it at 0.5 s
    assert tick(11.5) == [("detach", copy)]
    tick(11.75)
    assert attr(own, 172, 4) == 0.0                                       # its markers still sliding home
    tick(11.8)
    assert [attr(own, rec, 4) for rec in (8, 10, 172)] == [1.0] * 3
    tick(11.9)                                                            # the rig windows: from 0.33 s past
    assert attr(copy, 57, 5) == pytest.approx(30.0 * (1 - 0.07 * 3), rel=1e-4)
    tick(12.2)
    assert (attr(copy, 57, 5), attr(copy, 172, 4), attr(copy, 8, 5), attr(copy, 8, 4)) == (0.0, 1.0, 0.0, 0.0)
    tick(13.45)
    assert r.dead(copy) == 0
    tick(13.55)
    assert r.dead(copy) == 1

    built = bytes(_swap("balthazar", sounds="garret4")["default.xbe"])     # (p) AZ-653: his drain row (X37)
    held = trampoline_symbol_va(built, DRAIN_HOOKS[0], DRAIN_STATE, shim_source=DRAIN_SHIM.source_path()) + 64
    r = _RingSim(built, ("characters/balthazar_airship/v/fx/fx_default", 64, {
        42: {3: 1.0}, 44: {4: 100.0, 5: 30.0}, 2: {4: 1.0}, 46: {17: 2.0}, 17: {4: 1.0}, 24: {5: 80.0}}),
        links={42: [(44, 4), (46, 17)]})                                  # the switch's: the stream and the box
    tick, enter, attr, dirty, own = r.tick, r.enter, r.attr, r.dirty, r.own
    linked = {(44, 4): 1.0, (46, 17): 1.0}
    r.layers(0, c0=(r.IDLE, 0.5))
    assert tick(10.0) == []
    target = (r.other, 0x19FC08, 0x12345)                                 # X37's target, with its identity (AZ-682)
    r.w(held - 60, struct.pack("<3I", *target))                           # the drained critter
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))                                  # basic2: the drain
    ((_, name, *_, drain, _),) = enter(1, 11.0)
    assert (name, attr(drain, 2, 4), attr(drain, 46, 17)) == (r.key, 1.0, 0.0)   # its pool on; damage the link's
    assert (r.level(drain, 46), r.factors(drain, 42)) == (0, linked)      # AZ-683: the box's authored level off
    tick(11.05)
    assert attr(own, 2, 4) == 0.0                                          # the own drain's pool off: the copy shows it
    r.put(drain, 46, 17, 2.0)                                       # the switch's link, bound
    r.layers(2, 0.1, c1=(r.ATTACK, 1.5), c2=(r.SWING, 0.0))               # basic3 at drain clip 1.5 s: the beam
    got = enter(2, 11.6)
    assert [c[:2] for c in got] == [("detach", drain), ("spawn", r.key)]
    beam = got[1][6]
    assert (attr(drain, 46, 17), dirty(drain, 46) & 1 << 17, attr(drain, 42, 3)) == (0.0, 1 << 17, 1.0)   # DETACH
    assert struct.unpack("<8I", r.sim.uc.mem_read(held, 32)) == (drain, *target, 0, 0, 0, 0)   # on X37's target
    assert (attr(beam, 2, 4), dirty(beam, 2) & 0x10, attr(beam, 44, 4)) == (0.0, 0x10, 100.0)   # its drain's shut
    assert (r.level(beam, 46), r.factors(beam, 42)) == (0, {(44, 4): 1.0, (46, 17): 0.0})   # AZ-683: no damage
    assert r.factors(drain, 42) == r.factors(own, 42) == linked and r.level(own, 46) == 2   # from the switch
    r.w(held + 16, struct.pack("<4I", 0x12345, *target))                  # a copy no slot plays out
    tick(12.1)                                                            # its window to 2.05 clip s: 12.15
    assert (attr(drain, 42, 3), attr(drain, 44, 5), r.sim.u32(held), r.sim.u32(held + 16)) == (1.0, 30.0, drain, 0)
    r.w(r.node(drain, 42) + 0x10, struct.pack("<I", 0))
    tick(12.2)                                                            # the switch 0 (its links: [44], [46])
    assert (attr(drain, 42, 3), dirty(drain, 42), attr(drain, 2, 4), attr(drain, 44, 5)) == (0.0, 0x8, 1.0, 30.0)
    assert struct.unpack("<2I", r.sim.uc.mem_read(held, 8)) == (0, 0)     # off the target
    tick(14.45)
    assert r.dead(drain) == 0
    tick(14.5)                                                            # past its 2.33 s tail
    assert r.dead(drain) == 1
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))                                  # AZ-684: a second drain
    (drain2,) = [c[6] for c in enter(1, 15.0) if c[:2] == ("spawn", r.key)]
    r.layers(2, 0.1, c1=(r.ATTACK, 1.5), c2=(r.SWING, 0.0))
    assert [c[:2] for c in enter(2, 15.6)][0] == ("detach", drain2)        # held on X37's target to 16.15
    assert struct.unpack("<4I", r.sim.uc.mem_read(held, 16)) == (drain2, *target)
    r.w(held + 4, struct.pack("<I", 0))                                   # X37 dropped it: dead or deleted
    r.w(r.node(drain2, 42) + 0x10, struct.pack("<I", 0))
    tick(15.7)                                                            # the switch 0 at once, the entry left
    assert (attr(drain2, 42, 3), dirty(drain2, 42), r.sim.u32(held)) == (0.0, 0x8, 0)
    tick(18.45)
    assert r.dead(drain2) == 0                                            # it lives to the window's end and its tail
    tick(18.5)
    assert r.dead(drain2) == 1
    r.w(held - 60, struct.pack("<3I", 0, 0, 0))                           # a drain X37 holds no target for
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))
    (drain3,) = [c[6] for c in enter(1, 19.0) if c[:2] == ("spawn", r.key)]
    r.layers(2, 0.1, c1=(r.ATTACK, 1.5), c2=(r.SWING, 0.0))
    assert [c[:2] for c in enter(2, 19.6)][0] == ("detach", drain3)
    tick(19.7)                                                            # listed with none: closed at once
    assert (attr(drain3, 42, 3), r.sim.u32(held)) == (0.0, 0)
    seen = held - 40                                                      # D567: X37's last evaluation's clock
    r.w(held - 60, struct.pack("<3I", *target))                           # a target left from an earlier window
    r.w(seen, struct.pack("<d", 20.0))
    r.layers(1, 0.1, c1=(r.ATTACK, 0.0))                                  # a fourth drain, bound
    (drain4,) = [c[6] for c in enter(1, 21.0) if c[:2] == ("spawn", r.key)]
    tick(21.05)                                                           # X37 hasn't evaluated it yet
    r.w(held - 60, struct.pack("<I", 0))
    r.w(seen, struct.pack("<d", 21.06))                                   # its window: none in reach
    assert (tick(21.1), attr(drain4, 42, 3)) == ([], 1.0)                 # never held one: it plays on
    r.w(held - 60, struct.pack("<I", target[0]))
    r.w(seen, struct.pack("<d", 21.13))                                   # an enemy picked
    assert tick(21.15) == []
    r.w(held - 60, struct.pack("<I", 0))                                  # dead, none in reach: dropped
    r.put(drain4, 46, 17, 2.0)                                     # the switch's link, bound
    r.w(r.node(drain4, 42) + 0x10, struct.pack("<I", 0))
    assert tick(21.2) == [("detach", drain4)]                             # let go at once, held with none
    assert (attr(drain4, 46, 17), attr(drain4, 42, 3), dirty(drain4, 42), r.sim.u32(held)) == (0.0, 0.0, 0x8, 0)
    tick(21.7)                                                            # the clip plays on: the own pool off
    assert attr(own, 2, 4) == 0.0
    r.layers(0, 0.2, c0=(r.IDLE, 0.0))                                    # the idle: its crossfade and a tick
    tick(22.0)
    tick(22.2)
    assert attr(own, 2, 4) == 0.0
    tick(22.25)
    assert attr(own, 2, 4) == 1.0


def test_beamlords_air_blast_jumps_to_its_impact_when_he_lands():
    """D451 (Step 2.153, X39; the owner: "an air attack which is him
    firing a bolt straight downwards that expands into an aoe blast"):
    beamlord's jump attack plays his air_blast clip, its bolt phase until
    the impact (1.8 clip s); no box meets the floor, so the blast has to
    come from his landing. The build hooks the attack state's chain
    check's CALL 0xCB020 at 0x8D44D, and (Step 2.153b) the state
    machine's CALL 0x89480 at 0x8D39A and the classifier's two CALLs of
    the hard landing 0x8B100 at 0x85A7C and 0x85B65 (beamlord's alone:
    plain Balthazar's keeps them), each landing with his blast mask
    (column 13) and impact. L2 at each entry (X39 alone on vanilla, the
    callee stubbed), column 13 playing and its slot (0x5F) still the
    critter's: (a) 0x8D44D in state 0x100: the top layer's time goes
    0.4 -> 1.8 and 2.0 stays 2.0; state 0x102 (still in the air),
    another slot (a hard landing's touchdown), another column or a layer
    with no clip leave it; 0xCB020 gets ECX, the anim object, once; a
    plain RET, EBX, EDX, ESI, EDI and EBP kept; (b) 0x8D39A in state
    0x102: the time 1.79 is held at 1.5 (the impact less 0.3: a tick's
    advance comes after it), 0.4 stays, and 2.0 stays (a ground blast
    whose floor went is 0x102 again: never rewound); state 0x100, another slot or
    column leave it; 0x89480 gets EDI and its argument as the game set
    them, once, and pops the argument (RET 4); every register kept; (c)
    0x85A7C and 0x85B65 in state 0x102: the soft landing's writes, +0x94
    0x100 and +0x16C's bit 2, the hard landing's copy of the move result's
    +0xC0 velocity into +0x24 (fall damage reads its z), and a plain RET
    without 0x8B100; another
    column, slot or state: 0x8B100 gets EAX, ECX and EDX as the game set
    them, once, and nothing is written."""
    built = bytes(_swap("beamlord")["default.xbe"])
    plain = bytes(_swap("balthazar")["default.xbe"])
    assert [verify_trampoline_patch(built, hook) for hook in BLAST_HOOKS] == ["applied"] * 4
    assert [verify_trampoline_patch(plain, hook) for hook in BLAST_HOOKS] == ["original"] * 4
    assert [[_param(built, hook, BLAST_SHIM, f"_player_model_blast_{k}") for k in ("columns", "impact")]
            for hook in BLAST_HOOKS] == [[1 << 13, pytest.approx(1.8)]] * 4
    vanilla = _xbe()
    blasting = bytearray(vanilla)
    install_air_blast_shim(blasting, 1 << 13, 1.8)
    assert l1.check(vanilla, built) == l1.check(vanilla, bytes(blasting)) == []

    def entry(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", blasting, va_to_file(hook.va) + 1)[0]
    base = 0x20000000
    pc, critter, anim, clip, inp = (base + 0x1000 * k for k in range(5))

    def staged(state: int, column: int, slot: int, time: float, played: int) -> Sim:
        sim = Sim(bytes(blasting))
        sim.uc.mem_map(base, 0x8000)
        for at, data in ((pc + 0x20, struct.pack("<I", critter)), (pc + 0x94, struct.pack("<i", state)),
                         (pc + 0x134, struct.pack("<i", column)), (pc + 0x16C, b"\x10"),
                         (critter + 0x17C, struct.pack("<I", anim)), (critter + 0x200, struct.pack("<i", slot)),
                         (anim + 0x10, struct.pack("<i", 1)), (anim + 0x84, struct.pack("<I", played)),
                         (anim + 0x98, struct.pack("<f", time)), (clip + 0x10, struct.pack("<f", 3.0))):
            sim.uc.mem_write(at, data)
        return sim

    def callee(sim: Sim, va: int, seen: list, regs: tuple[str, ...], pops: int) -> None:
        def hit(uc, addr, size, _):   # the game's callee: what it was given, then RET (pops)
            esp = sim.reg("esp")
            seen.append(tuple(sim.reg(r) for r in regs) + tuple(sim.u32(esp + 4 * (k + 1)) for k in range(pops // 4)))
            uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4 + pops)
        sim.uc.hook_add(UC_HOOK_CODE, hit, begin=va, end=va)

    def landed(*, state: int = 0x100, column: int = 13, slot: int = 0x5F, time: float = 0.4, played: int = clip
               ) -> float:   # (a)
        sim, seen = staged(state, column, slot, time, played), []
        callee(sim, 0xCB020, seen, ("ecx",), 0)
        kept = {"ebx": 0x11, "edx": 0x22, "esi": 0x33, "edi": 0x44, "ebp": pc}
        sim.call(entry(BLAST_HOOK), regs={**kept, "ecx": anim}, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and seen == [(anim,)]
        assert {r: sim.reg(r) for r in kept} == kept
        return sim.f32(anim + 0x98)
    assert (landed(), landed(time=2.0)) == (pytest.approx(1.8), 2.0)
    for kw in ({"state": 0x102}, {"slot": 0x25}, {"column": 12, "slot": 0x5E}, {"played": 0}):
        assert landed(**kw) == pytest.approx(0.4), kw

    def held(*, state: int = 0x102, column: int = 13, slot: int = 0x5F, time: float = 1.79) -> float:   # (b)
        sim, seen = staged(state, column, slot, time, clip), []
        regs = {"eax": 0x55, "ebx": 0x11, "ecx": 0x66, "edx": 0x22, "esi": 0x33, "edi": pc, "ebp": 0x77}
        callee(sim, 0x89480, seen, tuple(regs), 4)
        sim.call(entry(BLAST_HOLD_HOOK), regs=regs, args=(inp,), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and seen == [(*regs.values(), inp)]
        assert {r: sim.reg(r) for r in regs} == regs
        return sim.f32(anim + 0x98)
    assert (held(), held(time=0.4), held(time=2.0)) == (pytest.approx(1.5), pytest.approx(0.4), 2.0)
    for kw in ({"state": 0x100}, {"slot": 0x25}, {"column": 12, "slot": 0x5E}):
        assert held(**kw) == pytest.approx(1.79), kw

    moved, fall = base + 0x5000, struct.pack("<3f", 0.25, -0.5, -9.75)

    def touched(hook, *, state: int = 0x102, column: int = 13, slot: int = 0x5F) -> tuple:   # (c)
        sim, seen = staged(state, column, slot, 1.5, clip), []
        sim.uc.mem_write(moved + 0xC0, fall)
        regs = {"eax": moved, "ecx": pc, "edx": inp, "ebx": 0x11, "esi": 0x33, "edi": 0x44, "ebp": 0x77}
        callee(sim, 0x8B100, seen, ("eax", "ecx", "edx"), 0)
        sim.call(entry(hook), regs=regs, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100
        assert {r: sim.reg(r) for r in ("ebx", "esi", "edi", "ebp")} == {r: regs[r] for r in ("ebx", "esi", "edi", "ebp")}
        return seen, sim.u32(pc + 0x94), sim.uc.mem_read(pc + 0x16C, 1)[0], bytes(sim.uc.mem_read(pc + 0x24, 12))
    for hook in BLAST_LAND_HOOKS:
        assert touched(hook) == ([], 0x100, 0x14, fall), hook.va
        for kw in ({"column": 12, "slot": 0x5E}, {"slot": 0x0B}, {"state": 0x100}):
            assert touched(hook, **kw) == ([(moved, pc, inp)], kw.get("state", 0x102), 0x10, bytes(12)), (hook.va, kw)


@pytest.mark.parametrize("region", REGIONS)
def test_white_cycles_a_swapped_bodys_attack_sets_and_direction_never_picks(region):
    """D325, D326, D352 (Step 2.135, X36; the owner: WHITE cycles which
    attacks are used, direction shouldn't restrict them, and a short line
    names the set) and D441 (Step 2.153: the line in the HUD's top-left
    corner, small): the transition search 0x7EF10 keyed the column on the
    stick's direction (a sideways stick played right1/left1, never the
    combo's forward rows), and nothing cycled. X36 in own body:
    (a) the build: the search's je at 0x7EF90 and the three direction
        writes' imm32 hold forward (USA; Europe each 0x50 lower), the three
        hooks land, the white and HUD landings point at the search's
        state, the HUD landing at its release's 2D material (0x97420,
        Europe 0x974F0), the map holds the set count and each set's columns
        (spideyzar three, its finisher in finish, finish2 and finish3;
        beamlord's from his recipe, the air elemental's gust from W23),
        the lines the sets' (set_lines, whole names wrapped at 40
        characters) in the HUD landing's copy too; attacks_transitions'
        combo rows 28-31 keep their target features at the default chain
        (AzurKit's D1045, where Modkit's D432 cleared them: a recipe's
        ``chain`` "any" clears them, ``test_characters.py``'s chain test),
        16 and 32 keep theirs; X10 off with two sets or more;
        Balthazar one set; garret4's own body and Skin only keep every byte
        of 0x7EF10's, the three CALLs and the six cells;
    (b) L2 at 0x88D78's entry (0x7EF10 stubbed, 0x7F1F0 real): in set 2 a
        combo column C the search picks plays the set's column S: S's
        record, PC+0x134 S, the yaw H for an empty Aim, else the game's
        yaw plus C's Aim less S's (the same target); the next search of
        a set's swing still playing (+0x200 0x52 + S) is keyed on C; the
        stub sees the six arguments, AL and CL as the game passed them;
        set 1 and a column past finish3 are the game's; RET 0x18, EBX,
        ESI, EDI and EBP kept;
    (c) L2 at 0x854B4's entry (0x84940 real): a fresh WHITE press
        selects the next set (its latch taken) and shows its line for 2.0
        s; held (latched), swimming (state 6) or while the presses wait no
        cycle, the latch still taken (WHITE held onto land never cycles);
        past 2.0 s or a clock set back no line; outside the attack state
        the last set swing is forgotten; a plain RET;
    (d) L2 at 0x1B306's entry (0x1B110, 0xD09E0, 0xD0830, 0x97420 and
        0xD0D60 stubbed): the HUD's list is drawn first (the HUD its
        argument), then, while the line shows, the font, the anchor left |
        top at 0.8, the material yellow with EDI the font, a draw of each
        of the set's lines, the pen at x 2 and y -2 - font[+8], stepped
        by -font[+4], and the HUD's own anchor (5 at 1.0) back; not
        shown, no font or no material: no draw; RET 4, EBX, ESI, EDI and
        EBP kept."""
    europe = region == "europe"
    game = _swap("spideyzar", sounds="garret4")
    built = bytes(game["default.xbe"])
    search, white, hud = SETS_HOOKS

    def gates(game) -> list:   # attacks_transitions' target features: 16, the combo's 28-31, 32
        t = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_transitions")
        return [t.find_cell("a", "target features", c).string_value for c in (16, *CHAIN_GATES, 32)]
    assert gates(game) == ["stunned frozen"] * 5 + ["stunned"]   # D1045: chain "hit" by default

    def landed(xbe: bytes, hook, symbol: str, size: int) -> bytes:
        at = resolve_va_to_file(xbe, trampoline_symbol_va(xbe, hook, symbol, shim_source=SETS_SHIM.source_path()))
        return xbe[at:at + size]
    for xbe in (built,):
        assert [verify_trampoline_patch(xbe, hook) for hook in (*SETS_HOOKS, ROTATE_HOOK)] == [
            "applied", "applied", "applied", "original"]
        assert all(xbe[(off := patch_spec_site(xbe, spec)[0]):off + len(spec.patch)] == spec.patch
                   for spec in DIRECTION_EDITS)
    state = trampoline_symbol_va(built, search, SETS_STATE, shim_source=SETS_SHIM.source_path())
    assert [struct.unpack("<I", landed(built, hook, "_player_model_sets_state_at", 4))[0]
            for hook in (white, hud)] == [state, state]
    assert landed(built, hud, "_player_model_sets_material", 4) == struct.pack("<I", 0x974F0 if europe else 0x97420)
    rows = landed(built, search, "_player_model_sets_map", 49)
    assert (rows[0], list(rows[1:19])) == (3, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 10, 11, 10, 11, 11, 11])
    lines = ["Attack set 1/3\nattack_1 attack_2 attack_3 whirlwind", "Attack set 2/3\nattack_4 attack_5 attack_6 attack_7",
             "Attack set 3/3\ndeathbeam jump"]
    for hook in (search, hud):
        text = landed(built, hook, "_player_model_sets_lines", 3 * 80)
        assert [text[80 * k:80 * k + 80].rstrip(b"\0").decode() for k in range(3)] == lines
    if europe:
        return
    vanilla = _xbe()
    assert l1.check(vanilla, built) == []
    for name, want in (("beamlord", [[0, 1, 2, 3, 4, 5], [8, 9, 10, 13, 13, 13]]),   # his air blast set 2's 4th
                       ("air_elemental", [[0, 1, 2, 3, 4, 5], [6, 6, 6, 6, 6, 6]]),   # (booblord's sets: her
                       ("balthazar", [[0, 1, 2, 3, 4, 5]])):                           # G3 golden's default.xbe)
        xbe = bytes((_swap(name) if name in builtins() else _swap(name, sounds="garret4"))["default.xbe"])
        got = landed(xbe, search, "_player_model_sets_map", 49)
        assert [list(got[1 + 6 * k:7 + 6 * k]) for k in range(got[0])] == want, name
    for kw in ({"mode": "garret4"}, {"model_scale": 2.0, "species": "garret4"}):
        swapped = _swap(kw.pop("species", "spideyzar"), sounds="garret4", **kw)
        xbe = bytes(swapped["default.xbe"])
        assert gates(swapped) == ["stunned frozen"] * 5 + ["stunned"], kw
        assert [verify_trampoline_patch(xbe, hook) for hook in SETS_HOOKS] == ["original"] * 3, kw
        assert all(xbe[va_to_file(spec.va):va_to_file(spec.va) + len(spec.original)] == spec.original
                   for spec in DIRECTION_EDITS), kw
    base = 0x20000000
    pc, inp, critter, records, clock, font, hud_at = (base + 0x1000 * k for k in range(7))

    def entry(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]

    def record(column: int, aim: float) -> bytes:
        return (struct.pack("<iiif", column * 1000, 0x52 + column, column * 1000 + 2, aim)
                + struct.pack("<18i", *(column * 1000 + 4 + j for j in range(18))))

    def sim_at(aims: dict[int, float], *, set_: int, logical: int = -1, source: int = -1, pressed: float = -1e300,
               column: int = -1, slot: int = 1, now: float = 10.0, move: int = 0) -> Sim:
        sim = Sim(built)
        sim.uc.mem_map(base, 0x8000)
        for at, data in ((pc + 0x20, struct.pack("<I", critter)), (pc + 0xC, struct.pack("<I", clock)),
                         (pc + 0x94, struct.pack("<i", move)), (pc + 0x134, struct.pack("<i", column)),
                         (critter + 0x200, struct.pack("<i", slot)), (clock + 0x10, struct.pack("<d", now)),
                         (0x38BC60, struct.pack("<I", records)), (0x38BC50, struct.pack("<f", math.pi / 180)),
                         (state, struct.pack("<iiiid", set_, logical, source, 0, pressed))):
            sim.uc.mem_write(at, data)
        for k in range(24):
            sim.uc.mem_write(records + 0x58 * k, record(k, aims.get(k, 1e5)))
        return sim

    def sets_state(sim: Sim) -> tuple:
        return struct.unpack("<iiiid", sim.uc.mem_read(state, 24))
    heading, facing = 0.7, 0.25
    sim_args = (pc + 0xDC, *struct.unpack("<2I", struct.pack("<2f", facing, heading)), 1, 1, 0)

    def pick(sim: Sim, picked: int, yaw: float, seen: list) -> None:
        def stub(uc, addr, size, _):   # 0x7EF10: __stdcall(24) with AL, CL; the game's pick
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<7I", uc.mem_read(esp, 28))
            seen.append((tuple(args), sim.reg("eax") & 0xFF, sim.reg("ecx") & 0xFF,
                         struct.unpack("<i", uc.mem_read(pc + 0x134, 4))[0]))
            uc.mem_write(pc + 0x134, struct.pack("<i", picked))
            uc.mem_write(pc + 0xDC, bytes(uc.mem_read(records + 0x58 * picked, 0x58)))
            uc.mem_write(pc + 0x138, struct.pack("<f", yaw))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 4 + 0x18)
        sim.uc.hook_add(UC_HOOK_CODE, stub, begin=0x7EF10, end=0x7EF10)

    def searched(picked: int, yaw: float, aims: dict[int, float], **kw) -> tuple:
        sim, seen = sim_at(aims, **kw), []
        sim.uc.mem_write(inp + 0x38, struct.pack("<f", heading))
        pick(sim, picked, yaw, seen)
        kept = {"ebx": 0x11, "esi": inp, "edi": pc, "ebp": 0x44}
        sim.call(entry(search), regs={**kept, "eax": 0x1201, "ecx": 0x3400}, args=sim_args, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0x18
        assert {r: sim.reg(r) for r in kept} == kept
        assert [s[:3] for s in seen] == [(sim_args, 0x01, 0x00)]
        return (sim.u32(pc + 0x134), bytes(sim.uc.mem_read(pc + 0xDC, 0x58)), sim.f32(pc + 0x138),
                sets_state(sim)[1:3], seen[0][3])
    rec = {k: record(k, a) for k, a in ((7, 1e5), (6, 0.0), (9, 0.0))}
    assert searched(1, heading, {}, set_=1)[:4] == (7, rec[7], _f32(heading), (1, 7))   # basic2 -> sweep2
    assert searched(0, 1.2, {0: 0.0, 6: 0.0}, set_=1)[:4] == (6, rec[6], _f32(1.2), (0, 6))
    assert searched(0, 1.2, {0: 0.0, 6: 30.0}, set_=1)[2] == pytest.approx(1.2 - math.radians(30), abs=1e-6)
    assert searched(4, 1.2, {4: 0.0, 9: 0.0}, set_=1)[:4] == (9, rec[9], _f32(1.2), (4, 9))   # finish2's
    assert searched(1, 0.5, {}, set_=1, logical=0, source=6, column=6, slot=0x58)[4] == 0   # keyed on basic1
    assert searched(1, 0.5, {}, set_=1, logical=0, source=6, column=6, slot=1)[4] == 6    # its swing over
    for set_, picked in ((0, 1), (1, 6)):   # the game's combo; a sweep
        got = searched(picked, 0.5, {}, set_=set_)
        assert (got[0], got[3][0]) == (picked, -1), set_
    pad = l2.CONTROLLERS

    def pressed(*, white_: float = 1.0, latch: int = 0, locked: int = 0, **kw) -> tuple:
        sim = sim_at({}, **kw)
        sim._name(l2.CONTROLLER_INDEX, "I", 0)   # the guarded pad globals, named
        sim._name(pad + 0x2C, "f", white_)
        sim._name(pad + 0x4D, "B", latch)
        sim.uc.mem_write(inp + 0x30, bytes([locked]))
        kept = {"ebx": 0x11, "esi": inp, "edi": 0x33, "ebp": pc, "ecx": inp}
        sim.call(entry(white), regs=kept, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # a plain RET
        return sets_state(sim), sim.uc.mem_read(pad + 0x4D, 1)[0]
    got, latch = pressed(set_=0, now=10.0)
    assert (got[0], got[3], got[4], latch) == (1, 1, 10.0, 1)
    assert pressed(set_=2)[0][0] == 0                                      # the third wraps to the first
    for kw in ({"move": 6}, {"latch": 1}, {"locked": 1}):
        got, latch = pressed(set_=0, **kw)
        assert (got[0], got[3], latch) == (0, 0, 1), kw
    for since, shows in ((1.0, True), (2.5, False), (-5.0, False)):
        got, _ = pressed(set_=1, white_=0.0, pressed=10.0 - since, now=10.0)
        assert got[:1] + got[3:4] == (1, int(shows)), since

    def drawn(*, shown: int = 1, typeface: int = font, material: int = 1) -> list:
        sim = sim_at({}, set_=1)
        sim.uc.mem_write(state + 12, struct.pack("<i", shown))
        sim.uc.mem_write(font + 4, struct.pack("<2i", 20, 13))   # the line step, the top
        calls = []

        def stub(va: int, pop: int, what):
            def hook(uc, addr, size, _):
                esp = sim.reg("esp")
                ret, *args = struct.unpack(f"<{1 + pop // 4}I", uc.mem_read(esp, 4 + pop))
                eax = what(args)
                if eax is not None:
                    uc.reg_write(UC_X86_REG_EAX, eax)
                uc.reg_write(UC_X86_REG_EIP, ret)
                uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
            sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)
        stub(0x1B110, 4, lambda a: calls.append(("list", *a)))
        stub(0xD09E0, 0, lambda a: calls.append(("font",)) or typeface)
        stub(0xD0830, 8, lambda a: calls.append(("anchor", a[0], struct.unpack(
            "<2f", sim.uc.mem_read(a[1], 8)))))
        stub(0x97420, 8, lambda a: calls.append(("material", struct.unpack(
            "<4f", sim.uc.mem_read(sim.reg("esi"), 16)), sim.reg("edi"), *a)) or material)
        stub(0xD0D60, 8, lambda a: calls.append(("text", struct.unpack(
            "<9f", sim.uc.mem_read(sim.reg("esi"), 36)), a[0], sim.cstr(a[1]))))
        kept = {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
        sim.call(entry(hud), regs=kept, args=(hud_at,), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 4
        assert {r: sim.reg(r) for r in kept} == kept
        return calls
    corner, back = ("anchor", 9, (_f32(0.8), _f32(0.8))), ("anchor", 5, (1.0, 1.0))
    yellow = ("material", tuple(_f32(v) for v in (1.0, 0.9, 0.2, 1.0)), font, 0, 1)
    assert drawn() == [("list", hud_at), ("font",), corner, yellow,
                       *(("text", (2.0, -15.0 - 20.0 * k, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0), font, row)
                         for k, row in enumerate(lines[1].split("\n"))), back]
    assert drawn(material=0) == [("list", hud_at), ("font",), corner, yellow, back]
    assert drawn(typeface=0) == [("list", hud_at), ("font",)]
    assert drawn(shown=0) == [("list", hud_at)]
    assert [pressed(white_=0.0, set_=1, logical=2, source=8, move=m)[0][1] for m in (0x100, 0)] == [2, -1]


def test_a_white_set_plays_its_four_slots_round_and_round_and_no_swing_twice_in_a_row():
    """AZ-680 (Step 2.159a's sitting B, row A5): booblord's set 2 (hspin,
    the kit's shove, stomp) padded its fourth with its first, and its
    fourth, chaining at sweep1's early point while its own hit's stun
    held, was keyed on finish3, from which no chain row leads: the first
    row a stunned target matches is row 32's finish2 (no last move), which
    the set maps to its fourth again, so it hand-spun on every press.
    A short set walks back through its picks (a b c b, a b a b; one pick
    all four), so no swing follows itself round the cycle but a set's only
    one; and in X36's search (L2 at 0x88D78's entry, spideyzar's set 2:
    sweep1, sweep2, sweep ledge, elemental1) a chain out of the set's
    fourth still playing that the game's search answers with a finisher
    plays the set's first, keyed basic1 for the next chain, while a fresh
    press it answers with finish2 still plays the fourth, as the game's
    combo plays finish2."""
    columns = ["basic1", "basic2", "basic3", "finish", "finish2", "finish3", "sweep1", "sweep2", "sweep ledge",
               "elemental1", "roll forward"]
    for n, want in ((1, [6, 6, 6, 6]), (2, [6, 7, 6, 7]), (3, [6, 7, 8, 7]), (4, [6, 7, 8, 9])):
        picks = ["a"] * 6 + [f"p{k}" for k in range(n)] + ["a"] * (4 - n) + ["roll"]
        assert attack_sets(columns, picks)[1:] == [want], n
    built = bytes(_swap("spideyzar", sounds="garret4")["default.xbe"])
    search = SETS_HOOKS[0]
    state = trampoline_symbol_va(built, search, SETS_STATE, shim_source=SETS_SHIM.source_path())
    base = 0x20000000
    pc, inp, critter, records = (base + 0x1000 * k for k in range(4))

    def searched(picked: int, *, logical: int = -1, source: int = -1, column: int = -1) -> tuple:
        """The search's key, then PC+0x134 and X36's (logical, source) after the entry, the game's search
        picking ``picked`` in set 2 while the critter plays ``source``'s slot."""
        sim, keys = Sim(built), []
        sim.uc.mem_map(base, 0x4000)
        for at, data in ((pc + 0x20, struct.pack("<I", critter)), (pc + 0x134, struct.pack("<i", column)),
                         (critter + 0x200, struct.pack("<i", 0x52 + source)), (0x38BC60, struct.pack("<I", records)),
                         (0x38BC50, struct.pack("<f", math.pi / 180)),
                         (state, struct.pack("<iiiid", 1, logical, source, 0, -1e300)),
                         *((records + 0x58 * k, struct.pack("<iiif", k, 0x52 + k, k, 0.0) + bytes(0x48))
                           for k in range(24))):
            sim.uc.mem_write(at, data)

        def stub(uc, addr, size, _):   # 0x7EF10: __stdcall(24), keyed on PC+0x134; the game's pick
            esp = sim.reg("esp")
            keys.append(struct.unpack("<i", uc.mem_read(pc + 0x134, 4))[0])
            uc.mem_write(pc + 0x134, struct.pack("<i", picked))
            uc.mem_write(pc + 0xDC, bytes(uc.mem_read(records + 0x58 * picked, 0x58)))
            uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4 + 0x18)
        sim.uc.hook_add(UC_HOOK_CODE, stub, begin=0x7EF10, end=0x7EF10)
        entry = search.va + 5 + struct.unpack_from("<i", built, va_to_file(search.va) + 1)[0]
        sim.call(entry, regs={"esi": inp, "edi": pc}, args=(pc + 0xDC, 0, 0, 1, 1, 0), until=l2._RETURN)
        return keys, sim.u32(pc + 0x134), struct.unpack("<iiiid", sim.uc.mem_read(state, 24))[1:3]
    for finisher in (3, 4, 5):   # out of the fourth (elemental1), row 32's finish2: the set's first, then basic2
        assert searched(4, logical=finisher, source=9, column=9) == ([finisher], 6, (0, 6)), finisher
    assert searched(1, logical=0, source=6, column=6) == ([0], 7, (1, 7))
    assert searched(4) == ([-1], 9, (4, 9))   # a fresh press on a stunned target: the fourth


@pytest.mark.parametrize("region", REGIONS)
def test_balthazars_drain_beam_drains_the_enemy_it_lands_on_never_the_wearer_and_heals_what_it_deals_per_enemy(
        region):
    """D324, D357 (Step 2.135, X37; the owner: "Beam drains enemies",
    "Heals you a little") and D452 (Step 2.153: "let's make it heal 100%.
    also the drain life attack should heal per enemy hit, and give it a
    bigger and wider range"): Balthazar's attack_2 keys m_lifedrainswitch,
    whose stream and norm_2 box hang under 'onPlayer' (inherit mode 7: at
    [[[node+4]+0x44]+0xC0], the player critter, 0x68A49), so worn he
    drained himself and W17 played a copy without the switch, losing the
    beam. X37 in own body:
    (a) the build: balthazar's seven attack_2 columns play attack_2 itself
        (mask 0x224492), beamlord's elemental2 (0x400), every critter (D782); the three hooks
        land (the finder's state the others'), share 1.0, range 16.0, the
        radius X21's; the drain box [45] scaled 12, 12, 2 in both builds'
        fx ([46]'s 2 x 2 x 2 m: 24 x 24 x 4 m, Step 2.153b, AZ-663);
        Skin only keeps W17's copy and no X37, keylord none;
    (b) L2 at 0x7EE3B's entry: the finder's candidate ESI is kept, EDX its
        +0x168, a plain RET;
    (c) L2 at 0x68A49's entry (attack_target_find stubbed): in the drain's
        window ESI is the critter the finder returns at 16 m at any bearing
        (the radius 3.0 again after), once a window while it lives (again
        after 1 s with no evaluation: a new beam, its passed list
        cleared); with no live target (none found, or dead) it picks again
        each evaluation, the passed list kept; no target or no drain
        playing is the game's player; (AZ-653, Step 2.153c) once the
        drain stops its target stays 0.5 s past the last evaluation while
        it lives (0.2 s on: the target; 0.6 s on or dead: the player, the
        window closed), and a node of an instance (EDX) in the held list
        X38 fills is on its target while it lives, drain or none (dead:
        the player), another instance's the game's; (AZ-682, Step 2.153d)
        each target is kept with its vtable and serial (+0xE0's low 24
        bits), and one whose vtable is the delete's 0x19DF08 or whose
        serial changed is gone whatever its HP reads: the window picks
        again, the tail closes, a held entry keeps its instance with no
        target (the player); a new tag byte is the same critter;
    (d) L2 at 0x7A1CA's entry (the hit's vtable +0xB4 stubbed, apply_damage
        real): in the window a norm platform's touch by the player is
        dropped (RET 4, no hit), by the enemy it drains (the window's
        target: AZ-758's test has the others) sent and the player healed by
        what it lost (15 -> 15, at least 1), a plain RET; a common AI
        enemy's (its controller's slot +0x18 0x38C60) first touch in the
        window at a no-hit window of 2.9 s is sent at 0 and listed, its
        window then 2.9 again (a heavy hit's longer one: AZ-765's test); a listed one's, one
        at 5.0 s and a boss's are sent as they are; the knock the hit
        writes at a common AI enemy's controller+0x24 (6.261, 0.5, 3.1305)
        loses its horizontal part, (0, 0, 3.1305) (AZ-672, Step 2.153c),
        where a boss's or a hit taking no HP keeps it; 0.3 s after the window
        (the switch's fade) the player's still dropped, 0.6 s after sent;
        another platform type, level 0, a dead player and no drain are the
        game's;
    (e) (Step 2.161c, the review's P1) only the player's own graph: a node
        of his fx_default's instance (critter+0x230's handle less 0x20) or
        of another instance of its asset (+0x4C: X38's copy) is placed as
        above; another critter's (the airship boss's own, its asset
        another) keeps the game's player in the drain, its target and
        window untouched; a platform whose node (+0x294) is another
        graph's, or which no node made, is the game's: the player's touch
        sent, an enemy's sent with no heal."""
    europe = region == "europe"
    game = _swap("balthazar", sounds="garret4")
    built = bytes(game["default.xbe"])
    find, anchor, touch = DRAIN_HOOKS
    assert [verify_trampoline_patch(built, hook) for hook in DRAIN_HOOKS] == ["applied"] * 3
    state = trampoline_symbol_va(built, find, DRAIN_STATE, shim_source=DRAIN_SHIM.source_path())
    radius = trampoline_symbol_va(built, SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, shim_source=SEARCH_SHIM.source_path())

    def landed(xbe: bytes, hook, symbol: str) -> int:
        return struct.unpack_from("<I", xbe, resolve_va_to_file(xbe, trampoline_symbol_va(
            xbe, hook, symbol, shim_source=DRAIN_SHIM.source_path())))[0]
    assert [landed(built, hook, "_player_model_drain_state_at") for hook in DRAIN_HOOKS] == [0, state, state]
    assert landed(built, touch, "_player_model_drain_radius_at") == radius
    assert [_param(built, find, DRAIN_SHIM, f"_player_model_drain_{k}") for k in ("columns", "share", "range")] == [
        0x224492, 1.0, 16.0]
    if europe:
        return
    assert l1.check(_xbe(), built) == []
    assert _anims(game["config.xbr"])[1] == "attack_2"
    variant = builtins()["beamlord"]
    beam = _swap("beamlord")
    assert [_param(bytes(beam["default.xbe"]), hook, DRAIN_SHIM, f"_player_model_drain_{k}")
            for hook, k in ((find, "columns"), (touch, "every"))] == [0x400, 1.0]   # D782: his drain takes every critter
    assert DRAIN_BOX in overlay("balthazar").fx and DRAIN_BOX in variant.fx   # their fx edits pinned by test_player_variants
    assert DRAIN_BOX["set"] == {"scaleX": 12.0, "scaleY": 12.0, "scaleZ": 2.0}   # [46]'s 2 x 2 x 2 m: 24 x 24 x 4
    for species, kw in (("balthazar", {"mode": "garret4"}), ("keylord", {})):
        xbe = bytes(_swap(species, sounds="garret4", **kw)["default.xbe"])
        assert [verify_trampoline_patch(xbe, hook) for hook in DRAIN_HOOKS] == ["original"] * 3, species
    base = 0x20000000
    world, player, pc, clock, enemy, platform, vtable, control = (base + 0x1000 * k for k in range(8))
    hit_stub, ai_vtable = base + 0x9000, base + 0x9100
    own, boss_fx, ring_copy, node = base + 0x9400, base + 0x9600, base + 0x9700, base + 0x9A00   # P1's
    serial = 0x03012345   # the enemy's +0xE0: its serial 0x012345 under a tag byte
    ids = {0: (0, 0, 0), enemy: (enemy, vtable, serial & 0xFFFFFF), player: (player, vtable, 0)}   # X37's identity

    def entry(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]

    def sim_at(*, column: int = 1, slot: int = 0x53, flags: int = 8, now: float = 10.0, seen: float = -1e300,
               active: int = 0, target: int = 0, player_hp: int = 150, enemy_hp: int = 100, window: float = 0.0,
               handler: int = 0x38C60, passed: tuple = (), held: tuple = (), made_by: int = 0) -> Sim:
        sim = Sim(built)
        sim.uc.mem_map(base, 0xA000)
        for at, data in ((world + 0xC0, struct.pack("<I", player)), (player + 0x180, struct.pack("<I", pc)),
                         (player + 0x200, struct.pack("<i", slot)), (player + 0x210, struct.pack("<ii", player_hp, 200)),
                         (pc + 0xC, struct.pack("<I", clock)), (pc + 0x134, struct.pack("<if", column, 0.3)),
                         (pc + 0x16C, bytes([flags])), (clock + 0x10, struct.pack("<d", now)),
                         (enemy, struct.pack("<I", vtable)), (enemy + 0x168, struct.pack("<I", 0x40)),
                         (enemy + 0xE0, struct.pack("<I", serial)),
                         (enemy + 0x210, struct.pack("<ii", enemy_hp, 100)), (player, struct.pack("<I", vtable)),
                         (vtable + 0xB4, struct.pack("<I", hit_stub)), (platform + 0x154, struct.pack("<I", world)),
                         (enemy + 0x180, struct.pack("<I", control)), (enemy + 0x1E0, struct.pack("<f", window)),
                         (control, struct.pack("<I", ai_vtable)), (ai_vtable + 0x18, struct.pack("<I", handler)),
                         (state, struct.pack("<I3Iiid8I64I", 0, *ids[target], active, len(passed), seen,
                                             *passed, *(0,) * (8 - len(passed)),
                                             *(v for copy, who in held for v in (copy, *ids[who])),
                                             *(0,) * (64 - 4 * len(held)))),
                         (radius, struct.pack("<f", 3.0)), (player + 0x230, struct.pack("<I", own + 0x20)),
                         (own + 0x4C, struct.pack("<i", 7)), (ring_copy + 0x4C, struct.pack("<i", 7)),
                         (boss_fx + 0x4C, struct.pack("<i", 9)), (platform + 0x294, struct.pack("<I", node)),
                         (node + 4, struct.pack("<I", made_by))):
            sim.uc.mem_write(at, data)
        return sim
    # (b) the finder's candidate
    sim = sim_at()
    sim.uc.mem_write(enemy + 0x168, struct.pack("<I", 0x4040))
    kept = {"ebx": 0x11, "esi": enemy, "edi": 0x33, "ebp": 0x44}
    sim.call(entry(find), regs=kept, until=l2._RETURN)
    assert (sim.reg("esp"), sim.u32(state), sim.reg("edx"), {r: sim.reg(r) for r in kept}) == (
        l2._STACK_TOP - 0x100, enemy, 0x4040, kept)

    # (c) the anchor
    def anchored(*, off: float = 0.4, count: int = 1, instance: int = own, gone: dict | None = None, **kw) -> tuple:
        sim, seen = sim_at(**kw), []
        for at, word in (gone or {}).items():   # AZ-682: the game deleted the enemy, or gave its block again
            sim.uc.mem_write(enemy + at, struct.pack("<I", word))

        def finder(uc, addr, size, _):   # attack_target_find: __stdcall(12); F would keep its candidate
            esp = sim.reg("esp")
            ret, who, facing, out = struct.unpack("<IIfI", uc.mem_read(esp, 16))
            seen.append((who, round(facing, 6), sim.f32(radius)))
            uc.mem_write(out, struct.pack("<I", count) + bytes(16) + struct.pack("<f", off) + bytes(0x20))
            uc.mem_write(state, struct.pack("<I", enemy if count else 0))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 16)
        sim.uc.hook_add(UC_HOOK_CODE, finder, begin=0x7EBB0, end=0x7EBB0)
        kept = {"ebx": 0x11, "edi": 0x33, "ebp": 0x44}
        sim.call(entry(anchor), regs={**kept, "eax": world, "edx": instance}, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and {r: sim.reg(r) for r in kept} == kept
        got = struct.unpack("<I3Iiid", sim.uc.mem_read(state, 32))
        return sim.reg("esi"), seen, sim.f32(radius), (got[1], got[4]), got[6], got[5], got[1:4], \
            struct.unpack("<4I", sim.uc.mem_read(state + 64, 16))
    esi, seen, after, (target, active), stamped, _, ident, _ = anchored(off=2.6)       # any bearing
    assert (esi, seen, after, target, active, stamped) == (enemy, [(player, 0.3, 16.0)], 3.0, enemy, 1, 10.0)
    assert ident == ids[enemy]                                                         # kept with its identity
    assert anchored(active=1, target=enemy, seen=9.97)[:2] == (enemy, [])            # once a window
    got = anchored(active=1, target=0, seen=9.0, passed=(enemy,))                       # a new beam, no reset between
    assert (got[1], got[5]) == ([(player, 0.3, 16.0)], 0)
    for kw in ({"target": 0}, {"target": enemy, "enemy_hp": 0}):   # no live target: picked again, the list kept
        got = anchored(active=1, seen=9.97, count=0, passed=(enemy,), **kw)
        assert (got[0], got[1], got[5]) == (player, [(player, 0.3, 16.0)], 1), kw
    for kw in ({"count": 0}, {"column": 0}, {"slot": 1}, {"flags": 0}):
        esi, seen, *_ = anchored(**kw)
        assert esi == player, kw
    # AZ-653 (Step 2.153c): the drain stopped, its target kept for 0.5 s past its last evaluation while it lives
    got = anchored(column=0, active=1, target=enemy, seen=9.8)
    assert (got[0], got[1], got[3], got[4]) == (enemy, [], (enemy, 1), 9.8)
    for kw in ({"seen": 9.4}, {"enemy_hp": 0}):
        got = anchored(column=0, active=1, target=enemy, **{"seen": 9.8} | kw)
        assert (got[0], got[1], got[3]) == (player, [], (0, 0)), kw
    copy = base + 0x9800   # X38's detached drain copy: on its held target while it lives, whatever else plays
    for kw, want in (({}, enemy), ({"column": 0}, enemy), ({"enemy_hp": 0}, player)):
        got = anchored(instance=copy, held=((0x1234, player), (copy, enemy)), **kw)
        assert (got[0], got[1]) == (want, []), kw
    assert anchored(instance=copy + 4, held=((copy, enemy),), column=0)[0] == player   # another instance: the game's
    # AZ-682 (Step 2.153d): a kept critter whose vtable or serial changed is gone, its HP never read: the game's
    # delete writes the base vtable 0x19DF08 (its HP still reads 100), a block given again holds another serial;
    # a new tag byte over the serial is the same critter
    deleted, reused, tagged = {0: 0x19DF08}, {0xE0: serial + 1}, {0xE0: serial & 0xFFFFFF | 0x05000000}
    for gone in (deleted, reused):
        got = anchored(active=1, target=enemy, seen=9.97, count=0, gone=gone)       # in the window: picked again
        assert (got[0], got[1], got[3]) == (player, [(player, 0.3, 16.0)], (0, 1)), gone
        got = anchored(column=0, active=1, target=enemy, seen=9.8, gone=gone)       # in the tail: closed
        assert (got[0], got[1], got[3]) == (player, [], (0, 0)), gone
        got = anchored(instance=copy, held=((copy, enemy),), gone=gone)             # a held copy's: X38 closes it
        assert (got[0], got[7]) == (player, (copy, 0, 0, 0)), gone
    assert anchored(active=1, target=enemy, seen=9.97, gone=tagged)[:2] == (enemy, [])
    # (e) P1 (Step 2.161c): X38's copy of his graph is his; the airship boss's own graph keeps the game's player
    assert anchored(instance=ring_copy)[:2] == (enemy, [(player, 0.3, 16.0)])
    got = anchored(instance=boss_fx, active=1, target=enemy, seen=9.97)
    assert (got[0], got[1], got[3], got[4]) == (player, [], (enemy, 1), 9.97)
    got = anchored(instance=boss_fx)
    assert (got[0], got[1], got[3]) == (player, [], (0, 0))

    # (d) the touch
    def touched(toucher: int, *, kind: bytes = b"norm", level: int = 2, dealt: int = 15, gives: float | None = None,
                made_by: int = own, **kw) -> tuple:
        sim, hits = sim_at(made_by=made_by or 0, **{"target": enemy} | kw), []   # the enemy the window drains
        sim.uc.mem_write(platform + 0x27E, bytes([level]) + b"\0" + kind)
        if made_by is None:   # no node made it
            sim.uc.mem_write(platform + 0x294, struct.pack("<I", 0))

        def hit(uc, addr, size, _):   # the toucher's slot: thiscall, RET 4; it deals and gives its window
            esp = sim.reg("esp")
            ret, message = struct.unpack("<2I", uc.mem_read(esp, 8))
            hits.append((sim.reg("ecx"), message))
            if sim.reg("ecx") == enemy:
                windows.append(sim.f32(enemy + 0x1E0))
                if gives is not None:
                    uc.mem_write(enemy + 0x1E0, struct.pack("<f", gives))
                uc.mem_write(control + 0x24, struct.pack("<3f", *KNOCK))   # 0x30BD0's knock, inside the send
            hp = struct.unpack("<i", uc.mem_read(sim.reg("ecx") + 0x210, 4))[0]
            uc.mem_write(sim.reg("ecx") + 0x210, struct.pack("<i", hp - dealt))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 8)
        windows = []

        def play(uc, addr, size, _):   # critter_play_fx (AZ-759's stream, its own test's): RET 4
            esp = sim.reg("esp")
            uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, esp + 8)
        sim.uc.hook_add(UC_HOOK_CODE, hit, begin=hit_stub, end=hit_stub)
        sim.uc.hook_add(UC_HOOK_CODE, play, begin=0x440F0, end=0x440F0)
        kept = {"ebx": 0x11, "esi": 0x22, "edi": vtable, "ebp": platform}
        sim.call(entry(touch), regs={**kept, "eax": 0x5150, "ecx": toucher}, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and {r: sim.reg(r) for r in kept} == kept   # a plain RET
        listed = struct.unpack("<8I", sim.uc.mem_read(state + 32, 32))[:struct.unpack(
            "<i", sim.uc.mem_read(state + 20, 4))[0]]
        return hits, struct.unpack("<i", sim.uc.mem_read(player + 0x210, 4))[0], \
            struct.unpack("<i", sim.uc.mem_read(enemy + 0x210, 4))[0], windows, sim.f32(enemy + 0x1E0), list(listed), \
            struct.unpack("<3f", sim.uc.mem_read(control + 0x24, 12))
    KNOCK = (6.261, 0.5, 3.1305)
    assert touched(player)[:3] == ([], 150, 100)                                   # never the wearer
    assert touched(enemy)[:3] == ([(enemy, 0x5150)], 165, 85)                      # 15 dealt, 15 back
    assert touched(enemy, dealt=2)[:3] == ([(enemy, 0x5150)], 152, 98)             # 2 back
    assert touched(enemy, dealt=0)[1] == 150
    # the first touch passes a common AI critter's no-hit window, once a window
    assert touched(enemy, window=2.9, gives=2.6)[1:6] == (165, 85, [0.0], _f32(2.9), [enemy])
    for kw, w in (({"passed": (enemy,)}, 2.9), ({"window": 5.0}, 5.0), ({"handler": 0x279B0}, 2.9)):   # the game's
        assert touched(enemy, **({"window": 2.9} | kw))[3:5] == ([_f32(w)], _f32(w)), kw
    # AZ-672: a common AI enemy the drain took HP from hops where it stands; a boss, or no HP taken, the game's
    assert touched(enemy)[6] == pytest.approx((0.0, 0.0, KNOCK[2]))
    for kw in ({"handler": 0x279B0}, {"dealt": 0}):
        assert touched(enemy, **kw)[6] == pytest.approx(KNOCK), kw
    assert touched(player, column=0, seen=9.7)[:3] == ([], 150, 100)               # the switch's fade
    assert touched(player, column=0, seen=9.4)[0] == [(player, 0x5150)]           # past it
    for kw in ({"kind": b"fire"}, {"level": 0}, {"column": 0}):
        hits, hp, *_ = touched(enemy, **kw)
        assert (hits, hp) == ([(enemy, 0x5150)], 150), kw
    assert touched(enemy, player_hp=0)[1] == 0                                     # no heal from the dead
    # (e) P1: X38's copy's box is his; the airship boss's box and a platform no node made are the game's
    assert touched(player, made_by=ring_copy)[:3] == ([], 150, 100)
    for made_by in (boss_fx, None):
        assert touched(player, made_by=made_by)[:2] == ([(player, 0x5150)], 135), made_by
        assert touched(enemy, made_by=made_by)[:3] == ([(enemy, 0x5150)], 150, 85), made_by


def _drain_touch(built: bytes, toucher: str, *, target: str | None = "enemy", every: bool = False, gone: bool = False,
                 dealt: int = 15, hp: int = 100, gives: float | None = None, times: tuple = (10.0,),
                 window: float = 0.0) -> tuple:
    """X37's touch (0x7A1CA's entry) under L2 on ``built`` (plain Balthazar's
    build: column 1 drains) in a drain whose window holds ``target``: the
    ``toucher`` ("player", or "enemy" or "other", two common AI critters of
    ``hp`` HP) touches a norm_2 platform of the player's own graph, its hit
    slot (vtable +0xB4) dealing ``dealt`` while its no-hit window (+0x1E0)
    is 0 (0x4323C), then setting the window and +0x1E4 to ``gives`` (a heavy
    reaction's, 0x38EED), else to the hit record's Delay 0.33 (0x43591),
    with drain_every ``every``; ``gone``: the game deleted the target (its
    vtable 0x19DF08, AZ-682); one touch at each clock time of ``times`` in one
    sim, the toucher's window ``window`` at the first (+0x1E0 and +0x1E4),
    running down between.  critter_play_fx (0x440F0) is
    stubbed (it links the critter's +0x23C handle, its flags 1, as the
    game's does).  Returns (the critters hit, the player's, enemy's and
    other's HP, each (critter, key, the handle's flags after the touch) it
    played, the toucher's (+0x1E0, +0x1E4) after each touch)."""
    find, _, touch = DRAIN_HOOKS
    state = trampoline_symbol_va(built, find, DRAIN_STATE, shim_source=DRAIN_SHIM.source_path())
    flag = trampoline_symbol_va(built, touch, "_player_model_drain_every", shim_source=DRAIN_SHIM.source_path())
    base = 0x20000000
    world, player, pc, clock, enemy, other, platform, vtable, control = (base + 0x1000 * k for k in range(9))
    hit_stub, ai_vtable, own, node = base + 0x9000, base + 0x9100, base + 0x9400, base + 0x9A00
    message, record = base + 0x9900, base + 0x9940   # the platform's hit (0x255C0: +8 its record) and norm_2's record
    who = {"player": player, "enemy": enemy, "other": other}
    name = {v: k for k, v in who.items()}
    ident = {"enemy": (enemy, vtable, 0x12345), None: (0, 0, 0)}
    sim, hits, plays = Sim(built), [], []
    sim.uc.mem_map(base, 0xA000)
    for at, data in ((world + 0xC0, struct.pack("<I", player)), (player + 0x180, struct.pack("<I", pc)),
                     (player + 0x200, struct.pack("<i", 0x53)), (player + 0x210, struct.pack("<ii", 150, 200)),
                     (player + 0x230, struct.pack("<I", own + 0x20)), (own + 0x4C, struct.pack("<i", 7)),
                     (pc + 0xC, struct.pack("<I", clock)), (pc + 0x134, struct.pack("<if", 1, 0.3)),
                     (pc + 0x16C, bytes([8])), (clock + 0x10, struct.pack("<d", 10.0)),
                     (platform + 0x154, struct.pack("<I", world)), (platform + 0x27E, b"\x02\0norm"),
                     (platform + 0x294, struct.pack("<I", node)), (node + 4, struct.pack("<I", own)),
                     (vtable + 0xB4, struct.pack("<I", hit_stub)), (control, struct.pack("<I", ai_vtable)),
                     (ai_vtable + 0x18, struct.pack("<I", 0x38C60)), (flag, struct.pack("<f", float(every))),
                     (message, struct.pack("<3If", 3, platform, record, 1.0)), (record + 0x10, struct.pack("<f", 0.33)),
                     (state, struct.pack("<I3Iiid", 0, *ident[target], 1, 0, 9.97))):
        sim.uc.mem_write(at, data)
    for critter in (enemy, other):
        for at, data in ((0, struct.pack("<I", vtable)), (0xE0, struct.pack("<I", 0x12345)),
                         (0x168, struct.pack("<I", 0x40)), (0x180, struct.pack("<I", control)),
                         (0x210, struct.pack("<ii", hp, 100))):
            sim.uc.mem_write(critter + at, data)
    sim.uc.mem_write(who[toucher] + 0x1E0, struct.pack("<ff", window, window))
    if gone:   # AZ-682: the game deleted the target (the base vtable 0x19DF08), its HP still reading as it was
        sim.uc.mem_write(enemy, struct.pack("<I", 0x19DF08))

    def hit(uc, addr, size, _):   # the toucher's slot: thiscall, RET 4; it deals ``dealt`` outside its window
        esp, ecx = sim.reg("esp"), sim.reg("ecx")
        hits.append(name[ecx])
        if sim.f32(ecx + 0x1E0) <= 0:
            uc.mem_write(ecx + 0x210, struct.pack("<i", struct.unpack("<i", uc.mem_read(ecx + 0x210, 4))[0] - dealt))
            uc.mem_write(ecx + 0x1E0, struct.pack("<ff", *(2 * (0.33 if gives is None else gives,))))
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 8)

    def play(uc, addr, size, _):   # critter_play_fx: thiscall (ECX the critter, the key), RET 4
        esp = sim.reg("esp")
        ret, key = struct.unpack("<2I", uc.mem_read(esp, 8))
        plays.append((sim.reg("ecx"), bytes(uc.mem_read(key, 64)).split(b"\0")[0].decode()))
        uc.mem_write(sim.reg("ecx") + 0x23C, struct.pack("<3I", base + 0x9820, 0, 1))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 8)
    sim.uc.hook_add(UC_HOOK_CODE, hit, begin=hit_stub, end=hit_stub)
    sim.uc.hook_add(UC_HOOK_CODE, play, begin=0x440F0, end=0x440F0)
    kept = {"ebx": 0x11, "esi": 0x22, "edi": vtable, "ebp": platform}
    windows, now = [], times[0]
    for t in times:   # the damage pass runs the window down meanwhile
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", t))
        sim.uc.mem_write(who[toucher] + 0x1E0, struct.pack("<f", max(0.0, sim.f32(who[toucher] + 0x1E0) - (t - now))))
        now = t
        sim.call(touch.va + 5 + struct.unpack_from("<i", built, va_to_file(touch.va) + 1)[0],
                 regs={**kept, "eax": message, "ecx": who[toucher]}, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and {r: sim.reg(r) for r in kept} == kept   # a plain RET
        windows.append(tuple(round(sim.f32(who[toucher] + o), 4) for o in (0x1E0, 0x1E4)))
    return hits, *(struct.unpack("<i", sim.uc.mem_read(c + 0x210, 4))[0] for c in (player, enemy, other)), [
        (name.get(c, c), key, struct.unpack("<I", sim.uc.mem_read(c + 0x244, 4))[0]) for c, key in plays], windows


def test_the_drain_takes_life_from_its_target_alone_unless_a_recipe_or_style_takes_every_critter_it_touches():
    """AZ-758 (Step 2.196, D765, the owner: "also the drain attack is
    currently draining all enemies life within radius, not just the
    nearest. can you make it just drain the nearest? Although having multi
    enemy target attacks like this is cool, for future weapons"): X37's
    drain box ([45], 24 x 24 x 4 m round its pick) sent every critter's
    touch, so each enemy within 12 m of the target lost norm_2's 15 and
    healed the wearer. Now:
    (a) a recipe's or weapon style's ``drain`` {"targets": "nearest" | "all"}
        ("nearest" by default; a style's left out hashes nothing, so every
        weapon keeps its sha) sets X37's float param drain_every: 0.0 on
        plain Balthazar's build, 1.0 on beamlord's (D782, the owner:
        "beamlord keeps the area drain, balthazar drains one target": his
        recipe asks "all", every other built-in none, the X37 test reading
        his build's); another value or key fails by name;
    (b) L2 at 0x7A1CA's entry (the hit's vtable +0xB4 stubbed, apply_damage
        real), in the drain: the target's touch is sent and heals 15;
        another enemy's is dropped (no hit, no HP lost, no heal), and with
        no live target (none, or one the game deleted: AZ-682's identity)
        every enemy's; at drain_every 1.0 the other enemy's is sent and
        heals 15, as before."""
    from azurkit.tools.characters._player_weapons import WEAPONS_FILE, load_weapons

    built = bytes(_swap("balthazar", sounds="garret4")["default.xbe"])
    touch = DRAIN_HOOKS[2]
    assert _param(built, touch, DRAIN_SHIM, "_player_model_drain_every") == 0.0
    assert {n: v.drain for n, v in builtins().items()} == {n: "all" if n == "beamlord" else "nearest" for n in builtins()}
    for bad, why in (({"targets": "few"}, "drain.targets: 'few' is not one of nearest, all"),
                     ({"target": "all"}, "drain: unknown key 'target'")):
        with pytest.raises(ValueError, match=re.escape(why)):
            load_variants(json.dumps({"drainall": {"base": "balthazar", "drain": bad}}), "test")
    doc = json.loads(WEAPONS_FILE.read_text(encoding="utf-8"))
    assert {n: w.style.drain for n, w in weapons().items()} == {n: None for n in doc["weapons"]}
    doc["styles"]["balthazar"]["drain"] = {"targets": "all"}
    assert load_weapons(json.dumps(doc))["balthazar_magic"].style.drain == "all"

    assert _drain_touch(built, "enemy")[:4] == (["enemy"], 165, 85, 100)      # the target: drained, 15 back
    assert _drain_touch(built, "other")[:4] == ([], 150, 100, 100)            # another enemy in the box: untouched
    for kw in ({"target": None}, {"gone": True}):                              # no live target: none drained
        assert _drain_touch(built, "other", **kw)[:4] == ([], 150, 100, 100), kw
    assert _drain_touch(built, "other", every=True)[:4] == (["other"], 165, 100, 85)   # drain.targets all


def test_a_drain_hit_leaves_its_target_open_to_the_next_swing_and_drains_it_once_a_heavy_reaction():
    """AZ-765 (Step 2.197, D789, the owner: "Fix now"): X37's drain hit is
    the platform's, not the player's, so X18 never makes it light, and
    norm_2's 15 HP over a blaze sentinel's threshold 5 is a level-2 hit,
    whose reaction gives the target a no-hit window of 0.25 s plus its
    ouch clip (0x38EED: 2.58 s), which 0x4356E keeps: in plain play it
    voided the wearer's beam and finish3 after the drain (Step 2.195b's
    record, R4; main too).  L2 at 0x7A1CA's entry, the target's hit slot
    stubbed (it deals 15 while its window is 0, then gives its window):
    a heavy reaction's window (2.5833) is left as a light hit's, the hit
    record's Delay 0.33 in +0x1E0 and +0x1E4, and the drain's own touches
    on it are dropped until the heavy window would have ended (0.5 and
    2.0 s on: no hit), then sent (2.6 s on: 15 more, 15 more heal); over a
    longer window the touch passed (2.0 s) it leaves that one, held off the
    same; a light reaction's window (the record's Delay) is the game's, the
    drain held off nothing (its touch 0.5 s on sent)."""
    built = bytes(_swap("balthazar", sounds="garret4")["default.xbe"])
    hits, player, enemy, _, _, windows = _drain_touch(built, "enemy", gives=2.5833, times=(10.0, 10.5, 12.0, 12.6))
    assert (hits, player, enemy) == (["enemy", "enemy"], 180, 70)
    assert windows == [(0.33, 0.33), (0.0, 0.33), (0.0, 0.33), (0.33, 0.33)]
    hits, player, enemy, _, _, windows = _drain_touch(built, "enemy", window=2.0, gives=2.5833, times=(10.0, 10.5, 12.6))
    assert (hits, player, enemy, windows) == (["enemy", "enemy"], 180, 70, [(2.0, 2.0), (1.5, 2.0), (0.33, 0.33)])
    hits, player, enemy, _, _, windows = _drain_touch(built, "enemy", times=(10.0, 10.5))
    assert (hits, player, enemy, windows) == (["enemy", "enemy"], 180, 70, [(0.33, 0.33), (0.33, 0.33)])


def test_balthazars_beam_bolts_reach_its_target_and_past_his_blasts_reach_his_combo_ends_on_the_beam():
    """AZ-769 and D797 (Step 2.197b; D767: magic is the ranged style): his
    beam drew its bolts at three fixed points 6 and 15 units ahead under
    the floor, never at what it hit, and past 3 m his combo ended on the
    short blast, which misses there.
    (a) his build: the three bolt targets (locator1-3, records 58, 60, 62)
        inherit mode 7 on the player's clone; X37 holds them, the beam's
        columns (attack_3's: basic3 and finish3 among them), the beam's
        reach (its box's far face) and his chest; W40 makes the transition
        search's long-range line his blast's reach (0.6; D797's 3.0 m
        until Step 2.202, D804 (b): his blast stops reaching at 1.26 m, so
        from there to 3 m the finisher whiffed): the finish column's box's
        far face ahead of his feet, x X13's bump there, and its basic3 ->
        finish3 row long range, so the blast plays where it reaches and
        the beam past it; keylord's own build keeps both;
    (b) X37's anchor at 0x68A49 under L2, EBX a bolt target's node: in
        the beam, on the critter the finder gives along the swing's yaw
        within the reach (the radius at the reach for the call) where it
        stands in the beam's box (ahead within the reach, within the
        box's half-width of the yaw, its radius added; the review's F2: a
        45 degree cone took one 2 m to the side, which the box misses),
        its translate (side, 0, its chest: 0.7 of its bounds' height over
        glide_origin's point); none found, one off the box, or no beam, on
        the player straight ahead to the reach at his chest; the drain's
        last pick before the finder's where it stands in the box; a kept
        target knocked out of the box picked again (AZ-805, Step 2.202b:
        the late review's P2, firedrake's bolts followed one knocked 5 m
        past its 2.83 m box); the
        anchor the one the node's matrix this pass holds (its local y past
        0.5 m: straight ahead's, the player; else the target its last
        translate was written for while it is that object, dead or alive:
        the review's P1, a target knocked off the box put its offset on the
        player for a tick, and the late review's F1, so did one the beam
        killed with another critter in the box), the translate for the
        next."""
    game = _swap("balthazar", sounds="garret4")
    built = bytes(game["default.xbe"])
    find, anchor, _ = DRAIN_HOOKS
    assert aim_records(overlay("balthazar").fx) == (58, 60, 62)
    aim_at = resolve_va_to_file(built, trampoline_symbol_va(built, anchor, "_player_model_drain_aim",
                                                            shim_source=DRAIN_SHIM.source_path()))
    assert built[aim_at:aim_at + 4] == bytes([3, 58, 60, 62])
    beams = round(_param(built, anchor, DRAIN_SHIM, "_player_model_drain_beams"))
    columns = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims").col_names()
    assert {"basic3", "finish3"} <= {c for i, c in enumerate(columns) if beams >> i & 1} and not beams & 0b11
    reach, chest, half = (_param(built, anchor, DRAIN_SHIM, f"_player_model_drain_aim_{k}")
                          for k in ("reach", "chest", "half"))
    assert 6.0 < reach < 8.0 and 1.0 < chest < 3.0 and 0.4 < half < 0.6
    bodies, config0 = (_read(f"gamedata/{n}.xbr") for n in ("characters", "config"))
    finish = columns.index("finish")
    bump = round(_param(built, ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, "_player_attack_bump_mask")) >> finish & 1
    blast = max(w.forward for w in next(a for a in attacks(config0, bodies, "balthazar")
                                        if a.column == "finish").windows) * (REACH_BUMP if bump else 1.0)
    for xbe, config, line in ((built, game["config.xbr"], blast),
                              (*(lambda g: (bytes(g["default.xbe"]), g["config.xbr"]))(_swap("keylord")), None)):
        off = patch_spec_site(bytearray(xbe), FINISH_RANGE)[0]
        row = XbrDocument.from_bytes(bytes(config)).keyed_section("attacks_transitions")
        assert (struct.unpack_from("<f", xbe, off)[0], row.find_cell(row.col_names()[FINISH_ROW], "long range",
                                                                    FINISH_ROW).double_value) == (
            (_f32(line), 1.0) if line else (_f32(0.6), 0.0))
    assert 1.2 < blast < 1.7   # his blast's 1.26 m, x1.25 where W14 bumps the column
    state = trampoline_symbol_va(built, find, DRAIN_STATE, shim_source=DRAIN_SHIM.source_path())
    radius = trampoline_symbol_va(built, SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, shim_source=SEARCH_SHIM.source_path())
    base = 0x20000000
    world, player, pc, clock, enemy, other, vtable, own, recs, node, onplayer = (
        base + 0x1000 * k for k in range(11))
    beam = next(i for i in range(len(columns)) if beams >> i & 1)

    def sim_at(side: float = 1.2) -> Sim:
        sim = Sim(built)
        sim.uc.mem_map(base, 0xC000)
        for at, data in ((world + 0xC0, struct.pack("<I", player)), (player + 0x180, struct.pack("<I", pc)),
                         (player + 0x210, struct.pack("<i", 150)), (pc + 0xC, struct.pack("<I", clock)),
                         (pc + 0x138, struct.pack("<f", 0.0)), (pc + 0x16C, bytes([8])),
                         (player + 0x230, struct.pack("<I", own + 0x20)), (own + 0x4C, struct.pack("<i", 7)),
                         (own + 0x24, struct.pack("<2I", recs, recs + 64 * 4)), (recs + 58 * 4, struct.pack("<I", node)),
                         (node + 8, struct.pack("<I", node + 0x100)), (radius, struct.pack("<f", 3.0)),
                         *((c, struct.pack("<I", vtable)) for c in (enemy, other)),
                         *((c + 0x210, struct.pack("<i", 100)) for c in (enemy, other)),
                         *((c + 0x90, struct.pack("<f", 1.0)) for c in (enemy, other)),
                         (enemy + 0x15C, struct.pack("<3f", 0.0, 3.0, 0.0)), (other + 0x15C, struct.pack("<3f", side, 4.0, 0.0)),
                         (enemy + 0xF8, struct.pack("<6f", -1.0, 2.0, 0.0, 1.0, 4.0, 2.0)),
                         (other + 0xF8, struct.pack("<6f", 1.0, 3.0, 0.5, 3.0, 5.0, 1.5))):
            sim.uc.mem_write(at, data)
        return sim

    def anchored(sim: Sim, *, column: int, now: float, finds: int, count: int = 1, at: int = node) -> tuple:
        seen = []
        sim.uc.mem_write(pc + 0x134, struct.pack("<i", column))
        sim.uc.mem_write(player + 0x200, struct.pack("<i", 0x52 + column))
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", now))

        def finder(uc, addr, size, _):   # attack_target_find, __stdcall(12): its candidate into X37's state
            esp = sim.reg("esp")
            ret, _who, _facing, out = struct.unpack("<IIfI", uc.mem_read(esp, 16))
            seen.append(round(sim.f32(radius), 4))
            uc.mem_write(out, struct.pack("<I", count) + bytes(16) + struct.pack("<f", 0.4) + bytes(0x20))
            uc.mem_write(state, struct.pack("<I", finds if count else 0))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 16)

        def origin(uc, addr, size, _):   # glide_origin, __stdcall(8): the critter's centre, its feet's z
            esp = sim.reg("esp")
            ret, who, out = struct.unpack("<3I", uc.mem_read(esp, 12))
            uc.mem_write(out, struct.pack("<3f", *struct.unpack("<2f", uc.mem_read(who + 0x15C, 8)), 0.0))
            uc.reg_write(UC_X86_REG_EAX, out)
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 12)
        hooks = [sim.uc.hook_add(UC_HOOK_CODE, finder, begin=0x7EBB0, end=0x7EBB0),
                 sim.uc.hook_add(UC_HOOK_CODE, origin, begin=0x42070, end=0x42070)]
        sim.call(anchor.va + 5 + struct.unpack_from("<i", built, va_to_file(anchor.va) + 1)[0],
                 regs={"eax": world, "edx": own, "ebx": at}, until=l2._RETURN)
        for h in hooks:
            sim.uc.hook_del(h)
        return sim.reg("esi"), [round(v, 4) for v in struct.unpack("<3f", sim.uc.mem_read(node + 0x104, 12))], seen
    ahead = [-0.4, round(_f32(0.8 * reach), 4), round(chest, 4)]
    sim = sim_at()   # in the beam: on the critter the finder gives along his yaw, the side bolt at its chest
    assert anchored(sim, column=beam, now=10.0, finds=other) == (player, [-0.15, 0.0, 1.2], [round(reach, 4)])
    assert anchored(sim, column=beam, now=10.1, finds=other) == (other, [-0.15, 0.0, 1.2], [])   # 0.5 + 0.7 x 1.0
    sim.uc.mem_write(other + 0x210, struct.pack("<i", 0))   # killed, the enemy in the box: on its body a tick more (F1)
    assert anchored(sim, column=beam, now=10.2, finds=enemy) == (other, [-0.15, 0.0, 1.4], [round(reach, 4)])
    assert anchored(sim, column=beam, now=10.3, finds=enemy) == (enemy, [-0.15, 0.0, 1.4], [])
    assert anchored(sim_at(), column=beam, now=10.0, finds=other, count=0) == (player, ahead, [round(reach, 4)])
    assert anchored(sim_at(2.0), column=beam, now=10.0, finds=other) == (player, ahead, [round(reach, 4)])   # off the box
    assert anchored(sim_at(), column=0, now=10.0, finds=other) == (player, ahead, [])   # basic1: no beam
    sim = sim_at()   # the drain's pick (basic2, onPlayer's evaluation), then the beam: on the drain's pick
    assert anchored(sim, column=1, now=10.0, finds=enemy, at=onplayer)[0] == enemy
    assert anchored(sim, column=beam, now=11.0, finds=other) == (player, [-0.15, 0.0, 1.4], [])
    sim = sim_at()   # a kept target knocked off the box: picked again, none in it, so straight ahead (AZ-805),
    anchored(sim, column=beam, now=10.0, finds=other)   # the bolts on it while the matrix holds its translate (P1)
    sim.uc.mem_write(other + 0x15C, struct.pack("<3f", 2.0, 4.0, 0.0))
    assert anchored(sim, column=beam, now=10.1, finds=other) == (other, ahead, [round(reach, 4)])
    sim.uc.mem_write(node + 0xA4, struct.pack("<f", 5.0))
    assert anchored(sim, column=beam, now=10.2, finds=other) == (player, ahead, [round(reach, 4)])
    sim = sim_at()   # the matrix this pass built still straight ahead's (its local y): on the player a tick more
    sim.uc.mem_write(node + 0xA4, struct.pack("<f", 5.0))
    assert anchored(sim, column=beam, now=10.0, finds=other) == (player, [-0.15, 0.0, 1.2], [round(reach, 4)])



def test_the_magic_finishers_line_is_met_on_the_level_so_the_blast_plays_where_it_reaches_its_target():
    """AZ-803 (Step 2.202b, D829, the owner: "Blast where it hits, beam
    beyond"): W40's line is the blast box's far face, but the transition
    search compared it with its finder's distance less radius between the
    bounds centres, which counts their height: f6's blaze sentinel's
    centre stands 1.0 m over the player's, so it was called long range
    0.15-0.3 m inside the blast's reach and the beam's 28-30 HP replaced
    the blast's 84-97 there (Step 2.202's record). The blast hits wherever
    its face reaches the target's side on the level (Step 2.202b's
    sitting, its line poked past every gap: town_male_6 1.275 m hit and
    1.375 missed against its 1.302 face, Balthazar 1.50 / 1.60 against
    1.574, Balthazar x0.7 1.05 / 1.15 against 1.102, keylord missed at
    1.00 against 0.995). X50 at 0x7F0B2 (L2, Balthazar's own build, run
    to 0x7F0CF): it stores ESI as the game's mov did and the compare
    meets the finder's distance less radius on the level (less its
    vector's height share), so a target 1.0 m higher 0.05 m inside the
    face plays the blast (long range 0) where the game called it long
    range, one 0.05 m past it the beam, a level one the same; with no
    target the game's stale distance. keylord's own build, no W40, keeps
    the game's bytes."""
    built = bytes(_swap("balthazar", sounds="garret4")["default.xbe"])
    assert verify_trampoline_patch(built, FINISH_RANGE_HOOK) == "applied"
    line = struct.unpack_from("<f", built, patch_spec_site(bytearray(built), FINISH_RANGE)[0])[0]
    assert 1.5 < line < 1.6   # his blast's face, x1.25 where W14 bumps the finish
    frame = l2._STACK_TOP - 0x104   # ESP at 0x7F0B2: the finder's result at +0x18

    def long_range(ahead: float, up: float, *, found: int = 1, stale: float | None = None) -> int:
        sim = Sim(built)
        whole = math.hypot(ahead, up)
        sim.uc.mem_write(frame + 0x18, struct.pack("<I3f", found, 0.0, ahead, up))
        sim.uc.mem_write(frame + 0x30, struct.pack("<f", whole - 1.0 if stale is None else stale))
        sim.uc.mem_write(frame + 0x54, struct.pack("<I", 0xBAD))
        sim.call(FINISH_RANGE_HOOK.va, regs={"esi": 1, "ebx": 0x33, "edi": 0x44}, until=0x7F0CF)
        assert sim.reg("esp") == frame and (sim.reg("ebx"), sim.reg("esi"), sim.reg("edi")) == (0x33, 1, 0x44)
        return sim.u32(frame + 0x54)
    assert math.hypot(line + 0.95, 1.0) - 1.0 > line   # the game's distance: past the line
    assert [long_range(line + 1.0 + d, up) for d in (-0.05, 0.05) for up in (1.0, 0.0)] == [0, 0, 1, 1]
    assert [long_range(9.0, 0.0, found=0, stale=v) for v in (line - 0.1, line + 0.1)] == [0, 1]
    keylord = bytes(_swap("keylord")["default.xbe"])
    assert verify_trampoline_patch(keylord, FINISH_RANGE_HOOK) == "original"

def test_a_drain_hit_streams_red_particles_from_the_critter_it_drains_into_the_players_chest():
    """AZ-759 (Step 2.196, D764, the owner: "also for the life drain attack,
    can you have some visual particles coming from the enemy into the
    player to indicate their life was drained?"):
    (a) an X37 build (plain Balthazar's) appends fx/damage/v/fx_drain to
        fx.xbr with its index.xbr record and names it in X37's 32-byte
        drain_fx slot, each landing's: fx_norm_1's copy (the plain hit's
        flash, its timer, its unload) with NPC Balthazar's drain stream
        grafted: [6] onPlayer, inherit 7 (the game's player: X37's anchor
        leaves another graph's to the game), holding the pull [12]-[13]
        (300, his 50) and the box sink [14] at the player's chest, 0.7 of
        the body's drawn height (Balthazar's 1.476 m); the emitter [16]-[18]
        on the victim's m_hitLocation [1] (bound), the pool [8]-[9] under
        onPlayer, unscaled (the player's frame: a victim that moves doesn't
        drag the stream's end off his chest); the timer turns the emitter off by its
        flash's fade curve at half speed (0.67 s) and unloads at 2.0 s
        (stopped at 2.2); red additive sprites (blend 5) living 1.3 s;
    (b) L2 at 0x7A1CA's entry (critter_play_fx stubbed): a drain hit that
        takes life from a critter plays the stream on it, once, a killing
        one too (Step 2.196's skeptic, F1: the third of the drain's hits
        that killed a sleeth streamed nothing), and sets its handle's flags
        to 2, so what releases it next (the AI's death clip's key 0 at
        0x37D16, another hit's visual, the delete) detaches it to play out
        where it is rather than stopping it; a hit taking none, the
        player's touch and a dropped one play none; with drain.targets all
        each critter it drains plays its own."""
    from azurkit.tools.characters._player_character import DRAIN_FX, DRAIN_STREAM

    game = _swap("balthazar", sounds="garret4")
    built, fx = bytes(game["default.xbe"]), bytes(game["fx.xbr"])
    old = parse_toc(_read("gamedata/fx.xbr"))
    for hook in DRAIN_HOOKS:
        slot = resolve_va_to_file(built, trampoline_symbol_va(built, hook, DRAIN_FX.symbol,
                                                              shim_source=DRAIN_SHIM.source_path()))
        assert built[slot:built.index(b"\0", slot)] == DRAIN_STREAM.encode(), hook.name
    toc, named = parse_toc(fx), {k: i for i, k in named_resources(fx).items()}
    assert named[DRAIN_STREAM] >= len(old) and (DRAIN_STREAM, "fx.xbr", "node") in {
        (r.key, r.archive, r.fourcc) for r in parse_index_xbr(bytes(game["index.xbr"])).records}
    schema = Schema(built)
    g = Graph(fx, toc, toc[named[DRAIN_STREAM]], schema)

    def attr(r: int, name: str) -> float:
        return round(g.attr_named(r, name), 4)

    def parent(r: int) -> int:
        return struct.unpack_from("<i", g.s, g.recs[r] + 0x18)[0]
    assert [(g.names[r], g.types[r]) for r in range(19)] == [
        ("effectOrigin", "transform"), ("m_hitLocation", "transform"), ("NormalHit_timer", "timer"),
        ("Flash", "transform"), ("FlashShape", "platform"), ("Unload_effectControl", "effectControl"),
        ("onPlayer", "transform"), ("pRendererB1", "pRendererB"), ("pSystem1", "transform"),
        ("pSystemShape1", "pSystem"), ("pSink1", "transform"), ("pSinkShape1", "pSink"), ("pGravity1", "transform"),
        ("pGravityShape1", "pGravity"), ("pBoxSink1", "transform"), ("pBoxSinkShape1", "pBoxSink"),
        ("pEmitter1", "transform"), ("timer1", "timer"), ("pEmitterShape1", "pEmitter")]
    assert [struct.unpack_from("<iI", g.s, g.recs[r] + 0x18) for r in (0, 1, 6)] == [(-1, 1), (0, 1), (-1, 0)]
    assert struct.unpack_from("<I", g.s, g.recs[6] + 0x28)[0] == 7   # the victim's two bound nodes; onPlayer a root, 7
    assert {r: parent(r) for r in (8, 12, 14, 16, 18)} == {8: 6, 12: 6, 14: 6, 16: 1, 18: 16}
    assert attr(12, "translateZ") == attr(14, "translateZ") == 1.4759          # his chest, 0.7 of his drawn height
    assert (attr(13, "magnitude"), attr(11, "maxAge"), attr(8, "scaleX"), attr(14, "scaleX"), attr(14, "scaleZ")) == (
        300.0, 1.3, 1.0, 1.6, 2.2)
    assert (attr(7, "blendMode"), attr(7, "color2R"), attr(7, "color2G"), attr(2, "stopTime")) == (5.0, 0.95, 0.15, 2.2)
    links = [(k.dst, schema.types[g.types[k.dst]].attrs[k.dst_plug], k.weight) for k in g.links(2)]
    assert links[3:] == [(18, "enable", 0.5), (5, "forceUnload", pytest.approx(1 / 6))]
    assert [(k.dst, schema.types[g.types[k.dst]].attrs[k.dst_plug]) for k in g.links(17)] == [(18, "emitRate")]

    plays = {kw_key: _drain_touch(built, *args, **kw)[4] for kw_key, args, kw in (
        ("drained", ("enemy",), {}), ("none taken", ("enemy",), {"dealt": 0}), ("killed", ("enemy",), {"hp": 15}),
        ("player", ("player",), {}), ("dropped", ("other",), {}), ("all", ("other",), {"every": True}))}
    assert plays == {"drained": [("enemy", DRAIN_STREAM, 2)], "none taken": [], "killed": [("enemy", DRAIN_STREAM, 2)],
                     "player": [], "dropped": [], "all": [("other", DRAIN_STREAM, 2)]}


def test_the_drain_streams_pull_rides_the_players_drawn_chest_and_its_sink_spans_the_lift_for_its_particles_life():
    """AZ-764 (Step 2.196's skeptic, F2): the stream's pull [12] and box
    sink [14] hang under its inherit-7 onPlayer [6], which follows the
    player's critter frame alone, so while Balthazar's basic3 lifted his
    drawn feet 2.0 m the stream ended under them. X37's anchor, placing [6]
    for an instance neither his nor held whose graph is the stream's (19
    records, [6] inherit 7), sets [12]'s translateZ to the chest (float
    param drain_chest: plain Balthazar's 1.4759 m) plus his lowest posed
    bone (anim object +8, 0xB0 bytes each, z at +0xA8; his rig's 135,
    drain_bones) over his bind pose's lowest (drain_feet), times his drawn
    scale (drain_drawn), with its dirty bit (1 << 3); the critter it
    returns is the player's. Step 2.202 (AZ-764's open part: as beamlord's
    jump attack raised the pull 0.5-0.6 m a tick, particles at the chest
    it left passed under the lifted box and were flung 12-17 m): [14]
    spans the standing chest to the lifted one, its translateZ the chest
    plus half the lift and its scaleZ the standing height (float param
    drain_sink, 2.2 m) plus the lift's size, with both dirty bits (1 << 3,
    1 << 9). Under L2 at 0x68A49's entry: lifted 2.0 model units the pull
    sits 2.0 m higher and the sink 4.2 m tall from 1.1 m under the chest;
    dipped 0.5 the pull 0.5 m lower and the sink 2.7 m tall up to 1.1 m
    over the chest; standing, or with no anim object, both at the chest,
    the sink 2.2 m; another graph's (20 records, or [6] not inherit 7)
    untouched. Step 2.202b (AZ-764's long stream: as basic3's lift ended,
    particles flying in from a target 10 m off passed over the standing
    box and flew 11-13 m off the line): by the player's clock (his
    PlayerControl's +0xC, +0x10) the sink keeps the largest lift's span for
    the particles' 1.3 s life, the pull back at the chest at once: lifted
    2.0 at 10.0 s, standing at 10.5 s the sink still 4.2 m tall to the
    lifted chest, at 11.4 s 2.2 m at the chest."""
    built = bytes(_swap("balthazar", sounds="garret4")["default.xbe"])
    _, anchor, _ = DRAIN_HOOKS
    body = read_body(_read("gamedata/characters.xbr"), "balthazar_airship")
    feet = min(p[2] for _n, p in body.bones)
    got = {k: _param(built, anchor, DRAIN_SHIM, f"_player_model_drain_{k}")
           for k in ("chest", "bones", "feet", "drawn", "sink")}
    assert got == pytest.approx({"chest": 1.4759, "bones": 135.0, "feet": feet, "drawn": 1.0, "sink": 2.2}, abs=1e-4)
    base = 0x20000000
    world, player, instance, recs, anim, bones = (base + 0x1000 * k for k in range(6))
    nodes = {r: base + 0x10000 + 0x200 * r for r in range(20)}

    pc, clock = base + 0x6000, base + 0x7000

    def placed(lift: float, *, count: int = 19, inherit: int = 7, animated: bool = True, sim: Sim | None = None,
               now: float | None = None) -> tuple:
        if sim is None:
            sim = Sim(built)
            sim.uc.mem_map(base, 0x14000)
        if now is not None:   # his PlayerControl's clock
            sim.uc.mem_write(player + 0x180, struct.pack("<I", pc))
            sim.uc.mem_write(pc + 0xC, struct.pack("<I", clock))
            sim.uc.mem_write(clock + 0x10, struct.pack("<d", now))
        for at, data in ((world + 0xC0, struct.pack("<I", player)), (player + 0x17C, struct.pack("<I", anim * animated)),
                         (anim + 8, struct.pack("<I", bones)),
                         (instance + 0x24, struct.pack("<II", recs, recs + 4 * count)),
                         (recs, struct.pack(f"<{count}I", *(nodes[r] for r in range(count)))),
                         (nodes[6] + 0xF0, struct.pack("<i", inherit))):
            sim.uc.mem_write(at, data)
        for r in (12, 14):
            sim.uc.mem_write(nodes[r] + 8, struct.pack("<I", nodes[r] + 0x100))
        for k in range(135):   # his posed bones: the lowest ``lift`` model units over his bind pose's lowest
            sim.uc.mem_write(bones + 0xB0 * k + 0xA8, struct.pack("<f", feet + lift + (0.5 if k % 7 else 0.0)))
        kept = {"ebx": nodes[6], "edi": 0x33, "ebp": 0x44}
        sim.call(DRAIN_HOOKS[1].va + 5 + struct.unpack_from("<i", built, va_to_file(anchor.va) + 1)[0],
                 regs={**kept, "eax": world, "edx": instance}, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and {r: sim.reg(r) for r in kept} == kept
        assert sim.reg("esi") == player
        return tuple((round(sim.f32(nodes[r] + 0x100 + 12), 4), round(sim.f32(nodes[r] + 0x100 + 36), 4),
                      sim.u32(nodes[r] + 0x10)) for r in (12, 14))
    assert placed(2.0) == ((3.4759, 0.0, 8), (2.4759, 4.2, 0x208))     # lifted 2 m: the pull 2 m up, the sink to it
    assert placed(-0.5) == ((0.9759, 0.0, 8), (1.2259, 2.7, 0x208))    # dipped 0.5 m: the sink down to it
    assert placed(0.0) == ((1.4759, 0.0, 8), (1.4759, 2.2, 0x208))     # standing: at his chest
    assert placed(2.0, animated=False) == ((1.4759, 0.0, 8), (1.4759, 2.2, 0x208))   # no anim object: at his chest
    for kw in ({"count": 20}, {"inherit": 0}):                           # another graph's: untouched
        assert placed(2.0, **kw) == ((0.0, 0.0, 0), (0.0, 0.0, 0)), kw
    sim = Sim(built)   # by his clock: the sink keeps the lift's span for the particles' 1.3 s
    sim.uc.mem_map(base, 0x14000)
    assert [placed(up, sim=sim, now=t)[1][:2] for up, t in ((2.0, 10.0), (0.0, 10.5), (0.0, 11.4))] == [
        (2.4759, 4.2), (2.4759, 4.2), (1.4759, 2.2)]
    assert placed(0.0, sim=sim, now=11.5)[0][0] == 1.4759   # the pull at the chest


@pytest.mark.parametrize("region", REGIONS)
def test_a_tiny_player_body_is_drawn_with_the_level_camera_within_a_metre_of_its_centre(region):
    """AZ-541 (Step 2.116, X27): the critter draw 0x3EA00 skips a critter
    whose box centre is under 1.0 m from the render eye (0x3EA69, 0x3EC6B)
    and fades it to 1.5 m (0x3ECA7) while "movie mode" ([[cvar]+4]) is
    off; the player's centre is +0x15C, 1.0 m over its drawn feet at any
    size, so at X25's 0.1 floor the eye sat 0.70-0.91 m from it and only
    its shadow and armor were drawn (sitting 2.107 B). X27 (L2, town_male_6
    at garret4's height x0.4) at the two 9-byte loads of the flag (0x3EA57
    into EAX, 0x3EC58 into ECX): the flag as the game loads it, through
    the cvar the build read from its own vanilla load (USA 0x380E04,
    Europe 0x382DA4), or 1 for the player by the game's own test
    ([[critter+0x154]+0xC0] == critter), so the draw takes the movie-mode
    branch past both exits and the fade; another critter, or one with no
    world, gets the flag; site 1 keeps ECX and leaves EDX the cvar record,
    as vanilla; site 2 keeps EAX and EDX; EBX, ESI, EDI and EBP kept, a
    plain RET. Installed only under a rig scale of 0.5: x0.55 and x1 keep
    the game's loads."""
    europe = region == "europe"
    built = bytes(_swap("town_male_6", sounds="garret4", size="garret4",
                        model_scale=0.4)["default.xbe"])
    cvar = 0x382DA4 if europe else 0x380E04
    for hook in NEAR_HOOKS:
        assert verify_trampoline_patch(built, hook) == "applied"
        assert struct.unpack_from("<I", built, resolve_va_to_file(built, trampoline_symbol_va(
            built, hook, "_player_model_movie_cvar", shim_source=NEAR_SHIM.source_path())))[0] == cvar
    if europe:
        return
    assert l1.check(_xbe(), built) == []
    base = 0x20000000
    critter, world, record, other = (base + 0x100 * k for k in range(4))

    def load(site: int, *, player: bool = True, movie: int = 0, placed: bool = True) -> int:
        sim = Sim(built)
        sim.uc.mem_map(base, 0x1000)
        for at, value in ((cvar, record), (record + 4, movie), (critter + 0x154, world if placed else 0),
                          (world + 0xC0, critter if player else other)):
            sim.uc.mem_write(at, struct.pack("<I", value))
        hook = NEAR_HOOKS[site]
        kept = {"ebx": 0, "esi": critter, "edi": 0x33, "ebp": 0x44, "ecx" if site == 0 else "eax": 0x1234}
        if site:
            kept["edx"] = 0x5678
        got = sim.call(hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0],
                       regs=kept, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # a plain RET
        assert {r: sim.reg(r) for r in kept} == kept
        if site == 0:
            assert sim.reg("edx") == record              # [cvar], as vanilla leaves it
            return got
        return sim.reg("ecx")

    for site in (0, 1):
        assert load(site) == 1, site                                       # the player: drawn
        assert [load(site, player=False, movie=m) for m in (0, 1)] == [0, 1], site
        assert load(site, placed=False) == 0, site
        assert load(site, movie=1) == 1, site
    for scale in (0.55, 1.0):
        xbe = bytes(_swap("town_male_6", sounds="garret4", size="garret4", model_scale=scale)["default.xbe"])
        assert [verify_trampoline_patch(xbe, hook) for hook in NEAR_HOOKS] == ["original"] * 2, scale


@pytest.mark.parametrize("region", REGIONS)
def test_a_tiny_bodys_camera_pushed_by_the_water_never_ends_under_its_point(region):
    """AZ-556's resting side (Step 2.116b, X29): the level camera's water
    push 0x81E10 moves a camera within 0.4 m of the surface (0x60BD0's
    depth a0 at its probe point, the camera less 0.4 m in z, in (0, 0.8))
    to its first candidate, the other side (surface -/+ 0.5 m), when the
    sweep there is clear, else its own side (surface +/- 0.4 m), and
    0x820E0 latches the pitch and distance from there. A body drawn under
    about 0.37 of garret4's size has its camera within the push's 0.9 m
    of its point, so the far side put it under the point and it rested
    looking up (+14 to +78 degrees, x0.37, flicken, boulder, x0.1), where
    garret4's pushes leave him over his point. X29 (L2, 0x81E10 run on
    town_male_6 at garret4's height x0.37's build with 0x60BD0 and
    0x60870 stubbed) at the first candidate's CALL of camera_reach
    (0x81DB0, 0x81FEB): for the player, when the far side is under the
    point and its own side at or over it, the two swap (counted), so the
    camera 0.2 m over the surface with the point 0.3 m under it ends 0.4
    m over the surface (vanilla: 0.5 m under), and one already under its
    point too (the point 0.1 m over it); the point 1 m under the camera
    (the far side over it), a camera under the water with the point over
    both and another critter's camera keep the game's push; the own
    side's sweep blocked, the game's fallback, the far side. R2 (Step
    2.116d, AZ-556 item 1): in the hoist out of the water (the 0x100 bit,
    anim 0x41 hoist or 0x42 hoist_waist) the game's order, so the camera
    goes under the body there and looks up at it, as main's; another
    aligned move or anim 0x41 outside one still swaps. Installed with X27
    (a rig scale under 0.5): x0.55 and x1 keep the CALL."""
    europe = region == "europe"
    built = bytes(_swap("town_male_6", sounds="garret4", size="garret4",
                        model_scale=0.37)["default.xbe"])
    assert verify_trampoline_patch(built, PUSH_HOOK) == "applied"
    if europe:
        return
    assert l1.check(_xbe(), built) == []
    base, surface = 0x20000000, 10.0
    camera, target, species, world, point, control = (base + 0x400 * k for k in range(6))
    swaps = trampoline_symbol_va(built, PUSH_HOOK, "_player_model_push_swaps", shim_source=PUSH_SHIM.source_path())

    def push(xbe: bytes, cam: float, at: float, *, player: bool = True, hits: tuple[bool, ...] = (),
             state: int = 0, anim: int = 0) -> tuple[float | None, int]:
        """Run 0x81E10 on a camera ``cam`` m and its point ``at`` m over
        the surface (2.5 m behind it), the player in move ``state``
        playing ``anim``: the z over the surface it commits (None: none),
        and X29's swap count."""
        sim = Sim(xbe)
        sim.uc.mem_map(base, 0x2000)
        for at_, fmt, value in ((camera + 0x15C, "<3f", (0.0, -2.5, surface + cam)), (camera + 0x154, "<I", world),
                                (camera + 0x190, "<I", target), (target + 0x178, "<I", species),
                                (target + 0x180, "<I", control), (control + 0x94, "<i", state),
                                (target + 0x200, "<i", anim),
                                (species + 0x64, "<I", 0x24 if player else 0x04), (point, "<3f", (0.0, 0.0, surface + at))):
            sim.uc.mem_write(at_, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        answers, got = list(hits), []

        def depth(uc, addr, size, _):   # 0x60BD0: __stdcall(24), the depth at the probe point into its 5th argument
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<7I", uc.mem_read(esp, 28))
            probe = struct.unpack("<3f", uc.mem_read(args[1], 12))[2]
            uc.mem_write(args[4], struct.pack("<f", surface - probe))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 28)

        def sweep(uc, addr, size, _):   # collision_sweep: __stdcall(36), RET 0x24
            esp = sim.reg("esp")
            ret = struct.unpack("<I", uc.mem_read(esp, 4))[0]
            uc.reg_write(UC_X86_REG_EAX, int(answers.pop(0)) if answers else 0)
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 40)

        def commit(uc, addr, size, _):   # the place committed (+0x170); the room and the re-aim skipped
            got.append(struct.unpack("<3f", uc.mem_read(camera + 0x170, 12))[2] - surface)
            uc.reg_write(UC_X86_REG_EIP, 0x820D0)

        for va, fn in ((0x60BD0, depth), (0x60870, sweep), (0x820A7, commit)):
            sim.uc.hook_add(UC_HOOK_CODE, fn, begin=va, end=va)
        kept = {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
        sim.call(0x81E10, regs={"eax": point, **kept}, args=(camera,))   # RET 4, the stack checked
        assert {r: sim.reg(r) for r in kept} == kept
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0          # the x87 stack empty
        return (round(got[0], 4) if got else None), (sim.u32(swaps) if xbe is built else 0)

    vanilla = _xbe()
    assert push(vanilla, 0.2, -0.3) == (-0.5, 0)                    # vanilla: under the surface, under its point
    assert push(built, 0.2, -0.3) == (0.4, 1)                       # X29: its own side, over its point
    assert push(built, 0.2, 0.3) == (0.4, 1)                        # already under its point: over it
    assert push(built, 0.2, -0.8) == (-0.5, 0)                      # the far side over its point: the game's
    assert push(built, -0.2, 0.8) == (0.5, 0)                       # under the water, the point over both
    assert push(built, 0.2, -0.3, player=False) == (-0.5, 0)        # another critter's camera
    assert push(built, 0.2, -0.3, hits=(True,)) == (-0.5, 1)        # its own side blocked: the far side
    for anim in (0x41, 0x42):                                       # the hoist out of the water (R2): the game's
        assert push(built, 0.2, -0.3, state=0x100, anim=anim) == (-0.5, 0), anim
    assert push(built, 0.2, -0.3, state=0x100, anim=0x3F) == (0.4, 1)   # another aligned move (climb_up_edge)
    assert push(built, 0.2, -0.3, anim=0x41) == (0.4, 1)                 # not in an aligned move
    for scale in (0.55, 1.0):
        xbe = bytes(_swap("town_male_6", sounds="garret4", size="garret4", model_scale=scale)["default.xbe"])
        assert [verify_trampoline_patch(xbe, hook) for hook in (PUSH_HOOK, LATCH_HOOK, EASE_HOOK)
                ] == ["original"] * 3, scale


@pytest.mark.parametrize("region", REGIONS)
def test_a_tiny_bodys_camera_pushed_by_the_water_eases_back_to_its_rest_pitch_where_the_water_leaves_it(region):
    """AZ-556's latch (Step 2.116e, R1): 0x820E0's re-aim writes a push's
    pitch and distance into the wanted ones (+0x1A0, +0x1A4) and the
    update eases the pitch toward the wanted one only by the sticks' sum,
    so a tiny body's camera kept a push's -20 to -23 degrees at the placed
    rest, -43 to -48 after a plunge and x0.1's level beach (2.116b's
    sitting), where garret4's rests at -30. X29's latch entry (L2, on
    town_male_6 at garret4's height x0.37's build with 0x81E10 stubbed to
    re-aim at chosen values, RET 4, and the volume query 0x60BD0 stubbed to
    answer a chosen depth, RET 0x18) at the push's CALL 0x81BEA: at rest
    (6 swimming, 0 the ground) the wanted values go back to what another
    writer last asked for (the reset's -30 deg / 1.8 m here), on every
    push in a row (2.116d's dwell guard tripped on the 10th), asked of the
    game's own band at the place the camera would rest at (the tree, that
    place less 0.4 m, the camera as the asker, touch 0): inside it
    (0 < depth < 0.8) the game's latch stays, and out of it the base comes
    back, never a latch (2.116d's owed the latch after a trip); in the air
    (2) and the hoist (0x100, anim 0x41) the push's latch stays. A hoist
    push arms the snap: the ease entry at 0x81891 (the block
    0x8185F-0x818E6 run, no stick) sets the pitch at once on every rest
    ease that finds it off the base, through 0.5 s of rest calls that
    weren't held off (a held-off stand doesn't use them), else eases at the
    game's 30 deg/s, 1 degree a tick, where vanilla's stays. Another
    writer's value is the new base when the camera showed its base (the
    stick, a zoom), but a stick touched while a push's line shows (easing
    back, or the hoist's latch) is a nudge: the base and the snap stay.
    Another critter's camera keeps the push's values; EBX, ESI, EDI, EBP,
    RET 4 and an empty x87 stack kept, ECX and EDX through the ease. The
    ease landing reads the latch landing's hold through its bytes param;
    the latch landing's CALLs reach each release's push and query.
    Installed with X27 (a rig scale under 0.5): x0.55 and x1 keep all
    three sites (the X29 test)."""
    europe = region == "europe"
    built = bytes(_swap("town_male_6", sounds="garret4", size="garret4",
                        model_scale=0.37)["default.xbe"])
    assert [verify_trampoline_patch(built, hook) for hook in (LATCH_HOOK, EASE_HOOK)] == ["applied"] * 2
    hold = trampoline_symbol_va(built, LATCH_HOOK, "_player_model_push_hold", shim_source=PUSH_SHIM.source_path())
    assert struct.unpack_from("<I", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, EASE_HOOK, "_player_model_push_hold_at", shim_source=PUSH_SHIM.source_path())))[0] == hold
    obj, text, text_va, landed = ports._landed_text(built, LATCH_HOOK)
    calls = {obj.symbols[r.symbol].name: text_va + r.offset + 4 + struct.unpack_from("<i", landed, r.offset)[0]
             for r in text.relocations if r.type == coff.REL32}
    assert (calls["_camera_water_push@4"], calls["_volume_query@24"]) == (
        (0x81DC0, 0x60B80) if europe else (0x81E10, 0x60BD0))
    if europe:
        return
    assert l1.check(_xbe(), built) == []
    base, tree = 0x20000000, 0x5EED0000
    camera, target, species, control, point, world = (base + 0x400 * k for k in range(6))
    latch = LATCH_HOOK.va + 5 + struct.unpack_from("<i", built, va_to_file(LATCH_HOOK.va) + 1)[0]

    def sim_for(xbe: bytes) -> Sim:
        sim = Sim(xbe)
        sim.uc.mem_map(base, 0x2000)
        for at, fmt, value in ((camera + 0x190, "<I", target), (target + 0x178, "<I", species),
                               (target + 0x180, "<I", control), (species + 0x64, "<I", 0x24),
                               (camera + 0x154, "<I", world), (world + 0xAC, "<I", tree),
                               (camera + 0x15C, "<3f", (0.0, -2.0, 11.0)), (point, "<3f", (0.0, 0.0, 10.0)),
                               (camera + 0x198, "<2f", (math.radians(-30.0), 1.8)),     # committed
                               (camera + 0x1A0, "<2f", (math.radians(-30.0), 1.8))):    # the reset's
            sim.uc.mem_write(at, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        return sim

    sim, pushes, asked, water = sim_for(built), [], [], [2.0]

    def push(uc, addr, size, _):   # 0x81E10 stubbed: [ESP+4] the camera, EAX the point, RET 4
        esp = sim.reg("esp")
        ret, cam = struct.unpack("<2I", uc.mem_read(esp, 8))
        assert (cam, sim.reg("eax")) == (camera, point)
        latched = pushes.pop(0)
        if latched:   # the re-aim: the pitch and distance and the wanted ones
            for at in (0x198, 0x1A0):
                uc.mem_write(cam + at, struct.pack("<2f", math.radians(latched[0]), latched[1]))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 8)

    def query(uc, addr, size, _):   # 0x60BD0 stubbed: __stdcall(24), the depth into its 5th argument
        esp = sim.reg("esp")
        ret, at_tree, at, asker, flags, depth, touch = struct.unpack("<7I", uc.mem_read(esp, 28))
        asked.append((at_tree, tuple(round(v, 4) for v in struct.unpack("<3f", uc.mem_read(at, 12))), asker, touch))
        uc.mem_write(depth, struct.pack("<f", water[0]))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 28)

    sim.uc.hook_add(UC_HOOK_CODE, push, begin=0x81E10, end=0x81E10)
    sim.uc.hook_add(UC_HOOK_CODE, query, begin=0x60BD0, end=0x60BD0)

    def tick(state: int, latched: tuple[float, float] | None = None, *, anim: int = 0, player: bool = True,
             depth: float = 2.0, dt: float = 1 / 30) -> tuple[float, float]:
        """One call of the latch entry in move ``state`` at the update's ``dt``, the push re-aiming at
        ``latched`` (pitch in degrees, distance) or not, the water ``depth`` under the rest place's probe:
        the wanted pitch and distance it leaves."""
        sim.uc.mem_write(control + 0x94, struct.pack("<i", state))
        sim.uc.mem_write(target + 0x200, struct.pack("<i", anim))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", 0x24 if player else 0x04))
        pushes.append(latched)
        water[0] = depth
        kept = {"ebx": 0, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
        frame = (camera,) + (0,) * 47 + struct.unpack("<I", struct.pack("<f", dt))   # [ESP+4] .. [ESP+0xC4]: dt
        sim.call(latch, regs={"eax": point, **kept}, args=frame, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 - 4 * 48          # RET 4
        assert {r: sim.reg(r) for r in kept} == kept
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0          # the x87 stack empty
        return round(math.degrees(sim.f32(camera + 0x1A0)), 3), round(sim.f32(camera + 0x1A4), 3)

    def ease(at: Sim, pitch: float) -> float:
        """The ease block (0x8185F-0x818E6) in ``at`` with no stick, one 1/30 s tick of a camera at ``pitch``
        degrees: its new pitch."""
        at.uc.mem_write(camera + 0x198, struct.pack("<f", math.radians(pitch)))
        frame = [0] * 48                                                # the block's ESP + 4 ..
        frame[3] = camera                                               # [ESP + 0x10]: the camera
        frame[46] = struct.unpack("<I", struct.pack("<f", 1 / 30))[0]   # [ESP + 0xBC]: dt
        at.call(0x8185F, regs={"ecx": camera, "edx": 0x55}, args=tuple(frame), until=0x818E6)
        assert at.reg("edx") == 0x55
        return round(math.degrees(at.f32(camera + 0x198)), 3)

    def stick(pitch: float) -> None:   # 0x81822 / 0x81832: the pitch, then the wanted one := it
        for at in (0x198, 0x1A0):
            sim.uc.mem_write(camera + at, struct.pack("<f", math.radians(pitch)))

    def word(offset: int) -> int:
        return sim.u32(hold + offset)

    probe = (0.0, round(-1.8 * math.cos(math.radians(30.0)), 4), 10.5)   # 1.8 m at -30 deg from the point, - 0.4 m
    assert tick(6, (-20.0, 1.2)) == (-30.0, 1.8)          # swimming, the rest place out of the band: the base
    assert (word(0x24), word(0x28), asked) == (1, 1, [(tree, probe, camera, 0)])
    assert ease(sim, -20.0) == -21.0                      # eased at 30 deg/s
    assert ease(sim_for(_xbe()), -20.0) == -20.0   # vanilla: the push's pitch stays
    for _ in range(12):                                   # the placement's sink: pushed every tick
        assert tick(6, (-20.0, 1.2)) == (-30.0, 1.8)
    assert (word(0x24), word(0x28)) == (13, 13)
    assert tick(0, (-42.7, 0.589), depth=0.3) == (-42.7, 0.589)   # the rest place in the band: the game's latch
    assert tick(0, depth=0.3) == (-42.7, 0.589)
    assert (word(0x20), word(0x2C)) == (1, 2)
    assert tick(0, depth=1.2) == (-30.0, 1.8)             # out of it: the base, not the latch
    assert word(0x20) == 0
    queried = len(asked)
    assert tick(2, (-45.0, 2.0)) == (-45.0, 2.0)          # in the air: the game's latch, nothing asked
    assert len(asked) == queried
    assert tick(6) == (-30.0, 1.8)
    for k in range(20):                                   # the shore walk, pushed in the band every tick
        assert tick(0, (-42.0 - 0.6 * k, 0.6), depth=0.3) == (round(-42.0 - 0.6 * k, 3), 0.6)
    assert tick(2, (-44.0, 0.7)) == (-44.0, 0.7)
    assert tick(6) == (-30.0, 1.8)                        # into the water: the base again
    assert tick(0x100, (46.0, 0.9), anim=0x41) == (46.0, 0.9)   # the hoist out: the game's (R2's view)
    assert word(0x18) == 1                                # the snap armed
    for _ in range(20):                                   # the stand before its pop, held off
        assert tick(0, depth=0.3) == (46.0, 0.9)
    assert ease(sim, 46.0) == 46.0                        # the game's: no snap off the base
    assert tick(0) == (-30.0, 1.8)                        # the pop: out of the band
    assert ease(sim, 46.0) == -30.0                       # the snap, still armed after the held-off ticks
    assert ease(sim, -86.0) == -30.0                      # the stand's re-derive after it: again
    assert word(0x30) == 2
    for _ in range(16):                                   # 0.5 s of rest calls
        assert tick(0) == (-30.0, 1.8)
    assert word(0x18) == 0
    assert ease(sim, -40.0) == -39.0
    stick(-30.0)                                          # the ease done
    assert tick(0) == (-30.0, 1.8)
    stick(-10.0)                                          # the player's stick at rest: an ask
    assert tick(0) == (-10.0, 1.8)
    assert (struct.unpack("<f", struct.pack("<I", word(0)))[0], word(0x14) & 1) == (sim.f32(camera + 0x1A0), 0)
    assert ease(sim, -40.0) == -40.0                      # not held: the game's rate
    sim.uc.mem_write(camera + 0x1A4, struct.pack("<f", 1.5))   # the zoom: an ask
    assert tick(6) == (-10.0, 1.5)
    assert tick(6, (-20.0, 1.2)) == (-10.0, 1.5)          # the base is the player's
    assert ease(sim, -40.0) == -39.0
    assert tick(0, (-54.0, 0.6)) == (-10.0, 1.5)
    stick(-53.0)                                          # the stick while the push's -54 shows: a nudge
    assert tick(0) == (-10.0, 1.5)
    assert tick(0x100, (46.0, 0.9), anim=0x41) == (46.0, 0.9)
    stick(28.5)                                           # a nudge in the hoist
    assert tick(0x100, anim=0x41) == (28.5, 0.9)
    assert word(0x18) == 1
    assert tick(0) == (-10.0, 1.5)
    assert ease(sim, 28.5) == -10.0                       # the snap after it
    queried = len(asked)
    assert tick(6, (-20.0, 1.2), player=False) == (-20.0, 1.2)   # another critter's camera
    assert len(asked) == queried


@pytest.mark.parametrize("species, mode, tall, eye", [
    ("kingkong", "own", 3.381, 1.9925),       # golem x 5: its mesh's top (its bones' 3.03)
    ("firefly", "garret4", 0.174, 0.1002),    # its wings lie flat: their 17 cm span
    ("firefly", "own", 0.174, 0.1002),        # and X3's box at its chest, not 8 m up
    ("balthazar", "own", 2.119, None),        # balthazar_airship's own m_head
])
def test_a_body_sized_to_garret4_stands_his_height_with_the_camera_at_his_eye(species, mode, tall, eye):
    """Q304, 2.60 REPORT §4.1 (2)-(3), Step 2.68: a swapped body renders
    at its model's size times its scale (kingkong's golem x 5 filled the
    screen, a firefly is a speck; xemu sitting p8). ``size="garret4"``,
    in any mode, writes garret4's height over the body's as garret4's
    scale cell (in place of the species' scale; in garret4's exact, which
    writes none), so its mesh's top stands at garret4's 2.002 m (a mesh
    that lies flat, the firefly's, the tentacles': its longest side
    there). X8 aims the camera at garret4's eye height (his m_head,
    1.9925 m: a point the game scales by the critter's scale) on an
    upright body without an m_head, and on a flat one at garret4's share
    of its drawn top (Step 2.107: the firefly's wings, 0.10 m up, even
    though its bind pose has no top); a body with its own m_head keeps
    the game's lookup. A body with neither a
    hand nor a damage marker has its action point, X3's box and W6's
    particles, at 0.7 x its height, so at 0.7 x garret4's (the firefly's
    bones have no top: it was 1 model unit, 8 m up once sized).
    ``size="own"`` is the default build."""
    characters = _read("gamedata/characters.xbr")
    vanilla = _read("gamedata/config.xbr")
    garret4 = 2.002
    game = _swap(species, mode=mode, size="garret4")
    engine = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("critters_engine")
    scale = engine.find_cell("garret4", "scale", None).double_value

    assert height(characters, read_body(characters, "garret4")) == pytest.approx(garret4, abs=5e-4)
    assert scale * tall == pytest.approx(garret4, abs=0.001)
    assert engine.find_cell(species, "scale", None).double_value == XbrDocument.from_bytes(
        vanilla).keyed_section("critters_engine").find_cell(species, "scale", None).double_value
    built = bytes(game["default.xbe"])
    if eye:
        (x, y, z), returned = _camera_point(built, 0x24)
        assert (x, y, returned) == (0.0, 0.0, True) and z * scale == pytest.approx(eye, abs=1e-4)
    else:
        assert built[va_to_file(0x41F67):va_to_file(0x41F67) + 5] == _xbe()[
            va_to_file(0x41F67):va_to_file(0x41F67) + 5]
    if mode == "own" and species == "firefly":
        assert _x3_tick(built, 0, 0.35, scale=scale)[3][2] * scale == pytest.approx(0.7 * garret4, abs=1e-3)


@pytest.mark.parametrize("species, mode, size, k, bound, reach, want", [
    ("keylord", "own", "own", 2.0, 3.0, 2.0, None),          # its 2.0 x 2, bumped as at x1 (AZ-567); bound 1.5 x 2
    ("keylord", "garret4", "own", 0.5, 1.5, 1.0, None),      # 1.0 x 0.5; garret4's own boxes (X3) keep his reach
    ("kingkong", "own", "garret4", 2.5, None, 2.5, None),    # garret4's height x 2.5: its boxes x 2.5 (AZ-559)
    ("garret4", "own", "own", 2.0, 3.0, 2.0, 6.059),         # his own body (Step 2.123): his 1.5 x 2, his boxes x 2,
])                                                           # sweep2's 2 x 4.130 less its m_feet's 2.2 past basic1
def test_the_model_scale_draws_the_body_that_many_times_its_size_and_what_the_size_moves_follows(
        species, mode, size, k, bound, reach, want):
    """Step 2.98 (D279; the owner: "for models, I would like an option to
    scale model size, similar to how attack reach and others get
    options"): ``model_scale`` (``--player-character-scale``) multiplies
    the scale W2 writes for the mode and size (keylord's own 2.0;
    garret4's exact none, so 1.0; garret4's height), any finite number
    (D23), and every check the size feeds follows: the bounds (the
    body's at the new scale, at least garret4's times it), the reach the
    logic reads (keylord's own boxes twice as far; garret4's boxes in his
    exact unmoved; kingkong's x2.5, with the 4 m melee line: AZ-559;
    garret4's own twice as far, his own body drawn x2, Step 2.123) and
    the camera point, in model units, which the game scales with it (the
    log naming garret4's eye height x k at his height; how the camera
    frames it at k, the swim margins too, is :func:`camera_plan`'s,
    ``test_the_camera_frames_a_body_drawn_at_any_size_as_garret4_does_at_x1``).  No sitting has
    graded a scaled swapped build, so its status is unseen (D242), as
    ``player-models --scale`` lists it, whose ``--attacks`` measure the
    boxes at that scale; garret4's own x2 has sitting 2.123's grade.
    Since Step 2.197b (AZ-766) the logic and the listing read each box from
    the body, back by its clip's ``m_feet``, which the drawn origin keeps
    unscaled (``docs/RE_XBE.md``), so a lunge's box doesn't scale with
    the body: the listing's first swing does (no lunge), and garret4's
    sweep2 x2 reaches past his basic1."""
    config = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    one, scaled = AttackLogic(), AttackLogic()
    logs: list[list[str]] = [[], []]
    built = [_swap(species, lines=log, mode=mode, size=size, model_scale=s, logic=logic)
             for log, s, logic in zip(logs, (1.0, k), (one, scaled))]
    engines = [XbrDocument.from_bytes(g["config.xbr"]).keyed_section("critters_engine") for g in built]
    s1, sk = (e.find_cell("garret4", "scale", None) for e in engines)
    theirs = engines[0].find_cell(species, "boundRadius", None).double_value

    assert sk.double_value == pytest.approx((s1.double_value if s1.type_code == 1 else 1.0) * k)
    assert engines[1].find_cell("garret4", "boundRadius", None).double_value == pytest.approx(
        bound or theirs * sk.double_value)
    assert scaled.reach == (None if reach is None else pytest.approx(want or one.reach * reach, abs=2e-3))
    assert _camera_point(bytes(built[1]["default.xbe"]), 0x24) == _camera_point(bytes(built[0]["default.xbe"]), 0x24)
    graded = GARRET4_SIZES[k][0] if species == "garret4" else "unseen"
    assert logs[1][-1].startswith(f"  Player model status: {graded}") and not logs[0][-1].startswith(
        "  Player model status: unseen")
    assert (f"garret4's eye height x{k:g}" in "".join(logs[1])) is (size == "garret4")
    assert {m.species: m.status for m in player_models(config, characters, mode, size, k)}[species] == graded
    listed = [max(w.reach for r in attacks(config, characters, species, mode, size, s) if r.column == "basic1"
                  for w in r.windows) for s in (1.0, k)]
    assert listed[1] == pytest.approx(listed[0] * k, abs=0.01)   # keylord's attack_1 lunges 0.009 m


def test_the_logics_melee_line_is_drawn_at_the_model_size_and_a_staff_cast_never_counts():
    """AZ-559 (Step 2.123 C1; D237, D279): the randomizer's logic reads a
    build's farthest melee box (:func:`melee_reach`), melee by Step 2.61's
    4 m line, and a model scale draws every box that many times as far, so
    the line is drawn at the scale too and an attack's class is its x1
    one. On garret4's own table his basic2 (3.79 m) is the farthest at
    every size: x2.5 reads it x2.5, not the last box still under an
    absolute 4 m (right2's, 3.97 m; from x2.73 none), and x0.5 half of
    it, under D237's 2.77 m swing, not his elemental2 sphere's 3.52 m.
    The staff's casts (elemental1-3) are magic, never the basic swing D237
    asks for: a melee sweep (3.67 m) played in them leaves basic1's."""
    characters = _read("gamedata/characters.xbr")
    anims = XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section("attacks_anims")
    columns = anims.col_names()
    clips = [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    garret4 = read_body(characters, "garret4")

    def far(column: str) -> float:
        return max(w.reach for w in damage_windows(characters, "garret4", clips[columns.index(column)]))

    def reach(picks: list[str], k: float) -> float | None:
        return melee_reach(characters, garret4, columns, picks, k, 0, GARRET4_REACH, model_scale=k)
    assert [reach(clips, k) for k in (1.0, 2.5, 0.5)] == pytest.approx([far("basic2") * k for k in (1.0, 2.5, 0.5)])
    assert reach(clips, 0.5) < GARRET4_REACH < far("elemental2") * 0.5 < MELEE_REACH   # a half-size cast no longer passes
    cast = [clips[columns.index("sweep1")] if col in CASTS else clips[0] for col in columns]
    assert far("basic1") < far("sweep1") < MELEE_REACH and reach(cast, 1.0) == pytest.approx(far("basic1"))


def test_the_reach_bump_and_a_recipes_chain_search_judge_a_box_at_model_size_1():
    """AZ-567 (Step 2.175a; AZ-559's rule, D237): the balance's reach bump
    (a melee box under 0.75 of garret4's basic1 reach, 2.08 m: D345) and
    X21's search over a recipe's melee boxes (``search_reach`` with
    ``melee``) draw their lines at the Model size, as the logic's melee
    line does, so a box's class is its x1 one: keylord own bumps the same
    columns drawn x0.5, x1 and x2 (its basic1 among them; at x2 it was
    left out), and garret4's basics drawn x2.5 (2.77-3.79 m at x1, none
    still under an absolute 4 m) search out to basic2's, not X21's 3 m."""
    masks = {k: int(_param(bytes(_swap("keylord", model_scale=k)["default.xbe"]), ATTACK_BOX_HOOK, ATTACK_BOX_SHIM,
                           "_player_attack_bump_mask")) for k in (0.5, 1.0, 2.0)}
    assert masks[1.0] & 1 and masks[0.5] == masks[1.0] == masks[2.0], masks
    characters = _read("gamedata/characters.xbr")
    anims = XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section("attacks_anims")
    columns = anims.col_names()
    clips = [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    far = max(w.reach for w in damage_windows(characters, "garret4", clips[columns.index("basic2")]))
    assert search_reach(characters, read_body(characters, "garret4"), columns, clips, 2.5, 0, GARRET4_REACH,
                        melee=True, model_scale=2.5) == pytest.approx(far * 2.5)


def test_an_own_box_that_never_meets_the_pressed_targets_near_face_gives_its_column_to_x3():
    """AZ-613 (Step 2.175a; Step 2.69's reach test, D296): W19's pressed
    target stands PLAYER_RADIUS x max(drawn, 1) ahead of the feet and X13's
    fill keeps a box's far faces, so an own box that clears the 0.6 m reach
    test but whose far face stops short of that target never meets it:
    such a column, on a clip garret4 doesn't own, now takes X3 (fire_shard
    own x2, every attack column, its boxes 0.70 m ahead against 1.0 m;
    water_tentacle1 at garret4's height, its seven attack_l2/attack_r2 side
    swipes), while garret4's own left1, back1 and back2, which swing to the
    side and behind by design, keep passing at any size."""
    cases = (("fire_shard", "own", 2.0, ("basic1", "finish3", "jump attack", "back2", "down")),
             ("water_tentacle1", "garret4", 1.0, ("basic2", "finish3", "sweep ledge", "hose_attack_3", "right2",
                                                  "back2", "down")))
    anims = XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section("attacks_anims")
    columns = anims.col_names()
    for species, size, k, moved in cases:
        x3 = _x3_param(bytes(_swap(species, size=size, model_scale=k)["default.xbe"]), "columns")
        assert all(x3 >> columns.index(col) & 1 for col in moved), (species, hex(x3))
    assert x3 != (1 << len(columns)) - 1 - (1 << columns.index("roll forward"))   # the tentacle's others its own
    characters = _read("gamedata/characters.xbr")
    clips = [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    assert [reach_misses(characters, read_body(characters, "garret4"), columns, clips, s) for s in (1.0, 2.0)] == [0, 0]


def test_x3s_box_on_a_hand_keeps_its_sideways_place_when_the_model_is_scaled_up():
    """AZ-521 (xemu 2.98: town_male_6 own at --player-character-scale 2
    hit a blaze sentinel to 3.625 m where garret4 and x0.5-x1.5 hit to
    3.75, its box's centre 0.78-0.82 m to the side of the facing line
    against x1's 0.39-0.41): X3 puts garret4's narrow box (half width
    0.12 m) at the hand bone's runtime origin, in model units the game
    scales by the critter's +0x188, so the scale carried its sideways
    place (x) out with the hand, off a small target dead ahead. Since
    the fix (L2, X3's tick on each build) the hand's sideways place is
    multiplied by 1 over a model scale above 1, so in metres it stays
    x1's; at x1 and x0.5 the box is as before, and forward (garret4's
    1.2341 m ahead, over the scale) and up it follows the hand. (Since
    Step 2.134a town_male_6 swings garret4's attacks with his own boxes in
    Balanced, so Balthazar own's hand, left_w, carries the box here.)"""
    hand = (0.35, 0.10, 1.11)
    places, scales = {}, {}
    for k in (1.0, 2.0, 0.5):
        built = _swap("balthazar", model_scale=k, sounds="garret4")   # his fall voices (X15) touch an L2 blind spot
        xbe = bytes(built["default.xbe"])
        cell = XbrDocument.from_bytes(built["config.xbr"]).keyed_section("critters_engine").find_cell(
            "garret4", "scale", None)
        scale = cell.double_value if cell is not None and cell.type_code == 1 else 1.0   # x1: his cell stays empty
        bone, columns = _x3_param(xbe, "bone"), _x3_param(xbe, "columns")
        assert bone >= 0, k                                     # X3 rides the hand
        column = next(c for c in range(24) if columns >> c & 1)
        centre = _x3_tick(xbe, column, 0.35, scale=scale, bones={bone: hand})[3]
        assert centre[1:] == pytest.approx((hand[1] + 1.2341 / scale, hand[2])), k
        places[k], scales[k] = centre[0] * scale, scale         # metres beside the facing line
    assert places[2.0] == pytest.approx(places[1.0]) and places[1.0] == pytest.approx(hand[0] * scales[1.0])
    assert places[0.5] == pytest.approx(places[1.0] / 2)


_MARKER = (0.25, 1.5, 1.2, math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5), 0.2, 0.4, 0.6, 0.5, 1.0)
"""A synthetic damage marker (position, quaternion, extents, length, active):
90 degrees about x, so the box's y axis points up and its z axis back."""


def _attack_box(built: bytes, flags: int, column: int | None,
                marker: tuple[float, ...] = _MARKER) -> tuple[tuple, tuple, bool]:
    """Run ``built``'s CALL at 0x43B47 (the damage pass's box build,
    X13's hook) under Unicorn on the damage ``marker``'s 12 values for a
    critter of a species with ``flags`` (S+0x64) whose PlayerControl
    (critter+0x180) plays ``attacks_anims`` column ``column`` (+0x134;
    None: no controller), EBX the critter's damage task (critter+0xD8) as
    in 0x43A80: the box's matrix (16 floats) and min/max (6), and whether
    it came back as 0xCA390 does (plain RET, EBX, ESI and EDI kept)."""
    at = va_to_file(0x43B47)
    target = 0x43B4C + struct.unpack_from("<i", built, at + 1)[0]
    sim, base = Sim(built), 0x20000000
    critter, species, control, box_marker, matrix, box = (base + k * 0x400 for k in range(6))
    sim.uc.mem_map(base, 0x2000)
    sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
    sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
    if column is not None:
        sim.uc.mem_write(critter + 0x180, struct.pack("<I", control))
        sim.uc.mem_write(control + 0x134, struct.pack("<i", column))
    sim.uc.mem_write(box_marker + 4, struct.pack("<12f", *marker))
    sim.call(target, regs={"ecx": matrix, "eax": box, "edx": box_marker, "ebx": critter + 0xD8,
                           "esi": 0x1234, "edi": 0x5678}, until=l2._RETURN)
    kept = (sim.reg("esp"), sim.reg("ebx"), sim.reg("esi"), sim.reg("edi")) == (
        l2._STACK_TOP - 0x100, critter + 0xD8, 0x1234, 0x5678)
    return (struct.unpack("<16f", sim.uc.mem_read(matrix, 64)),
            struct.unpack("<6f", sim.uc.mem_read(box, 24)), kept)


def _bounds(m: tuple, b: tuple, k: float = 1.0) -> tuple[list[float], list[float]]:
    """A box's model-space bounds (min, max per axis) from its matrix and
    min/max, its reach ``k`` times as X13 grows it (the centre's x and y
    and the min/max times k)."""
    centre = (m[12] * k, m[13] * k, m[14])
    lo = [centre[i] + sum(min(m[4 * j + i] * b[j], m[4 * j + i] * b[3 + j]) * k for j in range(3))
          for i in range(3)]
    hi = [centre[i] + sum(max(m[4 * j + i] * b[j], m[4 * j + i] * b[3 + j]) * k for j in range(3))
          for i in range(3)]
    return lo, hi


def test_x13_scales_the_players_hit_box_reach_and_fills_a_box_to_the_feet_the_line_and_the_floor():
    """D222 amended, D223 (Step 2.70): a swapped body's hit box is its own
    marker's (keylord's from 1.11 m up, Balthazar's from 1.23 m), which
    passes over a sleeth or a flicken (Step 2.61). With a reach other than
    1.0 or reach-to-ground the build hooks the damage pass's CALL 0xCA390
    at 0x43B47 (ECX the matrix, EAX the min/max, EDX the marker, EBX the
    critter's +0xD8 task); for the player's species the box's centre
    moves reach times as far ahead (its height stays) and its min/max
    grow reach times. AZ-605 (Step 2.132, D347, D341: guard_air's boxes
    stayed 1.27 m ahead or overhead, blaze_sentinel's X3 box 1.19-1.47 m
    right of the facing line, a big body's near face s times as far out):
    in every attack column but the roll the box becomes its model-space
    bounds (rows 0-2 the identity), and, unless it is wholly behind the
    feet, its near face comes back to them and it widens to the facing
    line, then a bottom above the feet comes down to them, its far faces
    and top kept: a pitched box ahead and high, one beside the line, one
    behind (lowered only). The roll, no controller and another critter
    keep the game's box (the reach aside); a build with neither option
    installs nothing. Balthazar own's default fills every column but the
    roll, his basic1 bumped x1.25 (D223) and his basic3 beam not; garret4
    drawn x2 fills his (D347: "including for big models"), x1 installs
    nothing. A reach takes any finite number (D23); randomize-full
    refuses NaN and inf before any work, as for the attack damage and
    speed options and the model scale (Step 2.98): ``characters.normalize``,
    which the sdk's and the CLI's builds read a character through."""
    vanilla = _xbe()
    built = bytes(_swap("keylord", attack_reach=1.25, attack_ground=True, attack_balance=False)["default.xbe"])
    assert l1.check(vanilla, built) == []
    pitch = (math.sin(math.radians(15)), 0.0, 0.0, math.cos(math.radians(15)))
    ahead = (0.0, 2.2, 2.2, *pitch, 0.47, 0.6, 1.0, 1.0, 1.0)                 # 1.2-3.2 m ahead, 1.0-3.4 m up
    beside = (1.33, 0.155, 1.07, 0.0, 0.0, 0.0, 1.0, 0.14, 1.525, 1.07, 1.0, 1.0)  # x 1.19-1.47, z 0-2.14
    behind = (0.3, -1.5, 1.0, 0.0, 0.0, math.sin(math.radians(20)), math.cos(math.radians(20)),
              0.3, 0.4, 0.5, 1.0, 1.0)
    for marker, column, fill in ((ahead, 0, "ahead"), (beside, 0, "beside"), (behind, 0, "behind"),
                                 (ahead, 20, None), (ahead, None, None)):
        m0, b0, _ = _attack_box(vanilla, 0x24, 0, marker)             # the game's own box
        lo0, hi0 = _bounds(m0, b0, 1.25)
        m, b, kept = _attack_box(built, 0x24, column, marker)
        lo, hi = _bounds(m, b)
        assert kept, (fill, column)
        if fill is None:                                              # reach alone, the game's axes
            assert m[:12] == m0[:12] and (lo, hi) == (pytest.approx(lo0, abs=1e-5), pytest.approx(hi0, abs=1e-5))
            continue
        assert m[:12] == (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0), fill
        want = {"ahead": ([lo0[0], 0.0, 0.0], hi0),                    # back to the feet, down to the floor
                "beside": ([0.0, lo0[1], lo0[2]], hi0),                # across to the facing line
                "behind": ([lo0[0], lo0[1], 0.0], hi0)}[fill]          # lowered only
        assert {"ahead": lo0[0] < 0.0 < lo0[1] and lo0[2] > 0.0, "beside": lo0[0] > 0.0 >= lo0[2],
                "behind": hi0[1] < 0.0 < lo0[2]}[fill], fill                # where the game's box is
        assert (lo, hi) == (pytest.approx(want[0], abs=1e-5), pytest.approx(want[1], abs=1e-5)), fill
    assert _attack_box(built, 0x04, 0, ahead)[:2] == _attack_box(vanilla, 0x04, 0, ahead)[:2]   # not the player
    assert verify_trampoline_patch(bytes(_swap("keylord", attack_ground=False, attack_balance=False)[
        "default.xbe"]), ATTACK_BOX_HOOK) == "original"
    for species, kw, mask, bumped in (("balthazar", {}, 0xEFFFFF, True), ("garret4", {"model_scale": 2.0}, 0xEFFFFF,
                                                                         False)):
        xbe = bytes(_swap(species, **kw)["default.xbe"])
        params = [_param(xbe, ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, f"_player_attack_{k}")
                  for k in ("reach", "ground_mask", "bump_mask")]
        assert params[:2] == [1.0, mask] and (int(params[2]) & 1, int(params[2]) >> 2 & 1) == (bumped, 0), species
    assert verify_trampoline_patch(bytes(_swap("garret4", attack_damage=2.0)["default.xbe"]),
                                   ATTACK_BOX_HOOK) == "original"
    for field, bad in (("attack_reach", math.nan), ("attack_reach", -math.inf), ("attack_damage", math.inf),
                       ("attack_speed", math.nan), ("scale", math.inf)):
        with pytest.raises(ValueError, match=f"^character: {field} {bad!r} is not a finite number"):
            characters.normalize({"species": "keylord", field: bad})


def _ring(built: bytes) -> tuple[int, int, int, int, list[int], int, dict[int, tuple[float, float]]]:
    """X10's ring in a build: its count, next entry, rotate mask, carry
    flag, each entry's column, the chained mask and each entry's chain
    point's terms (hit, after) by its column."""
    (start, _), = [span for span in shim_data(built) if span[1] - span[0] == RING_SIZE]
    at = resolve_va_to_file(built, start)
    count, turn, rotate, carry, chained = struct.unpack_from("<iiIII", built, at)
    entries = [RING_ENTRY.unpack_from(built, at + 0x14 + RING_ENTRY.size * k) for k in range(count)]
    return count, turn, rotate, carry, [e[0] for e in entries], chained, {e[0]: e[2:4] for e in entries}


@pytest.mark.parametrize("species, mode, options, weighed", [
    ("keylord", "own", {}, {"basic1": 1.55, "basic2": 3.34, "jump attack": 2.51}),
    ("balthazar", "own", {}, {"basic1": 2.45, "basic3": 1.32, "jump attack": 2.64, "up2": 2.08, "down": 2.2}),
    ("spideyzar", "own", {"attack_damage": 2.0, "attack_speed": 1.5}, {"basic1": 1.79, "right1": 0.88}),
    ("fire_elemental", "own", {}, {"basic1": 1.28, "basic2": 1.82, "basic3": 1.4}),
    ("balthazar", "garret4", {"attack_balance": True}, {"basic1": 1.0, "jump attack": 1.0, "elemental3": 1.0}),
    ("keylord", "garret4", {}, None),
    ("spideyzar", "own", {"attack_balance": False, "attack_damage": 0.5, "attack_speed": 2.0}, None),
    ("keylord", "own", {"attack_balance": False}, None),
])
def test_the_attack_balance_weighs_each_attacks_damage_against_garret4s_with_the_sliders_on_top(
        species, mode, options, weighed):
    """D223, D228 (Step 2.69, 2.61's formula): with the attack balance,
    on by default in own body, each attacks_anims column's Damage
    multiplier (W14; its empty cells filled) is garret4's x B, B = (the
    move's ticks / garret4's for that column) x sqrt(garret4's reach /
    its reach, x1.25 for a short melee box) x (garret4's hits / its),
    held to 0.5-4.0: per hit keylord's basic1 x1.55 and his 1.27 s
    attack_2 in basic2 x3.34 (both bumped since Step 2.132 draws the
    bump's line at 0.75 of garret4's reach, D345). D350 (Step 2.132,
    AZ-614): a slow attacker, whose basics chain on average at least
    twice as late as garret4's, takes its own factor on every attack,
    up to 5.0 (D350 amending D228's hold): Balthazar (2.10x, x1.12) his
    basic1 x2.45, his basic3 beam x1.32 and jump attack x2.64; the fire
    elemental (1.39x, its basics bumped) and keylord (1.24x) aren't slow,
    and the fire elemental, under garret4's damage on one enemy, takes
    x1.19 to reach it (D389): x1.28-1.82; spideyzar, whose basics play
    its own three clips since Step 2.135 (X36's sets, no X10 ring), isn't
    slow either and takes x1.77 (D389): its 6.1 m basic1 x1.79 and right1
    the floor's 0.5 x 1.77 (since Step 2.202b, AZ-804, garret4's norm as
    the game sends it). garret4's exact (every move in
    garret4's time, garret4's box) writes none, unless asked: an explicit option overrides the mode's default (garret4's
    exact, Step 2.68: X3 plays garret4's own box and window for each
    column in his time, so every column weighs x1.00).
    The damage slider multiplies
    every attack's multiplier and the speed slider every attack's Rate
    (W5's, if any) on top, never the roll's (any finite number, D23); at
    1.0 with the balance off nothing is written."""
    damage, speed = options.get("attack_damage", 1.0), options.get("attack_speed", 1.0)
    plain = {k: v for k, v in options.items() if k not in ("attack_damage", "attack_speed")}
    told: list[str] = []
    game = _swap(species, lines=told, mode=mode, **options)
    log = " ".join(told)
    tables = [XbrDocument.from_bytes(config).keyed_section("attacks_anims") for config in (
        _read("gamedata/config.xbr"), game["config.xbr"],
        _swap(species, mode=mode, **plain)["config.xbr"])]
    clause = re.search(r"\((a slow attacker|garret4's damage on one enemy): x([\d.]+) the balance's, (D350|D389)\)",
                       log)
    assert (clause and clause.group(3)) == (None if weighed is None or mode != "own" or species == "keylord" else
                                            "D389" if species in ("fire_elemental", "spideyzar") else "D350"
                                            ) and SLOW_RATIO == 2.0
    factors = {}
    for i, col in enumerate(tables[0].col_names()):
        (m0, rate0), (m, rate), (_, rate1) = (
            tuple(c.double_value if c.type_code == 1 else None
                  for c in (t.find_cell(col, MULTIPLIER, i), t.find_cell(col, "Rate", i))) for t in tables)
        if col == "roll forward":
            assert (m, rate) == (m0, rate1)
            continue
        assert rate == pytest.approx(rate1 * speed, rel=1e-12), col
        if weighed is None:
            assert m == (m0 if damage == 1.0 else (m0 or 1.0) * damage), col
        else:
            factors[col] = m / ((m0 or 1.0) * damage)
    k = float(clause.group(2)) if clause else 1.0
    assert weighed is None or (all(BALANCE_FLOOR * (k - 0.005) <= b <= min(BALANCE_CAP * (k + 0.005), BALANCE_CAP
                                                                          * SLOW_BONUS) for b in factors.values())
                               and {col: round(factors[col], 2) for col in weighed} == weighed)



def test_the_balance_weighs_an_own_bodys_attacks_against_garret4s_moves_as_the_game_sends_them():
    """AZ-804 (Step 2.202b; the late review of f46a9b550, P1): W14 weighed
    an own body's columns against garret4's moves read from his clip's
    boxes, but the game sends a lunge's box back from the body by his
    clip's horizontal m_feet (``sent_windows``, AZ-766), so his basic2,
    basic3, finish, sweeps and ups reached x1.08-1.16 farther in the
    measuring alone and an own body's multipliers there stood x1.09-1.16
    too high (a borrowed column, weighed as sent since Step 2.197b's F1,
    didn't). Now the norm is his move as sent in every column but in
    garret4's exact: keylord own's (no lift) basic1 0.7741 as before,
    basic2 1.6688, basic3 0.8506, finish 3.7515, sweep2 2.678, up1 1.1103
    and up2 5.3674 (were 1.8198, 0.9376, 4.3037, 3.11, 1.2586, 5.9651),
    the review's probe's values read as sent."""
    anims = XbrDocument.from_bytes(bytes(_swap("keylord")["config.xbr"])).keyed_section("attacks_anims")
    columns = anims.col_names()
    got = {col: round(anims.find_cell(col, MULTIPLIER, columns.index(col)).double_value, 4)
           for col in ("basic1", "basic2", "basic3", "finish", "sweep2", "up1", "up2")}
    assert got == {"basic1": 0.7741, "basic2": 1.6688, "basic3": 0.8506, "finish": 3.7515, "sweep2": 2.678,
                   "up1": 1.1103, "up2": 5.3674}

def test_a_skin_only_bodys_basics_chain_inside_the_stun_at_any_attack_speed():
    """AZ-568 (Step 2.175a; Step 2.123's chain rule, D312, Q2's default):
    Skin only (garret4 mode) plays each attack in garret4's time with his
    windows, so the speed slider moved its chain point with his raw one
    (basic1 2.6 ticks after its hit at x2, past the stun at x0.5); W14 now
    holds its basics' chain inside the stun as on his own body
    (``speed_chain``): keylord's basic1-3 Move end1 his own body's at x0.5
    and x2, and the log says so (a clipless body's:
    ``test_the_attack_sliders_write_garret4s_own_table_and_a_clipless_bodys_and_keep_his_combo_chaining``)."""
    vanilla = XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section("attacks_anims")
    columns = vanilla.col_names()

    def end1(game) -> list[float]:
        anims = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("attacks_anims")
        return [anims.find_cell(col, "Move end1", columns.index(col)).double_value for col in CHAINED]
    raw = end1({"config.xbr": _read("gamedata/config.xbr")})
    for speed in (0.5, 2.0):
        his = end1(_swap("garret4", attack_speed=speed))
        assert his[0] != raw[0], speed
        told: list[str] = []
        game = _swap("keylord", lines=told, mode="garret4", attack_speed=speed)
        log = " ".join(told)
        named = "basic1, basic2" if speed < 1 else "speed x2, basic1 "   # x2: basic2's own sees the stun (AZ-712)
        assert end1(game) == his and named in log.split("chaining inside the stun")[0][-40:], speed


def test_an_x3_column_is_weighed_at_the_reach_of_x3s_box_where_the_build_puts_it(monkeypatch):
    """AZ-415 (Step 2.175a; Step 2.64's action point, 2.70b): W14 weighs a
    column X3 serves at the reach of X3's box where the build puts it, the
    one the logic reads (``x3_reach``), not garret4's attack_1 box ahead of
    his feet (2.77 m): at its m_damage firedrake own's reaches 3.30 m and
    fire_shard's, centred on its feet, 1.53 m, so each of their X3 columns
    weighs sqrt(2.77 m / that reach) times what his box gave it (2.61's
    reach term), its own columns as before; on a hand (guard_fire1 own)
    X3's box is his where he holds it, weighed at his attack_1 as before."""
    calls = []
    real = weigh_attacks

    def spy(*args, **kw):
        calls.append((args, kw))
        return real(*args, **kw)
    monkeypatch.setattr(swapper, "weigh_attacks", spy)
    garret4 = max(w.reach for w in damage_windows(_read("gamedata/characters.xbr"), "garret4",
                                                  "attack_1"))
    for species, far in (("firedrake", 3.302), ("fire_shard", 1.530), ("guard_fire1", None)):
        calls.clear()
        _swap(species, fresh=True)
        (args, kw), = calls
        assert kw["x3_far"] == (None if far is None else pytest.approx(far, abs=5e-4)), species
        if far is None:
            continue
        x3, (new, *_, lift, _), (old, *_, was, _) = args[6], real(*args, **kw), real(*args, **{**kw, "x3_far": None})
        assert x3, species   # each over its build's D389 factor (AZ-804: fire_shard's at garret4's box x1.016)
        new = [None if b is None else b / (lift[0] if lift else 1.0) for b in new]
        old = [None if b is None else b / (was[0] if was else 1.0) for b in old]
        vanilla = args[3]   # a B held at D799's heavy-hit line (heavy_side) isn't free either
        base = [c.double_value if (c := vanilla.find_cell(col, MULTIPLIER, i)) is not None and c.type_code == 1
                else 1.0 for i, col in enumerate(vanilla.col_names())]
        free = [i for i, (a, b) in enumerate(zip(old, new)) if a is not None and BALANCE_FLOOR < min(a, b)
                and max(a, b) < BALANCE_CAP and (base[i] < LIGHT or base[i] * min(a, b) > LIGHT)]
        assert {i: new[i] / old[i] for i in free if x3 >> i & 1} == pytest.approx(
            {i: math.sqrt(garret4 / kw["x3_far"]) for i in free if x3 >> i & 1}) and len(free) > 3, species
        assert [new[i] for i in free if not x3 >> i & 1] == [old[i] for i in free if not x3 >> i & 1], species


@pytest.mark.parametrize("species, chains, factor, aim", [
    ("guard_air", (36.0, 36.0, 36.0), 1.93, SLOW_BONUS),
    ("kingkong", (8.6, 10.9, 11.2), 1.91, 1.0),
    ("fire_elemental", (12.6, 14.3, 14.3), 1.19, 1.0),
    ("keylord", None, None, None),
])
def test_an_own_body_deals_one_enemy_garret4s_damage_per_second_or_more_and_a_slow_attacker_1_25x_his(
        species, chains, factor, aim, monkeypatch):
    """AZ-614, D389 (Step 2.138; D334, D345, D350): the slow test paces
    each basic by the swing the combo plays, W19's chain point (0.2 s
    after its first hit, or 4 ticks after its box meets the target
    ahead), which the build writes as its Move end1, against garret4's
    first hit + 0.2 s (11.0, 9.25, 9.25 ticks): guard_air's basics chain
    at 36 ticks (Step 2.132's sitting: 36/37/36), slow; kingkong's at
    9-11 (9/11/12) and the fire elemental's at 13-14 (13/15/15), not,
    though their whole moves last 2.55x and 2.17x garret4's, which Step
    2.132's test weighed. A body's every weighed attack then takes the
    factor that makes its combo's damage per second on one target
    (combo_rate: basic1-3 a hit each to their chain points, then the
    finisher's, which the target recovers from in 3.75 s), at the
    multipliers it writes, 1.25x garret4's on a slow attacker (D350:
    guard_air x1.93 since Step 2.202b's AZ-804, x1.87 before; Step 2.132's x1.25 dealt 0.87x garret4's on a held
    sleeth) and garret4's on any body the balance leaves under his
    (D389: kingkong x1.91, the fire elemental x1.19, x1.89 and x1.11 before AZ-804, which the owner
    found "a bit weak", D334, at 0.92x on that sleeth); a body already
    at or above his (keylord, 1.78x) keeps its balance."""
    calls = []
    real = combo_rate

    def record(basics, finisher):
        calls.append((basics, finisher))
        return real(basics, finisher)
    monkeypatch.setattr(swapper, "combo_rate", record)
    told: list[str] = []
    game = _swap(species, mode="own", lines=told, fresh=True)
    log = " ".join(told)
    anims = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("attacks_anims")
    characters = bytes(game["characters.xbr"])
    garret4 = read_body(characters, "garret4")
    body = read_body(characters, XbrDocument.from_bytes(game["config.xbr"]).keyed_section(
        "critters_engine").find_cell("garret4", "body", None).string_value, dirs=(CENTRED_DIR,))

    def cell(col: str, row: str):
        return anims.find_cell(col, row, anims.col_names().index(col))
    written = []   # each basic's chain point as written, ticks into its move
    for col in CHAINED:
        owner, clip = source_clip(body, garret4, cell(col, "Anim").string_value)
        a0, a1, e1, rate = (cell(col, row).double_value for row in ("Anim start", "Anim end", "Move end1", "Rate"))
        start = move_window(anims, anims.col_names().index(col))[0]
        written.append(30 * ((e1 - a0) / (a1 - a0) - start) * owner.length(clip) / rate)
    assert chains is None or written == pytest.approx(chains, abs=0.5)
    clauses = re.findall(r"\((a slow attacker|garret4's damage on one enemy): x([\d.]+) the balance's, (D350|D389)\)",
                         log)
    assert clauses == ([] if factor is None else [
        ("a slow attacker", f"{factor:.2f}", "D350") if aim == SLOW_BONUS else
        ("garret4's damage on one enemy", f"{factor:.2f}", "D389")])
    (norm, *_), (own, finisher) = calls
    assert [t for *_, t in norm] == pytest.approx((11.0, 9.25, 9.25), abs=0.01)
    assert [t for *_, t in own] == pytest.approx(written, abs=1.0)   # W19 may keep a Move end1 a tick later
    k = factor or 1.0
    m = [cell(col, MULTIPLIER).double_value for col in CHAINED]
    end = statistics.fmean(cell(col, MULTIPLIER).double_value for col in FINISHERS)
    assert m + [end] == pytest.approx([b * k for b, _, _ in own] + [finisher[0] * k], rel=0.005)
    dealt = real([(b, h, t) for (_, h, t), b in zip(own, m)], (end, finisher[1])) / real(*calls[0])
    assert dealt == pytest.approx(aim, rel=0.005) if aim else dealt >= 1.0


def test_match_garret_gives_values_a_build_measures_as_garret4s():
    """D358 (Step 2.165b): the Player page's match-Garret values, each
    read at the sliders matched before it (Model size, then Attack reach
    at that size, then speed and damage at both), build the fire
    elemental as garret4, read from what the build wrote: its
    critters_engine scale draws it 2.002 m tall (his mesh top), its best
    melee hit is his basic swing's 2.76 m ahead (GARRET4_FORWARD), its
    basics chain at his mean 9.83 ticks (the chain points W19 writes at
    that speed, its own Move end1 where W19 keeps one) and its written
    Damage multipliers deal one target his damage per second (combo_rate
    at those chain points); garret4's own body matches at 1 throughout; a
    farmer, whose basics swing his own moves (Step 2.134a: their Move end1
    his, so the chain moves with the speed slider, not as W19's would),
    matches his damage at Attack speed 1 alone."""
    from azurkit.tools.characters._player_match import Match, garret_match

    def matched(species: str, **kw) -> Match:   # the engine's match on a staging of the image (sdk.match's own)
        return garret_match(ports.IsoStaging(ports._build().vanilla), species, **kw)
    assert matched("garret4") == Match(1.0, 1.0, 1.0)
    farmer = matched("town_male_farmer_1")
    assert (farmer.damage(1.0)[0], farmer.damage(2.0)[0]) == (pytest.approx(1.0), None)
    size = matched("fire_elemental").size
    reach = matched("fire_elemental", scale=size).reach
    match = matched("fire_elemental", scale=size, reach=reach)
    damage, _ = match.damage(match.speed)
    logic = AttackLogic()
    game = _swap("fire_elemental", model_scale=size, attack_reach=reach, attack_speed=match.speed,
                 attack_damage=damage, sounds="garret4", logic=logic)
    doc = XbrDocument.from_bytes(game["config.xbr"])
    anims = doc.keyed_section("attacks_anims")
    characters = bytes(game["characters.xbr"])
    garret4, body = read_body(characters, "garret4"), read_body(characters, "fire_elemental")

    def cell(col: str, row: str):
        return anims.find_cell(col, row, anims.col_names().index(col))

    def chain(col: str) -> float:   # ticks into the move, as written
        a0, a1, e1, rate = (cell(col, row).double_value for row in ("Anim start", "Anim end", "Move end1", "Rate"))
        owner, clip = source_clip(body, garret4, cell(col, "Anim").string_value)
        return 30 * ((e1 - a0) / (a1 - a0) - move_window(anims, anims.col_names().index(col))[0]) * (
            owner.length(clip) / rate)
    basics = [(cell(col, MULTIPLIER).double_value, swing.ticks(match.speed)[0], chain(col))
              for col, (swing,) in zip(CHAINED, logic.combo.basics)]
    ends = [(cell(col, MULTIPLIER).double_value, swing.ticks(match.speed)[0])
            for col, (swing,) in zip(FINISHERS, logic.combo.finishers) if swing is not None]
    dealt = combo_rate(basics, tuple(statistics.fmean(v) for v in zip(*ends))) / logic.combo.norm_rate
    drawn = doc.keyed_section("critters_engine").find_cell("garret4", "scale", None).double_value * height(
        characters, body)
    assert ([drawn, logic.reach], dealt) == (pytest.approx([height(characters, garret4), GARRET4_FORWARD]),
                                             pytest.approx(1.0, rel=1e-3))
    assert (logic.combo.norm_pace, statistics.fmean(t for *_, t in basics)) == (
        pytest.approx(9.83, abs=0.01), pytest.approx(logic.combo.norm_pace, abs=0.01))


def test_match_garret_dresses_the_body_on_the_build_s_packs_for_its_target_ram(image, monkeypatch):
    """Step 2.162i (D576): the match-Garret buttons (``sdk.match``) dress
    the body on the build's default.xbe, its packs on by default (its 42 MiB
    budget and both upper packs, so the build's size lines; at 256 MiB with
    qol_memory_upper256 too, Step 2.162l) with the build's ``ram`` passed
    on, so they measure every body the build would take."""
    from azurkit import sdk
    from azurkit.tools.characters import _player_match
    from azurkit.tools.characters import model_inspect as mi

    seen = []

    def dress(game, *_a, ram=64, **_k):
        xbe = bytes(game["default.xbe"])
        seen.append((mi.budget_of(xbe), mi.lines_ram(xbe, 256), ram))
        raise LookupError("dressed")
    monkeypatch.setattr(_player_match, "apply_player_model", dress)
    packs = {name: {} for name, pack in mods.PACKS.items() if pack.default_on}
    for ram in (64, 128, 256):
        with pytest.raises(LookupError):
            sdk.match({"iso": str(image), "packs": packs | ({mi.UPPER256_PACK: {}} if ram == 256 else {}),
                       "character": {"species": "fire_elemental", "ram": ram}})
    assert seen == [(42 * mi.MiB, 128, 64), (42 * mi.MiB, 128, 128), (42 * mi.MiB, 256, 256)]


def _hit_level(xbe: bytes, damage: int, multiplier: float, column: int, by_player: bool = True,
               own_multiplier: float | None = None) -> int:
    """The level the hit-level chooser 0x30BD0 of ``xbe`` gives a hit
    (L2, run to 0x30C26, before it reads the level): ``damage`` against a
    target whose ouch thresholds are a keylord's (5, 25; alive), its record
    carrying ``multiplier`` and as its attacker the player critter (else
    another), whose attack row's multiplier (+0x224) is ``own_multiplier``
    (by default the record's) and whose PlayerControl plays ``column``."""
    sim, base = Sim(xbe), 0x20000000
    sim.uc.mem_map(base, 0x10000)
    hit, holder, target, species, world, player, control, other = (base + 0x1000 * k for k in range(8))
    for at, fmt, value in ((hit + 4, "<I", player if by_player else other), (hit + 0xC, "<f", multiplier),
                           (holder + 0x20, "<I", target), (target + 0x178, "<I", species),
                           (target + 0x154, "<I", world), (target + 0x210, "<I", 1),
                           (species + 0x48, "<i", 5), (species + 0x4C, "<i", 25), (world + 0xBC, "<I", player),
                           (world + 0xC0, "<I", player), (player + 0x180, "<I", control),
                           (player + 0x224, "<f", multiplier if own_multiplier is None else own_multiplier),
                           (control + 0x134, "<i", column)):
        sim.uc.mem_write(at, struct.pack(fmt, value))
    sim.call(0x30BD0, regs={"eax": damage, "ecx": hit, "edx": holder}, args=(0,), until=0x30C26)
    return sim.reg("ebx")


def test_the_players_hit_in_a_column_garret4_hits_light_stuns_whatever_its_damage_multiplier():
    """AZ-525 (Step 2.104, X18): the hit-level chooser 0x30BD0 makes a hit
    whose Damage multiplier is under 1.0 level 1, a stun, and any other
    one its level by the damage (2 or 3 on a keylord, no stun), so own
    mode's balance, which lifts keylord's basic2 to 2.0 and guard_water's
    basic1 to 1.1667, and the damage slider at 2 (garret4's 0.5 to 1.0)
    left the player's basics stunning nothing and the combo stuck at
    basic1. With X18 the player's melee hit in a column whose vanilla
    multiplier is under 1.0 (basic1-3, right1, up1) is level 1 whatever
    its multiplier; its heavy columns, another attacker's hit and a hit
    whose multiplier isn't the attack row's keep the game's level. A
    build whose light columns stay under 1.0 (kingkong own) gets no X18."""
    vanilla = _xbe()
    keylord = bytes(_swap("keylord", sounds="garret4")["default.xbe"])
    columns = XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section(
        "attacks_anims").col_names()
    assert verify_trampoline_patch(keylord, LIGHT_HIT_HOOK) == "applied"
    assert round(struct.unpack_from("<f", keylord, resolve_va_to_file(keylord, trampoline_symbol_va(
        keylord, LIGHT_HIT_HOOK, "_player_model_light_columns",
        shim_source=LIGHT_HIT_SHIM.source_path())))[0]) == sum(
        1 << columns.index(c) for c in ("basic1", "basic2", "basic3", "right1", "up1"))
    for (damage, multiplier, column, kw), levels in {
            (10, 0.5, "basic1", ()): (1, 1),                                 # garret4's: the game's stun
            (24, 1.1667, "basic1", ()): (2, 1),                              # guard_water own's basic1
            (40, 2.0, "basic2", ()): (3, 1),                                 # keylord own's basic2
            (20, 1.0, "up1", ()): (2, 1),                                    # the damage slider at 2
            (50, 2.5, "finish3", ()): (3, 3),                                # a heavy column
            (24, 1.0, "basic1", (("by_player", False),)): (2, 2),            # another attacker's
            (24, 1.1667, "basic1", (("own_multiplier", 1.5),)): (2, 2),      # not the attack row's
    }.items():
        got = tuple(_hit_level(xbe, damage, multiplier, columns.index(column), **dict(kw))
                    for xbe in (vanilla, keylord))
        assert got == levels, (damage, multiplier, column, kw)
    assert verify_trampoline_patch(bytes(_swap("kingkong", sounds="garret4")["default.xbe"]),
                                   LIGHT_HIT_HOOK) == "original"


@pytest.mark.parametrize("kw, met, evened", [
    ({}, {"sweep1", "elemental2", "hose_attack_3", "left1", "left2", "back2", "down"},
     {"basic1": 0.4030, "sweep2": 1.3420, "back1": 1.7327}),
    ({"weapon": "farmers_hoe"}, {"sweep1", "sweep2", "sweep ledge", "jump attack", "left2", "back1", "back2"}, {}),
])
def test_the_balance_never_takes_a_swing_garret4_staggers_with_under_the_games_heavy_hit_line(kw, met, evened):
    """AZ-774, D799 (Step 2.201): the hit-level chooser 0x30BD0 makes a
    hit whose Damage multiplier is under 1.0 level 1, a light flinch (a
    0.30 s no-hit window, so a sweep's contacts land twice), and a 20-damage
    one of 1.0 or more level 2, a heavy one (2.55 s, one hit a swing). W14's
    weight took golem own's sweep1 to 0.7569 and golem with the hoe's sweep2
    to 0.9521 (sitting 2.197b: 20 + 20 where main's 21 once). Every column
    garret4 hits heavy (vanilla 1.0 or more) keeps a multiplier of 1.0 or
    more, the least the balance gave under it 1.0 exactly, and its hit
    stays heavy; a light column and a heavy one the balance leaves above 1.0
    keep their evened multipliers (golem own's basic1 0.4030, sweep2
    1.3420 since Step 2.202b's AZ-804; 0.3887, 1.5030 before)."""
    game = _swap("golem", **kw)
    built = bytes(game["default.xbe"])
    vanilla, anims = (XbrDocument.from_bytes(c).keyed_section("attacks_anims")
                      for c in (game.stored("config.xbr"), bytes(game["config.xbr"])))
    held, levels = set(), {}
    for i, col in enumerate(vanilla.col_names()):
        if col == "roll forward":
            continue
        his, cell = vanilla.find_cell(col, MULTIPLIER, i), anims.find_cell(col, MULTIPLIER, i)
        m = his.double_value if his is not None and his.type_code == 1 else 1.0
        w = _f32(cell.double_value)
        if col in evened:
            assert w == pytest.approx(evened[col], abs=5e-5), col
        if m < LIGHT:
            continue
        held |= {col} if w == LIGHT else set()
        if w not in levels:
            levels[w] = _hit_level(built, math.ceil(20 * w), w, i)
        assert w >= LIGHT and levels[w] >= 2, (col, w)
    assert held == met


@pytest.mark.parametrize("species, model_scale, late", [
    ("guard_water", 1.0, {}), ("keylord", 1.0, {}), ("keylord", 2.0, {}), ("balthazar", 1.0, {"left1": (13.90, 19.90)}),
    ("magmar", 1.0, {}), ("air_elemental", 1.0, {"right2": (30.0, 36.0)}),
    ("guard_air", 1.0, {col: (30.11, 36.0) for col in ("finish2", "right1", "left1")} | {"right2": (30.67, 36.0)}),
    ("sleeth_momma", 1.0, {"basic1": (21.20, 25.20), "right1": (25.90, 31.90), "left1": (31.80, 35.80)}),
    ("barnacle", 0.5, {"basic1": (9.07, 13.07), "basic2": (11.08, 15.08), "basic3": (11.0, 15.0)}),
    ("ice_shard", 1.0, {"basic3": (24.83, 28.83), "sweep1": (28.8, 32.8)})])
def test_an_own_bodys_attack_never_chains_before_it_touches_the_target_ahead(species, model_scale, late):
    """AZ-496 (Step 2.104, W19): the chain check 0x8D452 lets an A press
    start the next basic once the clip's fraction reaches the column's
    Move end1, and the next basic needs the target stunned, which a light
    hit holds 10-28 ticks (xemu sitting 2.103). An own body's basic1-3
    kept garret4's fractions of its own, longer clip, so guard_water's
    basic1 chained 53 ticks after its first hit and its stun was over.
    Own mode's basic1-3 (not a column X10 turns) chain 0.2 s (6 ticks)
    after the move's first damage tick, or keep their own chain when it
    comes after the hit and at most a tick later than that; Move start and
    Move end2, so a single press's whole move, stay the column's. AZ-495
    (Step 2.105): a box whose window opens before it reaches the target
    chained before its hit's stun showed (3 ticks after the hit; guard_air
    own's chain at 36-37 with its hit on the keylord ahead at 35-36), so
    a chain comes at least 4 ticks after the box first meets a keylord
    standing against the player dead ahead (``contact``): sleeth_momma's
    basic1 at 25.20; the others' are unchanged. X10's ring entries do
    the same at Rate 1: since Step 2.135 a body with two attack sets
    (rock_shard's, whose third and fourth clips chained 4 ticks after they
    met the target) gets no ring, and splinter's four, X3's boxes, chain
    6 ticks after their first damage. AZ-534 (Step 2.106): the
    contact is X13's box, lowered to the feet in a column it grounds
    (AZ-605, Step 2.132: filled, so guard_air's basics meet the target as
    their windows open, at 30-31 ticks, and chain 0.2 s after their first
    hit, 36, where they chained at 39.70-40.66 after a contact at
    35.70-36.66, the box's corner 1.27 m ahead), so keylord own x2's
    basic2 (its box 2.46-7.39 m up unlowered) meets the keylord at 8.25
    ticks, as xemu saw, and chains at its first hit's 15, not 18. AZ-495
    (Step 2.106): every other attack column but the roll kept garret4's
    Move end1 fraction, which on guard_air own let right1 and left1 chain
    into basic1 at 18 ticks, before their box reached the target at 36.66
    (sitting 2.75b's captures), so a column whose own chain comes before
    its move touches the target (its first damage tick, or that contact
    if later) chains as a basic does, and one already chaining at or
    after it keeps its own: guard_air's finish2, sweep1, right1, left1 and
    right2, balthazar's left1, air_elemental's right2 and sleeth_momma's right1 and
    left1 move, among others (sleeth's, evil_noreht's, the harvesters', the
    catalisks'). X10 turns
    such a column by its ring's chained mask: rock_shard's right1 and
    left1 (0x14007). AZ-537 (Step 2.118, D296): the player's move query
    keeps garret4's 0.5 m radius at every drawn scale, so a body drawn
    under x1 meets the target 0.5 m ahead, not 0.5 x D: barnacle own
    x0.5's basic1-3 chain 4 ticks after their boxes meet it (they kept
    their own chains against a target 0.25 m ahead). An own build's
    overlay columns (W23: the air elemental's gust) chain as its box
    arrives instead (Step 2.145, D414; test_player_variants.py). Step
    2.135: a column an X36 attack set plays in basic1-3 chains as the
    basics do (ice_shard's sweep1, attack_4 in its second set, 4 ticks
    after its box meets the target)."""
    thrown = set(overlay(species).columns) if overlay(species) is not None else set()
    vanilla = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    played = {a.column: a for a in attacks(vanilla, characters, species, model_scale=model_scale)}
    columns = list(played)
    chained = set(CHAINED) | {columns[c] for cols in attack_sets(columns, [a.clip for a in played.values()])[1:]
                              for c in cols[:3]}   # a set's basic slots (Step 2.135)
    engine = XbrDocument.from_bytes(vanilla).keyed_section("critters_engine")
    body, scale = (engine.find_cell(species, row) for row in ("body", "scale"))
    drawn = (scale.double_value if scale.type_code == 1 else 1.0) * model_scale
    anims, was = (XbrDocument.from_bytes(c).keyed_section("attacks_anims") for c in (
        _swap(species, sounds="garret4", model_scale=model_scale)["config.xbr"], vanilla))
    ticks = {}
    for i, col in enumerate(anims.col_names()):
        cells = [anims.find_cell(col, row, i) for row in (
            "Anim start", "Anim end", "Move end1", "Move start", "Move end2", "Rate")]
        attack = played[col]
        if col == "roll forward" or col in thrown or any(c is None or c.type_code != 1 for c in cells) or not (
                attack.windows or attack.x3):
            continue
        a0, a1, end1, start, end2, rate = (c.double_value for c in cells)
        assert (start, end2) == tuple(was.find_cell(col, row, i).double_value for row in ("Move start", "Move end2"))
        window = move_window(anims, i)
        hit = 30 * windup(rate, attack.length, window, None if attack.x3 else attack.windows)
        met = None if attack.x3 else contact(characters, body.string_value, attack.clip, drawn, attack.length, window,
                                             fill=attack.ground)
        touch = hit if met is None else max(hit, 30 * (met - window[0] * attack.length) / rate)

        def at(e1: float) -> float:
            return 30 * ((e1 - a0) / (a1 - a0) - window[0]) * attack.length / rate
        chain, kept = at(end1), at(was.find_cell(col, "Move end1", i).double_value)
        if col not in chained and kept >= touch - 1e-9:
            assert end1 == was.find_cell(col, "Move end1", i).double_value, col
            continue
        assert hit < chain <= max(hit + 30 * CHAIN_AFTER_HIT, touch + 30 * STUN_LAG) + (col in chained) + 1e-9, (
            col, hit, chain)
        assert met is None or chain >= touch + 30 * STUN_LAG - 1e-9, (col, touch, chain)
        if col not in chained or touch + 30 * STUN_LAG > hit + 30 * CHAIN_AFTER_HIT:
            ticks[col] = (round(touch, 2), round(chain, 2))
    assert ticks == late
    _, _, _, _, ring, chained, terms = _ring(bytes(_swap("splinter", sounds="garret4")["default.xbe"]))
    assert [tuple(round(v, 4) for v in terms[c]) for c in ring] == [(0.2, 0.1034)] * 4
    assert chained == 0x7


def test_an_own_body_whose_basics_reach_past_3_m_chains_on_a_stunned_target_out_to_its_reach():
    """AZ-523's 3 m rule (Step 2.105, X21): the combo's next basic needs a
    stunned target the transition search's finder 0x7EBB0 (the CALL at
    0x7EF80) returns, and it takes none past 3.0 m distance less radius
    (the 0x1A25BC it reads seven times), so golem own, whose hit stunned
    f6's blaze sentinel 3.6 m out, replayed basic1 in 12 of 12 presses
    (sitting 2.104). X21 (L2, golem own's build, 0x7EBB0 stubbed to find
    a target at 3.6 m or 2.5 m by the radius its 0x7EDA4 operand reads):
    the seven operands read the shim's radius (3.0 at rest); the
    player's search in basic1-3 (its PlayerControl's +0x134) that finds
    nothing within 3 m searches again at the build's reach (golem's
    basics 6.59 m) and keeps a stunned (0x8000) or frozen (0x10000)
    target there, else the first result; the radius is 3.0 again after.
    A target within 3 m, a fresh press (-1: rows 16 and 32 keep 3 m), the
    finish and another critter take one search. RET 0xC, EBX, ESI, EDI
    and EBP kept. keylord own (its basics under 3 m) and vanilla keep the
    CALL and the 0x1A25BC reads."""
    vanilla = _xbe()
    built = bytes(_swap("golem", sounds="garret4")["default.xbe"])
    assert l1.check(vanilla, built) == []
    radius = trampoline_symbol_va(built, SEARCH_HOOK, SEARCH_RADIUS_SYMBOL, shim_source=SEARCH_SHIM.source_path())
    reach = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, SEARCH_HOOK, "_player_model_search_reach", shim_source=SEARCH_SHIM.source_path())))[0]
    assert round(reach, 2) == 6.59
    assert all(struct.unpack_from("<I", built, va_to_file(site.va) + 2)[0] == radius for site in SEARCH_SITES)
    at = va_to_file(0x7EF80)
    entry = 0x7EF85 + struct.unpack_from("<i", built, at + 1)[0]
    base = 0x20000000
    critter, species, found, control = base, base + 0x1000, base + 0x2000, base + 0x2400

    def search(*, player: bool = True, far: float = 3.6, flags: int = 0x8000,
               column: int = 2) -> tuple[list[float], list[int]]:
        sim = Sim(built)
        sim.uc.mem_map(base, 0x3000)
        sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
        sim.uc.mem_write(critter + 0x180, struct.pack("<I", control))
        sim.uc.mem_write(control + 0x134, struct.pack("<i", column))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", 0x24 if player else 0x04))
        seen = []

        def find(uc, addr, size, _):   # attack_target_find: __stdcall(12), RET 0xC
            esp = sim.reg("esp")
            ret, who, _facing, out = struct.unpack("<4I", uc.mem_read(esp, 16))
            live = sim.f32(struct.unpack("<I", uc.mem_read(0x7EDA4 + 2, 4))[0])
            seen.append(live)
            hit = far <= live
            uc.mem_write(out, struct.pack("<6I", int(hit), len(seen), 0, 0, 0, 0)
                         + struct.pack("<fI", far if hit else 0.0, flags if hit else 0) + bytes(0x18))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 16)

        sim.uc.hook_add(UC_HOOK_CODE, find, begin=0x7EBB0, end=0x7EBB0)
        kept = {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
        sim.call(entry, regs=kept, args=(critter, 0, found), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0xC
        assert {r: sim.reg(r) for r in kept} == kept
        assert sim.f32(radius) == 3.0
        return [round(r, 2) for r in seen], list(struct.unpack("<8I", sim.uc.mem_read(found, 32)))

    seen, out = search()                                 # stunned 3.6 m out: chains
    assert (seen, out[0], out[1], out[7]) == ([3.0, 6.59], 1, 2, 0x8000)
    assert search(flags=0x10000)[1][7] == 0x10000         # frozen
    seen, out = search(flags=0)                            # not stunned: the game's empty result
    assert (seen, out[:2]) == ([3.0, 6.59], [0, 1])
    for kw in ({"far": 2.5}, {"column": -1}, {"column": 3}, {"player": False}):
        seen, out = search(**kw)
        assert (seen, out[0]) == ([3.0], int(kw.get("far", 3.6) <= 3.0)), kw
    for xbe in (vanilla, bytes(_swap("keylord", sounds="garret4")["default.xbe"])):
        assert verify_trampoline_patch(xbe, SEARCH_HOOK) == "original"
        assert all(xbe[va_to_file(site.va):va_to_file(site.va) + 6] == site.original for site in SEARCH_SITES)


def test_a_player_models_attacks_list_each_columns_damage_window_reach_and_fill_flag():
    """Step 2.61's evaluator (Step 2.70): a damage window is where a clip's
    m_damage or m_damage2 is on (active at least 0.5, length above 0, as
    the damage pass reads it), its box the marker's at the species' scale
    (garret4's attack_1: 2.77 m ahead, -0.13 to 1.26 m); X13 fills every
    column's box but the roll's, melee or ranged (Step 2.132, AZ-605:
    Balthazar's 6.96 m beam too); a column X3 serves (Step 2.64: its clip
    has no damage window, Balthazar's attack_2, every attack of flicken)
    hits with garret4's box, and so does a column whose own box can't
    hit a target on the ground (own mode's reach test, Step 2.69): a box
    reaching under 0.6 m (splinter's 0.33-0.43 m), while a short box seen
    hitting keeps its own (D222 amended: overlord's 0.97 m, which hit at
    0.9 m in sitting q281, and shard's 0.78 m, which dealt damage in p8).
    The fill brings every box ahead to the feet and the floor, so a box
    high or far no longer fails the test: spideyzar's ten clips all ring
    (its sweep ledge's 3.01 m attack_6, its 26.5 m jump), none X3 (its
    jump attack's 6.2 m attack_2 staying 1.29 m up keeps its own), and
    sized to garret4's height (Step 2.68: judged at the scale the build
    writes) sleeth x3.25 keeps its own 7.2 m box, in the build too, where
    splinter x6.19 reaches 2.69 m. garret4's build writes nothing: it
    lists the table's own Anims, none filled at x1, all but the roll
    drawn x2 (D347)."""
    config = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    garret4 = damage_windows(characters, "garret4", "attack_1")
    assert [(w.marker, round(w.on, 3), round(w.off, 3), round(w.reach, 2), round(w.low[2], 2),
             round(w.high[2], 2)) for w in garret4] == [("m_damage", 0.25, 0.327, 2.77, -0.13, 1.26)]
    for species, x3, first in (
            ("keylord", set(), ("attack_1", 0.23, 0.527, 1.74, 1.11, 2.31)),   # its boxes at its ticks from the
            # body (AZ-766, Step 2.197b): 1.81 m and 2.42 high its clip's
            ("balthazar", {"attack_2"}, ("attack_1", 0.463, 0.86, 1.33, 1.23, 1.77)),
            ("flicken", {"ouch_1"}, None),
            ("overlord", set(), ("attack_1", 0.397, 0.727, 0.97, 1.57, 3.07)),
            ("shard", set(), ("attack", 0.0, 0.933, 0.78, -0.25, 0.25)),
            ("splinter", {"attack", "eat", "eat_2", "eat_3"}, ("attack", 0.597, 1.927, 0.33, -0.02, 0.2)),
            ("spideyzar", set(), None)):
        rows = attacks(config, characters, species)
        assert len(rows) == 24 and {r.column for r in rows if not r.ground} == {"roll forward"}, species
        assert {r.column for r in rows if r.x3} == {
            r.column for r in rows if r.clip in x3 and r.column != "roll forward"}, species
        w = rows[0].windows[0] if first else None
        assert first is None or (rows[0].clip, round(w.on, 3), round(w.off, 3), round(w.reach, 2),
                                 round(w.low[2], 2), round(w.high[2], 2)) == first
    spideyzar = {r.column: r for r in attacks(config, characters, "spideyzar")}
    assert spideyzar["sweep ledge"].clip == "attack_6" and min(w.low[2] for w in spideyzar["jump attack"].windows) > 1
    sized = {sp: {r.column for r in attacks(config, characters, sp, size="garret4") if r.x3}
             for sp in ("splinter", "sleeth")}
    assert sized == {"splinter": set(), "sleeth": set()}
    hook = slice(va_to_file(DAMAGE_MARKER.va), va_to_file(DAMAGE_MARKER.va) + 5)
    assert bytes(_swap("sleeth", size="garret4")["default.xbe"])[hook] == _xbe()[hook]
    anims = XbrDocument.from_bytes(config).keyed_section("attacks_anims")
    assert [(r.column, r.clip, r.ground) for r in attacks(config, characters, "garret4")] == [
        (col, anims.find_cell(col, "Anim", i).string_value, False)
        for i, col in enumerate(anims.col_names())]
    assert {r.column for r in attacks(config, characters, "garret4", model_scale=2.0) if not r.ground} == {
        "roll forward"}


def test_a_swapped_bodys_attack_sets_hold_every_attack_it_plays_four_to_a_set():
    """D325 (Step 2.135, its census): WHITE cycles a swapped body's attack
    sets. Set 0 is the game's combo as W3 picks it (basic1, basic2, basic3,
    finish); every other distinct pick, by its first column in table order
    and the roll left out, goes four to a set onto basic1, basic2, basic3
    and the finisher, a short last set repeating its own, so every attack
    the body plays is in some set (finish2's and finish3's in set 0's):
    Balthazar one set, the shards two (sweep1's attack_4), spideyzar three
    (its whirlwind in finish, where W3's plan moves it), a farmer six
    (garret4's 23 baked clips); a body with no clips none.
    Each set's line names "Attack set k/n" and its clips, dirs stripped,
    repeats dropped, whole names wrapped at 40 characters (Step 2.153,
    D441: a farmer's)."""
    config = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    for species, want, line in (
            ("balthazar", [[0, 1, 2, 3]], "Attack set 1/1\nattack_1 attack_2 attack_3"),
            ("ice_shard", [[0, 1, 2, 3], [6, 6, 6, 6]], "Attack set 2/2\nattack_4"),
            ("spideyzar", [[0, 1, 2, 3], [6, 7, 8, 9], [10, 11, 10, 11]], "Attack set 3/3\ndeathbeam jump"),
            ("town_male_farmer_1", [[0, 1, 2, 3], [6, 7, 8, 9], [10, 11, 12, 13], [14, 15, 16, 17], [18, 19, 21, 22],
                                    [23, 23, 23, 23]], "Attack set 6/6\nattack_17")):
        rows = attacks(config, characters, species)
        columns, picks = [r.column for r in rows], [r.clip for r in rows]
        sets = attack_sets(columns, picks)
        assert sets == want, species
        assert {picks[c] for cols in sets for c in cols + [4, 5]} == {
            p for col, p in zip(columns, picks) if col != "roll forward"}, species
        assert set_lines(picks, sets)[-1] == line, species
    rows = attacks(config, characters, "town_male_farmer_3")
    picks = [r.clip for r in rows]
    assert set_lines(picks, attack_sets([r.column for r in rows], picks))[1] == (
        "Attack set 2/6\n360_basic_attack 360_sweep 360_ledge\nelemental_attack")
    assert attack_sets([r.column for r in attacks(config, characters, "keylord")], []) == []


def test_player_models_lists_each_builds_statuses_and_their_counts_in_that_mode_and_size():
    """Steps 2.74 and 2.75 (P8; Modkit's ``player-models --mode --size``,
    whose list the Characters tab shows, ``sdk.pickers``): each species'
    status as a build in that gameplay mode and size, from a sitting of
    that build (``MODE_GRADES``) or of the partner whose ISO it builds
    there; a mode and size no sitting graded is "unseen" (D242): garret4's
    exact on the bodies sittings graded there and their shares (kingkong
    unseen there, water_tentacle1 green, yellow in own body; flicken green,
    with flicken of peril, which builds flicken's ISO); garret4's height on
    sitting 2.75b S4's nine (water_tentacle1 and kingkong green there). The
    counts: garret4's exact 19 green, 3 yellow, 73 red (the 73 items,
    untested), 83 unseen, 6 refused; own body 60, 44, 73, 1, 6; own body at
    garret4's height 7, 3, 73, 95, 6. A species' attacks in a mode and size
    (``attacks``) are that build's: keylord's in garret4's exact aren't own
    body's, and splinter's X3 columns at garret4's height aren't its own
    size's."""
    config, bodies = _read("gamedata/config.xbr"), _read("gamedata/characters.xbr")
    listed = {mode: player_models(config, bodies, mode) for mode in MODES} | {
        "sized": player_models(config, bodies, "own", "garret4")}
    assert {(key, m.species): m.status for key, models in listed.items() for m in models
            if m.species in ("flicken", "flicken of peril", "water_tentacle1", "kingkong")} == {
        **{(mode, sp): "green" for mode in ("garret4", "own") for sp in ("flicken", "flicken of peril")},
        ("garret4", "kingkong"): "unseen", ("own", "kingkong"): "yellow",
        ("garret4", "water_tentacle1"): "green", ("own", "water_tentacle1"): "yellow",
        ("sized", "flicken"): "unseen", ("sized", "flicken of peril"): "unseen",
        ("sized", "water_tentacle1"): "green", ("sized", "kingkong"): "green"}
    assert {key: Counter(m.status for m in models) for key, models in listed.items()} == {
        "garret4": {"green": 19, "yellow": 3, "red": 73, "unseen": 83, "refused": 6},
        "own": {"green": 60, "yellow": 44, "red": 73, "unseen": 1, "refused": 6},
        "sized": {"green": 7, "yellow": 3, "red": 73, "unseen": 95, "refused": 6}}
    assert {key: sum(m.note == "untested" for m in models) for key, models in listed.items()} == dict.fromkeys(
        listed, 73)
    assert attacks(config, bodies, "keylord") != attacks(config, bodies, "keylord", "garret4")
    assert [r.x3 for r in attacks(config, bodies, "splinter", "own", "garret4")] != [
        r.x3 for r in attacks(config, bodies, "splinter")]


_GARRET4_SOUNDS = "loc/english/speech/azurik_speech"


@pytest.mark.parametrize("species, sound_dir, own, binds, counts, xbe", [
    ("keylord", "fx/sound/keylord", ("attack", "hurt", "death", "idle", "roll", "hit"),
     {"ouch_1": "ouch_1", "ouch_1b": "ouch_1", "die_3": "die", "idle_6": "idle",
      "basic1": "attack_1", "basic2": "attack_2", "touchdown": None, "climb_up": None,
      "victory_1": None, "roll forward": "attack_1"},
     (41, 24, "fx/sound/Overlord/overlord_ouch", None, 46, 0), {}),
    ("flicken", "fx/sound/flicken", ("hurt", "death", "hit"),
     {"ouch_1": "ouch_1", "ouch_2": "ouch", "die_1": "die", "basic1": "", "jump attack": "",
      "idle": None, "roll forward": None},
     (33, 0, None, None, 46, 0), {}),
    ("spideyzar", "fx/sound/balthazar_spider", ("attack", "hurt", "taunt", "jump", "roll", "hit"),
     {"jump": None, "jump_standing": None, "victory_6": "laugh", "ouch_3": "ouch",
      "elemental1": "attack_2", "die": None, "roll forward": "attack_1"},
     (36, 24, None, None, 46, 0),
     {"jump": "fx/sound/balthazar_spider/jump", "flap": "fx/sound/balthazar_spider/jump"}),
    ("overlord and golem", "fx/sound/golem_ol", ("attack", "hurt", "death", "footstep", "roll", "hit"),
     {"walk": "walk", "run": None, "ouch_1r": "ouch_1", "roll forward": "walk", "basic2": "attack_2"},
     (35, 24, "fx/sound/Golem/golem_ouch", None, 46, 0),
     {"walkl": "fx/sound/golem_ol/foot_left", "walkr": "fx/sound/golem_ol/foot_right"}),
    ("firefly", "fx/sound/firefly", ("ambient", "hit"), {"ouch_1": None, "basic1": None},
     (0, 0, None, "fx/sound/Firefly/firefly_fly_loop", 46, 0), {}),
    ("town_male_6", "loc/english/speech/male_6", ("attack", "hurt", "roll"),
     {"ouch_1": "talk_d", "ouch_2": "talk_o", "ouch_3": "talk_k", "ouch_1r": "talk_d",
      "basic1": "talk_q", "basic2": "talk_p", "die": None, "victory_1": None, "roll forward": "talk_q"},
     (30, 24, None, None, 0, 7), {}),
    ("balthazar", "fx/sound/balthazar_airship", ("attack", "hurt", "death", "taunt", "roll", "hit"),
     {"ouch_1": "ouch_1", "die": "die", "victory_1": "laugh", "idle": None, "basic1": "attack_1",
      "roll forward": "attack_1"},
     (40, 24, None, None, 46, 0),
     {"ouch": "fx/sound/balthazar_airship/ouch_1", "fallingdeath": "fx/sound/balthazar_airship/die"}),
])
def test_each_model_sound_role_is_its_own_species_or_garret4s(species, sound_dir, own, binds,
                                                                 counts, xbe):
    """D224, D231-D233 (Step 2.71): a swapped body's sounds are its own
    species' per role, read from the build's own Anim cells: hurt, death,
    idle and taunt by the slot's name or the species' alias for the role
    (ouch, die, laugh), jump only by its own name, each attack column the
    wave of its clip or the species' attack sounds in turn, and the
    townspeople's shortest speech lines as hurt and attack sounds. A role
    it has none for keeps Garret's (no bind: None), and an attack whose
    clip would bind Garret's ouch_1 binds nothing (AZ-392, flicken).
    counts: the binds, and Step 2.72's cells (the columns whose shouts
    give way, ouch, ambient, the hit rows, the speech lines). A build
    installs X14 at both hooks exactly when the map binds a slot.
    Step 2.72 (the option, own by default): the build empties the shout
    cells of those columns (W9; the roll's grunt too where the roll has a
    sound of its own, the overlord's golem: golem's rolls on garret4's baked
    roll since Step 2.134a), points garret4's critters_sounds ouch,
    ambient and hit rows at the species' (W10, W11) and changes no other
    cell, and X15 points the XBE's jump path (spideyzar's jump, which
    no jump slot binds again) or walkl and walkr paths (the golem
    family's feet) at the species' wave carved into the image; with
    sounds garret4 none of that, and no X14.  D328 (Step 2.141): a roll
    with no sound of its own takes its first attack column's (keylord's
    and spideyzar's attack_1, town_male_6's talk_q), so its grunt goes
    too; golem keeps its walk, and flicken, whose attacks bind none
    (AZ-392), and firefly keep Garret's.  D447, D448 (Step 2.153): X15
    points Balthazar's fall damage (0x8ADC2) and falling death (0x8BF61)
    at his own ouch_1 and die."""
    game, garret = _swap(species), _swap(species, sounds="garret4")
    roles = sound_roles({"config.xbr": game["config.xbr"], "fx.xbr": game.stored("fx.xbr"),   # its own waves, not
                         "english.xbr": game["english.xbr"]}, species)   # the kit's whoosh the build adds (Step 2.159a)
    columns = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section(
        "attacks_anims").col_names()
    vanilla, built = _xbe(), bytes(game["default.xbe"])

    def slot(name: str) -> int:
        return BASE_CLIPS.index(name) if name in BASE_CLIPS else ATTACK_SLOT + columns.index(name)

    assert (roles.sound_dir, roles.own) == (sound_dir, own)
    assert {name: roles.binds.get(slot(name)) for name in binds} == binds
    assert (len(roles.binds), len(roles.shouts), roles.ouch, roles.ambient, len(roles.hit_rows),
            len(roles.speech)) == counts
    for va in (BASE_HOOK_VA, ATTACK_HOOK_VA):
        at = va_to_file(va)
        assert (built[at:at + 5] != vanilla[at:at + 5]) == bool(roles.binds), hex(va)
        assert garret["default.xbe"][at:at + 5] == vanilla[at:at + 5], hex(va)
    before, after = _cells(bytes(garret["config.xbr"])), _cells(bytes(game["config.xbr"]))
    sounds = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("critters_sounds")
    player = f"{sounds.col_names().index('garret4')}:garret4"
    mine = {row: value for row, value in (("ouch", roles.ouch), ("ambient", roles.ambient))
            if value} | roles.hit_rows
    assert {key: after[key] for key in before if before[key] != after[key]} == {
        **{("attacks_anims", f"{columns.index(col)}:{col}", row): (0, None, None)
           for col in roles.shouts for row in SHOUT_ROWS
           if before["attacks_anims", f"{columns.index(col)}:{col}", row][0]},
        **{("critters_sounds", player, row): (2, None, value) for row, value in mine.items()
           if before["critters_sounds", player, row] != (2, None, value)}}
    assert roles.xbe == xbe
    for site in XBE_SOUND_SITES:
        at = va_to_file(site.va)
        assert garret["default.xbe"][at:at + 5] == site.original
        if site.sound in xbe:
            assert built[at] == site.original[0], hex(site.va)
            path = resolve_va_to_file(built, struct.unpack_from("<I", built, at + 1)[0])
            assert built[path:built.index(b"\0", path)].decode() == xbe[site.sound], hex(site.va)
        else:
            assert built[at:at + 5] == site.original, hex(site.va)
    if xbe:
        assert l1.check(vanilla, built) == []


def test_x14_binds_the_players_slots_from_the_models_sound_dir_and_every_other_as_before():
    """X14 (Step 2.71; D231, D232): 0x4B680 binds <S+8>/<clip> to a slot
    of the species record S (EDI), so the swapped player, still garret4,
    bound Garret's azurik_speech everywhere. Through each of its hooks
    (0x4B93C, the base clips; 0x7E3DD, the attack slots) X14 binds every
    slot its table names for the player's species (flag 0x20 in S+0x64)
    from the model's dir, the table's name in place of the clip (an empty
    one for flicken's attacks); a slot it doesn't name (a level's, past
    the table) and every slot of another species bind the clip from S+8
    unchanged. S+8 and EDI are put back and the stack is popped as
    0x4B680 pops it (RET 8); L1 is clean."""
    vanilla = _xbe()
    slots = range(ATTACK_SLOT + 28)
    config = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    for species in ("keylord", "flicken"):
        game = _swap(species)
        columns = XbrDocument.from_bytes(config).keyed_section("attacks_anims").col_names()
        played = dict(zip(columns, [a.clip for a in attacks(config, characters, species)]))   # keylord's c/0: attack_1
        built, roles = bytes(game["default.xbe"]), sound_roles(game, species, played if species == "keylord" else None)
        assert l1.check(vanilla, built) == []
        for va in (BASE_HOOK_VA, ATTACK_HOOK_VA):
            target = va + 5 + struct.unpack_from("<i", built, va_to_file(va) + 1)[0]
            sim, record = Sim(built), 0x20000000
            folder, clip = record + 0x100, record + 0x200
            sim.uc.mem_map(record, 0x1000)
            sim.uc.mem_write(folder, _GARRET4_SOUNDS.encode() + b"\0")
            sim.uc.mem_write(clip, b"clip\0")
            sim.uc.mem_write(record + 8, struct.pack("<I", folder))
            seen = []

            def bind(uc, addr, size, _):   # 0x4B680: __stdcall(8), EDI = S
                esp, edi = sim.reg("esp"), sim.reg("edi")
                seen.append((edi, sim.cstr(sim.u32(edi + 8)), sim.u32(esp + 4),
                             sim.cstr(sim.u32(esp + 8))))
                uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
                uc.reg_write(UC_X86_REG_ESP, esp + 12)

            sim.uc.hook_add(UC_HOOK_CODE, bind, begin=0x4B680, end=0x4B680)
            got, want = [], []
            for flags in (0x24, 0x04):
                sim.uc.mem_write(record + 0x64, struct.pack("<I", flags))
                for k in slots:
                    seen.clear()
                    sim.call(target, regs={"edi": record}, args=(k, clip), until=l2._RETURN)
                    got.append((*seen, sim.reg("esp"), sim.reg("edi"), sim.u32(record + 8)))
                    mine = flags & 0x20 and k in roles.binds
                    want.append(((record, roles.sound_dir if mine else _GARRET4_SOUNDS, k,
                                  roles.binds[k] if mine else "clip"),
                                 l2._STACK_TOP - 0x100, record, folder))
            assert got == want, (species, hex(va))


def test_a_swapped_body_s_air_armor_wings_restart_their_stroke_on_each_flap():
    """Step 2.77: the air armor's wings (fx_jump1-3) restart their stroke
    only when their fx transform m_jump, bound by name to the wearer's
    body marker m_jump, pulses its z: garret4's superjump, which wing_flap
    asks for on each flap, keys it 5 then 0. No other body has the
    marker, so the bind (the critter bind interface's slot 1, 0x44270,
    looking it up with the CALL 0xCA1D0 at 0x44355) found nothing and the
    wings held their end pose. Its build hooks that CALL and slot 2's
    (0x44370) CALL 0xCCDF0 at 0x44389 (L1 well formed): for the player's
    species (flag 0x20, S+0x64) a missing m_jump binds to 0xC000, which
    slot 2 poses as garret4's (x, -4, z), z 5 on the first evaluation
    that sees a new nonzero flap count (PlayerControl+0xD8) and 0 after,
    x his superjump's 2 while anim 17 plays (critter+0x200), his jumps'
    1 in 15 and 16 and 0 in every other (Step 2.134b: held at 2, the
    wings stuck in the stroke's raised end pose 4.27 s after a flap);
    other names, species and found nodes bind and pose as before, and
    the 4 bytes it keeps the count in are one span of the build's shim
    data (AZ-300)."""
    vanilla = _xbe()
    built = bytes(_swap("flicken")["default.xbe"])
    assert l1.check(vanilla, built) == []
    sim, base = Sim(built), 0x20000000
    this, species, anim, body, name, xf, control, markers = (base + k * 0x400 for k in range(8))
    sim.uc.mem_map(base, 0x2000 * 4)
    sim.uc.mem_write(this + 8, struct.pack("<3I", species, anim, control))   # critter+0x178..
    sim.uc.mem_write(anim, struct.pack("<I", body))
    sim.uc.mem_write(anim + 0xC, struct.pack("<I", markers))
    sim.uc.mem_write(markers, struct.pack("<I3f4f3f", 0, 0.5, 0.25, 2.0, 0, 0, 0, 1, 1, 1, 1))

    def bind(flags: int, node: bytes, has_it: bool = False) -> int:
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(name, node + b"\0")
        sim.uc.mem_write(body + 0x18, struct.pack("<II", int(has_it), 0x64))   # 1 marker, its record:
        sim.uc.mem_write(body + 0x84, struct.pack("<i", name - (body + 0x84)))  # a self-relative name
        return sim.call(0x44270, regs={"ecx": this}, args=(name,))

    def pose(index: int, flaps: int | None = None, playing: int = 17) -> tuple:
        sim.uc.mem_write(this + 0x90, struct.pack("<I", playing))   # critter+0x200: the anim index
        sim.uc.mem_write(this + 0x10, struct.pack("<I", 0 if flaps is None else control))
        sim.uc.mem_write(control + 0xD8, struct.pack("<I", flaps or 0))
        sim.uc.mem_write(xf, b"\xAA" * 0x70)
        sim.call(0x44370, regs={"ecx": this}, args=(index, xf))
        return (struct.unpack("<3f", sim.uc.mem_read(xf + 0x50, 12)),
                struct.unpack("<4f", sim.uc.mem_read(xf + 0x40, 16)),
                struct.unpack("<3f", sim.uc.mem_read(xf + 0x5C, 12)),
                tuple(sim.uc.mem_read(xf + 0x68, 2)))

    assert bind(0x24, b"m_jump") == 0xC000
    assert [bind(0x04, b"m_jump"), bind(0x24, b"m_jumps"), bind(0x24, b"m_hit")] == [0, 0, 0]
    assert bind(0x24, b"m_jump", has_it=True) == 0x8000            # the body's own marker 0
    written: set[int] = set()
    sim.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, access, va, size, value, _:
                    written.update(range(va, va + size)))
    rest = ((0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0), (1, 0))
    assert [pose(0xC000, n) for n in (0, 1, 1, 2, 0, 1, None)] == [
        ((2.0, -4.0, z), *rest) for z in (0.0, 5.0, 0.0, 5.0, 0.0, 5.0, 0.0)]
    assert [pose(0xC000, 3, playing)[0] for playing in (17, 15, 16, 9, 1, 0, 21)] == [   # x: garret4's in that anim
        (x, -4.0, z) for x, z in ((2.0, 5.0), (1.0, 0.0), (1.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0))]
    assert pose(0x8000, 1) == ((0.5, 0.25, 2.0), *rest)              # a found node: 0xCCDF0
    shims = next(s for s in parse_xbe_sections(built)[1] if s["name"] == "SHIMS")
    kept = {va for va in written if shims["vaddr"] <= va < shims["vaddr"] + shims["vsize"]}
    assert kept in [set(range(lo, hi)) for lo, hi in shim_data(built)]


def test_a_swapped_body_s_armor_pieces_ride_its_bones_from_where_w15_puts_them():
    """AZ-447/AZ-448 (Step 2.118, D294): the armors' pieces bind by name to
    garret4's ten armor nodes, which no other body has but m_root and
    m_waist, so on a swapped body each stayed at W15's fixed point in the
    model whatever the clip did (keylord's shoulder pieces out while his
    arms hang), and guard_air's own m_root bound its bubble at garret4's
    size. Through the game's own fx bind (0x62A20, the critter bind
    interface's slot 1 at 0x44270) and one fx frame (0x62C40: slot 2 at
    0x44370, then 0x68DE0 into each transform) on keylord own's build:
    for the player each armor name binds to X16's virtual node 0xC000 | n
    of the build's table (its role-mapped bone: m_chest his spine_2, the
    wrists his arm_2s), m_jump to 0xC000 and a node the body has as
    before; at the bind pose each piece's local is the one the game
    builds from W15's frame, and with the bones posed it is that frame
    times its own bone's motion (mode 6, the matrix given), its rotate
    attributes saying the same turn (the shoulder pads' links read them).
    m_jump poses (0, -4, 0) (anim 0 plays); another critter binds none of them,
    nor (Step 2.134b) the m_root W27 grew on keylord when it wears keylord;
    the x87 stack is as it was."""
    import numpy as np

    game = _swap("keylord")
    built, characters = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    sim, base = Sim(built), 0x20000000
    sim.uc.mem_map(base, 0x200000)
    table_va = trampoline_symbol_va(built, WINGS_POSE, "_player_model_wings_armor",
                                    shim_source=WINGS_SHIM.source_path())
    count = sim.u32(table_va)
    table = [(sim.cstr(table_va + 4 + 84 * k), sim.u32(table_va + 20 + 84 * k)) for k in range(count)]
    bones = read_body(characters, "keylord").bones
    assert {name: bones[b][0] for name, b in table} == {
        "m_root": "root_joint", "m_chest": "spine_2", "m_waist": "spine_2", "m_skull": "head",
        "m_shoulderLeft": "left_arm_1", "m_shoulderRight": "right_arm_1", "m_wristLeft": "left_arm_2",
        "m_wristRight": "right_arm_2", "m_ankleLeft": "left_leg_2", "m_ankleRight": "right_leg_2"}
    frames = _armor_frames(bytes(game["fx.xbr"]))
    jump = {"t": (2.0, -4.0, 0.0), "r": (0.0, 0.0, 0.0), "s": (1.0, 1.0, 1.0), "order": 0}
    nodes = [(name, frames[name]) for name, _ in table] + [("m_jump", jump), ("m_feet", jump), ("x_none", jump)]
    species, iface, anim, binder, graph, lists = (base + 0x100 * k for k in range(1, 7))
    body_at, runtime, markers, pairs, xforms = base + 0x100000, base + 0x40000, base + 0x60000, base + 0x70000, base + 0x80000
    off, size = _clip(characters, "characters/keylord")
    sim.uc.mem_write(body_at, characters[off:off + size])
    sim.uc.mem_write(iface, struct.pack("<I4xIII", 0x19FBCC, species, anim, 0))   # its vtable, as the critter's
    sim.uc.mem_write(anim, struct.pack("<I4xII", body_at, runtime, markers))
    sim.uc.mem_write(binder, struct.pack("<I", iface + 4))
    sim.uc.mem_write(graph + 0x24, struct.pack("<I", graph + 0x80))
    sim.uc.mem_write(graph + 0x54, struct.pack("<I", lists))
    sim.uc.mem_write(base + 0xF00, bytes.fromhex("89c8c3"))   # a node's +0x20: itself (mov eax, ecx; ret)
    sim.uc.mem_write(base + 0xE00 + 0x20, struct.pack("<I", base + 0xF00))
    for i, (name, x) in enumerate(nodes):
        o = xforms + 0x400 * i
        sim.uc.mem_write(graph + 0x80 + 4 * i, struct.pack("<I", o))
        sim.uc.mem_write(o, struct.pack("<I", base + 0xE00))
        sim.uc.mem_write(o + 0x08, struct.pack("<I", o + 0x200))
        sim.uc.mem_write(o + 0x200, struct.pack("<10f", 0.0, *x["t"], *x["r"], *x["s"]))
        sim.uc.mem_write(o + 0xF0, struct.pack("<III", 0, x["order"], o + 0x300))
        sim.uc.mem_write(o + 0x300, name.encode() + b"\0")

    def malloc(uc, addr, size, _):   # 0xEB1B0, cdecl(size): the bind's list
        esp = sim.reg("esp")
        uc.reg_write(UC_X86_REG_EAX, pairs)
        uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    sim.uc.hook_add(UC_HOOK_CODE, malloc, begin=0xEB1B0, end=0xEB1B0)

    def local(o: int, mode: int | None = None) -> np.ndarray:   # the game's 0x68BE0 from the attributes
        if mode is not None:
            sim.uc.mem_write(o + 0xF0, struct.pack("<I", mode))
        sim.call(l2.XFORM_LOCAL, regs={"ecx": o}, args=(base + 0x1000,))
        return np.array(struct.unpack("<16f", sim.uc.mem_read(base + 0x1000, 64))).reshape(4, 4)

    authored = [local(xforms + 0x400 * i) for i in range(len(table))]

    def bind(flags: int, wears: bytes = b"keylord") -> dict[str, int]:
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(species + 4, struct.pack("<I", base + 0xD00))   # S+4: its body's name
        sim.uc.mem_write(base + 0xD00, wears + b"\0")
        sim.uc.mem_write(lists, struct.pack("<IIIII", lists + 0x40, lists + 0x40 + 2 * len(nodes), 0, 0, 7))
        sim.uc.mem_write(lists + 0x40, struct.pack(f"<{len(nodes)}H", *range(len(nodes))))
        sim.uc.mem_write(binder + 8, bytes(8))
        sim.call(0x62A20, args=(binder, graph))
        n = sim.u32(binder + 0xC) & 0xFFFFFFF
        got = [struct.unpack("<II", sim.uc.mem_read(pairs + 8 * k, 8)) for k in range(n)]
        return {nodes[(o - xforms) // 0x400][0]: index for index, o in got}

    feet, grown = (list(read_body(characters, "keylord").markers).index(m) for m in ("m_feet", "m_root"))
    assert bind(0x04) == bind(0x04, b"KeyLord") == {"m_feet": 0x8000 | feet}   # another critter: the game's binds
    assert bind(0x04, b"golem") == {"m_feet": 0x8000 | feet, "m_root": 0x8000 | grown}   # W27's m_root: its body's
    assert bind(0x24) == {**{name: 0xC000 | n for n, (name, _) in enumerate(table, 1)},
                          "m_jump": 0xC000, "m_feet": 0x8000 | feet}
    binds = [np.array(m).reshape(4, 4) for m in inverse_binds(characters, "keylord")]

    def frame(motion) -> list[np.ndarray]:   # each bone's runtime matrix: its bind x motion(b)
        for b, ibm in enumerate(binds):
            sim.uc.mem_write(runtime + 0xB0 * b + 0x70, struct.pack("<16f", *(np.linalg.inv(ibm) @ motion(b)).ravel()))
        top = sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7
        sim.call(0x62C40, args=(binder, graph))
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == top
        return [np.array(struct.unpack("<16f", sim.uc.mem_read(xforms + 0x400 * i + 0x70, 64))).reshape(4, 4)
                for i in range(len(table))]

    def turn(b: int) -> np.ndarray:   # a rigid motion of bone b's own
        a, c = 0.1 * (b % 7 + 1), 0.07 * (b % 3 + 1)
        rz = np.array([[math.cos(a), math.sin(a), 0, 0], [-math.sin(a), math.cos(a), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        rx = np.array([[1, 0, 0, 0], [0, math.cos(c), math.sin(c), 0], [0, -math.sin(c), math.cos(c), 0],
                       [0.01 * b, -0.02 * b, 0.03, 1]])
        return rz @ rx

    for motion in (lambda b: np.eye(4), turn):
        got = frame(motion)
        for i, (name, b) in enumerate(table):
            want = authored[i] @ motion(b)
            o = xforms + 0x400 * i
            assert sim.u32(o + 0xF0) == 6 and np.allclose(got[i], want, atol=1e-4), name
            assert np.allclose(local(o, 0), want, atol=1e-4), name           # the attributes: the same turn
    jump_at = xforms + 0x400 * len(table)
    assert struct.unpack("<3f", sim.uc.mem_read(jump_at + 0x204, 12)) == (0.0, -4.0, 0.0)   # anim 0: x 0


@pytest.mark.parametrize("species, size", [("keylord", None), ("flicken", None), ("water_tentacle1", 11.97),
                                           ("guard_air", 2.76)])
def test_a_swapped_body_wears_the_air_armor_on_its_body_sized_to_it(species, size):
    """Step 2.77b (sitting 2.75a, row 48: on keylord at x2 and flicken the
    air armor's wing skeleton floated well above the body): the armors' fx
    hang the helm, breastplate, wings and limb pieces from transforms bound
    by name to garret4's m_skull, m_chest, m_root, m_waist and limb
    markers. No other body has them, so each kept its authored point,
    garret4's, in the player's model, which the critter's scale scales
    (the chest 1.5 units up, above flicken's 0.68 top). W15 multiplies each
    such transform's translate and scale by the body's height over
    garret4's, and the scale of each inherit-mode-1 child, which drops its
    parent's scale (the force shield's ForceField). The game's own
    transform code (L2: 0x68BE0, 0x681E0) then puts fx_jump3's wing group
    and helm, both above the body on vanilla's fx, at the same fraction of
    the body's height as of garret4's, under its top, and those and the
    ForceField at that size; m_jump keeps the (2, -4, 0) X16 pulses.
    A body whose bones lie flat (water_tentacle1's top 9.02e-10) is
    measured by its mesh, so its armor isn't sized to nothing (AZ-558:
    x11.97 garret4's, not 4.49e-10). A body with an m_root of its own
    (guard_air) has its m_root pieces sized too, the force bubble x2.76
    (it was garret4's size, 0.36 x the rest: AZ-448)."""
    xbe = _xbe()
    schema = Schema(xbe)
    characters = _read("gamedata/characters.xbr")
    body = read_body(characters, XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section(
        "critters_engine").find_cell(species, "body").string_value)
    garret4 = read_body(characters, "garret4")
    tall = body_height(characters, body)
    k = tall / garret4.top
    assert size is None or round(k, 2) == size
    pieces = (("fx_jump3", "fx_jumpWings:public_WingGroup"), ("fx_jump3", "Helm"), ("fx_shield_force3", "ForceField"))

    def worlds(fx: bytes) -> tuple[Graph, list]:
        toc, names = parse_toc(fx), named_resources(fx)
        out = []
        for res, name in pieces:
            graph = Graph(fx, toc, next(e for e in toc if names.get(e.index) == f"fx/magic/{res}"), schema)
            i = graph.names.index(name)
            chain = (*reversed(graph.ancestors(i)), i)   # the graph's root first
            out.append((graph, l2.transform_world(xbe, [graph.xform_fields(j) for j in chain])))
        return out[0][0], [m for _, m in out]

    _, his = worlds(_read("gamedata/fx.xbr"))
    graph, mine = worlds(bytes(_swap(species)["fx.xbr"]))
    for m, h in zip(mine[:2], his[:2]):
        assert tall > m[2][3] > 0.5 * tall and (h[2][3] > tall or tall > garret4.top)
    for m, h in zip(mine, his):
        assert [row[:4] for row in m[:3]] == [pytest.approx([k * v for v in row[:4]], abs=1e-5) for row in h[:3]]
    jump = graph.xform_fields(graph.names.index("m_jump"))
    assert (jump["t"], jump["s"]) == ((2.0, -4.0, 0.0), (1.0, 1.0, 1.0))


def test_every_attack_plays_one_of_the_bodys_attack_clips_and_the_combo_its_first_three():
    """AZ-294 kept every attack on a clip that switches the body's damage
    marker on (balthazar's attack_2 made no damage pass in sitting
    modelswap). D219 amended (Step 2.64: "give them as many attacks as we
    can"): X3 now gives a clip without a damage window a hit box, so
    every attack column plays one of the body's attack clips (its damage
    clips and every attack* clip): basic1, basic2 and basic3 its
    attack_1, attack_2 and attack_3, the others in turn, but a jump
    attack whose attack_2 deals no damage takes attack_1 when that does
    (Step 2.24f: 23 ticks against 45). Balthazar's combo is attack_1,
    attack_2 (his life-drain cast, with X3's box) and attack_3; a body
    whose clips switch none on (bosses/fire_guardian) attacks with its
    attack clips too, and one with none (flicken) with its ouch_1. A
    clip whose columns' strings are all shared or short takes another
    column's own (W3; the test below)."""
    config = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    columns = XbrDocument.from_bytes(config).keyed_section("attacks_anims").col_names()
    bodies = {m.body for m in player_models(config, characters) if m.status != "refused"}
    plays = {}
    for name in sorted(bodies):
        body = read_body(characters, name)
        if body.clips:
            plays[name] = dict(zip(columns, substitutes(columns, body)))
            attacks = {clip for col, clip in plays[name].items() if col != "roll forward"}
            assert not attack_clips(body) or attacks <= set(attack_clips(body)), name

    assert [plays["balthazar_airship"][col] for col in ("basic1", "basic2", "basic3", "jump attack")] == [
        "attack_1", "attack_2", "attack_3", "attack_1"]
    assert plays["keylord"]["jump attack"] == "attack_2"
    assert set(plays["bosses/fire_guardian"].values()) - {"walk"} == {"attack_1", "attack_2"}
    assert set(plays["flicken"].values()) == {"ouch_1", "run"}


def test_w3_builds_each_usable_bodys_picks_in_every_mode():
    """AZ-412 (Step 2.87): W3 makes each attacks_anims column play its
    pick (substitutes): written into a string in place, else pointed at
    the string its holder held after the writes (place_anims,
    write_anims; Step 2.73a's review found balthazar's right1, left2 and
    up1 reading attack_1 where the pick said attack_2, pointed through a
    holder that had moved on). For every usable body but garret4's (whose
    build writes nothing), in every mode, on config.xbr alone, each
    column's built Anim is its pick, but where an attack clip of the body
    no column's string could hold takes the string of a column whose clip
    another column plays too (spideyzar's whirlwind: hose_attack_3's
    string is shared), so spideyzar plays each of its body's ten attack
    clips. In garret4's exact on a body the bake serves, each attack
    column plays garret4's own clip baked onto it while a string can hold
    every name (B: a g4/ name is 3 longer than its column's own string,
    so it takes one no pick plays): Balthazar's basic1-basic3, finish,
    finish2, finish3, sweep2 and sweep ledge, and his roll g4/roll_forward
    in every mode."""
    config = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    anims = XbrDocument.from_bytes(config).keyed_section("attacks_anims")
    columns, strings = anims.col_names(), anim_strings(anims)
    built: dict[tuple[str, ...], list[str]] = {}
    moved, plays = {}, {}
    for name in sorted({m.body for m in player_models(config, characters) if m.status != "refused"} - {"garret4"}):
        body = read_body(characters, name)
        for mode in MODES if body.clips else ():
            baked = bakes(body, MODE_ANIMS[mode])
            picks = substitutes(columns, body, baked, strings if baked and mode == "garret4" else None)
            if tuple(picks) not in built:
                played = list(picks)
                section = XbrDocument.from_bytes(config).keyed_section("attacks_anims")
                write_anims(section, place_anims(columns, strings, played))
                assert [section.find_cell(col, "Anim", i).string_value
                        for i, col in enumerate(columns)] == played, (name, mode)
                built[tuple(picks)] = played
            played = built[tuple(picks)]
            plays[name, mode] = dict(zip(columns, played))
            moved |= {(name, mode, col): (pick, now) for col, pick, now in zip(columns, picks, played) if pick != now}

    assert moved == {("balthazar_spider", mode, "finish"): ("attack_1", "whirlwind") for mode in MODES}
    assert set(plays["balthazar_spider", "own"].values()) - {"walk"} == set(
        attack_clips(read_body(characters, "balthazar_spider")))
    assert {col for col, pick in plays["balthazar_airship", "garret4"].items() if pick.startswith("g4/")} == {
        "basic1", "basic2", "basic3", "finish", "finish2", "finish3", "sweep2", "sweep ledge", "roll forward"}
    assert [plays["balthazar_airship", mode]["roll forward"] for mode in MODES] == ["g4/roll_forward"] * len(MODES)


def test_x3_gives_a_hit_box_at_the_action_point_only_to_the_attacks_whose_clip_has_none():
    """D219 (Step 2.64, 2.24f's design 5a): X3 serves only the
    attacks_anims columns whose clip has no damage window (a 24-bit
    mask), and for every other column points critter+0x218 back at the
    body's own m_damage, as critter_init cached it, so Balthazar's
    attack_1 (basic1) and attack_3 (basic3) keep their own boxes while
    his attack_2 (basic2, the life-drain cast) gets X3's. Its box is
    centred garret4's box's 1.2341 m ahead of the action point (in
    garret4's units, so over the critter's scale): his right hand's
    runtime matrix (bone 70, read as 0xCCDF0 reads it for the fx bind),
    flicken's chest point. Its m_damage2 (critter+0x21C) stays the
    body's. garret4's exact: the test below."""
    hand, own, slots = (0.42, 0.24, 1.05), 0x20003000, {}
    balthazar = bytes(_swap("balthazar", sounds="garret4")["default.xbe"])   # his fall voices: an L2 blind spot
    (length, on), marker, _, centre = _x3_tick(balthazar, 1, 0.35, own=own, bones={70: hand},
                                               own2=own + 0x100, slots=slots)

    assert (marker != own, length, on, slots["m_damage2"][0]) == (True, 0.5, 1.0, own + 0x100)
    assert centre == pytest.approx((0.42, 0.24 + 1.2341, 1.05))
    assert _x3_tick(balthazar, 1, 0.35, own=own, bones={70: hand}, scale=2.0)[3] == pytest.approx(
        (0.42, 0.24 + 1.2341 / 2, 1.05))
    assert [_x3_tick(balthazar, col, 0.35, own=own, bones={70: hand})[1] for col in (0, 2)] == [own] * 2
    assert _x3_tick(bytes(_swap("flicken")["default.xbe"]), 0, 0.35)[3] == pytest.approx(
        (0.0, 0.1344 + 1.2341, 0.4725), abs=1e-3)


def test_a_giants_hit_box_comes_within_garret4s_swing_of_its_feet():
    """Step 2.70b (sitting 2.75a row 118: guard_earth's ground swings never
    touched an e7 enemy): a box must come within garret4's basic swing
    (HIT_NEAR, 2.77 m) of the feet to hit a target in front of the
    player. guard_earth's clips switch no damage marker on, so X3 serves
    every column, at its right hand (bone 10), which passes 6.5-8.5 m
    ahead of its 12.4 m body's feet through X3's window: its box came no
    nearer than 5.4 m (X13 lowering it to the ground there). X3's box
    goes where garret4 holds his instead, in own mode, and on
    guard_water, whose attack_1 hand stays 3.6 m off; sized to garret4's
    height guard_earth's hand comes near and keeps it, as guard_fire1's
    and Balthazar's do. A body's own box was judged alike (the reach
    test) until X13's fill (Step 2.132, AZ-605) brought every box ahead
    back to the feet: kingkong's attack (golem's, x5), 6.9 m off, keeps
    its own now, as sized and on golem (x1.25, 1.7 m off)."""
    config = _read("gamedata/config.xbr")
    characters = _read("gamedata/characters.xbr")
    for (species, mode, size), x3 in {
            ("guard_earth", "own", "own"): (23, True),
            ("guard_earth", "own", "garret4"): (23, False), ("guard_water", "own", "own"): (23, True),
            ("guard_fire1", "own", "own"): (23, False), ("balthazar", "own", "own"): (7, False),
            ("kingkong", "own", "own"): (0, False), ("kingkong", "own", "garret4"): (0, False),
            ("golem", "own", "own"): (0, False)}.items():
        rows = attacks(config, characters, species, mode, size)
        assert (sum(r.x3 for r in rows), any(r.x3_feet for r in rows)) == x3, (species, mode, size)
    assert [round(min(w.near for w in damage_windows(characters, "golem", "attack", scale)), 2)
            for scale in (1.25, 5.0)] == [1.73, 6.93] and HIT_NEAR == pytest.approx(2.77, abs=0.005)

    hand = (0.83, 8.44, 2.75)   # guard_earth's right hand 30% into attack_1, in its model
    assert _x3_tick(bytes(_swap("guard_earth")["default.xbe"]), 0, 0.35, bones={10: hand})[3] == pytest.approx(
        GARRET4_BOX)
    sized = _swap("guard_earth", size="garret4")
    scale = XbrDocument.from_bytes(sized["config.xbr"]).keyed_section("critters_engine").find_cell(
        "garret4", "scale", None).double_value
    assert _x3_tick(bytes(sized["default.xbe"]), 0, 0.35, bones={10: hand}, scale=scale)[3] == pytest.approx(
        (hand[0], hand[1] + 1.2341 / scale, hand[2]), rel=1e-5)


EXACT = [(0, "attack_1"), (1, "attack_9"), (7, "360_sweep"), (9, "elemental_attack"), (13, "attack_2"),
         (16, "attack_14"), (21, "attack_12"), (20, None)]
"""Columns of garret4's exact build and the clip each plays in vanilla:
the combo's first two, a sweep, an element, the jump attack, left1, up1
and the roll."""


def test_garret4s_exact_hits_each_column_with_garret4s_own_box_in_his_own_window():
    """2.60 REPORT §4.1 (1), Step 2.68: garret4's exact gave every
    attacks_anims column X3's attack_1 box, on from 20% to 50% of the
    move, while garret4's 23 attack columns play 23 clips, each with its
    own box and window (left1's attack_14 hits at 0.15-0.23 of its clip,
    the elemental_attack box is 8 m wide). X3 now gives each column
    garret4's own: on while the clip's time over its length (+0x178; W5
    plays the move in garret4's time, so the fraction is garret4's) is in
    the window where that clip, in vanilla, switches garret4's m_damage
    on (Step 2.61's evaluator), the box bounding garret4's boxes over it,
    centred from the feet, its extents x the marker's 0.5 its half
    extents, both over the critter's scale; the roll never. A body's
    action point plays no part (Balthazar's hand), and neither does its
    m_damage2: +0x21C points at a marker that is never on (the water
    tentacles' attack clips switch theirs on), and stays NULL on a body
    without one. Own body's X3 stays 20-50% at the action point (the
    test above). With reach-to-ground on, X13 fills every column's box
    but the roll's (Step 2.132)."""
    characters = _read("gamedata/characters.xbr")
    garret4 = read_body(characters, "garret4")
    hand, own = (0.42, 0.24, 1.05), 0x20003000
    built = bytes(_swap("balthazar", mode="garret4", attack_ground=True, sounds="garret4")["default.xbe"])   # (X15)
    assert l1.check(_xbe(), built) == []
    game = _attack_box(_xbe(), 0x24, 0)[:2]     # 0xCA390's box, which X13 keeps
    assert [c for c in range(24) if _attack_box(built, 0x24, c)[:2] == game] == [20]

    def tick(column: int, fraction: float, **kw):
        (length, on), marker, _, box = _x3_tick(built, column, (fraction - 0.1) / 0.8, own=own,
                                                bones={70: hand}, extents=True, **kw)
        assert marker != own
        return length, on, box
    for column, clip in EXACT:
        if clip is None:
            assert {tick(column, f)[1] for f in (0.2, 0.5, 0.8)} == {0.0}
            continue
        windows = damage_windows(characters, "garret4", clip)
        start, end = windows[0].on / garret4.length(clip), windows[-1].off / garret4.length(clip)
        low = [min(w.low[i] for w in windows) for i in range(3)]
        high = [max(w.high[i] for w in windows) for i in range(3)]
        assert [tick(column, f)[1] for f in (start - 0.02, start + 0.005, end - 0.005, end + 0.02)] == [
            0.0, 1.0, 1.0, 0.0], clip
        length, _, box = tick(column, (start + end) / 2)
        assert box == pytest.approx([(a + b) / 2 for a, b in zip(low, high)]
                                    + [(b - a) / (2 * length) for a, b in zip(low, high)], abs=1e-4), clip
        length, _, box = tick(column, (start + end) / 2, scale=2.0)
        assert (length, box[:3]) == (0.25, pytest.approx([(a + b) / 4 for a, b in zip(low, high)], abs=1e-4))
    assert tick(16, 0.19)[1] == 1.0 and tick(0, 0.19)[1] == 0.0      # left1 opens early, basic1 late
    slots = {}
    tick(0, 0.4, own2=own + 0x100, slots=slots)
    assert slots["m_damage2"][0] not in (0, own + 0x100) and slots["m_damage2"][1] == (0.0, 0.0)
    tick(0, 0.4, slots=slots)
    assert slots["m_damage2"] == (0, None)


def test_a_clipless_body_takes_garret4s_hit_windows_in_every_mode():
    """AZ-473 (Step 2.75e): a body with no clips (gargoylestone) plays
    garret4's clips, baked as timers (B, X12), in every gameplay mode, so
    X3 gives each column garret4's own box and window in every mode, as
    garret4's exact does (Step 2.68, the test above). In own body it
    gave Step 2.67's window, attack_1's box on from 20%
    to 50% of every move, so each swing hit early (sitting 2.75d: basic1
    on swing tick 2 where garret4 hits on 4, finish3 on 3 against 11).
    Its default.xbe is garret4's exact's in every mode but for own
    body's X13 fill (Step 2.132: every column but the roll) and its
    touch at its size (X34, Step 2.133), and the randomizer's logic
    reads that build's reach. basic1's box is on in
    attack_1's own window, 0.375-0.49 of the clip (L2)."""
    characters = _read("gamedata/characters.xbr")
    length = read_body(characters, "garret4").length("attack_1")
    windows = damage_windows(characters, "garret4", "attack_1")
    start, end = windows[0].on / length, windows[-1].off / length
    builds = {}
    for mode in MODES:
        logic = AttackLogic()
        builds[mode] = (bytes(_swap("gargoylestone", mode=mode, logic=logic)["default.xbe"]), logic.reach)

    assert builds["own"][1] == builds["garret4"][1]   # own body touches at its size (X34), Skin only at his (Step 2.133)
    assert _moved(builds["own"][0]) - _moved(builds["garret4"][0]) == {ATTACK_BOX_HOOK.va, TOUCH_HOOK.va}
    assert _param(builds["own"][0], ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, "_player_attack_ground_mask") == 0xEFFFFF
    assert [_x3_marker(builds["own"][0], 0, (f - 0.1) / 0.8)[1]
            for f in (start - 0.02, start + 0.005, end - 0.005, end + 0.02)] == [0.0, 1.0, 1.0, 0.0]


def test_a_body_with_more_attack_clips_than_the_combo_swings_the_next_one_each_time():
    """D219 amended (Step 2.64, 2.24f's design 5b): spideyzar's body has
    ten attack clips and the player reaches a few columns. X10 takes
    player_attack_enter's CALL of anim_change (0x42910) at 0x889A6 (L1
    well formed): for the player's species (flag 0x20, S+0x64) each swing
    of an attack column but the roll and the jump attack plays the clip
    of the next column of its ring (the first column holding each clip,
    in turn and round again: rotation, deterministic, over a random
    pick), from that column's slot (0x52 + it), and puts the slot back,
    so the index anim_change records stays the game's. Another species,
    the roll and the jump attack play their own slot. The ring's place
    persists (D227): a combo's end, an idle or the next enemy doesn't
    reset it, only a boot. The ring is the build's, written into the
    shim's .data (a count, the next entry, the columns that rotate,
    whether entries carry numbers and a struct per entry), which the guest
    then writes: own body (Step 2.69's reach test) rotates the clips
    whose own box can hit a target on the ground, all ten of spideyzar's
    since X13's fill brings every box ahead to the feet and the floor
    (Step 2.132, AZ-605: its six ranged attack_* clips stayed 0.79-1.39 m
    up and its melee attack_6 0.64 m up, so only deathbeam, jump and
    whirlwind rotated). A body with no more attack clips
    than the combo's three (balthazar) gets no X10, and neither does
    garret4's exact (Step 2.68), even with the balance asked for: each
    column plays its one clip in garret4's time, X3's windows being
    fractions of it. Step 2.69 (D223,
    D228): with the attack balance on (own body's default) each entry
    carries its clip's Rate (its home column's in the build's
    attacks_anims) and the Damage multiplier its clip deals in each
    column: garret4's for that column x the balance of that clip in that
    column's move, so a swing stays within 0.5-4.0 of garret4's for the
    column swinging (0.625-5.0 on a slow attacker such as spideyzar, D350) (a finish swing of a weak clip doesn't fall to a
    basic swing's 0.5 x B), and in its home column it is the table's. A
    rotating swing writes them into its PlayerControl (critter+0x180) at
    +0xEC, which each tick hands the damage pass, and +0x104, which
    player_attack_enter reads into the layer's rate right after the call;
    any other swing leaves them, and so does every swing without the
    balance. Step 2.104 (AZ-523, W19): in own body, with the balance or
    without it, each entry also carries its clip's chain point (the
    column's Move end1 fraction fits one clip, so a ring basic chained
    after the stun): a swing in basic1-3 writes into +0xFC its first
    damage tick plus 0.2 s at the Rate it plays at (+0x104: the entry's,
    or without the balance the column's), never past the row's Move end2
    (+0x100), and a swing in any other column leaves it. Step 2.106
    (AZ-495): so does a swing in a column some entry of which would chain
    before its move touches the target ahead, by garret4's Move end1
    (spideyzar's finish2, sweep1, right1, right2 and left1: 0x1C057).
    Step 2.135 (D325): a body with two attack sets or more (spideyzar's
    three, the shards', the tentacles') gets no X10, its sets playing
    each clip from a column of its own (X36), so the ring is pinned on
    splinter, one set of four clips (attack, eat, eat_2, eat_3; its basics
    chained, 0x7, and no slow factor)."""
    game = _swap("splinter")
    built = bytes(game["default.xbe"])
    at = va_to_file(0x889A6)
    target = 0x889AB + struct.unpack_from("<i", built, at + 1)[0]
    clips = _anims(game["config.xbr"])
    anims = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("attacks_anims")
    vanilla = XbrDocument.from_bytes(_read("gamedata/config.xbr")).keyed_section(
        "attacks_anims")
    numbers, garret4 = {}, {}
    for i, col in enumerate(anims.col_names()):
        cell = vanilla.find_cell(col, MULTIPLIER, i)
        garret4[i] = cell.double_value if cell is not None and cell.type_code == 1 else 1.0
        numbers[i] = (_f32(anims.find_cell(col, MULTIPLIER, i).double_value),
                      _f32(anims.find_cell(col, "Rate", i).double_value)) if col != "roll forward" else None
    sim, base = Sim(built), 0x20000000
    critter, species, control = base, base + 0x1000, base + 0x2000
    sim.uc.mem_map(base, 0x10000)
    sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
    sim.uc.mem_write(critter + 0x180, struct.pack("<I", control))
    table = [-1] * 0x71
    table[0x52:0x52 + 24] = range(1000, 1024)                 # each column's slot: its own handle
    sim.uc.mem_write(species + 0x124, struct.pack(f"<{len(table)}i", *table))
    seen = []

    def change(uc, addr, size, _):   # anim_change: __stdcall(12), RET 0xC
        esp = sim.reg("esp")
        ret, _critter, index, _flags = struct.unpack("<4I", uc.mem_read(esp, 16))
        seen.append(struct.unpack("<i", uc.mem_read(species + 0x124 + 4 * index, 4))[0] - 1000)
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 16)

    sim.uc.hook_add(UC_HOOK_CODE, change, begin=0x42910, end=0x42910)

    def swing(column: int, flags: int = 0x24, rate: float = -1.0, end2: float = 1.0) -> str:
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        for field, value in ((0xEC, -1.0), (0xFC, -1.0), (0x100, end2), (0x104, rate)):
            sim.uc.mem_write(control + field, struct.pack("<f", value))
        sim.call(target, args=(critter, 0x52 + column, 4), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0xC, as 0x42910's
        took.append((column, seen[-1], sim.f32(control + 0xEC), sim.f32(control + 0x104)))
        chains.append(sim.f32(control + 0xFC))
        return clips[seen[-1]]

    took: list[tuple[int, int, float, float]] = []
    chains: list[float] = []
    assert built[at] == 0xE8 and l1.check(_xbe(), built) == []
    count, _, _, carry, ring, chained, chain = _ring(built)
    assert (count, carry, {clips[c] for c in ring}) == (4, 1, {"attack", "eat", "eat_2", "eat_3"})
    assert chained == 0x7 and all(0.0 < chain[c][0] < 1.0 and chain[c][1] > 0.0 for c in ring)

    def point(home: int, rate: float) -> float:   # the chain point the shim writes
        return _f32(chain[home][0] + chain[home][1] * rate)
    assert [swing(column) for column in ring] == [clips[c] for c in ring]   # each in its home column
    assert [(m, rate) for _, _, m, rate in took] == [numbers[c] for c in ring]
    turns = [swing(column) for column in ((0, 3, 5, 21, 22, 1) * count)[:2 * count]]
    assert turns[count:] == turns[:count] and len(set(turns)) == count
    for (column, home, m, rate), fc in zip(took, chains):
        assert rate == numbers[home][1], (column, home)
        assert BALANCE_FLOOR * (1 - 1e-6) <= m / garret4[column] <= BALANCE_CAP * (1 + 1e-6), (column, home)
        assert (math.isclose(fc, point(home, rate), rel_tol=1e-6) if chained >> column & 1 else fc == -1.0), \
            (column, home)
    assert len({m for _, _, m, _ in took}) > 3
    assert {swing(13), swing(20), swing(0, flags=0x04)} == {clips[13], clips[20], clips[0]}
    assert [(m, rate) for _, _, m, rate in took[-3:]] == [(-1.0, -1.0)] * 3
    assert swing(1) == turns[0]   # D227: nothing but a boot resets the ring, not a combo's end or a new target
    (ring_va, _), = [span for span in shim_data(built) if span[1] - span[0] == RING_SIZE]
    sim.uc.mem_write(ring_va + 0xC, struct.pack("<I", 0))   # the balance off: no numbers carried
    for end2 in (1.0, 0.01):
        home = ring[struct.unpack("<i", sim.uc.mem_read(ring_va + 4, 4))[0]]
        swing(0, rate=0.75, end2=end2)
        assert took[-1][2:] == (-1.0, 0.75) and math.isclose(chains[-1], min(_f32(end2), point(home, 0.75)),
                                                             rel_tol=1e-6), (home, end2)
    off = _ring(bytes(_swap("splinter", attack_balance=False)["default.xbe"]))
    assert (off[3], off[5], off[6]) == (0, 0x7, chain)
    assert list(struct.unpack(f"<{len(table)}i", sim.uc.mem_read(species + 0x124, 4 * len(table)))) == table
    assert [bytes(_swap(species, mode=mode, **kw)["default.xbe"])[at:at + 5]
            for species, mode, kw in (("balthazar", "own", {}), ("spideyzar", "garret4", {"attack_balance": True}),
                                      ("spideyzar", "own", {}))
            ] == [_xbe()[at:at + 5]] * 3


@pytest.mark.parametrize("species, why", [
    ("jellyfish", "it has no body"),
    ("town_elder", "its body 'townspeople/elder' has no model in characters.xbr"),
    ("garret5", "no such species in config.xbr's critters_engine"),
])
def test_a_species_without_a_model_fails_the_build_by_name(image, species, why):
    """D35, D112: a species with no body cell or with no model (an item
    body no longer is refused: D260), or a name config.xbr doesn't have,
    fails the build (``sdk.image``) by name, the species and why, before
    it plans anything."""
    from azurkit import sdk

    with pytest.raises(ValueError, match=re.escape(f"--player-character {species!r}: {why}")):
        sdk.image({"iso": str(image), "packs": {}, "character": {"species": species}})


def test_player_models_lists_every_species_with_its_status_or_why_it_is_refused():
    """D111 refined: every species can dress the player, each shown green,
    yellow or red; D112 refuses the species without a model by name, and
    since D260 (Step 2.90b) the 73 items are offered, red "untested":
    ``player_models`` (Modkit's ``player-models`` list, the Characters
    tab's) gives each of the 184 ``critters_engine`` species its status
    or why it is refused. Sittings modelswap, modelswap2 and
    modelswap3 graded 24 species and sitting p8 the other usable ones
    (Step 2.40: P8, Q292, no "untested" left; the clipless bodies red,
    D132; town_male_6 and guard_air regraded, Q281), sitting q281
    regraded the earlier greens on their current builds (Step 2.45, Q281),
    each note citing its sitting, and a species whose build was
    byte-identical to a graded one carries its grade (D117: same files out
    of the model swap, so the same ISO; with Garret's sounds, the builds
    the sittings graded: the own sounds of Step 2.72 aren't on the
    checklist, and 8 of the pairs speak differently). Since Step 2.65 own
    mode also writes the species' own stride (W7), which five such
    species don't share with their partner (24hr, guard_fire2 and 3,
    town_male_6B, lava_shard): their default builds now differ, and since
    Step 2.132's X32 (D333) so did air_elemental_boss's and sleeth_x's,
    whose NPCs hit with another damage record than their partners'
    (since Step 2.180's one flash, D700, sleeth_x's is sleeth_momma's
    again; air_elemental_boss's differs beyond X32); every
    other pair's is still the same (statuses per mode: Step 2.74; the
    list shows a build's grade from a sitting of it where one graded it,
    Step 2.75, the test of ``--mode`` above; a mode's shares, AZ-492, the
    test below, which builds those 20 pairs in own mode with Garret's
    sounds and pins each as the same build: here each is checked to be
    one of its cases, and only the 6 that differ are built, Step X.55). The
    list's roles each species' own sounds take as the player's (Step 2.71)
    are ``model_sounds``', "-" for none."""
    config, bodies = _read("gamedata/config.xbr"), _read("gamedata/characters.xbr")
    models = {m.species: m for m in player_models(config, bodies)}
    graded = {s: SUPPORT[s] for s, m in models.items() if m.status != "refused" and m.note != "untested"}
    sat = {s: grade for s, grade in graded.items() if s not in SAME_BUILD}

    assert {s: colour for s, (colour, _) in sat.items() if colour != "green"} == {
        "guard_air": "yellow", "gargoylestone": "red", "tesla_tree": "red", "guard_earth": "yellow",
        "water_tentacle2": "yellow",
        "water_tentacle3": "yellow", "magmar": "yellow", "kingkong": "yellow", "guard_water": "yellow",
        "water_tentacle1": "yellow", "bot": "yellow", "channeler": "red", "firefly": "yellow",
        "fish_little1": "yellow", "fish_little2": "yellow", "fire_shard": "red", "splinter": "yellow",
        "town_child_farmer_1": "yellow", "town_child_farmer_2": "yellow", "town_child_farmer_3": "yellow",
        "town_female_4": "red", "town_girlchild_farmer_1": "yellow", "town_girlchild_farmer_2": "yellow",
        "shadow_demon": "yellow"}
    assert sum(colour == "green" for colour, _ in sat.values()) == 55
    assert all(re.search(r"(modelswap[23]?|p8|q281),", why) for _, why in sat.values())
    for species, (partner, sha) in SAME_BUILD.items():
        assert graded[species][0] == sat[partner][0]
        assert partner in graded[species][1] and sha in graded[species][1]
    differ = {"24hr", "guard_fire2", "guard_fire3", "town_male_6B", "lava_shard", "air_elemental_boss"}
    assert {species for species, (partner, _) in SAME_BUILD.items() if species not in differ and (
        MODE_SHARES["own", "own"].get(species, ("",))[0] != partner or partner not in MODE_GRADES["own", "own"])} == set()
    assert {species for species in differ
            if _changed(species, "own", "own", "garret4") != _changed(SAME_BUILD[species][0], "own", "own", "garret4")} == differ
    assert len(SAME_BUILD) == 26
    engine = XbrDocument.from_bytes(config).keyed_section("critters_engine")
    items = {s for s in models if engine.find_cell(s, "ai", None).string_value == "item"}
    assert {s for s, m in models.items() if m.note == "untested"} == items and len(items) == 73
    assert sum(m.status == "green" for m in models.values()) == 60   # own body (Step 2.134a's gust, golem; D700's sleeth_x)
    refused = {s for s, m in models.items() if m.status == "refused"}
    assert len(refused) == 6 and len(models) - len(refused) == 178 and len(models) == 184
    # Step 2.71: the roles its own sounds take as the player's, "-" for none (the roll its attack's, D328)
    files = {"config.xbr": config, "characters.xbr": bodies, "fx.xbr": _read("gamedata/fx.xbr"),
             "english.xbr": _read("gamedata/english.xbr")}
    assert {s: "-" if s in refused else ",".join(model_sounds(files, s).own) or "-" for s in (
        "keylord", "firefly", "town_male_6", "town_elder")} == {
        "keylord": "attack,hurt,death,idle,roll,hit", "firefly": "ambient,hit",
        "town_male_6": "attack,hurt,roll", "town_elder": "-"}


_CHANGED: dict = {}


def _changed(species: str, mode: str, size: str, sounds: str = "own") -> dict:
    """The files ``species``' build changes in ``mode`` and ``size``, each by its sha256 (kept for the run)."""
    key = (ports._build().vanilla.release.name, species, mode, size, sounds)
    if key not in _CHANGED:
        _CHANGED[key] = {path: hashlib.sha256(data).hexdigest()
                         for path, data in _swap(species, mode=mode, size=size, sounds=sounds).changed().items()}
    return _CHANGED[key]


@pytest.mark.parametrize("species, mode, size, partner", [
    *sorted((species, mode, size, partner) for (mode, size), shares in MODE_SHARES.items()
            for species, (partner, _, _) in shares.items() if partner in MODE_GRADES[mode, size]),
    ("town_male_6B", "own", "own", "town_male_6")])
def test_a_species_carries_a_modes_grade_only_from_a_partner_that_builds_its_iso_there_and_says_if_only_sounds_differ(
        species, mode, size, partner, monkeypatch):
    """AZ-492 (Step 2.75b, its census B0's finding 1): a mode's grade
    (``MODE_GRADES``) carries to a species whose build in that mode and
    size is its partner's (``MODE_SHARES``, B0's census on 71f13956), no
    longer by ``SAME_BUILD``, the pre-own-mode sittings' pairs:
    town_male_6B builds town_male_6's ISO in garret4's exact but not in
    own body (its own stride, W7), so it doesn't carry town_male_6's
    own-body grade (town_male_6 graded in both since sitting 2.75b S4).
    Each share whose partner a sitting graded there (a case each, since
    sitting 2.75b S3 graded most partners) builds the partner's files, with Garret's
    sounds and, unless only its own sounds differ, by default; a
    sounds-only share says so (flicken of peril was "byte for byte"
    though its default build differs)."""
    monkeypatch.setitem(MODE_GRADES[mode, size], partner, MODE_GRADES[mode, size].get(partner, ("green", "graded")))
    shares = MODE_SHARES[mode, size].get(species, ("", "", False))
    shared, sounds_only = shares[0] == partner, shares[2]

    assert (_changed(species, mode, size, "garret4") == _changed(partner, mode, size, "garret4")) is shared
    if shared:
        assert (_changed(species, mode, size) == _changed(partner, mode, size)) is not sounds_only
    assert mode_status(species, mode, size)[1].startswith(
        f"builds the same ISO as {partner} in this mode, "
        f"{'but for its own sounds' if sounds_only else 'byte for byte'}") is shared

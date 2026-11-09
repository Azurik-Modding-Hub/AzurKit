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
from pathlib import Path

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

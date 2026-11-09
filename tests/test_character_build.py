"""The player-model swap's build, ported from Modkit's ``test_player_character.py`` (its first half, Step 4.27b): the
gameplay modes' cells, the roll, the hit box and hit reactions, the staff's effects, the body's own fields, the clip
slots and their stand-ins, the zipline hang, the ladder, the camera and the size parts. Each build is the swap's layer as
``sdk._plan`` plans it from the player's image, laid as ``sdk.image`` lays it (:func:`_swap`), and each test asserts
what Modkit's asserted on the same inputs; the simulator checks run on ``devkit.sim``."""

from __future__ import annotations

import math
import struct
from collections import Counter, OrderedDict
from dataclasses import replace

import pytest
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EFLAGS, UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_FPSW

from azurkit import sdk
from azurkit.core import gate, iso
from azurkit.core.xbr.nodes import named_resources, parse_toc
from azurkit.edits.manifest import image
from azurkit.tools import characters as _characters
from azurkit.tools import mods
from azurkit.tools.characters import ports, retarget
from azurkit.tools.characters._player_borrow import BIND as BORROW_BIND, REUSE as BORROW_REUSE
from azurkit.tools.characters._player_character import (
    ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, CAMERA_RIG, CLIMB_HOOKS, CLIMB_OFFSETS_HOOK, CLIMB_SHIM, EASE_STATE,
    EYE_HANG_HOOK, EYE_HOOK, EYE_REGROW_HOOK, EYE_SHIM, EYE_SIGHT_HOOK, EYE_SWEEP_HOOK, EYE_SWEEP_SHIM, FADE_CAMERA,
    FADE_HOOK, FADE_LOOSE, FADE_LOW, FADE_SHIM, FADE_SOLE, G4_OVER_FEET, G4_OVER_ROWS, GARRET4_SIZES, HANG_EASE_GROUND,
    HANG_EASE_HOOKS, HANG_EASE_SHIM, HIT_FX_HOOK, HIT_HOOK, HOLD_HOOKS, HOLD_SHIM, HOLD_STATE, MODE_GRADES, MODE_SHARES,
    MODES, OVER_HOIST_HOOK, OVER_TOP_HOOK, OVER_TOP_SHIM, PLAYER_RADIUS, RATE_MARGIN, RIG_FLOOR, RIG_SITES, ROLL_HOOK,
    ROLL_HOOK_VA, SEARCH_HOOK, SEARCH_SHIM, SEARCH_SITES, SHIM_HOOKS, SIZED_ROLL, STAFF_WALLS, STAFF_X1,
    STANCE_HOOK, STANCE_SHIM, SUPPORT, SURFACE_FLOOR, SURFACE_SLOTS, SWIM_BOB, SWIM_MARGINS, TOUCH_HOOK, UNSEEN,
    WINDUP_MAX, ActionPoint, AttackLogic, _refusal, _species, action_point, at_point, attack_move, attacks, bakes,
    camera_plan, camera_shape, field_damage, field_switches, follow_hands, hang_loop, hang_scale, hang_top, hold_ahead,
    loose_bones, move_window, movement_size, player_models, quiet_fills, rest_distance, scripted_switches, size_scale,
    size_shape, staff_scales, standard_rate, substitutes, swim_margins, touch_query, windup,
)
from azurkit.tools.characters._player_damage_marker import (
    BOX, BOXES_SIZE, DAMAGE_MARKER, GARRET4_FORWARD, SHIM as DAMAGE_MARKER_SHIM, garret4_boxes,
)
from azurkit.tools.characters._player_slots import (
    ANIMS, BASE_CLIPS, HOOK as SLOTS_HOOK, JUMPS, SHIM as SLOTS_SHIM, TABLE as SLOTS_TABLE, X9, slot_fills,
)
from azurkit.tools.characters._player_sounds import XBE_SOUND_SITES
from azurkit.tools.characters._player_variants import overlay
from azurkit.tools.characters._player_victory import KEEPS_STAND_IN, VICTORY_CLIPS, victory_copies
from azurkit.tools.characters import _player_weapons as pw
from azurkit.tools.characters._player_weapons import CAST_SWITCH, _staff_hold, weapons
from azurkit.tools.characters.characters import (
    DAMAGE_MARKERS, FLAT, VERTEX_SIZE, body_names, bone_records, damage_windows, forward, height, inverse_binds,
    marker_records, mesh_groups, mesh_points, read_body,
)
from azurkit.tools.characters.ports import (
    XbrDocument, pack_f32, patch_spec_site, resolve_va_to_file, trampoline_shim_data, trampoline_symbol_va, va_to_file,
    verify_trampoline_patch, xbe_site,
)
from azurkit.tools.characters.retarget import MAPS as BAKED_BODIES, Rig, _turn, origins, pose, qinv, qmul, read_clip
from devkit.builds import verify_patches
from devkit.sim import l1, l2
from devkit.sim.l2 import PlayerSim, Sim
from devkit.sim.ports import parse_xbe_sections
from tests.test_roll import BASIC1, ROLLER

VANILLA_ISO, EUROPE_ISO = "usa", "europe"   # a build's release, as Modkit's tests named its image
_IMAGES: dict[str, object] = {}
_SHORT = {"default.xbe": _characters.XBE, "config.xbr": _characters.CONFIG,
          **{path.rsplit("/", 1)[1]: path for path in _characters.FILES}}
_KEYWORDS = {"model_scale": "scale", "missing_anims": "anims"}   # apply_player_model's keyword -> the recipe's field


@pytest.fixture(autouse=True)
def _image(request, usa_iso):
    """The images the test's builds read (USA's, and Europe's for a test marked ``europe``), and the swap's readers
    (a shim's landed symbols) run inside a build of the test's release (``ports.building``)."""
    _IMAGES[VANILLA_ISO] = usa_iso
    release = VANILLA_ISO
    if request.node.get_closest_marker("europe"):
        _IMAGES[EUROPE_ISO], release = request.getfixturevalue("europe_iso"), EUROPE_ISO
    with ports.building(ports.Build(_source(release))):
        yield


_VANILLA: dict[tuple[str, str], bytes] = {}


def _vanilla(path: str, release: str = VANILLA_ISO) -> bytes:
    """The release's vanilla file ``path`` (``default.xbe``, ``gamedata/...``), read once a process."""
    if (release, path) not in _VANILLA:
        with iso.Reader(_IMAGES[release]) as r:
            _VANILLA[release, path] = r.read(path)
    return _VANILLA[release, path]


class _Game:
    """A build's files: each one it changed by its path (:meth:`changed`), any by Modkit's short name or path."""

    def __init__(self, release: str, files: dict[str, bytes], notes: list[str]):
        self.release, self.files, self.notes = release, files, notes

    def __getitem__(self, name: str) -> bytes:
        path = _SHORT.get(name, name)
        return self.files[path] if path in self.files else _vanilla(path, self.release)

    def changed(self) -> dict[str, bytes]:
        return dict(self.files)

    def stored(self, name: str) -> bytes:
        """The release's vanilla file ``name``."""
        return _vanilla(_SHORT.get(name, name), self.release)


_SOURCES: dict[str, ports.Vanilla] = {}


def _source(release: str) -> ports.Vanilla:
    """The release's vanilla files as the swap reads them."""
    if release not in _SOURCES:
        stamp = gate.verify(str(_IMAGES[release]), whole=False)
        _SOURCES[release] = ports.Vanilla(stamp.release, stamp.path, stamped=stamp)
    return _SOURCES[release]


def _size_shape(release: str, species: str, *args, **kw):
    """``size_shape`` of ``species`` on the release's image, as a build sizes it (``characters.size``)."""
    vanilla = _source(release)
    with ports.building(ports.Build(vanilla)):
        return size_shape(vanilla, species, *args, **kw)


_BUILDS: OrderedDict = OrderedDict()   # the last few builds of the process (each holds a grown characters.xbr)


def _swap(species: str, iso_=VANILLA_ISO, lines: list | None = None, *, fold: bool = False,
          logic: AttackLogic | None = None, **kw) -> _Game:
    """``species`` worn on the release's image, ``kw`` its ``apply_player_model`` keywords (Modkit's call) as the
    recipe's fields, no pack on: ``sdk._plan``'s layers laid as ``sdk.image`` lays them, but for the player_physics
    layer the sdk folds the body's size into (the walk and roll x sqrt(s), randomize-full's, which Modkit's
    ``apply_player_model`` never wrote) unless ``fold``. The files the build changed (``filelist.txt``, derived,
    left out); ``lines`` hears the swap's build log (the layer's notes), ``logic`` its attacks
    (``characters.dressed``'s)."""
    fields = {_KEYWORDS.get(k, k): v for k, v in kw.items() if v is not None}
    recipe = {"species": species, **fields}
    key = (iso_, fold, species, tuple(sorted(fields.items())))
    if key not in _BUILDS:
        stamp, base, layers, _, _ = sdk._plan({"iso": str(_IMAGES[iso_]), "packs": {}, "character": recipe})
        made, manifest = image(stamp, [la for la in layers if fold or la.tool == _characters.TOOL], base)
        changed = [f for f in manifest.result if f != "filelist.txt"]
        with iso.Reader(made) as r:
            _BUILDS[key] = _Game(iso_, {f: r.read(f) for f in changed},
                                 [note for la in manifest.layers for note in la.notes])
        while len(_BUILDS) > 3:
            _BUILDS.popitem(last=False)
    _BUILDS.move_to_end(key)
    if lines is not None:
        lines += _BUILDS[key].notes
    if logic is not None:
        vanilla = _source(iso_)
        _characters.dressed(_characters.normalize(recipe), vanilla, [],
                            _characters.packs_view(vanilla.release, mods.PACKS), logic=logic)
    return _BUILDS[key]


def _cells(config: bytes) -> dict[tuple[str, str, str], tuple]:
    """Every keyed cell of ``config`` by (table, column, row): its type
    and value (a string cell by the string it reads)."""
    out = {}
    for table, section in ((s.name, s) for s in XbrDocument.from_bytes(config).sections()):
        rows, cols = section.row_names(), section.col_names()
        for c, col in enumerate(cols):
            for r, row in enumerate(rows):
                cell = section.read_cell(c, r)
                out[table, f"{c}:{col}", row] = (
                    cell.type_code, cell.double_value, cell.string_value)
    return out


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _x3_param(xbe: bytes, name: str) -> int:
    """X3's float param ``_player_model_x3_<name>`` in the built ``xbe``,
    rounded (its column mask or bone index)."""
    return round(struct.unpack_from("<f", xbe, resolve_va_to_file(xbe, trampoline_symbol_va(
        xbe, DAMAGE_MARKER, f"_player_model_x3_{name}", shim_source=DAMAGE_MARKER_SHIM.source_path())))[0])


def _clip(characters: bytes, key: str) -> tuple[int, int]:
    """The file offset and size of ``characters.xbr``'s resource ``key``."""
    toc = parse_toc(characters)
    index = next(i for i, name in named_resources(characters).items() if name.casefold() == key)
    return toc[index].file_offset, toc[index].size


def _garret4_node(characters: bytes, clip: str, node: str, t: float,
                  turn: tuple[float, ...]) -> tuple[float, ...]:
    """garret4's ``node`` in his ``clip`` at ``t`` s, sampled by the
    vanilla 0xCAB80 on his body from ``characters.xbr`` and turned by
    ``turn`` (the vanilla 0xA1420)."""
    sim, base = Sim(_vanilla("default.xbe")), 0x20000000
    sim.uc.mem_map(base, 0x1000000)
    for at, key in ((base + 0x100000, "characters/garret4"), (base + 0x800000, f"characters/garret4/{clip}")):
        off, size = _clip(characters, key)
        sim.uc.mem_write(at, characters[off:off + size])
    sim.uc.mem_write(base, struct.pack("<I", base + 0x100000))
    sim.uc.mem_write(base + 0x40, struct.pack("<4f", *turn))
    sim.uc.mem_write(base + 0x80, node.encode() + b"\0")
    sim.call(0xCAB80, regs={"eax": base}, args=(
        base + 0x80, base + 0x800000, struct.unpack("<I", struct.pack("<f", t))[0], base + 0x60, 0, 3))
    sim.call(0xA1420, regs={"eax": base + 0x40, "edx": base + 0x60, "esi": base + 0x70})
    return struct.unpack("<3f", sim.uc.mem_read(base + 0x70, 12))


def _garret4_feet_motion(windows, characters: bytes) -> list[float]:
    """How far garret4's roll_forward moves its m_feet forward over each
    clip window (t0, t1): the vanilla root-motion sampler 0xCACD0 run
    (L2) on garret4's body and clip from ``characters.xbr``."""
    sim, base = Sim(_vanilla("default.xbe")), 0x20000000
    sim.uc.mem_map(base, 0x1000000)
    for at, key in ((base + 0x100000, "characters/garret4"),
                    (base + 0x800000, "characters/garret4/roll_forward")):
        off, size = _clip(characters, key)
        sim.uc.mem_write(at, characters[off:off + size])
    sim.uc.mem_write(base, struct.pack("<I", base + 0x100000))   # the anim object's body
    node, out = sim.u32(0x1A9C5C), base + 0x40     # "m_feet", the node 0x8C630 samples
    motion = []
    for t0, t1 in windows:
        sim.call(0xCACD0, regs={"esi": out, "edi": base + 0x800000},
                 args=(base, node, *struct.unpack("<2I", struct.pack("<2f", t0, t1))))
        motion.append(sim.f32(out + 4))   # component 1, forward; 0 and 2 have no track
    return motion


def _x3_tick(xbe: bytes, attack: int, done: float, *, scale: float = 1.0,
             state: int = 0x100, anim: int | None = None, own: int = 0,
             bones: dict[int, tuple[float, float, float]] | None = None, extents: bool = False,
             own2: int = 0, slots: dict | None = None
             ) -> tuple[tuple[float, float], int, set[int], tuple[float, ...]]:
    """One tick of ``xbe``'s hook at 0x8C3B0, X3 (L2): attack column
    ``attack``, ``done`` of the way through its move (0.1 to 0.9 of the
    clip), PlayerControl state ``state``, on a critter of ``scale``
    playing anim ``anim`` (critter+0x200; by default the attack's own,
    0x52 + its column), whose m_damage critter_init cached at ``own``
    (critter+0x218) and its m_damage2 at ``own2`` (+0x21C), and whose
    anim object holds the runtime bones ``bones`` (index -> its matrix's
    translation). The shim must end by calling the staff-wall check with
    the PlayerControl. Returns the marker critter+0x218 points at after
    the tick, as (length, active), its VA, every VA the tick wrote, and
    its centre (with ``extents``, followed by its extents); ``slots``
    gets what +0x21C points at after it and that marker's (length,
    active)."""
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
    sim.uc.hook_add(UC_HOOK_MEM_WRITE, lambda uc, access, va, size, value, _:
                    written.update(range(va, va + size)))
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


ALL = "every column"


BUT_DOWN = "every column but down"


def _staff_sizes(fx: bytes, schema) -> tuple[dict, dict, dict]:
    """Under each staff end of ``fx.xbr``'s graphs, the size (the largest
    scale composed down from the end's children) of every mesh, with its
    end's child's name, and of every particle node, light and trail, by
    (graph, record), and each end's (end, bind name) pair -> the set of
    its (translation, scale)."""
    from azurkit.core.xbr.graph import bind_name, graphs

    meshes, kept, ends = {}, {}, {}
    for g, graph in enumerate(graphs(fx, schema)):
        kids: dict[int, list[int]] = {}
        for i in range(len(graph.recs)):
            if graph.parent(i) is not None:
                kids.setdefault(graph.parent(i), []).append(i)

        def walk(i: int, size: float, top: str) -> None:
            if schema.is_a(graph.types[i], "transform"):
                size *= max(map(abs, graph.xform_fields(i)["s"]))
            if graph.types[i] == "platform":
                meshes[g, i] = (graph.names[i], size, top)
            elif graph.types[i].startswith("p") or graph.types[i] in ("light", "polyTrail"):
                kept[g, i] = size
            for c in kids.get(i, ()):
                walk(c, size, top)

        for i, rec in enumerate(graph.recs):
            if graph.types[i] == "transform" and graph.names[i] in ("m_stafftop", "m_staffbottom"):
                xf = graph.xform_fields(i)
                ends.setdefault((graph.names[i], bind_name(graph.s, rec)), set()).add(
                    (tuple(xf["t"]), tuple(xf["s"])))
                for c in kids.get(i, ()):
                    walk(c, 1.0, graph.names[c])
    return meshes, kept, ends


def _head_places(fx: bytes, schema, whole: bool) -> dict[tuple, tuple[float, float, float]]:
    """Each particle node and trail under each staff end of ``fx.xbr``'s
    graphs, by (graph's offset, end, record): its place in the end's frame, or with
    ``whole`` in its parent's (the end's own transform too)."""
    from azurkit.core.xbr.graph import IDENTITY, graphs, mat_mul

    out = {}
    for graph in graphs(fx, schema):
        kids: dict[int, list[int]] = {}
        for i in range(len(graph.recs)):
            if graph.parent(i) is not None:
                kids.setdefault(graph.parent(i), []).append(i)

        def walk(i: int, m, end: str) -> None:
            if schema.is_a(graph.types[i], "transform"):
                m = mat_mul(m, graph.local(i)[0])
            elif graph.types[i] in ("pEmitter", "pBurstEmitter", "polyTrail"):
                out[graph.file_offset, end, i] = tuple(m[k][3] for k in range(3))
            for c in kids.get(i, ()):
                walk(c, m, end)
        for i in range(len(graph.recs)):
            if graph.types[i] == "transform" and graph.names[i] in ("m_stafftop", "m_staffbottom"):
                for c in kids.get(i, ()):
                    walk(c, graph.local(i)[0] if whole else IDENTITY, graph.names[i])
    return out


_MOVES = {8, 9, 12, 13, 14, 74}                      # walk, run, slide, both backwards, swim_2


_FILLED = {*range(1, 6), 8, 9, *range(12, 26), 27, 67, 70, 71, 72, 74}


_G4_LACKS = {6, 7, 26}                               # idle_5, idle_6, die_3


def _vase(slots: set[int], timed: bool) -> dict[int, tuple[str | None, bool]]:
    """town_female_4's expected slots: vasewalk for a move, else vaseidle."""
    return {i: (("vasewalk" if i in _MOVES else "vaseidle") if i in slots else None, timed and i in slots)
            for i in range(0x52)}


def _clip_lookup(sim: Sim, keys: dict[str, int]) -> None:
    """Stub species_clip_lookup's (0x4B600) callees in ``sim`` (L2): the
    asset registry 0xA5CA0 by ``keys`` (a case-folded name -> its handle,
    else -1) and the formatter 0x178C0; and the species load's sound
    binding 0x4B680 and 0xEB1B5."""
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


def _species_load(xbe: bytes, body: str, clips: dict[str, int], flags: int) -> dict[int, str | None]:
    """The base clip slots 0-0x51 the species load 0x4B8E0 gives a
    species of ``body`` with flags ``flags`` (0x20: the player's) in
    ``xbe`` (L2, :func:`_clip_lookup`), ``clips`` (a name under
    characters/<body>/ -> its handle) its clips: each slot's name, else
    ``None`` (-1)."""
    names = {handle: clip for clip, handle in clips.items()}
    sim, base = Sim(xbe), 0x20000000
    species_rec, name = base, base + 0x800
    sim.uc.mem_map(base, 0x10000)
    sim.uc.mem_write(name, body.encode() + b"\0")
    sim.uc.mem_write(species_rec + 4, struct.pack("<I", name))
    sim.uc.mem_write(species_rec + 0x64, struct.pack("<I", flags))
    _clip_lookup(sim, {f"characters/{body}/{clip}".casefold(): handle for clip, handle in clips.items()})
    sim.call(0x4B8E0, args=(species_rec,), until=0x4B977)
    return {i: names.get(h) for i, h in enumerate(struct.unpack("<82i", sim.uc.mem_read(species_rec + 0x124, 4 * 0x52)))}


def _garret4s(slots: set[int]) -> dict[int, tuple[str | None, bool]]:
    """garret4's clip baked onto the body's rig (g4/) in each of
    ``slots``, else empty."""
    return {i: ("g4/" + BASE_CLIPS[i] if i in slots else None, False) for i in range(0x52)}


def _x11_names(built: bytes) -> dict[int, str]:
    """X11's table in ``built``: each slot it fills and the clip name it holds."""
    table = resolve_va_to_file(built, trampoline_symbol_va(
        built, SLOTS_HOOK, SLOTS_TABLE, shim_source=SLOTS_SHIM.source_path()))
    names = built[table + 6 * 0x52:table + 6 * 0x52 + 2048]
    return {i: names[at - 1:names.index(b"\0", at - 1)].decode()
            for i, at in enumerate(struct.unpack_from("<82H", built, table)) if at}


def _attack_lookup(built: bytes, body: str, keys: dict[str, int], name: str, flags: int) -> int:
    """The handle the attacks_anims loader's lookup (its CALL at 0x7E3F0,
    X12's ATTACK hook in ``built``) gives a column naming ``name`` for a
    species of ``body`` with ``flags`` (0x20: the player's), the asset
    registry stubbed by name with ``keys`` (L2); -1 for none."""
    target = 0x7E3F5 + struct.unpack_from("<i", built, va_to_file(0x7E3F0) + 1)[0]
    sim, base = Sim(built), 0x20000000
    sim.uc.mem_map(base, 0x10000)
    sim.uc.mem_write(base + 0x800, body.encode() + b"\0")
    sim.uc.mem_write(base + 0x900, name.encode() + b"\0")
    sim.uc.mem_write(base + 4, struct.pack("<I", base + 0x800))
    sim.uc.mem_write(base + 0x64, struct.pack("<I", flags))
    _clip_lookup(sim, keys)
    sim.call(target, regs={"eax": base + 0x900, "edi": base + 0xA00}, args=(base,), until=l2._RETURN)
    return struct.unpack("<i", sim.uc.mem_read(base + 0xA00, 4))[0]


def _camera_points(built: bytes, flags: int, marker: tuple[float, float, float] | None = None,
                   rows=((None, 0.0, 0.0, 0.0),), margins: tuple[float, float] | None = None,
                   feet: tuple[float, float, float] | None = None, node: str = "m_feet",
                   swim: tuple[str, ...] = ()) -> list[tuple[tuple, bool]]:
    """Run ``built``'s CALL at 0x41F67 (the camera point's ``m_head``
    lookup, X8's hook) under Unicorn for a critter (EDI) of a species with
    ``flags`` (S+0x64) whose body has ``marker`` as its m_head (or no
    marker), once per row of ``rows`` in turn, on one critter: its
    controller (critter+0x180, the player's PlayerControl) in move state
    ``state`` (its +0x94; None: no controller), its +0x15C ``depth``
    under the water's surface (critter+0x27C), its ``scale``
    (critter+0x188) and its model origin (critter+0x1B0, where
    critter_model_matrix, 0x42200, puts it) ``origin`` metres above
    +0x15C (``margins``: X8's two swim margins, m, in place of the
    build's; ``feet``: the body's one marker is m_feet there instead, the
    critter's anim object +0x17C and its aligned node +0x1F8 ``node``;
    ``swim``: the body's markers are these, W27's m_root and m_eye, on
    the anim object, each row's fifth item their heights):
    per row the camera point it writes, and whether it returned as 0xCB2A0
    does (RET 4, EAX the out vector)."""
    at = va_to_file(0x41F67)
    target = 0x41F6C + struct.unpack_from("<i", built, at + 1)[0]
    sim, base = Sim(built), 0x20000000
    if margins:
        sim.uc.mem_write(trampoline_symbol_va(built, EYE_HOOK, "_player_model_swim_margin",
                                              shim_source=EYE_SHIM.source_path()), struct.pack("<2f", *margins))
    critter, species, anim, body, out, name, control, other = (base + k * 0x400 for k in range(8))
    sim.uc.mem_map(base, 0x2000 * 4)
    sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
    sim.uc.mem_write(critter + 0x18C, struct.pack("<4f", 0.0, 0.0, 0.0, 1.0))   # unturned
    sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
    sim.uc.mem_write(name, b"m_head\0")
    sim.uc.mem_write(anim, struct.pack("<4I", body, 0, 0, anim + 0x40))
    if marker or feet:   # the body's record (a self-relative name) and its runtime marker
        sim.uc.mem_write(other, node.encode() + b"\0")
        sim.uc.mem_write(other + 0x10, b"m_feet\0")
        sim.uc.mem_write(body + 0x18, struct.pack("<I", 1))
        sim.uc.mem_write(body + 0x80, struct.pack("<Ii", 6, (other + 0x10 if feet else name) - (body + 0x84)))
        sim.uc.mem_write(anim + 0x40, struct.pack("<I3f", body + 0x80, *(feet or marker)))
    if feet:
        sim.uc.mem_write(critter + 0x17C, struct.pack("<I", anim))
        sim.uc.mem_write(critter + 0x1F8, struct.pack("<I", other))
    for k, marked in enumerate(swim):   # records at body+0x80 on, 0xCB2A0's 0x34-byte runtime markers at anim+0x40 on
        sim.uc.mem_write(other + 0x20 + 0x10 * k, marked.encode() + b"\0")
        sim.uc.mem_write(body + 0x80 + 0x38 * k, struct.pack("<Ii", len(marked), other + 0x20 + 0x10 * k
                                                             - (body + 0x84 + 0x38 * k)))
        sim.uc.mem_write(anim + 0x40 + 0x34 * k, struct.pack("<I", body + 0x80 + 0x38 * k))
    if swim:
        sim.uc.mem_write(body + 0x18, struct.pack("<I", len(swim)))
        sim.uc.mem_write(critter + 0x17C, struct.pack("<I", anim))
    got = []
    for state, depth, scale, origin, *heights in rows:
        for k, z in enumerate(heights[0] if heights else ()):
            sim.uc.mem_write(anim + 0x44 + 0x34 * k, struct.pack("<3f", 0.0, 0.0, z))
        sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 0.0, 0.0, 10.0))
        sim.uc.mem_write(critter + 0x1B0, struct.pack("<3f", 0.0, 0.0, 10.0 + origin))
        sim.uc.mem_write(critter + 0x188, struct.pack("<f", scale))
        sim.uc.mem_write(critter + 0x27C, struct.pack("<f", depth))
        sim.uc.mem_write(critter + 0x180, struct.pack("<I", 0 if state is None else control))
        sim.uc.mem_write(control + 0x94, struct.pack("<I", state or 0))
        sim.uc.mem_write(out, struct.pack("<3f", 9.0, 9.0, 9.0))
        eax = sim.call(target, regs={"edi": critter, "ecx": anim, "eax": out},
                       args=(name,), until=l2._RETURN)
        got.append((struct.unpack("<3f", sim.uc.mem_read(out, 12)),
                    eax == out and sim.reg("esp") == l2._STACK_TOP - 0x100))
    return got


def _camera_point(built: bytes, flags: int,
                  marker: tuple[float, float, float] | None = None) -> tuple[tuple, bool]:
    """:func:`_camera_points` once, out of the water."""
    return _camera_points(built, flags, marker)[0]


BAKED_PROPS = {
    **dict.fromkeys((f"townspeople/female_{n}" for n in range(1, 5)), ("vase_joint",)),
    "water_elemental": ("blob_1_2", "blob_1_1", "blob_1_3", "blob_1_4", "blob_1_5", "blob_2_1", "blob_2_2",
                        "blob_2_3"),
}


def _staff_hits_walls(xbe: bytes) -> int:
    """The default ``xbe``'s cvar initialiser 0xFB9D0 gives ``combat/staff
    hits walls``: the third argument of its call of cvar_get_or_create
    (0x9F630) at 0xFB9E2."""
    sim = Sim(xbe)
    sim.call(0xFB9D0, until=0xFB9E2)
    esp = sim.reg("esp")
    assert sim.cstr(sim.u32(esp + 4)) == "combat/staff hits walls"
    return sim.u32(esp + 8)


def _seen(s: float, point: float, corner: tuple[float, float, float]) -> tuple[float, float, float]:
    """Where the level camera at rest, its rig at scale ``s``, sees
    ``corner`` (m from the drawn origin; x right, y the body's forward, z
    up): from behind at -30 degrees, the eye 5.11 x ``s`` m from the point
    ``point`` m over the origin, 70 degrees across at 4:3: its depth (m)
    and NDC x and y."""
    pitch, half = math.radians(30.0), math.tan(math.radians(35.0))
    ahead, up = (0.0, math.cos(pitch), -math.sin(pitch)), (0.0, math.sin(pitch), math.cos(pitch))
    eye = (0.0, -5.11 * s * ahead[1], point - 5.11 * s * ahead[2])
    rel = [c - e for c, e in zip(corner, eye)]
    depth = sum(r * a for r, a in zip(rel, ahead))
    return depth, rel[0] / (depth * half), sum(r * u for r, u in zip(rel, up)) / (depth * 0.75 * half)


def _regrow(xbe: bytes, distance: float, wanted: float) -> float:
    """The level camera's regrow (0x81952-0x81A04, the D-pad zoom at 0)
    in ``xbe`` under Unicorn, one 1/30 s tick of a camera ``distance`` m
    from its point that wants ``wanted`` m, with no stick held: its new
    distance (+0x19C)."""
    sim, camera = Sim(xbe), 0x20000000
    sim.uc.mem_map(camera, 0x1000)
    sim.uc.mem_write(camera + 0x19C, struct.pack("<f", distance))
    sim.uc.mem_write(camera + 0x1A4, struct.pack("<f", wanted))
    frame = [0] * 48                                            # the block's ESP + 4 ..
    frame[3] = camera                                           # [ESP + 0x10]: the camera
    frame[7] = struct.unpack("<I", struct.pack("<f", 0.0))[0]   # [ESP + 0x20]: the sticks' sum
    frame[46] = struct.unpack("<I", struct.pack("<f", 1 / 30))[0]   # [ESP + 0xBC]: dt
    sim.call(0x81952, regs={"ecx": camera}, args=tuple(frame), until=0x81A04)
    return sim.f32(camera + 0x19C)


def _held_regrow(xbe: bytes, distance: float, wanted: float, *, blocked: bool, state: int = 0, player: bool = True,
                 radius: float = 0.096) -> tuple[float, list[tuple[tuple[float, ...], tuple[float, ...], float]]]:
    """The regrow (as :func:`_regrow`) for the player's camera, its point 3 m
    over the centre and the camera 30 degrees over it behind, with the
    level's sweeps (collision_sweep, 0x60870) all ``blocked`` or clear and
    X19's sight landing holding the game's sweep ``radius``: the new
    distance, and each sweep's from, to and radius."""
    sim, base = Sim(xbe), 0x20000000
    camera, target, species, control, world = (base + 0x400 * k for k in range(5))
    sim.uc.mem_map(base, 0x2000)
    point = (0.0, 0.0, 3.0)
    for at, fmt, value in ((camera + 0x19C, "<f", distance), (camera + 0x1A4, "<f", wanted),
                           (camera + 0x15C, "<3f", (0.0, -4.0 * math.cos(math.radians(30)), 3.0 + 2.0)),
                           (camera + 0x154, "<I", world), (world + 0xAC, "<I", 0x5EE),
                           (camera + 0x190, "<I", target), (target + 0x178, "<I", species),
                           (species + 0x64, "<I", 0x24 if player else 0x04), (target + 0x180, "<I", control),
                           (control + 0x94, "<i", state), (target + 0x15C, "<3f", (0.0, 0.0, 0.0))):
        sim.uc.mem_write(at, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
    if verify_trampoline_patch(xbe, EYE_SIGHT_HOOK) == "applied":
        sim.uc.mem_write(trampoline_symbol_va(xbe, EYE_SIGHT_HOOK, "_player_model_sight_radius",
                                              shim_source=EYE_SWEEP_SHIM.source_path()), struct.pack("<f", radius))
    sweeps = []

    def sweep(uc, addr, size, _):   # collision_sweep: __stdcall(36), RET 0x24
        esp = sim.reg("esp")
        ret, tree, cam, zero, start, end, rxy = struct.unpack("<6If", uc.mem_read(esp, 28))
        assert (tree, cam, zero) == (0x5EE, camera, 0)
        sweeps.append((tuple(round(v, 4) for v in struct.unpack("<3f", uc.mem_read(start, 12))),
                       tuple(round(v, 4) for v in struct.unpack("<3f", uc.mem_read(end, 12))), round(rxy, 4)))
        uc.reg_write(UC_X86_REG_EAX, int(blocked))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 40)

    sim.uc.hook_add(UC_HOOK_CODE, sweep, begin=0x60870, end=0x60870)
    frame = [0] * 48                                            # the block's ESP + 4 ..
    frame[3] = camera                                           # [ESP + 0x10]: the camera
    frame[19:22] = struct.unpack("<3I", struct.pack("<3f", *point))   # [ESP + 0x50]: the point
    frame[46] = struct.unpack("<I", struct.pack("<f", 1 / 30))[0]     # [ESP + 0xBC]: dt
    kept = {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
    sim.call(0x81952, regs={"ecx": camera, **kept}, args=tuple(frame), until=0x81A04)
    assert {r: sim.reg(r) for r in kept} == kept
    return sim.f32(camera + 0x19C), sweeps


def _moved(built: bytes) -> set[int]:
    """The USA VAs of the swap's XBE sites (each shim hook, X15's sound
    names, X17's cvar default, X30's scale load, X21's radius reads, X25's
    rig) whose bytes in ``built`` (either release) aren't vanilla's."""
    sites = [*SHIM_HOOKS.items(), *((s.va, s.original) for s in (STAFF_WALLS, STAFF_X1)),
             *((s.va, s.original) for s in (*XBE_SOUND_SITES, *SEARCH_SITES, *RIG_SITES))]
    return {va for va, original in sites
            if (lambda _, off, vanilla: built[off:off + len(vanilla)] != vanilla)(*xbe_site(built, va, original))}


def _param(built: bytes, hook, shim, symbol: str) -> float:
    """The float param ``symbol`` of the shim ``hook`` installs in ``built``."""
    return struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, hook, symbol, shim_source=shim.source_path())))[0]


@pytest.mark.parametrize("species, mode, engine, data, rates, shims", [
    ("keylord", "garret4", {"body": "keylord"}, {}, ALL, {"X3", "X7"}),
    ("keylord", "own", {"body": "keylord", "scale": 2.0},   # W7 on garret4's calibration (Step 2.133)
     {"walkAnimSpeed": pytest.approx(1.431, abs=0.005), "runAnimSpeed": pytest.approx(2.061, abs=0.005),
      "walkSpeed": pytest.approx(5.241, abs=0.005)}, {"roll forward"}, {"X7"}),
    ("spideyzar", "own", {"body": "balthazar_spider", "scale": 1.5, "boundRadius": 2.25},
     {"walkAnimSpeed": 1.3, "runAnimSpeed": 1.3, "walkSpeed": pytest.approx(6.301, abs=0.005)},
     {"roll forward", "elemental2"}, {"X7"}),
    ("bot", "own", {"body": "bot"}, {"walkAnimSpeed": 1.0, "runAnimSpeed": 2.0,
                                      "walkSpeed": pytest.approx(3.665, abs=0.005)}, {"roll forward"}, {"X3", "X7"}),
    ("fire_shard", "own", {"body": "fire_shard"}, {"walkAnimSpeed": 1.0, "runAnimSpeed": 2.0,
                                                    "walkSpeed": pytest.approx(1.028, abs=0.005)}, ALL, {"X3", "X7"}),
    ("sleeth_x", "own", {"body": "water_lizardX", "scale": 2.5, "boundRadius": 3.75},
     {"walkAnimSpeed": pytest.approx(1.0, abs=0.005), "runAnimSpeed": 2.0, "walkSpeed": pytest.approx(4.384, abs=0.005)},
     {"roll forward"}, {"X7"}),
    ("gargoylestone", "own", {"body": "gargoylestone", "boundRadius": 1.8},
     {"walkAnimSpeed": 1.0, "runAnimSpeed": 2.0, "walkSpeed": pytest.approx(5.871, abs=0.005)}, set(), {"X3"}),
    ("magmar", "own", {"body": "magmar", "boundRadius": 3.0}, {"walkAnimSpeed": 1.0, "runAnimSpeed": 2.0,
                                                                "walkSpeed": pytest.approx(9.953, abs=0.005)},
     BUT_DOWN, {"X7"}),
])
def test_each_gameplay_mode_writes_its_own_attributes(species, mode, engine, data, rates, shims):
    """D112 (mechanism B), D219, D225 (Step 2.65): the player keeps
    species garret4 (``ai`` and ``other features`` = player, so its
    PlayerControl and flag 0x20), and only garret4's cells read new
    values; the species' own and every other cell stay vanilla. Each
    gameplay mode writes its own set:

    - garret4's exact (D131's standardize): only the body cell in
      critters_engine (garret4's scale and bounds), every attacks_anims
      Rate (each move in garret4's time), X3 (garret4's hit box) and X7;
    - own body (the default): the species' scale, and bounds widened to
      its boundRadius x scale when that passes garret4's 1.5 (sleeth_x:
      1.5 x 2.5; keylord's 0.5 x 2 doesn't), its stride (W7), garret4's
      walkSpeed x sqrt(s) at its size s (Step 2.145, D422), the roll's
      Rate (garret4's time), the Rate of each attack whose damage window
      opened later than 1.0 s (spideyzar's elemental2, deathbeam: the W5
      band, its window opening by 1.0 s at the new Rate; magmar's every
      column but down, whose attack_1 turns its marker's active part on at
      t 0 and its length only at 1.63 s, the window's opening by the
      damage pass's rule: Step 2.104, AZ-524; every column of
      fire_shard, whose one-tick clips ended each move before X3's window
      could hit, xemu 2.75b S2: garret4's time, Step 2.103, AZ-494), X7, and X3 only
      for the attacks whose clip has no damage window (Step 2.64) and
      those whose own box fails the reach test (Step 2.69: every column
      of bot, whose 1.11 m box made no contact in sitting p8; since X13's
      fill, Step 2.132, no box high or far off: spideyzar's jump attack,
      a 6.2 m box that stays 1.29 m up, and sleeth_x's attack clip, 5.6 m
      staying 0.77 m up, keep their own).

    A body with no clips (gargoylestone) keeps attacks_anims as it was,
    and X3 gives garret4's clips, played as timers, his hit box and
    window for each (Step 2.67; Step 2.75e). Garret's sounds here: the
    model's own write sound cells too (Step 2.72, the sounds test). characters.xbr and index.xbr change only
    on a body the bake serves (keylord's since Step 2.88), on a body with
    no clips, whose timers it bakes in every mode
    (Step 2.89), on a body with a clip that switches on its own damage
    field, whose W17 copy it adds in every mode (Balthazar, Step 2.75e),
    and on a body with a victory-like clip, whose victory copies it adds
    in every mode (spideyzar's, bot's, sleeth_x's, magmar's; Step 2.121);
    not on fire_shard, which has none, but for index.xbr's record of X32's
    flash on a body X32 serves (fire_shard's, Step 2.180, D700). Where X36 lands (own body, with
    clips) attacks_transitions' combo rows 28-31 keep their target
    features under the default chain, "hit" (D1045; Modkit's Step 2.153 dropped them, D432, as chain "any" does:
    ``test_characters.py``'s combo test)."""
    game = _swap(species, mode=mode, sounds="garret4")
    vanilla = _vanilla("gamedata/config.xbr")
    before, after = _cells(vanilla), _cells(game["config.xbr"])
    changed = {key for key in before if before[key] != after[key]}
    cols = {table: XbrDocument.from_bytes(vanilla).keyed_section(table).col_names()
            for table in ("critters_engine", "critters_critter_data", "attacks_anims")}
    garret4 = {t: f"{cols[t].index('garret4')}:garret4" for t in ("critters_engine", "critters_critter_data")}
    want = {**{("critters_engine", garret4["critters_engine"], row): v for row, v in engine.items()},
            **{("critters_critter_data", garret4["critters_critter_data"], row): v for row, v in data.items()}}
    xbe = bytes(game["default.xbe"])
    added = engine["body"].casefold() in {*BAKED_BODIES, *VICTORY_CLIPS} or species == "gargoylestone"
    flash = verify_trampoline_patch(xbe, HIT_FX_HOOK) == "applied"

    assert sorted(set(game.changed()) - {"default.xbe"}) == [
        *(["gamedata/characters.xbr"] if added else []), "gamedata/config.xbr", "gamedata/fx.xbr",
        *(["gamedata/index/index.xbr"] if added or flash else [])]
    assert {key for key in changed if key[0] not in ("attacks_anims", "attacks_transitions")} == set(want)
    assert {key for key in changed if key[0] == "attacks_transitions"} == set()   # the default chain "hit" (D1045)
    assert {key: after[key] for key in want} == {
        key: (2, None, v) if isinstance(v, str) else (1, v, None) for key, v in want.items()}
    assert {col.split(":", 1)[1] for table, col, row in changed
            if (table, row) == ("attacks_anims", "Rate")} == (
        set(cols["attacks_anims"]) if rates == ALL else set(cols["attacks_anims"]) - {"down"} if rates == BUT_DOWN
        else rates)
    for row in ("ai", "other features"):
        assert after["critters_engine", garret4["critters_engine"], row][2] == "player"
    assert {x for x, hook in (("X3", DAMAGE_MARKER), ("X7", HIT_HOOK))
            if verify_trampoline_patch(xbe, hook) == "applied"} == shims
    if mode == "own" and rates:
        characters = _vanilla("gamedata/characters.xbr")
        anims, was = (XbrDocument.from_bytes(c).keyed_section("attacks_anims") for c in (game["config.xbr"], vanilla))
        body, his = read_body(characters, engine["body"]), read_body(characters, "garret4")
        x3 = _x3_param(xbe, "columns") if "X3" in shims else 0
        for i, col in enumerate(anims.col_names()):
            if col == "roll forward" or (rates not in (ALL, BUT_DOWN) and col not in rates) or (
                    rates == BUT_DOWN and col == "down"):
                continue
            clip, rate = anims.find_cell(col, "Anim", i).string_value, anims.find_cell(col, "Rate", i).double_value
            vanilla_rate, window = was.find_cell(col, "Rate", i).double_value, move_window(anims, i)
            windows = None if x3 >> i & 1 else damage_windows(characters, body.name, clip)
            if attack_move(vanilla_rate, body.length(clip), window, windows).hits == 0:   # over before it hits
                assert rate == pytest.approx(standard_rate(
                    vanilla_rate, body.length(clip), his.length(was.find_cell(col, "Anim", i).string_value)))
                assert attack_move(rate, body.length(clip), window, windows).hits >= 1, col
                continue
            late = windup(rate, body.length(clip), window, windows)
            assert math.isclose(late * (1 + RATE_MARGIN), WINDUP_MAX, rel_tol=1e-9), col


@pytest.mark.parametrize("species, walk, run", [
    ("balthazar", 0.924, 3.792), ("keylord", 1.431, 2.061), ("air_elemental", 4.0, 7.0),
    ("town_female_1", 0.643, 5.0)])
def test_a_worn_bodys_walk_and_run_clips_keep_pace_with_the_ground_as_garret4s_do(species, walk, run):
    """AZ-610 (Step 2.133, D342; the owner on Balthazar: "his running
    animation looks like he is running faster than he actually is"): the
    walk and run clips play at the speed over (the drawn scale x
    walkAnimSpeed or runAnimSpeed) (0x30D90), and garret4's cells are 2.00 x
    and 1.48 x his clips' stance foot speed, but W7 wrote the species' own,
    Balthazar's 2.5 his own run's (2.56 units/s), so his run played at
    2.88 against garret4's 1.33. W7 now writes the stride of the clip each
    slot plays (its feet's backward speed in their stance) on garret4's
    calibration: Balthazar 0.924 and 3.79 (his run at 7.2 m/s 1.90),
    keylord 1.431 and 2.061; a floating body's feet plant nowhere
    (air_elemental: its own 4.0 and 7.0), and a slot playing a stand-in
    keeps the species' cell (town_female_1's run slot plays its walk: 5.0)."""
    game = _swap(species, sounds="garret4")
    data = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("critters_critter_data")
    cells = [data.find_cell("garret4", prop, None).double_value for prop in ("walkAnimSpeed", "runAnimSpeed")]
    assert cells == [pytest.approx(walk, abs=0.005), pytest.approx(run, abs=0.005)]


def test_a_model_whose_roll_clip_has_no_root_motion_rolls_garret4s_roll():
    """AZ-284, X4 (Step 2.21b): the roll travels by its clip's m_feet root
    motion (player_attack_root_motion 0x8C630 samples it through 0xCACD0),
    and no body but garret4's has a roll clip that moves it, so a model's
    roll ended without moving (xemu sitting swapb: flicken 0.003 m,
    garret4 3.05 m). A model whose roll clip doesn't move m_feet
    (flicken's run) gets a shim on the sampler's CALL at 0x8C6AE, well
    formed (L1); garret4 writes no default.xbe byte, and a body with no
    clips (gargoylestone) keeps the sampler's CALL. Under L2 the flicken
    build's roll (own body: W5's garret4 time) lasts his 21 ticks, and
    each tick moves as far forward as garret4's roll_forward
    moves m_feet over the same fraction of its clip (the game's own
    sampler on garret4's clip), with no vertical motion; basic1 still
    samples its own clip."""
    vanilla = _vanilla("default.xbe")
    game = _swap("flicken", mode="own")
    built = bytes(game["default.xbe"])
    at = va_to_file(ROLL_HOOK_VA)
    target = ROLL_HOOK_VA + 5 + struct.unpack_from("<i", built, at + 1)[0]
    _, sections = parse_xbe_sections(vanilla)

    assert built[at] == 0xE8 and not any(
        s["vaddr"] <= target < s["vaddr"] + s["vsize"] for s in sections)
    assert l1.check(vanilla, built) == []
    assert "default.xbe" not in _swap("garret4").changed()
    assert bytes(_swap("gargoylestone")["default.xbe"])[at:at + 5] == vanilla[at:at + 5]

    characters = _vanilla("gamedata/characters.xbr")
    run, roll = (struct.unpack_from("<f", characters, _clip(characters, key)[0] + 0x10)[0]
                 for key in ("characters/flicken/run", "characters/garret4/roll_forward"))
    anims = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("attacks_anims")
    rate = _f32(anims.find_cell("roll forward", "Rate", anims.col_names().index("roll forward")).double_value)
    flicken = PlayerSim(built, replace(ROLLER, clip_length=run, attack_rate=rate)).roll()
    windows, t, dt = [], _f32(run * _f32(0.1)), _f32(1 / 30)   # Move start 0.1 to end2 1.0
    while t < run:
        windows.append((t, _f32(t + rate * dt)))
        t = windows[-1][1]
    scale = _f32(roll / run)
    want = _garret4_feet_motion([(_f32(a * scale), _f32(b * scale)) for a, b in windows], characters)
    heading = [d / math.hypot(*flicken.displacement) for d in flicken.displacement]
    got = [(v[0] * heading[0] + v[1] * heading[1]) / 30.0   # 0x8C630 multiplies by [0x1A2650]
           for v in flicken.desired]

    assert (flicken.ticks, len(windows)) == (21, 21)
    assert all(math.isclose(g, w, abs_tol=1e-6) for g, w in zip(got, want)), (got, want)
    assert flicken.vz == (0.0,) * 21
    assert (PlayerSim(built, replace(BASIC1, clip_length=run)).roll()
            == PlayerSim(vanilla, replace(BASIC1, clip_length=run)).roll())


@pytest.mark.parametrize("species", ["flicken", "overlord and golem", "catalisk"])
def test_garret4s_exact_and_own_mode_roll_in_garret4s_time(species):
    """D131 (Step 2.23b), D225 (Step 2.65): in garret4's exact mode a
    move lasts its window times its clip's length over Rate, so each
    attacks_anims column's clip length over its Rate is garret4's own,
    shorter by 1 part in 10^4 (RATE_MARGIN). So under L2 the roll lasts
    garret4's 21 ticks there and in own mode (its roll Rate is the same;
    golem's exact length ratio rolled 22 for float rounding; the overlord's
    golem, golem_ol, is the unbaked golem rig since the bake serves golem's,
    Step 2.134a), and X4 moves it
    garret4's whole roll_forward distance (the game's own sampler on
    garret4's clip, Move start 0.1 to end2 1.0)."""
    characters = _vanilla("gamedata/characters.xbr")
    built = {mode: _swap(species, mode=mode) for mode in ("garret4", "own")}

    def plays(config: bytes, body: str) -> list[float]:
        """How long each attacks_anims column's clip plays at its Rate, s."""
        anims, model = (XbrDocument.from_bytes(config).keyed_section("attacks_anims"),
                        read_body(characters, body))
        clip, rate = (anims.row_names().index(row) for row in ("Anim", "Rate"))
        return [model.length(anims.read_cell(i, clip).string_value)
                / anims.read_cell(i, rate).double_value for i in range(len(anims.col_names()))]

    body = XbrDocument.from_bytes(built["garret4"]["config.xbr"]).keyed_section(
        "critters_engine").find_cell("garret4", "body", None).string_value
    garret4 = plays(_vanilla("gamedata/config.xbr"), "garret4")
    assert all(math.isclose(s * (1 + RATE_MARGIN), g, rel_tol=1e-12)
               for s, g in zip(plays(built["garret4"]["config.xbr"], body), garret4))

    def roll(game) -> tuple[float, float]:
        anims = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("attacks_anims")
        clip, rate = (anims.read_cell(anims.col_names().index("roll forward"),
                                      anims.row_names().index(row)) for row in ("Anim", "Rate"))
        return read_body(characters, body).length(clip.string_value), rate.double_value

    rolls = {mode: PlayerSim(bytes(game["default.xbe"]), replace(
                 ROLLER, clip_length=roll(game)[0], attack_rate=roll(game)[1])).roll()
             for mode, game in built.items()}
    g4 = read_body(characters, "garret4").length("roll_forward")
    whole = _garret4_feet_motion([(_f32(g4 * _f32(0.1)), g4)], characters)[0]

    assert {mode: r.ticks for mode, r in rolls.items()} == {"garret4": 21, "own": 21}
    assert math.isclose(math.hypot(*rolls["garret4"].displacement), whole, rel_tol=1e-5)
    assert rolls["own"] == rolls["garret4"]


@pytest.mark.parametrize("species, graded", [("harvester", True), ("sleeth_x", False)])
def test_a_builds_status_is_unseen_in_each_mode_no_sitting_graded(species, graded, monkeypatch):
    """D131 (Step 2.23b), Steps 2.65 and 2.74, D242 (Step 2.75b's sitting
    S4): a mode's status comes from a sitting of that mode's own build, or
    of the partner whose ISO it builds there. A species no sitting graded
    in a mode is "unseen" there in every mode, though the graded table
    holds it (harvester, green): the table graded the model's own D112
    build (its own scale and clip speed, garret4's stride, walk speed and
    hit time), which no mode builds exactly, so its note no longer shows.
    A species the table doesn't hold (on the vanilla disc only the 73 items
    since Step 2.40 and D260, so sleeth_x is dropped from it here) is red, "untested", in
    garret4's exact and own body: graded on nothing. Each is dropped from
    every mode's grades and shares here."""
    if not graded:
        monkeypatch.delitem(SUPPORT, species, raising=False)
    for mode in MODES:
        monkeypatch.delitem(MODE_GRADES[mode, "own"], species, raising=False)
        monkeypatch.delitem(MODE_SHARES[mode, "own"], species, raising=False)
    lines = {mode: [n for n in sdk.image({"iso": str(_IMAGES[VANILLA_ISO]), "packs": {}, "character": {
        "species": species, "mode": mode}})[1]["notes"] if n.startswith("Player model status:")][-1] for mode in MODES}

    unseen, untested = f"Player model status: {UNSEEN[0]} ({UNSEEN[1]})", "Player model status: red (untested)"
    assert lines == {"garret4": unseen if graded else untested, "own": unseen if graded else untested}


@pytest.mark.parametrize("species, top, bottom, kind", [
    ("balthazar", "left_w", "right_w", "hand"),          # the rig's names are mirrored
    ("keylord", "right_hand", "left_hand", "hand"),
    ("golem", "hand_left_1", "hand_left_1", "hand"),     # hand_right_1 can't fit in m_stafftop
    ("firedrake", "m_stafftop", "m_staffbottom", "point"),  # no hand: where it hits
    ("flicken", "m_stafftop", "m_staffbottom", "point"),   # nor m_damage: its chest
    ("town_male_farmer_1", "joint74", "joint97", "hoe"),                  # W26: the hoe's ends (D338)
])
def test_the_staffs_particles_come_from_the_bodys_action_point_with_its_blades_hidden(
        species, top, bottom, kind):
    """Step 2.24f (the owner on X.29's balthazar: "when we use elements ...
    the particle effects appear far to the side of us"): the staff fx's
    two ends (60 transforms in 30 graphs) bind by name to garret4's staff
    bones (0x62A20 → 0xCA1D0), so on another body they stayed at
    garret4's bind pose, 3 m to the side, and W4's 0.001 scale hid the
    blades but not the particles. W6 binds the top end to the body's
    right hand and the bottom end to its left (a hand or wrist bone; an
    end whose bone's name can't fit takes the other's), and since the bind
    then writes the bone's scale over W4's, shrinks the staff's blades
    under each end instead (Step 2.182, D707: the 62 meshes under an end's
    child named Blade*, a thousandth of their head's size, while the
    element meshes show at it; on the hands fx_staff_smash's force
    ring and ring cores hide too, their scale links' factors x0.001, F4).
    A body with no hand (D219, Step 2.64) keeps both ends unbound, with
    the same blades shrunk. Where its heads go is the next test's."""
    from azurkit.core.xbr.graph import Schema, graphs

    schema = Schema(_vanilla("default.xbe"))
    vanilla = _vanilla("gamedata/fx.xbr")
    built = bytes(_swap(species)["fx.xbr"])
    meshes, kept, ends = _staff_sizes(built, schema)
    plain, vanilla_kept, _ = _staff_sizes(vanilla, schema)

    assert len(staff_scales(vanilla)) == 60
    assert set(ends) == {("m_stafftop", top), ("m_staffbottom", bottom)}
    assert kept.keys() == vanilla_kept.keys()
    shown = {k: size for k, (_, size, _) in plain.items() if size > 0.0015}   # in vanilla
    hidden = {k for k, size in shown.items() if meshes[k][1] < 0.01 * size}
    assert hidden == {k for k in shown if plain[k][2].startswith("Blade")} and len(hidden) == 62

    def rings(fx: bytes) -> dict:
        return {(g, lk.src, n): lk.factor for g, graph in enumerate(graphs(fx, schema)) for i in range(len(graph.recs))
                for n, lk in enumerate(graph.links(i)) if lk.dst_plug in (7, 8, 9)
                and (graph.names[lk.dst] or "").startswith(("ForceRing", "RingCore"))}
    assert rings(vanilla) and rings(built) == pytest.approx({k: f * (0.001 if kind == "hand" else 1.0) for k, f in rings(vanilla).items()})
    if kind != "point":
        characters = _vanilla("gamedata/characters.xbr")
        body = XbrDocument.from_bytes(_vanilla("gamedata/config.xbr")).keyed_section(
            "critters_engine").find_cell(species, "body", None).string_value
        assert {top, bottom} <= {name for name, _ in read_body(characters, body).bones}


def test_the_power_heads_sheath_the_fist_lie_along_the_hoe_and_stand_clear_of_a_handless_body():
    """Step 2.182 (D703; the owner: "for models that don't use the axion
    ... the effect itself is still shaped to the axion though, can it be
    reshaped for the weapon that model uses?"; D707, his pick from the
    sheet, "B gauntlet"): on every weapon but the Axion staff each staff
    end's head is mapped by A = T(p) . RA . s . T(-h u) in its end's frame:
    on town_male_6's fists the end at the wrist, x0.45; along the farmer's
    hoe x0.6 from the blade's inner edge and a x0.2 cap at its handle's end
    (F2: x0.6 covered his hands); at flicken's point both heads centred
    upright, x0.20, over its mesh's top (F1: at its chest point they sat
    inside it), and fire_shard's past its mesh's front, where its hit
    landed inside it; firedrake's, where its bite lands at z 0.04, lifted
    until their lower end is on the floor, the model's origin (Step
    2.202, M11: 0.48 m under it).  Every emitter and trail lands where A
    puts its vanilla place (within 1 mm): the fists' within 0.4 m of the
    wrist where the Axion's reach 0.75 m past the end, the handle end's
    within 0.17 m of it, flicken's above its crest; each trail keeps
    vanilla's lineLength, which 0x7C1A0 lays along its node's scaled z
    axis (M11: x the head's size drew it the size squared); each of the
    10 rotateZ spins turns about the fist's axis; the sprites of the pools the ends feed outside them x0.8, those
    inside kept, but at the point alone all of them and the forces of those
    outside take the head's size (fire3's smoke rises at 1.4 x 0.20 m/s2,
    its sprites and its satellites' x0.20: in xemu full-size sprites crowded
    into the small head blew out white under a blue haze of smoke); a child
    linked in translation refuses the build (R2)."""
    import numpy as np

    from azurkit.tools.characters.characters import mesh_bounds
    from azurkit.tools.characters import _player_power_fx as power
    from azurkit.core.xbr.graph import Euler, Schema, graphs

    xbe = _vanilla("default.xbe")
    schema, euler = Schema(xbe), Euler(xbe)
    assert [*(schema.types["pRendererB"].attrs[k] for k in power.SIZES),
            *(schema.types["pAccelerator"].attrs[k] for k in power.MAGNITUDES)] == [
        "size1", "size2", "nearMagnitude", "farMagnitude"]
    line = schema.types["polyTrail"].attrs.index("lineLength")
    plain = _vanilla("gamedata/fx.xbr")
    characters = _vanilla("gamedata/characters.xbr")
    hidden = bytearray(plain)
    for at in staff_scales(plain):   # W4, which a handless body's ends come from
        hidden[at:at + 12] = struct.pack("<3f", 0.001, 0.001, 0.001)
    hands, hull, tall = ("right_hand", "left_hand"), mesh_bounds(characters, "flicken"), read_body(characters, "flicken").top
    point = power.point_shape((0.0, 0.134, 0.472), False, tall / read_body(characters, "garret4").top, hull, tall)
    shard = read_body(characters, "fire_shard")   # where its hit lands is inside its mesh: past its front
    hit, box = action_point(characters, shard, []).point, mesh_bounds(characters, "fire_shard")
    clear = power.point_shape(hit, True, shard.top / read_body(characters, "garret4").top, box, shard.top)
    assert hit[1] < box[1][1] and clear.heads["m_stafftop"].at == pytest.approx(
        (hit[0], box[1][1] + power.CLEAR * clear.forces, max(hit[2], power.CLEAR * clear.forces)))
    drake = read_body(characters, "firedrake")   # its bite at z 0.04: the heads' lower end lifted onto the floor
    bite = action_point(characters, drake, list(drake.damage_clips[:1])).point
    low = power.point_shape(bite, True, drake.top / read_body(characters, "garret4").top,
                            mesh_bounds(characters, "firedrake"), drake.top)
    assert bite[2] < power.CLEAR * low.forces and low.heads["m_stafftop"].at == pytest.approx(
        (bite[0], bite[1], power.CLEAR * low.forces))
    cases = {"hand": (power.hand_shape(characters, "townspeople/male_6", hands), plain,
                      lambda fx, shape: follow_hands(fx, hands, shape, euler)),
             "hoe": (power.hoe_shape(characters, weapons()["farmers_hoe"].prop, 1.0), plain,
                     lambda fx, shape: follow_hands(fx, ("joint74", "joint97"), shape, euler)),
             "point": (point, bytes(hidden), lambda fx, shape: at_point(fx, shape, euler))}
    toc = parse_toc(plain)
    names = {toc[i].file_offset: n.rsplit("/", 1)[-1] for i, n in named_resources(plain).items()}

    def attr(fx: bytes, typ: str, k: int) -> dict:
        return {(gr.file_offset, i): gr.attrs(i)[k] for gr in graphs(fx, schema) for i in range(len(gr.recs))
                if gr.types[i] == typ}
    before, smoke = _head_places(plain, schema, False), attr(plain, "pAccelerator", 5)
    sprite = attr(plain, "pRendererB", power.SIZES[1])
    rec = {(gr.file_offset, i): gr.names[i] for gr in graphs(plain, schema) for i in range(len(gr.recs))}
    for kind, (shape, start, build) in cases.items():
        doc = XbrDocument.from_bytes(start)
        build(doc, shape)
        after = _head_places(bytes(doc.raw), schema, kind == "point")
        lengths = attr(bytes(doc.raw), "polyTrail", line)
        assert after.keys() == before.keys() and len(after) > 300
        for (g, end, i), was in before.items():
            head = shape.heads[end]
            out = np.array((0.0, 0.0, 1.0 if end == "m_stafftop" else -1.0))
            h = power.HEAD_CENTRES.get(names[g], 0.0) if head.centred else 0.0
            now = np.array(after[g, end, i])
            assert np.linalg.norm(now - head.at - head.size * np.array(head.turn) @ (np.array(was) - h * out)) < 1e-3
            assert {"hand": np.linalg.norm(now - head.at) < 0.4, "point": now[2] > hull[1][2],
                    "hoe": end == "m_stafftop" or np.linalg.norm(now) < 0.17}[kind], (kind, names[g], end, i)
        assert lengths == attr(plain, "polyTrail", line) and lengths
        forced = {(names[g], i): f / smoke[g, i] for (g, i), f in attr(bytes(doc.raw), "pAccelerator", 5).items()
                  if f != smoke[g, i]}
        assert all(r == pytest.approx(point.forces) for r in forced.values())
        assert {n for n, _ in forced} & {"fx_staff_fire3"} == ({"fx_staff_fire3"} if kind == "point" else set())
        fire = {rec[k]: v / sprite[k] for k, v in attr(bytes(doc.raw), "pRendererB", power.SIZES[1]).items()
                if names[k[0]] == "fx_staff_fire3" and sprite[k]}
        assert fire["Smoke_pRendererShape"] == pytest.approx(shape.sprites) and fire[
            "Satellite_pRendererShape"] == pytest.approx(shape.sprites if kind == "point" else 1.0)   # inside
        if kind == "hand":
            spins = [lk.dst_plug for graph in graphs(bytes(doc.raw), schema) for lk in graph.all_links()
                     if graph.parent(lk.dst) is not None and graph.names[graph.parent(lk.dst)] in (
                         "m_stafftop", "m_staffbottom") and lk.dst_plug in (4, 5, 6)]
            assert sorted(spins) == [4] * 10   # rotateZ about the staff, now rotateX about the fist
    broken = bytearray(plain)   # water3's ball spin linked on translateX instead
    graph = next(gr for gr in graphs(plain, schema) if "public_WaterBallTop" in gr.names)
    src, n = next((lk.src, k) for gr in [graph] for i in range(len(gr.recs)) for k, lk in enumerate(gr.links(i))
                  if gr.names[lk.dst] == "public_WaterBallTop")
    struct.pack_into("<H", broken, graph.file_offset + graph.list_at(src, 0x10)[0] + 24 * n + 0x10, 1)
    with pytest.raises(ValueError, match=r"public_WaterBallTop is linked in translation.*\(R2\)"):
        follow_hands(XbrDocument.from_bytes(bytes(broken)), hands, cases["hand"][0], euler)


def test_every_usable_body_has_one_action_point_its_hand_else_its_hit_else_its_chest():
    """D219 (Step 2.64): one action point per body, shared by its element
    effects (W6) and X3's hit box, so what you see is where it hits: its
    hand bones (W6's pick, 53 of the 76 graded bodies but garret4's; X3
    follows the top end's, the model's right hand), else where its
    m_damage hits (its basic1 clip's damage window's middle: 11 bodies;
    bound by name the marker would rest at the body's origin outside its
    windows and give the particles its extents as their scale), else in
    front of its chest, (0, 0.4 m x its height over garret4's, 0.7 x its
    height) in model units (12, and each of the 59 item bodies, offered
    since D260)."""
    config = _vanilla("gamedata/config.xbr")
    characters = _vanilla("gamedata/characters.xbr")
    columns = XbrDocument.from_bytes(config).keyed_section("attacks_anims").col_names()
    points = {}
    for name in {m.body.casefold() for m in player_models(config, characters)
                 if m.status != "refused"} - {"garret4"}:
        body = read_body(characters, name)
        points[name] = action_point(characters, body, substitutes(columns, body) if body.clips else [])

    assert Counter(p.kind for p in points.values()) == {"hand": 53, "marker": 11, "chest": 71}
    assert points["balthazar_airship"] == ActionPoint("hand", ("left_w", "right_w"), 70)
    assert (points["firedrake"].kind, points["firedrake"].point) == (
        "marker", pytest.approx((0.0, 1.775, 0.037), abs=0.001))
    top = read_body(characters, "flicken").top / read_body(characters, "garret4").top
    assert (points["flicken"].kind, points["flicken"].point) == (
        "chest", pytest.approx((0.0, 0.4 * top, 0.7 * read_body(characters, "flicken").top)))


def test_a_body_whose_clips_switch_no_damage_marker_on_gets_garret4s_hit_box_mid_attack():
    """D112, AZ-284: a hit needs the body's m_damage marker switched on
    by the attack clip, so a flicken player never hit (sitting swapb: 0
    target queries over 172 attack ticks). For such a body the swap hooks
    X3 at the CALL of the staff-wall check at 0x8C3B0: each tick it points
    critter+0x218 at garret4's attack box, on from 20% to 50% of an
    attack move (never the roll), then calls the check with the
    PlayerControl. The box is divided by the critter's scale, which the
    damage pass multiplies back, so it stays garret4's size on any model
    (a x2 model's marker length is 0.25). The build is well formed (L1:
    the shim's one packed SSE operand lands 16-byte aligned). garret4
    keeps the vanilla default.xbe (which modes give a body with its own
    damage clips X3: ``test_each_gameplay_mode_writes_its_own_attributes``)."""
    assert _swap("garret4").changed() == {}
    xbe = bytes(_swap("flicken")["default.xbe"])
    assert verify_trampoline_patch(xbe, DAMAGE_MARKER) == "applied"
    assert l1.check(_vanilla("default.xbe"), xbe) == []
    assert [_x3_marker(xbe, 0, done) for done in (0.1, 0.35, 0.6)] == [
        (0.5, 0.0), (0.5, 1.0), (0.5, 0.0)]
    assert _x3_marker(xbe, 20, 0.35) == (0.5, 0.0)
    assert _x3_marker(xbe, 0, 0.35, scale=2.0) == (0.25, 1.0)


def test_a_hit_that_interrupts_an_attack_leaves_x3s_damage_marker_off():
    """AZ-295: the hit handler 0x8D600 sets state 0x102, which has X3's
    attack bit 0x100, and leaves the interrupted attack's column at
    +0x134, so X3 switched a flicken player's marker on again 4-7 ticks
    into the hit reaction (xemu sitting modelswap2: 4 of its 8 fight
    hits, with damage queries and one credited HP drop). The reaction
    plays through 0x42750, which records its anim, 37-42 (ouch_1 to
    ouch_1b), at critter+0x200, where an attack's player_attack_enter
    (0x88990, through anim_change 0x42910) records 0x52 + its column:
    X3 keeps the marker off while a hit reaction plays, mid-window on a
    ground attack (column 0) and a jump attack (13, itself state 0x102),
    which still switch it on."""
    xbe = bytes(_swap("flicken")["default.xbe"])
    for attack in (0, 13):
        assert _x3_marker(xbe, attack, 0.35, state=0x102) == (0.5, 1.0)
        assert [_x3_marker(xbe, attack, 0.35, state=0x102, anim=hit)[1]
                for hit in range(37, 43)] == [0.0] * 6


def test_a_swapped_body_hit_on_the_ground_recovers_in_garret4s_hit_time():
    """AZ-291: the player's hit handler (0x8D600) plays the hit reaction
    the chooser 0x30BD0 picks (anim 37-42: ouch_1, ouch_2, ouch_3 by the
    damage, then ouch_1r / _1l / _1b by the direction, each the first the
    body has, named by the XBE's base clip table and resolved per body)
    through 0x42750 at rate 1, and on the ground the player has no control
    until that clip ends: about 30 ticks per second of the body's own clip
    (sitting modelswap: keylord 63 ticks on its 2.07 s ouch_2, garret4
    13-32 on its 0.4 s clips). A swapped body's build hooks that CALL
    (0x8D682; L1 well formed): whatever the chooser picked, the hit plays
    the body's ouch_1 (garret4 plays only ouch_1 and its directional
    twins), else its idle, else the clip its roll plays (W3), at the rate
    that ends it in garret4's 0.4 s, 12 ticks; the species' clip slots
    are left as they were. garret4 and a body with no clips write no
    default.xbe byte (the roll test above)."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap("keylord")["default.xbe"])
    at = va_to_file(0x8D682)
    target = 0x8D687 + struct.unpack_from("<i", built, at + 1)[0]
    _, sections = parse_xbe_sections(vanilla)
    characters = _vanilla("gamedata/characters.xbr")

    def seconds(key: str) -> float:
        return struct.unpack_from("<f", characters, _clip(characters, key)[0] + 0x10)[0]

    def hit(slots: dict[int, float], index: int) -> tuple[int, float, bool]:
        """Run the hooked CALL for a hit the chooser gave ``index``, on a
        species whose clip slots ``slots`` maps to clip lengths: the slot
        0x42750 played, its layer's rate and whether the slots are as
        they were."""
        sim, base = Sim(built), 0x20000000
        critter, species, anim, clips = base, base + 0x1000, base + 0x2000, base + 0x3000
        table = [-1] * 0x71
        sim.uc.mem_map(base, 0x10000)
        for i, (slot, length) in enumerate(slots.items()):
            table[slot] = 100 + i
            sim.uc.mem_write(clips + 0x20 * i + 0x10, struct.pack("<f", length))
        sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
        sim.uc.mem_write(species + 0x124, struct.pack(f"<{len(table)}i", *table))
        played = []

        def play(uc, addr, size, _):   # 0x42750 as the game runs it: the slot's clip, layer 1, rate 1
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<5I", uc.mem_read(esp, 20))
            handle = struct.unpack("<i", uc.mem_read(species + 0x124 + 4 * args[1], 4))[0]
            played.append((args, handle))
            if handle != -1:
                uc.mem_write(anim + 0x10, struct.pack("<I", 1))
                uc.mem_write(anim + 0x84, struct.pack("<I", clips + 0x20 * (handle - 100)))
                uc.mem_write(anim + 0xA0, struct.pack("<f", 1.0))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 20)

        sim.uc.hook_add(UC_HOOK_CODE, play, begin=0x42750, end=0x42750)
        node = sim.u32(0x1A9C5C)                    # "m_feet", as 0x8D600 passes it
        sim.call(target, args=(critter, index, 4, node), until=l2._RETURN)
        (args, handle), = played
        assert args == [critter, index, 4, node]
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0x10, as 0x42750's
        kept = list(struct.unpack(f"<{len(table)}i", sim.uc.mem_read(species + 0x124, 4 * len(table))))
        return list(slots)[handle - 100], sim.f32(anim + 0xA0), kept == table

    assert built[at] == 0xE8 and not any(
        s["vaddr"] <= target < s["vaddr"] + s["vsize"] for s in sections)
    assert l1.check(vanilla, built) == []
    garret4 = seconds("characters/garret4/ouch_1")
    keylord = {0x25 + n: seconds(f"characters/keylord/ouch_{n + 1}") for n in range(3)}
    idle, walk = seconds("characters/barnacle/idle"), seconds("characters/townspeople/male_1/walk")
    for picked in (0x25, 0x26, 0x27):
        slot, rate, kept = hit(keylord, picked)
        assert (slot, kept) == (0x25, True)
        assert math.isclose(30 * keylord[0x25] / rate, 30 * garret4, rel_tol=1e-6)
    assert round(30 * garret4) == 12
    slot, rate, _ = hit({1: idle, 0x66: walk}, 0x25)
    assert slot == 1 and math.isclose(idle / rate, garret4, rel_tol=1e-6)
    slot, rate, _ = hit({0x66: walk}, 0x25)
    assert slot == 0x66 and math.isclose(walk / rate, garret4, rel_tol=1e-6)


def test_a_hit_reaction_ends_the_interrupted_clips_crossfade_so_its_damage_window_cant_hit():
    """AZ-304: a hit plays its reaction through 0x42750 on a fresh anim
    layer (0xCAD40), and the layers already playing fade out over 0.25 s
    (anim+0x14) while their clips keep running; a body marker reads the
    layers' weighted blend. So when the interrupted attack's clip reached
    its own damage window during the fade, the body's m_damage came on
    inside the reaction at the old layer's share, 0.99, 0.86, 0.73, 0.59
    (xemu sitting modelswap3: 12 credited hits inside reactions across 7
    bodies; guard_air's only one, 3 ticks in; sleeth and firedrake one
    each; the reaction clips themselves have no damage window). X7 now
    ends the crossfade at once, as the engine does when a fade-out
    finishes: every layer but the reaction's is freed (flags 0, weight
    0) and the reaction's takes weight 1.0, so only its clip drives the
    marker. Its rate still ends it in garret4's 0.4 s."""
    built = bytes(_swap("keylord")["default.xbe"])
    target = 0x8D687 + struct.unpack_from("<i", built, va_to_file(0x8D682) + 1)[0]
    sim, base = Sim(built), 0x20000000
    critter, species, anim, clips = base, base + 0x1000, base + 0x2000, base + 0x3000
    table = [-1] * 0x71
    table[0x25] = 100                                     # ouch_1, 1.0 s
    sim.uc.mem_map(base, 0x10000)
    sim.uc.mem_write(clips + 0x10, struct.pack("<f", 1.0))
    sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
    sim.uc.mem_write(species + 0x124, struct.pack(f"<{len(table)}i", *table))

    def layer(n: int) -> int:
        return anim + 0x40 + 0x40 * n

    for n, flags, weight in ((0, 0x09, 1.0), (1, 0x10, 0.4)):   # the attack; an older fade
        sim.uc.mem_write(layer(n) + 4, struct.pack("<I", clips + 0x100 + 0x20 * n))
        sim.uc.mem_write(layer(n) + 8, struct.pack("<I", flags))
        sim.uc.mem_write(layer(n) + 0x18, struct.pack("<4f", 0.5, weight, 1.5, 4.0))

    def play(uc, addr, size, _):   # 0x42750 and its 0xCAD40, as the game runs them
        esp = sim.reg("esp")
        ret, _critter, index, flags, _node = struct.unpack("<5I", uc.mem_read(esp, 20))
        for n in range(3):
            old = sim.u32(layer(n) + 8)
            if old:
                uc.mem_write(layer(n) + 8, struct.pack("<I", old & ~8 | 0x10))
        uc.mem_write(layer(2) + 4, struct.pack("<I", clips))
        uc.mem_write(layer(2) + 8, struct.pack("<I", flags & ~0x10 | 9))
        uc.mem_write(layer(2) + 0x18, struct.pack("<4f", 0.0, 0.01, 1.0, 1.0))
        uc.mem_write(anim + 0x10, struct.pack("<If", 2, 0.25))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 20)

    sim.uc.hook_add(UC_HOOK_CODE, play, begin=0x42750, end=0x42750)
    sim.call(target, args=(critter, 0x26, 4, sim.u32(0x1A9C5C)), until=l2._RETURN)
    state = [(sim.u32(layer(n) + 8), sim.f32(layer(n) + 0x1C)) for n in range(3)]

    assert state == [(0, 0.0), (0, 0.0), (0x0D, 1.0)]
    assert math.isclose(sim.f32(layer(2) + 0x20), 1.0 / 0.4, rel_tol=1e-6)


def test_a_body_whose_own_field_deals_damage_never_hurts_the_player_wearing_it():
    """AZ-450 (Step 2.75d): every critter gets its body's default fx
    (0x43700, ``characters/<body>/fx/fx_default``), the player too, and
    tesla_tree's holds a damage platform nothing switches off, dealing
    ``tesla`` (25 HP); the hit handler 0x8D600 reads the victim's
    critters_damage cell, and garret4's ``tesla`` is empty (the type's 25,
    a hit reaction and a knock-back) where the tree's is 0.0, so a player
    wearing it was hurt by his own body and never reached a steady tick
    (sitting 2.75c; p8 before the bake). W16: garret4 takes each damage
    type its body's live field deals as the species does, here the tree's
    0.0, and nothing else changes in critters_damage. Only tesla_tree's
    body has a live field.

    AZ-453 (Step 2.75e): Balthazar's airship box (``norm_2``, 15 HP) is
    switched on by ``m_lifedrainswitch``, which his attack_2 keys to 1,
    and hangs under ``onPlayer`` (inherit mode 7: on the player critter),
    and no platform hit is checked against its owner, so the player
    wearing him hurt himself in each column that plays attack_2 (sitting
    2.75d: own mode's basic2), and a cell can't tell that box from an
    enemy's hit. W17: those columns (seven in own body, four in
    garret4's exact) play a copy of attack_2 without that marker's
    tracks, with its length, bone tracks and other markers, and no column
    plays a clip that switches the box on; his own attack_2, which NPC
    Balthazar plays, is unchanged. Since Step 2.135 (D324, its design's
    J7) own body plays attack_2 itself, X37 putting the box on the enemy
    it lands on (test_balthazars_drain_beam_drains_the_enemy_it_lands_on_never_the_wearer_and_heals_a_share),
    and W17's copies are Skin only's."""
    characters = _vanilla("gamedata/characters.xbr")
    config = _vanilla("gamedata/config.xbr")
    garret4 = XbrDocument.from_bytes(config).keyed_section("critters_damage").col_names().index("garret4")
    before = _cells(config)
    games = {(species, mode): _swap(species, mode=mode, sounds="garret4")
             for species, mode in (("tesla_tree", "own"), *(("balthazar", mode) for mode in MODES))}
    built = {species: _cells(games[species, "own"]["config.xbr"]) for species in ("tesla_tree", "balthazar")}
    body = read_body(characters, "balthazar_airship")
    switch = body.markers.index("m_lifedrainswitch")
    at, size = _clip(characters, "characters/balthazar_airship/attack_2")
    drain = read_clip(characters, at)

    def switches_on(clip) -> bool:
        return any(t.target == switch and any(key[1] > 0 for key in t.keys) for t in clip.markers)

    copies, kept = {}, {}
    for mode in MODES:
        game = games["balthazar", mode]
        grown = bytes(game["characters.xbr"])
        anims = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
        played = {col: read_clip(grown, _clip(grown, "characters/balthazar_airship/"
                                              + anims.find_cell(col, "Anim", i).string_value.casefold())[0])
                  for i, col in enumerate(anims.col_names())}
        copies[mode] = [col for col, clip in played.items() if not switches_on(clip) and clip == replace(
            drain, markers=tuple(t for t in drain.markers if t.target != switch))]
        g_at, g_size = _clip(grown, "characters/balthazar_airship/attack_2")
        kept[mode] = (not any(map(switches_on, played.values())), grown[g_at:g_at + g_size] == characters[at:at + size])

    assert [body for body in body_names(characters) if field_damage(characters, body, config)] == ["tesla_tree"]
    assert {species: {key: cells[key] for key in before if key[0] == "critters_damage" and cells[key] != before[key]}
            for species, cells in built.items()} == {
        "tesla_tree": {("critters_damage", f"{garret4}:garret4", "tesla"): (1, 0.0, None)}, "balthazar": {}}
    assert field_switches(characters, "balthazar_airship") == {"m_lifedrainswitch"} and switches_on(drain)
    assert kept == {"garret4": (True, True), "own": (False, True)}
    assert copies == {"garret4": ["elemental2", "right1", "left2", "up1"], "own": []}


def test_a_worn_boss_bodys_death_plays_without_its_death_camera_or_drop():
    """AZ-603 (Step 2.131; D343: "keep custom death animations while
    removing the stall"): the player wearing a body wears its default fx
    (0x43700), and three bodies' fx script a scene off a marker their
    death keys: bosses/air_guardian's ``die`` holds ``m_dying`` at 1.0
    for its 9.667 s, which enables a death camera (freezePlayer 1) and,
    through a switch, the critter generator of ``frag_air_4``, the air
    disc fragment; the owner's guard_air death in the 2.76 play dropped
    it and the game stalled. W22: the scan finds exactly those bodies'
    markers (a transform reaching a camera or a critterGenerator, directly
    or through switches and latches), and the player's death slots 23-27
    play ``q/die``, ``die`` without its ``m_dying`` tracks (its length,
    bones and every other marker: the motion and explosions stay), which
    X11 now looks up from its table before the slot's own name; the
    body's own ``die``, which the NPC boss plays, is vanilla's byte for
    byte, the fall death (slot 21) keeps its fill and another species'
    slots are vanilla's; a slot a recipe's ``idles`` fill takes no quiet
    copy (Step 2.168)."""
    characters = _vanilla("gamedata/characters.xbr")
    assert {body: switches for body in body_names(characters)
            if (switches := scripted_switches(characters, body))} == {
        "balthazar_airship": {"m_dying"}, "bosses/air_guardian": {"m_dying"},
        "bosses/fire_guardian": {"m_dying", "m_shards"}}
    game = _swap("guard_air", mode="own")
    grown = bytes(game["characters.xbr"])
    body = read_body(characters, "bosses/air_guardian")
    dying = body.markers.index("m_dying")
    at, size = _clip(characters, "characters/bosses/air_guardian/die")
    die = read_clip(characters, at)
    g_at, g_size = _clip(grown, "characters/bosses/air_guardian/die")
    assert any(t.target == dying and any(key[1] > 0 for key in t.keys) for t in die.markers)
    quiets = set(quiet_fills(characters, body, {})[0])
    assert 23 in quiets and quiets - set(quiet_fills(characters, body, {}, {23: ("v/x", 0.0)})[0]) == {23}
    assert read_clip(grown, _clip(grown, "characters/bosses/air_guardian/q/die")[0]) == replace(
        die, markers=tuple(t for t in die.markers if t.target != dying))
    assert grown[g_at:g_at + g_size] == characters[at:at + size]
    clips = {clip: 100 + i for i, clip in enumerate(body.clips)} | {"q/die": 900}
    clips |= {f"v/victory_{v}": 5000 + v for v in range(1, 7)}
    built = bytes(game["default.xbe"])
    player = _species_load(built, body.name, clips, 0x24)
    assert {i: player[i] for i in (21, *range(23, 28))} == {21: "idle", **dict.fromkeys(range(23, 28), "q/die")}
    assert _species_load(built, body.name, clips, 0x04) == _species_load(_vanilla("default.xbe"), body.name, clips, 0x24)


@pytest.mark.parametrize("mode, weapon", [*((m, None) for m in MODES), ("own", "balthazar_magic")])
def test_a_worn_fire_guardians_swings_and_victories_play_without_its_shard_generator(mode, weapon):
    """AZ-611 (Step 2.175; W22 on the attacks): bosses/fire_guardian's
    ``attack_2`` keys ``m_shards``, which drives its default fx's
    ``fire_shard`` generator (maxAlive 5), and a guard_fire1 build plays
    it in 12 of its 24 attacks_anims columns and, stretched, as its
    victories, so each such swing or victory spawned shard critters
    around the player. In every mode those columns name ``q/0``, the
    clip without its scripted fx's markers (its length, bones and every
    other marker kept, so it moves, lasts and hits as it did: the
    listing still says attack_2), the ``v/`` victories hold none of
    those tracks, and the NPC boss's own attack_2 is vanilla's.  With
    Balthazar's magic (W34) ``q/0`` is taken from the cast clip, so it
    keys his lightning switch too (the review of 2.175c, finding 1)."""
    characters = _vanilla("gamedata/characters.xbr")
    config = _vanilla("gamedata/config.xbr")
    body = read_body(characters, "bosses/fire_guardian")
    marks = {body.markers.index(m) for m in scripted_switches(characters, body.name)}
    shards = body.markers.index("m_shards")
    at, size = _clip(characters, "characters/bosses/fire_guardian/attack_2")
    own = read_clip(characters, at)
    assert any(t.target == shards and any(key[1] > 0 for key in t.keys) for t in own.markers)
    game = _swap("guard_fire1", mode=mode, weapon=weapon)
    grown = bytes(game["characters.xbr"])
    anims = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
    named = [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(anims.col_names())]
    if weapon is not None:
        quiet = read_clip(grown, _clip(grown, "characters/bosses/fire_guardian/q/0")[0])
        cast = read_body(grown, body.name).markers.index(CAST_SWITCH)
        keyed = {t.target for t in quiet.markers if any(key[1] > 0 for key in t.keys)}
        assert named.count("q/0") == 12 and cast in keyed and not keyed & marks
        return
    listed = [a.clip for a in attacks(config, characters, "guard_fire1", mode)]
    assert named.count("q/0") == listed.count("attack_2") == 12
    assert [{"q/0": "attack_2"}.get(name, name) for name in named] == listed
    assert read_clip(grown, _clip(grown, "characters/bosses/fire_guardian/q/0")[0]) == replace(
        own, markers=tuple(t for t in own.markers if t.target not in marks))
    for v in (1, 3, 5, 6):
        victory = read_clip(grown, _clip(grown, f"characters/bosses/fire_guardian/v/victory_{v}")[0])
        assert victory.bones and not any(t.target in marks for t in victory.markers), v
    g_at, g_size = _clip(grown, "characters/bosses/fire_guardian/attack_2")
    assert grown[g_at:g_at + g_size] == characters[at:at + size]


@pytest.mark.parametrize("species, missing_anims, expected", [
    ("town_female_4", "garret4", _garret4s(_FILLED | {11, 37, 40, 41, 42, 68, *range(75, 82)} | X9)
     | {i: ("s/g4/" + BASE_CLIPS[i], False) for i in SURFACE_SLOTS}),
    ("town_female_4", "own", _vase(_FILLED | _G4_LACKS, False)),
    ("keylord", "garret4", {1: ("idle_1", False), 9: ("run", False), 15: ("g4/jump", False),
                            53: ("g4/step_up", False)}),
    ("spideyzar", "garret4", {**dict.fromkeys((16, 17, 20), ("jump_left", True)),
                              **dict.fromkeys((23, 24, 25, 27), ("ouch_1", True)), 81: (None, False),
                              **{75 + i: (f"v/victory_{v}", False) for i, v in enumerate((1, 1, 3, 3, 5, 6))}}),
    ("fire_elemental", "garret4", {1: ("idle_2", False), 2: ("idle_1", False), 3: ("idle_2", False),
                                   4: ("idle_3", False)}),
])
def test_a_swapped_bodys_empty_base_clip_slots_play_its_own_clips(species, missing_anims, expected):
    """Step 2.66 (X11; D226, D229; AZ-303's level start): the species load
    0x4B8E0 resolves base clip slots 0-0x51 by name (the CALL of
    species_clip_lookup 0x4B600 at 0x4B948: the name as a whole key, else
    characters/<body>/<name>), and an empty slot plays nothing: a body
    with no idle showed its bind pose at each level start (town_female_4,
    whose clips are vaseidle and vasewalk), and kept the clip already playing for a
    jump, a swim or a death. The loop runs here (L2) with the asset
    registry 0xA5CA0 and the formatter 0x178C0 stubbed by name: for the
    player's species (flag 0x20) each slot the body lacks gets its
    closest own clip (Step 2.60's rule), a walk for a move and its idle
    for the rest. Under garret4's
    rule (the default) a stand-in that isn't very similar is marked
    garret4-timed (the table holds garret4's clip length, D229) and a
    slot garret4 lacks (idle_5, idle_6, die_3) stays empty as his does;
    under own nothing is marked and those fill too. The hit reactions
    37-42 (no ouch clip: X7 plays its fallback), X9's slots (the ladder,
    hoist and step moves and climb loops 53, 55-60, 62-66) and the hard
    landing 11, hang 68 and use 81 (aligned moves X9 plays a stand-in
    for in garret4's time) stay empty, and any other species' slots are
    what vanilla gives. The victories 75-80 take garret4's length (Step
    2.121, D299, D300): spideyzar's its laugh over his, v/victory_N;
    town_female_4's under own stay empty (her vase, KEEPS_STAND_IN). A slot whose garret4 clip
    deals no damage takes none of the body's damage clips: spideyzar's
    jump and deathbeam switch m_damage on (the damage pass reads it in
    any state), so its standing jump, Flaps flap and climb drop take
    jump_left and its deaths and drowning ouch_1; off the bake's rigs the
    stand-in stays (spideyzar's jump, garret4-timed). Step 2.88: on a
    body garret4's clips are baked onto (retarget.MAPS: the townspeople's,
    keylord's) a slot with no very similar own clip, and every aligned
    one, X9's included, takes garret4's clip baked onto its rig by name
    (g4/<clip>, characters/<body>/g4/<clip>; untimed: it has his length),
    while a very similar own clip still plays (keylord's idle takes its
    idle_1). Step 2.134a (D331): in Balanced a body without its own idle
    stands on its calmest looping idle_N where its chain's pick moves at
    least twice as fast (the fire elemental's idle_2, not its busy
    idle_1), its other idles still playing now and then by name. Step
    2.134b (W27): its swim slots play copies of the baked clips keyed
    m_root, s/g4/<clip>."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap(species, missing_anims=missing_anims)["default.xbe"])
    characters = _vanilla("gamedata/characters.xbr")
    body = read_body(characters, next(m.body for m in player_models(
        _vanilla("gamedata/config.xbr"), characters) if m.species == species))
    garret4 = read_body(characters, "garret4")
    clips = {clip: 100 + i for i, clip in enumerate(body.clips)}
    clips |= {f"g4/{clip}": 3000 + i for i, clip in enumerate(garret4.clips)}
    clips |= {f"s/g4/{clip}": 7000 + i for i, clip in enumerate(garret4.clips)}
    clips |= {f"v/victory_{v}": 5000 + v for v in range(1, 7)}

    def load(xbe: bytes, flags: int) -> dict[int, str | None]:
        return _species_load(xbe, body.name, clips, flags)

    at = va_to_file(0x4B948)
    target = 0x4B94D + struct.unpack_from("<i", built, at + 1)[0]
    _, sections = parse_xbe_sections(vanilla)
    assert built[at] == 0xE8 and not any(
        s["vaddr"] <= target < s["vaddr"] + s["vsize"] for s in sections)
    assert l1.check(vanilla, built) == []
    table = resolve_va_to_file(built, trampoline_symbol_va(
        built, SLOTS_HOOK, SLOTS_TABLE, shim_source=SLOTS_SHIM.source_path()))
    lengths = struct.unpack_from("<82f", built, table + 2 * 0x52)
    player = load(built, 0x24)
    assert {i: (player[i], lengths[i]) for i in expected} == {
        i: (clip, _f32(garret4.length(BASE_CLIPS[i])) if timed else 0.0)
        for i, (clip, timed) in expected.items()}
    assert load(built, 0x04) == load(vanilla, 0x24)


def test_a_baked_childs_jumps_play_garret4s_baked_clips_and_its_own_jump_only_under_anims_own():
    """Step 2.194a (D760, AZ-756; the owner on town_girlchild_1: "why does
    the girl use running as her jump animation? why not the garret type of
    jump?"): the five children the bake serves ship a run-like clip named
    jump, which X11 kept over garret4's baked one (the slot plays its own
    name's clip) and which the standing jump, superjump and climb drop took
    as their chains' very similar clip. On a baked body under garret4's
    rule the jump family (JUMPS) plays his baked clips, g4/<clip> in his
    length, as the aligned moves do; under anims own (no bake) the body's
    own jump plays in all four, the jump slot by its own name."""
    characters = _vanilla("gamedata/characters.xbr")
    garret4 = read_body(characters, "garret4")
    got = {}
    for kid in ("child_1", "child_2", "child_3", "girlchild_1", "girlchild_2"):
        body = read_body(characters, f"townspeople/{kid}")
        got[kid] = ("jump" in body.clips, {anims: {i: fill for i, fill in slot_fills(
            body, garret4, anims, baked=bakes(body, anims)).items() if i in JUMPS} for anims in ANIMS})
    assert got == dict.fromkeys(got, (True, {
        "garret4": {i: ("g4/" + BASE_CLIPS[i], 0.0) for i in JUMPS},
        "own": {i: ("jump", 0.0) for i in JUMPS - {BASE_CLIPS.index("jump")}}}))


def test_a_baked_flyer_jumps_swims_and_rolls_on_its_own_floating_clips_in_balanced_only():
    """Step 2.134a (D334, the owner on the fire elemental: "it is supposed
    to float, as a flying enemy"; D335): a flyer the bake serves walked
    and ran on its own floating clips but slid, jumped, fell, hovered,
    swam and rolled on garret4's baked ones, which drop it to the floor
    and kick (its lowest bone -0.40..+0.05 model units against 0.21-0.69
    in its own). In Balanced those slots (FLOATS) play its own clips as
    an unbaked body's do, garret4-timed (X12's BIND and REUSE): the run
    for the slide and the swim, its calm idle_2 (D331) for the rest; the
    roll plays its own run on garret4's roll motion (X4), and the touchdown
    and step up stay baked (his markers place them). Skin only keeps
    garret4's baked moves and the roll g4/roll_forward (D327), its swims
    on W27's copies keyed m_root (Step 2.134b)."""
    characters = _vanilla("gamedata/characters.xbr")
    config = _vanilla("gamedata/config.xbr")
    body, garret4 = read_body(characters, "fire_elemental"), read_body(characters, "garret4")
    clips = {clip: 100 + i for i, clip in enumerate(body.clips)}
    clips |= {f"g4/{clip}": 3000 + i for i, clip in enumerate(garret4.clips)}
    clips |= {f"s/g4/{clip}": 7000 + i for i, clip in enumerate(garret4.clips)}
    floating = {12: "run", 74: "run", **dict.fromkeys((15, 16, 17, 18, 20, 21, 22, 70, 71, 72), "idle_2")}
    for mode in ("own", "garret4"):
        built = bytes(_swap("fire_elemental", mode=mode, sounds="garret4")["default.xbe"])
        own = mode == "own"
        table = resolve_va_to_file(built, trampoline_symbol_va(
            built, SLOTS_HOOK, SLOTS_TABLE, shim_source=SLOTS_SHIM.source_path()))
        lengths = struct.unpack_from("<82f", built, table + 2 * 0x52)
        player = _species_load(built, body.name, clips, 0x24)
        want = ({i: (clip, _f32(garret4.length(BASE_CLIPS[i]))) for i, clip in floating.items()} if own
                else {i: (("s/" if i in SURFACE_SLOTS else "") + f"g4/{BASE_CLIPS[i]}", 0.0) for i in floating})
        want |= {1: ("idle_2" if own else "idle_1", 0.0), 11: ("g4/touchdown", 0.0), 53: ("g4/step_up", 0.0)}
        assert {i: (player[i], lengths[i]) for i in want} == want, mode
        roll = "run" if own else "g4/roll_forward"
        assert [a.clip for a in attacks(config, characters, "fire_elemental", mode) if a.column == "roll forward"] == [
            roll], mode
        assert [verify_trampoline_patch(built, hook) for hook in (ROLL_HOOK, BORROW_BIND, BORROW_REUSE)] == [
            "applied" if own else "original"] * 3, mode


def test_guard_airs_swim_somersaults_once_then_bobs_in_its_barrel_in_balanced():
    """Step 2.134a (W25; D341, the owner: "it make a somersault and
    straightens into a barrel for swimming, but then resets the animation
    jarringly"; D419: "Slow bob"): guard_air's swim slot played run_begin
    garret4-timed and looped, its 2.0 s somersault drifting the root 7.35
    model units ahead, so each 1.467 s wrap snapped the barrel back and
    upright. In Balanced it plays a copy, h/run_begin, untimed and 600 s
    long (L2: the species load names it, its table length 0): the
    somersault once at rate 1, then the barrel's pose holds (its rotations
    at 600 s are its 2.0 s ones) while the whole body rises SWIM_BOB's
    0.25 model units and back every 2.4 s, smoothly, to the end (the held
    copy stood still), its root's forward track held at its t 0 value and
    each marker's y moved back by the same drift and its height bobbing
    with the root, so the barrel and its fx stay over the player, but
    m_root's (Step 2.134b, AZ-634: the swim places the model at its centre
    less m_root, so a bobbed m_root cancelled the drawn bob): it holds its
    2.0 s height. Skin only keeps run_begin in garret4's time."""
    vanilla = _vanilla("gamedata/characters.xbr")
    body, garret4 = read_body(vanilla, "bosses/air_guardian"), read_body(vanilla, "garret4")
    clips = {clip: 100 + i for i, clip in enumerate(body.clips)} | {"h/run_begin": 900}
    games = {}
    for mode, want in (("own", ("h/run_begin", 0.0)), ("garret4", ("run_begin", _f32(garret4.length("swim_2"))))):
        games[mode] = game = _swap("guard_air", mode=mode, sounds="garret4")
        built = bytes(game["default.xbe"])
        table = resolve_va_to_file(built, trampoline_symbol_va(
            built, SLOTS_HOOK, SLOTS_TABLE, shim_source=SLOTS_SHIM.source_path()))
        swim = (_species_load(built, body.name, clips, 0x24)[0x4A],
                struct.unpack_from("<82f", built, table + 2 * 0x52)[0x4A])
        assert swim == want, mode
    characters = bytes(games["own"]["characters.xbr"])
    held = read_clip(characters, _clip(characters, "characters/bosses/air_guardian/h/run_begin")[0])
    keyed = read_clip(vanilla, _clip(vanilla, "characters/bosses/air_guardian/run_begin")[0])
    rig = Rig.read(vanilla, body.name)
    root = next(k for k, bone in enumerate(rig.bones) if bone.parent < 0)
    y0 = next(tr for tr in keyed.bones if (tr.target, tr.comp) == (root, 1)).keys[0][1]
    m_root = body.markers.index("m_root")
    assert held.length == 600.0 and any(tr.target == m_root and tr.comp == 2 for tr in held.markers)
    assert {(tr.target, tr.comp): tr.keys for tr in held.bones if (tr.target, tr.comp) != (root, 2)} == {
        (tr.target, tr.comp): ((0.0, y0, 0.0, 0.0), (600.0, y0, 0.0, 0.0)) if (tr.target, tr.comp) == (root, 1)
        else tr.keys for tr in keyed.bones if (tr.target, tr.comp) != (root, 2)}
    assert pose(rig, held, 600.0) == pose(rig, held, 2.0)   # the barrel's pose holds
    rise, period = SWIM_BOB
    for t in (2.0 + period / 4, 2.0 + period / 2, 2.0 + period, 300.0 + period / 2, 598.0):   # and it bobs
        lift = rise * (1 - math.cos(2 * math.pi * (t - 2.0) / period)) / 2
        settled = origins(rig, held, 2.0)
        assert [pytest.approx(p, abs=0.02) for p in origins(rig, held, t)] == [(x, y, z + lift) for x, y, z in settled], t
        assert [pytest.approx(retarget.evaluate(tr.keys, t), abs=0.02) for tr in held.markers if tr.comp == 2] == [
            retarget.evaluate(tr.keys, 2.0) + (0.0 if tr.target == m_root else lift)
            for tr in held.markers if tr.comp == 2], t
    for t in (0.5, 1.2, 2.0):   # the somersault, the straightening, the barrel: run_begin's less its drift
        drift = origins(rig, keyed, t)[root][1] - y0
        assert [pytest.approx(p, abs=1e-4) for p in origins(rig, held, t)] == [
            (x, y - drift, z) for x, y, z in origins(rig, keyed, t)], t
        assert [pytest.approx(retarget.evaluate(tr.keys, t), abs=1e-4) for tr in held.markers if tr.comp == 1] == [
            retarget.evaluate(tr.keys, t) - drift for tr in keyed.markers if tr.comp == 1], t


def test_a_baked_body_without_m_root_swims_with_its_root_at_the_centre_as_garret4_does():
    """Step 2.134b (W27, AZ-638; the owner on town_female_4: "our model
    is fully out of the water floating above the water when we are at the
    max elevation in the water", "this also might be causing her camera
    to look like its too far above her in the water"): player_swim_tick
    places the model at the swim's centre less m_root sampled in the
    playing clip (0x42E40), and a baked body has no m_root, so its origin
    sat at the centre and her root 0.65-0.71 m over the surface. Her
    build grows garret4's m_root record (zeros at rest) at the end of her
    markers (W27's m_eye after it: Step 2.150's test below) and her four swim slots (swim_idle, swim_idle_up,
    swim_idle_down, swim_2) play copies of their baked clips, s/g4/<clip>,
    whose bones and other markers are the clip's and whose m_root is her
    drawn scale 1.15 x her root's place (swim_idle_down keys none: its
    rest), so the swim draws the root at the centre; no other clip keys
    m_root or m_eye (X8's land point rests on m_eye being 1), and X9's ladder offsets stay installed (the grown m_root is no
    ladder's). A flyer on its own swim (the fire elemental in Balanced)
    and guard_air, with its own m_root, get no copies."""
    vanilla = _vanilla("gamedata/characters.xbr")
    game = _swap("town_female_4")
    built, characters = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    body = read_body(characters, "townspeople/female_4")
    marker = body.markers.index("m_root")
    assert body.markers[marker:] == ("m_root", "m_eye") and dict(marker_records(characters, body.name))["m_root"] == dict(
        marker_records(vanilla, "garret4"))["m_root"]
    rt = retarget.Retarget(vanilla, body.name)
    root, rest = rt.root, rt.target.bones[rt.root].t
    names, unkeyed = _x11_names(built), set()
    for slot in SURFACE_SLOTS:
        pick = "g4/" + BASE_CLIPS[slot]
        assert names[slot] == "s/" + pick
        baked, copy = (read_clip(characters, _clip(characters, f"characters/{body.name}/{d}{pick}".casefold())[0])
                       for d in ("", "s/"))
        assert (copy.length, copy.bones, tuple(tr for tr in copy.markers if tr.target < marker)) == (
            baked.length, baked.bones, baked.markers)
        keyed = {tr.comp: tr.keys for tr in baked.bones if tr.target == root and tr.comp <= 2}
        placed = {tr.comp: tr.keys for tr in copy.markers if tr.target == marker}
        assert set(placed) == {0, 1, 2}, pick
        unkeyed |= {(pick, c) for c in range(3) if c not in keyed}
        for t in (copy.length * k / 20 for k in range(21)):
            assert [retarget.evaluate(placed[c], t) for c in range(3)] == pytest.approx(
                [1.15 * (retarget.evaluate(keyed[c], t) if c in keyed else rest[c]) for c in range(3)], abs=1e-5), pick
    assert ("g4/swim_idle_down", 2) in unkeyed
    prefix, toc = f"characters/{body.name}/".casefold(), parse_toc(characters)
    assert {n.casefold()[len(prefix):] for i, n in named_resources(characters).items()
            if n.casefold().startswith(prefix) and toc[i].tag == "banm"
            and any(tr.target in (marker, marker + 1) for tr in read_clip(characters, toc[i].file_offset).markers)} == {
        "s/g4/" + BASE_CLIPS[slot] for slot in SURFACE_SLOTS}
    assert verify_trampoline_patch(built, CLIMB_OFFSETS_HOOK) == "applied"
    for species in ("fire_elemental", "guard_air"):
        assert not any("/s/g4/" in n.casefold() for n in named_resources(
            bytes(_swap(species, mode="own", sounds="garret4")["characters.xbr"])).values()), species


def test_a_body_without_garret4s_aligned_clips_plays_a_stand_in_in_his_time_and_sits_on_the_rungs_where_he_does():
    """Step 2.63 (D219; the owner: Balthazar "had trouble latching onto
    the ladder"): the move-state setter 0x8BDB0 hands the latch (anim
    0x3C, climb_start, and the other ladder, hoist and step-up moves) to
    the aligned clip change 0x42430 with its CALL at 0x8BDF3, which
    returns at once when the species' slot is -1, and only garret4's body
    has those clips: a swapped body entered state 0x101 with no clip to
    end it. X9 takes that CALL (L1 well formed): for the player's species
    an empty slot plays the body's stand-in (idle, else idle_1, walk, run,
    the roll's) for the call, the slot is put back, and the move lasts
    garret4's time (the window ends at garret4's length over the stand-in's;
    a shorter one plays its whole window, slowed: AZ-489's test). On the rungs the
    climb tick loops climb_idle (its CALLs of anim_change at 0x883CB and
    0x88733, which X9 takes too: the stand-in) and places the model by its
    m_grab on the rung point (0x42E40), which no swapped body has, so its
    feet sat where garret4's hands go: X9 moves the point by garret4's
    m_grab in that clip, turned as the game turns it, so the body sits
    where garret4's origin does. (Since Step 2.87 Balthazar wears
    garret4's climb clips baked onto his rig, with his m_grab, and no X9,
    and since Step 2.134a the golem too: the overlord's golem, golem_ol,
    carries it here.) Step 2.66b (xemu 2.75a: balthazar and
    flicken held 33-45+ ticks after a hard landing against garret4's 13,
    flicken 77+ in the overhead hang on a fidget): the hard landing
    (touchdown, 0x8B0D4 and 0x8B18C) and the hang (hang_start, 0x8A4E3)
    call 0x42430 directly, so the state waited for whatever clip played;
    X9 takes those CALLs too, each the stand-in in garret4's time."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap("overlord and golem")["default.xbe"])
    characters = _vanilla("gamedata/characters.xbr")
    base = 0x20000000
    feet, grab = struct.unpack_from("<2I", vanilla, va_to_file(0x1A9C5C))   # "m_feet", "m_grab"

    def target(va: int) -> int:
        assert built[va_to_file(va)] == 0xE8
        return va + 5 + struct.unpack_from("<i", built, va_to_file(va) + 1)[0]

    def seconds(key: str) -> float:
        return struct.unpack_from("<f", characters, _clip(characters, key)[0] + 0x10)[0]

    def latch(flags: int, stand_in: float, hook: int = 0x8BDF3, index: int = 0x3C) -> tuple[int, bool, float, float]:
        """The aligned move ``index`` (the latch) through the hooked CALL
        at ``hook`` on a species with ``flags`` whose only clip is an idle
        of ``stand_in`` s: the slot 0x42430 saw, whether the slots are as
        they were, and the layer's end and the glide's window after it."""
        sim = Sim(built)
        critter, species, anim, clip = base, base + 0x1000, base + 0x2000, base + 0x3000
        table = [-1] * 0x71
        table[1] = 101
        sim.uc.mem_map(base, 0x10000)
        sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(species + 0x124, struct.pack(f"<{len(table)}i", *table))
        sim.uc.mem_write(clip + 0x10, struct.pack("<f", stand_in))
        seen = []

        def align(uc, addr, size, _):   # 0x42430: the slot's clip on layer 1, from t0 to t1
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<8I2f", uc.mem_read(esp, 40))
            seen.append(struct.unpack("<i", uc.mem_read(species + 0x124 + 4 * args[1], 4))[0])
            if seen[-1] != -1:
                uc.mem_write(anim + 0x10, struct.pack("<I", 1))
                uc.mem_write(anim + 0x84, struct.pack("<I", clip))
                uc.mem_write(anim + 0xA4, struct.pack("<f", args[8] * stand_in))
                uc.mem_write(critter + 0x1A0, struct.pack("<f", args[8] - args[7]))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 40)

        sim.uc.hook_add(UC_HOOK_CODE, align, begin=0x42430, end=0x42430)
        sim.call(target(hook), until=l2._RETURN, args=(
            critter, index, 0, base + 0x4000, base + 0x4010, feet, grab,
            *struct.unpack("<2I", struct.pack("<2f", 0.0, 1.0))))
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0x24, as 0x42430's
        kept = struct.unpack(f"<{len(table)}i", sim.uc.mem_read(species + 0x124, 4 * 0x71))
        return seen[0], list(kept) == table, sim.f32(anim + 0xA4), sim.f32(critter + 0x1A0)

    def rung(index: int, flags: int = 0x24, clip: int = -1) -> tuple[float, ...]:
        """The rung point the climb tick hands 0x42E40 after its hooked
        CALL of anim_change at 0x883CB for ``index`` (anim_change stubbed),
        on the player's species with an idle clip and ``clip`` in the
        index's slot."""
        sim = Sim(built)
        critter, species = base, base + 0x1000
        sim.uc.mem_map(base, 0x10000)
        sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(species + 0x124, struct.pack("<113i", -1, 101, *[-1] * 111))
        sim.uc.mem_write(species + 0x124 + 4 * index, struct.pack("<i", clip))
        frame = l2._STACK_TOP - 0x100                       # the caller's ESP before its pushes
        sim.uc.mem_write(frame + 0x98, struct.pack("<4f3f", *turn, *point))
        sim.call(target(0x883CB), args=(critter, index, 2), stubs={0x42910: 0}, until=l2._RETURN)
        assert sim.reg("esp") == frame                      # RET 0xC, as anim_change's
        return struct.unpack("<3f", sim.uc.mem_read(frame + 0xA8, 12))

    def garret4_rung() -> tuple[float, ...]:
        """Where garret4's m_grab puts his origin there: the point less his
        m_grab in climb_idle."""
        return tuple(_f32(p - q) for p, q in zip(point, _garret4_node(characters, "climb_idle", "m_grab", 0.5, turn)))

    turn = (0.0, 0.0, math.sin(math.radians(15)), math.cos(math.radians(15)))   # a 30-degree yaw
    point = (10.0, 20.0, 30.0)
    assert l1.check(vanilla, built) == []
    garret4, idle = seconds("characters/garret4/climb_start"), seconds("characters/balthazar_airship/idle")
    slot, kept, end, window = latch(0x24, idle)
    assert (slot, kept) == (101, True)
    assert math.isclose(end, garret4, rel_tol=1e-6) and math.isclose(window, garret4 / idle, rel_tol=1e-6)
    assert latch(0x24, 1.0)[2:] == (1.0, 1.0)                  # a shorter stand-in's whole window
    assert latch(0x04, idle)[:2] == (-1, True)                 # not the player: as before
    for hook, index, clip in ((0x8B0D4, 0x0B, "touchdown"), (0x8B18C, 0x0B, "touchdown"),
                              (0x8A4E3, 0x44, "hang_start")):
        his_time = seconds(f"characters/garret4/{clip}")
        slot, kept, end, window = latch(0x24, idle, hook, index)
        assert (slot, kept) == (101, True) and math.isclose(end, his_time, rel_tol=1e-6), clip
        assert math.isclose(window, his_time / idle, rel_tol=1e-6), clip
    his = garret4_rung()
    assert point[2] - his[2] > 2.0                             # his feet, 2.27 m below his hands
    assert all(math.isclose(a, b, abs_tol=1e-5) for a, b in zip(rung(0x37), his))
    assert rung(0x37, clip=105) == rung(0x37)                  # a slot another shim filled: the same
    assert rung(0x37, flags=0x04) == point                     # not the player: as before


@pytest.mark.parametrize("hook, index, rate_at, rate", [
    (0x8BDF3, 0x41, 0x86D9E, 1.5), (0x8BDF3, 0x3C, 0x870F7, 1.5), (0x8BDF3, 0x40, 0x87444, 1.5),
    (0x8BDF3, 0x3E, 0x87929, 1.5), (0x8BDF3, 0x3F, 0x87F55, 1.5), (0x8BDF3, 0x35, 0x8B6CD, 2.25),
    (0x8B0D4, 0x0B, None, 1.0), (0x8A4E3, 0x44, None, 1.0)],
    ids=["hoist", "climb_start", "climb_from_jump", "climb_down_edge", "climb_up_edge", "step_up",
         "touchdown", "hang_start"])
def test_an_aligned_move_on_a_stand_in_shorter_than_garret4s_clip_lasts_his_time_at_any_rate(
        hook, index, rate_at, rate):
    """AZ-489 (xemu 2.75b S1-S4, w1's tall ledge: on X9's stand-in the
    hoist held 0x100 for the stand-in's own length, golem's 2.93 s idle
    59 ticks, splinter's 0.8 s 16, fire_shard's one-tick idle 1, against
    garret4's 89; the water tentacles' and catalisk's idles, longer than
    his 4.4 s, held 89, X9 cutting their window): an aligned move plays
    its window t0..t1 of the clip at the layer's rate (+0x20), and each of
    the setter 0x8BDB0's six callers sets that rate right after it through
    0x30940 (the hoist and the ladder's 1.5, [0x1980E0]; step_up's from the
    speed), so a stand-in shorter than garret4's clip ended at its own
    end. X9 multiplies the rate by the stand-in's length over his: at the
    setter's CALL, for the direct calls (touchdown, hang_start), which
    set none after, and at each caller's CALL of 0x30940 (L2: 0x42430
    stubbed as the game starts the clip, a fresh layer at rate 1, then the
    caller's rate), so the window lasts garret4's length over that rate,
    whatever the stand-in's length; a longer stand-in, another species
    and a slot another shim filled keep the caller's rate (on the
    overlord's golem, golem_ol: the bake serves golem's rig since Step
    2.134a)."""
    built = bytes(_swap("overlord and golem")["default.xbe"])
    characters = _vanilla("gamedata/characters.xbr")
    base = 0x20000000
    critter, species, anim, clip, control = (base + k * 0x1000 for k in range(5))
    his = struct.unpack_from("<f", characters, _clip(
        characters, f"characters/garret4/{BASE_CLIPS[index]}")[0] + 0x10)[0]

    def target(va: int) -> int:
        assert built[va_to_file(va)] == 0xE8
        return va + 5 + struct.unpack_from("<i", built, va_to_file(va) + 1)[0]

    def layer(sim: Sim, stand_in: float, anim_index: int, t0: float, t1: float) -> None:
        """The clip on layer 1, active, from t0 to t1 at rate 1, as
        0x42430 starts it, and the move's anim and clip it records."""
        sim.uc.mem_write(anim + 0x10, struct.pack("<I", 1))
        sim.uc.mem_write(anim + 0x84, struct.pack("<I", clip))
        sim.uc.mem_write(anim + 0x98, struct.pack("<f4xff", t0 * stand_in, 1.0, t1 * stand_in))
        sim.uc.mem_write(critter + 0x200, struct.pack("<iI", anim_index, clip))

    def played(stand_in: float, flags: int = 0x24, slot: int = -1) -> float:
        """How long, in s, the move's window plays on a stand-in of
        ``stand_in`` s: its clip time over the layer's rate after the
        hooks."""
        sim = Sim(built)
        table = [-1] * 0x71
        table[1], table[index] = 101, slot
        sim.uc.mem_map(base, 0x10000)
        sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(species + 0x124, struct.pack(f"<{len(table)}i", *table))
        sim.uc.mem_write(clip + 0x10, struct.pack("<f", stand_in))
        sim.uc.mem_write(control + 0x20, struct.pack("<I", critter))
        layer(sim, stand_in, index, 0.0, 1.0)   # as a move left it, for a call that starts none

        def align(uc, addr, size, _):   # 0x42430: the slot's clip on a fresh layer 1, rate 1
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<8I2f", uc.mem_read(esp, 40))
            if struct.unpack("<i", uc.mem_read(species + 0x124 + 4 * args[1], 4))[0] != -1:
                layer(sim, stand_in, args[1], args[7], args[8])
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 40)

        sim.uc.hook_add(UC_HOOK_CODE, align, begin=0x42430, end=0x42430)
        sim.call(target(hook), until=l2._RETURN, args=(
            critter, index, 0, base + 0x5000, base + 0x5010, 0, 0,
            *struct.unpack("<2I", struct.pack("<2f", 0.0, 1.0))))
        if rate_at is not None:   # the caller's rate, through its CALL of 0x30940
            sim.call(target(rate_at), regs={"eax": control}, until=l2._RETURN,
                     args=struct.unpack("<I", struct.pack("<f", rate)))
            assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 4, as 0x30940's
        start, layer_rate, end = struct.unpack("<f4xff", sim.uc.mem_read(anim + 0x98, 16))
        return (end - start) / layer_rate

    for stand_in in (his / 1.5, his / 5.5, 1 / 30):   # as golem's and splinter's idles, fire_shard's tick
        assert math.isclose(played(stand_in), his / rate, rel_tol=1e-5), stand_in
    assert math.isclose(played(2 * his), his / rate, rel_tol=1e-5)   # longer: the window cut
    assert math.isclose(played(his / 2, flags=0x04), his / 2 / rate, rel_tol=1e-6)   # not the player
    assert math.isclose(played(his / 2, slot=105), his / 2 / rate, rel_tol=1e-6)   # another shim's clip


@pytest.mark.parametrize("request_, index", [(1, 0x4B), (6, 0x50), (None, 0x51)],
                         ids=["victory_1", "victory_6", "use"])
def test_a_victory_or_use_on_a_body_without_its_clip_plays_a_stand_in_in_garret4s_time_with_his_hit_immunity(
        request_, index):
    """AZ-444 (xemu 2.75b S1, S4: on flicken own and Balthazar full a
    victory request written in RAM [placed] read back 0 with no anim and
    no 0x100, and a use at e2's keylock played no clip, the lock opening):
    the ground state's 0x887D0 consumes the request (a victory 1-6, anim
    0x4A + it; a use target, anim 0x51) and then drops the move when the
    species' slot is -1 (the CMP at 0x888C2), which X11 leaves empty on
    X9's bodies (since Step 2.121 a victory's only on a body with no
    victory-like clip). X9 takes that CMP, the move's CALL of 0x42430 at 0x88951
    and the hit timer's load of the clip's length at 0x88958 (L2, the
    game's 0x887D0 on the overlord's golem's build, golem_ol, which the
    bake doesn't serve, 0x42430 stubbed as the game starts the clip): for
    the player's species the move plays the stand-in (its idle_1, 1.93 s:
    the use's window cut, victory_1's and victory_6's slowed) in
    garret4's time, the slot put back, and the critter can't
    be hit for his length (+0x1E0, +0x1E4), not the stand-in's; another
    species still drops it, and a clip in the slot keeps its own length."""
    built = bytes(_swap("overlord and golem")["default.xbe"])
    characters = _vanilla("gamedata/characters.xbr")
    assert l1.check(_vanilla("default.xbe"), built) == []
    his = read_body(characters, "garret4").length(BASE_CLIPS[index])
    idle = read_body(characters, "golem_ol").length("idle_1")
    base = 0x20000000
    critter, species, anim, clip, control, physics, holder, target = (base + k * 0x1000 for k in range(8))

    def move(flags: int = 0x24, slot: int = -1) -> tuple[int, int, list[int], bool, float, tuple]:
        """0x887D0 with the request on a species of ``flags`` whose clips
        are an idle and ``slot`` in the move's slot: AL, the state, the
        slots 0x42430 saw, whether they are as they were, how long the
        move's window plays and the hit timer (+0x1E0, +0x1E4, +0x1E8)."""
        sim = Sim(built)
        table = [-1] * 0x71
        table[1], table[index] = 101, slot
        sim.uc.mem_map(base, 0x10000)
        sim.uc.mem_write(critter + 0x154, struct.pack("<I", holder))
        sim.uc.mem_write(holder + 0xD8, struct.pack("<I", holder + 0x100))
        if request_ is None:   # a use target ahead: +0xC set
            sim.uc.mem_write(holder + 0x118, struct.pack("<I", target))
            sim.uc.mem_write(target, struct.pack("<2f4xB", 1.0, 2.0, 1))
        else:
            sim.uc.mem_write(holder + 0x104, struct.pack("<i", request_))
        sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(species + 0x124, struct.pack(f"<{len(table)}i", *table))
        sim.uc.mem_write(clip + 0x10, struct.pack("<f", idle))
        sim.uc.mem_write(control + 0x20, struct.pack("<I", critter))
        sim.uc.mem_write(physics, struct.pack("<I", critter))
        sim.uc.mem_write(physics + 0x7C, struct.pack("<4f", 0.0, 0.0, 0.0, 1.0))
        seen = []

        def align(uc, addr, size, _):   # 0x42430: the slot's clip on a fresh layer 1, rate 1
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<8I2f", uc.mem_read(esp, 40))
            seen.append(struct.unpack("<i", uc.mem_read(species + 0x124 + 4 * args[1], 4))[0])
            if seen[-1] != -1:
                uc.mem_write(anim + 0x10, struct.pack("<I", 1))
                uc.mem_write(anim + 0x84, struct.pack("<I", clip))
                uc.mem_write(anim + 0x98, struct.pack("<f4xff", args[7] * idle, 1.0, args[8] * idle))
                uc.mem_write(critter + 0x200, struct.pack("<iI", args[1], clip))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 40)

        def moved(uc, addr, size, _):   # 0x43170: the glide's offset, a plain RET
            esp = sim.reg("esp")
            uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4)

        sim.uc.hook_add(UC_HOOK_CODE, align, begin=0x42430, end=0x42430)
        sim.uc.hook_add(UC_HOOK_CODE, moved, begin=0x43170, end=0x43170)
        al = sim.call(0x887D0, regs={"eax": physics}, args=(control,)) & 0xFF
        kept = struct.unpack(f"<{len(table)}i", sim.uc.mem_read(species + 0x124, 4 * 0x71))
        start, rate, end = struct.unpack("<f4xff", sim.uc.mem_read(anim + 0x98, 16))
        return (al, sim.u32(control + 0x94), seen, list(kept) == table, (end - start) / rate if rate else 0.0,
                struct.unpack("<2fB", sim.uc.mem_read(critter + 0x1E0, 9)))

    al, state, seen, kept, played, immune = move()
    assert (al, state, seen, kept) == (1, 0x100, [101], True)
    assert math.isclose(played, his, rel_tol=1e-5) and immune == (_f32(his), _f32(his), 0)
    assert move(flags=0x04)[:3] == (0, 0, [])                     # not the player: dropped
    al, state, seen, kept, played, immune = move(slot=105)         # a clip in the slot: its own
    assert (al, seen, kept) == (1, [105], True) and immune[:2] == (_f32(idle), _f32(idle))


@pytest.mark.parametrize("species, anims, pick", [
    ("fire_elemental", "own", "g4/"), ("guard_air", None, "attack_arc"),
    ("good_noreht", None, "idle_3"), ("flicken", None, None), ("town_female_4", "own", None)])
def test_a_body_without_a_victory_plays_garret4s_retargeted_where_its_rig_fits_else_its_own_victory_like_clip(
        species, anims, pick):
    """Step 2.121 (D299, the owner: "for the victory, let's use garret4's
    animation if possible"; D300; xemu 2.117b's L25 and L26: Balthazar
    full and flicken own played their idle stand-in): no body but
    garret4's has a victory clip, and X11 now fills the victory slots
    75-80 with one of his length, unmarked, which 0x887D0 plays and
    times as his. A body his rig fits (retarget.MAPS) plays his victories
    baked onto it in every mode: under a recipe's anims own
    (``anims``), the only clips baked,
    with no marker grown (X9 kept, test_a_baked_body_builds_in_each_mode)
    and its root lifted to its own idle's height, so the fire elemental,
    which hovers 0.3 m in its idle_1, cuts in with its feet where they
    were (within 5 cm; unlifted they dropped 0.33-0.36 m). A body it doesn't
    fit plays its most victory-like own clip (VICTORY_CLIPS: guard_air's
    attack_arc since Step 2.175, AZ-561: its attack_wind sank its tail
    1.59 m under the floor, attack_arc at most 0.95 m) in every mode, a
    copy per garret4 victory length
    (v/victory_1, 3, 5, 6), the clip stretched as a whole to his length
    (a bone at t x k as the clip at t) and without its damage markers'
    and own damage field's tracks, every entry of the table harmless;
    good_noreht's (nice_noreht's, which 24hr wears too) its idle_3, the
    owner's call to try over its mutate (D320, V01; Step 2.126).
    A body with nothing victory-like (flicken) keeps X9's stand-in, and
    so does town_female_4, whose vase no baked clip carries."""
    from azurkit.tools.characters.retarget import Retarget, evaluate, named_clip

    vanilla = _vanilla("gamedata/characters.xbr")
    garret4 = read_body(vanilla, "garret4")
    body = read_body(vanilla, next(m.body for m in player_models(
        _vanilla("gamedata/config.xbr"), vanilla) if m.species == species))
    game = _swap(species, missing_anims=anims)
    built, characters = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    prefix = f"characters/{body.name}/".casefold()
    added = {n[len(prefix):] for n in set(named_resources(characters).values()) - set(named_resources(vanilla).values())
             if n.casefold().startswith(prefix)}
    victories = [f"victory_{v}" for v in range(1, 7)]
    slots = [_x11_names(built).get(slot) for slot in range(75, 81)]
    if pick is None:
        assert slots == [None] * 6 and not added and (body.name.casefold() in KEEPS_STAND_IN) == (anims == "own")
    elif pick == "g4/":
        assert slots == [f"g4/{v}" for v in victories] and added == set(slots)
        assert read_body(characters, body.name).markers == body.markers
        rt = Retarget(vanilla, body.name)
        stand = named_clip(vanilla, body.name, _x11_names(built)[1])

        def low(clip) -> float:
            at = origins(rt.target, clip, 0.0)
            return min(at[k][2] for k in rt.source)

        for v in victories:
            mine = named_clip(characters, body.name, f"g4/{v}")
            assert mine.length == _f32(garret4.length(v)) and abs(low(mine) - low(stand)) < 0.05, v
    else:
        firsts = ["victory_1", "victory_1", "victory_3", "victory_3", "victory_5", "victory_6"]
        # W22's death copy (Step 2.131, AZ-603) and W25's held swim (Step 2.134a, D341)
        quiet = {"q/die", "h/run_begin"} if species == "guard_air" else set()
        assert slots == [f"v/{v}" for v in firsts] and added == set(slots) | quiet
        own = named_clip(vanilla, body.name, pick)
        for v in sorted(set(firsts)):
            mine, k = named_clip(characters, body.name, f"v/{v}"), garret4.length(v) / own.length
            assert mine.length == _f32(garret4.length(v)), v
            track = next(tr for tr in own.bones if len({key[1] for key in tr.keys}) > 1)
            theirs = next(tr for tr in mine.bones if (tr.target, tr.comp) == (track.target, track.comp))
            for t in (0.1, 0.37, 0.5, 0.81):
                assert math.isclose(evaluate(theirs.keys, t * own.length * k), evaluate(track.keys, t * own.length),
                                    rel_tol=1e-5, abs_tol=1e-6), (v, t)
        for name in sorted(VICTORY_CLIPS):   # every entry: a clip of the body's, harmless as a victory
            other, switches, marks = read_body(vanilla, name), field_switches(vanilla, name), marker_records(vanilla, name)
            off = {i for i, (m, _) in enumerate(marks) if m in DAMAGE_MARKERS or m in switches}
            assert all(marks[i][1][11] < 0.5 for i in off), name   # each held off by its default
            copies = victory_copies(vanilla, other, garret4, switches)
            assert {n: c.length for n, c in copies.items()} == {
                f"v/{v}": garret4.length(v) for v in set(firsts)} and VICTORY_CLIPS[name] in other.clips, name
            assert not any(tr.target in off for c in copies.values() for tr in c.markers), name


@pytest.mark.parametrize("species, scale, kw", [
    ("overlord and golem", 1.0, {}), ("overlord and golem", 2.0, {}), ("town_male_6", 2.0, {}),
    ("town_male_6", 1.0, {}), ("keylord", 2.0, {}), ("keylord", 1.0, {}), ("kingkong", 2.0, {"size": "garret4"})])
def test_a_body_hangs_from_the_zipline_where_garret4_does_its_offset_drawn_at_the_model_scale(species, scale, kw):
    """AZ-443 (xemu 2.75c: flicken own rode f3's zipline with its feet on
    the cable, where garret4 hangs 3.2-3.7 m below it): the ride (state
    5, 0x8A510) hands anim_apply_translation (0x42E40, at 0x8AB32) the
    cable point with "m_grab", which places the model so that its m_grab
    sits there, and an X9 body has none; hang_start's target (0x8A4E3) is
    the cable point on these bodies (0x84A40's entries for its empty slot
    are zero), so its glide ended there too, or a body's own m_root's
    height off it. X9 (L2, the overlord's golem's build, golem_ol, unbaked;
    golem's own is baked since Step 2.134a): at 0x8AB32 the point 0x42E40
    gets is the cable point less garret4's m_grab in hang at t 0 (the
    vanilla 0xCAB80 on his clip), turned by the ride's turn (the vanilla
    0xA1420), EAX and ECX passed on and the stack as 0x42E40's RET 0x10
    leaves it; and after hang_start's 0x42430 its glide end (+0x1BC) is
    where garret4's ends, his target (the point plus his m_root less his
    m_grab at its end, turned) less his m_root, whatever the stand-in's
    own m_root put there; another species keeps both, and a clip in the
    slot the end it played to. AZ-526 (Step 2.104; sitting 2.103's row C:
    neither 0x42E40 nor 0x42430 reads the critter's scale, so at model
    scale 2 town_male_6's top rode 2.6 m above the cable, 3.15 m higher
    than at x1): a body drawn X times its size hangs X times x1's offset
    below it, the ride's point X x garret4's m_grab under the cable and
    hang_start's stand-in ending X x his end m_grab under it, and a clip
    of its own (X - 1) x that under the game's end; a baked body, whose
    own (garret4's) m_grab the game already hangs, (X - 1) x his on the
    ride, and above or below x1 only gets those two landings. AZ-529
    (Step 2.106): X times garret4's offset hangs each body's own pose
    where its height puts it (town_male_6 x2's top 1.07 m under the cable,
    kingkong's at garret4's height x2 3.91 m under, keylord x2's 1.02 m
    over it, across its torso: sitting 2.104 and the hang clip's bones),
    so away from x1 X is the build's X' (its climb_scale), at which the
    top of the hang pose the body plays (a baked body's g4/hang, X9's
    stand-in) at its highest over the clip's loop (Step 2.175b, AZ-599),
    drawn at the build's scale, sits 0.05 m under the cable, as
    garret4's 3.645 m top does under his 3.693 m grab. Since
    Step 2.118 (AZ-536, D291, D292) x1 too: town_male_6 own x1 (X' 0.87)
    and keylord own x1 (drawn at 2.0, its top 0.51 m over the cable at
    garret4's grab) hang their top at it, golem_ol own x1 at 0.991 (its
    idle_1, X9's stand-in in the hang slot), golem own x1 at 1.787 (its
    g4/hang's hands overhead, baked since Step 2.134a)."""
    vanilla = _vanilla("default.xbe")
    game = _swap(species, model_scale=scale, **kw)
    built = bytes(game["default.xbe"])
    body = XbrDocument.from_bytes(_vanilla("gamedata/config.xbr")).keyed_section(
        "critters_engine").find_cell(species, "body").string_value
    baked = body.casefold() in BAKED_BODIES
    grown = bytes(game["characters.xbr"])
    drawn = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("critters_engine").find_cell(
        "garret4", "scale").double_value
    key = {name.casefold(): i for i, name in named_resources(grown).items()}[   # its hang: g4/hang, X9's stand-in
        f"characters/{body}/{_x11_names(built)[0x43]}".casefold()]
    hung_clip, hung_rig = read_clip(grown, parse_toc(grown)[key].file_offset), Rig.read(grown, body)
    top = max(z for t in hang_loop(hung_clip) for _, _, z in origins(hung_rig, hung_clip, t))   # its loop's (AZ-599)
    want = (drawn * top + 0.05) / 3.69323754
    model_scale, scale = scale, struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, CLIMB_HOOKS[[h.va for h in CLIMB_HOOKS].index(0x8AB32)], "_player_model_climb_scale",
        shim_source=CLIMB_SHIM.source_path())))[0]
    assert math.isclose(scale, want, rel_tol=1e-5)
    k = scale - baked      # the ride's: 0x42E40 takes off a baked body's own
    characters = _vanilla("gamedata/characters.xbr")
    assert l1.check(vanilla, built) == []
    base = 0x20000000
    critter, species, anim, clip, names = (base + k * 0x1000 for k in range(5))
    turn = (0.0, 0.0, math.sin(math.radians(20)), math.cos(math.radians(20)))   # a 40-degree yaw
    cable = (10.0, 20.0, 30.0)
    hang_start = read_body(characters, "garret4").length("hang_start")

    def target(va: int) -> int:
        assert built[va_to_file(va)] == 0xE8
        return va + 5 + struct.unpack_from("<i", built, va_to_file(va) + 1)[0]

    def ride(flags: int) -> tuple[tuple[float, ...], int, int]:
        """The point, EAX and ECX the hooked CALL at 0x8AB32 hands 0x42E40."""
        sim = Sim(built)
        sim.uc.mem_map(base, 0x10000)
        sim.uc.mem_write(critter + 0x178, struct.pack("<I", species))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(names, struct.pack("<4f", *turn))
        sim.uc.mem_write(names + 0x20, struct.pack("<3f", *cable))
        seen = []

        def apply(uc, addr, size, _):   # 0x42E40: thiscall, RET 0x10
            esp = sim.reg("esp")
            ret, who, _t, _node, point = struct.unpack("<5I", uc.mem_read(esp, 20))
            seen.append((struct.unpack("<3f", uc.mem_read(point, 12)), sim.reg("eax"), sim.reg("ecx")))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 0x14)

        sim.uc.hook_add(UC_HOOK_CODE, apply, begin=0x42E40, end=0x42E40)
        sim.call(target(0x8AB32), regs={"eax": base + 0x7000, "ecx": names}, until=l2._RETURN,
                 args=(critter, 0, names + 0x40, names + 0x20))
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0x10, as 0x42E40's
        return seen[0]

    def hang(flags: int, root: float, slot: int = -1) -> tuple[float, ...]:
        """hang_start's glide end (+0x1BC) after its hooked CALL at
        0x8A4E3 on a species with ``flags`` whose clips are an idle and
        ``slot``, 0x42430 (stubbed) ending the glide with an m_root of
        ``root`` m over the target, as the stand-in's own puts it."""
        sim = Sim(built)
        table = [-1] * 0x71
        table[1], table[0x44] = 101, slot
        sim.uc.mem_map(base, 0x10000)
        sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        sim.uc.mem_write(species + 0x124, struct.pack(f"<{len(table)}i", *table))
        sim.uc.mem_write(clip + 0x10, struct.pack("<f", 1.0))
        sim.uc.mem_write(names, struct.pack("<4f", *turn))
        sim.uc.mem_write(names + 0x20, struct.pack("<3f", *cable))

        def align(uc, addr, size, _):   # 0x42430: the slot's clip on layer 1, the glide's end
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<8I2f", uc.mem_read(esp, 40))
            if struct.unpack("<i", uc.mem_read(species + 0x124 + 4 * args[1], 4))[0] != -1:
                uc.mem_write(anim + 0x10, struct.pack("<I", 1))
                uc.mem_write(anim + 0x84, struct.pack("<I", clip))
                uc.mem_write(anim + 0x98, struct.pack("<f4xff", 0.0, 1.0, 1.0))
                uc.mem_write(critter + 0x1BC, struct.pack("<3f", *cable[:2], cable[2] - root))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 40)

        sim.uc.hook_add(UC_HOOK_CODE, align, begin=0x42430, end=0x42430)
        sim.call(target(0x8A4E3), until=l2._RETURN, args=(
            critter, 0x44, 0, names + 0x20, names, 0, 0,
            *struct.unpack("<2I", struct.pack("<2f", 0.0, 1.0))))
        return struct.unpack("<3f", sim.uc.mem_read(critter + 0x1BC, 12))

    grab = _garret4_node(characters, "hang", "m_grab", 0.0, turn)
    point, eax, ecx = ride(0x24)
    assert (eax, ecx) == (base + 0x7000, names)
    assert all(math.isclose(a, c - k * g, abs_tol=1e-5) for a, c, g in zip(point, cable, grab))
    assert grab[2] > 3.6                                       # his origin 3.7 m under the cable
    assert ride(0x04)[0] == cable                              # not the player: as before
    root, end_grab = (_garret4_node(characters, "hang_start", node, hang_start, turn) for node in ("m_root", "m_grab"))
    his_target = tuple(c + r - g for c, r, g in zip(cable, root, end_grab))   # 0x8A40B's, his offsets
    garret4s = tuple(t - r for t, r in zip(his_target, root))   # where 0x42430 ends his glide
    if not baked:   # X9's stand-in: X x his end under the cable
        for own_root in (0.0, 2.111):                          # none, or gargoyle's m_root
            assert all(math.isclose(a, c - scale * (c - b), abs_tol=1e-5)
                       for a, b, c in zip(hang(0x24, own_root), garret4s, cable))
    game_end = (*cable[:2], cable[2] - 2.111)
    assert hang(0x04, 2.111, slot=105) == (*cable[:2], _f32(cable[2] - 2.111))   # not the player
    assert all(math.isclose(a, e - (scale - 1) * g, abs_tol=1e-5)         # a clip of its own
               for a, e, g in zip(hang(0x24, 2.111, slot=105), game_end, end_grab))


def test_a_one_bone_body_hangs_from_the_zipline_by_its_mesh_top_where_its_bone_holds_it():
    """AZ-536's N1 (Step 2.118; its critique's point 9): X9 hangs a body by
    the top of its hang pose, which it took as the highest posed bone, but
    61 bodies have one bone and are drawn by their mesh around it (ruby's
    bone rides 1.0 unit up at t 0 of its idle, its mesh 0.212 over the
    bone; key_fire1's bone at its origin, its mesh 1.03 over it), so the
    top is the highest vertex moved by the bone's pose at t 0 of the clip
    its hang slot plays: ruby own x1 hangs X' = (D x 1.212 + 0.05) / 3.693
    times garret4's grab under the cable, its gem's top at the cable."""
    game = _swap("ruby", sounds="garret4")
    built, grown = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    body = read_body(grown, "ruby")
    cell = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("critters_engine").find_cell(
        "garret4", "scale")
    drawn = cell.double_value if cell.type_code == 1 else 1.0
    top = max(p[2] for p in mesh_points(grown, "ruby")) + 1.0     # the idle's bone 1.0 up, unturned
    scale = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, CLIMB_HOOKS[[h.va for h in CLIMB_HOOKS].index(0x8AB32)], "_player_model_climb_scale",
        shim_source=CLIMB_SHIM.source_path())))[0]
    assert len(body.bones) == 1 and math.isclose(scale, (drawn * top + 0.05) / 3.69323754, rel_tol=1e-5) and scale < 1


def test_a_body_whose_hang_clip_bobs_keeps_its_top_under_the_zipline_cable_over_the_whole_ride():
    """AZ-599 (Step 2.175b): X9 hung a body by its hang clip's top at t 0,
    so a top that rises over the loop the ride plays passed over the
    cable: water_tentacle1 own x1's idle (X9's stand-in in the hang slot)
    lifts its top 3.5 m over its t 0 one, key_air1 own x2's 7.95 m over
    the cable on 265 of 280 ride ticks (sitting 2.175b's frames). X'
    hangs the highest the top reaches over that loop 0.05 m under the
    cable, so at every time of the loop, sampled finer than a tick at the
    ride's X12 rate, the drawn top stays at least 0.05 m under the cable
    and meets that line at its highest."""
    game = _swap("water_tentacle1", sounds="garret4")
    built, grown = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    body = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("critters_engine").find_cell(
        "water_tentacle1", "body").string_value
    cell = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("critters_engine").find_cell(
        "garret4", "scale")
    drawn = cell.double_value if cell.type_code == 1 else 1.0
    key = {name.casefold(): i for i, name in named_resources(grown).items()}[
        f"characters/{body}/{_x11_names(built)[0x43]}".casefold()]
    clip, rig = read_clip(grown, parse_toc(grown)[key].file_offset), Rig.read(grown, body)
    hung = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, CLIMB_HOOKS[[h.va for h in CLIMB_HOOKS].index(0x8AB32)], "_player_model_climb_scale",
        shim_source=CLIMB_SHIM.source_path())))[0]
    tops = [drawn * max(z for _, _, z in origins(rig, clip, clip.length * k / 960)) for k in range(961)]
    under = [hung * 3.69323754 - t for t in tops]   # the cable less the drawn top, m
    assert max(tops) - tops[0] > 3.0                    # its top bobs: t 0 is 3 m under its highest
    assert min(under) == pytest.approx(0.05, abs=0.005) and all(u > 0.045 for u in under)


def test_a_body_drawn_at_a_model_scale_eases_off_the_zipline_to_its_stance_a_step_a_placement():
    """AZ-529 (Step 2.105, X22): X9's ride hangs a body drawn x2 twice
    garret4's grab under the cable, so its drawn origin rode 5.4-5.6 m
    under its centre, and the let-go's placement (0x42E40 at 0x89290)
    and the airborne tick's (0x8996D, the cable's end too) put it 1.0 m
    under in one tick: a 4.55-4.64 m pop (sitting 2.104; the control
    0.85 m). X22 (L2, town_male_6 own x2's build, 0x42E40 stubbed to put
    the centre at EAX's point and the origin at the pushed point, glide
    mode 0) at the let-go, the wing flap (0x8944E) and the airborne tick:
    the game's call with the caller's ECX, EAX and arguments, then the
    drawn offset (origin less centre) moves from where it was drawn
    toward the game's at most 0.847 m a placement, reaching the stance in
    6 placements while the centre falls as the game moves it; a new
    offset within a step, one past the build's span (|X' - 1| x 3.693 +
    2 m, X' X9's hang scale, 1.724 here since Step 2.175b: a teleport), a
    gliding body and another critter keep the game's
    placement. RET 0x10, EBX, ESI, EDI and EBP kept, the x87 stack empty.
    golem own x2 (X9's) gets it too; a build at x1 keeps the three CALLs."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap("town_male_6", sounds="garret4", model_scale=2.0)["default.xbe"])
    assert l1.check(vanilla, built) == []
    span = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, HANG_EASE_HOOKS[0], "_player_model_hang_span", shim_source=HANG_EASE_SHIM.source_path())))[0]
    hung = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, CLIMB_HOOKS[[h.va for h in CLIMB_HOOKS].index(0x8AB32)], "_player_model_climb_scale",
        shim_source=CLIMB_SHIM.source_path())))[0]
    assert round(hung, 3) == 1.724 and math.isclose(span, (hung - 1) * 3.69323754 + 2.0, rel_tol=1e-5)
    base = 0x20000000
    critter, species, centre_at, point_at, turn = (base + 0x1000 * k for k in range(5))

    def place(hook, was: tuple, at: tuple, *, player: bool = True, mode: int = 0, drop: float = 0.3):
        """One placement through ``hook``'s shim: the body drawn ``was``
        off a centre ``at``, the game's placing m_feet 1.0 m under the
        centre ``drop`` m lower; the drawn offset after, the new centre."""
        sim = Sim(built)
        sim.uc.mem_map(base, 0x5000)
        new = (at[0], at[1], at[2] - drop)
        for at_, fmt, value in ((critter + 0x15C, "<3f", at), (critter + 0x178, "<I", species),
                                (critter + 0x19C, "<i", mode), (critter + 0x1B0, "<3f", tuple(map(sum, zip(at, was)))),
                                (critter + 0x1BC, "<3f", tuple(map(sum, zip(at, was)))),
                                (species + 0x64, "<I", 0x24 if player else 0x04), (centre_at, "<3f", new),
                                (point_at, "<3f", (new[0], new[1], new[2] - 1.0))):
            sim.uc.mem_write(at_, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        calls = []

        def translate(uc, addr, size, _):   # 0x42E40: ECX the turn, EAX the centre; RET 0x10
            esp = sim.reg("esp")
            ret, who, blend, marker, point = struct.unpack("<5I", uc.mem_read(esp, 20))
            calls.append((sim.reg("ecx"), sim.reg("eax"), who, blend, marker, point))
            uc.mem_write(who + 0x15C, bytes(uc.mem_read(sim.reg("eax"), 12)))
            for off in (0x1B0, 0x1BC):
                uc.mem_write(who + off, bytes(uc.mem_read(point, 12)))
            uc.mem_write(who + 0x19C, struct.pack("<i", 0))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 20)

        sim.uc.hook_add(UC_HOOK_CODE, translate, begin=0x42E40, end=0x42E40)
        entry = hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]
        kept = {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
        sim.call(entry, regs={"ecx": turn, "eax": centre_at, **kept},
                 args=(critter, 0, 0x5A5A, point_at), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0x10, as 0x42E40's
        assert {r: sim.reg(r) for r in kept} == kept
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        assert calls == [(turn, centre_at, critter, 0, 0x5A5A, point_at)]
        drawn, again = (struct.unpack("<3f", sim.uc.mem_read(critter + off, 12)) for off in (0x1B0, 0x1BC))
        assert drawn == again
        now = struct.unpack("<3f", sim.uc.mem_read(critter + 0x15C, 12))
        return tuple(d - c for d, c in zip(drawn, now)), now

    letgo, flap, airborne = HANG_EASE_HOOKS
    was, at, steps = (0.3, 0.1, -5.4), (1.0, 2.0, 10.0), []
    for hook in (letgo, *[airborne] * 6):
        now_was, at = place(hook, was, at)
        steps.append(math.dist(now_was, was))
        was = now_was
    assert all(s <= 0.847 + 1e-4 for s in steps) and steps[:5] == pytest.approx([0.847] * 5, abs=1e-4)
    assert was == pytest.approx((0.0, 0.0, -1.0), abs=1e-4) and steps[6] == pytest.approx(0.0, abs=1e-4)
    assert math.dist(place(flap, (0.3, 0.1, -5.4), at)[0], (0.3, 0.1, -5.4)) == pytest.approx(0.847, abs=1e-4)
    for kw, was in (({}, (0.0, 0.0, -1.5)), ({}, (0.0, 30.0, -1.0)), ({"mode": 2}, (0.3, 0.1, -5.4)),
                    ({"player": False}, (0.3, 0.1, -5.4))):
        assert place(airborne, was, at, **kw)[0] == pytest.approx((0.0, 0.0, -1.0), abs=1e-4), (kw, was)
    assert {verify_trampoline_patch(bytes(_swap("golem", sounds="garret4", model_scale=2.0)["default.xbe"]), hook)
            for hook in HANG_EASE_HOOKS} == {"applied"}
    for species_ in ("golem", "town_male_6"):   # x1: X' 1.006, 0.87
        one = bytes(_swap(species_, sounds="garret4")["default.xbe"])
        assert {verify_trampoline_patch(one, hook) for hook in HANG_EASE_HOOKS} == {"applied"}, species_


def test_a_body_eases_off_the_zipline_from_where_its_aligned_node_term_drew_it():
    """AZ-600 (Step 2.175b, X22): the draw adds 0x402E0's aligned-node
    term to the origin, and the let-go and the cable's end change it in
    the tick X22 eases (the airborne clip's layer started, the node
    m_feet): frag_air_1 own x1's frame dropped 2.0 m on its first
    airborne tick, 1.184 of it the term, while X22 moved the origin
    0.79 m (sitting 2.127 C; the layer on at 0.01 at X22's landing,
    sitting 2.175b). X22 (L2, frag_air_1 own x1's build; 0x42E40 stubbed
    as in the X22 pin, 0x402E0 to a term the test sets, the critter's
    clock at +0xE4) eases the drawn offset, origin plus term, at most
    0.847 m a placement: the let-go from the ride's drawn offset (its
    term 0, not 0x402E0's before the call, which reads the ride's m_grab
    in the jump clip that keys none: garret4's -2.24, the review's F1)
    toward the game's (origin 1.0 m under the centre, term -1.121), the
    next airborne tick from the term the let-go's landing kept in the
    airborne landing's block (not 0x402E0's before the call), then the
    game's; a kept term older than 0.1 s isn't used: 0x402E0's before
    the call off the ground, 0 off the ladder."""
    built = bytes(_swap("frag_air_1", sounds="garret4")["default.xbe"])
    base = 0x20000000
    critter, species, centre_at, point_at, turn, clock, control = (base + 0x1000 * k for k in range(7))
    sim = Sim(built)
    sim.uc.mem_map(base, 0x7000)
    for at_, fmt, value in ((critter + 0xE4, "<I", clock), (critter + 0x178, "<I", species),
                            (critter + 0x180, "<I", control), (species + 0x64, "<I", 0x24)):
        sim.uc.mem_write(at_, struct.pack(fmt, value))
    term = {"before": (0.0, 0.0, 0.0), "after": (0.0, 0.0, 0.0), "now": "before"}

    def translate(uc, addr, size, _):   # 0x42E40: the centre from EAX, the origin at the point; RET 0x10
        esp = sim.reg("esp")
        ret, who, _blend, _marker, point = struct.unpack("<5I", uc.mem_read(esp, 20))
        uc.mem_write(who + 0x15C, bytes(uc.mem_read(sim.reg("eax"), 12)))
        for off in (0x1B0, 0x1BC):
            uc.mem_write(who + off, bytes(uc.mem_read(point, 12)))
        term["now"] = "after"
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 20)

    def node(uc, addr, size, _):   # 0x402E0: EDI the out, EAX = EDI; a plain RET
        esp, out = sim.reg("esp"), sim.reg("edi")
        uc.mem_write(out, struct.pack("<3f", *term[term["now"]]))
        uc.reg_write(UC_X86_REG_EAX, out)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    sim.uc.hook_add(UC_HOOK_CODE, translate, begin=0x42E40, end=0x42E40)
    sim.uc.hook_add(UC_HOOK_CODE, node, begin=0x402E0, end=0x402E0)

    def place(hook, t: float, was: tuple, before: tuple, after: tuple, last: int = 2) -> float:
        """One placement at clock ``t``, the PlayerControl's last tick in state ``last``: the origin ``was``
        off the centre, 0x402E0's term ``before`` and ``after`` the game's call (which puts the origin 1.0 m
        under a centre 0.3 m lower); the drawn offset's z after (origin plus the new term, against the new
        centre)."""
        at = (1.0, 2.0, 10.0)
        new = (at[0], at[1], at[2] - 0.3)
        for at_, value in ((critter + 0x15C, at), (critter + 0x1B0, tuple(map(sum, zip(at, was)))),
                           (critter + 0x1BC, tuple(map(sum, zip(at, was)))), (centre_at, new),
                           (point_at, (new[0], new[1], new[2] - 1.0))):
            sim.uc.mem_write(at_, struct.pack("<3f", *value))
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", t))
        sim.uc.mem_write(control + 0x98, struct.pack("<i", last))
        term.update(before=before, after=after, now="before")
        entry = hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]
        sim.call(entry, regs={"ecx": turn, "eax": centre_at}, args=(critter, 0, 0x5A5A, point_at), until=l2._RETURN)
        origin = struct.unpack("<3f", sim.uc.mem_read(critter + 0x1BC, 12))
        return origin[2] - new[2] + after[2]

    letgo, _flap, airborne = HANG_EASE_HOOKS
    z1 = place(letgo, 10.0, (0.0, 0.0, -0.2), (0.0, 0.0, -2.24), (0.0, 0.0, -1.121), last=5)
    assert z1 == pytest.approx(-0.2 - 0.847, abs=1e-4)              # a step from the ride's term 0, not the game's -2.121
    origin1 = z1 + 1.121
    z2 = place(airborne, 10.0 + 1 / 30, (0.0, 0.0, origin1), (0.0, 0.0, -5.0), (0.0, 0.0, -0.959), last=5)
    assert z2 == pytest.approx(z1 - 0.847, abs=1e-4)                # from the kept term, not 0x402E0's -5.0
    z3 = place(airborne, 10.0 + 2 / 30, (0.0, 0.0, z2 + 0.959), (0.0, 0.0, -5.0), (0.0, 0.0, -0.74))
    assert z3 == pytest.approx(-1.0 - 0.74, abs=1e-4)               # within a step: the game's
    stale = place(airborne, 20.0, (0.0, 0.0, -0.2), (0.0, 0.0, -0.3), (0.0, 0.0, -1.121), last=0)
    assert stale == pytest.approx(-0.5 - 0.847, abs=1e-4)           # 10 s on, off the ground: 0x402E0's before the call
    ladder = place(letgo, 30.0, (0.0, 0.0, -0.2), (0.0, 0.0, -2.24), (0.0, 0.0, -1.121), last=1)
    assert ladder == pytest.approx(-0.2 - 0.847, abs=1e-4)          # off the ladder: its term 0


def test_a_body_landing_inside_x22s_ease_goes_on_easing_to_its_stance_on_the_ground_a_step_a_tick():
    """AZ-711 (Step 2.189b, X22): a body that lands while X22 still eases
    it off the zipline was put at its stance by the walk's placement
    (0x42E40 at 0x866D9, which X22 doesn't take) in one tick: key_air1
    own x2 popped 9.53 m landing off the cable's end on the ease's 7th
    tick (sitting 2.175b). X22's fourth landing (L2, town_male_6 own x2's
    build; 0x42E40, 0x402E0 and the classifier 0x85920 stubbed) at the
    walk's CALL of the classifier right after that placement: from where
    the last placement drew the body (the shared block's offset, the same
    critter within 0.1 s, an ease not done) the drawn offset goes on a
    step a tick to the game's stance, then the walk is the game's; a walk
    with no ease left, one 0.2 s after the last placement and another
    critter's are the game's; a jump from the ground reads 0x402E0's term
    before its call, not the walk's kept one. The classifier gets the
    caller's three arguments and ESI; RET 0xC, EBX, ESI, EDI and EBP
    kept, the x87 stack empty. The build lands it with the shared block."""
    built = bytes(_swap("town_male_6", sounds="garret4", model_scale=2.0)["default.xbe"])
    letgo, _flap, airborne = HANG_EASE_HOOKS
    block = trampoline_symbol_va(built, airborne, EASE_STATE, shim_source=HANG_EASE_SHIM.source_path())
    assert struct.unpack_from("<I", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, HANG_EASE_GROUND, "_player_model_ease_shared", shim_source=HANG_EASE_SHIM.source_path())))[0] == block
    base = 0x20000000
    critter, species, centre_at, point_at, turn, clock, control, other, args = (base + 0x1000 * k for k in range(9))
    sim = Sim(built)
    sim.uc.mem_map(base, 0x9000)
    for who in (critter, other):
        for at_, value in ((who + 0xE4, clock), (who + 0x178, species), (who + 0x180, control)):
            sim.uc.mem_write(at_, struct.pack("<I", value))
    sim.uc.mem_write(species + 0x64, struct.pack("<I", 0x24))
    term, classified = {"before": 0.0, "after": 0.0, "now": "after"}, []

    def translate(uc, addr, size, _):   # 0x42E40: the centre from EAX, the origin at the point; RET 0x10
        esp = sim.reg("esp")
        ret, who, _blend, _marker, point = struct.unpack("<5I", uc.mem_read(esp, 20))
        uc.mem_write(who + 0x15C, bytes(uc.mem_read(sim.reg("eax"), 12)))
        for off in (0x1B0, 0x1BC):
            uc.mem_write(who + off, bytes(uc.mem_read(point, 12)))
        term["now"] = "after"
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 20)

    def node(uc, addr, size, _):   # 0x402E0: EDI the out, (0, 0, the term); EAX = EDI, a plain RET
        esp, out = sim.reg("esp"), sim.reg("edi")
        uc.mem_write(out, struct.pack("<3f", 0.0, 0.0, term[term["now"]]))
        uc.reg_write(UC_X86_REG_EAX, out)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    def classify(uc, addr, size, _):   # 0x85920: ESI the PlayerControl, three arguments, RET 0xC
        esp = sim.reg("esp")
        classified.append((sim.reg("esi"), *struct.unpack("<3I", uc.mem_read(esp + 4, 12))))
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 16)

    for va, hook in ((0x42E40, translate), (0x402E0, node), (0x85920, classify)):
        sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)

    def entry(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]

    def place(hook, t: float, was: float, *, last: int = 2, who: int = critter, before: float = 0.0,
              after: float = 0.0) -> float:
        """One airborne placement at clock ``t``: the body drawn ``was`` m off its centre, the game's putting
        m_feet 1.0 m under a centre 0.3 m lower; the drawn offset's z after (origin plus term)."""
        at, new = (1.0, 2.0, 10.0), (1.0, 2.0, 9.7)
        for at_, value in ((who + 0x15C, at), (who + 0x1B0, (1.0, 2.0, 10.0 + was - before)),
                           (who + 0x1BC, (1.0, 2.0, 10.0 + was - before)), (centre_at, new), (point_at, (1.0, 2.0, 8.7))):
            sim.uc.mem_write(at_, struct.pack("<3f", *value))
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", t))
        sim.uc.mem_write(control + 0x98, struct.pack("<i", last))
        term.update(before=before, after=after, now="before")
        sim.call(entry(hook), regs={"ecx": turn, "eax": centre_at}, args=(who, 0, 0x5A5A, point_at), until=l2._RETURN)
        return struct.unpack("<3f", sim.uc.mem_read(who + 0x1BC, 12))[2] - 9.7 + after

    def walk(t: float, *, who: int = critter) -> float:
        """One walk tick at clock ``t``: the game's placement put the origin 1.0 m under the centre; the
        drawn offset's z after the hook (origin plus term 0)."""
        sim.uc.mem_write(who + 0x15C, struct.pack("<3f", 1.0, 2.0, 10.0))
        for off in (0x1B0, 0x1BC):
            sim.uc.mem_write(who + off, struct.pack("<3f", 1.0, 2.0, 9.0))
        sim.uc.mem_write(args, struct.pack("<I", who))
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", t))
        term.update(after=0.0, now="after")
        del classified[:]
        kept = {"ebx": 0x11, "esi": control, "edi": 0x33, "ebp": 0x44}
        sim.call(entry(HANG_EASE_GROUND), regs=kept, args=(args, args + 0x100, args + 0x200), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and {r: sim.reg(r) for r in kept} == kept
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        assert classified == [(control, args, args + 0x100, args + 0x200)]
        a, b = (struct.unpack("<3f", sim.uc.mem_read(who + off, 12)) for off in (0x1B0, 0x1BC))
        assert a == b and a[:2] == (1.0, 2.0)
        return a[2] - 10.0

    t = 10.0
    z = place(letgo, t, -5.4, last=5)                                  # off the cable: a step from the hang
    for k in (1, 2):
        z = place(airborne, t + k / 30, z)
    assert z == pytest.approx(-5.4 + 3 * 0.847, abs=1e-4)
    steps = [walk(t + k / 30) for k in range(3, 7)]                   # landed: the ease goes on on the ground
    assert steps == [pytest.approx(v, abs=1e-4) for v in (z + 0.847, z + 2 * 0.847, -1.0, -1.0)]
    assert walk(t + 7 / 30) == -1.0                                    # no ease left: the game's
    jump = place(airborne, t + 8 / 30, -1.0 - 1.2, last=0, before=-1.2, after=-1.2)
    assert jump == pytest.approx(-1.0 - 1.2, abs=1e-4)                # 0x402E0's term before the call, not the walk's 0
    z = place(airborne, 50.0, -5.4, last=5)
    assert walk(50.2) == -1.0                                          # 0.2 s after the last placement
    z = place(airborne, 60.0, -5.4, last=5)
    assert walk(60.0 + 1 / 30, who=other) == -1.0                      # another critter


def test_a_big_bodys_landing_is_held_at_the_floor_exactly_and_its_let_go_and_takeoff_over_it_a_step_a_tick():
    """AZ-706, AZ-711 (Step 2.189b, X48): over a move's first ticks the
    anim layers cross from the old clip into the new, and on a body drawn
    larger than garret4 the blend can swing the pose far under its
    origin: guard_air own x2's lowest point 3.29 m under it 4 ticks after
    letting go of f3's cable (sittings 2.118c, 2.175b), 2.95 m through the
    end platform 2 ticks after landing off the cable's end and 3.15 m 5
    ticks into f6's jump landing (sittings 2.127, 2.118c). Step 2.175b's
    let-go hold (X22, a table of the crossfade's least) lifted it up to
    3.95 m over the floor where its own pose had risen, and left it 2.56 m
    over its stance when it landed inside the hold (a 3.56 m drop in a
    tick, sitting 2.175b); landings had none. X48 (L2, guard_air own x2's
    build; 0x42070, 0x402E0 and collision_sweep stubbed) at
    critter_model_matrix's CALL of glide_origin: for 12 ticks after the
    PlayerControl's last tick started on the ride (+0x98 5) and left it,
    or started airborne (2) and landed (state 0, or 0x100 the hard
    landing's touchdown), the drawn origin is raised by how far its
    lowest point (the origin, the term and D x the lowest posed bone,
    less the build's sole) lies under the floor under the centre plus the
    build's fade_low (the ground clips' own lowest), the lift moving at
    most 0.847 m a tick of the clock from the last clock's (D293's step:
    held exactly, it jerked guard_air own x2's drawn body and the camera
    2.11 m in a tick at f3's cable's end, sitting 2.189b), a frame drawn
    again on the same clock the same; past the 12 ticks it lets go a step
    a tick, no more than the pose still needs (it dropped 3.76 m where the
    window ended mid-dip). Since Step 2.199 (AZ-706) a takeoff arms it
    too, the last tick started on the ground, a slope or an aligned move
    (0, 3, 4, 0x100) and the state now airborne: the jump's and the fall's
    anim changes restart their clip, and guard_air own x2's lowest point
    went 2.84 m through the floor 3 ticks into f6's standing jump and 3.82
    m 3 ticks after running off a ledge (Step 2.189b's record sitting),
    where the hold had armed on none. Since Step 2.200 (AZ-706, D800:
    "Stop at the floor") a landing's lift is the shortfall each tick of
    its window, no step either way (guard_air own x2 still dipped
    1.01-1.61 m through f6's floor 3-4 ticks into its landings rising a
    step a tick, Step 2.199's sitting), and past the window lets go a step
    a tick; the let-go's and the takeoffs' still move a step a tick. Since
    Step 2.200b (AZ-780, D815: "Fix all three") a landing that ends a fall
    begun off the ride (armed off it under 24 ticks ago, airborne on every
    draw since) moves a step a tick too (held exactly, water_tentacle1 own
    x2's let-go landing popped 2.73 m for one tick and guard_air own x2's
    cable's end followed its tail tip's one-tick flick, -1.87 then +1.86 m;
    a longer fall's landing is held exactly, the review's S1), and a landing onto a
    slope (state 3 or 4) is held exactly as a flat one (water_tentacle1 own
    x2's run-off onto f6's ledge went 1.42 m under its line, unheld).
    Since Step 2.200c (AZ-780) each low bone, from the lowest up, is held
    over the lower of the first floor under it, cast from the ray over the
    centre's height at its x, y turned by the matrix's rows (ESI,
    0xA0770's; the term turned too, 0xE91BB's T x M), and the first under
    the centre, the lift the most any needs: under the centre alone,
    guard_air own x2's 3.5 m-off tail tip read f6's ramp's own slope as a
    dip, bobbing its landing twice and dropping it 1.50 m in a tick (Step
    2.200b's record seat), and by its lowest bone alone from the centre's
    height an uphill floor less than 1 m over the centre's lifted the body,
    a higher one was missed (the review's F1, a 3.11 m pop on that ramp)
    and the bones behind a tip over a drop went into the floor; a slope
    landing is held over the floor under its low bone where that is lower,
    the centre's where it is uphill, and with its lowest bone over a drop
    by the next one over the floor. And on a landing that ends a fall begun
    off the ride, a lift that met its need is kept for the tick its need
    first falls more than a step under it, then steps (the cable's end's
    tail tip flicked up 1.87 m for one tick: the drawn body dropped a step
    and came back, its torso 19 px down and up in one frame); a let-go's
    in the air still steps at once. A slide's end at a slope's foot (3 or 4 ->
    0 or 0x100) arms as a landing, held exactly (guard_air own x2 went
    5.26 m under its line at f6's ramp's foot, unheld). For
    another critter, with no lift left, and in a hoist from the air (0x100
    too, +0x200 0x41 or 0x42: its centre on the ledge at once, its drawn
    body gliding up from under it), held or arming, the game's.
    RET 8, EAX the out, the kept registers, the x87 stack empty. The build
    gates it on the crossfades' dip past the ground clips' lowest (flicken
    own x2 keeps the CALL; so does guard_water own, X28's body whose
    crossfade meets that lowest up to rounding: past it by 1 mm, Step
    2.207d's review) and X22 keeps no let-go hold."""
    built = bytes(_swap("guard_air", sounds="garret4", model_scale=2.0)["default.xbe"])

    def param(name: str) -> float:
        va = trampoline_symbol_va(built, FADE_HOOK, f"_player_model_fade_{name}", shim_source=FADE_SHIM.source_path())
        return struct.unpack_from("<f", built, resolve_va_to_file(built, va))[0]
    ray, sole, low = param("ray"), param("sole"), param("low")
    assert ray > 7.0 and -0.3 < low < -0.2 and 0.0 < sole < 0.2
    for species, kw in (("flicken", {"sounds": "garret4", "model_scale": 2.0}), ("guard_water", {})):
        assert verify_trampoline_patch(bytes(_swap(species, **kw)["default.xbe"]), FADE_HOOK) == "original", species
    assert not any(h.float_params and any(p.name.startswith("ease_") for p in h.float_params)
                   for h in HANG_EASE_HOOKS)
    base = 0x20000000
    critter, species, control, clock, anim, body, bones, level, out, matrix = (base + 0x1000 * k for k in range(10))
    sim = Sim(built)
    sim.uc.mem_map(base, 0xA000)
    for at_, value in ((critter + 0xE4, clock), (critter + 0x154, level), (critter + 0x178, species),
                       (critter + 0x17C, anim), (critter + 0x180, control), (level + 0xAC, 0x5A5A0000),
                       (anim, body), (anim + 8, bones), (body, 2)):
        sim.uc.mem_write(at_, struct.pack("<I", value))
    sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 1.0, 2.0, 11.0))   # the centre
    sim.uc.mem_write(critter + 0x188, struct.pack("<f", 2.0))
    sim.uc.mem_write(matrix, struct.pack("<12f", 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0))   # 0xA0770's rows: a quarter turn
    sim.uc.mem_write(bones + 0xB0 + 0xA0, struct.pack("<2f", 1.5, 0.25))   # the low bone's x, y (model units)
    now = {"origin": (1.0, 2.0, 10.0), "term": (0.0, 0.0, 0.0), "floor": 9.0}

    def glide(uc, addr, size, _):   # 0x42070: __stdcall(8), the critter and the out; EAX = out
        esp = sim.reg("esp")
        ret, _who, dst = struct.unpack("<3I", uc.mem_read(esp, 12))
        uc.mem_write(dst, struct.pack("<3f", *now["origin"]))
        uc.reg_write(UC_X86_REG_EAX, dst)
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 12)

    def node(uc, addr, size, _):   # 0x402E0: EAX the critter, EDI the out; EAX = EDI, a plain RET
        esp, edi = sim.reg("esp"), sim.reg("edi")
        uc.mem_write(edi, struct.pack("<3f", *now["term"]))
        uc.reg_write(UC_X86_REG_EAX, edi)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    def sweep(uc, addr, size, _):   # collision_sweep: the floor now["floor"] (or its value at x, y), __stdcall(36)
        esp = sim.reg("esp")
        ret, tree, me, _zero, frm, to, _rxy, _rz, mask, rec = struct.unpack("<6I2f2I", uc.mem_read(esp, 40))
        frm, to = (struct.unpack("<3f", uc.mem_read(v, 12)) for v in (frm, to))
        assert (tree, me, mask) == (0x5A5A0000, critter, 0x10) and to[2] == pytest.approx(11.0 - ray)
        tx, ty, _ = now["term"]   # under the held point: the origin + (2 x (1.5, 0.25) + the term) turned, from the ray
        bones_at = [(1.0 - (0.5 + ty), 2.0 + 3.0 + tx, 11.0 + ray), (1.0 - ty, 2.0 + tx, 11.0 + ray)]   # over its height
        assert sum(frm == pytest.approx(p, abs=1e-5) for p in (*bones_at, (1.0, 2.0, 11.0))) == 1 and to[:2] == frm[:2]
        f = now["floor"](*frm[:2]) if callable(now["floor"]) else now["floor"]
        got = f == "wall" or (f is not None and to[2] <= f <= frm[2])   # "wall": the first hit isn't a floor
        if got:
            nz, frac = (0.0, 0.5) if f == "wall" else (1.0, (frm[2] - f) / (frm[2] - to[2]))
            uc.mem_write(rec + 0x14, struct.pack("<2f", nz, frac))
        uc.reg_write(UC_X86_REG_EAX, int(got))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 40)

    for va, hook in ((0x42070, glide), (0x402E0, node), (0x60870, sweep)):
        sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)
    entry = FADE_HOOK.va + 5 + struct.unpack_from("<i", built, va_to_file(FADE_HOOK.va) + 1)[0]

    def draw(t: float, last: int, state: int, bone: float, *, player: bool = True, term=(0.0, 0.0, 0.0),
             floor=9.0, other: float = 3.0) -> float:
        """One draw at clock ``t``, the PlayerControl's (+0x98, +0x94), the lowest posed bone ``bone``
        (``other`` the other's, at (0, 0)), the floor (a z, None or a function of x, y); the drawn origin's z it returns."""
        now.update(term=term, floor=floor)
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", t))
        sim.uc.mem_write(control + 0x94, struct.pack("<2i", state, last))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", 0x24 if player else 0x04))
        for k, z in enumerate((other, bone)):
            sim.uc.mem_write(bones + 0xB0 * k + 0xA8, struct.pack("<f", z))
        kept = {"ebx": 0x11, "esi": matrix, "edi": 0x33, "ebp": 0x44}
        eax = sim.call(entry, regs=kept, args=(critter, out), until=l2._RETURN)
        assert (eax, {r: sim.reg(r) for r in kept}) == (out, kept) and sim.reg("esp") == l2._STACK_TOP - 0x100
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        x, y, z = struct.unpack("<3f", sim.uc.mem_read(out, 12))
        assert (x, y) == (1.0, 2.0)
        return z

    def need(bone: float, term: float = 0.0, floor: float = 9.0) -> float:   # the lift: its lowest point at floor + low
        return floor + low - (term + 2.0 * bone - sole) - 10.0

    step = 0.847
    full = need(-2.0)
    assert full > 3 * step
    t0 = 100.0
    assert draw(t0, 5, 2, -2.0) == pytest.approx(10.0 + step, abs=1e-4)                # off the ride: a step
    assert draw(t0, 5, 2, -2.0) == pytest.approx(10.0 + step, abs=1e-4)                # the same clock drawn again
    assert draw(t0 + 1 / 30, 2, 2, -2.0) == pytest.approx(10.0 + 2 * step, abs=1e-4)
    assert draw(t0 + 3 / 30, 2, 2, -2.0) == pytest.approx(10.0 + full, abs=1e-4)       # two ticks: two steps' room
    lift = need(-1.5, 0.3)
    assert 0.0 < lift < full - step
    assert draw(t0 + 4 / 30, 2, 2, -1.5, term=(0.0, 0.0, 0.3)) == pytest.approx(10.0 + full - step, abs=1e-4)
    assert draw(t0 + 5 / 30, 2, 2, -1.5, term=(0.0, 0.0, 0.3)) == pytest.approx(10.0 + lift, abs=1e-4)
    assert draw(t0 + 6 / 30, 2, 2, 0.0) == pytest.approx(10.0 + max(0.0, lift - step), abs=1e-4)   # over the floor
    assert draw(t0 + 7 / 30, 2, 2, -2.0, floor=None) == 10.0                           # no floor: let go
    assert draw(t0 + 13 / 30, 2, 2, -2.0) == 10.0                                      # past the 12 ticks
    sim.uc.mem_write(critter + 0x200, struct.pack("<i", 0xB))                          # touchdown
    # the landing that ends the fall begun off the ride (at t0): a step a tick either way
    got = [draw(t0 + k / 30, 2 if k == 20 else 0, 0, 0.0 if k == 23 else -2.0) for k in range(20, 25)]
    assert got == pytest.approx([10.0 + w for w in (step, 2 * step, 3 * step, 2 * step, 3 * step)], abs=1e-4)
    for state in (0, 0x100, 3, 4):           # off the ride onto the ground, onto a ladder, then a soft, hard or slope
        t0 += 1.0                            # landing: held exactly (the fall begun off the ride's: above)
        assert [draw(t0 + 18 / 30, 5, 0, 0.0), draw(t0 + 19 / 30, 0, 1, 0.0)] == [10.0, 10.0]
        got = ([draw(t0 + 20 / 30, 2, state, -2.0)] + [draw(t0 + k / 30, state, state, -2.0) for k in (21, 22)]
               + [draw(t0 + 23 / 30, state, state, 0.0)]
               + [draw(t0 + k / 30, state, state, -2.0) for k in (*range(24, 32), 33, 34, 35)])
        want = [full] * 3 + [0.0] + [full] * 8 + [max(0.0, full - step * k) for k in (2, 3, 4)]
        assert got == pytest.approx([10.0 + w for w in want], abs=1e-4), state        # exactly; past 12 a step a tick
    t0 += 1.0     # a landing onto a slope: the floor under the held point (y 5.3, the term turned) 1.65 m under the
    down, up = (lambda x, y: 10.0 - 0.5 * y), (lambda x, y: 9.0 + (y - 2.0))   # centre's (y 2), or 3 m over it
    edge, wall = (lambda x, y: 9.0 if y < 4.0 else None), (lambda x, y: 9.0 if y < 4.0 else "wall")
    got = [draw(t0, 2, 3, -2.0, term=(0.3, 0.2, 0.0), floor=down), draw(t0 + 1 / 30, 3, 3, -2.0, floor=up),
           draw(t0 + 2 / 30, 3, 3, -2.0, floor=edge, other=-1.0), draw(t0 + 3 / 30, 3, 3, -2.0, floor=wall)]
    assert got == pytest.approx([10.0 + need(-2.0, floor=7.35), 10.0 + need(-2.0), 10.0 + need(-1.0),
                                 10.0 + need(-2.0)], abs=1e-4)
    # each low bone over its own floor if lower, else the centre's, also over the centre's height (review F1: one
    # under it lifted the body, one over it was missed and held nothing); the lowest over a drop needs nothing, the
    # next over the floor its own lift; one whose cast first meets a wall or an underside the centre's
    for slope, ground in ((4, 0), (3, 0x100)):   # a slide's end at a ramp's foot: a landing, held exactly
        t0 += 1.0
        assert [draw(t0 + k / 30, slope if k else 2, slope, 0.0) for k in range(15)] == [10.0] * 15
        got = [draw(t0 + 15 / 30, slope, ground, -2.0), draw(t0 + 16 / 30, ground, ground, -2.0)]
        assert got == pytest.approx([10.0 + full] * 2, abs=1e-4), (slope, ground)
    t0 += 1.0     # a landing off the ride whose lift met its need: the need's fall of more than a step ridden a tick
    met = need(-1.25)
    assert step < met < 2 * step
    assert [draw(t0 + k / 30, 2 if k else 5, 2, 0.0) for k in range(4)] == [10.0] * 4    # off the ride, no dip
    got = [draw(t0 + k / 30, 2 if k == 4 else 0, 0, b)
           for k, b in ((4, -1.25), (5, -1.25), (6, 0.0), (7, -1.25), (8, 0.0), (9, 0.0), (10, 0.0))]
    assert got == pytest.approx([10.0 + w for w in (step, met, met, met, met, met - step, 0.0)], abs=1e-4)
    t0 += 1.0                                # a fall begun off the ride 25 ticks before it lands: a fall's landing
    assert draw(t0, 5, 2, 0.0) == 10.0
    got = [draw(t0 + 25 / 30, 2, 0, -2.0), draw(t0 + 26 / 30, 0, 0, -2.0)]
    assert got == pytest.approx([10.0 + full] * 2, abs=1e-4)                           # held exactly (the review's S1)
    t0 += 1.0
    for hoist in (0x41, 0x42):
        sim.uc.mem_write(critter + 0x200, struct.pack("<i", hoist))
        assert draw(t0, 2, 0x100, -2.0) == 10.0, hoist                                 # a hoist from the air
        assert draw(t0 + 1 / 30, 0x100, 0x100, -2.0) == 10.0, hoist                    # and it armed no hold
        assert draw(t0 + 2 / 30, 5, 2, -2.0) == pytest.approx(10.0 + step, abs=1e-4), hoist   # off the ride
        assert draw(t0 + 4 / 30, 2, 0x100, -2.0) == 10.0, hoist                        # a hoist after it, let go
        t0 += 1.0
    sim.uc.mem_write(critter + 0x200, struct.pack("<i", 0x10))                         # the standing jump
    for k, ground in enumerate((0, 3, 4, 0x100)):                                      # a takeoff, a step a tick
        t = t0 + 50.0 + 10 * k
        got = [draw(t, ground, 2, -2.0), draw(t + 1 / 30, 2, 2, -2.0), draw(t + 3 / 30, 2, 2, -2.0)]
        assert got == pytest.approx([10.0 + step, 10.0 + 2 * step, 10.0 + full], abs=1e-4), ground
    assert draw(t0 + 100.0, 1, 2, -2.0) == 10.0                                        # off a ladder: none
    assert draw(t0 + 110.0, 5, 2, -2.0, player=False) == 10.0                          # another critter


def test_a_landings_crossfade_hold_leaves_the_camera_point_the_games_and_lifts_for_no_swinging_cloth_or_hair():
    """AZ-746 (Step 2.192, X48): on booblord's hard landing X48 lifted her
    drawn origin up to 0.234 m, first for a toe in the fall -> touchdown
    crossfade, then for her sash's front flap tip swinging 0.36 m through
    the floor in the touchdown she borrows (AZ-728), floating her whole
    body 0.24 m over it; and the camera point (0x41F40's CALL of
    critter_model_matrix at 0x41FB0) rode the same origin, so the screen
    bobbed +0.16, -0.10, +0.17, -0.23 m in 11 ticks where garret4's
    stays within 9 mm (the owner, X.79's play session; sitting 2.192).
    The build leaves a body's hair and cloth chains (and a carried prop)
    out of X48's lowest: on female_2, her hair_1-3 and both loincloth
    panels, no foot. L2, guard_air own x2's build (0x42070, 0x402E0 and
    collision_sweep stubbed): the camera point's call (0x42200 returning
    to its CALL's end, 0x41FB5, the build's) gets the game's origin on a
    held tick while the draw's gets the lift, and a bone of the build's
    mask under the floor lifts nothing."""
    characters = _vanilla("gamedata/characters.xbr")
    rig = Rig.read(characters, "townspeople/female_2")
    assert {rig.bones[k].name for k in loose_bones(rig)} == {
        *(f"hair_{k}" for k in (1, 2, 3)), *(f"loincloth_{s}_{k}" for s in ("front", "back") for k in range(1, 6))}
    built = bytes(_swap("guard_air", sounds="garret4", model_scale=2.0)["default.xbe"])

    def at(param) -> int:
        return trampoline_symbol_va(built, FADE_HOOK, param.symbol, shim_source=FADE_SHIM.source_path())
    camera = struct.unpack_from("<I", built, resolve_va_to_file(built, at(FADE_CAMERA)))[0]
    assert camera == 0x41FB5
    base = 0x20000000
    critter, species, control, clock, anim, body, bones, level, out, matrix = (base + 0x1000 * k for k in range(10))
    sim = Sim(built)
    sim.uc.mem_map(base, 0xA000)
    sim.uc.mem_write(matrix, struct.pack("<12f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0))   # 0xA0770's rows: no turn
    for at_, value in ((critter + 0xE4, clock), (critter + 0x154, level), (critter + 0x178, species),
                       (critter + 0x17C, anim), (critter + 0x180, control), (level + 0xAC, 0x5A5A0000),
                       (anim, body), (anim + 8, bones), (body, 3), (species + 0x64, 0x24)):
        sim.uc.mem_write(at_, struct.pack("<I", value))
    sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 1.0, 2.0, 11.0))   # the centre, the floor 2 m under it
    sim.uc.mem_write(critter + 0x188, struct.pack("<f", 2.0))
    sim.uc.mem_write(at(FADE_LOOSE), bytes([0b100]) + bytes(FADE_LOOSE.size - 1))   # bone 2 loose (a flap)

    def stub(uc, addr, size, _):   # 0x42070 (the origin 10.0), 0x402E0 (no term), collision_sweep (the floor)
        esp = sim.reg("esp")
        if addr == 0x42070:
            ret, _who, dst = struct.unpack("<3I", uc.mem_read(esp, 12))
            uc.mem_write(dst, struct.pack("<3f", 1.0, 2.0, 10.0))
            eax, pop = dst, 12
        elif addr == 0x402E0:
            ret, eax, pop = struct.unpack("<I", uc.mem_read(esp, 4))[0], sim.reg("edi"), 4
            uc.mem_write(eax, struct.pack("<3f", 0.0, 0.0, 0.0))
        else:
            ret, frm, to, rec = (struct.unpack("<I", uc.mem_read(esp + o, 4))[0] for o in (0, 16, 20, 36))
            frm, to = (struct.unpack("<3f", uc.mem_read(v, 12))[2] for v in (frm, to))
            uc.mem_write(rec + 0x14, struct.pack("<2f", 1.0, (frm - 9.0) / (frm - to)))
            eax, pop = 1, 40
        uc.reg_write(UC_X86_REG_EAX, eax)
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + pop)

    for va in (0x42070, 0x402E0, 0x60870):
        sim.uc.hook_add(UC_HOOK_CODE, stub, begin=va, end=va)
    entry = FADE_HOOK.va + 5 + struct.unpack_from("<i", built, va_to_file(FADE_HOOK.va) + 1)[0]

    def draw(t: float, last: int, toe: float, flap: float, ret: int) -> float:
        """One 0x42200 returning to ``ret`` at clock ``t`` (landed from the air: state 0, its last tick
        ``last``), the posed bones 3.0, ``toe`` and ``flap`` (model units); the drawn origin's z."""
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", t))
        sim.uc.mem_write(control + 0x94, struct.pack("<2i", 0, last))
        for k, z in enumerate((3.0, toe, flap)):
            sim.uc.mem_write(bones + 0xB0 * k + 0xA8, struct.pack("<f", z))
        kept = {"ebx": 0x11, "esi": matrix, "edi": 0x33, "ebp": 0x44}   # 0x42200's frame: its return at [ESP + 0x2C]
        eax = sim.call(entry, regs=kept, args=(critter, out, *(0,) * 8, ret), until=l2._RETURN)
        assert (eax, {r: sim.reg(r) for r in kept}) == (out, kept)
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        return struct.unpack("<3f", sim.uc.mem_read(out, 12))[2]

    sole, low = (struct.unpack_from("<f", built, resolve_va_to_file(built, at(p)))[0] for p in (FADE_SOLE, FADE_LOW))
    lift = 9.0 + low - (10.0 + 2.0 * -0.8 - sole)   # the toe 0.8 under the origin: under the hold, under a step
    assert 0.0 < lift < 0.847
    drawn = 0x3E857   # the critter draw's (its CALL of 0x42200 at 0x3E852)
    t0 = 100.0
    assert draw(t0, 2, -0.8, 1.0, camera) == 10.0                                      # the camera point: the game's
    assert draw(t0, 2, -0.8, 1.0, drawn) == pytest.approx(10.0 + lift, abs=1e-4)     # the draw: held
    assert draw(t0 + 1 / 30, 0, -0.8, 1.0, camera) == 10.0
    assert draw(t0 + 1 / 30, 0, -0.8, 1.0, drawn) == pytest.approx(10.0 + lift, abs=1e-4)
    assert draw(t0 + 2 / 30, 0, 1.0, -1.5, drawn) == 10.0                              # a flap under the floor: none
    assert draw(t0 + 3 / 30, 0, 1.0, -1.5, drawn) == 10.0


def test_a_body_hanging_deeper_than_garret4_rides_over_every_floor_under_its_path_at_most_a_step_a_tick():
    """AZ-529 (b) (Step 2.118, X28; reworked Step 2.118c; D293): X9 hangs
    a body drawn at a model scale by its pose's top under the cable, drawn
    from its origin while it collides at its centre, so where the drawn
    hang reaches deeper than garret4's (2.83 m) it was drawn through f3's
    platforms (sitting 2.106), and 2.118's first X28 held the ride but
    ratcheted hang_start's glide up uncapped and dropped ride tick 1 by up
    to 4.44 m (sitting 2.118). X28 (L2, kingkong own x2's build: 48 ticks
    of lookahead, its hang garret4's baked g4/hang since Step 2.134a, 33 on
    its idle before; collision_sweep, 0x8C080, 0x42070 and 0x402E0 stubbed). The ride
    (0x8AB3F) over f3's profile (the flat start, the 0.34 slope, the void,
    the 0.14 cliff, the 0.85 ledge, the 0.25 slope, the end floor) at
    kingkong own x2's, golem own x2's and town_male_6 own x2's depths:
    its lowest bone never under the floor under the centre plus the
    margin; the drawn origin no more than 0.847 m from the last tick's and
    never under the game's, eased back to it over the void and risen early
    to the end platform, every future tick sampled (a ray from the centre
    advanced k ticks along its last motion, k = 1..the lookahead, mask
    0x10, any slope); another critter untouched; RET 8, the kept
    registers, the x87 stack empty. hang_start: the set-up (0x8A4F0, RET
    8) then 21 ticks (0x8D091, the replayed mov ebp,[ebp+0x30]; test
    ebp,ebp) over f3's start platform with guard_air own x2's crossfade
    dip in the table (3.11 m under its origin at h4, falling 1.5 m a
    tick): the drawn lowest point over the floor on every tick, risen to
    from h1, no tick's drawn blend more than 0.847 m from the last (h1
    from the stance), the glide's ends carrying this tick's offset only,
    so with the floor gone it eases to the game's blend a step a tick and
    the ends are the game's again (no ratchet); another critter
    untouched; with guard_air own x2's aligned-node term rising 0.032 m a
    tick in its crossfade (0x402E0, which the draw adds: it drew 0.88 m a
    tick in sitting 2.118c) the drawn height (the blend plus the term)
    still moves at most 0.847 m a tick and stays over the floor. Ride tick 1 after it, with the game's origin 1.16 m
    (town_male_6 own x2) or 4.44 m (water_tentacle2 own x1) under
    hang_start's last drawn height, eases a step from it; 0.2 s later or
    another critter, the game's. The build: the set-up's and the tick's
    state is the ride landing's block; guard_air own x2's table at h4
    clears its measured 3.11 m dip; the ray and lookahead reach the drawn
    hang's span and margin (water_tentacle2 own x4's 22 m, where the
    hang's depth plus 2 m, 14.9 m, stopped short); flicken own x2, whose
    hang reaches no deeper than garret4's, keeps all three sites."""
    game = _swap("kingkong", sounds="garret4", model_scale=2.0)
    built = bytes(game["default.xbe"])
    assert l1.check(_vanilla("default.xbe"), built) == []
    ride_hook, setup_hook, tick_hook = HOLD_HOOKS

    def param_va(name: str, hook, xbe: bytes = built) -> int:
        return trampoline_symbol_va(xbe, hook, f"_player_model_hold_{name}", shim_source=HOLD_SHIM.source_path())

    sim, base = Sim(built), 0x20000000
    sim.uc.mem_map(base, 0x10000)
    built_ray, built_margin, built_ahead = (sim.f32(param_va(name, ride_hook)) for name in ("ray", "margin", "ahead"))
    assert built_ahead == 48 and sim.f32(param_va("step", ride_hook)) == pytest.approx(0.847)
    block = trampoline_symbol_va(built, ride_hook, HOLD_STATE, shim_source=HOLD_SHIM.source_path())
    assert [sim.u32(param_va("shared", hook)) for hook in HOLD_HOOKS] == [0, block, block]
    control, critter, species, level, clock, anim, body, bones, ctx = (base + 0x800 * k for k in range(9))
    for at, value in ((control + 0xC, clock), (control + 0x20, critter), (critter + 0x154, level),
                      (level + 0xAC, 0x5A5A0000), (critter + 0x178, species), (critter + 0x17C, anim),
                      (anim, body), (anim + 8, bones), (body, 1)):
        sim.uc.mem_write(at, struct.pack("<I", value))
    floors = [                       # f3's profile: x from, x to, z at the start, its fall a metre, normal z
        (-10.0, 6.0, -3.75, 0.0, 1.0), (6.0, 8.0, -3.75, 2.0, 0.34),          # the start, its slope
        (61.0, 64.0, -25.0, 0.0, 0.14), (64.0, 67.0, -12.2, 0.0, 0.85),       # the cliff, the ledge
        (67.0, 70.0, -12.2, -0.68, 0.25), (70.0, 90.0, -10.16, 0.0, 0.999)]   # the slope, the end floor

    def floor_at(x: float):
        return next(((z - fall * (x - lo), nz) for lo, hi, z, fall, nz in floors if lo <= x < hi), None)

    sweeps, frac = [], [0.0]

    def sweep(uc, addr, size, _):   # collision_sweep: __stdcall(36), RET 0x24
        esp = sim.reg("esp")
        ret, tree, me, zero, frm, to, rxy, rz, mask, rec = struct.unpack("<6I2f2I", uc.mem_read(esp, 40))
        frm, to = (struct.unpack("<3f", uc.mem_read(v, 12)) for v in (frm, to))
        sweeps.append(((tree, me, zero, rxy, rz, mask, bytes(uc.mem_read(rec + 0x20, 4))), frm, to))
        f = floor_at(frm[0])
        got = f is not None and to[2] <= f[0] <= frm[2]
        if got:
            uc.mem_write(rec + 0x14, struct.pack("<2f", f[1], (frm[2] - f[0]) / (frm[2] - to[2])))
        uc.reg_write(UC_X86_REG_EAX, int(got))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 40)

    landings = []

    def landing(uc, addr, size, _):   # 0x8C080: EAX the PlayerControl, RET 8
        esp = sim.reg("esp")
        landings.append((sim.reg("eax"), *struct.unpack("<2I", uc.mem_read(esp + 4, 8))))
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 12)

    term = [0.0]

    def node(uc, addr, size, _):   # 0x402E0: EAX the critter, EDI the out, (0, 0, term[0]), a plain RET
        esp, out = sim.reg("esp"), sim.reg("edi")
        assert sim.reg("eax") == critter
        uc.mem_write(out, struct.pack("<3f", 0.0, 0.0, term[0]))
        uc.reg_write(UC_X86_REG_EAX, out)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    def blend(uc, addr, size, _):   # 0x42070, __stdcall(8): frac[0] of the way from +0x1B0 to +0x1BC
        esp = sim.reg("esp")
        ret, me, out = struct.unpack("<3I", uc.mem_read(esp, 12))
        a, b = (struct.unpack("<3f", uc.mem_read(me + off, 12)) for off in (0x1B0, 0x1BC))
        uc.mem_write(out, struct.pack("<3f", *(p + frac[0] * (q - p) for p, q in zip(a, b))))
        uc.reg_write(UC_X86_REG_EAX, out)
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 12)

    for va, hook in ((0x60870, sweep), (0x8C080, landing), (0x42070, blend), (0x402E0, node)):
        sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)

    def entry(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]

    def setting(hook, **params) -> None:
        for name, v in params.items():
            if name == "table":
                sim.uc.mem_write(param_va(name, hook), struct.pack(f"<{len(v)}f", *v))
            else:
                sim.uc.mem_write(param_va(name, hook), struct.pack("<f", v))

    def ends() -> tuple[float, float]:
        return tuple(_f32(struct.unpack("<3f", sim.uc.mem_read(critter + off, 12))[2]) for off in (0x1B0, 0x1BC))

    def ride_tick(now: float, x: float, g: float, centre_z: float, regs: dict[str, int]) -> float:
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", now))
        sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", x, 1.0, centre_z))
        for off in (0x1B0, 0x1BC):
            sim.uc.mem_write(critter + off, struct.pack("<3f", x, 1.0, g))
        del sweeps[:], landings[:]
        sim.call(entry(ride_hook), regs={"eax": control, **regs}, args=(0x33, ctx), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100 and {r: sim.reg(r) for r in regs} == regs
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0 and landings == [(control, 0x33, ctx)]
        z, end = ends()
        assert z == end
        return z

    def ride(depth: float, drawn: float, low: float, ahead: int, margin: float, ray: float, player: bool = True):
        """A ride from x -2 to 80 at 0.25 m a tick, the cable falling 0.02 m a tick: per tick the drawn
        origin, the game's, the floor within the ray under the centre and the sweeps."""
        setting(ride_hook, ray=ray, margin=margin, ahead=float(ahead))
        sim.uc.mem_write(critter + 0x188, struct.pack("<f", drawn))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", 0x24 if player else 0x04))
        sim.uc.mem_write(bones + 0xA8, struct.pack("<f", low))
        rows = []
        for t in range(329):
            x, cable = -2.0 + 0.25 * t, -0.02 * t
            g = cable - depth
            z = ride_tick(100.0 + t / 30, x, g, cable - 2.693, {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44})
            f = floor_at(x)
            rows.append((z, _f32(g), f[0] if f and f[0] >= cable - 2.693 - ray else None, list(sweeps)))
        return rows

    for name, (depth, drawn, low) in {"kingkong": (built_ray - built_margin - 2.0, 8.0, 0.0), "golem": (7.379, 2.0, 0.0),
                                      "town_male_6": (6.363, 2.3, 1.09)}.items():
        span, margin = depth - drawn * low, 0.5
        ahead, ray = math.ceil((span + margin - 2.83) / 0.847), span + margin + 2.0   # hold_plan's
        rows = ride(depth, drawn, low, ahead, margin, ray)
        assert [len(sw) for *_, sw in rows] == [1] + [1 + ahead] * (len(rows) - 1), name   # every tick ahead
        assert {call for *_, sw in rows for call, _, _ in sw} == {
            (0x5A5A0000, critter, 0, 0.0, 0.0, 0x10, bytes((0, 0x80, 0, 0xCC)))}
        assert all(frm[2] - to[2] == pytest.approx(ray, abs=1e-3) for *_, sw in rows for _, frm, to in sw)
        for t, (z, g, f, _) in enumerate(rows):
            if f is not None:
                assert z + drawn * low >= f + margin - 1e-3, (name, t)        # never under the floor
            if t:
                assert abs(z - rows[t - 1][0]) <= 0.847 + 1e-3, (name, t)     # at most a step a tick
            assert z >= g, (name, t)
        void = [t for t in range(len(rows)) if 25.0 <= -2.0 + 0.25 * t <= 45.0]
        assert all(rows[t][0] == rows[t][1] for t in void), name                  # eased back to the game's
        assert rows[0][0] > rows[0][1] and rows[-1][0] > rows[-1][1], name        # held at both platforms
    assert all(z == g and not sw for z, g, _, sw in ride(29.37, 8.0, 0.0, 33, 0.5, 31.87, player=False))

    # hang_start over f3's start platform (-3.75 under the cable point), guard_air own x2's dip in the table
    dip = [0.86, -0.88, -2.35, -3.11, -2.97, -2.23, -1.13, -0.01] + [0.5] * 22   # its drawn lowest point a tick
    wide = [min(dip[max(0, j - 2):j + 3]) for j in range(30)]
    table = [min(wide[j] + 0.847 * (j - t) for j in range(t, 30)) for t in range(22)]
    for hook in (setup_hook, tick_hook):
        setting(hook, ray=12.0, margin=0.5, table=table)
    sim.uc.mem_write(critter + 0x188, struct.pack("<f", 2.0))
    stance, deep = -3.75, -3.75 - 5.0      # the glide: the stance on the floor to a hang under it

    def hang_start(*, player: bool = True, gone: int = 99, behind: int = 0x1234,
                   ramp: tuple[float, ...] = (0.0,) * 22) -> list[tuple[float, float]]:
        """The set-up and 21 ticks, the aligned-node term ``ramp``; per tick (the drawn height: the
        blend plus the term, the offset over the game's)."""
        sim.uc.mem_write(species + 0x64, struct.pack("<I", 0x24 if player else 0x04))
        sim.uc.mem_write(control + 0x30, struct.pack("<I", behind))
        for off, z in ((0x1B0, stance), (0x1BC, deep)):   # 0x42430's ends
            sim.uc.mem_write(critter + off, struct.pack("<3f", 0.0, 1.0, z))
        rows = []
        for j in range(22):
            frac[0], term[0] = j / 22, ramp[j]
            x = 0.0 if j < gone else 30.0                       # past 'gone' no floor under the centre
            sim.uc.mem_write(clock + 0x10, struct.pack("<d", 200.0 + j / 30))
            sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", x, 1.0, -2.75 + 0.1 * j))
            sim.uc.mem_write(bones + 0xA8, struct.pack("<f", (dip[j - 1] if j else 0.0) / 2.0))   # the last drawn
            if j == 0:
                regs = {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
                del landings[:]
                sim.call(entry(setup_hook), regs={"eax": control, **regs}, args=(0x33, ctx), until=l2._RETURN)
                assert sim.reg("esp") == l2._STACK_TOP - 0x100 and landings == [(control, 0x33, ctx)]
            else:
                regs = {"eax": 0x55, "ecx": 0x66, "edx": 0x77, "ebx": 0x11, "esi": 0x22, "edi": 0x33}
                sim.call(entry(tick_hook), regs={"ebp": control, **regs}, until=l2._RETURN)
                assert sim.reg("esp") == l2._STACK_TOP - 0x100 and sim.reg("ebp") == behind
                assert bool(sim.uc.reg_read(UC_X86_REG_EFLAGS) & 0x40) == (behind == 0)   # the replayed test
            assert {r: sim.reg(r) for r in regs} == regs and sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
            a, b = ends()
            g = _f32(stance + frac[0] * (_f32(deep) - stance))
            off = a - stance
            assert off >= -1e-4 and b - _f32(deep) == pytest.approx(off, abs=1e-4), j   # this tick's offset, both ends
            rows.append((g + off + ramp[j], off))
        term[0] = 0.0
        return rows

    held = hang_start()
    assert held[0][0] - stance <= 0.847 + 1e-3                                  # h1 from the stance
    assert all(abs(z - held[j - 1][0]) <= 0.847 + 1e-3 for j, (z, _) in enumerate(held) if j)
    assert all(z + d >= stance - 1e-3 for (z, _), d in zip(held, dip)), held   # the dip over the floor: risen early
    assert held[0][1] > 0.8 and held[3][0] - stance > 3.0
    ramp = (-0.212, -0.180, -0.147, -0.115, -0.084, -0.055, -0.030, -0.009) + (0.0,) * 14   # guard_air own x2's
    drawn = hang_start(ramp=ramp)
    assert all(abs(z - drawn[j - 1][0]) <= 0.847 + 1e-3 for j, (z, _) in enumerate(drawn) if j), drawn
    assert drawn[0][0] - stance <= 0.847 + 1e-3 and all(z + d >= stance - 1e-3 for (z, _), d in zip(drawn, dip))
    eased = hang_start(gone=10)                                                 # the floor gone from h11
    for j in range(10, 22):
        g = stance + j / 22 * (deep - stance)
        assert eased[j][0] == pytest.approx(max(g, eased[j - 1][0] - 0.847), abs=1e-3), j
    assert eased[-1][1] == 0.0 and ends() == (_f32(stance), _f32(deep))       # the game's ends again: no ratchet
    assert all(off == 0.0 for _, off in hang_start(player=False))
    hang_start(behind=0)                                                        # the replayed JE's flag
    # ride tick 1 after hang_start's last: eased from its drawn height, not dropped
    setting(ride_hook, ray=12.0, margin=0.5, ahead=4.0)
    for drop in (1.16, 4.44):
        last = hang_start()[-1][0]
        r1 = ride_tick(200.0 + 22 / 30, 30.0, last - drop, -2.0, {})
        assert r1 == pytest.approx(last - 0.847, abs=1e-4), drop
        last = hang_start()[-1][0]
        assert ride_tick(200.0 + 22 / 30 + 0.2, 30.0, last - drop, -2.0, {}) == _f32(last - drop)
    flicken = bytes(_swap("flicken", sounds="garret4", model_scale=2.0)["default.xbe"])
    assert {verify_trampoline_patch(flicken, hook) for hook in HOLD_HOOKS} == {"original"}
    tall = bytes(_swap("kingkong", sounds="garret4")["default.xbe"])   # x1 (D292): its top at the cable, held
    assert {verify_trampoline_patch(tall, hook) for hook in HOLD_HOOKS} == {"applied"}
    air = bytes(_swap("guard_air", sounds="garret4", model_scale=2.0)["default.xbe"])
    h4 = struct.unpack_from("<f", air, resolve_va_to_file(air, param_va("table", setup_hook, air) + 4 * 3))[0]
    assert h4 <= -3.11 + 0.10                                                   # sitting 2.118's placed h4
    tentacle = bytes(_swap("water_tentacle2", sounds="garret4", model_scale=4.0)["default.xbe"])
    for xbe in (built, tall, tentacle):
        ray, margin, ahead = (struct.unpack_from("<f", xbe, resolve_va_to_file(xbe, param_va(name, ride_hook, xbe)))[0]
                              for name in ("ray", "margin", "ahead"))
        assert 2.83 + 0.847 * (ahead - 1) < ray - 2.0 <= 2.83 + 0.847 * ahead + 1e-3   # span and margin, both
    assert ray > 22.0                                                           # water_tentacle2 own x4's reach


def test_a_bobbing_hang_rides_over_the_platform_by_its_pose_at_the_clips_own_time_its_lowest_point_stepping():
    """AZ-713 (Step 2.189b, X28): the ride held the lowest posed bone of
    the last drawn pose (a tick late) over the floor by a margin of a
    tick's fastest move, and moved the drawn origin at most a step a
    tick, so key_air1 own x2, whose hang (its idle at X12's x16) bobs 8 m
    a loop, 1.2 m a tick, rode up to 7.7 m over f3's start platform with
    its top 4.7 m over the cable, where it fits under it (sitting
    2.175b). The build writes X28 the hang clip's float32 length and its
    lowest drawn point over the origin at 64 times over its loop (its
    mesh: a one-bone rig); the ride (L2, key_air1 own x2's build;
    collision_sweep, 0x8C080 and 0x402E0 stubbed) with the active layer
    playing that clip at full weight takes its pose there (at the
    layer's time, the table interpolated), no margin:
    over the platform the drawn lowest point sits on the floor every tick
    as the hang bobs (the origin moving more than a step against it),
    past its end the origin comes down a step a tick to the game's, as
    before; mid-crossfade
    (weight 0.5) or with another clip on the layer, the live bones less
    the margin, as before. A tick that switches between the live bones
    and the table (their lowest points apart by the margin and the live
    pose's lag) steps the drawn origin a step from the last, and the next
    ticks step the lowest point down a step a tick to the floor (stepped
    from the live tick's lowest point, key_air1 own x2 dropped 4.57 m in
    a tick at ride tick 9 over f3's start platform, sitting 2.189b)."""
    built = bytes(_swap("key_air1", sounds="garret4", model_scale=2.0)["default.xbe"])
    ride_hook = HOLD_HOOKS[0]

    def param(name: str, fmt: str = "<f"):
        va = trampoline_symbol_va(built, ride_hook, f"_player_model_hold_{name}", shim_source=HOLD_SHIM.source_path())
        return struct.unpack_from(fmt, built, resolve_va_to_file(built, va))
    length, *table = param("loop", "<65f")
    margin, = param("margin")
    assert length == 24.0 and 12.5 < min(table) < 13.5 and 7.5 < max(table) - min(table) < 8.5 and margin > 2.0
    sim, base = Sim(built), 0x20000000
    sim.uc.mem_map(base, 0x10000)
    control, critter, species, level, clock, anim, body, bones, ctx, clip = (base + 0x800 * k for k in range(10))
    for at, value in ((control + 0xC, clock), (control + 0x20, critter), (critter + 0x154, level),
                      (level + 0xAC, 0x5A5A0000), (critter + 0x178, species), (critter + 0x17C, anim),
                      (anim, body), (anim + 8, bones), (body, 1), (species + 0x64, 0x24), (anim + 0x10, 0),
                      (anim + 0x44, clip), (anim + 0x48, 1)):
        sim.uc.mem_write(at, struct.pack("<I", value))
    sim.uc.mem_write(critter + 0x188, struct.pack("<f", 4.0))
    sim.uc.mem_write(anim + 0x60, struct.pack("<f", 16.0))   # the layer's rate
    floor = {"z": -3.75, "to": 8.0}

    def sweep(uc, addr, size, _):   # collision_sweep: the platform at floor["z"] for x under floor["to"]
        esp = sim.reg("esp")
        ret, _tree, _me, _zero, frm, to, _rxy, _rz, _mask, rec = struct.unpack("<6I2f2I", uc.mem_read(esp, 40))
        frm, to = (struct.unpack("<3f", uc.mem_read(v, 12)) for v in (frm, to))
        got = frm[0] < floor["to"] and to[2] <= floor["z"] <= frm[2]
        if got:
            uc.mem_write(rec + 0x14, struct.pack("<2f", 1.0, (frm[2] - floor["z"]) / (frm[2] - to[2])))
        uc.reg_write(UC_X86_REG_EAX, int(got))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 40)

    def landing(uc, addr, size, _):   # 0x8C080: EAX the PlayerControl, RET 8
        esp = sim.reg("esp")
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 12)

    def node(uc, addr, size, _):   # 0x402E0: no term; EAX = EDI, a plain RET
        esp, out = sim.reg("esp"), sim.reg("edi")
        uc.mem_write(out, struct.pack("<3f", 0.0, 0.0, 0.0))
        uc.reg_write(UC_X86_REG_EAX, out)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    for va, hook in ((0x60870, sweep), (0x8C080, landing), (0x402E0, node)):
        sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va, end=va)
    entry = ride_hook.va + 5 + struct.unpack_from("<i", built, va_to_file(ride_hook.va) + 1)[0]
    game = -1.86 - 23.962   # the game's drawn origin against the cable (0): X' x 3.693 under it

    def pose_at(t: float) -> float:   # the table at clip time t, interpolated over its loop
        f = (t / length) % 1.0 * 64
        i = int(f)
        return table[i] * (1 - (f - i)) + table[(i + 1) % 64] * (f - i)

    def ride(j: int, t: float, *, weight: float = 1.0, clip_length: float = 24.0, bone: float = 3.0) -> float:
        """Ride tick j at clip time t: the drawn origin's height after the hook."""
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", 100.0 + j / 30))
        sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 0.25 * j, 1.0, -1.86))
        for off in (0x1B0, 0x1BC):
            sim.uc.mem_write(critter + off, struct.pack("<3f", 0.25 * j, 1.0, game))
        sim.uc.mem_write(anim + 0x58, struct.pack("<2f", t, weight))
        sim.uc.mem_write(clip + 0x10, struct.pack("<f", clip_length))
        sim.uc.mem_write(bones + 0xA8, struct.pack("<f", bone))   # the last drawn bone, model units
        sim.call(entry, regs={"eax": control}, args=(0x33, ctx), until=l2._RETURN)
        z, end = (struct.unpack("<3f", sim.uc.mem_read(critter + off, 12))[2] for off in (0x1B0, 0x1BC))
        assert z == end
        return z

    rows = []
    for j in range(60):
        t = 3.0 + j * 16.0 / 30
        rows.append((ride(j, t), pose_at(t), 0.25 * j < 8.0))
    lows = [z + low for z, low, _ in rows]
    on = [j for j, (_, _, over) in enumerate(rows) if over]
    assert all(lows[j] == pytest.approx(-3.75, abs=2e-3) for j in on), [round(lows[j], 3) for j in on]
    assert max(abs(rows[j][0] - rows[j - 1][0]) for j in on[1:]) > 1.0          # the origin against the bob
    for j in range(on[-1] + 1, len(rows)):                                     # no floor: the origin a step a tick
        assert rows[j][0] == pytest.approx(max(game, rows[j - 1][0] - 0.847), abs=1e-3), j
    assert rows[-1][0] == pytest.approx(game, abs=1e-4)
    floor["to"] = 1e9
    live = 3.0 * 4.0 - margin
    for kw in ({"weight": 0.5}, {"clip_length": 1.5}):                         # the live bones less the margin
        z0 = ride(100, 3.0)
        want = min(max(game, -3.75 - live, z0 - 0.847), max(z0 + 0.847, game))   # the switch: the origin steps
        assert ride(101, 3.0 + 16.0 / 30, **kw) == pytest.approx(want, abs=1e-3), kw
    zs = [ride(110 + j, 3.0, weight=0.5) for j in range(8)]                   # the live hold settles on the floor
    assert zs[-1] == pytest.approx(-3.75 - live, abs=1e-3)
    t = 3.0 + 4 * 16.0 / 30                                                   # the switch to the table
    lows = [ride(120 + j, t + j * 16.0 / 30) + pose_at(t + j * 16.0 / 30) for j in range(16)]
    assert lows[0] == pytest.approx(max(-3.75, zs[-1] - 0.847 + pose_at(t)), abs=1e-3)   # the origin a step down
    assert lows[0] > -3.75 + 2.0
    assert all(b_ == pytest.approx(max(-3.75, a_ - 0.847), abs=1e-3) for a_, b_ in zip(lows, lows[1:])), lows
    assert lows[-1] == pytest.approx(-3.75, abs=1e-3)


def test_the_crossfade_model_blends_two_clips_keying_turns_in_opposite_signs_the_short_way():
    """AZ-825 (Step 2.207d): 0xCB730 turns each anim layer's rotation to
    unit length and w >= 0 before 0xA0B70 blends it (0xCBB6D-0xCBB7C),
    so a clip keying a bone's turn of 60 degrees as q and one keying 80
    degrees as -q blend between the two (70 half-way); the crossfade model
    X28's and X48's tables read summed the raw components, the long way
    round: a quarter in, the tip 0.64 under the root, under both clips'
    (0.50 and 0.17), half-way over it."""
    from azurkit.tools.characters.characters import BoneRecord
    from azurkit.tools.characters.retarget import Clip, Track
    from azurkit.tools.characters import _player_crossfade as cf

    rest = (0.0, 0.0, 0.0, 1.0)
    rig = Rig("two", (BoneRecord("root", -1, False, rest, rest, (0.0, 0.0, 0.0), rest, (1.0, 1.0, 1.0)),
                      BoneRecord("tip", 0, False, rest, rest, (0.0, 0.0, -1.0), rest, (1.0, 1.0, 1.0))),
              ((0.0, 0.0, 0.0), (0.0, 0.0, -1.0)), (rest, rest), ())

    def held(degrees: float, sign: float):   # a clip keying the root's turn about x, sampled at t 0
        h = math.radians(degrees) / 2
        keys = (math.sin(h), 0.0, 0.0, math.cos(h))
        return cf.sample(rig, Clip(1.0, tuple(Track(0, 3 + c, ((0.0, sign * v, 0.0, 0.0),))
                                              for c, v in enumerate(keys)), ()), [0.0])
    a, b = held(60.0, 1.0), held(80.0, -1.0)
    lows = [float(cf.lowest(rig, cf.blend(a, b, w))[0]) for w in (0.25, 0.5, 0.75)]
    assert all(-math.cos(math.radians(60.0)) <= v <= -math.cos(math.radians(80.0)) for v in lows), lows
    assert lows[1] == pytest.approx(-math.cos(math.radians(70.0)), abs=1e-9)


def test_hang_starts_end_and_the_rides_crossfade_are_held_by_their_known_pose_so_a_fitting_hang_keeps_under_the_cable():
    """AZ-713 (Step 2.199, X28): hang_start held the least of its table and
    the live bones less the margin (a tick of the pose's fastest move) on
    every tick, and the ride the live bones less the margin until its hang
    layer had crossed in, so key_air1 own x2 (margin 2.42 m) left
    hang_start 3.27 m over f3's start platform and rose to 4.95 m over it
    on the ride's first 9 ticks, its top up to 4.26 m over the cable on
    ride ticks 1-14 where it fits under it (Step 2.189b's record sitting).
    The build writes X28 the ride's crossfade from hang_start's clip (its
    time at the ride's first tick, its rate) into the hang clip from t 0:
    key_air1 own x2's 8 lows the sitting's frames of ride ticks 1-8 (whose
    ride replayed its idle on a layer of its own) to 0.01 m. The ride (L2,
    key_air1 own x2's build; collision_sweep, 0x8C080, 0x402E0 and 0x42070
    stubbed) whose hang layer fades in (its weight the tick) while the one
    other layer holds hang_start's clip at that tick's time draws its
    lowest point on the platform from that table, no margin, then from the
    loop's; with that layer's time 2 ticks off, or a third layer playing,
    the live bones less the margin, as before. hang_start holds by its
    table alone once its prior's layer is free, the least of it and the
    live bones less the margin while that layer plays. Its table is the
    ride going on on hang_start's layer; where a layer before its own
    holds its clip (0xCAD40's loop takes that one first and restarts the
    clip there: key_air1's crossfade) it holds by the least of that and
    the crossfade's dips ahead, which the build writes per tick: a table
    of both ways rose guard_air own x2 1.1 m off the platform over
    hang_start's last two ticks for a crossfade its ride doesn't play
    (the record seat's sitting)."""
    built = bytes(_swap("key_air1", sounds="garret4", model_scale=2.0)["default.xbe"])
    ride_hook, setup_hook, tick_hook = HOLD_HOOKS

    def param(name: str, fmt: str, hook=ride_hook):
        va = trampoline_symbol_va(built, hook, f"_player_model_hold_{name}", shim_source=HOLD_SHIM.source_path())
        return struct.unpack_from(fmt, built, resolve_va_to_file(built, va))
    length, t1, rate, *cross = param("cross", "<11f")
    assert param("cross", "<33f")[11:] == pytest.approx(hold_ahead([math.inf] * 22 + cross), abs=1e-4)
    loop_length, *loop = param("loop", "<65f")
    least = param("table", "<22f")
    margin, = param("margin", "<f")
    assert (length, loop_length, rate) == (24.0, 24.0, 1.0) and t1 == pytest.approx(22 / 30, abs=1e-6)
    seen = (13.0924, 13.098, 13.2057, 13.4996, 14.0416, 14.8537, 15.9342, 17.2633)   # sitting 2.189b, r1-r8
    assert cross == pytest.approx(seen, abs=0.01)
    sim, base = Sim(built), 0x20000000
    sim.uc.mem_map(base, 0x10000)
    control, critter, species, level, clock, anim, body, bones, ctx, clips = (base + 0x800 * k for k in range(10))
    for at, value in ((control + 0xC, clock), (control + 0x20, critter), (critter + 0x154, level),
                      (level + 0xAC, 0x5A5A0000), (critter + 0x178, species), (critter + 0x17C, anim),
                      (anim, body), (anim + 8, bones), (body, 1), (species + 0x64, 0x24)):
        sim.uc.mem_write(at, struct.pack("<I", value))
    sim.uc.mem_write(critter + 0x188, struct.pack("<f", 4.0))
    floor, step, frac = -3.75, 0.847, [0.0]

    def stub(uc, addr, size, _):   # collision_sweep (the platform), 0x8C080 (RET 8), 0x402E0 (no term), 0x42070
        esp = sim.reg("esp")
        if addr == 0x60870:
            ret, frm, to, rec = (struct.unpack("<I", uc.mem_read(esp + o, 4))[0] for o in (0, 16, 20, 36))
            frm, to = (struct.unpack("<3f", uc.mem_read(v, 12))[2] for v in (frm, to))
            got = to <= floor <= frm
            if got:
                uc.mem_write(rec + 0x14, struct.pack("<2f", 1.0, (frm - floor) / (frm - to)))
            eax, pop = int(got), 40
        elif addr == 0x8C080:
            ret, eax, pop = struct.unpack("<I", uc.mem_read(esp, 4))[0], sim.reg("eax"), 12
        elif addr == 0x402E0:
            ret, eax, pop = struct.unpack("<I", uc.mem_read(esp, 4))[0], sim.reg("edi"), 4
            uc.mem_write(eax, struct.pack("<3f", 0.0, 0.0, 0.0))
        else:   # __stdcall(8): frac[0] of the way from +0x1B0 to +0x1BC
            ret, me, eax = struct.unpack("<3I", uc.mem_read(esp, 12))
            a, b = (struct.unpack("<3f", uc.mem_read(me + off, 12)) for off in (0x1B0, 0x1BC))
            uc.mem_write(eax, struct.pack("<3f", *(p + frac[0] * (q - p) for p, q in zip(a, b))))
            pop = 12
        uc.reg_write(UC_X86_REG_EAX, eax)
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + pop)
    for va in (0x60870, 0x8C080, 0x402E0, 0x42070):
        sim.uc.hook_add(UC_HOOK_CODE, stub, begin=va, end=va)

    def entry(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]

    def layers(active: int, *rows, alias: bool = False) -> None:
        """The anim layers: per layer (its clip's length, flags, time, weight); the ``active`` one; ``alias``:
        layer 0 holds the active one's clip."""
        for n in range(3):
            length_, flags, time_, weight = rows[n] if n < len(rows) else (0.0, 0, 0.0, 0.0)
            sim.uc.mem_write(clips + 0x40 * n + 0x10, struct.pack("<f", length_))
            clip = clips + 0x40 * (active if alias and n == 0 else n) if length_ else 0
            sim.uc.mem_write(anim + 0x44 + 0x40 * n, struct.pack("<2I", clip, flags))
            sim.uc.mem_write(anim + 0x58 + 0x40 * n, struct.pack("<2f", time_, weight))
        sim.uc.mem_write(anim + 0x10, struct.pack("<i", active))

    game = -1.86 - 23.962   # the ride's game origin against the cable (0)

    def ride(t: float, k: int, *, off: float = 0.0, third: bool = False, bone: float = 3.0) -> float:
        """A ride tick at clock ``t``, ``k`` ticks into the crossfade (hang_start's layer ``off`` ticks
        late): the drawn origin's height."""
        old = (24.0, 0x11, t1 + (k + off) / 30, max(0.0, 1.0 - k / 7.5)) if k < 8 else (24.0, 0, 0.0, 0.0)
        layers(1, old, (24.0, 0xB, k * 16.0 / 30, min(1.0, 0.01 + k / 7.5)), *[(2.5, 0x11, 0.3, 0.2)] * third)
        sim.uc.mem_write(clock + 0x10, struct.pack("<d", t))
        sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 0.25 * k, 1.0, -1.86))
        for off_ in (0x1B0, 0x1BC):
            sim.uc.mem_write(critter + off_, struct.pack("<3f", 0.25 * k, 1.0, game))
        sim.uc.mem_write(bones + 0xA8, struct.pack("<f", bone))   # the last drawn bone, model units
        sim.call(entry(ride_hook), regs={"eax": control}, args=(0x33, ctx), until=l2._RETURN)
        return struct.unpack("<3f", sim.uc.mem_read(critter + 0x1B0, 12))[2]

    def loop_at(t: float) -> float:
        f = (t / 24.0) % 1.0 * 64
        i = int(f)
        return loop[i] * (1 - (f - i)) + loop[(i + 1) % 64] * (f - i)
    lows = [ride(100.0 + k / 30, k) + (cross[k] if k < 8 else loop_at(k * 16.0 / 30)) for k in range(14)]
    assert lows == pytest.approx([floor] * 14, abs=2e-3)                          # on the platform every tick
    live = 3.0 * 4.0 - margin
    for kw in ({"off": 2.0}, {"third": True}):                                   # not the ride's own crossfade
        assert ride(200.0, 3, **kw) == pytest.approx(floor - live, abs=1e-3), kw   # the live bones less the margin
    assert ride(300.0, 3) == pytest.approx(floor - cross[3], abs=1e-3)

    def hang_start(t0: float, prior_free_from: int, alias: bool = False) -> list[float]:
        """The set-up and 21 ticks from a prior of no build's length, its layer free from tick
        ``prior_free_from``, the live bone 0.84 m under the table's end (as key_air1's mesh lies over its
        bone, sitting 2.189b); ``alias``: from tick 1 the prior's layer holds hang_start's clip. Per tick the
        drawn height."""
        stance, deep = floor, game
        for off_, z in ((0x1B0, stance), (0x1BC, deep)):
            sim.uc.mem_write(critter + off_, struct.pack("<3f", 0.0, 1.0, z))
        sim.uc.mem_write(bones + 0xA8, struct.pack("<f", (least[-1] - 0.84) / 4.0))
        sim.uc.mem_write(control + 0x30, struct.pack("<I", 0x1234))
        drawn = []
        for j in range(22):
            prior = (2.5, 0x11, 0.3, 1.0) if j < prior_free_from else (2.5, 0, 0.0, 0.0)
            layers(1, prior, (24.0, 0xF, j / 30, min(1.0, 0.01 + j / 7.5)), alias=alias and j > 0)
            frac[0] = j / 22
            sim.uc.mem_write(clock + 0x10, struct.pack("<d", t0 + j / 30))
            sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 0.0, 1.0, stance + 1.0))
            if j == 0:
                sim.call(entry(setup_hook), regs={"eax": control}, args=(0x33, ctx), until=l2._RETURN)
            else:
                sim.call(entry(tick_hook), regs={"ebp": control}, until=l2._RETURN)
            a, b = (struct.unpack("<3f", sim.uc.mem_read(critter + off_, 12))[2] for off_ in (0x1B0, 0x1BC))
            drawn.append(a + frac[0] * (b - a))
        return drawn

    def expect(lows_: list[float]) -> list[float]:
        """hold_start's heights: the most of the game's, the floor less the low and the last less a step,
        at most a step over the last unless the game's is higher (the set-up's last the stance)."""
        out, last = [], floor
        for j in range(22):
            g = floor + j / 22 * (game - floor)
            want = max(g, floor - lows_[j], last - step)
            if want > last + step:
                want = max(last + step, g)
            out.append(want)
            last = want
        return out
    live = least[-1] - 0.84 - margin
    playing = hang_start(400.0, 22)
    assert playing == pytest.approx(expect([min(v, live) for v in least]), abs=2e-3)      # the prior plays: live too
    freed = hang_start(500.0, 9)
    assert freed == pytest.approx(expect([min(v, live) if j < 9 else v for j, v in enumerate(least)]), abs=2e-3)
    assert freed[-1] + least[-1] == pytest.approx(floor, abs=2e-3)               # on the floor at its end
    assert playing[-1] + least[-1] > floor + 3.0                                 # held up by the margin
    ahead = [5.0] * 12 + [v - 1.5 for v in least[12:]]   # a crossfade dipping 1.5 m under the table from tick 12
    for hook in (setup_hook, tick_hook):
        va = trampoline_symbol_va(built, hook, "_player_model_hold_cross", shim_source=HOLD_SHIM.source_path())
        sim.uc.mem_write(va + 4 * 11, struct.pack("<22f", *ahead))
    assert hang_start(600.0, 9) == pytest.approx(freed, abs=2e-3)                 # the ride goes on: not taken
    crossing = hang_start(700.0, 9, alias=True)                                   # a layer before holds its clip
    assert crossing == pytest.approx(expect([min(min(v, live) if j < 9 else v, ahead[j]) if j else min(v, live)
                                             for j, v in enumerate(least)]), abs=2e-3)
    assert crossing[-1] > freed[-1] + 1.0


def test_hang_start_is_held_by_the_table_of_the_prior_its_grab_starts_from_and_where_its_glide_dips():
    """AZ-574 (Step 2.175b, X28): X28's gate counted the hang alone, so a
    hang no deeper than garret4's got no hold however deep hang_start
    took the drawn body (overlord own x2, X' 1.45: its glide carries the
    origin 1.6 m under f3's start platform, the pose at it, 0.49 m
    through it), and hang_start's one table was the least over every
    prior clip and phase, so every grab was held up for the one that dips
    (guard_air own x2: from its idle at phase 0 0.23 m under its origin,
    at phase 4/12 3.56, from its walk 4.26; sitting 2.175b's frames of
    firedrake own x2's grab from its idle at t 0.567, its set-up's layers,
    matched the crossfade from that phase to 1 mm). The build now gates
    on that dip past where the body's own ground clips draw it (firedrake
    own x2's fly pose dips 4.29 m itself: no X28; flicken own x2 none) and
    keys a table per prior clip, by its length, and phase twelfth; X28
    (L2, guard_air own x2's build; collision_sweep, 0x8C080, 0x42070 and
    0x402E0 stubbed as in the X28 pin, the floor at the stance, the live
    pose high) picks one at the set-up by the anim layer other than the
    active one with the most weight and holds every tick of hang_start
    by it: the drawn heights are hold_start's with that table (the most
    of the game's, the floor less the table's entry and the last less a
    step, at most a step over the last), the idle's at phase 0, the
    idle's at phase 4/12 and the walk's apart, and the least for a clip
    of no prior's length."""
    built = bytes(_swap("guard_air", sounds="garret4", model_scale=2.0)["default.xbe"])
    _ride, setup_hook, tick_hook = HOLD_HOOKS
    va = trampoline_symbol_va(built, setup_hook, "_player_model_hold_priors", shim_source=HOLD_SHIM.source_path())
    keys = struct.unpack_from("<8f", built, resolve_va_to_file(built, va))
    tables = struct.unpack_from(f"<{8 * 12 * 22}f", built, resolve_va_to_file(built, va) + 32)
    least_va = trampoline_symbol_va(built, setup_hook, "_player_model_hold_table", shim_source=HOLD_SHIM.source_path())
    least = struct.unpack_from("<22f", built, resolve_va_to_file(built, least_va))
    idle, walk = _f32(3.93333333), _f32(0.93333333)
    assert idle in keys and walk in keys

    def table(key: float, twelfth: int) -> tuple[float, ...]:
        at = (keys.index(key) * 12 + twelfth) * 22
        return tables[at:at + 22]
    sim, base = Sim(built), 0x20000000
    sim.uc.mem_map(base, 0x10000)
    control, critter, species, level, clock, anim, body, bones, ctx, clips = (base + 0x800 * k for k in range(10))
    for at, value in ((control + 0xC, clock), (control + 0x20, critter), (critter + 0x154, level),
                      (level + 0xAC, 0x5A5A0000), (critter + 0x178, species), (critter + 0x17C, anim),
                      (anim, body), (anim + 8, bones), (body, 1), (species + 0x64, 0x24)):
        sim.uc.mem_write(at, struct.pack("<I", value))
    sim.uc.mem_write(critter + 0x188, struct.pack("<f", 2.0))
    sim.uc.mem_write(bones + 0xA8, struct.pack("<f", 50.0))   # the live pose: never the lower
    stance, deep, frac, step = -3.75, -6.0, [0.0], 0.847

    def sweep(uc, addr, size, _):   # collision_sweep: the platform under every point, __stdcall(36)
        esp = sim.reg("esp")
        ret, _tree, _me, _zero, frm, to, _rxy, _rz, _mask, rec = struct.unpack("<6I2f2I", uc.mem_read(esp, 40))
        frm, to = (struct.unpack("<3f", uc.mem_read(v, 12)) for v in (frm, to))
        got = to[2] <= stance <= frm[2]
        if got:
            uc.mem_write(rec + 0x14, struct.pack("<2f", 1.0, (frm[2] - stance) / (frm[2] - to[2])))
        uc.reg_write(UC_X86_REG_EAX, int(got))
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 40)

    def landing(uc, addr, size, _):   # 0x8C080: RET 8
        esp = sim.reg("esp")
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 12)

    def node(uc, addr, size, _):   # 0x402E0: no term, a plain RET
        esp, out = sim.reg("esp"), sim.reg("edi")
        uc.mem_write(out, struct.pack("<3f", 0.0, 0.0, 0.0))
        uc.reg_write(UC_X86_REG_EAX, out)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    def blend(uc, addr, size, _):   # 0x42070, __stdcall(8): frac[0] of the way from +0x1B0 to +0x1BC
        esp = sim.reg("esp")
        ret, me, out = struct.unpack("<3I", uc.mem_read(esp, 12))
        a, b = (struct.unpack("<3f", uc.mem_read(me + off, 12)) for off in (0x1B0, 0x1BC))
        uc.mem_write(out, struct.pack("<3f", *(p + frac[0] * (q - p) for p, q in zip(a, b))))
        uc.reg_write(UC_X86_REG_EAX, out)
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 12)

    for va_, hook in ((0x60870, sweep), (0x8C080, landing), (0x42070, blend), (0x402E0, node)):
        sim.uc.hook_add(UC_HOOK_CODE, hook, begin=va_, end=va_)

    def entry(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]

    def hang_start(prior: float, t: float, t0: float) -> list[float]:
        """The set-up and 21 ticks from a prior layer of clip length ``prior`` at time ``t``: per tick
        the drawn height (the game's blend plus the hold's offset on the ends)."""
        for n, (length, flags, time_, weight) in enumerate(((0.0, 0, 0.0, 0.0), (prior, 19, t, 1.0),
                                                            (0.73333335, 77, 0.0, 0.01))):
            layer = anim + 0x40 + 0x40 * n
            sim.uc.mem_write(clips + 0x40 * n + 0x10, struct.pack("<f", length))
            sim.uc.mem_write(layer + 4, struct.pack("<2I", clips + 0x40 * n if length else 0, flags))
            sim.uc.mem_write(layer + 0x18, struct.pack("<2f", time_, weight))
        sim.uc.mem_write(anim + 0x10, struct.pack("<i", 2))
        sim.uc.mem_write(control + 0x30, struct.pack("<I", 0x1234))
        for off, z in ((0x1B0, stance), (0x1BC, deep)):
            sim.uc.mem_write(critter + off, struct.pack("<3f", 0.0, 1.0, z))
        drawn = []
        for j in range(22):
            frac[0] = j / 22
            sim.uc.mem_write(clock + 0x10, struct.pack("<d", t0 + j / 30))
            sim.uc.mem_write(critter + 0x15C, struct.pack("<3f", 0.0, 1.0, stance + 1.0))
            if j == 0:
                sim.call(entry(setup_hook), regs={"eax": control}, args=(0x33, ctx), until=l2._RETURN)
            else:
                sim.call(entry(tick_hook), regs={"ebp": control}, until=l2._RETURN)
            a, b = (struct.unpack("<3f", sim.uc.mem_read(critter + off, 12))[2] for off in (0x1B0, 0x1BC))
            drawn.append(a + frac[0] * (b - a))
        return drawn

    def expect(tab: tuple[float, ...]) -> list[float]:
        """hold_start's drawn heights with table ``tab``: the most of the game's, the floor less the entry and
        the last less a step, at most a step over the last unless the game's is higher (the set-up's last the
        stance)."""
        out, last = [], stance
        for j in range(22):
            g = stance + j / 22 * (deep - stance)
            want = max(g, stance - tab[j], last - step)
            if want > last + step:
                want = max(last + step, g)
            out.append(want)
            last = want
        return out
    cases = ((idle, 0.0, table(idle, 0)), (idle, 3.9333 * 4.5 / 12, table(idle, 4)), (walk, 0.4, table(walk, 5)),
             (_f32(2.5), 1.0, least))
    got = [hang_start(prior, t, 400.0 + 10 * k) for k, (prior, t, _) in enumerate(cases)]
    for (prior, t, tab), drawn in zip(cases, got):
        assert drawn == pytest.approx(expect(tab), abs=2e-3), (prior, t)
    assert got[0][4] < got[1][4] - 1.0 and got[1] != got[2] and max(got[3]) >= max(max(d) for d in got[:3]) - 1e-3
    for species_, want in (("overlord", "applied"), ("firedrake", "original"), ("flicken", "original")):
        xbe = bytes(_swap(species_, sounds="garret4", model_scale=2.0)["default.xbe"])
        assert {verify_trampoline_patch(xbe, hook) for hook in HOLD_HOOKS} == {want}, species_


def test_a_baked_body_drawn_at_a_model_scale_goes_over_the_ladder_top_onto_the_floor_where_garret4s_feet_land():
    """AZ-529's ladder (Step 2.106, X23): climb_up_edge (anim 0x3F, state
    0x100) glides the drawn origin from +0x1B0 to +0x1BC; 0x41E50 starts
    it from the drawn m_grab, scaled by the critter's +0x188, less the
    clip's m_grab unscaled, and 0x42430 ends it at the ledge less the
    clip's m_feet unscaled, so town_male_6 own x2 (D 2.3, baked) started
    2.95 m high, floated 1.8-3.1 m over the top floor and dropped into
    its stance (sitting 2.105). X23 (L2, that build; 0x8C080 stubbed) at
    the top dismount's CALL of 0x8C080 (0x87F65): the call with the
    caller's EAX (the PlayerControl) and arguments, RET 8, EBX, ESI, EDI
    and EBP kept, the x87 stack empty; for the player's species in state
    0x100 gliding (+0x19C 2) into climb_up_edge at D other than 1 the
    start moves down by (D - 1) x garret4's m_grab at the clip's start
    and the end by (D - 1) x his m_feet at its end (the vanilla 0xCAB80
    on his clip), turned by +0x18C (the vanilla 0xA1420). D 1, another
    anim, another state, no glide and another critter keep both. golem_ol
    own x2 (the overlord's golem: X9's stand-in, no markers; golem's own is
    baked since Step 2.134a) and balthazar own x1 (D 1) keep
    the CALL; since Step 2.118 (AZ-536, D291) a baked body drawn at D
    other than 1 at x1 takes it too (town_male_6 own x1, D 1.15, floated
    0.34 m over the top floor), but a one-bone rig only at a model scale
    (frag_air_1 own x1, D 4: X23 put garret4's feet where its bone is,
    8.75 m under the floor in sitting 2.118; AZ-562). The hoist (Step
    2.127, AZ-572): its setter sets state 0x100 with hoist (0x41) or
    hoist_waist (0x42), whose glide 0x42430 ends at the ledge less the
    clip's m_feet at its end unscaled, so garret4 x2 ended his drawn feet
    1.68 m over the ledge's floor, x0.5 0.90 m under it (sitting 2.123's
    h65); X23's second landing, the hoist's CALL of 0x8C080 at 0x86DAE,
    moves the end by (D - 1) x his m_feet at that clip's end, the start
    kept (climb_down_edge's 0x40 keeps both), on the bodies its ladder
    landing serves but one with no clips. Such a body (Step 2.127,
    AZ-562), whose root rides garret4's m_feet / D (the timer bake), takes
    the ladder's landing at D other than 1 at x1 too (frag_air_1 own x1,
    D 4) with its float param over_feet_k 0, so only the start moves (the
    game's unscaled end already puts the prop at its entity), and no X26;
    X8 takes his three rows at 1 / D (its timer mode)."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap("town_male_6", sounds="garret4", model_scale=2.0)["default.xbe"])
    assert l1.check(vanilla, built) == []
    characters = _vanilla("gamedata/characters.xbr")
    garret4 = read_body(characters, "garret4")
    length = garret4.length("climb_up_edge")
    turn = (0.0, 0.0, math.sin(math.radians(35)), math.cos(math.radians(35)))   # a 70-degree yaw
    grab = _garret4_node(characters, "climb_up_edge", "m_grab", 0.0, turn)
    feet = _garret4_node(characters, "climb_up_edge", "m_feet", length, turn)
    base = 0x20000000
    control, critter, species, ctx = (base + 0x1000 * k for k in range(4))
    start, end = (1.0, 2.0, 3.0), (4.0, 5.0, 9.0)

    def entry_of(hook) -> int:
        return hook.va + 5 + struct.unpack_from("<i", built, va_to_file(hook.va) + 1)[0]

    entry = entry_of(OVER_TOP_HOOK)

    feet_k = trampoline_symbol_va(built, OVER_TOP_HOOK, "_player_model_over_feet_k",
                                  shim_source=OVER_TOP_SHIM.source_path())
    assert struct.unpack_from("<f", built, resolve_va_to_file(built, feet_k))[0] == 1.0

    def dismount(*, scale: float = 2.3, anim: int = 0x3F, state: int = 0x100, mode: int = 2,
                 player: bool = True, via: int | None = None,
                 k: float | None = None) -> tuple[tuple[float, ...], tuple[float, ...]]:
        sim = Sim(built)
        sim.uc.mem_map(base, 0x4000)
        if k is not None:
            sim.uc.mem_write(feet_k, struct.pack("<f", k))
        for at, fmt, value in ((control + 0x20, "<I", critter), (control + 0x94, "<i", state),
                               (critter + 0x178, "<I", species), (critter + 0x188, "<f", scale),
                               (critter + 0x18C, "<4f", turn), (critter + 0x19C, "<i", mode),
                               (critter + 0x1B0, "<3f", start), (critter + 0x1BC, "<3f", end),
                               (critter + 0x200, "<i", anim), (species + 0x64, "<I", 0x24 if player else 0x04)):
            sim.uc.mem_write(at, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        calls = []

        def landing(uc, addr, size, _):   # 0x8C080: EAX the PlayerControl, RET 8
            esp = sim.reg("esp")
            calls.append((sim.reg("eax"), *struct.unpack("<2I", uc.mem_read(esp + 4, 8))))
            uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, esp + 12)

        sim.uc.hook_add(UC_HOOK_CODE, landing, begin=0x8C080, end=0x8C080)
        kept = {"ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44}
        sim.call(via or entry, regs={"eax": control, **kept}, args=(0x33, ctx), until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 8, as 0x8C080's
        assert {r: sim.reg(r) for r in kept} == kept
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        assert calls == [(control, 0x33, ctx)]
        return tuple(struct.unpack("<3f", sim.uc.mem_read(critter + off, 12)) for off in (0x1B0, 0x1BC))

    moved_start, moved_end = dismount()
    assert moved_start == pytest.approx(tuple(s - 1.3 * g for s, g in zip(start, grab)), abs=1e-4)
    assert moved_end == pytest.approx(tuple(e - 1.3 * f for e, f in zip(end, feet)), abs=1e-4)
    assert grab[2] > 2.2 and feet[2] > 2.2                         # 1.3 x 2.27 m: the float
    for kw in ({"scale": 1.0}, {"anim": 0x3E}, {"state": 0x101}, {"mode": 0}, {"player": False}):
        assert dismount(**kw) == (start, end), kw
    hoist = entry_of(OVER_HOIST_HOOK)
    for anim, clip in ((0x41, "hoist"), (0x42, "hoist_waist")):   # the hoist: its end only, by its own m_feet
        landed = _garret4_node(characters, clip, "m_feet", garret4.length(clip), turn)
        assert landed[2] > 1.0, clip                                # 1.77 / 1.00 m: the float x (D - 1)
        assert dismount(anim=anim, via=hoist) == (start, pytest.approx(
            tuple(e - 1.3 * f for e, f in zip(end, landed)), abs=1e-4)), clip
        for kw in ({"scale": 1.0}, {"state": 0}, {"mode": 0}, {"player": False}):
            assert dismount(anim=anim, via=hoist, **kw) == (start, end), (clip, kw)
    assert dismount(anim=0x40, via=hoist) == (start, end)           # climb_down_edge: neither
    lowered = dismount(k=0.0)                                        # a body with no clips': the start alone
    assert lowered == (pytest.approx(moved_start, abs=1e-6), end)
    for species_, scale, state, hoisted in (("overlord and golem", 2.0, "original", "original"),
                                            ("balthazar", 1.0, "original", "original"),
                                            ("town_male_6", 1.0, "applied", "applied"),
                                            ("frag_air_1", 1.0, "applied", "original")):
        xbe = bytes(_swap(species_, sounds="garret4", model_scale=scale)["default.xbe"])
        assert (verify_trampoline_patch(xbe, OVER_TOP_HOOK), verify_trampoline_patch(xbe, OVER_HOIST_HOOK)) == (
            state, hoisted), (species_, scale)
    assert verify_trampoline_patch(built, OVER_HOIST_HOOK) == "applied"
    # frag_air_1 own x1 (no clips, D 4): X23's start term alone, no X26, X8 no rows and its timer 1 / D

    def param(hook, shim, symbol, n=1):
        return struct.unpack_from(f"<{n}f", xbe, resolve_va_to_file(xbe, trampoline_symbol_va(
            xbe, hook, symbol, shim_source=shim.source_path())))

    assert (param(OVER_TOP_HOOK, OVER_TOP_SHIM, "_player_model_over_feet_k"),
            verify_trampoline_patch(xbe, STANCE_HOOK)) == ((0.0,), "original")
    assert param(EYE_HOOK, EYE_SHIM, "_player_model_over_timer") == pytest.approx((0.25,), rel=1e-6)
    assert param(EYE_HOOK, EYE_SHIM, "_player_model_over_feet", 9) == (0.0,) * 9


def test_a_baked_body_drawn_larger_stays_on_the_floor_and_in_frame_from_a_ladders_top_into_its_stance():
    """D286's limit 2 (Step 2.116; Step 2.107's L10). climb_up_edge (state
    0x100, +0x200 0x3F) glides the drawn origin from +0x1B0 to +0x1BC
    (+0x19C 2, 0x42070's blend) while the clip lifts the body: X8's (0, 0,
    top) on that origin let every baked body climb to the frame's top edge,
    and under X23's lowered end keylord own x2's point sank under the hatch
    until the 0.8 s sight pull took the camera 10.5 m in (sitting 2.107 C).
    At the switch to the stance 0x402E0's aligned-node term (added unscaled
    after critter_model_matrix's CALL at 0x42253) holds the drawn origin
    back by 1 x m_feet while the bones are x D, so the body and the point
    popped (D - 1) x 2.647 m (3.0-6.7 m measured, 7.9 m computed on keylord
    own x2). X26 (L2, keylord own x2's build, 0x402E0 stubbed) at 0x42253:
    the game's term, x the drawn scale while the stance's hold is on: on in
    state 0 right after climb_up_edge (0x100, +0x200 0x3F; another
    critter between doesn't count) with the node m_feet and the term over
    1 mm, kept through a jump (state 2) while both hold, off under 1 mm and
    staying off outside state 0 (the zipline's let-go), never in a stance
    after anything else (a landing, the step-up's anim 53: sitting 2.116's
    skeptic, its 0.84 m one-tick step on keylord own x2), nor for the node
    m_grab (the ladder latches) or another critter; EAX = EDI, a plain
    RET, EBX, ESI, EDI and
    EBP kept, the x87 stack empty. X8 (0x42070 and 0x402E0 stubbed): on a
    baked body (the build's over_feet, garret4's climb_up_edge m_feet) the
    glide's point is (0, 0, top) + t x m_feet, t the glide's fraction (0,
    0.5, 1; a hit's 0x102 too; 1 on a glide under 1 mm), and while the same
    hold is on (0, 0, top) less the term (after the step-up the land
    point); the land point otherwise, and its
    swim point in the water. With over_timer (Step 2.127, AZ-562: a body
    with no clips, its root riding garret4's m_feet / D) the point out of
    the water is (0, 0, top) + over_timer x its m_feet marker, which the
    vanilla 0xCB2A0 reads from the anim object (critter +0x17C), in any
    state (the zipline's 5 and hang_start's 0x105, a glide, the hold),
    and the land point with no anim object. golem_ol own x2 (the overlord's
    golem, X9's stand-ins, no over_feet; golem's own is baked since Step
    2.134a) keeps the land point there; X26 is installed where X23 is
    (town_male_6 and keylord own x2, not keylord own x1 nor golem_ol own
    x2), and the build's summary names both only there."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap("keylord", sounds="garret4", model_scale=2.0)["default.xbe"])
    assert l1.check(vanilla, built) == []
    characters = _vanilla("gamedata/characters.xbr")
    length = read_body(characters, "garret4").length("climb_up_edge")
    unturned = (0.0, 0.0, 0.0, 1.0)
    assert G4_OVER_FEET == pytest.approx(_garret4_node(characters, "climb_up_edge", "m_feet", length, unturned),
                                         abs=1e-6)
    base = 0x20000000
    critter, species, control, names, out, term_at = (base + 0x1000 * k for k in range(6))
    node_at = {"m_feet": names, "m_grab": names + 0x10, "m_root": names + 0x20}
    now = {"term": (0.0, 0.0, 0.0), "at": None}

    def sim_for(xbe: bytes) -> Sim:
        sim = Sim(xbe)
        sim.uc.mem_map(base, 0x8000)
        for name, at in node_at.items():
            sim.uc.mem_write(at, name.encode() + b"\0")

        def node_offset(uc, addr, size, _):   # 0x402E0: EAX the critter, EDI the out; EAX = EDI, a plain RET
            esp, edi = sim.reg("esp"), sim.reg("edi")
            uc.mem_write(edi, struct.pack("<3f", *now["term"]))
            uc.reg_write(UC_X86_REG_EAX, edi)
            uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, esp + 4)

        def glide(uc, addr, size, _):   # 0x42070: __stdcall(8), the critter and the out; EAX = out
            esp = sim.reg("esp")
            ret, who, dst = struct.unpack("<3I", uc.mem_read(esp, 12))
            uc.mem_write(dst, struct.pack("<3f", *(now["at"] or struct.unpack("<3f", uc.mem_read(who + 0x1B0, 12)))))
            uc.reg_write(UC_X86_REG_EAX, dst)
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 12)

        sim.uc.hook_add(UC_HOOK_CODE, node_offset, begin=0x402E0, end=0x402E0)
        sim.uc.hook_add(UC_HOOK_CODE, glide, begin=0x42070, end=0x42070)
        return sim

    def place(sim: Sim, *, state: int, node: str = "m_feet", term=(0.0, 0.0, 0.0), at=None, player: bool = True,
              anim: int = 0, mode: int = 0, start=(1.0, 2.0, 3.0), end=None, depth: float = -50.0) -> None:
        now.update(term=term, at=at)
        for at_, fmt, value in ((critter + 0x15C, "<3f", start), (critter + 0x178, "<I", species),
                                (critter + 0x180, "<I", control), (critter + 0x188, "<f", 4.0),
                                (critter + 0x18C, "<4f", unturned), (critter + 0x19C, "<i", mode),
                                (critter + 0x1B0, "<3f", start), (critter + 0x1BC, "<3f", end or start),
                                (critter + 0x1F8, "<I", node_at[node]), (critter + 0x200, "<i", anim),
                                (critter + 0x27C, "<f", depth), (species + 0x64, "<I", 0x24 if player else 0x04),
                                (control + 0x94, "<i", state)):
            sim.uc.mem_write(at_, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))

    def stance(sim: Sim, **row) -> tuple[float, ...]:
        place(sim, **row)
        kept = {"ebx": 0x11, "esi": 0x22, "edi": term_at, "ebp": 0x44}
        eax = sim.call(STANCE_HOOK.va + 5 + struct.unpack_from("<i", built, va_to_file(STANCE_HOOK.va) + 1)[0],
                       regs={"eax": critter, **kept}, until=l2._RETURN)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # a plain RET, as 0x402E0's
        assert (eax, {r: sim.reg(r) for r in kept}) == (term_at, kept)
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        return struct.unpack("<3f", sim.uc.mem_read(term_at, 12))

    def point(sim: Sim, xbe: bytes, **row) -> tuple[float, ...]:
        place(sim, **row)
        sim.uc.mem_write(out, struct.pack("<3f", 9.0, 9.0, 9.0))
        eax = sim.call(0x41F6C + struct.unpack_from("<i", xbe, va_to_file(0x41F67) + 1)[0],
                       regs={"edi": critter, "ecx": 0, "eax": out}, args=(names,), until=l2._RETURN)
        assert (eax, sim.reg("esp")) == (out, l2._STACK_TOP - 0x100)   # RET 4, out in EAX
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        return struct.unpack("<3f", sim.uc.mem_read(out, 12))

    t1, t2, tiny = (0.5, -1.0, -2.5), (0.25, -0.5, -0.4), (0.0, 0.0, 0.0005)
    sim = sim_for(built)
    edge = {"state": 0x100, "anim": 0x3F, "node": "m_grab"}
    rows = (({**edge, "term": t1}, t1),                                    # climb_up_edge: the game's
            ({"state": 0, "term": t1, "player": False}, t1),               # another critter between
            ({"state": 0, "term": t1}, tuple(4.0 * v for v in t1)),        # the stance after it: the term x D
            ({"state": 2, "term": t2}, tuple(4.0 * v for v in t2)),        # a jump in it: still held
            ({"state": 2, "term": tiny}, tiny),                            # under 1 mm: the hold is off
            ({"state": 2, "term": t2}, t2),                                # and stays off outside state 0
            ({"state": 0, "term": t1}, t1),                                # a landing's stance: the game's
            ({"state": 0x100, "anim": 53, "term": t2}, t2),                # the step-up (anim 53)
            ({"state": 0, "term": t1}, t1),                                # its end: the game's
            *((row, v) for hoist in (0x41, 0x42) for row, v in (          # a hoist (Step 2.127): as the top
                ({"state": 0x100, "anim": hoist, "term": t2}, t2),
                ({"state": 0, "term": t1}, tuple(4.0 * v for v in t1)),
                ({"state": 0, "term": tiny}, tiny))),
            (edge, (0.0, 0.0, 0.0)),
            ({"state": 0, "node": "m_grab", "term": t1}, t1),              # a ladder latch's node
            ({"state": 0, "term": t1}, t1))                                # and no hold after it
    assert [stance(sim, **row) for row, _ in rows] == [pytest.approx(v, abs=1e-6) for _, v in rows]

    def eye_param(xbe: bytes, name: str, n: int = 1) -> tuple[float, ...]:
        return struct.unpack_from(f"<{n}f", xbe, resolve_va_to_file(xbe, trampoline_symbol_va(
            xbe, EYE_HOOK, name, shim_source=EYE_SHIM.source_path())))

    top = eye_param(built, "_player_model_eye_height")[0]
    rows9 = eye_param(built, "_player_model_over_feet", 9)
    assert rows9 == pytest.approx([f for row in G4_OVER_ROWS for f in row], abs=1e-6)
    feet, hoisted = rows9[:3], rows9[3:6]
    assert hoisted == pytest.approx(_garret4_node(characters, "hoist", "m_feet", read_body(
        characters, "garret4").length("hoist"), unturned), abs=1e-6)
    start, end = (1.0, 2.0, 3.0), (1.5, 4.0, 1.0)
    mid = tuple(a + 0.5 * (b - a) for a, b in zip(start, end))
    glide = {"anim": 0x3F, "mode": 2, "start": start, "end": end}

    def lifted(k: float, by=feet) -> tuple[float, ...]:
        return tuple(k * f + (top if i == 2 else 0.0) for i, f in enumerate(by))

    sim = sim_for(built)
    rows = (({"state": 0x100, "at": start, **glide}, lifted(0.0)),        # the glide's start: the land point
            ({"state": 0x100, "at": mid, **glide}, lifted(0.5)),          # half way: half garret4's m_feet over it
            ({"state": 0x100, "at": end, **glide}, lifted(1.0)),          # its end: the ledge plus the top
            ({"state": 0x102, "at": mid, **glide}, lifted(0.5)),          # hit mid-glide: the same
            ({"state": 0x100, **glide, "end": start}, lifted(1.0)),       # a glide under 1 mm: its end
            ({"state": 0x100, "node": "m_grab", "anim": 0x3F}, lifted(0.0)),   # no glide
            ({"state": 0, "term": t1}, lifted(-1.0, t1)),                 # the stance: less the term
            ({"state": 2, "term": t2}, lifted(-1.0, t2)),                 # a jump in it: still
            ({"state": 2, "term": tiny}, lifted(0.0)),                    # under 1 mm: the land point
            ({"state": 2, "term": t2}, lifted(0.0)),                      # and stays so outside state 0
            ({"state": 0x100, "anim": 53, "term": t2}, lifted(0.0)),      # the step-up (anim 53)
            ({"state": 0, "term": t1}, lifted(0.0)),                      # its end: the land point
            ({"state": 0x100, "at": mid, **glide, "anim": 0x41}, lifted(0.5, hoisted)),   # a hoist: its own row
            ({"state": 0, "term": t1}, lifted(-1.0, t1)),                 # held after it
            ({"state": 0, "term": tiny}, lifted(0.0)),
            ({"state": 0x100, "node": "m_grab", "anim": 0x3F}, lifted(0.0)),
            ({"state": 0, "node": "m_grab", "term": t1}, lifted(0.0)),    # a ladder latch's node
            ({"state": 0, "term": t1}, lifted(0.0)),                      # and no hold after it
            ({"state": 6, "node": "m_root", "depth": 1.0}, lifted(0.0)))  # swimming: its swim point, the top here
    assert [point(sim, built, **row) for row, _ in rows] == [pytest.approx(v, abs=1e-4) for _, v in rows]
    timer = trampoline_symbol_va(built, EYE_HOOK, "_player_model_over_timer", shim_source=EYE_SHIM.source_path())
    assert struct.unpack_from("<f", built, resolve_va_to_file(built, timer))[0] == 0.0
    sim.uc.mem_write(timer, struct.pack("<f", 0.25))                      # a body with no clips at D 4 (Step 2.127)

    def marker(at) -> None:   # the anim object (critter +0x17C), its body's m_feet record and runtime marker
        anim, rig = base + 0x6000, base + 0x6100
        sim.uc.mem_write(critter + 0x17C, struct.pack("<I", anim if at else 0))
        sim.uc.mem_write(anim, struct.pack("<4I", rig, 0, 0, anim + 0x40))
        sim.uc.mem_write(anim + 0x40, struct.pack("<I3f", rig + 0x80, *(at or (0.0,) * 3)))
        sim.uc.mem_write(rig + 0x18, struct.pack("<I", 1))
        sim.uc.mem_write(rig + 0x80, struct.pack("<Ii", 6, names - (rig + 0x84)))

    hang, roll = (0.0, 0.645, 1.196), (0.0, 4.065, 0.0)
    rows = ((hang, {"state": 5}, lifted(0.25, hang)),                     # the zipline: the hang's m_feet / D
            (hang, {"state": 0x105}, lifted(0.25, hang)),                 # hang_start
            (feet, {"state": 0x100, "at": mid, **glide}, lifted(0.25)),   # a glide: the marker, not t x the row
            (feet, {"state": 0, "term": t1}, lifted(0.25)),               # held: the marker, not the term
            (roll, {"state": 0}, lifted(0.25, roll)),                     # the roll's root motion
            (hang, {"state": 6, "node": "m_root", "depth": 1.0}, lifted(0.0)),   # swimming: its swim point
            (None, {"state": 5}, lifted(0.0)))                            # no anim object: the land point
    got = []
    for at, row, _ in rows:
        marker(at)
        got.append(point(sim, built, **row))
    assert got == [pytest.approx(v, abs=1e-4) for _, _, v in rows]
    def build(species_: str, scale: float) -> tuple[bytes, str]:
        told: list[str] = []
        game = _swap(species_, sounds="garret4", model_scale=scale, lines=told)
        return bytes(game["default.xbe"]), " ".join(told)

    golem, golem_told = build("overlord and golem", 2.0)
    sim, top = sim_for(golem), eye_param(golem, "_player_model_eye_height")[0]
    for row in ({"state": 0x100, "at": end, **glide}, {"state": 0, "term": t1}):
        assert point(sim, golem, **row) == pytest.approx((0.0, 0.0, top), abs=1e-6), row
    for species_, scale, state in (("town_male_6", 2.0, "applied"), ("keylord", 1.0, "applied"),
                                   ("balthazar", 1.0, "original"), ("overlord and golem", 2.0, "original")):
        xbe, told = (golem, golem_told) if species_ == "overlord and golem" else build(species_, scale)
        assert (verify_trampoline_patch(xbe, STANCE_HOOK), verify_trampoline_patch(xbe, OVER_TOP_HOOK)) == (
            state, state), species_
        assert ("(X23)" in told, "(X26)" in told) == (state == "applied",) * 2, species_   # the summary names them
    assert verify_trampoline_patch(built, STANCE_HOOK) == "applied"


def test_a_baked_body_drawn_larger_goes_over_the_ladder_top_with_its_lowest_point_no_higher_than_the_top_floor():
    """AZ-529 (c) (Step 2.175b, X26): X23 moves climb_up_edge's glide ends
    to the drawn scale, but between them the clip's own pose rises over
    its origin x D: keylord own x2 (D 4) drew its lowest point up to
    2.86 m over a1's top floor 8 ticks into the glide, where garret4's
    stays within 0.05 m of it (sitting 2.175b on main; the clip's lowest
    bone x D matched the frames' to 0.07 m from the crossfade's end on:
    results/glide-check). The build writes X26 the clip's lowest bone at
    its end (keylord's g4/climb_up_edge on its rig, where X23's end puts
    the drawn feet on the floor); X26 (L2, keylord own x2's build; 0x402E0
    and 0x42070 stubbed) in that glide (state 0x100, +0x200 0x3F, +0x19C
    2) lowers the term by however far the drawn lowest point (the glide
    origin plus the term plus D x the lowest posed bone) is over the
    glide's end's (+0x1BC plus D x that end bone): the game's under it,
    not gliding, and for another critter."""
    built = bytes(_swap("keylord", sounds="garret4", model_scale=2.0)["default.xbe"])
    grown = bytes(_swap("keylord", sounds="garret4", model_scale=2.0)["characters.xbr"])

    def param(name: str) -> float:
        va = trampoline_symbol_va(built, STANCE_HOOK, f"_player_model_stance_{name}", shim_source=STANCE_SHIM.source_path())
        return struct.unpack_from("<f", built, resolve_va_to_file(built, va))[0]
    from azurkit.tools.characters.retarget import named_clip
    clip = named_clip(grown, "keylord", "g4/climb_up_edge")
    end_low = min(z for _, _, z in origins(Rig.read(grown, "keylord"), clip, clip.length))
    assert param("glide_on") == 1.0 and param("glide_end") == pytest.approx(end_low, abs=1e-5) and end_low > 2.0
    base = 0x20000000
    critter, species, control, anim, body, bones, term_at = (base + 0x1000 * k for k in range(7))
    sim = Sim(built)
    sim.uc.mem_map(base, 0x8000)
    now = {"term": (0.0, 0.0, 0.0), "at": (0.0, 0.0, -4.0)}

    def node_offset(uc, addr, size, _):   # 0x402E0: EAX the critter, EDI the out; EAX = EDI, a plain RET
        esp, edi = sim.reg("esp"), sim.reg("edi")
        uc.mem_write(edi, struct.pack("<3f", *now["term"]))
        uc.reg_write(UC_X86_REG_EAX, edi)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4)

    def glide(uc, addr, size, _):   # 0x42070: __stdcall(8), the critter and the out; EAX = out
        esp = sim.reg("esp")
        ret, _who, dst = struct.unpack("<3I", uc.mem_read(esp, 12))
        uc.mem_write(dst, struct.pack("<3f", *now["at"]))
        uc.reg_write(UC_X86_REG_EAX, dst)
        uc.reg_write(UC_X86_REG_EIP, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 12)

    sim.uc.hook_add(UC_HOOK_CODE, node_offset, begin=0x402E0, end=0x402E0)
    sim.uc.hook_add(UC_HOOK_CODE, glide, begin=0x42070, end=0x42070)
    entry = STANCE_HOOK.va + 5 + struct.unpack_from("<i", built, va_to_file(STANCE_HOOK.va) + 1)[0]

    def draw(lows: tuple[float, ...], *, term=(0.0, 0.0, 0.0), mode: int = 2, player: bool = True,
             end_z: float = -8.0) -> tuple[float, ...]:
        now["term"] = term
        for at_, fmt, value in ((critter + 0x178, "<I", species), (critter + 0x17C, "<I", anim),
                                (critter + 0x180, "<I", control), (critter + 0x188, "<f", 4.0),
                                (critter + 0x19C, "<i", mode), (critter + 0x1BC, "<3f", (0.0, 0.0, end_z)),
                                (critter + 0x1F8, "<I", 0), (critter + 0x200, "<i", 0x3F),
                                (species + 0x64, "<I", 0x24 if player else 0x04), (control + 0x94, "<i", 0x100),
                                (anim, "<I", body), (anim + 8, "<I", bones), (body, "<i", len(lows))):
            sim.uc.mem_write(at_, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        for k, z in enumerate(lows):
            sim.uc.mem_write(bones + 0xB0 * k + 0xA8, struct.pack("<f", z))
        kept = {"ebx": 0x11, "esi": 0x22, "edi": term_at, "ebp": 0x44}
        eax = sim.call(entry, regs={"eax": critter, **kept}, until=l2._RETURN)
        assert (eax, {r: sim.reg(r) for r in kept}) == (term_at, kept) and sim.reg("esp") == l2._STACK_TOP - 0x100
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        return struct.unpack("<3f", sim.uc.mem_read(term_at, 12))

    top = -8.0 + 4.0 * _f32(end_low)
    for lows, term in (((3.0, 1.6), (0.0, 0.0, 0.0)), ((1.6, 2.2), (0.1, -0.2, 0.3))):
        want = -4.0 + term[2] + 4.0 * 1.6 - top                       # its lowest over the top floor
        assert want > 1.0
        assert draw(lows, term=term) == pytest.approx((term[0], term[1], term[2] - want), abs=1e-4)
    assert draw((0.5, 3.0)) == (0.0, 0.0, 0.0)                         # under the top floor: the game's
    assert draw((3.0, 1.6), mode=0) == (0.0, 0.0, 0.0)                 # not gliding
    assert draw((3.0, 1.6), player=False) == (0.0, 0.0, 0.0)           # another critter


def test_a_swapped_body_latches_on_garret4s_ladder_offsets_where_his_clips_gave_it_none():
    """Step 2.63b (AZ-393; xemu 2.75a: no swapped body latched onto a1's
    ladder, 0x86DD0 returning 0 on the face garret4 latched on): the latch
    sweeps for the rungs at m_grab's height over m_root at climb_start's
    start (0x38B678 less 0x38ABB8), and that, with the offsets the latch
    from a jump, the top moves and the overhead hang aim by, is what
    player_move_offsets_init (0x84A40) samples once per boot at the
    PlayerPhysics constructor's CALL at 0x84E59: m_root, m_feet and
    m_grab at both ends of each of the player's clip slots, zeros for an
    empty slot or a marker the body lacks (every swapped body read 0.0
    there). X9's hook there (L1 well formed) gives each offset read that
    0x84A40 left (0, 0, 0) garret4's: L2 runs 0x84A40 on garret4's clips
    (the vanilla offsets, which the sitting's control read) and golem's
    hook with its ladder slots empty but climb_start's holding another
    clip, whose own offsets stay; the hang's two (hang_start's end) stay
    zero, so its target is the cable point, where the ride (0x8A510) puts
    a body without m_grab, not 3.2 m below it."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap("golem")["default.xbe"])
    characters = _vanilla("gamedata/characters.xbr")
    base = 0x20000000
    root, feet, grab = 0x38A610, 0x389B78, 0x38B0D0
    read = [(root, 0x3C, 0), (grab, 0x3C, 0), (grab, 0x3C, 1), (feet, 0x3E, 1), (grab, 0x3E, 1),
            (feet, 0x3F, 1), (grab, 0x3F, 0), (feet, 0x40, 1), (grab, 0x40, 1), (grab, 0x44, 1),
            (root, 0x44, 1)]

    def offsets(xbe: bytes, entry: int, clips: dict[int, str]) -> dict[tuple[int, int, int], tuple]:
        """The offsets ``read`` after ``entry`` runs for a player with
        garret4's body and ``clips`` (slot -> garret4's clip) in its slots."""
        sim = Sim(xbe)
        critter, species, anim, at = base, base + 0x1000, base + 0x2000, base + 0x200000
        sim.uc.mem_map(base, 0x4000000)
        off, size = _clip(characters, "characters/garret4")
        sim.uc.mem_write(base + 0x100000, characters[off:off + size])
        sim.uc.mem_write(anim, struct.pack("<I", base + 0x100000))
        sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
        loaded, table = {}, [-1] * 0x71
        for slot, clip in clips.items():
            off, size = _clip(characters, f"characters/garret4/{clip}")
            sim.uc.mem_write(at, characters[off:off + size])
            loaded[slot], table[slot], at = at, slot, at + (size + 0xFFF & ~0xFFF)
        sim.uc.mem_write(species + 0x124, struct.pack("<113i", *table))

        def resolve(uc, addr, size, _):   # 0xA67A0: the handle's clip, RET 8
            esp = sim.reg("esp")
            uc.reg_write(UC_X86_REG_EAX, loaded[sim.reg("eax")])
            uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 12)

        sim.uc.hook_add(UC_HOOK_CODE, resolve, begin=0xA67A0, end=0xA67A0)
        sim.call(entry, args=(critter,), until=l2._RETURN, budget=5_000_000)
        assert sim.reg("esp") == l2._STACK_TOP - 0x100        # RET 4, as 0x84A40's
        return {(a, s, e): struct.unpack("<3f", sim.uc.mem_read(a + 0x18 * s + 12 * e, 12)) for a, s, e in read}

    at = va_to_file(0x84E59)
    hook = 0x84E5E + struct.unpack_from("<i", built, at + 1)[0]
    assert built[at] == 0xE8 and l1.check(vanilla, built) == []
    ladder = {i: BASE_CLIPS[i] for i in (0x3C, 0x3E, 0x3F, 0x40, 0x44)}
    his = offsets(vanilla, 0x84A40, ladder)
    other = offsets(vanilla, 0x84A40, {0x3C: "climb_up_edge"})
    assert his[(root, 0x3C, 0)][2] == pytest.approx(1.0734, abs=1e-4)   # the sitting's control
    assert his[(grab, 0x3C, 1)] == pytest.approx((0.0, 0.6131, 2.269), abs=1e-4)
    swapped = offsets(built, hook, {0x3C: "climb_up_edge"})
    assert swapped == {k: other[k] if k[1] == 0x3C else (0.0,) * 3 if k[1] == 0x44 else his[k]
                       for k in read}
    assert swapped[(root, 0x3C, 0)] != his[(root, 0x3C, 0)]


@pytest.mark.parametrize("species, mode, rule", [
    ("town_male_6", "own", "garret4"), ("town_male_6", "garret4", "garret4"), ("gargoylestone", "own", None)])
def test_the_missing_clip_rule_is_the_modes_unless_asked(species, mode, rule):
    """Step 2.73a (D226, D229): with no recipe anims, X11's
    rule is the gameplay mode's: garret4's (a very similar own clip, else
    garret4's: baked onto the townsman's rig, Step 2.89) in garret4's
    exact and own body; a body with no clips (``None``) plays garret4's as
    timers in every mode, its own asked for too (it has none). Asked for,
    the rule is the one asked (the townsman's own clips, nothing baked)."""
    told: list[str] = []
    game = _swap(species, lines=told, mode=mode)
    line = told[0]
    if rule is None:
        asked = _swap(species, mode=mode, missing_anims="own")
        assert "garret4's play as timers" in line and asked["default.xbe"] == game["default.xbe"], line
    else:
        assert (f"(X11, anims {rule})" in line, "garret4's baked onto its rig in" in line) == (
            True, rule == "garret4"), line
    if (species, mode) == ("town_male_6", "own"):
        told = []
        _swap(species, lines=told, mode=mode, missing_anims="own")
        asked = told[0]
        assert "(X11, anims own)" in asked and "garret4's baked onto its rig in" not in asked, asked


def test_a_garret4_timed_stand_in_ends_in_garret4s_time():
    """Step 2.67 (X12, D229): off the bake's rigs X11 fills a slot with no
    very similar clip with the body's closest own one, marked
    garret4-timed, and anim_change (0x42910) plays it at rate 1, so a
    rock_shard jump played its idle at its own length, not garret4's
    1.73 s jump. X12's hook after the track binder (0xCAF6B) sees
    anim_change's return and sets the new layer's rate to the clip's
    length over garret4's (L2: anim_change run for the player's species,
    the handle resolver 0xA67A0 and the table resize 0xCD4F0 stubbed); an
    untimed slot (its idle, its idle_1) keeps rate 1, and so does any
    species without the player flag. A change without flag 4 to a clip a
    layer already plays (the fall, flags 2, after the jump on the same
    idle) takes 0xCAD40's other path, which makes that layer active
    again at rate 1 and skips the binder: X12's hook there (0xCAEC0)
    gives the fall garret4's fall time, and the idle_1 rate 1 again."""
    built = bytes(_swap("rock_shard")["default.xbe"])
    characters = _vanilla("gamedata/characters.xbr")
    garret4 = read_body(characters, "garret4")
    off, size = _clip(characters, "characters/rock_shard/idle")
    length = struct.unpack_from("<f", characters, off + 0x10)[0]

    def rate(flags: int, *changes: tuple[int, int]) -> float:
        """The active layer's rate after anim_change's ``changes`` (each
        an index and its flags) for a species with ``flags``."""
        sim, base = Sim(built), 0x20000000
        critter, species, anim, clock, clip = base, base + 0x1000, base + 0x2000, base + 0x3000, base + 0x100000
        sim.uc.mem_map(base, 0x1000000)
        sim.uc.mem_write(clip, characters[off:off + size])
        sim.uc.mem_write(critter + 0x178, struct.pack("<2I", species, anim))
        sim.uc.mem_write(species + 0x64, struct.pack("<I", flags))
        for index, _ in changes:
            sim.uc.mem_write(species + 0x124 + 4 * index, struct.pack("<i", 7))
        sim.uc.mem_write(anim + 4, struct.pack("<I", clock))
        free = [base + 0x800000]

        def resolve(uc, addr, size, _):   # 0xA67A0: the handle's clip, RET 8
            esp = sim.reg("esp")
            uc.reg_write(UC_X86_REG_EAX, clip)
            uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 12)

        def resize(uc, addr, size, _):    # 0xCD4F0: ECX the vector, EDX the count, the fill pushed
            esp, count = sim.reg("esp"), sim.reg("edx")
            uc.mem_write(free[0], bytes(uc.mem_read(sim.u32(esp + 4), 8)) * count)
            uc.mem_write(sim.reg("ecx"), struct.pack("<2I", free[0], free[0] + 8 * count))
            free[0] += 8 * count + 0x100
            uc.reg_write(UC_X86_REG_EIP, sim.u32(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 8)

        sim.uc.hook_add(UC_HOOK_CODE, resolve, begin=0xA67A0, end=0xA67A0)
        sim.uc.hook_add(UC_HOOK_CODE, resize, begin=0xCD4F0, end=0xCD4F0)
        for index, change in changes:
            sim.call(0x42910, args=(critter, index, change), until=0x429DF)
        return sim.f32(anim + 0x40 + 0x40 * sim.u32(anim + 0x10) + 0x20)

    def timed(clip: str) -> float:
        return _f32(length / _f32(garret4.length(clip)))

    changes = {"jump": ((15, 0),), "idle": ((1, 0),), "fall after jump": ((15, 4), (18, 2)),
               "idle_1 after jump": ((15, 4), (2, 2))}
    assert {(what, flags): rate(flags, *change) for what, change in changes.items()
            for flags in (0x24, 0x04)} == {
        ("jump", 0x24): timed("jump"), ("idle", 0x24): 1.0, ("fall after jump", 0x24): timed("fall"),
        ("idle_1 after jump", 0x24): 1.0} | {(what, 0x04): 1.0 for what in changes}


def test_a_body_with_no_clips_plays_garret4s_clips_as_timers():
    """Step 2.67 (X12): gargoylestone and tesla_tree have no clips, so a
    move kept the clip already playing: the statue's roll and attacks
    never started or ended on a clip. Step 2.89 (D239: one mechanism for
    garret4's clips): the bake gives such a body garret4's clips as
    timers, characters/<body>/g4/<clip>, exactly the ones X11's slot
    table names (every slot the player asks for that he has) and the
    attacks_anims columns he has, each with his length, none of his bone
    tracks (a 1-bone statue can't bind his ~60 bone indices) and his
    m_feet, m_grab and m_attacklevel tracks on those markers, added to
    its body, so its moves travel his root motion; since Step 2.127
    (AZ-562) its root bone's translation is its rest plus his m_feet over
    the drawn scale D wherever that leaves his origin (g4/climb_up_edge's
    y and z; none in g4/idle): the game places the model at the entity
    less m_feet unscaled and draws the bone x D, so held at its bind it
    was drawn 1.95 m under the floor at a ladder's top, and riding m_feet
    x 1 (Step 2.118c's dropped fix) (D - 1) x m_feet off the other way;
    gargoylestone at garret4's height, D 0.725. X12's hook on the attacks_anims
    loader's lookup (0x7E3F0) gives the player's species (flag 0x20) the
    baked timer, g4/<name>, for each column its body can't resolve (L2,
    the registry stubbed by name): roll_forward, attack_1. Another
    species' lookup, and a name garret4 has no clip for, stay -1."""
    from azurkit.tools.characters.retarget import ADDED_MARKERS, read_clip

    game = _swap("gargoylestone", size="garret4")
    built, characters = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    vanilla = _vanilla("gamedata/characters.xbr")
    garret4 = read_body(vanilla, "garret4")
    drawn = size_scale(vanilla, read_body(vanilla, "gargoylestone"))
    assert drawn == pytest.approx(0.725, abs=0.005)
    prefix = "characters/gargoylestone/g4/"
    keys = {(prefix + clip).casefold(): 1000 + i for i, clip in enumerate(garret4.clips)}
    got = {(name, flags): _attack_lookup(built, "gargoylestone", keys, name, flags)
           for name in ("roll_forward", "attack_1", "no_such_clip") for flags in (0x24, 0x04)}
    assert got == dict.fromkeys(got, -1) | {(name, 0x24): keys[prefix + name] for name in ("roll_forward", "attack_1")}

    table = resolve_va_to_file(built, trampoline_symbol_va(
        built, SLOTS_HOOK, SLOTS_TABLE, shim_source=SLOTS_SHIM.source_path()))
    names = built[table + 6 * 0x52:table + 6 * 0x52 + 2048]
    named = {names[at - 1:names.index(b"\0", at - 1)].decode()[3:]
             for at in struct.unpack_from("<82H", built, table) if at}
    anims = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
    named |= {anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(anims.col_names())} & set(
        garret4.clips)
    toc = parse_toc(characters)
    baked = {name[len(prefix):]: toc[i].file_offset for i, name in named_resources(characters).items()
             if name.casefold().startswith(prefix)}
    markers = read_body(characters, "gargoylestone").markers
    assert set(baked) == named and markers == ADDED_MARKERS
    rest = bone_records(characters, "gargoylestone")[0].t
    feet = garret4.markers.index("m_feet")
    for name, at in baked.items():
        mine, his = read_clip(characters, at), read_clip(vanilla, _clip(vanilla, f"characters/garret4/{name}")[0])
        rides = [(0, tr.comp, [(t, rest[tr.comp] + v / drawn, i / drawn, o if o > 3.4e38 else o / drawn)
                               for t, v, i, o in tr.keys], tr.modes)
                 for tr in his.markers if tr.target == feet and tr.comp <= 2 and any(abs(k[1]) > 1e-3 for k in tr.keys)]
        assert (mine.length, [(tr.target, tr.comp, [pytest.approx(k, rel=1e-6, abs=1e-6) for k in tr.keys], tr.modes)
                              for tr in mine.bones]) == (his.length, rides), name
        assert {(markers[tr.target], tr.comp): tr.keys for tr in mine.markers} == {
            (garret4.markers[tr.target], tr.comp): tr.keys for tr in his.markers
            if garret4.markers[tr.target] in markers}, name
    assert {tr.comp for tr in read_clip(characters, baked["climb_up_edge"]).bones} == {1, 2}   # y 1.364, z 2.269
    assert read_clip(characters, baked["idle"]).bones == ()


def test_a_farmer_swings_garret4s_attacks_on_its_rig_in_balanced():
    """Step 2.134a (the owner on town_child_1: "attacking is just using the
    model's running animation"; D337: the farmers swing their hoe as
    garret4 his staff): a townsperson has no attack clip, so
    substitutes' last rule gave every attack column its run. In Balanced
    a body the bake serves with no attack clip of its own (Loadout.borrowing) that
    holds a weapon (W20's hoe: the six farmers; the others swing the
    bare-hands kit since Step 2.159a, the next test)
    swings garret4's: W3 leaves every attacks_anims Anim vanilla, the
    bake adds his clip for each onto its rig (characters/<body>/g4/<Anim>,
    with bone tracks), and X12's ATTACK lookup (0x7E3F0) resolves each
    name the body lacks to that baked clip for the player's species (L2:
    attack_1 and the roll's roll_forward; another species, and a name
    garret4 has no clip for, stay -1); X3 gives each column his own box
    and window, as garret4's exact does (basic1 on in attack_1's own
    0.375-0.49 of the clip), and his Move end1 chains each (no W19).
    Skin only keeps its run in the columns its strings can't hold
    garret4's names for."""
    characters = _vanilla("gamedata/characters.xbr")
    game = _swap("town_male_farmer_1", sounds="garret4")
    built, grown = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    anims = [XbrDocument.from_bytes(c).keyed_section("attacks_anims")
             for c in (_vanilla("gamedata/config.xbr"), bytes(game["config.xbr"]))]
    played, chains = ([[a.find_cell(col, row, i).string_value if row == "Anim" else a.find_cell(col, row, i).double_value
                        for i, col in enumerate(a.col_names())] for a in anims] for row in ("Anim", "Move end1"))
    assert (played[1], chains[1]) == (played[0], chains[0])   # his Anims, and his chains (no W19)
    prefix = "characters/townspeople/male_farmer_1/g4/"
    toc, at = parse_toc(grown), {name.casefold(): i for i, name in named_resources(grown).items()}
    assert all(read_clip(grown, toc[at[(prefix + clip).casefold()]].file_offset).bones for clip in played[0])
    keys = {(prefix + clip).casefold(): 1000 + i for i, clip in enumerate(played[0])}
    got = {(name, flags): _attack_lookup(built, "townspeople/male_farmer_1", keys, name, flags)
           for name in ("attack_1", "roll_forward", "no_such_clip") for flags in (0x24, 0x04)}
    assert got == dict.fromkeys(got, -1) | {(name, 0x24): keys[prefix + name] for name in ("attack_1", "roll_forward")}
    length = read_body(characters, "garret4").length("attack_1")
    windows = damage_windows(characters, "garret4", "attack_1")
    start, end = windows[0].on / length, windows[-1].off / length
    assert [_x3_marker(built, 0, (f - 0.1) / 0.8)[1]
            for f in (start - 0.02, start + 0.005, end - 0.005, end + 0.02)] == [0.0, 1.0, 1.0, 0.0]


@pytest.mark.parametrize("species, body, source", [
    ("town_male_6", "townspeople/male_6", "townspeople/male_6"),
    ("town_female_4", "townspeople/female_4", "townspeople/female_1"),
    ("town_child_1", "townspeople/child_1", "townspeople/child_1")])
def test_a_weaponless_townsperson_punches_kicks_and_shoves_with_the_kits_clips(species, body, source):
    """Step 2.159a (D471: "townsfolk without weapons should not have
    balthazar's beam attack or life steal. instead, they should have
    interesting melee/hand attacks"; D472: a jab-cross-uppercut combo, a
    kick and a two-hand shove finisher, authored in Blender): in Balanced
    a townsperson the bake serves with no weapon (all but the six
    farmers, the test above) plays in each attack column the kit's clip
    for it (kit.json: basic1 jab, basic2 cross, basic3 upper, the
    finishers shove and kick, ...; no b/ or Balthazar clip), its family's
    clip (the townsmen's keyed on male_6, the townswomen's on female_1,
    the children's on child_1) baked onto its rig as t/<clip>, the roll
    keeping g4/roll_forward: each clip the kit's length, every bone the
    role maps pair turning within 1 degree of the kit's at 30 Hz, at
    Rate 1.0 with the move the whole clip (down's Move start 0.1 gone).
    X3's box serves each (L2; at the limb it strikes with since Step 2.195,
    the next test), on over the kit's window (the jab's ticks 4-7 of 12, the cross's 5-8 of
    13, the uppercut's 6-9 of 15, the shove's 10-13 of 20, the kick's
    8-11 of 18, the shim's box table), X13 fills every attack column's
    box to the feet but the throw's (right1, Step 2.159b: its own test
    file), and basic1-3 chain 4-7 ticks after their first hit
    (W19). town_female_4's vase rides her head x0.4 in every kit clip but the throw, as
    her own clips show it, and in garret4's clips baked onto her (her
    idle, walk and roll), so it never pops in or out with an attack;
    town_female_1's shows none."""
    from azurkit.tools.characters.retarget import Retarget, named_clip, qangle
    from azurkit.tools.characters._player_kit import carried as kit_carried, kit_document, kit_style

    vanilla = _vanilla("gamedata/characters.xbr")
    game = _swap(species, sounds="garret4")
    built, grown = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    anims = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
    columns = anims.col_names()
    kit = kit_document()
    picks = [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]
    assert picks == ["g4/roll_forward" if col == "roll forward" else "t/" + kit["columns"][col] for col in columns]
    kits = [i for i, col in enumerate(columns) if col != "roll forward"]
    assert {(anims.find_cell(columns[i], "Rate", i).double_value, move_window(anims, i)) for i in kits} == {
        (1.0, (0.0, 1.0))}
    style = kit_style(vanilla, read_body(vanilla, body))
    assert style.source == source
    rt = Retarget(vanilla, body, lender=source, grow=False)
    rig = Rig.read(grown, body)
    names = [b.name for b in rig.bones]
    worst = 0.0
    for name, theirs in style.clips(vanilla).items():
        clip = named_clip(grown, body, "t/" + name)
        assert clip.length == theirs.length == pytest.approx(kit["clips"][name]["ticks"] / 30), name
        for i in range(kit["clips"][name]["ticks"] + 1):
            t = min(i / 30, clip.length)
            lent, its = pose(rt.garret4, theirs, t), pose(rt.target, clip, t)
            worst = max(worst, max(qangle(its[k], qmul(qmul(lent[g], qinv(rt.garret4.world[g])), rt.rest(k)))
                                   for k, g in rt.source.items()))
        if "vase_joint" in names and name != "throw":   # the vase: x0.4 on her head where her own clips show it,
            # else hidden (the throw takes it: tests/test_player_throw.py)
            vase, head = names.index("vase_joint"), names.index("head")
            scale = {tr.keys[0][1] for tr in clip.bones if tr.target == vase and tr.comp >= 7}
            assert scale == ({_f32(0.4)} if species == "town_female_4" else {0.0}), name
            if species == "town_female_4":
                assert all(abs(math.dist((at := origins(rig, clip, t))[vase], at[head]) - 0.125) < 0.002
                           for t in (0.0, clip.length / 2, clip.length)), name
    if species == "town_female_4":
        for name in ("g4/idle", "g4/walk", "g4/roll_forward"):
            clip = named_clip(grown, body, name)
            assert {tr.keys[0][1] for tr in clip.bones if tr.target == vase and tr.comp >= 7} == {_f32(0.4)}, name
    assert worst < 1.0 and kit_carried(vanilla, read_body(vanilla, "townspeople/female_1"), source) == {}
    for col in ("basic1", "basic2", "basic3", "finish", "finish2"):
        i, clip = columns.index(col), kit["clips"][kit["columns"][col]]
        on, off = (tick / clip["ticks"] for tick in clip["hit"])
        assert [_x3_marker(built, i, (f - 0.1) / 0.8)[1]
                for f in (on - 0.02, on + 0.01, off - 0.01, off + 0.02)] == [0.0, 1.0, 1.0, 0.0], col
    assert round(_param(built, ATTACK_BOX_HOOK, ATTACK_BOX_SHIM, "_player_attack_ground_mask")) == sum(
        1 << i for i in kits if picks[i] != "t/throw")   # the throw swings no box (Step 2.159b)
    for col in ("basic1", "basic2", "basic3"):
        i, clip = columns.index(col), kit["clips"][kit["columns"][col]]
        chain = (anims.find_cell(col, "Move end1", i).double_value - anims.find_cell(col, "Anim start", i).double_value) / (
            anims.find_cell(col, "Anim end", i).double_value - anims.find_cell(col, "Anim start", i).double_value)
        assert 4 <= chain * clip["ticks"] - clip["hit"][0] <= 7, col


@pytest.mark.parametrize("species, kw, reach", [
    ("town_male_6", {}, (0.91, 1.03, 0.68, 0.82, 1.31)),
    ("town_female_4", {}, (0.82, 0.92, 0.68, 0.77, 1.31)),
    ("town_child_1", {}, (0.74, 0.82, 0.66, 0.69, 0.91)),
    ("keylord", {"weapon": "bare_hands"}, (1.08, 1.12, 1.08, 1.08, 1.15))])
def test_bare_hands_reach_a_fist_or_a_foot_past_the_limb_well_short_of_a_staff(species, kw, reach):
    """AZ-760 (Step 2.195, D763; the owner in the X.80 play: "the range of
    the jabs for the melee attacks is too long, make it shorter - having
    range variance with weapons makes them more diverse and interesting"):
    X3 put garret4's staff box (3.05 m long, 1.23 m ahead) at the right
    hand for every kit clip, so a townsman's jab reached 2.97 m ahead and
    his cross 3.57 m, past garret4's staff (basic1, 2.76 m). Each kit
    clip's box is now its own, fixed in the model (L2, X3's tick on each
    build; X3's anchor the feet): it bounds the limb the clip strikes with
    (the jab's and the uppercut's left fist, the cross's right, the
    shove's two palms, the kick's right foot) through its window, grown a
    fist's or a foot's length every way, at the body's size, each drawn
    x1.15: the jab, cross, uppercut, shove and kick reach (m ahead of the
    feet) the townsman's 0.91, 1.03, 0.68, 0.82 and 1.31, the
    townswoman's 0.82, 0.92, 0.68, 0.77 and 1.31 and the child's 0.74,
    0.82, 0.66, 0.69 and 0.91: each under half a staff's swing, the kick
    the farthest. Each also reaches past W19's contact front (0.5 m x the
    drawn scale, at least 1), where an enemy walked up stops: the child's
    uppercut (0.55 by its limb) and keylord's (drawn x2, front 1.0 m)
    jab, uppercut, shove and kick end a fist or a foot past it (the
    skeptic of Step 2.195)."""
    from azurkit.tools.characters._player_kit import kit_document

    game = _swap(species, sounds="garret4", **kw)
    built, config = bytes(game["default.xbe"]), XbrDocument.from_bytes(bytes(game["config.xbr"]))
    columns = config.keyed_section("attacks_anims").col_names()
    drawn = config.keyed_section("critters_engine").find_cell("garret4", "scale", None).double_value
    kit = kit_document()
    assert _x3_param(built, "bone") == -1
    got = []
    for col in ("basic1", "basic2", "basic3", "finish", "finish2"):
        clip = kit["clips"][kit["columns"][col]]
        (length, on), _, _, box = _x3_tick(built, columns.index(col), (sum(clip["hit"]) / 2 / clip["ticks"] - 0.1) / 0.8,
                                           scale=drawn, extents=True)
        assert on == 1.0, col
        got.append(drawn * (box[1] + box[4] * length))   # the far face, m ahead of the feet
    assert got == pytest.approx(reach, abs=0.01) and max(got) == got[4] < GARRET4_FORWARD / 2
    assert min(got) > PLAYER_RADIUS * max(drawn, 1.0) + 0.05


@pytest.mark.parametrize("species, body, mapped, hip", [
    ("balthazar", "balthazar_airship", 67, 1.112), ("keylord", "keylord", 44, 0.439),
    ("fire_elemental", "fire_elemental", 53, 1.123), ("water_elemental", "water_elemental", 53, 0.872),
    ("air_elemental", "air_elemental", 53, 1.557), ("town_female_1", "townspeople/female_1", 66, 0.964),
    ("town_child_1", "townspeople/child_1", 60, 0.667), ("town_male_6", "townspeople/male_6", 68, 1.0),
    ("kingkong", "golem", 35, 1.208)])
def test_garret4s_clips_baked_onto_a_humanoid_rig_move_each_mapped_bone_as_his(species, body, mapped, hip):
    """Step 2.87 (D226; the owner: "also try and make humanoids work"): a
    clip writes local rotations in its body's joint frames, so garret4's
    clips can't play on another rig as they are (Balthazar's arm names are
    mirrored and his joints bind up to 180 degrees off). One row per rig
    retarget.MAPS serves (Step 2.88: keylord's, which overlord wears too,
    each elemental's, a townswoman's and a child's, whose hips sit at two
    thirds of his; Step 2.89, D239: a townsman's, garret4's own rig, which
    X12 had played his clips on by a bone and marker name remap at run
    time): under a recipe's anims garret4 the build
    bakes garret4's clips onto the body's rig as characters/<body>/g4/<clip>,
    exactly the ones X11's slot table and attacks_anims name (no more, no
    fewer); each, read back from the build's characters.xbr and posed with
    the engine model (rest values, Hermite tracks, JO x q x RA, 0xCA470:
    retarget.pose), turns every bone the role map gives a garret4 bone from
    its re-posed bind within 1 degree of how garret4's own clip turns his
    bone from his bind, at 30 Hz; its root's height over his m_feet (where
    the model is placed, so a hoist ends with its feet on the ledge) is
    his times the hip-height ratio (its thighs' bind height over his), and
    it travels as his across; it has his length, and his marker tracks on
    the markers it has by name, those of m_feet, m_grab and m_attacklevel
    it lacks added to its body, an own-build overlay's after them (W23;
    the air elemental's, Step 2.155) (the roll's horizontal ones drawn about
    the centre at a drawn scale other than 1: Step 2.133,
    test_a_body_drawn_at_a_size_rolls_about_its_centre). Each row: how
    many of the body's bones the role map gives a garret4 bone, and its
    hip-height ratio. Step 2.134a (D340, the owner: kingkong "looks like
    it has arms, but is not using them"; D355): kingkong's golem rig, its
    side mid-name and no head (left unmapped on purpose), its root lifted
    by its LIFTS entry (0.07 model units) so its feet split garret4's
    jump's cuts from its own idle; and (D420, the owner: "Garret's roll,
    lifted"; AZ-629) a clip retarget.FLOORED names for the body, the
    golem's roll, raised on top of that through the clip so no bone but a
    hidden prop's goes under the floor (its tuck put the golem's hands 2.20
    model units under it, 10.6 m at kingkong's own size), at 120 Hz within
    0.01 units."""
    from azurkit.tools.characters.retarget import (
        ADDED_MARKERS, LIFTS, Retarget, evaluate, pose, qangle, qinv, qmul, read_clip)

    game = _swap(species)
    built, characters = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    vanilla = _vanilla("gamedata/characters.xbr")
    table = resolve_va_to_file(built, trampoline_symbol_va(
        built, SLOTS_HOOK, SLOTS_TABLE, shim_source=SLOTS_SHIM.source_path()))
    names = built[table + 6 * 0x52:table + 6 * 0x52 + 2048]
    named = {names[at - 1:names.index(b"\0", at - 1)].decode()
             for at in struct.unpack_from("<82H", built, table) if at}
    surfaced = any(n.startswith("s/") for n in named)   # W27's swim copies of baked clips (Step 2.134b)
    named = {n.removeprefix("s/") for n in named}
    anims = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
    own = set(read_body(vanilla, body).clips)   # an Anim the body lacks plays baked (X12's ATTACK, Step 2.134a)
    named |= {a if "/" in a or a in own else "g4/" + a
              for a in (anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(anims.col_names()))}
    prefix = f"characters/{body}/"
    toc = parse_toc(characters)
    baked = {name[len(prefix):]: toc[i].file_offset for i, name in named_resources(characters).items()
             if name.startswith(prefix + "g4/")}
    assert set(baked) == {name for name in named if name.startswith("g4/")} and baked

    rt = Retarget(vanilla, body, lift=LIFTS.get(body, 0.0))
    garret4, rig = rt.garret4, rt.target
    grown = (*rig.markers, *(m for m in ADDED_MARKERS if m not in rig.markers))
    worn = overlay(species)   # W23's markers grown after the bake and W27 (the air elemental's, Step 2.155: D434)
    assert read_body(characters, body).markers == (*grown, *(("m_root", "m_eye") if surfaced else ()),
                                                   *(worn.markers if worn is not None else ()))
    k_root = rt.root
    g_root = rt.source[k_root]
    worst = 0.0
    for name, at in sorted(baked.items()):
        theirs = read_clip(vanilla, _clip(vanilla, f"characters/garret4/{name[3:]}")[0])
        mine = read_clip(characters, at)
        assert mine.length == theirs.length, name
        across = (0, 1) if name == "g4/roll_forward" else ()   # drawn about the centre (AZ-608)
        by_name = {(garret4.markers[tr.target], tr.comp): tr.keys for tr in theirs.markers
                   if garret4.markers[tr.target] in grown}
        assert {(grown[tr.target], tr.comp): tr.keys for tr in mine.markers
                if tr.comp not in across or grown[tr.target] == "m_feet"} == {
            key: keys for key, keys in by_name.items() if key[1] not in across or key[0] == "m_feet"}, name
        root = {tr.comp: tr.keys for tr in theirs.bones if tr.target == g_root and tr.comp <= 2}
        mine_root = {tr.comp: tr.keys for tr in mine.bones if tr.target == k_root and tr.comp <= 2}
        feet = next((tr.keys for tr in theirs.markers
                     if garret4.markers[tr.target].casefold() == "m_feet" and tr.comp == 2), None)
        assert set(mine_root) == set(root) | ({2} if feet or rt.lift else set()), name
        lifted = name[3:] in retarget.FLOORED.get(body, ())
        n = max(2, int(mine.length * 30) + 1)
        for i in range(n):
            t = mine.length * i / (n - 1)
            his, its = pose(garret4, theirs, t), pose(rig, mine, t)
            for k, g in rt.source.items():
                want = qmul(qmul(his[g], qinv(garret4.world[g])), rt.rest(k))
                worst = max(worst, qangle(its[k], want))
            f = (0.0, 0.0, evaluate(feet, t) if feet else 0.0)
            for comp in set(mine_root) - set(across):
                his = evaluate(root[comp], t) if comp in root else garret4.bones[g_root].t[comp]
                moved = his - garret4.bones[g_root].t[comp] - f[comp]
                want = (rig.bones[k_root].t[comp] + (rt.lift if comp == 2 else 0.0)
                        + moved * (rt.hip if comp == 2 else 1.0))
                if lifted and comp == 2:   # raised off the floor (D420)
                    assert evaluate(mine_root[comp], t) - f[comp] >= want - 1e-4, name
                else:
                    assert evaluate(mine_root[comp], t) - f[comp] == pytest.approx(want, abs=1e-4), name
        if lifted:
            shown = [k for k in range(len(rig.bones)) if k not in rt.props]
            lows = [min(at[k][2] for k in shown) - (evaluate(feet, t) if feet else 0.0)
                    for t in (mine.length * j / 140 for j in range(141)) for at in [origins(rig, mine, t)]]
            assert min(lows) > -0.01, name
    assert worst < 1.0
    assert (len(rt.source), round(rt.hip, 3)) == (mapped, hip)


def test_a_farmers_hoe_rides_garret4s_staff_its_effects_at_its_ends_and_its_hits_to_its_tip():
    """Step 2.134b (W26; D337, the owner: "make it look like they are
    using it visually, like how garret uses his axion?"; D338: the
    effects "at the end of the weapon", every body that holds one; D339:
    "as long reach as it looks like the hoe should have"): each townsman
    farmer's hoe is a group of its own mesh (276 vertices, 1.878 units)
    skinned to root_joint alone (only the six farmers have such a prop,
    their default weapon: test_player_weapons). W20 rode it on
    the right hand, so it missed garret4's staff wherever the staff turns
    or slides in his hands. W26 re-parents joint74 to right_hand and
    joint97 under it, skins the hoe to joint74 with its blade tip at the
    origin and its handle down -y (1.878), and keys joint74 in every
    baked clip so the tip rides the hoe's over (0.735) past garret4's
    m_stafftop along his staff, its +y the staff's axis (2 mm, half a
    degree), held in the hand as his tip is in his (the centred roll
    too: the judge's A1), turned up about his grip where it would go under
    the floor (W41, Step 2.207); W6 binds the staff fx to joint74/joint97 (the parametrized
    staff fx test); in Balanced X3's rows the box around the hoe drawn
    x1.15 (Step 2.195b, D767; finish 4.54 m ahead, 4.38 grown from
    garret4's box before), the logic reads its idle swings' 3.098 m
    (AZ-566; from the body since Step 2.197b, AZ-766: 3.927 its clip's)
    and the balance 0.8 (D228's B x D389's k; garret4's move it is
    weighed against read from the body too, the review's F1); Skin only keeps
    garret4's rows and numbers (his sweep1's 2.953 m)."""
    characters = _vanilla("gamedata/characters.xbr")
    over = weapons()["farmers_hoe"].prop.over
    name = "townspeople/male_farmer_1"
    logics = {mode: AttackLogic() for mode in ("own", "garret4")}
    games = {mode: _swap("town_male_farmer_1", mode=mode, sounds="garret4", logic=logics[mode]) for mode in logics}
    built = bytes(games["own"]["characters.xbr"])
    rig, g4 = Rig.read(built, name), Rig.read(characters, "garret4")
    bones = [b.name for b in rig.bones]
    hand, carrier, end = (bones.index(n) for n in ("right_hand", "joint74", "joint97"))
    assert (rig.bones[carrier].parent, rig.bones[end].parent) == (hand, carrier)
    was, now = mesh_groups(characters, name), mesh_groups(built, name)
    k, = [i for i, g in enumerate(was) if g.bones == (0,)]
    assert [g.bones for g in now] == [(carrier,) if i == k else g.bones for i, g in enumerate(was)]
    assert all(built[n.vertices:n.vertices + VERTEX_SIZE * n.count] == characters[w.vertices:w.vertices + VERTEX_SIZE * w.count]
               for i, (w, n) in enumerate(zip(was, now)) if i != k)
    m = inverse_binds(built, name)[carrier]
    local = [[sum(p[i] * m[4 * i + j] for i in range(3)) + m[12 + j] for j in range(3)]
             for p in (struct.unpack_from("<3f", built, now[k].vertices + VERTEX_SIZE * j) for j in range(now[k].count))]
    assert (min(p[1] for p in local), max(p[1] for p in local)) == (pytest.approx(-1.878, abs=1e-3), pytest.approx(0.0, abs=1e-3))

    g_names = [b.name for b in g4.bones]
    top, bottom, his_hand = (g_names.index(n) for n in ("m_stafftop", "m_staffbottom", "right_hand"))
    k_turn = _staff_hold(characters, weapons()["farmers_hoe"].style, over)[3]
    hull, long = pw._prop_hull(characters, weapons()["farmers_hoe"].prop)
    for clip in ("attack_1", "attack_10", "attack_14", "smash_attack_1", "elemental_attack", "roll_forward"):
        mine = read_clip(built, _clip(built, f"characters/{name}/g4/{clip}".casefold())[0])
        his = read_clip(characters, _clip(characters, f"characters/garret4/{clip}")[0])
        for t in sorted({key[0] for tr in mine.bones if tr.target == carrier for key in tr.keys})[::3]:
            at, theirs = origins(rig, mine, t), origins(g4, his, t)
            axis = [a - b for a, b in zip(theirs[top], theirs[bottom])]
            axis = [c / math.sqrt(sum(a * a for a in axis)) for c in axis]
            tip = [a + over * c for a, c in zip(theirs[top], axis)]
            w_rot, g_rot = pose(rig, mine, t), pose(g4, his, t)   # W41 (Step 2.207): turned up about his grip where
            lift = pw._floor_lift(tip, qmul(g_rot[top], k_turn), theirs[his_hand], hull, long,   # it'd go under
                                  *pw._up_and_floor(theirs[his_hand], 1.0, at[hand], qmul(w_rot[hand], qinv(g_rot[his_hand]))))
            if lift is not None:
                tip, axis = pw._lifted(lift, tuple(tip), (0.0, 0.0, 0.0, 1.0))[0], _turn(lift[0], axis)
            up = _turn(pose(rig, mine, t)[carrier], (0.0, 1.0, 0.0))
            held = [c - h for c, h in zip(at[carrier], at[hand])]   # in the hand, wherever the bake puts it
            assert math.dist(held, [c - h for c, h in zip(tip, theirs[his_hand])]) < 2e-3, (clip, t)
            assert math.degrees(math.acos(min(1.0, sum(a * b for a, b in zip(up, axis))))) < 0.5, (clip, t)

    anims = XbrDocument.from_bytes(_vanilla("gamedata/config.xbr")).keyed_section("attacks_anims")
    columns = anims.col_names()
    clips = [anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns)]

    def rows(mode: str) -> list[tuple[float, ...]]:
        xbe = bytes(games[mode]["default.xbe"])
        span, = [s for s in trampoline_shim_data(xbe, DAMAGE_MARKER, shim_source=DAMAGE_MARKER_SHIM.source_path())
                 if s[1] - s[0] == BOXES_SIZE]
        at = resolve_va_to_file(xbe, span[0]) + 4
        return [BOX.unpack_from(xbe, at + BOX.size * i) for i in range(len(columns))]
    finish = rows("own")[columns.index("finish")]
    assert forward([c - e / 2 for c, e in zip(finish[2:5], finish[5:8])],
                   [c + e / 2 for c, e in zip(finish[2:5], finish[5:8])]) == pytest.approx(4.54, abs=5e-3)
    assert rows("garret4") == [pytest.approx(r, abs=1e-6) for r in garret4_boxes(characters, clips)]
    assert {mode: (round(lg.reach, 3), round(lg.damage, 3)) for mode, lg in logics.items()} == {
        "own": (3.098, 0.8), "garret4": (2.953, 1.0)}   # own: its boxes from the body (AZ-766, Step 2.197b)


def test_a_baked_clip_hides_each_prop_on_a_root_of_its_own():
    """Step 2.88b (sitting 2.75a rows 6, 113, 114: town_female_4's vase
    sat round her hips over her legs in own and garret4 modes): a bone no
    mapped bone is above (the townswomen's vase_joint, a second root,
    which town_female_4's own clips carry on her head at x0.4 and the
    others' at x0; the water elemental's blob chain, x0 but mid-throw)
    gets no motion from the bake, so it held its bind at full size (the
    vase's the model's origin, the blob's the T-pose left hand). Every
    clip baked onto a body (garret4's idle here) scales each of its props
    to zero, all three axes for the clip's whole length, and no other
    bone (the blob rides the left hand at x0 outside its throws, so
    hidden it looks as following the hand would). One row per body with
    props, every other body none."""
    from azurkit.tools.characters.retarget import Retarget, bake_clip, read_clip

    characters = _vanilla("gamedata/characters.xbr")
    idle = read_clip(characters, _clip(characters, "characters/garret4/idle")[0])
    for body in BAKED_BODIES:
        rt = Retarget(characters, body)
        assert tuple(rt.target.bones[k].name for k in rt.props) == BAKED_PROPS.get(body, ()), body
        scales = {(tr.target, tr.comp): tr.keys for tr in bake_clip(rt, idle).bones if tr.comp >= 7}
        assert scales == {(k, comp): ((0.0, 0.0, 0.0, 0.0), (idle.length, 0.0, 0.0, 0.0))
                          for k in rt.props for comp in (7, 8, 9)}, body


@pytest.mark.parametrize("mode", MODES)
def test_a_baked_body_builds_in_each_mode_and_rolls_on_garret4s_baked_roll(mode):
    """Step 2.87 on the gameplay modes (Steps 2.65, 2.73a; D238): the bake
    serves a recipe's anims garret4, the mode's rule in garret4's
    exact and own body, so a default Balthazar build there grows
    characters.xbr and index.xbr and its roll plays garret4's roll_forward
    baked onto his rig, g4/roll_forward. Every lookup of a pick on the
    body reads a g4/ pick as garret4's clip (source_clip; on the body the
    roll's length lookup raised and the build failed): W5 gives the roll
    the Rate that plays his clip in his time, W3 and player-models
    --attacks agree on every column's clip and length, and with m_grab
    grown into his body neither X4 nor X9's climb lands, only X9's two
    zipline landings, which hang his top at the cable (Step 2.118, AZ-536:
    X' under 1 at x1). garret4 mode adds W17's copy of his attack_2, p/0,
    which the listing names as attack_2 (Step 2.75e); own mode plays
    attack_2 itself (X37, Step 2.135)."""
    characters = _vanilla("gamedata/characters.xbr")
    config = _vanilla("gamedata/config.xbr")
    game = _swap("balthazar", mode=mode)
    built, vanilla = bytes(game["default.xbe"]), _vanilla("default.xbe")
    anims = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
    columns = anims.col_names()
    listed = attacks(config, characters, "balthazar", mode)
    roll = columns.index("roll forward")
    rate = XbrDocument.from_bytes(config).keyed_section("attacks_anims").find_cell(
        "roll forward", "Rate", roll).double_value
    g4 = read_body(characters, "garret4").length("roll_forward")
    hooks = {ROLL_HOOK_VA, *(hook.va for hook in CLIMB_HOOKS)}

    prefix = "characters/balthazar_airship/g4/"
    g4_clips = {name[len(prefix):] for name in named_resources(bytes(game["characters.xbr"])).values()
                if name.startswith(prefix)}
    victories = {f"victory_{v}" for v in range(1, 7)}
    assert victories < g4_clips
    assert (read_body(bytes(game["characters.xbr"]), "balthazar_airship").markers
            != read_body(characters, "balthazar_airship").markers)
    assert [{"p/0": "attack_2"}.get(name, name) for name in (
        anims.find_cell(col, "Anim", i).string_value for i, col in enumerate(columns))] == [a.clip for a in listed]
    assert (listed[roll].clip, listed[roll].length, anims.find_cell("roll forward", "Rate", roll).double_value) == (
        "g4/roll_forward", g4, standard_rate(rate, g4, g4))
    assert {va for va in hooks if built[va_to_file(va):va_to_file(va) + 5]
            != vanilla[va_to_file(va):va_to_file(va) + 5]} == {0x8AB32, 0x8A4E3}


@pytest.mark.parametrize("species, kw, body, drawn, column, source", [
    ("keylord", {}, "keylord", 2.0, "roll forward", "garret4/roll_forward"),
    ("keylord", {"model_scale": 2.0}, "keylord", 4.0, "roll forward", "garret4/roll_forward"),
    ("town_female_4", {}, "townspeople/female_4", 1.15, "roll forward", "garret4/roll_forward"),
    ("garret4", {"model_scale": 2.0}, "garret4", 2.0, "roll forward", "garret4/roll_forward"),
    ("balthazar", {}, "balthazar_airship", 1.0, "roll forward", "garret4/roll_forward"),
    ("keylord", {}, "keylord", 2.0, "basic1", "keylord/attack_1"),
    ("keylord", {"mode": "garret4", "model_scale": 2.0}, "keylord", 2.0, "basic3", "garret4/attack_3"),
    ("garret4", {"model_scale": 2.0}, "garret4", 2.0, "basic3", "garret4/attack_3")])
def test_a_body_drawn_at_a_size_rolls_and_lunges_about_its_centre(species, kw, body, drawn, column, source):
    """AZ-608 (Step 2.133, D330; the owner on keylord own: "the rolls feel
    further than garret's") and AZ-623 (Step 2.175): the game places the
    model at the centre less the clip's m_feet, unscaled (0x42E40), and
    draws its bones and markers x D, so through garret4's roll_forward
    (m_feet 0 -> 4.07 m forward) the drawn body led its centre by (D - 1)
    x m_feet: 4.07 m on keylord own (D 2) and garret4 x2 at the roll's
    end, 0.61 m on town_female_4 (D 1.15), 12.2 m on keylord x2 (D 4),
    whose camera then passed it (AZ-616; sitting 2.133 R1, R5), and an
    attack whose clip moves m_feet led it the same way, then slid back
    over its exit: keylord's own attack_1 0.16 m at its own D 2 (sitting
    2.133b's LG-KL2 at D 4: 0.48 m), garret4's attack_3 0.78 m at D 2.
    Read back from each build's characters.xbr, the clip the column plays
    (the bake's g4/ clip; a copy of the body's own, c/0, or of garret4's
    at his size, p/roll and c/0) keeps its m_feet, so it travels as far,
    and at 30 Hz through it the drawn root and every marker the clip
    moves sit off the centre horizontally D times where the source's do
    at x1 (the pose about the centre, x D), but its damage markers keep
    the source's tracks (its boxes hit where the build's reach reads them,
    D x the clip's from where it starts); at D 1 the bake is as before."""
    from azurkit.tools.characters.retarget import Retarget, evaluate

    game = _swap(species, **kw)
    vanilla = _vanilla("gamedata/characters.xbr")
    characters = bytes(game["characters.xbr"])
    anims = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("attacks_anims")
    anim = anims.find_cell(column, "Anim", anims.col_names().index(column)).string_value
    key = f"characters/{body}/{anim}".casefold()
    if key not in {n.casefold() for n in named_resources(characters).values()}:
        key = f"characters/{body}/g4/{anim}".casefold()   # a borrowing townsperson's: X12's g4/ (Step 2.134a)
    if drawn != 1.0:
        assert key != f"characters/{source}".casefold()   # a copy, never the body's own clip
    mine = read_clip(characters, _clip(characters, key)[0])
    owner = source.rsplit("/", 1)[0]
    his = read_clip(vanilla, _clip(vanilla, f"characters/{source}")[0])
    rig, g4 = Rig.read(characters, body), Rig.read(vanilla, owner)
    root = 0 if body == "garret4" else Retarget(vanilla, body).root
    src_root = 0 if owner == "garret4" else root
    markers = read_body(characters, body).markers
    baked = set(markers) - ({"m_root", "m_eye"} - set(read_body(vanilla, body).markers))   # W27's: after B (Step 2.134b)

    def tracks(clip, names, k: int) -> dict:
        return {("root", tr.comp): tr.keys for tr in clip.bones if tr.target == k and tr.comp <= 1} | {
            (names[tr.target], tr.comp): tr.keys for tr in clip.markers if tr.comp <= 1}

    ours, theirs = tracks(mine, markers, root), tracks(his, g4.markers, src_root)
    kept = {"m_feet", *(DAMAGE_MARKERS if column != "roll forward" else ())}   # the root motion, an attack's boxes
    assert {c: ours[c] for c in ours if c[0] in kept} == {c: theirs[c] for c in theirs if c[0] in kept and c[0] in baked}
    assert set(ours) == {("root", 0), ("root", 1)} | {c for c in theirs if c[0] != "root" and c[0] in baked}

    def value(keys, t: float, rest: float = 0.0) -> float:
        return evaluate(keys, t) if keys else rest

    for i in range(int(his.length * 30) + 1):
        t = i / 30
        for (name, comp), keys in ours.items():
            if name in kept:
                continue
            feet = value(theirs.get(("m_feet", comp)), t)
            rest = g4.bones[src_root].t[comp]
            x1 = (value(theirs.get((name, comp)), t, rest) - rest + rig.bones[root].t[comp] if name == "root"
                  else value(theirs[name, comp], t))
            assert -feet + drawn * value(keys, t) == pytest.approx(drawn * (x1 - feet), abs=1e-4), (name, comp, t)


def test_a_body_without_garret4s_staff_never_sweeps_one_against_the_walls():
    """AZ-441 (Step 2.75d): while an attack move plays (state 0x100) and
    the body's ``m_attacklevel`` is up, the staff-hits-wall sweep 0x8C8A0
    casts garret4's ``staff_center2slide`` against the level, and a hit
    freezes the clip and clears 0x100 with no damage. The bake gave every
    body it serves garret4's ``m_attacklevel`` and its tracks (Step 2.87),
    and water_lizardX (sleeth_x) has its own, but no body but garret4's
    has the bone, so the sweep cast a staff of stale stack bytes: sitting
    2.75c's garret4-mode basic1 ended after 4-5 ticks on every press on
    the townsfolk, and at times on Balthazar and keylord. X17 makes the
    sweep's switch, the only reader of that cvar, default to off on such
    a body; vanilla keeps it on, and so does a body none of whose clips
    raises the marker past the gate, whose sweep never runs (firedrake's
    own; keylord's and Balthazar's own-mode goldens pin the bake's)."""
    assert _staff_hits_walls(_vanilla("default.xbe")) == 1
    for species, mode, on in (("town_female_1", "garret4", 0), ("sleeth_x", "own", 0),
                              ("firedrake", "own", 1)):
        assert _staff_hits_walls(bytes(_swap(species, mode=mode)["default.xbe"])) == on, species


def test_a_body_without_a_usable_head_marker_aims_the_camera_at_garret4s_share_of_its_top_not_its_feet():
    """AZ-304's camera half (D128): the cameras aim at a critter's camera
    point (its vtable slot +0xB0, 0x41F40, which only the cameras call):
    its body's m_head marker, looked up by exact name with the CALL
    0xCB2A0 at 0x41F67 (ECX the anim object, EAX the out vector, the name
    on the stack, RET 4), turned into the world and scaled by +0x188. A
    body without m_head gives zeros, so the camera aimed at the critter's
    feet: of the usable bodies only garret4's, balthazar_airship's and
    fire_elemental's have one (fire_elemental's rests at 0), and
    guard_air's body, which rises to 5.58 m, hung above the frame with
    only its tail showing (xemu sitting modelswap3). Its build hooks that
    CALL (L1 well formed): for the player's species (flag 0x20, S+0x64)
    the point is garret4's share of the body's mesh top (Step 2.107, D280:
    his m_head over his mesh's top, 0.9954, where Step 2.23c took the top
    bone); any other critter looks its marker up as the game does. A body
    whose m_head rests at half its top or higher (balthazar) keeps the
    vanilla CALL; fire_elemental's gets X8."""
    vanilla = _vanilla("default.xbe")
    built = bytes(_swap("guard_air")["default.xbe"])
    at = va_to_file(0x41F67)
    target = 0x41F6C + struct.unpack_from("<i", built, at + 1)[0]
    _, sections = parse_xbe_sections(vanilla)
    assert built[at] == 0xE8 and not any(
        s["vaddr"] <= target < s["vaddr"] + s["vsize"] for s in sections)
    assert l1.check(vanilla, built) == []
    (x, y, z), returned = _camera_point(built, 0x24)
    assert (x, y, returned) == (0.0, 0.0, True) and z == pytest.approx(0.99535 * 5.5763, abs=0.001)
    assert _camera_point(built, 0x04) == ((0.0, 0.0, 0.0), True)                  # not the player
    assert _camera_point(built, 0x04, (0.5, 0.25, 2.0)) == ((0.5, 0.25, 2.0), True)
    assert bytes(_swap("balthazar")["default.xbe"])[at:at + 5] == vanilla[at:at + 5]
    assert verify_trampoline_patch(bytes(_swap("fire_elemental", sounds="garret4")["default.xbe"]),
                                   EYE_HOOK) == "applied"


def test_the_camera_point_rides_a_body_drawn_through_a_clips_m_feet():
    """AZ-609 (Step 2.133, D330; the owner on keylord own: "the camera is
    not following keylord as it rolls"): through a clip whose ``m_feet``
    moves (the roll, an attack's lunge) the drawn origin is the centre
    less that m_feet (0x42E40, unscaled, the node +0x1F8 named "m_feet"),
    so X8's (0, 0, top) trailed the roll by it. On the land path with the
    node m_feet the point adds the blended pose's m_feet x and y, which
    0xCB2A0 gives by name for the critter's anim object (+0x17C), over
    the critter's drawn scale D (+0x188; AZ-616: undivided it rode a roll
    still drawn (D - 1) x m_feet ahead, and the camera reached keylord x2's
    origin, which then wasn't drawn): 0x41F40 turns the point by the
    model's matrix, the origin less m_feet and x D, so it is the centre
    plus D x top, where the roll is drawn about since AZ-608. On keylord
    own's build (X8, baked) its m_feet at (0.4, 3, 0.2) puts the point at
    (0.2, 1.5, top) at D 2 and (0.1, 0.75, top) at D 4; on a ladder (node
    m_grab) and swimming it keeps its land and swim points, and another
    critter, and a body without the marker, are as before."""
    built = bytes(_swap("keylord", sounds="garret4")["default.xbe"])
    top = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, EYE_HOOK, "_player_model_eye_height", shim_source=EYE_SHIM.source_path())))[0]
    feet = (0.4, 3.0, 0.2)
    land, land4, swim = (0, 50.0, 2.0, 0.0), (0, 50.0, 4.0, 0.0), (6, 1.0, 2.0, 0.0)
    assert [p for p, _ in _camera_points(built, 0x24, rows=(land, land4, swim), feet=feet)] == [
        pytest.approx((0.2, 1.5, top), abs=1e-6), pytest.approx((0.1, 0.75, top), abs=1e-6),
        (0.0, 0.0, pytest.approx(top, abs=1e-6))]
    assert _camera_points(built, 0x24, rows=(land,), feet=feet, node="m_grab")[0] == (
        (0.0, 0.0, pytest.approx(top, abs=1e-6)), True)
    assert _camera_points(built, 0x04, rows=(land,), feet=feet)[0] == ((0.0, 0.0, 0.0), True)   # not the player
    assert _camera_points(built, 0x24, rows=(land,))[0] == ((0.0, 0.0, pytest.approx(top, abs=1e-6)), True)


def test_a_tall_camera_point_keeps_its_distance_where_a_line_from_garret4s_eye_height_is_clear():
    """AZ-520's zipline part (Step 2.104, X19): the level camera's 0x80FB0
    sweeps from the point it aims at to its wanted place (collision_sweep,
    0x60870, the CALL at 0x810F3) and pulls in to a hit, and a tall body's
    point (X8's: golem own 1.80 m above garret4's 1.9925 m eye then)
    hit f3's zipline beam garret4's line passes under, so the camera sat
    0.6-0.7 m from the point (sitting 2.103's row C). X19 (L2, golem's
    build, the sweep stubbed: it hits from above z 4.5): on a hit for the
    player, not swimming, it sweeps again from the point lowered by the
    build's lift along the line from the body's centre (+0x15C), never
    below it, to the same place, into a record of its own; clear, AL 0
    and the caller's record keeps the first sweep's; hit, the game's hit.
    A first sweep that's clear, another target and a swimming player get
    one sweep and the game's answer. Its second entry, at the camera's
    line-of-sight test (0x80C10's sweep from the camera's place to the
    point, the CALL at 0x80C35; Step 2.107: on a1's ladder a body drawn
    x2 snapped in 7-14 m every climb as the sight of its drawn top was
    lost), lowers the point at that sweep's far end the same way. The build writes the lift as the
    point's height above garret4's eye (garret4's share of the drawn top
    since Step 2.107): golem own 2.21, town_male_6 own x2 2.31, kingkong
    at garret4's height x2 1.9925, keylord own 0.20, and from a body's own
    m_head at rest Balthazar own x2 1.9925. Where both of its lines stay
    blocked the game pulls the camera on its 24th blocked test (0.8 s), in
    one 7-9 m step on a1's ladder at x2-2.4, where garret4's own slides in
    after 8-9 (Step 2.116b, D286's limit 4, AZ-555): on a blocked test for
    the player on the ground or the ladder (state 0 or 1) with its timer
    (+0x1B4, before this tick's dt) at 0.29 s or more, the camera's yaw,
    pitch and distance held and the point's step steady since the last
    call, the entry sweeps both lines moved on by the steps left to the
    game's 24th test ((0.8 - timer) / dt - 1: 14 at the 10th test, a ladder
    model blocking any line whose point end is under a height) into its own
    record, and when both are blocked writes 1.0 into the timer, so the game
    pulls this tick (the 10th test, garret4's 0.33 s); a run whose 24th
    line clears (x2.7's climb), state 2, a step that jumps (X8's swim
    switch) or a camera whose distance moves keeps the game's timer."""
    built = bytes(_swap("golem", sounds="garret4")["default.xbe"])
    assert l1.check(_vanilla("default.xbe"), built) == []
    entries = {va: va + 5 + struct.unpack_from("<i", built, va_to_file(va) + 1)[0] for va in (0x810F3, 0x80C35)}
    base = 0x20000000
    camera, target, species, control, points, record = (base + 0x1000 * k for k in range(6))

    def sweep(*, player: bool = True, state: int = 0, point: float = 6.0, sight: bool = False
              ) -> tuple[int, list, bytes]:
        sim = Sim(built)
        sim.uc.mem_map(base, 0x10000)
        for at_, fmt, value in ((camera + 0x190, "<I", target), (target + 0x178, "<I", species),
                                (target + 0x180, "<I", control), (target + 0x15C, "<3f", (1.0, 2.0, 3.0)),
                                (species + 0x64, "<I", 0x24 if player else 0x04), (control + 0x94, "<i", state),
                                (points, "<3f", (1.5, 2.5, point)), (points + 0x10, "<3f", (5.0, 6.0, 4.5))):
            sim.uc.mem_write(at_, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        calls = []

        def stub(uc, addr, size, _):   # collision_sweep: __stdcall(36), RET 0x24
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<10I", uc.mem_read(esp, 40))
            ends = [struct.unpack("<3f", uc.mem_read(a, 12)) for a in args[3:5]]
            hit = max(e[2] for e in ends) > 4.5
            calls.append((ends[1 if sight else 0], args[8] == record))
            if hit:
                uc.mem_write(args[8], bytes([len(calls)]) * 0x48)
            uc.reg_write(UC_X86_REG_EAX, int(hit))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 40)

        sim.uc.hook_add(UC_HOOK_CODE, stub, begin=0x60870, end=0x60870)
        radius = struct.unpack("<I", struct.pack("<f", 0.096))[0]
        ends = (points + 0x10, points) if sight else (points, points + 0x10)   # the point is the sight's far end
        al = sim.call(entries[0x80C35 if sight else 0x810F3], args=(base + 0x7000, camera, 0, *ends, radius, radius,
                                                                     0x40, record), until=l2._RETURN) & 0xFF
        assert sim.reg("esp") == l2._STACK_TOP - 0x100   # RET 0x24, as 0x60870's
        return al, calls, bytes(sim.uc.mem_read(record, 0x48))

    lift = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, EYE_SWEEP_HOOK, "_player_model_eye_lift", shim_source=EYE_SWEEP_SHIM.source_path())))[0]
    t = (3.0 - lift) / 3.0                         # the point 3 m over the centre, lowered by the lift
    low = (1.0 + 0.5 * t, 2.0 + 0.5 * t, 3.0 + 3.0 * t)
    for sight in (False, True):
        al, calls, kept = sweep(sight=sight)
        assert (al, kept) == (0, bytes([1]) * 0x48)
        assert [own for _, own in calls] == [True, False]
        assert all(math.isclose(a, b, abs_tol=1e-4) for a, b in zip(calls[1][0], low))
        al, calls, kept = sweep(point=8.0, sight=sight)   # lowered to 5.8, still above 4.5: the game's hit
        assert (al, [own for _, own in calls], kept) == (1, [True, False], bytes([1]) * 0x48)
        for kw in ({"player": False}, {"state": 6}, {"point": 3.5}):
            al, calls, _ = sweep(sight=sight, **kw)
            assert (al, len(calls)) == (int(kw.get("point", 6.0) > 4.5), 1), kw

    def climb(*, top: float, calls: int = 10, state: int = 1, jump: int = 0, zoom: float = 0.0
              ) -> list[tuple[float, int, bool, tuple]]:
        """``calls`` blocked sight tests on one sim as a climb: the point,
        its centre and the camera rise 0.0667 m a call (4 m lower from call
        ``jump`` on), the camera's yaw and pitch held (its distance moving
        ``zoom`` m a call), the timer at entry (n - 1) / 30; a line is
        blocked while its point end is under ``top``. Per call: the timer
        after it, the sweeps run, whether the caller's record is the game's
        sweep's, and the third sweep's ends (the first moved line)."""
        sim = Sim(built)
        sim.uc.mem_map(base, 0x10000)
        for at_, fmt, value in ((camera + 0x190, "<I", target), (target + 0x178, "<I", species),
                                (target + 0x180, "<I", control), (species + 0x64, "<I", 0x24),
                                (control + 0x94, "<i", state), (camera + 0x194, "<2f", (0.5, -0.5236))):
            sim.uc.mem_write(at_, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        made = []

        def stub(uc, addr, size, _):
            esp = sim.reg("esp")
            ret, *args = struct.unpack("<10I", uc.mem_read(esp, 40))
            ends = [struct.unpack("<3f", uc.mem_read(a, 12)) for a in args[3:5]]
            hit = ends[1][2] < top
            sweeps.append((ends, args[8] == record))
            if hit:
                uc.mem_write(args[8], bytes([len(sweeps)]) * 0x48)
            uc.reg_write(UC_X86_REG_EAX, int(hit))
            uc.reg_write(UC_X86_REG_EIP, ret)
            uc.reg_write(UC_X86_REG_ESP, esp + 40)

        sim.uc.hook_add(UC_HOOK_CODE, stub, begin=0x60870, end=0x60870)
        radius = struct.unpack("<I", struct.pack("<f", 0.096))[0]
        for n in range(1, calls + 1):
            z = 0.0667 * n - (4.0 if jump and n >= jump else 0.0)
            for at_, value in ((target + 0x15C, (1.0, 2.0, 3.0 + z)), (points, (1.5, 2.5, 6.0 + z)),
                               (points + 0x10, (5.0, 6.0, 4.5 + z))):
                sim.uc.mem_write(at_, struct.pack("<3f", *value))
            sim.uc.mem_write(camera + 0x19C, struct.pack("<2f", 10.0 + zoom * n, 0.0))
            sim.uc.mem_write(camera + 0x1B4, struct.pack("<f", (n - 1) / 30))
            sweeps = []
            al = sim.call(entries[0x80C35], args=(base + 0x7000, camera, 0, points + 0x10, points, radius, radius,
                                                  0x40, record), until=l2._RETURN) & 0xFF
            assert al == 1 and sim.reg("esp") == l2._STACK_TOP - 0x100
            made.append((round(sim.f32(camera + 0x1B4), 4), len(sweeps),
                         bytes(sim.uc.mem_read(record, 0x48)) == bytes([1]) * 0x48,
                         sweeps[2][0] if len(sweeps) > 2 else None))
        return made

    far = 6.0 + 0.0667 * 30                       # the 24th test's line still blocked: the game pulls this run
    got = climb(top=far)
    assert [timer for timer, *_ in got] == [round((n - 1) / 30, 4) for n in range(1, 10)] + [1.0]
    assert [(sweeps, kept) for _, sweeps, kept, _ in got] == [(2, True)] * 9 + [(4, True)]
    ahead = 0.0667 * 14                           # the 10th test's lines moved 14 steps on: the 24th's
    assert [round(c, 3) for end in got[-1][3] for c in end] == [
        round(c, 3) for c in (5.0, 6.0, 4.5 + 0.667 + ahead, 1.5, 2.5, 6.0 + 0.667 + ahead)]
    near = 6.0 + 0.0667 * 20                      # x2.7's climb: its 24th line clears, so no pull
    assert [timer for timer, *_ in climb(top=near, calls=19)][9:] == [round((n - 1) / 30, 4) for n in range(10, 20)]
    for kw in ({"state": 2}, {"zoom": 0.1}):      # airborne; a camera whose distance moves
        assert [timer for timer, *_ in climb(top=far, **kw)][-1] == round(9 / 30, 4), kw
    assert [timer for timer, *_ in climb(top=far, calls=11, jump=9)][9:] == [round(9 / 30, 4), 1.0]   # a 4 m jump
    lifts = {}
    for species, kw in (("golem", {}), ("town_male_6", {"model_scale": 2.0}),
                        ("kingkong", {"size": "garret4", "model_scale": 2.0}),
                        ("balthazar", {"model_scale": 2.0}), ("keylord", {})):
        xbe = bytes(_swap(species, sounds="garret4", **kw)["default.xbe"])
        lifts[species] = (round(struct.unpack_from("<f", xbe, resolve_va_to_file(xbe, trampoline_symbol_va(
            xbe, EYE_SWEEP_HOOK, "_player_model_eye_lift", shim_source=EYE_SWEEP_SHIM.source_path())))[0], 4)
            if verify_trampoline_patch(xbe, EYE_SWEEP_HOOK) == "applied" else None)
    assert lifts == {"golem": 2.2139, "town_male_6": 2.3117, "kingkong": 1.9925, "balthazar": 1.9925,
                     "keylord": 0.1969}


def test_a_body_drawn_larger_aims_the_camera_no_lower_than_its_centre_on_the_zipline_ride_and_off_it():
    """AZ-520's ride (Step 2.105, X20): X9 hangs a body drawn x2 twice
    garret4's grab under the cable, so its camera point rode 1.4-1.6 m
    under its centre, and the level camera 0x81240, which aims its
    line-of-sight test and slide from that point (its local at ESP +
    0x50 once the target's vtable +0xB0 wrote it), collapsed to 0.3-0.4 m
    from it mid-ride (sitting 2.104). X20 (L2, town_male_6 own x2's build)
    at 0x81292, where every path goes on from getting the point: while
    the camera's target (+0x190) is the player and its PlayerControl is
    on the ride (state 5), or airborne (2) with its drawn origin (+0x1BC)
    more than 1.25 m under its centre (X22 easing it off the ride), or
    hanging onto it (hang_start, 0x105: Step 2.107, so the point doesn't
    jump as hang_start turns into the ride), the point's z rises to the
    centre's (+0x164), x and y kept; a point over the centre, an airborne
    body at its stance (the origin 1.0 m under), the ground (0), another
    target and no PlayerControl keep the game's. Then the two loads it
    replaced (EDI the camera, EDX its +0x154), EBX, ESI and EBP kept, a
    plain RET. The rule is :func:`camera_plan`'s: a body drawn taller than
    garret4 (golem own x1: Step 2.107), or away from x1 one whose point
    rides under its centre on Step 2.106's hang, which hangs the top of
    its hang pose at the cable (water_tentacle1 own x2, 0.37 of his
    height: its hang pose stands 7.9 m over its origin, its mesh 0.75 m,
    so its point rides 5.3 m under the centre; the sitting plan's F7). A body drawn shorter whose
    point rides over it (flicken own x2, 0.70 of his height, 2.1 m over)
    keeps 0x81292's bytes, and since Step 2.118 (AZ-536, D291) x1 hangs a
    shorter body by its top too, so the rule holds there (water_tentacle1
    own x1 takes X20; flicken own x1, no longer hung a height under the
    cable at garret4's grab, keeps the bytes)."""
    built = bytes(_swap("town_male_6", sounds="garret4", model_scale=2.0)["default.xbe"])
    assert l1.check(_vanilla("default.xbe"), built) == []
    at = va_to_file(0x81292)
    assert built[at + 5:at + 10] == b"\x90" * 5
    entry = 0x81297 + struct.unpack_from("<i", built, at + 1)[0]
    base = 0x20000000
    camera, target, species, control = (base + 0x1000 * k for k in range(4))

    def point(*, player: bool = True, state: int | None = 5, z: float = 1.5, origin: float = -1.65) -> tuple[float, ...]:
        sim = Sim(built)
        sim.uc.mem_map(base, 0x4000)
        for at_, fmt, value in ((camera + 0x154, "<I", 0x5A5A), (camera + 0x190, "<I", target),
                                (target + 0x15C, "<3f", (1.0, 2.0, 3.0)), (target + 0x1BC, "<3f", (1.0, 2.0, origin)),
                                (target + 0x178, "<I", species),
                                (target + 0x180, "<I", 0 if state is None else control),
                                (species + 0x64, "<I", 0x24 if player else 0x04), (control + 0x94, "<i", state or 0)):
            sim.uc.mem_write(at_, struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value))
        frame = [0] * 24                         # the caller's ESP + 0 .. + 0x5C
        frame[4] = camera
        frame[20:23] = struct.unpack("<3I", struct.pack("<3f", 4.0, 5.0, z))
        kept = {"ebx": 0, "esi": 0x11, "ebp": 0x33}
        sim.call(entry, regs=kept, args=tuple(frame), until=l2._RETURN)
        caller = l2._STACK_TOP - 0x100 - 4 * len(frame)
        assert sim.reg("esp") == caller          # a plain RET
        assert ({r: sim.reg(r) for r in kept}, sim.reg("edi"), sim.reg("edx")) == (kept, camera, 0x5A5A)
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        return struct.unpack("<3f", sim.uc.mem_read(caller + 0x50, 12))

    assert point() == point(state=2) == point(state=0x105) == (4.0, 5.0, 3.0)   # the ride; the let-go; hang_start
    for kw in ({"z": 3.5}, {"state": 2, "origin": 2.0}, {"state": 0}, {"player": False}, {"state": None}):
        assert point(**kw) == (4.0, 5.0, kw.get("z", 1.5)), kw
    for species, scale, state in (("water_tentacle1", 2.0, "applied"), ("water_tentacle1", 1.0, "applied"),
                                  ("flicken", 2.0, "original"), ("flicken", 1.0, "original")):
        game = _swap(species, sounds="garret4", model_scale=scale)
        assert verify_trampoline_patch(bytes(game["default.xbe"]), EYE_HANG_HOOK) == state, (species, scale)


def test_a_swimming_player_models_camera_stays_on_one_side_of_the_surface_with_its_body():
    """AZ-307, AZ-311, AZ-413, AZ-414: the level camera (0x81240) has no
    swim mode. It sits at its distance and pitch from the camera point
    (2.5 m above it), and in the water 0x81E10 only moves a camera that
    comes within 0.4 m of the surface 0.5 m to the other side and keeps
    that distance and pitch (0x820E0); a camera above the water shows
    nothing under it. Step 2.80's point, 0.5 m under the surface for a
    body taller than its +0x15C's depth, else the game's zeros, failed
    sitting 2.75a on guard_air's sink and rise (captures *-dswim-*):
    its model stands 3.07 m under +0x15C in the water (sitting
    sight223b), so at its resting depth (1.13 m) the point was 3.57 m
    under the surface and the camera crossed it 5 times in 99 ticks, and
    once its top sank 1 m under, the camera stayed above with nothing in
    frame; guard_fire1's dropped from 3.0 m to its feet at depth 3.65 m
    and framed it from below, its top cut off. While the player swims
    (its PlayerControl, critter+0x180, in move state 6 at +0x94) X8
    measures the body from its model origin (critter_model_matrix,
    0x42200) against the surface (+0x15C's height plus critter+0x27C):
    while its top (x scale, critter+0x188) is out, the point is the
    land point, its top, raised only to keep the camera the first swim
    margin's height over the water (Step 2.116, AZ-311: a margin under the
    surface put a body drawn x2 floating at rest at its origin, under its
    drawn feet, so it filled the frame's top edge); once the top is 0.25 m
    under and +0x15C deeper than 2.55 m (a dive: rest depths are 1.04-1.38
    m), the second margin under the surface (3.5 m: the camera about 1 m
    under), climbing the body as it sinks, below its feet if need be (Step
    2.107); back above once the top is 0.25 m out or +0x15C no deeper than
    2.35 m, so x0.37, its top 0.24-0.30 m under at rest, no longer crosses
    the surface; never above its top under the water. The dive's edges are
    garret4's own crossing depths (Step 2.116b, AZ-556: at 1.7 and 1.5 m
    splinter's camera went under and back in a 2.3 m dive, where garret4's
    crosses at 2.549 m down and 2.518 m up), so a dive to 2.4 m stays over. The build writes
    both margins from its camera rig's scale (:func:`swim_margins`; here
    the object's own 0.5 and 3.5, then x2's and x0.37's: the camera 2s m
    over the surface, max(0.6, s) m under it). On land, in the
    air and with no controller the point is the top. Rows: guard_air's
    sink and rise depths from 2.75a's captures, then where keylord and
    guard_fire1 stood (at +0x15C), at other sizes."""
    built = bytes(_swap("guard_air")["default.xbe"])
    top, below = 0.99535 * 5.5763, -3.07
    rows = {   # (state, depth, scale, origin) -> the point's height, model units; in this order
        (6, 1.126, 1.0, below): top,       # resting, its top 1.35 m out: the land point
        (6, 2.69, 1.0, below): top,        # sinking, its top 0.21 m under: the camera stays above
        (6, 2.821, 1.0, below): 2.391,     # 0.34 m under: the camera goes under, 3.5 m under the surface
        (6, 3.8, 1.0, below): 3.37,        # and climbs the body as it sinks
        (6, 5.787, 1.0, below): 5.357,
        (6, 7.0, 1.0, below): top,         # never above its top
        (6, 2.4, 1.0, below): 1.97,        # rising, its top 0.08 m out, +0x15C past 2.35 m: the camera stays under
        (6, 2.33, 1.0, below): top,        # +0x15C 2.35 m deep or less (garret4's crossing): back above, at its top
        (6, 1.126, 1.0, 0.0): top,         # standing at +0x15C (keylord, guard_fire1)
        (6, 3.2, 0.5, 0.0): -0.6,          # all under at half its size: 3.5 m under the surface, below its feet
        (6, 1.126, 2.0, 0.0): top,         # back above at twice its size: its top, not 0.313 at its feet
        (0, 2.96, 1.0, 0.0): top, (2, 2.96, 1.0, 0.0): top, (None, 2.96, 1.0, 0.0): top,
    }
    m0, m1 = swim_margins(0.37)
    k = 0.737 / top   # garret4's height x0.37
    scaled = {   # the rig's margins (m) -> rows as above
        swim_margins(2.0): {(6, 1.126, 2.0, 0.0): top, (6, 7.0, 0.5, 0.0): (7.0 - 7.055) / 0.5},
        (m0, m1): {
            (6, 1.04, k, 0.0): (1.04 - m0) / k,   # at rest, its top 0.3 m under: over the water, 0.74 m up
            (6, 1.8, k, 0.0): (1.8 - m0) / k,     # sinking, no dive yet (splinter's 1.77 m crossing): still over
            (6, 2.4, k, 0.0): (2.4 - m0) / k,     # 2.4 m: still over, as garret4's
            (6, 2.6, k, 0.0): top,                # past 2.55 m: under the water, the point at most its top
            (6, 2.38, k, 0.0): top,               # rising, still past 2.35 m: still under, at most its top
            (6, 2.3, k, 0.0): (2.3 - m0) / k},    # back over
    }
    for margins, want in ((SWIM_MARGINS, rows), *scaled.items()):
        got = _camera_points(built, 0x24, rows=tuple(want), margins=margins)
        assert all((x, y, returned) == (0.0, 0.0, True) for (x, y, _), returned in got)
        assert [z for (_, _, z), _ in got] == [pytest.approx(v, abs=0.005) for v in want.values()], margins


def test_a_surfaced_bodys_swim_camera_sits_over_its_drawn_root_where_garret4s_sits_over_his():
    """Step 2.150 (AZ-642; the owner on town_female_4 in the 2.76 play:
    "this also might be causing her camera to look like its too far above
    her in the water"): W27 draws a baked body's root at the swim's centre
    (its origin the centre less its m_root, 0x42E40), and X8's swim point,
    that origin plus the standing top, rode 1.45 m over garret4's in the
    stroke, floored at 2.00 m over the surface at rest where his camera
    rests 1.78-1.83 m over (sitting 2.134b C). Her build grows W27's
    m_eye after m_root, at rest (0, 0, 1), and keys it in each swim copy
    with garret4's head over his root in his clip over his eye height
    (his m_head is one height per swim clip: 1.9925 unkeyed at rest, 0.519
    in swim_2); X8's swim top is m_root / D + its eye height x m_eye, so at
    the settled depth (1.126 m) her camera, run through the built shim at
    each copy's markers through all four swim slots, sits where garret4's
    does over the surface within 0.01 m (her share x D 0.998). W27's
    floor is 0.6 m over the surface (0x81E10's 0.4 m band and 0.2 m),
    not the size's 2.00 m: in the stroke at 2.4 m it holds the camera
    there, still over (a dive is past 2.55 m). Out of the water the top is
    her eye height x the pose's m_eye too (1 on every land clip), so the
    hoist's crossfade out of a swim copy blends it up from the swim's,
    where the standing top popped her camera 1.96 m in one tick (Step
    2.150's sitting). A body without m_eye keeps the standing top."""
    vanilla = _vanilla("gamedata/characters.xbr")
    game = _swap("town_female_4")
    built, characters = bytes(game["default.xbe"]), bytes(game["characters.xbr"])
    body = read_body(characters, "townspeople/female_4")
    root, eye = len(body.markers) - 2, len(body.markers) - 1
    assert body.markers[root:] == ("m_root", "m_eye")
    assert dict(marker_records(characters, body.name))["m_eye"][:3] == (0.0, 0.0, 1.0)
    his = [m.casefold() for m in read_body(vanilla, "garret4").markers]
    rest = {i: marker_records(vanilla, "garret4")[i][1][2] for i in (his.index("m_head"), his.index("m_root"))}
    drawn, depth, rise = 1.15, 1.126, 2.5   # her drawn scale; no rig at s 0.999

    def height(clip, target: int, t: float, default: float) -> float:
        keys = next((tr.keys for tr in clip.markers if (tr.target, tr.comp) == (target, 2)), None)
        return default if keys is None else retarget.evaluate(keys, t)
    rows, garret4 = [], []
    for slot in SURFACE_SLOTS:
        name = BASE_CLIPS[slot]
        copy = read_clip(characters, _clip(characters, f"characters/{body.name}/s/g4/{name}".casefold())[0])
        g4 = read_clip(vanilla, _clip(vanilla, f"characters/garret4/{name}")[0])
        for t in (copy.length * k / 12 for k in range(13)):
            z = (height(copy, root, t, 0.0), height(copy, eye, t, 1.0))
            rows.append((6, depth, drawn, -z[0], z))
            head, under = (height(g4, i, t, v) for i, v in rest.items())
            garret4.append(head - under - depth + rise)   # his camera over the surface (m)
    stroke = rows[-1]
    rows.append((6, 2.4, drawn, *stroke[3:]))   # the stroke 2.4 m down: on W27's floor
    got = _camera_points(built, 0x24, rows=tuple(rows), swim=("m_root", "m_eye"))
    assert all((x, y, returned) == (0.0, 0.0, True) for (x, y, _), returned in got)
    cameras = [origin + drawn * z + rise - d for (_, d, _, origin, _), ((_, _, z), _) in zip(rows, got)]
    assert cameras[:-1] == [pytest.approx(c, abs=0.01) for c in garret4]
    assert cameras[-1] == pytest.approx(0.6, abs=1e-4)
    top = struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
        built, EYE_HOOK, "_player_model_eye_height", shim_source=EYE_SHIM.source_path())))[0]
    land = ((0, 0.0, drawn, 0.0, stroke[4]), (0, 0.0, drawn, 0.0, (0.0, 1.0)))   # the hoist's first pose; a land clip
    assert _camera_points(built, 0x24, rows=land, swim=("m_root", "m_eye")) == [
        ((0.0, 0.0, pytest.approx(top * stroke[4][1])), True), ((0.0, 0.0, top), True)]
    for state in (6, 0):
        assert _camera_points(built, 0x24, rows=((state, *stroke[1:4], (stroke[4][0],)),), swim=("m_root",))[0] == (
            (0.0, 0.0, pytest.approx(top)), True)


def test_the_camera_frames_a_body_drawn_at_any_size_as_garret4_does_at_x1():
    """D280 (Step 2.107; the owner: "can you also make sure the camera
    properly positions itself for models of any size (including custom
    sizes)?"; D115's default: framed as garret4 is at x1). The level
    camera sits at a distance and pitch from its point, 5.11 m from the
    eye (its 5 m and the eye's 0.11) at -30 degrees, 70 degrees across at
    4:3, and every number it moves by is in metres, so a build scales its
    metre-valued constants (X25's rig) by the drawn body's size over
    garret4's, and its picture is his at x1. For every usable species at
    both sizes on a ladder of model scales (D23: no limit), the build's
    plan (:func:`camera_plan`) seen by this test's own projection: the
    drawn mesh box cut at the feet is in frame (NDC within 0.95), every
    corner past the near plane (so the eye is outside the box); an upright
    body aimed at garret4's share of its top at its drawn height's scale
    has its top and feet where his are at x1 (within 0.01); a scale above
    that and the 0.1 floor is the least that frames the box (the wings,
    tails and lengths that lift it: guard_air own, the tentacles), and
    the floor holds only bodies drawn under a tenth of his height; the
    swim margins keep the camera 0.6 m or more from the surface (0.2 m
    clear of the 0.4 m push band), and are the object's own 0.5 and 3.5
    without a rig, as at x1; X20 on a body drawn taller than garret4
    (golem own x1, not flicken own x2.4). A body drawn at 0 or less (a
    point, or mirrored under its feet), or at a scale the game's float32
    holds as 0 or a denormal (x1e-46, x1e-39), gets no camera part (D7).
    A body whose idle and swim slots' clips raise its bones more than 8
    times its mesh's top is measured by that pose (Step 2.116b, AZ-556:
    water_tentacle3's camera sat inside its risen part at rest): the
    tentacles (water_tentacle3 own s 2.081, its point at 4.147 m, X20 and
    X19's lift on, X27 off), not key_air1's 5.06x bob nor garret4's 1.21x."""
    characters = _vanilla("gamedata/characters.xbr")
    rows = _species(XbrDocument.from_bytes(_vanilla("gamedata/config.xbr"))
                    .keyed_section("critters_engine"))
    bodies = body_names(characters)
    g4 = camera_shape(characters, read_body(characters, "garret4"))
    his = [_seen(1.0, g4.g4_eye, (0.0, 0.0, z))[2] for z in (g4.high[2], 0.0)]   # his top and feet at x1
    shapes, plans = {}, {}
    for species, row in rows.items():
        if species == "garret4" or _refusal(rows, bodies, species):
            continue   # garret4 writes nothing (the build test below)
        body = read_body(characters, row["body"])
        if body.name not in shapes:
            shapes[body.name] = camera_shape(characters, body), size_scale(characters, body)
        shape, sized = shapes[body.name]
        low, high = shape.low, shape.high
        upright = high[2] >= FLAT * max(h - lo for lo, h in zip(low, high))
        for size, scale in (("own", row["scale"] or 1.0), ("garret4", sized)):
            for x in (0.1, 0.25, 0.37, 1.0, 1.37, 2.4, 3.3, 10.0, 0.0, -1.0, 1e-39, 1e-46) if scale else ():
                drawn, case = scale * x, (species, size, x)
                plan = plans[case] = camera_plan(shape, sized if size == "garret4" else None, drawn, x)
                if x <= 0.0 or struct.unpack("<f", struct.pack("<f", drawn))[0] < 2.0 ** -126:
                    assert (plan.x8, plan.lift, plan.x20, plan.rig) == (False, 0.0, False, False), case
                    continue
                corners = [(cx * drawn, cy * drawn, max(cz, 0.0) * drawn)
                           for cx in (low[0], high[0]) for cy in (low[1], high[1]) for cz in (low[2], high[2])]

                def framed(s: float, edge: float = 0.95 + 1e-3) -> bool:
                    return all(depth >= 0.11 + 0.1 * s and abs(nx) <= edge and abs(ny) <= edge
                               for depth, nx, ny in (_seen(s, plan.aim * drawn, c) for c in corners))

                least = max(plan.k_h, RIG_FLOOR)
                assert framed(plan.s) and plan.s >= least, case
                if plan.s > least * (1 + 1e-6):   # the least that frames it
                    assert not framed(plan.s * (1 - 1e-3), 0.95), case
                assert plan.s != RIG_FLOOR or plan.k_h <= RIG_FLOOR, case
                if upright and plan.x8 and plan.s == plan.k_h:
                    mine = [_seen(plan.s, plan.aim * drawn, (0.0, 0.0, z))[2] for z in (high[2] * drawn, 0.0)]
                    assert mine == pytest.approx(his, abs=0.01), case
                rise = 0.5 * rest_distance(plan.s)
                if plan.rig:
                    assert min(rise - plan.margins[0], plan.margins[1] - rise) >= 0.6 - 1e-9, case
                else:
                    assert plan.margins == SWIM_MARGINS and abs(plan.s - 1.0) < 0.005, case
                assert plan.x20 is (plan.k_h > 1.0), case
    assert swim_margins(1.0) == pytest.approx(SWIM_MARGINS) and rest_distance(1.0) == pytest.approx(5.0)
    assert {case: (round(plans[case].s, 3), plans[case].rig, plans[case].x20) for case in (
        ("kingkong", "own", 1.0), ("guard_air", "own", 1.0), ("golem", "own", 1.0), ("flicken", "own", 2.4),
        ("town_male_6", "garret4", 1.0), ("firefly", "own", 1.0), ("water_tentacle3", "own", 1.0),
        ("key_air1", "own", 1.0))} == {
        ("kingkong", "own", 1.0): (8.444, True, True),          # 43 m back
        ("guard_air", "own", 1.0): (3.178, True, True),         # its wings lift it past its height's 2.786
        ("golem", "own", 1.0): (2.111, True, True),
        ("flicken", "own", 2.4): (0.843, True, False),
        ("town_male_6", "garret4", 1.0): (1.0, False, False),   # the game's own rig
        ("firefly", "own", 1.0): (RIG_FLOOR, True, False),      # 1 cm tall: the floor
        ("water_tentacle3", "own", 1.0): (2.081, True, True),   # its risen idle, 14.6x its mesh's top
        ("key_air1", "own", 1.0): (0.977, True, False)}         # its bind mesh: a one-bone bob of 5.06x
    tentacle = plans["water_tentacle3", "own", 1.0]
    assert (round(tentacle.aim, 3), round(tentacle.lift, 3), tentacle.near) == (4.147, 2.154, False)


@pytest.mark.parametrize("species, kw, region", [
    ("keylord", {"model_scale": 2.0}, "usa"),         # x2.2 garret4's size: the rig, X8, X19, X20
    ("kingkong", {"size": "garret4"}, "usa"),         # his height at x1: the game's rig
    ("guard_air", {"model_scale": 0.0}, "usa"),       # drawn as a point: no camera part
    ("garret4", {}, "usa"),                           # garret4 at x1 writes nothing
    ("garret4", {"model_scale": 2.0}, "usa"),         # his own body x2 (Step 2.123): the rig, X19, X20, no X8
    ("water_tentacle3", {}, "usa"),                   # measured by its risen idle (Step 2.116b): X19, X20, the rig
    pytest.param("town_male_6", {"model_scale": 2.0}, "europe", marks=pytest.mark.europe),
])
def test_a_build_scales_the_level_cameras_rig_to_its_drawn_body_and_regrows_it_at_rest(species, kw, region):
    """D280 (Step 2.107, X25): the level camera's rig is eight metre-valued
    f32 constants only the camera module (0x80820-0x82680) and its boot
    copy (0xFB550) read: the rest distance 5.0 (0x19814C, the reset's at a
    level start, a respawn and a warp), the D-pad zoom's 0.5-12 m and its
    and the regrow's 10 m/s, the 3 m past the wanted distance, the water
    push's 2 m and RT's 6 m. A build writes each as the plan's
    (:func:`camera_plan`) at the rig scale s (the rest distance 5.11s -
    0.11, the eye's 0.11 m kept), at Europe's addresses on a Europe build,
    and NOPs the regrow's multiply by the sticks' sum (0x8196F), so a
    camera something pulled in grows back at 10s m/s with no stick held
    (2.105: town_male_6 own x2's ride started at 0.627 m and never
    recovered), never more than 3s past the wanted distance; on vanilla it
    stays (L2: the block on a synthetic camera). X8's point and margins
    (on a W27 body its 0.6 m floor, Step 2.150), X19's lift and X20 are
    each the plan's. A body at garret4's size x1
    keeps the game's rig; one drawn at 0 gets no camera part (D7); the
    species garret4 builds the vanilla image (D1) at x1, and drawn x2
    (Step 2.123) the rig at his size x2 with X19 and X20, his own
    ``m_head`` his camera point (no X8). B2 (Step 2.116d,
    AZ-555): with X19 and the rig, X19's third entry at the step's add
    (0x819C9) holds a growing step while the line from the point lowered
    by the lift out along the camera's direction to the grown distance is
    blocked (on a1's ladder x2.2 regrew 35 ticks before garret4 with its
    body under the floor), with the radius the sight landing keeps; clear,
    it grows; a shrinking step, a swimming player, another target and no
    radius yet are the game's."""
    europe = region == "europe"
    game = _swap(species, EUROPE_ISO if europe else VANILLA_ISO, sounds="garret4", **kw)
    built, vanilla = bytes(game["default.xbe"]), _vanilla("default.xbe", EUROPE_ISO if europe else VANILLA_ISO)
    if species == "garret4" and not kw:
        assert built == vanilla
        return
    characters = game.stored("characters.xbr")
    body = read_body(characters, _species(XbrDocument.from_bytes(game.stored("config.xbr"))
                                          .keyed_section("critters_engine"))[species]["body"])
    cell = XbrDocument.from_bytes(game["config.xbr"]).keyed_section("critters_engine").find_cell(
        "garret4", "scale", None)
    sized = size_scale(characters, body) if kw.get("size") == "garret4" else None
    plan = camera_plan(camera_shape(characters, body), sized, cell.double_value if cell.type_code == 1 else 1.0,
                       kw.get("model_scale", 1.0))
    held = [built[off:off + 4] for off in (xbe_site(built, site.va, site.original)[1] for site in RIG_SITES)]
    rig = [rest_distance(plan.s), *(v * plan.s for _, v in CAMERA_RIG[1:])] if plan.rig else [v for _, v in CAMERA_RIG]
    assert [struct.unpack("<f", h)[0] for h in held[:-1]] == [struct.unpack("<f", pack_f32(v))[0] for v in rig]
    assert (held[-1] == b"\x90" * 4) is plan.rig
    assert [verify_trampoline_patch(built, hook) == "applied" for hook in (EYE_HOOK, EYE_SWEEP_HOOK, EYE_SIGHT_HOOK,
                                                                           EYE_REGROW_HOOK, EYE_HANG_HOOK)
            ] == [plan.x8, plan.lift >= 0.01, plan.lift >= 0.01, plan.lift >= 0.01 and plan.rig, plan.x20]
    if not plan.x8 or europe:
        return

    def param(hook, shim, symbol, n=1):
        return struct.unpack_from(f"<{n}f", built, resolve_va_to_file(built, trampoline_symbol_va(
            built, hook, symbol, shim_source=shim.source_path())))

    assert param(EYE_HOOK, EYE_SHIM, "_player_model_eye_height") == pytest.approx((plan.aim,), rel=1e-6)
    surfaced = "m_eye" in read_body(bytes(game["characters.xbr"]), body.name).markers   # W27's floor (Step 2.150)
    margins = swim_margins(plan.s if plan.rig else 1.0, SURFACE_FLOOR) if surfaced else plan.margins
    assert param(EYE_HOOK, EYE_SHIM, "_player_model_swim_margin", 2) == pytest.approx(margins, rel=1e-6)
    if plan.lift >= 0.01:
        assert param(EYE_SWEEP_HOOK, EYE_SWEEP_SHIM, "_player_model_eye_lift") == pytest.approx((plan.lift,), rel=1e-5)
    if not plan.rig:
        return
    wanted, step, cap = rest_distance(plan.s), 10 * plan.s / 30, 3 * plan.s
    assert _regrow(built, 0.6, wanted) == pytest.approx(0.6 + step, rel=1e-5)          # pulled in: it grows back
    assert _regrow(built, wanted + cap + 1.0, wanted) == pytest.approx(wanted + cap, rel=1e-5)
    assert _regrow(vanilla, 0.6, 5.0) == pytest.approx(0.6)                             # vanilla: it stays
    if plan.lift < 0.01:
        return
    low = (0.0, 0.0, round(3.0 - plan.lift, 4))
    out = [round(v * (0.6 + step) / 4.0, 4) for v in (0.0, -4.0 * math.cos(math.radians(30)), 2.0)]
    held, sweeps = _held_regrow(built, 0.6, wanted, blocked=True)
    assert (held, sweeps) == (pytest.approx(0.6), [(low, tuple(pytest.approx(a + b, abs=1e-3) for a, b in zip(low, out)),
                                                    0.096)])                         # garret4's line blocked: held
    assert _held_regrow(built, 0.6, wanted, blocked=False)[0] == pytest.approx(0.6 + step, rel=1e-5)   # clear: grows
    assert _held_regrow(built, wanted + 1.0, wanted, blocked=True) == (pytest.approx(wanted + 1.0 - step, rel=1e-5), [])
    for kw_ in ({"state": 6}, {"player": False}, {"radius": 0.0}):                # swimming, another, no radius yet
        assert _held_regrow(built, 0.6, wanted, blocked=True, **kw_) == (pytest.approx(0.6 + step, rel=1e-5), []), kw_


@pytest.mark.parametrize("scale, region", [
    (1.0, "usa"), (2.0, "usa"), (0.5, "usa"), pytest.param(2.0, "europe", marks=pytest.mark.europe)])
def test_garret4_drawn_at_a_model_size_gets_only_the_size_parts_his_own_body_needs(scale, region):
    """D302 (Step 2.123; the owner: "yes, let garret scale"): garret4's own
    body takes the Model size as a swapped one does (a recipe's species
    garret4 at its ``scale``). W2 writes his scale cell and grows his boundRadius
    with it (1.5 x 2), and he gets only the size parts his own body
    needs: X9's two zipline landings at his own grab (1) and X'
    (:func:`hang_scale`), X22, X23 and X26 at every size but x1, X19
    (with B2's regrow entry, Step 2.116d), X20, X21 out to 3 m x s
    (the boxes grow with him, the combo's search with them), X28
    (Step 2.127, AZ-529: his x2 hang reaches 5.11 m under the cable, past
    G4_SPAN, and stepped 0.996 m onto ride tick 1 in sitting 2.123; x0.5's
    1.32 m none), X13's fill (Step 2.132, D347) and X30 drawn larger, X8's
    swim point alone drawn smaller (Step 2.126: on land his ``m_head`` is
    the eye), X25's rig and X34's touch at his size, his walkSpeed (the
    walk/run switch) x sqrt(s) (Step 2.145, D422), and his roll column
    playing p/roll, his roll_forward drawn about his centre at his size
    (Step 2.133, AZ-608), and the five columns whose clip lunges (moves
    his m_feet) a copy drawn the same way, c/0-c/4 (Step 2.175, AZ-623);
    nothing else of the swap's (no other Anim,
    clip, sound, fx or other hook), the same bytes in every mode, size, clip and sound
    option (none applies to his own body), the mode's attack defaults
    left alone and the balance or reach-to-ground asked on refused by
    name (D35), at Europe's addresses on a Europe build. Drawn x2 and x0.5
    his status is the grade sitting 2.123 gave those sizes (D242). At x1 exactly (his hang top gives X' 0.99999996
    there, which would put X9, X22 and X23 on the build) the image is
    vanilla's."""
    europe = region == "europe"
    iso = EUROPE_ISO if europe else VANILLA_ISO
    log: list[str] = []
    game = _swap("garret4", iso, log, model_scale=scale)
    built = bytes(game["default.xbe"])
    if scale == 1.0:
        assert (built == _vanilla("default.xbe", iso), sorted(game.changed()), log) == (
            True, [], ["Player model: garret4, the vanilla player (green); nothing written"])
        for field, flag in (("attack_balance", "balance"), ("attack_ground", "ground")):
            with pytest.raises(ValueError, match=rf"--player-attack-{flag} on: garret4"):
                sdk.image({"iso": str(_IMAGES[iso]), "packs": {}, "character": {
                    "species": "garret4", "scale": 2.0, field: True}})
        return
    before, after = _cells(game.stored("config.xbr")), _cells(bytes(game["config.xbr"]))
    col = next(c for t, c, _ in before if t == "critters_engine" and c.endswith(":garret4"))
    data = next(c for t, c, _ in before if t == "critters_critter_data" and c.endswith(":garret4"))
    bound = before["critters_engine", col, "boundRadius"][1]
    hang = [h for h in CLIMB_HOOKS if h.float_params]
    grown = scale > 1.0
    others = [_swap("garret4", iso, mode="garret4", size="garret4", model_scale=scale, missing_anims="own",
                    sounds="garret4"),
              _swap("garret4", iso, mode="own", model_scale=scale, attack_balance=False, attack_ground=False)]

    def param(hook, symbol):
        return struct.unpack_from("<f", built, resolve_va_to_file(built, trampoline_symbol_va(
            built, hook, symbol, shim_source=CLIMB_SHIM.source_path())))[0]
    roll = ("attacks_anims", next(c for t, c, _ in before if t == "attacks_anims" and c.endswith(":roll forward")),
            "Anim")
    lunges = {("attacks_anims", c, "Anim"): name for t, c, _ in before if t == "attacks_anims"
              for col, name in (("sweep1", "c/0"), ("sweep2", "c/1"), ("up1", "c/2"), ("basic3", "c/3"),
                                ("basic2", "c/4")) if c.endswith(f":{col}")}
    assert sorted(game.changed()) == ["default.xbe", "gamedata/characters.xbr", "gamedata/config.xbr",
                                      "gamedata/index/index.xbr"]
    assert {key: after[key] for key in before if after[key] != before[key]} == {
        ("critters_engine", col, "scale"): (1, scale, None), roll: (*before[roll][:2], SIZED_ROLL),
        **{key: (*before[key][:2], name) for key, name in lunges.items()},
        ("critters_critter_data", data, "walkSpeed"): (1, pytest.approx(5.0 * math.sqrt(scale)), None),
        **({("critters_engine", col, "boundRadius"): (1, bound * scale, None)} if grown else {})}
    assert _moved(built) == {h.va for h in (*hang, *HANG_EASE_HOOKS, HANG_EASE_GROUND, OVER_TOP_HOOK, OVER_HOIST_HOOK,
                                            STANCE_HOOK,
                                            ATTACK_BOX_HOOK, TOUCH_HOOK, *(
        (EYE_SWEEP_HOOK, EYE_SIGHT_HOOK, EYE_REGROW_HOOK, EYE_HANG_HOOK, SEARCH_HOOK, STAFF_X1, *HOLD_HOOKS) if grown
        else (EYE_HOOK,)))} | {
        s.va for s in (*RIG_SITES, *(SEARCH_SITES if grown else ()))}
    characters = game.stored("characters.xbr")
    want = hang_scale(scale, scale, hang_top(characters, read_body(characters, "garret4"), {}))
    assert [(param(h, "_player_model_climb_scale"), param(h, "_player_model_climb_grab")) for h in hang] == [
        (pytest.approx(want, rel=1e-6), 1.0)] * 2
    if grown:
        radius = trampoline_symbol_va(built, SEARCH_HOOK, "_player_model_search_reach",
                                      shim_source=SEARCH_SHIM.source_path())
        assert struct.unpack_from("<f", built, resolve_va_to_file(built, radius))[0] == pytest.approx(3.0 * scale)
    assert [bytes(g[f]) for g in others for f in ("default.xbe", "config.xbr", "characters.xbr")] == [
        built, bytes(game["config.xbr"]), bytes(game["characters.xbr"])] * 2
    assert [n for n in log if n.startswith("Player model status:")][-1] == "Player model status: {} ({})".format(
        *GARRET4_SIZES[scale])


@pytest.mark.parametrize("species, scale, size, mode", [
    ("keylord", 1.0, 1.0988, "own"), ("keylord", None, 1.0, "own"), ("garret4", 2.0, 2.0, "own"),
    ("keylord", 1.0, 1.0, "garret4")])
def test_a_worn_body_runs_and_rolls_garret4s_times_the_root_of_its_drawn_height_over_his(species, scale, size, mode):
    """D330, D342, D353 (Step 2.133; D115's default, the design's C1 and
    C2): a worn body's size s is its drawn height over garret4's
    (camera_plan's k_h, exactly 1 within X25's 0.005), and a build
    folds sqrt(s) into the player_physics walk and roll sliders before its
    plan (``layer.size_params``), so the body runs garret4's runSpeed and
    rolls his distance x sqrt(s) (one writer per site: the walk's
    runSpeed cell and the roll's hand shim at 0x8C745) and the logic reads
    the same numbers: keylord own at Model size 1 (s 1.0988) and garret4's
    own body drawn x2. At s 1 (keylord standardized to garret4's height,
    D358's Model size 1 / its s) nothing folds: runSpeed 7.0 and the
    vanilla CALL; nor in Skin only (mode garret4, garret4's exact gameplay:
    the Model size alone, D115's default), whose keylord skin is half his
    height. The size the fold reads is the build's own (the sdk
    checks it against the model layer's, D35), also on a body measured by
    its pose (water_tentacle1) and one whose prop W20 moves into its hands
    (town_male_farmer_1: 2.133's critique, finding 2). D422 (Step 2.145,
    AZ-617): garret4's walkSpeed, the walk/run switch, scales the same,
    5.0 x sqrt(s) (keylord own 5.241, garret4 x2 7.071), so a full-stick
    run stays past it at every size; 5.0 at s 1."""
    from azurkit.core import facts
    from azurkit.tools.randomizer import layer
    from devkit.builds import inspect_physics, source

    if scale is None:
        scale = 1.0 / movement_size(_size_shape(VANILLA_ISO, species), 1.0)
    game = _swap(species, fold=True, sounds="garret4", model_scale=scale, mode=mode)
    rows = inspect_physics.inspect_player_physics(source.Build(
        _IMAGES[VANILLA_ISO], game["default.xbe"], game["config.xbr"], gate.USA, facts.of(gate.USA),
        _vanilla("default.xbe"), "the image"))["sliders"]
    walk = XbrDocument.from_bytes(bytes(game["config.xbr"])).keyed_section("critters_critter_data").find_cell(
        "garret4", "walkSpeed", None).double_value
    if size == 1.0:
        assert (rows["walk"]["state"], rows["walk"]["value"], rows["roll"]["state"], walk) == (
            "VANILLA", 7.0, "VANILLA", 5.0)
    else:
        assert movement_size(_size_shape(VANILLA_ISO, species, mode), scale) == pytest.approx(size, abs=1e-4)
        root = math.sqrt(movement_size(_size_shape(VANILLA_ISO, species, mode), scale))
        assert (rows["walk"]["value"], rows["roll"]["value"], walk) == (pytest.approx(7.0 * root, rel=1e-12),
                                                                        _f32(root), pytest.approx(5.0 * root))
        assert layer.size_params([], {}, size) == (
            ["player_physics"], {"player_physics": {"walk_speed_scale": pytest.approx(math.sqrt(size)),
                                                    "roll_speed_scale": pytest.approx(math.sqrt(size))}})
    if species == "keylord" and size != 1.0:
        assert layer.size_params(["qol_skip_logo"], {"x": {"y": 2.0}}, 1.0) == (["qol_skip_logo"], {"x": {"y": 2.0}})
        for posed in ("water_tentacle1", "town_male_farmer_1"):
            logic = AttackLogic()
            _swap(posed, sounds="garret4", logic=logic)
            assert movement_size(_size_shape(VANILLA_ISO, posed), 1.0) == logic.size != 1.0, posed


@pytest.mark.parametrize("species, scale, region, expected", [
    ("garret4", 0.5, "usa", (0.5, 0.5, -0.5)), ("garret4", 2.0, "usa", (2.0, math.sqrt(2.0), 0.0)),
    ("kingkong", 1.0, "usa", (8.4443, 2.9059, 0.0)), ("garret4", 1.0, "usa", None), ("keylord", None, "usa", None),
    pytest.param("garret4", 2.0, "europe", (2.0, math.sqrt(2.0), 0.0), marks=pytest.mark.europe)])
def test_a_worn_body_touches_pickups_at_its_size(species, scale, region, expected):
    """D344, D356 (Step 2.133, X34; the owner: "a leg is touching a pickup
    but it is not collected"): the player's pickup query (0x8C520's
    collision_sweep, radii 1.0 both ways round the body's centre, feet +
    1 m, at every drawn size) takes the body's size s: run from the hook
    at 0x8C553 to the centre's store at 0x8C56E under Unicorn, the stack
    holds the horizontal radius s, the vertical sqrt(s) above 1 (2.133's
    critique, finding 4: it contains x1's test and dips 0.46 m under the
    feet at x2, not 1.05) and s below 1, with the mask 0x80 and the
    centre pointers as the game's, and the centre's z moved by s - 1
    below 1 (feet + s: an item on the floor stays touchable) and kept
    above; garret4 drawn x0.5 and x2, kingkong own at Model size 1 (s
    8.44). Europe at its own address (0x8C503). At s 1 (garret4 x1,
    keylord standardized to his height) the game's bytes stay."""
    europe = region == "europe"
    iso = EUROPE_ISO if europe else VANILLA_ISO
    if scale is None:
        scale = 1.0 / movement_size(_size_shape(iso, species), 1.0)
    told: list[str] = []
    built = bytes(_swap(species, iso, told, model_scale=scale, sounds="garret4")["default.xbe"])
    log = " ".join(told)
    va, off, vanilla = xbe_site(built, TOUCH_HOOK.va, TOUCH_HOOK.replaced_bytes)
    if expected is None:
        assert (built[off:off + len(vanilla)] == vanilla, "(X34)" in log) == (True, False)
        return
    assert (verify_trampoline_patch(built, TOUCH_HOOK), "(X34)" in log) == ("applied", True)
    query = touch_query(movement_size(_size_shape(iso, species), scale))
    assert query == pytest.approx(expected, abs=1e-4)
    if europe:
        return

    def run(xbe: bytes) -> tuple:
        sim, entity, out = Sim(xbe), 0x20000000, 0x20000100
        sim.uc.mem_map(entity, 0x1000)
        sim.uc.mem_write(entity + 0x164, struct.pack("<f", 12.5))
        sim.call(TOUCH_HOOK.va, regs={"eax": entity, "ecx": struct.unpack("<I", struct.pack("<f", 12.5))[0],
                                      "edx": out, "ebx": 0x11, "esi": 0x22, "edi": 0x33, "ebp": 0x44},
                 until=0x8C56E)
        esp = sim.reg("esp")
        centre, also, wide, tall, mask = struct.unpack("<2I2fI", sim.uc.mem_read(esp, 20))
        z = struct.unpack("<f", sim.uc.mem_read(esp + 0x20, 4))[0]   # the centre's z, as 0x8C56A stored it
        assert sim.uc.reg_read(UC_X86_REG_FPSW) >> 11 & 7 == 0
        return ((esp, centre - esp, also - esp, mask, [sim.reg(r) for r in ("eax", "ebx", "esi", "edi", "ebp")]),
                (wide, tall, z))

    (kept, mine), (theirs, vanilla_query) = run(built), run(_vanilla("default.xbe"))
    assert kept == theirs and vanilla_query == (1.0, 1.0, 12.5)
    assert mine == pytest.approx((query[0], query[1], 12.5 + query[2]), rel=1e-6)


@pytest.mark.parametrize("scale, region", [
    (2.0, "usa"), (1.7, "usa"), (0.5, "usa"), (1.0, "usa"), pytest.param(2.0, "europe", marks=pytest.mark.europe)])
def test_a_garret_drawn_larger_checks_his_staff_against_the_walls_at_his_x1_size(tmp_path, scale, region):
    """AZ-575 (Step 2.126, D317, the owner: "Clank as at x1"): the
    staff-hits-wall check 0x8C8A0 poses garret4's staff_center2slide in
    the critter's world matrix, whose rows 0-2 0xA3860 scales by the
    critter's +0x188 (loaded at 0x8C9CC), so a Garret drawn x2 swept a
    staff twice as long, twice as far out, and clanked on walls a x1 one
    clears (sitting 2.123's re-run: 23 basic1s cut on one e7 run). X30
    loads 1.0 there on a Garret drawn larger, so the check poses the x1
    Garret's staff, its length and its place, whatever +0x188 holds
    (Europe's load at 0x8C97C the same), and verify-patches --strict
    declares the site. Drawn smaller (Q1's default) and at x1 the check
    keeps the critter's scale: vanilla's at x2 gives 2.0."""
    europe = region == "europe"
    game = _swap("garret4", EUROPE_ISO if europe else VANILLA_ISO, model_scale=scale)
    built = bytes(game["default.xbe"])
    off, original, patch = patch_spec_site(built, STAFF_X1)
    assert built[off:off + 6] == (patch if scale > 1.0 else original)
    (tmp_path / "default.xbe").write_bytes(built)   # verify-patches --strict declares the site
    assert verify_patches.main(["--xbe", str(tmp_path / "default.xbe"), "--original",
                                str(_IMAGES[EUROPE_ISO if europe else VANILLA_ISO]), "--strict"]) == 0
    if europe:
        return
    sim, critter = Sim(built), 0x20000000
    sim.uc.mem_map(critter, 0x1000)
    probe = scale if scale != 1.0 else 2.0
    sim.uc.mem_write(critter + 0x188, pack_f32(probe))
    sim.call(STAFF_X1.va, regs={"edi": critter}, until=STAFF_X1.va + 6)   # to the PUSH EDX
    assert struct.pack("<I", sim.reg("edx")) == pack_f32(1.0 if scale > 1.0 else probe)


@pytest.mark.parametrize("scale, region", [
    (0.5, "usa"), (0.37, "usa"), pytest.param(0.5, "europe", marks=pytest.mark.europe)])
def test_a_garret_drawn_smaller_keeps_his_swim_camera_over_the_water_and_his_own_head_on_land(scale, region):
    """AZ-576 (Step 2.126, D319, the owner: "Camera over the water", as a
    small swapped body's): the game floats the body's centre 1.02-1.13 m
    deep at every size, so garret4 drawn x0.5 rests wholly under the
    surface and the game's camera followed him under it (1.18-1.38 m
    under, the water push every tick: sitting 2.123's re-run, S5). Drawn
    under x1 he gets X8 swim-only (its land flag 0): swimming (move state
    6) the point is his m_head height raised so the camera rests
    max(2s, 0.6) m over the surface (x0.5: 1.0 m) and goes under only in
    a dive past 2.55 m with his top under, as a tiny swapped body's (X25's
    margins at the drawn size); out of the water (state 0, 0x100, no
    controller) it is the game's own m_head lookup, 0xCB2A0 run with ECX
    and the name as they came (here a head at (0.1, 0.05, 1.9)), which
    also puts the camera back on the top's side (swimming again at 2.4 m,
    inside the dive's hysteresis, it is over); another critter is the
    game's. Europe the same hook."""
    europe = region == "europe"
    game = _swap("garret4", EUROPE_ISO if europe else VANILLA_ISO, model_scale=scale)
    built = bytes(game["default.xbe"])
    assert verify_trampoline_patch(built, EYE_HOOK) == "applied"
    if europe:
        return
    characters = game.stored("characters.xbr")
    plan = camera_plan(camera_shape(characters, read_body(characters, "garret4")), None, scale, scale)
    (m0, m1), rise = swim_margins(plan.s), 0.5 * rest_distance(plan.s)
    head, origin = (0.1, 0.05, 1.9), -1.38   # his model origin at rest, under +0x15C (his top ~1.45 m under)
    rows = ((0, 1.07, scale, origin), (0x100, 1.07, scale, origin), (None, 1.07, scale, origin),
            (6, 1.07, scale, origin), (6, 2.8, scale, origin), (0, 2.8, scale, origin), (6, 2.4, scale, origin))
    got = _camera_points(built, 0x24, head, rows)
    assert all(returned for _, returned in got)
    points = [p for p, _ in got]
    assert points[:3] == [pytest.approx(head)] * 3 == points[5:6] * 3         # on land: the game's m_head
    for (state, depth, _, _), (x, y, z), over in zip(rows[3:5], points[3:5], (True, False)):
        camera = z * scale + origin + rise - depth                             # m over the surface
        assert (x, y) == (0.0, 0.0) and (camera >= max(2 * scale, 0.6) - 1e-4 if over else camera < 0.0), depth
    assert points[3] == pytest.approx((0.0, 0.0, (1.07 - origin - m0) / scale), abs=1e-4)
    assert points[4] == pytest.approx((0.0, 0.0, plan.aim), abs=1e-4)        # a dive: under, at most his top
    assert points[6] == pytest.approx((0.0, 0.0, (2.4 - origin - m0) / scale), abs=1e-4)   # land reset the side
    assert _camera_point(built, 0x04, head) == (pytest.approx(head), True)    # not the player

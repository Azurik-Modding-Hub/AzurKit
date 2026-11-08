"""The simulator (``devkit.sim``, Step 4.13a: Modkit's L0-L3, its search and explorer): what each level runs and
judges, on the USA image's XBE (L2) or on synthetic snapshots and XBEs (L3; no game bytes).

What simulator Level 2 can and can't judge (Modkit's Step 2.10).  L2 runs the game's own code on a named fake
state and asserts where the game consumes the value, so it would have caught four of the catalogued patches
whose bytes landed with no in-game effect (the ``azurik-game-reference`` skill).  Replayed from vanilla, each
leaves its L2 measurement at the vanilla value, so the k-times-vanilla check of its behavior test fails:

1.  jump v1: 9.0 -> 9.0·k at the five MOV imm32 sites 0x84ED3, 0x856D4, 0x890EA, 0x89126 and 0x8D322, which set
    air control; the launch speed is the FSQRT at 0x89160;
4.  air control v1: the same five sites; airborne_reinit 0x83F90 rewrites entity+0x140 on every ordinary
    takeoff;
2.  flap v1: the FADD at 0x896EA adds 8.0·k (replayed by scaling the 8.0 it reads, 0x1A25C0); it sits in the
    airborne tick behind the cheat-buttons flag 0x40, and wing_flap never reads it;
10. XBR Editor edits to Flaps that landed in config.xbr's TOC entry 1 (attacks_anims, labelled
    armor_properties_unused until AZ-113: the attacks table, not armor), replayed by overwriting its whole cell
    grid 0x5094-0x6894; the loader 0x3C700 reads the 0x3000 grid.  Its asset-load stub hands over that grid by a
    fixed offset, so this case pins the grid the stub picks; the game's own lookup of config/armor_properties
    doesn't run.

Blind spots are what L2 can't judge.  ``devkit/sim/data/sim_blind_spots.toml`` lists them with the vanilla hash
of each range: a probe may stub only a listed function, and ``Sim`` refuses a build that changes a listed range
unless the test is signed off (:func:`xemu_signoff`) by an xemu session the file lists with that range.  A pass
means "the patched code computes this from this state", not "the game does this".
"""

from __future__ import annotations

import math
import os
import struct
import typing
from unittest import mock

import pytest

from azurkit.core import facts, gate, iso
from devkit.sim.l2 import (BOOT_TICK, JUMP_INIT, SHIELD_2, STANDING, PlayerSim, ProbeError, Sim, armor_slots,
                           blind_spots)
from devkit.sim.ports import apply_pack, get_pack, parse_xbe_sections

K = 2.0                    # the slider value each historical patch was tried at
AIR_CONTROL_IMM32 = (0x84ED3, 0x856D4, 0x890EA, 0x89126, 0x8D322)  # MOV [reg+0x140], 9.0
FLAP_V1_ADDEND = 0x1A25C0  # f32 8.0: what the v1 flap FADD at 0x896EA adds
TOC1_GRID = slice(0x5094, 0x6894)  # config.xbr TOC entry 1's 24 x 16 cells (the attacks table)


@pytest.fixture(scope="module")
def usa(usa_iso) -> dict[str, bytes]:
    """The USA image's ``default.xbe`` and ``gamedata/config.xbr``."""
    with iso.Reader(usa_iso) as r:
        return {name: bytes(r.read(name)) for name in ("default.xbe", "gamedata/config.xbr")}


def xemu_signoff(session: str):
    """Sign a test off by the xemu session ``session`` (sim_blind_spots.toml's ``[signoffs]``): its run sets
    ``Sim.signoff``, so a build that changes a blind spot that session lists loads (Modkit's marker)."""
    def mark(test):
        test.xemu_signoff = session
        return test
    return mark


@pytest.fixture(autouse=True)
def _xemu_signoff(request, monkeypatch):
    if session := getattr(request.function, "xemu_signoff", None):
        monkeypatch.setattr(Sim, "signoff", session)


def va_to_file(va: int) -> int:
    return facts.of(gate.USA).offset(va)


def _scaled(xbe: bytes, vas: tuple[int, ...], vanilla: float) -> bytes:
    """``xbe`` with the f32 ``vanilla`` at each of ``vas`` times K."""
    out = bytearray(xbe)
    for va in vas:
        assert struct.unpack_from("<f", out, va_to_file(va))[0] == vanilla, hex(va)
        struct.pack_into("<f", out, va_to_file(va), vanilla * K)
    return bytes(out)


def _jump_vz(xbe: bytes) -> float:
    return PlayerSim(xbe).jump().vz


def _air_control(xbe: bytes) -> tuple[float, float]:
    return tuple(PlayerSim(xbe, player).jump().air_control for player in (STANDING, SHIELD_2))


def _flap_next_tick(xbe: bytes) -> float:
    sim = PlayerSim(xbe, SHIELD_2)
    sim.jump()
    sim.flap()
    return sim.fall()


def test_historical_no_effect_patches_fail_the_ratio_checks(usa):
    """Cases 1, 2, 4 and 10 at k = 2: each L2 measurement stays at
    vanilla, so no ratio check passes them."""
    vanilla, config = usa["default.xbe"], usa["gamedata/config.xbr"]
    five_sites = _scaled(vanilla, AIR_CONTROL_IMM32, 9.0)
    toc1 = bytearray(config)
    toc1[TOC1_GRID] = b"\xA5" * len(config[TOC1_GRID])
    for case, measure, before, after in (
            (1, _jump_vz, vanilla, five_sites),
            (4, _air_control, vanilla, five_sites),
            (2, _flap_next_tick, vanilla, _scaled(vanilla, (FLAP_V1_ADDEND,), 8.0)),
            (10, lambda xbr: armor_slots(vanilla, xbr), config, bytes(toc1))):
        assert measure(after) == measure(before), case


@xemu_signoff("xemu-oracle-2026-10-09")
def test_blind_spot_builds_need_an_xemu_signoff(usa):
    """A probe may stub only a listed function.  Vanilla loads, but
    without a sign-off a build that changes any byte of a listed
    blind spot doesn't; and a sign-off unlocks only the spots its
    session lists.  This test's sign-off names the roll and skip-logo
    session, which lists none, so fps_unlock (its solver sites are in
    0x47380) loads only once that session lists 0x47380."""
    vanilla = usa["default.xbe"]
    with pytest.raises(ProbeError, match="stub 0x89060 isn't listed"):
        Sim(vanilla).call(BOOT_TICK, args=(0,), stubs={JUMP_INIT: 0})
    with mock.patch.object(Sim, "signoff", None):
        for spot in blind_spots()[0].values():
            xbe = bytearray(vanilla)
            xbe[va_to_file(spot.va + spot.size - 1)] ^= 0xFF
            with pytest.raises(ProbeError, match=rf"\({spot.va:#x} "):
                Sim(bytes(xbe))
    fps = bytearray(vanilla)
    apply_pack(get_pack("fps_unlock"), fps, {})
    with pytest.raises(ProbeError, match=r"0x47380 .*'xemu-oracle-2026-10-09' doesn't"):
        Sim(bytes(fps))
    with mock.patch.dict(blind_spots()[1], {Sim.signoff: frozenset({0x47380})}):
        Sim(bytes(fps))


def _slider_ends(s, setting: str) -> float:
    """A slider's value at ``setting``: its default, its track's ends, or a span past each (D23: the ends are
    display hints), held to what its encoding takes (a whole slider's range, D45; config.xbr's int32)."""
    lo, hi = s.slider_min, s.slider_max
    value = {"default": s.default, "min": lo, "max": hi, "below min": lo - (hi - lo),
             "above max": hi + (hi - lo)}[setting]
    if s.whole:
        value = min(max(round(value), s.whole[0]), s.whole[1])
    return value


def test_every_pack_at_its_slider_ends_builds_a_sound_xbe_whose_patched_code_is_well_formed(usa):
    """Modkit's behavior tests 3 and 4 (Steps 2.5 and 2.7) over every pack at once, each slider at its default,
    its track's ends and a span past each: L0 finds the build sound (sections in bounds and apart, the entry point
    in .text, the image size, kernel thunks by ordinal 1..378, TLS in a section; config.xbr parses) and L1 its
    patched code well formed (it decodes, branches land on instructions in mapped code, shims keep the replaced
    callee's ret N, floats are finite, Pentium III only).  L0 flags a thunk slot with bits above its ordinal: the
    loader indexes the export table with the low 31 bits, so bit 16 set on NtClose (187) is ordinal 65723."""
    from azurkit.edits import layer
    from azurkit.tools.mods import PACKS, engine
    from devkit.sim import l1, static

    floats = [s.va for p in PACKS.values() for s in p.sliders()
              if isinstance(s, engine.ParametricPatch) and not s.virtual]
    for setting in ("default", "min", "max", "below min", "above max"):
        layers = []
        for pack in PACKS.values():
            layers.append(engine.plan(pack, gate.USA, usa, {s.name: _slider_ends(s, setting) for s in pack.sliders()},
                                      [c for la in layers for c in la.claims]))
        built, _ = layer.compose(usa, layers)
        xbe = bytes(built["default.xbe"])
        assert xbe != usa["default.xbe"] and "SHIMS" in {s["name"] for s in parse_xbe_sections(xbe)[1]}, setting
        assert static.check(xbe, {"gamedata/config.xbr": bytes(built["gamedata/config.xbr"])}) == [], setting
        assert l1.check(usa["default.xbe"], xbe, floats) == [], setting
    thunk = bytearray(usa["default.xbe"])
    struct.pack_into("<I", thunk, va_to_file(0x18F3A0), 0x80000000 | 0x10000 | 187)
    assert static.check(bytes(thunk)) == ["kernel thunk 0x18F3A0 imports ordinal 65723, not 1..378"]


def test_l1_and_l2_refuse_a_europe_xbe_by_name():
    """Step RG.5 (D146): the simulator's VAs, stubs and blind spots are
    the USA release's, so L1 and L2 refuse a Europe XBE (told by its
    kernel-thunk address) naming the release, instead of judging
    Europe's code at USA addresses."""
    from devkit.sim import l1

    europe = bytearray(0x200)
    europe[:4] = b"XBEH"
    struct.pack_into("<I", europe, 0x158, facts.of(gate.EUROPE).thunks ^ facts.THUNK_KEY)
    for run in (lambda: l1.check(bytes(europe), bytes(europe)), lambda: Sim(bytes(europe))):
        with pytest.raises(ValueError, match="USA release only; this XBE is the Europe release"):
            run()


def _l3_snapshot(tmp_path, code: dict[int, bytes], meta: dict, regs: dict | None = None):
    """A synthetic L3 snapshot (no game bytes): ``code`` at its VAs; the player entity 0x100000 (its
    scheduler 0x100800, event time 12.5, velocity (0.5, 0, -1), critter 0x103000 in cell 3 of the world's cells
    0x102000, HP 200 of 250, body centre (5, 6, 7));
    the scene 0x101000 with pd 0x101100 (the critter's too), request block 0x101200, world 0x101300, armor
    manager 0x101400 (its slot 0x101500: Flaps 2), inventory 0x101600 (element levels 1, 2, 0, 3) and one latch
    "Gate" = 1 (map 0x101800, head 0x101820, node 0x101840); ControllerState[0] (active index 4); the page
    tables' self-map over all of it."""
    from devkit.sim import l3

    ent, crit = 0x100000, 0x103000
    pages = {va: bytearray(0x1000) for va in (0x8C000, 0x85000, 0x18F000, 0x100000, 0x101000, 0x102000, crit,
                                             0x198000, 0x1A7000, 0x1BF000, 0x37B000, 0x38C000, 0x390000,
                                             l3.PDE_BASE, l3.PTE_BASE)}
    for va, b in code.items():
        pages.setdefault(va & ~0xFFF, bytearray(0x1000))[va & 0xFFF:(va & 0xFFF) + len(b)] = b
    struct.pack_into("<I", pages[l3.PDE_BASE], 0, 0x1001)
    for va in pages:
        if va < 0x400000:
            struct.pack_into("<I", pages[l3.PTE_BASE], (va >> 12) * 4, va | 1)
    for va, fmt, *v in ((ent + 0x0C, "<I", 0x100800), (ent + 0x18, "<d", 12.5), (ent + 0x20, "<I", crit),
                        (ent + 0x24, "<3f", 0.5, 0.0, -1.0), (ent + 0x40, "<I", 0x3000),   # a size to allocate
                        (crit + 0x154, "<I", 0x101100),
                        (crit + 0x158, "<I", 0x102000 + 3 * 0xB4), (crit + 0x15C, "<3f", 5.0, 6.0, 7.0),
                        (crit + 0x210, "<2i", 200, 250), (l3.ACTIVE_PAD, "<I", 4), (l3.SCENE_PTR, "<I", 0x101000),
                        (0x10102C, "<I", 0x101100), (0x1011D4, "<I", 0x101300), (0x1011D8, "<I", 0x101200),
                        (0x101328, "<I", 0x102000), (0x1011CC, "<I", 0x101400), (0x1011E0, "<2I", 0x101600, 0x101800),
                        (0x101420, "<I", 0x101500), (0x101538, "<i", 2), (0x101604, "<4i", 1, 2, 0, 3),
                        (0x101800, "<I", 0x101820), (0x101824, "<I", 0x101840), (0x101850, "<5s", b"Gate"),
                        (0x1018A0, "<I", 0x1018B0), (0x1018B0, "<I", 1)):
        struct.pack_into(fmt, pages[va & ~0xFFF], va & 0xFFF, *v)
    path = tmp_path / "s.l3snap"
    def read(va, n):   # page by page: a run spans several
        return b"".join(bytes(pages[p & ~0xFFF][max(va, p) & 0xFFF:][:min(va + n, p + 0x1000) - max(va, p)])
                        for p in range(va & ~0xFFF, va + n, 0x1000))
    info = l3.write_snapshot(read, path, {"fs_base": 0x80035BDC, **(regs or {})},
                             {"entity": ent, "at": "update", **meta},
                             [(va, 0x1000, read) for va in sorted(pages) if va >= l3.HIGH and va not in (l3.PDE_BASE, l3.PTE_BASE)])
    return path, info


def _rel(src: int, dst: int) -> bytes:
    return struct.pack("<i", dst - (src + 5))


def _l3_walker(folder, code=None, **meta):
    """A synthetic snapshot ``s`` in ``folder`` (more metadata: ``meta``; more code by VA: ``code``) whose player
    update moves the body centre's x by the stick's y, sets the state to the Y latch from before the tick (latching
    a held Y), consumes a place request and runs an input builder that copies the camera direction it reads at
    0x85276 to entity+0x60.  The player also stands in state 0's timer 0.25 on a 0.8 slope (the contact normal) with
    a fall reference of 3.5, in animation 9, with the gauge at 0.6 of a Level 3 slot (Step TD.0's fields)."""
    upd, ib = 0x8C230, 0x85270
    body = bytes.fromhex(
        "d9059cbe3700" "8b4120" "d8805c010000" "d9985c010000"  # body x += stick y
        "0fb615e3be3700" "899194000000"                         # state = the Y latch before the tick
        "833dbcbe370000" "7407" "c605e3be370001"                # Y down: latch it
        "c7050812100000000000")                                 # [R+8] = 0 (the place request consumed)
    body += b"\xe8" + _rel(upd + len(body), ib)
    body += b"\xe9" + _rel(upd + len(body), 0x8C3F1)
    builder = bytes.fromhex("83ec20" "909090"                   # 0x85276: the camera direction
                            "8b542414" "895160" "8b542418" "895164" "83c420" "c3")   # -> ent+0x60, +0x64
    fields = {0x10009C: struct.pack("<f", 0.25), 0x1000B8: struct.pack("<3f", 0.0, 0.6, 0.8),
              0x100164: struct.pack("<f", 2.25), 0x100168: struct.pack("<f", 3.5), 0x103200: struct.pack("<i", 9),
              0x101424: struct.pack("<f", 0.6), 0x101508: struct.pack("<i", 3)}
    return _l3_snapshot(folder, {upd: body, 0x8C3F1: b"\xc3", ib: builder, **fields, **(code or {})},
                        {"label": "s", **meta})[0]


class _ReachX:
    """A goal the pool's workers build by name: the body centre's x at least ``x``, guided straight ahead."""
    settle = 0

    def __init__(self, x: float):
        self.x = x

    def reached(self, r):
        return r.pos[0] >= self.x

    def cost(self, r):
        return max(0.0, self.x - r.pos[0]) / 7

    def toward(self, r):
        return 0.0, False

    def cell(self, r):
        return (round(r.pos[0] * 4), r.state)

    def zone(self, r):             # the explorer's guide: no zones
        return None


def _l3_xbe(text: bytes, ordinals: list[int], extra=()) -> bytes:
    """A stand-in XBE (no game bytes) for :func:`_l3_snapshot`: ``.text`` = ``text`` at 0x8C000 and ``.rdata``
    at 0x18F000, both executable and read-only, the kernel thunk table at 0x18F400 importing ``ordinals``, then
    each ``extra`` section ``(name, va, data, flags)``."""
    base, x = 0x10000, bytearray(0x3000)
    x[:4] = b"XBEH"
    struct.pack_into("<I", x, 0x104, base)
    struct.pack_into("<I", x, 0x10C, 0x200000)
    struct.pack_into("<II", x, 0x11C, 2 + len(extra), base + 0x200)
    struct.pack_into("<I", x, 0x158, 0x18F400 ^ facts.THUNK_KEY)
    secs = [(b".text", 0x8C000, 0x6, 0x1000, 0x1000), (b".rdata", 0x18F000, 0x6, 0x2000, 0x1000)]
    for name, va, data, flags in extra:
        secs.append((name.encode(), va, flags, len(x), len(data)))
        x += data
    for i, (name, va, flags, raw, size) in enumerate(secs):
        struct.pack_into("<6I", x, 0x200 + 56 * i, flags, va, size, raw, size, base + 0x400 + 8 * i)
        x[0x400 + 8 * i:0x400 + 8 * i + len(name)] = name
    x[0x1000:0x2000] = text
    for i, o in enumerate(ordinals):
        struct.pack_into("<I", x, 0x2400 + 4 * i, 0x80000000 | o)
    return bytes(x)


def test_l3_snapshot_store_and_a_step_with_the_scheduler_clock_allocation_and_fs(tmp_path):
    """Steps X.5-X.6, X.10 (D168, D170): a snapshot read through the page tables' self-map round-trips with its
    metadata, mode 0600 (the store's refusal and the formats: test_xemu_harness); a step runs the player update
    with the scheduler's now set from the event time entity+0x18, NtAllocateVirtualMemory mapping a new region and
    FS on the KPCR, and a reset unmaps that region so the rerun allocates the same one."""
    from unicorn import UcError

    from devkit.sim.l3 import L3, read_meta, read_snapshot

    ent, kernel = 0x100000, 0x80016000
    upd = 0x8C230
    code = bytes.fromhex(
        "53" "89cb" "6a04" "6800200000" "8d4340" "50" "6a00" "8d4344" "50"  # NtAllocateVirtualMemory(
        "ff1524f41800"                                    # &ent+0x44, 0, &ent+0x40, reserve, rw)
        "8b4344" "c70034120000"                           # *base = 0x1234
        "8b430c" "dd4010" "dd5b50"                        # ent+0x50 = sched now (f64)
        "64a128000000" "894358" "5b")                     # ent+0x58 = fs:[0x28]
    code += b"\xe9" + _rel(upd + len(code), 0x8C3F1)     # out through the update's RET
    store_dir = tmp_path / "store"
    store_dir.mkdir(mode=0o700)
    path, info = _l3_snapshot(store_dir, {upd: code, 0x8C3F1: b"\xc3", 0x18F424: struct.pack("<I", kernel)},
                              {"level": "levels/water/w1"})
    assert (info["pages"], info["runs"]) == (13, 10)
    assert os.name != "posix" or path.stat().st_mode & 0o777 == 0o600   # modes say nothing on Windows
    assert read_meta(path) == {"entity": ent, "at": "update", "level": "levels/water/w1"}
    snap = read_snapshot(path)
    assert snap.meta == read_meta(path) and [va for va, _ in snap.runs][:3] == [0x85000, 0x8C000, 0x100000]

    sim = L3(snap, {kernel: "NtAllocateVirtualMemory"})
    sim.step()
    base = sim.u32(ent + 0x44)
    assert base and sim.u32(base) == 0x1234 and sim.u32(ent + 0x40) == 0x3000
    assert struct.unpack("<d", sim.read(ent + 0x50, 8))[0] == 12.5
    assert sim.kernel_calls == {"NtAllocateVirtualMemory": 1}
    sim.reset()
    with pytest.raises(UcError):
        sim.read(base, 4)
    sim.step()
    assert sim.u32(ent + 0x44) == base and sim.u32(base) == 0x1234


def test_a_cleanup_never_deletes_a_snapshot_the_reach_engine_a_running_run_or_a_proof_starts_from(
        tmp_path, monkeypatch, capsys):
    """AZ-720 (Step X.83): D658's cleanup deleted the start a running reach run read by its bare label and every
    start ``proofs.jsonl`` names.  The hold keeps every snapshot in ``reach-live`` and its ``reach-live-*`` clones,
    each one a running command line names (a bare label or a file's path) and each one a checkout's ``proofs.jsonl``
    starts from; a check of a folder or the store names each held one under it, and a loose one is free.  The CLI's
    check, like prune's, reads every worktree's ``proofs.jsonl`` (the review's D1: it read only its own)."""
    import json
    import subprocess

    from devkit.sim import l3_hold
    from devkit.sim.l3_hold import PROOFS, blocking, held, worktrees

    store = tmp_path / "store"
    for rel in ("reach-live/r216c-w1-k0-1.l3snap", "reach-live-hold-2026-10-27/r216c-w1-k0-1.l3snap",
                "x7/x7-w1-k0-205806.l3snap", "x7/x99-proof-k0-140435.l3snap", "td1/by-path.l3snap",
                "reach-live-old.l3snap", "x7/loose-k0-1.l3snap"):
        (store / rel).parent.mkdir(parents=True, exist_ok=True)
        (store / rel).write_bytes(b"")
    checkout, lane = tmp_path / "main", tmp_path / "lanes" / "x.99"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True, timeout=60)
    subprocess.run(["git", "-C", str(checkout), "worktree", "add", "-q", "--orphan", str(lane)], check=True, timeout=60)
    (lane / PROOFS).parent.mkdir(parents=True)
    (lane / PROOFS).write_text(json.dumps({"start": {"snapshot": {"label": "x99-proof-k0-140435"}}}) + "\nnot json\n",
                               encoding="utf-8")
    commands = ["nice -n 19 python scripts/reach_engine.py run w1 --plan a --snapshot x7-w1-k0-205806 --workers 16",
                f"python probe.py --start={store}/td1/by-path.l3snap"]

    holds = held(store, worktrees(checkout), commands)
    assert {p.relative_to(store).as_posix(): why.split(" ")[0] for p, why in holds.items()} == {
        "reach-live/r216c-w1-k0-1.l3snap": "in", "reach-live-hold-2026-10-27/r216c-w1-k0-1.l3snap": "in",
        "x7/x7-w1-k0-205806.l3snap": "named", "td1/by-path.l3snap": "named", "x7/x99-proof-k0-140435.l3snap": "a"}
    assert sorted(p.name for p, _ in blocking([store / "x7"], holds)) == ["x7-w1-k0-205806.l3snap",
                                                                        "x99-proof-k0-140435.l3snap"]
    assert len(blocking([store], holds)) == 5
    assert blocking([store / "x7" / "loose-k0-1.l3snap", store / "reach-live-old.l3snap"], holds) == []
    monkeypatch.setattr(l3_hold, "CHECKOUT", checkout)
    assert l3_hold.main(["--store", str(store), "--check", str(store / "x7" / "x99-proof-k0-140435.l3snap")]) == 1
    assert "lanes/x.99/" in capsys.readouterr().out


def test_l3_snapshot_reads_its_pages_from_one_physical_ram_dump_through_the_page_tables_it_holds(tmp_path):
    """Step X.22: ``ram_reader`` reads virtual memory out of a dump of guest RAM (the fork build's QMP
    xemu-dump-ram) through the page directory and tables in the dump itself: pages contiguous in VA but not in
    RAM, a 4 MiB page, the page tables' self-map; a frame no RAM backs goes to the gdbstub, a page that isn't
    present fails as an E14 does.  A snapshot written through it is the one the live (gdbstub) view writes."""
    from devkit.sim import l3

    ram, pd = bytearray(0x800000), 0x1000
    pages = {0x10000: 0x5000, 0x11000: 0x3000, 0x20000: 0x900000}   # VA -> frame (0x900000: past the dump)
    struct.pack_into("<3I", ram, pd, 0x2001, 0x400081, 0)            # PDE 0: a table at 0x2000; PDE 1: 4 MiB
    struct.pack_into("<I", ram, pd + 4 * (l3.PDE_BASE >> 22), pd | 1)   # the self-map
    for va, pa in pages.items():
        struct.pack_into("<I", ram, 0x2000 + 4 * (va >> 12), pa | 1)
    for pa in (0x3000, 0x5000):
        ram[pa:pa + 0x1000] = bytes([pa >> 12]) * 0x1000
    ram[0x400000:] = bytes(range(256)) * 0x4000
    mmio = bytes([0x99]) * 0x1000
    view = {**{va: bytes(ram[pa:pa + 0x1000]) for va, pa in pages.items() if pa < len(ram)}, 0x20000: mmio,
            l3.PDE_BASE: bytes(ram[pd:pd + 0x1000]), l3.PTE_BASE: bytes(ram[0x2000:0x3000]),
            **{0x400000 + o: bytes(ram[0x400000 + o:0x401000 + o]) for o in range(0, 0x400000, 0x1000)}}

    def live(va, n):   # the gdbstub's view, page by page
        out = b""
        while n:
            k = min(n, 0x1000 - (va & 0xFFF))
            if va & ~0xFFF not in view:
                raise OSError(f"read {va:#x}: b'E14'")
            out += view[va & ~0xFFF][va & 0xFFF:(va & 0xFFF) + k]
            va, n = va + k, n - k
        return out

    read = l3.ram_reader(ram, pd, lambda va, n: live(va, n))
    for va, n in ((0x10FF0, 0x20), (0x400123, 0x2000), (0x20004, 8), (l3.PDE_BASE, 0x1000), (l3.PTE_BASE, 0x1000)):
        assert read(va, n) == live(va, n)
    for reader, va in ((read, 0x30000), (l3.ram_reader(ram, pd), 0x20000)):
        with pytest.raises(OSError):
            reader(va, 4)
    store = tmp_path / "store"
    store.mkdir(mode=0o700)
    a, b = (l3.write_snapshot(r, store / f"{n}.l3snap", {}) for n, r in (("dump", read), ("live", live)))
    assert a == b and a["pages"] == 3 + 1024
    assert (store / "dump.l3snap").read_bytes() == (store / "live.l3snap").read_bytes()


def test_l3_a_code_poke_runs_the_new_bytes_and_a_reset_the_old(tmp_path):
    """Step X.7 (the engine review's 2.6 and 7.1): Unicorn 2.1.4 keeps running code it translated before a host
    write, so ``L3.write`` and ``reset`` drop the translations of what they rewrite: a poke of the update's
    immediate takes effect on the next step and a reset brings the old code back."""
    from devkit.sim.l3 import L3, read_snapshot

    ent, upd = 0x100000, 0x8C230
    code = bytes.fromhex("c7405011000000")                    # mov [eax+0x50], 0x11  (ECX = entity; EAX := ECX first)
    code = bytes.fromhex("89c8") + code + b"\xe9" + _rel(upd + 2 + 7, 0x8C3F1)
    store_dir = tmp_path / "store"
    store_dir.mkdir(mode=0o700)
    path, _ = _l3_snapshot(store_dir, {upd: code, 0x8C3F1: b"\xc3"}, {})
    sim = L3(read_snapshot(path), {})
    sim.step()
    assert sim.u32(ent + 0x50) == 0x11
    sim.write(upd + 5, b"\x22")                               # the immediate's low byte, after the code has run
    sim.step()
    assert sim.u32(ent + 0x50) == 0x22
    sim.reset()
    sim.step()
    assert sim.u32(ent + 0x50) == 0x11


def test_l3_a_runaway_step_still_stops_and_the_critical_sections_run_unhooked(tmp_path):
    """Step X.42: arming a step's timeout only stores its deadline (under a lock no thread waits on), and the
    watchdog's thread, looking every period, stops a step that never returns: ``L3Error`` within its timeout and a
    period, the watchdog disarmed.  RtlEnterCriticalSection and RtlLeaveCriticalSection run as guest code at their
    kernel addresses: EAX 0, the argument popped, no hook (no ``kernel_calls``), no taint."""
    import time

    from devkit.sim.l3 import L3, L3Error, read_snapshot

    ent, upd, kern = 0x100000, 0x8C230, 0x80016000
    code = bytes.fromhex("50" "ff1524f41800"                # RtlEnterCriticalSection(entity)  (EAX = ECX here)
                         "89c8" "51" "ff1528f41800"         # RtlLeaveCriticalSection(entity), EAX nonzero before
                         "894158")                          # ent+0x58 = EAX
    code = bytes.fromhex("89c8") + code + b"\xe9" + _rel(upd + 2 + len(code), 0x8C3F1)
    d = tmp_path / "store"
    d.mkdir(mode=0o700)
    path, _ = _l3_snapshot(d, {upd: code, 0x8C3F1: b"\xc3", 0x18F424: struct.pack("<2I", kern, kern + 0x100),
                               ent + 0x58: b"\xff" * 4}, {})
    sim = L3(read_snapshot(path), {kern: "RtlEnterCriticalSection", kern + 0x100: "RtlLeaveCriticalSection"})
    row = sim.step()
    assert (sim.u32(ent + 0x58), sim.kernel_calls, row.taint) == (0, {}, frozenset())
    sim.write(upd, b"\xeb\xfe")                               # jmp $: a runaway
    t0 = time.monotonic()
    with pytest.raises(L3Error, match="did not return within 200000 us"):
        sim.step(timeout_us=200_000)
    assert time.monotonic() - t0 < 5.0 and sim._wd.armed is None


def test_l3_refuses_another_builds_code_and_taints_what_it_does_not_model(tmp_path):
    """Step X.10: a snapshot whose code isn't the given XBE's is refused naming the section (the thunk slots the
    kernel filled aside); each step starts from the snapshot's MXCSR; and a run that reads what L3 doesn't model
    is tainted, row by row and in its saved states: a file read (zeros), a kernel clock (a data export, read
    through its thunk), an RDTSC (a virtual clock instead of host time), a high page (a zero page; its reader)
    and a kernel call L3 only stubs."""
    from devkit.sim.l3 import L3, read_snapshot

    upd, kern = 0x8C230, 0x80016000
    slot = {n: 0x18F400 + 4 * i for i, n in enumerate(("NtReadFile", "KeTickCount", "KeSetEvent"))}
    cases = [(b"\x6a\x00" * 8 + b"\xff\x15" + struct.pack("<I", slot["NtReadFile"]), {"read"}),
             (b"\xa1" + struct.pack("<I", slot["KeTickCount"]) + b"\x8b\x00", {"time"}),
             (b"\x0f\x31", {"rdtsc"}),
             (b"\xa1\x00\x00\x00\xfd", {f"high:{upd:#x}"}),
             (b"\x6a\x00" * 3 + b"\xff\x15" + struct.pack("<I", slot["KeSetEvent"]), {"kernel:KeSetEvent"}),
             (b"\x0f\xae\x1d" + struct.pack("<I", 0x100070), set())]          # stmxcsr [entity+0x70]
    for i, (code, taint) in enumerate(cases):
        code += b"\xe9" + _rel(upd + len(code), 0x8C3F1)
        thunks = {va: struct.pack("<I", kern + 0x10 * k) for k, va in enumerate(slot.values())}
        d = tmp_path / str(i)
        d.mkdir(mode=0o700)
        path, _ = _l3_snapshot(d, {upd: code, 0x8C3F1: b"\xc3", **thunks}, {}, {"mxcsr": 0x1FC0})
        snap = read_snapshot(path)
        xbe = _l3_xbe(bytes(dict(snap.runs)[0x8C000]), [219, 156, 145])
        sim = L3(snap, xbe)
        row = sim.step()
        assert (row.taint, sim.taint) == (frozenset(taint), taint), i
        if i == 0:
            state = sim.save()
            sim.reset()
            assert not sim.taint and sim.step().taint == {"read"}
            sim.reset(state)
            assert sim.taint == {"read"}
    assert sim.u32(0x100070) == 0x1FC0
    with pytest.raises(ValueError, match="the snapshot's .text differs from the XBE's in 1 bytes"):
        L3(snap, xbe[:0x1235] + b"\x01" + xbe[0x1236:])


def test_l3_names_each_fault_by_kind_and_site_and_each_kernel_taint_by_its_game_caller_and_file(tmp_path):
    """Step X.52: an ``L3Error`` names its site (a game assert by file and line, an unmapped access, a runaway by
    EIP, a player update that didn't run) and keeps it across a process boundary; a search's result tallies the
    rollouts each site ended.  A kernel call L3 doesn't model taints the run with its first caller in the game's own
    code (an EBP walk past the XAPI wrapper that made it and the C-library frame that called that) and, for
    NtCreateFile, the file it opens, kept in the run's saved states."""
    import pickle

    from devkit.sim.l3 import L3, L3Error, read_snapshot
    from devkit.sim.l3_search import Limits, search

    upd, crt, wrap, kern, oa = 0x8C230, 0xE9000, 0xE1000, 0x80016000, 0x101A00
    name = b"\\Device\\Harddisk0\\Partition1\\TDATA\\x52.bin"
    body = b"\xe8" + _rel(upd, crt)                                   # the update calls the C library (fopen's kind)
    body += b"\xe9" + _rel(upd + len(body), 0x8C3F1)
    fopen = bytes.fromhex("55" "89e5") + b"\xe8" + _rel(crt + 3, wrap) + bytes.fromhex("89ec" "5d" "c3")   # -> XAPI
    wrapper = (bytes.fromhex("55" "89e5") + b"\x6a\x00" * 6           # push ebp; mov ebp, esp; 6 arguments
               + b"\x68" + struct.pack("<I", oa) + b"\x6a\x00" * 2    # ObjectAttributes, DesiredAccess, FileHandle
               + bytes.fromhex("ff1524f41800" "89ec" "5d" "c3"))      # call [NtCreateFile]; leave; ret
    code = {upd: body, 0x8C3F1: b"\xc3", crt: fopen, wrap: wrapper, 0x18F424: struct.pack("<I", kern),
            0xA9000: b"\xc3", oa: struct.pack("<3I", 0, oa + 0x10, 0),     # OBJECT_ATTRIBUTES, its ANSI_STRING
            oa + 0x10: struct.pack("<2HI", len(name), len(name) + 1, oa + 0x20), oa + 0x20: name, oa + 0x80: b"t.cpp\0"}
    d = tmp_path / "store"
    d.mkdir(mode=0o700)
    path, _ = _l3_snapshot(d, code, {})
    sim = L3(read_snapshot(path), {kern: "NtCreateFile"})
    row = sim.step()
    want = {"kernel:NtCreateFile": {f"{upd + 5:#x} {name.decode()}"}}
    assert row.taint == {"kernel:NtCreateFile"} and sim.taint_at == want
    state = sim.save()
    sim.reset()
    assert sim.taint_at == {}
    sim.reset(state)
    assert sim.taint_at == want
    errs = []
    for poke, site, timeout in ((b"\xa1\x00\x00\x50\x00", f"unmapped@{upd:#x}", None),     # mov eax, [0x500000]
                                (b"\xeb\xfe", f"runaway@{upd:#x}", 200_000),                 # jmp $
                                (b"\xc3", "no player update", None),                         # ret: no update's RET
                                (b"\x6a\x07\x68" + struct.pack("<I", oa + 0x80) + b"\xe8" + _rel(upd + 7, 0xA9000),
                                 "assert t.cpp:7", None)):                                   # the game asserts
        sim.reset()
        sim.write(upd, poke)
        with pytest.raises(L3Error) as e:
            sim.step(timeout_us=timeout)
        assert e.value.site == site and pickle.loads(pickle.dumps(e.value)).site == site
        errs.append(e.value)

    class Faulting(_Toy):          # each of the first four jumps raises one of those errors
        def step(self, pad):
            if "y" in pad.buttons and errs:
                raise errs.pop(0)
            return super().step(pad)
    sites = [e.site for e in errs]
    res = search(Faulting(), Faulting().save(), _ToyRow((0.0, 0.0, 1.0), 0, 200), _ToyGoal(),
                 Limits(steps=20_000, ticks=300, seg=4, hold=3), cam=1.2, seed=1)
    assert res.faults == 4 and res.summary()["fault_sites"] == dict.fromkeys(sorted(sites), 1)


def test_a_branch_that_takes_a_level_exit_ends_there_with_no_fault_or_taint_and_the_verdict_counts_it(tmp_path):
    """Step X.52b: a levelSwitch's fire (0x6F050, the switch in EDI) is on its step's row (``Row.exit``: the level
    and movie it posts), the tick run to its end, and in ``L3.fires`` until a reset; a step that reaches the level's
    unload 0x542E0 with flag 0 (a level exit) stops at its entry (``LevelExit``, site ``level exit``: nothing after
    it runs, nothing taints), with flag 1 (a death) it runs on.  A search and the explorer end a branch on a fire's
    row (the goal tests it first) or at that stop, count it by the level it loads, never as a fault or a taint,
    and a miss's verdict names those branches."""
    from devkit.sim import l3, l3_explore as X
    from devkit.sim.l3 import L3, LevelExit, read_snapshot
    from devkit.sim.l3_search import Limits, exits_text, search

    upd, ls, scene, mark = 0x8C230, 0x101A00, 0x101000, bytes.fromhex("c7055800100001000000")   # [ent+0x58] = 1
    calls = {"fire": (b"\xbf" + struct.pack("<I", ls), l3.FIRE),                     # mov edi, switch; call FIRE
             "exit": (b"\x6a\x00\x68" + struct.pack("<I", scene), l3.UNLOAD),        # UNLOAD(scene, 0)
             "death": (b"\x6a\x01\x68" + struct.pack("<I", scene), l3.UNLOAD)}       # UNLOAD(scene, 1)
    got = {}
    for name, (pre, to) in calls.items():
        body = pre + b"\xe8" + _rel(upd + len(pre), to) + mark
        body += b"\xe9" + _rel(upd + len(body), 0x8C3F1)
        d = tmp_path / name
        d.mkdir(mode=0o700)
        path, _ = _l3_snapshot(d, {upd: body, 0x8C3F1: b"\xc3", l3.FIRE: b"\xc3", l3.UNLOAD: b"\xc2\x08\x00",
                                   ls + 0x18: struct.pack("<2I", 0, ls + 0x40), ls + 0x40: b"levels/x\0"}, {})
        sim = L3(read_snapshot(path), {})
        try:
            row = sim.step()
            got[name] = (row.exit, list(sim.fires), sim.u32(0x100058))
        except LevelExit as e:
            got[name] = (e.site, sorted(sim.taint), sim.u32(0x100058))
        sim.reset()
        assert sim.fires == []
    assert got == {"fire": (("levels/x", None), [(0, "levels/x", None)], 1), "exit": ("level exit", [], 0),
                   "death": (None, [], 1)}

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int
        zone: str | None = None
        flaps: int = 0
        exit: tuple | None = None

    class Leaving(_Toy):        # east of x = 1 a levelSwitch fires; west of x = -0.3 the step reaches the unload
        def step(self, pad):
            r = super().step(pad)
            if r.pos[0] < -0.3:
                raise LevelExit("planted")
            return Row(*r, exit=("levels/x", None) if r.pos[0] > 1.0 else None)

    class East(_ToyGoal):       # x at least ``x``, guided east (the player faces (-sin h, cos h))
        settle = 0

        def __init__(self, x):
            self.x = x

        def reached(self, r):
            return r.pos[0] >= self.x

        def cost(self, r):
            return max(0.0, self.x - r.pos[0]) / 7

        def toward(self, r):
            return -math.pi / 2, False

        def zone(self, r):
            return None
    row0, lim = _ToyRow((0.0, 0.0, 1.0), 0, 200), Limits(steps=3000, ticks=300, seg=4, hold=3)
    sim = Leaving()
    assert search(sim, sim.save(), row0, East(1.2), lim, seed=1).reached     # the fire's row is in the goal
    res = search(sim, sim.save(), row0, East(5.0), lim, seed=1)
    assert not res.reached and res.faults == 0 and not res.taint and set(res.exits) == {"levels/x", "unload"}
    assert res.why == f"the step budget ran out; {exits_text(res.exits)}" and res.summary()["exits"] == res.exits
    ex = X.explore(sim, sim.save(), row0, East(5.0), X.Limits(steps=3000), seed=1)
    assert not ex.found and ex.faults == 0 and not ex.taint and set(ex.exits) == {"levels/x", "unload"}
    n = sum(ex.exits.values())
    assert X._verdict([ex.summary()]) == f"not found within budget; {n} branches fired levels/x " \
        f"({ex.exits['levels/x']}), unload ({ex.exits['unload']})"


def test_l3_rtlinitansistring_fills_the_ansi_string_as_the_kernel_does_and_taints_nothing(tmp_path):
    """Step R1.22a (AZ-381): RtlInitAnsiString(dest, src) sets dest's Length to the source's strlen (here a
    string across a page boundary), MaximumLength to one more and Buffer to the source; a NULL source zeroes all
    three; it pops its two arguments and the run stays untainted."""
    from devkit.sim.l3 import L3, read_snapshot

    ent, upd, kern, src = 0x100000, 0x8C230, 0x80016000, 0x104FF8
    text = b"z:\\gamedata\\level.xbr"
    code = bytes.fromhex("53" "89cb"
                         "68" + struct.pack("<I", src).hex() + "8d4360" "50" "ff1524f41800"   # (&ent+0x60, src)
                         "6a00" "8d4368" "50" "ff1524f41800" "5b")                            # (&ent+0x68, NULL)
    code += b"\xe9" + _rel(upd + len(code), 0x8C3F1)
    d = tmp_path / "store"
    d.mkdir(mode=0o700)
    path, _ = _l3_snapshot(d, {upd: code, 0x8C3F1: b"\xc3", 0x18F424: struct.pack("<I", kern),
                               ent + 0x68: b"\xff" * 8, src: text[:8], src + 8: text[8:] + b"\0"}, {})
    sim = L3(read_snapshot(path), {kern: "RtlInitAnsiString"})
    row = sim.step()
    assert sim.read(ent + 0x60, 16) == struct.pack("<2HI", len(text), len(text) + 1, src) + bytes(8)
    assert (row.taint, sim.kernel_calls) == (frozenset(), {"RtlInitAnsiString": 2})


def test_l3_overlay_runs_a_builds_code_sections_and_config_cells_on_a_vanilla_snapshot(tmp_path):
    """Step X.11 (D173's T6): an overlay lays a build over a vanilla snapshot: the bytes it changes in a section
    (a code immediate), a section it appends (SHIMS, mapped where the loader puts it), the world clock's quantum
    the game copied out of 0x198410 into the player's scheduler (fps_unlock's 1/F), and the config cells the
    game read at load (garret4's runSpeed in its CritterData, air shield 1's Flaps in the armor slot vector); a
    reset keeps the overlay.  Refused by name: a changed byte the snapshot holds otherwise than vanilla's loader
    put it (live .data), an appended section over a page the snapshot maps, a config slider it can't poke."""
    from devkit.sim import overlay
    from devkit.sim.l3 import L3, read_snapshot

    ent, upd, shims = 0x100000, 0x8C230, 0x200000
    code = bytes.fromhex("9090909090909090"                        # (L3 hooks the entry's first bytes)
                         "89c8" "c7405011000000"                      # mov eax, ecx; mov [eax+0x50], 0x11
                         "8b5020" "8b9278010000" "8b5240" "895054"     # [eax+0x54] = [[[eax+0x20]+0x178]+0x40]
                         "8b15d4c43800" "8b5238" "895058")             # [eax+0x58] = the first slot's Flaps
    code += b"\xe9" + _rel(upd + len(code), 0x8C3F1)
    slot = 0x38C600
    q30, q60 = struct.pack("<f", 1 / 30), struct.pack("<f", 1 / 60)    # the world clock's quantum, and its copy
    planted = {upd: code, 0x8C3F1: b"\xc3", 0x103178: struct.pack("<I", 0x102800), 0x198410: q30, 0x10080C: q30,
               0x102840: struct.pack("<f", 7.0), 0x38C4D4: struct.pack("<II", slot, slot + 0x40),
               slot: struct.pack("<I", 0x38C700), slot + 0x38: struct.pack("<i", 1), 0x38C700: b"air_shield_1\0"}
    d = tmp_path / "store"
    d.mkdir(mode=0o700)
    snap = read_snapshot(_l3_snapshot(d, planted, {})[0])
    text = bytes(dict(snap.runs)[0x8C000])
    data = (".data", 0x1A7000, bytes(0x1000), 0x7)                  # the game since wrote 4 at 0x1A7AE4
    clock = ("CLOCK", 0x198000, bytes(0x410) + q30 + bytes(0xBEC), 0x2)
    vanilla = _l3_xbe(text, [], [data, clock])
    hop = upd + len(code) - 5                                          # the build jumps into its SHIMS instead
    built = bytearray(text)
    built[upd - 0x8C000 + 13] = 0x22
    built[hop - 0x8C000:hop - 0x8C000 + 5] = b"\xe9" + _rel(hop, shims)
    stub = bytes.fromhex("c7405c33000000") + b"\xe9" + _rel(shims + 7, 0x8C3F1)   # [eax+0x5C] = 0x33
    cells = (("critters_critter_data", "garret4", "runSpeed", 14.0), ("armor_properties", "air_shield_1", "Flaps", 3.9))
    ov = overlay.Overlay(_l3_xbe(bytes(built), [], [data, clock[:2] + (bytes(0x410) + q60 + bytes(0xBEC), 0x2),
                                                    ("SHIMS", shims, stub, 0x6)]), cells)

    def run(sim):
        sim.step()
        return (sim.u32(ent + 0x50), struct.unpack("<f", sim.read(ent + 0x54, 4))[0], sim.u32(ent + 0x58),
                sim.u32(ent + 0x5C))
    sim = L3(snap, vanilla, overlay=ov)
    assert run(sim) == (0x22, 14.0, 3, 0x33) and sim.overlay is ov and len(ov.sha12) == 12
    assert sim.read(0x198410, 4) == sim.read(0x10080C, 4) == q60
    sim.reset()
    assert run(sim) == (0x22, 14.0, 3, 0x33)
    assert run(L3(snap, vanilla)) == (0x11, 7.0, 1, 0)
    with pytest.raises(ValueError, match=r"otherwise than vanilla's loader put them \(.data: 1\)"):
        L3(snap, vanilla, overlay=ov._replace(xbe=_l3_xbe(bytes(built), [], [
            (".data", 0x1A7000, bytes(0xAE4) + b"\x05" + bytes(0x51B), 0x7), clock, ("SHIMS", shims, stub, 0x6)])))
    with pytest.raises(ValueError, match="SHIMS section lands on 0x390000, a page the snapshot or L3 maps"):
        L3(snap, vanilla, overlay=ov._replace(xbe=_l3_xbe(bytes(built), [], [data, clock,
                                                                              ("SHIMS", 0x390000, stub, 0x6)])))
    assert overlay.build(vanilla, {"air_shield_flaps": {"air_shield_2_flaps": 4}}) == overlay.Overlay(
        vanilla, (("armor_properties", "air_shield_2", "Flaps", 4.0),))
    with pytest.raises(ValueError, match="player_max_hp.starting_hp: config.xbr settings_foo/initial hp/Value is not"):
        overlay.build(vanilla, {"player_max_hp": {"starting_hp": 50}})


def test_l3_serves_the_stream_modules_file_reads_from_the_disc_and_polls_them_between_steps(tmp_path):
    """Step X.15: the game's file reads in a step are the stream module's (ReadFile returning into 0xA527B), and L3
    serves them from the disc's files at the offsets asked: a read in flight in the snapshot (pending on the list
    0x1AA7F8) completes at load, a read the step makes completes at once (the bytes, the OVERLAPPED's status and
    count; past the file's end STATUS_END_OF_FILE), none of it taints the run, and from the second step on the main
    loop's poll 0xA58A0 runs first.  Without a disc a read stays zeros and taints the run "read"."""
    from devkit.sim import l3
    from devkit.sim.l3 import L3, read_snapshot

    upd, kern, ent = 0x8C230, 0x80016000, 0x100000
    req_a, req_b, req_c, fo_a, fo_b = 0x104000, 0x104100, 0x104200, 0x104400, 0x104440
    code = (b"\x68" + struct.pack("<I", 0xA527B) + b"\x55\x89\xe5"                     # ReadFile's frame
            + b"".join(b"\x68" + struct.pack("<I", v) for v in (req_b + 0x10, 0x200, 0x104800, req_b + 8,
                                                                 req_b + 8, 0, 0x2C, 0x88))  # NtReadFile(...)
            + b"\xff\x15" + struct.pack("<I", 0x18F404) + b"\x5d\x83\xc4\x04")
    code += b"\xe9" + _rel(upd + len(code), 0x8C3F1)
    mem = {upd: code, 0x8C3F1: b"\xc3", 0x18F404: struct.pack("<I", kern),
           0xA58A0: b"\xff\x05" + struct.pack("<I", ent + 0x74) + b"\xc3",      # the poll: counts its runs
           l3.STREAM_DIR: b"Z:\\gamedata\0", l3.STREAM_PENDING: struct.pack("<2I", req_a, req_c),
           fo_a: struct.pack("<II", fo_a + 0x10, 0x30) + bytes(8) + b"fx.xbr\0",
           fo_b: struct.pack("<II", fo_b + 0x10, 0x88) + bytes(8) + b"characters.xbr\0"}
    for req, nxt, fo, buf, off in ((req_a, req_c, fo_a, 0x104600, 0x10), (req_c, l3.STREAM_PENDING, fo_a, 0x104700,
                                                                         0x900), (req_b, 0, fo_b, 0x104800, 0x100)):
        mem[req] = struct.pack("<8I4I", nxt, 0, l3.STATUS_PENDING, 0, off, 0, 0x2C, 0,      # links, OVERLAPPED
                               fo, 0, buf, 0x40 if req != req_b else 0x200)                 # file, buffer, length
    files = {"gamedata/fx.xbr": bytes(range(256)) * 8, "gamedata/characters.xbr": bytes(range(255, -1, -1)) * 2}

    def disc(path, off, n):
        return files[path][off:off + n] if path in files else None
    store_dir = tmp_path / "store"
    store_dir.mkdir(mode=0o700)
    snap = read_snapshot(_l3_snapshot(store_dir, mem, {})[0])
    sim = L3(snap, {kern: "NtReadFile"}, disc=disc)
    assert sim.read(0x104600, 0x40) == files["gamedata/fx.xbr"][0x10:0x50]
    assert struct.unpack("<II", sim.read(req_a + 8, 8)) == (0, 0x40)
    assert struct.unpack("<II", sim.read(req_c + 8, 8)) == (l3.STATUS_END_OF_FILE, 0)
    row = sim.step()
    assert sim.read(0x104800, 0x100) == files["gamedata/characters.xbr"][0x100:]
    assert struct.unpack("<II", sim.read(req_b + 8, 8)) == (0, 0x100) and not row.taint and not sim.taint
    assert sim.u32(ent + 0x74) == 0 and (sim.step(), sim.u32(ent + 0x74))[1] == 1
    bare = L3(snap, {kern: "NtReadFile"}, disc=lambda *a: None)
    assert bare.taint == {"read"} and bare.step().taint == {"read"} and bare.read(0x104800, 0x100) == bytes(0x100)


def test_l3_whole_steps_from_an_update_entry_finish_its_frame_on_its_stack_and_map_high_pages_as_taken(tmp_path):
    """Step X.15: a format 3 snapshot holds high runs (the thread's stack, the RAM window), which L3 maps page by
    page as a step touches them, as taken (no taint; a page outside them is still a zero page that taints), the
    real KPCR among them in place of L3's zeroed one.  So whole
    steps run from a player-update-entry snapshot (a chain's join): the first finishes the frame the snapshot
    stopped in, on the snapshot's own stack (the update, the rest of the scheduler, scene_state_tick's return
    pointed at the stop), the next are whole scene ticks; a reset reruns it the same."""
    from devkit.sim import l3
    from devkit.sim.l3 import L3, read_snapshot

    upd, ent, stack = 0x8C230, 0x100000, 0xD0000F00
    code = (b"\xa1" + struct.pack("<I", 0x83000010) + b"\xa3" + struct.pack("<I", ent + 0x78)   # a RAM-window read
            + b"\x64\xa1\x28\x00\x00\x00" + b"\xa3" + struct.pack("<I", ent + 0x88)            # the KPCR's thread
            + b"\xff\x05" + struct.pack("<I", ent + 0x7C))                                     # updates run
    code += b"\xe9" + _rel(upd + len(code), 0x8C3F1)
    rest = b"\xff\x05" + struct.pack("<I", ent + 0x80) + b"\xc2\x08\x00"   # the frame's rest: count; RET 8
    tick = (b"\xb9" + struct.pack("<I", ent) + b"\xe8" + _rel(l3.SCENE_TICK + 5, upd)          # the update, then
            + b"\xff\x05" + struct.pack("<I", ent + 0x84) + b"\xc2\x08\x00")                 # count; RET 8
    mem = {upd: code, 0x8C3F1: b"\xc3", 0x8C600: rest, l3.SCENE_TICK: tick, l3.RENDER: b"\xc2\x08\x00",
           0x83000010: struct.pack("<I", 0x5A5A5A5A), stack: struct.pack("<3I", 0x8C600, 0x566E1, 0x101000),
           0x80035BDC + 0x28: struct.pack("<I", 0xD002F018)}
    store_dir = tmp_path / "store"
    store_dir.mkdir(mode=0o700)
    path, info = _l3_snapshot(store_dir, mem, {}, {"esp": stack, "ecx": ent})
    snap = read_snapshot(path)
    assert info["high_pages"] == 3 and [va for va, _ in snap.runs if va >= l3.HIGH] == [0x80035000, 0x83000000,
                                                                                         0xD0000000]
    sim = L3(snap, {}, scene=True)
    rows = [sim.step(), sim.step()]
    assert [sim.u32(ent + o) for o in (0x78, 0x7C, 0x80, 0x84, 0x88)] == [0x5A5A5A5A, 2, 1, 1, 0xD002F018]
    assert [r.k for r in rows] == [0, 1] and not sim.taint and sim.u32(stack + 4) == l3._STOP
    sim.reset()
    assert sim.u32(stack + 4) == 0x566E1 and sim.u32(ent + 0x7C) == 0
    assert [sim.step().k, sim.step().k] == [0, 1] and [sim.u32(ent + o) for o in (0x7C, 0x80, 0x84)] == [2, 1, 1]
    (tmp_path / "bare").mkdir(mode=0o700)
    with pytest.raises(ValueError, match="holds its stack"):
        L3(read_snapshot(_l3_snapshot(tmp_path / "bare", {upd: code, 0x8C3F1: b"\xc3"}, {})[0]), {}, scene=True)


def test_l3_whole_steps_render_each_frame_with_the_gpu_a_stub_that_has_done_its_work(tmp_path):
    """Step X.20 (AZ-358, AZ-361): the frame outside the step moves the game too: after its scene tick the main loop
    renders, and the render moves the cameras and draws from the game's random numbers (its draw lists' sort), which
    critters draw from too.  So a whole step from a format 3 snapshot runs the render 0x54800 (the scene, the step's
    dt) after its scene tick, to 0x55820, before the flush and the present; the next tick sees what it did.  The GPU
    is a stub that has done all it was given: its push buffer's GET reads the last PUT, and a kickoff (a PUT) makes
    D3D's GPU time its CPU time.  A snapshot without high memory skips the render and taints "render"; player
    ticks run none."""
    from devkit.sim import l3
    from devkit.sim.l3 import L3, read_snapshot

    upd, ent, scene, dev = 0x8C230, 0x100000, 0x101000, 0x101900

    def ref(op: bytes, off: int) -> bytes:
        return op + struct.pack("<I", ent + off)
    tick = (b"\xb9" + struct.pack("<I", ent) + b"\xe8" + _rel(l3.SCENE_TICK + 5, upd)
            + ref(b"\xff\x05", 0x84) + b"\xc2\x08\x00")                               # the update; count; RET 8
    code = ref(b"\xa1", 0x98) + ref(b"\xa3", 0x9C)                                       # the render's mark, seen
    code += b"\xe9" + _rel(upd + len(code), 0x8C3F1)
    render = (b"\x8b\x44\x24\x04" + ref(b"\xa3", 0xA0) + b"\x8b\x44\x24\x08" + ref(b"\xa3", 0xA4)   # scene, dt
              + ref(b"\xa1", 0x84) + ref(b"\xa3", 0x98)                                  # mark: the ticks so far
              + b"\xc7\x05" + struct.pack("<II", l3.NV2A + l3.NV_PUT, 0x1234)             # a kickoff: PUT
              + b"\xa1" + struct.pack("<I", l3.NV2A + l3.NV_GETS[0]) + ref(b"\xa3", 0xAC))   # GET
    render += b"\xe9" + _rel(l3.RENDER + len(render), l3.RENDER_END)
    mem = {upd: code, 0x8C3F1: b"\xc3", l3.SCENE_TICK: tick, l3.RENDER: render,
           l3.RENDER_END: ref(b"\xff\x05", 0xA8) + b"\xc2\x08\x00",                    # the present: never
           l3.D3D_DEVICE: struct.pack("<I", dev), dev + 0x1C: struct.pack("<I", 77),        # its CPU time
           dev + 0x3F0: struct.pack("<I", 0x101E00), 0x101E00: struct.pack("<I", 5)}        # -> its GPU time
    meta = {"at": "scene", "scene": scene, "dt": l3.DT_30}
    (tmp_path / "f3").mkdir(mode=0o700)
    (tmp_path / "f2").mkdir(mode=0o700)
    path, _ = _l3_snapshot(tmp_path / "f3", {**mem, 0x83000000: bytes(4)}, meta)   # format 3: a high run
    sim = L3(read_snapshot(path), {}, scene=True)
    sim.run([l3.Pad()] * 3)
    assert [sim.u32(ent + o) for o in (0x84, 0x98, 0x9C, 0xA0, 0xA4, 0xA8, 0xAC)] == [3, 3, 2, scene, l3.DT_30, 0,
                                                                                         0x1234]
    assert sim.u32(0x101E00) == 77 and not sim.taint
    for other in (L3(read_snapshot(_l3_snapshot(tmp_path / "f2", mem, meta)[0]), {}, scene=True),
                  L3(read_snapshot(path), {})):
        other.run([l3.Pad()] * 3)
        assert other.u32(ent + 0x98) == 0 and other.taint == ({"render"} if other.scene else set())


def test_l3_runs_an_input_string_with_the_poll_camera_teleport_and_resets(tmp_path):
    """Step X.6 (D170): an input string, a pad per tick, as the game gets it: the stick and buttons go into
    ControllerState at the player update's entry, and from the second tick on the main loop's poll
    (0xA2880) first frees the latch of each button that read 0 the frame before, so a held Y stays latched
    until a frame after its release; the camera yaw becomes the ground direction (-sin, cos) the input
    builder reads at 0x85276, held until the next yaw; each row is read at the update's RET with the
    caller's zone and the writes and camera a replay needs.  A teleport posts the game's own place request
    (R6) in the player's cell; save and reset replay bit for bit.  Each row's observation is the shared
    reader's (Step X.10): velocity, feet, camera yaw, the armor's Flaps, the kit, the inventory and flag hashes,
    and Step TD.0's contact normal, fall reference, state time, animation, gauge and armor Level, the light read's
    too (the trick explorer's)."""
    import hashlib
    import math

    from devkit.sim import l3, obs
    from devkit.sim.l3 import L3, Pad, read_snapshot

    ent = 0x100000
    sim = L3(read_snapshot(_l3_walker(tmp_path)), {}, zone_at=lambda feet: f"Z{int(feet[0])}")
    y = frozenset({"y"})
    rows = sim.run([Pad((0.0, 1.0), y), Pad((0.0, 0.5), y, math.pi / 2), Pad(), Pad((0.0, 0.0), y)])
    assert [(r.k, r.pos, r.state, r.hp, r.zone) for r in rows] == [
        (0, (6.0, 6.0, 7.0), 0, 200, "Z6"), (1, (6.5, 6.0, 7.0), 1, 200, "Z6"),
        (2, (6.5, 6.0, 7.0), 1, 200, "Z6"), (3, (6.5, 6.0, 7.0), 0, 200, "Z6")]
    turned = l3.camera_dir(math.pi / 2)
    assert [r.cam for r in rows] == [bytes(8), turned, turned, turned] and sim.read(ent + 0x60, 8) == turned
    o = rows[1].obs                    # Step X.10: the observation the xemu replayer reads at the same RET
    inv = sim.read(0x101600, 0x1D4)
    flags = hashlib.sha256(struct.pack("<I", 4) + b"Gate" + struct.pack("<I", 1)).hexdigest()[:12]
    assert (o.pos, o.feet, o.vel, o.state, o.hp, o.hp_max, o.flaps, o.kit, o.inv_sha12, o.flags_sha12) == (
        (6.5, 6.0, 7.0), (6.5, 6.0, 6.0), (0.5, 0.0, -1.0), 1, 200, 250, 2, (1, 2, 0, 3),
        hashlib.sha256(inv[4:]).hexdigest()[:12], flags)     # AZ-389: past the day clock
    f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]   # noqa: E731
    td0 = ("normal", "fall_ref", "state_t", "anim", "gauge", "armor_level", "flaps", "peak_z")   # peak_z: R1.29e
    assert [getattr(o, f) for f in td0] == [(0.0, f32(0.6), f32(0.8)), 3.5, 0.25, 9, f32(0.6), 3, 2, 2.25]
    light = obs.read(sim.read, ent, rows[1].cam, deep=False)
    assert [getattr(light, f) for f in td0] == [getattr(o, f) for f in td0] and light.kit is None
    assert abs(o.cam_yaw - math.pi / 2) < 1e-6 and obs.digest(o) == obs.digest(rows[2].obs) != obs.digest(rows[0].obs)
    assert obs.compare([r.obs for r in rows], [rows[0].obs, rows[1].obs._replace(anim=10),   # a TD.0 field: counted,
                                               o._replace(flaps=3, anim=10), rows[3].obs]) == {   # not judged
        "fields_differ": {"anim": 2, "flaps": 1}, "first_diff": [2, ["flaps"]]}
    assert rows[1].writes == ((l3.CONTROLLER_STATE, l3.pad_floats(Pad((0.0, 0.5), y))),)
    with pytest.raises(ValueError, match="unknown buttons"):
        sim.step(Pad(buttons=frozenset({"jump"})))

    start = sim.save()
    tp = sim.teleport((1.0, 2.0, 3.0), math.pi)
    assert sim.read(l3.PLACE_BUF, 30) == struct.pack("<3f4fH", 1.0, 2.0, 3.0, 0.0, 0.0, 1.0, math.cos(math.pi / 2), 3)
    assert [va for va, _ in tp.writes] == [l3.CONTROLLER_STATE, l3.PLACE_BUF, 0x101208] and sim.u32(0x101208) == 0
    more = [tp, *sim.run([Pad((0.0, 2.0))] * 2)]
    sim.reset(start)
    assert [sim.teleport((1.0, 2.0, 3.0), math.pi), *sim.run([Pad((0.0, 2.0))] * 2)] == more
    sim.reset()
    assert sim.k == 0 and sim.run([Pad((0.0, 1.0), y)]) == rows[:1]


class _ToyRow(typing.NamedTuple):
    pos: tuple
    state: int
    hp: int
    zone: str | None = None
    flaps: int = 0


class _Toy:
    """0.25 m a tick times the stick, along the camera; a wall at y = 2 for |x| < ``width``, ``wall`` m high.  A jump
    rises 1.05 m; a fresh Y press in the air is a flap (+0.25 m/tick up, the per-jump counter +1) while the counter
    is under ``cap`` (the armor's Flaps)."""
    def __init__(self, wall=0.5, cap=0, width=3.0):
        self.s, self.wall, self.cap, self.width = (0.0, 0.0, 0.0, 0.0, 0, False), wall, cap, width   # x y z vz flaps Y
    def save(self):
        return self.s
    def reset(self, s):
        self.s = s
    def step(self, pad):
        x, y, z, vz, fl, held = self.s
        h = pad.yaw + math.atan2(-pad.stick[0], pad.stick[1])
        m = 0.25 * math.hypot(*pad.stick)
        y_down = "y" in pad.buttons
        if z == 0.0 and y_down:
            vz, fl = 0.3, 0
        elif z > 0 and y_down and not held and fl < self.cap:
            vz, fl = 0.25, fl + 1
        nx, ny = x - m * math.sin(h), y + m * math.cos(h)
        if abs(nx) < self.width and (y < 2) != (ny < 2) and z < self.wall:
            nx, ny = x, y
        z, vz = max(0.0, z + vz), (vz - 0.05 if z + vz > 0 else 0.0)
        self.s = (nx, ny, z, vz, fl if z > 0 else 0, y_down)
        return _ToyRow((nx, ny, z + 1.0), 2 if z > 0 else 0, 200, None, self.s[4])


class _ToyGoal:   # beyond the wall; guidance straight at it (into the wall)
    settle = 3
    def reached(self, r):
        return r.pos[1] >= 4 and abs(r.pos[0]) < 1 and r.state == 0
    def cost(self, r):
        return math.dist(r.pos[:2], (0.0, 4.0)) / 7
    def toward(self, r):
        return math.atan2(r.pos[0], 4.0 - r.pos[1]), False
    def cell(self, r):
        return (int(r.pos[0] // 0.5), int(r.pos[1] // 0.5), int(r.pos[2] // 0.5), r.state)


def test_a_contact_normal_and_a_point_find_the_touched_face_with_its_slippery_climbable_and_spring_bits():
    """Step TD.0: the face a contact touched, looked up in memory from the body centre and the normal the game
    stored (entity+0xB8): of the solid faces near the point, the nearest whose front normal agrees and that the
    point is in front of, so the normal decides between a floor and a nearer wall, and a nearer water surface or a
    sheet the point is behind is passed over; its id, owner and collision bits; none for a normal no nearby face
    has (an edge's) or a point far from every face."""
    from devkit.sim.faces import Faces
    from azurkit.tools.randomizer.art import collision as c

    floor = ((0, 0, 0), (10, 0, 0), (0, 10, 0))                   # faces up
    wall = ((5, 0, 0), (5, 0, 5), (5, 5, 0))                      # faces -x
    pad = ((20, 20, 2), (22, 20, 2), (20, 22, 2))
    water = ((0, 0, 0.5), (10, 0, 0.5), (0, 10, 0.5))             # a water volume's surface, 0.5 m over the floor
    sheet = ((0, 0, 1.4), (10, 0, 1.4), (0, 10, 1.4))             # faces up, 0.4 m over the point: it is behind
    solid = c.W_SOLID | c.W_BLOCK
    fs = Faces([floor, wall, pad, water, sheet], [solid, solid | c.W_SLIPPERY | c.W_CLIMBABLE, solid | c.W_AUTOSPRING,
                                                  c.W_WATER | c.W_FIELD, solid], [0, 0, 3, 4, 5])
    up, off = (0.0, 0.0, 1.0), (0.0, math.sin(math.radians(1)), math.cos(math.radians(1)))
    f = fs.face((2, 2, 1), up)
    assert (f.id, f.owner, f.nz, f.dist, f.slippery, f.climbable, f.spring) == (0, 0, 1.0, 1.0, False, False, False)
    w = fs.face((4.5, 2, 1), (-1.0, 0.0, 0.0))
    assert (w.id, w.dist, w.slippery, w.climbable, w.spring) == (1, 0.5, True, True, False)
    assert fs.face((4.5, 2, 1), off).id == 0 and fs.face((21, 20.5, 3), up)[:2] == (2, 3)
    assert fs.face((21, 20.5, 3), up).spring
    assert fs.face((2, 2, 1), (0.0, -0.7071, 0.7071)) is None and fs.face((50, 50, 0), up) is None
    assert fs.face((2, 2, 4), up) is None                         # 4 m over the floor: no contact


def test_l3_search_finds_confirms_and_grades_a_string():
    """Step X.7 (D170, D172): the L3 input search (Go-Explore over the goal's cells, guidance plus random headings
    and jumps) finds a string over a wall a straight walk can't pass, confirms it from the start and grades it
    under jitter; on a step budget with a seeded stream the same problem gives the same string; a rollout that
    raises ``L3Error`` (a game assert) ends only its branch; the result carries every explored run's taint.
    Its pads are a real pad's: the camera turns at most 3.33 deg a tick toward the heading and the stick stays in
    the round gate; their JSON is the run-length form ``l3.pads`` reads."""
    from devkit.sim import l3
    from devkit.sim.l3 import L3Error
    from devkit.sim.l3_search import (CAM_RATE, Limits, pads, robustness, search, segments,
                                          string_sha12)

    Row, Toy, Goal = _ToyRow, _Toy, _ToyGoal

    class Faulty(Toy):   # the game asserts on the first three jumps: each such rollout ends, the search goes on;
        jumps = 0        # an assert's run read a clock L3 doesn't model, so the result is tainted

        def step(self, pad):
            if "y" in pad.buttons and self.jumps < 3:
                self.jumps += 1
                self.taint = {"time"}
                raise L3Error("assert: a planted one")
            return super().step(pad)

    cam, row0, lim = 1.2, Row((0.0, 0.0, 1.0), 0, 200), Limits(steps=80_000, ticks=300, seg=4, hold=3)
    sim = Toy()
    start = sim.save()
    res = search(sim, start, row0, Goal(), lim, cam=cam, seed=1)
    assert res.reached and res.why == "reached" and 0 < res.ticks <= 300 and any(s.hold for s in res.segs)
    assert search(Toy(), start, row0, Goal(), lim, cam=cam, seed=1).segs == res.segs      # reproducible
    sim.reset(start)
    string = pads(res.segs, cam)
    rows = [sim.step(p) for p in string]
    assert Goal().reached(rows[-1]) and len(rows) == res.ticks
    yaws = [cam] + [p.yaw for p in string]
    assert all(abs(b - a) <= CAM_RATE + 1e-12 for a, b in zip(yaws, yaws[1:]))
    assert all(math.hypot(*p.stick) <= 1.0 + 1e-9 for p in string)
    assert l3.pads(segments(string)) == string and len(string_sha12(string)) == 12
    assert 0.0 <= robustness(sim, start, res.segs, Goal(), cam=cam, trials=8) <= 1.0
    assert search(sim, start, row0, Goal(), Limits(steps=5_000), cam=cam, seeds=[res.segs]).why == "a seed string"
    faulty = search(Faulty(), start, row0, Goal(), lim, cam=cam, seed=1)
    assert faulty.reached and faulty.faults == 3 and any(s.hold for s in faulty.segs)
    assert faulty.taint == {"time"} and not res.taint and faulty.summary()["taint"] == ["time"]


def test_a_runs_wall_cap_follows_its_step_budget_so_a_slow_scene_runs_its_steps(monkeypatch):
    """Step X.52b: with no wall cap given, a search's and an exploration's safety net is their steps at 4 a second
    (``l3_search.WALL_RATE``: under the slowest whole steps measured, 5.8-6.2 a second, which R1.29f's fixed 4,000 s
    cap cut at 23-30 k of 30 k steps), so a run at 5 steps a second ends on its budget and one at 3 on the cap; a
    cap given is kept."""
    import types

    from devkit.sim import l3_explore as X, l3_search as S

    clock = [0.0]
    for mod in (S, X):
        monkeypatch.setattr(mod, "time", types.SimpleNamespace(monotonic=lambda: clock[0]))

    class Slow(_Toy):
        rate = 5.0

        def step(self, pad):
            clock[0] += 1.0 / self.rate
            return super().step(pad)

    class Never(_ToyGoal):
        def reached(self, r):
            return False

        def zone(self, r):
            return None
    got = []
    for rate in (5.0, 3.0):
        Slow.rate, sim, row0 = rate, Slow(), _ToyRow((0.0, 0.0, 1.0), 0, 200)
        clock[0] = 0.0
        got.append(S.search(sim, sim.save(), row0, Never(), S.Limits(steps=2000, ticks=300), seed=1).why)
        clock[0] = 0.0
        got.append(X.explore(sim, sim.save(), row0, Never(), X.Limits(steps=2000), seed=1).verdict)
    assert got == ["the step budget ran out", "not found within budget", "wall-cap", "wall-cap"]
    assert (S.Limits(steps=2000).wall_s(), X.Limits(steps=2000).wall_s(), S.Limits(wall_cap_s=9.0).wall_s()) == (
        500.0, 500.0, 9.0)


def test_every_l3_result_carries_its_engine_and_two_compare_only_on_one_engine_with_no_faults(tmp_path):
    """Step X.52b: a problem id hashes the start, the goal's spec and the search's shape, never code (Step X.52 found
    12 commits that moved TD.2's runs under the same ids), so every search's and exploration's summary carries
    ``l3.engine()``: sha256[:12] of the engine's code and the reach model's data (``l3.ENGINE_FILES``, a folder's
    .py, .toml, .json and .gz files at any depth: a goal names its model only by its pickle's path) and Unicorn's
    version, with the wall-time caps a step runs under; the hash moves with any engine file's bytes.  Two results
    compare only on one engine and with no fault on either side (a fault is a wall-time cap or a step L3 can't run,
    so it isn't reproducible under another load); a result without an engine compares with none."""
    from devkit.sim import l3, l3_explore as X
    from devkit.sim.l3_search import Limits, search

    class Goal(_ToyGoal):       # never reached: each run ends on its budget
        def reached(self, r):
            return False

        def zone(self, r):
            return None
    sim, row0 = _Toy(), _ToyRow((0.0, 0.0, 1.0), 0, 200)
    res = search(sim, sim.save(), row0, Goal(), Limits(steps=500, ticks=300), seed=1).summary()
    ex = X.explore(sim, sim.save(), row0, Goal(), X.Limits(steps=500), seed=1).summary()
    assert res["engine"] == ex["engine"] == l3.engine() and len(l3.engine()["sha12"]) == 12
    assert l3.engine()["caps"] == {"scene_us": l3.SCENE_US, "update_us": l3.UPDATE_US, "render_us": l3.RENDER_US,
                                   "cold_render_us": l3.COLD_RENDER_US, "poll_us": l3.POLL_US, "watchdog_s": 0.025}
    root = tmp_path / "code"
    (root / "sim").mkdir(parents=True)
    (root / "sim" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "x.toml").write_text("y = 1\n", encoding="utf-8")
    one = l3.engine_sha12(root, ("sim", "x.toml"))
    (root / "sim" / "notes.txt").write_text("not code", encoding="utf-8")
    assert l3.engine_sha12(root, ("sim", "x.toml")) == one
    (root / "sim" / "a.py").write_text("x = 2\n", encoding="utf-8")
    two = l3.engine_sha12(root, ("sim", "x.toml"))
    assert two != one and {"src/azurkit/tools/randomizer/draft", "src/azurkit/tools/randomizer/data"} <= set(l3.ENGINE_FILES)
    (root / "sim" / "derived").mkdir()
    (root / "sim" / "derived" / "f3.json.gz").write_bytes(b"model")     # a model fix that changes only data
    assert l3.engine_sha12(root, ("sim", "x.toml")) != two
    clean = {"engine": {"sha12": "a"}, "faults": 0}
    assert l3.comparable(clean, dict(clean)) and l3.comparable({"engine": {"sha12": "a"}, "runs": [clean]}, clean)
    assert not any(l3.comparable(clean, other) for other in (
        {**clean, "faults": 2}, {"engine": {"sha12": "b"}, "faults": 0}, {"faults": 0},
        {"engine": {"sha12": "a"}, "runs": [clean, {"faults": 3}]}))


def test_ram_recipes_post_the_level_hop_and_kit_requests_the_game_reads():
    """Step X.9: the sitting kit's RAM recipes (devkit.sim.recipes, shared with L3's teleport) find the
    request block and inventory from the scene global, write a level hop as the levelSwitch fire builds it
    (movie, level, spot in 0x104-byte slots, then [R+0x10]) and an exact kit (element levels, fragments 1..n,
    keys by fourcc in the 5 key slots, Step R1.16), and read the inventory back by name; a release's address map
    moves the globals they use."""
    from azurkit.tools.randomizer.live import recipes as r

    mem = {r.SCENE_PTR: 0x1000, 0x1000 + r.SCENE_PD: 0x2000, 0x2000 + r.PD_REQ: 0x3000,
           0x2000 + r.PD_INV: 0x4000, 0x2000 + r.PD_WORLD: 0x5000, 0x5000 + r.WORLD_CELLS: 0x6000}
    u32 = lambda va: mem.get(va, 0)  # noqa: E731
    hop = r.hop(u32, "levels/fire/f6", "bossPlatformShape1")
    assert hop == [(r.LEVEL_BUF, b"\0"), (r.LEVEL_BUF + 0x104, b"levels/fire/f6\0"),
                   (r.LEVEL_BUF + 0x208, b"bossPlatformShape1\0"), (0x3010, struct.pack("<I", r.LEVEL_BUF))]
    kit = r.element_levels(u32, {"water": 1, "fire": 0}) + r.fragments(u32, "f", 3) + r.keys(u32, {"d2k1": 6})
    inv = bytearray(r.INV_SAVED)
    for va, data in kit:
        inv[va - 0x4000:va - 0x4000 + len(data)] = data
    got = r.inventory(bytes(inv))
    assert (got["level.water"], got["level.fire"], [got[f"fgf{k}"] for k in range(1, 5)]) == (1, 0, [1, 1, 1, 0])
    assert (inv[r.KEY0:r.KEY0 + 4], [got[f"key{i}"] for i in range(5)]) == (b"d2k1", [6, 0, 0, 0, 0])
    with pytest.raises(ValueError, match="5 key slots"):
        r.keys(u32, {f"k{i}xx"[:4]: 1 for i in range(6)})
    with pytest.raises(ValueError, match="no element 'staff'"):
        r.element_levels(u32, {"staff": 1})
    moved = r.hop(lambda va: mem.get(va - 0x10 if va == r.SCENE_PTR + 0x10 else va, 0), "levels/air/a1", "x",
                  va=lambda v: v + 0x10)
    assert [va for va, _ in moved] == [r.LEVEL_BUF + 0x10, r.LEVEL_BUF + 0x114, r.LEVEL_BUF + 0x218, 0x3010]


def test_a_place_given_the_player_entity_starts_the_body_at_rest():
    """AZ-437: the place consumer 0x855D0 writes the centre, facing and state but keeps the player's velocity
    (PlayerControl +0x24), so a place right after a warp onto a1's rising tree lift flew 6.8 m up.  Given the
    entity, R6 also zeroes those 12 bytes; without one (L3's teleport) it writes the place struct and the request
    pointer alone, as before."""
    from azurkit.tools.randomizer.live import recipes as r

    mem = {r.SCENE_PTR: 0x1000, 0x1000 + r.SCENE_PD: 0x2000, 0x2000 + r.PD_REQ: 0x3000}
    u32 = lambda va: mem.get(va, 0)  # noqa: E731
    bare = r.place(u32, (1.0, 2.0, 3.0), 0.0, cell=4)
    assert [va for va, _ in bare] == [r.PLACE_BUF, 0x3000 + r.R_PLACE]
    assert r.place(u32, (1.0, 2.0, 3.0), 0.0, cell=4, entity=0x7000) == bare + [(0x7024, bytes(12))]


def test_l3_search_dives_for_a_pickup_under_the_water_only_when_its_share_is_set():
    """Step R1.29: swimming, BLACK held sinks (A, B and BLACK dive, X and Y rise: RE_MOVEMENT), so a pickup under
    the surface is out of reach of walks and jumps; with ``Limits.dive`` a share of the segments in the water hold
    BLACK throughout and the search reaches it, the share joining the problem's identity only when set."""
    from devkit.sim.l3_search import Limits, buttons, search

    class Swim(_Toy):    # a pool's surface at z 0 (state 6): BLACK sinks 0.2 m a tick, Y rises
        def step(self, pad):
            x, y, z, *_ = self.s
            h = pad.yaw + math.atan2(-pad.stick[0], pad.stick[1])
            m = 0.25 * math.hypot(*pad.stick)
            z = min(0.0, z - 0.2 * ("black" in pad.buttons) + 0.2 * ("y" in pad.buttons))
            self.s = (x - m * math.sin(h), y + m * math.cos(h), z, 0.0, 0, False)
            return _ToyRow((self.s[0], self.s[1], z + 1.0), 6, 200)

    class Under(_ToyGoal):   # 3 m under the surface, 2 m ahead
        settle = 0
        def reached(self, r):
            return math.dist(r.pos, (0.0, 2.0, -2.0)) < 0.6
        def cost(self, r):
            return math.dist(r.pos, (0.0, 2.0, -2.0)) / 7

    lim = dict(steps=20_000, ticks=200, seg=4, hold=3)
    got = {}
    for dive in (0.0, 0.3):
        sim = Swim()
        got[dive] = search(sim, sim.save(), _ToyRow((0.0, 0.0, 1.0), 6, 200), Under(), Limits(dive=dive, **lim),
                           cam=0.0, seed=1)
    assert not got[0.0].reached and got[0.3].reached, (got[0.0].why, got[0.3].why)
    assert any(all("black" in buttons(s, t) for t in range(s.n)) for s in got[0.3].segs)
    assert "dive" not in Limits().shape() and Limits(dive=0.3).shape()["dive"] == 0.3


def test_l3_search_keeps_to_a_flap_budget_and_a_kit_is_part_of_the_problem():
    """Step R1.8g (D183): the search's flap budget caps the flaps in any one jump (the game's per-jump counter a
    row carries): a wall a jump can't clear is never passed on a budget of 0, and on a budget of 1 the winner
    flaps exactly once; a segment's buttons are Y for a jump or flap, BLACK for a roll, LT+Y for an armor cast;
    the budget, the move shares and the kit join the problem's identity only when set, so an X.7 problem keeps
    its own."""
    from devkit.sim.l3_search import Limits, Seg, Segment, buttons, problem_sha12, search

    lim = dict(steps=60_000, ticks=300, seg=4, hold=3)
    for budget, reached in ((0, False), (1, True)):
        sim = _Toy(wall=1.2, cap=2, width=1e9)
        res = search(sim, sim.save(), _ToyRow((0.0, 0.0, 1.0), 0, 200), _ToyGoal(), Limits(flaps=budget, **lim),
                     cam=1.2, seed=1)
        assert res.reached is reached and (res.flaps == 1 if reached else res.flaps is None), (budget, res.why)
    assert [buttons(Seg(4, 0.0, 2, roll=1), t) for t in range(3)] == [{"y", "black"}, {"y"}, set()]
    assert buttons(Seg(4, 0.0, 2, cast=1), 0) == {"lt", "y"}
    assert "flaps" not in Limits().shape() and Limits(flaps=0).shape()["flaps"] == 0
    with mock.patch("devkit.sim.l3_search.read_meta", return_value={"level": "w1"}), \
            mock.patch("devkit.sim.l3_search.snapshot_path"):
        ids = {problem_sha12(Segment("s", kit=kit), {"g": 1}, Limits(flaps=f)) for kit in (None, {"air": 1})
               for f in (None, 1)}
    assert len(ids) == 4


def test_a_douse_casts_then_walks_through_attacking_until_the_to_node_and_a_leg_runs_on_from_its_pads(
        tmp_path, monkeypatch):
    """Step R1.29e: ``sim.douse`` is ``Chain.staff``'s recipe as a closed loop in L3: it turns to the barrier (12
    ticks at a 0.15 stick), casts the staff's elements (LT from tick 14, water's X at 16, LT up at 21), then walks
    toward the shape's mirror point holding A 4 ticks every 24 until the feet stand in the to-node for 8 ticks; a
    toy fire wall an attack within 2 m opens once water is cast lets it through, the same start gives the same pads,
    and with nothing cast it never opens.  A leg runs on from those pads: ``Segment.tail`` (``l3.pads`` segments)
    runs after the prefix, the camera ends at its last yaw and it joins the problem's identity;
    ``l3_certify.leg_pads`` runs a doused leg's parts in turn; ``l3_certify.crossing`` reads the barrier on
    f1/g0/r1693's way there (f1.flameSpout15: its shape, water, water 1, the to-node's zone) and on the way back
    ``plan`` sets up (its kit search and barrier crossings, AZ-517): none on f1/g0/r1693's, e2.FireWall_03 at water
    1 on e2/g0/r4376's; ``crossings`` reads every barrier of a leg in turn (Step R1.29f: f1/g0/r1689's way back,
    f1.flameSpout11 then f1.flameSpout13), and a leg doused twice keeps its five pieces in turn (to each barrier,
    each douse's pads, on from the last) with their ticks and least robustness.
    A wall is in the way when crossing to the body's mirror point through it brings the to-node nearer (else
    nothing crosses it, as ``Chain.staff``); a leg's start is read from the snapshot (the leader's simulator ran
    the last one's); and ``_verify`` meets a doused leg's goal at its last row and counts no goal row in a leg's
    lead (an air kit's recast before a way back that starts in its goal)."""
    import types
    from pathlib import Path

    from devkit.sim import douse as dz, l3
    from devkit.sim.l3 import Pad
    from devkit.sim.l3_search import Limits, Segment, problem_sha12, segments, start_of

    class Wall:          # a fire wall at y = 3; water cast (LT with X) and A within 2 m of it open it
        def __init__(self):
            self.s = (0.0, 0.0, False, False)

        def step(self, pad):
            x, y, water, lit = self.s
            h, m = pad.yaw + math.atan2(-pad.stick[0], pad.stick[1]), 0.25 * math.hypot(*pad.stick)
            water = water or {"lt", "x"} <= pad.buttons
            lit = lit or water and "a" in pad.buttons and abs(3.0 - y) < 2.0
            nx, ny = x - m * math.sin(h), y + m * math.cos(h)
            self.s = (nx, y if not lit and y < 3.0 <= ny else ny, water, lit)
            return _ToyRow((self.s[0], self.s[1], 1.0), 0, 200)

    def run(elements):
        return dz.douse(Wall(), _ToyRow((0.0, 0.0, 1.0), 0, 200), (0.0, 3.0, 0.0), elements,
                        lambda r: r.pos[1] > 4.0, 0.0)
    d = run(["water"])
    held = [p.buttons for p in d.pads]
    assert d.passed and d.attacks >= 1 and run(["water"]).pads == d.pads
    assert math.hypot(*d.pads[0].stick) == pytest.approx(0.15) and held[12] == set()
    assert held[13] == {"lt"} and held[15] == {"lt", "x"} and held[19] == {"lt"} and held[20] == set()
    assert held[24:29] == [{"a"}] * 4 + [set()]
    stuck = run([])
    assert not stuck.passed and len(stuck.pads) == dz.schedule([])[2] + dz.THROUGH_MAX

    store = tmp_path / "store"
    store.mkdir(mode=0o700)
    _l3_walker(store)
    sim = l3.L3(l3.read_snapshot(l3.snapshot_path("s", store)), {})
    tail = segments([Pad((0.0, 1.0), frozenset(), 0.7)] * 3)
    _, row, cam, _, rows = start_of(sim, Segment("s", settle=1, store=str(store), tail=tail))
    assert (len(rows), cam, row.pos[0]) == (4, 0.7, pytest.approx(rows[0].pos[0] + 3.0))
    assert problem_sha12(Segment("s", settle=1, store=str(store), tail=tail), {"g": 1}, Limits()) != \
        problem_sha12(Segment("s", settle=1, store=str(store)), {"g": 1}, Limits())
    ahead = lambda r: abs(10.0 - r.pos[1])                                   # noqa: E731  (the to-node at y 10)
    assert dz.in_the_way(ahead, (0.0, 3.0, 0.0), (0.0, 0.0, 1.0)) and not dz.in_the_way(ahead, (0.0, -3.0, 0.0),
                                                                                          (0.0, 0.0, 1.0))

def test_the_trick_explorer_keeps_a_charged_catch_in_its_own_cell_and_is_the_same_for_a_seed():
    """Step TD.1 (the trick-discovery plan §3.2): in the catch (0x101) the dynamic cell's speed bucket is linear in
    the charge a Y adds (4.6434 m/s along the stored wall normal; the entry's speed into the wall stays), so each
    press is a new cell at the same place, and a place cell keeps two strings: its shortest (a plain walk there) and
    the one of most potential (the most charged), so a quicker plain visit never evicts a charge.  Exploring a toy with a catchable wall from the same seed gives the same archive."""
    from devkit.sim import l3_explore as X

    class Obs(typing.NamedTuple):
        vel: tuple
        flaps: int = 0
        flaps_used: int = 0
        gauge: float | None = None
        normal: tuple | None = None

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        hp: int = 200
        zone: str | None = None
        obs: Obs | None = None

    class Catch:   # flat ground; a wall at y = 3 (|x| < 2) caught in the air (16 ticks); each Y edge charges
        def __init__(self):
            self.s = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0.0, False)

        def save(self):
            return self.s

        def reset(self, s):
            self.s = s

        def step(self, pad):
            x, y, z, vx, vy, vz, st, timer, charge, held = self.s
            h, m = pad.yaw + math.atan2(-pad.stick[0], pad.stick[1]), math.hypot(*pad.stick)
            edge = "y" in pad.buttons and not held
            if st == 0x101:
                timer, charge = timer - 1, charge + X.CHARGE * edge
                vx = vy = vz = 0.0
                if not timer:
                    st, vy, vz = 2, -charge, charge
            elif st == 0:
                vx, vy = -7 * m * math.sin(h), 7 * m * math.cos(h)
                st, vz = (2, 4.64) if edge else (0, 0.0)
            else:
                vz -= 9.8 / 30
            nx, ny, nz = x + vx / 30, y + vy / 30, z + vz / 30
            if st in (0, 2) and abs(nx) < 2 and y < 3 <= ny:
                st, timer, charge, vx, vy, vz = (0x101, 16, 0.0, 0.0, 0.0, 0.0) if st == 2 else (0, 0, 0.0, 0, 0, 0)
                nx, ny, nz = x, min(y, 2.99), z
            if st == 2 and nz <= 0:
                st, nz, vz = 0, 0.0, 0.0
            self.s = (nx, ny, nz, vx, vy, vz, st, timer, charge, "y" in pad.buttons)
            return Row((nx, ny, nz + 1.0), st, obs=Obs((vx, vy, vz)))

    class Guide:
        def zone(self, row):
            return "toy.Z000"

    at = (0.5, 2.9, 3.0)
    plain = Row(at, 0, obs=Obs((0.3, 0.0, 0.0)))
    # caught at 7 m/s into the wall (its normal -y): |v| runs 7, 2.4, 2.3, 6.9 over the presses, the charge rises
    charged = [Row(at, 0x101, obs=Obs((0.0, 7.0 - k * X.CHARGE, 0.0), normal=(0.0, -1.0, 0.0))) for k in range(4)]
    assert len({X.cells(r, "z")[0] for r in [plain, *charged]}) == 1
    assert len({X.cells(r, "z")[1] for r in [plain, *charged]}) == 5
    arch = X.Archive()
    got = []
    for ticks, r in [(40, charged[0]), (44, charged[1]), (48, charged[2]), (52, charged[3]), (12, plain)]:
        e = X.Entry(len(arch.entries), None, (), ticks, r, 0.0, 0, 0, 0, None)
        arch.add(e)
        got.append(arch.offer(e, "z"))
    assert got == [2, 1, 1, 1, 1]                # a new place and dynamic cell, then a new dynamic cell each
    shortest, best = arch.place[X.cells(plain, "z")[0]]
    assert (arch.entries[shortest].row, arch.entries[best].row) == (plain, charged[3])
    assert arch.live(0).tolist() == [False, False, False, True, True] and arch.live(1).all()

    sim, r0 = Catch(), Row((0.0, 0.0, 1.0), 0, obs=Obs((0.0, 0.0, 0.0)))
    start, lim = sim.save(), X.Limits(steps=12_000, exhaust=400)
    runs = [X.explore(sim, start, r0, Guide(), lim, seed=seed, digest=True) for seed in (2, 2)]
    assert runs[0].archive == runs[1].archive and runs[0].place == runs[1].place > 1 and runs[0].classes["catch"]


def test_a_long_string_splits_at_its_last_settle_point_within_the_gate_into_d172_pieces():
    """Step TD.4b (D172): a string longer than the long-replay gate is cut into pieces of at most the gate's ticks,
    each ending at the last settle point within its reach (10 ticks at rest on the ground, where the next piece's
    replay starts from the halted guest), else at the gate's length (marked unsettled: a join in motion); the
    pieces cover the string tick for tick, and a short string is one piece."""
    from devkit.sim.l3_explore import split

    class Obs(typing.NamedTuple):
        vel: tuple

    class Row(typing.NamedTuple):
        state: int
        obs: Obs

    moving, rest, air = Row(0, Obs((5.0, 0.0, 0.0))), Row(0, Obs((0.0, 0.0, 0.0))), Row(2, Obs((0.0, 0.0, -9.0)))
    rows = [moving] * 1000 + [rest] * 12 + [moving] * 1988 + [rest] * 20 + [air] * 6000 + [moving] * 2980
    pieces = split(rows, most=5000)
    assert [(p["start"], p["ticks"], p["settled"]) for p in pieces] == [(0, 3020, True), (3020, 5000, False),
                                                                        (8020, 3980, False)]
    assert split(rows[:3020]) == [{"start": 0, "ticks": 3020, "settled": True}]


def test_the_trick_explorers_ablations_take_the_speed_from_its_cells_and_draw_no_option_and_no_site_weight():
    """Step TD.4b (the pilot's ablations, the trick-discovery plan §4): ``speed`` keys the dynamic cell without its
    speed bucket, ``options`` never draws an option, ``sites`` never asks the guide's site prior; an ablation joins
    the problem's identity only when set, and any other name (or a bare string) is refused."""
    from devkit.sim import l3_explore as X

    class Obs(typing.NamedTuple):
        vel: tuple
        flaps: int = 0
        flaps_used: int = 0
        gauge: float | None = None

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        obs: Obs

    fast, slow = Row((1.0, 1.0, 1.0), 0, Obs((9.0, 0.0, 0.0))), Row((1.0, 1.0, 1.0), 0, Obs((1.0, 0.0, 0.0)))
    assert X.cells(fast, "z")[1] != X.cells(slow, "z")[1] and X.cells(fast, "z", False) == X.cells(slow, "z", False)

    class Count(X.Option):
        name, fired = "count", 0

        def begin(self, row, rng):
            Count.fired += 1

    class Guide:
        asked = 0

        def zone(self, row):
            return None

        def site_prior(self, row, seen):
            Guide.asked += 1
            return 1.0

    got = []
    for ablate in ((), ("options", "sites")):
        Count.fired = Guide.asked = 0
        sim = _Toy()
        X.explore(sim, sim.save(), _ToyRow((0.0, 0.0, 1.0), 0, 200), Guide(), X.Limits(steps=3000, ablate=ablate),
                  options=[Count()], seed=1)
        got.append((Count.fired > 0, Guide.asked > 0))
    assert got == [(True, True), (False, False)]
    assert "ablate" not in X.Limits().shape() and X.Limits(ablate=["speed", "sites", "speed"]).shape()["ablate"] == [
        "sites", "speed"]
    for bad in (["speeds"], "sites"):
        with pytest.raises(ValueError, match="ablate"):
            X.Limits(ablate=bad)


def test_the_trick_miner_counts_presses_takeoffs_slope_contacts_and_hoists_and_names_the_tricks_a_trace_used():
    """Step TD.3 (the trick-discovery plan §3.5): one miner for a demo trace (the recorder's rows) and an L3 string
    counts each button's presses, the takeoffs (entries into the air), the slope contacts (entries into state 3) and
    the hoists, and names the tricks from the game's rules: a hoist (0x100 straight from the air, clip 66), a slope
    hop with an LT+Y recast, a chained roll (40 rows of 0x100: two rolls) ending in a mid-air roll jump, a roll off
    an edge with no Y (no roll jump), a step-up (clip 53), a steep walk (a 0.72 face, rising), a charge in the catch
    (two presses), a deflection (lift off a steep face with no press) and an 0x100 off the slope no rule names (a
    candidate).  An older trace (no animation or stored normal) still gives the hoist, the step-up, the rolls and
    the candidate."""
    from devkit.sim import l3_explore as X
    from devkit.sim import tricks_detect as td

    assert (td.AIRBORNE, td.CHARGE_STEP) == (X.AIRBORNE, X.CATCH_STEP)      # the miner's copies (it loads no L3)

    rows = []

    def put(n, st, b=(), v=(0.0, 0.0, 0.0), dz=0.0, anim=None, n_=(0.0, 0.0, 1.0)):
        for _ in range(n):
            z = (rows[-1]["body"][2] if rows else 0.0) + dz
            rows.append({"n": len(rows), "st": st, "stt": 0.0, "vel": list(v), "body": [0.0, 0.0, z], "fl": 0,
                         "pad": {"ly": 1.0, **{k: 1.0 for k in b}}, "anim": anim, "nrm": list(n_), "fuel": 1.0})
    put(5, 0)
    put(1, 2, ("y",), (0, 0, 4.6))
    put(14, 2, v=(0, 0, -1.0))
    put(36, 0x100, dz=0.05, anim=66)                             # the hoist
    put(3, 3, n_=(0.0, -0.73, 0.68))                             # a slope contact, a jump off it and a recast
    put(1, 2, ("y",), (0, 0, 4.0))
    put(1, 2, ("lt", "y"))
    put(10, 2)
    put(3, 0)
    put(1, 0x100, ("blk",), anim=102)
    put(39, 0x100, dz=-0.1, anim=102)                            # a roll chained into a second, off a ledge
    put(1, 2, ("y",), (0, 0, 4.643))                             # the end-tick jump in mid-air
    put(10, 2)
    put(2, 0)
    put(1, 0x100, ("blk",), anim=102)
    put(20, 0x100, dz=-0.1, anim=102)                            # a roll off an edge, no Y: no roll jump
    put(6, 2, v=(0, 0, -2.0))
    put(2, 0)
    put(6, 0x100, dz=0.1, anim=53)                               # a step-up
    put(12, 0, dz=0.06, n_=(0.0, -0.69, 0.72))                   # a steep walk
    put(1, 2, ("y",), (0, 0, 4.0))
    put(2, 2)
    wall = (0.0, -1.0, 0.0)
    put(1, 0x101, n_=wall)                                       # the catch: two presses, two charges
    put(1, 0x101, ("y",), (0, -4.64, 0), n_=wall)
    put(1, 0x101, v=(0, -4.64, 0), n_=wall)
    put(1, 0x101, ("y",), (0, -9.29, 0), n_=wall)
    put(3, 2, v=(0, -9.29, 5.0), n_=wall)
    put(1, 2, v=(0, -6.0, 7.5), n_=(0.0, -0.95, 0.3))            # lift off a steep face, no press
    put(3, 0)
    put(2, 3, n_=(0.0, -0.73, 0.68))
    put(8, 0x100, dz=0.1, anim=70)                               # an 0x100 off the slope no rule names
    put(2, 0)
    ticks = td.from_trace(rows)

    class Obs(typing.NamedTuple):
        vel: tuple
        anim: int | None
        flaps_used: int
        normal: tuple

    class Row(typing.NamedTuple):
        pos: tuple
        state: int
        obs: Obs

    class Pad(typing.NamedTuple):
        buttons: frozenset

    names = {"blk": "black"}
    l3_rows = [Row(tuple(r["body"]), r["st"], Obs(tuple(r["vel"]), r["anim"], 0, tuple(r["nrm"]))) for r in rows]
    pads = [Pad(frozenset(names.get(k, k) for k in r["pad"] if k != "ly")) for r in rows]
    assert td.from_l3(l3_rows, pads) == ticks                    # an L3 string's rows read the same way
    m = td.mine(ticks)
    assert (m["presses"]["black"], m["presses"]["y"], m["presses"]["lt"]) == (2, 6, 1)
    assert (m["takeoffs"], m["slope_contacts"], m["hoists"]) == (6, 2, 1)
    assert m["labels"] == {"CANDIDATE": 1, "DEFLECT_LAUNCH": 1, "HOIST": 1, "ROLL_CHAIN": 1, "ROLL_JUMP_AIR": 1,
                           "SLOPE_RECAST_HOP": 1, "STEEP_WALK": 1, "STEP_UP": 1, "TJUMP_CHARGE": 1}
    old = td.mine(td.from_trace([{k: v for k, v in r.items() if k not in ("anim", "nrm")} for r in rows]))
    assert old["labels"] == {"CANDIDATE": 1, "HOIST": 1, "ROLL_CHAIN": 1, "ROLL_JUMP_AIR": 1, "SLOPE_RECAST_HOP": 1,
                             "STEP_UP": 1}


def test_the_explorers_options_are_registered_and_each_reacts_to_the_rows_it_sees():
    """Step TD.3 (the trick-discovery plan §3.2): the explorer's limits carry every option by spec; each fires on its
    own precondition and steers by each tick's row: the hoist runs, jumps early when stopped against a face and
    pushes into the face the air contact reports until the hoist (0x100) ends; the slope hop jumps uphill off a
    slope and flaps; the steep walk heads uphill on a 0.6-0.8 face; the roll chain presses BLACK, chains on its
    drawn roll tick (the last, 20, too) and holds Y into the last roll's end."""
    import random

    from devkit.sim import l3_explore as X
    from devkit.sim import l3_options as O

    class Obs(typing.NamedTuple):
        vel: tuple = (0.0, 0.0, 0.0)
        normal: tuple = (0.0, 0.0, 1.0)
        flaps: int = 0
        flaps_used: int = 0
        gauge: float | None = None

    class Row(typing.NamedTuple):
        state: int
        obs: Obs = Obs()

    opts = [X.option(s) for s in X.Limits().options]
    assert [o.name for o in opts] == ["hoist", "slope_hop", "steep_walk", "roll_chain"]
    hoist, slope, steep, roll = opts
    run, stopped, face = Row(0, Obs((7.0, 0.0, 0.0))), Row(0, Obs((0.5, 0.0, 0.0))), Obs(normal=(0.0, -1.0, 0.0))
    p = {"h": 1.0, "run": 12, "hold": 2, "jump": None, "up": False}
    got = [hoist.act(p, r, t) for t, r in enumerate([run] * 4 + [stopped, Row(2), Row(2, face), Row(0x100), Row(0)])]
    assert [g and (round(g[0], 3), g[2]) for g in got] == [
        (1.0, frozenset()), (1.0, frozenset()), (1.0, frozenset()), (1.0, frozenset()),
        (1.0, O.Y), (1.0, O.Y), (0.0, frozenset()), (0.0, frozenset()), None]
    assert hoist.applies(Row(2, face)) and not hoist.applies(Row(2)) and hoist.applies(run)
    on = Row(3, Obs(normal=(0.0, 0.73, 0.68), flaps=2))
    assert slope.applies(on) and not slope.applies(run) and abs(O.uphill(on) - math.pi) < 1e-9
    p = {"h": math.pi, "mag": 1.0, "hold": 2, "flap": 6, "cast": None}
    got = [slope.act(p, r, t) for t, r in enumerate([on, Row(2), *[Row(2, Obs(flaps=2))] * 6, Row(0)])]
    assert [g and g[2] for g in got] == [O.Y, O.Y] + [frozenset()] * 4 + [O.Y, O.Y, None]
    walk = Row(0, Obs(normal=(0.69, 0.0, 0.72)))
    assert steep.applies(walk) and not steep.applies(run)
    p = steep.begin(walk, random.Random(0))
    assert abs(steep.act(p, walk, 0)[0] - (O.uphill(walk) + p["off"])) < 1e-9 and O.uphill(walk) == math.pi / 2
    p = {"h": 0.5, "rolls": 2, "chain": 20, "y": 4, "end": None}
    rows = [run] + [Row(0x100)] * 40 + [Row(2), Row(2)]
    got = [roll.act(p, r, t) for t, r in enumerate(rows)]
    pressed = {t: g[2] for t, g in enumerate(got) if g and g[2]}
    assert pressed == {0: O.BLACK, 19: O.BLACK, **{t: O.Y for t in range(22, 41)}} and got[41] and got[42] is None

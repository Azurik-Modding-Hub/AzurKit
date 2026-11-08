"""The xemu oracle: its core (Step 4.14a1), the harness's Unicorn-free parts:
the sittings' first-come queue and the batch token that gives way to it
(``devkit.xemu.queue``), a sitting's warm build states (``devkit.xemu.warm``),
the guest RAM snapshot's file (``devkit.sim.snapshot``), the observation both
backends read (``devkit.sim.obs``) and the pad (``devkit.sim.inputs``); and
the harness (Step 4.14a2, ``devkit.xemu.oracle``), by its offline selftest,
with the build data its code check leaves out (``devkit.xemu.shim_ranges``).
xemu is a dev-only oracle (D108): nothing here launches one, and every
memory read is synthetic, no game bytes."""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from azurkit.core import gate, iso
from azurkit.edits.layer import compose
from azurkit.tools import mods
from azurkit.tools.characters import ports
from azurkit.tools.mods import engine
from devkit.sim import inputs, obs, snapshot
from devkit.xemu import queue, shim_ranges
from devkit.xemu.warm import HDD, IDLE_S, WarmStore, sweep


def test_a_batch_that_gave_way_takes_its_workers_back_within_a_poll_once_the_sitting_is_gone(tmp_path):
    """AZ-563: a batch whose token fell to one task while a sitting's ticket waited starts its next task within a
    poll of the ticket going, while the running task is still running (it waited for a task to end before)."""
    ticket = queue.take_ticket({"W": "test"}, tmp_path)
    queue.renew_ticket(ticket, "1.0 of 24 CPU cores are free (test)")
    b_started = threading.Event()

    def task(name: str) -> bool:
        if name == "B":
            b_started.set()
            return True
        queue.drop_ticket(ticket)        # the sitting starts; A runs on and waits for B
        return b_started.wait(5.0)
    with ThreadPoolExecutor(2) as pool, queue.BatchToken("test", 2, root=tmp_path) as tok:
        tok.POLL_S = 0.05
        got = list(tok.ordered(pool, task, [("A",), ("B",)]))
    assert got == [True, True]


def test_a_batch_gives_way_only_to_a_sitting_that_waits_for_free_cores(tmp_path, monkeypatch):
    """AZ-620: while a sitting's ticket waits for what freed cores can't give it (RAM, an owner demo's hold) a batch
    keeps every worker and the explorer's ``give_way`` doesn't sleep; a ticket waiting for cores, or one from a
    harness that doesn't say which (no ``cores``), takes the batch down to one task and makes ``give_way`` wait; a
    wait for another launch's lock (``cores`` None) leaves the ticket as it was."""
    ticket = queue.take_ticket({"W": "test"}, tmp_path)
    got = []
    for why, cores in (("0.1 GiB of RAM is free (test)", False), ("another sandbox is launching", None),
                       ("1.0 of 24 CPU cores are free (test)", True), ("another sandbox is launching", None),
                       ("an older harness's refusal (test)", "old")):
        queue.renew_ticket(ticket, why, cores=None if cores == "old" else cores)
        if cores == "old":
            doc = json.loads(ticket.read_text(encoding="utf-8"))
            ticket.write_text(json.dumps({k: v for k, v in doc.items() if k != "cores"}), encoding="utf-8")
        monkeypatch.setattr(queue, "_WAY_AT", -math.inf)
        stops = []
        with queue.BatchToken("test", 4, root=tmp_path) as tok:
            got.append((tok.allowed(), queue.give_way(lambda: stops.append(1) or True, root=tmp_path) >= 0
                        and len(stops)))
    assert got == [(4, 0), (4, 0), (1, 1), (1, 1), (1, 1)]


def test_a_batch_beside_an_owner_demo_keeps_its_budget_and_runs_its_workers_in_the_background(tmp_path, monkeypatch):
    """D526 (Step X.59): while the owner-demo file names a live pid a batch keeps at most the demo's budget of tasks in
    flight and puts every process under it at background priority (a worker started since too, never the demo's own
    xemu), and the token's file says so; once the demo ends it takes them back out and its workers back. A record of the
    harnesses' own whose pid is no xemu (a reused pid) is no demo."""
    lease, calls, kids = tmp_path / "owner-demo.json", [], [111, 222]
    monkeypatch.setattr(queue, "demo_budget", lambda: 2)
    monkeypatch.setattr(queue, "descendants", lambda pid=None: list(kids))
    monkeypatch.setattr(queue, "set_background", lambda pid, on: calls.append((pid, on)) or True)
    with queue.BatchToken("test", 4, root=tmp_path, lease=lease) as tok:
        tok.POLL_S = 0.0
        got = [tok.allowed()]
        ours = {"pid": os.getpid(), "who": queue.OWNER_DEMO_WHO}   # its pid no xemu: no demo
        lease.write_text(json.dumps(ours), encoding="utf-8")
        got.append(tok.allowed())
        lease.write_text(json.dumps({"pid": os.getpid(), "who": "the owner"}),
                         encoding="utf-8")   # this process stands in for its xemu
        got.append(tok.allowed())
        kids += [333, os.getpid()]
        got.append(tok.allowed())
        listed = [j["background"] for j in queue.batch_jobs(tmp_path)]
        lease.unlink()
        got.append(tok.allowed())
    assert (got, listed) == ([4, 4, 2, 2, 4], [True])
    assert calls == [(111, True), (222, True), (333, True), (111, False), (222, False), (333, False)]


def test_a_sittings_sandboxes_boot_each_build_and_tag_cold_once(tmp_path):
    """Step X.81d: a sitting's sandboxes share its warm build states (``WarmStore``): each (build, tag) boots cold
    once and is published; a later sandbox, or a running one that relaunches onto the drive holding it, loads it
    warm, also after two sandboxes published apart; a sandbox that saved a tag no drive holds (a parked start) keeps
    its drive; a store left idle goes."""
    store = WarmStore(tmp_path / "warm", {"sitting": "ev", "xemu": "abc", "release": "usa", "deterministic": True})
    cold: list[str] = []

    class Box:   # a sandbox whose drive is a file listing the snapshot tags it holds
        def __init__(self, name: str):
            self.w = tmp_path / name
            self.w.mkdir()
            self.drive(set())
            self.warm, self.saved = {}, set()
            self.adopt()

        def drive(self, tags: set[str] | None = None) -> set[str]:
            if tags is not None:
                (self.w / HDD).write_text(json.dumps(sorted(tags)), encoding="utf-8")
            return set(json.loads((self.w / HDD).read_text(encoding="utf-8")))

        def adopt(self, need=None):
            if got := store.adopt(self.w, set(self.warm), self.saved, need):
                self.warm, self.saved = got, set(got)

        def boot(self, build: str, tag: str) -> str:
            key = f"b-{build}-{tag}"
            if store.plan(key, self.warm, self.saved) == "adopt":
                self.adopt(key)
            if key in self.warm:
                assert key in self.drive() and (self.w / f"b-{build}.iso").exists()
                return "warm"
            cold.append(key)
            (self.w / f"b-{build}.iso").write_text(build, encoding="utf-8")
            self.drive(self.drive() | {key})
            self.warm[key] = {"disc": f"b-{build}.iso", "level": tag}
            self.saved.add(key)
            store.publish(self.w, self.warm)
            return "cold"

    runs = [(b, t) for b in ("ctl", "flicken") for t in ("w1", "f6", "a1")]
    first = Box("s1")
    assert [first.boot(*r) for r in runs] == ["cold"] * 6
    later = Box("s2")   # a re-run's sandbox
    assert [later.boot(*r) for r in runs] == ["warm"] * 6
    a, b = Box("s3"), Box("s4")   # two at once: each publishes a drive the other's lacks
    got = [a.boot("x", "w1"), b.boot("y", "w1"), a.boot("y", "w1"), b.boot("x", "w1")]
    assert got == ["cold", "cold", "warm", "warm"]
    parked = Box("s5")
    parked.saved.add("start-1")
    assert [parked.boot("z", "w1"), Box("s6").boot("z", "w1"), parked.boot("x", "w1")] == ["cold", "warm", "cold"]
    assert cold == [f"b-{b}-{t}" for b, t in runs] + ["b-x-w1", "b-y-w1", "b-z-w1", "b-x-w1"]   # the last: parked's
    assert sorted(p.name for p in store.dir.glob("b-*.iso")) == ["b-ctl.iso", "b-flicken.iso", "b-x.iso", "b-y.iso",
                                                                 "b-z.iso"]
    os.utime(store.dir / "warm.json", (0, 0))
    assert sweep(store.root, IDLE_S) == [store.dir.name] and not store.dir.exists()


def test_the_private_store_keeps_snapshots_and_results_mode_600_and_reads_each_snapshot_format_it_knows(tmp_path):
    """Steps X.5, X.10, X.51: guest RAM holds console keys, so a store others may enter is refused and one made is
    mode 700; a snapshot (the present user pages through the page tables' self-map, the registers, the metadata and
    the runs at or above HIGH) is written mode 0600 and read back page for page with its metadata, in format 3 with
    high runs and 2 without (a format 1 file, its pages right after the header, still reads; an unknown format is
    refused by name); a label is a plain name; a results file never replaces another."""
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o755)
    posix = os.name == "posix"   # modes say nothing on Windows
    if posix:
        with pytest.raises(ValueError, match="must be private"):
            snapshot.store(shared)
    assert not posix or snapshot.snapshot_path("w1-start", tmp_path / "s").parent.stat().st_mode & 0o777 == 0o700
    with pytest.raises(ValueError, match="bad snapshot label"):
        snapshot.snapshot_path("../w1", tmp_path / "s")

    page = snapshot.PAGE
    pages = {va: bytes([va >> 12 & 0xFF]) * page for va in (0x10000, 0x11000, 0x20000, 0x80010000, 0x80011000)}
    pde, pte = bytearray(page), bytearray(page)
    struct.pack_into("<I", pde, 0, 0x2001)                      # PDE 0: a page table
    for va in (0x10000, 0x11000, 0x20000):
        struct.pack_into("<I", pte, 4 * (va >> 12), va | 1)
    pages |= {snapshot.PDE_BASE: bytes(pde), snapshot.PTE_BASE: bytes(pte)}

    def read(va, n):   # page by page: a run spans several
        return b"".join(pages[p][max(va, p) - p:min(va + n, p + page) - p] for p in range(va & ~0xFFF, va + n, page))
    store = snapshot.store(tmp_path / "store")
    meta = {"level": "levels/water/w1", "entity": 0x100000, "at": "update"}
    info = snapshot.write_snapshot(read, store / "s.l3snap", {"fs_base": 0x80035BDC}, meta, [(0x80010000, 0x2000, read)])
    low = pages[0x10000] + pages[0x11000] + pages[0x20000]
    assert info == {"pages": 3, "runs": 2, "high_pages": 2, "bytes": 0x3000,
                    "sha12": hashlib.sha256(low).hexdigest()[:12]}
    assert (not posix or (store / "s.l3snap").stat().st_mode & 0o777 == 0o600) and snapshot.read_meta(store / "s.l3snap") == meta
    snap = snapshot.read_snapshot(store / "s.l3snap")
    want = [(0x10000, low[:0x2000]), (0x20000, low[0x2000:]), (0x80010000, pages[0x80010000] + pages[0x80011000])]
    assert ([(va, bytes(d)) for va, d in snap.runs], snap.regs, snap.meta) == (want, {"fs_base": 0x80035BDC}, meta)

    snapshot.write_snapshot(read, store / "two.l3snap", {}, meta)
    raw = (store / "two.l3snap").read_bytes()
    n = struct.unpack_from("<I", raw, 8)[0]
    hdr = json.loads(raw[12:12 + n])
    assert hdr["format"] == 2 and [(va, bytes(d)) for va, d in snapshot.read_snapshot(store / "two.l3snap").runs] \
        == want[:2]
    for fmt, name in ((1, "old.l3snap"), (9, "new.l3snap")):
        head = json.dumps({**{k: v for k, v in hdr.items() if k != "format"}, **({"format": 9} if fmt == 9 else {})})
        (store / name).write_bytes(snapshot.MAGIC + struct.pack("<I", len(head)) + head.encode() + low)
    assert [(va, bytes(d)) for va, d in snapshot.read_snapshot(store / "old.l3snap").runs] == want[:2]
    with pytest.raises(ValueError, match="of format 9; this reader reads formats 1 to 3"):
        snapshot.read_snapshot(store / "new.l3snap")

    first = snapshot.private_out(store / "r.json", {"run": 1})
    second = snapshot.private_out(store / "r.json", {"run": 2})
    assert (first.name, second.name) == ("r.json", "r.2.json")
    assert [json.loads(p.read_text(encoding="utf-8")) for p in (first, second)] == [{"run": 1}, {"run": 2}]
    assert not posix or {p.stat().st_mode & 0o777 for p in (first, second)} == {0o600}


def test_an_observation_reads_the_players_fields_and_hashes_through_any_reader():
    """Steps X.10, TD.0, R1.29e: the observation reads the player through any ``read(va, n)`` (L3's memory or a halted
    xemu's gdbstub): the body centre, velocity, state, HP, the camera the input builder read, the armor's Flaps and
    Level, the gauge, the contact normal, fall reference, state time, animation and peak_z; with ``deep`` the kit and
    the inventory's hash past its day clock (AZ-389) and the global latches' hash; before the player data exists the
    armor's fields are None. Its digest is coordinate-free, and a trace comparison counts every field but judges only
    those before TD.0's."""
    base, ent, crit, pd, armor, slot, inv, shared = (0x100000, 0x100000, 0x103000, 0x101100, 0x101400, 0x101500,
                                                     0x101600, 0x101800)
    mem = bytearray(0x4000)
    for va, fmt, *v in ((ent + 0x20, "<I", crit), (ent + 0x24, "<3f", 0.5, 0.0, -1.0), (ent + 0x94, "<I", 1),
                        (ent + 0x9C, "<f", 0.25), (ent + 0xB8, "<3f", 0.0, 0.6, 0.8), (ent + 0xD8, "<i", 1),
                        (ent + 0x164, "<f", 2.25), (ent + 0x168, "<f", 3.5),
                        (crit + 0x154, "<I", pd), (crit + 0x15C, "<3f", 6.5, 6.0, 7.0), (crit + 0x200, "<i", 9),
                        (crit + 0x210, "<2i", 200, 250), (pd + 0xCC, "<I", armor), (pd + 0xE0, "<2I", inv, shared),
                        (armor + 0x20, "<If", slot, 0.6), (slot + 0x08, "<i", 3), (slot + 0x38, "<i", 2),
                        (inv, "<5i", 77, 1, 2, 0, 3), (shared, "<I", 0x101820), (0x101824, "<I", 0x101840),
                        (0x101850, "<5s", b"Gate"), (0x1018A0, "<I", 0x1018B0), (0x1018B0, "<I", 1)):
        struct.pack_into(fmt, mem, va - base, *v)

    def read(va, n):
        return bytes(mem[va - base:va - base + n])
    cam = snapshot.camera_dir(math.pi / 2)
    o = obs.read(read, ent, cam)
    f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]   # noqa: E731
    flags = hashlib.sha256(struct.pack("<I", 4) + b"Gate" + struct.pack("<I", 1)).hexdigest()[:12]
    assert (o.pos, o.feet, o.vel, o.state, o.hp, o.hp_max, o.flaps_used, o.kit, o.inv_sha12, o.flags_sha12) == (
        (6.5, 6.0, 7.0), (6.5, 6.0, 6.0), (0.5, 0.0, -1.0), 1, 200, 250, 1, (1, 2, 0, 3),
        hashlib.sha256(read(inv + 4, 0x1D4 - 4)).hexdigest()[:12], flags)
    td0 = ("normal", "fall_ref", "state_t", "anim", "gauge", "armor_level", "flaps", "peak_z")
    assert [getattr(o, f) for f in td0] == [(0.0, f32(0.6), f32(0.8)), 3.5, 0.25, 9, f32(0.6), 3, 2, 2.25]
    assert o.cam_yaw == pytest.approx(math.pi / 2)
    light = obs.read(read, ent, cam, deep=False)
    assert [getattr(light, f) for f in td0] == [getattr(o, f) for f in td0] and light.kit is light.flags_sha12 is None
    struct.pack_into("<I", mem, crit + 0x154 - base, 0)   # no player data yet
    bare = obs.read(read, ent)
    assert (bare.cam, bare.gauge, bare.armor_level, bare.flaps, bare.kit) == (None, None, None, None, None)
    assert obs.digest(o) == obs.digest(o._replace()) != obs.digest(o._replace(pos=(6.5, 6.0, 7.5)))
    assert obs.digest(o, obs.CORE) == obs.digest(o._replace(anim=10), obs.CORE)
    assert obs.compare([o, o, o], [o, o._replace(anim=10), o._replace(flaps=3, anim=10)]) == {   # a TD.0 field:
        "fields_differ": {"anim": 2, "flaps": 1}, "first_diff": [2, ["flaps"]]}                # counted, not judged


def test_a_pad_string_is_controllerstates_floats_and_the_stick_a_real_pad_gives():
    """Steps X.4, X.6: a run-length input string becomes one pad a tick (its camera a yaw or the exact f32 pair);
    a pad is ControllerState's 18 floats (the sticks, the D-pad, the 12 buttons at 1.0 held), an unknown button and a
    stick that isn't finite refused; the camera yaw is the ground direction (-sin, cos). The pilot's stick points up
    along the camera and left 90 degrees to its left; along an axis (or within 5 degrees of one, the other axis left
    in its dead zone) it reaches 1.0, on a diagonal only the round gate's 0.761."""
    got = snapshot.pads([{"n": 2, "stick": [0, 1], "buttons": ["y"], "yaw": 0.5}, {"n": 1, "cam": [0, 1]}])
    y = frozenset({"y"})
    assert got == [snapshot.Pad((0.0, 1.0), y, 0.5)] * 2 + [snapshot.Pad(cam=(0.0, 1.0))]
    floats = struct.unpack("<18f", snapshot.pad_floats(got[0]))
    assert floats == (0.0, 1.0) + (0.0,) * 4 + tuple(float(b == "y") for b in snapshot.BUTTONS)
    for pad, why in ((snapshot.Pad(buttons=frozenset({"jump"})), "unknown buttons"),
                     (snapshot.Pad((math.nan, 0.0)), "isn't finite")):
        with pytest.raises(ValueError, match=why):
            snapshot.pad_floats(pad)
    assert snapshot.camera_dir(0.0) == struct.pack("<2f", -0.0, 1.0)

    r = math.radians
    assert inputs.stick(r(30.0), r(30.0)) == inputs.stick(r(33.0), r(30.0)) == pytest.approx((0.0, 1.0), abs=1e-4)
    assert inputs.stick(r(120.0), r(30.0), 0.5) == pytest.approx((-0.5, 0.0), abs=1e-9)
    x, yy = inputs.stick(r(75.0), r(30.0))
    assert math.hypot(x, yy) == pytest.approx(0.761, abs=1e-3) and x == pytest.approx(-yy)
    assert inputs.stick(None, 0.0) == (0.0, 0.0)


@pytest.mark.xemu
def test_the_harness_passes_its_offline_selftest_with_no_xemu_and_no_fixtures(capsys):
    """Step 4.14a2 (D11): the harness's own logic against stand-ins, launching no xemu and reading no fixtures: the
    scratch config (volume 0, the keyboard pad on scancodes no key reaches), the sandbox proof, the slots and their
    admission (D108 as D174 and D263 amend it: a third sandbox waits while either suite's lock is held, Modkit's or
    AzurKit's), the queue and the owner demo's lease, QMP, the gdbstub and the pad, readiness, parks, relaunches and
    the teardown, the code check and a Europe disc's addresses."""
    from devkit.xemu import oracle   # macOS's own calls: imported here, so the file collects on every platform

    assert oracle.selftest() == 0, "\n".join(line for line in capsys.readouterr().out.splitlines()
                                             if line.startswith("FAIL"))


@pytest.mark.parametrize("release", [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
                                     pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe],
                                                  id="europe")])
def test_xemus_code_check_leaves_out_the_copy_gates_state_a_running_build_writes(release, request):
    """AZ-817's round-2 sitting: main's first frame writes the copy gate's g_main in SHIMS, and xemu's code check
    (boot-build), which left out only the player-model shims' data, refused every default build. The harness reads
    the gate's state from the build: the door's landing's .bss, all seven words the shim writes (the tick's and the
    park's landings reach them through the door and write none of their own); vanilla has none, nor the
    player-model shims' data, and neither has a build without the swap."""
    with iso.Reader(request.getfixturevalue(f"{release.name}_iso")) as r:
        vanilla = r.read(engine.XBE)
    layer = mods.plan(mods.PACKS["qol_alloc_race"], release, {engine.XBE: vanilla})
    built = bytes(compose({engine.XBE: vanilla}, [layer])[0][engine.XBE])
    (lo, hi), = shim_ranges.copy_gate(built)
    with shim_ranges.building(built):
        words = [ports.trampoline_symbol_va(built, shim_ranges.COPY_GATE, f"_g_{name}")
                 for name in ("lock", "main", "parked", "busy", "state", "size", "freed")]
    assert hi - lo == 4 * len(words) and all(lo <= va <= hi - 4 for va in words)
    assert shim_ranges.copy_gate(vanilla) == shim_ranges.player_model(vanilla) == shim_ranges.player_model(built) == []

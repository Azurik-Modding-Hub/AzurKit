"""The owner-demo kit (D205, D207; Steps X.27, X.28, X.31a): record what the owner plays in a visible sandbox.

An owner demo runs one windowed real-time sandbox (``oracle up --window --owner-pad PORT``, or the kit's
``serve ... --window --owner-pad PORT``: the owner's pad bound on PORT, volume 0) with the fork's input recorder on
that port (``--record PORT``). Beside it, this module's two watchers read guest RAM through the sandbox's
``XEMU_RAM_SHM`` and the fork's PC hooks (no gdbstub):

    uv run --locked python -m devkit xemu demo record <W> <trace.jsonl> [--meta META]   # one row per player tick
    uv run --locked python -m devkit xemu demo replug <W> <log> [--once]                # the pad on port 1, per load

A demo's setup and its body switches are one verb each (Step X.56; ``add_body``): a body built from this checkout,
booted quiet at w1's or f6's save, tagged after 60 ticks at rest (its level checked at the save) and loaded:

    uv run --locked python -m devkit xemu demo add-body <sock> <body> [--mode M] [--size S] [--level w1|f6]
        [--no-load] [--meta META] [-- <more azurkit build args>]                        # or: <sock> --vanilla

``record`` writes one JSONL row per change of the player's event clock (entity +0x18): state, body, velocity, flaps
used, HP, armor, the air gauge, the stored contact normal (+0xB8), the fall reference (+0x168), the animation index
(critter +0x200), the active ControllerState, the camera direction the input builder read (AZ-508: a stack local,
so the fork's PC hook at 0x85276 collects it, ``CamHook``), inventory changes, the level's switch and timer nodes the
meta file names, and every critterGenerator's numDead (a boss's too), on change (numbers only, never game bytes);
missed ticks as ``gap_ticks``; each state load marked (the run log's ``xemu: state loaded`` lines, the tag matched
by the clock, level and disc ``note_tag`` recorded against the tray's, AZ-612). On the fork's v0.15 each row is taken at the player update's RET by a
PC hook (``HookRows``, Step X.32b; a row says ``ret``): one tick's fields together (AZ-518: a poll could read a new
clock with the tick before's state, state time or body), the pad the input builder read, and the nodes by address
expressions from their record indices, evaluated at every tick, so a load, a reload or the game's own respawn
(AZ-479) is followed from the next tick. On an older build the shared-RAM poller records instead: the pad read first
at every poll, exact, with the read before the tick where it differs (``tick_pads``, AZ-475), and the nodes resolved
again after every load or clock jump (AZ-397) and after a watched node's pointer moved (AZ-479; the row says
``moved``). ``TickReplay`` and ``fit_cams`` skip a poller's row that holds the tick before's (AZ-518's marker). It
stops on SIGTERM, SIGINT or a ``STOP`` file beside the trace.

``replay`` replays a run of a trace tick by tick in a sandbox (``TickReplay``: each tick's pad block and camera
written where the game reads them, the body, state and HP compared with the trace's), and ``fit-cams`` fits the
camera per tick in L3 for a trace recorded without one (``fit_cams``: X.36's M2):

    uv run --locked python -m devkit xemu demo fit-cams <trace.jsonl> --lines A:B --snapshot LABEL --out CAMS
    uv run --locked python -m devkit xemu demo replay <W> <trace.jsonl> --lines A:B --tag TAG [--cams CAMS] --out RES

``replug`` re-plugs the owner's pad bound on port 1 (X.27, X.28) 3 s after a load restored a guest USB state
without it (the game's pad handle slot 2 empty); on port 2, where the D98 states were saved with a pad, no
re-plug is expected [inferred, untried with the owner's pad]. It also logs, timestamped, each change of W's QMP
socket: gone, replaced, or no longer accepting a connection (``QmpWatch``; sitting x32 lost it with its xemu
alive, cause open). It only logs. Both watchers talk QMP only while they hold W's QMP turn (``xo.QmpTurn``, AZ-644),
which the kit's serve holds for each request, so they may run through a demo's setup, its boots, tags and loads.

USA VAs; dev only (devkit, Step 4.14a3): pytest runs only the harness's offline selftest, which checks the recorder
on a fake (``tests/test_xemu_harness.py``). ``fit-cams`` runs L3 (``devkit.sim.l3``, Step 4.13a). The trace holds
positions: keep it private (the L3 store), never ``$EV`` or a repo.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import json
import math
import os
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path
from typing import Callable

from azurkit.tools.randomizer.live import pages, recipes
from devkit.sim import obs
from devkit.sim import snapshot as l3   # Modkit's sim.l3 without its CPU (Step 4.14a1); L3 itself: fit-cams
from devkit.xemu import oracle as xo

GRAPH, VEC, ATTRS_AT = 0xDC, 0x24, 0x08   # [pd+0xDC] the level's main graph; +0x24 its node vector; node+8 attrs
GENERATOR_VT = 0x19D6B8   # a critterGenerator node's vtable (USA; the live tracker's ADDRESSES["generator"])
NUM_DEAD = 0x20           # its numDead, an f32 attribute at [node+8]+0x20 (live.ATTR_COUNTS + 8)
PAD_HANDLES = 0x1BE314                    # the game's four pad handles (X.27: slot 2 empties after such a load)
PADF = {"lx": 0x00, "ly": 0x04, "rx": 0x08, "ry": 0x0C, "dpy": 0x10, "dpx": 0x14, "a": 0x18, "b": 0x1C, "x": 0x20,
        "y": 0x24, "blk": 0x28, "wht": 0x2C, "lt": 0x30, "rt": 0x34, "u38": 0x38, "u3c": 0x3C, "start": 0x40,
        "back": 0x44}
NODE_RX = (r"(?i)toggle|switch|keylock|keystand|blocker|latch|timer|torpedo|tower|lift|spot|machine|beam|door|gate|"
           r"ring|elev|lever|button|plate|counter|combiner|fan|wind|updraft|gear")
ATTRS = ("goal", "output", "turnOn", "currentTime", "repeat", "rate", "input", "enable", "state", "value")
POLL_S, FLUSH_S = 0.002, 2.0
HOOK_POLL_S = 0.05        # the RET rows' drain: each drain takes every tick since the last, so it needn't keep pace
CR_ANIM = 0x200           # the critter's animation index (i32)
CAM_HOOK = {"pcs": [l3.CAMERA_DIR], "collect": [{"addr": "esp+0x14", "size": 8}, {"addr": "ebp+0x18", "size": 8}]}
"""The fork's PC hook (v0.15's ``xemu-hooks-set``; collects, writes nothing) at 0x85276, where the input builder reads
the camera's ground direction: the two f32 at [esp+0x14] and the entity's event clock +0x18 (EBP is the entity there:
0x84F95 loads it and nothing up to 0x85276 writes it but its two callees, which keep it) [verified static]."""
QMP_DRAIN_S = 0.25        # a drain waits this long for QMP (another client may hold it), then the row goes without
TAG_TIE_S = 0.05          # a load's tags whose gaps differ by less can't be told apart by the clock (match_tag)
NODE_RETRY_S = 1.0        # a level's node hooks QMP didn't take (held: the harness's load) are tried again this late
END_TURN_S = 30.0         # at its end the recorder waits this long for W's QMP turn to clear its hooks
DEMO_META = "demo-meta.json"   # W's meta file (note_level's, note_tag's): record's and add-body's default
DEMO_STARTS = {"w1": "vanilla-ig-w1", "f6": "vanilla-ig-f6"}   # add-body's boot states: SaveGame #1 in each level
DEMO_LEVELS = {"w1": "levels/water/w1", "f6": "levels/fire/f6"}  # the level each loads (boot_build's want: AZ-363)
LOAD_GAP_TICKS = 10       # add-body runs this many player ticks past a new tag before loading it (a visible jump)
VEL_S, QUAT_M = 1.0, 1.0  # fit_cams weighs a velocity error over 1 s (in the air one decays x0.983 a tick, so it
                          # moves the body about 2 s' worth) and a facing quaternion's as 1 m [proposal]


def rnd(v: float, k: int = 4):
    return round(v, k) if math.isfinite(v) else None


class Recorder:
    """One row per player tick from ``read(va, n)`` (guest RAM). ``meta``: ``{"levels": {level: {"count": the
    main graph's records, "nodes": {"<name>#<record>": {attr: index}}}}, "tags": {tag: {"clk", "lvl", "disc"}}}``.
    ``loads``: the run log's load count (``loads_seen``), read on a row a clock jump marks (AZ-522). ``disc``: the
    tray's disc name (``xo.tray_disc``), read on a load's row: a tag saved with another disc is never that load's
    (AZ-612)."""

    def __init__(self, read: Callable[[int, int], bytes], meta: dict | None = None,
                 cam: Callable[[float, float, int], tuple[bytes, int | None, list] | None] | None = None,
                 loads: Callable[[], int] | None = None, disc: Callable[[], str | None] | None = None):
        self.read, self.meta, self.cam = read, meta if meta is not None else {}, cam   # cam: CamHook.take
        self.loads, self.disc = loads, disc
        self.seen = loads() if loads is not None else 0   # the newest load count a row is marked with (or the start's)
        self.n = self.missed = 0
        self.last_clk = self.last_lvl = self.last_inv = None
        self.last_sw: dict = {}
        self.last_dead: dict = {}
        self.vas: dict = {}
        self.gens: dict[str, int] = {}   # "#<record>" -> a critterGenerator's numDead VA (AZ-479)
        self.pad_last: tuple | None = None   # (wall s, active index, ControllerState) at the poll before (AZ-475)
        self.watch: tuple | None = None  # (graph, vector begin, end, {record: (node, its attrs)}): what a respawn moves

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.read(va, 4))[0]

    def player(self) -> tuple[int, int, int, float]:
        """pd, the player critter, its entity and the entity's event clock; ``KeyError`` while there is none."""
        pd = self.u32(self.u32(recipes.SCENE_PTR) + recipes.SCENE_PD)
        crit = self.u32(pd + recipes.PD_PLAYER)
        ent = self.u32(crit + 0x180)
        if not crit or self.u32(ent + 0x20) != crit:
            raise KeyError("no player entity")
        clk = struct.unpack("<d", self.read(ent + 0x18, 8))[0]
        if not math.isfinite(clk):
            raise KeyError("no event clock")
        return pd, crit, ent, clk

    def resolve(self, pd: int, level: str) -> dict[str, dict[str, int]]:
        """The level's node attribute VAs, from the meta's record and attribute indices against the live node
        vector (none when the meta has no such level or the graph's size differs); and, whatever the meta names,
        every critterGenerator node's numDead VA (``gens``: a boss's generator too, AZ-479). ``watch`` keeps the
        pointers they were read through, which ``moved`` checks."""
        graph = self.u32(pd + GRAPH)
        b, e = struct.unpack("<II", self.read(graph + VEC, 8))
        n = (e - b) // 4 if e >= b else 0
        nodes = struct.unpack(f"<{n}I", self.read(b, 4 * n)) if 0 < n <= 0x10000 else ()
        self.gens, held = {}, {}
        for i, node in enumerate(nodes):
            try:
                if node and self.u32(node) == GENERATOR_VT:
                    held[i] = (node, self.u32(node + ATTRS_AT))
                    self.gens[f"#{i}"] = held[i][1] + NUM_DEAD
            except OSError:   # a record whose node isn't mapped: not a generator we can read
                continue
        out = {}
        spec = self.meta.get("levels", {}).get(level)
        if spec and n == spec["count"]:
            for key, attrs in spec["nodes"].items():
                if node := nodes[int(key.rsplit("#", 1)[1])]:
                    ap = self.u32(node + ATTRS_AT)
                    held[int(key.rsplit("#", 1)[1])] = (node, ap)
                    out[key] = {a: ap + 4 * k for a, k in attrs.items()}
        self.watch = (graph, b, e, held)
        return out

    def moved(self, pd: int) -> bool:
        """Whether the nodes the recorder reads moved since ``resolve``: the graph, its vector, a watched record's
        node or that node's attributes (AZ-479: the game's own respawn re-allocates them with no load and no clock
        jump, so X.34's reads after Spideyzar's respawn were stale)."""
        if self.watch is None:
            return False
        graph, b, e, held = self.watch
        if self.u32(pd + GRAPH) != graph or struct.unpack("<II", self.read(graph + VEC, 8)) != (b, e):
            return True
        vec = self.read(b, e - b) if held else b""
        return any(struct.unpack_from("<I", vec, 4 * i)[0] != node or self.u32(node + ATTRS_AT) != ap
                   for i, (node, ap) in held.items())

    def match_tag(self, clk: float, level: str, disc: str | None = None) -> tuple[str | None, float | None, list]:
        """The tag a load to ``clk`` in ``level`` restored: the meta's tag on that level whose clock is 0.05 s before
        to 3 s after, the smallest gap, but never one saved with another disc than ``disc`` (the tray's, a name or a
        path: compared by name, so a W spelled another way, /private/tmp for /tmp, still matches; None: not known).
        Every boot tag is its save's arrival plus the same 60 ticks, so builds' tags share clocks (AZ-612: 2.142's two
        w1 tags 0.0000 s apart): tags within ``TAG_TIE_S`` of the smallest gap can't be told apart, and
        then none is named. Returns the tag (or None), its gap and the tied tags."""
        near = sorted((clk - t["clk"], tag) for tag, t in self.meta.get("tags", {}).items()
                      if t.get("lvl") == level and -0.05 <= clk - t["clk"] <= 3.0
                      and not (disc and t.get("disc") and Path(t["disc"]).name != Path(disc).name))
        if not near:
            return None, None, []
        tied = [tag for d, tag in near if d - near[0][0] < TAG_TIE_S]
        return (near[0][1] if len(tied) == 1 else None), near[0][0], tied

    def tray(self) -> str | None:
        """The tray's disc (``disc``), None without one or on a QMP error."""
        try:
            return self.disc() if self.disc is not None else None
        except (OSError, EOFError, ValueError, KeyError, TypeError):
            return None

    def pad(self) -> tuple[int, bytes]:
        """The active pad index and its ControllerState (0x54 bytes: the floats the input builder reads, then the
        latches)."""
        idx = self.u32(xo.ACTIVE_PAD)
        return idx, self.read(xo.CONTROLLER_STATE + 0x54 * (idx if idx < 4 else 0), 0x54)

    def flushed(self, k: int) -> int | None:
        """The flush's mark for the run log's load count ``k``: ``k`` while no row is marked with it (a load with no
        clock jump, or one whose jump row hasn't come yet), else None (its jump row took it: AZ-522)."""
        if k > self.seen:
            self.seen = k
            return k
        return None

    def step(self, now: float, load: int | None = None, hooked: tuple[dict, dict] | None = None) -> dict | None:
        """One poll: the row of a new player tick, else None. ``load``: the run log's load count, when a load was
        seen since the last row (``flushed``); a row a clock jump marks reads the count itself (``loads``) and takes
        it as seen, so no later row is marked for that load (AZ-522). ``hooked``: a RET record's node values
        (``HookRows``), read there, not resolved (a RET row, its ``read`` the record's: ``row_reader``).

        The pad (AZ-475): the game polls it once an update, then its input builder reads it and the player tick
        moves the clock. Each poll reads it right after the clock, so a row's ``pad`` is the first read after its
        tick (exact floats); when the last read before the tick differs, that one is ``pad_alt`` and the builder
        read one of the two (a poll fell between the reads; ``pad_ms`` apart). A row without ``pad_alt`` has the
        pad its tick's builder read unless ``pad_ms`` spans a whole tick (``tick_pads``)."""
        pd, crit, ent, clk = self.player()
        pad_now = (now, *self.pad())
        if clk == self.last_clk:
            self.pad_last = pad_now
            return None
        rate = struct.unpack("<d", self.read(l3.MAIN_RATE, 8))[0] or 30.0   # ticks a second (fps_unlock's F)
        e = self.read(ent, 0x1B0)
        g = lambda o, c="f": struct.unpack_from("<" + c, e, o)[0]   # noqa: E731
        row: dict = {"w": round(now, 4), "n": self.n, "clk": rnd(clk, 5)}
        jump = self.last_clk is not None and (clk < self.last_clk or clk - self.last_clk > 1.0)
        if jump and load is None and self.loads is not None:
            load = self.flushed(self.loads())   # None: no new count (an in-game reload, or one already marked)
        if self.last_clk is not None and not jump and clk - self.last_clk > 1.5 / rate:
            row["gap_ticks"] = round((clk - self.last_clk) * rate) - 1
            self.missed += row["gap_ticks"]
        level = self.read(pd + recipes.PD_LEVEL, 0x50).split(b"\0")[0].decode("latin-1")
        if level != self.last_lvl:
            row["lvl"] = level
        moved = not (jump or load is not None or level != self.last_lvl) and hooked is None and self.moved(pd)
        if jump or load is not None or level != self.last_lvl or moved:   # a load or a respawn re-allocates the
            if jump or load is not None:                                   # nodes: resolve again
                disc = self.tray()
                tag, gap, tied = self.match_tag(clk, level, disc)
                row["load"] = {"clk_jump": jump, "loads": load, "tag": tag,
                               "since_save_s": round(gap, 3) if tag else None,
                               **({"disc": disc} if self.disc is not None else {}),
                               **({"tags": tied} if len(tied) > 1 else {})}
            if moved:
                row["moved"] = True
            self.vas = {} if hooked is not None else self.resolve(pd, level)
            self.last_sw, self.last_inv, self.last_lvl, self.last_dead = {}, None, level, {}
        row.update(st=g(0x94, "I"), pst=g(0x98, "I"), stt=rnd(g(0x9C)), pos=[rnd(g(o)) for o in (0x38, 0x3C, 0x40)],
                   vel=[rnd(g(o)) for o in (0x24, 0x28, 0x2C)], bbz=rnd(g(0x1A4)), fl=g(0xD8, "i"),
                   hold=rnd(g(0x148)), actl=rnd(g(0x140)), h=rnd(g(0x144)), peak=rnd(g(0x164)))
        row.update(nrm=[rnd(g(o)) for o in (0xB8, 0xBC, 0xC0)], fref=rnd(g(0x168)),
                   anim=struct.unpack("<i", self.read(crit + CR_ANIM, 4))[0])
        row["body"] = [rnd(v) for v in struct.unpack("<3f", self.read(crit + recipes.CR_BODY, 12))]
        row["quat"] = [rnd(v) for v in struct.unpack("<4f", self.read(crit + recipes.CR_QUAT, 16))]
        row["hp"] = list(struct.unpack("<ii", self.read(crit + recipes.CR_HP, 8)))
        am = self.u32(pd + recipes.PD_ARMOR)
        slot = self.u32(am + 0x20)
        row["fuel"] = rnd(struct.unpack("<f", self.read(am + 0x24, 4))[0])
        row["mask"] = struct.unpack("<i", self.read(am + 0x1C, 4))[0]
        row["arm"] = [struct.unpack("<i", self.read(slot + o, 4))[0] for o in (0x08, 0x38)] if slot else None
        _, idx, pb = pad_now
        row["pidx"] = idx
        row["pad"] = pad_dict(pb)
        row["latch"] = list(pb[0x48:0x54])
        if self.pad_last is not None and not jump and load is None and hooked is None:   # (a RET row's is exact)
            row["pad_ms"] = round((now - self.pad_last[0]) * 1000, 1)
            if self.pad_last[1] != idx or self.pad_last[2][:0x48] != pb[:0x48]:
                row["pad_alt"] = pad_dict(self.pad_last[2])
                if self.pad_last[1] != idx:
                    row["pidx_alt"] = self.pad_last[1]
        self.pad_last = pad_now
        # AZ-508: what this tick's builder read, and the ticks' it missed before it
        if self.cam is not None and (c := self.cam(clk, rate, row.get("gap_ticks", 0))) is not None:
            row["cam"], row["cf"] = list(struct.unpack("<2f", c[0])), c[1]
            if c[2]:
                row["cam_gap"] = [None if x is None else list(struct.unpack("<2f", x)) for x in c[2]]
        inv = recipes.inventory(self.read(self.u32(pd + recipes.PD_INV), recipes.INV_SAVED))
        if self.last_inv is None:
            row["inv"] = inv
        elif inv != self.last_inv:
            row["inv_ch"] = {k: v for k, v in inv.items() if self.last_inv.get(k) != v}
        self.last_inv = inv
        sw, dead = hooked if hooked is not None else self._nodes()
        if sw:
            strip = lambda d: {a: x for a, x in d.items() if a != "currentTime"}   # noqa: E731
            if self.n % 300 == 0 or not self.last_sw:
                row["sw_all"] = sw
            elif ch := {k: v for k, v in sw.items() if strip(self.last_sw.get(k, {})) != strip(v)}:
                row["sw"] = ch
            self.last_sw = sw
        if dead:   # every generator's numDead (a boss's death, a pickup, a respawned spot), on change
            if self.n % 300 == 0 or not self.last_dead:
                row["dead_all"] = dead
            elif ch := {k: v for k, v in dead.items() if self.last_dead.get(k) != v}:
                row["dead"] = ch
            self.last_dead = dead
        self.last_clk, self.n = clk, self.n + 1
        return row

    def _nodes(self) -> tuple[dict, dict]:
        """The watched nodes' attributes and every generator's numDead, read at the VAs ``resolve`` found."""
        f32 = lambda va: rnd(struct.unpack("<f", self.read(va, 4))[0], 3)   # noqa: E731
        return ({nm: {a: f32(va) for a, va in vas.items()} for nm, vas in self.vas.items()},
                {k: f32(va) for k, va in self.gens.items()})


class CamHook:
    """The camera direction the input builder read, per player tick (AZ-508): a stack local, which the shared-memory
    reads can't see, so the fork's PC hook :data:`CAM_HOOK` collects it at 0x85276 with no stop, and the recorder
    drains it over QMP at each row.  ``qmp(cmd, **args)`` sends one command and returns its reply (a connection per
    call: W's QMP serves one client).  ``arm`` installs the hook (it persists across loads; the recorder's own hook
    from an earlier ``arm`` is cleared first, another client's are left): the fork installs one only on a stopped VM
    (``xemu-hooks-set`` refuses a running one), so a running guest is paused for the call (QMP ``stop``, ``cont``: a
    few ms) and a stopped one (``-S``, the gdbstub's) is left so; on a build without hooks it says why (``why``)
    and the rows go without ``cam``.  ``disarm`` clears it and drains what it left (the recorder's exit).
    ``take(clk, rate, gap)`` drains and gives the camera (8 bytes) and the hit's frame of the newest hit whose entry
    clock is within 1.5 ticks before ``clk`` (the tick that moved the clock there), else None, and the cameras of
    the ``gap`` ticks the recorder missed before it (each the newest hit within half a tick of that tick's entry
    clock, else None)."""

    def __init__(self, qmp: Callable[..., dict]):
        self.qmp, self.recs, self.dropped, self.why, self.id = qmp, [], 0, "not armed", None
        self.fed = False   # its records come from HookRows' drain (one drain takes every hook's), not its own

    def arm(self) -> str | None:
        paused = False
        try:
            names = {c.get("name") for c in self.qmp("query-commands").get("return", [])}
            if "xemu-hooks-set" not in names:
                self.why = "this xemu has no PC hooks (the fork's v0.15 or later has them)"
                return self.why
            self.disarm()
            if self.qmp("query-status").get("return", {}).get("status") == "running":
                paused = "return" in self.qmp("stop")
            r = self.qmp("xemu-hooks-set", hooks=[CAM_HOOK])
            self.why = None if "return" in r else f"xemu-hooks-set: {r.get('error')}"
            self.id = r["return"][0].get("id") if self.why is None and r["return"] else None
        except (OSError, EOFError, ValueError) as e:
            self.why = f"QMP: {e}"
        finally:
            if paused:
                self._cont()
        return self.why

    def _cont(self) -> None:
        """``cont`` after ``arm``'s pause (``cont``; else the guest stays paused: said)."""
        if not cont(self.qmp):
            self.why = (self.why or "armed") + "; cont failed: the guest is left paused"

    def disarm(self) -> None:
        """Clear this recorder's hook, if armed (another client's stay), and drain the records it left (they would
        come back in the next ``xemu-frame-advance`` reply)."""
        if self.id is None:
            return
        hid, self.id = self.id, None
        try:
            self.qmp("xemu-hooks-clear", ids=[hid])
            self.drain()
        except (OSError, EOFError, ValueError):
            pass

    def drain(self) -> None:
        r = self.qmp("xemu-hooks-drain").get("return") or {}
        self.dropped += r.get("dropped") or 0
        self.feed(r.get("records", ()))

    def feed(self, records) -> None:
        """Keep the camera hits among ``records`` (a drain's, in execution order), the newest 512."""
        for x in records:
            if x.get("pc") == l3.CAMERA_DIR and len(x.get("data", ())) >= 2 and all(x["data"][:2]):
                self.recs.append((struct.unpack("<d", bytes.fromhex(x["data"][1]))[0], bytes.fromhex(x["data"][0]),
                                  x.get("frame")))
        del self.recs[:-512]

    def take(self, clk: float, rate: float, gap: int = 0) -> tuple[bytes, int | None, list] | None:
        if self.why is not None:
            return None
        try:
            if not self.fed:
                self.drain()
        except (OSError, EOFError, ValueError):   # QMP held past QMP_DRAIN_S: this row goes without
            return None
        for i in range(len(self.recs) - 1, -1, -1):
            c, cam, frame = self.recs[i]
            if 0 < clk - c <= 1.5 / rate:
                missed = []
                for j in range(gap):   # the missed tick j entered about gap + 1 - j ticks before clk
                    at = clk - (gap + 1 - j) / rate
                    missed.append(next((h[1] for h in reversed(self.recs[:i]) if abs(h[0] - at) <= 0.5 / rate),
                                       None))
                del self.recs[:i + 1]
                return cam, frame, missed
        return None


E_PD = f"[[{recipes.SCENE_PTR:#x}]+{recipes.SCENE_PD:#x}]"   # address expressions (the fork's v0.15): pd
E_ENT = f"[[{E_PD}+{recipes.PD_PLAYER:#x}]+0x180]"           # the player's entity
ROW_REGIONS = (   # what a row reads, collected at the player update's RET, each by an expression evaluated there
    (hex(recipes.SCENE_PTR), 4), (f"[{recipes.SCENE_PTR:#x}]+{recipes.SCENE_PD:#x}", 4),   # the scene, pd
    (E_PD, recipes.PD_INV + 4),                                    # pd: its level, player, armor, graph, inventory
    (f"[{E_PD}+{recipes.PD_PLAYER:#x}]+{recipes.CR_BODY:#x}", recipes.CR_HP + 8 - recipes.CR_BODY),  # the critter
    (E_ENT, 0x1B0),                                                # the entity
    (f"[{E_PD}+{recipes.PD_ARMOR:#x}]+0x1c", 0xC),                 # the armor manager's mask, slot and fuel
    (f"[[{E_PD}+{recipes.PD_ARMOR:#x}]+0x20]+0x8", 0x34),          # its slot's Level to Flaps
    (f"[{E_PD}+{recipes.PD_INV:#x}]", recipes.INV_SAVED),          # the inventory
    (hex(l3.MAIN_RATE), 8), (hex(xo.ACTIVE_PAD), 4), (hex(xo.CONTROLLER_STATE), 0x54 * 4))
ROW_KEY = {"addr": f"{E_ENT}+0x18", "size": 8}   # the player's event clock: a hit per tick, at its own RET
ROW_COND = [{**ROW_KEY, "type": "f", "op": "ge", "value": -1e300}]   # (false while there is no player: unreadable)
ROW_HOOK = {"pcs": list(l3.UPDATE_RETS), "key": ROW_KEY, "cond": ROW_COND,
            "collect": [{"addr": a, "size": n} for a, n in ROW_REGIONS]}
"""The row's hook (AZ-518, Step X.32b): the player update writes its event clock at 0xAB830, before its state
machine 0x8CCC0, so a poll can read a new clock with the tick before's state, state time or body; at the update's
RET the whole row is one tick's. The pointers come first, so ``row_reader`` places each region where it was read."""


def row_reader(data: list[str]) -> Callable[[int, int], bytes]:
    """``read(va, n)`` over one row hook record (``ROW_HOOK``'s regions, in order), each region at the address the
    pointers before it name, for :class:`Recorder`'s reads; ``OSError`` past them, as an unmapped page is."""
    b = [bytes.fromhex(d) if d else b"" for d in data]
    u = lambda blk, o=0: struct.unpack_from("<I", blk, o)[0] if len(blk) >= o + 4 else 0   # noqa: E731
    scene, pd = u(b[0]), u(b[1])
    crit, am, inv = u(b[2], recipes.PD_PLAYER), u(b[2], recipes.PD_ARMOR), u(b[2], recipes.PD_INV)
    mem = {recipes.SCENE_PTR: b[0], scene + recipes.SCENE_PD: b[1], pd: b[2], crit + recipes.CR_BODY: b[3],
           u(b[3], 0x180 - recipes.CR_BODY): b[4], am + 0x1C: b[5], u(b[5], 0x20 - 0x1C) + 0x8: b[6], inv: b[7],
           l3.MAIN_RATE: b[8], xo.ACTIVE_PAD: b[9], xo.CONTROLLER_STATE: b[10]}

    def read(va: int, n: int) -> bytes:
        for base, blk in mem.items():
            if blk and base <= va and va + n <= base + len(blk):
                return blk[va - base:va - base + n]
        raise OSError(f"read {va:#x}: not in the row's record")
    return read


def node_hooks(meta: dict, level: str, count: int | None, gens: list[int]) -> tuple[list[dict], list[tuple]]:
    """The level's watched nodes (the meta's, when its count is the graph's) and its critterGenerators' numDead
    (``gens``: their record indices) as collect hooks at the update's RET, keyed as rows are, each region an address
    expression from the record index, evaluated at every hit (AZ-479: a respawn that re-allocates a node is followed
    from the next tick, with no load and no clock jump); 63 regions a hook after the clock. Returns the hooks and,
    per region, how its bytes read back (``node_values``)."""
    def node(i: int) -> str:
        return f"[[[{E_PD}+{GRAPH:#x}]+{VEC:#x}]+{4 * i:#x}]"
    spec = meta.get("levels", {}).get(level)
    regions: list[tuple] = []
    for key, attrs in (spec["nodes"].items() if spec and spec["count"] == count else ()):
        lo, hi = min(attrs.values()), max(attrs.values())
        regions.append(("sw", key, lo, attrs, f"[{node(int(key.rsplit('#', 1)[1]))}+{ATTRS_AT:#x}]+{4 * lo:#x}",
                        4 * (hi - lo + 1)))
    regions += [("dead", f"#{i}", NUM_DEAD // 4, {}, f"[{node(i)}+{ATTRS_AT:#x}]+{NUM_DEAD:#x}", 4) for i in gens]
    hooks = [{**{k: ROW_HOOK[k] for k in ("pcs", "key", "cond")},
              "collect": [ROW_KEY, *({"addr": r[4], "size": r[5]} for r in regions[i:i + 63])]}
             for i in range(0, len(regions), 63)]
    return hooks, regions


def node_values(records: list[dict], regions: list[tuple]) -> tuple[dict, dict]:
    """``node_hooks``' records of one tick (one per hook, in its order) read back: the watched nodes' attributes
    and the generators' numDead (a region that didn't read is left out)."""
    sw: dict = {}
    dead: dict = {}
    data = [d for x in records for d in x["data"][1:]]
    for (kind, key, lo, attrs, _, _), d in zip(regions, data):
        if not d:
            continue
        v = struct.unpack(f"<{len(d) // 8}f", bytes.fromhex(d))
        if kind == "sw":
            sw[key] = {a: rnd(v[k - lo], 3) for a, k in attrs.items()}
        else:
            dead[key] = rnd(v[0], 3)
    return sw, dead


class HookRefused(OSError):
    """xemu refused an ``xemu-hooks-set`` (its answer, not a held QMP: asking again gets the same)."""


class HookRows:
    """The recorder's rows taken at the player update's RET by the fork's PC hooks (v0.15, AZ-518, Step X.32b): the
    row hook (``ROW_HOOK``) and, per level, the node hooks (``node_hooks``), drained with the camera's in one
    ``xemu-hooks-drain`` (``qmp``, a connection per call, as ``CamHook``'s) without pausing the guest. ``arm`` sets
    the row hook (the guest paused around the call, as ``CamHook.arm``); ``why`` says why not (a build without
    hooks: the shared-RAM poller records). ``nodes(level, pd)`` sets the level's node hooks (their generators
    found through ``live``, a reader of the running guest's RAM: the shared memory), ``drain`` returns the row
    records in order with their tick's node values, feeding the camera hook its records. ``disarm`` clears this
    recorder's hooks only. ``notes`` collects what the trace should say (node hooks not set, a guest left
    paused)."""

    def __init__(self, qmp: Callable[..., dict], cams: CamHook, live: Callable[[int, int], bytes], meta: dict):
        self.qmp, self.cams, self.live, self.meta = qmp, cams, live, meta
        self.id, self.node_ids, self.regions, self.level = None, [], [], None
        self.stale: list[int] = []   # node hooks a set that didn't go through left for the next set to clear
        self.why, self.dropped, self.retry_at, self.notes = "not armed", 0, 0.0, []
        self.held: dict[str, list[dict]] = {}   # node records by their tick's clock, for a row a later drain brings

    def _set(self, hooks: list[dict], clear: list[int]) -> list[int]:
        """``clear``'s ids cleared, each out of the list once xemu answered (one a call, the guest running: xemu
        clears none of a call naming one it no longer has, its error reply), then ``hooks`` installed, the guest
        paused around that call if it ran (xemu sets hooks only on a stopped VM; a ``cont`` that fails for 5 s is
        noted: the guest is left paused); a refusal raises ``HookRefused``."""
        for i in list(clear):
            self.qmp("xemu-hooks-clear", ids=[i])
            clear.remove(i)
        if not hooks:
            return []
        paused = False
        try:
            if self.qmp("query-status").get("return", {}).get("status") == "running":
                paused = "return" in self.qmp("stop")
            r = self.qmp("xemu-hooks-set", hooks=hooks)
            if "return" not in r:
                raise HookRefused(f"xemu-hooks-set: {r.get('error')}")
            return [h.get("id") for h in r["return"]]
        finally:
            if paused and not cont(self.qmp):
                self.notes.append("cont failed after a hook call: the guest is left paused")

    def arm(self) -> str | None:
        """Set the row hook (the last one's cleared first); else ``why`` says why not, and the camera hook drains
        its own records again (``fed``), as the poller's rows take them."""
        self.cams.fed = False
        try:
            names = {c.get("name") for c in self.qmp("query-commands").get("return", [])}
            if not {"xemu-hooks-set", "xemu-hooks-drain"} <= names:
                self.why = "this xemu has no PC hooks (the fork's v0.15 or later has them): rows by the poller"
                return self.why
            self.id, self.node_ids, self.level = self._set([ROW_HOOK], self.disarm(drain=False))[0], [], None
            self.why = None
            self.cams.fed = True
        except (OSError, EOFError, ValueError, IndexError) as e:
            self.why = f"QMP: {e}"
        return self.why

    def nodes(self, level: str, pd: int) -> None:
        """The level's node hooks in place of the last level's (``level`` None after a meta change or a relaunch
        makes the next row set them); until they are set the rows read no nodes. A set QMP didn't take (held: the
        harness's load) is tried again from the first row ``NODE_RETRY_S`` later; one xemu refused isn't, this
        level's rows reading none; each is noted."""
        if time.monotonic() < self.retry_at:
            return
        self.stale += self.node_ids   # the last level's: cleared by the set
        self.node_ids, self.regions = [], []
        try:
            count, gens = generators(self.live, pd)
        except (OSError, struct.error):
            count, gens = None, []   # the graph isn't readable yet (a load): this level's nodes go unread
        hooks, regions = node_hooks(self.meta, level, count, gens)
        try:
            self.node_ids = self._set(hooks, self.stale)
        except HookRefused as e:
            self.level = level
            self.notes.append(f"{level}: its node hooks refused, its rows read no nodes ({e})")
            return
        except (OSError, EOFError, ValueError, IndexError) as e:
            self.retry_at = time.monotonic() + NODE_RETRY_S
            self.notes.append(f"{level}: its node hooks not set, again in {NODE_RETRY_S:g} s (QMP: {e})")
            return
        self.regions, self.level = regions, level

    def drain(self) -> list[tuple[dict, tuple[dict, dict]]]:
        r = self.qmp("xemu-hooks-drain").get("return") or {}
        self.dropped += r.get("dropped") or 0
        recs = r.get("records", [])
        self.cams.feed(recs)
        for x in recs:
            if x.get("hook") in self.node_ids:
                self.held.setdefault(x["data"][0], []).append(x)
        out = []
        for x in recs:
            if x.get("hook") == self.id:
                mine = sorted(self.held.pop(x["data"][4][0x30:0x40], []), key=lambda n: self.node_ids.index(n["hook"]))
                out.append((x, node_values(mine, self.regions) if len(mine) == len(self.node_ids) else ({}, {})))
        while len(self.held) > 8:   # a tick whose row went by: its node records go too
            self.held.pop(next(iter(self.held)))
        return out

    def disarm(self, drain: bool = True) -> list[int]:
        """Clear this recorder's hooks, ``stale`` ones too (another client's stay); returns the ids it held, which
        ``drain=False`` leaves to the caller."""
        ids = [i for i in (self.id, *self.node_ids) if i is not None]
        self.id, self.node_ids = None, []
        if drain:
            self.stale += ids
            with contextlib.suppress(OSError, EOFError, ValueError):
                self._set([], self.stale)
        return ids


def generators(read: Callable[[int, int], bytes], pd: int) -> tuple[int, list[int]]:
    """The level's main graph's record count and its critterGenerator records (by vtable), read through ``read``."""
    graph = struct.unpack("<I", read(pd + GRAPH, 4))[0]
    b, e = struct.unpack("<II", read(graph + VEC, 8))
    n = (e - b) // 4 if e >= b else 0
    nodes = struct.unpack(f"<{n}I", read(b, 4 * n)) if 0 < n <= 0x10000 else ()
    out = []
    for i, node in enumerate(nodes):
        with contextlib.suppress(OSError):
            if node and struct.unpack("<I", read(node, 4))[0] == GENERATOR_VT:
                out.append(i)
    return n, out


def cont(qmp: Callable[..., dict], s: float = 5.0) -> bool:
    """QMP ``cont`` after a hook call's pause, again for ``s`` while QMP is held; whether the guest runs again."""
    end = time.monotonic() + s
    while True:
        try:
            if "return" in qmp("cont"):
                return True
        except (OSError, EOFError, ValueError):
            pass
        if time.monotonic() > end:
            return False
        time.sleep(0.05)


def pad_dict(pb: bytes) -> dict[str, float]:
    """A ControllerState's floats by name (``PADF``), exact (an f32 as the double it is: JSON gives it back)."""
    return {k: struct.unpack_from("<f", pb, o)[0] for k, o in PADF.items()}


def pad_block(pad: dict[str, float]) -> bytes:
    """``pad_dict``'s inverse: the 0x48 bytes of floats the input builder reads (the latches after them stay the
    game's)."""
    out = bytearray(0x48)
    for k, o in PADF.items():
        struct.pack_into("<f", out, o, pad.get(k, 0.0))
    return bytes(out)


def tick_pads(rows: list[dict]) -> list[dict]:
    """A trace's per-tick pads for a replay driven tick by tick (AZ-475; the fork's vblank-tagged input record
    lands on other ticks once the session's ticks ran long): one entry per player tick, ``{"n", "clk", "pidx",
    "block"}`` (``pad_block``) per row, plus ``"alt"``, the other block the builder may have read, where the
    recorder couldn't tell (``pad_alt``; ``None``, unknown, after missed ticks or reads more than 1.5 ticks apart, a
    tick's length taken from the rows' clocks, so at the build's rate). A row after ``gap_ticks`` missed ticks comes
    after that many entries ``{"missed": True}`` holding the last pad read (``alt`` None), so the list's index
    stays the tick's (``n`` counts rows). The first row and rows after a load or a jump start a new run
    (``"start": True``). A row taken at the update's RET (``ret``, Step X.32b) holds the very pad the builder read:
    no ``alt``. ``cam`` (AZ-508) is the camera direction (8 bytes) the builder read on the row's tick, None
    where the trace has none (an older trace, a build without hooks); a missed tick has the one the hook caught on it
    (the row's ``cam_gap``), else holds the last one. A driver
    writes ``block`` into ControllerState[pidx] at each update entry and ``cam`` at 0x85276 (:class:`TickReplay`),
    branching on ``alt``."""
    out: list[dict] = []
    prev = None
    for r in rows:
        if "n" not in r or "pad" not in r:
            continue
        t = {"n": r["n"], "clk": r["clk"], "pidx": r.get("pidx"), "block": pad_block(r["pad"]),
             "cam": struct.pack("<2f", *r["cam"]) if "cam" in r else None}
        gap = r.get("gap_ticks") or 0
        if "load" in r or prev is None or ("pad_ms" not in r and "ret" not in r):
            t["start"] = True
        else:
            cg = r.get("cam_gap") or [None] * gap
            out += [{"n": None, "clk": None, "pidx": prev["pidx"], "block": prev["block"], "alt": None,
                     "cam": prev["cam"] if cg[j] is None else struct.pack("<2f", *cg[j]), "missed": True}
                    for j in range(gap)]
        if "pad_alt" in r:
            t["alt"] = pad_block(r["pad_alt"])
        elif "ret" not in r and (gap or ("start" not in t and
                                         r["pad_ms"] > 1.5 * (r["clk"] - prev["clk"]) * 1000 / (1 + gap))):
            t["alt"] = None   # unknown: the reads were more than a tick apart (a RET row's pad is the builder's)
        out.append(t)
        prev = t
    return out


def torn(row: dict, now: tuple[int, float | None], prev: tuple[int, float | None] | None) -> bool:
    """AZ-518's marker for a row the shared-RAM poller wrote (one without ``ret``): it holds the tick before's state
    and state time where the replay moved on (``now``, ``prev``: the replay's (state, state time) on this tick and
    the one before, xemu's or L3's), as a poll inside the update reads them; the next whole row decides. A row taken
    at the update's RET, or one with no state time, never is."""
    if "ret" in row or prev is None or row.get("stt") is None:
        return False
    same = lambda o: o[0] == row["st"] and o[1] is not None and abs(o[1] - row["stt"]) <= 5e-4   # noqa: E731
    return same(prev) and not same(now)


class TickReplay:
    """One run of a demo's trace replayed tick by tick (AZ-475, AZ-508): ``rows`` the run's rows (its lines, from
    the load that starts it; one run: a later clock jump is refused) at ``rate`` ticks a second.  The tick entering
    clock key c (round(clock x rate)) takes the row with key c + 1, which the recorder wrote once that tick moved
    the clock (sitting x36: the first tick after a load enters at the load row's key).  A driver calls, per stop:

    - ``entry(c, active)`` at the player's update entry: the writes, the row's pad block (its ``alt`` where ``alts``
      holds c: :func:`fit_cams`'s choice) into ControllerState[active] (the replay's own active pad), or None past
      the run's end;
    - ``camera(esp)`` at 0x85276: the camera over [esp+0x14] as ``Sandbox.replay`` writes an L3 row's (``cams[c]``,
      :func:`fit_cams`'s, else the row's recorded ``cam``); none: the game's own camera runs;
    - ``ret(o)`` at the update's RET: the observation (``obs.read``) against the row, the body centre's error,
      state and HP; ``done`` once ``patience`` ticks in a row are off (more than ``diverge`` m, another state or HP).
      A poller's row that holds the tick before's (``torn``, AZ-518) is marked ``torn`` and judges nothing.

    ``results`` holds a dict per tick (``key``, ``err`` m, ``st_ok``, ``hp_ok``, ``cam`` written, ``pidx_ok``: the
    trace's active pad was the replay's; ``torn``): no positions."""

    def __init__(self, rows: list[dict], rate: float, *, cams: dict[int, bytes] | None = None,
                 alts: set[int] = frozenset(), diverge: float = 0.5, patience: int = 3):
        self.rate, self.cams, self.alts, self.diverge, self.patience = rate, cams or {}, alts, diverge, patience
        rows = [r for r in rows if "n" in r and "pad" in r]
        if any(r.get("load", {}).get("clk_jump") for r in rows[1:]):
            raise ValueError("the rows span a clock jump (a load): replay one run at a time")
        by_n, self.by_key, key = {r["n"]: r for r in rows}, {}, None
        for t in tick_pads(rows):
            key = round(t["clk"] * rate) if t["clk"] is not None else key + 1
            self.by_key[key] = (t, by_n.get(t["n"]))
        self.results: list[dict] = []
        self.cur: dict | None = None
        self.prev: tuple | None = None   # the replay's (state, state time) on the tick before
        self.bad, self.done = 0, False

    def entry(self, c: int, active: int) -> list[tuple[int, bytes]] | None:
        if (hit := self.by_key.get(c + 1)) is None:
            return None
        t, row = hit
        self.cur = {"key": c, "t": t, "row": row, "res": {"key": c, "cam": False, "pidx_ok": t["pidx"] == active}}
        block = t["alt"] if c in self.alts and t.get("alt") else t["block"]
        return [(xo.CONTROLLER_STATE + 0x54 * (active if active < 4 else 0), block)]

    def camera(self, esp: int) -> list[tuple[int, bytes]]:
        if self.cur is None or (cam := self.cams.get(self.cur["key"], self.cur["t"]["cam"])) is None:
            return []
        self.cur["res"]["cam"] = True
        return [(esp + 0x14, cam)]

    def ret(self, o) -> bool:
        cur, self.cur = self.cur, None
        res, row = cur["res"], cur["row"]
        if row is not None:
            res.update(err=round(math.dist(o.pos, row["body"]), 4), st_ok=o.state == row["st"],
                       hp_ok=o.hp == row["hp"][0])
            if torn(row, (o.state, o.state_t), self.prev):
                res["torn"] = True
            else:
                off = res["err"] > self.diverge or not (res["st_ok"] and res["hp_ok"])
                self.bad = self.bad + 1 if off else 0
        self.prev = (o.state, o.state_t)
        self.results.append(res)
        self.done = self.bad >= self.patience
        return self.done

    def summary(self, bar: float = 0.1) -> dict:
        r = [x for x in self.results if "err" in x and not x.get("torn")]
        errs = sorted(x["err"] for x in r)
        return {"ticks": len(self.results), "of": len(self.by_key) - 1, "torn": sum("torn" in x for x in self.results),
                f"within_{bar}m": sum(e <= bar for e in errs),
                "median_err_m": errs[len(errs) // 2] if errs else None, "max_err_m": errs[-1] if errs else None,
                f"first_over_{bar}m": next((x["key"] for x in r if x["err"] > bar), None),
                "state_differ": sum(not x["st_ok"] for x in r), "hp_differ": sum(not x["hp_ok"] for x in r),
                "first_state_differ": next((x["key"] for x in r if not x["st_ok"]), None),
                "cams_written": sum(x["cam"] for x in self.results),
                "pidx_differ": sum(not x["pidx_ok"] for x in self.results)}


def start_at(sb, tag: str) -> dict:
    """``loadvm tag`` paused, then run to the player's first update entry with no tick lost (the entity from the
    scene's chain, which the loaded RAM holds): where :func:`replay_ticks` starts.  Returns the entity, its event
    clock and ``start_hash`` (an L3 snapshot of the same start has the same, ``snapshot(here=True)``)."""
    res = sb.loadvm(tag, paused=True)
    g = sb.halt()
    ent = sb.read_u32(recipes.chain(sb.read_u32)["player"] + 0x180)
    for _ in range(64):
        if sb.wait_bp([l3.PLAYER_UPDATE], 10.0) != l3.PLAYER_UPDATE:
            raise SystemExit(f"no player update within 10 s of loading {tag}")
        if g.regs()["ecx"] == ent:
            break
    else:
        raise SystemExit(f"64 updates after loading {tag}, none of the player entity {ent:#x}")
    return {"tag": tag, "loadvm_s": res.get("loadvm_s"), "entity": ent,
            "clock": struct.unpack("<d", sb.read(ent + 0x18, 8))[0], "start_sha12": xo.start_hash(sb.read, ent)}


def replay_ticks(sb, tr: TickReplay, *, timeout: float = 5.0) -> dict:
    """``tr`` replayed in ``sb`` from the guest halted at the player's update entry (:func:`start_at`): at each
    update entry of that entity (a new event clock; a repeated report of one entry folded) ``tr.entry``'s writes,
    at 0x85276 ``tr.camera``'s, at the update's RET ``tr.ret`` on the light observation.  Ends at the run's end, at
    the entry after ``tr`` diverged, or on a stall (no update within ``timeout``: a dialog, a load); halted there
    with no breakpoints.  Returns how it ended (``at``: end, diverged or stall; the key)."""
    g = sb.halt()
    r = g.regs()
    if r["eip"] != l3.PLAYER_UPDATE:
        raise SystemExit(f"the guest is at {r['eip']:#x}, not the player's update entry: start_at first")
    ent, vas, last, end = r["ecx"], [l3.PLAYER_UPDATE, l3.CAMERA_DIR, *l3.UPDATE_RETS], None, {}
    xo.arm(g, vas)
    try:
        while True:
            if r["eip"] == l3.PLAYER_UPDATE and r["ecx"] == ent:
                clock = struct.unpack("<d", sb.read(ent + 0x18, 8))[0]
                if clock != last:
                    last, key = clock, round(clock * tr.rate)
                    writes = None if tr.done else tr.entry(key, g.u32(xo.ACTIVE_PAD))
                    if writes is None:
                        end = {"at": "diverged" if tr.done else "end", "key": key}
                        break
                    for va, data in writes:
                        g.write(va, data)
            elif r["eip"] == l3.CAMERA_DIR and tr.cur is not None:
                for va, data in tr.camera(r["esp"]):
                    g.write(va, data)
            elif r["eip"] in l3.UPDATE_RETS and tr.cur is not None:
                tr.ret(obs.read(sb.read, ent, deep=False))
            xo.resume(g, vas, r["eip"])
            sb._halted = False
            if not sb._wait(timeout):
                end = {"at": "stall", "key": None if last is None else round(last * tr.rate)}
                break
            r = g.regs()
    finally:
        g.cmd("?")
    return end


def _golden(f: Callable[[float], float], a: float, b: float, tol: float) -> float:
    k = (math.sqrt(5) - 1) / 2
    c, d = b - k * (b - a), a + k * (b - a)
    fc, fd = f(c), f(d)
    while b - a > tol:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - k * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + k * (b - a)
            fd = f(d)
    return (a + b) / 2


def fit_cams(sim, tr: TickReplay, *, scan_deg: int = 12, tol: float = 0.05) -> tuple[dict[int, bytes], set[int], dict]:
    """A camera per tick for a run recorded without one (AZ-508's older traces, X.36's M2), fitted in L3: ``sim``
    runs player ticks from the L3 snapshot of the run's start (its first update entry: ``replay --snapshot-as``,
    the same ``start_sha12`` as :func:`start_at`'s), each tick with the row's pad block written where the pad goes.
    On a tick whose stick is off rest the camera yaw is searched whose tick puts the body centre, the velocity and
    the facing (critter +0x18C) nearest the row's (their errors weighed by :data:`VEL_S` and :data:`QUAT_M`: the
    facing carries a roll's and a jump's direction, a velocity error the body's later ticks): the whole circle at 3 degrees on the
    run's first such tick, then +-``scan_deg`` at 1 degree round the last yaw, then a golden section to 1e-6 rad.
    Where the recorder kept the other pad the builder may have read (``alt``) both are fitted and the nearer
    taken.  L3 goes on from the choice.  A poller's row that holds the tick before's (``torn``, AZ-518: sitting x36's
    spikes, TD.0's B and A) isn't fitted: the last camera stays and the next whole row decides; such ticks are
    counted (``torn``) and left out of the comparison.  A tick with the stick at rest keeps
    the last camera (the builder's heading turns only the stick, 0x85276-0x85291) [inferred], and so does one where
    every yaw gives the same tick (the stick steers nothing: a roll; sitting TD.0); before the first fit
    none is written (the snapshot's own).  Returns the cams by entry key (``TickReplay(cams=)``), the keys whose
    ``alt`` pad was taken (``TickReplay(alts=)``) and counts: ticks run; fitted, their error's median and max (m) and
    how many over ``tol``; and over every tick L3's body against the trace's (within 0.1 m, the first
    tick past it, the first of 3 in a row past it: ``l3_off_from``, the max), ticks whose state or HP differ, and an
    L3 error that ended it."""
    k, pv, cams, alts, errs = round(sim.snap.meta["clock"] * tr.rate), sim.pad_va(), {}, set(), []
    out, every, yaw, prev = {"ran": 0, "differ": 0, "torn": 0}, [], None, None
    while (hit := tr.by_key.get(k + 1)) is not None:
        t, row = hit
        start = sim.save()

        def run(y: float | None, block: bytes):
            sim.reset(start)
            pad = l3.Pad() if y is None else l3.Pad(cam=struct.unpack("<2f", l3.camera_dir(y)))
            r = sim.step(pad, writes=[(pv, block)])
            if row is None:
                return r, 0.0
            quat = struct.unpack("<4f", sim.read(sim.u32(sim.entity + 0x20) + recipes.CR_QUAT, 16))
            return r, (math.dist(r.pos, row["body"]) + VEL_S * math.dist(r.obs.vel, row["vel"])
                       + QUAT_M * math.dist(quat, row["quat"]))

        def fit(block: bytes) -> tuple[float | None, float]:
            if row is None or not any(struct.unpack_from("<2f", block)):
                return yaw, run(yaw, block)[1]
            grid = ([yaw + math.radians(d) for d in range(-scan_deg, scan_deg + 1)] if yaw is not None
                    else [math.radians(d) for d in range(0, 360, 3)])
            es = [run(y, block)[1] for y in grid]
            if max(es) == min(es):   # the stick steers nothing this tick (a roll, an attack): no yaw is decided
                return yaw, es[0]
            best, w = grid[es.index(min(es))], math.radians(1 if yaw is not None else 3)
            y = _golden(lambda y: run(y, block)[1], best - w, best + w, 1e-6)
            return y, run(y, block)[1]
        try:
            r, _ = run(yaw, t["block"])
            if cut := row is not None and torn(row, (r.state, getattr(r.obs, "state_t", None)), prev):
                out["torn"] += 1   # AZ-518: the row holds the tick before's: no fit, the next whole row decides
            else:
                blocks = [t["block"], *([t["alt"]] if t.get("alt") else [])]
                (y, e), i = min(((fit(bl), i) for i, bl in enumerate(blocks)), key=lambda f: f[0][1])
                if y is not yaw:
                    errs.append(e)
                yaw = y
                if i:
                    alts.add(k)
                r, _ = run(yaw, blocks[i])
        except _l3_error() as ex:
            out["error"] = f"key {k}: {ex}"
            break
        if yaw is not None:
            cams[k] = l3.camera_dir(yaw)
        out["ran"] += 1
        if row is not None and not cut:
            every.append((k, math.dist(r.pos, row["body"])))
            out["differ"] += (r.state, r.hp) != (row["st"], row["hp"][0])
        prev = (r.state, getattr(r.obs, "state_t", None))
        k += 1
    errs.sort()
    return cams, alts, {**out, "fitted": len(errs), "alts": len(alts),
                        "median_err_m": round(errs[len(errs) // 2], 5) if errs else None,
                        "max_err_m": round(errs[-1], 5) if errs else None, f"over_{tol}m": sum(e > tol for e in errs),
                        "l3_within_0.1m": sum(e <= 0.1 for _, e in every),
                        "l3_first_over_0.1m": next((key for key, e in every if e > 0.1), None),
                        "l3_off_from": next((every[j][0] for j in range(len(every) - 2)
                                             if all(e > 0.1 for _, e in every[j:j + 3])), None),
                        "l3_max_err_m": round(max((e for _, e in every), default=0.0), 4)}


def _l3_error() -> type[Exception]:
    """L3's own error (``devkit.sim.l3``'s, Step 4.13a): ``fit_cams`` matches a tick's exception against it, which
    imports the engine only once a tick raised."""
    from devkit.sim.l3 import L3Error
    return L3Error


def trace_lines(path: Path, lines: str) -> list[dict]:
    """The trace's rows on lines ``A:B`` (0-based, both included): one run of a demo."""
    a, b = (int(x) for x in lines.split(":"))
    out = []
    with path.open(encoding="utf-8") as f:
        for i, ln in enumerate(f):
            if i > b:
                break
            if i >= a:
                out.append(json.loads(ln))
    return out


def sandbox_state(w: Path) -> dict:
    try:
        return json.loads((w / "sandbox.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit(f"{w} is not a sandbox (no sandbox.json)") from None


def shm_reader(w: Path) -> tuple[Callable[[int, int], bytes], shared_memory.SharedMemory, int]:
    """``read(va, n)`` over W's guest RAM in shared memory (its ``XEMU_RAM_SHM``, Step X.31a), through the page
    tables of the page directory the RAM holds (``pages.find_page_directory``: the retail kernel's at 0xF000 when it
    maps itself, as the live tracker finds it; no QMP), the shared memory and that directory's physical address.
    ``OSError`` while the RAM has none (a guest not yet booted)."""
    st = sandbox_state(w)
    if st.get("release", "usa") != "usa":
        raise SystemExit("the demo kit reads USA VAs: a USA sandbox only")
    if not st.get("ram_shm"):
        raise SystemExit(f"{w} has no XEMU_RAM_SHM (an older build or harness): the recorder needs it")
    shm = shared_memory.SharedMemory(st["ram_shm"], track=False)
    if (pd := pages.find_page_directory(shm.buf)) is None:
        shm.close()
        raise OSError(f"{w}'s guest RAM has no page directory yet")
    return l3.ram_reader(shm.buf, pd), shm, pd


def page_directory(buf, pd: int) -> int | None:
    """``pd`` while it is still the guest's page directory (it maps itself), else the one that does now, else None
    (AZ-438: the recorder runs with no gdbstub to check its CR3 against, so it checks the RAM itself)."""
    return pd if pages.maps_itself(buf, pd) else pages.find_page_directory(buf)


def loads_seen(w: Path) -> int:
    return xo.log_count(w, xo.LOADED)


class TurnQmp:
    """A demo watcher's QMP (AZ-644): one connection per command (``QMP_DRAIN_S``; W's QMP serves one client), sent
    only while the watcher's pass holds W's QMP turn (``turn``, ``xo.QmpTurn``), else ``OSError`` with no connect:
    the kit's serve is mid-request (a boot, a tag, a load), and the watcher's callers cope as with a held QMP."""

    def __init__(self, w: Path, timeout: float = QMP_DRAIN_S):
        self.w, self.timeout, self.turn = Path(w), timeout, xo.QmpTurn(w)

    def __call__(self, cmd: str, **args) -> dict:
        if not self.turn.mine:
            raise OSError(f"{self.w.name}: the serve's QMP turn (it holds W's QMP for a request)")
        q = xo.QMP(self.w / "qmp.sock", timeout=self.timeout)
        try:
            return q.execute(cmd, **args)
        finally:
            q.s.close()


def record(w: Path, out: Path, meta_path: Path | None = None) -> int:
    """Append a row per player tick to ``out`` until a signal or a ``STOP`` file beside it. On a build with PC hooks
    (v0.15) each row is taken at the player update's RET (``HookRows``: no row torn, AZ-518; the level's nodes by
    address expressions, AZ-479), drained every ``HOOK_POLL_S``; else W's guest RAM is polled every ``POLL_S``
    through its shared memory (``Recorder``). It re-reads the meta file at each pass it changed by (a tag saved and
    loaded in one serve request is named when its rows drain after it), and every ``FLUSH_S`` the run log's load
    count, and maps the shared memory again after a relaunch (a new xemu makes a new object under the name),
    arming the hooks again (the camera's, ``CamHook``, and the rows'; the meta line says which are armed; both
    cleared at the end). Each pass talks QMP only while it holds W's QMP turn (``TurnQmp``, AZ-644), which the kit's
    serve holds for each request, so it can run through a demo's setup: the hooks are armed (and the meta or
    ``relaunched`` line written) at the first pass with the turn, an arm whose QMP met another client is tried
    again (only a build without hooks makes the poller), and a drain waits in xemu meanwhile."""
    read, shm, pd = shm_reader(w)
    pid = sandbox_state(w).get("pid")
    stop = {"now": False}
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.update(now=True))

    qmp_once = TurnQmp(w)   # QMP only in a pass that holds W's QMP turn (AZ-644)
    cams = CamHook(qmp_once)
    meta_mt, rec = None, Recorder(read, cam=cams.take, loads=lambda: loads_seen(w),
                                 disc=lambda: xo.tray_disc(qmp_once("query-block")["return"], w))
    hooks = HookRows(qmp_once, cams, read, rec.meta)
    load, idle_t, flush_t, stop_t, last_row_t = None, 0.0, 0.0, 0.0, time.time()
    arm_due: str | None = "meta"   # the start's arm (the meta line), then a relaunch's: at a pass with the turn

    def armed() -> dict:
        res = {"cam_hook": cams.arm() or "armed", "rows": "ret" if hooks.arm() is None else f"poll: {hooks.why}"}
        if hooks.notes:
            res["hooks"], hooks.notes = list(hooks.notes), []
        return res

    def hook_rows(now: float) -> int:
        """The rows the drain brought (each read from its record), written; how many."""
        nonlocal load, last_row_t
        try:
            got = hooks.drain()
        except (OSError, EOFError, ValueError):   # QMP held (the serve's turn): the records wait in xemu
            return 0
        for x, nodes in got:
            rec.read = row_reader(x["data"])
            try:
                row = rec.step(now, load, nodes)
            except (KeyError, OSError, struct.error):
                continue
            if row is None:
                continue
            row.update(ret=1, f=x.get("frame"))
            f.write(json.dumps(row) + "\n")
            load, last_row_t = None, now
            if rec.last_lvl != hooks.level and x["data"][1]:   # a new level: its node hooks
                hooks.nodes(rec.last_lvl, struct.unpack("<I", bytes.fromhex(x["data"][1]))[0])
        for note in hooks.notes:
            f.write(json.dumps({"w": round(now, 3), "hooks": note}) + "\n")
        hooks.notes.clear()
        return len(got)
    with out.open("a", buffering=1, encoding="utf-8") as f:
        try:
            while not stop["now"]:
                nap, now = 0.0, time.time()
                if now - stop_t > FLUSH_S:   # (also while the serve holds the turn)
                    stop_t = now
                    if (out.parent / "STOP").exists():
                        break
                mine = qmp_once.turn.take()   # none while the serve runs a request: QMP waits for its end
                try:
                    if arm_due is not None:   # nothing is recorded until the hooks are armed or found missing
                        if not mine:
                            nap = HOOK_POLL_S
                            continue
                        res = armed()
                        if any(str(v).startswith(("QMP: ", "poll: QMP: ")) for v in res.values()):
                            nap = HOOK_POLL_S   # a QMP that met another client: armed at a later pass, never
                            continue            # the poller for the whole run (AZ-644)
                        f.write(json.dumps({"meta": {"started": xo.now(), "W": w.name, "poll_s": POLL_S, **res}}
                                           if arm_due == "meta" else {"w": round(now, 3), "relaunched": True, **res})
                                + "\n")
                        arm_due = None
                    if meta_path is not None and (mt := _mtime_ns(meta_path)) != meta_mt:   # every pass: a tag
                        meta_mt, rec.meta = mt, _meta(meta_path)   # saved and loaded in one serve request is named
                        rec.last_lvl, hooks.meta, hooks.level = None, rec.meta, None   # when its rows drain after it
                    if now - flush_t > FLUSH_S:
                        flush_t = now
                        if (now_pid := sandbox_state(w).get("pid")) != pid:
                            try:
                                (read, new, new_pd), pid = shm_reader(w), now_pid
                            except (OSError, EOFError, TypeError):
                                new = None   # not up yet: the next flush tries again
                            if new is not None:
                                shm.close()
                                shm, pd, rec.read, rec.last_lvl, rec.seen, hooks.live = new, new_pd, read, None, -1, read
                                cams.id = hooks.id = None   # the old xemu's hooks went with it
                                hooks.node_ids, hooks.stale, hooks.level, hooks.retry_at = [], [], None, 0.0
                                arm_due = "relaunched"
                                continue
                        if (now_pd := page_directory(shm.buf, pd)) != pd:   # AZ-438: checked, never assumed
                            f.write(json.dumps({"w": round(now, 3), "page_directory_moved": now_pd is not None}) + "\n")
                            if now_pd is not None:
                                pd, rec.last_lvl = now_pd, None
                                read = hooks.live = l3.ram_reader(shm.buf, now_pd)
                                if hooks.why is not None:
                                    rec.read = read
                        if (k := rec.flushed(loads_seen(w))) is not None:
                            load = k
                            f.write(json.dumps({"w": round(now, 3), "load_seen": k}) + "\n")
                    if hooks.why is None:
                        if not hook_rows(now) and now - last_row_t > FLUSH_S and now - idle_t > FLUSH_S:
                            f.write(json.dumps({"w": round(now, 3), "idle": True, "clk": rec.last_clk,
                                                **({} if mine else {"serve_turn": True})}) + "\n")
                            idle_t = now
                        nap = HOOK_POLL_S
                        continue
                    try:
                        row = rec.step(now, load)
                    except (KeyError, OSError, struct.error):
                        if now - idle_t > FLUSH_S:
                            f.write(json.dumps({"w": round(now, 3), "noent": True}) + "\n")
                            idle_t = now
                        nap = 0.01
                        continue
                    if row is None:
                        if now - last_row_t > FLUSH_S and now - idle_t > FLUSH_S:
                            f.write(json.dumps({"w": round(now, 3), "idle": True, "clk": rec.last_clk}) + "\n")
                            idle_t = now
                    else:
                        f.write(json.dumps(row) + "\n")
                        load, last_row_t = None, now
                    nap = POLL_S
                finally:
                    qmp_once.turn.drop()   # before the sleep: the serve's next request may take it
                    if nap:
                        time.sleep(nap)
        finally:
            got = qmp_once.turn.take(wait_s=END_TURN_S)   # the last rows and the hooks' clear need QMP
            try:
                if got and hooks.why is None and arm_due is None:
                    hook_rows(time.time())   # the rows still waiting
            finally:
                if got:
                    hooks.disarm()   # else the hooks stay, their records coming back in the next frame advance's reply
                    cams.disarm()
                qmp_once.turn.close()
        f.write(json.dumps({"end": xo.now(), "rows": rec.n, "missed_ticks": rec.missed,
                            "cam_dropped": cams.dropped, "rows_dropped": hooks.dropped,
                            **({} if got else {"hooks_left": "the serve held W's QMP turn"})}) + "\n")
    shm.close()
    return 0


class QmpWatch:
    """W's QMP socket, watched (Step X.34: sitting x32's ``qmp.sock`` was gone at 00:41 with its xemu alive, no
    relaunch, cause open): ``poll`` checks the file at every call and connects (closing at once) every
    ``probe_s`` and whenever the file changed; it returns one line per change (missing, replaced, not a socket,
    accepting or refusing a connection), else None. It logs only: nothing is fixed or retried."""

    def __init__(self, w: Path, probe_s: float = 10.0):
        self.path, self.probe_s = w / "qmp.sock", probe_s
        self.last: tuple[str, str | None] | None = None
        self.probed_at = -math.inf
        self.accepts: str | None = None

    def file(self) -> str:
        try:
            st = self.path.lstat()
        except FileNotFoundError:
            return "missing"
        return f"socket inode {st.st_ino}" if stat.S_ISSOCK(st.st_mode) else "not a socket"

    def connect(self) -> str:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.settimeout(2.0)
        try:
            c.connect(str(self.path))
            return "accepts a connection"
        except OSError as e:
            return f"refuses a connection ({errno.errorcode.get(e.errno, e.errno) if e.errno else type(e).__name__})"
        finally:
            c.close()

    def poll(self, now: float) -> str | None:
        f = self.file()
        if self.last is None or f != self.last[0] or now - self.probed_at >= self.probe_s:
            self.accepts, self.probed_at = (self.connect() if f.startswith("socket") else None), now
        if (cur := (f, self.accepts)) == self.last:
            return None
        was, self.last = self.last, cur
        said = ", ".join(x for x in cur if x)
        return f"qmp.sock: {said}" + (f" (was: {', '.join(x for x in was if x)})" if was else "")


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (TypeError, ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def replug_once(w: Path) -> list[dict]:
    """The owner's pad (port 1's binding, index 0) on a new hub at root port 1.1, over QMP (X.27's fix)."""
    q, out = xo.QMP(w / "qmp.sock"), []
    try:
        out.append(q.execute("device_del", id="demohub"))
        time.sleep(1.0)
        out.append(q.execute("device_add", driver="usb-hub", port="1.1", ports=3, id="demohub"))
        out.append(q.execute("device_add", driver="usb-xbox-gamepad", index=0, port="1.1.1", id="demopad"))
    finally:
        q.s.close()
    return out


def replug(w: Path, log_path: Path, once: bool = False) -> int:
    """Watch the game's pad handles every 0.5 s; slot 2 empty (slot 1 set) for 3 s after a load: re-plug (again every
    15 s while it stays empty). Its QMP (the socket's probe, the re-plug) waits for W's QMP turn (AZ-644): while the
    serve runs a request it is skipped, a due re-plug going at the next poll that has the turn. After a relaunch
    (``sandbox.json``'s pid changed) it maps the new xemu's shared memory (the old one's holds a stopped guest)."""
    def note(m: str) -> None:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {m}\n")
    if once:
        with xo.qmp_turn(w):
            note(f"replug: {json.dumps(replug_once(w))}")
        return 0
    pid, turn = sandbox_state(w).get("pid"), xo.QmpTurn(w)
    read, shm, _pd = shm_reader(w)
    bad, due, qw = 0, False, QmpWatch(w)
    note("watching")
    while True:
        mine = turn.take()
        try:
            if (now_pid := sandbox_state(w).get("pid")) != pid:   # a relaunch: the new xemu's shared memory
                try:
                    (read, new, _pd), pid = shm_reader(w), now_pid
                    shm.close()
                    shm = new
                    note(f"xemu relaunched (pid {pid}): its shared memory mapped again")
                except (OSError, EOFError, TypeError):
                    read = None   # not up yet: the next poll tries again
            if mine and (line := qw.poll(time.monotonic())):
                note(f"{line}; xemu pid {pid} {'alive' if _alive(pid) else 'gone'}")
            if read is not None:
                h = struct.unpack("<4I", read(PAD_HANDLES, 16))
                bad = bad + 1 if (h[2] == 0 and h[1] != 0) else 0
                due = (due or bad % 30 == 6) and bad > 0
                if due and mine:
                    due = False
                    note(f"slot 2 empty for {bad / 2:g} s: re-plugging: {json.dumps(replug_once(w))}")
        except (OSError, EOFError) as e:
            note(f"skipped: {e}")
            bad = 0
        finally:
            turn.drop()
        time.sleep(0.5)


def note_level(sb, iso, meta_path: Path) -> int:
    """Write the loaded level's switch and timer nodes into the recorder's meta file (a demo's setup driver, the
    guest halted): each one's record index in the main graph and its attributes' indices, which the recorder
    resolves against the live graph after every load. Returns how many."""
    from devkit.xemu import minigames as mg
    level = recipes.level_path(sb.read, sb.read_u32)
    lf = mg.Minigames(sb, iso, level.rsplit("/", 1)[-1])
    nodes = {}
    for nm in sorted({nm for nm in lf.g.names if nm and re.search(NODE_RX, nm)}):
        for i in lf.by.get(nm, []):
            al = lf.schema.types[lf.g.types[i]].attrs
            if sb.read_u32(lf.vec + 4 * i) and (idx := {a: al.index(a) for a in ATTRS if a in al}):
                nodes[f"{nm}#{i}"] = idx
    meta = _meta(meta_path)
    meta["levels"][level] = {"count": len(lf.g.recs), "nodes": nodes}
    _save_meta(meta_path, meta)
    return len(nodes)


def note_tag(sb, tag: str, meta_path: Path) -> None:
    """``savevm tag`` with its player clock and level in the meta file, so the recorder names a load of it, and what
    a replay of it needs (AZ-439): the disc it was saved with (a name in W), the USB devices it holds (the owner's pad
    hub, the replug watcher's demo hub) and the port the demo records (``Sandbox.adopt_tags``, then ``loadvm`` and
    ``play_recording(..., port=)`` in a ``Sandbox(pad_port=)`` on a clone of the demo's drive)."""
    ent = sb.read_u32(sb.g.regs()["esp"] + 4) if sb.g.regs()["eip"] == xo.PLAYER_TICK else None
    if ent is None:
        raise SystemExit("note_tag: halt at a player tick first")
    at = {"clk": struct.unpack("<d", sb.read(ent + 0x18, 8))[0], "lvl": recipes.level_path(sb.read, sb.read_u32)}
    sb.savevm(tag)
    meta = _meta(meta_path)
    meta["tags"][tag] = {**at, "disc": sb.st.get("tag_discs", {}).get(tag), "usb": sb.st.get("tag_usb", {}).get(tag),
                         "record_port": sb.st.get("record_port")}
    _save_meta(meta_path, meta)


def ground(s, n: int = 60, limit: int = 900, tries: int = 5) -> dict:
    """Halted at a player tick once ``n`` ticks in a row ran on the ground (state 0) at rest (under 0.05 m/s), a
    tag's start (Step 2.147's, moved into the kit); a popup or dialog that holds the player tick cleared by A
    (``clear_dialog``) and the count started again, ``tries`` runs of ``limit`` ticks. Its try and ticks (no
    positions)."""
    last = None
    for t in range(tries):
        if not (s.sb.g.regs()["eip"] == xo.PLAYER_TICK or s.tick(4.0) is not None or s.clear_dialog()):
            s.clear_dialog()
            continue
        run = {"n": 0}

        def at_rest(_sb, row, _rows):
            ok = row.get("state") == 0 and math.hypot(row.get("vx") or 0.0, row.get("vy") or 0.0) < 0.05
            run["n"] = run["n"] + 1 if ok else 0
            return ["stop"] if run["n"] >= n else None
        c = s.capture(limit, {}, label=None, on_tick=at_rest, body=False, chain=False)
        last = c["meta"].get("stop")
        if run["n"] >= n:
            return {"try": t + 1, "ticks": c["meta"]["rows"]}
        s.clear_dialog()
    raise SystemExit(f"never {n} ticks on the ground at rest in {tries} tries (last stop: {last})")


def add_body(s, sb, iso: Path | str | None, level: str = "w1", want: str | None = None,
             meta: Path | str | None = None, load: bool = True, what: dict | None = None) -> dict:
    """``add-body``'s request, in the kit's serve (holding W's QMP turn, so the demo's watchers step aside): a body's
    tag for an owner demo (Step X.56). ``iso`` (a build; None: the vanilla ISO, a setup's C0) staged, and refused
    when its sha12 isn't ``want``; its tag ``<serve>-<iso sha12>-<level>``. A tag the meta holds with that disc and
    this sandbox saved is loaded at once (a switch back). Else: the quiet boot at ``level``'s save
    (``DEMO_STARTS``: SaveGame #1, ``.text`` and ``SHIMS`` checked, a warm state saved, retries relaunching, a try
    that loads another level than ``DEMO_LEVELS``' a menu miss it retries), refused when it booted another ISO or
    level; a boot or tag that fails loads the tag loaded before it again (the body the owner played: ``_back``), else
    lets the guest run, and the error stands; the level's nodes noted once (``note_level``); 60 ticks at rest
    (``ground``), then ``note_tag``. The level the meta recorded for the tag must be the booted one (AZ-645:
    2.147's AE -w1 tag was saved in e6): once more from the warm boot state, then refused and dropped from the meta.
    One results row (no positions); then, with ``load``, ``LOAD_GAP_TICKS`` ticks run on (the load of a tag just
    saved, the guest halted there, moves no clock: the recorder names a load by its clock jump) and the tag loaded
    (the owner's pad waited for) and the guest let run (the owner plays; replug re-plugs a port-1 pad). ``meta``:
    default ``W/demo-meta.json``, the recorder's. Returns the row's names, hashes and times."""
    t0 = time.monotonic()
    if level not in DEMO_STARTS:
        raise SystemExit(f"add-body: level {level!r}: one of {', '.join(DEMO_STARTS)}")
    meta = Path(meta) if meta else sb.w / DEMO_META
    iso = Path(iso) if iso else xo.vanilla_iso()
    disc, sha12 = sb.stage(iso)
    if want and sha12 != want:
        raise SystemExit(f"add-body: {iso.name} is {sha12}, not the build's {want}")
    tag = f"{s.name}-{sha12}-{level}"
    out: dict = {**(what or {}), "tag": tag, "sha12": sha12, "level": level, "disc": disc}
    if (old := _meta(meta)["tags"].get(tag)) and old.get("disc") == disc and sb.loadable(tag):
        out["reused"] = True
    else:
        prev = sb.st.get("last_tag")   # the body the owner played: back to it if this one fails
        try:
            _new_body(s, sb, iso, tag, sha12, level, meta, load, out, t0)
        except BaseException:
            _back(s, sb, prev)
            raise
    if load:
        out.update(load_tag(s, sb, tag))
    out["total_s"] = round(time.monotonic() - t0, 1)
    return out


def _new_body(s, sb, iso: Path, tag: str, sha12: str, level: str, meta: Path, load: bool, out: dict,
              t0: float) -> None:
    """``add_body``'s new body: booted, its nodes noted, tagged at rest (AZ-645's level check), its row, and the
    ticks before its load."""
    start = DEMO_STARTS[level]
    b = s.boot(iso, start, quiet=True, want=DEMO_LEVELS[level])
    out.update(boot_s=b.get("s"), tries=b.get("tries"), warm=b.get("warm"), xbe_sha12=b.get("xbe_sha256"),
               incidents=[i.get("class") for i in b.get("incidents") or []])
    if b.get("iso_sha12") != sha12:
        raise SystemExit(f"add-body: booted {b.get('iso_sha12')}, not {sha12}")
    if not (booted := s.level()).endswith("/" + level):
        raise SystemExit(f"add-body: {start} booted into {booted}, not {level}")
    if booted not in _meta(meta)["levels"]:
        try:
            out["nodes"] = note_level(sb, xo.vanilla_iso(), meta)
        except Exception as e:  # noqa: BLE001  (the recorder then follows no switch nodes there)
            out["nodes"] = f"err {type(e).__name__}: {str(e)[:80]}"
    for attempt in (1, 2):
        out["ground"] = ground(s)
        note_tag(sb, tag, meta)
        if (saved := _meta(meta)["tags"][tag].get("lvl")) == booted:
            break
        out.setdefault("level_misses", []).append(saved)
        if attempt == 2:
            m = _meta(meta)
            m["tags"].pop(tag, None)
            _save_meta(meta, m)
            raise SystemExit(f"add-body: {tag} was saved in {saved}, not the booted {booted}, twice (AZ-645): "
                             "dropped from the meta")
        s.loadvm(f"b-{sha12}-{start}", quiet=True)   # the warm boot state: the boot's steady tick again
    out["tag_s"] = round(time.monotonic() - t0, 1)
    s.result({"case": "add-body", **out})
    if load:   # the load of a tag just saved, the guest halted there, moves no clock: run on a little first,
        for _ in range(LOAD_GAP_TICKS):   # so the recorder sees its clock jump back and names it
            if s.tick(2.0) is None:
                break


def _back(s, sb, prev: str | None) -> None:
    """After a failed ``_new_body``: ``prev`` (the tag loaded before it) loaded again, so the owner's window shows
    the body played before; else (none, not loadable here, or its load failed) the guest let run. The kit's load
    failures are SystemExits (tag_disc's refusal of an oracle tag in a demo, a failed loadvm, no owner's pad): caught
    too, so the failure that brought us here stands."""
    try:
        if prev and sb.loadable(prev):
            load_tag(s, sb, prev)
            xo.log(f"add-body failed: {prev} loaded again (the body before)")
            return
    except (Exception, SystemExit) as e:  # noqa: BLE001  (the failure that brought us here is the one that stands)
        xo.log(f"add-body failed, and {prev} didn't load again: {type(e).__name__}: {str(e)[:160]}")
    with contextlib.suppress(Exception, SystemExit):
        sb.release()


def load_tag(s, sb, tag: str) -> dict:
    """A demo tag loaded (the owner's pad waited for, as any demo load) and the guest let run: the owner plays."""
    t1 = time.monotonic()
    r = s.loadvm(tag)
    sb.release()
    return {"load_s": round(time.monotonic() - t1, 2), "loadvm": r.get("loadvm"), "pad_wait_s": r.get("pad_wait_s")}


def _git(root: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _request(sock: Path, src: str, key: str) -> dict:
    """One exec request to the serve; the JSON its output's ``key`` line holds (else its output, refused)."""
    from devkit.xemu import sitting as xs
    said = xs.send(sock, src)
    line = next((ln for ln in reversed(said.splitlines()) if ln.startswith(key + " ")), None)
    if line is None:
        raise SystemExit(f"add-body: the serve's request failed:\n{said.rstrip()[-6000:]}")
    return json.loads(line[len(key) + 1:])


def add_body_cli(sock: Path, body: str | None, *, mode: str | None = None, size: str | None = None,
                 level: str = "w1", vanilla: bool = False, load: bool = True, meta: Path | None = None,
                 extra: list[str] | None = None) -> int:
    """``add-body``: a body for the serving demo at ``sock`` (its exec socket) in under a minute (Step X.56). The build runs
    here, from this checkout's tree (``make_builds``: azurkit build --character '{"species": BODY}' from the
    vanilla ISO, D27, into the serve's private ``builds/``; a failed build stops before the serve is touched, D35; the
    same tree's same build is reused), so the owner plays on meanwhile; then one request (``add_body``) tags and loads
    it. Prints ``TAG <tag>`` and one JSON line of hashes and times."""
    from devkit.xemu import sitting as xs
    t0 = time.monotonic()
    if vanilla == bool(body):
        raise SystemExit("add-body: a body, or --vanilla (the vanilla ISO: a setup's C0), not both")
    info = _request(sock, "import json\nprint('ADD_BODY_INFO ' + json.dumps({'name': s.name, 'private': "
                    "str(s.private), 'w': str(sb.w), 'release': sb.st.get('release')}))", "ADD_BODY_INFO")
    if info.get("release", "usa") != "usa":
        raise SystemExit("add-body: the demo kit reads USA VAs: a USA sandbox only")
    root = Path(__file__).resolve().parents[2]
    head, main_ = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "origin/main")
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
    notes = ([f"HEAD isn't origin/main ({main_[:12] or 'unknown'}; nothing fetched or moved)"] if head != main_ else []) \
        + (["the tree has uncommitted changes"] if dirty else [])
    xo.log(f"add-body: {'the vanilla ISO' if vanilla else body} from {root.name} at {head[:12]}"
           + (f" ({'; '.join(notes)})" if notes else ""))
    iso, want, built, build_s = None, None, {}, 0.0
    if not vanilla:
        cli = ["build", "--character", json.dumps({"species": body, **({"mode": mode} if mode else {}),
                                                   **({"size": size} if size else {})}), *(extra or [])]
        label = "-".join([body, *([mode] if mode else []), *([size] if size else [])])
        name = f"{label}-{hashlib.sha256(json.dumps([head, cli]).encode()).hexdigest()[:8]}"
        out = Path(info["private"]) / "builds"
        out.mkdir(mode=0o700, exist_ok=True)
        index_p = out / "index.json"
        index = json.loads(index_p.read_text(encoding="utf-8")) if index_p.exists() else {}
        t1 = time.monotonic()
        if not dirty and name in index and (out / f"{name}.iso").exists():
            built = index[name]
        else:
            b = xs.make_builds({name: {"cli": cli}}, out, xo.vanilla_iso())[name]
            built = index[name] = {"iso_sha12": b["iso_sha12"], "xbe_sha12": b["xbe_sha12"], "head": head, "cli": cli}
            _save_meta(index_p, index)
        build_s, iso, want = round(time.monotonic() - t1, 1), str(out / f"{name}.iso"), built["iso_sha12"]
    what = {"body": body or "vanilla", "mode": mode, "size": size, "extra": extra or [], "main": head[:12],
            **({"xbe_sha12": built["xbe_sha12"]} if built else {})}
    seed = ("from pathlib import Path\n_st = Path(ISO).stat()\nsb.st.setdefault('staged', {})[f'{Path(ISO).resolve()}|"
            "{_st.st_size}|{_st.st_mtime_ns}'] = WANT   # stage's key: make_builds hashed this very file\n") if iso else ""
    res = _request(sock, f"import json\nfrom devkit.xemu import demo as xd\nISO, WANT = {iso!r}, {want!r}\n{seed}"
                   f"print('ADD_BODY ' + json.dumps(xd.add_body(s, sb, ISO, {level!r}, WANT, "
                   f"{str(meta) if meta else None!r}, {load!r}, {what!r})))", "ADD_BODY")
    print(f"TAG {res['tag']}")
    print(json.dumps({"sha12": res["sha12"], "main": head[:12], "build_s": build_s, "boot_s": res.get("boot_s"),
                      "ground": res.get("ground"), "reused": res.get("reused", False), "load_s": res.get("load_s"),
                      "total_s": round(time.monotonic() - t0, 1)}))
    return 0


def _mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def _meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"levels": {}, "tags": {}}


def _save_meta(path: Path, meta: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta), encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record", help="one JSONL row per player tick from W's guest RAM (XEMU_RAM_SHM)")
    p.add_argument("W", type=Path)
    p.add_argument("trace", type=Path, help="the JSONL trace (private: it holds positions)")
    p.add_argument("--meta", type=Path, help=f"the nodes and tags file note_level and note_tag write (default "
                   f"W/{DEMO_META}, add-body's)")
    p = sub.add_parser("add-body", help="build a body from this checkout, tag it in the serving demo (the quiet boot, "
                       "60 ticks at rest) and load it; prints TAG <tag> (Step X.56)")
    p.add_argument("sock", type=Path, help="the serve's exec socket (logs/sock-<name>.txt)")
    p.add_argument("body", nargs="?", help="the character's species or variant (e.g. air_elemental)")
    p.add_argument("--mode", choices=("own", "garret4"), help="the character's mode")
    p.add_argument("--size", choices=("own", "garret4"), help="the character's size")
    p.add_argument("--level", choices=tuple(DEMO_STARTS), default="w1", help="the save it boots at (default w1)")
    p.add_argument("--vanilla", action="store_true", help="no body: the vanilla ISO (a setup's control, C0)")
    p.add_argument("--no-load", action="store_true", help="tag it, leave it unloaded")
    p.add_argument("--meta", type=Path, help=f"the recorder's meta file (default W/{DEMO_META})")
    p = sub.add_parser("replug", help="re-plug the owner's pad on port 1 after a load drops it")
    p.add_argument("W", type=Path)
    p.add_argument("log", type=Path)
    p.add_argument("--once", action="store_true", help="re-plug now and exit")
    for name, text in (("replay", "replay one run of a trace tick by tick in W, against the trace's rows"),
                       ("fit-cams", "fit the camera per tick in L3 for a run recorded without one")):
        p = sub.add_parser(name, help=text)
        if name == "replay":
            p.add_argument("W", type=Path)
        p.add_argument("trace", type=Path)
        p.add_argument("--lines", required=True, help="A:B, the run's lines in the trace (0-based, both included; "
                       "A its load row)")
        p.add_argument("--out", type=Path, required=True, help="the per-tick results or cams (JSON, mode 0600: "
                       "keep it in the private store)")
        p.add_argument("--store", type=Path, help="the private L3 store (default: the user data dir's)")
        if name == "replay":
            p.add_argument("--tag", required=True, help="the state the run starts from (loadable in W)")
            p.add_argument("--owner-snapshot", action="store_true", help="allow --tag, a vm-* name, for this call: "
                           "the owner's own Snapshots save on a clone of a demo's private drive (never a July "
                           "vm-20260704* state, hazard 1)")
            p.add_argument("--demo-meta", type=Path, help="the demo's meta file (note_tag's): adopt its tags first "
                           "(a sandbox on a clone of the demo's drive, AZURIK_XEMU_HDD at up)")
            p.add_argument("--like", help="with --demo-meta: --tag takes this demo tag's disc and USB pads (an "
                           "owner's Snapshots save note_tag didn't record, saved with the same pads)")
            p.add_argument("--cams", type=Path, help="fit-cams' cameras, written over the trace's")
            p.add_argument("--snapshot-as", help="take an L3 snapshot of the start under this label first (for "
                           "fit-cams)")
            p.add_argument("--check-snapshot", help="refuse to replay unless the start is this L3 snapshot's")
            p.add_argument("--no-pin", action="store_true", help="leave the slow-motion cvar as the state holds it "
                           "(default: one scene tick a frame, pin_pace)")
            p.add_argument("--diverge", type=float, default=0.5, help="m off (or another state or HP) that counts a "
                           "tick as off; 3 in a row end the replay (default 0.5)")
        else:
            p.add_argument("--snapshot", required=True, help="the L3 snapshot of the run's start")
            p.add_argument("--scan", type=int, default=12, help="degrees searched round the last yaw (default 12)")
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = argv[argv.index("--") + 1:] if "--" in argv else []   # add-body's further azurkit build arguments
    a = ap.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    if extra and a.cmd != "add-body":
        ap.error("arguments after -- go to add-body's build only")
    if a.cmd == "record":
        return record(a.W, a.trace, a.meta or a.W / DEMO_META)
    if a.cmd == "add-body":
        return add_body_cli(a.sock, a.body, mode=a.mode, size=a.size, level=a.level, vanilla=a.vanilla,
                            load=not a.no_load, meta=a.meta, extra=extra)
    if a.cmd == "replug":
        return replug(a.W, a.log, a.once)
    rows = trace_lines(a.trace, a.lines)
    if a.cmd == "fit-cams":
        snap = l3.read_snapshot(l3.snapshot_path(a.snapshot, a.store))
        from devkit.sim.l3 import L3   # the engine (Step 4.13a)
        sim = L3(snap, xo.read_file(xo.vanilla_iso(), "default.xbe"), deep=False)
        tr = TickReplay(rows, struct.unpack("<d", sim.read(l3.MAIN_RATE, 8))[0])
        t0 = time.monotonic()
        cams, alts, info = fit_cams(sim, tr, scan_deg=a.scan)
        l3.private_out(a.out, {"snapshot": a.snapshot, "lines": a.lines,
                               "cams": {k: v.hex() for k, v in cams.items()}, "alts": sorted(alts)})
        print(json.dumps({**info, "of": len(tr.by_key) - 1, "seconds": round(time.monotonic() - t0, 1)}))
        return 0 if "error" not in info else 1
    sb = xo.Sandbox.attach(a.W)
    try:
        if a.owner_snapshot:
            if not a.tag.startswith("vm-") or a.tag.startswith("vm-20260704") or not sb.st.get("hdd"):
                raise SystemExit("--owner-snapshot: a vm-* tag of this session's owner on a private drive's clone "
                                 "only (never a July vm-20260704* state)")
            loadable = sb.loadable
            sb.loadable = lambda tag: tag == a.tag or loadable(tag)
        if a.demo_meta:
            tags = json.loads(a.demo_meta.read_text(encoding="utf-8"))["tags"]
            sb.adopt_tags({**tags, **({a.tag: tags[a.like]} if a.like else {})})
        start = start_at(sb, a.tag)
        g = sb.halt()
        cvar = g.u32(l3.SLOW_MOTION)
        held = g.u32(cvar + 4)
        if a.snapshot_as:
            snap = sb.snapshot(a.snapshot_as, store=a.store, here=True)
            start["snapshot"] = {k: snap[k] for k in ("label", "pages", "sha12")}
        if a.check_snapshot:
            want = l3.read_meta(l3.snapshot_path(a.check_snapshot, a.store))["start_sha12"]
            if want != start["start_sha12"]:
                raise SystemExit(f"the start {start['start_sha12']} isn't {a.check_snapshot}'s ({want})")
        if a.no_pin:
            g.write(cvar + 4, struct.pack("<I", held))
        else:
            xo.pin_pace(g)
        rate = struct.unpack("<d", g.read(l3.MAIN_RATE, 8))[0]
        fit = json.loads(a.cams.read_text(encoding="utf-8")) if a.cams else {"cams": {}, "alts": []}
        tr = TickReplay(rows, rate, cams={int(k): bytes.fromhex(v) for k, v in fit["cams"].items()},
                        alts=set(fit["alts"]), diverge=a.diverge)
        if (k0 := round(start["clock"] * rate)) + 1 not in tr.by_key:
            raise SystemExit(f"the start's clock key {k0} isn't where the lines' run starts (its load row's key): "
                             "the tag or the lines are another run's")
        end = replay_ticks(sb, tr)
        out = {"start": {k: start[k] for k in ("tag", "clock", "start_sha12", "snapshot") if k in start},
               "start_key": round(start["clock"] * rate), "pinned": not a.no_pin, "slow_motion_held": held,
               "end": end, **tr.summary()}
        l3.private_out(a.out, {**out, "results": tr.results})
        print(json.dumps(out))
    finally:
        sb.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
